"""E2E for the Reporting share modal (cross-user sharing).

TestAdmin owns the report it creates, so the Share button is enabled and the
modal can set visibility and add an explicit per-user share. Verified against the
server's shares endpoint. The recipient side (a non-owner seeing a shared report)
is covered by the integration tests, since TEST has only one reporting user.
"""

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.goto(f"{base}/reporting")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.flaky_e2e
def test_share_modal_sets_visibility_and_adds_user(nexora_server, page):
    _login(page, nexora_server)
    token = page.evaluate("() => document.querySelector('meta[name=\"csrf-token\"]').content")
    headers = {"X-CSRFToken": token, "Content-Type": "application/json"}
    created = page.request.post(
        f"{nexora_server}/api/reporting/reports",
        headers=headers,
        data={
            "name": "Share E2E",
            "definition": {
                "kind": "sql",
                "target": "statistics",
                "sql": "SELECT 1 AS one",
                "title": "Share E2E",
            },
        },
    )
    assert created.ok, created.text()
    rid = created.json()["id"]

    page.goto(f"{nexora_server}/reporting")
    page.wait_for_load_state("domcontentloaded")
    page.locator(f'[data-testid="reporting-saved-reports"] option[value="{rid}"]').wait_for(
        state="attached"
    )
    page.locator('[data-testid="reporting-saved-reports"]').select_option(str(rid))

    # Share is enabled for an owned report; opening the modal shows the controls.
    expect(page.locator('[data-testid="reporting-share"]')).to_be_enabled()
    page.locator('[data-testid="reporting-share"]').click()
    expect(page.locator('[data-testid="reporting-share-modal"]')).to_be_visible()

    # Flip to "shared with everyone".
    with page.expect_response(
        lambda r: r.request.method == "POST" and f"/reports/{rid}/shares" in r.url
    ):
        page.locator('[data-testid="reporting-share-shared"]').check()

    # Add an explicit per-user share.
    page.fill('[data-testid="reporting-share-user"]', "user@test.local")
    with page.expect_response(
        lambda r: r.request.method == "POST" and f"/reports/{rid}/shares" in r.url
    ):
        page.locator('[data-testid="reporting-share-add"]').click()
    expect(page.locator('[data-testid="reporting-share-list"]')).to_contain_text("Test User")
    page.screenshot(path="var/screenshots/reporting_share_modal.png")

    # Server reflects both the visibility flip and the user share.
    state = page.request.get(f"{nexora_server}/api/reporting/reports/{rid}/shares").json()
    assert state["visibility"] == "shared"
    assert any(s["username"] == "user@test.local" for s in state["shares"])

    page.request.delete(f"{nexora_server}/api/reporting/reports/{rid}", headers=headers)
