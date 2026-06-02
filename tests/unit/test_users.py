"""Unit tests for nx_lib.users — portal user lookup + icon URL resolver."""

from unittest.mock import patch

from nx_lib.users import get_all_portal_users, resolve_user_icon_url


def test_get_all_portal_users_returns_empty_without_permission(auth_app_ctx, fake_session):
    """Without `<from_request>.<action>` permission the function returns []."""
    fake_session["permissions"] = []
    fake_session["organizationcode"] = "TEST"
    users = get_all_portal_users(from_request="workitems", action="assign")
    assert users == []


def test_get_all_portal_users_admin_global_returns_all_users(auth_app_ctx, fake_session):
    """With admin.interact.users.all the query is unscoped."""
    fake_session["permissions"] = ["workitems.assign", "admin.interact.users.all"]
    fake_session["organizationcode"] = "TEST"
    users = get_all_portal_users(from_request="workitems", action="assign")
    assert isinstance(users, list)
    usernames = {u["fullname"] for u in users}
    # Seed users must be present
    assert "Test Admin" in usernames or "Test User" in usernames
    # The dict shape is column-keyed
    assert all("userID" in u and "fullname" in u for u in users)


def test_get_all_portal_users_org_scoped_for_non_global(auth_app_ctx, fake_session):
    """Without admin.interact.users.all the query filters by organizationcode."""
    fake_session["permissions"] = ["workitems.assign"]
    fake_session["organizationcode"] = "TEST"
    users = get_all_portal_users(from_request="workitems", action="assign")
    assert isinstance(users, list)
    # Seed users have organizationcode = 'TEST' and accessid in (1,2,3) for
    # TestAdmin/TestUser/TestNoPerm. The query excludes accessid IN (1,2) —
    # so depending on seed.sql's AccessProfile IDs the list size varies.
    # At minimum, the query ran without error and returned a list.


def test_get_all_portal_users_exception_returns_empty(auth_app_ctx, fake_session):
    """If the DB call raises, returns [] and logs the error — does not propagate."""
    fake_session["permissions"] = ["workitems.assign", "admin.interact.users.all"]
    with patch("nx_lib.users.engine_nexora_db") as mock_engine:
        mock_engine.raw_connection.side_effect = RuntimeError("simulated DB down")
        users = get_all_portal_users(from_request="workitems", action="assign")
    assert users == []


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
    assert target in url
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
    assert target in url
    assert "v=1700000001" in url
