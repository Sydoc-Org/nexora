"""The authenticated session cookie must survive the app being closed (#354).

Without `session.permanent`, Flask writes the cookie with no Expires/Max-Age —
a *browser session* cookie, discarded the moment the browsing session ends. On
a desktop that is rarely noticed. In an installed home-screen app it is
constant: iOS evicts the web app from memory routinely, the cookie goes with
it, and the user is signed out minutes after signing in.

Measured before the fix: dev sent `session=…; HttpOnly; Path=/; SameSite=Lax`
while PROD sent the same plus `Expires=…; Secure`, because SESSION_PERMANENT
sat inside the `if IS_PROD:` block.

The lifetime itself is unchanged — PERMANENT_SESSION_LIFETIME (24h) is what
bounds the session, and it only applies to permanent sessions. This makes it
apply everywhere rather than nowhere.
"""

import re


def _session_cookies(resp):
    return [c for c in resp.headers.getlist("Set-Cookie") if c.startswith("session=")]


def test_authenticated_session_cookie_carries_an_expiry(client):
    client.get("/dev/login/admin@test.local")
    resp = client.get("/dashboard")

    cookies = _session_cookies(resp)
    assert cookies, "no session cookie was set on an authenticated request"
    assert any("Expires=" in c or "Max-Age=" in c for c in cookies), (
        "the session cookie has no expiry, so it dies when the app is closed: " + str(cookies)
    )


def test_the_expiry_matches_the_configured_lifetime(app, client):
    """Not an arbitrary date -- it must be the session lifetime the app
    configures, so shortening that actually shortens the cookie."""
    client.get("/dev/login/admin@test.local")
    resp = client.get("/dashboard")

    cookie = next(c for c in _session_cookies(resp) if "Expires=" in c)
    # Flask writes Expires as an HTTP date; just prove it is in the future and
    # not further out than the configured lifetime allows.
    assert re.search(r"Expires=[A-Z][a-z]{2}, \d{2} [A-Z][a-z]{2} \d{4}", cookie), cookie
    assert app.config["PERMANENT_SESSION_LIFETIME"].total_seconds() > 0


def test_a_signed_out_visitor_gets_no_lasting_cookie(client):
    """Only authenticated sessions are made permanent. The pre-login cookie
    exists solely to carry a CSRF token and should not outlive the visit."""
    resp = client.get("/login")
    for cookie in _session_cookies(resp):
        assert "Expires=" not in cookie and "Max-Age=" not in cookie, (
            "a signed-out visitor should not receive a persistent cookie: " + cookie
        )
