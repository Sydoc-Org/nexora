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
import re

from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")


PIECE_OF = {
    "kpi": "kpi",
    "chart": "chart",
    "line": "chart",
    "bar": "chart",
    "donut": "chart",
    "table": "table",
    "report": "report",
}


def _add_card_via_mask(page, card_type, report_name):
    """Add a card the way the UI does: open the add-card overlay from the grid
    tile, pick the saved report, then take one piece of the rendered report
    (a KPI tile, the chart, the table or the whole report) and close."""
    page.get_by_test_id("rdb-add-tile").click()
    mask = page.get_by_test_id("rdb-add-mask")
    expect(mask).to_be_visible()
    mask.get_by_test_id("rdb-mask-report").filter(has_text=report_name).click()
    expect(mask.get_by_test_id("rdb-pick-report")).to_be_visible()
    piece = PIECE_OF[card_type]
    if piece == "report":
        mask.get_by_test_id("rdb-pick-report").click()
    else:
        expect(mask.get_by_test_id("rdb-pick-report-body")).to_be_visible()
        mask.get_by_test_id(f"rdb-pick-{piece}").first.click(force=True)
    mask.get_by_test_id("rdb-add-mask-close").click()
    expect(mask).to_be_hidden()


def _as_reference_cards(definition):
    """Fixtures still describe cards the old way (a copied definition plus a
    draw type). Turn each into a reference card -- reportId 'src-<card id>',
    the piece it maps to -- and return the per-report payloads the
    /api/reporting/reports/<id> stub must answer with."""
    reports = {}
    for c in definition.get("cards", []):
        if "definition" not in c or "reportId" in c:
            continue
        rid = f"src-{c['id']}"
        reports[rid] = {"id": rid, "name": c.get("title") or rid, "definition": c["definition"]}
        c["reportId"] = rid
        c["type"] = PIECE_OF.get(c.get("type"), "report")
        if c["type"] == "kpi":
            c.setdefault("kpiIndex", 0)
    return reports


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

    # #214: the library card's own "..." menu must say "Delete dashboard",
    # not "Delete report", for a dashboard-kind card. The kebab/menu are
    # siblings of the card button inside .rs-card-wrap, not descendants of it.
    card = page.get_by_test_id("rs-card").first
    page.get_by_test_id("rs-card-kebab").first.click()
    expect(page.get_by_test_id("rs-card-delete").first).to_have_text("Delete dashboard")
    page.get_by_test_id("rs-card-kebab").first.click()  # close before navigating away

    card.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    expect(page.get_by_test_id("rs-result")).to_be_hidden()


def _stub_dashboard_report(page, report_id, definition, reports=None):
    """Library list + GET-by-id stubs for one dashboard. Cards written the old
    way become reference cards (see _as_reference_cards); `reports` adds more
    {id: {id, name, definition}} payloads the by-id stub should answer."""
    payloads = dict(reports or {})
    payloads.update(_as_reference_cards(definition))

    def by_id(route):
        rid = route.request.url.rstrip("/").rsplit("/", 1)[-1]
        if rid in payloads:
            body = dict(payloads[rid], visibility="private", owned=True, canEdit=True)
        else:
            body = {
                "id": report_id,
                "name": definition["title"],
                "definition": definition,
                "visibility": "private",
                "owned": True,
                "canEdit": True,
            }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    page.route("**/api/reporting/reports/*", by_id)
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
        "**/api/reporting/measures",
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
    expect(
        page.get_by_test_id("rdb-rs-kpi-total").locator(".reporting-ledger-kpi-value")
    ).to_have_text("1,204")
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
    expect(
        page.get_by_test_id("rdb-rs-kpi-total").locator(".reporting-ledger-kpi-value")
    ).to_have_text("999")
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
    expect(
        page.get_by_test_id("rdb-rs-kpi-total").locator(".reporting-ledger-kpi-value")
    ).to_have_text("1,204")
    assert run_calls[-1]["filters"] == [{"field": "status", "op": "eq", "value": "Open"}]

    override_chip = page.get_by_test_id("rdb-card-filter")
    expect(override_chip).to_have_count(1)
    override_chip.get_by_test_id("rdb-card-filter-remove").click()

    expect(page.get_by_test_id("rdb-card-filter")).to_have_count(0)
    expect(
        page.get_by_test_id("rdb-rs-kpi-total").locator(".reporting-ledger-kpi-value")
    ).to_have_text("500")
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


SEQ_COLLISION_DASH = {
    "kind": "dashboard",
    "schemaVersion": 1,
    "title": "e2e seq dashboard",
    "globalFilters": [],
    "cards": [
        {
            "id": "n100",  # minted by an earlier add -- the next add must not reuse it
            "type": "kpi",
            "span": 3,
            "title": "Count",
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
    session), entering edit mode, and adding a new card via the add-card mask
    must NOT mint another n100 -- open() has to seed state.seq past the
    highest existing n-/dup-prefixed numeric id in the loaded definition
    instead of always resetting it to 100.
    """
    _login(page, nexora_server)
    _stub_dashboard_report(
        page,
        "e2e-dash-seq",
        SEQ_COLLISION_DASH,
        reports={"601": {"id": 601, "name": "Documents per month", "definition": MASK_DEFINITION}},
    )
    # The library lists the dashboard AND a report the add-card overlay can offer.
    page.route(
        "**/api/reporting/reports",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                [
                    {
                        "id": "e2e-dash-seq",
                        "name": "e2e seq dashboard",
                        "ownerName": "Admin",
                        "updatedAt": "2026-07-01T00:00:00Z",
                        "visibility": "private",
                        "owned": True,
                        "kind": "dashboard",
                    },
                    MASK_REPORTS[0],
                ]
            ),
        ),
    )
    page.route(
        "**/api/reporting/run",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            # Shape matches MASK_DEFINITION (one dimension + the count), so the
            # overlay's KPI band has a tile to pick.
            body=json.dumps(
                {
                    "columns": [
                        {"field": "status", "header": "Status"},
                        {"field": "id", "header": "Count"},
                    ],
                    "rows": [["open", 4]],
                    "rowCount": 1,
                }
            ),
        ),
    )

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    expect(page.get_by_test_id("rdb-card")).to_have_count(1)

    page.get_by_test_id("rdb-edit-toggle").click()  # Edit -> enter editing mode
    _add_card_via_mask(page, "kpi", "Documents per month")

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
    expect(
        page.get_by_test_id("rdb-rs-kpi-total").locator(".reporting-ledger-kpi-value")
    ).to_have_text("42")

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

    _add_card_via_mask(page, "report", "Documents per month")
    expect(page.get_by_test_id("rdb-card")).to_have_count(1)
    expect(page.locator('[data-testid="rdb-card"][data-type="report"]')).to_have_count(1)

    # The whole report: KPI band (Simple's own markup, rdb- prefixed testids),
    # chart canvas, table collapsed behind its toggle. The band's own total
    # card carries the grand total from the zero-column clone.
    expect(page.get_by_test_id("rdb-report-kpis")).to_be_visible()
    expect(page.get_by_test_id("rdb-rs-kpi-total")).to_contain_text("12")
    expect(page.locator('[data-testid="rdb-report-chartcard"] canvas')).to_be_visible()
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


def test_report_card_zero_dim_totals_without_second_run(nexora_server, page):
    """I1: a saved report with metrics but ZERO dimensions/columns (a pure
    "Total X this period" report, no breakdown) must still show its total --
    from the breakdown run's own first row, mirroring Simple's runCurrent
    `hasMetrics && !dims` setGrandTotals branch -- and must NOT fire a second
    /api/reporting/run POST to get there: for this shape the breakdown run's
    own result already IS the total, so there is nothing left to clone."""
    _login(page, nexora_server)
    _stub_gfilter_catalog(page)

    reports_list = [
        {
            "id": 602,
            "name": "Open workitems total",
            "ownerName": "Admin",
            "updatedAt": "2026-07-01T00:00:00Z",
            "visibility": "private",
            "owned": True,
            "kind": "kpi",
        },
    ]
    adopted_definition = {
        "source": "workitems",
        "metrics": [{"field": "id", "agg": "count"}],
        "columns": [],
        "filters": [{"field": "status", "op": "eq", "value": "open"}],
        "sort": [],
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
        "**/api/reporting/reports/602",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "id": 602,
                    "name": "Open workitems total",
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
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"columns": [{"field": "id", "header": "Count"}], "rows": [[42]], "rowCount": 1}
            ),
        )

    page.route("**/api/reporting/run", fulfill_run)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-dashboard").click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()

    _add_card_via_mask(page, "report", "Open workitems total")
    expect(page.get_by_test_id("rdb-card")).to_have_count(1)

    # Zero-dim: no chart, and no Buckets/Avg/Peak card (nothing to
    # distribute) -- but the labelled total still renders, from the breakdown
    # run's own (only) row.
    expect(page.get_by_test_id("rdb-report-kpis")).to_be_visible()
    expect(page.get_by_test_id("rdb-rs-kpi-total")).to_contain_text("42")
    expect(page.get_by_test_id("rdb-rs-kpi-stats-title")).to_have_count(0)
    expect(page.locator('[data-testid="rdb-report-chartcard"]')).to_be_hidden()

    # Two /api/reporting/run calls in total: the add-card overlay's render of
    # the report, then the card's own -- and NO zero-column clone for a
    # zero-dim report (the breakdown run already returned the total).
    assert len(posted) == 2, posted
    assert all(b.get("columns") == [] and b.get("compare") is True for b in posted), posted


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

    posted = []

    def fulfill_run(route):
        body = route.request.post_data_json or {}
        posted.append(body)
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
    expect(page.get_by_test_id("rdb-rs-kpi-total-extra")).to_contain_text("90")

    expect(page.get_by_test_id("rdb-report-table")).to_be_hidden()
    page.get_by_test_id("rdb-report-table-toggle").click()
    expect(page.get_by_test_id("rdb-report-table")).to_be_visible()
    expect(page.get_by_test_id("rdb-report-table-toggle")).to_have_text("Hide table")
    expect(page.get_by_test_id("rdb-rs-forecast-row")).to_have_count(2)

    # #10: the zero-column totals clone must genuinely drop forecast/compare
    # from the saved definition (this definition carries a real forecast, so
    # "absent" here proves the clone stripped it, not that it was never set).
    totals = [b for b in posted if not b.get("columns")]
    assert totals, "zero-column grand-total clone never fired"
    assert "forecast" not in totals[0] and "compare" not in totals[0]


def test_whole_report_card_table_toggle_and_row_drill(nexora_server, page):
    """Show table toggles the full grid; clicking a data row drills through
    (same handler as the table card), forecast rows are inert."""
    _login(page, nexora_server)
    _stub_gfilter_catalog(page)
    definition = {
        "source": "workitems",
        "metrics": [{"metric": "id_count"}],
        "columns": [{"field": "status"}],
        "filters": [],
        "sort": [],
        "chartType": "bar",
    }
    dash = {
        "kind": "dashboard",
        "schemaVersion": 1,
        "title": "e2e whole report drill",
        "globalFilters": [],
        "cards": [
            {
                "id": "r1",
                "type": "report",
                "span": 12,
                "title": "By status",
                "definition": definition,
                "filterOverrides": [],
            }
        ],
    }
    _stub_dashboard_report(page, "e2e-dash-whole-drill", dash)

    def fulfill_run(route):
        body = route.request.post_data_json or {}
        if body.get("rowLimit") == 100:
            # the drill drawer's own run (raw rows behind the clicked bucket)
            payload = {
                "columns": [{"field": "status", "header": "Status"}],
                "rows": [["closed"]],
                "rowCount": 1,
                "truncated": False,
            }
        elif not body.get("columns"):
            payload = {
                "columns": [{"field": "id_count", "header": "Count"}],
                "rows": [[9]],
                "rowCount": 1,
            }
        else:
            payload = {
                "columns": [
                    {"field": "status", "header": "Status"},
                    {"field": "id_count", "header": "Count"},
                ],
                "rows": [["open", 4], ["closed", 5]],
                "rowCount": 2,
            }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("**/api/reporting/run", fulfill_run)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").filter(has_text="e2e whole report drill").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    expect(page.locator('[data-testid="rdb-report-chartcard"] canvas')).to_be_visible()

    toggle = page.get_by_test_id("rdb-report-table-toggle")
    table = page.get_by_test_id("rdb-report-table")
    expect(table).to_be_hidden()
    toggle.click()
    expect(table).to_be_visible()
    expect(toggle).to_have_text("Hide table")
    expect(table.locator("tbody tr")).to_have_count(2)
    expect(table.locator("table")).to_have_class(re.compile(r"reporting-drill-clickable"))

    table.locator("tbody tr").nth(1).click()
    expect(page.get_by_test_id("reporting-drill-panel")).to_be_visible()
    expect(page.locator("#rdTitle")).to_have_text("By status")

    # Close the drill drawer before touching the card again -- while open it
    # covers the card's right-aligned toggle (both span the viewport's right
    # 640px at the default e2e size), so a real user closes it first too.
    page.get_by_test_id("reporting-drill-close").click()
    expect(page.get_by_test_id("reporting-drill-panel")).to_be_hidden()

    toggle.click()
    expect(table).to_be_hidden()
    expect(toggle).to_have_text("Show table")


# ---------------------------------------------------------------------------
# Add-card mask + corner resize: the card geometry (span x rows) is chosen in
# the mask, adjustable by dragging a card's bottom-right corner, and persisted
# on the card as span/rows.
# ---------------------------------------------------------------------------

MASK_REPORTS = [
    {
        "id": 601,
        "name": "Documents per month",
        "ownerName": "Admin",
        "updatedAt": "2026-07-01T00:00:00Z",
        "visibility": "private",
        "owned": True,
        "kind": "line",
    },
    {
        "id": 602,
        "name": "Raw SQL thing",
        "ownerName": "Admin",
        "updatedAt": "2026-07-01T00:00:00Z",
        "visibility": "private",
        "owned": True,
        "kind": "sql",
    },
]

MASK_DEFINITION = {
    "source": "workitems",
    "metrics": [{"field": "id", "agg": "count"}],
    "columns": [{"field": "status"}],
    "filters": [],
}


def _stub_mask_reports(page):
    """GET /api/reporting/reports -> MASK_REPORTS, POST -> a new report id,
    GET /api/reporting/reports/601 -> MASK_DEFINITION. Returns the list that
    captured POST bodies land in."""
    posted = []

    def handle_reports(route):
        if route.request.method == "POST":
            posted.append(route.request.post_data_json)
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps({"id": 88, "ok": True})
            )
        else:
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps(MASK_REPORTS)
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
                    "definition": MASK_DEFINITION,
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
                {
                    "columns": [
                        {"field": "status", "header": "Status"},
                        {"field": "id", "header": "Count"},
                    ],
                    "rows": [["open", 4], ["closed", 9]],
                    "rowCount": 2,
                }
            ),
        ),
    )
    return posted


def test_corner_drag_resizes_card_in_grid_steps_and_persists(nexora_server, page):
    """Dragging a card's bottom-right corner (rdb-card-resize) snaps its width
    to whole grid columns and its height to whole grid rows, clamping at
    12 columns; Done then autosaves the new span/rows.
    """
    _login(page, nexora_server)
    posted = _stub_mask_reports(page)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-dashboard").click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()

    _add_card_via_mask(page, "kpi", "Documents per month")
    card = page.get_by_test_id("rdb-card")
    expect(card).to_have_count(1)
    # KPI defaults: 3 columns wide, 2 rows tall (DEFAULT_SPAN / DEFAULT_ROWS).
    style = card.get_attribute("style")
    assert "span 3" in style, style
    assert "--rdb-cardrows:2" in style.replace(" ", ""), style

    # The drag snaps per column/row step, so derive the step from the live grid
    # rather than hard-coding a viewport width.
    step = page.evaluate(
        """() => {
            const g = document.getElementById('rdbGrid');
            const cs = getComputedStyle(g);
            const gap = parseFloat(cs.getPropertyValue('--rdb-gap'));
            const row = parseFloat(cs.getPropertyValue('--rdb-row'));
            return { col: (g.getBoundingClientRect().width - gap * 11) / 12 + gap,
                     row: row + gap };
        }"""
    )

    handle = page.get_by_test_id("rdb-card-resize")
    box = handle.bounding_box()
    start_x = box["x"] + box["width"] / 2
    start_y = box["y"] + box["height"] / 2

    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x + step["col"] * 3, start_y + step["row"] * 2, steps=8)
    page.mouse.up()

    style = card.get_attribute("style")
    assert "span 6" in style, style  # 3 + 3 columns
    assert "--rdb-cardrows:4" in style.replace(" ", ""), style  # 2 + 2 rows

    # Dragging past the last column clamps at the full 12 rather than
    # overflowing the grid. The taller card can push the handle below the
    # fold, where pointer events would not reach it.
    handle.scroll_into_view_if_needed()
    box = handle.bounding_box()
    far_x = min(page.viewport_size["width"] - 4, box["x"] + step["col"] * 8)
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(far_x, box["y"], steps=8)
    page.mouse.up()
    assert "span 12" in card.get_attribute("style")

    page.get_by_test_id("rdb-edit-toggle").click()  # Done -> autosave
    expect(page.get_by_test_id("reporting-toast")).to_contain_text("Dashboard saved")
    assert len(posted) == 1
    saved = posted[0]["definition"]["cards"][0]
    assert saved["span"] == 12
    assert saved["rows"] == 4


def test_add_card_overlay_takes_pieces_of_the_opened_report(nexora_server, page):
    """Add card -> pick a report -> the report renders whole in the overlay and
    every piece carries an Add button. Taking a KPI tile, the chart, the table
    and the whole report yields four reference cards ({reportId, type,
    kpiIndex}) -- no copied definition is persisted -- and each card shows only
    its piece.
    """
    _login(page, nexora_server)
    posted = _stub_mask_reports(page)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-dashboard").click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()

    page.get_by_test_id("rdb-add-tile").click()
    mask = page.get_by_test_id("rdb-add-mask")
    expect(mask).to_be_visible()
    # SQL reports are not offered.
    expect(mask.get_by_test_id("rdb-mask-report")).to_have_count(1)
    mask.get_by_test_id("rdb-mask-report").click()
    expect(mask.get_by_test_id("rdb-add-mask-title")).to_have_text("Documents per month")
    body = mask.get_by_test_id("rdb-pick-report-body")
    expect(body.locator('[data-testid="rdb-report-chartcard"] canvas')).to_be_visible()
    # The table is shown in the overlay (no toggle), with its own Add button.
    expect(body.get_by_test_id("rdb-report-table")).to_be_visible()

    mask.get_by_test_id("rdb-pick-kpi").first.click(force=True)
    expect(mask.get_by_test_id("rdb-pick-kpi").first).to_have_text("Added")
    mask.get_by_test_id("rdb-pick-chart").click(force=True)
    mask.get_by_test_id("rdb-pick-table").click()
    mask.get_by_test_id("rdb-pick-report").click()
    # The overlay stays open across picks; the grid already holds the cards.
    expect(mask).to_be_visible()
    expect(page.get_by_test_id("rdb-card")).to_have_count(4)
    mask.get_by_test_id("rdb-add-mask-close").click()
    expect(mask).to_be_hidden()

    cards = page.get_by_test_id("rdb-card")
    assert [cards.nth(i).get_attribute("data-type") for i in range(4)] == [
        "kpi",
        "chart",
        "table",
        "report",
    ]
    kpi, chart, table, whole = (cards.nth(i) for i in range(4))
    # KPI: one tile, no chart, no table. Title = report · tile caption.
    expect(kpi.get_by_test_id("rdb-rs-kpi-total")).to_be_visible()
    expect(kpi.get_by_test_id("rdb-report-chartcard")).to_be_hidden()
    expect(kpi.locator(".rdb-card-title")).to_contain_text("Documents per month ·")
    # Chart: canvas only.
    expect(chart.locator("canvas")).to_be_visible()
    expect(chart.get_by_test_id("rdb-report-kpis")).to_be_hidden()
    expect(chart.get_by_test_id("rdb-report-table")).to_be_hidden()
    # Table: grid shown, no toggle.
    expect(table.get_by_test_id("rdb-report-table")).to_be_visible()
    expect(table.get_by_test_id("rdb-report-table-toggle")).to_be_hidden()
    expect(table.get_by_test_id("rdb-report-chartcard")).to_be_hidden()
    # Whole report: everything, table behind the toggle as before.
    expect(whole.get_by_test_id("rdb-report-kpis")).to_be_visible()
    expect(whole.locator("canvas")).to_be_visible()
    expect(whole.get_by_test_id("rdb-report-table-toggle")).to_have_text("Show table")

    page.get_by_test_id("rdb-edit-toggle").click()  # Done -> autosave
    expect(page.get_by_test_id("reporting-toast").last).to_contain_text("Dashboard saved")
    saved = posted[0]["definition"]["cards"]
    assert [c["type"] for c in saved] == ["kpi", "chart", "table", "report"]
    assert all(c["reportId"] == "601" for c in saved), saved
    assert saved[0]["kpiIndex"] == 0
    assert all("definition" not in c for c in saved), "cards must reference, not copy"


def test_legacy_card_shows_notice_and_never_runs(nexora_server, page):
    """A card saved by the pre-pick dashboard (copied definition, own draw
    type, no reportId) renders a remove-and-re-add notice and fires no run."""
    _login(page, nexora_server)
    dash_definition = {
        "kind": "dashboard",
        "schemaVersion": 1,
        "title": "e2e legacy dashboard",
        "globalFilters": [],
        "cards": [
            {
                "id": "k1",
                "type": "donut",
                "span": 4,
                "title": "Old donut",
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
    # reportId present (None) keeps the fixture conversion off: legacy shape stays.
    dash_definition["cards"][0]["reportId"] = None
    _stub_dashboard_report(page, "e2e-dash-legacy", dash_definition)
    runs = []
    page.route("**/api/reporting/run", lambda r: (runs.append(1), r.fulfill(status=500)))

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    expect(page.get_by_test_id("rdb-card-legacy")).to_contain_text("older dashboard version")
    assert runs == []
