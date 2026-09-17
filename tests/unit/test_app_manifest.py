"""The web app manifest that makes nexora installable (#354).

The two fields worth testing are `scope` and `start_url`. PROD and STAGING
serve under `/nexora` and INT does not, so a manifest with a hard-coded path
would send one environment's installed app to a 404 — and a wrong `scope` is
the worse half, because navigating outside it drops the user out of the
installed window and back into a browser tab, which looks like the app
crashing.
"""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

MANIFEST_URL = "/manifest.webmanifest"


def _manifest(client, **kwargs):
    resp = client.get(MANIFEST_URL, **kwargs)
    assert resp.status_code == 200
    return resp, json.loads(resp.get_data(as_text=True))


def test_manifest_is_served_as_a_manifest(client):
    resp, data = _manifest(client)
    assert resp.headers["Content-Type"].startswith("application/manifest+json")
    assert data["display"] == "standalone"
    assert data["icons"], "a manifest without icons is not installable"


def test_manifest_needs_no_login(client):
    """It is linked from the login page -- that is where people install from,
    so it must resolve while signed out rather than redirecting to /login."""
    resp = client.get(MANIFEST_URL)
    assert resp.status_code == 200


def test_scope_and_start_url_follow_the_url_prefix(client):
    """The PROD/STAGING case. PrefixMiddleware mounts the app under /nexora,
    which reaches Flask as SCRIPT_NAME; url_for() then has to carry it."""
    _, plain = _manifest(client)
    assert plain["start_url"] == "/"
    assert plain["scope"] == "/"

    _, prefixed = _manifest(client, environ_overrides={"SCRIPT_NAME": "/nexora"})
    assert prefixed["start_url"] == "/nexora/", (
        "an installed PROD app would open on a 404: " + prefixed["start_url"]
    )
    assert (
        prefixed["scope"] == "/nexora/"
    ), "a scope outside the prefix drops the user back into a browser tab"
    for icon in prefixed["icons"]:
        assert icon["src"].startswith("/nexora/"), f"icon escapes the prefix: {icon['src']}"


def test_name_says_which_environment_it_is(client):
    """All three hosts are installable and become identical icons on a home
    screen. Only PROD may claim the bare name, or someone installs dev, reads
    INT data and believes it is production."""
    _, data = _manifest(client)
    # The suite runs as ENVIRONMENT=TEST.
    assert data["name"] != "nexora"
    assert "test" in data["name"].lower()


def test_declared_icons_exist_on_disk(client):
    _, data = _manifest(client)
    for icon in data["icons"]:
        rel = icon["src"].split("?")[0].lstrip("/")  # src carries a ?v= cache-buster
        assert (REPO / rel).is_file(), f"manifest points at a missing file: {icon['src']}"


def test_maskable_icon_is_declared(client):
    """Android crops icons to the launcher's shape; without a maskable variant
    the mark gets its edges shaved off."""
    _, data = _manifest(client)
    purposes = {i.get("purpose") for i in data["icons"]}
    assert "maskable" in purposes
    assert "any" in purposes


def test_login_page_offers_the_install(client):
    """No manifest link on the page means no Install option in the browser."""
    html = client.get("/login").get_data(as_text=True)
    assert 'rel="manifest"' in html
    # iOS ignores the manifest icons and reads this instead; without it the
    # home screen shows a letter or a screenshot.
    assert 'rel="apple-touch-icon"' in html
