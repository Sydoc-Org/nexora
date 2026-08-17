"""Integration tests for the What's New page + badge (#169).

Routes covered:
- GET /whats_new (login gate, permission-filtered entries, seen-marker stamp)
- the header badge (whats_new_unseen context processor) via /profile

admin@test.local holds every seeded permission, so "admin sees every curated
entry" doubles as validation that each entry's perm code actually exists in
dbo.Permission — a typo'd code would hide that entry from admins too and fail
here.
"""

import pytest
from sqlalchemy import text

from nx_lib.db import engine_nexora_db
from nx_lib.version import __version__
from nx_lib.whats_new import RELEASES

ALL_TITLES = [str(e["title"]) for rel in RELEASES for e in rel["entries"]]
GATED_TITLES = [str(e["title"]) for rel in RELEASES for e in rel["entries"] if e["perm"]]
UNGATED_TITLES = [str(e["title"]) for rel in RELEASES for e in rel["entries"] if not e["perm"]]

NEWS_DOT = b'data-testid="header-news-dot"'


def _set_seen(username, value):
    with engine_nexora_db.connect() as conn:
        conn.execute(
            text("UPDATE Users SET whats_new_seen_version = :v WHERE username = :u"),
            {"v": value, "u": username},
        )
        conn.commit()


def _get_seen(username):
    with engine_nexora_db.connect() as conn:
        return conn.execute(
            text("SELECT whats_new_seen_version FROM Users WHERE username = :u"),
            {"u": username},
        ).scalar()


def test_whats_new_anonymous_redirects_to_login(client):
    resp = client.get("/whats_new", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_admin_sees_every_entry(admin_client):
    """Every curated entry renders for the all-permission admin — catches both
    perm-filter over-blocking and entry perm codes that don't exist in the DB."""
    html = admin_client.get("/whats_new").data.decode()
    missing = [t for t in ALL_TITLES if t not in html]
    assert not missing, f"admin should see all entries, missing: {missing}"


def test_noperm_sees_only_ungated_entries(noperm_client):
    html = noperm_client.get("/whats_new").data.decode()
    for title in UNGATED_TITLES:
        assert title in html
    leaked = [t for t in GATED_TITLES if t in html]
    assert not leaked, f"gated entries leaked to a no-permission user: {leaked}"


def test_noperm_drops_fully_gated_releases(noperm_client):
    """2.5.64 has only gated entries — the whole release section must vanish."""
    html = noperm_client.get("/whats_new").data.decode()
    assert "v3.1" in html  # has the ungated Appearance entry
    assert "v2.5.64" not in html


def test_dashboard_only_user_matches_their_permissions(user_client):
    """user@test.local holds dashboard.view only — no gated entry qualifies."""
    html = user_client.get("/whats_new").data.decode()
    leaked = [t for t in GATED_TITLES if t in html]
    assert not leaked, f"gated entries leaked to dashboard-only user: {leaked}"
    for title in UNGATED_TITLES:
        assert title in html


def test_badge_lights_then_clears(admin_client):
    _set_seen("admin@test.local", None)
    assert NEWS_DOT in admin_client.get("/profile").data

    assert admin_client.get("/whats_new").status_code == 200
    assert _get_seen("admin@test.local") == __version__
    assert NEWS_DOT not in admin_client.get("/profile").data


def test_badge_off_when_up_to_date(admin_client):
    _set_seen("admin@test.local", __version__)
    assert NEWS_DOT not in admin_client.get("/profile").data


def test_badge_on_for_older_seen_version(admin_client):
    _set_seen("admin@test.local", "2.5.64")
    assert NEWS_DOT in admin_client.get("/profile").data
    _set_seen("admin@test.local", __version__)


def test_badge_lights_for_noperm_user_via_ungated_entry(noperm_client):
    """The ungated entry keeps the badge meaningful even with zero permissions."""
    _set_seen("noperm@test.local", None)
    assert NEWS_DOT in noperm_client.get("/profile").data
    noperm_client.get("/whats_new")
    assert NEWS_DOT not in noperm_client.get("/profile").data


@pytest.mark.parametrize(
    "endpoint", sorted({e["endpoint"] for r in RELEASES for e in r["entries"] if e["endpoint"]})
)
def test_entry_endpoints_resolve(app, endpoint):
    """A typo'd endpoint name would 500 the page via url_for — fail it here."""
    from flask import url_for

    with app.test_request_context():
        assert url_for(endpoint)
