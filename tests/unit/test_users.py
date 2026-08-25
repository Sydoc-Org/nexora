"""Unit tests for nx_lib.users — icon URL resolver."""

from nx_lib.users import resolve_user_icon_url


def test_resolve_user_icon_url_none_returns_default(app):
    """A None user_id falls through to the default icon."""
    with app.test_request_context("/"):
        url = resolve_user_icon_url(None)
    assert url.endswith("default-icon.png")


def test_resolve_user_icon_url_zero_returns_default(app):
    """A falsy user_id (0) returns the default icon."""
    with app.test_request_context("/"):
        url = resolve_user_icon_url(0)
    assert url.endswith("default-icon.png")


def test_resolve_user_icon_url_unknown_returns_default(app):
    """A user_id with no icon file on disk returns the default icon."""
    with app.test_request_context("/"):
        url = resolve_user_icon_url(99999999)
    assert url.endswith("default-icon.png")


def test_resolve_user_icon_url_lowercase_filename_found(app, monkeypatch):
    """When `<id>-icon.png` exists, the returned URL points at it with cache-bust."""
    target = "99887766-icon.png"
    real_exists = __import__("os").path.exists

    def fake_exists(path):
        return path.endswith(target) or real_exists(path)

    monkeypatch.setattr("nx_lib.users.os.path.exists", fake_exists)
    monkeypatch.setattr("nx_lib.users.os.path.getmtime", lambda p: 1700000000)

    with app.test_request_context("/"):
        url = resolve_user_icon_url(99887766)
    assert "/avatar/99887766" in url
    assert "v=1700000000" in url


def test_resolve_user_icon_url_uppercase_filename_found(app, monkeypatch):
    """When only `<id>-Icon.png` (uppercase I) exists, that one is returned."""
    target = "55667788-Icon.png"
    real_exists = __import__("os").path.exists

    def fake_exists(path):
        # Pretend the lowercase variant does NOT exist, only the uppercase
        if path.endswith("55667788-icon.png"):
            return False
        return path.endswith(target) or real_exists(path)

    monkeypatch.setattr("nx_lib.users.os.path.exists", fake_exists)
    monkeypatch.setattr("nx_lib.users.os.path.getmtime", lambda p: 1700000001)

    with app.test_request_context("/"):
        url = resolve_user_icon_url(55667788)
    assert "/avatar/55667788" in url
    assert "v=1700000001" in url
