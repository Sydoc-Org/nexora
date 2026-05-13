"""Playwright smoke test — full login + 2FA + dashboard landing."""

import pyotp
import pytest


@pytest.mark.flaky_e2e
def test_login_smoke(nexora_server, page):
    page.goto(f"{nexora_server}/login")

    page.fill('input[name="username"]', "user@test.local")
    page.fill('input[name="password"]', "Test1234!")
    page.click('button[type="submit"]')

    # Login redirects to /verify_2fa for seed users (twoFA=1, InitReset=1).
    page.wait_for_url("**/verify_2fa", timeout=10000)

    # TOTP secret here MUST match sql/test/seed.sql for user@test.local.
    code = pyotp.TOTP("KRSXG5CTMVRXEZLU").now()
    page.fill('input[name="code"]', code)
    page.click('button[type="submit"]')

    # user@test.local has dashboard.view, so startpage_redirect_to lands on /dashboard.
    page.wait_for_url("**/dashboard", timeout=10000)
    assert "/dashboard" in page.url
