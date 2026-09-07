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

from .stats import _percentile

MAX_ROWS = 100_000  # same ceiling as stats.MAX_STATS_ROWS
METRIC_COLUMN_UNAVAILABLE = "no_numeric_column"
_DATE_FIELD = re.compile(r"date", re.I)


def _field(col):
    return col["field"] if isinstance(col, dict) else col


def _is_num(v):
    return isinstance(v, int | float) and not isinstance(v, bool)


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
        if cells and all(_is_num(v) for v in cells):
            return i
    return None


def _numbers(rows, idx):
    return [float(r[idx]) for r in rows if _is_num(r[idx])]


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


OPS = {
    "current": _current,
    "mean": lambda nums, ctx: statistics.fmean(nums),
    "minmax": _minmax,
    "range": lambda nums, ctx: max(nums) - min(nums),
    "stddev": lambda nums, ctx: statistics.stdev(nums) if len(nums) > 1 else 0.0,
    "percentile": lambda nums, ctx: _percentile(sorted(nums), ctx["measure"].get("q", 0.5)),
}


def compute_derived(layout, rd, columns, rows):
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
        res = OPS[m["op"]](nums, {"rd": rd, "rows": rows, "idx": idx, "measure": m})
        entry = {"op": m["op"], "n": len(nums)}
        if isinstance(res, dict):
            entry.update(res)
        else:
            entry["value"] = float(res)
        if m["op"] == "percentile":
            entry["q"] = m.get("q", 0.5)
        out[m["id"]] = entry
    return out
