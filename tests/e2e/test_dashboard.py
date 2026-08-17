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
def test_dashboard_process_filter_opens_a_checkbox_menu(nexora_server, page):
    """The filter is a multi-select scope picker (issue #150), not a <select>:
    the menu is built client-side and holds one checkbox per allowed process
    plus the 'All Processes' row."""
    _login(page, nexora_server)
    expect(page.locator('[data-testid="dashboard-process-filter"]')).to_be_visible()
    menu = page.locator('[data-testid="dashboard-process-filter-menu"]')
    expect(menu).to_be_hidden()
    page.locator('[data-testid="dashboard-process-filter-btn"]').click()
    expect(menu).to_be_visible()
    assert menu.locator('input[type="checkbox"]').count() >= 1
    # Value stays on the hidden input the backend reads.
    assert page.locator('[data-testid="dashboard-process-filter-value"]').input_value() == "all"
