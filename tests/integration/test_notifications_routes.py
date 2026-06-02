"""Integration tests for nx_lib.views.notifications — 2 routes.

The Notifications table is absent from sql/test/schema.sql, so the route
bodies hit the except branch and return 500 JSON. The 401 branches are
exercised directly. The 200 happy path uses MagicMock on raw_connection.

Routes:
- GET  /api/notifications              get_notifications
- POST /api/notifications/mark_as_read mark_notifications_as_read
"""

from unittest.mock import MagicMock, patch


def test_get_notifications_anonymous_returns_401(client):
    resp = client.get("/api/notifications")
    assert resp.status_code == 401
    assert resp.is_json
    assert "error" in resp.get_json()


def test_get_notifications_authed_table_missing_returns_500(user_client):
    """Notifications table absent → except branch → 500."""
    resp = user_client.get("/api/notifications")
    assert resp.status_code == 500
    assert resp.is_json


def test_get_notifications_authed_with_mocked_db(user_client):
    """Mock the connection to return two rows; assert payload shape."""
    fake_cursor = MagicMock()
    fake_cursor.description = [
        ("NotificationID",),
        ("Message",),
        ("Link",),
        ("Icon",),
        ("Timestamp",),
    ]
    fake_cursor.fetchall.return_value = [
        (1, "Hello", "/x", "info", "2026-06-01T12:00"),
        (2, "Bye", "/y", "warn", "2026-06-01T11:00"),
    ]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor
    with patch("nx_lib.views.notifications.engine_nexora_db") as fake_engine:
        fake_engine.raw_connection.return_value = fake_conn
        resp = user_client.get("/api/notifications")
    assert resp.status_code == 200
    body = resp.get_json()
    assert isinstance(body, list)
    assert body[0]["NotificationID"] == 1
    assert body[1]["Message"] == "Bye"


def test_mark_as_read_anonymous_returns_401(client):
    resp = client.post("/api/notifications/mark_as_read", json={"ids": [1]})
    assert resp.status_code == 401


def test_mark_as_read_missing_ids_returns_400(user_client):
    resp = user_client.post("/api/notifications/mark_as_read", json={})
    assert resp.status_code == 400


def test_mark_as_read_non_list_ids_returns_400(user_client):
    resp = user_client.post("/api/notifications/mark_as_read", json={"ids": "not-a-list"})
    assert resp.status_code == 400


def test_mark_as_read_authed_table_missing_returns_500(user_client):
    resp = user_client.post("/api/notifications/mark_as_read", json={"ids": [1, 2]})
    assert resp.status_code == 500


def test_mark_as_read_authed_with_mocked_db(user_client):
    fake_cursor = MagicMock()
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor
    with patch("nx_lib.views.notifications.engine_nexora_db") as fake_engine:
        fake_engine.raw_connection.return_value = fake_conn
        resp = user_client.post("/api/notifications/mark_as_read", json={"ids": [1, 2, 3]})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
