"""CSRF failures render a page a person can act on (#354 follow-up).

With no handler registered, Flask-WTF's CSRFError fell through to Werkzeug's
raw 400: a white page reading "The CSRF session token is missing" and nothing
to click. That is what a real user hit on dev after submitting a login form
whose session had expired -- the token is tied to the session, and the session
outlives neither the 24-hour lifetime nor a page served from a cache.

The point of these tests is that the refusal is unchanged and only the
presentation improved: still 400, still rejected, but explained.
"""

import pytest

from nx_lib import create_app


@pytest.fixture(scope="module")
def csrf_app():
    """A real app with CSRF enforcement ON.

    The shared `app` fixture sets WTF_CSRF_ENABLED=False so the rest of the
    suite can post freely, which would make these tests vacuous.
    """
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)
    return app


@pytest.fixture()
def csrf_client(csrf_app):
    return csrf_app.test_client()


def test_missing_csrf_token_is_still_refused(csrf_client):
    """The security behaviour must not have been softened into a pass."""
    resp = csrf_client.post("/login", data={"username": "x", "password": "y"})
    assert resp.status_code == 400


def test_the_refusal_explains_itself(csrf_client):
    """Instead of "The CSRF session token is missing"."""
    resp = csrf_client.post("/login", data={"username": "x", "password": "y"})
    html = resp.get_data(as_text=True)
    assert "expired" in html.lower(), "the page should say the page expired"
    # The raw Werkzeug body is what we replaced; make sure it is gone.
    assert "CSRF session token is missing" not in html


def test_it_offers_a_way_back_to_the_form(csrf_client):
    """A retry link to the path that was posted to, so a GET issues a fresh
    token -- not the landing page, which leaves the user to find the form
    again themselves."""
    resp = csrf_client.post("/login", data={"username": "x", "password": "y"})
    html = resp.get_data(as_text=True)
    assert 'href="/login"' in html, "no retry link back to the form"


def test_external_api_gets_json_not_a_web_page(csrf_client):
    """The API surface must never be handed an HTML error page."""
    resp = csrf_client.post("/api/v1/workitems", data={})
    # Either the API's own auth rejects it first, or CSRF does -- but if this
    # path produces a CSRF error it must be JSON.
    if resp.status_code == 400:
        assert resp.mimetype == "application/json", resp.get_data(as_text=True)[:200]
