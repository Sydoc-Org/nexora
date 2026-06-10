"""E2E smoke tests for /reporting.

Requires ENVIRONMENT=TEST with reporting.* permissions seeded (sql/test/seed.sql
grants every permission to TestAdmin, which includes reporting.view and
reporting.source.docprocessing). The page chrome and source select are asserted;
data rows are not checked because the statistics DB is absent in TEST.
"""

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
    page.evaluate(
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
    # Give loadSelectedReport (async fetch + applyDefinition) time to complete.
    page.wait_for_timeout(2000)
    # The filter row for ForDate should have a preset select (nth(1) = second
    # select in the row, after the field select) showing last_month.
    row = page.locator(".reporting-filter-row").first
    from playwright.sync_api import expect

    expect(row.locator("select").nth(1)).to_have_value("last_month")
