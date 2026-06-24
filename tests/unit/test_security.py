"""Unit tests for nx_lib.security — pure logic, no DB."""

import uuid
from datetime import date
from unittest.mock import patch

from sqlalchemy import text
from werkzeug.exceptions import HTTPException
from werkzeug.wrappers import Response

from nx_lib.db import engine_nexora_db
from nx_lib.security import (
    PermissionDenied,
    _check_add_deadline,
    _get_add_min_date,
    _revoke_session_by_id,
    has_permission,
    load_permissions_for_user,
    page_visibility,
    require_any_permission,
    require_permission,
    startpage_redirect_to,
)

# ---------------------------------------------------------------------------
# has_permission (pre-existing tests)
# ---------------------------------------------------------------------------


def test_has_permission_returns_true_when_present():
    with patch("nx_lib.security.session", {"permissions": ["admin.view"]}):
        assert has_permission("admin.view") is True


def test_has_permission_returns_false_when_missing():
    with patch("nx_lib.security.session", {"permissions": ["dashboard.view"]}):
        assert has_permission("admin.delete") is False


def test_has_permission_returns_false_when_no_permissions_in_session():
    with patch("nx_lib.security.session", {}):
        assert has_permission("admin.view") is False


# ---------------------------------------------------------------------------
# PermissionDenied
# ---------------------------------------------------------------------------


def test_permission_denied_is_http_exception_subclass():
    assert issubclass(PermissionDenied, HTTPException)


def test_permission_denied_code_is_403():
    assert PermissionDenied.code == 403


# ---------------------------------------------------------------------------
# load_permissions_for_user — real DB via db_conn fixture
# ---------------------------------------------------------------------------


def test_load_permissions_for_user_returns_expected_codes(db_conn):
    row = db_conn.execute(
        text("SELECT userid FROM Users WHERE username = 'admin@test.local'")
    ).fetchone()
    perms = load_permissions_for_user(row.userid)
    assert "admin.view" in perms
    assert "admin.users.manage" in perms
    assert "dashboard.view" in perms


def test_load_permissions_for_user_returns_empty_for_noperm(db_conn):
    row = db_conn.execute(
        text("SELECT userid FROM Users WHERE username = 'noperm@test.local'")
    ).fetchone()
    perms = load_permissions_for_user(row.userid)
    assert perms == []


def test_load_permissions_for_user_unknown_id_returns_empty():
    perms = load_permissions_for_user(-999)
    assert perms == []


# ---------------------------------------------------------------------------
# _get_add_min_date — boundary cases
# ---------------------------------------------------------------------------


def test_get_add_min_date_on_day_1_returns_prev_month_first():
    with patch("nx_lib.security.date") as mock_date:
        mock_date.today.return_value = date(2026, 3, 1)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        assert _get_add_min_date() == date(2026, 2, 1)


def test_get_add_min_date_on_day_3_still_prev_month():
    with patch("nx_lib.security.date") as mock_date:
        mock_date.today.return_value = date(2026, 3, 3)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        assert _get_add_min_date() == date(2026, 2, 1)


def test_get_add_min_date_on_day_4_returns_current_month():
    with patch("nx_lib.security.date") as mock_date:
        mock_date.today.return_value = date(2026, 3, 4)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        assert _get_add_min_date() == date(2026, 3, 1)


def test_get_add_min_date_in_january_wraps_to_prev_dec():
    with patch("nx_lib.security.date") as mock_date:
        mock_date.today.return_value = date(2026, 1, 2)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        assert _get_add_min_date() == date(2025, 12, 1)


# ---------------------------------------------------------------------------
# _check_add_deadline
# ---------------------------------------------------------------------------


def test_check_add_deadline_valid_date_in_range_passes(fake_session):
    # Use a far-future date so it always passes regardless of when the test runs.
    fake_session["permissions"] = []
    today = date.today()
    far_future = date(today.year + 1, today.month, 15).isoformat()
    assert _check_add_deadline(far_future, "some.bypass.perm") is None


def test_check_add_deadline_too_old_returns_error(fake_session):
    fake_session["permissions"] = []
    # Use a clearly-old date (year 2000) — guaranteed to be outside any window.
    result = _check_add_deadline("2000-01-15", "some.bypass.perm")
    assert result == "Date is outside the allowed entry window"


def test_check_add_deadline_bypass_perm_short_circuits(fake_session):
    fake_session["permissions"] = ["maintenance.bypass"]
    # Even ancient date passes when bypass perm is held.
    assert _check_add_deadline("1999-01-01", "maintenance.bypass") is None


def test_check_add_deadline_invalid_date_string_returns_error(fake_session):
    fake_session["permissions"] = []
    assert _check_add_deadline("not-a-date", "some.bypass.perm") == "Invalid date"


def test_check_add_deadline_none_input_returns_invalid_date(fake_session):
    fake_session["permissions"] = []
    # TypeError path of the try/except.
    assert _check_add_deadline(None, "some.bypass.perm") == "Invalid date"


# ---------------------------------------------------------------------------
# require_permission decorator
# ---------------------------------------------------------------------------


def test_require_permission_returns_wrapped_value_when_perm_present(fake_session, auth_app_ctx):
    fake_session["username"] = "admin@test.local"
    fake_session["permissions"] = ["admin.view"]

    @require_permission("admin.view")
    def view():
        return "ok"

    assert view() == "ok"


def test_require_permission_raises_when_perm_missing(fake_session, auth_app_ctx):
    fake_session["username"] = "user@test.local"
    fake_session["permissions"] = ["dashboard.view"]

    @require_permission("admin.view")
    def view():
        return "ok"

    try:
        view()
    except PermissionDenied:
        return
    raise AssertionError("expected PermissionDenied to be raised")


def test_require_permission_redirects_when_no_username(fake_session, app):
    # No username key → 302 redirect to /login. url_for() needs a request
    # context (or SERVER_NAME) to build the URL, so use test_request_context.
    fake_session["permissions"] = ["admin.view"]

    @require_permission("admin.view")
    def view():
        return "ok"

    with app.test_request_context("/"):
        response = view()
    assert isinstance(response, Response)
    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")


# ---------------------------------------------------------------------------
# require_any_permission decorator
# ---------------------------------------------------------------------------


def test_require_any_permission_accepts_when_first_code_present(fake_session, auth_app_ctx):
    fake_session["username"] = "u"
    fake_session["permissions"] = ["admin.view"]

    @require_any_permission("admin.view", "dashboard.view")
    def view():
        return "ok"

    assert view() == "ok"


def test_require_any_permission_accepts_when_second_code_present(fake_session, auth_app_ctx):
    fake_session["username"] = "u"
    fake_session["permissions"] = ["dashboard.view"]

    @require_any_permission("admin.view", "dashboard.view")
    def view():
        return "ok"

    assert view() == "ok"


def test_require_any_permission_rejects_when_neither_present(fake_session, auth_app_ctx):
    fake_session["username"] = "u"
    fake_session["permissions"] = ["chat.view"]

    @require_any_permission("admin.view", "dashboard.view")
    def view():
        return "ok"

    try:
        view()
    except PermissionDenied:
        return
    raise AssertionError("expected PermissionDenied to be raised")


def test_require_any_permission_redirects_when_no_username(fake_session, app):
    fake_session["permissions"] = ["admin.view"]

    @require_any_permission("admin.view", "dashboard.view")
    def view():
        return "ok"

    with app.test_request_context("/"):
        response = view()
    assert isinstance(response, Response)
    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")


# ---------------------------------------------------------------------------
# startpage_redirect_to
# ---------------------------------------------------------------------------


def _all_false_page_v():
    return {
        "dashboardPagePerm": False,
        "reportingPagePerm": False,
        "workitemsPagePerm": False,
        "invoicesPagePerm": False,
        "generaliPagePerm": False,
        "generaliDocumentsPerm": False,
        "generaliReportingPerm": False,
        "generaliAdditionalServicesPerm": False,
        "generaliBaseServicesPerm": False,
        "generaliProjectManagementPerm": False,
        "generaliPDQMPerm": False,
        "chatPagePerm": False,
        "adminPagePerm": False,
    }


def test_startpage_redirect_to_picks_first_truthy_perm():
    pv = _all_false_page_v()
    pv["workitemsPagePerm"] = True
    pv["invoicesPagePerm"] = True
    assert startpage_redirect_to(pv) == "workitems_overview"


def test_startpage_redirect_to_dashboard_wins_over_workitems():
    pv = _all_false_page_v()
    pv["dashboardPagePerm"] = True
    pv["workitemsPagePerm"] = True
    assert startpage_redirect_to(pv) == "dashboard"


def test_startpage_redirect_to_admin_only_falls_through():
    pv = _all_false_page_v()
    pv["adminPagePerm"] = True
    assert startpage_redirect_to(pv) == "admin_dashboard"


def test_startpage_redirect_to_returns_login_when_no_perms():
    pv = _all_false_page_v()
    assert startpage_redirect_to(pv) == "login"


# ---------------------------------------------------------------------------
# page_visibility — all 18 keys
# ---------------------------------------------------------------------------


def test_page_visibility_returns_all_18_keys_with_no_perms(fake_session):
    fake_session["permissions"] = []
    pv = page_visibility()
    expected_keys = {
        "adminPagePerm",
        "dashboardPagePerm",
        "reportingPagePerm",
        "workitemsPagePerm",
        "preparedDocsPagePerm",
        "invoicesPagePerm",
        "chatPagePerm",
        "generaliPagePerm",
        "generaliDocumentsPerm",
        "generaliReportingPerm",
        "generaliAdditionalServicesPerm",
        "generaliBaseServicesPerm",
        "generaliProjectManagementPerm",
        "generaliPDQMPerm",
        "generaliImportStatusPerm",
        "adminMaintenanceViewPerm",
        "adminMaintenanceEditPerm",
        "adminMaintenanceBypassPerm",
    }
    assert set(pv.keys()) == expected_keys
    assert all(v is False for v in pv.values())


def test_page_visibility_reflects_selected_perms(fake_session):
    fake_session["permissions"] = [
        "admin.view",
        "dashboard.view",
        "generali.pdqm.view",
        "admin.maintenance.bypass",
    ]
    pv = page_visibility()
    assert pv["adminPagePerm"] is True
    assert pv["dashboardPagePerm"] is True
    assert pv["generaliPDQMPerm"] is True
    assert pv["adminMaintenanceBypassPerm"] is True
    # Spot-check that unselected perms are still False.
    assert pv["workitemsPagePerm"] is False
    assert pv["invoicesPagePerm"] is False
    assert pv["chatPagePerm"] is False
    assert pv["adminMaintenanceEditPerm"] is False


# ---------------------------------------------------------------------------
# _revoke_session_by_id — real DB via raw_connection
# ---------------------------------------------------------------------------
# Note: _revoke_session_by_id uses engine_nexora_db.raw_connection() and
# commits its own transaction, so the db_conn fixture's rollback won't undo
# it. We use raw_connection here too — insert a row with a uniquely generated
# SID, run the function, then clean up in a finally block.


def _insert_active_session(sid, user_id):
    conn = engine_nexora_db.raw_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO ActiveSessions (SessionID, UserID) VALUES (?, ?)",
            (sid, int(user_id)),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _active_session_exists(sid):
    conn = engine_nexora_db.raw_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM ActiveSessions WHERE SessionID = ?", (sid,))
        return cur.fetchone() is not None
    finally:
        cur.close()
        conn.close()


def _delete_active_session(sid):
    conn = engine_nexora_db.raw_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM ActiveSessions WHERE SessionID = ?", (sid,))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def test_revoke_session_by_id_returns_true_when_row_exists(db_conn, auth_app_ctx):
    sid = f"test-revoke-{uuid.uuid4().hex}"
    user_row = db_conn.execute(
        text("SELECT userid FROM Users WHERE username = 'admin@test.local'")
    ).fetchone()
    _insert_active_session(sid, user_row.userid)
    try:
        assert _active_session_exists(sid) is True
        result = _revoke_session_by_id(sid)
        assert result is True
        assert _active_session_exists(sid) is False
    finally:
        # Defensive cleanup in case the assertion failed before the delete.
        _delete_active_session(sid)


def test_revoke_session_by_id_returns_false_when_sid_absent(auth_app_ctx):
    sid = f"never-existed-{uuid.uuid4().hex}"
    result = _revoke_session_by_id(sid)
    assert result is False


# ---------------------------------------------------------------------------
# Task 8: page_visibility includes reportingPagePerm
# ---------------------------------------------------------------------------


def test_page_visibility_includes_reporting(app):
    from nx_lib.security import page_visibility

    with app.test_request_context():
        from flask import session

        session["permissions"] = ["reporting.view"]
        pv = page_visibility()
        assert pv["reportingPagePerm"] is True
