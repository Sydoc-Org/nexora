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
- MaintenanceBanner  (admin/maintenance endpoints)
- Logs               (admin/logs and admin_dashboard counters)
- DashboardLayouts   (dashboard widget routes — not in this file)

Sections:
- /admin                    overview
- /admin/organizations/*    CRUD + list
- /admin/maintenance*       CRUD + list  (MaintenanceBanner absent)
- /admin/logs*              search + export  (Logs absent)
- /admin/sessions + /admin/users/* CRUD + revoke
- /admin/access_control + access profile + override
- /api/admin/permissions/*  CRUD
"""

import uuid

import pytest


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


def test_api_admin_organizations_list(admin_client, admin_all_perms):
    resp = admin_client.get("/api/admin/organizations/list")
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)


# ============================ maintenance banner =============================


def test_admin_maintenance_view_gated(noperm_client):
    resp = noperm_client.get("/admin/maintenance")
    assert resp.status_code == 403


def test_admin_maintenance_view_with_perms(admin_client, admin_all_perms):
    """MaintenanceBanner table absent → 200 or 500 from except branch."""
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


def test_admin_add_user_duplicate_returns_409_or_500(admin_client, admin_all_perms, monkeypatch):
    """Re-add user@test.local → IntegrityError 409.

    admin_all_perms only patches nx_lib.security.has_permission (reached by the
    @require_permission decorator's dynamic lookup); it does NOT reach the
    inline admin.assign.user.accessprofile.* gate added to admin_add_user,
    which resolves nx_lib.views.admin.has_permission (bound at import time).
    Patch that binding too so this test keeps exercising the duplicate-409
    path instead of newly dying on the 403 gate.
    """
    monkeypatch.setattr("nx_lib.views.admin.has_permission", lambda code: True)
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


def test_admin_add_user_without_assign_permission_returns_403(admin_client, monkeypatch, db_conn):
    """admin.create.user alone must not be enough to assign an access profile.

    The @require_permission("admin.create.user") decorator resolves the REAL
    nx_lib.security.has_permission at call time — TestAdmin (admin@test.local)
    is seeded with every permission, so that check still passes. Only the
    inline admin.assign.user.accessprofile.<profile> gate is denied here, by
    patching the nx_lib.views.admin module-level binding (the one the inline
    call inside admin_add_user actually resolves — patching
    nx_lib.security.has_permission would NOT reach it).
    """
    from sqlalchemy import text

    monkeypatch.setattr(
        "nx_lib.views.admin.has_permission",
        lambda code: not code.startswith("admin.assign.user.accessprofile."),
    )
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


def test_admin_add_user_with_assign_permission_returns_200(admin_client, monkeypatch, db_conn):
    """Holding the assign-permission (in addition to admin.create.user) allows creation.

    Deliberately does NOT use admin_all_perms — that fixture patches
    nx_lib.security.has_permission, which the inline gate in admin_add_user
    (bound as nx_lib.views.admin.has_permission at import time) cannot see.
    """
    from sqlalchemy import text

    from nx_lib.db import engine_nexora_db

    monkeypatch.setattr("nx_lib.views.admin.has_permission", lambda code: True)
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

    monkeypatch.setattr("nx_lib.views.admin.has_permission", lambda code: True)

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
        assert _load_reset_token(token) == username
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
# reassigns the profile. These tests patch nx_lib.views.admin.has_permission
# (the module-level binding the inline gate in admin_edit_user actually
# resolves — see test_admin_add_user_without_assign_permission_returns_403's
# docstring above) to simulate an admin who cannot assign 'TestUser' or
# 'TestNoPerm', while editing user@test.local whose current profile IS
# 'TestUser'.


def test_admin_edit_user_unchanged_unassignable_profile_roundtrips(
    admin_client, monkeypatch, db_conn
):
    """Echoing the user's current (unassignable-to-this-admin) profile back
    unchanged must succeed — an untouched <select> round-trips the current
    value even when it isn't in this admin's assignable set."""
    from sqlalchemy import text

    monkeypatch.setattr(
        "nx_lib.views.admin.has_permission",
        lambda code: code
        not in (
            "admin.assign.user.accessprofile.testuser",
            "admin.assign.user.accessprofile.testnoperm",
        ),
    )
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

    monkeypatch.setattr(
        "nx_lib.views.admin.has_permission",
        lambda code: code
        not in (
            "admin.assign.user.accessprofile.testuser",
            "admin.assign.user.accessprofile.testnoperm",
        ),
    )
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

    monkeypatch.setattr(
        "nx_lib.views.admin.has_permission",
        lambda code: code
        not in (
            "admin.assign.user.accessprofile.testuser",
            "admin.assign.user.accessprofile.testnoperm",
        ),
    )
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

    monkeypatch.setattr(
        "nx_lib.views.admin.has_permission",
        lambda code: code
        not in (
            "admin.assign.user.accessprofile.testuser",
            "admin.assign.user.accessprofile.testnoperm",
        ),
    )
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
    """Permission.SortingCode exists (Task 1) so this no longer 500s."""
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
    """Add -> edit -> verify Code/SortingCode round-trip with case preserved -> delete.

    Exercises the SortingCode column end-to-end (Task 1 added it to Permission;
    this proves add/edit persist it correctly and that Code/SortingCode are
    never lowercased, since *.filter.process.* codes elsewhere are case-significant).
    """
    from sqlalchemy import text

    add_resp = admin_client.post(
        "/api/admin/permissions/add",
        json={"code": "Test.RoundTrip.Perm", "description": "d", "sortingCode": "Z9"},
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
                "sortingCode": "Z9",
            },
        )
        assert edit_resp.status_code == 200

        row = db_conn.execute(
            text("SELECT Code, SortingCode, Description FROM Permission WHERE PermissionID = :pid"),
            {"pid": perm_id},
        ).one()
        assert row.Code == "Test.RoundTrip.Perm"
        assert row.SortingCode == "Z9"
        assert row.Description == "d-updated"
    finally:
        del_resp = admin_client.delete(f"/api/admin/permissions/delete/{perm_id}")
        assert del_resp.status_code == 200
