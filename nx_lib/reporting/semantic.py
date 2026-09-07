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
        anchor = spec.get("anchor")
        if anchor:
            # Date-anchored metric: the builder projects a per-leg counter
            # column aliased to the metric code and the outer query SUMs that
            # alias — so base_field becomes the code itself, and the registry
            # BaseField (if any) is the per-row value column (e.g. pagecount),
            # validated against the catalog like any aggregate base.
            if agg != "sum":
                raise MetricResolveError(f"anchored metric {code!r} must aggregate with sum")
            value = spec.get("base_field")
            if value is not None:
                if not isinstance(value, str) or not _CODE.match(value):
                    raise MetricResolveError(f"unsafe metric base field: {value!r}")
                if value not in catalog_fields:
                    raise MetricResolveError(f"metric base field not in catalog: {value!r}")
            seen.add(code)
            out.append(
                {
                    "code": code,
                    "aggregation": "sum",
                    "base_field": code,
                    "anchor": anchor,
                    "value_field": value,
                }
            )
            continue
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
        resolved = {"code": code, "aggregation": agg, "base_field": base}
        cond = _resolve_condition(spec.get("filter"), catalog_fields, code)
        if cond:
            resolved["filter"] = cond
        out.append(resolved)
    return out


# Conditional metrics: a registry row may carry a condition (dbo.ReportingMetrics
# .FilterJson, parsed to a list of {field, op, value}) that turns the aggregate
# into CASE WHEN <cond> THEN <x> END -- "documents where OnTime = 1" as one
# number instead of a breakdown the reader sums by eye. Fields are whitelisted
# against the catalog, ops come from this enum, values are always parameters.
_COND_OPS = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
_COND_SET_OPS = {"in": "IN", "not_in": "NOT IN"}
_COND_NULL_OPS = {"is_null": "IS NULL", "is_not_null": "IS NOT NULL"}
_SCALAR = (str, int, float, bool)


def _resolve_condition(filt, catalog_fields, code):
    if not filt:
        return None
    if not isinstance(filt, list):
        raise MetricResolveError(f"metric {code!r}: filter must be a list of clauses")
    out = []
    for cl in filt:
        if not isinstance(cl, dict):
            raise MetricResolveError(f"metric {code!r}: filter clause must be an object")
        field, op, val = cl.get("field"), cl.get("op"), cl.get("value")
        if not isinstance(field, str) or not _CODE.match(field):
            raise MetricResolveError(f"metric {code!r}: unsafe filter field {field!r}")
        if field not in catalog_fields:
            raise MetricResolveError(f"metric {code!r}: filter field not in catalog: {field!r}")
        if op in _COND_OPS:
            if not isinstance(val, _SCALAR):
                raise MetricResolveError(f"metric {code!r}: {op} needs a scalar value")
        elif op in _COND_SET_OPS:
            if not isinstance(val, list) or not val or not all(isinstance(v, _SCALAR) for v in val):
                raise MetricResolveError(f"metric {code!r}: {op} needs a non-empty list")
        elif op in _COND_NULL_OPS:
            val = None
        else:
            raise MetricResolveError(f"metric {code!r}: unsupported filter op {op!r}")
        out.append({"field": field, "op": op, "value": val})
    return out


def condition_fields(resolved_metrics):
    """Catalog fields a resolved metric list's conditions reference (deduped)."""
    return list(
        dict.fromkeys(cl["field"] for m in resolved_metrics or [] for cl in m.get("filter") or [])
    )


def _condition_sql(clauses, col_for_field, params):
    parts = []
    for cl in clauses:
        col = col_for_field(cl["field"])
        op, val = cl["op"], cl["value"]
        if op in _COND_OPS:
            parts.append(f"{col} {_COND_OPS[op]} ?")
            params.append(val)
        elif op in _COND_SET_OPS:
            parts.append(f"{col} {_COND_SET_OPS[op]} ({','.join('?' * len(val))})")
            params.extend(val)
        else:
            parts.append(f"{col} {_COND_NULL_OPS[op]}")
    return " AND ".join(parts)


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


def metric_select_expr(resolved, col_for_field, params=None):
    """Build 'AGG(col) AS [code]'. `col_for_field(field)` returns a safe, already
    bracket-quoted column reference, keeping this provider-agnostic.

    A conditional metric wraps its argument in CASE WHEN <cond> THEN ... END and
    appends the condition's parameter values to `params` (SELECT-list params
    precede WHERE params in positional order, so callers prepend them)."""
    code = resolved["code"]
    agg = resolved["aggregation"]
    cond = resolved.get("filter")
    if cond:
        if params is None:
            raise MetricResolveError(f"metric {code!r}: conditional metric needs a params list")
        when = _condition_sql(cond, col_for_field, params)
        arg = "1" if agg == "count" else col_for_field(resolved["base_field"])
        inner = f"CASE WHEN {when} THEN {arg} END"
        fn = "COUNT({})" if agg == "count" else _AGG_SQL[agg]
        return f"{fn.format(inner)} AS [{code}]"
    if agg == "count":
        return f"COUNT(*) AS [{code}]"
    return f"{_AGG_SQL[agg].format(col_for_field(resolved['base_field']))} AS [{code}]"


def build_aggregate_sql(
    *, inner_from, dim_fields, resolved_metrics, sort, cap, dim_exprs=None, params_out=None
):
    """Assemble `SELECT TOP(cap) <dims>, <agg exprs> FROM <inner_from>
    GROUP BY <dims> [ORDER BY ...]`.

    `inner_from` is an already-safe FROM body (a bracket-quoted object, or a
    `(<union>) t` subquery). `dim_fields` are whitelisted field keys projected as
    `[field]`; the same alias names back the aggregate columns. Empty dim_fields
    yields a global aggregate with no GROUP BY (zero-dimension grand total).
    `dim_exprs` optionally maps a dim field to a raw SQL expression (e.g. a date-
    grain bucketing expression) to project/group by instead of the bare column;
    the field's alias is preserved either way. Sort may target a dim or a metric
    code; anything else raises (defence in depth). Conditional metrics append
    their SELECT-list parameter values to `params_out` (required when any
    resolved metric carries a filter)."""
    dim_exprs = dim_exprs or {}

    def bracket(field):
        return f"[{field}]"

    def dim_expr(field):
        return dim_exprs.get(field, bracket(field))

    dim_select = ", ".join(
        f"{dim_expr(d)} AS {bracket(d)}" if d in dim_exprs else bracket(d) for d in dim_fields
    )
    metric_exprs = ", ".join(metric_select_expr(m, bracket, params_out) for m in resolved_metrics)
    select_list = ", ".join(p for p in (dim_select, metric_exprs) if p)
    sql = f"SELECT TOP ({int(cap)}) {select_list} FROM {inner_from}"
    if dim_fields:
        sql += " GROUP BY " + ", ".join(dim_expr(d) for d in dim_fields)

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
