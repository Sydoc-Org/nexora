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
    page.goto(f"{base}/reporting?tab=advanced")
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


# Mounts a 3-column pivot, then moves a field into Columns via synthetic HTML5
# drag-and-drop to exercise the multi-level (nested) column header path.
_NESTED = """() => {
  const cols = [{field:'region',header:'Region'},{field:'client',header:'Client'},
                {field:'amt',header:'Amount'}];
  const rows = [['West','Acme',100],['West','Acme',50],['East','Globex',70],['East','Acme',30]];
  const pivot = document.getElementById('rpPivot');
  pivot.hidden = false;
  window.ReportingViz.mountPivot(pivot, cols, rows);
  // After auto-seed (Region->Rows, Amount->Values) only Client remains in Fields.
  const chip = pivot.querySelector('[data-zone="src"] .reporting-pivot-chip');
  const colsZone = pivot.querySelector('[data-zone="cols"]');
  const dt = new DataTransfer();
  chip.dispatchEvent(new DragEvent('dragstart', {bubbles:true, dataTransfer:dt}));
  colsZone.dispatchEvent(new DragEvent('drop', {bubbles:true, dataTransfer:dt}));
  const ex = window.ReportingViz.getPivotExport();
  return {
    headerRows: pivot.querySelectorAll('table.reporting-pivot-table thead tr').length,
    exportCols: ex ? ex.columns.length : 0,
    exportRows: ex ? ex.rows.length : 0
  };
}"""


@pytest.mark.flaky_e2e
def test_pivot_nested_headers_and_export_model(nexora_server, page):
    _login(page, nexora_server)
    result = page.evaluate(_NESTED)
    # One column dimension (Client) + a measure row => 2 nested header rows.
    assert result["headerRows"] == 2, result
    # Export model is populated for the chart/pivot Export path.
    assert result["exportCols"] > 0 and result["exportRows"] > 0, result
    page.screenshot(path="var/screenshots/reporting_pivot_nested.png")


# Two-dimension row tuples that collide under a naive "".join(tuple) bucket
# key: ['ab','c'] and ['a','bc'] both flatten to "abc". Both dims are dragged
# into Rows so the pivot buckets on the full tuple; a correct unambiguous key
# (JSON.stringify) keeps them as two distinct pivot rows with distinct sums,
# instead of silently merging them into one row summed to 30.
_COLLIDING_TUPLES = """() => {
  const cols = [{field:'dim1',header:'Dim1'},{field:'dim2',header:'Dim2'},
                {field:'amt',header:'Amount'}];
  const rows = [['ab','c',10],['a','bc',20]];
  const pivot = document.getElementById('rpPivot');
  pivot.hidden = false;
  window.ReportingViz.mountPivot(pivot, cols, rows);
  // Auto-seed put dim1 -> Rows, amt -> Values; dim2 is still in Fields.
  const chip = pivot.querySelector('[data-zone="src"] .reporting-pivot-chip');
  const rowsZone = pivot.querySelector('[data-zone="rows"]');
  const dt = new DataTransfer();
  chip.dispatchEvent(new DragEvent('dragstart', {bubbles:true, dataTransfer:dt}));
  rowsZone.dispatchEvent(new DragEvent('drop', {bubbles:true, dataTransfer:dt}));
  const bodyRows = pivot.querySelectorAll('table.reporting-pivot-table tbody tr');
  return {
    // last <tr> is the grand-total row, so subtract it from the data-row count.
    dataRowCount: bodyRows.length - 1,
    cellTexts: Array.from(bodyRows).map(
      tr => Array.from(tr.children).map(td => td.textContent)
    )
  };
}"""


@pytest.mark.flaky_e2e
def test_pivot_bucket_keys_do_not_collide(nexora_server, page):
    _login(page, nexora_server)
    result = page.evaluate(_COLLIDING_TUPLES)
    # ['ab','c'] and ['a','bc'] must render as two distinct pivot rows, not
    # merge into one (which is what a "".join('') bucket key would do).
    assert result["dataRowCount"] == 2, result
    # Last row is the grand total (10 + 20 = 30, expected there); the two
    # data rows above it must keep their own values distinct and unmerged.
    data_rows, total_row = result["cellTexts"][:-1], result["cellTexts"][-1]
    flat_data = [cell for row in data_rows for cell in row]
    assert "10" in flat_data and "20" in flat_data, result
    assert "30" not in flat_data, result
    assert "30" in total_row, result
