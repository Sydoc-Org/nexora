"""/install: how to put nexora on a phone, with a QR code of the sign-in page.
Also the phone start page hint the header gives nx_core.js (NX_PHONE_START)."""

import base64

import nx_lib.hooks as hooks


def test_install_page_shows_steps_and_a_qr_of_the_login_page(user_client):
    resp = user_client.get("/install")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for testid in ("install-qr", "install-iphone", "install-android"):
        assert f'data-testid="{testid}"' in html
    # the QR is an inline PNG (CSP: no third-party QR service) of the login URL
    b64 = html.split("data:image/png;base64,", 1)[1].split('"', 1)[0]
    assert base64.b64decode(b64).startswith(b"\x89PNG")
    assert "/login" in html


def test_install_page_needs_a_sign_in(client):
    resp = client.get("/install")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_header_sets_phone_start_only_for_post_reporters(user_client, monkeypatch):
    monkeypatch.setattr(
        hooks,
        "load_permissions_for_user",
        lambda uid: ["tenant.generali.reporting.view", "tenant.generali.reporting.add"],
    )
    html = user_client.get("/install").get_data(as_text=True)
    assert 'window.NX_PHONE_START = "/generali/reporting";' in html

    monkeypatch.setattr(
        hooks, "load_permissions_for_user", lambda uid: ["tenant.generali.reporting.view"]
    )
    html = user_client.get("/install").get_data(as_text=True)
    assert "window.NX_PHONE_START = null;" in html
