"""E2E tests for misc pages: hero landing, jdvance, maintenance, 404 handler."""

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.flaky_e2e
def test_hero_renders_anonymous(nexora_server, page):
    page.goto(f"{nexora_server}/")
    # index() renders hero.html when there is no session.
    expect(page.locator('[data-testid="hero-access-portal-cta"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_hero_access_portal_navigates_to_login(nexora_server, page):
    page.goto(f"{nexora_server}/")
    page.click('[data-testid="hero-access-portal-cta"]')
    page.wait_for_url("**/login")
    expect(page.locator('[data-testid="login-form"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_maintenance_page_renders(nexora_server, page):
    page.goto(f"{nexora_server}/maintenance")
    expect(page.locator('[data-testid="maintenance-login"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_maintenance_login_link_navigates(nexora_server, page):
    page.goto(f"{nexora_server}/maintenance")
    page.click('[data-testid="maintenance-login"]')
    page.wait_for_url("**/login")


@pytest.mark.flaky_e2e
def test_jdvance_renders_for_permitted_user(nexora_server, page):
    _login(page, nexora_server)
    resp = page.goto(f"{nexora_server}/jdvance")
    page.wait_for_load_state("domcontentloaded")
    assert resp is not None and resp.status == 200
    assert "/jdvance" in page.url
    assert "internal server error" not in page.content().lower()


@pytest.mark.flaky_e2e
def test_404_page_renders_with_home_link(nexora_server, page):
    resp = page.goto(f"{nexora_server}/this-route-does-not-exist")
    assert resp is not None and resp.status == 404
    expect(page.locator('[data-testid="error-404-home"]')).to_be_visible()
