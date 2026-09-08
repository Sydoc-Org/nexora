"""Shared pytest fixtures for the nexora test suite.

This file MUST set ENVIRONMENT=TEST before any nx_lib import, otherwise
nx_lib.config would load whatever environment is currently active.
"""

import os
import sys

# CRITICAL: set BEFORE importing nx_lib. setdefault avoids overwriting if a
# caller deliberately set a different environment (e.g. for debug).
os.environ.setdefault("ENVIRONMENT", "TEST")
# The per-process user cache (nx_lib/user_cache.py) would carry one test's
# patched permissions/prefs into the next; 0 disables it (the e2e subprocess
# inherits this environment too). tests/unit/test_user_cache.py covers it.
os.environ.setdefault("NEXORA_USER_CACHE_TTL", "0")

import pyotp
import pytest
from sqlalchemy import text

from nx_lib import create_app
from nx_lib.db import engine_nexora_db

# Pinned TOTP secrets — must match sql/test/seed.sql exactly.
TOTP_SECRETS = {
    "admin@test.local": "JBSWY3DPEHPK3PXP",
    "user@test.local": "KRSXG5CTMVRXEZLU",
    "noperm@test.local": "MFRGGZDFMZTWQ2LK",
    "noai@test.local": "GEZDGNBVGY3TQOJQ",
}

TEST_PASSWORD = "Test1234!"


@pytest.fixture(scope="session", autouse=True)
def _shared_test_db_lock(request):
    """Serialise this whole pytest session against other runs (#235).

    One NEXORA_TEST is shared by CI and every local run, and both sides reset
    it. Holding the lock for the session -- not just the reset -- is the point:
    the collisions that cost a day were a peer's reset landing in the middle of
    a suite, not two resets racing.

    Fails OPEN when the database is unreachable. A run that cannot connect
    cannot corrupt anyone, and pure-unit runs should not start needing a
    server. Anything that genuinely needs the DB fails later on its own terms.
    """
    try:
        from scripts.db_lock import hold
        from scripts.test_db_reset import connect_test_db
    except ImportError as e:  # pragma: no cover - repo layout changed
        print(f"[db-lock] helper unavailable, not serialising: {e}", file=sys.stderr)
        yield
        return

    try:
        conn = connect_test_db()
    except Exception as e:
        print(f"[db-lock] no NEXORA_TEST connection, not serialising: {e}", file=sys.stderr)
        yield
        return

    # pytest captures stderr, so hold()'s "waiting for a peer" line would never
    # reach the terminal and a 20-minute wait would look like a freeze.
    capman = request.config.pluginmanager.getplugin("capturemanager")

    def notify(msg):
        if capman is None:
            print(msg, file=sys.stderr, flush=True)
            return
        with capman.global_and_fixture_disabled():
            print(msg, file=sys.stderr, flush=True)

    try:
        with hold(conn, label="pytest", notify=notify):
            yield
    finally:
        conn.close()


@pytest.fixture(scope="session")
def app():
    """Flask app configured for testing. One per test session."""
    flask_app = create_app()
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
    )
    yield flask_app


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset Flask-Limiter's in-memory storage before EVERY test.

    Without this, sibling tests that POST to /login (10/min) or any other
    rate-limited route cumulatively exhaust the quota — eventually every
    user_client / admin_client login fixture starts seeing 429s. Tests that
    intentionally exercise the rate limit (test_auth_routes.test_*_rate_limit)
    still work because the reset runs *before* the test body.

    E2E tests run against a subprocess so the in-process limiter isn't bound
    to an app — the reset is a no-op there.
    """
    try:
        from nx_lib.extensions import limiter

        limiter.reset()
    except (AssertionError, RuntimeError):
        # Limiter not bound to an app context (e.g. e2e subprocess tests).
        pass
    yield


@pytest.fixture()
def client(app):
    """Flask test client. Fresh per test."""
    return app.test_client()


@pytest.fixture()
def clear_2fa_lockout():
    """Wipe the seed user's 2FA lockout row (dbo.LoginLockout "2fa:1001")
    before AND after -- views/auth commits on its own connection, so a
    test that burns wrong codes would otherwise lock later tests out."""

    def _wipe():
        with engine_nexora_db.begin() as conn:
            conn.execute(text("DELETE FROM dbo.LoginLockout WHERE userid = '2fa:1001'"))

    _wipe()
    yield
    _wipe()


@pytest.fixture()
def db_conn():
    """SQLAlchemy connection with transaction-scoped isolation.

    Anything written through this connection is rolled back at end-of-test,
    so tests can mutate freely without polluting other tests.
    """
    conn = engine_nexora_db.connect()
    trans = conn.begin()
    try:
        yield conn
    finally:
        trans.rollback()
        conn.close()


@pytest.fixture()
def totp_for():
    """Compute the current TOTP code for a seeded test user."""

    def _totp(username):
        secret = TOTP_SECRETS[username]
        return pyotp.TOTP(secret).now()

    return _totp


@pytest.fixture()
def login(client, totp_for):
    """Log in as a seeded test user. Returns the authenticated test client.

    Flow (driven by nx_lib/views/auth.py):
      1. POST /login with username + password.
         - On success and twoFA=1 (which all seed users have), redirects to /verify_2fa.
      2. POST /verify_2fa with the current TOTP code.
         - On success, session.clear() is called and full session state is set.
    """

    def _login(username="user@test.local", password=TEST_PASSWORD):
        resp = client.post(
            "/login",
            data={"username": username, "password": password},
            follow_redirects=False,
        )
        # Bad creds re-render index.html with 401; good creds redirect (302).
        if resp.status_code != 302:
            raise AssertionError(
                f"/login failed for {username}: status={resp.status_code} "
                f"body={resp.data[:200]!r}"
            )

        code = totp_for(username)
        resp = client.post(
            "/verify_2fa",
            data={"code": code},
            follow_redirects=False,
        )
        if resp.status_code != 302:
            raise AssertionError(
                f"/verify_2fa failed for {username}: status={resp.status_code} "
                f"body={resp.data[:200]!r}"
            )

        return client

    return _login


@pytest.fixture()
def admin_client(login):
    """Authenticated admin@test.local test client (has admin.view + dashboard.view + admin.users.manage)."""
    return login(username="admin@test.local")


@pytest.fixture()
def user_client(login):
    """Authenticated user@test.local test client (has dashboard.view only)."""
    return login(username="user@test.local")


@pytest.fixture()
def noperm_client(login):
    """Authenticated noperm@test.local test client (no permissions)."""
    return login(username="noperm@test.local")


@pytest.fixture()
def auth_app_ctx(app):
    """Push a Flask app context for tests that need current_app / url_for outside a request.

    Use when calling functions like security.startpage_redirect_to which read current_app.
    """
    with app.app_context():
        yield app


@pytest.fixture()
def fake_session(monkeypatch):
    """Inject a fake session dict into nx_lib.security.session.

    Returns the dict so the test can mutate it mid-test:

        def test_x(fake_session):
            fake_session["permissions"] = ["admin.view"]
            assert has_permission("admin.view")
    """
    session_dict = {}
    monkeypatch.setattr("nx_lib.security.session", session_dict)
    return session_dict


TEST_ORG_CODE = "TEST"  # seeded by sql/test/seed.sql


@pytest.fixture()
def seeded_org():
    """The organizationcode used by every seed user. Use in tests that need
    to filter scope-based queries."""
    return TEST_ORG_CODE
