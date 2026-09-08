"""Serialise hand resets of the shared NEXORA_TEST database (#235).

pytest itself no longer needs this: every run creates a private
NEXORA_TEST_<user>_<pid> (tests/conftest.py). The shared NEXORA_TEST remains
for hand-driven TEST servers, and two scripts/test_db_reset.py runs resetting
it at once would corrupt each other: whichever runs second re-seeds
dbo.Users under the one already going, and a random login fixture dies with
`KeyError: 'userid'` or a stray 401. The failure is never the same test twice
and always passes in isolation, so it reads as "that test is flaky" rather
than "something else is resetting your database".

`sp_getapplock` makes the second runner WAIT instead of corrupting. The lock is
taken with @LockOwner='Session', which ties it to the SQL session holding it:
a killed run releases it when SQL Server reaps that session, so there is no
stale lock to clear by hand.

Wall-clock is NOT a reliable tell for contention -- a brief collision reddens a
run without slowing it (the deploy of #231 failed in 3m54s, well inside the
normal ~5m). That is why this is a lock and not a "check before you run" note.

Escape hatch: NEXORA_TEST_LOCK_SKIP=1 disables locking entirely, mirroring the
SQL_SYNC_SKIP=1 convention used by the pre-commit hooks.
"""

from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager

# Database-scoped: both parties connect to NEXORA_TEST, so they contend on the
# same name. Anything else running against that database should use it too.
RESOURCE = "nexora_test_suite"

# A full CI tier is ~5 min and e2e ~12, so a peer can legitimately hold this
# for a while. Long enough to queue behind one of those, short enough that a
# genuinely wedged lock surfaces instead of hanging until someone notices.
DEFAULT_TIMEOUT_MS = 20 * 60 * 1000

SKIP_ENV = "NEXORA_TEST_LOCK_SKIP"
TIMEOUT_ENV = "NEXORA_TEST_LOCK_TIMEOUT_MS"

# sp_getapplock return codes. >= 0 means the lock is held.
_GRANTED = {0: "granted", 1: "granted after waiting"}
_REFUSED = {
    -1: "timed out waiting for another test run to finish",
    -2: "cancelled",
    -3: "chosen as a deadlock victim",
    -999: "parameter or call error",
}


def _timeout_ms(explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    raw = os.environ.get(TIMEOUT_ENV)
    return int(raw) if raw and raw.isdigit() else DEFAULT_TIMEOUT_MS


def _acquire(cursor, resource: str, timeout_ms: int) -> int:
    cursor.execute(
        "DECLARE @rc int; "
        "EXEC @rc = sp_getapplock @Resource = ?, @LockMode = 'Exclusive', "
        "@LockOwner = 'Session', @LockTimeout = ?; "
        "SELECT @rc;",
        resource,
        timeout_ms,
    )
    return int(cursor.fetchone()[0])


def _default_notify(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


@contextmanager
def hold(
    conn,
    label: str = "test run",
    resource: str = RESOURCE,
    timeout_ms: int | None = None,
    notify=_default_notify,
):
    """Hold the shared-database lock on `conn` for the duration of the block.

    `conn` must be an autocommit DBAPI connection to NEXORA_TEST, and must stay
    open for as long as the lock is needed -- the lock dies with its session.

    Probes with a zero timeout first so that waiting for a peer prints a reason
    rather than looking like a hang. `notify` exists because pytest captures
    stderr by default -- conftest passes one that suspends capture, otherwise
    the "waiting" line is swallowed and a 20-minute wait looks like a freeze.
    """
    if os.environ.get(SKIP_ENV) == "1":
        notify(f"[db-lock] {SKIP_ENV}=1 -- not serialising ({label})")
        yield "skipped"
        return

    total_ms = _timeout_ms(timeout_ms)
    cursor = conn.cursor()

    rc = _acquire(cursor, resource, 0)
    if rc < 0:
        mins = total_ms / 60000
        notify(
            f"[db-lock] another test run holds {resource}; waiting up to {mins:.0f} min "
            f"({label}). Set {SKIP_ENV}=1 to bypass -- see issue #235."
        )
        waited = time.monotonic()
        rc = _acquire(cursor, resource, total_ms)
        if rc >= 0:
            notify(f"[db-lock] acquired after {time.monotonic() - waited:.0f}s")

    if rc < 0:
        raise RuntimeError(
            f"could not acquire {resource}: {_REFUSED.get(rc, f'sp_getapplock returned {rc}')}. "
            f"Another test run is using NEXORA_TEST. Wait for it, raise {TIMEOUT_ENV}, "
            f"or set {SKIP_ENV}=1 to run anyway (see issue #235)."
        )

    try:
        yield _GRANTED.get(rc, "held")
    finally:
        try:
            cursor.execute(
                "EXEC sp_releaseapplock @Resource = ?, @LockOwner = 'Session';", resource
            )
        except Exception as e:
            # Not fatal: the lock is session-scoped, so closing the connection
            # (or SQL Server reaping it) frees it anyway.
            notify(f"[db-lock] release failed, session close will free it: {e}")
