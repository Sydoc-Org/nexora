"""e2e: the dashboard builder skeleton (Task 11, Spec 2 Phase 7).

A dashboard is a saved report whose DefinitionJSON is
{kind:'dashboard', schemaVersion:1, title, globalFilters:[...], cards:[...]}
persisted through the existing /api/reporting/reports CRUD -- no new
endpoints, no schema change. These tests cover only the skeleton:
opening a brand-new dashboard in editing mode + autosave on Done, and a
library card whose kind is 'dashboard' routing to the builder view
instead of the normal single-report result view.
"""

import json

from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")


def test_new_dashboard_opens_builder_and_saves(nexora_server, page):
    _login(page, nexora_server)
    saved = {}

    def capture_save(route):
        if route.request.method == "POST":
            saved.update(route.request.post_data_json)
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps({"id": 42, "ok": True})
            )
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps([]))

    # Register BEFORE goto -- the library load fires as soon as the Simple
    # pane mounts (same convention as test_reporting_simple.py).
    page.route("**/api/reporting/reports", capture_save)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-dashboard").click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    # A brand-new dashboard opens straight into editing mode.
    expect(page.get_by_test_id("rdb-edit-toggle")).to_have_text("Done")

    page.get_by_test_id("rdb-edit-toggle").click()  # Done -> autosave (D2)
    # Sync point: the toast only appears after the POST's response resolves,
    # so waiting for it avoids racing the plain dict assert below.
    expect(page.get_by_test_id("reporting-toast")).to_contain_text("Dashboard saved")
    assert saved["definition"]["kind"] == "dashboard"
    assert saved["definition"]["schemaVersion"] == 1


def test_dashboard_report_in_library_routes_to_builder(nexora_server, page):
    _login(page, nexora_server)
    dash_definition = {
        "kind": "dashboard",
        "schemaVersion": 1,
        "title": "e2e dashboard",
        "globalFilters": [],
        "cards": [],
    }
    page.route(
        "**/api/reporting/reports",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                [
                    {
                        "id": "e2e-dash-1",
                        "name": "e2e dashboard",
                        "ownerName": "Admin",
                        "updatedAt": "2026-07-01T00:00:00Z",
                        "visibility": "private",
                        "owned": True,
                        "kind": "dashboard",
                    }
                ]
            ),
        ),
    )
    page.route(
        "**/api/reporting/reports/*",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "id": "e2e-dash-1",
                    "name": "e2e dashboard",
                    "definition": dash_definition,
                    "visibility": "private",
                    "owned": True,
                    "canEdit": True,
                }
            ),
        ),
    )

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    expect(page.get_by_test_id("rs-result")).to_be_hidden()
