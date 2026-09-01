"""Descriptor -> SQL builders for the tenant kernel (both dialects).

Pure functions: given a ``TenantEntity`` / ``TenantField`` descriptor (as
loaded by ``nx_lib/tenant/registry.py``) and a target dialect, build the SQL
text + bound parameters a route needs to list, insert, update or delete rows
in the tenant's box. No DB access, no Flask import -- this module only ever
touches the descriptor objects it is handed and the two dialect string
constants below.

Dialect discipline mirrors the existing MS02 precedent in
``nx_lib/workitem_sources.py`` (its ``_MS02_IDENT`` guard and the ``%s``/``?``
marker split around ``client.dialect``): tsql identifiers are bracket-quoted,
postgres identifiers are double-quoted with case preserved (PG folds
unquoted identifiers to lowercase, so a PascalCase column like ``"Id"``
*must* stay quoted), tsql binds with ``?``, postgres binds with ``%s``.

Every value from a caller (filter values, pagination offsets/limits, row
data at write time) is a bound parameter -- never string-interpolated into
the SQL text. Every identifier (column names, drawn from the registry's
already-validated ``TenantEntity``/``TenantField`` rows) is re-validated
against ``_IDENT_RE`` here too: the registry drops unsafe rows at load time,
but ``quote_ident`` raises on a miss as a second, independent gate before any
of these strings reach a query -- belt-and-braces, same reasoning as
``registry.py``'s own validation.
"""

from .registry import _IDENT_RE, TenantEntity, TenantField

_TSQL = "tsql"
_POSTGRES = "postgres"

# dialect -> bound-parameter marker (pyodbc uses "?", psycopg2 uses "%s").
_MARKERS = {_TSQL: "?", _POSTGRES: "%s"}

# Filter operators accepted by build_list_query's `filters` argument.
_FILTER_OPS = {"eq", "contains", "startswith", "gte", "lt"}


def _marker(dialect: str) -> str:
    try:
        return _MARKERS[dialect]
    except KeyError:
        raise ValueError(f"unknown dialect: {dialect!r}") from None


def quote_ident(name: str, dialect: str) -> str:
    """Quote a bare identifier for ``dialect``.

    ``[name]`` for tsql, ``"name"`` for postgres (case preserved -- PG folds
    an unquoted identifier to lowercase, so a PascalCase column must stay
    quoted to match what the registry validated). Raises ``ValueError`` on an
    unknown dialect or an ``_IDENT_RE`` miss -- this is the second,
    independent validation gate mentioned in the module docstring; the
    registry already dropped unsafe rows at load time, but nothing here
    trusts that alone.
    """
    if dialect not in _MARKERS:
        raise ValueError(f"quote_ident: unknown dialect {dialect!r}")
    if not _IDENT_RE.match(name):
        raise ValueError(f"quote_ident: unsafe identifier {name!r}")
    return f'"{name}"' if dialect == _POSTGRES else f"[{name}]"


def _filter_clause(column: str, op: str, value: object, dialect: str) -> tuple[str, object]:
    """(sql_fragment, bound_value) for one ``(column, op, value)`` filter.

    'contains'/'startswith' wrap the value in ``%...%``/``...%`` on the
    PARAMETER, never in the SQL text -- the SQL only ever carries a bare
    ``LIKE``/``ILIKE <marker>``, so a caller's value can never inject its own
    wildcards into the clause shape. postgres uses ``ILIKE`` (case-
    insensitive, matching tsql's default case-insensitive collation); tsql
    uses plain ``LIKE``. 'startswith' mirrors workitem_sources.py's own
    id-prefix search semantics (``CAST(id AS ...) LIKE 'id%'``) -- added for
    the tenant list page's id-column filter (task-9 brief parity gap).
    """
    if op not in _FILTER_OPS:
        raise ValueError(f"unsupported filter op: {op!r}")
    col = quote_ident(column, dialect)
    marker = _marker(dialect)
    if op == "eq":
        return f"{col} = {marker}", value
    if op == "gte":
        return f"{col} >= {marker}", value
    if op == "lt":
        return f"{col} < {marker}", value
    keyword = "ILIKE" if dialect == _POSTGRES else "LIKE"
    if op == "startswith":
        return f"{col} {keyword} {marker}", f"{value}%"
    # contains
    return f"{col} {keyword} {marker}", f"%{value}%"


def _order_by(
    entity: TenantEntity,
    fields: list[TenantField],
    dialect: str,
    sort: tuple[str, str] | None,
) -> str:
    """ORDER BY clause: explicit ``sort`` wins; otherwise the first
    ``semantic_role == 'date'`` field DESC (most-recent-first is the natural
    default for a box list); with no date field at all, fall back to the
    entity's own ``id_column`` ASC."""
    if sort is not None:
        column, direction = sort
        direction = direction.upper()
        if direction not in ("ASC", "DESC"):
            raise ValueError(f"invalid sort direction: {direction!r}")
        return f"{quote_ident(column, dialect)} {direction}"
    date_field = next((f for f in fields if f.semantic_role == "date"), None)
    if date_field is not None:
        return f"{quote_ident(date_field.column, dialect)} DESC"
    return f"{quote_ident(entity.id_column, dialect)} ASC"


def build_list_query(
    entity: TenantEntity,
    fields: list[TenantField],
    dialect: str,
    *,
    filters: list[tuple[str, str, object]] | None = None,
    sort: tuple[str, str] | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[str, str, tuple[list, list]]:
    """Build a paged list query pair for ``entity``.

    Returns ``(count_sql, page_sql, params)`` where ``params`` is a
    ``(count_params, page_params)`` pair: bind ``count_params`` to
    ``count_sql``, ``page_params`` to ``page_sql``. ``page_params`` is the
    filter params followed by the two pagination values, in dialect order --
    ``(offset, limit)`` for tsql's ``OFFSET ? ROWS FETCH NEXT ? ROWS ONLY``,
    ``(limit, offset)`` for postgres's ``LIMIT %s OFFSET %s`` -- mirroring
    the exact param ordering ``workitem_sources.py`` uses for the same two
    pagination shapes.

    The SELECT list is the entity's ``id_column`` (always first, deduped)
    followed by every column in ``fields``, in the order given -- callers
    that only want visible columns should pass an already-filtered
    ``fields`` list; this function does not re-filter it (unlike
    ``build_insert``/``build_update``, which are write paths and always
    restrict themselves to visible, non-id columns).
    """
    if dialect not in _MARKERS:
        raise ValueError(f"build_list_query: unknown dialect {dialect!r}")
    offset = int(offset)
    limit = int(limit)

    where_parts = []
    count_params: list = []
    for column, op, value in filters or []:
        clause, param = _filter_clause(column, op, value, dialect)
        where_parts.append(clause)
        count_params.append(param)
    where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""

    count_sql = f"SELECT COUNT(*) FROM {entity.source_object}{where_sql}"

    select_cols = [entity.id_column] + [f.column for f in fields if f.column != entity.id_column]
    cols_sql = ", ".join(quote_ident(c, dialect) for c in select_cols)
    order_sql = _order_by(entity, fields, dialect, sort)

    if dialect == _POSTGRES:
        page_sql = (
            f"SELECT {cols_sql} FROM {entity.source_object}{where_sql} "
            f"ORDER BY {order_sql} LIMIT %s OFFSET %s"
        )
        page_params = [*count_params, limit, offset]
    else:
        page_sql = (
            f"SELECT {cols_sql} FROM {entity.source_object}{where_sql} "
            f"ORDER BY {order_sql} OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        )
        page_params = [*count_params, offset, limit]

    return count_sql, page_sql, (count_params, page_params)


def _require_entries_kind(entity: TenantEntity, fn_name: str) -> None:
    if entity.kind != "entries":
        raise ValueError(f"{fn_name}: entity kind must be 'entries', got {entity.kind!r}")


def _writable_columns(entity: TenantEntity, fields: list[TenantField]) -> list[str]:
    """Visible field columns, excluding the id column -- the set of columns
    an INSERT/UPDATE is allowed to write. The id column is always excluded
    even if a field row happens to name it and be marked visible: it is the
    entity's key, set by the DB (identity/serial) or by the WHERE clause on
    write, never by the value list."""
    return [f.column for f in fields if f.visible and f.column != entity.id_column]


def build_insert(entity: TenantEntity, fields: list[TenantField], dialect: str) -> str:
    """INSERT statement over ``entity``'s visible, non-id columns.

    Only valid for ``Kind='entries'`` entities (documents/lookup boxes are
    read/CRUD-linked, not directly row-inserted) -- raises ``ValueError``
    otherwise. Every value is a bound parameter, in the same order as the
    returned column list.
    """
    _require_entries_kind(entity, "build_insert")
    cols = _writable_columns(entity, fields)
    if not cols:
        raise ValueError("build_insert: no visible, writable fields for entity")
    marker = _marker(dialect)
    col_sql = ", ".join(quote_ident(c, dialect) for c in cols)
    val_sql = ", ".join([marker] * len(cols))
    return f"INSERT INTO {entity.source_object} ({col_sql}) VALUES ({val_sql})"


def build_update(entity: TenantEntity, fields: list[TenantField], dialect: str) -> str:
    """UPDATE statement over ``entity``'s visible, non-id columns, keyed by
    ``id_column``. Only valid for ``Kind='entries'`` entities -- raises
    ``ValueError`` otherwise."""
    _require_entries_kind(entity, "build_update")
    cols = _writable_columns(entity, fields)
    if not cols:
        raise ValueError("build_update: no visible, writable fields for entity")
    marker = _marker(dialect)
    set_sql = ", ".join(f"{quote_ident(c, dialect)} = {marker}" for c in cols)
    id_sql = quote_ident(entity.id_column, dialect)
    return f"UPDATE {entity.source_object} SET {set_sql} WHERE {id_sql} = {marker}"


def build_delete(entity: TenantEntity, dialect: str) -> str:
    """DELETE statement over ``entity``, keyed by ``id_column``. Only valid
    for ``Kind='entries'`` entities -- raises ``ValueError`` otherwise."""
    _require_entries_kind(entity, "build_delete")
    marker = _marker(dialect)
    id_sql = quote_ident(entity.id_column, dialect)
    return f"DELETE FROM {entity.source_object} WHERE {id_sql} = {marker}"
