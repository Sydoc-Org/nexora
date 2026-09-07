"""Contribution analysis ("Why did it move?") — Flask-free maths.

Given a Simple definition whose KPI band shows a delta chip, explain the
change vs. the shifted prior window by decomposing the first metric along a
few categorical dimensions. The view layer (nx_lib/views/reporting/run.py,
api_contribution) does the I/O; everything here is pure so the later Eddard
weekly card can call it without HTTP.
"""

import copy
from typing import Any

from .sources import MAX_ROW_LIMIT

EMPTY_LABEL = "(empty)"
OTHER_LABEL = "(other)"
RATIO_AGGREGATIONS = {"avg", "min", "max", "count_distinct"}


def pick_dimensions(catalog, filters, *, cap=3):
    """Catalog entries to decompose by: processname first when present, then
    string-typed entries in catalog order; never workitem_id, never a field a
    single-value `eq` filter already pins. At most `cap` entries."""
    pinned = {
        f.get("field") for f in (filters or []) if isinstance(f, dict) and f.get("op") == "eq"
    }
    by_field = {c["field"]: c for c in catalog or []}
    out = []
    if "processname" in by_field and "processname" not in pinned:
        out.append(by_field["processname"])
    for c in catalog or []:
        if len(out) >= cap:
            break
        f = c.get("field")
        if f in ("processname", "workitem_id") or f in pinned:
            continue
        if c.get("type") != "string":
            continue
        out.append(c)
    return out[:cap]


def single_dimension_definition(rd, field, metric_code):
    """Deep copy of `rd` grouped by exactly one column with exactly one metric,
    ready for _prepare_run. Tokens stay intact (the run path resolves them)."""
    out = copy.deepcopy(rd)
    out["columns"] = [{"field": field}]
    out["metrics"] = [{"metric": metric_code}]
    out["sort"] = []
    out["rowLimit"] = MAX_ROW_LIMIT
    out.pop("forecast", None)
    out.pop("compare", None)
    return out


def is_ratio_metric(metric_def):
    """True for aggregations whose per-group values do not sum to the total —
    a 'share of the change' is meaningless for them (avg/min/max/distinct)."""
    agg = (metric_def or {}).get("aggregation")
    return agg in RATIO_AGGREGATIONS


def _num(v):
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _label(v):
    return EMPTY_LABEL if v is None or v == "" else str(v)


def contribution_rows(current_rows, prior_rows, *, top=8):
    """Full outer join of two [value, metric] row lists on value, delta per
    value, sorted by |delta| desc. Keeps `top` rows and folds the rest into
    one '(other)' row. `share` is left None — fill_shares sets it once the
    caller knows the grand totals (D3)."""
    joined: dict[str, list[float]] = {}
    for v, m in current_rows or []:
        joined.setdefault(_label(v), [0.0, 0.0])[0] += _num(m)
    for v, m in prior_rows or []:
        joined.setdefault(_label(v), [0.0, 0.0])[1] += _num(m)
    rows: list[dict[str, Any]] = [
        {"value": k, "current": c, "prior": p, "delta": c - p, "share": None}
        for k, (c, p) in joined.items()
    ]
    rows.sort(key=lambda r: (-abs(r["delta"]), r["value"]))
    head, tail = rows[:top], rows[top:]
    if tail:
        c = sum(r["current"] for r in tail)
        p = sum(r["prior"] for r in tail)
        head.append({"value": OTHER_LABEL, "current": c, "prior": p, "delta": c - p, "share": None})
    return head


def fill_shares(dimensions, total_delta, is_ratio):
    """share = delta / total_delta, or None for ratio metrics / a zero total."""
    usable = (not is_ratio) and bool(total_delta)
    for d in dimensions:
        for r in d.get("rows", []):
            r["share"] = (r["delta"] / total_delta) if usable else None
