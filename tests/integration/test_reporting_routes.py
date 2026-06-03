"""Integration tests for nx_lib.views.reporting.

Seed test users have no reporting.* perms, so guarded routes return 403 (authed)
or redirect (anon). Endpoints whose first DB hit needs tables absent from the
TEST schema are asserted as (200, 500) to stay forward-compatible, mirroring the
dashboard route tests.
"""

from datetime import datetime, time
from unittest.mock import patch

from nx_lib.db import engine_nexora_db


def test_reporting_anonymous_redirects_to_login(client):
    resp = client.get("/reporting", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_reporting_without_perm_returns_403(user_client):
    resp = user_client.get("/reporting")
    assert resp.status_code == 403


def test_sources_without_perm_returns_403(user_client):
    resp = user_client.get("/api/reporting/sources")
    assert resp.status_code == 403


def test_run_invalid_json_returns_400_or_403(user_client):
    # no perm → 403 before body parsing
    resp = user_client.post("/api/reporting/run", data="not-json")
    assert resp.status_code in (400, 403)


def test_run_anonymous_redirects(client):
    resp = client.post("/api/reporting/run", json={}, follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_reports_list_without_perm_403(user_client):
    resp = user_client.get("/api/reporting/reports")
    assert resp.status_code == 403


def test_sql_run_without_perm_403(user_client):
    resp = user_client.post(
        "/api/reporting/sql/run", json={"target": "statistics", "sql": "SELECT 1"}
    )
    assert resp.status_code in (400, 403)


def test_sql_run_anonymous_redirects(client):
    resp = client.post(
        "/api/reporting/sql/run",
        json={"target": "statistics", "sql": "SELECT 1"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 401)


def test_sql_ack_without_perm_403(user_client):
    resp = user_client.post("/api/reporting/sql/ack", json={})
    assert resp.status_code in (400, 403)


def test_sql_run_octopus_target_without_perm_403(user_client):
    # The base reporting.sql.run gate blocks before the Octopus target check.
    resp = user_client.post("/api/reporting/sql/run", json={"target": "octopus", "sql": "SELECT 1"})
    assert resp.status_code in (400, 403)


def test_sql_run_serializes_binary_and_time_cells(user_client):
    """A result row with bytes (varbinary/rowversion) or datetime.time must
    serialize as strings, not crash jsonify with a 500 (regression)."""
    columns = [{"field": "Data", "header": "Data"}, {"field": "T", "header": "T"}]
    rows = [[b"\x00\x01\x02", time(13, 45, 0)]]
    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.views.reporting._has_acked", return_value=True),
        patch("nx_lib.views.reporting._authorize_sql_target"),
        patch("nx_lib.views.reporting._run_sql", return_value=(columns, rows)),
    ):
        resp = user_client.post(
            "/api/reporting/sql/run", json={"target": "statistics", "sql": "SELECT 1"}
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["rows"][0][0] == "0x000102"
    assert data["rows"][0][1] == "13:45:00"


# --- /api/reporting/export/grid (client-supplied grid; no DB access) ---


def test_export_grid_without_perm_403(user_client):
    resp = user_client.post(
        "/api/reporting/export/grid",
        json={"columns": [{"header": "A"}], "rows": [["x"]]},
    )
    assert resp.status_code == 403


def test_export_grid_anonymous_redirects(client):
    resp = client.post(
        "/api/reporting/export/grid",
        json={"columns": [{"header": "A"}], "rows": [["x"]]},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 401)


def test_export_grid_xlsx_ok(admin_client):
    # TestAdmin holds reporting.export; the endpoint serializes without touching a DB.
    resp = admin_client.post(
        "/api/reporting/export/grid",
        json={
            "columns": [{"header": "Client"}, {"header": "Total"}],
            "rows": [["Acme", 1700.5], ["Globex", 5940.25]],
            "title": "Pivot",
            "format": "xlsx",
        },
    )
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["Content-Type"]
    assert "Pivot.xlsx" in resp.headers["Content-Disposition"]


def test_export_grid_csv_ok_has_bom(admin_client):
    resp = admin_client.post(
        "/api/reporting/export/grid",
        json={
            "columns": [{"header": "Client"}, {"header": "Total"}],
            "rows": [["Acme", 1700.5]],
            "title": "Pivot",
            "format": "csv",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/csv")
    assert "Pivot.csv" in resp.headers["Content-Disposition"]
    assert resp.data[:3] == b"\xef\xbb\xbf"  # UTF-8 BOM
    assert b"Client,Total" in resp.data


def test_export_grid_bad_body_400(admin_client):
    resp = admin_client.post("/api/reporting/export/grid", json={"columns": "nope"})
    assert resp.status_code == 400


# --- Cross-user sharing (A2). TestAdmin owns the reports it creates. ---


def _create_report(admin_client, name="Share Test"):
    resp = admin_client.post(
        "/api/reporting/reports",
        json={
            "name": name,
            "definition": {
                "kind": "sql",
                "target": "statistics",
                "sql": "SELECT 1 AS one",
                "title": name,
            },
        },
    )
    assert resp.status_code == 200, resp.data
    return resp.get_json()["id"]


def test_shares_get_owner_default_private(admin_client):
    rid = _create_report(admin_client)
    try:
        resp = admin_client.get(f"/api/reporting/reports/{rid}/shares")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["visibility"] == "private"
        assert data["shares"] == []
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid}")


def test_set_visibility_shared_reflects_in_list(admin_client):
    rid = _create_report(admin_client)
    try:
        resp = admin_client.post(
            f"/api/reporting/reports/{rid}/shares", json={"visibility": "shared"}
        )
        assert resp.status_code == 200
        assert resp.get_json()["visibility"] == "shared"
        lst = admin_client.get("/api/reporting/reports").get_json()
        row = next(r for r in lst if r["id"] == rid)
        assert row["visibility"] == "shared" and row["owned"] is True
        bad = admin_client.post(f"/api/reporting/reports/{rid}/shares", json={"visibility": "nope"})
        assert bad.status_code == 400
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid}")


def test_add_and_remove_user_share(admin_client):
    rid = _create_report(admin_client)
    try:
        resp = admin_client.post(
            f"/api/reporting/reports/{rid}/shares",
            json={"user": "user@test.local", "canEdit": True},
        )
        assert resp.status_code == 200
        shares = resp.get_json()["shares"]
        assert len(shares) == 1 and shares[0]["canEdit"] is True
        uid = shares[0]["userId"]
        rem = admin_client.delete(f"/api/reporting/reports/{rid}/shares/{uid}")
        assert rem.status_code == 200
        assert rem.get_json()["shares"] == []
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid}")


def test_share_unknown_user_404(admin_client):
    rid = _create_report(admin_client)
    try:
        resp = admin_client.post(
            f"/api/reporting/reports/{rid}/shares", json={"user": "ghost@nowhere.invalid"}
        )
        assert resp.status_code == 404
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid}")


def test_share_with_self_400(admin_client):
    rid = _create_report(admin_client)
    try:
        resp = admin_client.post(
            f"/api/reporting/reports/{rid}/shares", json={"user": "admin@test.local"}
        )
        assert resp.status_code == 400
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid}")


def test_shares_endpoints_without_perm_403(user_client):
    assert user_client.get("/api/reporting/reports/1/shares").status_code == 403
    assert (
        user_client.post(
            "/api/reporting/reports/1/shares", json={"visibility": "shared"}
        ).status_code
        == 403
    )


# --- Scheduled report delivery (A1) ---


def test_schedules_without_perm_403(user_client):
    assert user_client.get("/api/reporting/reports/1/schedules").status_code == 403
    assert (
        user_client.post(
            "/api/reporting/reports/1/schedules",
            json={"frequency": "daily", "hour": 6, "recipients": "a@x.com"},
        ).status_code
        == 403
    )


def test_schedule_crud(admin_client):
    rid = _create_report(admin_client)
    try:
        assert admin_client.get(f"/api/reporting/reports/{rid}/schedules").get_json() == []
        cr = admin_client.post(
            f"/api/reporting/reports/{rid}/schedules",
            json={
                "frequency": "daily",
                "hour": 6,
                "minute": 0,
                "format": "xlsx",
                "recipients": "a@x.com, b@y.com",
            },
        )
        assert cr.status_code == 200, cr.data
        sid = cr.get_json()["id"]
        lst = admin_client.get(f"/api/reporting/reports/{rid}/schedules").get_json()
        assert len(lst) == 1 and lst[0]["frequency"] == "daily" and lst[0]["nextRunAt"]

        up = admin_client.put(
            f"/api/reporting/reports/{rid}/schedules/{sid}",
            json={
                "frequency": "weekly",
                "hour": 7,
                "minute": 30,
                "weekday": 1,
                "format": "csv",
                "recipients": "c@z.com",
                "enabled": False,
            },
        )
        assert up.status_code == 200
        lst = admin_client.get(f"/api/reporting/reports/{rid}/schedules").get_json()
        assert lst[0]["frequency"] == "weekly" and lst[0]["enabled"] is False
        assert lst[0]["weekday"] == 1 and lst[0]["format"] == "csv"

        assert (
            admin_client.delete(f"/api/reporting/reports/{rid}/schedules/{sid}").status_code == 200
        )
        assert admin_client.get(f"/api/reporting/reports/{rid}/schedules").get_json() == []
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid}")


def test_schedule_validation_400(admin_client):
    rid = _create_report(admin_client)
    try:
        assert (
            admin_client.post(
                f"/api/reporting/reports/{rid}/schedules",
                json={"frequency": "daily", "hour": 6, "recipients": "bad"},
            ).status_code
            == 400
        )
        assert (
            admin_client.post(
                f"/api/reporting/reports/{rid}/schedules",
                json={"frequency": "weekly", "hour": 6, "recipients": "a@x.com"},
            ).status_code
            == 400
        )
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid}")


def test_runner_dry_run_processes_due_table_report(admin_client):
    # End-to-end: register a 'table' source over Users, save a report on it, queue
    # a past-due schedule, then run the runner in dry-run (builds the report via
    # the session-independent runner; no mail, no NextRunAt advance).
    from ops import run_scheduled_reports

    src = admin_client.post(
        "/api/reporting/admin/sources",
        json={
            "code": "sched_users",
            "kind": "curated",
            "label": "Sched Users",
            "permission": "reporting.source.docprocessing",
            "provider": "table",
            "engine": "nexora",
            "baseObject": "dbo.Users",
            "columns": [
                {
                    "field": "username",
                    "label": "Username",
                    "type": "string",
                    "filterable": True,
                    "sortable": True,
                }
            ],
            "enabled": True,
            "sortOrder": 15,
        },
    )
    src_id = src.get_json()["id"]
    rep = admin_client.post(
        "/api/reporting/reports",
        json={
            "name": "Sched Users Report",
            "definition": {
                "schemaVersion": 1,
                "source": "sched_users",
                "visualization": "table",
                "title": "Sched Users Report",
                "columns": [{"field": "username"}],
                "filters": [],
                "sort": [],
                "scope": {},
                "rowLimit": 10,
            },
        },
    )
    rid = rep.get_json()["id"]
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT userID FROM dbo.Users WHERE username = 'admin@test.local'")
        owner = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO dbo.ReportSchedules (ReportID, OwnerUserID, Recipients, Format, "
            "Frequency, Hour, Minute, Enabled, NextRunAt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (rid, owner, "a@x.com", "csv", "daily", 6, 0, 1, datetime(2000, 1, 1)),
        )
        conn.commit()

        failed = run_scheduled_reports.run_once(dry_run=True)
        assert failed == 0
    finally:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.ReportSchedules WHERE ReportID = ?", (rid,))
        conn.commit()
        conn.close()
        admin_client.delete(f"/api/reporting/reports/{rid}")
        admin_client.delete(f"/api/reporting/admin/sources/{src_id}")


# --- Seeded curated 'table' sources (A5 Generali, A6 Workitems) ---


def test_generali_and_workitems_sources_registered(admin_client):
    # TestAdmin holds both source permissions (seed); listing builds the field
    # catalog from ColumnsJSON with no Generali/Octopus DB access.
    by_id = {s["id"]: s for s in admin_client.get("/api/reporting/sources").get_json()}
    assert by_id["generali_pdqm"]["kind"] == "curated"
    assert any(f["field"] == "ParentCategory" for f in by_id["generali_pdqm"]["fields"])
    assert by_id["workitems"]["kind"] == "curated"
    assert any(f["field"] == "WorkItemIdentifier" for f in by_id["workitems"]["fields"])


# --- Source registry admin (A3) ---


def test_admin_sources_page_without_perm_403(user_client):
    assert user_client.get("/reporting/sources").status_code == 403
    assert user_client.get("/api/reporting/admin/sources").status_code == 403


def test_admin_sources_page_renders(admin_client):
    resp = admin_client.get("/reporting/sources")
    assert resp.status_code == 200
    assert b"reporting-sources-admin" in resp.data


def test_admin_sources_list_has_defaults(admin_client):
    data = admin_client.get("/api/reporting/admin/sources").get_json()
    assert any(s["id"] == "docprocessing" for s in data["defaults"])
    assert isinstance(data["rows"], list)


def test_admin_sources_crud(admin_client):
    create = admin_client.post(
        "/api/reporting/admin/sources",
        json={
            "code": "crud_src",
            "kind": "sql",
            "label": "CRUD Source",
            "permission": "reporting.sql.run",
            "target": "statistics",
            "enabled": True,
            "sortOrder": 50,
        },
    )
    assert create.status_code == 200, create.data
    sid = create.get_json()["id"]
    try:
        rows = admin_client.get("/api/reporting/admin/sources").get_json()["rows"]
        assert any(r["id"] == sid and r["label"] == "CRUD Source" for r in rows)
        upd = admin_client.put(
            f"/api/reporting/admin/sources/{sid}",
            json={
                "code": "crud_src",
                "kind": "sql",
                "label": "Renamed",
                "permission": "reporting.sql.run",
                "target": "statistics",
                "enabled": False,
                "sortOrder": 50,
            },
        )
        assert upd.status_code == 200
        rows = admin_client.get("/api/reporting/admin/sources").get_json()["rows"]
        assert next(r for r in rows if r["id"] == sid)["label"] == "Renamed"
    finally:
        dele = admin_client.delete(f"/api/reporting/admin/sources/{sid}")
        assert dele.status_code == 200
    assert admin_client.delete(f"/api/reporting/admin/sources/{sid}").status_code == 404


def test_admin_sources_validation(admin_client):
    base = {"kind": "curated", "label": "L", "permission": "reporting.view"}
    assert (
        admin_client.post(
            "/api/reporting/admin/sources", json={**base, "code": "bad code!"}
        ).status_code
        == 400
    )
    assert (
        admin_client.post(
            "/api/reporting/admin/sources",
            json={"code": "ok1", "label": "L", "permission": "p", "kind": "weird"},
        ).status_code
        == 400
    )
    assert (
        admin_client.post(
            "/api/reporting/admin/sources",
            json={**base, "code": "ok2", "columns": "{not json"},
        ).status_code
        == 400
    )


def test_table_source_end_to_end(admin_client):
    # Register a generic 'table' source over the TEST Users table and run it.
    create = admin_client.post(
        "/api/reporting/admin/sources",
        json={
            "code": "e2e_users",
            "kind": "curated",
            "label": "E2E Users",
            "permission": "reporting.source.docprocessing",
            "provider": "table",
            "engine": "nexora",
            "baseObject": "dbo.Users",
            "columns": [
                {
                    "field": "username",
                    "label": "Username",
                    "type": "string",
                    "filterable": True,
                    "sortable": True,
                },
                {
                    "field": "Email",
                    "label": "Email",
                    "type": "string",
                    "filterable": True,
                    "sortable": True,
                },
            ],
            "enabled": True,
            "sortOrder": 10,
        },
    )
    assert create.status_code == 200, create.data
    sid = create.get_json()["id"]
    try:
        srcs = admin_client.get("/api/reporting/sources").get_json()
        entry = next((s for s in srcs if s["id"] == "e2e_users"), None)
        assert entry is not None and any(f["field"] == "username" for f in entry["fields"])

        run = admin_client.post(
            "/api/reporting/run",
            json={
                "schemaVersion": 1,
                "source": "e2e_users",
                "visualization": "table",
                "title": "Users",
                "columns": [{"field": "username"}, {"field": "Email"}],
                "filters": [{"field": "username", "op": "contains", "value": "admin"}],
                "sort": [{"field": "username", "dir": "asc"}],
                "scope": {},
                "rowLimit": 100,
            },
        )
        assert run.status_code == 200, run.data
        data = run.get_json()
        assert data["rowCount"] >= 1
        flat = [c for row in data["rows"] for c in row]
        assert "admin@test.local" in flat
    finally:
        admin_client.delete(f"/api/reporting/admin/sources/{sid}")


def test_shared_report_visible_to_non_owner(admin_client):
    # A report owned by user@test.local (a different user), marked 'shared', must
    # appear in admin's list (owned=false) and be loadable, but not manageable.
    conn = engine_nexora_db.raw_connection()
    rid = None
    try:
        cur = conn.cursor()
        cur.execute("SELECT userID FROM dbo.Users WHERE username = 'user@test.local'")
        other = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO dbo.Reports (OwnerUserID, Name, DefinitionJSON, Visibility) "
            "OUTPUT INSERTED.ReportID VALUES (?, ?, ?, 'shared')",
            (
                other,
                "Shared By Other",
                '{"kind":"sql","target":"statistics","sql":"SELECT 1 AS one",'
                '"title":"Shared By Other"}',
            ),
        )
        rid = cur.fetchone()[0]
        conn.commit()

        lst = admin_client.get("/api/reporting/reports").get_json()
        row = next((r for r in lst if r["id"] == rid), None)
        assert row is not None
        assert row["owned"] is False and row["canEdit"] is False
        assert row["ownerName"] == "user@test.local"
        got = admin_client.get(f"/api/reporting/reports/{rid}")
        assert got.status_code == 200 and got.get_json()["owned"] is False
        # Not the owner => cannot manage its shares.
        assert admin_client.get(f"/api/reporting/reports/{rid}/shares").status_code == 404
    finally:
        if rid is not None:
            cur = conn.cursor()
            cur.execute("DELETE FROM dbo.ReportShares WHERE ReportID = ?", (rid,))
            cur.execute("DELETE FROM dbo.Reports WHERE ReportID = ?", (rid,))
            conn.commit()
        conn.close()
