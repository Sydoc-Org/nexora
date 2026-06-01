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


def test_create_app_registers_invoices_endpoint():
    app = create_app()
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    assert "invoices" in endpoints


def test_create_app_registers_chat_endpoint():
    app = create_app()
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    assert "chat_page" in endpoints


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
        "init_2FA",
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
        "get_all_tags",
        "invoices",
        "api_invoices",
        "chat_page",
        "jdvance",
        "maintenance_page",
    }
    missing = critical - endpoints
    assert not missing, f"Critical route endpoints missing: {sorted(missing)}"
