"""E2E tests for the shared header/sidebar (templates/_header.html + _header_js).

The header renders on every authenticated page. admin@test.local sees the admin
nav group; user@test.local does not (lacks admin.view), which is asserted here.
Real route paths come from register_routes (e.g. admin overview is /admin, not
/admin/dashboard).
"""

import re

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.wait_for_url("**/dashboard")


@pytest.mark.flaky_e2e
def test_header_logo_links_home(nexora_server, page):
    _login(page, nexora_server)
    page.click('[data-testid="nexora-logo-home"]')
    # Logged in, "/" redirects to the dashboard.
    page.wait_for_url("**/dashboard")


@pytest.mark.flaky_e2e
def test_header_profile_link_navigates(nexora_server, page):
    _login(page, nexora_server)
    page.click('[data-testid="header-profile-toggle"]')
    page.click('[data-testid="header-profile-link"]')
    page.wait_for_url("**/profile")


@pytest.mark.flaky_e2e
def test_header_logout_ends_session(nexora_server, page):
    _login(page, nexora_server)
    page.click('[data-testid="header-profile-toggle"]')
    page.click('[data-testid="header-logout-link"]')
    page.wait_for_load_state("domcontentloaded")
    assert "/dashboard" not in page.url
    # Session is gone: an auth-only page now bounces to login.
    page.goto(f"{nexora_server}/profile")
    page.wait_for_load_state("domcontentloaded")
    assert "/login" in page.url


@pytest.mark.flaky_e2e
def test_header_dark_mode_toggle(nexora_server, page):
    _login(page, nexora_server)
    before = page.evaluate("document.documentElement.classList.contains('dark')")
    page.click('[data-testid="header-dark-mode-toggle"]')
    after = page.evaluate("document.documentElement.classList.contains('dark')")
    assert before != after


@pytest.mark.flaky_e2e
def test_header_admin_nav_expands_and_navigates(nexora_server, page):
    _login(page, nexora_server)
    page.click('[data-testid="header-nav-admin-toggle"]')
    link = page.locator('[data-testid="header-nav-admin-organizations"]')
    expect(link).to_be_visible()
    link.click()
    page.wait_for_url("**/admin/organizations")


@pytest.mark.flaky_e2e
def test_header_admin_nav_hidden_for_plain_user(nexora_server, page):
    _login(page, nexora_server, who="user@test.local")
    # user@test.local lacks admin.view, so the admin nav group is not rendered.
    expect(page.locator('[data-testid="header-nav-admin-toggle"]')).to_have_count(0)


@pytest.mark.flaky_e2e
def test_header_notifications_toggle_opens_panel(nexora_server, page):
    _login(page, nexora_server)
    page.click('[data-testid="header-notifications-toggle"]')
    # Panel is toggled client-side; the Notifications table is absent in TEST so
    # the fetch may fail, but the panel element should still reveal.
    expect(page.locator("#notification-panel")).to_be_visible()


@pytest.mark.flaky_e2e
def test_header_burger_toggles_sidebar_on_mobile(nexora_server, page):
    page.set_viewport_size({"width": 390, "height": 844})
    _login(page, nexora_server)
    page.click('[data-testid="header-burger"]')
    expect(page.locator("#nexora-sidebar")).to_have_class(re.compile(r"\bopen\b"))
