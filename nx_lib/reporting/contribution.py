"""Contribution analysis ("Why did it move?") — Flask-free maths.

Given a Simple definition whose KPI band shows a delta chip, explain the
change vs. the shifted prior window by decomposing the first metric along a
few categorical dimensions. The view layer (nx_lib/views/reporting/run.py,
api_contribution) does the I/O; everything here is pure so the later Eddard
weekly card can call it without HTTP.
"""

import copy

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


def is_ratio_metric(metric_def):  # Task 2
    raise NotImplementedError


def contribution_rows(current_rows, prior_rows, *, top=8):  # Task 2
    raise NotImplementedError


def fill_shares(dimensions, total_delta, is_ratio):  # Task 2
    raise NotImplementedError
