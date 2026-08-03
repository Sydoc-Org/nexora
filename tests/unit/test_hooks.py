"""Unit tests for nx_lib.hooks — request lifecycle + error handlers."""

import time
from unittest.mock import MagicMock, patch

from flask import request, session

from nx_lib import hooks as hooks_mod
from nx_lib.hooks import (
    _enforce_active_session,
    _enforce_maintenance_lockout,
    _forbidden_page,
    _handle_permission_denied,
    _inject_current_lang,
    _internal_error,
    _load_user_locale,
    _log_every_request,
    _page_not_found,
    _reload_user_permissions,
    _start_timer,
    _utility_processor,
    get_ip,
)
from nx_lib.security import PermissionDenied

# ---------- get_ip ----------


def test_get_ip_uses_remote_addr_with_no_xff(app):
    with app.test_request_context("/", environ_overrides={"REMOTE_ADDR": "10.0.0.1"}):
        assert get_ip() == "10.0.0.1"


def test_get_ip_prefers_x_forwarded_for(app):
    with app.test_request_context("/", headers={"X-Forwarded-For": "1.2.3.4"}):
        assert get_ip() == "1.2.3.4"


def test_get_ip_uses_first_in_xff_list(app):
    with app.test_request_context(
        "/",
        headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"},
    ):
        assert get_ip() == "1.2.3.4"


def test_get_ip_returns_unknown_when_nothing_set(app):
    with app.test_request_context(
        "/",
        environ_overrides={"REMOTE_ADDR": ""},
    ):
        assert get_ip() == "Unknown"


# ---------- _start_timer ----------


def test_start_timer_sets_request_start_time(app):
    with app.test_request_context("/"):
        before = time.time()
        _start_timer()
        after = time.time()
        assert before <= request.start_time <= after


# ---------- _enforce_active_session ----------


def test_enforce_active_session_skips_static(app):
    with app.test_request_context("/static/x.css"):
        assert _enforce_active_session() is None


def test_enforce_active_session_skips_login(app):
    with app.test_request_context("/login"):
        assert _enforce_active_session() is None


def test_enforce_active_session_skips_when_no_userid(app):
    with app.test_request_context("/dashboard"):
        assert _enforce_active_session() is None


def test_enforce_active_session_skips_when_no_sid(app):
    with app.test_request_context("/dashboard"):
        session["userid"] = 1
        # No sid set — function should return None silently
        assert _enforce_active_session() is None


def test_enforce_active_session_passes_when_row_present(app):
    fake_cursor = MagicMock()
    fake_cursor.rowcount = 1
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    with app.test_request_context("/dashboard"):
        session["userid"] = 1
        session["_dev_sid"] = "sid-123"
        with patch.object(hooks_mod, "engine_nexora_db") as mock_engine:
            mock_engine.raw_connection.return_value = fake_conn
            assert _enforce_active_session() is None
        # Session retained
        assert "userid" in session


def test_enforce_active_session_clears_and_redirects_html(app):
    fake_cursor = MagicMock()
    fake_cursor.rowcount = 0  # row missing → revoked
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    with app.test_request_context("/dashboard"):
        session["userid"] = 1
        session["_dev_sid"] = "sid-revoked"
        with patch.object(hooks_mod, "engine_nexora_db") as mock_engine:
            mock_engine.raw_connection.return_value = fake_conn
            resp = _enforce_active_session()
        assert resp is not None
        assert "userid" not in session


def test_enforce_active_session_returns_json_for_api(app):
    fake_cursor = MagicMock()
    fake_cursor.rowcount = 0
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    with app.test_request_context("/api/foo"):
        session["userid"] = 1
        session["_dev_sid"] = "sid-revoked"
        with patch.object(hooks_mod, "engine_nexora_db") as mock_engine:
            mock_engine.raw_connection.return_value = fake_conn
            resp, status = _enforce_active_session()
        assert status == 401
        assert b"revoked" in resp.get_data()


def test_enforce_active_session_fails_open_on_db_error(app):
    with app.test_request_context("/dashboard"):
        session["userid"] = 1
        session["_dev_sid"] = "sid-x"
        with patch.object(hooks_mod, "engine_nexora_db") as mock_engine:
            mock_engine.raw_connection.side_effect = RuntimeError("boom")
            assert _enforce_active_session() is None
        # Session retained — fail-open
        assert "userid" in session


# ---------- _reload_user_permissions ----------


def test_reload_user_permissions_skips_static(app):
    with app.test_request_context("/static/x.css"):
        # No-op, no DB call
        _reload_user_permissions()


def test_reload_user_permissions_no_session_user(app):
    with app.test_request_context("/dashboard"):
        # No userid — nothing happens
        _reload_user_permissions()


def test_reload_user_permissions_loads_perms(app):
    with app.test_request_context("/dashboard"):
        session["userid"] = 42
        with patch.object(
            hooks_mod,
            "load_permissions_for_user",
            return_value=["a", "b"],
        ):
            _reload_user_permissions()
        assert session["permissions"] == ["a", "b"]


def test_reload_user_permissions_swallows_error(app):
    with app.test_request_context("/dashboard"):
        session["userid"] = 42
        with patch.object(
            hooks_mod,
            "load_permissions_for_user",
            side_effect=RuntimeError("DB"),
        ):
            _reload_user_permissions()  # must not raise


# ---------- _load_user_locale ----------


def test_load_user_locale_skips_when_no_userid(app):
    with app.test_request_context("/"):
        _load_user_locale()


def test_load_user_locale_skips_when_already_set(app):
    with app.test_request_context("/"):
        session["userid"] = 1
        session["locale"] = "de"
        _load_user_locale()
        # Should NOT call DB; locale unchanged
        assert session["locale"] == "de"


def test_load_user_locale_loads_from_db(app):
    fake_cursor = MagicMock()
    fake_cursor.fetchone.return_value = ("fr",)
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    with app.test_request_context("/"):
        session["userid"] = 1
        with patch.object(hooks_mod, "engine_nexora_db") as mock_engine:
            mock_engine.raw_connection.return_value = fake_conn
            _load_user_locale()
        assert session["locale"] == "fr"


def test_load_user_locale_ignores_unsupported(app):
    fake_cursor = MagicMock()
    fake_cursor.fetchone.return_value = ("xx",)  # unsupported locale
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    with app.test_request_context("/"):
        session["userid"] = 1
        with patch.object(hooks_mod, "engine_nexora_db") as mock_engine:
            mock_engine.raw_connection.return_value = fake_conn
            _load_user_locale()
        assert "locale" not in session


def test_load_user_locale_swallows_error(app):
    with app.test_request_context("/"):
        session["userid"] = 1
        with patch.object(hooks_mod, "engine_nexora_db") as mock_engine:
            mock_engine.raw_connection.side_effect = RuntimeError("DB")
            _load_user_locale()  # must not raise


# ---------- _enforce_maintenance_lockout ----------


def test_enforce_maintenance_lockout_skips_skip_path(app):
    with app.test_request_context("/login"):
        assert _enforce_maintenance_lockout() is None


def test_enforce_maintenance_lockout_no_banner_passes(app):
    with (
        app.test_request_context("/dashboard"),
        patch.object(hooks_mod, "_get_blocking_maintenance", return_value=None),
    ):
        assert _enforce_maintenance_lockout() is None


def test_enforce_maintenance_lockout_bypass_perm_passes(app):
    with (
        app.test_request_context("/dashboard"),
        patch.object(
            hooks_mod,
            "_get_blocking_maintenance",
            return_value={"id": 1, "title": "x"},
        ),
    ):
        session["permissions"] = ["admin.maintenance.bypass"]
        assert _enforce_maintenance_lockout() is None


def test_enforce_maintenance_lockout_bypass_perm_passes_mixed_case(app):
    """Routed through has_permission() (Task 3), so a mixed-case permission
    string stored in the session (e.g. from a differently-cased DB seed)
    still grants the bypass instead of forcing the user out."""
    with (
        app.test_request_context("/dashboard"),
        patch.object(
            hooks_mod,
            "_get_blocking_maintenance",
            return_value={"id": 1, "title": "x"},
        ),
    ):
        session["permissions"] = ["Admin.Maintenance.Bypass"]
        assert _enforce_maintenance_lockout() is None


def test_enforce_maintenance_lockout_mid_login_bypass(app):
    with (
        app.test_request_context("/dashboard"),
        patch.object(
            hooks_mod,
            "_get_blocking_maintenance",
            return_value={"id": 1, "title": "x"},
        ),
        patch.object(
            hooks_mod,
            "_user_has_maintenance_bypass",
            return_value=True,
        ),
    ):
        session["pre_2fa_userid"] = 42
        assert _enforce_maintenance_lockout() is None


def test_enforce_maintenance_lockout_api_returns_json_503(app):
    banner = {"id": 1, "title": "x", "message": "down"}
    with (
        app.test_request_context("/api/foo"),
        patch.object(
            hooks_mod,
            "_get_blocking_maintenance",
            return_value=banner,
        ),
        patch.object(
            hooks_mod,
            "_user_has_maintenance_bypass",
            return_value=False,
        ),
    ):
        session["userid"] = 1
        session["permissions"] = []
        resp = _enforce_maintenance_lockout()
        assert resp is not None
        body, status = resp
        assert status == 503
        assert b"Maintenance" in body.get_data()
        # Session cleared
        assert "userid" not in session


def test_enforce_maintenance_lockout_html_returns_template_503(app):
    banner = {
        "id": 1,
        "title": "x",
        "message": "down",
        "startAt": "2026-06-01T00:00:00",
        "endAt": "2026-06-01T01:00:00",
        "severity": "warning",
    }
    with (
        app.test_request_context("/dashboard"),
        patch.object(
            hooks_mod,
            "_get_blocking_maintenance",
            return_value=banner,
        ),
        patch.object(
            hooks_mod,
            "_user_has_maintenance_bypass",
            return_value=False,
        ),
    ):
        session["userid"] = 1
        session["permissions"] = []
        resp = _enforce_maintenance_lockout()
        assert resp is not None
        body, status = resp
        assert status == 503


# ---------- _log_every_request ----------


def test_log_every_request_skips_static(app):
    fake_response = MagicMock(status_code=200)
    with app.test_request_context("/static/x.css"):
        result = _log_every_request(fake_response)
    assert result is fake_response


def test_log_every_request_writes_csv_row(app, tmp_path, monkeypatch):
    """Redirect logs to a tmp dir + run a fake request through the hook."""
    fake_paths = MagicMock()
    fake_paths.logs = tmp_path
    monkeypatch.setattr(hooks_mod, "PATHS", fake_paths)

    fake_response = MagicMock(status_code=200)
    with app.test_request_context("/dashboard"):
        request.start_time = time.time() - 0.05
        session["userid"] = 1
        session["username"] = "u"
        result = _log_every_request(fake_response)
    assert result is fake_response

    # Find any CSV files under tmp_path/user/
    import glob

    files = glob.glob(str(tmp_path / "user" / "**" / "*.csv"), recursive=True)
    assert len(files) >= 1
    with open(files[0], encoding="utf-8") as f:
        body = f.read()
    assert "/dashboard" in body
    assert "200" in body


def test_log_every_request_swallows_io_error(app, monkeypatch):
    """If writing the CSV fails, the function logs and returns the response."""
    fake_paths = MagicMock()
    fake_paths.logs.__truediv__.side_effect = RuntimeError("permission denied")
    monkeypatch.setattr(hooks_mod, "PATHS", fake_paths)

    fake_response = MagicMock(status_code=200)
    with app.test_request_context("/dashboard"):
        request.start_time = time.time()
        result = _log_every_request(fake_response)
    assert result is fake_response


# ---------- error handlers ----------


def test_page_not_found_returns_404(app):
    with app.test_request_context("/missing"):
        body, status = _page_not_found(MagicMock())
        assert status == 404
        assert "<" in body.lower() or "html" in body.lower()


def test_internal_error_returns_500(app):
    with app.test_request_context("/"):
        body, status = _internal_error(MagicMock())
        assert status == 500


def test_forbidden_page_returns_403(app):
    with app.test_request_context("/"):
        body, status = _forbidden_page(MagicMock())
        assert status == 403


def test_handle_permission_denied_returns_403(app):
    with app.test_request_context("/"):
        body, status = _handle_permission_denied(PermissionDenied())
        assert status == 403


# ---------- context processors ----------


def test_inject_current_lang_returns_dict(app):
    with app.test_request_context("/"):
        ctx = _inject_current_lang()
        assert "current_lang" in ctx
        assert isinstance(ctx["current_lang"], str)


def test_utility_processor_exposes_helpers(app):
    with app.test_request_context("/"):
        ctx = _utility_processor()
        assert "has_permission" in ctx
        assert "get_user_icon_url" in ctx
        assert callable(ctx["has_permission"])
        assert callable(ctx["get_user_icon_url"])


# ---------- init_app ----------


def test_init_app_registers_before_request_hooks(app):
    """The session-scoped `app` fixture went through create_app which called
    hooks.init_app. Verify the before_request list includes our hooks."""
    before_names = {fn.__name__ for fns in app.before_request_funcs.values() for fn in fns}
    assert "_start_timer" in before_names
    assert "_enforce_active_session" in before_names
    assert "_reload_user_permissions" in before_names
    assert "_load_user_locale" in before_names
    assert "_enforce_maintenance_lockout" in before_names


def test_init_app_registers_after_request_hook(app):
    """Some after_request handlers may be functools.partial (e.g. from
    Flask-WTF CSRF) which lack __name__ — use getattr fallback."""
    after_names = set()
    for fns in app.after_request_funcs.values():
        for fn in fns:
            name = getattr(fn, "__name__", None) or getattr(fn, "func", None)
            if isinstance(name, str):
                after_names.add(name)
            elif name is not None:
                after_names.add(getattr(name, "__name__", repr(name)))
    assert "_log_every_request" in after_names


def test_init_app_registers_error_handlers(app):
    # error_handler_spec is indexed by blueprint key (None = app-wide)
    spec = app.error_handler_spec.get(None, {})
    # 403, 404, 500 codes registered
    assert spec.get(403) or any(403 in v for v in spec.values())
    assert spec.get(404) or any(404 in v for v in spec.values())
    assert spec.get(500) or any(500 in v for v in spec.values())


def test_init_app_registers_context_processors(app):
    # template_context_processors[None] is the app-wide list
    procs = app.template_context_processors[None]
    proc_names = {p.__name__ for p in procs}
    assert "_inject_current_lang" in proc_names
    assert "_utility_processor" in proc_names


# ---------- error handlers: /api/v1 JSON branch ----------


def test_page_not_found_api_v1_returns_json(app):
    with app.test_request_context("/api/v1/nope"):
        body, status = _page_not_found(MagicMock())
        assert status == 404
        assert body.get_json() == {"error": "Not found"}


def test_internal_error_api_v1_returns_json(app):
    with app.test_request_context("/api/v1/stats/today"):
        body, status = _internal_error(MagicMock())
        assert status == 500
        assert body.get_json() == {"error": "Internal server error"}


def test_forbidden_api_v1_returns_json(app):
    with app.test_request_context("/api/v1/stats/today"):
        body, status = _forbidden_page(MagicMock())
        assert status == 403
        assert body.get_json() == {"error": "Forbidden"}


def test_permission_denied_api_v1_returns_json(app):
    with app.test_request_context("/api/v1/stats/today"):
        body, status = _handle_permission_denied(PermissionDenied())
        assert status == 403
        assert body.get_json() == {"error": "Forbidden"}
