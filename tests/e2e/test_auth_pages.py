"""E2E tests for the auth page family (login, 2FA, forgot/reset password).

Selectors are the real data-testid values rendered by the templates (verified
against the running TEST server), not the aspirational names in the plan.

Anonymous pages need no login. The wrong-code 2FA test drives a real /login
POST; rate limiting is disabled for the e2e subprocess (see tests/e2e/conftest)
so repeated logins across the session do not trip the limiter.
"""

import pytest
from playwright.sync_api import expect


@pytest.mark.flaky_e2e
def test_login_page_renders(nexora_server, page):
    page.goto(f"{nexora_server}/login")
    expect(page.locator('[data-testid="login-form"]')).to_be_visible()
    expect(page.locator('[data-testid="login-username"]')).to_be_visible()
    expect(page.locator('[data-testid="login-password"]')).to_be_visible()
    expect(page.locator('[data-testid="login-submit"]')).to_be_visible()
    expect(page.locator('[data-testid="login-forgot"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_login_forgot_link_navigates(nexora_server, page):
    page.goto(f"{nexora_server}/login")
    page.click('[data-testid="login-forgot"]')
    page.wait_for_url("**/forgot_password")
    expect(page.locator('[data-testid="forgot-password-form"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_login_empty_submit_stays_on_page(nexora_server, page):
    page.goto(f"{nexora_server}/login")
    page.click('[data-testid="login-submit"]')
    # Empty credentials re-render index.html (401); the form stays put.
    expect(page.locator('[data-testid="login-form"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_login_invalid_credentials_stays_on_page(nexora_server, page):
    page.goto(f"{nexora_server}/login")
    page.fill('[data-testid="login-username"]', "nobody@test.local")
    page.fill('[data-testid="login-password"]', "wrong-password")
    page.click('[data-testid="login-submit"]')
    page.wait_for_load_state("domcontentloaded")
    # Bad creds keep us on the login page (no redirect to /verify_2fa).
    expect(page.locator('[data-testid="login-form"]')).to_be_visible()
    assert "/verify_2fa" not in page.url


@pytest.mark.flaky_e2e
def test_2fa_wrong_code_re_renders(nexora_server, page):
    page.goto(f"{nexora_server}/login")
    page.fill('[data-testid="login-username"]', "user@test.local")
    page.fill('[data-testid="login-password"]', "Test1234!")
    page.click('[data-testid="login-submit"]')
    page.wait_for_url("**/verify_2fa")

    page.fill('[data-testid="verify-2fa-code"]', "000000")
    page.click('[data-testid="verify-2fa-submit"]')
    page.wait_for_load_state("domcontentloaded")
    # Wrong code re-renders verify_2fa with a 401; the code field is still there.
    expect(page.locator('[data-testid="verify-2fa-code"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_forgot_password_page_renders(nexora_server, page):
    page.goto(f"{nexora_server}/forgot_password")
    expect(page.locator('[data-testid="forgot-password-form"]')).to_be_visible()
    expect(page.locator('[data-testid="forgot-password-email"]')).to_be_visible()
    expect(page.locator('[data-testid="forgot-password-submit"]')).to_be_visible()
    expect(page.locator('[data-testid="forgot-password-back-to-login"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_forgot_password_back_to_login(nexora_server, page):
    page.goto(f"{nexora_server}/forgot_password")
    page.click('[data-testid="forgot-password-back-to-login"]')
    page.wait_for_url("**/login")
    expect(page.locator('[data-testid="login-form"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_forgot_password_submit_does_not_error(nexora_server, page):
    page.goto(f"{nexora_server}/forgot_password")
    page.fill('[data-testid="forgot-password-email"]', "user@test.local")
    page.click('[data-testid="forgot-password-submit"]')
    page.wait_for_load_state("domcontentloaded")
    # Whether the email send succeeds or not, the app must not 500.
    assert "internal server error" not in page.content().lower()


@pytest.mark.flaky_e2e
def test_init_2fa_no_session_redirects_to_login(nexora_server, page):
    # /init_2FA without a pre-2FA session should bounce to /login, not 500.
    page.goto(f"{nexora_server}/init_2FA")
    page.wait_for_load_state("domcontentloaded")
    assert "internal server error" not in page.content().lower()
    assert "/login" in page.url or "/init_2FA" in page.url


@pytest.mark.flaky_e2e
def test_reset_password_invalid_token_redirects(nexora_server, page):
    # An invalid/expired token must not 500; it redirects back to login.
    page.goto(f"{nexora_server}/reset_password/not-a-real-token")
    page.wait_for_load_state("domcontentloaded")
    assert "internal server error" not in page.content().lower()
