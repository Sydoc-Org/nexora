"""web.config is the whole PROD hosting contract (IIS HttpPlatformHandler ->
waitress). Guard the bits that break the site or the rate limiter if lost.
See docs/howto/iis.md."""

import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_web_config_hands_iis_to_waitress():
    ws = ET.parse(ROOT / "web.config").getroot().find("system.webServer")
    assert [h.get("modules") for h in ws.find("handlers")] == ["httpPlatformHandler"]
    # A rewrite to nx_main.py would reach waitress as a 404.
    assert ws.find("rewrite") is None
    hp = ws.find("httpPlatform")
    args = hp.get("arguments")
    assert "%HTTP_PLATFORM_PORT%" in args and args.endswith(" nx_main:app")
    # waitress >= 2 strips X-Forwarded-* from untrusted peers -> limiter/CSV log blind.
    assert "--trusted-proxy=127.0.0.1" in args and "x-forwarded-for" in args
    assert "--url-scheme=https" in args  # TLS ends at ngrok; avoids Talisman redirect loop
    env = {e.get("name"): e.get("value") for e in hp.find("environmentVariables")}
    assert env["ENVIRONMENT"] == "PROD" and env["PYTHONPATH"] == r"D:\sydoc\nexora"
    assert "wfastcgi" not in (ROOT / "web.config").read_text(encoding="utf-8").lower()


def test_waitress_is_a_runtime_dependency():
    assert "waitress==" in (ROOT / "requirements.txt").read_text(encoding="utf-8")


def test_limiter_keys_on_forwarded_client_not_proxy_peer(app):
    from nx_lib.extensions import client_ip

    # waitress (--trusted-proxy=127.0.0.1, count 1) trims X-Forwarded-For to
    # the single hop IIS appended before Flask sees it; a client-typed prefix
    # is exactly what must NOT win.
    with app.test_request_context(
        headers={"X-Forwarded-For": "203.0.113.9"},
        environ_base={"REMOTE_ADDR": "127.0.0.1"},
    ):
        assert client_ip() == "203.0.113.9"
    with app.test_request_context(
        headers={"X-Forwarded-For": "6.6.6.6, 203.0.113.9"},
        environ_base={"REMOTE_ADDR": "127.0.0.1"},
    ):
        assert client_ip() == "203.0.113.9"
    with app.test_request_context(environ_base={"REMOTE_ADDR": "10.1.2.3"}):
        assert client_ip() == "10.1.2.3"
