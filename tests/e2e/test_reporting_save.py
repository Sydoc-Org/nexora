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


@pytest.mark.flaky_e2e
def test_save_as_uses_name_modal(nexora_server, page):
    """Save as opens the custom name modal (not a browser prompt) and creates
    a new report under that name."""
    _login(page, nexora_server)
    token = page.evaluate("() => document.querySelector('meta[name=\"csrf-token\"]').content")
    headers = {"X-CSRFToken": token, "Content-Type": "application/json"}

    # Ack the SQL modal so it doesn't block
    page.request.post(f"{nexora_server}/api/reporting/sql/ack", headers=headers, data={})
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.wait_for_load_state("domcontentloaded")

    # Switch to SQL mode and type a minimal query so there's something to save
    page.locator('[data-testid="reporting-mode-sql"]').click()
    page.locator('[data-testid="reporting-sql-editor"]').fill("SELECT 1 AS x")

    # The "Saved" alert fires after the POST completes; accept it automatically.
    page.on("dialog", lambda d: d.accept())

    # Click Save as (no loaded report → same as save-as)
    page.locator('[data-testid="reporting-save-as"]').click()
    modal = page.get_by_test_id("reporting-name-modal")
    expect(modal).to_be_visible()
    page.get_by_test_id("reporting-name-input").fill("modal-save-e2e")
    page.get_by_test_id("reporting-name-ok").click()
    expect(modal).to_be_hidden()

    # The new report should appear in the saved reports dropdown. loadReports()
    # repopulates it asynchronously after the create POST resolves, so wait for the
    # option to show up rather than snapshotting the <select> immediately (which races
    # the refresh and intermittently sees only the placeholder).
    expect(page.locator('[data-testid="reporting-saved-reports"]')).to_contain_text(
        "modal-save-e2e"
    )

    # Clean up
    reports = page.request.get(f"{nexora_server}/api/reporting/reports").json()
    r = next((x for x in reports if x["name"] == "modal-save-e2e"), None)
    if r:
        page.request.delete(f"{nexora_server}/api/reporting/reports/{r['id']}", headers=headers)
    page.screenshot(path="var/screenshots/reporting_save_as_modal.png")
