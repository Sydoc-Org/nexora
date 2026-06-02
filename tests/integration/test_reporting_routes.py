"""Integration tests for nx_lib.views.reporting.

Seed test users have no reporting.* perms, so guarded routes return 403 (authed)
or redirect (anon). Endpoints whose first DB hit needs tables absent from the
TEST schema are asserted as (200, 500) to stay forward-compatible, mirroring the
dashboard route tests.
"""


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
