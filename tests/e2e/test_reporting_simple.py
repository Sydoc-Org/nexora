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


# ---------------------------------------------------------------------------
# Task 11: delta chips vs the prior period (compare: true) on the Simple KPI
# band. Uses the same _stub_catalogs/WIZ_STUB_* fixtures as the Task 7 wizard
# tests further down this file (module-level names resolve at call time, so
# the forward reference is fine).
# ---------------------------------------------------------------------------


def test_delta_chip_renders_vs_prior_period(nexora_server, page):
    """A wizard run with a time preset posts compare: true, and a response
    carrying a `comparison` block renders an up/down/flat delta chip next to
    the KPI band's total/avg/peak values. The tooltip is the literal prior
    date range, never a calendar name -- shifted_definition_for_comparison
    shifts back by the CURRENT window's own length, which is not always the
    previous calendar period (e.g. a 31-day month vs. a 30-day one)."""
    _login(page, nexora_server)
    _stub_catalogs(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")

    payload = {
        "columns": [{"field": "stub_count", "header": "Stub count"}],
        "rows": [[42]],
        "truncated": False,
        "rowCount": 1,
        "sql": None,
        "params": [],
        "resolvedDates": [],
        "comparison": {
            "columns": [{"field": "stub_count", "header": "Stub count"}],
            "rows": [[30]],
            "priorStart": "2026-05-01",
            "priorEnd": "2026-05-31",
        },
    }
    captured = []

    def handler(route):
        captured.append(route.request.post_data_json)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    # Stub registered BEFORE the Run click that fires the request.
    page.route("**/api/reporting/run", handler)

    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Stub count").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-time-list").get_by_text("This month", exact=True).click()
    page.get_by_test_id("rs-wizard-run").click()

    expect(page.get_by_test_id("rs-result")).to_be_visible()
    assert captured and all(body.get("compare") is True for body in captured)

    chip = page.get_by_test_id("rs-kpi-total").get_by_test_id("rp-delta")
    expect(chip).to_be_visible()
    expect(chip).to_have_class(re.compile(r"rp-delta--up"))
    expect(chip).to_have_text("↑ 40%")
    expect(chip).to_have_attribute("title", "vs 2026-05-01 – 2026-05-31")  # noqa: RUF001 -- literal en dash, matches the brief's copy pattern


def test_delta_chip_absent_without_comparison(nexora_server, page):
    """Same wizard flow, response has no `comparison` key -- no delta chip
    renders anywhere in the KPI band (not an empty/zero chip)."""
    _login(page, nexora_server)
    _stub_catalogs(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")

    payload = {
        "columns": [{"field": "stub_count", "header": "Stub count"}],
        "rows": [[42]],
        "truncated": False,
        "rowCount": 1,
        "sql": None,
        "params": [],
        "resolvedDates": [],
    }
    page.route(
        "**/api/reporting/run",
        lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(payload)),
    )

    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Stub count").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-time-list").get_by_text("This month", exact=True).click()
    page.get_by_test_id("rs-wizard-run").click()

    expect(page.get_by_test_id("rs-result")).to_be_visible()
    expect(page.get_by_test_id("rs-kpi-total")).to_contain_text("42")
    expect(page.get_by_test_id("rp-delta")).to_have_count(0)


def test_delta_chip_avg_zero_fills_sparse_prior_period(nexora_server, page):
    """Task 11 follow-up fix: comparison.rows must get the SAME zero-fill
    treatment the current run's rows already get before computeKpiBand --
    otherwise the two periods' `buckets` counts disagree whenever either
    has an empty date bucket (the normal case for a multi-month breakdown),
    which skews the avg delta chip specifically (total/peak are unaffected
    since a missing bucket contributes 0 to those either way).

    Current period: 3 dense months (10, 20, 30 -> total 60, avg 20).
    Prior period: same 3-month span, but only the middle month has a row
    (30) -- the other two buckets are the sparse GROUP BY omission this
    zero-fill exists to correct. Zero-filled, that's total 30 over 3
    buckets = avg 10, an UP delta of +100%. Pre-fix (no zero-fill on the
    prior side), priorKpi.buckets would be 1 -> avg 30, a DOWN delta of
    -33% -- the wrong direction, which makes a regression here impossible
    to miss even without reading the percentage closely."""
    _login(page, nexora_server)
    _stub_catalogs(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")

    payload = {
        "columns": [
            {"field": "import_date", "header": "Import date"},
            {"field": "stub_count", "header": "Stub count"},
        ],
        "rows": [["2026-01-01", 10], ["2026-02-01", 20], ["2026-03-01", 30]],
        "truncated": False,
        "rowCount": 3,
        "sql": None,
        "params": [],
        "resolvedDates": [{"field": "import_date", "start": "2026-01-01", "end": "2026-03-31"}],
        "comparison": {
            "columns": [
                {"field": "import_date", "header": "Import date"},
                {"field": "stub_count", "header": "Stub count"},
            ],
            # Sparse: only the middle month of the 3-month prior window has
            # a row -- the other two buckets never existed in the backend's
            # GROUP BY, same as any empty bucket.
            "rows": [["2025-11-01", 30]],
            "priorStart": "2025-10-01",
            "priorEnd": "2025-12-31",
        },
    }
    captured = []

    def handler(route):
        captured.append(route.request.post_data_json)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    # Stub registered BEFORE the Run click that fires the request.
    page.route("**/api/reporting/run", handler)

    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Stub count").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-breakdown-list").locator('[data-bd-field="import_date"]').click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-time-list").get_by_text("Last 3 months", exact=True).click()
    page.get_by_test_id("rs-wizard-run").click()

    expect(page.get_by_test_id("rs-result")).to_be_visible()
    # Two requests fire for a metrics+breakdown run: the zero-column
    # grand-total clone (index 0) and the breakdown run itself (index 1).
    # Finding 1 (Phase 3 review): the clone never posts compare -- nothing
    # reads its comparison payload, so adding it was a fully wasted extra
    # query. Only the breakdown run, whose comparison feeds the delta chips
    # below, carries compare: true.
    assert len(captured) == 2
    assert captured[0].get("compare") is not True
    assert captured[1].get("compare") is True

    avg_chip = page.get_by_test_id("rs-kpi-avg").get_by_test_id("rp-delta")
    expect(avg_chip).to_be_visible()
    expect(avg_chip).to_have_class(re.compile(r"rp-delta--up"))
    expect(avg_chip).to_have_text("↑ 100%")


def test_delta_chip_avg_suppressed_on_bucket_count_mismatch(nexora_server, page):
    """Finding 2 (Phase 3 review): shifted_definition_for_comparison shifts
    the prior window back by the CURRENT window's length in DAYS, not by an
    integer number of grain periods. For a "this quarter" preset (3 calendar
    months, day-length not a multiple of a month) the shifted priorStart can
    land mid-month, so month-grain zero-fill produces a DIFFERENT bucket
    count than the current period -- comparing per-bucket averages across
    genuinely different-length periods (3 months vs. 4) would fabricate a
    percentage.

    Current period: 3 dense months (Jul/Aug/Sep 2026: 10, 20, 30 -> total 60,
    3 buckets, avg 20, peak 30).
    Prior period: 4 dense months (Mar-Jun 2026: 5, 15, 25, 5 -> total 50,
    4 buckets, avg 12.5, peak 25) -- priorStart '2026-03-31' is mid-month,
    the exact shape shifted_definition_for_comparison produces for a
    quarter-length window shifted back by its own day count.

    total (60 vs 50, +20%) and peak (30 vs 25, +20%) deltas must still
    render -- only avg is suppressed, since kpi.buckets (3) != priorKpi.buckets
    (4)."""
    _login(page, nexora_server)
    _stub_catalogs(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")

    payload = {
        "columns": [
            {"field": "import_date", "header": "Import date"},
            {"field": "stub_count", "header": "Stub count"},
        ],
        "rows": [["2026-07-01", 10], ["2026-08-01", 20], ["2026-09-01", 30]],
        "truncated": False,
        "rowCount": 3,
        "sql": None,
        "params": [],
        "resolvedDates": [{"field": "import_date", "start": "2026-07-01", "end": "2026-09-30"}],
        "comparison": {
            "columns": [
                {"field": "import_date", "header": "Import date"},
                {"field": "stub_count", "header": "Stub count"},
            ],
            # Dense across all 4 calendar months touched by the mid-month
            # priorStart -- isolates the bucket-COUNT mismatch from the
            # separate sparse-row zero-fill case already covered above.
            "rows": [
                ["2026-03-01", 5],
                ["2026-04-01", 15],
                ["2026-05-01", 25],
                ["2026-06-01", 5],
            ],
            "priorStart": "2026-03-31",
            "priorEnd": "2026-06-30",
        },
    }
    captured = []

    def handler(route):
        captured.append(route.request.post_data_json)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    # Stub registered BEFORE the Run click that fires the request.
    page.route("**/api/reporting/run", handler)

    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Stub count").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-breakdown-list").locator('[data-bd-field="import_date"]').click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-time-list").get_by_text("This quarter", exact=True).click()
    page.get_by_test_id("rs-wizard-run").click()

    expect(page.get_by_test_id("rs-result")).to_be_visible()
    assert len(captured) == 2 and captured[1].get("compare") is True

    total_chip = page.get_by_test_id("rs-kpi-total").get_by_test_id("rp-delta")
    expect(total_chip).to_be_visible()
    expect(total_chip).to_have_class(re.compile(r"rp-delta--up"))
    expect(total_chip).to_have_text("↑ 20%")

    peak_chip = page.get_by_test_id("rs-kpi-peak").get_by_test_id("rp-delta")
    expect(peak_chip).to_be_visible()
    expect(peak_chip).to_have_class(re.compile(r"rp-delta--up"))
    expect(peak_chip).to_have_text("↑ 20%")

    expect(page.get_by_test_id("rs-kpi-avg").get_by_test_id("rp-delta")).to_have_count(0)


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


def _stub_run_ok(page, capture=None):
    """Stub /api/reporting/run with a deterministic success.

    Library/wizard-flow tests fire an async runCurrent() whose real
    /api/reporting/run can error intermittently on the test DB (stale
    NEXORA_TEST state). The error path, showResultError(), hides the chips
    mid-test, racing later clicks. Stubbing the response keeps the result UI
    up regardless of the backend. Pass `capture` (a list) to record each run
    payload for assertions.
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


def _stub_agent_ok(page, answer="Here is your report."):
    """Stub /api/reporting/ai/agent with a deterministic success (same shape
    as tests/e2e/test_reporting_agent.py's _stub_agent, but fulfilling the
    shared chat panel's endpoint instead of the Advanced-tab Agent submode)."""
    body = json.dumps(
        {
            "answer": answer,
            "toolTrace": [],
            "turns": 1,
            "stoppedReason": "final",
            "definition": None,
            "sql": None,
        }
    )
    page.route(
        "**/api/reporting/ai/agent",
        lambda r: r.fulfill(status=200, content_type="application/json", body=body),
    )


# ---- Auto AI captions (Task 13) -------------------------------------------


def _stub_caption(page, caption="Most requests come from acme.inv.", status=200, delay_s=0.0):
    """Stub /api/reporting/ai/caption. status=200 -> {caption}; anything else
    -> a generic {error} body, matching how api_ai_caption degrades (502/503/
    429/403 all just mean "no caption" to the frontend)."""
    import time as _time

    def handler(route):
        if delay_s:
            _time.sleep(delay_s)
        if status == 200:
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps({"caption": caption})
            )
        else:
            route.fulfill(
                status=status, content_type="application/json", body=json.dumps({"error": "boom"})
            )

    page.route("**/api/reporting/ai/caption", handler)


def _create_caption_source_and_metric(page, nexora_server):
    """Create a real curated source + count metric (same recipe as
    test_timing_badge_shows_rows_and_elapsed_ms), via the Advanced tab's admin
    API. Returns the {src, met} ids for cleanup."""
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    return page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'caption_users', kind: 'curated', label: 'Caption Users',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 41});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'caption_user_count', sourceId: 'caption_users', label: 'Caption user count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )


def _wizard_measure_breakdown_run(page):
    """Click through the Simple wizard's measure -> breakdown -> Run steps for
    the 'Caption user count' / 'Username' pair _create_caption_source_and_metric
    creates. Caller must already be on ?tab=simple with /api/reporting/run
    (and any AI stub) already registered -- the wizard's Run button calls
    runCurrent() synchronously on click, so this is the single trigger for the
    run+caption round trip the shimmer-timing assertions below need."""
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Caption user count").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-wizard-run").click()


def _run_caption_wizard(page, nexora_server):
    """Create the source/metric, stub a successful run, and drive the wizard
    straight to Run. Unlike opening a saved report (openReport() awaits
    loadSourcesCatalog()/loadMetricsCatalog() -- real, uncached, multi-second
    calls -- BEFORE calling runCurrent()), this reaches runCurrent() with
    catalogs already warm from building the wizard. Caller registers
    /api/reporting/ai/caption BEFORE calling this (route stubs must exist
    before the triggering click). Returns the {src, met} ids for cleanup."""
    ids = _create_caption_source_and_metric(page, nexora_server)
    _stub_run_ok(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    _wizard_measure_breakdown_run(page)
    return ids


def _cleanup_caption_wizard(page, ids):
    page.evaluate(
        """async (ids) => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
          await del('/api/reporting/admin/metrics/' + ids.met);
          await del('/api/reporting/admin/sources/' + ids.src);
        }""",
        ids,
    )


def test_hero_ask_routes_into_chat_panel(nexora_server, page):
    """Task 4: the hero's Ask AI no longer builds/runs its own report -- it
    opens the shared chat panel and forwards the question there."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")

    # Stub BEFORE clicking — ReportingChat.send() fires the request the
    # instant the hero handler calls it, right after open().
    _stub_agent_ok(page)
    page.get_by_test_id("rs-ai-prompt").fill("docs by process")
    page.get_by_test_id("rs-ai-ask").click()

    expect(page.get_by_test_id("reporting-chat-panel")).to_be_visible()
    expect(page.get_by_test_id("rp-chat-msg-user")).to_contain_text("docs by process")
    expect(page.get_by_test_id("rp-chat-msg-ai")).to_contain_text("Here is your report.")
    expect(page.get_by_test_id("reporting-chat-input")).to_have_value("")
    # The hero's own prompt input is cleared once the question is forwarded.
    expect(page.get_by_test_id("rs-ai-prompt")).to_have_value("")


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


def test_chips_edit_and_remove_rerun_without_ai(nexora_server, page):
    """Chip edit/remove is definition-driven, not AI-specific -- reach the
    result via a library report (the AI can no longer land a definition in
    Simple's own result view; that now only happens through the chat panel's
    'Open in builder' into Advanced)."""
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

    # Register stubs BEFORE goto -- the library load fires as soon as the
    # Simple pane mounts.
    page.route(
        "**/api/reporting/reports",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps([_row("e2e-chip-edit", STUB_AI_DEFINITION["title"])]),
        ),
    )
    page.route(
        "**/api/reporting/reports/*",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "name": STUB_AI_DEFINITION["title"],
                    "definition": STUB_AI_DEFINITION,
                    "owned": True,
                    "canEdit": True,
                }
            ),
        ),
    )
    run_payloads = []
    _stub_run_ok(page, capture=run_payloads)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-group-mine").get_by_text(STUB_AI_DEFINITION["title"]).click()
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
    page.route(
        "**/api/reporting/reports",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                [
                    {
                        "id": "e2e-chip-labels",
                        "name": STUB_AI_DEFINITION["title"],
                        "ownerName": "Admin",
                        "updatedAt": "2026-07-01T00:00:00Z",
                        "visibility": "private",
                        "owned": True,
                        "kind": "table",
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
                    "name": STUB_AI_DEFINITION["title"],
                    "definition": STUB_AI_DEFINITION,
                    "owned": True,
                    "canEdit": True,
                }
            ),
        ),
    )
    _stub_run_ok(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-group-mine").get_by_text(STUB_AI_DEFINITION["title"]).click()
    chips = page.get_by_test_id("rs-chips")
    # First paint may show the raw key; the catalog-resolve re-render fixes it.
    expect(chips.get_by_test_id("rs-chip").first).to_contain_text("Process = acme.inv")


def test_wizard_result_shows_chips(nexora_server, page):
    """After a wizard run, chips appear (not just for AI-built results)."""
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

        # Chips are now visible for wizard results too.
        chips = page.locator("#rsChips")
        expect(chips).to_be_visible()

        # The wizard adds no filters, so the "no filters" placeholder chip renders.
        expect(chips).to_contain_text("no filters")
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
    """A non-wizard def filtered on {token: this_quarter} keeps 'Adjust' visible.

    Reached via a library report (not AI) -- the AI can no longer land a
    definition in Simple's own result view directly; that path now goes
    through the chat panel's 'Open in builder' into Advanced instead.
    """
    _login(page, nexora_server)

    definition = {
        "schemaVersion": 1,
        "source": "stub_src",
        "visualization": "table",
        "title": "quarter stub",
        "subtitle": None,
        "columns": [],
        "metrics": [{"metric": "stub_count"}],
        "filters": [{"field": "import_date", "op": "between", "value": {"token": "this_quarter"}}],
        "sort": [],
        "scope": {"clients": [], "processes": []},
        "rowLimit": 5000,
    }

    # Register stubs BEFORE goto -- the library list + catalogs fetch as soon
    # as the Simple pane mounts.
    page.route(
        "**/api/reporting/reports",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                [
                    {
                        "id": "e2e-quarter-stub",
                        "name": "quarter stub",
                        "ownerName": "Admin",
                        "updatedAt": "2026-07-01T00:00:00Z",
                        "visibility": "private",
                        "owned": True,
                        "kind": "table",
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
                    "name": definition["title"],
                    "definition": definition,
                    "owned": True,
                    "canEdit": True,
                }
            ),
        ),
    )
    _stub_catalogs(page)
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

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-group-mine").get_by_text("quarter stub").click()
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
    # Second date field: #164 -- both "Over time" chips must be selectable at once.
    {
        "field": "export_date",
        "label": "Export date",
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


def test_wizard_allows_both_date_breakdowns(nexora_server, page):
    """#164: export date + import date are selectable together and BOTH reach the
    run payload as grained columns (they used to be mutually exclusive)."""
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, DOCPROC_WIZ_SOURCES, DOCPROC_WIZ_METRICS)
    captured = []
    _stub_run_ok(page, capture=captured)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Docproc count stub").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-scope-next").click()
    bklist = page.get_by_test_id("rs-breakdown-list")
    exp = bklist.locator('[data-bd-field="export_date"]')
    imp = bklist.locator('[data-bd-field="import_date"]')
    exp.click()
    imp.click()
    # The second click must NOT deselect the first.
    expect(exp).to_have_attribute("aria-pressed", "true")
    expect(imp).to_have_attribute("aria-pressed", "true")
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-wizard-run").click()
    expect(page.get_by_test_id("rs-result")).to_be_visible()
    with_cols = [p for p in captured if p.get("columns")]
    assert with_cols, f"no run payload carried columns: {captured}"
    cols = with_cols[0]["columns"]
    assert {c["field"] for c in cols} == {"export_date", "import_date"}, cols
    # Both carry the wizard's single grain -- neither is emitted as a raw date.
    assert all(c.get("grain") for c in cols), cols


def test_wizard_grain_visible_before_date_pick(nexora_server, page):
    """#178 B8: the Granularity select is visible (disabled) as soon as the
    breakdown step opens for a source with date fields, enabled once a date
    breakdown is picked."""
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, DOCPROC_WIZ_SOURCES, DOCPROC_WIZ_METRICS)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Docproc count stub").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-scope-next").click()
    grain_wrap = page.locator("#rsGrainWrap")
    expect(grain_wrap).to_be_visible()
    expect(page.locator("#rsGrain")).to_be_disabled()
    page.locator('[data-bd-kind="date"]').first.click()
    expect(page.locator("#rsGrain")).to_be_enabled()


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


TEN_SERIES_RUN_BODY = json.dumps(
    {
        "columns": [
            {"field": "doctype", "header": "Document Type"},
            {"field": "docsource", "header": "Document Source"},
            {"field": "doc_count", "header": "doc_count"},
        ],
        # One x-value ("Invoice") x ten distinct docsource values -> ten
        # composite series, all sharing the same x-point -- exercises the
        # palette at exactly the width Finding B's regression hit. With the
        # old 7-color NX_PALETTE, series 8 (index 7) would silently draw in
        # the same color as series 1 (index 0) via `i % NX_PALETTE.length`.
        "rows": [["Invoice", "S%02d" % i, i + 1] for i in range(10)],
        "truncated": False,
        "rowCount": 10,
        "sql": None,
        "params": [],
        "resolvedDates": [],
    }
)


def test_ten_series_breakdown_chart_gets_distinct_colors(nexora_server, page):
    """Finding B regression test: the shared NX_PALETTE must have enough
    entries that a breakdown chart with more series than the old 7-color
    palette (up to the 12-series cap) never repeats a color. Before the fix,
    series 8 drew in the exact same color as series 1 (`i % 7` wrapping),
    making two genuinely different breakdown values visually indistinguishable
    on a legend-driven chart."""
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, THREE_DIM_SOURCES, THREE_DIM_METRICS)
    page.route(
        "**/api/reporting/run",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=TEN_SERIES_RUN_BODY
        ),
    )
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Count stub").click()
    page.get_by_test_id("rs-measure-next").click()
    bklist = page.get_by_test_id("rs-breakdown-list")
    bklist.locator('[data-bd-field="doctype"]').click()
    bklist.locator('[data-bd-field="docsource"]').click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-wizard-run").click()
    expect(page.locator("#rsChartCanvas")).to_be_visible()
    colors = page.evaluate(
        "() => window.Chart && (() => {"
        "  const c = Chart.getChart(document.getElementById('rsChartCanvas'));"
        "  return c ? c.data.datasets.map(d => d.borderColor) : null;"
        "})()"
    )
    assert colors and len(colors) == 10
    assert len(set(colors)) == 10, f"expected 10 distinct series colors, got {colors}"
    page.screenshot(path="var/screenshots/reporting_simple_ten_series_chart.png")


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


def test_landing_hero_suggestion_opens_chat_and_sends(nexora_server, page):
    """Task 4: the landing hero holds the AI command bar + suggestion chips.
    Clicking a chip now routes straight into the shared chat panel (open +
    send its own text) instead of just prefilling the prompt input."""
    _login(page, nexora_server)
    # Stub BEFORE goto/click — the chip click fires ReportingChat.send()
    # immediately.
    _stub_agent_ok(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    hero = page.get_by_test_id("rs-hero")
    expect(hero).to_be_visible()
    expect(hero.get_by_test_id("rs-ai-prompt")).to_be_visible()
    chip = page.get_by_test_id("rs-suggestion").first
    chip_text = chip.inner_text()
    chip.click()
    expect(page.get_by_test_id("reporting-chat-panel")).to_be_visible()
    expect(page.get_by_test_id("rp-chat-msg-user")).to_contain_text(chip_text)
    expect(page.get_by_test_id("rp-chat-msg-ai")).to_contain_text("Here is your report.")
    expect(page.get_by_test_id("rs-ai-prompt")).to_have_value("")


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


@pytest.mark.flaky_e2e
def test_caption_fires_after_run_shows_shimmer_then_ai_chip(nexora_server, page):
    """After a Simple result renders, an auto caption request fires; the
    caption slot shimmers while in flight, then shows the AI chip + caption
    text once the (stubbed) response lands (Task 13)."""
    _login(page, nexora_server)
    _stub_caption(page, caption="Most requests come from acme.inv.", delay_s=0.3)
    ids = _run_caption_wizard(page, nexora_server)
    try:
        loading = page.locator("#rsCaption.rp-caption--loading")
        expect(loading).to_be_visible()

        settled = page.locator("#rsCaption:not(.rp-caption--loading)")
        expect(settled).to_contain_text("Most requests come from acme.inv.")
        expect(settled.locator(".rp-caption-chip")).to_have_text("AI")
        page.screenshot(path="var/screenshots/reporting_simple_caption.png")
    finally:
        _cleanup_caption_wizard(page, ids)


@pytest.mark.flaky_e2e
def test_caption_hides_silently_on_error_no_console_noise(nexora_server, page):
    """A caption request that errors must never surface an error state or log
    to the console -- the slot shimmers briefly then goes back to hidden
    (Task 13's silent-fail contract, deliberately unlike the chat panel's
    error bubbles)."""
    _login(page, nexora_server)
    ids = _create_caption_source_and_metric(page, nexora_server)
    try:
        _stub_run_ok(page)
        _stub_caption(page, status=502, delay_s=0.2)
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.wait_for_load_state("domcontentloaded")
        # Listeners are registered only now -- after login's redirect through
        # the dashboard page (which fires its own unrelated fetch-failure
        # console errors, unstubbed here and irrelevant to this feature) has
        # fully resolved and we've landed on a quiet, not-yet-run Simple tab.
        console_errors = []
        page_errors = []
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        _wizard_measure_breakdown_run(page)

        expect(page.locator("#rsCaption.rp-caption--loading")).to_be_visible()
        expect(page.locator("#rsCaption")).to_be_hidden()
        # Chrome itself logs one "Failed to load resource: ... 502" line for
        # ANY fetch that resolves with a non-2xx status -- a browser-level
        # network diagnostic no application JS can suppress, unrelated to how
        # gracefully the page's own code then handles the rejection. The bar
        # this test actually holds fireCaption() to is the one within its
        # control: no uncaught exception, and no application-level
        # console.error of its own (nothing beyond that one expected line).
        unexpected = [m for m in console_errors if "Failed to load resource" not in m]
        assert unexpected == [], f"unexpected console errors: {unexpected}"
        assert page_errors == [], f"unexpected uncaught exceptions: {page_errors}"
    finally:
        _cleanup_caption_wizard(page, ids)


# ---------------------------------------------------------------------------
# Task 5: Forecast toggle (Simple tab chart toolbar)
# ---------------------------------------------------------------------------


def test_forecast_toggle_requests_and_renders_forecast(nexora_server, page):
    """Toggling Forecast re-runs with forecast.enabled and renders the
    dashed-extension buckets as marked table rows."""
    _login(page, nexora_server)
    _stub_catalogs(page)
    fc_block = {
        "anchor": "2025-08-01",
        "grain": "month",
        "method": "trend",
        "horizon": 3,
        "buckets": ["2025-09-01", "2025-10-01", "2025-11-01"],
        "series": [
            {
                "field": "doc_count",
                "values": [26.0, 28.0, 30.0],
                "lower": [24.0, 25.5, 27.0],
                "upper": [28.0, 30.5, 33.0],
            }
        ],
    }

    def run_stub(route):
        body = route.request.post_data_json or {}
        payload = {
            "columns": [{"field": "export_date"}, {"field": "doc_count"}],
            "rows": [[f"2025-{m:02d}-01", 10 + 2 * (m - 1)] for m in range(1, 9)],
            "rowCount": 8,
            "truncated": False,
            "resolvedDates": [],
        }
        if (body.get("forecast") or {}).get("enabled"):
            payload["forecast"] = fc_block
        route.fulfill(json=payload)

    page.route("**/api/reporting/run", run_stub)
    page.goto(f"{nexora_server}/reporting?tab=simple")

    # Build/run a 1-date-dim + metric report the same way the neighbouring
    # wizard e2e tests do (import_date breakdown + Last 3 months).
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Stub count").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-breakdown-list").locator('[data-bd-field="import_date"]').click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-time-list").get_by_text("Last 3 months", exact=True).click()
    page.get_by_test_id("rs-wizard-run").click()

    expect(page.get_by_test_id("rs-result")).to_be_visible()

    toggle = page.get_by_test_id("rs-forecast-toggle")
    expect(toggle).to_be_visible()
    expect(toggle).to_have_attribute("aria-pressed", "false")
    toggle.click()
    expect(toggle).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_test_id("rs-forecast-horizon")).to_be_visible()

    # Predicted rows land in the table, marked
    page.get_by_test_id("rs-table-toggle").click()
    rows = page.get_by_test_id("rs-forecast-row")
    expect(rows).to_have_count(3)
    expect(rows.first).to_contain_text("2025-09-01")
    expect(rows.first).to_contain_text("Forecast")

    # Toggle off -> rows disappear
    toggle.click()
    expect(page.get_by_test_id("rs-forecast-row")).to_have_count(0)


def test_forecast_trims_zero_filled_rows_past_anchor(nexora_server, page):
    """Regression (#168 final review, Finding 1): Simple's display zero-fill
    (a "This year" filter with data that stops mid-year) must not leave
    trailing fake zero rows for the SAME calendar buckets compute_forecast
    is about to append via forecast.anchor -- rows are trimmed back to the
    anchor before the forecast rows land, so July-Sept show up exactly once
    each, as forecast rows, not first as zero-filled real rows too."""
    _login(page, nexora_server)
    _stub_catalogs(page)
    fc_block = {
        "anchor": "2025-06-01",
        "grain": "month",
        "method": "trend",
        "horizon": 3,
        "buckets": ["2025-07-01", "2025-08-01", "2025-09-01"],
        "series": [
            {
                "field": "doc_count",
                "values": [26.0, 28.0, 30.0],
                "lower": [24.0, 25.5, 27.0],
                "upper": [28.0, 30.5, 33.0],
            }
        ],
    }

    def run_stub(route):
        body = route.request.post_data_json or {}
        payload = {
            "columns": [{"field": "import_date"}, {"field": "doc_count"}],
            # Real data covers only Jan-Jun 2025. The "This year" filter's
            # resolved range runs through December, so zeroFillDateBuckets
            # would (without the anchor trim) pad Jul-Dec with 6 fake zero
            # rows -- landing right on top of the 3 forecast buckets below.
            "rows": [[f"2025-{m:02d}-01", 10 + 2 * (m - 1)] for m in range(1, 7)],
            "rowCount": 6,
            "truncated": False,
            "resolvedDates": [{"field": "import_date", "start": "2025-01-01", "end": "2025-12-31"}],
        }
        if (body.get("forecast") or {}).get("enabled"):
            payload["forecast"] = fc_block
        route.fulfill(json=payload)

    page.route("**/api/reporting/run", run_stub)
    page.goto(f"{nexora_server}/reporting?tab=simple")

    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Stub count").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-breakdown-list").locator('[data-bd-field="import_date"]').click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-time-list").get_by_text("This year", exact=True).click()
    page.get_by_test_id("rs-wizard-run").click()

    expect(page.get_by_test_id("rs-result")).to_be_visible()

    toggle = page.get_by_test_id("rs-forecast-toggle")
    expect(toggle).to_be_visible()
    toggle.click()
    expect(toggle).to_have_attribute("aria-pressed", "true")

    page.get_by_test_id("rs-table-toggle").click()

    # 6 real rows (Jan-Jun) + 3 forecast rows (Jul-Sep) = 9. Without the
    # anchor trim this would be 12 real/zero rows + 3 forecast rows, with
    # Jul/Aug/Sep each appearing twice (once as a fake zero, once forecast).
    plain_rows = page.locator("#rsTableWrap tbody tr:not(.is-forecast)")
    expect(plain_rows).to_have_count(6)
    forecast_rows = page.get_by_test_id("rs-forecast-row")
    expect(forecast_rows).to_have_count(3)

    expect(plain_rows.last).to_contain_text("2025-06-01")
    expect(
        page.locator("#rsTableWrap tbody tr:not(.is-forecast)", has_text="2025-07-01")
    ).to_have_count(0)
    expect(forecast_rows.first).to_contain_text("2025-07-01")


def test_hero_hidden_outside_library_view(nexora_server, page):
    """#178 B6: the 'Build a report in seconds' hero must vanish when a
    wizard/result is open and come back in the library."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    expect(page.get_by_test_id("rs-hero")).to_be_visible()
    page.get_by_test_id("rs-new-report").click()
    expect(page.get_by_test_id("rs-hero")).to_be_hidden()
    page.get_by_test_id("rs-wizard-backlib").first.click()
    expect(page.get_by_test_id("rs-hero")).to_be_visible()


def test_granularity_chip_changes_grain_and_reruns(nexora_server, page):
    """#178 B7: a date-grained definition shows a Granularity chip; picking a
    different grain re-POSTs the definition with the new grain."""
    posted = []
    _stub_run_ok(page, capture=posted)
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    # Open a grained definition through the exposed test seam (Task 4 adds
    # window.ReportingSimple.openDefinition; if Task 4 is not merged yet,
    # drive the wizard like the neighbouring wizard tests instead).
    page.evaluate("""() => window.ReportingSimple.openDefinition({
      schemaVersion: 1, visualization: 'table', source: 'docprocessing',
      title: 'per month', columns: [{field: 'export_date', grain: 'month'}],
      metrics: [{metric: 'doc_count'}], filters: [], sort: [],
      scope: {clients: [], processes: []}, rowLimit: 5000}, 'per month')""")
    chip = page.get_by_test_id("rs-chip").filter(has_text="Granularity")
    expect(chip).to_be_visible()
    chip.click()
    page.get_by_test_id("rs-chip-grain").locator("select").select_option("week")
    page.get_by_test_id("rs-chip-grain-apply").click()
    # The re-rendered chip reflecting the new grain proves runCurrent()
    # completed, so the posted payload below is settled, not racing.
    expect(page.get_by_test_id("rs-chip").filter(has_text="Granularity")).to_contain_text("Week")
    assert any((p.get("columns") or [{}])[0].get("grain") == "week" for p in posted)


def test_kpi_band_total_uses_latest_snapshot_for_latest_mode_metric(nexora_server, page):
    """#178 C10: for a latest-mode metric (backlog_total) with a date
    dimension, the orange GESAMT card totals only the newest date bucket's
    row -- not the sum across every bucket in the result set.

    Reduced-motion is emulated so the KPI value's count-up animation
    (animateValue) writes the final total synchronously instead of counting
    up through 0..N -- otherwise a mid-animation frame could transiently
    contain "9" or omit "36" regardless of which value the band settles on,
    making the assertions below meaningless.
    """
    _login(page, nexora_server)
    page.emulate_media(reduced_motion="reduce")
    page.route(
        "**/api/reporting/metrics",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "backlog_history": [
                        {
                            "code": "backlog_total",
                            "label": "Backlog total",
                            "aggregation": "sum",
                            "totalMode": "latest",
                        }
                    ]
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
                    "columns": [{"field": "SnapshotAt"}, {"field": "backlog_total"}],
                    "rows": [["2026-08-05", 27122], ["2026-08-06", 9755]],
                    "rowCount": 2,
                    "truncated": False,
                    "resolvedDates": [],
                }
            ),
        ),
    )
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.evaluate("""() => window.ReportingSimple.openDefinition({
      schemaVersion: 1, visualization: 'table', source: 'backlog_history',
      title: 'backlog', columns: [{field: 'SnapshotAt', grain: 'day'}],
      metrics: [{metric: 'backlog_total'}], filters: [], sort: [],
      scope: {clients: [], processes: []}, rowLimit: 5000}, 'backlog')""")

    total = page.get_by_test_id("rs-kpi-total")
    expect(total).to_contain_text("9")  # 9,755 -- latest bucket only
    expect(total).not_to_contain_text("36")  # never 36,877 (the sum)


# ---------------------------------------------------------------------------
# #178 B8 (processes half): table sources have no `processes` registry, but a
# filterable string field named/labelled like one still gets a wizard scope
# step, backed by /api/reporting/field_values (Task 12).
# ---------------------------------------------------------------------------

FIELD_SCOPE_WIZ_SOURCES = [
    {
        "id": "backlog_history",
        "label": "Backlog history",
        "kind": "curated",
        "processes": [],
        "fields": [
            {
                "field": "ProcessName",
                "label": "Process",
                "type": "string",
                "grainable": False,
                "filterable": True,
            },
        ],
    }
]
FIELD_SCOPE_WIZ_METRICS = {
    "backlog_history": [
        {"code": "backlog_total", "label": "Backlog measure", "aggregation": "sum"},
    ]
}


def test_wizard_field_scope_step_serializes_to_in_filter(nexora_server, page):
    """A source without a process registry but with a filterable ProcessName
    field gets the scope step anyway, sourced from /api/reporting/field_values;
    unticking one value narrows the wizard-built definition to a plain
    in-filter on that field (editable later as an ordinary chip)."""
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, FIELD_SCOPE_WIZ_SOURCES, FIELD_SCOPE_WIZ_METRICS)
    page.route(
        "**/api/reporting/field_values",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"values": ["01_EasyTax", "02_Invoice", "03_Invoice_New"]}),
        ),
    )
    captured = []
    _stub_run_ok(page, capture=captured)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Backlog measure").click()
    page.get_by_test_id("rs-measure-next").click()
    expect(page.locator("#rsStepScope")).to_be_visible()
    boxes = page.locator("#rsScopeList input[type=checkbox]")
    expect(boxes).to_have_count(3)
    boxes.nth(0).uncheck()
    page.get_by_test_id("rs-scope-next").click()
    page.get_by_test_id("rs-breakdown-next").click()
    run = page.get_by_test_id("rs-wizard-run")  # renderTimeStep() unhides it; All time default
    expect(run).to_be_visible()
    run.click()
    expect(page.get_by_test_id("rs-result")).to_be_visible()
    posted = [p for p in captured if p]
    assert posted, f"no run payload captured: {captured}"
    assert any(
        any(
            f.get("op") == "in"
            and f.get("field") == "ProcessName"
            and sorted(f.get("value") or []) == ["02_Invoice", "03_Invoice_New"]
            for f in (b.get("filters") or [])
        )
        for b in posted
    )


def test_filter_chip_editor_preserves_in_filter_on_apply(nexora_server, page):
    """Final whole-branch review, Finding 1 (#178): editing (or just
    re-Applying without changes) a 2-value `in`-filter chip must NOT coerce
    it into `{op:'between', value:[v0, v1]}` -- filterChipEditor used to
    branch on Array.isArray(f.value) alone, silently turning a field-scope
    value LIST (Task 13) into a lexical range on Apply."""
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, FIELD_SCOPE_WIZ_SOURCES, FIELD_SCOPE_WIZ_METRICS)
    captured = []
    _stub_run_ok(page, capture=captured)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.evaluate("""() => window.ReportingSimple.openDefinition({
      schemaVersion: 1, visualization: 'table', source: 'backlog_history',
      title: 'in-filter chip', columns: [], metrics: [{metric: 'backlog_total'}],
      filters: [{field: 'ProcessName', op: 'in', value: ['02_Invoice', '03_Invoice_New']}],
      sort: [], scope: {clients: [], processes: []}, rowLimit: 5000
    }, 'in-filter chip')""")
    chips = page.get_by_test_id("rs-chips")
    chip = chips.get_by_test_id("rs-chip").first
    expect(chip).to_contain_text("02_Invoice, 03_Invoice_New")  # comma, not '->' (not a range)
    chip.click()
    # Apply WITHOUT changing anything -- the corrupting bug fired even here.
    page.get_by_test_id("rs-chip-apply").click()
    expect(chips.get_by_test_id("rs-chip").first).to_contain_text("02_Invoice, 03_Invoice_New")
    posted = [p for p in captured if p]
    assert posted, f"no run payload captured: {captured}"
    last_filters = posted[-1].get("filters") or []
    assert len(last_filters) == 1
    assert last_filters[0]["op"] == "in"
    assert sorted(last_filters[0]["value"]) == ["02_Invoice", "03_Invoice_New"]


# Regression (Phase 5 batched review, #178): wizardStateFromDefinition must
# only capture an in-filter as the wizard's field-scope pick when it targets
# the SAME field processFieldFor(src) would offer -- not any string in-filter.
# A source WITH a processes registry never has a process-like field to match,
# so an unrelated string in-filter must keep bailing to Advanced (Adjust
# button hidden), exactly like before Task 13, instead of being silently
# swallowed (and dropped on the next wizard save).
REGISTRY_SCOPE_WIZ_SOURCES = [
    {
        "id": "docprocessing_scope",
        "label": "Document processing (scope regression)",
        "kind": "curated",
        "processes": ["acme.inv", "acme.hr"],
        "fields": [
            {
                "field": "doctype",
                "label": "Document Type",
                "type": "string",
                "grainable": False,
                "filterable": True,
            },
        ],
    }
]
REGISTRY_SCOPE_WIZ_METRICS = {
    "docprocessing_scope": [
        {"code": "docp_scope_count", "label": "Docp scope count", "aggregation": "count"},
    ]
}


def test_wizard_state_from_definition_ignores_unrelated_in_filter(nexora_server, page):
    """A registry-process source's unrelated string in-filter must not be
    misattributed as a field-scope pick: Adjust-in-wizard stays unavailable
    (bails to Advanced) rather than silently mapping and then dropping the
    filter on save."""
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, REGISTRY_SCOPE_WIZ_SOURCES, REGISTRY_SCOPE_WIZ_METRICS)
    _stub_run_ok(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.evaluate("""() => window.ReportingSimple.openDefinition({
      schemaVersion: 1, visualization: 'table', source: 'docprocessing_scope',
      title: 'scope regression', columns: [],
      metrics: [{metric: 'docp_scope_count'}],
      filters: [{field: 'doctype', op: 'in', value: ['a', 'b']}],
      sort: [], scope: {clients: [], processes: []}, rowLimit: 5000
    }, 'scope regression')""")
    expect(page.get_by_test_id("rs-result")).to_be_visible()
    expect(page.get_by_test_id("rs-adjust-wizard")).to_be_hidden()


def test_open_in_advanced_runs_report_and_reveals_sql(nexora_server, page):
    """#178 A5 ("Live SQL geht nicht"): Simple's "Open in Advanced" escape
    hatch (rsOpenAdvanced) must actually run the restored definition, not
    just call applyDefinition() and switch tabs. Before the fix, Advanced
    landed on the loaded builder state with an empty results grid and
    "Show query" (rpShowSql) still hidden -- reading as "Live SQL doesn't
    work" to an owner who had just opened an AI-built report from Simple."""
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
        "source": "docprocessing",
        "visualization": "table",
        "title": "e2e open advanced report",
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
            body=json.dumps([_row("e2e-open-advanced", "e2e open advanced report")]),
        ),
    )
    page.route(
        "**/api/reporting/reports/*",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "name": "e2e open advanced report",
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
    page.get_by_test_id("rs-group-mine").get_by_text("e2e open advanced report").click()
    expect(page.get_by_test_id("rs-result-title")).to_contain_text("e2e open advanced report")

    page.get_by_test_id("rs-more").click()
    page.get_by_test_id("rs-open-advanced").click()

    # Landed on Advanced -- and it must have actually run the definition:
    # the results grid holds the stubbed row, and "Show query" is revealed
    # (not just an empty builder with rpShowSql still hidden).
    expect(page.get_by_test_id("reporting-field-panel")).to_be_visible()
    expect(page.get_by_test_id("reporting-results")).to_contain_text("acme.inv")
    expect(page.get_by_test_id("reporting-show-sql")).to_be_visible()


def test_reporting_simple_exposes_result_builders(nexora_server, page):
    """Whole-report dashboard cards draw through the Simple pane's own result
    builders; they must be reachable (and pure functions) on
    window.ReportingSimple. Each Phase-1 task of the whole-report-card plan
    adds its builder to this list."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    expect(page.get_by_test_id("rs-hero")).to_be_visible()
    names = [
        "ensureCatalogs",
        "fmtNumber",
        "zeroFillDateBuckets",
        "kpiBandHtml",
        "statCardHtml",
        "buildChartData",
    ]
    kinds = page.evaluate("(names) => names.map(k => typeof window.ReportingSimple[k])", names)
    assert kinds == ["function"] * len(names), dict(zip(names, kinds, strict=False))
