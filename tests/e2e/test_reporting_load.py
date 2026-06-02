"""E2E smoke for the Reporting saved-report load flow.

TestAdmin holds the reporting.* perms (sql/test/seed.sql) and the TEST schema
carries dbo.Reports (sql/test/schema.sql), so a report can be created via the
API and then loaded back through the UI. A SQL-kind report is used because it
restores fully without needing the Statistics DB (absent in TEST).
"""

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.goto(f"{base}/reporting")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.flaky_e2e
def test_saved_report_load_round_trip(nexora_server, page):
    _login(page, nexora_server)

    # The saved-report controls render.
    expect(page.locator('[data-testid="reporting-saved-reports"]')).to_be_visible()
    expect(page.locator('[data-testid="reporting-load"]')).to_be_visible()

    # Create a SQL report straight through the API (same session/cookies as the
    # page) to avoid driving the Save → prompt → alert dialog chain.
    token = page.evaluate("() => document.querySelector('meta[name=\"csrf-token\"]').content")
    resp = page.request.post(
        f"{nexora_server}/api/reporting/reports",
        headers={"X-CSRFToken": token, "Content-Type": "application/json"},
        data={
            "name": "E2E Load Report",
            "definition": {
                "kind": "sql",
                "target": "statistics",
                "sql": "SELECT 1 AS one",
                "title": "E2E Load Report",
            },
        },
    )
    assert resp.ok, resp.text()

    # Reload so the dropdown repopulates, then load the report through the UI.
    page.goto(f"{nexora_server}/reporting")
    page.wait_for_load_state("domcontentloaded")
    option = page.locator(
        '[data-testid="reporting-saved-reports"] option', has_text="E2E Load Report"
    ).first
    option.wait_for(state="attached")
    page.locator('[data-testid="reporting-saved-reports"]').select_option(
        label="E2E Load Report (SQL)"
    )
    page.locator('[data-testid="reporting-load"]').click()

    # The SQL editor is populated and the page switched to SQL mode.
    editor = page.locator('[data-testid="reporting-sql-editor"]')
    expect(editor).to_be_visible()
    expect(editor).to_have_value("SELECT 1 AS one")
    page.screenshot(path="var/screenshots/reporting_load_smoke.png")
