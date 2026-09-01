"""Integration tests for nx_lib.views.tenant -- the parametrized
``/t/<tenant_code>/<page_key>`` route family (registry.py Task 2, queries.py
Task 3, this route layer Task 4).

Permission is dynamic (``tenant.<code>.view``/``.edit``), checked *inside*
each view rather than via ``@require_permission`` (which only ever takes a
static string). Every test therefore monkeypatches
``nx_lib.views.tenant.has_permission`` directly -- the module's own imported
binding of the name, not ``nx_lib.security.has_permission`` -- the same
pattern ``tests/integration/test_admin_routes.py``'s ``no_restart_perm``
fixture uses for a view module that calls ``has_permission`` directly rather
than through the ``@require_permission`` decorator.

The registry collaborators (``registry()``, ``tenant()``, ``pages_for()``,
``entity_for()``, ``fields_for()``) are monkeypatched the same way -- these
tests exercise the route layer's own logic (permission gate placement,
404/503/redirect branching, CRUD ``Kind='entries'`` gating, the
filter/sort column allow-list), not the registry's DB-loading code
(``tests/unit/test_tenant_registry.py``) or the query builders
(``tests/unit/test_tenant_queries.py``).
"""

import nx_lib.views.tenant as tv
from nx_lib.clients import CLIENTS, ClientConfig
from nx_lib.tenant.registry import Tenant, TenantEntity, TenantField, TenantPage

TENANT_CODE = "acme"


def _tenant(client_code=TENANT_CODE):
    return Tenant(
        code=TENANT_CODE,
        display_name="Acme Co",
        organization_code="ACM",
        client_code=client_code,
        active=True,
    )


def _page(key="dossiers", page_type="list", entity="dossiers", layout=None, sort_order=100):
    return TenantPage(
        tenant=TENANT_CODE,
        key=key,
        page_type=page_type,
        entity=entity,
        layout=layout,
        sort_order=sort_order,
    )


def _entity(key="dossiers", kind="entries", engine_role="runtime", id_column="Id"):
    return TenantEntity(
        tenant=TENANT_CODE,
        key=key,
        source_object="dbo.Dossiers",
        kind=kind,
        engine_role=engine_role,
        id_column=id_column,
        labels={"en": "Dossiers", "de": None, "fr": None, "it": None},
        sort_order=100,
    )


def _field(column="Status", semantic_role="category", visible=True):
    return TenantField(
        tenant=TENANT_CODE,
        entity="dossiers",
        column=column,
        semantic_role=semantic_role,
        lookup_entity=None,
        labels={"en": column, "de": None, "fr": None, "it": None},
        visible=visible,
        sort_order=100,
    )


def _stub_registry(monkeypatch, *, tenant=None, pages=None, entity=None, fields=None):
    """Patch the registry-layer collaborators nx_lib.views.tenant imports by
    name -- these tests are the route layer's own, not the registry's."""
    pages = pages or []
    fields = fields or []
    monkeypatch.setattr(tv, "registry", lambda: object())
    monkeypatch.setattr(tv, "tenant", lambda code: tenant if code == TENANT_CODE else None)
    monkeypatch.setattr(tv, "pages_for", lambda code: pages if code == TENANT_CODE else [])
    monkeypatch.setattr(tv, "entity_for", lambda code, key: entity)
    monkeypatch.setattr(tv, "fields_for", lambda code, key: fields)


def _client_with_engine(engine, *, dialect="tsql"):
    return ClientConfig(
        code=TENANT_CODE,
        runtime_engine=engine,
        dialect=dialect,
        octo_domain=None,
        octo_client_id=None,
        octo_secret=None,
        octo_grant_type=None,
    )


class _FakeCursor:
    """Records every execute() call (sql, params) and hands back canned
    results -- fetchone() for a COUNT(*), fetchall()/description for a page
    query, matching how api_tenant_list/api_tenant_export drive a real
    pyodbc/psycopg2 cursor."""

    def __init__(self, count=0, rows=None, cols=None, rowcount=1):
        self.count = count
        self.rows = rows or []
        self.description = [(c,) for c in (cols or [])]
        self.rowcount = rowcount
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, list(params or [])))

    def fetchone(self):
        return [self.count]

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        pass


class _FakeEngine:
    def __init__(self, cursor):
        self.conn = _FakeConn(cursor)

    def raw_connection(self):
        return self.conn


# ------------------------------------------------------------- tenant_page --


def test_tenant_page_403_without_view_permission(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: False)
    resp = user_client.get(f"/t/{TENANT_CODE}/dossiers")
    assert resp.status_code == 403


def test_tenant_page_404_for_unknown_tenant_or_page(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)

    # Unknown tenant entirely.
    _stub_registry(monkeypatch, tenant=None, pages=[])
    resp = user_client.get("/t/unknown/nope")
    assert resp.status_code == 404

    # Known tenant, but the page key isn't in its page list.
    _stub_registry(monkeypatch, tenant=_tenant(), pages=[_page(key="dossiers")])
    resp = user_client.get(f"/t/{TENANT_CODE}/does-not-exist")
    assert resp.status_code == 404


def test_tenant_page_200_with_permission(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page()],
        entity=_entity(),
        fields=[_field(column="Status")],
    )

    resp = user_client.get(f"/t/{TENANT_CODE}/dossiers")

    assert resp.status_code == 200
    assert b"Status" in resp.data
    assert b"tenant-page-unavailable" not in resp.data


def test_tenant_page_renders_unavailable_state_when_registry_none(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    monkeypatch.setattr(tv, "registry", lambda: None)

    resp = user_client.get(f"/t/{TENANT_CODE}/dossiers")

    assert resp.status_code == 200
    assert b"tenant-page-unavailable" in resp.data


def test_custom_page_redirects_to_layout_endpoint(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[
            _page(key="custom1", page_type="custom", entity=None, layout={"endpoint": "dashboard"})
        ],
    )

    resp = user_client.get(f"/t/{TENANT_CODE}/custom1", follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/dashboard")


def test_custom_page_404_without_endpoint_in_layout(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page(key="custom1", page_type="custom", entity=None, layout=None)],
    )

    resp = user_client.get(f"/t/{TENANT_CODE}/custom1")

    assert resp.status_code == 404


# ---------------------------------------------------------------- api_list --


def test_api_list_403_without_view_permission(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: False)
    resp = user_client.get(f"/api/t/{TENANT_CODE}/dossiers")
    assert resp.status_code == 403


def test_api_list_engine_missing_returns_503_not_empty(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page()],
        entity=_entity(engine_role="runtime"),
        fields=[_field()],
    )
    monkeypatch.setitem(CLIENTS, TENANT_CODE, _client_with_engine(None))

    resp = user_client.get(f"/api/t/{TENANT_CODE}/dossiers")

    assert resp.status_code == 503
    assert resp.get_json() == {"success": False, "unavailable": True}


def test_api_list_success_returns_rows_and_ignores_unknown_filter_column(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page()],
        entity=_entity(),
        fields=[_field(column="Status")],
    )
    cursor = _FakeCursor(count=1, rows=[(1, "open")], cols=["Id", "Status"])
    monkeypatch.setitem(CLIENTS, TENANT_CODE, _client_with_engine(_FakeEngine(cursor)))

    resp = user_client.get(
        f"/api/t/{TENANT_CODE}/dossiers?filter_Status=open&filter_SecretColumn=x&sort=SecretColumn"
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["total"] == 1
    assert body["rows"] == [{"Id": 1, "Status": "open"}]
    # Security invariant: a query-string column absent from fields_for(...)
    # never reaches the SQL text, whether as a filter or a sort column.
    all_sql = " ".join(sql for sql, _params in cursor.executed)
    assert "SecretColumn" not in all_sql
    assert "Status" in all_sql


# --------------------------------------------------------------- api write --


def test_api_write_403_without_edit_permission(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: False)
    resp = user_client.post(f"/api/t/{TENANT_CODE}/dossiers", json={"Status": "open"})
    assert resp.status_code == 403


def test_api_write_404_for_documents_entity(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page(key="docs", entity="docs")],
        entity=_entity(key="docs", kind="documents"),
        fields=[_field()],
    )

    resp = user_client.post(f"/api/t/{TENANT_CODE}/docs", json={"Status": "open"})

    assert resp.status_code == 404


def test_api_write_add_success_with_validated_values(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page()],
        entity=_entity(),
        fields=[_field(column="Status", semantic_role="category")],
    )
    cursor = _FakeCursor()
    engine = _FakeEngine(cursor)
    monkeypatch.setitem(CLIENTS, TENANT_CODE, _client_with_engine(engine))

    resp = user_client.post(f"/api/t/{TENANT_CODE}/dossiers", json={"Status": "open"})

    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    assert engine.conn.committed is True
    sql, params = cursor.executed[0]
    assert sql.startswith("INSERT INTO")
    assert params == ["open"]


def test_api_write_add_rejects_invalid_date(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page()],
        entity=_entity(),
        fields=[
            _field(column="Status", semantic_role="category"),
            _field(column="DueDate", semantic_role="date"),
        ],
    )
    monkeypatch.setitem(CLIENTS, TENANT_CODE, _client_with_engine(_FakeEngine(_FakeCursor())))

    resp = user_client.post(
        f"/api/t/{TENANT_CODE}/dossiers", json={"Status": "open", "DueDate": "not-a-date"}
    )

    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_api_write_edit_not_found_returns_404(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page()],
        entity=_entity(),
        fields=[_field(column="Status")],
    )
    cursor = _FakeCursor(rowcount=0)
    monkeypatch.setitem(CLIENTS, TENANT_CODE, _client_with_engine(_FakeEngine(cursor)))

    resp = user_client.post(f"/api/t/{TENANT_CODE}/dossiers/999", json={"Status": "open"})

    assert resp.status_code == 404


def test_api_write_delete_not_found_returns_404(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page()],
        entity=_entity(),
        fields=[_field(column="Status")],
    )
    cursor = _FakeCursor(rowcount=0)
    monkeypatch.setitem(CLIENTS, TENANT_CODE, _client_with_engine(_FakeEngine(cursor)))

    resp = user_client.delete(f"/api/t/{TENANT_CODE}/dossiers/999")

    assert resp.status_code == 404


def test_api_write_delete_success(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page()],
        entity=_entity(),
        fields=[_field(column="Status")],
    )
    cursor = _FakeCursor(rowcount=1)
    engine = _FakeEngine(cursor)
    monkeypatch.setitem(CLIENTS, TENANT_CODE, _client_with_engine(engine))

    resp = user_client.delete(f"/api/t/{TENANT_CODE}/dossiers/42")

    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    sql, params = cursor.executed[0]
    assert sql.startswith("DELETE FROM")
    assert params == [42]  # _coerce_record_id: "42" -> int 42
    assert engine.conn.committed is True


# -------------------------------------------------------------- api_export --


def test_api_tenant_export_returns_xlsx(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page()],
        entity=_entity(),
        fields=[_field(column="Status")],
    )
    cursor = _FakeCursor(rows=[(1, "open")], cols=["Id", "Status"])
    monkeypatch.setitem(CLIENTS, TENANT_CODE, _client_with_engine(_FakeEngine(cursor)))

    resp = user_client.get(f"/api/t/{TENANT_CODE}/dossiers/export")

    assert resp.status_code == 200
    assert resp.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment" in resp.headers.get("Content-Disposition", "")
