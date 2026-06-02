"""Unit tests for nx_lib.notifications — create_notification DB writer.

NEXORA_TEST does not include the Notifications table (it's a subset schema —
see sql/test/schema.sql). Until that bootstrap is extended, these tests mock
engine_nexora_db at the connection level and verify the SQL we'd send."""

from unittest.mock import MagicMock, patch

from nx_lib import notifications as notif_mod
from nx_lib.notifications import create_notification


def _make_mocked_engine():
    """Returns (patch_target_engine, fake_cursor) bound through MagicMock."""
    fake_cursor = MagicMock()
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor
    return fake_conn, fake_cursor


def test_create_notification_executes_insert_with_all_params(app):
    fake_conn, fake_cursor = _make_mocked_engine()
    with (
        patch.object(notif_mod, "engine_nexora_db") as mock_engine,
        app.app_context(),
    ):
        mock_engine.raw_connection.return_value = fake_conn
        create_notification(
            1000,
            "Hello",
            link="/dashboard",
            icon="fa-check",
        )

    # Inspect the INSERT SQL and bound parameters
    fake_cursor.execute.assert_called_once()
    sql, params = fake_cursor.execute.call_args.args
    assert "INSERT INTO Notifications" in sql
    assert "UserID" in sql and "Message" in sql and "Link" in sql and "Icon" in sql
    assert params == (1000, "Hello", "/dashboard", "fa-check")
    fake_conn.commit.assert_called_once()
    fake_cursor.close.assert_called_once()
    fake_conn.close.assert_called_once()


def test_create_notification_uses_default_icon(app):
    fake_conn, fake_cursor = _make_mocked_engine()
    with (
        patch.object(notif_mod, "engine_nexora_db") as mock_engine,
        app.app_context(),
    ):
        mock_engine.raw_connection.return_value = fake_conn
        create_notification(1000, "Hello")

    sql, params = fake_cursor.execute.call_args.args
    assert params == (1000, "Hello", None, "fa-info-circle")


def test_create_notification_accepts_none_link(app):
    fake_conn, fake_cursor = _make_mocked_engine()
    with (
        patch.object(notif_mod, "engine_nexora_db") as mock_engine,
        app.app_context(),
    ):
        mock_engine.raw_connection.return_value = fake_conn
        create_notification(1000, "msg", link=None, icon="fa-bell")

    _, params = fake_cursor.execute.call_args.args
    assert params == (1000, "msg", None, "fa-bell")


def test_create_notification_swallows_raw_connection_error(app):
    """raw_connection() raises — the function logs and returns without
    propagating."""
    with (
        patch.object(notif_mod, "engine_nexora_db") as mock_engine,
        app.app_context(),
    ):
        mock_engine.raw_connection.side_effect = RuntimeError("DB down")
        create_notification(1, "msg")  # must not raise


def test_create_notification_swallows_execute_error_and_cleans_up(app):
    """If cursor.execute() raises, the finally block still closes cursor + conn."""
    fake_conn, fake_cursor = _make_mocked_engine()
    fake_cursor.execute.side_effect = RuntimeError("constraint violation")

    with (
        patch.object(notif_mod, "engine_nexora_db") as mock_engine,
        app.app_context(),
    ):
        mock_engine.raw_connection.return_value = fake_conn
        create_notification(1, "msg")  # must not raise

    # commit must NOT have been called (execute raised first)
    fake_conn.commit.assert_not_called()
    # finally closed both
    fake_cursor.close.assert_called_once()
    fake_conn.close.assert_called_once()


def test_create_notification_swallows_cursor_error_after_conn(app):
    """If conn.cursor() raises, finally must skip cursor.close() but still
    close the connection."""
    fake_conn = MagicMock()
    fake_conn.cursor.side_effect = RuntimeError("cursor failed")

    with (
        patch.object(notif_mod, "engine_nexora_db") as mock_engine,
        app.app_context(),
    ):
        mock_engine.raw_connection.return_value = fake_conn
        create_notification(1, "msg")  # must not raise

    fake_conn.close.assert_called_once()
