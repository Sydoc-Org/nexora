"""E2E tests for the /admin/* pages.

admin@test.local holds every permission (test seed), so all admin pages render.
Tables absent in TEST (Logs, MaintenanceBanner) make those pages render empty
but not 500. Destructive controls (delete org/user) are only opened and then
cancelled — never confirmed against seed data.

Route paths come from admin.register_routes: overview is /admin, user detail is
/admin/users/<id>.
"""

import json
import re
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import expect
from sqlalchemy import text

from nx_lib.db import engine_nexora_db


def _login_admin(page, base):
    page.goto(f"{base}/dev/login/admin@test.local")
    page.wait_for_url("**/dashboard")


def _delete_test_profile(name):
    """Remove a profile (and any permission rows on it) created by a test.

    Runs in the pytest process (ENVIRONMENT=TEST), which shares the database
    with the browser subprocess started by the nexora_server fixture.
    """
    with engine_nexora_db.begin() as conn:
        access_id = conn.execute(
            text("SELECT AccessID FROM AccessProfile WHERE Name = :n"), {"n": name}
        ).scalar()
        if access_id is not None:
            conn.execute(
                text("DELETE FROM AccessProfilePermission WHERE AccessID = :a"),
                {"a": access_id},
            )
            conn.execute(text("DELETE FROM AccessProfile WHERE AccessID = :a"), {"a": access_id})


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

    def test_untouched_profile_drawer_saves_no_permission_rows(self, nexora_server, page):
        """Task 45 regression: every permission radio defaults to the neutral
        (unset/inherit) state, not Deny, so saving a drawer the admin never
        touched must create zero AccessProfilePermission rows."""
        profile_name = "Task45UntouchedProfile"
        _delete_test_profile(profile_name)
        try:
            self._open(page, nexora_server)
            page.click('[data-testid="admin-ac-tab-profiles"]')
            page.click('[data-testid="admin-ac-add-profile"]')
            expect(page.locator('[data-testid="admin-ac-drawer-close"]')).to_be_visible()
            page.fill('[data-testid="admin-ac-profile-name"]', profile_name)

            with page.expect_response(
                lambda r: "/api/admin/access_profile/save" in r.url
            ) as resp_info:
                page.click('[data-testid="admin-ac-drawer-save"]')
            assert resp_info.value.ok

            with engine_nexora_db.connect() as conn:
                access_id = conn.execute(
                    text("SELECT AccessID FROM AccessProfile WHERE Name = :n"),
                    {"n": profile_name},
                ).scalar()
                assert access_id is not None, "profile was not created"
                row_count = conn.execute(
                    text("SELECT COUNT(*) FROM AccessProfilePermission WHERE AccessID = :a"),
                    {"a": access_id},
                ).scalar()
                assert row_count == 0
        finally:
            _delete_test_profile(profile_name)


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

    def test_manual_date_edit_after_preset_wins_on_first_change(self, nexora_server, page):
        """Regression: clicking "Last hour" sets a sub-day presetRangeOverride
        that fetchLogs() prefers over the visible date inputs. A prior bug had
        the override-clearing listener registered in a separate
        DOMContentLoaded handler that fired AFTER wireLiveFilters()'s own
        change listener already re-fetched with the stale override — so the
        user's first manual date edit was silently discarded. Both must now
        live in the same handler so the very first edit wins."""
        _login_admin(page, nexora_server)

        captured = []

        def _capture(route):
            qs = parse_qs(urlparse(route.request.url).query)
            captured.append(qs)
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"logs": [], "page": 1, "pages": 1, "total": 0}),
            )

        page.route("**/api/admin/logs/search*", _capture)
        page.goto(f"{nexora_server}/admin/logs")
        expect(page.locator('[data-testid="admin-logs-filter-path"]')).to_be_visible()

        before = len(captured)
        preset_1h = page.locator('[data-testid="admin-logs-preset-1h"]')
        preset_1h.click()
        expect(preset_1h).to_have_class(re.compile(r"\bis-active\b"))
        assert len(captured) > before
        # The "Last hour" preset must have sent a precise datetime override,
        # not a bare date, confirming it actually engaged presetRangeOverride.
        assert " " in captured[-1]["start_date"][0]

        before = len(captured)
        start_input = page.locator('[data-testid="admin-logs-filter-start"]')
        # fill() on a native <input type="date"> already dispatches its own
        # change event — no need to dispatch one manually.
        start_input.fill("2020-06-15")

        assert len(captured) == before + 1, "manual date edit must trigger exactly one refetch"
        assert captured[-1]["start_date"][0] == "2020-06-15", (
            "the FIRST manual date edit after a preset must be honored immediately, "
            "not silently discarded in favor of the stale preset override"
        )
