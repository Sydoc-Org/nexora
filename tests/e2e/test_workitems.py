"""E2E tests for /workitems.

admin@test.local has workitems.view plus all filter perms. The workitem tables
are absent in TEST so the result table is empty; tests target the filter form,
the advanced-filter toggle and the export modal rather than data rows.
"""

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.flaky_e2e
def test_workitems_renders(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    expect(page.locator('[data-testid="workitems-filter-form"]')).to_be_visible()
    assert "internal server error" not in page.content().lower()


@pytest.mark.flaky_e2e
def test_workitems_filter_controls_present(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    expect(page.locator('[data-testid="workitems-search"]')).to_be_visible()
    expect(page.locator('[data-testid="workitems-status-filter"]')).to_be_visible()
    expect(page.locator('[data-testid="workitems-process-filter"]')).to_be_visible()
    expect(page.locator('[data-testid="workitems-per-page"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_workitems_toggle_advanced_reveals_date_range(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    page.click('[data-testid="workitems-toggle-advanced"]')
    expect(page.locator('[data-testid="workitems-start-date"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_workitems_export_csv_opens_modal(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    page.click('[data-testid="workitems-export-csv"]')
    expect(page.locator('[data-testid="workitems-close-export-modal"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_workitems_export_modal_closes(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    page.click('[data-testid="workitems-export-csv"]')
    close = page.locator('[data-testid="workitems-close-export-modal"]')
    expect(close).to_be_visible()
    close.click()
    expect(close).to_be_hidden()
