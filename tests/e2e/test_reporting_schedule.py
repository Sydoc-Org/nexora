"""E2E for the Reporting schedule modal (A1).

TestAdmin holds reporting.schedule, so the Schedule button renders and is enabled
for an owned report; a daily schedule can be added and is reflected by the
schedules endpoint. The runner/email path is covered by the integration tests.
"""

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.goto(f"{base}/reporting?tab=advanced")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.flaky_e2e
def test_schedule_modal_adds_schedule(nexora_server, page):
    _login(page, nexora_server)
    token = page.evaluate("() => document.querySelector('meta[name=\"csrf-token\"]').content")
    headers = {"X-CSRFToken": token, "Content-Type": "application/json"}
    created = page.request.post(
        f"{nexora_server}/api/reporting/reports",
        headers=headers,
        data={
            "name": "Sched E2E",
            "definition": {
                "kind": "sql",
                "target": "statistics",
                "sql": "SELECT 1 AS one",
                "title": "Sched E2E",
            },
        },
    )
    assert created.ok, created.text()
    rid = created.json()["id"]

    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.wait_for_load_state("domcontentloaded")
    page.locator(f'[data-testid="reporting-saved-reports"] option[value="{rid}"]').wait_for(
        state="attached"
    )
    page.locator('[data-testid="reporting-saved-reports"]').select_option(str(rid))

    expect(page.locator('[data-testid="reporting-schedule"]')).to_be_enabled()
    page.locator('[data-testid="reporting-schedule"]').click()
    expect(page.locator('[data-testid="reporting-schedule-modal"]')).to_be_visible()

    page.fill('[data-testid="reporting-schedule-recipients"]', "ops@example.com")
    with page.expect_response(
        lambda r: r.request.method == "POST" and f"/reports/{rid}/schedules" in r.url
    ):
        page.locator('[data-testid="reporting-schedule-add"]').click()
    expect(page.locator('[data-testid="reporting-schedule-list"]')).to_contain_text(
        "ops@example.com"
    )
    page.screenshot(path="var/screenshots/reporting_schedule_modal.png")

    schedules = page.request.get(f"{nexora_server}/api/reporting/reports/{rid}/schedules").json()
    assert len(schedules) == 1 and schedules[0]["frequency"] == "daily"
    assert schedules[0]["nextRunAt"]

    page.request.delete(f"{nexora_server}/api/reporting/reports/{rid}", headers=headers)
