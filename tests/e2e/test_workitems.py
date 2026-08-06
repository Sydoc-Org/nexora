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


@pytest.mark.flaky_e2e
def test_workitems_saved_filter_view_roundtrip(nexora_server, page):
    """Saved filter views (#170): save the current filter state as a named
    chip, re-apply it on a fresh page load, rename via the pencil, delete via
    the x. Runs against the real /api/workitem_filter_views endpoints (table
    exists in TEST). Pre-cleans the user's views so a run that died mid-test
    can't leave a stale chip behind for the next run."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    page.evaluate(
        """async () => {
            const h = {'X-CSRFToken': csrfToken};
            const r = await fetch('/api/workitem_filter_views', {headers: h});
            for (const v of (await r.json()).views) {
                await fetch(`/api/workitem_filter_views/${v.id}`, {method: 'DELETE', headers: h});
            }
        }"""
    )
    page.reload()

    # Build a state and save it as a named view.
    page.fill('[data-testid="workitems-search"]', "4711")
    page.select_option('[data-testid="workitems-status-filter"]', "Done")
    page.click('[data-testid="workitems-save-view"]')
    name_input = page.locator('[data-testid="workitems-view-name-input"]')
    expect(name_input).to_be_visible()
    name_input.fill("E2E backlog")
    name_input.press("Enter")

    chip = page.locator('[data-testid="workitems-view-chip"]')
    expect(chip).to_have_count(1)
    expect(chip).to_contain_text("E2E backlog")

    # Fresh load: the chip persists; clicking its name restores the state.
    page.goto(f"{nexora_server}/workitems")
    chip = page.locator('[data-testid="workitems-view-chip"]')
    expect(chip).to_be_visible()
    expect(page.locator('[data-testid="workitems-search"]')).to_have_value("")
    chip.locator("button").first.click()
    expect(page.locator('[data-testid="workitems-search"]')).to_have_value("4711")
    expect(page.locator('[data-testid="workitems-status-filter"]')).to_have_value("Done")

    # Rename via the pencil (chip buttons: 0 = apply/deselect, 1 = pencil,
    # 2 = deselect-x, shown on the active chip only).
    chip.locator("button").nth(1).click()
    name_input = page.locator('[data-testid="workitems-view-name-input"]')
    expect(name_input).to_be_visible()
    name_input.fill("E2E renamed")
    name_input.press("Enter")
    chip = page.locator('[data-testid="workitems-view-chip"]')
    expect(chip).to_contain_text("E2E renamed")

    # The x on the ACTIVE chip deselects — filters reset, nothing deleted
    # (an always-delete x nuked views when people meant to unselect).
    chip.locator("button").nth(2).click()
    expect(page.locator('[data-testid="workitems-search"]')).to_have_value("")
    chip = page.locator('[data-testid="workitems-view-chip"]')
    expect(chip).to_have_count(1)

    # Delete lives in the pencil editor's trash button.
    chip.locator("button").nth(1).click()
    page.click('[data-testid="workitems-view-delete"]')
    expect(page.locator('[data-testid="workitems-view-chip"]')).to_have_count(0)
    page.goto(f"{nexora_server}/workitems")
    expect(page.locator('[data-testid="workitems-saved-views"]')).to_be_hidden()


@pytest.mark.flaky_e2e
def test_workitems_saved_view_folder_grouping(nexora_server, page):
    """Saved-view folders (#186): saving with a folder renders a folder chip
    (name + count) instead of a plain chip; its dropdown lists the views with
    apply/delete. Same pre-clean discipline as the roundtrip test."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    page.evaluate(
        """async () => {
            const h = {'X-CSRFToken': csrfToken};
            const r = await fetch('/api/workitem_filter_views', {headers: h});
            for (const v of (await r.json()).views) {
                await fetch(`/api/workitem_filter_views/${v.id}`, {method: 'DELETE', headers: h});
            }
        }"""
    )
    page.reload()

    # Save a view into a folder.
    page.fill('[data-testid="workitems-search"]', "555")
    page.click('[data-testid="workitems-save-view"]')
    page.fill('[data-testid="workitems-view-name-input"]', "Foldered view")
    folder_input = page.locator('[data-testid="workitems-view-folder-input"]')
    folder_input.fill("Search Specific")
    folder_input.press("Enter")

    # A folder chip renders (no plain chip for a foldered view).
    folder_chip = page.locator('[data-testid="workitems-view-folder"]')
    expect(folder_chip).to_be_visible()
    expect(folder_chip).to_contain_text("Search Specific (1)")
    expect(page.locator('[data-testid="workitems-view-chip"]')).to_have_count(0)

    # Fresh load: open the folder dropdown and apply the view from it.
    page.goto(f"{nexora_server}/workitems")
    folder_chip = page.locator('[data-testid="workitems-view-folder"]')
    expect(folder_chip).to_be_visible()
    folder_chip.click()
    apply_btn = page.locator('[data-testid="workitems-view-menu-apply"]')
    expect(apply_btn).to_be_visible()
    apply_btn.click()
    expect(page.locator('[data-testid="workitems-search"]')).to_have_value("555")

    # Delete via the dropdown row's pencil -> editor trash button: the folder
    # chip disappears with its last view.
    folder_chip.click()
    page.locator(".saved-view-folder-menu button[aria-label]").last.click()
    page.click('[data-testid="workitems-view-delete"]')
    expect(page.locator('[data-testid="workitems-view-folder"]')).to_have_count(0)
