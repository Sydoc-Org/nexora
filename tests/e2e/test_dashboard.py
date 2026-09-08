"""E2E tests for /dashboard.

The dashboard is heavily JS-driven: the KPI strip and both charts hydrate from
XHR endpoints that hit tables absent in TEST (ProcessSources, t_WorkItems,
BacklogHistory). So these tests assert the page chrome renders and the
server-rendered controls (process filter, range control, view tabs) behave,
rather than data.
"""

import re

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


@pytest.mark.flaky_e2e
def test_dashboard_view_tabs_switch_the_chart_body(nexora_server, page):
    """The hourly chart is a tab on the main chart now, not its own card."""
    _login(page, nexora_server)
    tabs = page.locator('[data-testid="dashboard-view-tabs"]')
    expect(tabs).to_be_visible()
    expect(page.locator("#chart-body-time")).to_be_visible()
    tabs.locator('[data-view="hour"]').click()
    expect(page.locator("#chart-body-hour")).to_be_visible()
    expect(page.locator("#chart-body-time")).to_be_hidden()


@pytest.mark.flaky_e2e
def test_dashboard_range_control_marks_the_picked_window(nexora_server, page):
    """14 / 30 / 90-day segmented control; the picked window carries is-active."""
    _login(page, nexora_server)
    control = page.locator('[data-testid="dashboard-range"]')
    expect(control.locator(".nx-segmented__btn")).to_have_count(3)
    control.locator('[data-range="30"]').click()
    expect(control.locator('[data-range="30"]')).to_have_class(re.compile("is-active"))


@pytest.mark.flaky_e2e
def test_dashboard_has_no_card_frames_and_no_activity_feed(nexora_server, page):
    """Option 1a is borderless: no nx-card on the page, and the feed is gone."""
    _login(page, nexora_server)
    page.wait_for_load_state("domcontentloaded")
    assert page.locator("main .nx-card").count() == 0
    assert page.locator("#activity-feed").count() == 0
