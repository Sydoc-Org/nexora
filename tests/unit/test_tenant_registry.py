"""Unit tests for nx_lib.tenant.registry -- cached registry over the four
tenant tables (dbo.Tenants / TenantEntities / TenantFields / TenantPages,
migration 0084).

Mocks engine_nexora_db.raw_connection() the same way tests/unit/test_mapping_config.py
does.
"""

import importlib
import logging
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


def _tenant_row(code="ms02", display_name="MS02 Client", is_active=True):
    return types.SimpleNamespace(TenantCode=code, DisplayName=display_name, IsActive=is_active)


def _entity_row(
    tenant="ms02",
    entity_key="dossiers",
    source_object='public."Dossier"',
    client_code="ms02",
    kind="documents",
    engine_role="runtime",
    id_column="Id",
    label_en="Dossiers",
    label_de=None,
    label_fr=None,
    label_it=None,
    sort_order=100,
    status="active",
):
    row = types.SimpleNamespace(
        TenantCode=tenant,
        EntityKey=entity_key,
        SourceObject=source_object,
        ClientCode=client_code,
        Kind=kind,
        EngineRole=engine_role,
        IdColumn=id_column,
        LabelEn=label_en,
        LabelDe=label_de,
        LabelFr=label_fr,
        LabelIt=label_it,
        SortOrder=sort_order,
    )
    # Status isn't in the SELECT list (it's WHERE-only), so it's carried as a
    # private, non-selected attribute purely for _FakeCursor's own filtering
    # below -- production code never reads it.
    row._status = status
    return row


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
    status="active",
):
    row = types.SimpleNamespace(
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
    row._status = status
    return row


def _page_row(
    tenant="ms02",
    page_key="dossiers-list",
    page_type="list",
    entity_key="dossiers",
    layout_json=None,
    sort_order=100,
    status="active",
):
    row = types.SimpleNamespace(
        TenantCode=tenant,
        PageKey=page_key,
        PageType=page_type,
        EntityKey=entity_key,
        LayoutJSON=layout_json,
        SortOrder=sort_order,
    )
    row._status = status
    return row


class _FakeCursor:
    """Routes each execute() by table name to a canned result set, mirroring
    the mocking pattern in tests/unit/test_mapping_config.py.

    Also *simulates* the WHERE filter a real DB would apply: it only drops
    inactive/draft rows when the executed SQL text actually carries the
    expected filter clause. If the implementation's SQL ever loses
    "WHERE Status = 'active'" / "WHERE IsActive = 1", this cursor stops
    filtering too, so a test asserting a draft/inactive row is absent will
    fail -- catching the regression instead of always self-filtering
    regardless of what the code under test actually sent.
    """

    def __init__(self, tenants=(), entities=(), fields=(), pages=()):
        self._tenants = list(tenants)
        self._entities = list(entities)
        self._fields = list(fields)
        self._pages = list(pages)
        self._result = []

    def execute(self, sql, *params):
        if "FROM Tenants" in sql:
            rows = self._tenants
            if "IsActive = 1" in sql:
                rows = [r for r in rows if r.IsActive]
            self._result = rows
        elif "FROM TenantEntities" in sql:
            rows = self._entities
            if "Status = 'active'" in sql:
                rows = [r for r in rows if getattr(r, "_status", "active") == "active"]
            self._result = rows
        elif "FROM TenantFields" in sql:
            rows = self._fields
            if "Status = 'active'" in sql:
                rows = [r for r in rows if getattr(r, "_status", "active") == "active"]
            self._result = rows
        elif "FROM TenantPages" in sql:
            rows = self._pages
            if "Status = 'active'" in sql:
                rows = [r for r in rows if getattr(r, "_status", "active") == "active"]
            self._result = rows
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
        tenants=[
            _tenant_row(code="ms02", is_active=True),
            _tenant_row(code="mothballed", is_active=False),
        ],
        entities=[
            _entity_row(entity_key="dossiers", status="active"),
            _entity_row(entity_key="archived", status="draft"),
        ],
    )
    monkeypatch.setattr(tr, "engine_nexora_db", eng)

    with app.app_context():
        reg = tr.registry()

    assert reg is not None
    # Active rows load.
    assert "ms02" in reg.tenants
    assert ("ms02", "dossiers") in reg.entities
    # Inactive/draft rows do not -- this only passes if the implementation's
    # SQL actually carries "WHERE IsActive = 1" / "WHERE Status = 'active'"
    # (see _FakeCursor.execute, which only filters when it finds that text).
    assert "mothballed" not in reg.tenants
    assert ("ms02", "archived") not in reg.entities
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


def test_unsafe_source_object_row_is_dropped_and_logged(app, monkeypatch, caplog):
    eng, _ = _engine_with(
        tenants=[_tenant_row()],
        entities=[
            _entity_row(entity_key="ok", source_object="dbo.Good"),
            _entity_row(entity_key="bad", source_object="bad;--name"),
        ],
    )
    monkeypatch.setattr(tr, "engine_nexora_db", eng)

    with app.app_context(), caplog.at_level(logging.ERROR):
        reg = tr.registry()

    assert reg is not None
    assert ("ms02", "ok") in reg.entities
    assert ("ms02", "bad") not in reg.entities
    # registry.py logs the drop via current_app.logger.error(...) -- confirm
    # it actually fired, naming the dropped row, not just that it's absent.
    assert any(
        "bad" in rec.message and "ms02" in rec.message and rec.levelno == logging.ERROR
        for rec in caplog.records
    )


def test_unsafe_column_name_row_is_dropped_and_logged(app, monkeypatch, caplog):
    eng, _ = _engine_with(
        tenants=[_tenant_row()],
        fields=[
            _field_row(column="GoodColumn"),
            _field_row(column="bad;--col"),
        ],
    )
    monkeypatch.setattr(tr, "engine_nexora_db", eng)

    with app.app_context(), caplog.at_level(logging.ERROR):
        reg = tr.registry()

    assert reg is not None
    columns = {f.column for f in reg.fields}
    assert "GoodColumn" in columns
    assert "bad;--col" not in columns
    # registry.py logs the drop via current_app.logger.error(...) -- confirm
    # it actually fired, naming the dropped row, not just that it's absent.
    assert any(
        "bad;--col" in rec.message and rec.levelno == logging.ERROR for rec in caplog.records
    )


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


def test_entity_for_returns_defensive_copy_of_labels(app, monkeypatch):
    """cache is Flask-Caching's SimpleCache (in-process dict, no
    serialization boundary) -- cache.get() hands back the exact object
    cache.set() stored. A caller mutating the returned .labels dict must
    never corrupt the shared cached registry, or every other tenant/request
    sees the corruption for up to _TTL seconds."""
    eng, _ = _engine_with(
        tenants=[_tenant_row()],
        entities=[_entity_row(entity_key="dossiers", label_en="Dossiers")],
    )
    monkeypatch.setattr(tr, "engine_nexora_db", eng)

    with app.app_context():
        first = tr.entity_for("ms02", "dossiers")
        first.labels["en"] = "CORRUPTED"

        second = tr.entity_for("ms02", "dossiers")

    assert second.labels["en"] == "Dossiers"


def test_fields_for_returns_defensive_copy_of_labels(app, monkeypatch):
    eng, _ = _engine_with(
        tenants=[_tenant_row()],
        fields=[_field_row(column="Status", label_en="Status")],
    )
    monkeypatch.setattr(tr, "engine_nexora_db", eng)

    with app.app_context():
        first = tr.fields_for("ms02", "dossiers")
        first[0].labels["en"] = "CORRUPTED"

        second = tr.fields_for("ms02", "dossiers")

    assert second[0].labels["en"] == "Status"


def test_pages_for_returns_defensive_copy_of_layout(app, monkeypatch):
    eng, _ = _engine_with(
        tenants=[_tenant_row()],
        pages=[_page_row(page_key="custom", layout_json='{"endpoint": "/x"}')],
    )
    monkeypatch.setattr(tr, "engine_nexora_db", eng)

    with app.app_context():
        first = tr.pages_for("ms02")
        first[0].layout["endpoint"] = "CORRUPTED"

        second = tr.pages_for("ms02")

    assert second[0].layout["endpoint"] == "/x"


# ------------------------------------------------- provision_tenant_permissions --


def test_provision_tenant_permissions_inserts_view_and_edit_idempotently():
    """Mirrors nx_lib/views/admin/processes.py's api_admin_process_source_add
    idempotent-insert shape: INSERT ... SELECT ... WHERE NOT EXISTS (SELECT 1
    FROM dbo.Permission p WHERE p.Code = ?), one call per permission code, so
    a second call (or a re-run of the seed migration) is a no-op rather than
    a duplicate-key error."""
    cursor = MagicMock()

    tr.provision_tenant_permissions(cursor, "ms02")

    assert cursor.execute.call_count == 2
    seen_codes = set()
    for call in cursor.execute.call_args_list:
        sql, params = call.args
        assert sql.startswith("INSERT INTO dbo.Permission")
        assert "WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = ?)" in sql
        code, description, code_again = params
        assert code == code_again  # same code bound to both the insert and the guard
        assert isinstance(description, str) and description
        seen_codes.add(code)
    assert seen_codes == {"tenant.ms02.view", "tenant.ms02.edit"}


def test_provision_tenant_permissions_never_commits():
    """Caller owns the transaction (commit/rollback) -- this only executes the
    two INSERTs on the cursor it's given, same as the process-source idiom it
    mirrors, where the surrounding view calls conn.commit() itself afterwards.

    Asserts against the actual cursor passed in (not an unrelated conn mock
    the function never touches) -- a bare MagicMock exposes .commit()/
    .rollback() too, so this is a real signal: it fails if
    provision_tenant_permissions ever calls anything but execute() on the
    object it was actually given."""
    cursor = MagicMock()

    tr.provision_tenant_permissions(cursor, "acme")

    cursor.commit.assert_not_called()
    cursor.rollback.assert_not_called()
    called_methods = {call[0] for call in cursor.method_calls}
    assert called_methods == {"execute"}, (
        f"provision_tenant_permissions called {called_methods} on its cursor -- "
        f"expected only execute()"
    )


# ---------------------------------------------------------------- organization_tenant --


def _org_engine(rows):
    cur = MagicMock()
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value = cur
    eng = MagicMock()
    eng.raw_connection.return_value = conn
    return eng


def test_organization_tenant_maps_org_to_its_tenant_and_caches(app, monkeypatch):
    eng = _org_engine([types.SimpleNamespace(organizationcode="PDBS", TenantCode="ms02")])
    monkeypatch.setattr(tr, "engine_nexora_db", eng)
    with app.app_context():
        assert tr.organization_tenant("PDBS") == "ms02"
        assert tr.organization_tenant("SYDC") is None  # not in a tenant
        assert tr.organization_tenant(None) is None
        assert tr.organization_tenant("PDBS") == "ms02"
    assert eng.raw_connection.call_count == 1  # second lookups hit the cache


def test_organization_tenant_fails_closed_to_not_scoped(app, monkeypatch):
    monkeypatch.setattr(tr, "engine_nexora_db", _dead_engine())
    with app.app_context():
        assert tr.organization_tenant("PDBS") is None
