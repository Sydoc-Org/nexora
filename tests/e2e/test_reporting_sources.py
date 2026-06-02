"""E2E for the reporting source-registry admin page (A3).

TestAdmin holds reporting.admin.sources, so the page renders and a new 'table'
source can be registered through the form and appears in the registry list.
"""

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.goto(f"{base}/reporting/sources")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.flaky_e2e
def test_sources_admin_add_and_list(nexora_server, page):
    _login(page, nexora_server)
    expect(page.locator('[data-testid="reporting-sources-admin"]')).to_be_visible()
    expect(page.locator('[data-testid="reporting-sources-defaults"]')).to_contain_text(
        "docprocessing"
    )

    page.fill('[data-testid="rps-code"]', "e2e_src")
    page.fill('[data-testid="rps-label"]', "E2E Src")
    page.fill("#rpsPermission", "reporting.view")
    page.select_option("#rpsProvider", "table")
    page.select_option("#rpsEngine", "nexora")
    page.fill("#rpsBaseObject", "dbo.Users")
    page.fill(
        '[data-testid="rps-columns"]',
        '[{"field":"username","label":"Username","type":"string","filterable":true,"sortable":true}]',
    )
    page.locator('[data-testid="rps-save"]').click()
    expect(page.locator('[data-testid="rps-msg"]')).to_contain_text("Saved")
    expect(page.locator('[data-testid="reporting-sources-rows"]')).to_contain_text("e2e_src")
    page.screenshot(path="var/screenshots/reporting_sources_admin.png")

    # Clean up the registered row so it doesn't leak into other e2e runs.
    token = page.evaluate("() => document.querySelector('meta[name=\"csrf-token\"]').content")
    rows = page.request.get(f"{nexora_server}/api/reporting/admin/sources").json()["rows"]
    sid = next(r["id"] for r in rows if r["code"] == "e2e_src")
    page.request.delete(
        f"{nexora_server}/api/reporting/admin/sources/{sid}",
        headers={"X-CSRFToken": token, "Content-Type": "application/json"},
    )
