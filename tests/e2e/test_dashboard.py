"""E2E tests for /dashboard.

The dashboard is heavily JS-driven: KPI cards, charts and the activity feed
hydrate from XHR endpoints that hit tables absent in TEST (Statconfig,
t_WorkItems). So these tests assert the page chrome renders and the one
server-rendered control (the process filter) is present, rather than data.
"""

import pytest
from playwright.sync_api import expect


def _login(page, base, who="user@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.wait_for_url("**/dashboard")


@pytest.mark.flaky_e2e
def test_dashboard_renders_for_user(nexora_server, page):
    _login(page, nexora_server)
    expect(page.locator('[data-testid="dashboard-process-filter"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_dashboard_does_not_error(nexora_server, page):
    _login(page, nexora_server)
    page.wait_for_load_state("domcontentloaded")
    assert "internal server error" not in page.content().lower()


@pytest.mark.flaky_e2e
def test_dashboard_process_filter_is_a_select(nexora_server, page):
    _login(page, nexora_server)
    select = page.locator('[data-testid="dashboard-process-filter"]')
    expect(select).to_be_visible()
    # A native <select> exposes options even before any data loads.
    assert select.evaluate("el => el.tagName.toLowerCase()") == "select"
