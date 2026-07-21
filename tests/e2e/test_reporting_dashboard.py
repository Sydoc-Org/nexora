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


def test_dashboard_cards_render_real_data_per_card(nexora_server, page):
    """Task 12: renderCard/runCard -- one /api/reporting/run per card, real
    Chart.js/DOM output keyed off the response {columns, rows}, not mock data.
    A zero-dim KPI card and a dimensioned line card get distinct stubbed
    payloads, matched on the presence of a `columns` entry in the posted
    report definition (KPI cards run a zero-column clone; charts don't).
    """
    _login(page, nexora_server)
    dash_definition = {
        "kind": "dashboard",
        "schemaVersion": 1,
        "title": "e2e dashboard",
        "globalFilters": [],
        "cards": [
            {
                "id": "k1",
                "type": "kpi",
                "span": 3,
                "title": "Document count",
                "definition": {
                    "source": "workitems",
                    "metrics": [{"field": "id", "agg": "count"}],
                    "columns": [],
                    "filters": [],
                },
                "filterOverrides": [],
            },
            {
                "id": "c1",
                "type": "line",
                "span": 8,
                "title": "Documents per month",
                "definition": {
                    "source": "workitems",
                    "metrics": [{"field": "id", "agg": "count"}],
                    "columns": [{"field": "createdDate", "grain": "month"}],
                    "filters": [],
                },
                "filterOverrides": [],
            },
        ],
    }
    page.route(
        "**/api/reporting/reports",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                [
                    {
                        "id": "e2e-dash-2",
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
                    "id": "e2e-dash-2",
                    "name": "e2e dashboard",
                    "definition": dash_definition,
                    "visibility": "private",
                    "owned": True,
                    "canEdit": True,
                }
            ),
        ),
    )

    def fulfill_run(route):
        posted = route.request.post_data_json or {}
        if posted.get("columns"):  # the line card's own definition has one
            payload = {
                "columns": [
                    {"field": "createdDate", "header": "Month"},
                    {"field": "id", "header": "Count"},
                ],
                "rows": [["2026-01", 12], ["2026-02", 18], ["2026-03", 9]],
                "rowCount": 3,
            }
        else:  # zero-dim KPI clone -- just the metric column
            payload = {
                "columns": [{"field": "id", "header": "Count"}],
                "rows": [[1204]],
                "rowCount": 1,
            }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("**/api/reporting/run", fulfill_run)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()

    kpi_card = page.locator('[data-testid="rdb-card"][data-card-id="k1"]')
    expect(kpi_card.get_by_test_id("rdb-kpi-value")).to_have_text("1,204")

    line_card = page.locator('[data-testid="rdb-card"][data-card-id="c1"]')
    expect(line_card.locator("canvas")).to_have_count(1)


def _stub_dashboard_report(page, report_id, definition):
    page.route(
        "**/api/reporting/reports",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                [
                    {
                        "id": report_id,
                        "name": definition["title"],
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
                    "id": report_id,
                    "name": definition["title"],
                    "definition": definition,
                    "visibility": "private",
                    "owned": True,
                    "canEdit": True,
                }
            ),
        ),
    )


# One source with one filterable string field -- enough for the popover's
# field <select> to have something to offer. Registered BEFORE goto, same
# convention as _stub_catalogs() in test_reporting_simple.py.
GFILTER_STUB_SOURCES = [
    {
        "id": "workitems",
        "label": "Workitems",
        "kind": "curated",
        "processes": [],
        "fields": [
            {
                "field": "status",
                "label": "Status",
                "type": "string",
                "grainable": False,
                "filterable": True,
            }
        ],
    }
]
GFILTER_STUB_METRICS = {
    "workitems": [{"code": "id_count", "label": "Count", "aggregation": "count"}]
}


def _stub_gfilter_catalog(page):
    page.route(
        "**/api/reporting/sources",
        lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(GFILTER_STUB_SOURCES)
        ),
    )
    page.route(
        "**/api/reporting/metrics",
        lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(GFILTER_STUB_METRICS)
        ),
    )


def test_global_filter_popover_adds_chip_and_reruns_affected_card(nexora_server, page):
    """Task 13: adding a global filter via the popover renders an rdb-gfilter
    chip and re-runs the (only, affected) card -- the run stub must be hit
    a second time with the new filter present on the posted definition.
    """
    _login(page, nexora_server)
    dash_definition = {
        "kind": "dashboard",
        "schemaVersion": 1,
        "title": "e2e gfilter dashboard",
        "globalFilters": [],
        "cards": [
            {
                "id": "k1",
                "type": "kpi",
                "span": 3,
                "title": "Document count",
                "definition": {
                    "source": "workitems",
                    "metrics": [{"field": "id", "agg": "count"}],
                    "columns": [],
                    "filters": [],
                },
                "filterOverrides": [],
            }
        ],
    }
    _stub_dashboard_report(page, "e2e-dash-gfilter", dash_definition)
    _stub_gfilter_catalog(page)

    run_calls = []

    def fulfill_run(route):
        posted = route.request.post_data_json or {}
        run_calls.append(posted)
        # Distinct value on the 2nd+ call -- a DOM-observable signal that the
        # re-run actually happened, same sync idiom as
        # test_refine_sends_prior_context_and_replaces_result (assert on a
        # rendered value via expect(), then inspect the captured payload).
        value = 1204 if len(run_calls) == 1 else 999
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"columns": [{"field": "id", "header": "Count"}], "rows": [[value]], "rowCount": 1}
            ),
        )

    page.route("**/api/reporting/run", fulfill_run)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    expect(page.get_by_test_id("rdb-kpi-value")).to_have_text("1,204")
    assert len(run_calls) == 1

    page.get_by_test_id("rdb-add-filter").click()
    popover = page.locator("#rdbFilterPop")
    expect(popover).to_be_visible()
    popover.get_by_test_id("rdb-filter-field").select_option("status")
    popover.get_by_test_id("rdb-filter-op").select_option("contains")
    popover.get_by_test_id("rdb-filter-value").fill("Open")
    popover.get_by_test_id("rdb-filter-apply").click()

    expect(popover).to_be_hidden()
    chip = page.get_by_test_id("rdb-gfilter")
    expect(chip).to_have_count(1)
    expect(chip).to_contain_text("Status")
    expect(chip).to_contain_text("Open")

    # The one card on this dashboard is affected by every global filter (it
    # has no override), so the run stub must have been re-hit -- the KPI's
    # new (distinct) value proves the 2nd run resolved and rendered.
    expect(page.get_by_test_id("rdb-kpi-value")).to_have_text("999")
    assert len(run_calls) == 2
    assert run_calls[-1]["filters"] == [{"field": "status", "op": "contains", "value": "Open"}]


def test_card_override_chip_removal_clears_filter_and_reruns_card(nexora_server, page):
    """Task 13: the x on a card's violet override chip clears filterOverrides
    entirely for that card and re-runs it -- the run stub is hit again with
    the override no longer present.
    """
    _login(page, nexora_server)
    dash_definition = {
        "kind": "dashboard",
        "schemaVersion": 1,
        "title": "e2e override dashboard",
        "globalFilters": [],
        "cards": [
            {
                "id": "k1",
                "type": "kpi",
                "span": 3,
                "title": "Document count",
                "definition": {
                    "source": "workitems",
                    "metrics": [{"field": "id", "agg": "count"}],
                    "columns": [],
                    "filters": [],
                },
                "filterOverrides": [{"field": "status", "op": "eq", "value": "Open"}],
            }
        ],
    }
    _stub_dashboard_report(page, "e2e-dash-override", dash_definition)
    _stub_gfilter_catalog(page)

    run_calls = []

    def fulfill_run(route):
        posted = route.request.post_data_json or {}
        run_calls.append(posted)
        # Distinct value on the 2nd+ call -- a DOM-observable signal that the
        # re-run actually happened (same idiom as the sibling gfilter test).
        value = 1204 if len(run_calls) == 1 else 500
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"columns": [{"field": "id", "header": "Count"}], "rows": [[value]], "rowCount": 1}
            ),
        )

    page.route("**/api/reporting/run", fulfill_run)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    expect(page.get_by_test_id("rdb-kpi-value")).to_have_text("1,204")
    assert run_calls[-1]["filters"] == [{"field": "status", "op": "eq", "value": "Open"}]

    override_chip = page.get_by_test_id("rdb-card-filter")
    expect(override_chip).to_have_count(1)
    override_chip.get_by_test_id("rdb-card-filter-remove").click()

    expect(page.get_by_test_id("rdb-card-filter")).to_have_count(0)
    expect(page.get_by_test_id("rdb-kpi-value")).to_have_text("500")
    assert len(run_calls) == 2
    assert run_calls[-1]["filters"] == []
