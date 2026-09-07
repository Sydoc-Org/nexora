"""Delete expired rows from dbo.ActiveSessions (#227).

Session expiry was implemented on one half only: ops/cleanup/
cleanup_expired_sessionFiles.ps1 removes the session *files* under var/session,
but nothing ever removed the matching database rows. Measured on PROD in
September 2026: 1,505 rows, ~99% of them expired, the oldest four months old.
An orphaned row cannot authenticate -- its file is gone -- but it still sits
there claiming to be a session.

WHY A STRAIGHT DELETE, NOT AN ARCHIVE
Every reader of this table filters to the last 30 minutes:

    admin overview      SELECT COUNT(*) ... WHERE LastSeenAt >= DATEADD(minute, -30, GETDATE())
    admin users list    ... WHERE a.LastSeenAt >= DATEADD(minute, -30, GETDATE())

The remaining uses are an UPDATE of LastSeenAt on the current session, a DELETE
on logout, and a lookup by UserID for admin force-logout. Nothing reads a row
older than half an hour, so old rows are unreachable, not merely unused. Login
history already lives in dbo.Logs (which is what the admin overview counts
sign-ins from) and Users.LastLoginAt. The one field not duplicated elsewhere is
IPAddress -- personal data with no stated retention purpose, so keeping months
of it by accident is a liability rather than an asset.

RETENTION
SESSION_LIFETIME + SESSION_ROW_RETENTION_GRACE, both from nx_lib.config, so the
window cannot drift below the lifetime of a live session. Today that is
24 hours + 7 days = 8 days.

USAGE
    python ops/cleanup/prune_active_sessions.py --dry-run    # report only
    python ops/cleanup/prune_active_sessions.py              # delete

ENVIRONMENT selects the target database, exactly as it does for the app
(ENVIRONMENT=PROD on the scheduled run).

NOT YET SCHEDULED -- MANUAL DEPLOY STEP
Merging this changes nothing on its own: no row is deleted until someone
registers a scheduled task on the app host, next to the existing
cleanup_expired_sessionFiles.ps1. Until that task exists, do not state the
retention anywhere user-facing -- the privacy page (#260) made exactly that
mistake. Same failure mode as env/PROD.env in CLAUDE.md: the repo change
lands, the server side is hand-work, and forgetting is silent.

    ENVIRONMENT=PROD python ops/cleanup/prune_active_sessions.py --dry-run
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nx_lib import config as cfg
from nx_lib.db import engine_nexora_db

RETENTION = cfg.SESSION_LIFETIME + cfg.SESSION_ROW_RETENTION_GRACE

# Minutes, not days. DATEADD(day, ...) took int(total_seconds() // 86400), which
# floored the window: a grace of 23 hours on a 24-hour lifetime collapsed from
# an intended 47 hours to 24, and a 12-hour lifetime with 6 hours of grace
# floored to DATEADD(day, 0, GETDATE()) -- i.e. now, deleting every row and
# signing out every live session. Today's 24h + 7d is exactly 8 days so nothing
# was lost, but the arithmetic must not depend on that.
RETENTION_MINUTES = int(RETENTION.total_seconds() // 60)

# Guard rail, not decoration: a threshold at or under SESSION_LIFETIME deletes
# rows belonging to sessions that are still valid, and _enforce_active_session
# logs a user out the moment their SID is missing from this table. Asserted on
# RETENTION_MINUTES -- the number the query actually uses -- because the old
# check passed on the un-floored timedelta and so guarded nothing.
LIFETIME_MINUTES = int(cfg.SESSION_LIFETIME.total_seconds() // 60)
assert RETENTION_MINUTES > LIFETIME_MINUTES, "retention must exceed the session lifetime"

COUNT_SQL = (
    "SELECT COUNT(*) FROM dbo.ActiveSessions WHERE LastSeenAt < DATEADD(minute, ?, GETDATE())"
)
DELETE_SQL = "DELETE FROM dbo.ActiveSessions WHERE LastSeenAt < DATEADD(minute, ?, GETDATE())"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="report how many rows would go, delete nothing",
    )
    args = ap.parse_args()

    if engine_nexora_db is None:
        print("NexoraDB engine is not configured (check ENVIRONMENT and env vars).")
        return 2

    minutes = -RETENTION_MINUTES
    env = os.environ.get("ENVIRONMENT", "(unset)")
    print(f"[prune-sessions] env={env} retention={RETENTION} (LastSeenAt older than {RETENTION})")

    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(COUNT_SQL, (minutes,))
        row = cur.fetchone()
        stale = row[0] if row else 0

        cur.execute("SELECT COUNT(*) FROM dbo.ActiveSessions")
        row = cur.fetchone()
        total = row[0] if row else 0

        if args.dry_run:
            print(f"[prune-sessions] would delete {stale} of {total} row(s); nothing written.")
            return 0

        if not stale:
            print(f"[prune-sessions] nothing to delete ({total} row(s) all within retention).")
            return 0

        cur.execute(DELETE_SQL, (minutes,))
        conn.commit()
        print(f"[prune-sessions] deleted {stale} of {total} row(s); {total - stale} remain.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
