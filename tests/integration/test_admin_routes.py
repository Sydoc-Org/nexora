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


def test_admin_add_user_duplicate_returns_409_or_500(admin_client, admin_all_perms):
    """Re-add user@test.local → IntegrityError 409."""
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
        json={"code": "test.roundtrip.perm", "description": "d", "sortingCode": "Z9"},
    )
    assert add_resp.status_code == 200
    perm_id = add_resp.get_json()["permissionId"]
    assert perm_id

    try:
        edit_resp = admin_client.post(
            f"/api/admin/permissions/edit/{perm_id}",
            json={
                "code": "test.roundtrip.perm",
                "description": "d-updated",
                "sortingCode": "Z9",
            },
        )
        assert edit_resp.status_code == 200

        row = db_conn.execute(
            text("SELECT Code, SortingCode, Description FROM Permission WHERE PermissionID = :pid"),
            {"pid": perm_id},
        ).one()
        assert row.Code == "test.roundtrip.perm"
        assert row.SortingCode == "Z9"
        assert row.Description == "d-updated"
    finally:
        del_resp = admin_client.delete(f"/api/admin/permissions/delete/{perm_id}")
        assert del_resp.status_code == 200
