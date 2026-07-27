"""e2e: the Simple/Advanced tabs and the Simple library (Spec 2)."""

import json
import re

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")


def test_default_tab_is_simple(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    expect(page.get_by_test_id("reporting-simple")).to_be_visible()
    expect(page.get_by_test_id("reporting-field-panel")).to_be_hidden()


def test_tab_param_overrides_to_advanced(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    expect(page.get_by_test_id("reporting-field-panel")).to_be_visible()
    expect(page.get_by_test_id("reporting-simple")).to_be_hidden()


def test_tab_choice_sticks_across_reload(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    page.get_by_test_id("reporting-tab-advanced").click()
    expect(page.get_by_test_id("reporting-field-panel")).to_be_visible()
    page.goto(f"{nexora_server}/reporting")  # no ?tab param: localStorage wins
    expect(page.get_by_test_id("reporting-field-panel")).to_be_visible()
    expect(page.get_by_test_id("reporting-simple")).to_be_hidden()


def test_library_groups_and_hides_sql_kind(nexora_server, page):
    _login(page, nexora_server)
    # Seed one table report + one sql-kind report via the API from the page
    # context (cookies + CSRF available in-page).
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const mk = (name, definition) => fetch('/api/reporting/reports', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify({name, definition})
          });
          await mk('e2e simple lib', {schemaVersion: 1, source: 'docprocessing',
            visualization: 'table', title: 'e2e simple lib',
            columns: [{field: 'processname'}], filters: [], sort: [],
            scope: {clients: [], processes: []}, rowLimit: 100});
          await mk('e2e sql hidden', {kind: 'sql', target: 'statistics',
            sql: 'SELECT 1 AS x', title: 'e2e sql hidden'});
        }"""
    )
    # ?tab=simple: the seeding visit persisted 'advanced' to localStorage.
    page.goto(f"{nexora_server}/reporting?tab=simple")
    expect(page.get_by_test_id("rs-group-mine")).to_contain_text("e2e simple lib")
    expect(page.get_by_test_id("reporting-simple")).not_to_contain_text("e2e sql hidden")


def test_library_report_run_400_shows_detail_and_advanced_action(nexora_server, page):
    """A 400 from /api/reporting/run must show the server's error + detail
    (a stale saved report's actual problem), keep the report title visible,
    offer an Open-in-Advanced escape hatch, and disable Save/Export until a
    successful run replaces the error state. Opening a DIFFERENT report that
    then succeeds must clear the escape-hatch button — it must never float
    above a successful result."""
    _login(page, nexora_server)

    def _row(rid, name):
        return {
            "id": rid,
            "name": name,
            "ownerName": "Admin",
            "updatedAt": "2026-07-01T00:00:00Z",
            "visibility": "private",
            "owned": True,
            "kind": "table",
        }

    def _definition(title):
        return {
            "schemaVersion": 1,
            "source": "docprocessing",
            "visualization": "table",
            "title": title,
            "columns": [{"field": "processname"}],
            "filters": [],
            "sort": [],
            "scope": {"clients": [], "processes": []},
            "rowLimit": 100,
        }

    # Register stubs BEFORE goto — the library load fires as soon as the
    # Simple pane mounts.
    page.route(
        "**/api/reporting/reports",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                [_row("e2e-400-report", "e2e 400 report"), _row("e2e-ok-report", "e2e ok report")]
            ),
        ),
    )

    def _report_detail(route):
        name = "e2e ok report" if route.request.url.endswith("e2e-ok-report") else "e2e 400 report"
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"name": name, "definition": _definition(name), "owned": True, "canEdit": True}
            ),
        )

    page.route("**/api/reporting/reports/*", _report_detail)

    def _run(route):
        body = route.request.post_data_json or {}
        if body.get("title") == "e2e 400 report":
            route.fulfill(
                status=400,
                content_type="application/json",
                body=json.dumps(
                    {
                        "error": "This report definition is invalid or outdated.",
                        "detail": "unknown metric: 'workitem_count'",
                    }
                ),
            )
        else:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "columns": [{"field": "processname", "header": "Process"}],
                        "rows": [["acme.inv"]],
                        "truncated": False,
                        "rowCount": 1,
                        "sql": None,
                        "params": [],
                        "resolvedDates": [],
                    }
                ),
            )

    page.route("**/api/reporting/run", _run)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-group-mine").get_by_text("e2e 400 report").click()

    expect(page.get_by_test_id("rs-error")).to_contain_text("unknown metric: 'workitem_count'")
    expect(page.get_by_test_id("rs-result-title")).to_contain_text("e2e 400 report")
    expect(page.get_by_test_id("rs-error-open-advanced")).to_be_visible()
    expect(page.get_by_test_id("rs-save")).to_be_disabled()
    expect(page.get_by_test_id("rs-export")).to_be_disabled()
    expect(page.get_by_test_id("reporting-timing")).to_be_hidden()

    # Error -> success: opening a different report that runs fine must clear
    # the stale escape hatch along with the error text.
    page.get_by_test_id("rs-exit").click()
    page.get_by_test_id("rs-group-mine").get_by_text("e2e ok report").click()
    expect(page.get_by_test_id("rs-result-title")).to_contain_text("e2e ok report")
    expect(page.get_by_test_id("rs-table")).to_be_visible()
    expect(page.get_by_test_id("rs-error")).to_be_hidden()
    expect(page.get_by_test_id("rs-error-open-advanced")).to_have_count(0)
    expect(page.get_by_test_id("rs-save")).to_be_enabled()
    expect(page.get_by_test_id("rs-export")).to_be_enabled()


def test_library_card_shows_preview_band_and_type_badge(nexora_server, page):
    """A library card renders a two-band layout: a preview thumbnail on top
    with a type badge. A saved report whose server-computed previewKind is
    'line' (mirroring the real list endpoint's shape — it never sends the raw
    definition, only the derived kind) must show the LINE badge."""
    _login(page, nexora_server)

    def _row(rid, name, preview_kind=None):
        row = {
            "id": rid,
            "name": name,
            "ownerName": "Admin",
            "updatedAt": "2026-07-01T00:00:00Z",
            "visibility": "private",
            "owned": True,
            "kind": "table",
        }
        if preview_kind is not None:
            row["previewKind"] = preview_kind
        return row

    page.route(
        "**/api/reporting/reports",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps([_row("e2e-preview-line", "e2e preview line", "line")]),
        ),
    )
    page.goto(f"{nexora_server}/reporting?tab=simple")
    card = page.get_by_test_id("rs-card").first
    expect(card.locator(".rs-card-preview")).to_be_visible()
    expect(card.locator(".rs-card-badge")).to_contain_text("LINE")


def test_library_card_preview_cache_round_trips_real_values(nexora_server, page):
    """D5 contract, end-to-end: running a saved report once must write its
    real result into the preview cache (writePreviewCache, keyed off
    state.current.reportId), and the NEXT library render must surface that
    real value in the card's thumbnail -- not the deterministic seeded
    fallback used before any cache exists. Uses the zero-dim (metrics-only,
    no columns) shape so fillResult takes the 'total' cache branch:
    payload = {t: 'total', v: Number(rows[0][0])}. previewBandHtml renders
    the cached value via fmtNumber in a bare '.rs-card-total' div, versus the
    '.rs-card-total.rs-card-total-label' fallback shown pre-cache -- so the
    class list itself distinguishes real-cache from seeded-fallback."""
    _login(page, nexora_server)

    def _row(rid, name):
        return {
            "id": rid,
            "name": name,
            "ownerName": "Admin",
            "updatedAt": "2026-07-01T00:00:00Z",
            "visibility": "private",
            "owned": True,
            "kind": "table",
            "previewKind": "total",
        }

    definition = {
        "schemaVersion": 1,
        "source": "docprocessing",
        "visualization": "table",
        "title": "e2e preview cache report",
        "columns": [],
        "metrics": [{"metric": "workitem_count", "label": "Total Widgets"}],
        "filters": [],
        "sort": [],
        "scope": {"clients": [], "processes": []},
        "rowLimit": 100,
    }

    # Register stubs BEFORE goto -- the library load fires as soon as the
    # Simple pane mounts.
    page.route(
        "**/api/reporting/reports",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps([_row("e2e-preview-cache", "e2e preview cache report")]),
        ),
    )
    page.route(
        "**/api/reporting/reports/*",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "name": definition["title"],
                    "definition": definition,
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
                    "columns": [{"field": "workitem_count", "header": "Total"}],
                    "rows": [[777]],
                    "rowCount": 1,
                    "truncated": False,
                    "sql": None,
                    "params": [],
                    "resolvedDates": [],
                }
            ),
        ),
    )

    page.goto(f"{nexora_server}/reporting?tab=simple")
    total_before = page.get_by_test_id("rs-card").first.locator(".rs-card-total")
    # No cache yet -- the seeded/label fallback renders, not a real number.
    expect(total_before).to_have_class(re.compile(r"\brs-card-total-label\b"))

    page.get_by_test_id("rs-group-mine").get_by_text("e2e preview cache report").click()
    expect(page.get_by_test_id("rs-result")).to_be_visible()

    # Exit re-fetches the list and re-renders every card from scratch --
    # this is where a just-cached run's real value must now surface.
    page.get_by_test_id("rs-exit").click()
    expect(page.get_by_test_id("rs-library")).to_be_visible()
    total_after = page.get_by_test_id("rs-card").first.locator(".rs-card-total")
    expect(total_after).to_have_text("777")
    expect(total_after).not_to_have_class(re.compile(r"\brs-card-total-label\b"))


def test_wizard_opens_and_lists_measures_or_empty_state(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    page.get_by_test_id("rs-new-report").click()
    expect(page.get_by_test_id("rs-wizard")).to_be_visible()
    # Either seeded metrics render as measure chips, or the explicit empty
    # state shows — assert one of the two concretely (not just non-empty).
    measure_list = page.get_by_test_id("rs-measure-list")
    chips = measure_list.locator("button.reporting-simple-choice")
    empty = measure_list.locator("p.reporting-simple-empty")
    assert chips.count() > 0 or empty.count() > 0


def test_wizard_category_breakdown_to_result_cards(nexora_server, page):
    # Full wizard -> result run over a seeded table source + count metric:
    # measure chip pins the source, category breakdown, no date field (table
    # source), Show result renders the grand-total stat card + the chart/table.
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'wiz_users', kind: 'curated', label: 'Wizard Users',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 10});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_user_count', sourceId: 'wiz_users', label: 'Wizard user count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Wizard user count").click()
        page.get_by_test_id("rs-measure-next").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        run = page.get_by_test_id("rs-wizard-run")
        expect(run).to_be_visible()
        run.click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()
        stat = page.get_by_test_id("rs-stat-card")
        expect(stat).to_be_visible()
        expect(stat).to_contain_text("Wizard user count")
        # The seeded TEST DB always has at least the admin user.
        value = page.locator("#rsStatValue").inner_text()
        assert value.strip() not in ("", "–", "0")  # noqa: RUF001 — fmtNumber's null dash
        expect(page.get_by_test_id("rs-table-toggle")).to_be_visible()
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_timing_badge_shows_rows_and_elapsed_ms(nexora_server, page):
    """After a Simple wizard run, the masthead timing badge becomes visible
    and reports "<rows> rows · <ms> ms" for the round-trip."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'timing_users', kind: 'curated', label: 'Timing Users',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 13});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'timing_user_count', sourceId: 'timing_users', label: 'Timing user count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        badge = page.get_by_test_id("reporting-timing")
        _stub_run_ok(page)
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Timing user count").click()
        page.get_by_test_id("rs-measure-next").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()
        expect(badge).to_be_visible()
        expect(badge).to_have_text(re.compile(r"\d+ rows · \d+ ms"))
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_kpi_band_shows_total_buckets_avg(nexora_server, page):
    """After a Simple wizard run whose result has a numeric measure column,
    the KPI band renders client-computed total/buckets/avg for the rows
    already on screen (no second query)."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'kpi_users', kind: 'curated', label: 'KPI Users',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 22});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'kpi_user_count', sourceId: 'kpi_users', label: 'KPI user count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")

        # /api/reporting/run is hit twice per wizard run: once with an empty
        # columns array for the grand-total stat card, once with the real
        # breakdown. Only the breakdown response carries the numeric measure
        # column the KPI band needs, so branch on that to keep both calls
        # deterministic.
        def handler(route):
            body = route.request.post_data_json or {}
            if body.get("columns"):
                payload = {
                    "columns": [
                        {"field": "username", "header": "Username"},
                        {"field": "kpi_user_count", "header": "KPI user count"},
                    ],
                    "rows": [["alice", 4], ["bob", 5], ["carol", 3]],
                    "truncated": False,
                    "rowCount": 3,
                    "sql": None,
                    "params": [],
                    "resolvedDates": [],
                }
            else:
                payload = {
                    "columns": [{"field": "kpi_user_count", "header": "KPI user count"}],
                    "rows": [[12]],
                    "truncated": False,
                    "rowCount": 1,
                    "sql": None,
                    "params": [],
                    "resolvedDates": [],
                }
            route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

        page.route("**/api/reporting/run", handler)
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("KPI user count").click()
        page.get_by_test_id("rs-measure-next").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()

        band = page.get_by_test_id("rs-kpi-band")
        expect(band).to_be_visible()
        # total: 4 + 5 + 3; buckets: 3 rows; avg per bucket: 12 / 3;
        # peak: bob's row (5) is the largest metric value.
        expect(page.get_by_test_id("rs-kpi-total")).to_contain_text("12")
        expect(page.get_by_test_id("rs-kpi-buckets")).to_contain_text("3")
        expect(page.get_by_test_id("rs-kpi-avg")).to_contain_text("4")
        expect(page.get_by_test_id("rs-kpi-peak")).to_contain_text("5")
        expect(page.get_by_test_id("rs-kpi-peak")).to_contain_text("bob")
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


STUB_AI_DEFINITION = {
    "schemaVersion": 1,
    "source": "docprocessing",
    "visualization": "table",
    "title": "stub ai report",
    "subtitle": None,
    "columns": [{"field": "processname"}],
    "filters": [{"field": "processname", "op": "eq", "value": "acme.inv"}],
    "sort": [],
    "scope": {"clients": [], "processes": []},
    "rowLimit": 100,
    "groupBy": [],
    "sql": None,
    "sqlTarget": None,
}


def _stub_ai_build(page, definition=None, delay_s=0.0):
    import json
    import time

    body = json.dumps(
        {
            "definition": definition or STUB_AI_DEFINITION,
            "explanation": "stubbed explanation",
            "valid": True,
            "error": None,
        }
    )

    def handler(route):
        if delay_s:
            time.sleep(delay_s)
        route.fulfill(status=200, content_type="application/json", body=body)

    page.route("**/api/reporting/ai/build", handler)


def _stub_run_ok(page, capture=None):
    """Stub /api/reporting/run with a deterministic success.

    AI-flow tests fire an async runCurrent() whose real /api/reporting/run can
    error intermittently on the test DB (stale NEXORA_TEST state). The error
    path, showResultError(), hides the chips/refine bar mid-test, racing later
    clicks. Stubbing the response keeps the result UI up regardless of the
    backend. Pass `capture` (a list) to record each run payload for assertions.
    """

    def _handler(route):
        if capture is not None:
            capture.append(route.request.post_data_json)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "columns": [{"field": "processname", "header": "Process"}],
                    "rows": [["acme.inv"]],
                    "truncated": False,
                    "rowCount": 1,
                    "sql": None,
                    "params": [],
                    "resolvedDates": [],
                }
            ),
        )

    page.route("**/api/reporting/run", _handler)


def test_ai_ask_shows_loading_then_result(nexora_server, page):
    """Loading indicator appears while AI request is in-flight and hides once
    the result is ready.  We verify appearance by injecting a JS latch that
    records whether rsAiLoading was ever un-hidden, then assert on end-state.
    """
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")

    # Inject a MutationObserver that sets window.__aiLoadingWasSeen = true
    # the first time rsAiLoading.hidden flips to false — and records whether
    # the header Save button was disabled at that same moment (an out-of-page
    # expect() can't observe the in-flight window: the stub's blocking sleep
    # stalls the Playwright dispatcher until fulfillment).
    page.evaluate("""() => {
        window.__aiLoadingWasSeen = false;
        window.__saveDisabledDuringLoading = false;
        const el = document.getElementById('rsAiLoading');
        if (!el) return;
        const record = () => {
            window.__aiLoadingWasSeen = true;
            const save = document.getElementById('rsSave');
            window.__saveDisabledDuringLoading = !!(save && save.disabled);
        };
        if (!el.hidden) { record(); return; }
        const obs = new MutationObserver(() => {
            if (!el.hidden) {
                record();
                obs.disconnect();
            }
        });
        obs.observe(el, { attributes: true, attributeFilter: ['hidden'] });
    }""")

    _stub_ai_build(page, delay_s=0.8)
    _stub_run_ok(page)  # async runCurrent() run must not error and tear down the result
    page.get_by_test_id("rs-ai-prompt").fill("docs by process")
    page.get_by_test_id("rs-ai-ask").click()

    # Wait for the result to finish loading (explanation text appears).
    expect(page.get_by_test_id("rs-result")).to_be_visible()
    expect(page.get_by_test_id("rs-msg")).to_contain_text("stubbed explanation")

    # Loading indicator must be hidden again now that the result is rendered.
    expect(page.get_by_test_id("rs-ai-loading")).to_be_hidden()

    # MutationObserver must have recorded that rsAiLoading was shown during
    # the in-flight period.
    was_seen = page.evaluate("() => window.__aiLoadingWasSeen")
    assert was_seen, "rsAiLoading was never made visible during the AI request"

    # …and that Save was disabled at that in-flight moment, so a mid-draft
    # click can't save the previous result under a blank header.
    save_disabled = page.evaluate("() => window.__saveDisabledDuringLoading")
    assert save_disabled, "rsSave stayed enabled while the AI draft was in flight"


def test_saved_token_report_shows_resolved_range(nexora_server, page):
    # Seed an admin source backed by dbo.Reports (NexoraDB — always available in
    # TEST) with a grainable date column, so we can save + run a token report
    # without depending on external DBs (Octo/Generali/Statistics).
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'tok_reports', kind: 'curated', label: 'Token Test Reports',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Reports',
            columns: [
              {field: 'Name', label: 'Name', type: 'string',
               filterable: true, sortable: true},
              {field: 'CreatedAt', label: 'Created', type: 'date',
               filterable: true, sortable: true, grainable: true}
            ],
            enabled: true, sortOrder: 50});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'tok_reports_count', sourceId: 'tok_reports',
            label: 'Token report count', aggregation: 'count', format: 'int'});
          const rpt = await post('/api/reporting/reports', {
            name: 'e2e token range report',
            definition: {
              schemaVersion: 1, source: 'tok_reports', visualization: 'table',
              title: 'e2e token range report',
              columns: [{field: 'Name'}],
              filters: [{field: 'CreatedAt', op: 'between',
                         value: {token: 'last_month'}}],
              sort: [], scope: {clients: [], processes: []}, rowLimit: 100}});
          return {src: src.id, met: met.id, rpt: rpt.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        # Open it from the library — the resolved-range line must appear regardless
        # of whether there are matching rows.
        page.get_by_test_id("rs-group-mine").get_by_text("e2e token range report").click()
        expect(page.get_by_test_id("rs-msg")).to_be_visible()
        expect(page.get_by_test_id("rs-msg")).to_contain_text("→")
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              if (ids.rpt) await del('/api/reporting/reports/' + ids.rpt);
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_refine_sends_prior_context_and_replaces_result(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    seen = []

    def handler(route):
        payload = route.request.post_data_json
        seen.append(payload)
        # First call: return the base stub definition so it gets stored as the
        # prior; second call: return the refined title so the result updates.
        if len(seen) == 1:
            defn = STUB_AI_DEFINITION
            expl = "stubbed explanation"
        else:
            defn = dict(STUB_AI_DEFINITION, title="refined report")
            expl = "refined expl"
        body = json.dumps({"definition": defn, "explanation": expl, "valid": True, "error": None})
        route.fulfill(status=200, content_type="application/json", body=body)

    page.route("**/api/reporting/ai/build", handler)
    # Both the ask and the refine fire an async runCurrent(); a real run error
    # would hide the refine bar (showResultError) before the refine click below.
    _stub_run_ok(page)
    page.get_by_test_id("rs-ai-prompt").fill("docs by process")
    page.get_by_test_id("rs-ai-ask").click()
    expect(page.get_by_test_id("rs-refine-bar")).to_be_visible()
    # The bar is pre-filled with the asked question.
    expect(page.get_by_test_id("rs-refine-input")).to_have_value("docs by process")

    page.get_by_test_id("rs-refine-input").fill("only acme please")
    page.get_by_test_id("rs-refine").click()
    expect(page.get_by_test_id("rs-result-title")).to_contain_text("refined report")
    assert seen[0].get("priorQuestion") is None
    assert seen[1]["priorQuestion"] == "docs by process"
    assert seen[1]["priorDefinition"]["title"] == "stub ai report"
    assert seen[1]["question"] == "only acme please"


def test_chips_edit_and_remove_rerun_without_ai(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    _stub_ai_build(page)
    # "Ask AI" fires an async runCurrent() -> real /api/reporting/run; a backend
    # error there hits showResultError(), hiding rs-chips mid-test. Stub it (and
    # capture run payloads) so the chips stay up regardless of the backend.
    run_payloads = []
    _stub_run_ok(page, capture=run_payloads)
    page.get_by_test_id("rs-ai-prompt").fill("docs by process")
    page.get_by_test_id("rs-ai-ask").click()
    chips = page.get_by_test_id("rs-chips")
    expect(chips).to_be_visible()
    # STUB_AI_DEFINITION has filters: [{field: "processname", op: "eq", value: "acme.inv"}].
    # eq renders as '='; the field key stays raw here because the TEST env's
    # docprocessing catalog is empty (no Statistics DB), so no label resolves.
    expect(chips.get_by_test_id("rs-chip").first).to_contain_text("processname = acme.inv")

    # Edit the filter value in place; the run payload must carry the new value.
    chips.get_by_test_id("rs-chip").first.click()
    page.get_by_test_id("rs-chip-input").fill("acme.other")
    page.get_by_test_id("rs-chip-apply").click()
    expect(chips.get_by_test_id("rs-chip").first).to_contain_text("acme.other")
    assert any(
        p.get("filters") and p["filters"][0].get("value") == "acme.other" for p in run_payloads
    )

    # Remove the filter chip entirely -> "no filters" placeholder renders.
    chips.get_by_test_id("rs-chip-remove").first.click()
    expect(chips).to_contain_text("no filters")


def test_chip_labels_resolve_field_and_op(nexora_server, page):
    """Chips show the catalog field label and a symbol op, not raw codes."""
    _login(page, nexora_server)
    page.route(
        "**/api/reporting/sources",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                [
                    {
                        "id": "docprocessing",
                        "label": "Document processing",
                        "kind": "curated",
                        "processes": ["acme.inv"],
                        "fields": [
                            {
                                "field": "processname",
                                "label": "Process",
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
    _stub_ai_build(page)
    _stub_run_ok(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-ai-prompt").fill("docs by process")
    page.get_by_test_id("rs-ai-ask").click()
    chips = page.get_by_test_id("rs-chips")
    # First paint may show the raw key; the catalog-resolve re-render fixes it.
    expect(chips.get_by_test_id("rs-chip").first).to_contain_text("Process = acme.inv")


def test_wizard_result_shows_chips_and_refine_bar(nexora_server, page):
    """After a wizard run, chips and refine bar appear (not just for AI-built results)."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'wiz_chips', kind: 'curated', label: 'Wizard Chips',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 11});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_chips_count', sourceId: 'wiz_chips', label: 'Wizard chips count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Wizard chips count").click()
        page.get_by_test_id("rs-measure-next").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()

        # Chips and refine bar are now visible for wizard results too.
        chips = page.locator("#rsChips")
        expect(chips).to_be_visible()
        expect(page.get_by_test_id("rs-refine-input")).to_be_visible()

        # The wizard adds no filters, so the "no filters" placeholder chip renders.
        expect(chips).to_contain_text("no filters")

        # The refine input starts empty for a wizard result (no aiQuestion).
        expect(page.get_by_test_id("rs-refine-input")).to_have_value("")

        # Stub the AI build endpoint so refine works without a live AI key.
        refined_def = dict(STUB_AI_DEFINITION, title="wizard refined report", source="wiz_chips")
        seen_payloads = []

        def _ai_handler(route):
            seen_payloads.append(route.request.post_data_json)
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "definition": refined_def,
                        "explanation": "refined from wizard",
                        "valid": True,
                        "error": None,
                    }
                ),
            )

        page.route("**/api/reporting/ai/build", _ai_handler)

        # Refine: fill the input and submit — must send priorDefinition but NO priorQuestion.
        page.get_by_test_id("rs-refine-input").fill("only compass")
        page.get_by_test_id("rs-refine").click()
        expect(page.get_by_test_id("rs-result-title")).to_contain_text("wizard refined report")

        assert len(seen_payloads) == 1
        payload = seen_payloads[0]
        assert payload.get("priorDefinition") is not None, "priorDefinition must be sent"
        assert (
            "priorQuestion" not in payload or payload.get("priorQuestion") is None
        ), "priorQuestion must be absent for wizard result refine"
        assert payload["question"] == "only compass"
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_adjust_wizard_button_round_trip(nexora_server, page):
    """Wizard-built result shows 'Adjust'; clicking it re-opens the
    walkthrough with the previous measure choice pre-selected; running again
    re-renders the result."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'wiz_adjust', kind: 'curated', label: 'Wizard Adjust',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 12});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_adjust_count', sourceId: 'wiz_adjust', label: 'Wizard adjust count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        # Run the wizard once to get a wizard-built result.
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Wizard adjust count").click()
        page.get_by_test_id("rs-measure-next").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()

        # The "Adjust" button must be visible for wizard-built results.
        adjust_btn = page.get_by_test_id("rs-adjust-wizard")
        expect(adjust_btn).to_be_visible()

        # Click it — the wizard view opens again.
        adjust_btn.click()
        expect(page.get_by_test_id("rs-wizard")).to_be_visible()

        # The previous measure choice is still selected (is-selected class).
        expect(page.locator(".reporting-simple-choice.is-selected").first).to_be_visible()

        # Run again — the result re-renders successfully.
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()

        # The "Adjust" button is still present on the new result.
        expect(page.get_by_test_id("rs-adjust-wizard")).to_be_visible()
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_total_only_result_explains_missing_chart(nexora_server, page):
    """A 'None — just the total' wizard run shows the number card plus a
    note explaining why there is no chart."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'wiz_total_note', kind: 'curated', label: 'Wizard Total Note',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 14});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_total_note_count', sourceId: 'wiz_total_note', label: 'Total note count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Total note count").click()
        page.get_by_test_id("rs-measure-next").click()
        # pick "None — just the total" (the last button in breakdown list)
        page.get_by_test_id("rs-breakdown-list").get_by_role(
            "button", name=re.compile(r"just the total", re.I)
        ).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-stat-card")).to_be_visible()
        expect(page.get_by_test_id("rs-msg")).to_contain_text("single total")
        expect(page.get_by_test_id("rs-chart-card")).to_be_hidden()
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_chart_type_switcher(nexora_server, page):
    """The result chart card offers bar/line/pie/doughnut switching."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'wiz_chart_switch', kind: 'curated', label: 'Wizard Chart Switch',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 15});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_chart_switch_count', sourceId: 'wiz_chart_switch', label: 'Chart switch count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Chart switch count").click()
        page.get_by_test_id("rs-measure-next").click()
        # pick the first category breakdown (not 'just the total')
        page.get_by_test_id("rs-breakdown-list").get_by_role("button").first.click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-chart-card")).to_be_visible()
        expect(page.get_by_test_id("rs-chart-tools")).to_be_visible()
        page.get_by_test_id("rs-chart-pie").click()
        expect(page.get_by_test_id("rs-chart-pie")).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#rsChartCanvas")).to_be_visible()
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_saved_report_adjust_in_wizard(nexora_server, page):
    """A wizard-shaped SAVED report re-enters the wizard with choices restored,
    even in a fresh session (no in-memory wizard state)."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'wiz_saved_adj', kind: 'curated', label: 'Wizard Saved Adjust',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 16});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_saved_adj_count', sourceId: 'wiz_saved_adj', label: 'Saved adjust count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        # Build + save via wizard
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Saved adjust count").click()
        page.get_by_test_id("rs-measure-next").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()
        # Save the report: first click reveals the name input, second click saves
        page.get_by_test_id("rs-save").click()
        save_name_input = page.get_by_test_id("rs-save-name")
        expect(save_name_input).to_be_visible()
        save_name_input.fill("adjust-saved-e2e")
        page.get_by_test_id("rs-save").click()
        # Wait for the save confirmation message before navigating away
        expect(page.get_by_test_id("rs-msg")).to_be_visible()
        # Fresh page load wipes state.wiz
        page.goto(f"{nexora_server}/reporting?tab=simple")
        # Wait for library to load and report to appear
        expect(page.get_by_test_id("rs-group-mine").get_by_text("adjust-saved-e2e")).to_be_visible()
        page.get_by_test_id("rs-group-mine").get_by_text("adjust-saved-e2e").click()
        adjust = page.get_by_test_id("rs-adjust-wizard")
        expect(adjust).to_be_visible()
        adjust.click()
        expect(page.get_by_test_id("rs-wizard")).to_be_visible()
        # The previously chosen measure renders pre-selected
        expect(page.locator(".reporting-simple-choice.is-selected").first).to_be_visible()
    finally:
        # Clean up metric + source
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )
        # Delete the saved report by name
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.evaluate(
            """async () => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const res = await fetch('/api/reporting/reports').then(r => r.json());
              const r = (res || []).find(x => x.name === 'adjust-saved-e2e');
              if (r) await fetch('/api/reporting/reports/' + r.id, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
            }"""
        )


def test_show_query_reveals_sql(nexora_server, page):
    """A result offers Show query, revealing the executed SELECT."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'wiz_showsql', kind: 'curated', label: 'Show SQL Test',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 18});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_showsql_count', sourceId: 'wiz_showsql', label: 'Show SQL count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Show SQL count").click()
        page.get_by_test_id("rs-measure-next").click()
        page.get_by_test_id("rs-breakdown-list").get_by_role("button").first.click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        # Task 7: Show-query now lives in the ⋯ overflow menu — open it first.
        page.get_by_test_id("rs-more").click()
        show = page.get_by_test_id("rs-show-sql")
        expect(show).to_be_visible()
        # Collapsed by default: the panel is hidden until the user expands it.
        sql_view = page.get_by_test_id("rs-sql-view")
        expect(sql_view).to_be_hidden()
        show.click()
        expect(sql_view).to_be_visible()
        expect(page.locator("#rsSqlText")).to_contain_text("SELECT")
        # Pretty-printed (multi-line) and token-highlighted.
        assert "\n" in page.locator("#rsSqlText").inner_text()
        assert page.locator("#rsSqlText span.sql-kw").count() > 0
        # Second click re-collapses.
        show.click()
        expect(sql_view).to_be_hidden()
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_result_back_returns_to_wizard(nexora_server, page):
    """Back on a wizard-built result re-enters the wizard; X exits to library."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'wiz_back_test', kind: 'curated', label: 'Wizard Back Test',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 17});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_back_count', sourceId: 'wiz_back_test', label: 'Back test count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Back test count").click()
        page.get_by_test_id("rs-measure-next").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()
        # Back on a wizard result re-enters the wizard
        page.get_by_test_id("rs-back").click()
        expect(page.get_by_test_id("rs-wizard")).to_be_visible()
        # X (wizard close) exits to library
        page.get_by_test_id("rs-wizard-close").click()
        expect(page.get_by_test_id("rs-library")).to_be_visible()
        # Now open a fresh wizard result and use rs-exit from the result bar
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Back test count").click()
        page.get_by_test_id("rs-measure-next").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()
        page.get_by_test_id("rs-exit").click()
        expect(page.get_by_test_id("rs-library")).to_be_visible()
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_back_from_library_report_returns_to_library(nexora_server, page):
    """Back on a library-opened result returns to the library -- even when the
    definition happens to be wizard-shaped (single metric, <=3 columns). Back
    must key off where the result was opened from (its origin), not guess
    from the definition's shape (that guess is what test_result_back_
    returns_to_wizard's wizard-built case still legitimately relies on)."""
    _login(page, nexora_server)

    def _row(rid, name):
        return {
            "id": rid,
            "name": name,
            "ownerName": "Admin",
            "updatedAt": "2026-07-01T00:00:00Z",
            "visibility": "private",
            "owned": True,
            "kind": "table",
        }

    definition = {
        "schemaVersion": 1,
        "source": "stub_src",
        "visualization": "table",
        "title": "e2e origin lib report",
        "columns": [{"field": "doctype"}],
        "metrics": [{"metric": "stub_count"}],
        "filters": [],
        "sort": [],
        "scope": {"clients": [], "processes": []},
        "rowLimit": 100,
    }

    # Register stubs BEFORE goto -- the library list + catalogs fetch as soon
    # as the Simple pane mounts.
    page.route(
        "**/api/reporting/reports",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps([_row("e2e-origin-lib", "e2e origin lib report")]),
        ),
    )
    page.route(
        "**/api/reporting/reports/*",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "name": definition["title"],
                    "definition": definition,
                    "owned": True,
                    "canEdit": True,
                }
            ),
        ),
    )
    page.route(
        "**/api/reporting/sources",
        lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(WIZ_STUB_SOURCES)
        ),
    )
    page.route(
        "**/api/reporting/metrics",
        lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(WIZ_STUB_METRICS)
        ),
    )
    _stub_run_ok(page)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-group-mine").get_by_text("e2e origin lib report").click()
    expect(page.get_by_test_id("rs-result")).to_be_visible()

    page.get_by_test_id("rs-back").click()
    expect(page.get_by_test_id("rs-library")).to_be_visible()
    expect(page.get_by_test_id("rs-group-mine")).to_be_visible()
    expect(page.get_by_test_id("rs-wizard")).to_be_hidden()


def test_wizard_two_breakdowns(nexora_server, page):
    """Two category breakdowns produce a 3-column grouped result."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'wiz_two_bds', kind: 'curated', label: 'Wizard Two Breakdowns',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [
              {field: 'username', label: 'Username', type: 'string',
               filterable: true, sortable: true},
              {field: 'locale', label: 'Locale', type: 'string',
               filterable: true, sortable: true}
            ],
            enabled: true, sortOrder: 19});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_two_bds_count', sourceId: 'wiz_two_bds', label: 'Two-bd count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Two-bd count").click()
        page.get_by_test_id("rs-measure-next").click()
        bklist = page.get_by_test_id("rs-breakdown-list")
        bklist.get_by_text("Username", exact=True).click()
        bklist.get_by_text("Locale", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()
        # Table is hidden behind the toggle when there are metrics; reveal it.
        page.get_by_test_id("rs-table-toggle").click()
        headers = page.locator("#rsTableWrap table thead th")
        expect(headers).to_have_count(3)  # dim1, dim2, metric
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_two_breakdown_chart_has_series(page, nexora_server):
    """A two-breakdown result charts with one dataset per second-dim value."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'chart_two_bd', kind: 'curated', label: 'Chart Two Breakdown',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [
              {field: 'username', label: 'Username', type: 'string',
               filterable: true, sortable: true},
              {field: 'locale', label: 'Locale', type: 'string',
               filterable: true, sortable: true}
            ],
            enabled: true, sortOrder: 20});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'chart_two_bd_count', sourceId: 'chart_two_bd', label: 'Chart 2-bd count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Chart 2-bd count").click()
        page.get_by_test_id("rs-measure-next").click()
        bklist = page.get_by_test_id("rs-breakdown-list")
        # Locale first (X axis, 1 distinct value in TEST), Username second
        # (series dimension, 3 distinct values in TEST) — guarantees >= 2 series.
        bklist.get_by_text("Locale", exact=True).click()
        bklist.get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        canvas = page.locator("#rsChartCanvas")
        expect(canvas).to_be_visible()
        series = int(canvas.get_attribute("data-series"))
        assert series >= 2
        # Smoke text-pin (NOT red-first, NOT independent coverage): the canvas
        # being visible already proves mountChart did not bail with the
        # too-many-points note (chartCardNote hides the canvas). TEST cardinality
        # can't exceed 50 pivoted x-points, so this just pins the exact note text.
        too_many = page.locator(
            "#rsChartNote",
            has_text="Too many data points to chart",
        )
        expect(too_many).to_have_count(0)
        expect(page.get_by_test_id("rs-chart-stacked")).to_be_visible()
        expect(page.get_by_test_id("rs-chart-pie")).to_be_hidden()
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_chart_png_download(page, nexora_server):
    """The chart toolbar PNG button downloads a .png file of the current chart."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'chart_png_dl', kind: 'curated', label: 'Chart PNG Download',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [
              {field: 'locale', label: 'Locale', type: 'string',
               filterable: true, sortable: true}
            ],
            enabled: true, sortOrder: 21});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'chart_png_dl_count', sourceId: 'chart_png_dl', label: 'PNG dl count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("PNG dl count").click()
        page.get_by_test_id("rs-measure-next").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Locale", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-chart-card")).to_be_visible()
        with page.expect_download() as dl:
            page.get_by_test_id("rs-chart-png").click()
        assert dl.value.suggested_filename.endswith("-chart.png")
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_sqlformat_escapes_and_highlights(nexora_server, page):
    """ReportingSqlFormat.toHtml escapes every emitted piece (no raw HTML can
    reach innerHTML) and wraps tokens in classed spans."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    html = page.evaluate(
        "() => ReportingSqlFormat.toHtml(\"SELECT [a] FROM t WHERE x = '<script>' -- note\")"
    )
    assert "<script>" not in html  # escaped, not injected
    assert "&lt;script&gt;" in html
    assert '<span class="sql-kw">SELECT</span>' in html
    assert '<span class="sql-ident">[a]</span>' in html
    assert '<span class="sql-comment">-- note</span>' in html
    assert '<span class="sql-string">' in html


def test_sqlformat_marks_placeholders_and_numbers(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    html = page.evaluate(
        "() => ReportingSqlFormat.toHtml('SELECT TOP 100 * FROM t WHERE a >= ? AND b < ?')"
    )
    assert html.count('<span class="sql-param">?</span>') == 2
    assert '<span class="sql-number">100</span>' in html


def test_simple_truncation_note(nexora_server, page):
    """A library report with rowLimit:1 over dbo.Users triggers truncation; the
    rs-msg element must contain 'first 1'."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'trunc_users', kind: 'curated', label: 'Truncation Users',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 30});
          const rpt = await post('/api/reporting/reports', {
            name: 'e2e trunc note',
            definition: {
              schemaVersion: 1, source: 'trunc_users', visualization: 'table',
              title: 'e2e trunc note',
              columns: [{field: 'username'}],
              filters: [], sort: [],
              scope: {clients: [], processes: []},
              rowLimit: 1}});
          return {src: src.id, rpt: rpt.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-group-mine").get_by_text("e2e trunc note").click()
        expect(page.locator("#rsResult table")).to_be_visible(timeout=15000)
        expect(page.get_by_test_id("rs-msg")).to_contain_text("first 1")
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              if (ids.rpt) await del('/api/reporting/reports/' + ids.rpt);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_advanced_truncation_note_renders(nexora_server, page):
    """Advanced result view: when /api/reporting/run returns truncated=true and
    rowCount=5000, a .reporting-truncated-note element containing '5000' renders
    above the table."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'trunc_adv', kind: 'curated', label: 'Truncation Advanced',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 31});
          return {src: src.id};
        }"""
    )
    try:
        # Stub /run to return a truncated response with synthetic data.
        stub_body = json.dumps(
            {
                "columns": [{"field": "username", "header": "Username"}],
                "rows": [["alice"]],
                "truncated": True,
                "rowCount": 5000,
                "sql": None,
                "params": [],
                "resolvedDates": [],
            }
        )

        def _stub_run(route):
            route.fulfill(status=200, content_type="application/json", body=stub_body)

        page.route("**/api/reporting/run", _stub_run)

        # Use applyDefinition to pre-populate the builder, then click Run.
        page.wait_for_selector("[data-testid='reporting-field-panel']", state="visible")
        page.evaluate(
            """() => {
              if (window.Reporting && window.Reporting.applyDefinition) {
                window.Reporting.applyDefinition({
                  schemaVersion: 1, source: 'trunc_adv', visualization: 'table',
                  title: 'trunc adv test',
                  columns: [{field: 'username'}],
                  filters: [], sort: [],
                  scope: {clients: [], processes: []}, rowLimit: 5000
                }, 'trunc adv test', null);
              }
            }"""
        )
        page.get_by_test_id("reporting-run").click()
        note = page.locator(".reporting-truncated-note")
        expect(note).to_be_visible()
        expect(note).to_contain_text("5000")
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


# ---------------------------------------------------------------------------
# Task 7: This week / This quarter wizard presets + WIZ_TOKENS round-trip
# ---------------------------------------------------------------------------

WIZ_STUB_SOURCES = [
    {
        "id": "stub_src",
        "label": "Stub source",
        "kind": "curated",
        "processes": [],
        "fields": [
            {
                "field": "import_date",
                "label": "Import date",
                "type": "date",
                "grainable": True,
                "filterable": True,
            },
            {
                "field": "doctype",
                "label": "Doc type",
                "type": "string",
                "grainable": False,
                "filterable": True,
            },
        ],
    }
]
WIZ_STUB_METRICS = {
    "stub_src": [
        {"code": "stub_count", "label": "Stub count", "aggregation": "count"},
    ]
}


def _stub_catalogs(page):
    # MUST be registered before page.goto: the Simple pane fetches the metrics
    # catalog in initOnce() at rp:tabshown (page load), not at first wizard open.
    page.route(
        "**/api/reporting/sources",
        lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(WIZ_STUB_SOURCES)
        ),
    )
    page.route(
        "**/api/reporting/metrics",
        lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(WIZ_STUB_METRICS)
        ),
    )


def test_wizard_time_step_offers_week_and_quarter(nexora_server, page):
    _login(page, nexora_server)
    _stub_catalogs(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Stub count").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-breakdown-next").click()
    tl = page.get_by_test_id("rs-time-list")
    expect(tl.get_by_text("This week", exact=True)).to_be_visible()
    expect(tl.get_by_text("This quarter", exact=True)).to_be_visible()


def test_adjust_in_wizard_maps_this_quarter(nexora_server, page):
    """A non-wizard def filtered on {token: this_quarter} keeps 'Adjust' visible."""
    _login(page, nexora_server)
    _stub_catalogs(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    # Warm the sources cache (fetched lazily at first wizard open; the adjust
    # check reads state.sources/state.metricsBySource).
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-wizard-close").click()
    page.route(
        "**/api/reporting/run",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "columns": [{"field": "stub_count", "header": "Stub count"}],
                    "rows": [[7]],
                    "rowCount": 1,
                    "truncated": False,
                    "sql": "SELECT 7",
                    "params": [],
                }
            ),
        ),
    )
    _stub_ai_build(
        page,
        definition={
            "schemaVersion": 1,
            "source": "stub_src",
            "visualization": "table",
            "title": "quarter stub",
            "subtitle": None,
            "columns": [],
            "metrics": [{"metric": "stub_count"}],
            "filters": [
                {"field": "import_date", "op": "between", "value": {"token": "this_quarter"}}
            ],
            "sort": [],
            "scope": {"clients": [], "processes": []},
            "rowLimit": 5000,
        },
    )
    page.get_by_test_id("rs-ai-prompt").fill("total this quarter")
    page.get_by_test_id("rs-ai-ask").click()
    expect(page.get_by_test_id("rs-result")).to_be_visible()
    expect(page.get_by_test_id("rs-adjust-wizard")).to_be_visible()


def test_adjust_in_wizard_prefills_custom_range(nexora_server, page):
    """A definition with a literal between range must have its custom range
    visible in the flatpickr the moment adjustInWizard opens the wizard --
    not just applied silently on the next Show result while the picker looks
    empty."""
    _login(page, nexora_server)

    def _row(rid, name):
        return {
            "id": rid,
            "name": name,
            "ownerName": "Admin",
            "updatedAt": "2026-07-01T00:00:00Z",
            "visibility": "private",
            "owned": True,
            "kind": "table",
        }

    definition = {
        "schemaVersion": 1,
        "source": "stub_src",
        "visualization": "table",
        "title": "e2e custom range report",
        "columns": [{"field": "doctype"}],
        "metrics": [{"metric": "stub_count"}],
        "filters": [
            {"field": "import_date", "op": "between", "value": ["2026-01-01", "2026-03-31"]}
        ],
        "sort": [],
        "scope": {"clients": [], "processes": []},
        "rowLimit": 100,
    }

    # Register stubs BEFORE goto -- the library list + catalogs fetch as soon
    # as the Simple pane mounts.
    page.route(
        "**/api/reporting/reports",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps([_row("e2e-custom-range", "e2e custom range report")]),
        ),
    )
    page.route(
        "**/api/reporting/reports/*",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "name": definition["title"],
                    "definition": definition,
                    "owned": True,
                    "canEdit": True,
                }
            ),
        ),
    )
    _stub_catalogs(page)
    _stub_run_ok(page)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-group-mine").get_by_text("e2e custom range report").click()
    expect(page.get_by_test_id("rs-result")).to_be_visible()

    page.get_by_test_id("rs-adjust-wizard").click()
    expect(page.get_by_test_id("rs-wizard")).to_be_visible()
    range_input = page.locator("#rsTimeRange")
    expect(range_input).to_be_visible()
    expect(range_input).to_have_value(re.compile("2026-01-01"))


def test_wizard_back_steps_back_not_exit(nexora_server, page):
    """Back walks time -> breakdown -> measure -> library, preserving picks."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'back_users', kind: 'curated', label: 'Back Users',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 31});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'back_user_count', sourceId: 'back_users', label: 'Back user count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Back user count").click()
        page.get_by_test_id("rs-measure-next").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        expect(page.get_by_test_id("rs-wizard-run")).to_be_visible()

        back = page.get_by_test_id("rs-wizard-back")
        back.click()  # time step -> breakdown step
        expect(page.get_by_test_id("rs-wizard")).to_be_visible()
        expect(page.get_by_test_id("rs-wizard-run")).to_be_hidden()
        expect(page.locator("#rsStepBreakdown")).to_be_visible()

        back.click()  # breakdown step -> measure step
        expect(page.get_by_test_id("rs-wizard")).to_be_visible()
        expect(page.locator("#rsStepBreakdown")).to_be_hidden()

        back.click()  # measure step -> library
        expect(page.get_by_test_id("rs-wizard")).to_be_hidden()
        expect(page.get_by_test_id("rs-new-report")).to_be_visible()
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_run_shows_loading_then_result(nexora_server, page):
    """The pulsing run indicator appears while /api/reporting/run is in flight
    and is hidden once the result cards render. Localhost runs are fast, so
    visibility is latched with a MutationObserver (same idiom as the AI test)."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'wiz_runload', kind: 'curated', label: 'Run Load Test',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 19});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_runload_count', sourceId: 'wiz_runload', label: 'Run load count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.evaluate("""() => {
            window.__runLoadingWasSeen = false;
            const el = document.getElementById('rsRunLoading');
            if (!el) return;
            if (!el.hidden) { window.__runLoadingWasSeen = true; return; }
            const obs = new MutationObserver(() => {
                if (!el.hidden) {
                    window.__runLoadingWasSeen = true;
                    obs.disconnect();
                }
            });
            obs.observe(el, { attributes: true, attributeFilter: ['hidden'] });
        }""")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Run load count").click()
        page.get_by_test_id("rs-measure-next").click()
        page.get_by_test_id("rs-breakdown-list").get_by_role("button").first.click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        # Task 7: Show-query now lives in the ⋯ overflow menu — open it first.
        page.get_by_test_id("rs-more").click()
        # rs-show-sql appears only after the MAIN run response is processed,
        # which is strictly after the indicator is hidden.
        expect(page.get_by_test_id("rs-show-sql")).to_be_visible()
        expect(page.get_by_test_id("rs-run-loading")).to_be_hidden()
        expect(page.get_by_test_id("rs-stat-card")).to_be_visible()
        assert page.evaluate(
            "() => window.__runLoadingWasSeen"
        ), "rsRunLoading never became visible during the report run"
        page.screenshot(path="var/screenshots/reporting_simple_run_loading.png")
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_advanced_ai_ask_shows_loading(nexora_server, page):
    """The Advanced AI panel shows the pulsing indicator while a request is in
    flight and hides it when the draft arrives (today it only disables Ask)."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.get_by_test_id("reporting-mode-ai").click()
    page.evaluate("""() => {
        window.__aiPanelLoadingWasSeen = false;
        const el = document.getElementById('rpAiLoading');
        if (!el) return;
        if (!el.hidden) { window.__aiPanelLoadingWasSeen = true; return; }
        const obs = new MutationObserver(() => {
            if (!el.hidden) {
                window.__aiPanelLoadingWasSeen = true;
                obs.disconnect();
            }
        });
        obs.observe(el, { attributes: true, attributeFilter: ['hidden'] });
    }""")
    _stub_ai_build(page, delay_s=0.8)
    page.get_by_test_id("reporting-ai-prompt").fill("docs by process")
    page.get_by_test_id("reporting-ai-ask").click()
    expect(page.get_by_test_id("reporting-ai-def-result")).to_be_visible()
    expect(page.get_by_test_id("reporting-ai-loading")).to_be_hidden()
    assert page.evaluate(
        "() => window.__aiPanelLoadingWasSeen"
    ), "rpAiLoading never became visible during the AI request"
    page.screenshot(path="var/screenshots/reporting_advanced_ai_loading.png")


@pytest.mark.flaky_e2e
def test_simple_export_csv(nexora_server, page):
    """The Simple export control downloads CSV when the format select says so."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'csv_dl_users', kind: 'curated', label: 'CSV dl Users',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 32});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'csv_dl_count', sourceId: 'csv_dl_users', label: 'CSV dl count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("CSV dl count").click()
        page.get_by_test_id("rs-measure-next").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()
        page.get_by_test_id("rs-export-format").select_option("csv")
        with page.expect_download() as dl:
            page.get_by_test_id("rs-export").click()
        assert dl.value.suggested_filename.endswith(".csv")
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


# ---------------------------------------------------------------------------
# Task 6: drill-through — pure-transform pins + drawer e2e
# ---------------------------------------------------------------------------


def test_drill_transform_category_eq(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    dd = page.evaluate("""() => ReportingDrill.buildDrillDefinition(
        {source: 's1', columns: [{field: 'doctype'}],
         filters: [{field: 'status', op: 'eq', value: 'ok'}]},
        [{field: 'doctype', filterable: true}, {field: 'status', filterable: true}],
        [{field: 'doctype', value: 'invoice'}])""")
    assert dd["rowLimit"] == 100
    assert {"field": "doctype", "op": "eq", "value": "invoice"} in dd["filters"]
    assert {"field": "status", "op": "eq", "value": "ok"} in dd["filters"]
    assert "metrics" not in dd or not dd["metrics"]


def test_drill_transform_month_grain_bounds(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    dd = page.evaluate("""() => ReportingDrill.buildDrillDefinition(
        {source: 's1', columns: [{field: 'exportdate', grain: 'month'}], filters: []},
        [{field: 'exportdate', filterable: true, grainable: true}],
        [{field: 'exportdate', grain: 'month', value: '2026-04-01'}])""")
    assert {"field": "exportdate", "op": "gte", "value": "2026-04-01"} in dd["filters"]
    assert {"field": "exportdate", "op": "lt", "value": "2026-05-01"} in dd["filters"]


def test_drill_transform_null_group_uses_is_null(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    dd = page.evaluate("""() => ReportingDrill.buildDrillDefinition(
        {source: 's1', columns: [{field: 'doctype'}], filters: []},
        [{field: 'doctype', filterable: true}],
        [{field: 'doctype', value: null}])""")
    assert {"field": "doctype", "op": "is_null"} in dd["filters"]


def test_drill_transform_unfilterable_dim_returns_null(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    dd = page.evaluate("""() => ReportingDrill.buildDrillDefinition(
        {source: 's1', columns: [{field: 'doctype'}], filters: []},
        [{field: 'doctype', filterable: false}],
        [{field: 'doctype', value: 'x'}])""")
    assert dd is None


# Task 35's guard (`if (!dd) { toast(...); return; }` in ReportingDrill.open(),
# _reporting_drill_js.html) is what actually keeps a null drill definition
# from ever opening the drawer unfiltered -- test_drill_transform_unfilterable_
# dim_returns_null above only proves buildDrillDefinition() itself returns
# null for an unfilterable clicked field. This drives the real open() call
# (the same one row-click handlers and chart onClick handlers make) with the
# same unfilterable-dim shape, and asserts the full contract: a toast fires,
# the panel stays hidden, and _stub_run_ok's capture list shows zero requests
# reached /api/reporting/run. A regression that made open() proceed despite a
# null definition -- reopening the "drill opens unfiltered" bug Task 35 was
# fixing -- would pass the pure-transform test above but fail this one.
def test_drill_open_refuses_null_definition_with_toast(nexora_server, page):
    """open() must honor buildDrillDefinition returning null and refuse to
    proceed: no toast-then-silent-open, no panel, no outgoing request."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")

    captured = []
    _stub_run_ok(page, capture=captured)

    page.evaluate("""() => {
      ReportingDrill.open({
        definition: {source: 's1', columns: [{field: 'doctype'}], filters: []},
        fields: [{field: 'doctype', filterable: false}],
        clicked: [{field: 'doctype', value: 'x'}],
        header: 'test'
      });
    }""")

    expect(page.get_by_test_id("reporting-toast")).to_be_visible()
    expect(page.get_by_test_id("reporting-drill-panel")).to_be_hidden()
    assert (
        captured == []
    ), "no request may reach /api/reporting/run when the drill definition is null"


def test_drill_row_opens_panel(nexora_server, page):
    """Clicking an aggregate result row opens the drill drawer with rows."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'wiz_drill', kind: 'curated', label: 'Wizard Drill',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 33});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_drill_count', sourceId: 'wiz_drill', label: 'Wizard drill count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        # Same wizard-walk pattern as test_wizard_category_breakdown_to_result_cards
        # (measure -> category breakdown -> Continue -> Show result), then click an
        # aggregate row to open the drill drawer.
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Wizard drill count").click()
        page.get_by_test_id("rs-measure-next").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()
        # Table is hidden behind the toggle when there are metrics; reveal it
        # (same pattern as test_wizard_two_breakdowns).
        page.get_by_test_id("rs-table-toggle").click()
        page.locator("#rsTableWrap tbody tr").first.click()
        panel = page.get_by_test_id("reporting-drill-panel")
        expect(panel).to_be_visible()
        expect(panel.locator("tbody tr").first).to_be_visible()
        page.keyboard.press("Escape")
        expect(panel).to_be_hidden()
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_drill_row_opens_panel_with_context_chips(nexora_server, page):
    """Task 9 restyle: opening a drill renders #rdChips (testid
    reporting-drill-chips) with at least one .reporting-drill-chip -- one
    indigo chip per pre-existing definition filter, one violet chip per
    clicked-derived filter. Same wizard-walk + seed pattern as
    test_drill_row_opens_panel above."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'wiz_drill_chips', kind: 'curated', label: 'Wizard Drill Chips',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 34});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wiz_drill_chips_count', sourceId: 'wiz_drill_chips',
            label: 'Wizard drill chips count', aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        # Same wizard-walk pattern as test_drill_row_opens_panel (measure ->
        # category breakdown -> Continue -> Show result), then click an
        # aggregate row to open the drill drawer and inspect its chip row.
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Wizard drill chips count").click()
        page.get_by_test_id("rs-measure-next").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()
        page.get_by_test_id("rs-table-toggle").click()
        page.locator("#rsTableWrap tbody tr").first.click()
        panel = page.get_by_test_id("reporting-drill-panel")
        expect(panel).to_be_visible()
        chips = page.get_by_test_id("reporting-drill-chips")
        expect(chips).to_be_visible()
        assert chips.locator(".reporting-drill-chip").count() >= 1
        page.keyboard.press("Escape")
        expect(panel).to_be_hidden()
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


# ---------------------------------------------------------------------------
# Final-review fix: e2e coverage for the Advanced pane's own drill-through
# wiring (templates/js/_reporting_js.html canDrill()/renderResults()), which
# is separate from Simple's wizard-driven drill (test_drill_row_opens_panel
# above exercises Simple's _reporting_simple_js.html path over an
# Advanced-admin-seeded source). Also covers the security-relevant
# `kind !== 'sql'` exclusion guard in canDrill() with a live SQL-sandbox run.
# ---------------------------------------------------------------------------


def test_advanced_grid_drill_click_through(nexora_server, page):
    """Building a curated report directly in the Advanced builder (source
    dropdown -> field-list click for a dimension -> Add metric) and running it
    renders a drillable grid; clicking a row opens the shared drill panel with
    at least one row."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'adv_drill_users', kind: 'curated', label: 'Advanced Drill Users',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 40});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'adv_drill_count', sourceId: 'adv_drill_users', label: 'Advanced drill count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        # Reload so the builder's loadSources()/loadMetrics() catalog fetches
        # pick up the just-seeded source + metric (they were created after the
        # page's initial load above).
        page.goto(f"{nexora_server}/reporting?tab=advanced")
        # The dropdown's option value is the source's Code (registry key), not
        # the numeric SourceID returned above (that's only used for cleanup).
        page.locator('[data-testid="reporting-source-select"]').select_option(
            value="adv_drill_users"
        )
        page.locator("#rpFieldList").get_by_text("Username", exact=True).click()
        page.get_by_test_id("reporting-add-metric").click()
        page.get_by_test_id("reporting-run").click()
        table = page.locator("#rpResults table")
        expect(table).to_be_visible()
        assert "reporting-drill-clickable" in (table.get_attribute("class") or "")
        table.locator("tbody tr").first.click()
        panel = page.get_by_test_id("reporting-drill-panel")
        expect(panel).to_be_visible()
        expect(panel.locator("tbody tr").first).to_be_visible()
        page.keyboard.press("Escape")
        expect(panel).to_be_hidden()
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_drill_row_opens_workitem_panel(nexora_server, page):
    """Clicking a workitem-id link inside the drill drawer opens the shared
    NexoraWorkitemDetail panel in a read-only modal over the drawer, without
    navigating away; a plain aggregate-row click still opens the drawer as
    usual. Same source/metric seeding as test_advanced_grid_drill_click_through
    above -- the drill *request* is built from that source's fields, but the
    drill *response* is stubbed (keyed on rowLimit === 100, the drill's
    fixed page size -- see templates/js/_reporting_drill_js.html buildDrillDefinition)
    so it can carry a synthetic workitem_id column regardless of the
    underlying dbo.Users-backed source."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'wi_panel_drill', kind: 'curated', label: 'WI Panel Drill',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 41});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'wi_panel_drill_count', sourceId: 'wi_panel_drill', label: 'WI panel drill count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        # NexoraWorkitemDetail.render() fires audit/media/collaboration fetches
        # for whatever workitem id we hand it; the id here only exists in the
        # stubbed drill response below, so stub those too (minimal deterministic
        # shapes -- see templates/js/_workitem_detail_panel_js.html loadHistory /
        # loadDetailData / loadCollaborationData for the exact fields read).
        page.route(
            "**/api/get_audithistory/*",
            lambda r: r.fulfill(status=200, content_type="application/json", body="[]"),
        )
        page.route(
            "**/api/get_media_info/*",
            lambda r: r.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"media_count": 0, "fields": {}}),
            ),
        )
        page.route(
            "**/api/workitem/*/interactions",
            lambda r: r.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"priority": 0, "assigneduserid": None, "tags": [], "comments": []}
                ),
            ),
        )

        def _run_handler(route):
            body = route.request.post_data_json or {}
            if body.get("rowLimit") == 100 and body.get("visualization") == "table":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "columns": [{"field": "workitem_id", "header": "Workitem ID"}],
                            "rows": [["999901"]],
                            "truncated": False,
                            "rowCount": 1,
                            "sql": None,
                            "params": [],
                            "resolvedDates": [],
                        }
                    ),
                )
            else:
                route.continue_()

        page.route("**/api/reporting/run", _run_handler)

        page.goto(f"{nexora_server}/reporting?tab=advanced")
        page.locator('[data-testid="reporting-source-select"]').select_option(
            value="wi_panel_drill"
        )
        page.locator("#rpFieldList").get_by_text("Username", exact=True).click()
        page.get_by_test_id("reporting-add-metric").click()
        page.get_by_test_id("reporting-run").click()
        table = page.locator("#rpResults table")
        expect(table).to_be_visible()
        table.locator("tbody tr").first.click()

        panel = page.get_by_test_id("reporting-drill-panel")
        expect(panel).to_be_visible()
        wi_link = panel.locator("a.reporting-drill-wi-link")
        expect(wi_link).to_have_text("999901")

        current_url = page.url
        wi_link.click()

        modal = page.locator("#rdWiModal")
        expect(modal).to_be_visible()
        body_el = page.locator("#rdWiBody")
        expect(body_el).to_be_visible()
        assert body_el.inner_html().strip() != ""
        assert page.url == current_url  # click was intercepted, no navigation

        page.locator("#rdWiClose").click()
        expect(modal).to_be_hidden()
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )


def test_advanced_sql_sandbox_not_drillable(nexora_server, page):
    """A SQL-sandbox result is never drillable: canDrill()'s `kind !== 'sql'`
    guard (templates/js/_reporting_js.html) excludes it, so the results grid
    gets no reporting-drill-clickable class and a row click never opens the
    drill panel. The Statistics DB is absent in TEST (see test_reporting_sql.py),
    so /api/reporting/sql/run is stubbed with a deterministic 2-row response —
    same idiom as _stub_run_ok above, applied to the SQL-sandbox endpoint."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    # Pre-acknowledge the live-SQL warning via the API, then reload so the
    # builder bootstraps with acknowledged=true (mirrors
    # test_sql_run_shows_loading_indicator in test_reporting_sql.py).
    page.evaluate(
        """() => fetch('/api/reporting/sql/ack', {
        method: 'POST',
        headers: {'Content-Type': 'application/json',
                  'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
        body: '{}'
    })"""
    )
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.route(
        "**/api/reporting/sql/run",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "columns": [{"field": "x", "header": "x"}],
                    "rows": [[1], [2]],
                    "truncated": False,
                    "rowCount": 2,
                    "sql": "SELECT 1 AS x",
                    "params": [],
                }
            ),
        ),
    )
    page.locator('[data-testid="reporting-mode-sql"]').click()
    page.locator('[data-testid="reporting-sql-editor"]').fill("SELECT 1 AS x")
    page.locator('[data-testid="reporting-run"]').click()
    table = page.locator("#rpResults table")
    expect(table).to_be_visible()
    assert "reporting-drill-clickable" not in (table.get_attribute("class") or "")
    table.locator("tbody tr").first.click()
    expect(page.get_by_test_id("reporting-drill-panel")).to_be_hidden()


# Task 35: an unparseable grain-bucket label (addGrainUpper returns null) must
# never let the drill open unfiltered. Both drive ReportingDrill.open()
# directly -- the same call renderTable's row-click handler and the chart
# onClick handlers make (templates/js/_reporting_simple_js.html openDrill /
# templates/js/_reporting_js.html openDrill) -- with _stub_run_ok's capture
# list recording exactly what reaches /api/reporting/run, so the assertion is
# on the real outgoing request body, not just the pure buildDrillDefinition
# transform (see test_drill_transform_month_grain_bounds above for that).
#
# Phase-9 follow-up fix: Task 35's own fallback conflated "no raw value" with
# "unparseable" and toast-aborted a genuinely NULL date bucket (the grained
# chart's own "(empty)"/nullLabel bucket -- a real, valid case, not a parse
# failure) instead of reusing the is_null handling the non-grained branch
# already had. test_drill_null_grain_bucket_opens_with_is_null_filter below
# covers the corrected behavior; the eq-fallback test below it is unchanged
# regression coverage proving the genuinely-garbled non-null case Task 35
# fixed still works.
def test_drill_unparseable_grain_bucket_falls_back_to_eq_filter(nexora_server, page):
    """A grain bucket whose raw label can't be parsed as a date (e.g. a
    "N/A"/malformed group key) must still constrain the drill on that raw
    value -- never drop the filter and show every row. RED before the fix:
    buildDrillDefinition's clicked.forEach did a bare `return` on `!upper`,
    skipping the field's filters entirely, so the outgoing request carried
    zero constraints on exportdate."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")

    captured = []
    _stub_run_ok(page, capture=captured)

    page.evaluate("""() => {
      ReportingDrill.open({
        definition: {source: 's1', columns: [{field: 'exportdate', grain: 'month'}], filters: []},
        fields: [{field: 'exportdate', filterable: true, grainable: true}],
        clicked: [{field: 'exportdate', grain: 'month', value: 'N/A'}],
        header: 'test'
      });
    }""")

    expect(page.get_by_test_id("reporting-drill-panel")).to_be_visible()
    assert len(captured) == 1
    exportdate_filters = [f for f in captured[0]["filters"] if f["field"] == "exportdate"]
    assert exportdate_filters == [{"field": "exportdate", "op": "eq", "value": "N/A"}], (
        "unparseable grain bucket must fall back to an equality filter on the "
        "raw bucket value, never drop the constraint entirely"
    )


def test_drill_transform_month_grain_null_bucket_uses_is_null(nexora_server, page):
    """A NULL date bucket on a grained chart (rawX[i] is the raw SQL NULL,
    surfaced client-side via I18N.nullLabel) is a real, valid case -- not an
    unparseable label. buildDrillDefinition must emit the same is_null shape
    the non-grained branch already uses (see
    test_drill_transform_null_group_uses_is_null above), and must NOT also
    carry a stray date-range filter."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    dd = page.evaluate("""() => ReportingDrill.buildDrillDefinition(
        {source: 's1', columns: [{field: 'exportdate', grain: 'month'}], filters: []},
        [{field: 'exportdate', filterable: true, grainable: true}],
        [{field: 'exportdate', grain: 'month', value: null}])""")
    assert dd is not None
    assert {"field": "exportdate", "op": "is_null"} in dd["filters"]
    range_filters = [f for f in dd["filters"] if f["op"] in ("gte", "lt", "eq")]
    assert (
        range_filters == []
    ), f"a NULL grain bucket must carry only is_null, no stray range/eq filter: {range_filters}"


def test_drill_null_grain_bucket_opens_with_is_null_filter(nexora_server, page):
    """RED before the fix: a NULL date bucket on a grained chart hit the same
    fallback as a genuinely unparseable label and toast-aborted instead of
    drilling in. It must open the drawer (no toast) with the same is_null
    filter the non-grained branch already produces for a NULL group -- never
    an unfiltered request, and never a silent no-op."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")

    captured = []
    _stub_run_ok(page, capture=captured)

    page.evaluate("""() => {
      ReportingDrill.open({
        definition: {source: 's1', columns: [{field: 'exportdate', grain: 'month'}], filters: []},
        fields: [{field: 'exportdate', filterable: true, grainable: true}],
        clicked: [{field: 'exportdate', grain: 'month', value: null}],
        header: 'test'
      });
    }""")

    expect(page.get_by_test_id("reporting-drill-panel")).to_be_visible()
    expect(page.get_by_test_id("reporting-toast")).to_have_count(0)
    assert len(captured) == 1
    exportdate_filters = [f for f in captured[0]["filters"] if f["field"] == "exportdate"]
    assert exportdate_filters == [
        {"field": "exportdate", "op": "is_null"}
    ], "a NULL grain bucket must drill in with an is_null filter, not abort or go unfiltered"


# ---------------------------------------------------------------------------
# Per-process (per-client) breakdown chip -- docprocessing wizard curation.
# TEST env has no Statistics DB, so the docprocessing catalog is stubbed
# (same pattern as _stub_catalogs; the id MUST be 'docprocessing' so the
# wizard's DOCPROC_DIM_ORDER/DOCPROC_DIM_HIDE curation branch fires).
# ---------------------------------------------------------------------------

DOCPROC_WIZ_FIELDS = [
    {
        "field": "import_date",
        "label": "Import date",
        "type": "date",
        "grainable": True,
        "filterable": True,
    },
] + [
    {"field": f, "label": lbl, "type": "string", "grainable": False, "filterable": True}
    for f, lbl in [
        ("processname", "Process"),
        ("docsource", "Document Source"),
        ("doctype", "Document Type"),
        ("forwarding", "Forwarding"),
        ("ownernr", "Owner no."),
        ("propertynr", "Property No."),
        ("registered", "Registered"),
        ("tenancynr", "Tenancy no."),
        ("archiveboxno", "Archive-box No."),
        ("branch", "Branch"),
        ("client", "Client"),
        ("confidentiality", "Confidentiality"),
        ("crdname", "Creditor Name"),
        ("bankpk", "Bank PK"),  # DOCPROC_DIM_HIDE noise -- must stay hidden
        ("workitem_id", "Workitem ID"),  # DOCPROC_DIM_HIDE noise -- must stay hidden
    ]
]
DOCPROC_WIZ_SOURCES = [
    {
        "id": "docprocessing",
        "label": "Document processing",
        "kind": "curated",
        "processes": ["acme.inv", "acme.hr"],
        "fields": DOCPROC_WIZ_FIELDS,
    }
]
DOCPROC_WIZ_METRICS = {
    "docprocessing": [{"code": "doc_count", "label": "Docproc count stub", "aggregation": "count"}]
}

# 20 string fields: pins the category-chip cap (16) for generic sources.
CAP_WIZ_SOURCES = [
    {
        "id": "cap_src",
        "label": "Cap source",
        "kind": "curated",
        "processes": [],
        "fields": [
            {
                "field": "f%02d" % i,
                "label": "Field %02d" % i,
                "type": "string",
                "grainable": False,
                "filterable": True,
            }
            for i in range(20)
        ],
    }
]
CAP_WIZ_METRICS = {
    "cap_src": [{"code": "cap_count", "label": "Cap count stub", "aggregation": "count"}]
}


def _stub_wiz_catalogs(page, sources, metrics):
    # MUST be registered before page.goto (catalogs are fetched at page load).
    page.route(
        "**/api/reporting/sources",
        lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(sources)),
    )
    page.route(
        "**/api/reporting/metrics",
        lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(metrics)),
    )


def test_wizard_docprocessing_offers_process_breakdown(nexora_server, page):
    """The per-process chip is offered FIRST and noise curation still applies."""
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, DOCPROC_WIZ_SOURCES, DOCPROC_WIZ_METRICS)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Docproc count stub").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-scope-next").click()
    bklist = page.get_by_test_id("rs-breakdown-list")
    proc = bklist.locator('[data-bd-field="processname"]')
    expect(proc).to_be_visible()
    expect(proc).to_have_text("Process")  # label straight from the catalog entry
    # First CATEGORY chip (date chips render before category chips).
    first_cat = bklist.locator('[data-bd-kind="category"]').first
    assert first_cat.get_attribute("data-bd-field") == "processname"
    # All 13 candidates render (the 12 previously-visible business chips plus
    # Process): nothing is silently evicted by the cap, noise stays hidden.
    expect(bklist.locator('[data-bd-kind="category"]')).to_have_count(13)
    expect(bklist.locator('[data-bd-field="crdname"]')).to_be_visible()
    expect(bklist.locator('[data-bd-field="bankpk"]')).to_have_count(0)
    expect(bklist.locator('[data-bd-field="workitem_id"]')).to_have_count(0)


def test_wizard_process_breakdown_serializes_to_processname_column(nexora_server, page):
    """Selecting the Process chip emits columns=[{field:'processname',...}] in the run."""
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, DOCPROC_WIZ_SOURCES, DOCPROC_WIZ_METRICS)
    captured = []
    _stub_run_ok(page, capture=captured)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Docproc count stub").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-scope-next").click()
    page.get_by_test_id("rs-breakdown-list").locator('[data-bd-field="processname"]').click()
    page.get_by_test_id("rs-breakdown-next").click()
    run = page.get_by_test_id("rs-wizard-run")  # renderTimeStep() unhides it; All time default
    expect(run).to_be_visible()
    run.click()
    expect(page.get_by_test_id("rs-result")).to_be_visible()
    # runCurrent() also fires the zero-column grand-total clone; assert on the
    # payload that carries columns.
    with_cols = [p for p in captured if p.get("columns")]
    assert with_cols, f"no run payload carried columns: {captured}"
    assert with_cols[0]["columns"][0]["field"] == "processname"


def test_wizard_shows_all_category_chips_uncapped(nexora_server, page):
    """The category-chip cap is GONE: every filterable string field renders a
    chip (the coverage sort keeps rarely-provided fields at the bottom, the
    docprocessing hide-list still filters noise)."""
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, CAP_WIZ_SOURCES, CAP_WIZ_METRICS)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Cap count stub").click()
    page.get_by_test_id("rs-measure-next").click()
    bklist = page.get_by_test_id("rs-breakdown-list")
    expect(bklist.locator('[data-bd-kind="category"]')).to_have_count(20)


# ---------------------------------------------------------------------------
# Process-coverage marking: chips/measures whose field only some processes
# provide get an "n/m" badge; the chip list follows the scope picker like the
# Advanced tab's field list. Fields WITHOUT a `processes` tag are universal
# (table sources; also why the older wizard stubs above are unaffected).
# ---------------------------------------------------------------------------

COV_WIZ_SOURCES = [
    {
        "id": "docprocessing",
        "label": "Document processing",
        "kind": "curated",
        "processes": ["acme.inv", "acme.hr"],
        "fields": [
            {
                "field": "import_date",
                "label": "Import date",
                "type": "date",
                "grainable": True,
                "filterable": True,
                "processes": ["acme.inv", "acme.hr"],
            },
            {
                "field": "doctype",
                "label": "Document Type",
                "type": "string",
                "grainable": False,
                "filterable": True,
                "processes": ["acme.inv", "acme.hr"],
            },
            {
                "field": "propertynr",
                "label": "Property No.",
                "type": "string",
                "grainable": False,
                "filterable": True,
                "processes": ["acme.inv"],
            },
        ],
    }
]
COV_WIZ_METRICS = {
    "docprocessing": [
        {
            "code": "doc_count",
            "label": "Cov count stub",
            "aggregation": "count",
            "baseField": None,
            "format": "int",
        },
    ]
}


def test_wizard_chip_coverage_badge(nexora_server, page):
    """A chip whose field only some selected processes provide shows an n/m
    badge and a tooltip naming the providers; full-coverage chips stay plain."""
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, COV_WIZ_SOURCES, COV_WIZ_METRICS)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Cov count stub").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-scope-next").click()
    bklist = page.get_by_test_id("rs-breakdown-list")
    prop = bklist.locator('[data-bd-field="propertynr"]')
    expect(prop.locator(".reporting-simple-chip-cov")).to_have_text("1/2")
    assert "acme.inv" in prop.get_attribute("title")
    expect(bklist.locator('[data-bd-field="doctype"] .reporting-simple-chip-cov')).to_have_count(0)
    expect(
        bklist.locator('[data-bd-field="import_date"] .reporting-simple-chip-cov')
    ).to_have_count(0)


def test_wizard_scope_filters_chips_and_prunes_selection(nexora_server, page):
    """Unticking the only process that provides a field hides its chip and
    drops it from the selected breakdowns (Advanced-tab parity); re-ticking
    brings the chip back (unselected)."""
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, COV_WIZ_SOURCES, COV_WIZ_METRICS)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Cov count stub").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-scope-next").click()
    bklist = page.get_by_test_id("rs-breakdown-list")
    bklist.locator('[data-bd-field="propertynr"]').click()
    expect(bklist.locator('[data-bd-field="propertynr"]')).to_have_class(
        re.compile(r"\bis-selected\b")
    )
    # The scope step stays visible above the breakdown step (progressive
    # accordion) — its checkboxes re-filter the chip list live.
    page.get_by_test_id("rs-scope-list").locator('input[value="acme.inv"]').uncheck()
    expect(bklist.locator('[data-bd-field="propertynr"]')).to_have_count(0)
    expect(bklist.locator('[data-bd-field="doctype"]')).to_be_visible()
    page.get_by_test_id("rs-scope-list").locator('input[value="acme.inv"]').check()
    prop = bklist.locator('[data-bd-field="propertynr"]')
    expect(prop).to_be_visible()
    expect(prop).not_to_have_class(re.compile(r"\bis-selected\b"))


def test_sqlformat_display_and_copy_policy(nexora_server, page):
    """displayText prefers the inlined sqlDisplay; copyText returns runnable
    SQL when inlined and falls back to raw + params comment otherwise. One
    window seam serves BOTH tabs' Show-query panels."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    res = {
        "sql": "SELECT ?",
        "sqlPretty": "SELECT\n  ?",
        "sqlDisplay": "SELECT\n  'x'",
        "params": ["x"],
    }
    assert page.evaluate("(r) => ReportingSqlFormat.displayText(r)", res) == "SELECT\n  'x'"
    assert page.evaluate("(r) => ReportingSqlFormat.copyText(r)", res) == "SELECT\n  'x'"
    fb = {"sql": "SELECT ?", "sqlPretty": "SELECT\n  ?", "sqlDisplay": None, "params": ["x"]}
    assert page.evaluate("(r) => ReportingSqlFormat.displayText(r)", fb) == "SELECT\n  ?"
    assert (
        page.evaluate("(r) => ReportingSqlFormat.copyText(r)", fb) == 'SELECT ?\n-- params: ["x"]'
    )


def test_show_query_inlines_parameters_and_copies_runnable_sql(nexora_server, page):
    """D-params: the panel shows literals instead of ?, the params footer is
    gone from the DOM, and Copy writes the runnable inlined statement."""
    _login(page, nexora_server)
    _stub_catalogs(page)
    raw = (
        "SELECT TOP (100) [d] AS [d], COUNT(*) AS [n] FROM [dbo].[T] "
        "WHERE [d] >= ? AND [d] < ? GROUP BY [d]"
    )
    inlined = (
        "SELECT TOP 100 [d] AS [d], COUNT(*) AS [n] FROM [dbo].[T] "
        "WHERE [d] >= '2026-07-01' AND [d] < '2026-08-01' GROUP BY [d]"
    )

    def _handler(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "columns": [{"field": "d", "header": "D"}, {"field": "n", "header": "N"}],
                    "rows": [["2026-07-01", 7]],
                    "truncated": False,
                    "rowCount": 1,
                    "sql": raw,
                    "sqlPretty": raw,
                    "sqlDisplay": inlined,
                    "params": ["2026-07-01", "2026-08-01"],
                }
            ),
        )

    page.route("**/api/reporting/run", _handler)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Stub count").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-breakdown-list").get_by_role("button").first.click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-wizard-run").click()
    # Task 7: Show-query now lives in the ⋯ overflow menu — open it first.
    page.get_by_test_id("rs-more").click()
    show = page.get_by_test_id("rs-show-sql")
    expect(show).to_be_visible()
    # Capture clipboard writes without clipboard-read permissions.
    page.evaluate(
        "() => { window.__copied = null;"
        " navigator.clipboard.writeText = t => { window.__copied = t; return Promise.resolve(); }; }"
    )
    show.click()
    expect(page.locator("#rsSqlText")).to_contain_text("'2026-07-01'")
    assert page.locator("#rsSqlText span.sql-param").count() == 0  # no bare ? shown
    assert page.locator("#rsSqlParams").count() == 0  # footer element gone
    page.get_by_test_id("rs-sql-copy").click()
    assert page.evaluate("() => window.__copied") == inlined


def test_library_empty_groups_show_calls_to_action(nexora_server, page):
    """Empty library groups explain the next step instead of a dead end."""
    _login(page, nexora_server)
    page.route(
        "**/api/reporting/reports",
        lambda r: r.fulfill(status=200, content_type="application/json", body="[]"),
    )
    page.goto(f"{nexora_server}/reporting?tab=simple")
    expect(page.get_by_test_id("rs-group-mine")).to_contain_text(
        "You haven't saved any reports yet"
    )
    expect(page.get_by_test_id("rs-group-shared")).to_contain_text(
        "No reports have been shared with everyone yet."
    )
    expect(page.get_by_test_id("rs-group-direct")).to_contain_text(
        "No reports have been shared with you yet."
    )


def test_ai_unavailable_shows_notice_not_silent_vanish(nexora_server, page):
    """A 503 from the AI hides the bar AND tells the user why (previously the
    bar just disappeared, eating the typed question without a word)."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.route(
        "**/api/reporting/ai/build",
        lambda r: r.fulfill(
            status=503, content_type="application/json", body='{"error": "AI is not configured"}'
        ),
    )
    page.get_by_test_id("rs-ai-prompt").fill("anything")
    page.get_by_test_id("rs-ai-ask").click()
    expect(page.get_by_test_id("rs-ai-bar")).to_be_hidden()
    notice = page.get_by_test_id("rs-ai-gone")
    expect(notice).to_be_visible()
    expect(notice).to_contain_text("AI assistant is unavailable")


def test_advanced_no_rows_shows_designed_empty_state(nexora_server, page):
    """A zero-row Advanced run renders the nx-empty pattern, not a bare 'No rows.'"""
    _login(page, nexora_server)
    page.route(
        "**/api/reporting/run",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "columns": [{"field": "n", "header": "N"}],
                    "rows": [],
                    "rowCount": 0,
                    "truncated": False,
                    "sql": None,
                    "params": [],
                }
            ),
        ),
    )
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.get_by_test_id("reporting-run").click()
    empty = page.get_by_test_id("reporting-no-rows")
    expect(empty).to_be_visible()
    expect(empty).to_contain_text("No rows matched")


def test_zero_rows_shows_empty_state_hint(nexora_server, page):
    """A successful zero-row Simple-pane run always shows the no-data empty
    state plus a hint — even though the zero-column grand-total call succeeds
    and leaves the stat card visible (previously the empty state only showed
    when el('rsStatCard') was hidden, so a visible zero stat card produced a
    bare header-only grid instead)."""
    _login(page, nexora_server)
    _stub_catalogs(page)

    def handler(route):
        body = route.request.post_data_json or {}
        is_total_call = not body.get("columns")
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "columns": [
                        {"field": "import_date", "header": "Import date"},
                        {"field": "doc_count", "header": "doc_count"},
                    ],
                    "rows": [[0]] if is_total_call else [],
                    "rowCount": 0,
                    "truncated": False,
                    "sql": None,
                    "params": [],
                }
            ),
        )

    page.route("**/api/reporting/run", handler)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Stub count").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-breakdown-list").get_by_text("Doc type", exact=True).click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-wizard-run").click()

    expect(page.get_by_test_id("rs-result")).to_be_visible()
    empty = page.locator("#rsTableWrap .nx-empty")
    expect(empty).to_be_visible()
    expect(empty).to_contain_text("No data for this report")
    expect(empty).to_contain_text("Widen the time range or remove a filter.")
    # Zero rows must never render as a bare header-only grid alongside/instead
    # of the empty state.
    expect(page.locator("#rsTableWrap table")).to_have_count(0)


def test_advanced_save_shows_toast_not_alert(nexora_server, page):
    """Saving surfaces an in-page toast; no browser alert dialog fires."""
    _login(page, nexora_server)
    token = page.evaluate("() => document.querySelector('meta[name=\"csrf-token\"]').content")
    headers = {"X-CSRFToken": token, "Content-Type": "application/json"}
    page.request.post(f"{nexora_server}/api/reporting/sql/ack", headers=headers, data={})
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.locator('[data-testid="reporting-mode-sql"]').click()
    page.locator('[data-testid="reporting-sql-editor"]').fill("SELECT 1 AS x")
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.type), d.accept()))
    page.locator('[data-testid="reporting-save-as"]').click()
    page.get_by_test_id("reporting-name-input").fill("toast-save-e2e")
    page.get_by_test_id("reporting-name-ok").click()
    try:
        expect(page.get_by_test_id("reporting-toast")).to_be_visible()
        expect(page.get_by_test_id("reporting-toast")).to_contain_text("Saved")
        assert dialogs == []  # window.alert is gone from the save path
    finally:
        reports = page.request.get(f"{nexora_server}/api/reporting/reports").json()
        for r in reports:
            if r.get("name") == "toast-save-e2e":
                page.request.delete(
                    f"{nexora_server}/api/reporting/reports/{r['id']}", headers=headers
                )


def test_wizard_alltime_hint_toggles(nexora_server, page):
    """The default All-time choice warns about full-history scans; picking a
    bounded range hides the hint, coming back shows it again."""
    _login(page, nexora_server)
    _stub_catalogs(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Stub count").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-breakdown-list").get_by_role("button").first.click()
    page.get_by_test_id("rs-breakdown-next").click()
    hint = page.get_by_test_id("rs-alltime-hint")
    expect(hint).to_be_visible()  # All time is the default selection
    page.get_by_test_id("rs-time-list").get_by_text("This year", exact=True).click()
    expect(hint).to_be_hidden()
    page.get_by_test_id("rs-time-list").get_by_text("All time", exact=True).click()
    expect(hint).to_be_visible()


def test_wizard_measure_coverage_badge_and_unrunnable_hidden(nexora_server, page):
    """A sum measure over a partially-covered base field gets the n/m badge;
    a metric whose base field no allowed process provides is not offered at
    all (it could never run); count metrics stay plain."""
    metrics = {
        "docprocessing": [
            {
                "code": "doc_count",
                "label": "Cov count stub",
                "aggregation": "count",
                "baseField": None,
                "format": "int",
            },
            {
                "code": "page_sum",
                "label": "Pages stub",
                "aggregation": "sum",
                "baseField": "propertynr",
                "format": "int",
            },
            {
                "code": "ghost_sum",
                "label": "Ghost stub",
                "aggregation": "sum",
                "baseField": "ghostfield",
                "format": "int",
            },
        ]
    }
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, COV_WIZ_SOURCES, metrics)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    mlist = page.get_by_test_id("rs-measure-list")
    pages_btn = mlist.locator("button", has_text="Pages stub")
    expect(pages_btn.locator(".reporting-simple-chip-cov")).to_have_text("1/2")
    assert "acme.inv" in pages_btn.get_attribute("title")
    count_btn = mlist.locator("button", has_text="Cov count stub")
    expect(count_btn.locator(".reporting-simple-chip-cov")).to_have_count(0)
    expect(mlist.get_by_text("Ghost stub")).to_have_count(0)


# ---------------------------------------------------------------------------
# Three breakdowns: the chart caps at two dims (mountChart shows a note
# instead), so the table — the only surface that can show all three and the
# only remaining drill-through target — must render visible immediately, not
# collapsed behind the "Show table" toggle.
# ---------------------------------------------------------------------------

THREE_DIM_SOURCES = [
    {
        "id": "docprocessing",
        "label": "Document processing",
        "kind": "curated",
        "fields": [
            {
                "field": "doctype",
                "label": "Document Type",
                "type": "string",
                "grainable": False,
                "filterable": True,
            },
            {
                "field": "docsource",
                "label": "Document Source",
                "type": "string",
                "grainable": False,
                "filterable": True,
            },
            {
                "field": "propertynr",
                "label": "Property No.",
                "type": "string",
                "grainable": False,
                "filterable": True,
            },
        ],
    }
]
THREE_DIM_METRICS = {
    "docprocessing": [
        {
            "code": "doc_count",
            "label": "Count stub",
            "aggregation": "count",
            "baseField": None,
            "format": "int",
        },
    ]
}


THREE_DIM_RUN_BODY = json.dumps(
    {
        "columns": [
            {"field": "doctype", "header": "Document Type"},
            {"field": "docsource", "header": "Document Source"},
            {"field": "propertynr", "header": "Property No."},
            {"field": "doc_count", "header": "doc_count"},
        ],
        # Two propertynr values under the same (doctype, docsource) pair — the
        # chart pivot keys series on ALL remaining dims, so these become two
        # composite series ("Mail · P-1" = 7, "Mail · P-2" = 3), not one 10.
        "rows": [["Invoice", "Mail", "P-1", 7], ["Invoice", "Mail", "P-2", 3]],
        "truncated": False,
        "rowCount": 2,
        "sql": None,
        "params": [],
        "resolvedDates": [],
    }
)


def _walk_three_breakdowns(nexora_server, page, measure_label):
    page.route(
        "**/api/reporting/run",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=THREE_DIM_RUN_BODY
        ),
    )
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text(measure_label).click()
    page.get_by_test_id("rs-measure-next").click()
    bklist = page.get_by_test_id("rs-breakdown-list")
    for fld in ("doctype", "docsource", "propertynr"):
        bklist.locator(f'[data-bd-field="{fld}"]').click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-wizard-run").click()
    expect(page.get_by_test_id("rs-result")).to_be_visible()


def test_three_breakdowns_chart_composite_series_and_drill(nexora_server, page):
    """Three breakdowns chart with the first as axis and the remaining two
    joined into composite series ("Mail · P-1") — nothing collapses, no
    limitation note; the table stays reachable via the toggle and rows drill."""
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, THREE_DIM_SOURCES, THREE_DIM_METRICS)
    _walk_three_breakdowns(nexora_server, page, "Count stub")
    expect(page.locator("#rsChartCanvas")).to_be_visible()
    expect(page.locator("#rsChartNote")).to_be_hidden()
    # One series per (docsource, propertynr) combo, each with its exact value.
    chart = page.evaluate(
        "() => window.Chart && (() => {"
        "  const c = Chart.getChart(document.getElementById('rsChartCanvas'));"
        "  return c ? c.data.datasets.map(d => [d.label, d.data[0]]) : null;"
        "})()"
    )
    assert sorted(chart) == [["Mail · P-1", 7], ["Mail · P-2", 3]]
    # Charted result: table behind the toggle as usual; rows still drill.
    page.get_by_test_id("rs-table-toggle").click()
    page.locator("#rsTableWrap tbody tr").first.click()
    expect(page.get_by_test_id("reporting-drill-panel")).to_be_visible()


def test_three_breakdowns_nonadditive_charts_exact(nexora_server, page):
    """A non-additive metric (avg) charts three breakdowns too: with every
    dim in the composite series key nothing collapses in the pivot, so each
    point is one exact aggregate row — the old note-only card is gone."""
    metrics = {
        "docprocessing": [
            {
                "code": "avg_prop",
                "label": "Avg stub",
                "aggregation": "avg",
                "baseField": "propertynr",
                "format": "int",
            },
        ]
    }
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, THREE_DIM_SOURCES, metrics)
    _walk_three_breakdowns(nexora_server, page, "Avg stub")
    expect(page.locator("#rsChartCanvas")).to_be_visible()
    expect(page.locator("#rsChartNote")).to_be_hidden()
    chart = page.evaluate(
        "() => window.Chart && (() => {"
        "  const c = Chart.getChart(document.getElementById('rsChartCanvas'));"
        "  return c ? c.data.datasets.map(d => [d.label, d.data[0]]) : null;"
        "})()"
    )
    assert sorted(chart) == [["Mail · P-1", 7], ["Mail · P-2", 3]]


def test_sql_peek_footer_reveals_query_on_click(nexora_server, page):
    """Task 6: a persistent one-line query footer sits under the results,
    showing the first line of the inlined sqlDisplay. Clicking it opens the
    same Show-query panel as the rs-show-sql button (same reveal path)."""
    _login(page, nexora_server)
    _stub_catalogs(page)
    sql_display = "SELECT [d] AS [d], COUNT(*) AS [n]\nFROM [dbo].[T]\nGROUP BY [d]"

    def _handler(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "columns": [{"field": "d", "header": "D"}, {"field": "n", "header": "N"}],
                    "rows": [["2026-07-01", 7]],
                    "truncated": False,
                    "rowCount": 1,
                    "sql": "SELECT [d] AS [d], COUNT(*) AS [n] FROM [dbo].[T] GROUP BY [d]",
                    "sqlPretty": sql_display,
                    "sqlDisplay": sql_display,
                    "params": [],
                }
            ),
        )

    page.route("**/api/reporting/run", _handler)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Stub count").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-breakdown-list").get_by_role("button").first.click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-wizard-run").click()

    peek = page.get_by_test_id("rs-sql-peek")
    expect(peek).to_be_visible()
    expect(peek).to_have_text("SELECT [d] AS [d], COUNT(*) AS [n]…")

    sql_view = page.get_by_test_id("rs-sql-view")
    expect(sql_view).to_be_hidden()
    peek.click()
    expect(sql_view).to_be_visible()
    expect(page.locator("#rsSqlText")).to_contain_text("GROUP BY")


def test_landing_hero_suggestion_fills_prompt(nexora_server, page):
    """Task 3: the landing hero holds the AI command bar + suggestion chips.
    Clicking a chip fills rsAiPrompt with the chip's own text (no wizard or
    catalog interaction needed to reach this — the hero is static markup)."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    hero = page.get_by_test_id("rs-hero")
    expect(hero).to_be_visible()
    expect(hero.get_by_test_id("rs-ai-prompt")).to_be_visible()
    chip = page.get_by_test_id("rs-suggestion").first
    chip_text = chip.inner_text()
    chip.click()
    expect(page.get_by_test_id("rs-ai-prompt")).to_have_value(chip_text)


def test_wizard_rail_tracks_progress(nexora_server, page):
    """Task 5: the two-column wizard shell shows a step counter + a left
    progress rail tracking wiz state. Same stub catalog + click sequence as
    test_wizard_docprocessing_offers_process_breakdown (a source WITH
    processes, so Continue reveals the Processes/scope step next, i.e. step 2
    of 4) rather than the empty-process WIZ_STUB_SOURCES used elsewhere."""
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, DOCPROC_WIZ_SOURCES, DOCPROC_WIZ_METRICS)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    rail = page.get_by_test_id("rs-wizard-rail")
    expect(rail).to_be_visible()
    expect(page.locator("#rsWizardStepNo")).to_have_text("Step 1 of 4")
    page.get_by_test_id("rs-measure-list").get_by_text("Docproc count stub").click()
    page.get_by_test_id("rs-measure-next").click()
    expect(page.locator("#rsWizardStepNo")).to_have_text("Step 2 of 4")
    expect(rail).to_contain_text("Docproc count stub")  # chosen-value summary


def test_result_more_menu_holds_advanced_and_sql(nexora_server, page):
    """Task 7: the result header's ⋯ overflow menu now hosts Open-in-Advanced
    and Show-query. Both keep their exact ids/testids, but are only
    actionable once the caller opens #rsMoreMenu (D6 result-header regroup).
    Menu also closes on Escape and on an outside click."""
    _login(page, nexora_server)

    def _row(rid, name):
        return {
            "id": rid,
            "name": name,
            "ownerName": "Admin",
            "updatedAt": "2026-07-01T00:00:00Z",
            "visibility": "private",
            "owned": True,
            "kind": "table",
        }

    def _definition(title):
        return {
            "schemaVersion": 1,
            "source": "docprocessing",
            "visualization": "table",
            "title": title,
            "columns": [{"field": "processname"}],
            "filters": [],
            "sort": [],
            "scope": {"clients": [], "processes": []},
            "rowLimit": 100,
        }

    page.route(
        "**/api/reporting/reports",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps([_row("e2e-more-menu-report", "e2e more menu report")]),
        ),
    )
    page.route(
        "**/api/reporting/reports/*",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "name": "e2e more menu report",
                    "definition": _definition("e2e more menu report"),
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
                    "columns": [{"field": "processname", "header": "Process"}],
                    "rows": [["acme.inv"]],
                    "truncated": False,
                    "rowCount": 1,
                    "sql": "SELECT [processname] FROM [dbo].[V]",
                    "sqlPretty": "SELECT [processname] FROM [dbo].[V]",
                    "sqlDisplay": "SELECT [processname] FROM [dbo].[V]",
                    "params": [],
                    "resolvedDates": [],
                }
            ),
        ),
    )
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-group-mine").get_by_text("e2e more menu report").click()
    expect(page.get_by_test_id("rs-result-title")).to_contain_text("e2e more menu report")

    # Closed by default: both menu-hosted controls are not actionable.
    expect(page.get_by_test_id("rs-open-advanced")).to_be_hidden()
    expect(page.get_by_test_id("rs-show-sql")).to_be_hidden()
    page.get_by_test_id("rs-more").click()
    expect(page.get_by_test_id("rs-open-advanced")).to_be_visible()
    expect(page.get_by_test_id("rs-show-sql")).to_be_visible()

    # Escape closes the menu again.
    page.keyboard.press("Escape")
    expect(page.get_by_test_id("rs-open-advanced")).to_be_hidden()

    # Re-open, then a click outside the menu closes it too.
    page.get_by_test_id("rs-more").click()
    expect(page.get_by_test_id("rs-open-advanced")).to_be_visible()
    page.get_by_test_id("rs-result-title").click()
    expect(page.get_by_test_id("rs-open-advanced")).to_be_hidden()
