"""Generic, whitelist-driven query builder for DB-registered 'table' sources.

Unlike nx_lib.reporting.query (the docprocessing Statconfig builder), this builds
a plain projected SELECT over a single registered object (view/table). Every
identifier — the base object and each column — comes from the admin-defined
source registry and is validated against a strict whitelist; end users only pick
among the catalog's columns and supply *values*, which are always parameterized.
"""

import re

from .semantic import build_aggregate_sql

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_OP_SYMBOLS = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}


class TableQueryError(ValueError):
    """Raised when a generic table query cannot be built safely."""


def _grain_sql(d, grain):
    """Wrap a DATE/DATETIME expression `d` for the requested grain. None = raw.
    Mirrors query.py's _grain_sql (T-SQL, DATEFIRST-independent week), plus an
    explicit 'day' cast: table sources group DATETIME columns, and an
    untruncated day grain would bucket per timestamp, not per day."""
    if grain is None:
        return d
    if grain == "day":
        return f"CAST({d} AS date)"
    if grain == "week":
        return f"DATEADD(week, DATEDIFF(week, 0, {d}), 0)"
    if grain == "month":
        return f"DATEFROMPARTS(YEAR({d}), MONTH({d}), 1)"
    if grain == "quarter":
        return f"DATEFROMPARTS(YEAR({d}), (DATEPART(quarter, {d}) - 1) * 3 + 1, 1)"
    if grain == "year":
        return f"DATEFROMPARTS(YEAR({d}), 1, 1)"
    raise TableQueryError(f"unsupported date grain: {grain!r}")


def _quote_ident(name):
    if not _IDENT.match(name or ""):
        raise TableQueryError(f"unsafe identifier: {name!r}")
    return "[" + name + "]"


def _quote_object(base_object):
    """Validate + bracket-quote a 'Db.schema.object' name (1-3 dotted parts)."""
    parts = (base_object or "").split(".")
    if not 1 <= len(parts) <= 3 or not all(parts):
        raise TableQueryError("invalid base object")
    return ".".join(_quote_ident(p) for p in parts)


def _like_escape(v):
    # Bracket-escape LIKE metacharacters so no ESCAPE clause is needed.
    return str(v).replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")


def table_source_catalog(columns):
    """Normalize ColumnsJSON entries into the field-catalog shape the UI uses."""
    out = []
    for c in columns or []:
        field = c.get("field") or c.get("column")
        if not field:
            continue
        entry = {
            "field": field,
            "label": c.get("label") or field,
            "type": c.get("type") or "string",
            "filterable": bool(c.get("filterable", True)),
            "sortable": bool(c.get("sortable", True)),
            "aggregable": bool(c.get("aggregable", False)),
            "processes": [],
        }
        if c.get("grainable"):
            entry["grainable"] = True
        if c.get("labelWith"):
            # Companion column whose value prefixes this field's distinct values
            # in pickers (e.g. ProcessName labeled "client.process" via ClientName).
            entry["labelWith"] = c["labelWith"]
        if c.get("advanced"):
            # The Simple wizard folds these behind "Show advanced fields":
            # raw/diagnostic dimensions nobody breaks a report down by first.
            entry["advanced"] = True
        if c.get("grantScoped"):
            # Pickers offer only values whose client.process label is in the
            # caller's process.<client>.<name>.view grants — the snapshot table
            # holds every Octo process, most of which aren't configured/wanted.
            entry["grantScoped"] = True
        out.append(entry)
    return out


def _build_conditions(rd, by_field):
    """Return (conds, params) for rd['filters'] against the whitelisted catalog.
    Identical semantics to the prior inline loop; values are parameterized."""
    conds, params = [], []
    for f in rd.get("filters") or []:
        field = f.get("field")
        if field not in by_field:
            raise TableQueryError(f"unknown filter field: {field!r}")
        col = _quote_ident(field)
        op, val = f.get("op"), f.get("value")
        if isinstance(val, dict):
            raise TableQueryError(f"unresolved relative-date value for {field!r}")
        if op in _OP_SYMBOLS:
            conds.append(f"{col} {_OP_SYMBOLS[op]} ?")
            params.append(val)
        elif op == "contains":
            conds.append(f"{col} LIKE ?")
            params.append(f"%{_like_escape(val)}%")
        elif op == "starts_with":
            conds.append(f"{col} LIKE ?")
            params.append(f"{_like_escape(val)}%")
        elif op in ("in", "not_in"):
            vals = val if isinstance(val, list) else [val]
            if not vals:
                conds.append("1=0" if op == "in" else "1=1")
            else:
                placeholders = ",".join(["?"] * len(vals))
                conds.append(f"{col} {'IN' if op == 'in' else 'NOT IN'} ({placeholders})")
                params.extend(vals)
        elif op == "between":
            if not isinstance(val, list) or len(val) != 2:
                raise TableQueryError("between requires two values")
            conds.append(f"{col} BETWEEN ? AND ?")
            params.extend(val)
        elif op == "is_null":
            conds.append(f"{col} IS NULL")
        elif op == "is_not_null":
            conds.append(f"{col} IS NOT NULL")
        else:
            raise TableQueryError(f"unsupported filter op: {op!r}")
    return conds, params


def build_distinct_query(field, base_object, columns, *, cap=100):
    """SELECT DISTINCT TOP (cap) values of one whitelisted, filterable
    column — feeds the wizard's field-scope step (#178). No params: field
    and object are identifier-validated/quoted, cap is int-coerced."""
    by_field = {c["field"]: c for c in columns}
    meta = by_field.get(field)
    if meta is None or not meta.get("filterable"):
        raise TableQueryError(f"unknown or unfilterable field: {field!r}")
    col = _quote_ident(field)
    label_with = meta.get("labelWith")
    if label_with:
        if label_with not in by_field:
            raise TableQueryError(f"unknown labelWith field: {label_with!r}")
        lcol = _quote_ident(label_with)
        return (
            f"SELECT DISTINCT TOP ({int(cap)}) {col}, {lcol} "
            f"FROM {_quote_object(base_object)} "
            f"WHERE {col} IS NOT NULL ORDER BY {col}, {lcol}"
        )
    return (
        f"SELECT DISTINCT TOP ({int(cap)}) {col} FROM {_quote_object(base_object)} "
        f"WHERE {col} IS NOT NULL ORDER BY {col}"
    )


def build_generic_query(
    rd, base_object, columns, *, row_cap, resolved_metrics=None, latest_of=None
):
    """Build (sql, params) for a 'table' source.

    columns: the source field-catalog (table_source_catalog output). Projects
    rd['columns'] from base_object with rd['filters'] and rd['sort'], capped via
    TOP. The caller runs schema.validate_report_definition first, so fields are
    already whitelisted; this re-checks defensively and quotes every identifier.

    When resolved_metrics is non-empty the query uses a GROUP BY aggregate branch
    (via semantic.build_aggregate_sql); otherwise the existing row-projection path
    is used unchanged.
    """
    by_field = {c["field"]: c for c in columns}
    proj = [c.get("field") for c in rd.get("columns", [])]
    dim_fields = [f for f in proj if f in by_field]

    grain_by_field = {c.get("field"): c.get("grain") for c in rd.get("columns") or []}
    dim_exprs = {
        f: _grain_sql(_quote_ident(f), grain_by_field.get(f))
        for f in dim_fields
        if by_field[f].get("grainable") and grain_by_field.get(f) is not None
    }

    conds, params = _build_conditions(rd, by_field)

    # 1900-01-01 is SQL Server's zero-date sentinel; drop such rows from any
    # grained date dimension so they don't render as a plausible-looking 1900
    # bucket. NULL buckets stay — "no date yet" is a real group.
    for f in dim_exprs:
        col = _quote_ident(f)
        conds.append(f"({col} IS NULL OR {col} >= '19010101')")

    if resolved_metrics:
        # Zero-dimension grand totals: empty dim_fields is valid here and
        # yields a global aggregate with no GROUP BY.
        where = (" WHERE " + " AND ".join(conds)) if conds else ""
        inner_from = f"{_quote_object(base_object)}{where}"
        # #178: 'latest' metrics are point-in-time gauges — summing snapshots
        # across time is meaningless. Without the date field as a dimension the
        # run aggregates only the newest snapshot; with a grained date dimension
        # it keeps only the newest snapshot instant *within each bucket* (all
        # rows of one collector run share one SnapshotAt, so IN on the per-
        # bucket MAX keeps exactly that run's rows).
        if latest_of:
            if latest_of not in by_field:
                raise TableQueryError(f"unknown latest_of field: {latest_of!r}")
            col = _quote_ident(latest_of)
            glue = " AND " if conds else " WHERE "
            grain = grain_by_field.get(latest_of)
            if latest_of not in dim_fields:
                sub = f"(SELECT MAX({col}) FROM {_quote_object(base_object)}{where})"
                inner_from = f"{inner_from}{glue}{col} = {sub}"
                params = params + params  # outer WHERE params, then the subquery's
            elif grain is not None:
                bucket = _grain_sql(col, grain)
                sub = (
                    f"(SELECT MAX({col}) FROM {_quote_object(base_object)}{where} "
                    f"GROUP BY {bucket})"
                )
                inner_from = f"{inner_from}{glue}{col} IN {sub}"
                params = params + params
            # raw (grain None) date dimension: every instant is its own
            # bucket, the restriction would be a no-op — skip it.
        select_params: list = []
        sql = build_aggregate_sql(
            inner_from=inner_from,
            dim_fields=dim_fields,
            resolved_metrics=resolved_metrics,
            sort=rd.get("sort") or [],
            cap=row_cap,
            dim_exprs=dim_exprs,
            params_out=select_params,
        )
        # SELECT-list (conditional metric) params bind before the WHERE params.
        return sql, select_params + params

    select_cols = [
        f"{dim_exprs[f]} AS {_quote_ident(f)}" if f in dim_exprs else _quote_ident(f)
        for f in dim_fields
    ]
    if not select_cols:
        raise TableQueryError("no valid columns selected")

    sql = [
        f"SELECT TOP ({int(row_cap)}) {', '.join(select_cols)} FROM {_quote_object(base_object)}"
    ]
    if conds:
        sql.append("WHERE " + " AND ".join(conds))

    order = []
    for s in rd.get("sort") or []:
        field = s.get("field")
        if field not in by_field:
            raise TableQueryError(f"unknown sort field: {field!r}")
        order.append(f"{_quote_ident(field)} {'DESC' if s.get('dir') == 'desc' else 'ASC'}")
    if order:
        sql.append("ORDER BY " + ", ".join(order))

    return " ".join(sql), params
