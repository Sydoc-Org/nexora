"""Layout measures: derived statistics over one run result.

A *layout* (a saved report with kind 'layout' — the user-facing "Report
definition") lists measures such as mean / percentile / current value. This
module computes them over the (columns, rows) a report run returned, exactly
like forecast.py post-processes the same rows. Pure stdlib, Flask-free.

Each measure resolves to ``{"op", "value", "n"}`` (``minmax`` → ``min``/``max``)
or ``{"op", "unavailable": reason}``. Data problems never raise — one bad tile
must not take down the run. A malformed layout (unknown op) raises ValueError;
callers validate with schema.validate_layout_definition first.

Adding an op later (delta, growth rate, trend, target gap …) is one entry in
OPS plus a test.
"""

import re
import statistics

from .stats import MAX_STATS_ROWS as MAX_ROWS
from .stats import _percentile

METRIC_COLUMN_UNAVAILABLE = "no_numeric_column"
_DATE_FIELD = re.compile(r"date", re.I)


def _field(col):
    return col["field"] if isinstance(col, dict) else col


def _is_num(v):
    return isinstance(v, int | float) and not isinstance(v, bool)


def _to_num(v):
    """Coerce a raw DB cell to float, or None when it isn't numeric.

    Raw pyodbc rows can carry decimal.Decimal (SUM/AVG over a decimal/money
    column) — isinstance(v, int | float) rejects that, so coerce via a
    try/except instead (same pattern as forecast.py). bool is excluded
    explicitly: it's int-coercible but must never count as numeric.
    """
    if isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _metric_column_index(rd, columns, rows):
    """Index of the column to measure: the first declared metric, else the
    first column whose non-null cells are all numeric. None when nothing fits."""
    names = [_field(c) for c in columns]
    for m in rd.get("metrics") or []:
        code = m.get("metric") if isinstance(m, dict) else None
        if code in names:
            return names.index(code)
    for i in range(len(names)):
        cells = [r[i] for r in rows if r[i] is not None]
        if cells and all(_to_num(v) is not None for v in cells):
            return i
    return None


def _numbers(rows, idx):
    out = []
    for r in rows:
        n = _to_num(r[idx])
        if n is not None:
            out.append(n)
    return out


def _single_date_dimension(rd):
    cols = rd.get("columns") or []
    if len(cols) != 1 or not isinstance(cols[0], dict):
        return False
    return bool(cols[0].get("grain")) or bool(_DATE_FIELD.search(str(cols[0].get("field", ""))))


def _current(nums, ctx):
    if _single_date_dimension(ctx["rd"]):
        # Latest bucket by the first column's string order (ISO dates sort).
        dated = [
            (str(r[0]), r[ctx["idx"]])
            for r in ctx["rows"]
            if r[0] is not None and _is_num(r[ctx["idx"]])
        ]
        if dated:
            return float(max(dated)[1])
    return sum(nums)


def _minmax(nums, ctx):
    return {"min": min(nums), "max": max(nums)}


def _delta(nums, ctx):
    """Total now minus total over the comparison window (the standard band's
    "vs previous period" chip). Needs the run's comparison rows; without them
    the measure is unavailable rather than wrong."""
    prior_rows = ctx.get("comparison_rows")
    if prior_rows is None:
        return {"unavailable": NO_COMPARISON_UNAVAILABLE}
    prior = _numbers(prior_rows, ctx["idx"])
    cur, prev = sum(nums), sum(prior)
    out = {"value": cur - prev, "prior": prev}
    if prev:
        out["pct"] = (cur - prev) / abs(prev)
    return out


NO_COMPARISON_UNAVAILABLE = "no_comparison"

OPS = {
    "current": _current,
    "total": lambda nums, ctx: sum(nums),
    "buckets": lambda nums, ctx: float(len(nums)),
    "avg_bucket": lambda nums, ctx: sum(nums) / len(nums),
    "mean": lambda nums, ctx: statistics.fmean(nums),
    "median": lambda nums, ctx: statistics.median(nums),
    "minmax": _minmax,
    "range": lambda nums, ctx: max(nums) - min(nums),
    "stddev": lambda nums, ctx: statistics.stdev(nums) if len(nums) > 1 else 0.0,
    "percentile": lambda nums, ctx: _percentile(sorted(nums), ctx["measure"].get("q", 0.5)),
    "delta": _delta,
}


def compute_derived(layout, rd, columns, rows, comparison_rows=None):
    measures = layout.get("measures") or []
    for m in measures:
        if m.get("op") not in OPS:
            raise ValueError(f"unknown measure op: {m.get('op')!r}")
    out = {}
    if len(rows) > MAX_ROWS:
        return {m["id"]: {"op": m["op"], "unavailable": "too_many_rows"} for m in measures}
    idx = _metric_column_index(rd, columns, rows) if rows else None
    for m in measures:
        if not rows:
            out[m["id"]] = {"op": m["op"], "unavailable": "no_rows"}
            continue
        if idx is None:
            out[m["id"]] = {"op": m["op"], "unavailable": METRIC_COLUMN_UNAVAILABLE}
            continue
        nums = _numbers(rows, idx)
        if not nums:
            out[m["id"]] = {"op": m["op"], "unavailable": METRIC_COLUMN_UNAVAILABLE}
            continue
        res = OPS[m["op"]](
            nums,
            {"rd": rd, "rows": rows, "idx": idx, "measure": m, "comparison_rows": comparison_rows},
        )
        entry = {"op": m["op"], "n": len(nums)}
        if isinstance(res, dict):
            entry.update(res)
            if "unavailable" in res:
                entry.pop("n", None)
        else:
            entry["value"] = float(res)
        if m["op"] == "percentile":
            entry["q"] = m.get("q", 0.5)
        out[m["id"]] = entry
    return out
