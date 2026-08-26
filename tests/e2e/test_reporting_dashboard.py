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


def test_global_filter_popover_stays_open_on_cached_catalog_reopen(nexora_server, page):
    """Task 34: ensureCatalog()'s promise is cached after the first open.
    On the first open the real fetch is slow enough that the popover opens
    well after the triggering click has finished bubbling to the
    document-level outside-click closer. On every later open the cached
    promise resolves in a microtask that runs BEFORE the same click finishes
    bubbling -- the closer then sees filterPop.open just turned true and the
    click target outside the popover, and self-closes it immediately.
    Open, close, reopen (catalog now cached) -- it must stay open, and a
    genuine outside click afterward must still close it.
    """
    _login(page, nexora_server)
    dash_definition = {
        "kind": "dashboard",
        "schemaVersion": 1,
        "title": "e2e cached-reopen dashboard",
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
    _stub_dashboard_report(page, "e2e-dash-cachedreopen", dash_definition)
    _stub_gfilter_catalog(page)
    page.route(
        "**/api/reporting/run",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"columns": [{"field": "id", "header": "Count"}], "rows": [[1]], "rowCount": 1}
            ),
        ),
    )

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()

    popover = page.locator("#rdbFilterPop")

    # First open: real (uncached) catalog fetch -- already worked before the
    # fix. Close it via Cancel so the second open below is the one exercising
    # the cached-promise race.
    page.get_by_test_id("rdb-add-filter").click()
    expect(popover).to_be_visible()
    popover.get_by_test_id("rdb-filter-cancel").click()
    expect(popover).to_be_hidden()

    # Second open: ensureCatalog()'s promise is now cached -- this is the
    # regression case. Before the fix, the popover opened and immediately
    # self-closed on this very click.
    page.get_by_test_id("rdb-add-filter").click()
    expect(popover).to_be_visible()
    # Give any stray close handler a moment to fire before asserting it
    # *stays* visible, not just that it existed for one frame.
    page.wait_for_timeout(300)
    expect(popover).to_be_visible()

    # The fix must not break genuine outside-click-to-close behaviour.
    page.get_by_test_id("rdb-title").click()
    expect(popover).to_be_hidden()


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


# ---------------------------------------------------------------------------
# Task 14 -- edit mode: DnD reorder, add/duplicate/remove, add-card tile.
# Handlers ported 1:1 from the prototype's onDragStart/onDragOver/onDrop/
# onDragEnd + remove/duplicate (D10) -- see
# docs/superpowers/specs/2026-07-20-reporting-dashboard-prototype.dc.html.
# ---------------------------------------------------------------------------

RUN_STUB_SIMPLE = {"columns": [{"field": "id", "header": "Count"}], "rows": [[1]], "rowCount": 1}


def test_edit_mode_drag_reorders_cards_and_persists_on_done(nexora_server, page):
    """Dragging card k1 onto c1 splices k1 to sit after c1 in
    state.def.cards; Done then autosaves the reordered definition, observable
    in the captured PUT body's card id order.
    """
    _login(page, nexora_server)
    report_id = "e2e-dash-reorder"
    dash_definition = {
        "kind": "dashboard",
        "schemaVersion": 1,
        "title": "e2e reorder dashboard",
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
                        "id": report_id,
                        "name": dash_definition["title"],
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

    put_bodies = []

    def handle_report(route):
        if route.request.method == "PUT":
            put_bodies.append(route.request.post_data_json)
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps({"ok": True})
            )
        else:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "id": report_id,
                        "name": dash_definition["title"],
                        "definition": dash_definition,
                        "visibility": "private",
                        "owned": True,
                        "canEdit": True,
                    }
                ),
            )

    page.route(f"**/api/reporting/reports/{report_id}", handle_report)
    page.route(
        "**/api/reporting/run",
        lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(RUN_STUB_SIMPLE)
        ),
    )

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    expect(page.get_by_test_id("rdb-card")).to_have_count(2)

    page.get_by_test_id("rdb-edit-toggle").click()  # Edit -> enter editing mode
    expect(page.get_by_test_id("rdb-edit-toggle")).to_have_text("Done")

    source = page.locator('[data-testid="rdb-card"][data-card-id="k1"]')
    target = page.locator('[data-testid="rdb-card"][data-card-id="c1"]')
    try:
        source.drag_to(target, timeout=3000)
    except Exception:
        # Playwright's synthetic drag_to doesn't reliably fire native HTML5
        # DnD events in every environment (per the task brief's documented
        # fallback) -- dispatch dragstart/dragover/drop by hand instead.
        page.eval_on_selector(
            '[data-testid="rdb-card"][data-card-id="k1"]',
            "(el) => el.dispatchEvent(new DragEvent('dragstart', "
            "{bubbles: true, dataTransfer: new DataTransfer()}))",
        )
        page.eval_on_selector(
            '[data-testid="rdb-card"][data-card-id="c1"]',
            "(el) => { "
            "  el.dispatchEvent(new DragEvent('dragover', "
            "    {bubbles: true, cancelable: true, dataTransfer: new DataTransfer()})); "
            "  el.dispatchEvent(new DragEvent('drop', "
            "    {bubbles: true, cancelable: true, dataTransfer: new DataTransfer()})); "
            "}",
        )

    page.get_by_test_id("rdb-edit-toggle").click()  # Done -> autosave (D2)
    expect(page.get_by_test_id("reporting-toast")).to_contain_text("Dashboard saved")
    assert len(put_bodies) == 1
    ids = [c["id"] for c in put_bodies[0]["definition"]["cards"]]
    assert ids == ["c1", "k1"]


def test_edit_mode_duplicate_button_adds_a_card(nexora_server, page):
    """The control-cluster duplicate button (fa-clone, rdb-card-dup) clones
    the card with a fresh 'dup<seq>' id, inserted right after the original.
    """
    _login(page, nexora_server)
    dash_definition = {
        "kind": "dashboard",
        "schemaVersion": 1,
        "title": "e2e dup dashboard",
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
    _stub_dashboard_report(page, "e2e-dash-dup", dash_definition)
    page.route(
        "**/api/reporting/run",
        lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(RUN_STUB_SIMPLE)
        ),
    )

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    expect(page.get_by_test_id("rdb-card")).to_have_count(1)

    page.get_by_test_id("rdb-edit-toggle").click()
    page.locator('[data-testid="rdb-card"][data-card-id="k1"] [data-testid="rdb-card-dup"]').click()

    expect(page.get_by_test_id("rdb-card")).to_have_count(2)


def test_edit_mode_remove_button_removes_a_card(nexora_server, page):
    """The control-cluster remove button (fa-xmark, rdb-card-remove) splices
    the card out of state.def.cards.
    """
    _login(page, nexora_server)
    dash_definition = {
        "kind": "dashboard",
        "schemaVersion": 1,
        "title": "e2e remove dashboard",
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
    _stub_dashboard_report(page, "e2e-dash-remove", dash_definition)
    page.route(
        "**/api/reporting/run",
        lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(RUN_STUB_SIMPLE)
        ),
    )

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    expect(page.get_by_test_id("rdb-card")).to_have_count(2)

    page.get_by_test_id("rdb-edit-toggle").click()
    page.locator(
        '[data-testid="rdb-card"][data-card-id="k1"] [data-testid="rdb-card-remove"]'
    ).click()

    expect(page.get_by_test_id("rdb-card")).to_have_count(1)
    expect(page.locator('[data-testid="rdb-card"][data-card-id="c1"]')).to_have_count(1)


def test_add_card_tile_type_pill_adds_new_card_shell(nexora_server, page):
    """Clicking a type pill on the add-card tile (rdb-add-tile) appends a new
    empty-definition card shell of that type. A brand-new dashboard opens
    directly into editing mode with zero cards, so the tile is the only way
    to add one.
    """
    _login(page, nexora_server)

    def capture_reports(route):
        if route.request.method == "POST":
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps({"id": 77, "ok": True})
            )
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps([]))

    page.route("**/api/reporting/reports", capture_reports)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-dashboard").click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    expect(page.get_by_test_id("rdb-edit-toggle")).to_have_text("Done")

    expect(page.get_by_test_id("rdb-add-tile")).to_be_visible()
    expect(page.get_by_test_id("rdb-card")).to_have_count(0)

    page.get_by_test_id("rdb-add-kpi").click()

    expect(page.get_by_test_id("rdb-card")).to_have_count(1)
    expect(page.locator('[data-testid="rdb-card"][data-type="kpi"]')).to_have_count(1)


def test_add_card_configure_click_opens_picker_and_adopts_report(nexora_server, page):
    """v1 card configuration: a freshly added empty-definition card's body is
    a click-to-configure placeholder (rdb-card-configure); clicking it opens
    a picker of the caller's own saved non-SQL, non-dashboard reports (GET
    /api/reporting/reports), and picking one copies that report's definition
    + name into the card, then re-runs it.
    """
    _login(page, nexora_server)

    reports_list = [
        {
            "id": 501,
            "name": "Invoices by month",
            "ownerName": "Admin",
            "updatedAt": "2026-07-01T00:00:00Z",
            "visibility": "private",
            "owned": True,
            "kind": "table",
        },
        # excluded from the picker -- sql / dashboard kinds:
        {
            "id": 502,
            "name": "Raw SQL",
            "ownerName": "Admin",
            "updatedAt": "2026-07-01T00:00:00Z",
            "visibility": "private",
            "owned": True,
            "kind": "sql",
        },
        {
            "id": 503,
            "name": "Another dashboard",
            "ownerName": "Admin",
            "updatedAt": "2026-07-01T00:00:00Z",
            "visibility": "private",
            "owned": True,
            "kind": "dashboard",
        },
    ]
    adopted_definition = {
        "source": "workitems",
        "metrics": [{"field": "id", "agg": "count"}],
        "columns": [],
        "filters": [],
    }

    def handle_reports(route):
        if route.request.method == "POST":
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps({"id": 9, "ok": True})
            )
        else:
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps(reports_list)
            )

    page.route("**/api/reporting/reports", handle_reports)
    page.route(
        "**/api/reporting/reports/501",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "id": 501,
                    "name": "Invoices by month",
                    "definition": adopted_definition,
                    "visibility": "private",
                    "owned": True,
                    "canEdit": True,
                }
            ),
        ),
    )
    page.route(
        "**/api/reporting/run",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"columns": [{"field": "id", "header": "Count"}], "rows": [[42]], "rowCount": 1}
            ),
        ),
    )

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-dashboard").click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()

    page.get_by_test_id("rdb-add-kpi").click()
    expect(page.get_by_test_id("rdb-card")).to_have_count(1)

    page.get_by_test_id("rdb-card-configure").click()
    picker = page.get_by_test_id("rdb-report-picker")
    expect(picker).to_be_visible()
    picks = picker.get_by_test_id("rdb-report-pick")
    expect(picks).to_have_count(1)  # sql/dashboard-kind + non-owned rows filtered out
    expect(picks).to_have_text("Invoices by month")
    picks.click()

    expect(picker).to_be_hidden()
    expect(page.get_by_test_id("rdb-card").locator(".rdb-card-title")).to_have_text(
        "Invoices by month"
    )
    expect(page.get_by_test_id("rdb-kpi-value")).to_have_text("42")


# ---------------------------------------------------------------------------
# Task 15 -- KPI trend, card drill-through, Export. Drill mirrors the Simple
# pane's chart onClick -> ReportingDrill.open call exactly (re-Grepped in
# templates/js/_reporting_simple_js.html's drillFromChart/openDrill); the
# drill drawer + #rdChips are the shared panel Task 9 built
# (templates/js/_reporting_drill_js.html), reused verbatim here. KPI trend
# (D8) and Export (D9) semantics: docs/superpowers/plans/
# 2026-07-20-reporting-redesign-dashboard-builder.md.
# ---------------------------------------------------------------------------

DRILL_LINE_DASH = {
    "kind": "dashboard",
    "schemaVersion": 1,
    "title": "e2e drill dashboard",
    "globalFilters": [],
    "cards": [
        {
            "id": "c1",
            "type": "line",
            "span": 8,
            "title": "Documents per month",
            "definition": {
                "source": "workitems",
                "metrics": [{"field": "id", "agg": "count"}],
                "columns": [{"field": "createdDate"}],
                "filters": [],
            },
            "filterOverrides": [],
        }
    ],
}


def test_line_card_chart_click_opens_drill_panel(nexora_server, page):
    """Task 15 drill-through: clicking a rendered Chart.js point on a line
    card opens the SAME shared drill drawer the Simple pane's own chart
    onClick uses (ReportingDrill.open, mirrored 1:1 -- see
    templates/js/_reporting_simple_js.html's drillFromChart/openDrill).
    The drill's own detail-row request is distinguished from the card's own
    aggregate run by rowLimit === 100 (ReportingDrill's fixed page size --
    same convention as test_drill_row_opens_workitem_panel in
    test_reporting.py).
    """
    _login(page, nexora_server)
    _stub_dashboard_report(page, "e2e-dash-drill", DRILL_LINE_DASH)
    page.route(
        "**/api/reporting/sources",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                [
                    {
                        "id": "workitems",
                        "label": "Workitems",
                        "kind": "curated",
                        "processes": [],
                        "fields": [
                            {
                                "field": "createdDate",
                                "label": "Created",
                                "type": "date",
                                "grainable": False,
                                "filterable": True,
                            }
                        ],
                    }
                ]
            ),
        ),
    )
    page.route(
        "**/api/reporting/metrics",
        lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({})),
    )

    def fulfill_run(route):
        posted = route.request.post_data_json or {}
        if posted.get("rowLimit") == 100:  # the drill drawer's own detail-row request
            payload = {
                "columns": [{"field": "createdDate", "header": "Created"}],
                "rows": [["2026-01"]],
                "rowCount": 1,
                "truncated": False,
            }
        else:  # the card's own aggregate run
            payload = {
                "columns": [
                    {"field": "createdDate", "header": "Month"},
                    {"field": "id", "header": "Count"},
                ],
                "rows": [["2026-01", 12], ["2026-02", 18], ["2026-03", 9]],
                "rowCount": 3,
            }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("**/api/reporting/run", fulfill_run)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()

    line_card = page.locator('[data-testid="rdb-card"][data-card-id="c1"]')
    canvas = line_card.locator("canvas")
    expect(canvas).to_be_visible()
    # Chart.js animates points in on mount (default ~1s duration) -- reading
    # a point's position mid-animation would click a stale (moving) target,
    # so wait for the draw-in animation to settle first.
    page.wait_for_timeout(1200)

    # Playwright can't hit-test a <canvas> pixel by CSS selector -- read the
    # live Chart.js instance's own computed point position (the same data
    # getElementsAtEventForMode hit-tests against) and click there.
    point = canvas.evaluate(
        "(el) => { const c = Chart.getChart(el); const meta = c.getDatasetMeta(0); "
        "const r = el.getBoundingClientRect(); "
        "return { x: r.left + meta.data[0].x, y: r.top + meta.data[0].y }; }"
    )
    page.mouse.click(point["x"], point["y"])

    panel = page.get_by_test_id("reporting-drill-panel")
    expect(panel).to_be_visible()
    expect(page.locator("#rdTitle")).to_have_text("Documents per month")
    chips = page.get_by_test_id("reporting-drill-chips")
    expect(chips.locator(".reporting-drill-chip")).to_have_count(1)


DRILL_TABLE_DASH = {
    "kind": "dashboard",
    "schemaVersion": 1,
    "title": "e2e table drill dashboard",
    "globalFilters": [],
    "cards": [
        {
            "id": "t1",
            "type": "table",
            "span": 6,
            "title": "Documents by status",
            "definition": {
                "source": "workitems",
                "metrics": [{"field": "id", "agg": "count"}],
                "columns": [{"field": "status"}],
                "filters": [],
            },
            "filterOverrides": [],
        }
    ],
}


def test_table_card_row_click_opens_drill_panel(nexora_server, page):
    """Task 15 drill-through, table variant: a dashboard table card's row
    click builds the same {field, grain, value} clicked shape as a chart
    click, sourced from the clicked row's dimension value -- no coordinate
    math needed since table rows are plain DOM elements."""
    _login(page, nexora_server)
    _stub_dashboard_report(page, "e2e-dash-table-drill", DRILL_TABLE_DASH)
    page.route(
        "**/api/reporting/sources",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                [
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
            ),
        ),
    )
    page.route(
        "**/api/reporting/metrics",
        lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({})),
    )

    def fulfill_run(route):
        posted = route.request.post_data_json or {}
        if posted.get("rowLimit") == 100:
            payload = {
                "columns": [{"field": "status", "header": "Status"}],
                "rows": [["Open"]],
                "rowCount": 1,
                "truncated": False,
            }
        else:
            payload = {
                "columns": [
                    {"field": "status", "header": "Status"},
                    {"field": "id", "header": "Count"},
                ],
                "rows": [["Open", 12], ["Closed", 8]],
                "rowCount": 2,
            }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("**/api/reporting/run", fulfill_run)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()

    table_card = page.locator('[data-testid="rdb-card"][data-card-id="t1"]')
    expect(table_card.get_by_test_id("rdb-table-rows")).to_be_visible()
    table_card.locator(".rdb-table-k").first.click()

    panel = page.get_by_test_id("reporting-drill-panel")
    expect(panel).to_be_visible()
    expect(page.locator("#rdTitle")).to_have_text("Documents by status")


def test_export_menu_lists_cards_and_downloads_effective_definition(nexora_server, page):
    """D9: the header Export button (perm-gated via #rsDashboard's
    data-can-export attribute, set from has_permission('reporting.export'))
    opens a menu of card titles; picking one POSTs that card's EFFECTIVE
    (merged) definition to /api/reporting/export and downloads the result --
    same fetch->blob->anchor-click idiom as the Simple pane's own #rsExport
    listener in _reporting_simple_js.html.
    """
    _login(page, nexora_server)
    dash_definition = {
        "kind": "dashboard",
        "schemaVersion": 1,
        "title": "e2e export dashboard",
        "globalFilters": [{"field": "status", "op": "eq", "value": "Open"}],
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
    _stub_dashboard_report(page, "e2e-dash-export", dash_definition)
    page.route(
        "**/api/reporting/run",
        lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(RUN_STUB_SIMPLE)
        ),
    )

    export_calls = []

    def fulfill_export(route):
        export_calls.append(route.request.post_data_json)
        route.fulfill(
            status=200,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            body=b"stub-xlsx-bytes",
        )

    page.route("**/api/reporting/export", fulfill_export)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()

    page.get_by_test_id("rdb-export").click()
    menu = page.get_by_test_id("rdb-export-menu")
    expect(menu).to_be_visible()
    items = menu.get_by_test_id("rdb-export-item")
    expect(items).to_have_count(1)
    expect(items).to_have_text("Document count")

    with page.expect_download() as dl_info:
        items.click()
    assert dl_info.value.suggested_filename.endswith(".xlsx")

    assert len(export_calls) == 1
    assert export_calls[0]["source"] == "workitems"
    # The global filter must be merged into the effective (post-merge)
    # definition posted -- not the card's own bare (empty) filter list.
    assert export_calls[0]["filters"] == [{"field": "status", "op": "eq", "value": "Open"}]


def test_kpi_card_shows_trend_vs_previous_period(nexora_server, page):
    """Task 15/D8: a KPI card whose effective filters hold exactly one
    date-range filter triggers a second /api/reporting/run with the range
    shifted back one period. Here the filter uses the 'this_year' token,
    which has a documented sibling in nx_lib/reporting/tokens.py
    (RELATIVE_DATE_TOKENS) -- 'last_year' -- so the period-shift helper maps
    directly to it rather than computing a literal shift.
    """
    _login(page, nexora_server)
    dash_definition = {
        "kind": "dashboard",
        "schemaVersion": 1,
        "title": "e2e trend dashboard",
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
                    "filters": [
                        {"field": "createdDate", "op": "between", "value": {"token": "this_year"}}
                    ],
                },
                "filterOverrides": [],
            }
        ],
    }
    _stub_dashboard_report(page, "e2e-dash-trend", dash_definition)

    run_calls = []

    def fulfill_run(route):
        posted = route.request.post_data_json or {}
        run_calls.append(posted)
        token = ((posted.get("filters") or [{}])[0].get("value") or {}).get("token")
        value = 1200 if token == "this_year" else 1000
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
    expect(page.get_by_test_id("rdb-kpi-value")).to_have_text("1,200")

    trend = page.get_by_test_id("rdb-kpi-trend")
    expect(trend).to_be_visible()
    expect(trend).to_contain_text("+20.0%")
    expect(trend).to_contain_text("vs previous period")

    assert len(run_calls) == 2
    assert run_calls[1]["filters"] == [
        {"field": "createdDate", "op": "between", "value": {"token": "last_year"}}
    ]


def test_kpi_card_without_single_date_filter_shows_no_trend(nexora_server, page):
    """D8's negative case: zero date-range filters on the card's effective
    filters means no comparison is possible -- honest numbers or nothing,
    never a guessed/second run.
    """
    _login(page, nexora_server)
    dash_definition = {
        "kind": "dashboard",
        "schemaVersion": 1,
        "title": "e2e no-trend dashboard",
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
    _stub_dashboard_report(page, "e2e-dash-notrend", dash_definition)

    run_calls = []

    def fulfill_run(route):
        run_calls.append(route.request.post_data_json or {})
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"columns": [{"field": "id", "header": "Count"}], "rows": [[1204]], "rowCount": 1}
            ),
        )

    page.route("**/api/reporting/run", fulfill_run)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    expect(page.get_by_test_id("rdb-kpi-value")).to_have_text("1,204")

    expect(page.get_by_test_id("rdb-kpi-trend")).to_have_count(0)
    assert len(run_calls) == 1


def test_kpi_card_run_request_omits_breakdown_dims_and_shows_total(nexora_server, page):
    """D-KPI: a KPI card whose own definition carries a breakdown dimension
    (e.g. cloned/adapted from a chart card) must still request an
    undimensioned total -- the run payload strips `columns` down to []
    before POSTing, so the backend returns a single zero-dim total row
    instead of an arbitrary first bucket. renderKpi itself is untouched
    (it still reads rows[0]); the fix is entirely in what gets requested.
    """
    _login(page, nexora_server)
    dash_definition = {
        "kind": "dashboard",
        "schemaVersion": 1,
        "title": "e2e kpi breakdown dashboard",
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
                    "columns": [{"field": "status"}],
                    "filters": [],
                },
                "filterOverrides": [],
            }
        ],
    }
    _stub_dashboard_report(page, "e2e-dash-kpi-breakdown", dash_definition)

    run_calls = []

    def fulfill_run(route):
        posted = route.request.post_data_json or {}
        run_calls.append(posted)
        if posted.get("columns"):
            # The bug: a breakdown dim slipped through. Return per-bucket
            # rows so a regression (reading rows[0]) shows an arbitrary
            # first-bucket value instead of the stubbed total below.
            payload = {
                "columns": [
                    {"field": "status", "header": "Status"},
                    {"field": "id", "header": "Count"},
                ],
                "rows": [["open", 42], ["closed", 7735]],
                "rowCount": 2,
            }
        else:
            payload = {
                "columns": [{"field": "id", "header": "Count"}],
                "rows": [[7777]],
                "rowCount": 1,
            }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("**/api/reporting/run", fulfill_run)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    expect(page.get_by_test_id("rdb-kpi-value")).to_have_text("7,777")

    assert len(run_calls) == 1
    assert run_calls[0]["columns"] == []


# ---------------------------------------------------------------------------
# Phase 7 review-finding regressions:
#  1) handleCardChartClick/handleCardTableRowClick sourced grain from the
#     RUN RESULT's columns ({field, header} only -- api_reports_run never
#     echoes grain), so a grained line card always drilled with grain=null,
#     falling back to an exact-value match on the truncated bucket label
#     instead of a date range. Fixed to source {field, grain} from the
#     card's own definition.columns instead (mirrors clickedFor/
#     drillFromChart in _reporting_simple_js.html).
#  2) open() unconditionally reset state.seq to 100, so a saved dashboard
#     whose cards already used the n100/dup100 ids (persisted from a prior
#     add/duplicate) collided with the very next add/duplicate after
#     reopening. Fixed to seed seq from the highest existing n-/dup-prefixed
#     numeric id already in the loaded definition.
# ---------------------------------------------------------------------------

DRILL_LINE_GRAIN_DASH = {
    "kind": "dashboard",
    "schemaVersion": 1,
    "title": "e2e grain drill dashboard",
    "globalFilters": [],
    "cards": [
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
        }
    ],
}


def test_line_card_chart_click_drills_by_date_range_not_exact_bucket(nexora_server, page):
    """Review finding 1: a grained line card's chart-click drill must build a
    gte/lt date-RANGE filter for the clicked month bucket (sourced from
    card.definition.columns[0].grain), not an exact-value match on the raw
    bucket value (which the run result's columns never carry grain to guard
    against). Distinguishes the drill drawer's own detail-row request from
    the card's own aggregate run via rowLimit === 100, same convention as
    test_line_card_chart_click_opens_drill_panel above.
    """
    _login(page, nexora_server)
    _stub_dashboard_report(page, "e2e-dash-grain-drill", DRILL_LINE_GRAIN_DASH)
    page.route(
        "**/api/reporting/sources",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                [
                    {
                        "id": "workitems",
                        "label": "Workitems",
                        "kind": "curated",
                        "processes": [],
                        "fields": [
                            {
                                "field": "createdDate",
                                "label": "Created",
                                "type": "date",
                                "grainable": True,
                                "filterable": True,
                            }
                        ],
                    }
                ]
            ),
        ),
    )
    page.route(
        "**/api/reporting/metrics",
        lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({})),
    )

    drill_requests = []

    def fulfill_run(route):
        posted = route.request.post_data_json or {}
        if posted.get("rowLimit") == 100:  # the drill drawer's own detail-row request
            drill_requests.append(posted)
            payload = {
                "columns": [{"field": "createdDate", "header": "Created"}],
                "rows": [["2026-01-01"]],
                "rowCount": 1,
                "truncated": False,
            }
        else:  # the card's own aggregate run -- run-result columns carry NO grain
            payload = {
                "columns": [
                    {"field": "createdDate", "header": "Month"},
                    {"field": "id", "header": "Count"},
                ],
                "rows": [["2026-01-01", 12], ["2026-02-01", 18], ["2026-03-01", 9]],
                "rowCount": 3,
            }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("**/api/reporting/run", fulfill_run)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()

    line_card = page.locator('[data-testid="rdb-card"][data-card-id="c1"]')
    canvas = line_card.locator("canvas")
    expect(canvas).to_be_visible()
    # Same animation-settle wait as test_line_card_chart_click_opens_drill_panel.
    page.wait_for_timeout(1200)

    point = canvas.evaluate(
        "(el) => { const c = Chart.getChart(el); const meta = c.getDatasetMeta(0); "
        "const r = el.getBoundingClientRect(); "
        "return { x: r.left + meta.data[0].x, y: r.top + meta.data[0].y }; }"
    )
    page.mouse.click(point["x"], point["y"])

    panel = page.get_by_test_id("reporting-drill-panel")
    expect(panel).to_be_visible()

    assert len(drill_requests) == 1
    date_filters = [f for f in drill_requests[0]["filters"] if f["field"] == "createdDate"]
    # A grain-aware drill emits a RANGE (gte + lt), never a bare eq on the
    # clicked bucket value.
    assert {f["op"] for f in date_filters} == {"gte", "lt"}
    gte_filter = next(f for f in date_filters if f["op"] == "gte")
    lt_filter = next(f for f in date_filters if f["op"] == "lt")
    assert gte_filter["value"] == "2026-01-01"
    assert lt_filter["value"] == "2026-02-01"


SEQ_COLLISION_DASH = {
    "kind": "dashboard",
    "schemaVersion": 1,
    "title": "e2e seq dashboard",
    "globalFilters": [],
    "cards": [
        {
            "id": "n100",
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


def test_reopen_dashboard_then_add_card_does_not_collide_with_persisted_id(nexora_server, page):
    """Review finding 2: reopening a saved dashboard whose first card already
    uses the persisted id n100 (e.g. minted by an add/duplicate in an earlier
    session), entering edit mode, and adding a new card via the add-card tile
    must NOT mint another n100 -- open() has to seed state.seq past the
    highest existing n-/dup-prefixed numeric id in the loaded definition
    instead of always resetting it to 100.
    """
    _login(page, nexora_server)
    _stub_dashboard_report(page, "e2e-dash-seq", SEQ_COLLISION_DASH)
    page.route(
        "**/api/reporting/run",
        lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(RUN_STUB_SIMPLE)
        ),
    )

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    expect(page.get_by_test_id("rdb-card")).to_have_count(1)

    page.get_by_test_id("rdb-edit-toggle").click()  # Edit -> enter editing mode
    page.get_by_test_id("rdb-add-kpi").click()

    cards = page.get_by_test_id("rdb-card")
    expect(cards).to_have_count(2)
    ids = [cards.nth(i).get_attribute("data-card-id") for i in range(2)]
    assert len(set(ids)) == 2, f"duplicate data-card-id after add: {ids}"
    assert "n100" in ids  # the originally persisted card is untouched


def test_effective_filters_keeps_both_bounds_of_a_same_field_range(nexora_server, page):
    """Task 61: effectiveFilters() used to merge card.definition.filters +
    globalFilters + filterOverrides keyed by field with last-write-wins
    (`byField[f.field] = f`) -- so two DIFFERENT filters on the SAME field
    (e.g. a range split across two bound filters, gte + lte) silently
    collapsed to just the last one applied, dropping the other bound and
    widening the card's query. Both bounds must now survive into the
    run payload posted to /api/reporting/run.
    """
    _login(page, nexora_server)
    dash_definition = {
        "kind": "dashboard",
        "schemaVersion": 1,
        "title": "e2e same-field range dashboard",
        "globalFilters": [],
        "cards": [
            {
                "id": "k1",
                "type": "kpi",
                "span": 3,
                "title": "Documents in range",
                "definition": {
                    "source": "workitems",
                    "metrics": [{"field": "id", "agg": "count"}],
                    "columns": [],
                    "filters": [
                        {"field": "createdDate", "op": "gte", "value": "2026-01-01"},
                        {"field": "createdDate", "op": "lte", "value": "2026-03-31"},
                    ],
                },
                "filterOverrides": [],
            }
        ],
    }
    _stub_dashboard_report(page, "e2e-dash-samefield", dash_definition)

    run_calls = []

    def fulfill_run(route):
        run_calls.append(route.request.post_data_json or {})
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"columns": [{"field": "id", "header": "Count"}], "rows": [[42]], "rowCount": 1}
            ),
        )

    page.route("**/api/reporting/run", fulfill_run)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    # Sync point before inspecting the captured payload, same idiom as the
    # global-filter-popover test above.
    expect(page.get_by_test_id("rdb-kpi-value")).to_have_text("42")

    assert len(run_calls) == 1
    date_filters = [f for f in run_calls[0]["filters"] if f["field"] == "createdDate"]
    assert {(f["op"], f["value"]) for f in date_filters} == {
        ("gte", "2026-01-01"),
        ("lte", "2026-03-31"),
    }


def test_report_card_runs_definition_unmodified(nexora_server, page):
    """Whole-report card: POSTs the adopted definition as-is (grain, filters,
    sort intact, plus compare: true), fires the zero-column grand-total
    clone, and renders KPI band + chart + stat card + collapsed table."""
    _login(page, nexora_server)
    _stub_gfilter_catalog(page)

    reports_list = [
        {
            "id": 601,
            "name": "Documents per month",
            "ownerName": "Admin",
            "updatedAt": "2026-07-01T00:00:00Z",
            "visibility": "private",
            "owned": True,
            "kind": "line",
        },
    ]
    adopted_definition = {
        "source": "workitems",
        "metrics": [{"field": "id", "agg": "count"}],
        "columns": [{"field": "createdDate", "grain": "month"}],
        "filters": [{"field": "status", "op": "eq", "value": "open"}],
        "sort": [{"field": "createdDate", "dir": "asc"}],
        "chartType": "line",
    }

    def handle_reports(route):
        if route.request.method == "POST":
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps({"id": 9, "ok": True})
            )
        else:
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps(reports_list)
            )

    page.route("**/api/reporting/reports", handle_reports)
    page.route(
        "**/api/reporting/reports/601",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "id": 601,
                    "name": "Documents per month",
                    "definition": adopted_definition,
                    "visibility": "private",
                    "owned": True,
                    "canEdit": True,
                }
            ),
        ),
    )

    posted = []

    def fulfill_run(route):
        body = route.request.post_data_json or {}
        posted.append(body)
        if not body.get("columns"):
            # the zero-column grand-total clone the whole-report card fires
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"columns": [{"field": "id", "header": "Count"}], "rows": [[12]], "rowCount": 1}
                ),
            )
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "columns": [
                        {"field": "createdDate", "header": "Month"},
                        {"field": "id", "header": "Count"},
                    ],
                    "rows": [["2026-01-01", 5], ["2026-02-01", 7]],
                    "rowCount": 2,
                }
            ),
        )

    page.route("**/api/reporting/run", fulfill_run)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-dashboard").click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()

    page.get_by_test_id("rdb-add-report").click()
    expect(page.get_by_test_id("rdb-card")).to_have_count(1)
    expect(page.locator('[data-testid="rdb-card"][data-type="report"]')).to_have_count(1)

    page.get_by_test_id("rdb-card-configure").click()
    picker = page.get_by_test_id("rdb-report-picker")
    expect(picker).to_be_visible()
    page.get_by_test_id("rdb-report-pick").first.click()

    # The whole report: KPI band (Simple's own markup, rdb- prefixed testids),
    # chart canvas, grand-total stat card, table collapsed behind its toggle.
    expect(page.get_by_test_id("rdb-report-kpis")).to_be_visible()
    expect(page.get_by_test_id("rdb-rs-kpi-total")).to_contain_text("12")
    expect(page.locator('[data-testid="rdb-report-chartcard"] canvas')).to_be_visible()
    expect(page.get_by_test_id("rdb-report-stat")).to_contain_text("12")
    expect(page.get_by_test_id("rdb-report-table")).to_be_hidden()
    expect(page.get_by_test_id("rdb-report-table-toggle")).to_have_text("Show table")

    grained = [b for b in posted if (b.get("columns") or [{}])[0].get("grain") == "month"]
    assert grained, "definition lost its grain on the way to /run"
    assert grained[0]["filters"] == adopted_definition["filters"]
    assert grained[0]["sort"] == adopted_definition["sort"]
    assert grained[0].get("compare") is True, "whole-report run must ask for the prior period"
    totals = [b for b in posted if not b.get("columns")]
    assert totals and totals[0]["filters"] == adopted_definition["filters"]
    assert "compare" not in totals[0] and "forecast" not in totals[0]


def test_whole_report_card_keeps_saved_colours_axis_forecast_and_table(nexora_server, page):
    """The card draws through the Simple pane's own builders: saved series
    colours and right-axis picks reach the Chart.js datasets, the forecast
    tail is drawn per series, and Show table reveals the full grid with its
    forecast rows."""
    _login(page, nexora_server)
    _stub_gfilter_catalog(page)
    definition = {
        "source": "workitems",
        "metrics": [{"metric": "id_count"}, {"metric": "backlog_total"}],
        "columns": [{"field": "createdDate", "grain": "month"}],
        "filters": [],
        "sort": [],
        "chartType": "line",
        "style": {
            "colors": {"id_count": "#00aa00", "backlog_total": "#ff0000"},
            "rightAxis": ["backlog_total"],
        },
        "forecast": {"enabled": True, "horizon": 2},
    }
    dash = {
        "kind": "dashboard",
        "schemaVersion": 1,
        "title": "e2e whole report",
        "globalFilters": [],
        "cards": [
            {
                "id": "r1",
                "type": "report",
                "span": 12,
                "title": "Imports vs backlog",
                "definition": definition,
                "filterOverrides": [],
            }
        ],
    }
    _stub_dashboard_report(page, "e2e-dash-whole", dash)

    def fulfill_run(route):
        body = route.request.post_data_json or {}
        if not body.get("columns"):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "columns": [
                            {"field": "id_count", "header": "Count"},
                            {"field": "backlog_total", "header": "Backlog"},
                        ],
                        "rows": [[12, 90]],
                        "rowCount": 1,
                    }
                ),
            )
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "columns": [
                        {"field": "createdDate", "header": "Month"},
                        {"field": "id_count", "header": "Count"},
                        {"field": "backlog_total", "header": "Backlog"},
                    ],
                    "rows": [["2026-01-01", 5, 100], ["2026-02-01", 7, 90]],
                    "rowCount": 2,
                    "forecast": {
                        "anchor": "2026-02-01",
                        "buckets": ["2026-03-01", "2026-04-01"],
                        "series": [
                            {
                                "field": "id_count",
                                "values": [8, 9],
                                "upper": [10, 11],
                                "lower": [6, 7],
                            },
                            {
                                "field": "backlog_total",
                                "values": [80, 70],
                                "upper": [90, 80],
                                "lower": [70, 60],
                            },
                        ],
                    },
                }
            ),
        )

    page.route("**/api/reporting/run", fulfill_run)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").filter(has_text="e2e whole report").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()

    canvas = page.locator('[data-testid="rdb-report-chartcard"] canvas')
    expect(canvas).to_be_visible()
    page.wait_for_function(
        "() => { const c = document.querySelector('[data-testid=\"rdb-report-chartcard\"] canvas');"
        " return !!(c && window.Chart && Chart.getChart(c)); }"
    )
    datasets = page.evaluate(
        "() => { const c = document.querySelector('[data-testid=\"rdb-report-chartcard\"] canvas');"
        " return Chart.getChart(c).data.datasets.map(d => [d.borderColor, d.yAxisID || 'y', !!d._forecast]); }"
    )
    real = [d for d in datasets if not d[2]]
    assert [d[0] for d in real] == ["#00aa00", "#ff0000"], datasets
    assert [d[1] for d in real] == ["y", "y2"], datasets
    assert sum(1 for d in datasets if d[2]) == 2, datasets  # one forecast tail per series

    expect(page.get_by_test_id("rdb-rs-kpi-total")).to_contain_text("12")
    expect(page.get_by_test_id("rdb-report-stat")).to_contain_text("12")
    expect(page.get_by_test_id("rdb-report-stat")).to_contain_text("90")

    expect(page.get_by_test_id("rdb-report-table")).to_be_hidden()
    page.get_by_test_id("rdb-report-table-toggle").click()
    expect(page.get_by_test_id("rdb-report-table")).to_be_visible()
    expect(page.get_by_test_id("rdb-report-table-toggle")).to_have_text("Hide table")
    expect(page.get_by_test_id("rdb-rs-forecast-row")).to_have_count(2)


# #174: a saved report with a SECOND dimension. Before the fix the card
# renderers read a fixed column 1 as the value, so the breakdown column
# ("Invoice"/"Contract") landed in the value lookup, every row collapsed onto
# a repeated x-label and the card drew one flat zero line -- while the same
# report charted correctly in the Simple result view.
MULTI_SERIES_DASH = {
    "kind": "dashboard",
    "schemaVersion": 1,
    "title": "e2e multi-series dashboard",
    "globalFilters": [],
    "cards": [
        {
            "id": "c1",
            "type": "line",
            "span": 6,
            "title": "Documents per month / process",
            "definition": {
                "source": "workitems",
                "metrics": [{"field": "id", "agg": "count"}],
                "columns": [{"field": "createdDate", "grain": "month"}, {"field": "process"}],
                "filters": [],
            },
            "filterOverrides": [],
        }
    ],
}

# 3 months x 2 processes -- the (dim1 x dim2) cross-product a two-dimension
# run returns, in the column order [dim1, dim2, metric].
MULTI_SERIES_ROWS = [
    ["2026-01", "Invoice", 12],
    ["2026-01", "Contract", 5],
    ["2026-02", "Invoice", 18],
    ["2026-02", "Contract", 3],
    ["2026-03", "Invoice", 9],
    ["2026-03", "Contract", 7],
]


def _stub_multi_series_run(page):
    def fulfill_run(route):
        posted = route.request.post_data_json or {}
        if posted.get("rowLimit") == 100:  # the drill drawer's own detail-row request
            payload = {
                "columns": [{"field": "createdDate", "header": "Created"}],
                "rows": [["2026-01"]],
                "rowCount": 1,
                "truncated": False,
            }
        else:  # the card's own aggregate run
            payload = {
                "columns": [
                    {"field": "createdDate", "header": "Month"},
                    {"field": "process", "header": "Process"},
                    {"field": "id", "header": "Count"},
                ],
                "rows": MULTI_SERIES_ROWS,
                "rowCount": len(MULTI_SERIES_ROWS),
            }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("**/api/reporting/run", fulfill_run)


def test_line_card_pivots_second_dimension_into_series(nexora_server, page):
    """#174: a two-dimension report on a chart card renders one colored,
    named series per second-dimension value -- the same pivot the Simple
    result view does -- instead of a single flat zero line.
    """
    _login(page, nexora_server)
    _stub_dashboard_report(page, "e2e-dash-multiseries", MULTI_SERIES_DASH)
    _stub_multi_series_run(page)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()

    canvas = page.locator('[data-testid="rdb-card"][data-card-id="c1"] canvas')
    expect(canvas).to_be_visible()
    chart = canvas.evaluate(
        "(el) => { const c = Chart.getChart(el); return { labels: c.data.labels, "
        "legend: c.options.plugins.legend.display, "
        "sets: c.data.datasets.map(d => ({label: d.label, data: d.data, color: d.borderColor})) }; }"
    )

    assert chart["labels"] == ["2026-01", "2026-02", "2026-03"]
    # Series ordered by total desc (Invoice 39 > Contract 15), one color each.
    assert [s["label"] for s in chart["sets"]] == ["Invoice", "Contract"]
    assert [s["data"] for s in chart["sets"]] == [[12, 18, 9], [5, 3, 7]]
    assert chart["sets"][0]["color"] != chart["sets"][1]["color"]
    # Named series need a key; single-series cards keep the legend off.
    assert chart["legend"] is True


def test_multi_series_card_click_drills_on_axis_and_series(nexora_server, page):
    """#174 drill-through: clicking a point on a pivoted card must carry the
    clicked SERIES as well as the x bucket -- two chips, not one -- otherwise
    clicking one process's point drills into every process for that month.
    """
    _login(page, nexora_server)
    _stub_dashboard_report(page, "e2e-dash-multiseries-drill", MULTI_SERIES_DASH)
    page.route(
        "**/api/reporting/sources",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                [
                    {
                        "id": "workitems",
                        "label": "Workitems",
                        "kind": "curated",
                        "processes": [],
                        "fields": [
                            {
                                "field": "createdDate",
                                "label": "Created",
                                "type": "date",
                                "grainable": True,
                                "filterable": True,
                            },
                            {
                                "field": "process",
                                "label": "Process",
                                "type": "string",
                                "grainable": False,
                                "filterable": True,
                            },
                        ],
                    }
                ]
            ),
        ),
    )
    page.route(
        "**/api/reporting/metrics",
        lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({})),
    )
    _stub_multi_series_run(page)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()

    canvas = page.locator('[data-testid="rdb-card"][data-card-id="c1"] canvas')
    expect(canvas).to_be_visible()
    # Chart.js animates points in on mount -- same settle wait as
    # test_line_card_chart_click_opens_drill_panel above.
    page.wait_for_timeout(1200)
    point = canvas.evaluate(
        "(el) => { const c = Chart.getChart(el); const meta = c.getDatasetMeta(0); "
        "const r = el.getBoundingClientRect(); "
        "return { x: r.left + meta.data[0].x, y: r.top + meta.data[0].y }; }"
    )
    page.mouse.click(point["x"], point["y"])

    expect(page.get_by_test_id("reporting-drill-panel")).to_be_visible()
    chips = page.get_by_test_id("reporting-drill-chips").locator(".reporting-drill-chip")
    expect(chips).to_have_count(2)
