"""Shared pytest fixtures for the nexora test suite.

This file MUST set ENVIRONMENT=TEST before any nx_lib import, otherwise
nx_lib.config would load whatever environment is currently active.
"""

import os

# CRITICAL: set BEFORE importing nx_lib. setdefault avoids overwriting if a
# caller deliberately set a different environment (e.g. for debug).
os.environ.setdefault("ENVIRONMENT", "TEST")

import pyotp
import pytest

from nx_lib import create_app
from nx_lib.db import engine_nexora_db

# Pinned TOTP secrets — must match sql/test/seed.sql exactly.
TOTP_SECRETS = {
    "admin@test.local": "JBSWY3DPEHPK3PXP",
    "user@test.local": "KRSXG5CTMVRXEZLU",
    "noperm@test.local": "MFRGGZDFMZTWQ2LK",
}

TEST_PASSWORD = "Test1234!"


@pytest.fixture(scope="session")
def app():
    """Flask app configured for testing. One per test session."""
    flask_app = create_app()
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
    )
    yield flask_app


@pytest.fixture()
def client(app):
    """Flask test client. Fresh per test."""
    return app.test_client()


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
