"""E2E smoke tests for /reporting.

Requires ENVIRONMENT=TEST with reporting.* permissions seeded (sql/test/seed.sql
grants every permission to TestAdmin, which includes reporting.view and
reporting.source.docprocessing). The page chrome and source select are asserted;
data rows are not checked because the statistics DB is absent in TEST.
"""

import json

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    # admin@test.local lands on /admin (adminPagePerm fires first in
    # startpage_redirect_to), so navigate explicitly to /reporting.
    page.goto(f"{base}/reporting?tab=advanced")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.flaky_e2e
def test_reporting_page_loads(nexora_server, page):
    _login(page, nexora_server)
    expect(page.locator('[data-testid="reporting-page"]')).to_be_visible()
    page.screenshot(path="var/screenshots/reporting_page.png")


@pytest.mark.flaky_e2e
def test_reporting_help_panel_opens_and_closes(nexora_server, page):
    _login(page, nexora_server)
    modal = page.locator('[data-testid="reporting-help-modal"]')
    expect(modal).to_be_hidden()
    page.locator('[data-testid="reporting-help-toggle"]').click()
    expect(modal).to_be_visible()
    expect(page.locator('[data-testid="reporting-help-guide-link"]')).to_be_visible()
    page.locator('[data-testid="reporting-help-close"]').click()
    expect(modal).to_be_hidden()


@pytest.mark.flaky_e2e
def test_reporting_guide_page_renders(nexora_server, page):
    """/reporting/guide serves the rendered user guide with a TOC."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting/guide")
    page.wait_for_load_state("domcontentloaded")
    article = page.locator('[data-testid="reporting-guide-article"]')
    expect(article).to_be_visible()
    # A section heading from the guide, anchored for the TOC.
    expect(article.locator("h2#the-60-second-version")).to_have_count(1)
    expect(page.locator('[data-testid="reporting-guide-back"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_reporting_source_select_present(nexora_server, page):
    _login(page, nexora_server)
    source_select = page.locator('[data-testid="reporting-source-select"]')
    expect(source_select).to_be_visible()
    assert source_select.evaluate("el => el.tagName.toLowerCase()") == "select"


@pytest.mark.flaky_e2e
def test_reporting_does_not_error(nexora_server, page):
    _login(page, nexora_server)
    page.wait_for_load_state("domcontentloaded")
    assert "internal server error" not in page.content().lower()


@pytest.mark.flaky_e2e
def test_advanced_date_filter_token_preset_round_trips(nexora_server, page):
    _login(page, nexora_server)
    # Use generali_pdqm / ForDate — the only date-typed field available in TEST.
    # Save a definition with a last_month token on ForDate via the API.
    report_id = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const res = await fetch('/api/reporting/reports', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify({name: 'e2e adv token', definition: {
              schemaVersion: 1, source: 'generali_pdqm', visualization: 'table',
              title: 'e2e adv token',
              columns: [{field: 'ForDate'}],
              filters: [{field: 'ForDate', op: 'between',
                         value: {token: 'last_month'}}],
              sort: [], scope: {clients: [], processes: []}, rowLimit: 100}})
          });
          return (await res.json()).id;
        }"""
    )
    try:
        # Reload so loadReports() and loadSources() run and populate their selects.
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        # Wait for loadSources() to finish — generali_pdqm must be in #rpSource so
        # that applyDefinition can resolve state.sourcesById['generali_pdqm'].fields.
        page.wait_for_function(
            """() => {
              var sel = document.getElementById('rpSource');
              if (!sel) return false;
              for (var i = 0; i < sel.options.length; i++) {
                if (sel.options[i].value === 'generali_pdqm') return true;
              }
              return false;
            }""",
            timeout=8000,
        )
        # Wait for loadReports() to populate #rpSavedReports with our saved report.
        page.wait_for_function(
            """() => {
              var sel = document.getElementById('rpSavedReports');
              if (!sel) return false;
              for (var i = 0; i < sel.options.length; i++) {
                if (sel.options[i].text.indexOf('e2e adv token') !== -1) return true;
              }
              return false;
            }""",
            timeout=8000,
        )
        # Select the saved report from #rpSavedReports and click Load — this triggers
        # loadSelectedReport() -> applyDefinition() which restores state.filters and
        # calls renderFilters().
        page.evaluate(
            """() => {
              var sel = document.getElementById('rpSavedReports');
              for (var i = 0; i < sel.options.length; i++) {
                if (sel.options[i].text.indexOf('e2e adv token') !== -1) {
                  sel.value = sel.options[i].value;
                  break;
                }
              }
            }"""
        )
        page.click('[data-testid="reporting-load"]')
        # Wait until the filter row's preset select shows last_month — avoids a
        # fixed sleep and makes the assertion race-free.
        page.wait_for_function(
            """() => {
              var rows = document.querySelectorAll('.reporting-filter-row');
              if (!rows.length) return false;
              var sels = rows[0].querySelectorAll('select');
              return sels.length >= 2 && sels[1].value === 'last_month';
            }""",
            timeout=8000,
        )
        # The filter row for ForDate should have a preset select (nth(1) = second
        # select in the row, after the field select) showing last_month.
        row = page.locator(".reporting-filter-row").first
        from playwright.sync_api import expect

        expect(row.locator("select").nth(1)).to_have_value("last_month")
    finally:
        page.evaluate(f"""async () => {{
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          await fetch('/api/reporting/reports/{report_id}', {{
            method: 'DELETE', headers: {{'X-CSRFToken': csrf}}
          }});
        }}""")


@pytest.mark.flaky_e2e
def test_advanced_saved_reports_select_excludes_dashboards(nexora_server, page):
    """D17: a dashboard-kind report can't be represented by the Advanced
    builder's definition shape (unlike a sql-kind report, which stays
    pickable with an ' (SQL)' suffix) -- loadReports() must drop it from
    #rpSavedReports entirely. Already covered for the Simple library's
    click-to-open path (test_reporting_simple.py); this covers the other
    half of D17, the Advanced tab's saved-reports select."""
    _login(page, nexora_server)
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const mk = (name, definition) => fetch('/api/reporting/reports', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify({name, definition})
          }).then(r => r.json());
          const dash = await mk('e2e adv dash excluded', {
            kind: 'dashboard', title: 'e2e adv dash excluded', cards: []
          });
          const normal = await mk('e2e adv normal included', {
            schemaVersion: 1, source: 'generali_pdqm', visualization: 'table',
            title: 'e2e adv normal included',
            columns: [{field: 'ForDate'}], filters: [], sort: [],
            scope: {clients: [], processes: []}, rowLimit: 100});
          return {dash: dash.id, normal: normal.id};
        }"""
    )
    try:
        # Reload so loadReports() re-fetches the list and repopulates
        # #rpSavedReports with both newly-created reports.
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_function(
            """() => {
              var sel = document.getElementById('rpSavedReports');
              if (!sel) return false;
              for (var i = 0; i < sel.options.length; i++) {
                if (sel.options[i].text.indexOf('e2e adv normal included') !== -1) return true;
              }
              return false;
            }""",
            timeout=8000,
        )
        option_texts = page.eval_on_selector_all(
            "#rpSavedReports option", "opts => opts.map(o => o.textContent)"
        )
        assert any("e2e adv normal included" in t for t in option_texts)
        assert not any("e2e adv dash excluded" in t for t in option_texts)
    finally:
        page.evaluate(f"""async () => {{
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          await fetch('/api/reporting/reports/{ids["dash"]}', {{
            method: 'DELETE', headers: {{'X-CSRFToken': csrf}}
          }});
          await fetch('/api/reporting/reports/{ids["normal"]}', {{
            method: 'DELETE', headers: {{'X-CSRFToken': csrf}}
          }});
        }}""")


@pytest.mark.flaky_e2e
def test_switching_source_clears_stale_filters(nexora_server, page):
    """Task 62: pick() (Advanced tab's #rpSource onchange handler) used to
    reset state.columns/scope/metrics on a source switch but never
    state.filters -- the previous source's filter chips (referencing fields
    that may not exist on the new source) survived and 400'd every
    subsequent Run until cleared by hand. pick() now also clears
    state.filters and re-renders #rpWellFilters, so no stale chip -- and no
    stale field name in the run payload -- can survive a source switch."""
    _login(page, nexora_server)

    # Both curated (non-SQL) sources are seeded in sql/test/seed.sql and
    # granted to TestAdmin; wait for both to be present in #rpSource before
    # driving the select.
    page.wait_for_function(
        """() => {
          var sel = document.getElementById('rpSource');
          if (!sel) return false;
          var vals = Array.from(sel.options).map(o => o.value);
          return vals.indexOf('generali_pdqm') !== -1 && vals.indexOf('workitems') !== -1;
        }""",
        timeout=8000,
    )

    # loadSources() auto-picks the first curated source (generali_pdqm,
    # SortOrder 20) on load. Add a filter chip on it.
    page.select_option("#rpSource", "generali_pdqm")
    page.click("#rpAddFilter")
    expect(page.locator(".reporting-filter-row")).to_have_count(1)

    # Switch to the other curated source (workitems, disjoint field set) --
    # the generali_pdqm-scoped filter chip must not survive the switch.
    page.select_option("#rpSource", "workitems")
    expect(page.locator(".reporting-filter-row")).to_have_count(0)

    # Stub the run endpoint before the click (per project convention -- the
    # curated sources need live Generali/Octopus DBs the TEST env doesn't
    # have) and capture the posted payload to assert no stale filter field
    # leaked into the request that would 400 the real endpoint.
    captured = []

    def _run(route):
        captured.append(route.request.post_data_json)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"columns": [], "rows": [], "rowCount": 0}),
        )

    page.route("**/api/reporting/run", _run)
    page.click('[data-testid="reporting-run"]')

    # Run completed via the 200 stub, not the .catch(showError) path.
    expect(page.locator(".reporting-error")).to_have_count(0)
    expect(page.locator('[data-testid="reporting-no-rows"]')).to_be_visible()
    assert len(captured) == 1
    assert captured[0]["filters"] == []
    assert captured[0]["source"] == "workitems"
    # No stale chip re-appeared once the run completed either.
    expect(page.locator(".reporting-filter-row")).to_have_count(0)


# ---- Auto AI captions (Task 13) -------------------------------------------
# Advanced fires a caption request on CHART MOUNT (not on every grid render),
# so these stub /api/reporting/run with an aggregate-shaped 2-column result
# (mirrors test_reporting_viz.py's synthetic ReportingViz.mountChart shape)
# and switch to the Chart view before asserting on #rpCaption. The route stub
# is always registered before the click that triggers the request (the known
# e2e flake trap in this codebase).


def _stub_advanced_run_and_caption(page, caption="Client A drives most of the totals."):
    def _run_handler(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "columns": [
                        {"field": "client", "header": "Client"},
                        {"field": "pages", "header": "Pages"},
                    ],
                    "rows": [["A", 10], ["A", 5], ["B", 3]],
                    "truncated": False,
                    "rowCount": 3,
                    "sql": None,
                    "params": [],
                    "resolvedDates": [],
                }
            ),
        )

    page.route("**/api/reporting/run", _run_handler)
    page.route(
        "**/api/reporting/ai/caption",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps({"caption": caption})
        ),
    )


@pytest.mark.flaky_e2e
def test_advanced_chart_mount_fires_caption_for_explain_data_holder(nexora_server, page):
    """admin@test.local holds reporting.ai.explain_data (sql/test/seed.sql
    grants every permission to TestAdmin) -- switching to the Chart view
    mounts the chart and fires an auto caption that renders with its AI chip."""
    _login(page, nexora_server)
    _stub_advanced_run_and_caption(page)
    page.get_by_test_id("reporting-run").click()
    expect(page.get_by_test_id("reporting-view-chart")).to_be_visible()
    page.get_by_test_id("reporting-view-chart").click()
    expect(page.locator('[data-testid="reporting-chart"] canvas')).to_be_visible()
    caption = page.locator("#rpCaption")
    expect(caption).to_be_visible()
    expect(caption).to_contain_text("Client A drives most of the totals.")
    expect(caption.locator(".rp-caption-chip")).to_have_text("AI")
    page.screenshot(path="var/screenshots/reporting_caption.png")


@pytest.mark.flaky_e2e
def test_advanced_caption_absent_without_explain_data_permission(nexora_server, page):
    """noai@test.local has every TestAdmin permission EXCEPT
    reporting.ai.explain_data (per-user deny override, sql/test/seed.sql) --
    the caption slot must not exist in the DOM at all, and the rest of the
    Advanced pane (run, chart) must work exactly as it does for an
    explain_data holder (Task 13's 'unaffected without the perm' spot-check)."""
    _login(page, nexora_server, who="noai@test.local")
    _stub_advanced_run_and_caption(page)
    expect(page.locator("#rpCaption")).to_have_count(0)
    page.get_by_test_id("reporting-run").click()
    expect(page.get_by_test_id("reporting-view-chart")).to_be_visible()
    page.get_by_test_id("reporting-view-chart").click()
    expect(page.locator('[data-testid="reporting-chart"] canvas')).to_be_visible()
    expect(page.locator("#rpCaption")).to_have_count(0)


@pytest.mark.flaky_e2e
def test_advanced_caption_does_not_survive_a_new_run(nexora_server, page):
    """A caption from report A's chart-mount must not linger visible once
    report B's grid renders. Before the fix, resetViews() (called by every
    renderResults()) reset the chart/pivot mount flags and the view-toggle
    visibility but never touched #rpCaption -- only fireCaption() itself ever
    cleared it, and that only fires again on a NEW chart mount. So a plain
    re-run left the previous report's caption sentence sitting under the new
    report's numbers until the user happened to revisit the Chart view."""
    _login(page, nexora_server)
    _stub_advanced_run_and_caption(page, caption="Client A drives most of the totals.")
    page.get_by_test_id("reporting-run").click()
    expect(page.get_by_test_id("reporting-view-chart")).to_be_visible()
    page.get_by_test_id("reporting-view-chart").click()
    caption = page.locator("#rpCaption")
    expect(caption).to_be_visible()
    expect(caption).to_contain_text("Client A drives most of the totals.")

    # Re-stub /api/reporting/run for a second, different run (report B) --
    # the route stub must exist before the click that triggers the request
    # (the established e2e flake trap in this codebase).
    def _run_handler_b(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "columns": [
                        {"field": "client", "header": "Client"},
                        {"field": "pages", "header": "Pages"},
                    ],
                    "rows": [["C", 1]],
                    "truncated": False,
                    "rowCount": 1,
                    "sql": None,
                    "params": [],
                    "resolvedDates": [],
                }
            ),
        )

    page.route("**/api/reporting/run", _run_handler_b)
    page.get_by_test_id("reporting-run").click()
    expect(page.get_by_test_id("reporting-view-grid")).to_be_visible()
    # Report B's grid is showing -- A's stale caption must not still be
    # visible, even though B hasn't been switched to Chart view (yet).
    expect(page.locator("#rpCaption")).to_be_hidden()


@pytest.mark.flaky_e2e
def test_advanced_caption_does_not_survive_a_failed_run(nexora_server, page):
    """Same stale-caption bug as test_advanced_caption_does_not_survive_a_new_run,
    but for the ERROR path rather than a second successful run. Before the fix,
    showError() (fired when a re-run comes back 403/400/500/network) swapped
    #rpResults' innerHTML for the error message but never touched #rpCaption --
    only resetViews() (the success path) and fireCaption() itself cleared it --
    so report A's AI sentence stayed sitting above the error, narrating data
    that was no longer on screen."""
    _login(page, nexora_server)
    _stub_advanced_run_and_caption(page, caption="Client A drives most of the totals.")
    page.get_by_test_id("reporting-run").click()
    expect(page.get_by_test_id("reporting-view-chart")).to_be_visible()
    page.get_by_test_id("reporting-view-chart").click()
    caption = page.locator("#rpCaption")
    expect(caption).to_be_visible()
    expect(caption).to_contain_text("Client A drives most of the totals.")

    # Re-stub /api/reporting/run for a second run that fails -- the route stub
    # must exist before the click that triggers the request (the established
    # e2e flake trap in this codebase).
    def _run_handler_error(route):
        route.fulfill(
            status=500,
            content_type="application/json",
            body=json.dumps({"error": "Something went wrong."}),
        )

    page.route("**/api/reporting/run", _run_handler_error)
    page.get_by_test_id("reporting-run").click()
    expect(page.locator(".reporting-error")).to_be_visible()
    # The failed run's error message is showing -- A's stale caption must not
    # still be visible above it.
    expect(page.locator("#rpCaption")).to_be_hidden()
    page.screenshot(path="var/screenshots/reporting_caption_error.png")


# ---- Forecast toggle (Task 7) -----------------------------------------------
# Forecast eligibility needs a real single-grained-date-column + metric
# definition (forecastEligibleDef), which the semantic-metrics registry has
# nothing seeded for in TEST (sql/test/seed.sql carries no metric rows) --
# so this stubs /api/reporting/sources + /api/reporting/metrics with a
# minimal one-field/one-metric catalog (same WIZ_STUB_SOURCES/METRICS shape
# test_reporting_simple.py uses for its own builder-catalog stubs), driving
# the real field-picker + Add metric UI rather than faking builder state.

ADV_FC_STUB_SOURCES = [
    {
        "id": "adv_fc_src",
        "label": "Adv forecast stub source",
        "kind": "curated",
        "processes": [],
        "fields": [
            {
                "field": "export_date",
                "label": "Export date",
                "type": "date",
                "grainable": True,
                "filterable": True,
            },
        ],
    }
]
ADV_FC_STUB_METRICS = {
    "adv_fc_src": [{"code": "doc_count_metric", "label": "Doc count", "aggregation": "count"}],
}


@pytest.mark.flaky_e2e
def test_advanced_forecast_toggle_and_grid_rows(nexora_server, page):
    """Task 7: the Advanced results toolbar's Forecast checkbox appears only
    once the definition is forecast-eligible (single grained date column +
    a metric), buildDefinition() emits state.forecast on toggle, and the
    grid appends marked prediction rows echoed back on /run's forecast
    block -- the Advanced-pane mirror of Task 6's Simple-tab renderTable
    coverage, adapted to this pane's DOM-built (not string-built) grid."""
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
            "columns": [
                {"field": "export_date", "header": "Export date"},
                {"field": "doc_count", "header": "Doc count"},
            ],
            "rows": [[f"2025-{m:02d}-01", 10 + 2 * (m - 1)] for m in range(1, 9)],
            "rowCount": 8,
            "truncated": False,
            "resolvedDates": [],
        }
        if (body.get("forecast") or {}).get("enabled"):
            payload["forecast"] = fc_block
        route.fulfill(json=payload)

    # MUST be registered before page.goto -- initOnce() fetches both catalogs
    # at page load (same trap _stub_catalogs/_stub_wiz_catalogs guard against
    # in test_reporting_simple.py).
    page.route(
        "**/api/reporting/sources",
        lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(ADV_FC_STUB_SOURCES)
        ),
    )
    page.route(
        "**/api/reporting/metrics",
        lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(ADV_FC_STUB_METRICS)
        ),
    )
    _login(page, nexora_server)

    # Build a 1-date-dim + 1-metric report in the Advanced builder: click the
    # only (grainable) field into Columns -- renderFields()'s onclick sets
    # grain: 'month' automatically for a grainable field -- then add the
    # only available metric.
    page.locator("#rpFieldList li").filter(has_text="Export date").click()
    expect(page.locator(".reporting-grain")).to_have_count(1)
    page.click("#rpAddMetric")
    expect(page.locator('[data-testid="reporting-metric-select"]')).to_have_count(1)

    page.route("**/api/reporting/run", run_stub)
    page.get_by_test_id("reporting-run").click()

    wrap = page.get_by_test_id("reporting-forecast-wrap")
    expect(wrap).to_be_visible()
    page.get_by_test_id("reporting-forecast-toggle").check()
    rows = page.get_by_test_id("rp-forecast-row")
    expect(rows).to_have_count(3)
    expect(rows.first).to_contain_text("Forecast")
