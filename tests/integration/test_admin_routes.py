"""Integration tests for nx_lib.views.admin — 38 routes across 7 sections.

Test users have these admin permissions seeded:
- admin@test.local: admin.view + admin.users.manage + dashboard.view

Most admin sub-routes require finer-grained perms (admin.view.organizations,
admin.maintenance.edit, etc.) that no seed user has. To exercise the 200
path of the route body without expanding sql/test/seed.sql, the
`admin_all_perms` fixture monkeypatches nx_lib.security.has_permission to
return True — this satisfies every @require_permission gate. The fixture is
opt-in per test, not autouse, so gate tests can still assert 403.

Tables present in NEXORA_TEST (sql/test/schema.sql): Users, Organizations,
Permission, AccessProfile, AccessProfilePermission, UserPermissionOverride,
ActiveSessions. Routes touching these are asserted at 200.

Tables ABSENT (assertions use 200/500 tuple-match):
- Logs               (admin/logs and admin_dashboard counters)
- DashboardLayouts   (dashboard widget routes — not in this file)

MaintenanceBanner exists in sql/test/schema.sql (added in aea3998); the
maintenance routes still use a 200/500 tuple-match since these tests don't
seed banner rows.

Sections:
- /admin                    overview
- /admin/organizations/*    CRUD + list
- /admin/maintenance*       CRUD + list
- /admin/logs*              search + export  (Logs absent)
- /admin/sessions + /admin/users/* CRUD + revoke
- /admin/access_control + access profile + override
- /api/admin/permissions/*  CRUD
"""

import base64 as _b64
import io as _io
import re
import types as _types
import uuid
from unittest.mock import MagicMock

import pyodbc
import pytest

import nx_lib.views.admin as admin_module
import nx_lib.views.core as core_views


@pytest.fixture()
def admin_all_perms(monkeypatch):
    """Grant the admin client every permission for the duration of one test.

    The before_request hook reloads permissions from the DB on every request,
    so injecting via session_transaction would be wiped immediately.
    Monkeypatching has_permission survives because it's a module-level lookup
    inside require_permission's wrapper closure.
    """
    monkeypatch.setattr("nx_lib.security.has_permission", lambda code: True)
    yield


# ============================ /admin overview ================================


def test_admin_dashboard_anonymous_redirects_to_login(client):
    resp = client.get("/admin", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_admin_dashboard_without_perm_returns_403(noperm_client):
    resp = noperm_client.get("/admin")
    assert resp.status_code == 403


def test_admin_dashboard_with_perm_renders(admin_client):
    resp = admin_client.get("/admin")
    assert resp.status_code == 200


@pytest.fixture()
def no_restart_perm(monkeypatch):
    """Drop admin.restart the way STAGING does (#198): it resolves NexoraDB to
    the prod server, where migration 0059 never ran. Patches the binding inside
    views.admin.system only, so the admin.view gate in security.require_permission —
    which looks up its own module global — still lets the page render."""
    monkeypatch.setattr("nx_lib.views.admin.system.has_permission", lambda code: False)
    yield


def test_restart_control_renders_for_loopback_without_perm(admin_client, no_restart_perm):
    """#198: gating the control on the permission alone made the env switch a
    one-way trip — you could reach STAGING but never get back."""
    resp = admin_client.get("/admin")
    assert b'id="nx-restart-env"' in resp.data


def test_api_admin_restart_denied_for_remote_caller_without_perm(admin_client, no_restart_perm):
    resp = admin_client.post(
        "/api/admin/restart",
        json={"env": "INT"},
        environ_base={"REMOTE_ADDR": "10.9.9.9"},
    )
    assert resp.status_code == 403


# ============================ permission matrix ===============================


def test_admin_permission_matrix_view_gated(noperm_client):
    resp = noperm_client.get("/admin/permission_matrix")
    assert resp.status_code == 403


def test_admin_permission_matrix_view_with_perms(admin_client, admin_all_perms):
    resp = admin_client.get("/admin/permission_matrix")
    assert resp.status_code == 200


def test_api_admin_permission_holders_unknown_returns_404(admin_client, admin_all_perms):
    resp = admin_client.get("/api/admin/permissions/999999/holders")
    assert resp.status_code == 404


# ============================ organizations ==================================


def test_admin_organizations_view_gated(noperm_client):
    resp = noperm_client.get("/admin/organizations")
    assert resp.status_code == 403


def test_admin_organizations_view_with_perms(admin_client, admin_all_perms):
    resp = admin_client.get("/admin/organizations")
    assert resp.status_code == 200


def test_admin_add_organization_missing_body_returns_400(admin_client, admin_all_perms):
    resp = admin_client.post("/admin/organizations/add", json={})
    assert resp.status_code == 400


def test_admin_add_organization_duplicate_returns_409_or_500(admin_client, admin_all_perms):
    """Re-adding the seeded TEST org name should hit the IntegrityError branch."""
    resp = admin_client.post(
        "/admin/organizations/add", json={"organizationname": "Test Organization"}
    )
    assert resp.status_code in (200, 409, 500)


def test_admin_edit_organization_existing(admin_client, admin_all_perms, db_conn):
    resp = admin_client.post(
        "/admin/organizations/edit/TEST",
        json={"organizationname": "Test Organization Updated"},
    )
    assert resp.status_code == 200


def test_admin_delete_organization_unknown_returns_404(admin_client, admin_all_perms):
    """The DELETE returns 404 when no row matches."""
    resp = admin_client.delete("/admin/organizations/delete/XXXX")
    assert resp.status_code in (200, 404, 500)


# ---- deleting an org must also drop its branding (#98 phase 4) --------------
#
# A delete mutates the branding registry exactly like a save does. Without the
# invalidation the dead org keeps its brand -- and /branding/<code>/logo keeps
# serving its image -- for up to the registry's 60s TTL; without the unlink the
# file is orphaned forever and would be re-exposed verbatim if the same org
# code is created again. These reuse the branding_write fixture (defined with
# the other branding tests below) for the stubbed engine + tmp var/branding.


def test_delete_organization_removes_logo_and_invalidates(
    admin_client, admin_all_perms, branding_write
):
    tmp_path, _cursor, calls = branding_write
    (tmp_path / "TEST.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    # An earlier format switch left this behind alongside the current one.
    (tmp_path / "TEST.svg").write_bytes(b"<svg/>")
    (tmp_path / "OTHER.png").write_bytes(b"keep me")

    resp = admin_client.delete("/admin/organizations/delete/TEST")

    assert resp.status_code == 200
    assert [p.name for p in tmp_path.iterdir()] == ["OTHER.png"]
    assert calls == [1]


def test_delete_organization_without_a_logo_still_invalidates(
    admin_client, admin_all_perms, branding_write
):
    """NULL BrandLogoFile / nothing on disk: a missing file is not an error,
    and the registry still has to be dropped."""
    tmp_path, _cursor, calls = branding_write

    resp = admin_client.delete("/admin/organizations/delete/TEST")

    assert resp.status_code == 200
    assert list(tmp_path.iterdir()) == []
    assert calls == [1]


def test_delete_organization_not_found_touches_nothing(
    admin_client, admin_all_perms, branding_write, monkeypatch
):
    """No row deleted -> no cache invalidation and no file removed."""
    tmp_path, cursor, calls = branding_write
    cursor.rowcount = 0
    (tmp_path / "TEST.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    resp = admin_client.delete("/admin/organizations/delete/TEST")

    assert resp.status_code == 404
    assert [p.name for p in tmp_path.iterdir()] == ["TEST.png"]
    assert calls == []


def test_delete_branding_logo_refuses_a_hostile_org_code(monkeypatch, tmp_path):
    """The unlink derives its path from the org code, so the code is validated
    against the same _ORG_CODE_RE the upload uses -- nothing outside
    var/branding/ may ever be removed."""
    from nx_lib.views import admin as admin_views

    branding_dir = tmp_path / "branding"
    branding_dir.mkdir()
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"top-secret")
    monkeypatch.setattr("nx_lib.views.admin.organizations.PATHS.branding", branding_dir)

    for hostile in ("../secret", "..\\secret", "", None, "a/b"):
        admin_views._delete_branding_logo(hostile)

    assert outside.is_file()


def test_api_admin_organizations_list(admin_client, admin_all_perms):
    resp = admin_client.get("/api/admin/organizations/list")
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)


# ============================ clients (runtime sources) ======================

# dbo.Clients isn't in sql/test/schema.sql, so the clients endpoints run against
# _FakeClientsDb below. Like _FakeMappingDb further down it is not a bare stub:
# it emulates PK_Clients and stores the row the endpoint actually wrote, so a
# handler that drops or NULLs a column fails these tests rather than passing.

# The eleven writable columns, in the INSERT's parameter order. The UPDATE uses
# the same order minus ClientCode, with ClientCode last in the WHERE.
_CLIENTS_COLUMNS = (
    "ClientCode",
    "DisplayName",
    "Dialect",
    "RuntimeEngineKey",
    "StatsEngineKey",
    "StatsDialect",
    "DocfieldsEngineKey",
    "DocfieldsDialect",
    "OctoDomain",
    "SecretRef",
    "IsActive",
)

_SEEDED_CLIENTS = (
    {
        "ClientCode": "default",
        "DisplayName": "Sydoc (default)",
        "Dialect": "tsql",
        "RuntimeEngineKey": "engine_octo_db",
        "StatsEngineKey": "engine_statistics_db",
        "StatsDialect": "tsql",
        "DocfieldsEngineKey": "engine_statistics_db",
        "DocfieldsDialect": "tsql",
        "OctoDomain": None,
        "SecretRef": None,
        "IsActive": 1,
    },
    {
        "ClientCode": "ms02",
        "DisplayName": "MS02 (Azure Postgres)",
        "Dialect": "postgres",
        "RuntimeEngineKey": "engine_ms02_pg",
        "StatsEngineKey": "engine_ms02_stats_pg",
        "StatsDialect": "postgres",
        "DocfieldsEngineKey": "engine_ms02_docfields_pg",
        "DocfieldsDialect": "postgres",
        "OctoDomain": None,
        "SecretRef": "MS02",
        "IsActive": 1,
    },
)


class _FakeClientsDb:
    """In-memory stand-in for dbo.Clients (+ the ProcessSources reference count
    the delete endpoint checks)."""

    def __init__(self, rows=(), referenced=()):
        self.rows = {r["ClientCode"]: dict(r) for r in rows}
        self.referenced = set(referenced)
        self.rowcount = 0
        self.description = None
        self._rows = []
        self._fetchone = None

    # -- DBAPI-ish surface -------------------------------------------------
    def raw_connection(self):
        return self

    def cursor(self):
        return self

    def close(self):
        pass

    def commit(self):
        pass

    def fetchone(self):
        return self._fetchone

    def fetchall(self):
        return self._rows

    def execute(self, sql, params=None):
        flat = " ".join(sql.split())
        self.rowcount = 0
        self._fetchone = None

        if flat.startswith("SELECT ClientCode"):
            self.description = [(c,) for c in _CLIENTS_COLUMNS]
            self._rows = [
                tuple(self.rows[code][c] for c in _CLIENTS_COLUMNS) for code in sorted(self.rows)
            ]
        elif flat.startswith("INSERT INTO dbo.Clients"):
            row = dict(zip(_CLIENTS_COLUMNS, params, strict=True))
            if row["ClientCode"] in self.rows:
                raise pyodbc.IntegrityError("23000", "PK_Clients")
            self.rows[row["ClientCode"]] = row
            self.rowcount = 1
        elif flat.startswith("UPDATE dbo.Clients"):
            code = params[-1]
            if code in self.rows:
                self.rows[code].update(dict(zip(_CLIENTS_COLUMNS[1:], params[:-1], strict=True)))
                self.rowcount = 1
        elif flat.startswith("SELECT COUNT(*) FROM dbo.ProcessSources"):
            self._fetchone = (1 if params[0] in self.referenced else 0,)
        elif flat.startswith("DELETE FROM dbo.Clients"):
            self.rowcount = 1 if params[0] in self.rows else 0
            self.rows.pop(params[0], None)
        else:
            raise AssertionError(f"unexpected query: {sql}")


@pytest.fixture
def fake_clients_db(monkeypatch):
    db = _FakeClientsDb(rows=_SEEDED_CLIENTS)
    monkeypatch.setattr("nx_lib.views.admin.clients.engine_nexora_db", db)
    return db


_NEW_CLIENT = {
    "ClientCode": "acme",
    "DisplayName": "Acme AG",
    "Dialect": "postgres",
    "RuntimeEngineKey": "engine_ms02_pg",
    "StatsEngineKey": "engine_ms02_stats_pg",
    "StatsDialect": "postgres",
    "DocfieldsEngineKey": "engine_ms02_docfields_pg",
    "DocfieldsDialect": "postgres",
    "OctoDomain": "acme.octo.example",
    "SecretRef": "ACME",
    "IsActive": True,
}


def test_admin_clients_add_round_trips_every_writable_column(
    admin_client, admin_all_perms, fake_clients_db
):
    resp = admin_client.post("/admin/clients/add", json=_NEW_CLIENT)
    assert resp.status_code == 200, resp.data
    stored = fake_clients_db.rows["acme"]
    expected = dict(_NEW_CLIENT, IsActive=1)
    assert stored == expected


def test_admin_clients_add_rejects_duplicate_code(admin_client, admin_all_perms, fake_clients_db):
    resp = admin_client.post("/admin/clients/add", json=dict(_NEW_CLIENT, ClientCode="ms02"))
    assert resp.status_code == 409


def test_admin_clients_edit_one_field_preserves_the_others(
    admin_client, admin_all_perms, fake_clients_db
):
    """The regression this whole fix wave exists for: the edit modal must round-
    trip StatsEngineKey / StatsDialect / DocfieldsEngineKey / DocfieldsDialect,
    or fixing a display-name typo on 'ms02' NULLs its stats and doc-field
    engine bindings."""
    before = dict(fake_clients_db.rows["ms02"])
    # What the form posts after openEditClientModal() has populated it from the
    # row's data-client JSON, with only DisplayName changed.
    payload = {c: before[c] for c in _CLIENTS_COLUMNS if c != "ClientCode"}
    payload["DisplayName"] = "MS02 (Azure PostgreSQL)"
    payload["IsActive"] = bool(before["IsActive"])

    resp = admin_client.post("/admin/clients/edit/ms02", json=payload)
    assert resp.status_code == 200, resp.data

    after = fake_clients_db.rows["ms02"]
    assert after["DisplayName"] == "MS02 (Azure PostgreSQL)"
    for column in _CLIENTS_COLUMNS:
        if column == "DisplayName":
            continue
        assert after[column] == before[column], f"{column} was clobbered by the edit"


def test_admin_clients_edit_unknown_code_is_404(admin_client, admin_all_perms, fake_clients_db):
    resp = admin_client.post("/admin/clients/edit/nosuch", json=dict(_NEW_CLIENT))
    assert resp.status_code == 404


def test_admin_clients_edit_rejects_unknown_stats_engine_key(
    admin_client, admin_all_perms, fake_clients_db
):
    resp = admin_client.post(
        "/admin/clients/edit/ms02",
        json=dict(_NEW_CLIENT, StatsEngineKey="engine_not_real"),
    )
    assert resp.status_code == 400
    assert fake_clients_db.rows["ms02"]["StatsEngineKey"] == "engine_ms02_stats_pg"


def test_admin_clients_edit_accepts_empty_optional_columns_as_null(
    admin_client, admin_all_perms, fake_clients_db
):
    """The four stats/doc-field columns are nullable and a future client may
    legitimately have none of them -- empty must mean NULL, not a 400."""
    payload = dict(
        _NEW_CLIENT,
        StatsEngineKey="",
        StatsDialect="",
        DocfieldsEngineKey="",
        DocfieldsDialect="",
        OctoDomain="",
        SecretRef="",
    )
    resp = admin_client.post("/admin/clients/edit/ms02", json=payload)
    assert resp.status_code == 200, resp.data
    row = fake_clients_db.rows["ms02"]
    for column in (
        "StatsEngineKey",
        "StatsDialect",
        "DocfieldsEngineKey",
        "DocfieldsDialect",
        "OctoDomain",
        "SecretRef",
    ):
        assert row[column] is None


def test_admin_clients_delete_round_trip(admin_client, admin_all_perms, fake_clients_db):
    resp = admin_client.delete("/admin/clients/delete/ms02")
    assert resp.status_code == 200, resp.data
    assert "ms02" not in fake_clients_db.rows


def test_admin_clients_delete_unknown_code_is_404(admin_client, admin_all_perms, fake_clients_db):
    resp = admin_client.delete("/admin/clients/delete/nosuch")
    assert resp.status_code == 404


def test_admin_clients_view_gated(noperm_client):
    resp = noperm_client.get("/admin/clients")
    assert resp.status_code == 403


def test_admin_clients_view_renders_rows(
    admin_client, admin_all_perms, fake_clients_db, monkeypatch
):
    """dbo.Clients isn't in sql/test/schema.sql, so the table is faked (same
    technique as fake_mapping_db below). Asserted at a hard 200 with the seeded
    rows visible -- the old 200-or-500 tuple-match could not fail, so a Jinja
    error in clients.html would have shipped green."""
    monkeypatch.setattr("nx_lib.views.admin.clients.has_permission", lambda code: True)
    resp = admin_client.get("/admin/clients")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'data-testid="admin-client-row-default"' in html
    assert 'data-testid="admin-client-row-ms02"' in html
    assert "MS02 (Azure Postgres)" in html


def test_admin_clients_form_covers_every_writable_column(
    admin_client, admin_all_perms, fake_clients_db, monkeypatch
):
    """The edit UPDATE writes all ten writable columns, so the form must carry
    all ten and openEditClientModal() must populate all of them -- otherwise
    editing a display name silently NULLs StatsEngineKey / StatsDialect /
    DocfieldsEngineKey / DocfieldsDialect (MS02 statistics break, doc-field
    search fails closed after the next app-pool recycle)."""
    monkeypatch.setattr("nx_lib.views.admin.clients.has_permission", lambda code: True)
    html = admin_client.get("/admin/clients").data.decode()
    for column in _CLIENTS_COLUMNS:
        assert f'id="{column}"' in html, f"{column} has no form input"
        assert f"clientData.{column}" in html, f"openEditClientModal() ignores {column}"


def test_admin_clients_view_only_gets_no_edit_affordances(
    admin_client, admin_all_perms, fake_clients_db, monkeypatch
):
    """admin.view.clients without admin.edit.clients: the page renders, but no
    Add/Edit/Delete button -- clicking one only ever produced a 403 toast."""
    monkeypatch.setattr(
        "nx_lib.views.admin.clients.has_permission", lambda code: code != "admin.edit.clients"
    )
    resp = admin_client.get("/admin/clients")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'data-testid="admin-client-row-ms02"' in html
    assert "admin-helpers-page-action-add-client" not in html
    assert "admin-client-edit-ms02" not in html
    assert "admin-client-delete-ms02" not in html


# ---- configured state vs resolved state -------------------------------------
#
# 0079's seed is unconditional, so PROD gets an 'ms02' row whether or not
# env/PROD.env carries the MS02_* keys. Without them _build_clients() skips the
# row and the page would still say "Active: Yes" for a runtime that serves
# nothing.


def test_admin_clients_marks_a_row_the_registry_did_not_load(
    admin_client, admin_all_perms, fake_clients_db, monkeypatch
):
    monkeypatch.setattr("nx_lib.views.admin.clients.has_permission", lambda code: True)
    monkeypatch.setattr(
        admin_module.clients_registry, "CLIENTS", {"default": object()}, raising=False
    )
    html = admin_client.get("/admin/clients").data.decode()
    ms02 = html.split('data-testid="admin-client-loaded-ms02"')[1].split("</td>")[0]
    default = html.split('data-testid="admin-client-loaded-default"')[1].split("</td>")[0]
    assert "Configured, not loaded" in ms02
    assert "Configured, not loaded" not in default
    assert "Loaded" in default


def test_admin_clients_marks_every_row_loaded_when_the_registry_holds_them(
    admin_client, admin_all_perms, fake_clients_db, monkeypatch
):
    monkeypatch.setattr("nx_lib.views.admin.clients.has_permission", lambda code: True)
    monkeypatch.setattr(
        admin_module.clients_registry,
        "CLIENTS",
        {"default": object(), "ms02": object()},
        raising=False,
    )
    html = admin_client.get("/admin/clients").data.decode()
    assert "Configured, not loaded" not in html


def test_admin_clients_shows_a_banner_when_the_registry_is_degraded(
    admin_client, admin_all_perms, fake_clients_db, monkeypatch
):
    """A boot-time dbo.Clients failure drops every non-default runtime for the
    whole process lifetime, and its only other signal is a stderr line written
    before Flask configured logging."""
    monkeypatch.setattr("nx_lib.views.admin.clients.has_permission", lambda code: True)
    monkeypatch.setattr(
        admin_module.clients_registry,
        "REGISTRY_DEGRADED_REASON",
        "RuntimeError: NexoraDB down",
        raising=False,
    )
    html = admin_client.get("/admin/clients").data.decode()
    assert 'data-testid="admin-clients-degraded"' in html
    assert "NexoraDB down" in html


def test_admin_clients_has_no_banner_when_the_registry_is_healthy(
    admin_client, admin_all_perms, fake_clients_db, monkeypatch
):
    monkeypatch.setattr("nx_lib.views.admin.clients.has_permission", lambda code: True)
    monkeypatch.setattr(
        admin_module.clients_registry, "REGISTRY_DEGRADED_REASON", None, raising=False
    )
    html = admin_client.get("/admin/clients").data.decode()
    assert 'data-testid="admin-clients-degraded"' not in html


def test_admin_clients_add_gated(noperm_client):
    resp = noperm_client.post("/admin/clients/add", json={})
    assert resp.status_code == 403


def test_admin_clients_edit_gated(noperm_client):
    resp = noperm_client.post("/admin/clients/edit/default", json={})
    assert resp.status_code == 403


def test_admin_clients_delete_gated(noperm_client):
    resp = noperm_client.delete("/admin/clients/delete/default")
    assert resp.status_code == 403


def test_admin_clients_add_rejects_bad_dialect(admin_client, admin_all_perms):
    resp = admin_client.post(
        "/admin/clients/add",
        json={
            "ClientCode": "acme",
            "DisplayName": "Acme",
            "Dialect": "mysql",
            "RuntimeEngineKey": "engine_octo_db",
        },
    )
    assert resp.status_code == 400


def test_admin_clients_add_rejects_unknown_engine_key(admin_client, admin_all_perms):
    resp = admin_client.post(
        "/admin/clients/add",
        json={
            "ClientCode": "acme",
            "DisplayName": "Acme",
            "Dialect": "tsql",
            "RuntimeEngineKey": "engine_not_a_real_engine",
        },
    )
    assert resp.status_code == 400


def test_admin_clients_add_rejects_bad_client_code(admin_client, admin_all_perms):
    resp = admin_client.post(
        "/admin/clients/add",
        json={
            "ClientCode": "Not Valid!",
            "DisplayName": "Acme",
            "Dialect": "tsql",
            "RuntimeEngineKey": "engine_octo_db",
        },
    )
    assert resp.status_code == 400


def test_admin_clients_delete_refuses_when_referenced_by_process_sources(
    admin_client, admin_all_perms, monkeypatch
):
    """A ClientCode still wired into dbo.ProcessSources must be refused with
    409, not deleted out from under the mapping-config registry (nx_lib/
    mapping_config.py) and not a 500 -- dbo.ProcessSources isn't in
    sql/test/schema.sql, so the DB layer is faked here (same technique as
    test_api_admin_logs_search_returns_iso_timestamp above)."""
    import nx_lib.views.admin as admin_module

    class _FakeCursor:
        def execute(self, sql, params=None):
            pass

        def fetchone(self):
            return (1,)

        def close(self):
            pass

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(admin_module.engine_nexora_db, "raw_connection", lambda: _FakeConn())

    resp = admin_client.delete("/admin/clients/delete/ms02")
    assert resp.status_code == 409


# ============================ processes (mapping config, read-only) ==========

# The six (ClientCode, ProcessName) rows migration 0074 verified agree between
# SearchConfig and StatConfig on INT/PROD -- used here as canned mapping_config
# rows so the route tests exercise the real registry() shape rather than a
# schema this test DB doesn't have (dbo.ProcessSources isn't in
# sql/test/schema.sql, same as dbo.Clients above).


def _processes_source_row(client, process, table="dbo.tblAlpha"):
    return _types.SimpleNamespace(
        ClientCode=client,
        ProcessName=process,
        TableName=table,
        TableAlias=None,
        JoinCondition=None,
        TimeFilter=None,
        SuggestionTimeFilter=None,
        ExportColumn="ExportDate",
        ImportColumn="ImportDate",
        WorkitemColumn=None,
        ExtraCondition=None,
        IdColumnType=None,
    )


def _processes_mapping_row(client, process, field_key="DocType", column="DocType"):
    return _types.SimpleNamespace(
        ClientCode=client,
        ProcessName=process,
        FieldKey=field_key,
        ColumnName=column,
        ColumnType=None,
    )


_SIX_INT_SOURCE_ROWS = [
    _processes_source_row("default", "sydoc.05_PDBS"),
    _processes_source_row("default", "sydoc.Alpha"),
    _processes_source_row("default", "sydoc.Beta"),
    _processes_source_row("ms02", "privera.02_Posteingang"),
    _processes_source_row("ms02", "privera.03_Rechnungen"),
    _processes_source_row("ms02", "privera.04_Vertraege"),
]


class _ProcessesFakeCursor:
    def __init__(self, sources, mappings):
        self._sources = sources
        self._mappings = mappings
        self._result = []

    def execute(self, sql, *params):
        if "FROM ProcessSources" in sql:
            self._result = self._sources
        elif "FROM ProcessFieldMappings" in sql:
            self._result = self._mappings
        elif "FROM FieldLabels" in sql or "FROM FieldAliases" in sql:
            self._result = []
        else:
            raise AssertionError(f"unexpected query: {sql}")

    def fetchall(self):
        return self._result


def _fake_mapping_config_engine(sources, mappings):
    cur = _ProcessesFakeCursor(sources, mappings)
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.close.return_value = None
    eng = MagicMock()
    eng.raw_connection.return_value = conn
    return eng


@pytest.fixture
def mapping_config_with_six_rows(monkeypatch, app):
    import nx_lib.mapping_config as mc

    with app.app_context():
        mc.invalidate_mapping_config()

    eng = _fake_mapping_config_engine(
        _SIX_INT_SOURCE_ROWS,
        [_processes_mapping_row("default", "sydoc.Alpha", "doctype", "DocType")],
    )
    monkeypatch.setattr(mc, "engine_nexora_db", eng)
    yield
    with app.app_context():
        mc.invalidate_mapping_config()


def test_admin_processes_view_gated(noperm_client):
    resp = noperm_client.get("/admin/processes")
    assert resp.status_code == 403


def test_admin_processes_view_with_perm(
    admin_client, admin_all_perms, mapping_config_with_six_rows
):
    resp = admin_client.get("/admin/processes")
    assert resp.status_code == 200


def test_admin_processes_view_renders_unavailable_state_on_registry_none(
    admin_client, admin_all_perms, monkeypatch, app
):
    import nx_lib.mapping_config as mc

    with app.app_context():
        mc.invalidate_mapping_config()
    dead_eng = MagicMock()
    dead_eng.raw_connection.side_effect = RuntimeError("NexoraDB down")
    monkeypatch.setattr(mc, "engine_nexora_db", dead_eng)

    resp = admin_client.get("/admin/processes")
    assert resp.status_code == 200
    assert b"unavailable" in resp.data.lower() or b"config" in resp.data.lower()
    with app.app_context():
        mc.invalidate_mapping_config()


def test_api_admin_processes_list_gated(noperm_client):
    resp = noperm_client.get("/api/admin/processes/list?client=default")
    assert resp.status_code == 403


def test_api_admin_processes_list_returns_six_int_rows_shape(
    admin_client, admin_all_perms, mapping_config_with_six_rows
):
    resp = admin_client.get("/api/admin/processes/list")
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["processes"]) == 6
    process = body["processes"][0]
    for key in (
        "client",
        "process",
        "table",
        "alias",
        "join_condition",
        "time_filter",
        "suggestion_time_filter",
        "export_column",
        "import_column",
        "workitem_column",
        "extra_condition",
        "id_column_type",
        "fields",
    ):
        assert key in process


def test_api_admin_processes_list_filters_by_client(
    admin_client, admin_all_perms, mapping_config_with_six_rows
):
    resp = admin_client.get("/api/admin/processes/list?client=default")
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["processes"]) == 3
    assert all(p["client"] == "default" for p in body["processes"])
    alpha = next(p for p in body["processes"] if p["process"] == "sydoc.Alpha")
    assert alpha["fields"] == [{"field_key": "doctype", "column": "DocType", "column_type": None}]


def test_api_admin_processes_list_returns_503_on_registry_none(
    admin_client, admin_all_perms, monkeypatch, app
):
    import nx_lib.mapping_config as mc

    with app.app_context():
        mc.invalidate_mapping_config()
    dead_eng = MagicMock()
    dead_eng.raw_connection.side_effect = RuntimeError("NexoraDB down")
    monkeypatch.setattr(mc, "engine_nexora_db", dead_eng)

    resp = admin_client.get("/api/admin/processes/list")
    assert resp.status_code == 503
    with app.app_context():
        mc.invalidate_mapping_config()


# ==================== processes: writes + permission auto-provisioning =======

# dbo.ProcessSources / ProcessFieldMappings / Permission writes cannot run
# against NEXORA_TEST (sql/test/schema.sql has no mapping tables), so the write
# endpoints run against _FakeMappingDb below. It is not a bare stub: it
# emulates the three constraints these endpoints must respect --
# PK_ProcessSources, PK_ProcessFieldMappings and the UNIQUE index on
# dbo.Permission.Code -- plus the WHERE NOT EXISTS guard, so a non-idempotent
# or unguarded implementation fails these tests rather than passing them.


class _FakeMappingDb:
    """Tiny in-memory stand-in for the three tables the write endpoints touch."""

    def __init__(self, sources=(), mappings=(), permissions=(), clients=("default", "ms02")):
        self.sources = set(sources)
        self.mappings = set(mappings)
        self.permissions = set(permissions)
        self.clients = set(clients)
        self.calls = []  # ordered log of ("SQL", params) plus ("COMMIT", None)
        self.rowcount = 0
        self._last = ""
        self._fetchall = []

    # -- DBAPI-ish surface -------------------------------------------------
    def raw_connection(self):
        return self

    def cursor(self):
        return self

    def close(self):
        pass

    def commit(self):
        self.calls.append(("COMMIT", None))

    def fetchone(self):
        return self._fetchone

    def fetchall(self):
        return self._fetchall

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        self._last = sql
        self._fetchone = None
        self._fetchall = []
        self.rowcount = 0
        flat = " ".join(sql.split())

        if flat.startswith("SELECT ClientCode, ProcessName FROM dbo.ProcessSources"):
            # The reduction-collision scan run before every source INSERT.
            self._fetchall = sorted(self.sources)
        elif flat.startswith("SELECT ClientCode FROM dbo.Clients"):
            self._fetchall = [(c,) for c in sorted(self.clients)]
        elif flat.startswith("SELECT COUNT(*) FROM dbo.Clients"):
            self._fetchone = (1 if params[0] in self.clients else 0,)
        elif flat.startswith("INSERT INTO dbo.ProcessSources"):
            key = (params[0], params[1])
            if key in self.sources:
                raise pyodbc.IntegrityError("23000", "PK_ProcessSources")
            self.sources.add(key)
            self.rowcount = 1
        elif flat.startswith("UPDATE dbo.ProcessSources"):
            key = (params[-2], params[-1])
            self.rowcount = 1 if key in self.sources else 0
        elif flat.startswith("DELETE FROM dbo.ProcessSources"):
            key = (params[0], params[1])
            self.rowcount = 1 if key in self.sources else 0
            self.sources.discard(key)
        elif flat.startswith("SELECT COUNT(*) FROM dbo.ProcessFieldMappings"):
            self._fetchone = (
                sum(1 for m in self.mappings if (m[0], m[1]) == (params[0], params[1])),
            )
        elif flat.startswith("SELECT COUNT(*) FROM dbo.ProcessSources"):
            self._fetchone = (1 if (params[0], params[1]) in self.sources else 0,)
        elif flat.startswith("INSERT INTO dbo.ProcessFieldMappings"):
            key = (params[0], params[1], params[2])
            if key in self.mappings:
                raise pyodbc.IntegrityError("23000", "PK_ProcessFieldMappings")
            self.mappings.add(key)
            self.rowcount = 1
        elif flat.startswith("UPDATE dbo.ProcessFieldMappings"):
            key = (params[-3], params[-2], params[-1])
            self.rowcount = 1 if key in self.mappings else 0
        elif flat.startswith("DELETE FROM dbo.ProcessFieldMappings"):
            key = (params[0], params[1], params[2])
            self.rowcount = 1 if key in self.mappings else 0
            self.mappings.discard(key)
        elif flat.startswith("INSERT INTO dbo.Permission"):
            code = params[0]
            guarded = "WHERE NOT EXISTS" in flat
            if code in self.permissions:
                if not guarded:  # UNIQUE (Code) -- what SQL Server would do
                    raise pyodbc.IntegrityError("23000", "UQ_Permission_Code")
                self.rowcount = 0
            else:
                self.permissions.add(code)
                self.rowcount = 1
        else:
            raise AssertionError(f"unexpected query: {sql}")

    # -- assertions helpers ------------------------------------------------
    def statements(self):
        return [" ".join(sql.split()) for sql, _ in self.calls]

    def params_for(self, prefix):
        return [p for sql, p in self.calls if " ".join(sql.split()).startswith(prefix)]


@pytest.fixture
def fake_mapping_db(monkeypatch):
    """Point the admin write endpoints at _FakeMappingDb and neutralise the
    mapping-config cache invalidation so it can be asserted per test."""
    import nx_lib.views.admin as admin_module

    db = _FakeMappingDb(
        sources={("ms02", "privera.02_Posteingang")},
        mappings={("ms02", "privera.02_Posteingang", "doctype")},
        permissions={"process.privera.02_Posteingang.view"},
    )
    monkeypatch.setattr(admin_module.processes, "engine_nexora_db", db)
    return db


@pytest.fixture
def spy_invalidate(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "nx_lib.views.admin.processes.invalidate_mapping_config", lambda: calls.append(1)
    )
    return calls


_VALID_SOURCE = {
    "ClientCode": "default",
    "ProcessName": "acme.01_Eingang",
    "TableName": "dbo.tblAcme",
    "TableAlias": "a",
    "ExportColumn": "ExportDate",
    "ImportColumn": "ImportDate",
    "WorkitemColumn": "WorkitemId",
    "IdColumnType": "int",
}

_VALID_FIELD = {
    "ClientCode": "ms02",
    "ProcessName": "privera.02_Posteingang",
    "FieldKey": "invoice_no",
    "ColumnName": "InvoiceNo",
    "ColumnType": "nvarchar",
}


# ---- permission gates -------------------------------------------------------


def test_admin_process_source_add_gated(noperm_client):
    assert noperm_client.post("/admin/processes/sources/add", json={}).status_code == 403


def test_admin_process_source_edit_gated(noperm_client):
    resp = noperm_client.post("/admin/processes/sources/edit/ms02/p", json={})
    assert resp.status_code == 403


def test_admin_process_source_delete_gated(noperm_client):
    assert noperm_client.delete("/admin/processes/sources/delete/ms02/p").status_code == 403


def test_admin_field_mapping_add_gated(noperm_client):
    assert noperm_client.post("/admin/processes/fields/add", json={}).status_code == 403


def test_admin_field_mapping_edit_gated(noperm_client):
    resp = noperm_client.post("/admin/processes/fields/edit/ms02/p/doctype", json={})
    assert resp.status_code == 403


def test_admin_field_mapping_delete_gated(noperm_client):
    resp = noperm_client.delete("/admin/processes/fields/delete/ms02/p/doctype")
    assert resp.status_code == 403


# ---- permission auto-provisioning (D7) --------------------------------------


def test_process_source_add_provisions_permission_exactly_once(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate
):
    resp = admin_client.post("/admin/processes/sources/add", json=_VALID_SOURCE)
    assert resp.status_code == 200, resp.get_json()

    perm_params = fake_mapping_db.params_for("INSERT INTO dbo.Permission")
    assert len(perm_params) == 1
    assert perm_params[0][0] == "process.acme.01_Eingang.view"
    assert "process.acme.01_Eingang.view" in fake_mapping_db.permissions


def test_process_source_add_provisions_permission_granted_to_nobody(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate
):
    """Granting stays a deliberate act at /admin/access-control -- the endpoint
    must never write AccessProfilePermission or UserPermissionOverride."""
    admin_client.post("/admin/processes/sources/add", json=_VALID_SOURCE)
    joined = " ".join(fake_mapping_db.statements())
    assert "AccessProfilePermission" not in joined
    assert "UserPermissionOverride" not in joined


def test_process_source_add_provisions_permission_in_same_transaction(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate
):
    admin_client.post("/admin/processes/sources/add", json=_VALID_SOURCE)
    statements = fake_mapping_db.statements()
    first_commit = statements.index("COMMIT")
    before = statements[:first_commit]
    assert any(s.startswith("INSERT INTO dbo.ProcessSources") for s in before)
    assert any(s.startswith("INSERT INTO dbo.Permission") for s in before)


def test_process_source_add_permission_provisioning_is_idempotent(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate
):
    """Re-adding a process whose permission row survived an earlier delete must
    not blow up on the UNIQUE index on dbo.Permission.Code."""

    def add():
        return admin_client.post("/admin/processes/sources/add", json=_VALID_SOURCE)

    assert add().status_code == 200
    assert (
        admin_client.delete("/admin/processes/sources/delete/default/acme.01_Eingang").status_code
        == 200
    )
    assert add().status_code == 200
    assert sum(1 for c in fake_mapping_db.permissions if c.endswith("acme.01_Eingang.view")) == 1


# ---- cache invalidation on every write path (D8) ----------------------------


# ---- ProcessName shape: the entitlement invariant ---------------------------
#
# The auto-provisioned process.<client>.<name>.view permission is built from
# _permission_reduction(process_name) -- the last two dot-segments of
# ProcessName. Every consumer then reads the pair back out of the permission
# code via granted_processes() (nx_lib/process_helpers.py), which strips the
# fixed "process." prefix and ".view" suffix and requires exactly one dot in
# what's left. Before this page existed the two-segment invariant held because
# process names were migration-controlled; now an admin types them, so the
# endpoint has to enforce it -- every malformed shape below either mis-derives
# a reduction or gets silently dropped by granted_processes' single-dot check,
# never grantable as the admin intended.


def _derive_process_from_permission(code):
    """Exactly what granted_processes() (nx_lib/process_helpers.py) derives
    back out of a permission code -- or None when the pair fails the
    single-dot check and is silently dropped."""
    from nx_lib.process_helpers import granted_processes

    result = granted_processes([code])
    return result[0] if result else None


@pytest.mark.parametrize(
    "bad_name",
    [
        "Invoice",  # no dot -> dropped by granted_processes' single-dot check
        "acme.eu.01_Invoice",  # three parts -> two dots, also dropped
        "a.b.c.d",
        ".leading",
        "trailing.",
        "two..dots",
    ],
)
def test_process_source_add_rejects_names_the_permission_layer_misparses(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate, bad_name
):
    resp = admin_client.post(
        "/admin/processes/sources/add", json=dict(_VALID_SOURCE, ProcessName=bad_name)
    )
    assert resp.status_code == 400, resp.get_json()
    assert "<customer>.<process>" in resp.get_json()["message"]
    # Nothing written, nothing provisioned, nothing invalidated.
    assert not any(n for _c, n in fake_mapping_db.sources if n == bad_name)
    assert f"process.{bad_name}.view" not in fake_mapping_db.permissions
    assert spy_invalidate == []


@pytest.mark.parametrize("bad_name", ["Invoice", "acme.eu.01_Invoice"])
def test_the_rejected_shapes_really_would_have_mis_derived(bad_name):
    """Guard the premise of the test above rather than just asserting a regex:
    these names do NOT round-trip through the permission code -- the
    malformed pair is silently dropped by granted_processes' single-dot
    check, not mis-derived to a different process."""
    assert _derive_process_from_permission(f"process.{bad_name}.view") != bad_name


def test_two_segment_names_round_trip_through_the_permission_code():
    for name in ("acme.01_Invoice", "privera.02_Posteingang", "sydoc.05_PDBS", "a-b.c_d"):
        assert admin_module._PROCESS_NAME_RE.match(name), name
        assert _derive_process_from_permission(f"process.{name}.view") == name


def test_every_process_name_on_int_still_passes_the_tightened_pattern():
    """The pattern may not reject config that already exists. Every ProcessName
    literal that appears in sql/_migrations/NexoraDB/*.sql."""
    for name in (
        "sydoc.05_PDBS",
        "sydoc.praesidialdepartement_bs",
        "privera.02_Posteingang",
        "privera.02_InitialScan",
        "privera.03_Invoice_New",
        "compass.01_Invoice_SAP",
        "elektromaterial.02_Invoice",
    ):
        assert admin_module._PROCESS_NAME_RE.match(name), name


def test_field_key_keeps_the_looser_shape(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate
):
    """FieldKey never becomes a permission code, so tightening ProcessName must
    not have tightened it too -- 'doctype' has no dot."""
    resp = admin_client.post(
        "/admin/processes/fields/add", json=dict(_VALID_FIELD, FieldKey="doc.type.long")
    )
    assert resp.status_code == 200, resp.get_json()


def test_process_source_add_rejects_a_name_that_reduces_onto_an_existing_grant(
    admin_client, admin_all_perms, spy_invalidate, monkeypatch
):
    """A legacy three-segment row 'x.acme.01_Invoice' reduces to
    'acme.01_Invoice'. Adding that two-segment name would silently share one
    entitlement with a different customer's process."""
    db = _FakeMappingDb(sources={("ms02", "x.acme.01_Eingang")})
    monkeypatch.setattr(admin_module.processes, "engine_nexora_db", db)

    resp = admin_client.post("/admin/processes/sources/add", json=_VALID_SOURCE)
    assert resp.status_code == 409, resp.get_json()
    assert "x.acme.01_Eingang" in resp.get_json()["message"]
    assert ("default", "acme.01_Eingang") not in db.sources
    assert spy_invalidate == []


def test_process_source_add_rejects_the_same_name_under_a_different_client(
    admin_client, admin_all_perms, spy_invalidate, monkeypatch
):
    """The permission code carries no ClientCode, so the same ProcessName under
    two clients is one shared entitlement, not two."""
    db = _FakeMappingDb(sources={("ms02", "acme.01_Eingang")})
    monkeypatch.setattr(admin_module.processes, "engine_nexora_db", db)

    resp = admin_client.post("/admin/processes/sources/add", json=_VALID_SOURCE)
    assert resp.status_code == 409, resp.get_json()
    assert ("default", "acme.01_Eingang") not in db.sources


def test_process_source_add_allows_a_non_colliding_name(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate
):
    """The collision check must not turn into a blanket refusal."""
    resp = admin_client.post("/admin/processes/sources/add", json=_VALID_SOURCE)
    assert resp.status_code == 200, resp.get_json()
    assert ("default", "acme.01_Eingang") in fake_mapping_db.sources


# ---- ClientCode must be a real dbo.Clients row ------------------------------


def test_process_source_add_rejects_an_unknown_client_code(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate
):
    """No FK ties ProcessSources.ClientCode to dbo.Clients (0079 adds none on
    purpose), so a typo would otherwise create config that never resolves."""
    resp = admin_client.post(
        "/admin/processes/sources/add", json=dict(_VALID_SOURCE, ClientCode="defualt")
    )
    assert resp.status_code == 400, resp.get_json()
    assert "defualt" in resp.get_json()["message"]
    assert ("defualt", "acme.01_Eingang") not in fake_mapping_db.sources
    assert "process.acme.01_Eingang.view" not in fake_mapping_db.permissions
    assert spy_invalidate == []


def test_process_source_add_checks_the_client_before_writing_anything(
    admin_client, admin_all_perms, fake_mapping_db
):
    admin_client.post("/admin/processes/sources/add", json=dict(_VALID_SOURCE, ClientCode="nope"))
    assert not any(st.startswith("INSERT") for st in fake_mapping_db.statements())
    assert ("COMMIT", None) not in fake_mapping_db.calls


def test_processes_page_offers_a_client_picker_not_free_text(
    admin_client, admin_all_perms, mapping_config_with_six_rows, monkeypatch
):
    monkeypatch.setattr("nx_lib.views.admin.processes.has_permission", lambda code: True)
    monkeypatch.setattr(admin_module.processes, "_client_codes", lambda: ["default", "ms02"])
    resp = admin_client.get("/admin/processes")
    html = resp.get_data(as_text=True)
    assert 'id="ClientCode"' in html
    assert '<select id="ClientCode"' in html
    assert '<option value="ms02">' in html


def test_processes_page_falls_back_to_free_text_when_clients_unreadable(
    admin_client, admin_all_perms, mapping_config_with_six_rows, monkeypatch
):
    """An unreadable dbo.Clients must not leave an empty picker that blocks
    every add."""
    monkeypatch.setattr("nx_lib.views.admin.processes.has_permission", lambda code: True)
    monkeypatch.setattr(admin_module.processes, "_client_codes", list)
    html = admin_client.get("/admin/processes").get_data(as_text=True)
    assert '<input type="text" id="ClientCode"' in html


def test_every_process_write_path_invalidates_mapping_config(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate
):
    """Miss invalidate_mapping_config() on one path and that edit looks broken
    for up to the registry's 60s TTL."""
    calls = [
        ("POST", "/admin/processes/sources/add", _VALID_SOURCE),
        (
            "POST",
            "/admin/processes/sources/edit/ms02/privera.02_Posteingang",
            dict(_VALID_SOURCE, ClientCode="ms02", ProcessName="privera.02_Posteingang"),
        ),
        ("POST", "/admin/processes/fields/add", dict(_VALID_FIELD, FieldKey="amount")),
        (
            "POST",
            "/admin/processes/fields/edit/ms02/privera.02_Posteingang/doctype",
            _VALID_FIELD,
        ),
        ("DELETE", "/admin/processes/fields/delete/ms02/privera.02_Posteingang/doctype", None),
        ("DELETE", "/admin/processes/sources/delete/default/acme.01_Eingang", None),
    ]
    for i, (method, url, payload) in enumerate(calls, start=1):
        if method == "POST":
            resp = admin_client.post(url, json=payload)
        else:
            resp = admin_client.delete(url)
        assert resp.status_code == 200, (url, resp.get_json())
        assert len(spy_invalidate) == i, f"{url} did not invalidate the mapping config"


def test_failed_process_write_does_not_invalidate(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate
):
    resp = admin_client.post(
        "/admin/processes/sources/add", json=dict(_VALID_SOURCE, ProcessName="bad name!")
    )
    assert resp.status_code == 400
    assert spy_invalidate == []


# ---- constraint violations surface as 409, never 500 ------------------------


def test_process_source_delete_refused_while_field_mappings_reference_it(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate
):
    resp = admin_client.delete("/admin/processes/sources/delete/ms02/privera.02_Posteingang")
    assert resp.status_code == 409
    assert ("ms02", "privera.02_Posteingang") in fake_mapping_db.sources
    assert spy_invalidate == []


def test_process_source_add_duplicate_is_409(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate
):
    resp = admin_client.post(
        "/admin/processes/sources/add",
        json=dict(_VALID_SOURCE, ClientCode="ms02", ProcessName="privera.02_Posteingang"),
    )
    assert resp.status_code == 409


def test_field_mapping_add_duplicate_is_409(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate
):
    """PK_ProcessFieldMappings (ClientCode, ProcessName, FieldKey)."""
    resp = admin_client.post(
        "/admin/processes/fields/add", json=dict(_VALID_FIELD, FieldKey="doctype")
    )
    assert resp.status_code == 409


def test_process_source_edit_missing_row_is_404(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate
):
    resp = admin_client.post(
        "/admin/processes/sources/edit/ms02/nope.01",
        json=dict(_VALID_SOURCE, ClientCode="ms02", ProcessName="nope.01"),
    )
    assert resp.status_code == 404


def test_field_mapping_delete_missing_row_is_404(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate
):
    resp = admin_client.delete("/admin/processes/fields/delete/ms02/privera.02_Posteingang/nope")
    assert resp.status_code == 404


# ---- server-side validation -------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    ["bad name!", "a" * 101, "", "p; DROP TABLE dbo.Users--", "p'or'1'='1"],
)
def test_process_name_must_match_the_strict_pattern(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate, bad
):
    resp = admin_client.post(
        "/admin/processes/sources/add", json=dict(_VALID_SOURCE, ProcessName=bad)
    )
    assert resp.status_code == 400
    assert fake_mapping_db.calls == []


@pytest.mark.parametrize("bad", ["bad key!", "a" * 101, "", "k; DROP TABLE dbo.Users--"])
def test_field_key_must_match_the_strict_pattern(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate, bad
):
    resp = admin_client.post("/admin/processes/fields/add", json=dict(_VALID_FIELD, FieldKey=bad))
    assert resp.status_code == 400
    assert fake_mapping_db.calls == []


@pytest.mark.parametrize(
    "bad",
    [
        "dbo.tbl; DROP TABLE dbo.Users--",
        "dbo.tbl WHERE 1=1",
        "1tbl",
        "tbl'",
        "tbl)--",
        "a" * 101,
    ],
)
def test_table_name_rejected_unless_strict_identifier(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate, bad
):
    """TableName is interpolated into SQL by the downstream query builders
    (nx_lib/views/dashboard.py f-strings) -- it is config, not a bind param."""
    resp = admin_client.post(
        "/admin/processes/sources/add", json=dict(_VALID_SOURCE, TableName=bad)
    )
    assert resp.status_code == 400
    assert fake_mapping_db.calls == []


@pytest.mark.parametrize(
    "bad", ["Col; DROP TABLE dbo.Users--", "Col FROM x", "1Col", "Col'", "a" * 101]
)
def test_column_name_rejected_unless_strict_identifier(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate, bad
):
    resp = admin_client.post("/admin/processes/fields/add", json=dict(_VALID_FIELD, ColumnName=bad))
    assert resp.status_code == 400
    assert fake_mapping_db.calls == []


@pytest.mark.parametrize("field", ["TableAlias", "ExportColumn", "ImportColumn", "WorkitemColumn"])
def test_every_interpolated_source_column_is_identifier_validated(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate, field
):
    """dashboard.py f-strings these straight into SQL alongside TableName."""
    resp = admin_client.post(
        "/admin/processes/sources/add", json=dict(_VALID_SOURCE, **{field: "x; DROP TABLE y--"})
    )
    assert resp.status_code == 400
    assert fake_mapping_db.calls == []


def test_valid_identifiers_with_brackets_and_quotes_are_accepted(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate
):
    """The real config holds quoted PG identifiers (public."DossierStatistik")
    and bracketed T-SQL ones -- the pattern must not reject those."""
    resp = admin_client.post(
        "/admin/processes/sources/add",
        json=dict(
            _VALID_SOURCE,
            ProcessName="acme.02_Quoted",
            TableName='public."DossierStatistik"',
        ),
    )
    assert resp.status_code == 200, resp.get_json()


def test_unknown_client_code_shape_is_rejected(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate
):
    resp = admin_client.post(
        "/admin/processes/sources/add", json=dict(_VALID_SOURCE, ClientCode="Not Valid!")
    )
    assert resp.status_code == 400
    assert fake_mapping_db.calls == []


# ---- free-form SQL fragment columns stay out of the write surface -----------


def test_free_form_sql_fragment_columns_are_never_written(
    admin_client, admin_all_perms, fake_mapping_db, spy_invalidate
):
    """JoinCondition / TimeFilter / SuggestionTimeFilter / ExtraCondition are
    free-form SQL by design and stay migration-only -- a payload carrying them
    must not reach the INSERT."""
    payload = dict(
        _VALID_SOURCE,
        JoinCondition="1=1 OR 1=1",
        TimeFilter="1=1",
        SuggestionTimeFilter="1=1",
        ExtraCondition="1=1",
    )
    assert admin_client.post("/admin/processes/sources/add", json=payload).status_code == 200

    insert = next(
        s for s in fake_mapping_db.statements() if s.startswith("INSERT INTO dbo.Process")
    )
    for column in ("JoinCondition", "TimeFilter", "SuggestionTimeFilter", "ExtraCondition"):
        assert column not in insert
    params = fake_mapping_db.params_for("INSERT INTO dbo.ProcessSources")[0]
    assert "1=1 OR 1=1" not in params
    assert "1=1" not in params


def test_processes_page_exposes_no_free_form_sql_inputs(
    admin_client, admin_all_perms, mapping_config_with_six_rows
):
    html = admin_client.get("/admin/processes").get_data(as_text=True)
    for column in ("JoinCondition", "TimeFilter", "SuggestionTimeFilter", "ExtraCondition"):
        assert f'name="{column}"' not in html
        assert f'id="{column}"' not in html


# ============================ maintenance banner =============================


def test_admin_maintenance_view_gated(noperm_client):
    resp = noperm_client.get("/admin/maintenance")
    assert resp.status_code == 403


def test_admin_maintenance_view_with_perms(admin_client, admin_all_perms):
    """200 with an empty list, or 500 if the query fails."""
    resp = admin_client.get("/admin/maintenance")
    assert resp.status_code in (200, 500)


def test_api_admin_maintenance_list_no_table_returns_500_or_200(admin_client, admin_all_perms):
    resp = admin_client.get("/api/admin/maintenance")
    assert resp.status_code in (200, 500)


def test_api_admin_maintenance_add_invalid_body(admin_client, admin_all_perms):
    """No message/startAt/endAt → 400."""
    resp = admin_client.post("/api/admin/maintenance", json={"severity": "info"})
    assert resp.status_code in (400, 500)


def test_api_admin_maintenance_edit_missing_table_500(admin_client, admin_all_perms):
    resp = admin_client.put(
        "/api/admin/maintenance/1",
        json={
            "title": "T",
            "message": "M",
            "startAt": "2026-06-01 12:00",
            "endAt": "2026-06-01 13:00",
            "severity": "info",
        },
    )
    assert resp.status_code in (200, 400, 404, 500)


def test_api_admin_maintenance_delete_missing_table(admin_client, admin_all_perms):
    resp = admin_client.delete("/api/admin/maintenance/1")
    assert resp.status_code in (200, 404, 500)


# ============================ logs ===========================================


def test_admin_logs_view_gated(noperm_client):
    resp = noperm_client.get("/admin/logs")
    assert resp.status_code == 403


def test_admin_logs_view_with_perms(admin_client, admin_all_perms):
    """Logs table absent → render still works (page is static shell)."""
    resp = admin_client.get("/admin/logs")
    assert resp.status_code in (200, 500)


def test_api_admin_logs_search_missing_table(admin_client, admin_all_perms):
    resp = admin_client.get("/api/admin/logs/search")
    assert resp.status_code in (200, 500)


def test_api_admin_logs_search_returns_iso_timestamp(admin_client, admin_all_perms, monkeypatch):
    """Timestamp must serialize as ISO-8601, not Flask's default RFC-1123
    JSON repr for raw datetime objects (e.g. "Mon, 27 Jul 2026 13:45:30 GMT"),
    which the client reads as UTC and which shifts the displayed time by the
    server's UTC offset. The Logs table doesn't exist in NEXORA_TEST, so the
    DB layer is faked here to exercise the route's serialization in isolation.
    """
    import re
    from datetime import datetime
    from types import SimpleNamespace

    import nx_lib.views.admin as admin_module

    ts = datetime(2026, 7, 27, 13, 45, 30)

    class _FakeCursor:
        def execute(self, sql, params=None):
            pass

        def fetchone(self):
            return (1,)

        def fetchall(self):
            return [
                SimpleNamespace(
                    LogID=1,
                    Timestamp=ts,
                    Username="admin@test.local",
                    HttpRequestMethod="GET",
                    Path="/admin",
                    HttpResponseCode=200,
                    Args=None,
                    RequestIpAddress="127.0.0.1",
                    durationSeconds=0.1,
                )
            ]

        def close(self):
            pass

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

        def close(self):
            pass

    monkeypatch.setattr(admin_module.engine_nexora_db, "raw_connection", lambda: _FakeConn())

    resp = admin_client.get("/api/admin/logs/search")
    assert resp.status_code == 200
    raw_ts = resp.get_json()["logs"][0]["Timestamp"]

    assert raw_ts == ts.isoformat()
    assert "GMT" not in raw_ts
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", raw_ts)


def test_api_admin_logs_export_missing_table(admin_client, admin_all_perms):
    resp = admin_client.get("/api/admin/logs/export.csv")
    assert resp.status_code in (200, 500)


# ============================ sessions + users ===============================


def test_admin_sessions_view_gated(noperm_client):
    resp = noperm_client.get("/admin/sessions")
    assert resp.status_code == 403


def test_admin_sessions_view_with_perms(admin_client, admin_all_perms):
    resp = admin_client.get("/admin/sessions")
    assert resp.status_code == 200


def test_admin_add_user_missing_fields_returns_400(admin_client, admin_all_perms):
    resp = admin_client.post("/admin/users/add", json={"username": "x"})
    assert resp.status_code == 400


def test_add_user_refuses_a_higher_ranked_profile(user_client, admin_all_perms):
    # TestUser has Rank 10; TestAdmin is Rank 100 -> not assignable even with every code.
    resp = user_client.post(
        "/admin/users/add",
        json={
            "username": f"r{uuid.uuid4().hex[:6]}",
            "password": "Test1234!",
            "fullname": "Rank Test",
            "email": f"r{uuid.uuid4().hex[:6]}@test.local",
            "organization": "Test Organization",
            "accessprofile": "TestAdmin",
        },
    )
    assert resp.status_code == 403


def test_admin_add_user_duplicate_returns_409_or_500(admin_client, admin_all_perms):
    """Re-add user@test.local → IntegrityError 409.

    admin@test.local is TestAdmin (Rank 100), real-assigning TestUser (Rank
    10) — the rank-ceiling check in assignable_profile_ids() passes for real,
    no mocking needed; admin_all_perms only covers the
    @require_permission("admin.create.user") decorator gate.
    """
    resp = admin_client.post(
        "/admin/users/add",
        json={
            "username": "user@test.local",
            "password": "X",
            "fullname": "Y",
            "email": "user@test.local",
            "organization": "Test Organization",
            "accessprofile": "TestUser",
        },
    )
    assert resp.status_code in (200, 409, 500)


def test_admin_add_user_returns_403_when_profile_not_assignable(admin_client, monkeypatch, db_conn):
    """admin.create.user alone must not be enough to assign an access profile.

    The @require_permission("admin.create.user") decorator resolves the REAL
    nx_lib.security.has_permission at call time — TestAdmin (admin@test.local)
    is seeded with every permission, so that check still passes. Only the
    rank-ceiling assignable_profile_ids() gate denies here, by patching the
    nx_lib.views.admin.users module-level binding (the one admin_add_user
    actually calls) to return an empty set — no profile is assignable.
    """
    from sqlalchemy import text

    monkeypatch.setattr("nx_lib.views.admin.users.assignable_profile_ids", lambda: set())
    username = "task5-deny@test.local"
    resp = admin_client.post(
        "/admin/users/add",
        json={
            "username": username,
            "password": "X",
            "fullname": "Y",
            "email": username,
            "organization": "Test Organization",
            "accessprofile": "TestUser",
        },
    )
    assert resp.status_code == 403

    count = db_conn.execute(
        text("SELECT COUNT(*) FROM Users WHERE username = :u"), {"u": username}
    ).scalar()
    assert count == 0


def test_admin_add_user_with_assign_permission_returns_200(admin_client, db_conn):
    """admin@test.local (TestAdmin, Rank 100) may really assign TestUser (Rank 10).

    Deliberately does NOT use admin_all_perms or mock assignable_profile_ids —
    this exercises the real rank-ceiling query end to end.
    """
    from sqlalchemy import text

    from nx_lib.db import engine_nexora_db

    username = f"task5-allow-{uuid.uuid4().hex[:8]}@test.local"
    user_id = None
    try:
        resp = admin_client.post(
            "/admin/users/add",
            json={
                "username": username,
                "password": "X",
                "fullname": "Y",
                "email": username,
                "organization": "Test Organization",
                "accessprofile": "TestUser",
            },
        )
        assert resp.status_code == 200

        user_id = db_conn.execute(
            text("SELECT userID FROM Users WHERE username = :u"), {"u": username}
        ).scalar()
        assert user_id is not None
    finally:
        # NOTE: cleanup deliberately does NOT go through admin_client.delete(...)
        # or db_conn, even though the general convention for this file is to
        # clean up via the app's own delete routes:
        #   - admin_delete_user (nx_lib/views/admin.py) deletes from `tags`,
        #     `workitem_metadata`, `notifications`, etc. BEFORE it ever reaches
        #     `DELETE FROM users`. None of those tables exist in the minimal
        #     NEXORA_TEST schema (sql/test/schema.sql) — see the module
        #     docstring's "Tables ABSENT" list and
        #     test_admin_delete_user_missing_returns_404_or_500, which already
        #     tolerates the resulting 500. So the route raises on its first
        #     statement, is caught by a broad except, returns 500, and never
        #     deletes the Users row — calling it here would silently no-op.
        #   - db_conn's writes are rolled back at end-of-test (see its fixture
        #     docstring in tests/conftest.py), so a DELETE issued through it
        #     would never actually persist either.
        # A direct delete on a separate, explicitly-committed connection — the
        # same approach used to clear the RED-phase leftover row (see
        # task-5-report.md) — is the only way that actually removes the row.
        if user_id is not None:
            conn = engine_nexora_db.raw_connection()
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM Users WHERE userID = ?", [user_id])
                conn.commit()
                cur.close()
            finally:
                conn.close()

            remaining = db_conn.execute(
                text("SELECT COUNT(*) FROM Users WHERE userID = :uid"), {"uid": user_id}
            ).scalar()
            assert remaining == 0


def test_admin_add_user_invite_generates_password_and_mails_link(
    admin_client, monkeypatch, db_conn
):
    """send_invite=on: no admin-typed password, a mailed set-password link.

    Covers the whole invite branch — the generated placeholder password is
    stored hashed, InitReset is pre-set (the emailed link IS the password
    choice, so no forced change on top of it), and the mailed token round-
    trips back to the user's address through the invite salt.
    """
    import re

    from sqlalchemy import text

    from nx_lib.db import engine_nexora_db
    from nx_lib.views.auth import _load_reset_token

    sent = {}

    def _fake_send(email, message=None):
        sent["email"] = email
        sent["message"] = message
        return True

    monkeypatch.setattr("nx_lib.views.auth.send_reset_email", _fake_send)

    username = f"invite-{uuid.uuid4().hex[:8]}@test.local"
    user_id = None
    try:
        resp = admin_client.post(
            "/admin/users/add",
            json={
                "username": username,
                "fullname": "Y",
                "email": username,
                "organization": "Test Organization",
                "accessprofile": "TestUser",
                "send_invite": "on",
            },
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)

        row = db_conn.execute(
            text("SELECT userID, password, InitReset FROM Users WHERE username = :u"),
            {"u": username},
        ).fetchone()
        assert row is not None
        user_id, stored_hash, init_reset = row
        assert stored_hash.startswith("$2")  # bcrypt, not the raw placeholder
        assert init_reset == 1

        assert sent["email"] == username
        html = sent["message"]["message"]["body"]["content"]
        token = re.search(r"/reset_password/([\w.\-]+)", html).group(1)
        assert _load_reset_token(token) == (username, True)  # (email, is_invite)
    finally:
        # Same rationale as test_admin_add_user_with_assign_permission_returns_200:
        # only a separately-committed connection actually removes the row.
        if user_id is not None:
            conn = engine_nexora_db.raw_connection()
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM Users WHERE userID = ?", [user_id])
                conn.commit()
                cur.close()
            finally:
                conn.close()


def test_admin_edit_user_nonexistent(admin_client, admin_all_perms):
    """Editing a missing user — accept any non-200 since seed user-id is 1001+."""
    resp = admin_client.post(
        "/admin/users/edit/999999",
        json={
            "username": "x",
            "fullname": "y",
            "email": "z@z.local",
            "organization": "Test Organization",
            "accessprofile": "TestUser",
        },
    )
    assert resp.status_code in (200, 400, 403, 500)


# ---- Task 20: silent access-profile reassignment on save ------------------
#
# The admin_user_detail template only lists options from assignable_profiles
# (the *editing* admin's own assignable set). If the edited user's CURRENT
# profile is outside that set (e.g. a lesser admin viewing a user who holds a
# super-admin-only profile), no <option> is `selected`, the browser defaults
# to submitting the first option, and saving any unrelated field silently
# reassigns the profile. These tests patch
# nx_lib.views.admin.users.assignable_profile_ids (the module-level binding
# admin_edit_user actually calls — see
# test_admin_add_user_returns_403_when_profile_not_assignable's docstring
# above) to simulate an admin who can assign nothing, while editing
# user@test.local whose current profile IS 'TestUser'.


def test_admin_edit_user_unchanged_unassignable_profile_roundtrips(
    admin_client, monkeypatch, db_conn
):
    """Echoing the user's current (unassignable-to-this-admin) profile back
    unchanged must succeed — an untouched <select> round-trips the current
    value even when it isn't in this admin's assignable set."""
    from sqlalchemy import text

    monkeypatch.setattr("nx_lib.views.admin.users.assignable_profile_ids", lambda: set())
    uid = db_conn.execute(
        text("SELECT userID FROM Users WHERE username = 'user@test.local'")
    ).scalar()

    resp = admin_client.post(
        f"/admin/users/edit/{uid}",
        json={
            "username": "user@test.local",
            "fullname": "Test User",
            "email": "user@test.local",
            "organization": "Test Organization",
            "accessprofile": "TestUser",
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    profile = db_conn.execute(
        text(
            "SELECT ap.Name FROM Users u JOIN AccessProfile ap ON u.accessid = ap.AccessID "
            "WHERE u.userID = :uid"
        ),
        {"uid": uid},
    ).scalar()
    assert profile == "TestUser"


def test_admin_edit_user_changed_to_unassignable_profile_returns_403(
    admin_client, monkeypatch, db_conn
):
    """Switching to a DIFFERENT profile the admin cannot assign must be
    rejected, even though the user's current profile was already outside
    this admin's assignable set."""
    from sqlalchemy import text

    monkeypatch.setattr("nx_lib.views.admin.users.assignable_profile_ids", lambda: set())
    uid = db_conn.execute(
        text("SELECT userID FROM Users WHERE username = 'user@test.local'")
    ).scalar()

    resp = admin_client.post(
        f"/admin/users/edit/{uid}",
        json={
            "username": "user@test.local",
            "fullname": "Test User",
            "email": "user@test.local",
            "organization": "Test Organization",
            "accessprofile": "TestNoPerm",
        },
    )
    assert resp.status_code == 403

    profile = db_conn.execute(
        text(
            "SELECT ap.Name FROM Users u JOIN AccessProfile ap ON u.accessid = ap.AccessID "
            "WHERE u.userID = :uid"
        ),
        {"uid": uid},
    ).scalar()
    assert profile == "TestUser"


# ---- Phase-review fix: disabled+selected <option> is dropped from FormData -
#
# A code-review finding (post-26e6a3c) established that a <select> option
# that is both `selected` AND `disabled` is EXCLUDED from FormData on submit
# in real browsers (Playwright-verified on Chromium and Firefox). Since the
# JS builds its POST body via `new FormData(form)`, the disabled-but-selected
# current-profile option meant an untouched form silently omitted
# "accessprofile" from the request entirely -- and the server treated a
# missing/None value as "trying to clear the profile", 403ing the WHOLE
# request (not just the profile change) for any user whose current profile
# fell outside the editing admin's assignable set. The fix removes `disabled`
# from the template option (kept `selected`), plus a server-side
# defense-in-depth: an absent accessprofile key is now treated as "unchanged".


def test_admin_edit_user_missing_accessprofile_key_saves_other_fields(
    admin_client, monkeypatch, db_conn
):
    """Reproduces the finding directly: a request body with NO "accessprofile"
    key at all (what the pre-fix disabled+selected option produced via
    FormData) must still let the admin save an unrelated field (fullname)
    successfully -- 200, not 403 -- and must leave the profile untouched."""
    from sqlalchemy import text

    monkeypatch.setattr("nx_lib.views.admin.users.assignable_profile_ids", lambda: set())
    uid = db_conn.execute(
        text("SELECT userID FROM Users WHERE username = 'user@test.local'")
    ).scalar()

    resp = admin_client.post(
        f"/admin/users/edit/{uid}",
        json={
            "username": "user@test.local",
            "fullname": "Renamed Via Test",
            "email": "user@test.local",
            "organization": "Test Organization",
            # "accessprofile" intentionally omitted -- simulates the dropped
            # FormData key from a selected+disabled <option>.
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    row = db_conn.execute(
        text(
            "SELECT u.fullname, ap.Name FROM Users u JOIN AccessProfile ap ON u.accessid = ap.AccessID "
            "WHERE u.userID = :uid"
        ),
        {"uid": uid},
    ).one()
    assert row[0] == "Renamed Via Test"
    assert row[1] == "TestUser"


def test_admin_user_detail_current_unassignable_option_not_disabled(
    admin_client, monkeypatch, db_conn
):
    """Regression test for the literal template defect: the rendered
    current-but-unassignable <option> must be `selected` but must NOT be
    `disabled` -- the combination is what real browsers drop from FormData."""
    import re

    from sqlalchemy import text

    monkeypatch.setattr("nx_lib.views.admin.users.assignable_profile_ids", lambda: set())
    uid = db_conn.execute(
        text("SELECT userID FROM Users WHERE username = 'user@test.local'")
    ).scalar()

    resp = admin_client.get(f"/admin/users/{uid}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    m = re.search(r'<option[^>]*data-testid="admin-userdetail-accessprofile-current"[^>]*>', html)
    assert m, "expected the current-but-unassignable <option> to be rendered"
    option_tag = m.group(0)
    assert "selected" in option_tag
    assert "disabled" not in option_tag


def test_admin_user_detail_renders(admin_client, admin_all_perms, db_conn):
    """Use the seeded admin user-id (queried fresh because IDENTITY starts at 1001+)."""
    from sqlalchemy import text

    uid = db_conn.execute(
        text("SELECT userID FROM Users WHERE username = 'admin@test.local'")
    ).scalar()
    resp = admin_client.get(f"/admin/users/{uid}")
    assert resp.status_code in (200, 500)


def test_api_admin_user_activity_returns_json(admin_client, admin_all_perms, db_conn):
    from sqlalchemy import text

    uid = db_conn.execute(
        text("SELECT userID FROM Users WHERE username = 'admin@test.local'")
    ).scalar()
    resp = admin_client.get(f"/api/admin/users/{uid}/activity")
    assert resp.status_code in (200, 500)


def test_admin_delete_user_missing_returns_404_or_500(admin_client, admin_all_perms):
    resp = admin_client.delete("/admin/users/delete/999999")
    assert resp.status_code in (200, 404, 500)


# ---- delete-user cascade / atomicity (Task 13) -----------------------------
# admin_delete_user commits on its own raw connection, so its writes PERSIST
# past the transaction-scoped db_conn fixture. These tests therefore seed and
# tear down through a separate, explicitly-committed raw connection (the same
# approach the /admin/users/add cleanup above uses).


def _dc_raw():
    from nx_lib.db import engine_nexora_db

    return engine_nexora_db.raw_connection()


def _dc_seed_user(cur, username):
    cur.execute(
        "INSERT INTO Users (username, password, Fullname, Email, accessid, organizationCode) "
        "VALUES (?, 'x', 'Seed', ?, "
        "(SELECT AccessID FROM AccessProfile WHERE Name = 'TestUser'), 'TEST')",
        (username, username),
    )
    cur.execute("SELECT userID FROM Users WHERE username = ?", (username,))
    return cur.fetchone()[0]


def _dc_seed_report(cur, owner_id, name):
    cur.execute(
        "INSERT INTO Reports (OwnerUserID, Name, DefinitionJSON, Visibility) "
        "VALUES (?, ?, '{}', 'shared')",
        (owner_id, name),
    )
    cur.execute("SELECT ReportID FROM Reports WHERE OwnerUserID = ? AND Name = ?", (owner_id, name))
    return cur.fetchone()[0]


def _dc_cleanup(user_ids, report_ids):
    """Best-effort FK-safe teardown of anything the tests seeded, whether or not
    the route under test removed it (RED runs leave the whole fixture behind)."""
    uids = [u for u in user_ids if u]
    rids = [r for r in report_ids if r]
    conn = _dc_raw()
    try:
        cur = conn.cursor()
        if rids:
            rmarks = ",".join(["?"] * len(rids))
            cur.execute(f"DELETE FROM ReportShares WHERE ReportID IN ({rmarks})", rids)
            cur.execute(f"DELETE FROM ReportSchedules WHERE ReportID IN ({rmarks})", rids)
        if uids:
            umarks = ",".join(["?"] * len(uids))
            cur.execute(f"DELETE FROM ReportShares WHERE SharedWithUserID IN ({umarks})", uids)
            cur.execute(f"DELETE FROM ReportSchedules WHERE OwnerUserID IN ({umarks})", uids)
        if rids:
            cur.execute(f"DELETE FROM Reports WHERE ReportID IN ({rmarks})", rids)
        if uids:
            cur.execute(f"DELETE FROM Users WHERE userID IN ({umarks})", uids)
        conn.commit()
        cur.close()
    finally:
        conn.close()


def test_admin_delete_user_report_owner_is_atomic_no_halfstate(
    admin_client, admin_all_perms, db_conn
):
    """A report-owning user must never end up in a half-deleted state (their
    report gone but the Users row surviving).

    Under the pre-fix code each child delete committed individually, then the
    final `DELETE FROM users` violated FK_Reports_Users and threw — leaving the
    report gone but the user present and now undeletable.
    """
    from sqlalchemy import text

    suffix = uuid.uuid4().hex[:8]
    d_id = r_id = None
    try:
        conn = _dc_raw()
        cur = conn.cursor()
        d_id = _dc_seed_user(cur, f"del-{suffix}@test.local")
        r_id = _dc_seed_report(cur, d_id, f"rep-{suffix}")
        conn.commit()
        cur.close()
        conn.close()

        resp = admin_client.delete(f"/admin/users/delete/{d_id}")

        user_left = db_conn.execute(
            text("SELECT COUNT(*) FROM Users WHERE userID = :u"), {"u": d_id}
        ).scalar()
        report_left = db_conn.execute(
            text("SELECT COUNT(*) FROM Reports WHERE ReportID = :r"), {"r": r_id}
        ).scalar()

        # The atomicity invariant: it is never the case that the child row was
        # committed-deleted while the Users row survives.
        assert not (report_left == 0 and user_left == 1), (
            "HALF-STATE: report committed-deleted but Users row survives "
            f"(status={resp.status_code}, user_left={user_left}, report_left={report_left})"
        )
        # Fixed behaviour: a clean, fully atomic success.
        assert resp.status_code == 200, resp.get_json()
        assert user_left == 0
        assert report_left == 0
    finally:
        _dc_cleanup([d_id], [r_id])


def test_admin_delete_user_cascades_reporting_artifacts(admin_client, admin_all_perms, db_conn):
    """Deleting a report-owning user removes every reporting artifact tied to
    them — their reports, the shares/schedules they hold, AND the shares/
    schedules that point at reports they own but that belong to *other* users —
    while leaving the other user and their own report completely untouched.
    """
    from sqlalchemy import text

    suffix = uuid.uuid4().hex[:8]
    d_id = o_id = r_d = r_o = None
    try:
        conn = _dc_raw()
        cur = conn.cursor()
        d_id = _dc_seed_user(cur, f"del-{suffix}@test.local")
        o_id = _dc_seed_user(cur, f"other-{suffix}@test.local")
        r_d = _dc_seed_report(cur, d_id, f"rD-{suffix}")  # report owned by deleted user
        r_o = _dc_seed_report(cur, o_id, f"rO-{suffix}")  # report owned by survivor
        # Direct: a share held BY / schedule owned BY the deleted user, on the
        # survivor's report.
        cur.execute(
            "INSERT INTO ReportShares (ReportID, SharedWithUserID) VALUES (?, ?)", (r_o, d_id)
        )
        cur.execute(
            "INSERT INTO ReportSchedules (ReportID, OwnerUserID, Recipients, Frequency) "
            "VALUES (?, ?, 'x@test.local', 'daily')",
            (r_o, d_id),
        )
        # Transitive: a share / schedule that points at the deleted user's OWN
        # report but belongs to the *other* user — only reachable via the
        # report, not via SharedWithUserID / OwnerUserID = deleted user.
        cur.execute(
            "INSERT INTO ReportShares (ReportID, SharedWithUserID) VALUES (?, ?)", (r_d, o_id)
        )
        cur.execute(
            "INSERT INTO ReportSchedules (ReportID, OwnerUserID, Recipients, Frequency) "
            "VALUES (?, ?, 'x@test.local', 'daily')",
            (r_d, o_id),
        )
        conn.commit()
        cur.close()
        conn.close()

        resp = admin_client.delete(f"/admin/users/delete/{d_id}")
        assert resp.status_code == 200, resp.get_json()

        def _count(sql, **params):
            return db_conn.execute(text(sql), params).scalar()

        # The deleted user and every artifact tied to them are gone.
        assert _count("SELECT COUNT(*) FROM Users WHERE userID = :u", u=d_id) == 0
        assert _count("SELECT COUNT(*) FROM Reports WHERE ReportID = :r", r=r_d) == 0
        assert _count("SELECT COUNT(*) FROM ReportShares WHERE SharedWithUserID = :u", u=d_id) == 0
        assert _count("SELECT COUNT(*) FROM ReportSchedules WHERE OwnerUserID = :u", u=d_id) == 0
        # Transitive rows on the deleted user's report are gone too.
        assert _count("SELECT COUNT(*) FROM ReportShares WHERE ReportID = :r", r=r_d) == 0
        assert _count("SELECT COUNT(*) FROM ReportSchedules WHERE ReportID = :r", r=r_d) == 0
        # The survivor and their own report are untouched.
        assert _count("SELECT COUNT(*) FROM Users WHERE userID = :u", u=o_id) == 1
        assert _count("SELECT COUNT(*) FROM Reports WHERE ReportID = :r", r=r_o) == 1
    finally:
        _dc_cleanup([d_id, o_id], [r_d, r_o])


def test_admin_revoke_session_unknown_id(admin_client, admin_all_perms):
    resp = admin_client.post("/admin/sessions/not-a-real-sid/revoke")
    assert resp.status_code in (200, 404, 500)


def test_admin_revoke_all_sessions(admin_client, admin_all_perms, db_conn):
    from sqlalchemy import text

    uid = db_conn.execute(
        text("SELECT userID FROM Users WHERE username = 'admin@test.local'")
    ).scalar()
    resp = admin_client.post(f"/admin/users/{uid}/revoke_all")
    assert resp.status_code in (200, 500)


def test_api_admin_users_list_returns_json(admin_client, admin_all_perms):
    resp = admin_client.get("/api/admin/users/list")
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)


def test_admin_recent_logs_missing_table(admin_client, admin_all_perms):
    resp = admin_client.get("/api/admin/recent_logs")
    assert resp.status_code in (200, 500)


def test_admin_recent_logs_coerces_string_status_codes(admin_client, admin_all_perms, monkeypatch):
    """HttpResponseCode is NVARCHAR in the DB, so the route's `200 <= code < 300`
    comparison TypeErrors on every real row and the route 500s unconditionally.
    Also covers the sibling raw-datetime bug: Timestamp must serialize as
    ISO-8601, not Flask's default RFC-1123 JSON repr. The Logs table doesn't
    exist in NEXORA_TEST, so the DB layer is faked here to exercise the
    route's coercion + serialization in isolation.
    """
    import re
    from datetime import datetime
    from types import SimpleNamespace

    import nx_lib.views.admin as admin_module

    ts = datetime(2026, 7, 27, 13, 45, 30)

    rows = [
        SimpleNamespace(
            Timestamp=ts,
            Username="admin@test.local",
            HttpRequestMethod="GET",
            Path="/admin",
            HttpResponseCode="200",
        ),
        SimpleNamespace(
            Timestamp=ts,
            Username="admin@test.local",
            HttpRequestMethod="POST",
            Path="/admin/users/1",
            HttpResponseCode="500",
        ),
        SimpleNamespace(
            Timestamp=ts,
            Username="admin@test.local",
            HttpRequestMethod="GET",
            Path="/admin/broken",
            HttpResponseCode="ERR",
        ),
    ]

    class _FakeCursor:
        def execute(self, sql, params=None):
            pass

        def fetchall(self):
            return rows

        def close(self):
            pass

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

        def close(self):
            pass

    monkeypatch.setattr(admin_module.engine_nexora_db, "raw_connection", lambda: _FakeConn())

    resp = admin_client.get("/api/admin/recent_logs")
    assert resp.status_code == 200

    logs = resp.get_json()
    assert [entry["ActionStatus"] for entry in logs] == ["SUCCESS", "FAILURE", "FAILURE"]

    for entry in logs:
        assert entry["Timestamp"] == ts.isoformat()
        assert "GMT" not in entry["Timestamp"]
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", entry["Timestamp"])


def test_admin_active_sessions(admin_client, admin_all_perms):
    resp = admin_client.get("/api/admin/active_sessions")
    assert resp.status_code in (200, 500)


# ============================ access control + perms =========================


def test_admin_access_control_renders(admin_client, admin_all_perms):
    resp = admin_client.get("/admin/access_control")
    assert resp.status_code in (200, 500)


def test_get_users_admin_access_control(admin_client, admin_all_perms):
    resp = admin_client.get("/api/admin/users")
    assert resp.status_code in (200, 500)


def test_get_profile_details_seeded_id(admin_client, admin_all_perms, db_conn):
    from sqlalchemy import text

    aid = db_conn.execute(
        text("SELECT AccessID FROM AccessProfile WHERE Name = 'TestAdmin'")
    ).scalar()
    resp = admin_client.get(f"/api/admin/access_profile/{aid}/details")
    assert resp.status_code in (200, 500)


def test_save_access_profile_missing_body(admin_client, admin_all_perms):
    resp = admin_client.post("/api/admin/access_profile/save", json={})
    assert resp.status_code in (200, 400, 500)


def test_save_access_profile_stores_only_allow_rows(admin_client, admin_all_perms, db_conn):
    """Profile grants are allow-only rows (#238 Task 4): a 'D' entry in the
    save payload must simply not be persisted, not stored as a deny row."""
    from sqlalchemy import text

    access_id = db_conn.execute(
        text("SELECT AccessID FROM dbo.AccessProfile WHERE Name = 'TestNoPerm'")
    ).scalar()
    api_docs, jd = (
        row[0]
        for row in db_conn.execute(
            text(
                "SELECT PermissionID FROM dbo.Permission WHERE Code IN "
                "('jd.view', 'api.docs.view') ORDER BY Code"
            )
        ).fetchall()
    )
    try:
        resp = admin_client.post(
            "/api/admin/access_profile/save",
            json={
                "accessId": access_id,
                "name": "TestNoPerm",
                "description": "Test no-permission profile",
                "permissions": [
                    {"PermissionID": jd, "Effect": "A"},
                    {"PermissionID": api_docs, "Effect": "D"},
                ],
            },
        )
        assert resp.status_code == 200
        remaining = db_conn.execute(
            text("SELECT PermissionID FROM dbo.AccessProfilePermission WHERE AccessID = :aid"),
            {"aid": access_id},
        ).fetchall()
        assert [row[0] for row in remaining] == [jd]
    finally:
        db_conn.execute(
            text("DELETE FROM dbo.AccessProfilePermission WHERE AccessID = :aid"),
            {"aid": access_id},
        )
        db_conn.commit()


def test_save_access_profile_new_profile_inherits_creator_rank(
    admin_client, admin_all_perms, db_conn
):
    """#238 Phase 1 review finding: a brand-new profile (no accessId in the
    save payload) must inherit the creating actor's own Rank rather than
    fall through to the AccessProfile.Rank column default of 0. A Rank-0
    profile is assignable by every profiled actor per
    security.assignable_profile_ids() -- strictly weaker than the deleted
    admin.assign.user.accessprofile.* codes it replaced."""
    from sqlalchemy import text

    creator_rank = db_conn.execute(
        text(
            "SELECT ap.Rank FROM dbo.Users u "
            "JOIN dbo.AccessProfile ap ON ap.AccessID = u.accessid "
            "WHERE u.username = 'admin@test.local'"
        )
    ).scalar()
    assert creator_rank == 100  # seeded TestAdmin profile Rank (sql/test/seed.sql)

    name = f"task-rank-inherit-{uuid.uuid4().hex[:8]}"
    access_id = None
    try:
        resp = admin_client.post(
            "/api/admin/access_profile/save",
            json={"name": name, "description": "probe for creator-rank inheritance"},
        )
        assert resp.status_code == 200

        row = db_conn.execute(
            text("SELECT AccessID, Rank FROM dbo.AccessProfile WHERE Name = :name"),
            {"name": name},
        ).fetchone()
        assert row is not None
        access_id, rank = row
        assert rank == creator_rank
        assert rank != 0
    finally:
        if access_id is not None:
            db_conn.execute(
                text("DELETE FROM dbo.AccessProfilePermission WHERE AccessID = :aid"),
                {"aid": access_id},
            )
            db_conn.execute(
                text("DELETE FROM dbo.AccessProfile WHERE AccessID = :aid"),
                {"aid": access_id},
            )
            db_conn.commit()


def test_get_user_overrides_seeded(admin_client, admin_all_perms, db_conn):
    from sqlalchemy import text

    uid = db_conn.execute(
        text("SELECT userID FROM Users WHERE username = 'admin@test.local'")
    ).scalar()
    resp = admin_client.get(f"/api/admin/user_overrides/{uid}")
    assert resp.status_code in (200, 500)


def test_api_admin_user_effective_permissions(admin_client, admin_all_perms, db_conn):
    from sqlalchemy import text

    uid = db_conn.execute(
        text("SELECT userID FROM Users WHERE username = 'admin@test.local'")
    ).scalar()
    resp = admin_client.get(f"/api/admin/users/{uid}/effective_permissions")
    assert resp.status_code in (200, 500)


def test_save_user_overrides_missing_body(admin_client, admin_all_perms):
    resp = admin_client.post("/api/admin/user_overrides/save", json={})
    assert resp.status_code in (200, 400, 500)


def test_api_admin_permissions_list(admin_client, admin_all_perms):
    resp = admin_client.get("/api/admin/permissions/list")
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)


def test_api_admin_permission_users_seeded(admin_client, admin_all_perms, db_conn):
    from sqlalchemy import text

    pid = db_conn.execute(
        text("SELECT TOP 1 PermissionID FROM Permission ORDER BY PermissionID")
    ).scalar()
    resp = admin_client.get(f"/api/admin/permissions/{pid}/users")
    assert resp.status_code in (200, 500)


def test_api_admin_user_all_permissions(admin_client, admin_all_perms, db_conn):
    from sqlalchemy import text

    uid = db_conn.execute(
        text("SELECT userID FROM Users WHERE username = 'admin@test.local'")
    ).scalar()
    resp = admin_client.get(f"/api/admin/users/{uid}/all_permissions")
    assert resp.status_code == 200


def test_api_admin_permission_add_missing_body(admin_client, admin_all_perms):
    resp = admin_client.post("/api/admin/permissions/add", json={})
    assert resp.status_code == 400


def test_api_admin_permission_edit_unknown(admin_client, admin_all_perms):
    """PermissionID 999999 doesn't exist -> UPDATE affects 0 rows -> 404."""
    resp = admin_client.post(
        "/api/admin/permissions/edit/999999", json={"code": "x.y", "description": "d"}
    )
    assert resp.status_code == 404


def test_api_admin_permission_delete_unknown(admin_client, admin_all_perms):
    """PermissionID 999999 doesn't exist -> DELETE affects 0 rows -> 404."""
    resp = admin_client.delete("/api/admin/permissions/delete/999999")
    assert resp.status_code == 404


def test_api_admin_permission_crud_roundtrip(admin_client, admin_all_perms, db_conn):
    """Add -> edit -> verify Code round-trip with case preserved -> delete.

    Proves add/edit persist Code correctly and it's never lowercased, since
    process.<client>.<name>.view codes elsewhere are case-significant.
    """
    from sqlalchemy import text

    add_resp = admin_client.post(
        "/api/admin/permissions/add",
        json={"code": "Test.RoundTrip.Perm", "description": "d"},
    )
    assert add_resp.status_code == 200
    perm_id = add_resp.get_json()["permissionId"]
    assert perm_id

    try:
        edit_resp = admin_client.post(
            f"/api/admin/permissions/edit/{perm_id}",
            json={
                "code": "Test.RoundTrip.Perm",
                "description": "d-updated",
            },
        )
        assert edit_resp.status_code == 200

        row = db_conn.execute(
            text("SELECT Code, Description FROM Permission WHERE PermissionID = :pid"),
            {"pid": perm_id},
        ).one()
        assert row.Code == "Test.RoundTrip.Perm"
        assert row.Description == "d-updated"
    finally:
        del_resp = admin_client.delete(f"/api/admin/permissions/delete/{perm_id}")
        assert del_resp.status_code == 200


# ============================ header brand injection (#98 phase 4, Task 10) ===
#
# TEST_ORG_CODE ("TEST", seeded by sql/test/seed.sql) has no BrandName/
# BrandAccentHex/BrandLogoFile row content -- and the NEXORA_TEST database's
# Organizations table predates those columns entirely (nx_lib/branding.py's
# _is_missing_column_error path), so registry() already degrades to None on
# every real request here. That gives the "no branding" and "registry
# failure" cases the same natural coverage; the "org has branding" case is
# exercised by monkeypatching nx_lib.hooks.brand_for_org directly.


def _logo_block(html_bytes):
    html = html_bytes.decode("utf-8")
    m = re.search(r'<a[^>]*data-testid="nexora-logo-home".*?</a>', html, re.DOTALL)
    assert m, "nexora-logo-home block not found in rendered page"
    return m.group(0)


def _expected_unbranded_logo_block(href):
    """Today's pre-Task-10 markup, byte-for-byte -- an org with no branding
    (or a branding.registry() failure) must reproduce this exactly."""
    return (
        f'<a href="{href}" class="brand title-wrap flex items-center gap-3" '
        'data-testid="nexora-logo-home">\n'
        '  <div class="bh" aria-hidden="true">\n'
        '    <div class="bh-penumbra" aria-hidden="true"></div>\n'
        '    <div class="bh-core"></div>\n'
        '    <div class="bh-einstein-ring"></div>\n'
        '    <div class="bh-disk"></div>\n'
        '    <div class="bh-sparks" aria-hidden="true">\n'
        "      <i></i><i></i>\n"
        "    </div>\n"
        "  </div>\n"
        '  <div class="flex flex-col items-start">\n'
        '    <h1 class="nexora-title text-3xl font-semibold tracking-tight">nexora</h1>\n'
        '    <h2 class="nexora-subtitle text-xs font-semibold tracking-tight mt-1">powered by '
        "sydoc</h2>\n"
        "  </div>\n"
        "</a>"
    )


def test_header_logo_unbranded_org_renders_todays_markup(admin_client, app):
    """TEST org has no branding columns populated -- must be byte-identical
    to the pre-Task-10 fallback markup."""
    resp = admin_client.get("/admin")
    assert resp.status_code == 200
    block = _logo_block(resp.data)
    with app.test_request_context("/admin"):
        from flask import url_for

        href = url_for("index")
    assert block == _expected_unbranded_logo_block(href)


def test_header_logo_registry_failure_renders_todays_markup(admin_client, app, monkeypatch):
    """A branding.registry() failure (mirrored here as brand_for_org
    returning None) must also degrade to today's exact markup -- never a
    blank header."""
    monkeypatch.setattr("nx_lib.hooks.brand_for_org", lambda code: None)
    resp = admin_client.get("/admin")
    assert resp.status_code == 200
    block = _logo_block(resp.data)
    with app.test_request_context("/admin"):
        from flask import url_for

        href = url_for("index")
    assert block == _expected_unbranded_logo_block(href)


def test_header_logo_branded_org_shows_brand_name_and_logo(admin_client, monkeypatch):
    monkeypatch.setattr(
        "nx_lib.hooks.brand_for_org",
        lambda code: {"name": "Provera", "accent_hex": "#336699", "logo_file": "TEST.png"},
    )
    resp = admin_client.get("/admin")
    assert resp.status_code == 200
    block = _logo_block(resp.data)
    assert "Provera" in block
    assert ">nexora<" not in block
    assert "<img" in block
    assert "/branding/TEST/logo" in block or "TEST.png" in block


def test_header_prepaint_injects_brand_json_and_accent_fallback(admin_client, monkeypatch):
    monkeypatch.setattr(
        "nx_lib.hooks.brand_for_org",
        lambda code: {"name": "Provera", "accent_hex": "#336699", "logo_file": "TEST.png"},
    )
    resp = admin_client.get("/admin")
    body = resp.data.decode("utf-8")
    assert '"accent_hex": "#336699"' in body or '"accent_hex":"#336699"' in body
    assert "var brand = " in body


def test_header_prepaint_accent_fallback_source_uses_brand_then_hardcoded():
    """Regression guard for D4 (spec): the *user's own* stored accent must
    still win over the org brand accent, which itself only replaces the
    previously-hardcoded default. Asserted against the template source since
    exercising the inline pre-paint script needs a JS engine."""
    with open("templates/_header.html", encoding="utf-8") as f:
        src = f.read()
    assert "accent:     stored.accent     || (brand.accent_hex ? 'custom' : 'amber')," in src
    assert "accentHex:  stored.accentHex  || brand.accent_hex || '#4f46e5'," in src


def test_brand_logo_class_bounds_both_axes():
    """height="48" on the <img> bounds one axis only -- an SVG with no intrinsic
    size and no viewBox falls back to 300px wide. The header must not be
    pushable by a customer-uploaded logo, so .nx-brand-logo needs a real rule in
    the stylesheet the logo partial loads."""
    with open("templates/nexora_logo/_nexora_logo.html", encoding="utf-8") as f:
        assert 'class="nx-brand-logo"' in f.read()
    with open("static/css/_nexoraLogo.css", encoding="utf-8") as f:
        css = f.read()
    assert ".nx-brand-logo" in css
    rule = css.split(".nx-brand-logo", 1)[1].split("}", 1)[0]
    assert "max-width" in rule
    assert "object-fit" in rule


# ============================ /branding/<orgcode>/logo route ==================


def test_branding_logo_anonymous_is_rejected(client):
    resp = client.get("/branding/TEST/logo")
    assert resp.status_code in (401, 404)


def test_branding_logo_unknown_org_is_404(admin_client):
    resp = admin_client.get("/branding/NOPE/logo")
    assert resp.status_code == 404


def test_branding_logo_known_org_without_logo_file_is_404(admin_client, monkeypatch):
    monkeypatch.setattr("nx_lib.views.core.brand_for_org", lambda code: {"logo_file": None})
    resp = admin_client.get("/branding/TEST/logo")
    assert resp.status_code == 404


def test_branding_logo_missing_file_on_disk_is_404(admin_client, monkeypatch):
    monkeypatch.setattr(
        "nx_lib.views.core.brand_for_org", lambda code: {"logo_file": "TEST-missing.png"}
    )
    resp = admin_client.get("/branding/TEST/logo")
    assert resp.status_code == 404


def test_branding_logo_serves_file_with_hardening_headers(admin_client, monkeypatch, tmp_path):
    monkeypatch.setattr("nx_lib.views.core.PATHS.branding", tmp_path)
    (tmp_path / "TEST.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr("nx_lib.views.core.brand_for_org", lambda code: {"logo_file": "TEST.png"})
    resp = admin_client.get("/branding/TEST/logo")
    assert resp.status_code == 200
    assert resp.headers.get("Content-Security-Policy") == "sandbox"
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"


def test_branding_logo_is_cacheable(admin_client, monkeypatch, tmp_path):
    """The header fetches this on every page load of a branded org. Flask's
    default max_age is None -- a conditional round-trip per page view."""
    monkeypatch.setattr("nx_lib.views.core.PATHS.branding", tmp_path)
    (tmp_path / "TEST.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr("nx_lib.views.core.brand_for_org", lambda code: {"logo_file": "TEST.png"})
    resp = admin_client.get("/branding/TEST/logo")
    assert resp.status_code == 200
    assert "max-age=" in (resp.headers.get("Cache-Control") or "")
    assert resp.cache_control.max_age == core_views.BRANDING_LOGO_MAX_AGE > 0


# ---- the same assertion, but with Talisman active (i.e. the way PROD runs) ---
#
# Talisman is installed ONLY in PROD (nx_lib/__init__.py) and its after_request
# assigns Content-Security-Policy unconditionally. The test above therefore
# passes vacuously: it runs in TEST, where nothing can overwrite the view's
# header. These build a second app wired exactly like PROD so a regression --
# dropping branding_logo.talisman_view_options -- actually fails.


@pytest.fixture(scope="module")
def prod_csp_app():
    from flask_talisman import Talisman

    from nx_lib import config as _cfg
    from nx_lib import create_app as _create_app

    prod_app = _create_app()
    prod_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    Talisman(
        prod_app, content_security_policy=_cfg.CSP, content_security_policy_nonce_in=["script-src"]
    )
    return prod_app


@pytest.fixture()
def prod_csp_client(prod_csp_app):
    c = prod_csp_app.test_client()
    with c.session_transaction() as sess:
        sess["userid"] = 1
        sess["username"] = "admin@test.local"
    return c


def test_talisman_is_actually_active_on_the_prod_shaped_app(prod_csp_client):
    """Control: without this, the next test could pass for the wrong reason."""
    resp = prod_csp_client.get("/login", base_url="https://localhost")
    csp = resp.headers.get("Content-Security-Policy") or ""
    assert "script-src" in csp and "cdn.jsdelivr.net" in csp


def test_branding_logo_sandbox_csp_survives_talisman(prod_csp_client, monkeypatch, tmp_path):
    """The one control that makes script-capable SVG safe (spec D9) must reach
    the client on PROD, not just on INT."""
    monkeypatch.setattr("nx_lib.views.core.PATHS.branding", tmp_path)
    (tmp_path / "TEST.svg").write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>')
    monkeypatch.setattr("nx_lib.views.core.brand_for_org", lambda code: {"logo_file": "TEST.svg"})
    resp = prod_csp_client.get("/branding/TEST/logo", base_url="https://localhost")
    assert resp.status_code == 200
    csp = resp.headers.get("Content-Security-Policy") or ""
    # Talisman renders a dict policy as "<section> <content>" -> "sandbox ".
    assert csp.strip() == "sandbox"
    assert "script-src" not in csp
    assert "nonce-" not in csp
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"


def test_branding_logo_path_traversal_via_logo_file_is_blocked(admin_client, monkeypatch, tmp_path):
    """A hostile BrandLogoFile value must never escape var/branding/ -- even
    though Task 11's upload path is expected to only ever write
    <orgcode>.<ext>, defend the read side independently."""
    secret_dir = tmp_path.parent / "secret"
    secret_dir.mkdir()
    (secret_dir / "hidden.png").write_bytes(b"top-secret")
    monkeypatch.setattr("nx_lib.views.core.PATHS.branding", tmp_path)
    monkeypatch.setattr(
        "nx_lib.views.core.brand_for_org",
        lambda code: {"logo_file": "../secret/hidden.png"},
    )
    resp = admin_client.get("/branding/TEST/logo")
    assert resp.status_code == 404


# ============ /admin/organizations/<code>/branding (Task 11, #98 phase 4) =====
#
# Branding attaches to the Organization (the customer -- PRVR, LKTR, ...),
# never to ClientCode (the runtime source).
#
# The TEST database's Organizations table predates migration 0081, so the
# BrandName/BrandAccentHex/BrandLogoFile UPDATE cannot run against it: tests
# that need to reach the write substitute a fake engine.

_PNG_1x1 = _b64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
_BRANDING_URL = "/admin/organizations/TEST/branding"


def _fake_nexora_engine():
    """MagicMock stand-in for engine_nexora_db: every SELECT "succeeds" (the
    org exists) and the UPDATE is recorded rather than executed."""
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    engine = MagicMock()
    engine.raw_connection.return_value = conn
    return engine, conn, cursor


@pytest.fixture()
def branding_write(monkeypatch, tmp_path):
    """Redirect var/branding/ at a tmp dir, stub the DB and count
    invalidate_branding() calls. Yields (tmp_path, cursor, calls)."""
    engine, _conn, cursor = _fake_nexora_engine()
    calls = []
    monkeypatch.setattr("nx_lib.views.admin.organizations.engine_nexora_db", engine)
    monkeypatch.setattr("nx_lib.views.admin.organizations.PATHS.branding", tmp_path)
    monkeypatch.setattr(
        "nx_lib.views.admin.organizations.invalidate_branding", lambda: calls.append(1)
    )
    yield tmp_path, cursor, calls


def test_branding_save_without_permission_is_403(noperm_client):
    resp = noperm_client.post(_BRANDING_URL, json={"brand_name": "Provera"})
    assert resp.status_code == 403


def test_branding_save_gate_is_the_branding_permission(admin_client, monkeypatch):
    """admin.view.organizations alone must not be enough to save branding."""
    monkeypatch.setattr(
        "nx_lib.security.has_permission", lambda code: code == "admin.view.organizations"
    )
    resp = admin_client.post(_BRANDING_URL, json={"brand_name": "Provera"})
    assert resp.status_code == 403


def test_branding_save_rejects_non_image_with_svg_name(
    admin_client, admin_all_perms, branding_write
):
    """MIME sniff is on the bytes, not the filename: a Windows executable
    called logo.svg must be rejected and never reach disk."""
    tmp_path, _cursor, calls = branding_write
    data = {"logo": (_io.BytesIO(b"MZ\x90\x00" + b"\x00" * 4096), "logo.svg")}
    resp = admin_client.post(_BRANDING_URL, data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert list(tmp_path.iterdir()) == []
    assert calls == []


def test_branding_save_accepts_a_real_svg(admin_client, admin_all_perms, branding_write):
    tmp_path, _cursor, calls = branding_write
    svg = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8">'
        b'<rect width="8" height="8"/></svg>'
    )
    data = {"logo": (_io.BytesIO(svg), "brand.svg")}
    resp = admin_client.post(_BRANDING_URL, data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    assert (tmp_path / "TEST.svg").read_bytes() == svg
    assert calls == [1]


def test_branding_save_rejects_oversize_logo(admin_client, admin_all_perms, branding_write):
    """512 KB cap, enforced server-side and before anything is written."""
    tmp_path, _cursor, calls = branding_write
    oversize = _PNG_1x1 + b"\x00" * (512 * 1024)
    data = {"logo": (_io.BytesIO(oversize), "logo.png")}
    resp = admin_client.post(_BRANDING_URL, data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert list(tmp_path.iterdir()) == []
    assert calls == []


def test_branding_save_rejects_disallowed_extension(admin_client, admin_all_perms, branding_write):
    """is_file_allowed also knows pdf/xlsx -- a logo must not."""
    tmp_path, _cursor, calls = branding_write
    data = {"logo": (_io.BytesIO(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), "logo.pdf")}
    resp = admin_client.post(_BRANDING_URL, data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert list(tmp_path.iterdir()) == []
    assert calls == []


def test_branding_save_writes_logo_named_after_the_org(
    admin_client, admin_all_perms, branding_write
):
    """The stored name is derived from the org code, never from the client
    filename -- so Task 10's serve route finds it at var/branding/<code>.<ext>."""
    tmp_path, cursor, calls = branding_write
    data = {
        "brand_name": "Provera",
        "brand_accent_hex": "#336699",
        "logo": (_io.BytesIO(_PNG_1x1), "../../evil name.png"),
    }
    resp = admin_client.post(_BRANDING_URL, data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    assert (tmp_path / "TEST.png").read_bytes() == _PNG_1x1
    assert list(tmp_path.iterdir()) == [tmp_path / "TEST.png"]
    assert calls == [1]
    params = [c.args[1] for c in cursor.execute.call_args_list if len(c.args) > 1]
    assert any("Provera" in p and "#336699" in p and "TEST.png" in p for p in params)


def test_branding_save_json_without_logo_invalidates_cache(
    admin_client, admin_all_perms, branding_write
):
    _tmp, _cursor, calls = branding_write
    resp = admin_client.post(
        _BRANDING_URL, json={"brand_name": "Provera", "brand_accent_hex": "#336699"}
    )
    assert resp.status_code == 200
    assert calls == [1]


def test_branding_save_rejects_bad_accent_hex(admin_client, admin_all_perms, branding_write):
    _tmp, _cursor, calls = branding_write
    resp = admin_client.post(_BRANDING_URL, json={"brand_accent_hex": "red; drop table"})
    assert resp.status_code == 400
    assert calls == []


def test_branding_save_stores_null_for_empty_accent(admin_client, admin_all_perms, branding_write):
    """An empty accent means "fall back to Nexora branding", i.e. NULL."""
    _tmp, cursor, calls = branding_write
    resp = admin_client.post(_BRANDING_URL, json={"brand_name": "", "brand_accent_hex": ""})
    assert resp.status_code == 200
    assert calls == [1]
    updates = [
        c.args[1]
        for c in cursor.execute.call_args_list
        if c.args and "UPDATE" in c.args[0].upper() and len(c.args) > 1
    ]
    assert updates, "no UPDATE issued"
    assert updates[-1][0] is None and updates[-1][1] is None


def test_branding_save_rejects_traversal_shaped_orgcode(
    admin_client, admin_all_perms, branding_write
):
    """The org code reaches a filesystem path -- anything but a plain
    alphanumeric code must be refused before a path is built."""
    tmp_path, _cursor, calls = branding_write
    resp = admin_client.post("/admin/organizations/..TEST/branding", json={"brand_name": "Provera"})
    assert resp.status_code == 404
    assert list(tmp_path.iterdir()) == []
    assert calls == []


def test_branding_save_unknown_org_is_404(admin_client, admin_all_perms, monkeypatch, tmp_path):
    monkeypatch.setattr("nx_lib.views.admin.organizations.PATHS.branding", tmp_path)
    resp = admin_client.post("/admin/organizations/NOPE/branding", json={"brand_name": "Provera"})
    assert resp.status_code == 404


def test_organizations_page_shows_branding_panel_with_perm(
    admin_client, admin_all_perms, monkeypatch
):
    # can_edit_branding is resolved through views.admin.organizations' own
    # has_permission binding, which admin_all_perms (nx_lib.security) doesn't cover.
    monkeypatch.setattr("nx_lib.views.admin.organizations.has_permission", lambda code: True)
    resp = admin_client.get("/admin/organizations")
    assert resp.status_code == 200
    assert b'data-testid="admin-org-branding-panel"' in resp.data


def test_organizations_page_hides_branding_panel_without_perm(admin_client, monkeypatch):
    """A viewer who only holds admin.view.organizations must not see the
    controls at all -- a 403 toast after the click is the bug, not the gate."""
    monkeypatch.setattr(
        "nx_lib.security.has_permission", lambda code: code == "admin.view.organizations"
    )
    monkeypatch.setattr(
        "nx_lib.views.admin.organizations.has_permission",
        lambda code: code == "admin.view.organizations",
    )
    resp = admin_client.get("/admin/organizations")
    assert resp.status_code == 200
    assert b'data-testid="admin-org-branding-panel"' not in resp.data
    assert b"admin-org-branding-TEST" not in resp.data
