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
