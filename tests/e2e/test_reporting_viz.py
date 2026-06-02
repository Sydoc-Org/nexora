"""E2E smoke for the Reporting chart + pivot views.

The Statistics DB is absent in TEST, so a real run yields no rows and the
view toggle stays hidden. Instead this drives the window.ReportingViz module
directly with synthetic data — the same entry points the result-view toggle
calls — so the chart canvas and the drag-and-drop pivot matrix are exercised
without a database.
"""

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.goto(f"{base}/reporting")
    page.wait_for_load_state("domcontentloaded")


_SYNTHETIC = """() => {
  const cols = [{field:'client',header:'Client'},{field:'pages',header:'Pages'}];
  const rows = [['A',10],['A',5],['B',3]];
  const pivot = document.getElementById('rpPivot');
  const chart = document.getElementById('rpChart');
  pivot.hidden = false; chart.hidden = false;
  window.ReportingViz.mountPivot(pivot, cols, rows);
  window.ReportingViz.mountChart(chart, cols, rows);
}"""


@pytest.mark.flaky_e2e
def test_chart_and_pivot_render(nexora_server, page):
    _login(page, nexora_server)

    # The result-view toggle exists in the DOM (hidden until a run returns rows).
    expect(page.locator('[data-testid="reporting-view-pivot"]')).to_be_attached()

    page.evaluate(_SYNTHETIC)

    # Pivot: a matrix with the drag-and-drop shelf and seeded Rows/Values totals.
    pivot = page.locator('[data-testid="reporting-pivot"]')
    expect(pivot.locator(".reporting-pivot-zone")).to_have_count(4)
    table = pivot.locator("table.reporting-pivot-table")
    expect(table).to_be_visible()
    # client A => sum(10,5)=15; grand total = 18.
    expect(table).to_contain_text("15")
    expect(table).to_contain_text("18")

    # Chart: Chart.js renders into a canvas.
    expect(page.locator('[data-testid="reporting-chart"] canvas')).to_be_visible()

    page.screenshot(path="var/screenshots/reporting_viz_smoke.png")
