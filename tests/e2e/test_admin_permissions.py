"""E2E: the permissions grid toggles a grant and persists it (#238)."""

CELL = '[data-profile="TestNoPerm"][data-code="jd.view"] input'


def _login_admin(page, base):
    page.goto(f"{base}/dev/login/admin@test.local")
    page.wait_for_load_state("networkidle")


def test_grid_toggle_persists_and_reverts(nexora_server, page):
    _login_admin(page, nexora_server)
    page.goto(f"{nexora_server}/admin/permissions")
    page.wait_for_selector('[data-testid="admin-perms-grid"]')
    box = page.locator(CELL)
    before = box.is_checked()
    box.click()
    page.get_by_test_id("admin-perms-save").click()
    page.wait_for_selector('[data-testid="admin-perms-save"][disabled]')
    page.reload()
    page.wait_for_selector('[data-testid="admin-perms-grid"]')
    assert page.locator(CELL).is_checked() != before
    page.locator(CELL).click()
    page.get_by_test_id("admin-perms-save").click()
    page.wait_for_selector('[data-testid="admin-perms-save"][disabled]')
