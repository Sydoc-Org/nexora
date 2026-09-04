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

import types

from flask import url_for

import nx_lib.views.tenant as tv
from nx_lib.clients import CLIENTS, ClientConfig
from nx_lib.tenant.registry import Tenant, TenantEntity, TenantField, TenantPage

TENANT_CODE = "acme"


def _tenant():
    return Tenant(code=TENANT_CODE, display_name="Acme Co", active=True)


def _fake_registry(tenants):
    """Stand-in for the real TenantRegistry -- visible_tenant_nav() only ever
    reads .tenants off whatever registry() returns. ``entities`` is an empty
    dict, not omitted -- visible_tenant_nav() also calls the real
    entity_for(code, key) for list/crud pages' nav label (unless a test
    monkeypatches tv.entity_for itself), and the real entity_for() does
    ``reg.entities.get(...)`` on whatever registry() returns."""
    return types.SimpleNamespace(tenants=tenants, entities={})


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
        client_code=TENANT_CODE,
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
    name -- these tests are the route layer's own, not the registry's.

    ``registry()`` used to be stubbed as a bare ``object()`` sentinel (only
    ever used for its ``is not None`` truthiness by the route layer under
    test here). Since Task 6, ``nx_lib/hooks.py``'s ``_inject_tenant_nav``
    context processor runs on *every* render_template() call for a logged-in
    session -- including handlers/404.html on these very tests' 404 paths --
    and calls visible_tenant_nav(), which reads ``reg.tenants``. The sentinel
    has to be duck-type compatible with that now, not just non-None."""
    pages = pages or []
    fields = fields or []
    tenants = {TENANT_CODE: tenant} if tenant is not None else {}
    monkeypatch.setattr(tv, "registry", lambda: _fake_registry(tenants))
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
    # The #191 shim (templates/js/_tenant_page_js.html) is only ever included
    # from the available branch -- it dereferences entity/page/fields, which
    # are None/[] here. Never even attempted for the unavailable state.
    assert b"NX_TENANT" not in resp.data


# --------------------------------------------------- tenant_page rendering --


def test_tenant_page_renders_text_filter_input_for_category_field(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page()],
        entity=_entity(),
        fields=[_field(column="Status", semantic_role="category")],
    )

    resp = user_client.get(f"/t/{TENANT_CODE}/dossiers")

    assert resp.status_code == 200
    assert b'data-testid="tenant-filter-bar"' in resp.data
    assert b'data-testid="tenant-filter-Status"' in resp.data
    assert b'data-filter="filter_Status"' in resp.data


def test_tenant_page_renders_date_range_filter_for_first_date_field_only(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page()],
        entity=_entity(),
        fields=[
            _field(column="DueDate", semantic_role="date"),
            _field(column="ClosedDate", semantic_role="date"),
        ],
    )

    resp = user_client.get(f"/t/{TENANT_CODE}/dossiers")

    assert resp.status_code == 200
    assert b'data-filter="filter_DueDate_from"' in resp.data
    assert b'data-filter="filter_DueDate_to"' in resp.data
    # Only the first date-role field gets a range filter, per the brief.
    assert b"ClosedDate_from" not in resp.data
    assert b"ClosedDate_to" not in resp.data


def test_tenant_page_id_column_filter_always_renders(user_client, monkeypatch):
    """The filter bar itself is always present now (task-9 brief parity gap:
    /workitems' id-prefix search had no tenant-page equivalent) -- even an
    entity with no filterable descriptor fields at all still gets an
    id-column filter input, though a non-filterable field (money) gets none
    of its own."""
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page()],
        entity=_entity(id_column="Id"),
        fields=[_field(column="Amount", semantic_role="money")],
    )

    resp = user_client.get(f"/t/{TENANT_CODE}/dossiers")

    assert resp.status_code == 200
    assert b'data-testid="tenant-filter-bar"' in resp.data
    assert b'data-testid="tenant-filter-Id"' in resp.data
    assert b'data-filter="filter_Id"' in resp.data
    assert b'data-testid="tenant-filter-Amount"' not in resp.data


def test_tenant_page_renders_pagination_and_export_controls(user_client, monkeypatch):
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
    assert b'data-testid="tenant-page-prev"' in resp.data
    assert b'data-testid="tenant-page-next"' in resp.data
    assert b'data-testid="tenant-page-info"' in resp.data
    assert b'data-testid="admin-helpers-page-action-tenant-export"' in resp.data


def test_tenant_page_renders_crud_affordances_when_can_edit(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page(page_type="crud")],
        entity=_entity(),
        fields=[_field(column="Status")],
    )

    resp = user_client.get(f"/t/{TENANT_CODE}/dossiers")

    assert resp.status_code == 200
    assert b'data-testid="admin-helpers-page-action-tenant-add"' in resp.data
    assert b'data-testid="tenant-record-modal"' in resp.data
    assert b'data-testid="tenant-record-field-Status"' in resp.data


def test_tenant_page_hides_crud_affordances_for_list_page_type(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page(page_type="list")],
        entity=_entity(),
        fields=[_field(column="Status")],
    )

    resp = user_client.get(f"/t/{TENANT_CODE}/dossiers")

    assert resp.status_code == 200
    assert b'data-testid="admin-helpers-page-action-tenant-add"' not in resp.data
    assert b'data-testid="tenant-record-modal"' not in resp.data


def test_tenant_page_hides_crud_affordances_without_edit_permission(user_client, monkeypatch):
    # View allowed, edit denied -- can_edit is False so the Add button/modal
    # must not render even though the page itself is a crud page.
    monkeypatch.setattr(tv, "has_permission", lambda code: code.endswith(".view"))
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page(page_type="crud")],
        entity=_entity(),
        fields=[_field(column="Status")],
    )

    resp = user_client.get(f"/t/{TENANT_CODE}/dossiers")

    assert resp.status_code == 200
    assert b'data-testid="admin-helpers-page-action-tenant-add"' not in resp.data
    assert b'data-testid="tenant-record-modal"' not in resp.data
    # Export stays available to any viewer, regardless of edit rights.
    assert b'data-testid="admin-helpers-page-action-tenant-export"' in resp.data


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


def test_api_list_registry_unavailable_returns_503_not_404(user_client, monkeypatch):
    """A registry load failure (registry() returns None -- never cached) must
    surface as 503 unavailable, not the same 404 an actually-unknown
    tenant/page gets -- _resolve_page_entity checks registry() before ever
    calling tenant()/pages_for(), mirroring tenant_page's own upfront check."""
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    monkeypatch.setattr(tv, "registry", lambda: None)

    resp = user_client.get(f"/api/t/{TENANT_CODE}/dossiers")

    assert resp.status_code == 503
    assert resp.get_json() == {"success": False, "unavailable": True}


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


def test_api_list_id_column_filter_reaches_sql_as_prefix_match(user_client, monkeypatch):
    """?filter_<id_column>=... has no TenantFields row of its own (the id
    column isn't a descriptor field) -- _parse_filters must still forward it
    to build_list_query as a 'startswith' filter (task-9 brief parity gap)."""
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page()],
        entity=_entity(id_column="Id"),
        fields=[_field(column="Status")],
    )
    cursor = _FakeCursor(count=1, rows=[(11, "open")], cols=["Id", "Status"])
    monkeypatch.setitem(CLIENTS, TENANT_CODE, _client_with_engine(_FakeEngine(cursor)))

    resp = user_client.get(f"/api/t/{TENANT_CODE}/dossiers?filter_Id=11")

    assert resp.status_code == 200
    all_sql = " ".join(sql for sql, _params in cursor.executed)
    assert "[Id] LIKE ?" in all_sql
    all_params = [p for _sql, params in cursor.executed for p in params]
    assert "11%" in all_params


def test_tenant_page_exposes_entity_kind_for_the_view_link(user_client, monkeypatch):
    """window.NX_TENANT.entityKind drives static/js/tenant_pages.js's
    'documents'-only row link to the shared /workitems viewer (task-9 brief
    parity gap: the generic list page has no viewer of its own -- K4/K5 keep
    it on the shared machinery, so a 'documents' row links out instead)."""
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page(key="docs", entity="docs")],
        entity=_entity(key="docs", kind="documents", id_column="WorkItemID"),
        fields=[_field(column="Status")],
    )

    resp = user_client.get(f"/t/{TENANT_CODE}/docs")

    assert resp.status_code == 200
    assert b'entityKind: "documents"' in resp.data


def test_api_write_403_without_edit_permission(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: False)
    resp = user_client.post(f"/api/t/{TENANT_CODE}/dossiers", json={"Status": "open"})
    assert resp.status_code == 403


def test_api_write_registry_unavailable_returns_503_not_404(user_client, monkeypatch):
    """Same distinction as the list API's registry-down test, exercised on the
    require_entries=True path every write endpoint shares via
    _resolve_page_entity."""
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    monkeypatch.setattr(tv, "registry", lambda: None)

    resp = user_client.post(f"/api/t/{TENANT_CODE}/dossiers", json={"Status": "open"})

    assert resp.status_code == 503
    assert resp.get_json() == {"success": False, "unavailable": True}


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


def test_api_export_registry_unavailable_returns_503_not_404(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: True)
    monkeypatch.setattr(tv, "registry", lambda: None)

    resp = user_client.get(f"/api/t/{TENANT_CODE}/dossiers/export")

    assert resp.status_code == 503
    assert resp.get_json() == {"success": False, "unavailable": True}


# ---------------------------------------------------------- visible_tenant_nav --
#
# Task 6: [{"code", "label", "pages": [...]}] for every tenant the session
# holds tenant.<code>.view for -- consumed by nx_lib/hooks.py's
# _inject_tenant_nav context processor, which the header rendering tests
# below exercise end-to-end.


def test_visible_tenant_nav_empty_when_registry_unavailable(monkeypatch):
    monkeypatch.setattr(tv, "registry", lambda: None)
    assert tv.visible_tenant_nav() == []


def test_visible_tenant_nav_filters_by_view_permission(app, monkeypatch):
    acme = _tenant()
    other = Tenant(code="other", display_name="Other Co", active=True)
    monkeypatch.setattr(tv, "registry", lambda: _fake_registry({TENANT_CODE: acme, "other": other}))
    monkeypatch.setattr(
        tv, "pages_for", lambda code: [_page(key="dossiers")] if code == TENANT_CODE else []
    )
    # Only acme's view permission is held -- other's group must not appear.
    monkeypatch.setattr(tv, "has_permission", lambda code: code == f"tenant.{TENANT_CODE}.view")

    with app.test_request_context("/"):
        nav = tv.visible_tenant_nav()
        expected_url = url_for("tenant_page", tenant_code=TENANT_CODE, page_key="dossiers")

    assert [n["code"] for n in nav] == [TENANT_CODE]
    assert nav[0]["label"] == acme.display_name
    # No TenantEntity resolves for "dossiers" (the fake registry's .entities
    # is empty) -- label falls back to the raw PageKey, same as before this
    # fix wave's label enhancement (see the dedicated label-fallback tests
    # below for the entity-label case).
    assert nav[0]["pages"] == [
        {
            "key": "dossiers",
            "page_type": "list",
            "endpoint": None,
            "url": expected_url,
            "label": "dossiers",
        }
    ]


def test_visible_tenant_nav_custom_page_carries_layout_endpoint(app, monkeypatch):
    acme = _tenant()
    monkeypatch.setattr(tv, "registry", lambda: _fake_registry({TENANT_CODE: acme}))
    monkeypatch.setattr(
        tv,
        "pages_for",
        lambda code: [
            _page(key="dash", page_type="custom", entity=None, layout={"endpoint": "dashboard"})
        ],
    )
    monkeypatch.setattr(tv, "has_permission", lambda code: True)

    with app.test_request_context("/"):
        nav = tv.visible_tenant_nav()
        expected_url = url_for("dashboard")

    assert nav[0]["pages"] == [
        {
            "key": "dash",
            "page_type": "custom",
            "endpoint": "dashboard",
            "url": expected_url,
            "label": "dash",
            # presentation keys default when LayoutJSON carries none (07782e01)
            "icon": "fa-arrow-up-right-from-square",
            "active": "dashboard",
        }
    ]


def test_visible_tenant_nav_custom_page_with_unresolvable_endpoint_is_dropped(app, monkeypatch):
    """Gap (b): an endpoint that doesn't resolve (typo, removed route, an
    endpoint needing URL args this call can't supply) must never raise
    url_for's BuildError up through visible_tenant_nav() -- the page is
    simply omitted from the returned list."""
    acme = _tenant()
    monkeypatch.setattr(tv, "registry", lambda: _fake_registry({TENANT_CODE: acme}))
    monkeypatch.setattr(
        tv,
        "pages_for",
        lambda code: [
            _page(
                key="broken",
                page_type="custom",
                entity=None,
                layout={"endpoint": "no_such_endpoint_xyz"},
            )
        ],
    )
    monkeypatch.setattr(tv, "has_permission", lambda code: True)

    with app.test_request_context("/"):
        nav = tv.visible_tenant_nav()

    assert nav == [{"code": TENANT_CODE, "label": acme.display_name, "pages": []}]


def test_visible_tenant_nav_list_page_label_uses_entity_locale_label(app, monkeypatch):
    """Promoted minor: a list/crud page's nav label falls back to its
    entity's own locale label (TenantEntity.labels) rather than the raw
    PageKey slug -- MS02's seeded PageKey is the literal ProcessName
    ('sydoc.05_PDBS'), not something a user should ever read in a sidebar."""
    acme = _tenant()
    entity = _entity(key="sydoc.05_PDBS")  # labels={"en": "Dossiers", ...}
    monkeypatch.setattr(tv, "registry", lambda: _fake_registry({TENANT_CODE: acme}))
    monkeypatch.setattr(
        tv,
        "pages_for",
        lambda code: [_page(key="sydoc.05_PDBS", page_type="list", entity="sydoc.05_PDBS")],
    )
    monkeypatch.setattr(
        tv, "entity_for", lambda code, key: entity if key == "sydoc.05_PDBS" else None
    )
    monkeypatch.setattr(tv, "has_permission", lambda code: True)

    with app.test_request_context("/"):
        nav = tv.visible_tenant_nav()

    assert nav[0]["pages"][0]["key"] == "sydoc.05_PDBS"
    assert nav[0]["pages"][0]["label"] == "Dossiers"


def test_visible_tenant_nav_list_page_label_falls_back_to_page_key_without_entity(app, monkeypatch):
    acme = _tenant()
    monkeypatch.setattr(tv, "registry", lambda: _fake_registry({TENANT_CODE: acme}))
    monkeypatch.setattr(
        tv, "pages_for", lambda code: [_page(key="dossiers", page_type="list", entity="dossiers")]
    )
    monkeypatch.setattr(tv, "entity_for", lambda code, key: None)
    monkeypatch.setattr(tv, "has_permission", lambda code: True)

    with app.test_request_context("/"):
        nav = tv.visible_tenant_nav()

    assert nav[0]["pages"][0]["label"] == "dossiers"


# ------------------------------------------------------- header sidebar nav --
#
# End-to-end through nx_lib/hooks.py's _inject_tenant_nav context processor
# and templates/_header.html's per-tenant nav group -- driven via a real page
# render (GET /dashboard, dashboard.view-gated, which user@test.local holds)
# rather than /t/<tenant>/<page> itself, so the header's own tenant.<code>.view
# gate is exercised independently of tenant_page()'s own gate.


def test_header_shows_tenant_nav_group_with_view_permission(user_client, monkeypatch):
    acme = _tenant()
    monkeypatch.setattr(tv, "registry", lambda: _fake_registry({TENANT_CODE: acme}))
    monkeypatch.setattr(tv, "pages_for", lambda code: [_page(key="dossiers")])
    monkeypatch.setattr(tv, "has_permission", lambda code: code == f"tenant.{TENANT_CODE}.view")

    resp = user_client.get("/dashboard")

    assert resp.status_code == 200
    assert f'id="tenantNavGroup-{TENANT_CODE}"'.encode() in resp.data
    assert f'data-testid="header-nav-tenant-{TENANT_CODE}-toggle"'.encode() in resp.data
    assert f'data-testid="header-nav-tenant-{TENANT_CODE}-dossiers"'.encode() in resp.data


def test_header_hides_tenant_nav_group_without_view_permission(user_client, monkeypatch):
    acme = _tenant()
    monkeypatch.setattr(tv, "registry", lambda: _fake_registry({TENANT_CODE: acme}))
    monkeypatch.setattr(tv, "pages_for", lambda code: [_page(key="dossiers")])
    monkeypatch.setattr(tv, "has_permission", lambda code: False)

    resp = user_client.get("/dashboard")

    assert resp.status_code == 200
    assert b"tenantNavGroup-" not in resp.data


def test_header_shows_custom_page_link_with_resolved_url(user_client, monkeypatch):
    """No test previously exercised the page_type=='custom' nav branch
    end-to-end through Jinja/url_for -- only visible_tenant_nav()'s dict
    shape was unit-tested. This drives a real render and asserts the
    resolved <a href> actually appears."""
    acme = _tenant()
    monkeypatch.setattr(tv, "registry", lambda: _fake_registry({TENANT_CODE: acme}))
    monkeypatch.setattr(
        tv,
        "pages_for",
        lambda code: [
            _page(key="dash", page_type="custom", entity=None, layout={"endpoint": "dashboard"})
        ],
    )
    monkeypatch.setattr(tv, "has_permission", lambda code: code == f"tenant.{TENANT_CODE}.view")

    resp = user_client.get("/dashboard")

    assert resp.status_code == 200
    assert f'data-testid="header-nav-tenant-{TENANT_CODE}-dash"'.encode() in resp.data
    assert b'href="/dashboard"' in resp.data


def test_header_omits_custom_page_with_unresolvable_endpoint(user_client, monkeypatch):
    """Gap (b), end-to-end: a bad LayoutJSON endpoint (typo, removed route)
    must never raise url_for's BuildError inside _header.html and 500 the
    whole page for a user who holds the tenant's view permission -- the page
    renders fine and the broken nav entry is simply absent."""
    acme = _tenant()
    monkeypatch.setattr(tv, "registry", lambda: _fake_registry({TENANT_CODE: acme}))
    monkeypatch.setattr(
        tv,
        "pages_for",
        lambda code: [
            _page(
                key="broken",
                page_type="custom",
                entity=None,
                layout={"endpoint": "no_such_endpoint_xyz"},
            )
        ],
    )
    monkeypatch.setattr(tv, "has_permission", lambda code: code == f"tenant.{TENANT_CODE}.view")

    resp = user_client.get("/dashboard")

    assert resp.status_code == 200
    assert f'id="tenantNavGroup-{TENANT_CODE}"'.encode() in resp.data
    assert f'data-testid="header-nav-tenant-{TENANT_CODE}-broken"'.encode() not in resp.data


# ------------------------------------------------------------ membership (0096) --
#
# _can_view: a user whose organization belongs to the tenant sees it by right;
# everyone else needs tenant.<code>.view. Membership is stubbed through the
# module's own organization_tenant binding, the same way has_permission is.


def test_tenant_page_200_for_member_without_view_permission(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: False)
    monkeypatch.setattr(tv, "organization_tenant", lambda org: TENANT_CODE)
    _stub_registry(
        monkeypatch,
        tenant=_tenant(),
        pages=[_page()],
        entity=_entity(),
        fields=[_field(column="Status")],
    )
    assert user_client.get(f"/t/{TENANT_CODE}/dossiers").status_code == 200


def test_tenant_page_403_for_member_of_another_tenant(user_client, monkeypatch):
    monkeypatch.setattr(tv, "has_permission", lambda code: False)
    monkeypatch.setattr(tv, "organization_tenant", lambda org: "other")
    assert user_client.get(f"/t/{TENANT_CODE}/dossiers").status_code == 403


def test_visible_tenant_nav_includes_the_membership_tenant_without_a_grant(app, monkeypatch):
    acme = _tenant()
    other = Tenant(code="other", display_name="Other Co", active=True)
    monkeypatch.setattr(tv, "registry", lambda: _fake_registry({TENANT_CODE: acme, "other": other}))
    monkeypatch.setattr(tv, "pages_for", lambda code: [])
    monkeypatch.setattr(tv, "has_permission", lambda code: False)
    monkeypatch.setattr(tv, "organization_tenant", lambda org: TENANT_CODE)

    with app.test_request_context("/"):
        nav = tv.visible_tenant_nav()

    assert [n["code"] for n in nav] == [TENANT_CODE]


# ---------------------------------------------------- LayoutJSON query (0097) --


def test_visible_tenant_nav_custom_page_query_becomes_url_args(app, monkeypatch):
    acme = _tenant()
    monkeypatch.setattr(tv, "registry", lambda: _fake_registry({TENANT_CODE: acme}))
    monkeypatch.setattr(
        tv,
        "pages_for",
        lambda code: [
            _page(
                key="dashboard",
                page_type="custom",
                entity=None,
                layout={
                    "endpoint": "dashboard",
                    "query": {"tenant": TENANT_CODE, "bad": 1},
                    "active": f"tenant_{TENANT_CODE}_dashboard",
                },
            )
        ],
    )
    monkeypatch.setattr(tv, "has_permission", lambda code: True)

    with app.test_request_context("/"):
        (entry,) = tv.visible_tenant_nav()[0]["pages"]
        expected_url = url_for("dashboard", tenant=TENANT_CODE)

    assert entry["url"] == expected_url  # the non-string value is dropped
    assert entry["active"] == f"tenant_{TENANT_CODE}_dashboard"
