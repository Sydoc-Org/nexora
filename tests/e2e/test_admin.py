"""E2E tests for the /admin/* pages.

admin@test.local holds every permission (test seed), so all admin pages render.
Tables absent in TEST (Logs, MaintenanceBanner) make those pages render empty
but not 500. Destructive controls (delete org/user) are only opened and then
cancelled — never confirmed against seed data.

Route paths come from admin.register_routes: overview is /admin, user detail is
/admin/users/<id>.
"""

import pytest
from playwright.sync_api import expect


def _login_admin(page, base):
    page.goto(f"{base}/dev/login/admin@test.local")
    page.wait_for_url("**/dashboard")


@pytest.mark.flaky_e2e
class TestAdminOverview:
    def test_renders(self, nexora_server, page):
        _login_admin(page, nexora_server)
        page.goto(f"{nexora_server}/admin")
        expect(page.locator('[data-testid="admin-overview-organizations"]')).to_be_visible()

    def test_organizations_link(self, nexora_server, page):
        _login_admin(page, nexora_server)
        page.goto(f"{nexora_server}/admin")
        page.click('[data-testid="admin-overview-organizations"]')
        page.wait_for_url("**/admin/organizations")

    def test_sessions_link(self, nexora_server, page):
        _login_admin(page, nexora_server)
        page.goto(f"{nexora_server}/admin")
        page.click('[data-testid="admin-overview-sessions"]')
        page.wait_for_url("**/admin/sessions")

    def test_access_control_link(self, nexora_server, page):
        _login_admin(page, nexora_server)
        page.goto(f"{nexora_server}/admin")
        page.click('[data-testid="admin-overview-access-control"]')
        page.wait_for_url("**/admin/access_control")


@pytest.mark.flaky_e2e
class TestAdminOrganizations:
    def test_renders_seed_org(self, nexora_server, page):
        _login_admin(page, nexora_server)
        page.goto(f"{nexora_server}/admin/organizations")
        expect(page.locator('[data-testid="admin-org-row-TEST"]')).to_be_visible()

    def test_back_button(self, nexora_server, page):
        _login_admin(page, nexora_server)
        page.goto(f"{nexora_server}/admin/organizations")
        page.click('[data-testid="admin-helpers-back"]')
        page.wait_for_url("**/admin")

    def test_edit_opens_modal(self, nexora_server, page):
        _login_admin(page, nexora_server)
        page.goto(f"{nexora_server}/admin/organizations")
        page.click('[data-testid="admin-org-edit-TEST"]')
        expect(page.locator('[data-testid="admin-org-modal-form"]')).to_be_visible()

    def test_modal_cancel_closes(self, nexora_server, page):
        _login_admin(page, nexora_server)
        page.goto(f"{nexora_server}/admin/organizations")
        page.click('[data-testid="admin-org-edit-TEST"]')
        form = page.locator('[data-testid="admin-org-modal-form"]')
        expect(form).to_be_visible()
        page.click('[data-testid="admin-org-modal-cancel"]')
        expect(form).to_be_hidden()


@pytest.mark.flaky_e2e
class TestAdminSessions:
    def test_renders(self, nexora_server, page):
        _login_admin(page, nexora_server)
        page.goto(f"{nexora_server}/admin/sessions")
        expect(page.locator('[data-testid="admin-helpers-back"]')).to_be_visible()
        assert "internal server error" not in page.content().lower()


@pytest.mark.flaky_e2e
class TestAdminMaintenance:
    def test_renders(self, nexora_server, page):
        _login_admin(page, nexora_server)
        page.goto(f"{nexora_server}/admin/maintenance")
        # The banner form is a modal, hidden until "Add banner" is clicked; the
        # toolbar search input is the always-present landmark.
        expect(
            page.locator('[data-testid="admin-helpers-toolbar-maintSearchInput"]')
        ).to_be_visible()
        assert "internal server error" not in page.content().lower()

    def test_add_banner_opens_form(self, nexora_server, page):
        _login_admin(page, nexora_server)
        page.goto(f"{nexora_server}/admin/maintenance")
        page.click('[data-testid="admin-helpers-page-action-1"]')
        expect(page.locator('[data-testid="admin-maintenance-form"]')).to_be_visible()


@pytest.mark.flaky_e2e
class TestAdminAccessControl:
    def _open(self, page, base):
        _login_admin(page, base)
        page.goto(f"{base}/admin/access_control")

    def test_renders(self, nexora_server, page):
        self._open(page, nexora_server)
        expect(page.locator('[data-testid="admin-ac-tab-users"]')).to_be_visible()

    def test_tab_permissions(self, nexora_server, page):
        self._open(page, nexora_server)
        page.click('[data-testid="admin-ac-tab-permissions"]')
        expect(page.locator('[data-testid="admin-ac-perm-search"]')).to_be_visible()

    def test_add_user_modal_opens_and_closes(self, nexora_server, page):
        self._open(page, nexora_server)
        page.click('[data-testid="admin-ac-add-user"]')
        form = page.locator('[data-testid="admin-ac-user-form"]')
        expect(form).to_be_visible()
        page.click('[data-testid="admin-ac-user-modal-close"]')
        expect(form).to_be_hidden()

    def test_add_permission_modal_opens(self, nexora_server, page):
        self._open(page, nexora_server)
        page.click('[data-testid="admin-ac-tab-permissions"]')
        page.click('[data-testid="admin-ac-add-permission"]')
        expect(page.locator('[data-testid="admin-ac-perm-modal-close"]')).to_be_visible()

    def test_add_profile_drawer_opens(self, nexora_server, page):
        self._open(page, nexora_server)
        page.click('[data-testid="admin-ac-tab-profiles"]')
        page.click('[data-testid="admin-ac-add-profile"]')
        expect(page.locator('[data-testid="admin-ac-drawer-close"]')).to_be_visible()


@pytest.mark.flaky_e2e
class TestAdminUserDetail:
    def test_renders(self, nexora_server, page, seed_user_ids):
        _login_admin(page, nexora_server)
        uid = seed_user_ids["user@test.local"]
        page.goto(f"{nexora_server}/admin/users/{uid}")
        expect(page.locator('[data-testid="admin-userdetail-profile-form"]')).to_be_visible()

    def test_tab_overrides(self, nexora_server, page, seed_user_ids):
        _login_admin(page, nexora_server)
        uid = seed_user_ids["user@test.local"]
        page.goto(f"{nexora_server}/admin/users/{uid}")
        page.click('[data-testid="admin-userdetail-tab-overrides"]')
        expect(page.locator('[data-testid="admin-userdetail-overrides-form"]')).to_be_visible()

    def test_delete_opens_confirm_then_cancel(self, nexora_server, page, seed_user_ids):
        _login_admin(page, nexora_server)
        uid = seed_user_ids["user@test.local"]
        page.goto(f"{nexora_server}/admin/users/{uid}")
        page.click('[data-testid="admin-userdetail-delete"]')
        cancel = page.locator('[data-testid="admin-userdetail-confirm-delete-cancel"]')
        expect(cancel).to_be_visible()
        cancel.click()  # never confirm — would delete the seed user
        expect(cancel).to_be_hidden()


@pytest.mark.flaky_e2e
class TestAdminLogs:
    def test_renders(self, nexora_server, page):
        _login_admin(page, nexora_server)
        page.goto(f"{nexora_server}/admin/logs")
        expect(page.locator('[data-testid="admin-logs-filter-path"]')).to_be_visible()
        assert "internal server error" not in page.content().lower()

    def test_preset_buttons_present(self, nexora_server, page):
        _login_admin(page, nexora_server)
        page.goto(f"{nexora_server}/admin/logs")
        expect(page.locator('[data-testid="admin-logs-preset-24h"]')).to_be_visible()
