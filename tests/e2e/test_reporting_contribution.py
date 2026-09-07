"""e2e: the contribution-analysis drawer behind the Total delta chip."""

import json

from playwright.sync_api import expect

from tests.e2e.test_reporting_simple import _login, _stub_catalogs

RUN = {
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

CONTRIB = {
    "priorStart": "2026-05-01",
    "priorEnd": "2026-05-31",
    "metric": "stub_count",
    "metricLabel": "Stub count",
    "isRatio": False,
    "currentTotal": 42,
    "priorTotal": 30,
    "dimensions": [
        {
            "field": "processname",
            "label": "Process",
            "rows": [
                {"value": "acme.inv", "current": 30, "prior": 20, "delta": 10, "share": 0.83},
                {"value": "(empty)", "current": 2, "prior": 0, "delta": 2, "share": 0.17},
                {"value": "(other)", "current": 10, "prior": 10, "delta": 0, "share": 0.0},
            ],
        },
        {
            "field": "doctype",
            "label": "Document type",
            "rows": [
                {"value": "Invoice", "current": 42, "prior": 30, "delta": 12, "share": 1.0},
            ],
        },
    ],
    "skipped": ["status"],
}


def _run_with_preset(page):
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Stub count").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-time-list").get_by_text("This month", exact=True).click()
    page.get_by_test_id("rs-wizard-run").click()
    expect(page.get_by_test_id("rs-result")).to_be_visible()


def test_why_chip_opens_contribution_drawer_and_drills(nexora_server, page):
    _login(page, nexora_server)
    _stub_catalogs(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    posted = []

    def _contrib(route):
        posted.append(route.request.post_data_json)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(CONTRIB))

    runs = []

    def _run(route):
        runs.append(route.request.post_data_json)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(RUN))

    page.route("**/api/reporting/contribution", _contrib)
    page.route("**/api/reporting/run", _run)
    _run_with_preset(page)

    chip = page.get_by_test_id("rs-kpi-total").get_by_test_id("rp-delta")
    expect(chip).to_have_attribute("data-why", "1")
    chip.click()

    expect(page.get_by_test_id("contrib-head")).to_contain_text("Stub count")
    expect(page.get_by_test_id("contrib-tab")).to_have_count(2)
    rows = page.get_by_test_id("contrib-rows").first.get_by_test_id("contrib-row")
    expect(rows).to_have_count(3)
    expect(rows.first).to_contain_text("acme.inv")
    expect(rows.first).to_contain_text("+83%")
    expect(page.locator("#rdNote")).to_contain_text("status")
    # The posted body is the Simple definition with its token filter intact.
    assert posted and posted[0]["metrics"][0]["metric"] == "stub_count"
    assert any("token" in json.dumps(f) for f in posted[0]["filters"])

    # Second tab swaps the panel.
    page.get_by_test_id("contrib-tab").nth(1).click()
    expect(page.get_by_test_id("contrib-rows").nth(1)).to_be_visible()
    expect(page.get_by_test_id("contrib-rows").first).to_be_hidden()

    # Row click hands over to the drill drawer: one more /run POST with an eq
    # filter on the clicked dimension.
    before = len(runs)
    page.get_by_test_id("contrib-rows").nth(1).get_by_test_id("contrib-row").first.click()
    expect(page.locator("#rdTitle")).to_contain_text("Document type = Invoice")
    expect(page.locator("#rdChips")).to_contain_text("Invoice")  # drill repainted the shell
    assert len(runs) > before
    assert {"field": "doctype", "op": "eq", "value": "Invoice"} in runs[-1]["filters"]


def test_declined_drill_leaves_drawer_usable(nexora_server, page):
    """CONTRIB's first dimension is 'processname', which the stub source's
    field list (WIZ_STUB_SOURCES: import_date, doctype) doesn't carry -- the
    server picks contribution dimensions by type=="string" without checking
    filterable, so this is a real, reachable shape. Clicking one of its rows
    must decline the drill (toast) without leaving the drawer inert: tabs and
    the surviving rows must still respond afterwards."""
    _login(page, nexora_server)
    _stub_catalogs(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")

    def _contrib(route):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(CONTRIB))

    def _run(route):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(RUN))

    page.route("**/api/reporting/contribution", _contrib)
    page.route("**/api/reporting/run", _run)
    _run_with_preset(page)

    page.get_by_test_id("rs-kpi-total").get_by_test_id("rp-delta").click()
    expect(page.get_by_test_id("contrib-tab")).to_have_count(2)

    # First tab ("Process") is the un-drillable "processname" dimension.
    rows = page.get_by_test_id("contrib-rows").first.get_by_test_id("contrib-row")
    rows.first.click()
    expect(page.get_by_test_id("reporting-toast")).to_be_visible()

    # Declined -- the drawer is still the contribution drawer, not handed
    # over, and still fully interactive: rows are still there...
    expect(page.get_by_test_id("contrib-rows").first).to_be_visible()
    expect(rows).to_have_count(3)
    # ...and a tab click still switches panels.
    page.get_by_test_id("contrib-tab").nth(1).click()
    expect(page.get_by_test_id("contrib-rows").nth(1)).to_be_visible()
    expect(page.get_by_test_id("contrib-rows").first).to_be_hidden()


def test_why_chip_shows_server_error(nexora_server, page):
    _login(page, nexora_server)
    _stub_catalogs(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.route(
        "**/api/reporting/contribution",
        lambda r: r.fulfill(
            status=400,
            content_type="application/json",
            body=json.dumps(
                {
                    "error": "No comparison window — the report needs exactly one relative-date filter."
                }
            ),
        ),
    )
    page.route(
        "**/api/reporting/run",
        lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(RUN)),
    )
    _run_with_preset(page)
    page.get_by_test_id("rs-kpi-total").get_by_test_id("rp-delta").click()
    expect(page.get_by_test_id("contrib-error")).to_contain_text("No comparison window")
