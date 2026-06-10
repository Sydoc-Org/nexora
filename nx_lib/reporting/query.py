# nx_lib/reporting/query.py
"""Translate a validated report definition into a parameterized SQL query.

build_table_query is pure: it receives the report definition and injected
per-process configs + column maps (so it is DB-free and unit-testable), and
returns (sql, params) for the statistics engine. Every column/table name comes
from the injected maps/configs; only filter *values* become ? parameters.
"""

import re

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

_DATE_GRAINS = {"day", "week", "month", "quarter", "year"}

# Synthetic date field -> the process-config key holding its raw column expression.
_DATE_FIELD_COL = {"import_date": "import_col", "export_date": "export_col"}

# Synthetic workitem-id field -> the process-config key with its column name.
# Always projected via CAST(... AS nvarchar(100)): the per-process workitem
# columns have mixed types (nvarchar / int / numeric), and an unnormalized
# UNION ALL would coerce by type precedence and fail on non-numeric ids.
_WORKITEM_FIELD_COL = {"workitem_id": "workitem_col"}


def _date_base(col_expr):
    """Normalize a Statconfig date column to a DATE-typed expression, mirroring
    the dashboard: a value already containing CONVERT(...) is trusted as-is;
    otherwise wrap with CAST(... AS date). The expression originates only from
    Statconfig (server config), never the client."""
    return col_expr if "convert" in col_expr.lower() else f"CAST({col_expr} AS date)"


def _grain_sql(d, grain):
    """Wrap a DATE expression `d` for the requested grain. None/'day' = raw.
    Month/quarter/year via DATEFROMPARTS; week is Monday-anchored and
    DATEFIRST-independent."""
    if grain in (None, "day"):
        return d
    if grain == "week":
        return f"DATEADD(week, DATEDIFF(week, 0, {d}), 0)"
    if grain == "month":
        return f"DATEFROMPARTS(YEAR({d}), MONTH({d}), 1)"
    if grain == "quarter":
        return f"DATEFROMPARTS(YEAR({d}), (DATEPART(quarter, {d}) - 1) * 3 + 1, 1)"
    if grain == "year":
        return f"DATEFROMPARTS(YEAR({d}), 1, 1)"
    raise QueryBuildError(f"unsupported date grain: {grain!r}")


def _date_exprs_for(cfg, grain_by_field):
    """{date_field: sql_expr} for the date fields this process exposes, applying
    each field's grain (grain_by_field maps field -> grain; missing = raw)."""
    out = {}
    for field, cfg_key in _DATE_FIELD_COL.items():
        col = cfg.get(cfg_key)
        if col:
            out[field] = _grain_sql(_date_base(col), grain_by_field.get(field))
    return out


def _workitem_exprs_for(cfg):
    """{workitem_field: sql_expr} when this process maps a workitem column.
    The column name originates only from Statconfig (server config), never the
    client — the same SQL-injection boundary as the date expressions."""
    out = {}
    for field, cfg_key in _WORKITEM_FIELD_COL.items():
        col = cfg.get(cfg_key)
        if col:
            out[field] = f"CAST({col} AS nvarchar(100))"
    return out


class QueryBuildError(ValueError):
    """Raised when a report definition cannot be turned into SQL."""


_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _bracket_object(name):
    """Validate + bracket-quote a possibly schema-qualified object name
    part-by-part: 'dbo.X' -> '[dbo].[X]', 'X' -> '[X]'. Bracketing the whole
    dotted string as one identifier would make SQL Server look up a table
    literally named 'dbo.X'. Names originate from Statconfig (server config),
    never the client; the identifier check is defence in depth."""
    parts = str(name or "").split(".")
    if not 1 <= len(parts) <= 3 or not all(_IDENT.match(p) for p in parts):
        raise QueryBuildError(f"unsafe table name: {name!r}")
    return ".".join(f"[{p}]" for p in parts)


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

    # `columns` may be absent/empty for zero-dimension metric definitions.
    rd_columns = rd.get("columns") or []
    columns = [c["field"] for c in rd_columns]
    filters = rd.get("filters") or []
    sort = rd.get("sort") or []
    cap = min(int(rd.get("rowLimit", row_cap)), int(row_cap))

    # Per-column grain (date fields only); raw date otherwise.
    grain_by_field = {c["field"]: c.get("grain") for c in rd_columns}

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
    for cfg in process_configs:
        all_known_fields.update(_date_exprs_for(cfg, grain_by_field).keys())
        all_known_fields.update(_workitem_exprs_for(cfg).keys())
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
        # Projection uses the column grain; filters always use the RAW date.
        wi_exprs = _workitem_exprs_for(cfg)
        proj_resolved = {**colmap, **_date_exprs_for(cfg, grain_by_field), **wi_exprs}
        filt_resolved = {**colmap, **_date_exprs_for(cfg, {}), **wi_exprs}

        # A filter referencing a field this process doesn't expose can never
        # match here — drop the whole subquery for correctness.
        if any(f["field"] not in filt_resolved for f in col_filters):
            continue

        select_exprs = []
        for field in projected_fields:
            if field == "processname":
                select_exprs.append("? AS [processname]")
                params.append(cfg["process"])
            else:
                actual = proj_resolved.get(field)
                if actual:
                    select_exprs.append(f"{actual} AS [{field}]")
                else:
                    select_exprs.append(f"NULL AS [{field}]")

        if not select_exprs:
            # Zero-dimension + count-only metrics: nothing to project, but the
            # subquery still needs a SELECT list for the outer COUNT(*).
            select_exprs.append("1 AS [_one]")

        where = ["1 = 1"]
        for f in col_filters:
            col = filt_resolved.get(f["field"])
            if not col:
                continue
            where.append(_filter_clause(col, f["op"], f.get("value"), params))
        cond = f" {cfg['condition']}" if cfg.get("condition") else ""
        sub_queries.append(
            f"SELECT {', '.join(select_exprs)} FROM {_bracket_object(cfg['table'])} "
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
