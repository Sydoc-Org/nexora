"""E2E tests for /invoices.

admin@test.local has invoices.view (and the filter perms). Invoice rows come
from the external Bexio API, so TEST shows an empty table; tests assert the
filter form + action controls render and behave, not data rows.
"""

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.flaky_e2e
def test_invoices_renders(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/invoices")
    expect(page.locator('[data-testid="invoices-filter-form"]')).to_be_visible()
    assert "internal server error" not in page.content().lower()


@pytest.mark.flaky_e2e
def test_invoices_filter_controls_present(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/invoices")
    expect(page.locator('[data-testid="invoices-date-from"]')).to_be_visible()
    expect(page.locator('[data-testid="invoices-date-to"]')).to_be_visible()
    expect(page.locator('[data-testid="invoices-status-filter"]')).to_be_visible()
    expect(page.locator('[data-testid="invoices-export-csv"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_invoices_date_inputs_editable(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/invoices")
    page.fill('[data-testid="invoices-date-from"]', "2026-01-01")
    page.fill('[data-testid="invoices-date-to"]', "2026-12-31")
    expect(page.locator('[data-testid="invoices-date-from"]')).to_have_value("2026-01-01")
    expect(page.locator('[data-testid="invoices-date-to"]')).to_have_value("2026-12-31")


@pytest.mark.flaky_e2e
def test_invoices_reset_clears_query(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/invoices?status=Open")
    page.click('[data-testid="invoices-reset"]')
    page.wait_for_url("**/invoices**")
    # Reset returns to the invoices page (the form re-submits with empty values),
    # so the path is /invoices and the original status=Open filter is gone.
    assert page.url.split("?")[0].rstrip("/").endswith("/invoices")
    assert "status=Open" not in page.url
