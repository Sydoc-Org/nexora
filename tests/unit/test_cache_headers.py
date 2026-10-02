"""Cache policy on responses (#354).

Two halves that must not drift into each other:

  - rendered HTML must never be cached. It is per-user, and a cached page also
    pins the `?v=<mtime>` asset URLs baked into it, which silently defeats the
    long max-age on /static and makes a deploy look like it did nothing. The
    reported symptom was a nexora pinned to a phone home screen still showing
    the version it was pinned at days later.
  - versioned static assets must keep their long max-age. That is what makes
    navigation fast, and it is safe precisely because the HTML naming them is
    fresh.
"""

import re


def test_html_is_never_cached(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert resp.mimetype == "text/html"
    assert resp.headers.get("Cache-Control") == "no-store"


def test_error_pages_are_never_cached(client):
    """404 renders a template too, and is just as user-specific."""
    resp = client.get("/no-such-page-exists")
    assert resp.status_code == 404
    if resp.mimetype == "text/html":
        assert resp.headers.get("Cache-Control") == "no-store"


def test_static_assets_keep_their_long_cache(client):
    """The other half of the policy -- don't let a later change break this."""
    resp = client.get("/static/css/_header.css")
    assert resp.status_code == 200
    cc = resp.headers.get("Cache-Control", "")
    assert "public" in cc
    m = re.search(r"max-age=(\d+)", cc)
    assert m, f"no max-age on a static asset: {cc!r}"
    assert int(m.group(1)) > 60 * 60 * 24, "static assets should cache for far longer than a day"
    assert "no-store" not in cc
