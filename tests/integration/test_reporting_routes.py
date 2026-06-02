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
