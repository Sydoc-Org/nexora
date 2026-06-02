"""Cross-browser smoke. Runs the canonical login + 2FA flow in whichever
engines are passed via --browser (chromium by default; add firefox/webkit in
CI). Kept separate from the page-flow suites so the matrix run stays cheap.

  pytest tests/e2e/test_cross_browser.py --browser chromium --browser firefox --browser webkit
"""

import pyotp
import pytest
from playwright.sync_api import expect

# Matches sql/test/seed.sql and tests/conftest.py TOTP_SECRETS.
USER_TOTP_SECRET = "KRSXG5CTMVRXEZLU"


@pytest.mark.flaky_e2e
def test_login_2fa_flow(nexora_server, page):
    page.goto(f"{nexora_server}/login")
    page.fill('[data-testid="login-username"]', "user@test.local")
    page.fill('[data-testid="login-password"]', "Test1234!")
    page.click('[data-testid="login-submit"]')
    page.wait_for_url("**/verify_2fa", timeout=15000)

    code = pyotp.TOTP(USER_TOTP_SECRET).now()
    page.fill('[data-testid="verify-2fa-code"]', code)
    page.click('[data-testid="verify-2fa-submit"]')
    page.wait_for_url("**/dashboard", timeout=15000)
    expect(page.locator('[data-testid="dashboard-process-filter"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_dev_login_renders_dashboard(nexora_server, page):
    # Pure cross-engine rendering smoke via the 2FA-bypass route.
    page.goto(f"{nexora_server}/dev/login/admin@test.local")
    page.wait_for_url("**/dashboard")
    expect(page.locator('[data-testid="nexora-logo-home"]')).to_be_visible()
