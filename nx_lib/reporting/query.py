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
    if isinstance(value, dict):
        # A relative-date token reached the SQL layer: resolve_definition_tokens
        # (nx_lib.reporting.tokens) must run before query building.
        raise QueryBuildError(f"unresolved relative-date value for {col}")
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


# Date-anchored measures: shared time-axis field + anchor -> Statconfig date
# column key. The 'backlog' anchor reads dbo.BacklogHistory (same Statistics
# engine) as one more UNION leg.
ACTIVITY_FIELD = "activity_date"
_ANCHOR_DATE_KEY = {"import_date": "import_col", "export_date": "export_col"}
_BACKLOG_OBJECT = "[dbo].[BacklogHistory]"


def _build_anchored_query(rd, process_configs, field_col_maps, resolved_metrics, row_cap):
    """(sql, params) for date-anchored metrics (imported/exported/backlog).

    Long-format UNION ALL: one leg per (process, used date anchor) plus one
    BacklogHistory leg when a 'backlog'-anchored metric is selected. Every leg
    projects the shared [activity_date] axis (its OWN date, bucketed by the
    axis grain) and one counter column per metric (1 / the value column /
    BacklogCount on the matching-anchor leg, 0 elsewhere); the outer query
    GROUPs BY the dims and SUMs the counters. The backlog leg concatenates
    LOWER(ClientName)+'.'+ProcessName so its process vocabulary matches the
    docprocessing 'client.process' constants, and keeps only the newest
    snapshot instant per bucket (one collector timestamp per run).
    """
    rd_columns = rd.get("columns") or []
    columns = [c["field"] for c in rd_columns]
    filters = rd.get("filters") or []
    sort = rd.get("sort") or []
    cap = min(int(rd.get("rowLimit", row_cap)), int(row_cap))
    act_grain = next((c.get("grain") for c in rd_columns if c["field"] == ACTIVITY_FIELD), None)

    process_configs = _scope_by_processname(process_configs, filters)
    if not process_configs:
        raise QueryBuildError("no processes in scope after processname filter")
    col_filters = [f for f in filters if f["field"] != "processname"]
    act_filters = [f for f in col_filters if f["field"] == ACTIVITY_FIELD]
    other_filters = [f for f in col_filters if f["field"] != ACTIVITY_FIELD]

    used_anchors = list(dict.fromkeys(m["anchor"] for m in resolved_metrics))
    date_anchors = [a for a in used_anchors if a in _ANCHOR_DATE_KEY]
    has_backlog = "backlog" in used_anchors

    known = {ACTIVITY_FIELD, "processname"}
    for colmap in field_col_maps.values():
        known.update(colmap.keys())
    for field in columns:
        if field not in known:
            raise QueryBuildError(f"unknown column field: {field!r}")

    def counter_exprs(leg_anchor, colmap):
        exprs = []
        for m in resolved_metrics:
            if m["anchor"] != leg_anchor:
                # A backlog is a LEVEL, not an event count: a leg with no
                # snapshot contributes NULL so a bucket nobody measured sums
                # to NULL (rendered as a gap), never to a fake 0.
                null_or_zero = "NULL" if m["anchor"] == "backlog" else "0"
                exprs.append(f"{null_or_zero} AS [{m['code']}]")
            elif leg_anchor == "backlog":
                exprs.append(f"[BacklogCount] AS [{m['code']}]")
            elif m.get("value_field"):
                col = colmap.get(m["value_field"])
                # A process without the value column contributes nothing.
                exprs.append(
                    f"TRY_CAST({col} AS float) AS [{m['code']}]" if col else f"0 AS [{m['code']}]"
                )
            else:
                exprs.append(f"1 AS [{m['code']}]")
        return exprs

    sub_queries = []
    params = []
    for cfg in process_configs:
        colmap = field_col_maps.get(cfg["process"], {})
        for anchor in date_anchors:
            raw_col = cfg.get(_ANCHOR_DATE_KEY[anchor])
            if not raw_col:
                continue  # this process never has that date -> no events
            raw_date = _date_base(raw_col)
            select_exprs = []
            leg_params = []
            for field in columns:
                if field == ACTIVITY_FIELD:
                    select_exprs.append(f"{_grain_sql(raw_date, act_grain)} AS [{ACTIVITY_FIELD}]")
                elif field == "processname":
                    select_exprs.append("? AS [processname]")
                    leg_params.append(cfg["process"])
                else:
                    actual = colmap.get(field)
                    select_exprs.append(
                        f"{actual} AS [{field}]" if actual else f"NULL AS [{field}]"
                    )
            select_exprs += counter_exprs(anchor, colmap)
            # `>= '19010101'` drops both NULL anchors (the event never
            # happened for that row) and the zero-date sentinel.
            where = ["1 = 1", f"{raw_date} >= '19010101'"]
            skip = False
            for f in other_filters:
                col = colmap.get(f["field"])
                if not col:
                    if f["op"] != "is_null":
                        skip = True
                        break
                    continue
                where.append(_filter_clause(col, f["op"], f.get("value"), leg_params))
            if skip:
                continue
            for f in act_filters:
                where.append(_filter_clause(raw_date, f["op"], f.get("value"), leg_params))
            cond = f" {cfg['condition']}" if cfg.get("condition") else ""
            params.extend(leg_params)
            sub_queries.append(
                f"SELECT {', '.join(select_exprs)} FROM {_bracket_object(cfg['table'])} "
                f"WHERE {' AND '.join(where)}{cond}"
            )

    # A filter on a field BacklogHistory doesn't have can never match there —
    # drop the leg (same rule as per-process subqueries); is_null is trivially
    # TRUE (the leg projects NULL for foreign dims).
    if has_backlog and all(f["op"] == "is_null" for f in other_filters):
        proc_expr = "LOWER([ClientName]) + N'.' + [ProcessName]"
        snap = "CAST([SnapshotAt] AS date)"
        select_exprs = []
        leg_params = []
        for field in columns:
            if field == ACTIVITY_FIELD:
                select_exprs.append(f"{_grain_sql(snap, act_grain)} AS [{ACTIVITY_FIELD}]")
            elif field == "processname":
                select_exprs.append(f"{proc_expr} AS [processname]")
            else:
                select_exprs.append(f"NULL AS [{field}]")
        select_exprs += counter_exprs("backlog", {})
        where = ["1 = 1", f"{snap} >= '19010101'"]
        procs = [cfg["process"] for cfg in process_configs]
        placeholders = ", ".join(["?"] * len(procs))
        where.append(f"{proc_expr} IN ({placeholders})")
        leg_params.extend(procs)
        sub_where = [f"{snap} >= '19010101'"]
        for f in act_filters:
            where.append(_filter_clause(snap, f["op"], f.get("value"), leg_params))
        # Newest snapshot instant only — per bucket when the axis is bucketed,
        # globally otherwise (raw-grain axis needs no restriction). The MAX
        # subquery repeats the activity filters, so its params come last.
        sub_params = []
        for f in act_filters:
            sub_where.append(_filter_clause(snap, f["op"], f.get("value"), sub_params))
        if ACTIVITY_FIELD in columns and act_grain is not None:
            where.append(
                f"[SnapshotAt] IN (SELECT MAX([SnapshotAt]) FROM {_BACKLOG_OBJECT} "
                f"WHERE {' AND '.join(sub_where)} GROUP BY {_grain_sql(snap, act_grain)})"
            )
            leg_params.extend(sub_params)
        elif ACTIVITY_FIELD not in columns:
            where.append(
                f"[SnapshotAt] = (SELECT MAX([SnapshotAt]) FROM {_BACKLOG_OBJECT} "
                f"WHERE {' AND '.join(sub_where)})"
            )
            leg_params.extend(sub_params)
        params.extend(leg_params)
        sub_queries.append(
            f"SELECT {', '.join(select_exprs)} FROM {_BACKLOG_OBJECT} "
            f"WHERE {' AND '.join(where)}"
        )

    if not sub_queries:
        raise QueryBuildError("no subqueries produced for the requested scope/filters")

    return (
        build_aggregate_sql(
            inner_from=f"({' UNION ALL '.join(sub_queries)}) t",
            dim_fields=columns,
            resolved_metrics=resolved_metrics,
            sort=sort,
            cap=cap,
        ),
        params,
    )


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

    anchored = [m for m in (resolved_metrics or []) if m.get("anchor")]
    if anchored:
        if len(anchored) != len(resolved_metrics):
            raise QueryBuildError("anchored and unanchored metrics cannot be combined")
        return _build_anchored_query(rd, process_configs, field_col_maps, resolved_metrics, row_cap)

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

    # SUM/AVG/MIN/MAX bases are projected as TRY_CAST(col AS float): the
    # doc-extraction stat columns are varchar, and a raw SUM would
    # implicit-convert and fail on the first non-numeric cell — TRY_CAST
    # yields NULL there and SUM/AVG ignore NULLs. MIN/MAX need the same cast:
    # without it they compare lexicographically as strings ("9" > "10" is
    # true as strings), not numerically. T-SQL only, which is fine: this
    # builder targets the SQL Server statistics engine (table sources
    # aggregate typed columns in table_query).
    # ponytail: float is exact for page counts (< 2^53); switch to
    # decimal(18,2) when money metrics arrive.
    # This set alone is not the whole gate: applying it below also requires
    # `field in colmap`, so the cast only ever wraps real varchar stat columns,
    # never the synthetic date/workitem-id fields (see the usage site).
    numeric_bases = {
        m["base_field"]
        for m in (resolved_metrics or [])
        if m.get("base_field") and m["aggregation"] in ("sum", "avg", "min", "max")
    }

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
        # match here — drop the whole subquery. Exception: is_null is trivially
        # TRUE for such a process (the projection emits NULL for that field),
        # so it keeps the subquery and simply emits no clause.
        if any(f["field"] not in filt_resolved and f["op"] != "is_null" for f in col_filters):
            continue

        select_exprs = []
        for field in projected_fields:
            if field == "processname":
                select_exprs.append("? AS [processname]")
                params.append(cfg["process"])
            else:
                actual = proj_resolved.get(field)
                # numeric_bases gates SUM/AVG/MIN/MAX onto varchar stat columns
                # (colmap) only. proj_resolved also carries the synthetic
                # date/workitem-id expressions from _date_exprs_for /
                # _workitem_exprs_for, which already have their own typed
                # handling (DATE expressions, CAST ... AS nvarchar) — a numeric
                # float wrap around those is not just wrong, it's a hard SQL
                # Server error for date -> float (TRY_CAST doesn't degrade to
                # NULL for that pair, unlike varchar -> float).
                if actual and field in numeric_bases and field in colmap:
                    select_exprs.append(f"TRY_CAST({actual} AS float) AS [{field}]")
                elif actual:
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
        # Zero-date sentinel guard: empty-string/zero varchar dates CONVERT to
        # 1900-01-01 and would surface as a plausible-looking 1900 bucket on a
        # projected date dim. NULL rows stay — "no date yet" is a real group.
        raw_dates = _date_exprs_for(cfg, {})
        for field in columns:
            expr = raw_dates.get(field)
            if expr:
                where.append(f"({expr} IS NULL OR {expr} >= '19010101')")
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
