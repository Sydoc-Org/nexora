"""E2E smoke tests for /reporting.

Requires ENVIRONMENT=TEST with reporting.* permissions seeded (sql/test/seed.sql
grants every permission to TestAdmin, which includes reporting.view and
reporting.source.docprocessing). The page chrome and source select are asserted;
data rows are not checked because the statistics DB is absent in TEST.
"""

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    # admin@test.local lands on /admin (adminPagePerm fires first in
    # startpage_redirect_to), so navigate explicitly to /reporting.
    page.goto(f"{base}/reporting?tab=advanced")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.flaky_e2e
def test_reporting_page_loads(nexora_server, page):
    _login(page, nexora_server)
    expect(page.locator('[data-testid="reporting-page"]')).to_be_visible()
    page.screenshot(path="var/screenshots/reporting_page.png")


@pytest.mark.flaky_e2e
def test_reporting_source_select_present(nexora_server, page):
    _login(page, nexora_server)
    source_select = page.locator('[data-testid="reporting-source-select"]')
    expect(source_select).to_be_visible()
    assert source_select.evaluate("el => el.tagName.toLowerCase()") == "select"


@pytest.mark.flaky_e2e
def test_reporting_does_not_error(nexora_server, page):
    _login(page, nexora_server)
    page.wait_for_load_state("domcontentloaded")
    assert "internal server error" not in page.content().lower()
