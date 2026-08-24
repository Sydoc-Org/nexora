"""Integration tests for nx_lib.views.profile — profile page, profile update,
password change, language switch.

Routes covered:
- GET  /profile         (profile page)
- POST /update_profile  (profile update — invalid email, dup email, happy path)
- POST /change_password (mismatch, length, current-pw wrong, current-pw OK)
- GET  /language/<lang> (bad lang, valid lang)
- GET  /avatar/<id>     (uploaded-avatar serving; upload saves outside static/)

All write paths roll back via the db_conn-scoped transaction fixture where
possible. /update_profile and /change_password run via the test client which
holds its own connection, so changes persist within the test session — each
test that mutates restores the original password/email at the end.
"""

import io
from types import SimpleNamespace

import bcrypt
from PIL import Image


def test_profile_anonymous_redirects_to_login(client):
    resp = client.get("/profile", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_profile_authed_renders(user_client):
    resp = user_client.get("/profile")
    assert resp.status_code == 200


def test_update_profile_anonymous_redirects_to_login(client):
    resp = client.post(
        "/update_profile",
        data={"fullName": "X", "email": "x@y.local"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_update_profile_invalid_email_flashes_and_redirects(user_client):
    resp = user_client.post(
        "/update_profile",
        data={"fullName": "User", "email": "not-an-email"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/profile" in resp.headers.get("Location", "")


def test_update_profile_happy_path_updates_session(user_client, db_conn):
    """Valid email update succeeds; session reflects new fullname/email.

    Restores the seeded fullname afterward via db_conn (update_profile
    commits on its own connection, so db_conn's rollback can't undo it) --
    same pattern as test_change_password_happy_path_then_restore. Without
    this, the write to "Updated Test User" persists in the TEST database
    and silently drifts any other test/suite (e.g. the reporting-share e2e
    test) that depends on this account's seeded "Test User" fullname.
    """
    from sqlalchemy import text

    new_full = "Updated Test User"
    new_email = "user@test.local"  # keep same email to avoid uniqueness collision
    resp = user_client.post(
        "/update_profile",
        data={"fullName": new_full, "email": new_email},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with user_client.session_transaction() as sess:
        assert sess.get("fullname") == new_full

    db_conn.execute(
        text("UPDATE Users SET fullname = 'Test User' WHERE username = 'user@test.local'"),
    )
    db_conn.commit()


def test_update_profile_duplicate_email_redirects_with_flash(user_client):
    """Try to take admin's email — must be rejected."""
    resp = user_client.post(
        "/update_profile",
        data={"fullName": "User", "email": "admin@test.local"},
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_update_profile_get_redirects_to_profile(user_client):
    """GET must not fall through to a bare 500 — it should redirect."""
    resp = user_client.get("/update_profile", follow_redirects=False)
    assert resp.status_code == 302
    assert "/profile" in resp.headers.get("Location", "")


def test_change_password_anonymous_redirects_to_login(client):
    resp = client.post(
        "/change_password",
        data={"currentPassword": "x", "newPassword": "x", "confirmPassword": "x"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_change_password_get_redirects_to_profile(user_client):
    """GET must not fall through to a bare 500 — it should redirect."""
    resp = user_client.get("/change_password", follow_redirects=False)
    assert resp.status_code == 302
    assert "/profile" in resp.headers.get("Location", "")


def test_change_password_mismatch_flashes(user_client):
    resp = user_client.post(
        "/change_password",
        data={
            "currentPassword": "Test1234!",
            "newPassword": "NewPass1234!",
            "confirmPassword": "Different1!",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/profile" in resp.headers.get("Location", "")


def test_change_password_too_short_flashes(user_client):
    resp = user_client.post(
        "/change_password",
        data={
            "currentPassword": "Test1234!",
            "newPassword": "short",
            "confirmPassword": "short",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_change_password_wrong_current_flashes(user_client):
    resp = user_client.post(
        "/change_password",
        data={
            "currentPassword": "WrongPassword1!",
            "newPassword": "NewPass1234!",
            "confirmPassword": "NewPass1234!",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_change_password_happy_path_then_restore(user_client, db_conn):
    """Valid current-pw → password updates. Restore the original hash via
    db_conn so the seed remains usable for sibling tests in the same session."""
    from sqlalchemy import text

    new_pw = "BrandNewPw99!"
    resp = user_client.post(
        "/change_password",
        data={
            "currentPassword": "Test1234!",
            "newPassword": new_pw,
            "confirmPassword": new_pw,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302

    # Restore the seeded hash so subsequent tests in this session can log in.
    seeded_hash = "$2b$12$D7op.8v3zbknmjjmS//FTuGV0THtWdlF8OU6goyKsNlA5sJ0HC0a6"
    db_conn.execute(
        text("UPDATE Users SET password = :h WHERE username = 'user@test.local'"),
        {"h": seeded_hash},
    )
    # The fixture rolls back the transaction at teardown but the change_password
    # commit happened on a different connection — explicit restore is required.
    db_conn.commit()

    # Sanity-check the restore landed:
    row = db_conn.execute(
        text("SELECT password FROM Users WHERE username = 'user@test.local'")
    ).fetchone()
    assert bcrypt.checkpw(b"Test1234!", row[0].encode("utf-8"))


def test_set_language_invalid_lang_flashes_and_redirects(user_client):
    resp = user_client.get("/language/xx", follow_redirects=False)
    assert resp.status_code == 302
    assert "/profile" in resp.headers.get("Location", "")


def test_set_language_valid_lang_updates_session(user_client):
    resp = user_client.get("/language/de", follow_redirects=False)
    assert resp.status_code == 302
    with user_client.session_transaction() as sess:
        assert sess.get("locale") == "de"
    # Restore for sibling tests
    user_client.get("/language/en")


def test_set_language_all_valid_locales(user_client):
    for lang in ("de", "en", "fr", "it"):
        resp = user_client.get(f"/language/{lang}", follow_redirects=False)
        assert resp.status_code == 302
    # End on en for sibling tests
    user_client.get("/language/en")


def _patch_avatars_dir(monkeypatch, uploads_dir):
    """Point profile.py's PATHS.uploads at an isolated tmp dir for the
    duration of one test, so avatar tests never touch the real var/uploads/."""
    from nx_lib.views import profile as profile_module

    monkeypatch.setattr(profile_module, "PATHS", SimpleNamespace(uploads=uploads_dir))


def test_avatar_missing_returns_404(client, tmp_path, monkeypatch):
    _patch_avatars_dir(monkeypatch, tmp_path)
    resp = client.get("/avatar/999999")
    assert resp.status_code == 404


def test_avatar_serves_uploaded_file(client, tmp_path, monkeypatch):
    _patch_avatars_dir(monkeypatch, tmp_path)
    avatars_dir = tmp_path / "avatars"
    avatars_dir.mkdir(parents=True)
    img = Image.new("RGB", (1, 1))
    img.save(avatars_dir / "424242-icon.png", format="PNG")

    resp = client.get("/avatar/424242")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "image/png"


def test_avatar_upload_saves_outside_static(user_client, tmp_path, monkeypatch, db_conn):
    """Regression guard for the bug this route was added to fix: an uploaded
    avatar must land under var/uploads/avatars/, never under static/ -- that
    tree is robocopy /MIR'd from git on every deploy, which deletes anything
    not committed to source, i.e. it would silently wipe every user's
    uploaded avatar on the next release (see nx_lib/users.py).

    /update_profile requires fullName/email in the same POST as the file, so
    this incidentally rewrites Fullname too -- restored below via db_conn
    (same pattern as test_change_password_happy_path_then_restore) so this
    doesn't drift a value other tests/suites (e.g. the reporting-share e2e
    test) depend on.
    """
    from sqlalchemy import text

    _patch_avatars_dir(monkeypatch, tmp_path)

    buf = io.BytesIO()
    Image.new("RGB", (1, 1)).save(buf, format="PNG")
    buf.seek(0)

    resp = user_client.post(
        "/update_profile",
        data={
            "fullName": "User",
            "email": "user@test.local",
            "file": (buf, "avatar.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert resp.status_code == 302

    with user_client.session_transaction() as sess:
        userid = sess["userid"]
    assert (tmp_path / "avatars" / f"{userid}-icon.png").exists()

    # update_profile committed on its own connection -- db_conn's rollback
    # can't undo it, so restore the seeded fullname explicitly.
    db_conn.execute(
        text("UPDATE Users SET fullname = 'Test User' WHERE username = 'user@test.local'"),
    )
    db_conn.commit()
