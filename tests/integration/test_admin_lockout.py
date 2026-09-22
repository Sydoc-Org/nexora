r"""Admins can see who is locked out and unlock them in one click.

Before this, `dbo.LoginLockout` was read and written only by
`nx_lib/views/auth.py`. Nothing surfaced it, so unsticking a locked-out
colleague meant a hand-written DELETE against the production database -- and
the lockout is invisible from every other screen: the person is told "too
many attempts" and support is told nothing at all.

Two properties are worth pinning rather than just "the endpoint returns 200":

**Expired rows are not "locked".** auth.py only deletes a row on a successful
login, so the table keeps rows whose `locked_until` has passed. Listing by
existence rather than by time would show a queue of people who can already
log in perfectly well.

**Unlocking clears both keys.** auth.py locks the password step under the bare
userid and the TOTP step under `2fa:<userid>`; they lock independently. An
admin pressing Unlock means "let them in", not "let them past one of the two
doors".
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from nx_lib.db import engine_nexora_db


@pytest.fixture()
def lockout_rows():
    """Insert lockout rows, and clean them up whatever the test does."""
    made = []

    def _add(key, failed_count=5, minutes=15):
        with engine_nexora_db.begin() as c:
            c.execute(text("DELETE FROM dbo.LoginLockout WHERE userid = :k"), {"k": key})
            c.execute(
                text(
                    "INSERT INTO dbo.LoginLockout (userid, failed_count, locked_until) "
                    "VALUES (:k, :c, :u)"
                ),
                {
                    "k": key,
                    "c": failed_count,
                    "u": datetime.utcnow() + timedelta(minutes=minutes),
                },
            )
        made.append(key)
        return key

    yield _add

    with engine_nexora_db.begin() as c:
        for key in made:
            c.execute(text("DELETE FROM dbo.LoginLockout WHERE userid = :k"), {"k": key})


def _a_userid():
    with engine_nexora_db.connect() as c:
        return c.execute(text("SELECT TOP 1 userid FROM Users ORDER BY userid")).scalar()


def _locked(client):
    resp = client.get("/api/admin/locked_accounts")
    assert resp.status_code == 200, resp.status_code
    return resp.get_json()["locked"]


def test_a_currently_locked_account_is_listed(admin_client, lockout_rows):
    uid = _a_userid()
    lockout_rows(str(uid))

    rows = _locked(admin_client)
    mine = [r for r in rows if r["userID"] == uid]
    assert mine, f"userid {uid} is locked but not listed"
    assert mine[0]["stage"] == "password"
    assert mine[0]["failed_count"] == 5


def test_a_2fa_lock_is_named_as_such(admin_client, lockout_rows):
    """The two steps lock independently and support needs to know which."""
    uid = _a_userid()
    lockout_rows(f"2fa:{uid}")

    mine = [r for r in _locked(admin_client) if r["userID"] == uid]
    assert mine and mine[0]["stage"] == "2fa"


def test_an_expired_lock_is_not_listed(admin_client, lockout_rows):
    """auth.py leaves expired rows behind; they are not lockouts any more."""
    uid = _a_userid()
    lockout_rows(str(uid), minutes=-5)

    assert not [r for r in _locked(admin_client) if r["userID"] == uid], (
        "an expired lockout row was reported as a locked account -- listing by "
        "row existence rather than by locked_until"
    )


def test_unlock_clears_both_the_password_and_the_2fa_lock(admin_client, lockout_rows):
    uid = _a_userid()
    lockout_rows(str(uid))
    lockout_rows(f"2fa:{uid}")
    assert len([r for r in _locked(admin_client) if r["userID"] == uid]) == 2

    resp = admin_client.post(f"/admin/users/{uid}/unlock")
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    assert not [r for r in _locked(admin_client) if r["userID"] == uid], (
        "Unlock left one of the two lockout keys in place -- the user would "
        "still be stopped, just at the other step"
    )


def test_unlock_is_harmless_when_nothing_is_locked(admin_client):
    """Support will press it speculatively; it must not error."""
    resp = admin_client.post(f"/admin/users/{_a_userid()}/unlock")
    assert resp.status_code == 200
    assert resp.get_json()["cleared"] == 0


def test_unlock_needs_a_permission(user_client):
    """A plain user must not be able to unlock accounts."""
    resp = user_client.post(f"/admin/users/{_a_userid()}/unlock")
    assert resp.status_code in (401, 403), resp.status_code
