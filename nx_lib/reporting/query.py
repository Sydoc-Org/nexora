# nx_lib/reporting/query.py
"""Translate a validated report definition into a parameterized SQL query.

build_table_query is pure: it receives the report definition and injected
per-process configs + column maps (so it is DB-free and unit-testable), and
returns (sql, params) for the statistics engine. Every column/table name comes
from the injected maps/configs; only filter *values* become ? parameters.
"""

from .semantic import build_aggregate_sql

_OP_SQL = {
    "eq": "= ?",
    "ne": "<> ?",
    "gt": "> ?",
    "gte": ">= ?",
    "lt": "< ?",
    "lte": "<= ?",
    "is_null": "IS NULL",
    "is_not_null": "IS NOT NULL",
}

_SORT_DIRS = {"ASC", "DESC"}

# Filter ops handled specially below (not via the _OP_SQL binary-op fallback).
_SPECIAL_OPS = {"in", "not_in", "between", "contains", "starts_with"}


class QueryBuildError(ValueError):
    """Raised when a report definition cannot be turned into SQL."""


def _escape_like(value):
    """Escape LIKE metacharacters so user values are matched literally.

    Backslash is the ESCAPE char, so escape it first; then %, _ and [ (the
    SQL Server LIKE wildcards / character-class opener).
    """
    text = str(value)
    text = text.replace("\\", "\\\\")
    text = text.replace("%", "\\%")
    text = text.replace("_", "\\_")
    text = text.replace("[", "\\[")
    return text


def _filter_clause(col, op, value, params):
    """Append a single filter clause for `col`. Returns the SQL fragment."""
    if op not in _OP_SQL and op not in _SPECIAL_OPS:
        raise QueryBuildError(f"unsupported filter op: {op!r}")
    if op in ("is_null", "is_not_null"):
        return f"{col} {_OP_SQL[op]}"
    if op in ("in", "not_in"):
        if value is None:
            value = []
        values = value if isinstance(value, list) else [value]
        if not values:
            # empty IN — make it match nothing / everything safely
            return "1 = 0" if op == "in" else "1 = 1"
        placeholders = ", ".join(["?"] * len(values))
        params.extend(values)
        keyword = "IN" if op == "in" else "NOT IN"
        return f"{col} {keyword} ({placeholders})"
    if op == "between":
        if not isinstance(value, list) or len(value) != 2:
            raise QueryBuildError("between requires a 2-element list")
        params.extend(value)
        return f"{col} BETWEEN ? AND ?"
    if op == "contains":
        params.append(f"%{_escape_like(value)}%")
        return f"{col} LIKE ? ESCAPE '\\'"
    if op == "starts_with":
        params.append(f"{_escape_like(value)}%")
        return f"{col} LIKE ? ESCAPE '\\'"
    # simple binary ops (eq, ne, gt, gte, lt, lte)
    params.append(value)
    return f"{col} {_OP_SQL[op]}"


def _scope_by_processname(process_configs, filters):
    """Narrow process_configs by any `processname` filters.

    A processname filter restricts *which* process subqueries are produced
    rather than emitting a WHERE clause (the projected processname is a constant
    per subquery). Supports eq/ne/in/not_in; other ops on processname raise.
    """
    result = list(process_configs)
    for f in filters:
        if f["field"] != "processname":
            continue
        op = f["op"]
        value = f.get("value")
        if op == "eq":
            result = [c for c in result if c["process"] == value]
        elif op == "ne":
            result = [c for c in result if c["process"] != value]
        elif op == "in":
            wanted = set(value or [])
            result = [c for c in result if c["process"] in wanted]
        elif op == "not_in":
            excluded = set(value or [])
            result = [c for c in result if c["process"] not in excluded]
        else:
            raise QueryBuildError(f"unsupported processname filter op: {op!r}")
    return result


def build_table_query(rd, process_configs, field_col_maps, *, row_cap, resolved_metrics=None):
    """Build (sql, params) for a table report.

    process_configs: [{process, table, export_col, import_col, condition}] already
      filtered to the effective (permitted ∩ requested) process scope.
    field_col_maps: {process: {field_key: actual_column_name}}.
    row_cap: server-enforced TOP cap (min of definition rowLimit and server max).
    resolved_metrics: optional list of resolved metric specs from semantic.resolve_metrics.
      When non-empty the UNION is wrapped in an outer GROUP BY aggregate query.

    Column/table names come exclusively from process_configs and field_col_maps
    (injected, not from the report definition directly). Only filter *values*
    are passed as ? parameters — this is the SQL-injection security boundary.
    """
    if not process_configs:
        raise QueryBuildError("no processes in scope")

    columns = [c["field"] for c in rd["columns"]]
    filters = rd.get("filters") or []
    sort = rd.get("sort") or []
    cap = min(int(rd.get("rowLimit", row_cap)), int(row_cap))

    metric_base_fields = [m["base_field"] for m in (resolved_metrics or []) if m.get("base_field")]
    # Fields to project in each subquery: the group-by dims plus any metric base
    # fields (deduped, order-stable). For the row path this is just `columns`.
    projected_fields = list(dict.fromkeys(columns + metric_base_fields))

    # Validate that every requested column field is known across all maps.
    # "processname" is a synthetic field always available; others must appear
    # in at least one process's field_col_map so we don't silently project NULL
    # for entirely unknown fields that could indicate a client-side injection
    # attempt (the schema validator should have caught this first, but we
    # enforce it here as a defence-in-depth check).
    all_known_fields = {"processname"}
    for colmap in field_col_maps.values():
        all_known_fields.update(colmap.keys())
    for field in columns:
        if field not in all_known_fields:
            raise QueryBuildError(f"unknown column field: {field!r}")

    # A `processname` filter selects which process subqueries are included; it
    # is NOT a column WHERE clause (the value would never match the synthetic
    # constant). Apply it up front by narrowing process_configs, comparing the
    # filter value(s) to each cfg["process"]. Non-processname filters stay in
    # `col_filters` and become parameterized WHERE clauses per subquery.
    process_configs = _scope_by_processname(process_configs, filters)
    if not process_configs:
        raise QueryBuildError("no processes in scope after processname filter")
    col_filters = [f for f in filters if f["field"] != "processname"]

    sub_queries = []
    params = []
    for cfg in process_configs:
        colmap = field_col_maps.get(cfg["process"], {})

        # A filter referencing a field this process doesn't expose can never
        # match here — drop the whole subquery for correctness.
        if any(f["field"] not in colmap for f in col_filters):
            continue

        select_exprs = []
        for field in projected_fields:
            if field == "processname":
                select_exprs.append("? AS [processname]")
                params.append(cfg["process"])
            else:
                actual = colmap.get(field)
                if actual:
                    select_exprs.append(f"{actual} AS [{field}]")
                else:
                    select_exprs.append(f"NULL AS [{field}]")

        where = ["1 = 1"]
        for f in col_filters:
            col = colmap.get(f["field"])
            if not col:
                continue
            where.append(_filter_clause(col, f["op"], f.get("value"), params))
        cond = f" {cfg['condition']}" if cfg.get("condition") else ""
        sub_queries.append(
            f"SELECT {', '.join(select_exprs)} FROM [{cfg['table']}] "
            f"WHERE {' AND '.join(where)}{cond}"
        )

    if not sub_queries:
        raise QueryBuildError("no subqueries produced for the requested scope/filters")

    inner = " UNION ALL ".join(sub_queries)

    if resolved_metrics:
        sql = build_aggregate_sql(
            inner_from=f"({inner}) t",
            dim_fields=columns,
            resolved_metrics=resolved_metrics,
            sort=sort,
            cap=cap,
        )
        return sql, params

    out_cols = ", ".join(f"[{c}]" for c in columns)
    sql = f"SELECT TOP ({cap}) {out_cols} FROM ({inner}) t"
    if sort:
        projected = set(columns)
        order_parts = []
        for s in sort:
            field = s["field"]
            direction = str(s["dir"]).upper()
            if direction not in _SORT_DIRS:
                raise QueryBuildError(f"invalid sort direction: {s['dir']!r}")
            if field not in projected:
                raise QueryBuildError(f"sort field {field!r} not in projection")
            order_parts.append(f"[{field}] {direction}")
        sql += f" ORDER BY {', '.join(order_parts)}"
    return sql, params
