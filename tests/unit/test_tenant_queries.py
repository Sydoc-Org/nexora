"""Unit tests for nx_lib.tenant.queries -- descriptor-to-SQL builders.

Pure functions over TenantEntity/TenantField dataclasses: no DB, no Flask
app context needed (unlike test_tenant_registry.py, which mocks
engine_nexora_db). Assertions are on exact SQL text + bound params for both
dialects.
"""

import pytest

from nx_lib.tenant import queries as q
from nx_lib.tenant.registry import _IDENT_RE, TenantEntity, TenantField


def _entity(
    tenant="ms02",
    key="dossiers",
    source_object="dbo.Dossier",
    kind="entries",
    engine_role="runtime",
    id_column="Id",
    sort_order=100,
):
    return TenantEntity(
        tenant=tenant,
        key=key,
        source_object=source_object,
        kind=kind,
        engine_role=engine_role,
        id_column=id_column,
        labels={"en": "Dossiers"},
        sort_order=sort_order,
    )


def _field(
    tenant="ms02",
    entity="dossiers",
    column="Name",
    semantic_role="text",
    lookup_entity=None,
    visible=True,
    sort_order=100,
):
    return TenantField(
        tenant=tenant,
        entity=entity,
        column=column,
        semantic_role=semantic_role,
        lookup_entity=lookup_entity,
        labels={"en": column},
        visible=visible,
        sort_order=sort_order,
    )


# -- quote_ident --------------------------------------------------------


def test_quote_ident_tsql_uses_brackets():
    assert q.quote_ident("Name", "tsql") == "[Name]"


def test_quote_ident_postgres_uses_double_quotes_and_preserves_case():
    assert q.quote_ident("DossierStatus", "postgres") == '"DossierStatus"'


def test_quote_ident_raises_on_unsafe_name():
    with pytest.raises(ValueError):
        q.quote_ident("bad;--name", "tsql")


def test_quote_ident_raises_on_unknown_dialect():
    with pytest.raises(ValueError):
        q.quote_ident("Name", "oracle")


def test_quote_ident_reuses_registry_ident_re():
    # Task 3 must reuse Task 2's single source of truth for "is this string
    # safe to interpolate as an identifier", not redefine its own copy that
    # could silently drift from the registry's own load-time validation.
    assert q._IDENT_RE is _IDENT_RE


# -- _safe_source (final-review fix wave, Finding 1) ----------------------
#
# entity.source_object never went through _IDENT_RE inside this module --
# every column name gets a second, independent validation gate via
# quote_ident, but source_object (schema-qualified, used unquoted/pre-formed
# as-is) was the one exception to the module docstring's own "belt-and-
# braces" claim. Not exploitable today (the registry's load-time validation
# plus _IDENT_RE's restrictive character class already rule out injection),
# but every function that interpolates source_object must now validate it
# itself rather than trusting the registry alone.


def test_safe_source_returns_valid_source_object_unchanged():
    entity = _entity(source_object='public."Dossier"')
    assert q._safe_source(entity) == 'public."Dossier"'


def test_safe_source_raises_on_unsafe_source_object():
    entity = _entity(source_object="dbo.Dossier; DROP TABLE Users--")
    with pytest.raises(ValueError):
        q._safe_source(entity)


def test_build_list_query_raises_on_unsafe_source_object():
    entity = _entity(source_object="dbo.Dossier; DROP TABLE Users--")
    fields = [_field()]
    with pytest.raises(ValueError):
        q.build_list_query(entity, fields, "tsql")


def test_build_insert_raises_on_unsafe_source_object():
    entity = _entity(source_object="dbo.Dossier; DROP TABLE Users--", kind="entries")
    fields = [_field(column="Name", visible=True)]
    with pytest.raises(ValueError):
        q.build_insert(entity, fields, "tsql")


def test_build_update_raises_on_unsafe_source_object():
    entity = _entity(source_object="dbo.Dossier; DROP TABLE Users--", kind="entries")
    fields = [_field(column="Name", visible=True)]
    with pytest.raises(ValueError):
        q.build_update(entity, fields, "tsql")


def test_build_delete_raises_on_unsafe_source_object():
    entity = _entity(source_object="dbo.Dossier; DROP TABLE Users--", kind="entries")
    with pytest.raises(ValueError):
        q.build_delete(entity, "tsql")


# -- build_list_query: tsql ----------------------------------------------


def test_list_query_tsql_pagination_and_quoting():
    entity = _entity(source_object="dbo.Dossier", id_column="Id")
    fields = [
        _field(column="CreatedAt", semantic_role="date"),
        _field(column="Status", semantic_role="category"),
    ]

    count_sql, page_sql, (count_params, page_params) = q.build_list_query(
        entity, fields, "tsql", offset=20, limit=10
    )

    assert count_sql == "SELECT COUNT(*) FROM dbo.Dossier"
    assert page_sql == (
        "SELECT [Id], [CreatedAt], [Status] FROM dbo.Dossier "
        "ORDER BY [CreatedAt] DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
    )
    assert count_params == []
    # tsql pagination order is (offset, limit) -- matches the OFFSET/FETCH markers.
    assert page_params == [20, 10]


def test_list_query_tsql_defaults_to_id_column_when_no_date_field():
    entity = _entity(source_object="dbo.Dossier", id_column="Id")
    fields = [_field(column="Status", semantic_role="category")]

    _, page_sql, _ = q.build_list_query(entity, fields, "tsql")

    assert "ORDER BY [Id] ASC" in page_sql


# -- build_list_query: postgres -------------------------------------------


def test_list_query_postgres_pagination_and_quoting():
    entity = _entity(source_object='public."Dossier"', id_column="Id")
    fields = [
        _field(column="CreatedAt", semantic_role="date"),
        _field(column="Status", semantic_role="category"),
    ]

    count_sql, page_sql, (count_params, page_params) = q.build_list_query(
        entity, fields, "postgres", offset=20, limit=10
    )

    assert count_sql == 'SELECT COUNT(*) FROM public."Dossier"'
    assert page_sql == (
        'SELECT "Id", "CreatedAt", "Status" FROM public."Dossier" '
        'ORDER BY "CreatedAt" DESC LIMIT %s OFFSET %s'
    )
    assert count_params == []
    # postgres pagination order is (limit, offset) -- matches LIMIT/OFFSET markers.
    assert page_params == [10, 20]


def test_list_query_postgres_defaults_to_id_column_when_no_date_field():
    entity = _entity(source_object='public."Dossier"', id_column="Id")
    fields = [_field(column="Status", semantic_role="category")]

    _, page_sql, _ = q.build_list_query(entity, fields, "postgres")

    assert 'ORDER BY "Id" ASC' in page_sql


# -- build_list_query: filters --------------------------------------------


def test_contains_filter_binds_like_parameter():
    entity = _entity(source_object="dbo.Dossier", id_column="Id")
    fields = [_field(column="Name", semantic_role="text")]

    count_sql, page_sql, (count_params, page_params) = q.build_list_query(
        entity, fields, "tsql", filters=[("Name", "contains", "foo")]
    )

    assert "[Name] LIKE ?" in count_sql
    # The wildcard value never appears in the SQL text -- only in params.
    assert "foo" not in count_sql
    assert "%foo%" not in count_sql
    assert count_params == ["%foo%"]
    assert page_params[: len(count_params)] == ["%foo%"]


def test_contains_filter_uses_ilike_on_postgres():
    entity = _entity(source_object='public."Dossier"', id_column="Id")
    fields = [_field(column="Name", semantic_role="text")]

    count_sql, _, (count_params, _) = q.build_list_query(
        entity, fields, "postgres", filters=[("Name", "contains", "foo")]
    )

    assert '"Name" ILIKE %s' in count_sql
    assert count_params == ["%foo%"]


def test_startswith_filter_binds_prefix_like_parameter():
    # Mirrors workitem_sources.py's own id-prefix search semantics
    # (task-9 brief parity gap: the tenant list page's id-column filter).
    entity = _entity(source_object="dbo.Dossier", id_column="Id")
    fields = [_field(column="Name", semantic_role="text")]

    count_sql, _, (count_params, _) = q.build_list_query(
        entity, fields, "tsql", filters=[("Id", "startswith", "11")]
    )

    assert "[Id] LIKE ?" in count_sql
    assert "11%" not in count_sql  # never interpolated into the SQL text
    assert count_params == ["11%"]


def test_startswith_filter_uses_ilike_on_postgres():
    entity = _entity(source_object='public."Dossier"', id_column="Id")
    fields = [_field(column="Name", semantic_role="text")]

    count_sql, _, (count_params, _) = q.build_list_query(
        entity, fields, "postgres", filters=[("Id", "startswith", "11")]
    )

    assert '"Id" ILIKE %s' in count_sql
    assert count_params == ["11%"]


def test_eq_gte_lt_filters_are_anded_and_bound():
    entity = _entity(source_object="dbo.Dossier", id_column="Id")
    fields = [_field(column="Status", semantic_role="category")]

    count_sql, _, (count_params, _) = q.build_list_query(
        entity,
        fields,
        "tsql",
        filters=[
            ("Status", "eq", "open"),
            ("CreatedAt", "gte", "2026-01-01"),
            ("CreatedAt", "lt", "2026-02-01"),
        ],
    )

    assert count_sql == (
        "SELECT COUNT(*) FROM dbo.Dossier WHERE "
        "[Status] = ? AND [CreatedAt] >= ? AND [CreatedAt] < ?"
    )
    assert count_params == ["open", "2026-01-01", "2026-02-01"]


def test_unsupported_filter_op_raises():
    entity = _entity()
    fields = [_field()]
    with pytest.raises(ValueError):
        q.build_list_query(entity, fields, "tsql", filters=[("Name", "neq", "x")])


def test_filter_column_is_identifier_validated():
    entity = _entity()
    fields = [_field()]
    with pytest.raises(ValueError):
        q.build_list_query(entity, fields, "tsql", filters=[("bad;--name", "eq", "x")])


# -- build_list_query: sort + dialect validation --------------------------


def test_explicit_sort_overrides_default_date_ordering():
    entity = _entity(source_object="dbo.Dossier", id_column="Id")
    fields = [_field(column="CreatedAt", semantic_role="date")]

    _, page_sql, _ = q.build_list_query(entity, fields, "tsql", sort=("Status", "asc"))

    assert "ORDER BY [Status] ASC" in page_sql
    assert "ORDER BY [CreatedAt]" not in page_sql


def test_invalid_sort_direction_raises():
    entity = _entity()
    fields = [_field()]
    with pytest.raises(ValueError):
        q.build_list_query(entity, fields, "tsql", sort=("Status", "sideways"))


def test_build_list_query_raises_on_unknown_dialect():
    entity = _entity()
    fields = [_field()]
    with pytest.raises(ValueError):
        q.build_list_query(entity, fields, "oracle")


# -- build_insert / build_update ------------------------------------------


def test_build_insert_excludes_invisible_fields_and_id_column():
    entity = _entity(source_object="dbo.Dossier", id_column="Id", kind="entries")
    fields = [
        _field(column="Id", semantic_role="identifier", visible=True),
        _field(column="Name", semantic_role="text", visible=True),
        _field(column="Internal", semantic_role="text", visible=False),
    ]

    sql = q.build_insert(entity, fields, "tsql")

    assert sql == "INSERT INTO dbo.Dossier ([Name]) VALUES (?)"


def test_build_insert_postgres_markers():
    entity = _entity(source_object='public."Dossier"', id_column="Id", kind="entries")
    fields = [_field(column="Name", semantic_role="text", visible=True)]

    sql = q.build_insert(entity, fields, "postgres")

    assert sql == 'INSERT INTO public."Dossier" ("Name") VALUES (%s)'


def test_build_insert_raises_when_not_entries_kind():
    entity = _entity(kind="documents")
    fields = [_field()]
    with pytest.raises(ValueError):
        q.build_insert(entity, fields, "tsql")


def test_build_insert_raises_when_no_writable_fields():
    entity = _entity(id_column="Id")
    fields = [_field(column="Id", visible=True), _field(column="Hidden", visible=False)]
    with pytest.raises(ValueError):
        q.build_insert(entity, fields, "tsql")


def test_build_update_sets_only_visible_fields():
    entity = _entity(source_object="dbo.Dossier", id_column="Id", kind="entries")
    fields = [
        _field(column="Name", semantic_role="text", visible=True),
        _field(column="Internal", semantic_role="text", visible=False),
    ]

    sql = q.build_update(entity, fields, "tsql")

    assert sql == "UPDATE dbo.Dossier SET [Name] = ? WHERE [Id] = ?"
    assert "Internal" not in sql


def test_build_update_excludes_id_column_from_set_even_if_visible():
    entity = _entity(source_object="dbo.Dossier", id_column="Id", kind="entries")
    fields = [
        _field(column="Id", semantic_role="identifier", visible=True),
        _field(column="Name", semantic_role="text", visible=True),
    ]

    sql = q.build_update(entity, fields, "tsql")

    assert sql == "UPDATE dbo.Dossier SET [Name] = ? WHERE [Id] = ?"


def test_build_update_postgres_markers():
    entity = _entity(source_object='public."Dossier"', id_column="Id", kind="entries")
    fields = [_field(column="Name", semantic_role="text", visible=True)]

    sql = q.build_update(entity, fields, "postgres")

    assert sql == 'UPDATE public."Dossier" SET "Name" = %s WHERE "Id" = %s'


def test_build_update_raises_when_not_entries_kind():
    entity = _entity(kind="lookup")
    fields = [_field()]
    with pytest.raises(ValueError):
        q.build_update(entity, fields, "tsql")


def test_build_update_raises_when_no_writable_fields():
    entity = _entity(id_column="Id")
    fields = [_field(column="Id", visible=True)]
    with pytest.raises(ValueError):
        q.build_update(entity, fields, "tsql")


# -- build_delete ----------------------------------------------------------


def test_build_delete_is_parameterised_by_id():
    entity = _entity(source_object="dbo.Dossier", id_column="Id", kind="entries")

    sql = q.build_delete(entity, "tsql")

    assert sql == "DELETE FROM dbo.Dossier WHERE [Id] = ?"


def test_build_delete_postgres_markers():
    entity = _entity(source_object='public."Dossier"', id_column="Id", kind="entries")

    sql = q.build_delete(entity, "postgres")

    assert sql == 'DELETE FROM public."Dossier" WHERE "Id" = %s'


def test_build_delete_raises_when_not_entries_kind():
    entity = _entity(kind="documents")
    with pytest.raises(ValueError):
        q.build_delete(entity, "tsql")
