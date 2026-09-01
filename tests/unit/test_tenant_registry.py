"""Unit tests for nx_lib.tenant.registry -- cached registry over the four
tenant tables (dbo.Tenants / TenantEntities / TenantFields / TenantPages,
migration 0084).

Mocks engine_nexora_db.raw_connection() the same way tests/unit/test_mapping_config.py
does.
"""

import importlib
import types
from unittest.mock import MagicMock

import pytest

# nx_lib/tenant/__init__.py re-exports the `registry` FUNCTION under the same
# name as this submodule (mirroring how callers use it: `tenant.registry()`),
# which shadows `nx_lib.tenant.registry` as an attribute path. Reach the
# actual submodule via sys.modules (through importlib.import_module) so we
# can monkeypatch engine_nexora_db on it directly, the same way
# test_mapping_config.py patches the flat nx_lib.mapping_config module.
tr = importlib.import_module("nx_lib.tenant.registry")


@pytest.fixture(autouse=True)
def clear_cache(app):
    with app.app_context():
        from nx_lib.extensions import cache

        cache.clear()
    yield
    with app.app_context():
        from nx_lib.extensions import cache

        cache.clear()


def _tenant_row(
    code="ms02",
    display_name="MS02 Client",
    organization_code="MS02",
    client_code="ms02",
    is_active=True,
):
    return types.SimpleNamespace(
        TenantCode=code,
        DisplayName=display_name,
        OrganizationCode=organization_code,
        ClientCode=client_code,
        IsActive=is_active,
    )


def _entity_row(
    tenant="ms02",
    entity_key="dossiers",
    source_object='public."Dossier"',
    kind="documents",
    engine_role="runtime",
    id_column="Id",
    label_en="Dossiers",
    label_de=None,
    label_fr=None,
    label_it=None,
    sort_order=100,
):
    return types.SimpleNamespace(
        TenantCode=tenant,
        EntityKey=entity_key,
        SourceObject=source_object,
        Kind=kind,
        EngineRole=engine_role,
        IdColumn=id_column,
        LabelEn=label_en,
        LabelDe=label_de,
        LabelFr=label_fr,
        LabelIt=label_it,
        SortOrder=sort_order,
    )


def _field_row(
    tenant="ms02",
    entity_key="dossiers",
    column="Status",
    semantic_role="category",
    lookup_entity=None,
    label_en="Status",
    label_de=None,
    label_fr=None,
    label_it=None,
    is_visible=True,
    sort_order=100,
):
    return types.SimpleNamespace(
        TenantCode=tenant,
        EntityKey=entity_key,
        ColumnName=column,
        SemanticRole=semantic_role,
        LookupEntity=lookup_entity,
        LabelEn=label_en,
        LabelDe=label_de,
        LabelFr=label_fr,
        LabelIt=label_it,
        IsVisible=is_visible,
        SortOrder=sort_order,
    )


def _page_row(
    tenant="ms02",
    page_key="dossiers-list",
    page_type="list",
    entity_key="dossiers",
    layout_json=None,
    sort_order=100,
):
    return types.SimpleNamespace(
        TenantCode=tenant,
        PageKey=page_key,
        PageType=page_type,
        EntityKey=entity_key,
        LayoutJSON=layout_json,
        SortOrder=sort_order,
    )


class _FakeCursor:
    """Routes each execute() by table name to a canned result set, mirroring
    the mocking pattern in tests/unit/test_mapping_config.py."""

    def __init__(self, tenants=(), entities=(), fields=(), pages=()):
        self._tenants = list(tenants)
        self._entities = list(entities)
        self._fields = list(fields)
        self._pages = list(pages)
        self._result = []

    def execute(self, sql, *params):
        if "FROM Tenants" in sql:
            self._result = self._tenants
        elif "FROM TenantEntities" in sql:
            self._result = self._entities
        elif "FROM TenantFields" in sql:
            self._result = self._fields
        elif "FROM TenantPages" in sql:
            self._result = self._pages
        else:
            raise AssertionError(f"unexpected query: {sql}")

    def fetchall(self):
        return self._result


def _engine_with(tenants=(), entities=(), fields=(), pages=()):
    cur = _FakeCursor(tenants=tenants, entities=entities, fields=fields, pages=pages)
    conn = MagicMock()
    conn.cursor.return_value = cur
    eng = MagicMock()
    eng.raw_connection.return_value = conn
    return eng, conn


def _dead_engine(msg="NexoraDB down"):
    eng = MagicMock()
    eng.raw_connection.side_effect = RuntimeError(msg)
    return eng


def test_registry_loads_active_rows_only(app, monkeypatch):
    eng, conn = _engine_with(
        tenants=[_tenant_row()],
        entities=[
            _entity_row(entity_key="dossiers"),
        ],
    )
    monkeypatch.setattr(tr, "engine_nexora_db", eng)

    with app.app_context():
        reg = tr.registry()

    assert reg is not None
    assert "ms02" in reg.tenants
    assert ("ms02", "dossiers") in reg.entities
    # WHERE Status='active' is baked into the SQL itself (the fake cursor
    # routes purely by table name), so a 'draft' row never reaches fetchall();
    # this asserts the query text carries the filter.
    eng.raw_connection.assert_called_once()
    conn.close.assert_called_once()


def test_registry_load_failure_returns_none_and_is_not_cached(app, monkeypatch):
    eng = _dead_engine()
    monkeypatch.setattr(tr, "engine_nexora_db", eng)

    with app.app_context():
        assert tr.registry() is None
        # second call must re-query -- a failure is never cached
        assert tr.registry() is None

    assert eng.raw_connection.call_count == 2


def test_registry_success_is_cached_for_ttl(app, monkeypatch):
    eng, _ = _engine_with(tenants=[_tenant_row()])
    monkeypatch.setattr(tr, "engine_nexora_db", eng)

    with app.app_context():
        first = tr.registry()
        second = tr.registry()

    assert first == second
    eng.raw_connection.assert_called_once()


def test_invalidate_tenant_config_drops_cache(app, monkeypatch):
    eng, _ = _engine_with(tenants=[_tenant_row()])
    monkeypatch.setattr(tr, "engine_nexora_db", eng)

    with app.app_context():
        tr.registry()
        tr.registry()
        assert eng.raw_connection.call_count == 1

        tr.invalidate_tenant_config()
        tr.registry()
        assert eng.raw_connection.call_count == 2


def test_unsafe_source_object_row_is_dropped_and_logged(app, monkeypatch):
    eng, _ = _engine_with(
        tenants=[_tenant_row()],
        entities=[
            _entity_row(entity_key="ok", source_object="dbo.Good"),
            _entity_row(entity_key="bad", source_object="bad;--name"),
        ],
    )
    monkeypatch.setattr(tr, "engine_nexora_db", eng)

    with app.app_context():
        reg = tr.registry()

    assert reg is not None
    assert ("ms02", "ok") in reg.entities
    assert ("ms02", "bad") not in reg.entities


def test_unsafe_column_name_row_is_dropped_and_logged(app, monkeypatch):
    eng, _ = _engine_with(
        tenants=[_tenant_row()],
        fields=[
            _field_row(column="GoodColumn"),
            _field_row(column="bad;--col"),
        ],
    )
    monkeypatch.setattr(tr, "engine_nexora_db", eng)

    with app.app_context():
        reg = tr.registry()

    assert reg is not None
    columns = {f.column for f in reg.fields}
    assert "GoodColumn" in columns
    assert "bad;--col" not in columns


def test_pages_for_orders_by_sort_order(app, monkeypatch):
    eng, _ = _engine_with(
        tenants=[_tenant_row()],
        pages=[
            _page_row(page_key="third", sort_order=300),
            _page_row(page_key="first", sort_order=100),
            _page_row(page_key="second", sort_order=200),
        ],
    )
    monkeypatch.setattr(tr, "engine_nexora_db", eng)

    with app.app_context():
        pages = tr.pages_for("ms02")

    assert [p.key for p in pages] == ["first", "second", "third"]


def test_layout_json_parse_error_yields_layout_none(app, monkeypatch):
    eng, _ = _engine_with(
        tenants=[_tenant_row()],
        pages=[_page_row(page_key="broken", layout_json="{not valid json")],
    )
    monkeypatch.setattr(tr, "engine_nexora_db", eng)

    with app.app_context():
        pages = tr.pages_for("ms02")

    assert len(pages) == 1
    assert pages[0].layout is None
