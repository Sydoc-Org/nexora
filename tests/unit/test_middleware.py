"""Unit tests for nx_lib.middleware — PrefixMiddleware WSGI prefix stripper."""

from io import BytesIO

from nx_lib.middleware import PrefixMiddleware


def _echo_path_app(environ, start_response):
    """Dummy WSGI app that echoes PATH_INFO + SCRIPT_NAME for inspection."""
    body = f"PATH_INFO={environ['PATH_INFO']};SCRIPT_NAME={environ.get('SCRIPT_NAME', '')}".encode()
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [body]


def _run(middleware, path):
    """Invoke middleware with a minimal WSGI environ; return (status, body_bytes, headers)."""
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    environ = {
        "PATH_INFO": path,
        "SCRIPT_NAME": "",
        "wsgi.input": BytesIO(),
    }
    body = b"".join(middleware(environ, start_response))
    return captured["status"], body, captured["headers"]


def test_prefix_middleware_strips_matching_prefix():
    wrapped = PrefixMiddleware(_echo_path_app, prefix="/nexora")
    status, body, _ = _run(wrapped, "/nexora/login")
    assert status == "200 OK"
    assert b"PATH_INFO=/login" in body
    assert b"SCRIPT_NAME=/nexora" in body


def test_prefix_middleware_404_for_non_matching_path():
    wrapped = PrefixMiddleware(_echo_path_app, prefix="/nexora")
    status, body, headers = _run(wrapped, "/other/login")
    assert status.startswith("404")
    assert b"does not belong" in body
    # Headers include Content-Type
    content_types = [v for k, v in headers if k.lower() == "content-type"]
    assert content_types == ["text/plain"]


def test_prefix_middleware_strips_only_first_occurrence():
    """If the URL itself contains the prefix again (e.g. /nexora/nexora/foo),
    only the leading prefix is stripped."""
    wrapped = PrefixMiddleware(_echo_path_app, prefix="/nexora")
    status, body, _ = _run(wrapped, "/nexora/nexora/foo")
    assert status == "200 OK"
    assert b"PATH_INFO=/nexora/foo" in body


def test_prefix_middleware_empty_prefix_passes_through():
    """An empty prefix is the default ('') — every path starts with '' so the
    middleware always strips an empty string (no-op) and forwards."""
    wrapped = PrefixMiddleware(_echo_path_app, prefix="")
    status, body, _ = _run(wrapped, "/anything")
    assert status == "200 OK"
    assert b"PATH_INFO=/anything" in body
    assert b"SCRIPT_NAME=" in body  # set to "" (the prefix)


def test_prefix_middleware_sets_script_name():
    captured = {}

    def capturing_app(environ, start_response):
        captured["script_name"] = environ.get("SCRIPT_NAME")
        captured["path_info"] = environ.get("PATH_INFO")
        start_response("200 OK", [])
        return [b""]

    wrapped = PrefixMiddleware(capturing_app, prefix="/nexora")
    _run(wrapped, "/nexora/foo")
    assert captured["script_name"] == "/nexora"
    assert captured["path_info"] == "/foo"


def test_prefix_middleware_stores_app_and_prefix_attrs():
    """Constructor stores app + prefix as instance attrs (used elsewhere)."""
    dummy_app = object()
    mw = PrefixMiddleware(dummy_app, prefix="/x")
    assert mw.app is dummy_app
    assert mw.prefix == "/x"
