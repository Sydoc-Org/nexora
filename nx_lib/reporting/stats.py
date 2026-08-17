"""Deterministic statistics over a (columns, rows) result set.

Pure stdlib (no pandas/scipy) so it adds no runtime dependency to the WSGI app.
The model decides *what* to compute (the spec); this module computes it exactly
and reproducibly. Numbers never depend on the LLM's arithmetic.

Result-set shape matches what `_run_sql` / table queries return:
``columns`` is a list of field names or ``{"field", "header"}`` dicts, ``rows``
is a list of positional lists. ``spec`` selects the operation and its arguments.
"""

import math
import statistics
from collections import Counter

MAX_STATS_ROWS = 100_000  # defensive cap; callers already row-cap upstream


class StatsError(ValueError):
    """Raised when a stats spec is malformed or references unknown columns."""


def _col_index(columns, field):
    names = [c["field"] if isinstance(c, dict) else c for c in columns]
    if field not in names:
        raise StatsError(f"unknown column: {field!r}")
    return names.index(field)


def _column_values(columns, rows, field, *, drop_null=True):
    idx = _col_index(columns, field)
    vals = [r[idx] for r in rows]
    if drop_null:
        vals = [v for v in vals if v is not None]
    return vals


def _as_numbers(values):
    out = []
    for v in values:
        if isinstance(v, bool):  # bool is an int subclass; exclude
            raise StatsError("non-numeric value in numeric stat")
        if isinstance(v, int | float):
            out.append(float(v))
        else:
            raise StatsError(f"non-numeric value: {v!r}")
    return out


def _describe_one(columns, rows, field):
    idx = _col_index(columns, field)
    raw = [r[idx] for r in rows]
    non_null = [v for v in raw if v is not None]
    numericish = all(isinstance(v, int | float) and not isinstance(v, bool) for v in non_null)
    base = {"count": len(non_null), "nulls": len(raw) - len(non_null)}
    if non_null and numericish:
        nums = [float(v) for v in non_null]
        base.update(
            min=min(nums),
            max=max(nums),
            sum=sum(nums),
            mean=statistics.fmean(nums),
            median=statistics.median(nums),
            stddev=statistics.stdev(nums) if len(nums) > 1 else 0.0,
            variance=statistics.variance(nums) if len(nums) > 1 else 0.0,
        )
    else:
        counts = Counter(non_null)
        base.update(
            distinct=len(counts),
            top=counts.most_common(1)[0][0] if counts else None,
        )
    return base


_AGG_FUNCS = {
    "count": len,
    "sum": sum,
    "min": lambda n: min(n) if n else None,
    "max": lambda n: max(n) if n else None,
    "mean": lambda n: statistics.fmean(n) if n else None,
    "median": lambda n: statistics.median(n) if n else None,
    "stddev": lambda n: statistics.stdev(n) if len(n) > 1 else 0.0,
}


def _check_func(fn):
    if fn not in _AGG_FUNCS:
        raise StatsError(f"unknown agg function: {fn!r}")
    return True


def _percentile(sorted_nums, q):
    if not sorted_nums:
        raise StatsError("percentile of empty column")
    if not 0.0 <= q <= 1.0:
        raise StatsError(f"quantile out of range: {q}")
    if len(sorted_nums) == 1:
        return sorted_nums[0]
    pos = q * (len(sorted_nums) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return sorted_nums[lo]
    frac = pos - lo
    return sorted_nums[lo] * (1 - frac) + sorted_nums[hi] * frac


def _group_by(columns, rows, by, agg):
    by_idx = [_col_index(columns, f) for f in by]
    agg_idx = {f: _col_index(columns, f) for f in agg}
    buckets = {}
    for r in rows:
        key = tuple(r[i] for i in by_idx)
        buckets.setdefault(key, []).append(r)
    result = []
    for key in sorted(buckets, key=lambda k: tuple((v is None, str(v)) for v in k)):
        group_rows = buckets[key]
        values = {}
        for field, funcs in agg.items():
            nums = _as_numbers(
                [gr[agg_idx[field]] for gr in group_rows if gr[agg_idx[field]] is not None]
            )
            values[field] = {fn: _AGG_FUNCS[fn](nums) for fn in funcs if _check_func(fn)}
        result.append({"group": list(key), "values": values})
    return result


def _require(spec, key):
    val = spec.get(key)
    if val is None:
        raise StatsError(f"{spec.get('op')!r} requires {key!r}")
    return val


def compute_stats(columns, rows, spec):
    """Compute `spec` over the result set. Returns ``{"op": ..., "result": ...}``."""
    if not isinstance(spec, dict):
        raise StatsError("spec must be an object")
    if len(rows) > MAX_STATS_ROWS:
        raise StatsError(f"too many rows for stats: {len(rows)} > {MAX_STATS_ROWS}")
    op = spec.get("op")
    if op == "describe":
        fields = spec.get("columns") or []
        if not fields:
            raise StatsError("describe requires a non-empty 'columns' list")
        return {
            "op": op,
            "result": {f: _describe_one(columns, rows, f) for f in fields},
        }
    if op == "group_by":
        by = spec.get("by") or []
        agg = spec.get("agg") or {}
        if not by or not agg:
            raise StatsError("group_by requires 'by' and 'agg'")
        return {"op": op, "result": _group_by(columns, rows, by, agg)}
    if op == "percentiles":
        nums = sorted(_as_numbers(_column_values(columns, rows, _require(spec, "column"))))
        qs = spec.get("q") or [0.5]
        return {"op": op, "result": {str(q): _percentile(nums, q) for q in qs}}
    if op == "value_counts":
        vals = _column_values(columns, rows, _require(spec, "column"))
        counts = Counter(vals).most_common(spec.get("top_n"))
        return {"op": op, "result": [{"value": v, "count": c} for v, c in counts]}
    if op == "correlation":
        xs = _as_numbers(_column_values(columns, rows, _require(spec, "x"), drop_null=False))
        ys = _as_numbers(_column_values(columns, rows, _require(spec, "y"), drop_null=False))
        if len(xs) != len(ys) or len(xs) < 2:
            raise StatsError("correlation needs two equal-length numeric columns (n>=2)")
        try:
            r = statistics.correlation(xs, ys)
        except statistics.StatisticsError as e:
            raise StatsError(str(e)) from e
        return {"op": op, "result": {"r": r, "n": len(xs)}}
    if op == "top_n":
        idx = _col_index(columns, _require(spec, "by"))
        ascending = bool(spec.get("ascending"))
        keyed = [r for r in rows if r[idx] is not None]
        keyed.sort(key=lambda r: r[idx], reverse=not ascending)
        return {"op": op, "result": keyed[: int(spec.get("n", 10))]}
    raise StatsError(f"unknown stats op: {op!r}")
