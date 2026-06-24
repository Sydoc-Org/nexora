# nx_lib/reporting/semantic.py
"""Resolve canonical metrics into concrete aggregation specs and GROUP BY SQL.

Pure + DB-free: the metric registry rows and the source's whitelisted catalog
are injected, so this is unit-testable without a DB. Security: the aggregated
column and the metric alias are whitelist/identifier-validated; the aggregation
function comes from a fixed enum. This is the same boundary the row builders
(query.py / table_query.py) enforce -- only filter *values* are ever parameters.
"""

import re

AGGREGATIONS = {"count", "count_distinct", "sum", "avg", "min", "max"}
_CODE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class MetricResolveError(ValueError):
    """Raised when a report's metrics cannot be resolved safely."""


def resolve_metrics(metric_refs, metric_registry, catalog_fields):
    """Resolve `metric_refs` (rd['metrics'] = [{'metric': code}, ...]).

    metric_registry: {code: {'aggregation', 'base_field'}}.
    catalog_fields: set of the source's whitelisted column keys.
    Returns [{'code', 'aggregation', 'base_field'}] preserving order.
    Raises MetricResolveError on unknown/duplicate/unsafe/whitelist-miss.
    """
    out = []
    seen = set()
    for ref in metric_refs or []:
        if not isinstance(ref, dict):
            raise MetricResolveError("metric ref must be an object")
        code = ref.get("metric")
        if not isinstance(code, str) or not _CODE.match(code):
            raise MetricResolveError(f"unsafe metric code: {code!r}")
        if code in seen:
            raise MetricResolveError(f"duplicate metric: {code!r}")
        spec = metric_registry.get(code)
        if spec is None:
            raise MetricResolveError(f"unknown metric: {code!r}")
        agg = spec.get("aggregation")
        if agg not in AGGREGATIONS:
            raise MetricResolveError(f"unsupported aggregation: {agg!r}")
        base = spec.get("base_field")
        if agg == "count":
            base = None
        else:
            # Defence in depth: base_field is bracketed into the aggregate
            # expression, so identifier-validate it (symmetric with `code`)
            # before the catalog membership check — a corrupted registry row
            # must never reach the SQL with an unsafe identifier.
            if not isinstance(base, str) or not _CODE.match(base):
                raise MetricResolveError(f"unsafe metric base field: {base!r}")
            if base not in catalog_fields:
                raise MetricResolveError(f"metric base field not in catalog: {base!r}")
        seen.add(code)
        out.append({"code": code, "aggregation": agg, "base_field": base})
    return out


def drop_columns_shadowing_distinct_metrics(rd, metric_registry):
    """Remove grouping columns that name the very field a count_distinct
    metric aggregates — GROUP BY the counted field forces every count to 1,
    so such a draft is always wrong. Mutates `rd` in place (same contract as
    coerce_definition); returns the list of dropped field keys."""
    distinct_bases = set()
    for ref in rd.get("metrics") or []:
        spec = metric_registry.get((ref or {}).get("metric")) or {}
        if spec.get("aggregation") == "count_distinct" and spec.get("base_field"):
            distinct_bases.add(spec["base_field"])
    if not distinct_bases:
        return []
    cols = rd.get("columns") or []
    dropped = [c.get("field") for c in cols if c.get("field") in distinct_bases]
    if dropped:
        rd["columns"] = [c for c in cols if c.get("field") not in distinct_bases]
    return dropped


_AGG_SQL = {
    "count_distinct": "COUNT(DISTINCT {})",
    "sum": "SUM({})",
    "avg": "AVG({})",
    "min": "MIN({})",
    "max": "MAX({})",
}
_SORT_DIRS = {"asc": "ASC", "desc": "DESC"}


def metric_select_expr(resolved, col_for_field):
    """Build 'AGG(col) AS [code]'. `col_for_field(field)` returns a safe, already
    bracket-quoted column reference, keeping this provider-agnostic."""
    code = resolved["code"]
    agg = resolved["aggregation"]
    if agg == "count":
        return f"COUNT(*) AS [{code}]"
    return f"{_AGG_SQL[agg].format(col_for_field(resolved['base_field']))} AS [{code}]"


def build_aggregate_sql(*, inner_from, dim_fields, resolved_metrics, sort, cap):
    """Assemble `SELECT TOP(cap) <dims>, <agg exprs> FROM <inner_from>
    GROUP BY <dims> [ORDER BY ...]`.

    `inner_from` is an already-safe FROM body (a bracket-quoted object, or a
    `(<union>) t` subquery). `dim_fields` are whitelisted field keys projected as
    `[field]`; the same alias names back the aggregate columns. Empty dim_fields
    yields a global aggregate with no GROUP BY (zero-dimension grand total).
    Sort may target a dim or a metric code; anything else raises (defence in
    depth)."""

    def bracket(field):
        return f"[{field}]"

    dim_select = ", ".join(bracket(d) for d in dim_fields)
    metric_exprs = ", ".join(metric_select_expr(m, bracket) for m in resolved_metrics)
    select_list = ", ".join(p for p in (dim_select, metric_exprs) if p)
    sql = f"SELECT TOP ({int(cap)}) {select_list} FROM {inner_from}"
    if dim_fields:
        sql += " GROUP BY " + ", ".join(bracket(d) for d in dim_fields)

    projected = set(dim_fields) | {m["code"] for m in resolved_metrics}
    order_parts = []
    for s in sort or []:
        field = s.get("field")
        if field not in projected:
            raise MetricResolveError(f"sort field not projected: {field!r}")
        direction = _SORT_DIRS.get(str(s.get("dir")).lower())
        if direction is None:
            raise MetricResolveError(f"invalid sort dir: {s.get('dir')!r}")
        order_parts.append(f"[{field}] {direction}")
    if order_parts:
        sql += " ORDER BY " + ", ".join(order_parts)
    return sql
