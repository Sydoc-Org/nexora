# nx_lib/reporting/query.py
"""Translate a validated report definition into a parameterized SQL query.

build_table_query is pure: it receives the report definition and injected
per-process configs + column maps (so it is DB-free and unit-testable), and
returns (sql, params) for the statistics engine. Every column/table name comes
from the injected maps/configs; only filter *values* become ? parameters.
"""

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


class QueryBuildError(ValueError):
    """Raised when a report definition cannot be turned into SQL."""


def _filter_clause(col, op, value, params):
    """Append a single filter clause for `col`. Returns the SQL fragment."""
    if op in ("is_null", "is_not_null"):
        return f"{col} {_OP_SQL[op]}"
    if op in ("in", "not_in"):
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
        params.append(f"%{value}%")
        return f"{col} LIKE ?"
    if op == "starts_with":
        params.append(f"{value}%")
        return f"{col} LIKE ?"
    # simple binary ops (eq, ne, gt, gte, lt, lte)
    params.append(value)
    return f"{col} {_OP_SQL[op]}"


def build_table_query(rd, process_configs, field_col_maps, *, row_cap):
    """Build (sql, params) for a table report.

    process_configs: [{process, table, export_col, import_col, condition}] already
      filtered to the effective (permitted ∩ requested) process scope.
    field_col_maps: {process: {field_key: actual_column_name}}.
    row_cap: server-enforced TOP cap (min of definition rowLimit and server max).

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

    sub_queries = []
    params = []
    for cfg in process_configs:
        colmap = field_col_maps.get(cfg["process"], {})

        # A filter referencing a field this process doesn't expose can never
        # match here — drop the whole subquery for correctness.
        skip = False
        for f in filters:
            fk = f["field"]
            if fk != "processname" and fk not in colmap:
                skip = True
                break
        if skip:
            continue

        select_exprs = []
        for field in columns:
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
        for f in filters:
            fk = f["field"]
            col = colmap.get(fk)
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
    out_cols = ", ".join(f"[{c}]" for c in columns)
    sql = f"SELECT TOP ({cap}) {out_cols} FROM ({inner}) t"
    if sort:
        order = ", ".join(f"[{s['field']}] {s['dir'].upper()}" for s in sort)
        sql += f" ORDER BY {order}"
    return sql, params
