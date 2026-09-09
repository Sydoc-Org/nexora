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

import re
import threading
import time
from unittest.mock import MagicMock, patch

import bcrypt
import pytest


def _without_csrf_token(body):
    """Blank the CSRF token out of a rendered page before comparing two of them.

    Flask-WTF re-signs the session's CSRF secret on every request with an
    itsdangerous timestamp, and those have 1-second granularity -- so two
    otherwise byte-identical responses rendered either side of a second
    boundary differ, everywhere that token is rendered. It is per-request
    noise, not part of the "a registered and an unregistered address must
    look identical" contract the callers are asserting.
    """
    body = re.sub(rb'(?<=name="csrf-token" content=")[^"]*', b"", body)
    # The page carries the same token twice: the <meta> tag above and the
    # form's hidden input. Blanking only the first left the second to differ
    # across a second boundary -- the exact flake this helper exists to stop.
    return re.sub(rb'(?<=name="csrf_token" value=")[^"]*', b"", body)


def _clear_reset_token_marker(client, token):
    """Forget any "this reset token was already spent" mark left in the shared
    response cache.

    itsdangerous timestamps have 1-second granularity, so two of these tests
    minting a token for the same email within the same second get the SAME
    token string, and a predecessor's successful write leaves it marked
    consumed -- the next test's GET /reset_password/<token> then 302s instead
    of rendering.

    MUST delete inside ``client.application.app_context()``, never bare:
    outside a context Flask-Caching falls back to whatever app LAST called
    ``cache.init_app()`` -- e.g. test_admin_routes' module-scoped
    ``prod_csp_app`` -- so a bare delete clears THAT app's backend while the
    route under test keeps reading the session app's stale mark. Same trap
    documented at test_dashboard_routes._clear_response_cache.
    """
    from nx_lib.extensions import cache
    from nx_lib.views.auth import _reset_token_cache_key

    with client.application.app_context():
        cache.delete(_reset_token_cache_key(token))


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


def test_dev_login_blocks_non_loopback_caller(client):
    """Security #193: the passwordless dev-login must 404 for any non-loopback
    caller even on a non-PROD env, so a network-reachable INT/STAGING/TEST
    instance can't be used as a remote password+2FA bypass."""
    resp = client.get(
        "/dev/login/admin@test.local",
        environ_overrides={"REMOTE_ADDR": "203.0.113.7"},
        follow_redirects=False,
    )
    assert resp.status_code == 404
    with client.session_transaction() as sess:
        assert sess.get("username") is None  # no session was established


def test_dev_users_blocks_non_loopback_caller(client):
    """Security #193: the username-enumeration helper must 404 for a
    non-loopback caller too."""
    resp = client.get("/dev/users", environ_overrides={"REMOTE_ADDR": "203.0.113.7"})
    assert resp.status_code == 404


def test_dev_users_allows_loopback(client):
    """Local dev (nx --loginas, Playwright on 127.0.0.1) must still work."""
    resp = client.get("/dev/users")
    assert resp.status_code == 200


def test_login_unknown_user_runs_bcrypt_constant_time(client, monkeypatch):
    """Security #193: an unknown username must still pay one bcrypt comparison
    (against a dummy hash) so response latency can't distinguish real usernames
    from invalid ones."""
    import nx_lib.views.auth as auth

    calls = []
    monkeypatch.setattr(auth.bcrypt, "checkpw", lambda pw, h: calls.append((pw, h)) or False)

    resp = client.post(
        "/login",
        data={"username": "definitely-not-a-real-user-xyz@nowhere.local", "password": "whatever"},
    )
    assert resp.status_code == 401
    assert calls, "login must run bcrypt.checkpw even for an unknown username (constant-time)"


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


def test_init_reset_password_db_failure_renders_visible_error(client):
    """Task 41: init_reset_password's `except Exception: return` used to
    hand Flask a bare None -> 500. A DB error mid-request must now degrade
    to a real response instead of crashing.

    Phase-10 finding fix: Task 41 originally flash()ed the error and
    redirected to /login, but index.html never renders flashed messages —
    the user saw nothing there and the stale message resurfaced later on an
    unrelated page. It must now render index.html directly with the error
    visible in the response the user actually receives (login()'s own
    error idiom)."""
    with client.session_transaction() as sess:
        sess["pre_auth_userid"] = "1001"
    with patch(
        "nx_lib.views.auth.engine_nexora_db.raw_connection",
        side_effect=RuntimeError("db down"),
    ):
        resp = client.post(
            "/init_reset_password",
            data={"new-password": "NewPass1234!", "confirm-password": "NewPass1234!"},
            follow_redirects=False,
        )
    assert resp.status_code == 200
    assert b"something went wrong" in resp.data.lower()
    with client.session_transaction() as sess:
        assert "_flashes" not in sess


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


def test_reset_password_invite_token_renders_welcome_page(client):
    """An invite token gets the welcome page, not the reset page.

    Same URL, same form, same POST target -- only the copy differs, because
    an invited user has no previous password to reset. The error re-render
    has to stay on the welcome page too, or a typo'd confirmation would bump
    them onto reset wording mid-flow.
    """
    from nx_lib.extensions import s
    from nx_lib.views.auth import _reset_token_cache_key

    token = s.dumps("admin@test.local", salt="user-invite-salt")
    resp = client.get(f"/reset_password/{token}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "set-password-form" in body
    assert "reset-password-form" not in body
    with client.session_transaction() as sess:
        assert sess.get("email_for_password_reset") == "admin@test.local"
        assert sess.get("password_set_is_invite") is True
        sess["password_reset_token_key"] = _reset_token_cache_key("test-invite-mismatch")

    resp = client.post(
        "/set_new_password",
        data={"new-password": "NewPass1234!", "confirm-password": "Different1!"},
    )
    assert resp.status_code == 200
    assert "set-password-form" in resp.get_data(as_text=True)


def test_set_new_password_password_mismatch(client):
    """Mismatched passwords → re-render reset_password.html with error."""
    from nx_lib.views.auth import _reset_token_cache_key

    with client.session_transaction() as sess:
        sess["email_for_password_reset"] = "admin@test.local"
        # Phase-10 finding fix: set_new_password() now also requires a live
        # (present, not-yet-consumed) password_reset_token_key -- give it
        # one so this test still exercises the mismatch validation path
        # rather than the new not-consumed guard.
        sess["password_reset_token_key"] = _reset_token_cache_key("test-mismatch-token")
    resp = client.post(
        "/set_new_password",
        data={"new-password": "NewPass1234!", "confirm-password": "Different1!"},
    )
    assert resp.status_code == 200


def test_set_new_password_too_short(client):
    from nx_lib.views.auth import _reset_token_cache_key

    with client.session_transaction() as sess:
        sess["email_for_password_reset"] = "admin@test.local"
        sess["password_reset_token_key"] = _reset_token_cache_key("test-too-short-token")
    resp = client.post(
        "/set_new_password",
        data={"new-password": "short", "confirm-password": "short"},
    )
    assert resp.status_code == 200


def test_set_new_password_no_session_redirects_to_login(client):
    """GET/POST with no active reset session (no email_for_password_reset in
    session, e.g. navigating straight to the URL) used to fall through to
    session["email_for_password_reset"] raising KeyError, caught by the bare
    `except Exception: return` -> None -> Flask 500. Task 41: must redirect,
    not crash."""
    resp = client.post(
        "/set_new_password",
        data={"new-password": "NewPass1234!", "confirm-password": "NewPass1234!"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_set_new_password_db_failure_renders_visible_error(client):
    """Task 41: set_new_password's `except Exception: return` used to hand
    Flask a bare None -> 500. A DB error mid-request must now degrade to a
    real response instead of crashing.

    Phase-10 finding fix: Task 41 originally flash()ed the error and
    redirected to /login, but index.html never renders flashed messages --
    the user saw nothing there and the stale message resurfaced later on an
    unrelated page. It must now render index.html directly with the error
    visible in the response the user actually receives. A DB failure is a
    genuinely terminal exit (not a retry-able mistake), so the reset-session
    capability is still dropped here -- unlike a validation-error retry."""
    from nx_lib.views.auth import _reset_token_cache_key

    with client.session_transaction() as sess:
        sess["email_for_password_reset"] = "admin@test.local"
        sess["password_reset_token_key"] = _reset_token_cache_key("test-db-failure-token")
    with patch(
        "nx_lib.views.auth.engine_nexora_db.raw_connection",
        side_effect=RuntimeError("db down"),
    ):
        resp = client.post(
            "/set_new_password",
            data={"new-password": "NewPass1234!", "confirm-password": "NewPass1234!"},
            follow_redirects=False,
        )
    assert resp.status_code == 200
    assert b"something went wrong" in resp.data.lower()
    with client.session_transaction() as sess:
        assert "_flashes" not in sess
        # The D-RESET capability must still be dropped on this failure exit.
        assert "email_for_password_reset" not in sess


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
    assert _without_csrf_token(known_resp.data) == _without_csrf_token(unknown_resp.data)
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
    assert _without_csrf_token(known_resp.data) == _without_csrf_token(unknown_resp.data)
    # The route must return well before the blocking send's 5s hold is
    # released -- i.e. it did not wait on send_reset_email() (the closed
    # timing oracle). 3s (not 1s) so full-suite machine load can't flake it.
    assert known_elapsed < 3.0
    assert unknown_elapsed < 3.0


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


def test_reset_password_get_twice_then_write_consumes_token(client):
    """Phase-10 finding fix: rendering the reset-password GET link -- a
    plain browser refresh/tab-restore/back-forward, or a link-scanning mail
    gateway (Defender Safe Links, Proofpoint, Mimecast, ...) prefetching the
    URL before the user ever clicks it -- must NOT consume the token; only a
    SUCCESSFUL set_new_password() write does. GET the same link twice
    (simulating that refresh/prefetch) and confirm it's still valid both
    times, complete the reset, then confirm the token IS rejected on replay
    only after that write, and the session capability is gone."""
    from nx_lib.db import engine_nexora_db
    from nx_lib.extensions import s

    email = "admin@test.local"
    token = s.dumps(email, salt="password-reset-salt")
    _clear_reset_token_marker(client, token)

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

        # Simulated refresh / tab-restore / mail-gateway prefetch: GET the
        # exact same link again. It must still succeed -- not yet consumed
        # just from being rendered -- rather than being rejected as an
        # already-used token.
        second_get = client.get(f"/reset_password/{token}")
        assert second_get.status_code == 200
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
        # home, same as an invalid/expired token) -- the successful WRITE is
        # what consumed it, not either of the earlier renders.
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


def test_set_new_password_mismatch_does_not_drop_session(client):
    """Phase-10 finding fix: a validation-error re-render (mismatch, empty,
    too short, password reuse) must NOT drop the session capability -- only
    a terminal exit (success, or a hard failure) does. Popping it on every
    render-with-error left a user who simply mistypes their confirmation
    with no recovery path, forcing them to request an entirely new reset
    email for a one-character typo."""
    from nx_lib.views.auth import _reset_token_cache_key

    with client.session_transaction() as sess:
        sess["email_for_password_reset"] = "admin@test.local"
        sess["password_reset_token_key"] = _reset_token_cache_key(
            "test-mismatch-does-not-drop-session-token"
        )

    resp = client.post(
        "/set_new_password",
        data={"new-password": "Mismatch12!", "confirm-password": "Different12!"},
    )
    assert resp.status_code == 200
    assert b"do not match" in resp.data.lower()
    with client.session_transaction() as sess:
        assert sess.get("email_for_password_reset") == "admin@test.local"


def test_set_new_password_mismatch_then_retry_with_same_token_succeeds(client):
    """Phase-10 finding fix: prove the retry path actually works end to end
    -- submit a mismatched confirmation (re-renders with an error), then
    submit a correct confirmation using the SAME reset token/session, and
    it succeeds. Only then is the session capability dropped."""
    from nx_lib.db import engine_nexora_db
    from nx_lib.extensions import s

    email = "admin@test.local"
    token = s.dumps(email, salt="password-reset-salt")
    _clear_reset_token_marker(client, token)

    conn = engine_nexora_db.raw_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM Users WHERE Email = ?", email)
    original_hash = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    try:
        get_resp = client.get(f"/reset_password/{token}")
        assert get_resp.status_code == 200

        mismatch_resp = client.post(
            "/set_new_password",
            data={"new-password": "Mismatch123!", "confirm-password": "Different123!"},
        )
        assert mismatch_resp.status_code == 200
        assert b"do not match" in mismatch_resp.data.lower()
        with client.session_transaction() as sess:
            assert sess.get("email_for_password_reset") == email

        retry_resp = client.post(
            "/set_new_password",
            data={"new-password": "RetryWorks1!", "confirm-password": "RetryWorks1!"},
        )
        assert retry_resp.status_code == 200
        assert b"password changed" in retry_resp.data.lower()
        with client.session_transaction() as sess:
            assert "email_for_password_reset" not in sess
    finally:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET password = ? WHERE Email = ?", (original_hash, email))
        conn.commit()
        cursor.close()
        conn.close()


def test_set_new_password_missing_token_key_rejected(client):
    """Phase-10 finding fix: a session carrying the "may set a new password"
    capability but missing password_reset_token_key (e.g. seeded directly,
    or a pre-338e55f session that predates the key being stashed by
    reset_password()) must be rejected cleanly -- redirected to /login, not
    allowed to write silently and not a crash. Before this fix the
    `if token_cache_key:` guard around the cache.set() call let the write
    through while quietly skipping consumption, leaving the underlying
    signed token replayable via GET for its full max_age window."""
    with client.session_transaction() as sess:
        sess["email_for_password_reset"] = "admin@test.local"
        # Deliberately no password_reset_token_key.
    resp = client.post(
        "/set_new_password",
        data={"new-password": "ShouldNotWork1!", "confirm-password": "ShouldNotWork1!"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")
    with client.session_transaction() as sess:
        assert "email_for_password_reset" not in sess
        assert "password_reset_token_key" not in sess


def test_set_new_password_cross_session_replay_rejected_after_first_write(client):
    """Phase-10 finding fix (the core gap): two sessions holding the SAME
    reset-token capability (e.g. a mail-gateway prescan or shared-inbox
    viewer fetched the link before the real user did) -- the first to POST
    a successful write burns the token; the second's subsequent POST must
    be REJECTED (redirected to /login), not silently allowed to overwrite
    the password the legitimate user just set. Before this fix,
    authorization was purely `"email_for_password_reset" in session`, which
    stayed true in session B regardless of what session A had already
    consumed."""
    from nx_lib.db import engine_nexora_db
    from nx_lib.extensions import s

    email = "admin@test.local"
    token = s.dumps(email, salt="password-reset-salt")
    _clear_reset_token_marker(client, token)

    conn = engine_nexora_db.raw_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM Users WHERE Email = ?", email)
    original_hash = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    session_a = client
    session_b = client.application.test_client()

    try:
        # Both sessions fetch the same link -- GET is side-effect-free, so
        # both legitimately end up holding the capability + token key.
        get_a = session_a.get(f"/reset_password/{token}")
        assert get_a.status_code == 200
        get_b = session_b.get(f"/reset_password/{token}")
        assert get_b.status_code == 200

        # Session A (the real user) completes the reset first.
        resp_a = session_a.post(
            "/set_new_password",
            data={"new-password": "FirstWriter1!", "confirm-password": "FirstWriter1!"},
        )
        assert resp_a.status_code == 200
        assert b"password changed" in resp_a.data.lower()

        # Session B attempts to reuse the same (now-consumed) token key --
        # must be rejected, not allowed to overwrite session A's write.
        resp_b = session_b.post(
            "/set_new_password",
            data={
                "new-password": "SecondWriterHijack1!",
                "confirm-password": "SecondWriterHijack1!",
            },
            follow_redirects=False,
        )
        assert resp_b.status_code == 302
        assert "/login" in resp_b.headers.get("Location", "")
        with session_b.session_transaction() as sess:
            assert "email_for_password_reset" not in sess
            assert "password_reset_token_key" not in sess

        # The password on record must still be session A's, never session
        # B's hijack attempt.
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM Users WHERE Email = ?", email)
        current_hash = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        if isinstance(current_hash, str):
            current_hash = current_hash.encode("utf-8")
        assert bcrypt.checkpw(b"FirstWriter1!", current_hash)
        assert not bcrypt.checkpw(b"SecondWriterHijack1!", current_hash)
    finally:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET password = ? WHERE Email = ?", (original_hash, email))
        conn.commit()
        cursor.close()
        conn.close()


def test_verify_2fa_rate_limit_eventually_429(client, reset_limiter, clear_2fa_lockout):
    """Two ceilings on TOTP brute force, both asserted strictly. Per-IP:
    @limiter.limit('30 per hour') -- the 31st attempt within the hour is 429.
    Per-account: dbo.LoginLockout under the "2fa:<userid>" key -- the 5th
    wrong code locks the account for 15 minutes, so attempts 6..30 bounce
    (302 back to /verify_2fa) instead of being checked at all. 401 on every
    attempt is exactly the pre-fix defect this test exists to catch."""
    with client.session_transaction() as sess:
        sess["pre_2fa_userid"] = "1001"
    statuses = []
    for _ in range(31):
        resp = client.post("/verify_2fa", data={"code": "000000"}, follow_redirects=False)
        statuses.append(resp.status_code)
    assert statuses[:5] == [401] * 5, statuses
    assert statuses[5:30] == [302] * 25, statuses
    assert statuses[30] == 429, statuses


def test_verify_2fa_applies_ui_pref_prepaint(client):
    """The 2FA page must carry the UI-prefs pre-paint (#243).

    The shield gradient, submit button, focus rings and page backdrop all read
    --nx-accent* from nexora-ui.css / auth.css, but the page never set
    data-accent, so they stayed indigo whatever the user had chosen. The server
    cannot help here -- the session holds pre_2fa_userid, not userid, so
    _load_user_ui_prefs() does not run -- which is exactly why the block falls
    through to its localStorage mirror instead.
    """
    with client.session_transaction() as sess:
        sess["pre_2fa_userid"] = "1001"

    resp = client.get("/verify_2fa")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "applyCustomAccent" in body, "accent derivation missing"
    assert "nexora-ui-prefs" in body, "localStorage mirror missing"
    assert "data-accent" in body, "accent attribute never applied"


def test_ui_pref_prepaint_is_shared_not_duplicated():
    """_header.html must include the partial rather than inline its own copy.

    Two copies of the accent derivation would drift silently -- a wrong tint
    still looks plausible, so nothing would fail to tell us.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    header = (root / "templates" / "_header.html").read_text(encoding="utf-8")
    twofa = (root / "templates" / "verify_2fa.html").read_text(encoding="utf-8")

    assert "_ui_prefs_prepaint.html" in header
    assert "_ui_prefs_prepaint.html" in twofa
    assert "applyCustomAccent" not in header, "header still holds its own copy"
    assert "applyCustomAccent" not in twofa, "2FA page inlined a copy"
