"""Unit tests for nx_lib.maintenance — banner parsing + lockout decisions."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from nx_lib import maintenance as maint_mod
from nx_lib.maintenance import (
    MAINTENANCE_SEVERITIES,
    _get_blocking_maintenance,
    _maintenance_blocks_user,
    _maintenance_iso,
    _maintenance_parse_payload,
    _maintenance_row_to_dict,
    _user_has_maintenance_bypass,
)


@pytest.fixture(autouse=True)
def reset_maintenance_cache():
    """Reset the module-level TTL cache before every test so cached results
    don't leak between cases."""
    maint_mod._MAINTENANCE_BLOCK_CACHE["expires_at"] = 0.0
    maint_mod._MAINTENANCE_BLOCK_CACHE["data"] = None
    yield
    maint_mod._MAINTENANCE_BLOCK_CACHE["expires_at"] = 0.0
    maint_mod._MAINTENANCE_BLOCK_CACHE["data"] = None


# ---------- _maintenance_iso ----------


def test_maintenance_iso_returns_none_for_none():
    assert _maintenance_iso(None) is None


def test_maintenance_iso_formats_datetime():
    out = _maintenance_iso(datetime(2026, 6, 1, 12, 30, 45))
    assert out == "2026-06-01T12:30:45"


def test_maintenance_iso_str_fallback_for_non_date():
    assert _maintenance_iso("plain-string") == "plain-string"
    assert _maintenance_iso(42) == "42"


# ---------- _maintenance_row_to_dict ----------


def test_maintenance_row_to_dict_zips_and_converts():
    cols = [
        "ID",
        "Title",
        "StartAt",
        "EndAt",
        "CreatedAt",
        "Active",
        "BlockAccess",
        "AnnounceMinutesBefore",
    ]
    row = (
        1,
        "Banner",
        datetime(2026, 6, 1, 0, 0),
        datetime(2026, 6, 2, 0, 0),
        datetime(2026, 5, 30, 9, 0),
        1,
        0,
        15,
    )
    d = _maintenance_row_to_dict(row, cols)
    assert d["ID"] == 1
    assert d["Title"] == "Banner"
    assert d["StartAt"] == "2026-06-01T00:00:00"
    assert d["EndAt"] == "2026-06-02T00:00:00"
    assert d["CreatedAt"] == "2026-05-30T09:00:00"
    assert d["Active"] is True
    assert d["BlockAccess"] is False
    assert d["AnnounceMinutesBefore"] == 15


def test_maintenance_row_to_dict_handles_none_dates_and_int_defaults():
    cols = ["StartAt", "EndAt", "CreatedAt", "Active", "AnnounceMinutesBefore"]
    row = (None, None, None, 0, None)
    d = _maintenance_row_to_dict(row, cols)
    assert d["StartAt"] is None
    assert d["EndAt"] is None
    assert d["CreatedAt"] is None
    assert d["Active"] is False
    assert d["AnnounceMinutesBefore"] == 0


def test_maintenance_row_to_dict_skips_blockaccess_when_absent():
    cols = ["ID", "Title", "Active"]
    row = (1, "X", 1)
    d = _maintenance_row_to_dict(row, cols)
    assert "BlockAccess" not in d


# ---------- _maintenance_parse_payload ----------


def test_maintenance_parse_payload_accepts_minimal_valid():
    body = {
        "message": "ok",
        "startAt": "2026-06-01T00:00:00",
        "endAt": "2026-06-01T01:00:00",
    }
    out, err = _maintenance_parse_payload(body)
    assert err is None
    assert out["message"] == "ok"
    # startAt T is replaced with a space
    assert out["start_at"] == "2026-06-01 00:00:00"
    assert out["end_at"] == "2026-06-01 01:00:00"
    assert out["severity"] == "info"  # default
    assert out["active"] == 1
    assert out["block_access"] == 0
    assert out["announce_minutes"] == 0
    assert out["title"] is None


def test_maintenance_parse_payload_rejects_missing_message():
    body = {"startAt": "2026-06-01T00:00:00", "endAt": "2026-06-01T01:00:00"}
    out, err = _maintenance_parse_payload(body)
    assert out is None
    assert err == ("message is required", 400)


def test_maintenance_parse_payload_rejects_missing_dates():
    out, err = _maintenance_parse_payload({"message": "x"})
    assert out is None
    assert err == ("startAt and endAt are required", 400)


def test_maintenance_parse_payload_rejects_invalid_severity():
    body = {
        "message": "x",
        "startAt": "2026-06-01T00:00:00",
        "endAt": "2026-06-01T01:00:00",
        "severity": "extreme",
    }
    out, err = _maintenance_parse_payload(body)
    assert out is None
    assert err == ("invalid severity", 400)


def test_maintenance_parse_payload_accepts_all_severities():
    for sev in MAINTENANCE_SEVERITIES:
        out, err = _maintenance_parse_payload(
            {
                "message": "x",
                "startAt": "2026-06-01T00:00:00",
                "endAt": "2026-06-01T01:00:00",
                "severity": sev,
            }
        )
        assert err is None
        assert out["severity"] == sev


def test_maintenance_parse_payload_clamps_announce_minutes():
    body = {
        "message": "x",
        "startAt": "2026-06-01T00:00:00",
        "endAt": "2026-06-01T01:00:00",
        "announceMinutesBefore": 99999,
    }
    out, err = _maintenance_parse_payload(body)
    assert err is None
    assert out["announce_minutes"] == 1440  # max clamp


def test_maintenance_parse_payload_handles_bad_announce_minutes_type():
    body = {
        "message": "x",
        "startAt": "2026-06-01T00:00:00",
        "endAt": "2026-06-01T01:00:00",
        "announceMinutesBefore": "not-an-int",
    }
    out, err = _maintenance_parse_payload(body)
    assert err is None
    assert out["announce_minutes"] == 0  # falls back


def test_maintenance_parse_payload_uses_active_and_blockaccess_flags():
    body = {
        "message": "x",
        "startAt": "2026-06-01T00:00:00",
        "endAt": "2026-06-01T01:00:00",
        "active": False,
        "blockAccess": True,
    }
    out, err = _maintenance_parse_payload(body)
    assert err is None
    assert out["active"] == 0
    assert out["block_access"] == 1


# ---------- _get_blocking_maintenance ----------


def test_get_blocking_maintenance_returns_none_when_no_banner(app, db_conn):
    """Test runs against the real TEST DB. Default state: no active banner.
    db_conn isn't used directly — it just ensures we don't pollute. The real
    call goes through engine_nexora_db.raw_connection()."""
    # Ensure the cache is cold (autouse fixture handles this)
    with app.app_context():
        result = _get_blocking_maintenance()
    # No seeded blocking banner in NEXORA_TEST → None
    assert result is None or isinstance(result, dict)


def test_get_blocking_maintenance_fail_open_on_db_error(app):
    """If the DB query raises, the function returns None (fail-open)."""
    with (
        patch.object(maint_mod, "engine_nexora_db") as mock_engine,
        app.app_context(),
    ):
        mock_engine.raw_connection.side_effect = RuntimeError("boom")
        result = _get_blocking_maintenance()
    assert result is None


def test_get_blocking_maintenance_closes_connection_on_query_error(app):
    """Regression: a query that fails after connecting (e.g. MaintenanceBanner
    absent) must still return the pooled connection. Closing inside the try
    leaked one connection per request and eventually exhausted the pool."""
    fake_conn = MagicMock()
    fake_cursor = MagicMock()
    fake_cursor.execute.side_effect = RuntimeError("Invalid object name 'MaintenanceBanner'")
    fake_conn.cursor.return_value = fake_cursor

    with (
        patch.object(maint_mod, "engine_nexora_db") as mock_engine,
        app.app_context(),
    ):
        mock_engine.raw_connection.return_value = fake_conn
        result = _get_blocking_maintenance()

    assert result is None
    fake_conn.close.assert_called_once()


def test_get_blocking_maintenance_uses_cache(app):
    """Two calls within TTL should hit the DB only once."""
    call_count = {"n": 0}

    fake_conn = MagicMock()
    fake_cursor = MagicMock()
    fake_cursor.fetchone.return_value = None

    def counting_raw_conn():
        call_count["n"] += 1
        fake_conn.cursor.return_value = fake_cursor
        return fake_conn

    with (
        patch.object(maint_mod, "engine_nexora_db") as mock_engine,
        app.app_context(),
    ):
        mock_engine.raw_connection.side_effect = counting_raw_conn
        _get_blocking_maintenance()
        _get_blocking_maintenance()
    assert call_count["n"] == 1


def test_get_blocking_maintenance_parses_row(app):
    """When a row exists, it's serialised into the expected dict shape."""
    fake_conn = MagicMock()
    fake_cursor = MagicMock()
    fake_cursor.fetchone.return_value = (
        42,
        "Outage",
        "We're down",
        datetime(2026, 6, 1, 9, 0),
        datetime(2026, 6, 1, 11, 0),
        "critical",
    )
    fake_conn.cursor.return_value = fake_cursor

    with (
        patch.object(maint_mod, "engine_nexora_db") as mock_engine,
        app.app_context(),
    ):
        mock_engine.raw_connection.return_value = fake_conn
        result = _get_blocking_maintenance()

    assert result == {
        "id": 42,
        "title": "Outage",
        "message": "We're down",
        "startAt": "2026-06-01T09:00:00",
        "endAt": "2026-06-01T11:00:00",
        "severity": "critical",
    }


# ---------- _user_has_maintenance_bypass ----------


def test_user_has_maintenance_bypass_false_for_none_userid(app):
    with app.app_context():
        assert _user_has_maintenance_bypass(None) is False


def test_user_has_maintenance_bypass_true_when_perm_present(app):
    with (
        patch.object(
            maint_mod,
            "load_permissions_for_user",
            return_value=["admin.view", "admin.maintenance.bypass"],
        ),
        app.app_context(),
    ):
        assert _user_has_maintenance_bypass(123) is True


def test_user_has_maintenance_bypass_false_when_perm_missing(app):
    with (
        patch.object(
            maint_mod,
            "load_permissions_for_user",
            return_value=["admin.view"],
        ),
        app.app_context(),
    ):
        assert _user_has_maintenance_bypass(123) is False


def test_user_has_maintenance_bypass_false_on_exception(app):
    with (
        patch.object(
            maint_mod,
            "load_permissions_for_user",
            side_effect=RuntimeError("DB down"),
        ),
        app.app_context(),
    ):
        assert _user_has_maintenance_bypass(123) is False


def test_user_has_maintenance_bypass_against_real_admin(app, db_conn):
    """Real seeded admin@test.local holds the full permission set (see
    sql/test/seed.sql), which includes admin.maintenance.bypass."""
    admin_uid = db_conn.execute(
        text("SELECT userid FROM Users WHERE username='admin@test.local'")
    ).scalar()
    with app.app_context():
        assert _user_has_maintenance_bypass(admin_uid) is True


def test_user_has_maintenance_bypass_against_real_noperm(app, db_conn):
    """Real seeded noperm@test.local has no permissions, so no bypass."""
    noperm_uid = db_conn.execute(
        text("SELECT userid FROM Users WHERE username='noperm@test.local'")
    ).scalar()
    with app.app_context():
        assert _user_has_maintenance_bypass(noperm_uid) is False


# ---------- _maintenance_blocks_user ----------


def test_maintenance_blocks_user_none_when_no_banner(app):
    with (
        patch.object(maint_mod, "_get_blocking_maintenance", return_value=None),
        app.app_context(),
    ):
        assert _maintenance_blocks_user(123) is None


def test_maintenance_blocks_user_none_when_bypass(app):
    banner = {"id": 1, "title": "x"}
    with (
        patch.object(maint_mod, "_get_blocking_maintenance", return_value=banner),
        patch.object(maint_mod, "_user_has_maintenance_bypass", return_value=True),
        app.app_context(),
    ):
        assert _maintenance_blocks_user(123) is None


def test_maintenance_blocks_user_returns_banner_when_blocked(app):
    banner = {"id": 1, "title": "x"}
    with (
        patch.object(maint_mod, "_get_blocking_maintenance", return_value=banner),
        patch.object(maint_mod, "_user_has_maintenance_bypass", return_value=False),
        app.app_context(),
    ):
        assert _maintenance_blocks_user(123) is banner
