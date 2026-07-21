"""Integration tests for nx_lib.views.core — root, jdvance, maintenance, heartbeat.

The MaintenanceBanner table is intentionally absent from sql/test/schema.sql.
- maintenance_page() relies on _get_blocking_maintenance() which fails open
  (returns None) when the table is missing, so the page still renders with HTTP 200.
- api_maintenance_active() catches the SQL error and emits HTTP 500.

The 200 path for api_maintenance_active is covered by mocking the connection.

Routes covered:
- GET /                       (index)
- GET /jdvance                (jd.view-guarded)
- GET /maintenance            (maintenance_page)
- GET /api/maintenance/active (api_maintenance_active)
- GET /api/session/heartbeat  (session_heartbeat)
"""

from unittest.mock import MagicMock, patch


def test_index_unauthenticated_renders_landing(client):
    resp = client.get("/", follow_redirects=False)
    # Anonymous: renders hero.html with HTTP 200 (no <form> on the landing page —
    # the login form is on /login).
    assert resp.status_code == 200


def test_index_authenticated_redirects_to_dashboard(user_client):
    resp = user_client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/dashboard" in resp.headers.get("Location", "")


def test_index_without_dashboard_view_redirects_to_permitted_page(noperm_client, monkeypatch):
    """A user without dashboard.view but with workitems.view must land on their
    permitted page (e.g. /workitems), not hit a 403 via a hardcoded /dashboard
    redirect. Mirrors the startpage_redirect_to(page_visibility()) idiom used
    everywhere else post-auth (see nx_lib/views/auth.py)."""
    monkeypatch.setattr(
        "nx_lib.security.has_permission",
        lambda code: code == "workitems.view",
    )
    resp = noperm_client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/workitems" in location
    assert "/dashboard" not in location


def test_jdvance_anonymous_redirects_to_login(client):
    resp = client.get("/jdvance", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_jdvance_without_perm_returns_403(user_client):
    """Seed users have no jd.view permission — require_permission raises 403."""
    resp = user_client.get("/jdvance")
    assert resp.status_code == 403


def test_jdvance_with_perm_renders(user_client, monkeypatch):
    """Inject jd.view via monkeypatch since the before_request hook reloads
    permissions from the DB on every request and would clobber a session inject."""
    monkeypatch.setattr("nx_lib.security.has_permission", lambda code: True)
    resp = user_client.get("/jdvance")
    assert resp.status_code == 200


def test_maintenance_page_renders_when_no_blocker(client, monkeypatch):
    """MaintenanceBanner table missing → _get_blocking_maintenance returns None →
    page renders with 200."""
    monkeypatch.setattr("nx_lib.views.core._get_blocking_maintenance", lambda: None)
    resp = client.get("/maintenance")
    assert resp.status_code == 200


def test_maintenance_page_returns_503_when_blocking(client, monkeypatch):
    """When a blocking banner is active, the page renders with HTTP 503."""
    monkeypatch.setattr(
        "nx_lib.views.core._get_blocking_maintenance",
        lambda: {
            "id": 1,
            "title": "Down for upgrade",
            "message": "Back at 18:00",
            "startAt": "2026-06-01T17:00:00",
            "endAt": "2026-06-01T18:00:00",
            "severity": "critical",
        },
    )
    resp = client.get("/maintenance")
    assert resp.status_code == 503


def test_api_maintenance_active_returns_500_when_table_missing(client):
    """No MaintenanceBanner in TEST schema → except branch returns 500 JSON."""
    resp = client.get("/api/maintenance/active")
    assert resp.status_code == 500
    assert resp.is_json
    body = resp.get_json()
    assert body.get("success") is False


def test_api_maintenance_active_returns_active_banner(client):
    """Mock the raw_connection to return an active banner row."""
    fake_cursor = MagicMock()
    fake_cursor.fetchone.return_value = (
        42,
        "Hello",
        "Scheduled work",
        "2026-06-01 12:00:00",
        "2026-06-01 13:00:00",
        "info",
    )
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor
    with patch("nx_lib.views.core.engine_nexora_db") as fake_engine:
        fake_engine.raw_connection.return_value = fake_conn
        resp = client.get("/api/maintenance/active")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["banner"]["id"] == 42
    assert body["banner"]["title"] == "Hello"
    assert body["banner"]["upcoming"] is False


def test_api_maintenance_active_returns_upcoming_banner(client):
    """First query (active) returns None; second query (upcoming) returns a row."""
    fake_cursor = MagicMock()
    fake_cursor.fetchone.side_effect = [
        None,  # first SELECT (active) — nothing
        (
            7,
            "Heads up",
            "Window opens at 14:00",
            "2026-06-01 14:00:00",
            "2026-06-01 15:00:00",
            "warning",
        ),
    ]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor
    with patch("nx_lib.views.core.engine_nexora_db") as fake_engine:
        fake_engine.raw_connection.return_value = fake_conn
        resp = client.get("/api/maintenance/active")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["banner"]["id"] == 7
    assert body["banner"]["upcoming"] is True


def test_api_maintenance_active_returns_null_banner_when_no_rows(client):
    """Both queries return None → success: True, banner: None."""
    fake_cursor = MagicMock()
    fake_cursor.fetchone.return_value = None
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor
    with patch("nx_lib.views.core.engine_nexora_db") as fake_engine:
        fake_engine.raw_connection.return_value = fake_conn
        resp = client.get("/api/maintenance/active")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["banner"] is None


def test_session_heartbeat_returns_401_when_anonymous(client):
    resp = client.get("/api/session/heartbeat")
    assert resp.status_code == 401
    body = resp.get_json()
    assert body["ok"] is False
    assert body["reason"] == "unauthenticated"


def test_session_heartbeat_returns_200_when_authed(user_client):
    resp = user_client.get("/api/session/heartbeat")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
