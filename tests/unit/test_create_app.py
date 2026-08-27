"""Smoke tests for nx_lib.create_app — Flask app factory."""

from flask import Flask

from nx_lib import create_app


def test_create_app_returns_flask_app():
    app = create_app()
    assert isinstance(app, Flask)


def test_create_app_has_secret_key():
    app = create_app()
    assert app.config.get("SECRET_KEY")
    assert isinstance(app.config["SECRET_KEY"], str | bytes)


def test_create_app_hardens_session_cookie_in_every_env():
    """Security #193: HttpOnly + SameSite + a body cap must apply even in a
    non-PROD (here: TEST) app -- a non-PROD instance is not guaranteed
    unreachable."""
    app = create_app()
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["MAX_CONTENT_LENGTH"] == 25 * 1024 * 1024


def test_create_app_sets_baseline_security_headers_in_every_env():
    """Security #193: clickjacking + MIME-sniff headers on responses even in a
    non-PROD app (PROD additionally layers the full Talisman CSP)."""
    app = create_app()
    resp = app.test_client().get("/login")
    assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"


def test_create_app_registers_login_endpoint():
    app = create_app()
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    assert "login" in endpoints


def test_create_app_registers_logout_endpoint():
    app = create_app()
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    assert "logout" in endpoints


def test_create_app_registers_verify_2fa_endpoint():
    app = create_app()
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    assert "verify_2fa" in endpoints


def test_create_app_registers_dashboard_endpoint():
    app = create_app()
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    assert "dashboard" in endpoints


def test_create_app_registers_admin_dashboard_endpoint():
    app = create_app()
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    assert "admin_dashboard" in endpoints


def test_create_app_registers_workitems_endpoint():
    app = create_app()
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    assert "workitems_overview" in endpoints


def test_create_app_registers_profile_endpoint():
    app = create_app()
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    assert "profile" in endpoints


def test_create_app_registers_generali_routes():
    app = create_app()
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    # Generali routes use various prefixes; at minimum one of these:
    assert any("generali" in e for e in endpoints)


def test_create_app_route_count_meets_minimum():
    """If any register_routes() call gets accidentally removed, the rule
    count will drop dramatically — catch that."""
    app = create_app()
    rule_count = sum(1 for _ in app.url_map.iter_rules())
    assert rule_count >= 90, (
        f"Only {rule_count} routes registered — a register_routes() call " "may have been removed."
    )


def test_create_app_static_endpoint_present():
    """Flask's built-in /static endpoint should always be there."""
    app = create_app()
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    assert "static" in endpoints


def test_create_app_endpoint_set_includes_expected_critical_set():
    """Hard-checks the critical endpoint set so regressions surface loud."""
    app = create_app()
    endpoints = {r.endpoint for r in app.url_map.iter_rules() if r.endpoint != "static"}
    critical = {
        "index",
        "login",
        "logout",
        "verify_2fa",
        "init_2fa",
        "init_reset",
        "forgot_password",
        "reset_password",
        "dev_login",
        "profile",
        "set_language",
        "dashboard",
        "admin_dashboard",
        "workitems_overview",
        "api_workitems",
        "jdvance",
        "maintenance_page",
    }
    missing = critical - endpoints
    assert not missing, f"Critical route endpoints missing: {sorted(missing)}"


# Full enumeration of non-generali route endpoints registered by each
# nx_lib/views/*.py register_routes(). Mirror exactly what the modules emit.
# Generali endpoints intentionally excluded — covered by the Generali plan.
EXPECTED_NON_GENERALI_ENDPOINTS = {
    # views/core.py
    "index",
    "jdvance",
    "maintenance_page",
    "api_maintenance_active",
    "session_heartbeat",
    # views/auth.py
    "init_2fa",
    "verify_2fa",
    "init_reset",
    "init_reset_password",
    "dev_login",
    "login",
    "logout",
    "forgot_password",
    "set_new_password",
    "reset_password",
    "request_password_reset",
    # views/profile.py
    "profile",
    "update_profile",
    "change_password",
    "set_language",
    # views/dashboard.py
    "dashboard_processed_over_time",
    "dashboard_kpi_stats",
    "dashboard_hourly_stats",
    "dashboard_avg_processing_time",
    "dashboard",
    "dashboard_set_filter",
    "api_recent_activity",
    # views/admin.py
    "admin_dashboard",
    "admin_organizations_view",
    "admin_add_organization",
    "admin_edit_organization",
    "admin_delete_organization",
    "api_admin_organizations_list",
    "admin_maintenance_view",
    "api_admin_maintenance_list",
    "api_admin_maintenance_add",
    "api_admin_maintenance_edit",
    "api_admin_maintenance_delete",
    "admin_logs_view",
    "api_admin_logs_search",
    "api_admin_logs_export",
    "admin_sessions_view",
    "admin_add_user",
    "admin_edit_user",
    "admin_user_detail",
    "api_admin_user_activity",
    "admin_delete_user",
    "admin_revoke_session",
    "admin_revoke_all_sessions",
    "api_admin_users_list",
    "admin_recent_logs",
    "admin_active_sessions",
    "admin_access_control",
    "get_users_admin_access_control",
    "get_profile_details",
    "save_access_profile",
    "get_user_overrides",
    "api_admin_user_effective_permissions",
    "save_user_overrides",
    "api_admin_permissions_list",
    "api_admin_permission_users",
    "api_admin_user_all_permissions",
    "api_admin_permission_add",
    "api_admin_permission_edit",
    "api_admin_permission_delete",
    # views/workitems.py
    "api_config_fields",
    "api_docfield_values",
    "api_workitems",
    "export_workitems_csv",
    "workitems_overview",
    "import_workitems",
    "api_get_media_info",
    "api_get_media_raw",
    "get_audithistory",
    "api_workitems_page_init",
}


def test_create_app_full_non_generali_endpoint_set_registered():
    """Phase 2 close-out: hard-assert the complete non-generali endpoint set.

    Catches any future register_routes() removal or rename in nx_lib/views/.
    Generali endpoints are excluded by name prefix — they're tracked by the
    separate Generali-phase-2 plan."""
    app = create_app()
    endpoints = {r.endpoint for r in app.url_map.iter_rules() if r.endpoint != "static"}
    # Filter out generali-prefixed endpoints from the live set to keep the
    # comparison apples-to-apples.
    non_generali = {e for e in endpoints if "generali" not in e}

    missing = EXPECTED_NON_GENERALI_ENDPOINTS - non_generali
    extra = non_generali - EXPECTED_NON_GENERALI_ENDPOINTS
    # `extra` is informational only — new routes are healthy. `missing` is the
    # regression signal.
    assert not missing, (
        f"register_routes() regression detected — these endpoints disappeared: "
        f"{sorted(missing)}. Extra (new) endpoints: {sorted(extra)}"
    )
