"""E2E tests for /workitems.

admin@test.local has workitems.view plus all filter perms. The workitem tables
are absent in TEST so the result table is empty; tests target the filter form,
the advanced-filter toggle and the export modal rather than data rows.
"""

import json

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.flaky_e2e
def test_workitems_renders(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    expect(page.locator('[data-testid="workitems-filter-form"]')).to_be_visible()
    assert "internal server error" not in page.content().lower()


@pytest.mark.flaky_e2e
def test_workitems_filter_controls_present(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    expect(page.locator('[data-testid="workitems-search"]')).to_be_visible()
    expect(page.locator('[data-testid="workitems-status-filter"]')).to_be_visible()
    expect(page.locator('[data-testid="workitems-process-filter"]')).to_be_visible()
    expect(page.locator('[data-testid="workitems-per-page"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_workitems_toggle_advanced_reveals_date_range(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    page.click('[data-testid="workitems-toggle-advanced"]')
    expect(page.locator('[data-testid="workitems-start-date"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_workitems_export_csv_opens_modal(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    page.click('[data-testid="workitems-export-csv"]')
    expect(page.locator('[data-testid="workitems-close-export-modal"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_workitems_export_modal_closes(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    page.click('[data-testid="workitems-export-csv"]')
    close = page.locator('[data-testid="workitems-close-export-modal"]')
    expect(close).to_be_visible()
    close.click()
    expect(close).to_be_hidden()


@pytest.mark.flaky_e2e
def test_workitems_merged_list_renders(nexora_server, page):
    """Smoke: the multi-source list page renders its grid for an authorized
    user even when the TEST runtime DB has no rows (single-source passthrough
    when MS02 is unconfigured = byte-identical to before)."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    # The table container is present even with an empty runtime DB in TEST.
    expect(page.locator("#workitemsTable")).to_be_visible()
    # And the page did not hard-error (filter form rendered).
    expect(page.locator('[data-testid="workitems-filter-form"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_workitems_in_register_chip_is_client_scoped(nexora_server, page):
    """Regression: workitemid 1216 collides between the default and ms02
    clients (docs/design/ms02-multisource.md). Only the ms02 row is actually
    in_register; before the fix, `_inRegisterByWid` was seeded/read on the
    bare wid, so the default-client row inherited the ms02 row's "In
    register" chip. The TEST runtime DB has no workitem rows, so /api/
    workitems is stubbed to return the two colliding rows directly."""
    _login(page, nexora_server)

    def _fake_workitems(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "workitems": [
                        {
                            "workitemid": 1216,
                            "client": "default",
                            "status": "Open",
                            "modifiedat": None,
                            "current_stage": "Stage A",
                            "pid": None,
                            "in_register": False,
                        },
                        {
                            "workitemid": 1216,
                            "client": "ms02",
                            "status": "Closed",
                            "modifiedat": None,
                            "current_stage": "Stage B",
                            "pid": "PID-42",
                            "in_register": True,
                        },
                    ],
                    "pagination": {
                        "currentPage": 1,
                        "totalPages": 1,
                        "totalItems": 2,
                        "perPage": 20,
                    },
                    "degradedSources": [],
                }
            ),
        )

    page.route("**/api/workitems?*", _fake_workitems)
    page.goto(f"{nexora_server}/workitems")

    default_toggle = page.locator('button[data-rowkey="default-1216"]')
    ms02_toggle = page.locator('button[data-rowkey="ms02-1216"]')
    expect(default_toggle).to_be_visible()
    expect(ms02_toggle).to_be_visible()

    default_toggle.click()
    default_header = page.locator("#details-row-default-1216 .detail-panel-header")
    expect(default_header).to_be_attached()
    expect(default_header.locator('[data-testid="workitem-in-register"]')).to_have_count(0)

    ms02_toggle.click()
    ms02_header = page.locator("#details-row-ms02-1216 .detail-panel-header")
    expect(ms02_header.locator('[data-testid="workitem-in-register"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_workitems_sort_last_movement_toggles_order(nexora_server, page):
    """Regression: sortTable's parseDate expected 'd. m. yyyy - HH:MM' but
    renderTable actually writes ISO 'YYYY-MM-DD HH:MM:SS' for the "Last
    movement at" cell -- every comparison came back NaN, so clicking the
    header silently did nothing. Stub three rows out of date order and
    confirm the click both sorts ascending and flips to descending."""
    _login(page, nexora_server)

    def _fake_workitems(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "workitems": [
                        {
                            "workitemid": 501,
                            "client": "default",
                            "status": "Open",
                            "modifiedat": "2026-06-15T09:00:00Z",
                            "current_stage": "A",
                            "pid": None,
                            "in_register": False,
                        },
                        {
                            "workitemid": 502,
                            "client": "default",
                            "status": "Open",
                            "modifiedat": "2026-01-01T09:00:00Z",
                            "current_stage": "A",
                            "pid": None,
                            "in_register": False,
                        },
                        {
                            "workitemid": 503,
                            "client": "default",
                            "status": "Open",
                            "modifiedat": "2026-07-20T09:00:00Z",
                            "current_stage": "A",
                            "pid": None,
                            "in_register": False,
                        },
                    ],
                    "pagination": {
                        "currentPage": 1,
                        "totalPages": 1,
                        "totalItems": 3,
                        "perPage": 20,
                    },
                    "degradedSources": [],
                }
            ),
        )

    page.route("**/api/workitems?*", _fake_workitems)
    page.goto(f"{nexora_server}/workitems")

    rows = page.locator("#workitemsTbody tr.workitem-row")
    expect(rows).to_have_count(3)

    header = page.locator('#workitemsTable thead th[data-column-index="3"]')
    header.click()
    expect(rows.nth(0)).to_have_attribute("id", "row-default-502")
    expect(rows.nth(1)).to_have_attribute("id", "row-default-501")
    expect(rows.nth(2)).to_have_attribute("id", "row-default-503")

    header.click()
    expect(rows.nth(0)).to_have_attribute("id", "row-default-503")
    expect(rows.nth(1)).to_have_attribute("id", "row-default-501")
    expect(rows.nth(2)).to_have_attribute("id", "row-default-502")
