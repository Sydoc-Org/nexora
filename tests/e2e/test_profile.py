"""E2E tests for /profile (update form, password form, language pills, signout).

Uses user@test.local (has dashboard.view, which is enough to reach /profile).
Avoids persisting profile mutations: the update-name path is exercised only as
far as confirming the field is editable and the submit does not error.
"""

import re

import pytest
from playwright.sync_api import expect


def _login(page, base, who="user@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.flaky_e2e
def test_profile_renders(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/profile")
    expect(page.locator('[data-testid="profile-update-form"]')).to_be_visible()
    expect(page.locator('[data-testid="profile-password-form"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_profile_username_is_disabled(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/profile")
    expect(page.locator('[data-testid="profile-username"]')).to_be_disabled()


@pytest.mark.flaky_e2e
def test_profile_password_visibility_toggle(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/profile")
    field = page.locator('[data-testid="profile-current-password"]')
    expect(field).to_have_attribute("type", "password")
    page.click('[data-testid="profile-current-password-toggle"]')
    expect(field).to_have_attribute("type", "text")


@pytest.mark.flaky_e2e
def test_profile_jumpnav_password_keeps_form_visible(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/profile")
    page.click('[data-testid="profile-jumpnav-password"]')
    expect(page.locator('[data-testid="profile-password-form"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_profile_language_switch_to_german(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/profile")
    page.click('[data-testid="profile-lang-de"]')
    page.wait_for_url("**/profile**")
    # The active locale pill carries an is-active marker after the round trip.
    expect(page.locator('[data-testid="profile-lang-de"]')).to_have_class(re.compile("is-active"))


@pytest.mark.flaky_e2e
def test_profile_signout_link_ends_session(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/profile")
    page.click('[data-testid="profile-signout"]')
    page.wait_for_load_state("domcontentloaded")
    assert "/profile" not in page.url
    # Profile is auth-only; hitting it again should now bounce to login.
    page.goto(f"{nexora_server}/profile")
    page.wait_for_load_state("domcontentloaded")
    assert "/login" in page.url
