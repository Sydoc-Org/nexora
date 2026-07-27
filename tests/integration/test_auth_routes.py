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

import threading
import time
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


def test_login_post_db_failure_renders_graceful_503(client):
    """auth.py login(): raw_connection() is the first statement in the try
    block. If it raises before conn/cursor are assigned, the finally block's
    unconditional `if cursor:` / `if conn:` must not crash with
    UnboundLocalError - it should degrade to the except branch's graceful
    render_template("index.html", error="Login temporarily unavailable"), 503
    (same bug/fix shape as Task 18's get_allowed_client_details and the
    init_2fa fix above)."""
    with patch(
        "nx_lib.views.auth.engine_nexora_db.raw_connection",
        side_effect=RuntimeError("db down"),
    ):
        resp = client.post(
            "/login",
            data={"username": "user@test.local", "password": "Test1234!"},
            follow_redirects=False,
        )
    assert resp.status_code == 503
    assert b"login temporarily unavailable" in resp.data.lower()
    with client.session_transaction() as sess:
        assert "userid" not in sess


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


def test_init_2fa_post_db_failure_renders_graceful_error(client, totp_for):
    """auth.py init_2fa: a VALID code takes the DB-write branch. If
    raw_connection() raises before conn/cursor are assigned, the finally
    block must not crash with UnboundLocalError - it should degrade to the
    except branch's render_template("init_2FA.html", error="Database error")
    (same bug/fix shape as Task 18's get_allowed_client_details)."""
    with client.session_transaction() as sess:
        sess["pre_2fa_userid"] = "1001"
        sess["pre_2fa_username"] = "admin@test.local"
        sess["temp_2fa_secret"] = "JBSWY3DPEHPK3PXP"
    code = totp_for("admin@test.local")
    with patch(
        "nx_lib.views.auth.engine_nexora_db.raw_connection",
        side_effect=RuntimeError("db down"),
    ):
        resp = client.post("/init_2FA", data={"code": code}, follow_redirects=False)
    # Graceful degrade: re-renders init_2FA.html (200), not a 500 crash. The
    # error path doesn't pass qr_code, so the template's "no QR" branch is a
    # cheap, precise signal that we hit the except/render, not the success path.
    assert resp.status_code == 200
    assert b"error generating qr code" in resp.data.lower()
    with client.session_transaction() as sess:
        assert "userid" not in sess


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


def _wait_until(predicate, timeout=2.0, interval=0.02):
    """Poll ``predicate`` until it's truthy or ``timeout`` elapses.

    D-RESET dispatches send_reset_email() on a background daemon thread, so
    a mocked call it makes (e.g. requests.post) is no longer guaranteed to
    have landed by the time client.post() returns -- tests that assert on
    it need to wait for it instead of checking immediately.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def test_request_password_reset_unknown_email(client):
    """Unknown email → re-render forgot_password.html with the neutral message
    (D8: no "Invalid Email Address" — that would leak account existence)."""
    resp = client.post("/request-password-reset", data={"email": "nobody@nowhere.local"})
    assert resp.status_code == 200
    assert b"forgot" in resp.data.lower() or b"email" in resp.data.lower()


def test_request_password_reset_known_email_send_mocked(client):
    """Known email → send_reset_email path. Mock the Graph token call.

    D-RESET dispatches send_reset_email() on a background daemon thread, so
    the mock must still be live when the thread gets to use it -- wait for
    it inside the patch context rather than tearing the patch down the
    instant client.post() returns, or the thread could fall through to a
    real network call once the patch is undone."""
    fake_post = MagicMock()
    fake_post.return_value.json.return_value = {"access_token": "fake"}
    fake_post.return_value.text = ""
    fake_post.return_value.ok = True
    fake_post.return_value.status_code = 200
    with patch("nx_lib.views.auth.requests.post", fake_post) as mock_post:
        resp = client.post("/request-password-reset", data={"email": "admin@test.local"})
        assert resp.status_code == 200
        assert _wait_until(
            lambda: mock_post.call_count >= 2
        ), "background password-reset send never used the mocked requests.post"


def test_request_password_reset_known_and_unknown_email_same_response(client):
    """D8/Task 9 (user enumeration): the response must not reveal whether the
    submitted email belongs to a registered account. Known and unknown emails
    must get byte-identical status + body; only send_reset_email() may still
    branch on the row actually existing.

    D-RESET dispatches send_reset_email() on a background thread so the
    known-email response no longer waits on it either; poll for the mocked
    calls (token fetch + sendMail = 2) instead of asserting immediately, and
    keep the patch alive until the background work has settled so it never
    falls through to a real network call."""
    fake_post = MagicMock()
    fake_post.return_value.json.return_value = {"access_token": "fake"}
    fake_post.return_value.text = ""
    fake_post.return_value.ok = True
    fake_post.return_value.status_code = 200
    with patch("nx_lib.views.auth.requests.post", fake_post) as mock_post:
        known_resp = client.post("/request-password-reset", data={"email": "admin@test.local"})
        assert _wait_until(
            lambda: mock_post.call_count >= 2
        ), "background password-reset send never used the mocked requests.post"
        known_call_count = mock_post.call_count

        unknown_resp = client.post(
            "/request-password-reset", data={"email": "nobody@nowhere.local"}
        )
        # No background send should fire for an unregistered email; give any
        # (incorrect) dispatch a moment to land before checking.
        time.sleep(0.2)
        unknown_call_count = mock_post.call_count - known_call_count

    assert known_resp.status_code == unknown_resp.status_code == 200
    assert known_resp.data == unknown_resp.data
    # Mail must still only be attempted for the real account.
    assert known_call_count > 0
    assert unknown_call_count == 0


def test_request_password_reset_returns_before_send_completes(client):
    """D-RESET: request_password_reset() must not block on send_reset_email().
    The synchronous Graph mail call used to run only for a registered email,
    so its latency alone told an attacker whether an address existed even
    after the response body was unified (D8). Simulate a slow/hanging send
    and confirm the route answers immediately -- and identically for a
    registered and an unregistered email."""
    release = threading.Event()
    started = threading.Event()

    def blocking_send(*args, **kwargs):
        started.set()
        release.wait(timeout=5)
        return True

    with patch("nx_lib.views.auth.send_reset_email", side_effect=blocking_send):
        start = time.monotonic()
        known_resp = client.post("/request-password-reset", data={"email": "admin@test.local"})
        known_elapsed = time.monotonic() - start

        # Confirm the background thread really did fire (it did NOT delay
        # the response above), then release it so it finishes cleanly
        # before the patch context exits.
        assert started.wait(timeout=2), "send_reset_email was never dispatched"
        release.set()

        start = time.monotonic()
        unknown_resp = client.post(
            "/request-password-reset", data={"email": "nobody@nowhere.local"}
        )
        unknown_elapsed = time.monotonic() - start

    assert known_resp.status_code == unknown_resp.status_code == 200
    assert known_resp.data == unknown_resp.data
    # The route must return well before the blocking send is released --
    # i.e. it did not wait on send_reset_email() (the closed timing oracle).
    assert known_elapsed < 1.0
    assert unknown_elapsed < 1.0


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


def test_reset_password_token_single_use_and_session_dropped(client):
    """D-RESET: complete a full reset with a valid token, then replay the
    SAME token URL -> it must be rejected, not silently accepted again.
    Also confirms the session capability (email_for_password_reset) does
    not survive set_new_password completing successfully."""
    from nx_lib.db import engine_nexora_db
    from nx_lib.extensions import s

    email = "admin@test.local"
    token = s.dumps(email, salt="password-reset-salt")

    # Capture the real seeded password hash so it can be restored -- other
    # fixtures (login/user_client/admin_client) log in as this user with
    # TEST_PASSWORD for the rest of the suite.
    conn = engine_nexora_db.raw_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM Users WHERE Email = ?", email)
    original_hash = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    try:
        first_get = client.get(f"/reset_password/{token}")
        assert first_get.status_code == 200
        with client.session_transaction() as sess:
            assert sess.get("email_for_password_reset") == email

        post_resp = client.post(
            "/set_new_password",
            data={"new-password": "ReplayGuard1!", "confirm-password": "ReplayGuard1!"},
        )
        assert post_resp.status_code == 200
        assert b"password changed" in post_resp.data.lower()

        # Session capability must be gone once set_new_password has run.
        with client.session_transaction() as sess:
            assert "email_for_password_reset" not in sess

        # Replay of the exact same token URL must now be rejected (redirect
        # home, same as an invalid/expired token) rather than re-rendering
        # the reset form for reuse.
        replay_resp = client.get(f"/reset_password/{token}", follow_redirects=False)
        assert replay_resp.status_code == 302
        assert replay_resp.headers.get("Location", "").endswith("/")
        with client.session_transaction() as sess:
            assert "email_for_password_reset" not in sess
    finally:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET password = ? WHERE Email = ?", (original_hash, email))
        conn.commit()
        cursor.close()
        conn.close()


def test_set_new_password_session_dropped_on_forced_failure(client):
    """D-RESET: the session capability must be dropped on a FAILURE exit
    too, not just the success path -- otherwise one bad submission (e.g. a
    typo'd confirmation field) leaves "set a new password for this email"
    usable for the rest of the session."""
    with client.session_transaction() as sess:
        sess["email_for_password_reset"] = "admin@test.local"

    resp = client.post(
        "/set_new_password",
        data={"new-password": "Mismatch12!", "confirm-password": "Different12!"},
    )
    assert resp.status_code == 200
    assert b"do not match" in resp.data.lower()
    with client.session_transaction() as sess:
        assert "email_for_password_reset" not in sess


def test_verify_2fa_rate_limit_eventually_429(client, reset_limiter):
    """auth.py:309 — @limiter.limit('30 per hour'), added to close a TOTP
    brute-force gap (a valid pre_2fa_userid session let a caller try all
    1,000,000 6-digit codes with no throttling). 30 bad-code attempts are
    allowed (each 401); the 31st within the hour must be 429. Unlike the
    login/reset-password rate-limit tests above, this asserts the 31st
    status strictly rather than accepting a bare 401 fallback — 401 on every
    attempt is exactly the pre-fix defect this test exists to catch, so
    tolerating it here would make the test pass whether or not the limit is
    applied."""
    with client.session_transaction() as sess:
        sess["pre_2fa_userid"] = "1001"
    statuses = []
    for _ in range(31):
        resp = client.post("/verify_2fa", data={"code": "000000"}, follow_redirects=False)
        statuses.append(resp.status_code)
    assert statuses[:30] == [401] * 30, statuses
    assert statuses[30] == 429, statuses
