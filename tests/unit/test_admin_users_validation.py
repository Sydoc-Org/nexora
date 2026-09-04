"""Unit tests for admin_add_user/admin_edit_user input validation.

Covers a strict_optional-driven fix: an unknown accessprofile/organization name
used to reach ``cursor.fetchone()[0]`` on a None row (TypeError), caught only
by the outer broad ``except Exception`` and surfaced as a generic 500. These
now fail fast with a clear 400 instead.
"""

from unittest.mock import MagicMock, patch

from nx_lib.views.admin.users import admin_add_user, admin_edit_user


def _mock_cursor_returning(*rows):
    """A cursor whose fetchone() yields `rows` in order, then None forever."""
    cur = MagicMock()
    cur.fetchone.side_effect = [*rows, None]
    return cur


def test_admin_add_user_rejects_unknown_accessprofile(app):
    with app.test_request_context(
        "/admin/add_user",
        method="POST",
        json={
            "username": "newuser",
            "password": "Sup3rSecret!",
            "fullname": "New User",
            "email": "newuser@test.local",
            "organization": "Sydoc",
            "accessprofile": "does-not-exist",
        },
    ):
        from flask import session

        session["username"] = "admin@test.local"
        session["permissions"] = ["admin.create.user"]

        fake_cursor = _mock_cursor_returning()  # first fetchone() -> None
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cursor

        with patch(
            "nx_lib.views.admin.users.engine_nexora_db.raw_connection",
            return_value=fake_conn,
        ):
            resp = admin_add_user()

    body = resp[0].get_json() if isinstance(resp, tuple) else resp.get_json()
    status = resp[1] if isinstance(resp, tuple) else resp.status_code
    assert status == 400
    assert body["success"] is False
    fake_cursor.execute.assert_called_once()  # never reached the organization lookup


def test_admin_add_user_rejects_unknown_organization(app):
    with app.test_request_context(
        "/admin/add_user",
        method="POST",
        json={
            "username": "newuser",
            "password": "Sup3rSecret!",
            "fullname": "New User",
            "email": "newuser@test.local",
            "organization": "does-not-exist",
            "accessprofile": "viewer",
        },
    ):
        from flask import session

        session["username"] = "admin@test.local"
        session["permissions"] = ["admin.create.user"]

        fake_cursor = _mock_cursor_returning((1,))  # accessprofile found, org not
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cursor

        with (
            patch(
                "nx_lib.views.admin.users.engine_nexora_db.raw_connection",
                return_value=fake_conn,
            ),
            # accessid 1 (resolved above) must be assignable for the flow to
            # reach the organization lookup this test is actually exercising.
            patch("nx_lib.views.admin.users.assignable_profile_ids", return_value={1}),
        ):
            resp = admin_add_user()

    body = resp[0].get_json() if isinstance(resp, tuple) else resp.get_json()
    status = resp[1] if isinstance(resp, tuple) else resp.status_code
    assert status == 400
    assert body["success"] is False
    assert fake_cursor.execute.call_count == 2  # got as far as the org lookup


def test_admin_edit_user_rejects_unknown_accessprofile(app):
    with app.test_request_context(
        "/admin/edit_user/1",
        method="POST",
        json={
            "username": "existing",
            "fullname": "Existing User",
            "email": "existing@test.local",
            "organization": "Sydoc",
            "accessprofile": "does-not-exist",
        },
    ):
        from flask import session

        session["username"] = "admin@test.local"
        session["permissions"] = ["admin.edit.user"]

        # First fetchone(): current accessprofile lookup by user id -> some row.
        # Second fetchone(): the new accessprofile lookup -> None (unknown).
        fake_cursor = _mock_cursor_returning(("some-current-profile",))
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cursor

        with patch(
            "nx_lib.views.admin.users.engine_nexora_db.raw_connection",
            return_value=fake_conn,
        ):
            resp = admin_edit_user(1)

    body = resp[0].get_json() if isinstance(resp, tuple) else resp.get_json()
    status = resp[1] if isinstance(resp, tuple) else resp.status_code
    assert status == 400
    assert body["success"] is False
