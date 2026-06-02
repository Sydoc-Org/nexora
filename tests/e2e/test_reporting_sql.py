"""E2E smoke for the Reporting live-SQL tab.

TestAdmin holds reporting.sql.run (sql/test/seed.sql), so the SQL tab enables.
The statistics DB is absent in TEST, so a real run returns 503 — only the UI
flow (toggle, editor, acknowledgment) is asserted here, mirroring
tests/e2e/test_reporting.py which does not assert data rows either.
"""

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.goto(f"{base}/reporting")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.flaky_e2e
def test_sql_tab_enables_and_acknowledges(nexora_server, page):
    _login(page, nexora_server)
    sql_btn = page.locator('[data-testid="reporting-mode-sql"]')
    expect(sql_btn).to_be_enabled()
    sql_btn.click()
    editor = page.locator('[data-testid="reporting-sql-editor"]')
    expect(editor).to_be_visible()
    editor.fill("SELECT 1 AS one")
    page.locator('[data-testid="reporting-run"]').click()
    accept = page.locator('[data-testid="reporting-sql-ack-accept"]')
    expect(accept).to_be_visible()
    accept.click()
    expect(page.locator('[data-testid="reporting-sql-ack"]')).to_be_hidden()
    page.screenshot(path="var/screenshots/reporting_sql_smoke.png")
