"""E2E for the Reporting save-in-place flow (Save vs Save as).

With a report loaded, clicking Save overwrites it in place via PUT rather than
creating a copy. A SQL-kind report is used because it restores fully without the
Statistics DB (absent in TEST). TestAdmin holds the reporting.* perms.
"""

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.goto(f"{base}/reporting?tab=advanced")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.flaky_e2e
def test_save_overwrites_loaded_report_in_place(nexora_server, page):
    _login(page, nexora_server)
    token = page.evaluate("() => document.querySelector('meta[name=\"csrf-token\"]').content")
    headers = {"X-CSRFToken": token, "Content-Type": "application/json"}

    # Create a report through the API, then capture the owner's report count.
    created = page.request.post(
        f"{nexora_server}/api/reporting/reports",
        headers=headers,
        data={
            "name": "InPlace Orig",
            "definition": {
                "kind": "sql",
                "target": "statistics",
                "sql": "SELECT 1 AS one",
                "title": "InPlace Orig",
            },
        },
    )
    assert created.ok, created.text()
    rid = created.json()["id"]
    n_before = len(page.request.get(f"{nexora_server}/api/reporting/reports").json())

    # Saving a SQL report passes through the one-time live-SQL acknowledgment;
    # record it via the API so the reloaded page sees it acked (no blocking modal).
    ack = page.request.post(f"{nexora_server}/api/reporting/sql/ack", headers=headers, data={})
    assert ack.ok, ack.text()

    # Reload, select and load the report through the UI.
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.wait_for_load_state("domcontentloaded")
    page.locator(f'[data-testid="reporting-saved-reports"] option[value="{rid}"]').wait_for(
        state="attached"
    )
    page.locator('[data-testid="reporting-saved-reports"]').select_option(str(rid))
    page.locator('[data-testid="reporting-load"]').click()
    expect(page.locator('[data-testid="reporting-sql-editor"]')).to_have_value("SELECT 1 AS one")

    # The "Saved" alert auto-accepts; Save must issue a PUT (overwrite in place).
    page.on("dialog", lambda d: d.accept())
    page.fill('[data-testid="reporting-title"]', "InPlace Updated")
    with page.expect_response(
        lambda r: r.request.method == "PUT" and "/api/reporting/reports/" in r.url
    ) as resp_info:
        page.locator('[data-testid="reporting-save"]').click()
    assert resp_info.value.ok

    # No new report was created, and the existing one was renamed.
    n_after = len(page.request.get(f"{nexora_server}/api/reporting/reports").json())
    assert n_after == n_before
    got = page.request.get(f"{nexora_server}/api/reporting/reports/{rid}").json()
    assert got["name"] == "InPlace Updated"
    page.screenshot(path="var/screenshots/reporting_save_in_place.png")
