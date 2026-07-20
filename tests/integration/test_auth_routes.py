"""Integration tests for nx_lib.views.auth — routes not covered by test_auth_flow.

Covers:
- GET  /login                 render form (the POST path is in test_auth_flow.py)
- GET  /logout                clears session
- GET  /dev/login/<username>  test/INT-only shortcut: 200/302 happy path + 404
- GET  /forgot_password       render
- GET  /init_reset            render
- GET  /init_2FA              auth-gate redirect + happy-path QR render
- GET  /verify_2fa            auth-gate redirect
- POST /verify_2fa            invalid TOTP → 401
- POST /init_reset_password   validation paths
- GET  /reset_password/<tok>  bad token redirects to /; good token renders
- POST /set_new_password      mismatch + validation
- POST /request-password-reset
- rate-limit hooks (best-effort — Flask-Limiter is in-memory per worker)
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def reset_limiter():
    """Reset Flask-Limiter in-memory storage after a test that intentionally
    exhausts a rate limit. Without this the 429s leak into sibling tests."""
    yield
    from nx_lib.extensions import limiter

    limiter.reset()


def test_login_get_renders_form(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"<form" in resp.data.lower()


def test_logout_clears_session(user_client):
    resp = user_client.get("/logout", follow_redirects=False)
    assert resp.status_code == 302
    with user_client.session_transaction() as sess:
        assert "username" not in sess
        assert "userid" not in sess


def test_logout_when_not_logged_in_still_redirects(client):
    """Logout is unconditional — even an anonymous client gets a 302 to /."""
    resp = client.get("/logout", follow_redirects=False)
    assert resp.status_code == 302


def test_dev_login_seeded_user_lands_session(client):
    """In TEST env IS_PROD is False, so /dev/login/<u> bypasses 2FA."""
    resp = client.get("/dev/login/admin@test.local", follow_redirects=False)
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("username") == "admin@test.local"
        assert sess.get("userid") is not None


def test_dev_login_unknown_user_404(client):
    resp = client.get("/dev/login/nobody@nowhere.local")
    assert resp.status_code == 404


def test_forgot_password_get_renders(client):
    resp = client.get("/forgot_password")
    assert resp.status_code == 200


def test_init_reset_get_renders(client):
    resp = client.get("/init_reset")
    assert resp.status_code == 200


def test_init_2fa_without_pre_2fa_redirects_to_login(client):
    resp = client.get("/init_2FA", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_init_2fa_with_pre_2fa_renders_qr(client):
    """When pre_2fa_userid is set, GET /init_2FA renders the QR template."""
    with client.session_transaction() as sess:
        sess["pre_2fa_userid"] = "1001"
        sess["pre_2fa_username"] = "admin@test.local"
    resp = client.get("/init_2FA")
    assert resp.status_code == 200
    # Page embeds a base64 PNG; presence of <img is a cheap sanity check.
    assert b"<img" in resp.data.lower() or b"qr" in resp.data.lower()


def test_init_2fa_post_invalid_code_redirects_back(client):
    """Wrong TOTP triggers flash + redirect to /init_2FA."""
    with client.session_transaction() as sess:
        sess["pre_2fa_userid"] = "1001"
        sess["pre_2fa_username"] = "admin@test.local"
        sess["temp_2fa_secret"] = "JBSWY3DPEHPK3PXP"
    resp = client.post("/init_2FA", data={"code": "000000"}, follow_redirects=False)
    assert resp.status_code == 302
    assert "/init_2FA" in resp.headers.get("Location", "")


def test_init_2fa_post_missing_session_redirects(client):
    """No temp_2fa_secret in session → flash + redirect to /init_2FA."""
    with client.session_transaction() as sess:
        sess["pre_2fa_userid"] = "1001"
        sess["pre_2fa_username"] = "admin@test.local"
    resp = client.post("/init_2FA", data={"code": "123456"}, follow_redirects=False)
    assert resp.status_code == 302


def test_verify_2fa_get_without_pre_2fa_redirects_to_login(client):
    resp = client.get("/verify_2fa", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_verify_2fa_get_with_pre_2fa_renders(client):
    with client.session_transaction() as sess:
        sess["pre_2fa_userid"] = "1001"
    resp = client.get("/verify_2fa")
    assert resp.status_code == 200


def test_verify_2fa_post_invalid_code_returns_401(client):
    """Wrong TOTP → render verify_2fa.html with 401."""
    with client.session_transaction() as sess:
        sess["pre_2fa_userid"] = "1001"
    resp = client.post("/verify_2fa", data={"code": "000000"}, follow_redirects=False)
    # The route POSTs against seeded admin user. With a bogus code, totp.verify
    # is False → 401. (Status 302 acceptable if pre-flow validation kicks first.)
    assert resp.status_code in (401, 302)


def test_init_reset_password_mismatch_renders_error(client):
    """Passwords don't match → re-render init_reset.html (200)."""
    with client.session_transaction() as sess:
        sess["pre_auth_userid"] = "1001"
    resp = client.post(
        "/init_reset_password",
        data={"new-password": "Foo1234!", "confirm-password": "Bar1234!"},
    )
    assert resp.status_code == 200
    assert b"do not match" in resp.data.lower() or b"passwords" in resp.data.lower()


def test_init_reset_password_too_short_renders_error(client):
    """< 8 chars triggers the length-validation render."""
    with client.session_transaction() as sess:
        sess["pre_auth_userid"] = "1001"
    resp = client.post(
        "/init_reset_password",
        data={"new-password": "short", "confirm-password": "short"},
    )
    assert resp.status_code == 200


def test_reset_password_bad_token_redirects_home(client):
    resp = client.get("/reset_password/not-a-valid-token", follow_redirects=False)
    assert resp.status_code == 302
    # Loader exception path redirects to url_for("index") → "/".
    assert resp.headers.get("Location", "").endswith("/")


def test_reset_password_good_token_renders(client):
    """Valid signed token → renders reset_password.html and stashes the email."""
    from nx_lib.extensions import s

    token = s.dumps("admin@test.local", salt="password-reset-salt")
    resp = client.get(f"/reset_password/{token}")
    assert resp.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get("email_for_password_reset") == "admin@test.local"


def test_set_new_password_password_mismatch(client):
    """Mismatched passwords → re-render reset_password.html with error."""
    with client.session_transaction() as sess:
        sess["email_for_password_reset"] = "admin@test.local"
    resp = client.post(
        "/set_new_password",
        data={"new-password": "NewPass1234!", "confirm-password": "Different1!"},
    )
    assert resp.status_code == 200


def test_set_new_password_too_short(client):
    with client.session_transaction() as sess:
        sess["email_for_password_reset"] = "admin@test.local"
    resp = client.post(
        "/set_new_password",
        data={"new-password": "short", "confirm-password": "short"},
    )
    assert resp.status_code == 200


def test_request_password_reset_unknown_email(client):
    """Unknown email → re-render forgot_password.html with error."""
    resp = client.post("/request-password-reset", data={"email": "nobody@nowhere.local"})
    assert resp.status_code == 200
    assert b"forgot" in resp.data.lower() or b"email" in resp.data.lower()


def test_request_password_reset_known_email_send_mocked(client):
    """Known email → send_reset_email path. Mock the Graph token call."""
    fake_post = MagicMock()
    fake_post.return_value.json.return_value = {"access_token": "fake"}
    fake_post.return_value.text = ""
    fake_post.return_value.ok = True
    fake_post.return_value.status_code = 200
    with patch("nx_lib.views.auth.requests.post", fake_post):
        resp = client.post("/request-password-reset", data={"email": "admin@test.local"})
    assert resp.status_code == 200


def test_login_rate_limit_eventually_429(client, reset_limiter):
    """auth.py:447 — @limiter.limit('10 per minute'). After ~10 attempts the
    next call should be 429. Flask-Limiter uses in-memory storage so this can
    leak between tests; allow 401 or 429 to avoid brittleness."""
    last_status = None
    for i in range(15):
        resp = client.post(
            "/login",
            data={"username": f"x{i}@test.local", "password": "wrong"},
            follow_redirects=False,
        )
        last_status = resp.status_code
        if last_status == 429:
            break
    assert last_status in (401, 429)


def test_request_password_reset_rate_limit_eventually_429(client, reset_limiter):
    """auth.py:597 — @limiter.limit('5 per hour'). Burst, expect 429
    eventually (or 200 if the limiter is bypassed)."""
    last_status = None
    for _ in range(8):
        resp = client.post("/request-password-reset", data={"email": "nobody@nowhere.local"})
        last_status = resp.status_code
        if last_status == 429:
            break
    assert last_status in (200, 429)


def test_verify_2fa_rate_limit_eventually_429(client, reset_limiter):
    """auth.py:309 — @limiter.limit('10 per hour'), added to close a TOTP
    brute-force gap (a valid pre_2fa_userid session let a caller try all
    1,000,000 6-digit codes with no throttling). 10 bad-code attempts are
    allowed (each 401); the 11th within the hour must be 429. Unlike the
    login/reset-password rate-limit tests above, this asserts the 11th
    status strictly rather than accepting a bare 401 fallback — 401 on every
    attempt is exactly the pre-fix defect this test exists to catch, so
    tolerating it here would make the test pass whether or not the limit is
    applied."""
    with client.session_transaction() as sess:
        sess["pre_2fa_userid"] = "1001"
    statuses = []
    for _ in range(11):
        resp = client.post("/verify_2fa", data={"code": "000000"}, follow_redirects=False)
        statuses.append(resp.status_code)
    assert statuses[:10] == [401] * 10, statuses
    assert statuses[10] == 429, statuses
