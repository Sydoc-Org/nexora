"""Unit tests for nx_lib.tenant.reporting_sync -- ReportingSources sync for
T-SQL tenant `documents` entities (K6).

The tenant registry (`registry()`/`fields_for()`) is stubbed the same way
tests/integration/test_tenant_routes.py stubs nx_lib.views.tenant's registry
collaborators -- this module's own logic (dialect/engine resolution, the
MERGE shape, skip-and-log branching) is what's under test here, not the
registry's own DB-loading code (tests/unit/test_tenant_registry.py).

The MERGE write itself is mocked the same way tests/unit/test_prepared_documents.py
mocks engine_nexora_db.raw_connection() for nx_lib.prepared_documents's own
MERGE exemplar.

CLIENTS is the real shared dict from nx_lib.clients (monkeypatch.setitem, not
a module-local copy) -- reporting_sync.py's `from ..clients import CLIENTS`
and this test's `from nx_lib.clients import CLIENTS` are the same object.
"""

import json
import logging
from unittest.mock import MagicMock

import pytest

import nx_lib.tenant.reporting_sync as rs
from nx_lib.clients import CLIENTS, ClientConfig
from nx_lib.tenant.registry import Tenant, TenantEntity, TenantField

TENANT_CODE = "acme"


def _tenant(client_code=TENANT_CODE, display_name="Acme Co"):
    return Tenant(
        code=TENANT_CODE,
        display_name=display_name,
        organization_code="ACM",
        client_code=client_code,
        active=True,
    )


def _entity(
    key="dossiers",
    kind="documents",
    engine_role="runtime",
    source_object="dbo.Dossiers",
    label_en="Dossiers",
    sort_order=150,
):
    return TenantEntity(
        tenant=TENANT_CODE,
        key=key,
        source_object=source_object,
        kind=kind,
        engine_role=engine_role,
        id_column="Id",
        labels={"en": label_en, "de": None, "fr": None, "it": None},
        sort_order=sort_order,
    )


def _field(column="Status", semantic_role="category", visible=True, sort_order=100):
    return TenantField(
        tenant=TENANT_CODE,
        entity="dossiers",
        column=column,
        semantic_role=semantic_role,
        lookup_entity=None,
        labels={"en": column, "de": None, "fr": None, "it": None},
        visible=visible,
        sort_order=sort_order,
    )


def _client_with(runtime_engine, *, dialect="tsql", stats_engine=None, stats_dialect="tsql"):
    return ClientConfig(
        code=TENANT_CODE,
        runtime_engine=runtime_engine,
        dialect=dialect,
        octo_domain="x",
        octo_client_id="x",
        octo_secret="x",
        octo_grant_type="x",
        stats_engine=stats_engine,
        stats_dialect=stats_dialect,
    )


def _fake_registry(tenants=None, entities=None):
    class _Reg:
        def __init__(self):
            self.tenants = tenants or {}
            self.entities = entities or {}

    return _Reg()


def _stub_registry(monkeypatch, *, tenant=None, entities=None, fields=None):
    tenants = {TENANT_CODE: tenant} if tenant is not None else {}
    entities = entities or {}
    fields = fields if fields is not None else []
    monkeypatch.setattr(rs, "registry", lambda: _fake_registry(tenants, entities))
    monkeypatch.setattr(rs, "fields_for", lambda code, key: fields)


def _mock_engine():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    engine = MagicMock()
    engine.raw_connection.return_value = conn
    return engine, conn, cur


@pytest.fixture(autouse=True)
def _clean_clients():
    """CLIENTS is the shared process-wide registry -- restore it after every
    test even though monkeypatch.setitem also undoes its own writes, so a
    test that replaces the key outright (not via setitem) can't leak."""
    original = dict(CLIENTS)
    yield
    CLIENTS.clear()
    CLIENTS.update(original)


# --------------------------------------------------------------- happy path --


def test_sync_upserts_one_row_for_tsql_documents_entity(app, monkeypatch):
    entity = _entity()
    monkeypatch.setitem(CLIENTS, TENANT_CODE, _client_with(rs.engine_statistics_db, dialect="tsql"))
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        entities={(TENANT_CODE, "dossiers"): entity},
        fields=[_field(column="Status", visible=True)],
    )
    engine, conn, cur = _mock_engine()
    monkeypatch.setattr(rs, "engine_nexora_db", engine)

    with app.app_context():
        result = rs.sync_tenant_reporting_sources()

    assert result == {"synced": 1, "skipped": 0}
    cur.execute.assert_called_once()
    sql, params = cur.execute.call_args.args
    assert "MERGE dbo.ReportingSources" in sql
    assert "ON tgt.Code = src.Code" in sql
    assert params[0] == "tenant_acme_dossiers"  # Code (src side)
    # WHEN MATCHED UPDATE SET Kind, Label, Permission, Engine, Provider, BaseObject, ...
    assert params[1] == "curated"
    assert params[2] == "Acme Co — Dossiers"
    assert params[3] == "tenant.acme.view"
    assert params[4] == "statistics"
    assert params[5] == "table"
    assert params[6] == "dbo.Dossiers"
    columns = json.loads(params[7])
    assert columns == [
        {
            "field": "Status",
            "label": "Status",
            "type": "string",
            "filterable": True,
            "sortable": True,
        }
    ]
    assert params[8] == 1  # Enabled
    assert params[9] == 150  # SortOrder
    # Code repeated for the INSERT branch, values repeated identically.
    assert params[10] == "tenant_acme_dossiers"
    assert params[11:] == params[1:10]
    conn.commit.assert_called_once()
    conn.close.assert_called_once()


def test_sync_maps_semantic_roles_to_columns_json_types_and_hides_invisible_fields(
    app, monkeypatch
):
    entity = _entity()
    monkeypatch.setitem(CLIENTS, TENANT_CODE, _client_with(rs.engine_octo_db, dialect="tsql"))
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        entities={(TENANT_CODE, "dossiers"): entity},
        fields=[
            _field(column="OpenedOn", semantic_role="date", visible=True, sort_order=100),
            _field(column="AmountDue", semantic_role="money", visible=True, sort_order=200),
            _field(column="ItemCount", semantic_role="count", visible=True, sort_order=300),
            _field(column="Secret", semantic_role="text", visible=False, sort_order=400),
        ],
    )
    engine, conn, cur = _mock_engine()
    monkeypatch.setattr(rs, "engine_nexora_db", engine)

    with app.app_context():
        result = rs.sync_tenant_reporting_sources()

    assert result == {"synced": 1, "skipped": 0}
    _sql, params = cur.execute.call_args.args
    columns = json.loads(params[7])
    assert [c["field"] for c in columns] == ["OpenedOn", "AmountDue", "ItemCount"]
    assert {c["field"]: c["type"] for c in columns} == {
        "OpenedOn": "date",
        "AmountDue": "number",
        "ItemCount": "number",
    }
    assert params[4] == "octopus"


# ------------------------------------------------------------- skip + log --


def test_sync_skips_postgres_dialect_tenant_and_logs(app, monkeypatch, caplog):
    """The MS02-shaped case: a documents entity whose resolved dialect is
    'postgres' is skipped with a logged notice, not written -- K6 deferral."""
    entity = _entity()
    monkeypatch.setitem(CLIENTS, TENANT_CODE, _client_with(rs.engine_octo_db, dialect="postgres"))
    _stub_registry(
        monkeypatch, tenant=_tenant(), entities={(TENANT_CODE, "dossiers"): entity}, fields=[]
    )

    with app.app_context(), caplog.at_level(logging.INFO):
        result = rs.sync_tenant_reporting_sources()

    assert result == {"synced": 0, "skipped": 1}
    assert any("dossiers" in rec.message and "postgres" in rec.message for rec in caplog.records)


def test_sync_skips_engine_unmapped_to_curated_engines_and_logs(app, monkeypatch, caplog):
    entity = _entity()
    # tsql dialect, but the runtime engine is some object that isn't one of
    # the four _CURATED_ENGINES engines (e.g. a client-scoped engine with no
    # curated reporting counterpart).
    monkeypatch.setitem(CLIENTS, TENANT_CODE, _client_with(object(), dialect="tsql"))
    _stub_registry(
        monkeypatch, tenant=_tenant(), entities={(TENANT_CODE, "dossiers"): entity}, fields=[]
    )

    with app.app_context(), caplog.at_level(logging.INFO):
        result = rs.sync_tenant_reporting_sources()

    assert result == {"synced": 0, "skipped": 1}
    assert any("_CURATED_ENGINES" in rec.message for rec in caplog.records)


def test_sync_skips_entity_whose_tenant_is_not_in_clients(app, monkeypatch, caplog):
    entity = _entity()
    CLIENTS.pop(TENANT_CODE, None)
    _stub_registry(
        monkeypatch, tenant=_tenant(), entities={(TENANT_CODE, "dossiers"): entity}, fields=[]
    )

    with app.app_context(), caplog.at_level(logging.INFO):
        result = rs.sync_tenant_reporting_sources()

    assert result == {"synced": 0, "skipped": 1}


def test_sync_ignores_non_documents_kind_entities_without_counting_them_skipped(app, monkeypatch):
    entity = _entity(key="tasks", kind="entries")
    monkeypatch.setitem(CLIENTS, TENANT_CODE, _client_with(rs.engine_octo_db, dialect="tsql"))
    _stub_registry(
        monkeypatch, tenant=_tenant(), entities={(TENANT_CODE, "tasks"): entity}, fields=[]
    )
    engine, conn, cur = _mock_engine()
    monkeypatch.setattr(rs, "engine_nexora_db", engine)

    with app.app_context():
        result = rs.sync_tenant_reporting_sources()

    assert result == {"synced": 0, "skipped": 0}
    engine.raw_connection.assert_not_called()


def test_sync_registry_unavailable_returns_zero_and_never_connects(app, monkeypatch, caplog):
    monkeypatch.setattr(rs, "registry", lambda: None)
    engine, conn, cur = _mock_engine()
    monkeypatch.setattr(rs, "engine_nexora_db", engine)

    with app.app_context(), caplog.at_level(logging.ERROR):
        result = rs.sync_tenant_reporting_sources()

    assert result == {"synced": 0, "skipped": 0}
    engine.raw_connection.assert_not_called()
    assert any(rec.levelno == logging.ERROR for rec in caplog.records)


# ----------------------------------------------------------------- rerun --


def test_sync_rerun_upserts_via_merge_on_code_not_a_second_insert_path(app, monkeypatch):
    """Re-running issues the same MERGE-on-Code statement again (idempotence
    is a property of the MERGE ... ON tgt.Code = src.Code shape itself, which
    UQ_ReportingSources_Code backs against a real duplicate) -- not a second,
    different code path on the second call."""
    entity = _entity()
    monkeypatch.setitem(CLIENTS, TENANT_CODE, _client_with(rs.engine_statistics_db, dialect="tsql"))
    _stub_registry(
        monkeypatch, tenant=_tenant(), entities={(TENANT_CODE, "dossiers"): entity}, fields=[]
    )
    engine, conn, cur = _mock_engine()
    monkeypatch.setattr(rs, "engine_nexora_db", engine)

    with app.app_context():
        first = rs.sync_tenant_reporting_sources()
        second = rs.sync_tenant_reporting_sources()

    assert first == second == {"synced": 1, "skipped": 0}
    assert cur.execute.call_count == 2
    first_call, second_call = cur.execute.call_args_list
    assert first_call.args[0] == second_call.args[0]  # identical MERGE SQL text
    assert first_call.args[1][0] == second_call.args[1][0] == "tenant_acme_dossiers"


# --------------------------------------------------------------- db error --


def test_sync_db_error_rolls_back_logs_and_returns_partial_counts(app, monkeypatch, caplog):
    entity = _entity()
    monkeypatch.setitem(CLIENTS, TENANT_CODE, _client_with(rs.engine_statistics_db, dialect="tsql"))
    _stub_registry(
        monkeypatch, tenant=_tenant(), entities={(TENANT_CODE, "dossiers"): entity}, fields=[]
    )
    engine, conn, cur = _mock_engine()
    cur.execute.side_effect = RuntimeError("boom")
    monkeypatch.setattr(rs, "engine_nexora_db", engine)

    with app.app_context(), caplog.at_level(logging.ERROR):
        result = rs.sync_tenant_reporting_sources()

    assert result == {"synced": 0, "skipped": 0}
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
    conn.close.assert_called_once()
    assert any("boom" in rec.message for rec in caplog.records)
