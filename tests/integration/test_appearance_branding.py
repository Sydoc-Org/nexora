"""The Appearance page and the header hand a branded organization's accent
through: the swatch picker gives way to a note, and the pre-paint resolver
receives the brand hex (templates/_header.html resolves brand before prefs)."""

import nx_lib.hooks as hooks

BRAND = {"name": "Privera", "accent_hex": "#0d9488", "logo_file": None}


def test_appearance_shows_brand_note_instead_of_swatches_when_branded(user_client, monkeypatch):
    monkeypatch.setattr(hooks, "brand_for_org", lambda code: BRAND)
    resp = user_client.get("/appearance")
    assert resp.status_code == 200
    assert b'data-testid="appearance-accent-branded"' in resp.data
    assert b'data-testid="appearance-accent-amber"' not in resp.data
    assert b'"accent_hex": "#0d9488"' in resp.data  # what the header script resolves first


def test_appearance_keeps_swatches_without_branding(user_client, monkeypatch):
    monkeypatch.setattr(hooks, "brand_for_org", lambda code: None)
    resp = user_client.get("/appearance")
    assert resp.status_code == 200
    assert b'data-testid="appearance-accent-amber"' in resp.data
    assert b'data-testid="appearance-accent-branded"' not in resp.data
