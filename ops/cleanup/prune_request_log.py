r"""Delete request-log rows older than the retention period from dbo.Logs (#283).

WHY THIS EXISTS
dbo.Logs holds one row per request, forever. Nothing deleted from it, and it is
not merely an IP log -- each row carries RequestIpAddress, UserID, Username,
Path, HttpResponseCode and Args (the query parameters), so it is a per-user
behavioural trail. An IP tied to a named user and a timestamp is personal data;
keeping it indefinitely with no stated purpose is the hardest part of that
position to defend, and revDSG expects data to be destroyed or anonymised once
it is no longer needed for its purpose.

The logging itself is fine -- fault diagnosis and detecting account misuse are
ordinary legitimate interests for an internal platform. It was the unbounded
retention that was not.

RETENTION
REQUEST_LOG_RETENTION from nx_lib.config: 180 days. Six months is expressed in
days on purpose -- a calendar month varies in length and this window has to be
deterministic, since the same number is quoted in the privacy notice.

WHY BATCHED, UNLIKE THE SESSION PRUNE
prune_active_sessions.py deletes in one statement because ActiveSessions holds
a couple of thousand rows. dbo.Logs is unbounded and may hold millions on the
first run, where a single DELETE would hold a long lock on a table the admin
log viewer queries, and bloat the transaction log. This deletes in batches,
committing each one, so the first run is interruptible and never holds a lock
for long. IX_Logs_Timestamp already exists, so each batch is an index seek
rather than a scan.

SCHEDULING
prune-request-log-task.xml next to this script is the Task Scheduler definition
(daily at 03:45, offset from the session prune's 03:30 so the two never overlap),
and deploy.yml's "Register scheduled tasks" step imports it on every push to
main. No manual step -- see #280 for why that step exists.

    ENVIRONMENT=PROD python ops/cleanup/prune_request_log.py --dry-run
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nx_lib import config as cfg
from nx_lib.db import engine_nexora_db

RETENTION = cfg.REQUEST_LOG_RETENTION

# Minutes, not days, for the same reason as the session prune: expressing the
# window in days meant flooring it, and a floored window can silently collapse
# (see #227). Minutes carry every configuration exactly.
RETENTION_MINUTES = int(RETENTION.total_seconds() // 60)

# Guard rail. A misconfigured retention here deletes audit history that cannot
# be recovered, so refuse anything shorter than a day rather than trusting the
# caller. One day is already far below any defensible policy; the assert is
# there to stop a zero or a negative, not to validate the policy itself.
assert RETENTION_MINUTES >= 24 * 60, "request-log retention must be at least one day"

# Rows per batch. Large enough that a first run over millions of rows does not
# take all night, small enough that no single transaction is long-lived.
BATCH_SIZE = 5000

# Stops a runaway loop if something keeps re-inserting older rows: at 5000 a
# batch this is 10 million rows in one run, well past any plausible backlog.
MAX_BATCHES = 2000

COUNT_SQL = "SELECT COUNT(*) FROM dbo.Logs WHERE [Timestamp] < DATEADD(minute, ?, GETDATE())"
TOTAL_SQL = "SELECT COUNT(*) FROM dbo.Logs"
OLDEST_SQL = "SELECT MIN([Timestamp]) FROM dbo.Logs"
# TOP takes a literal rather than a parameter: the value is ours, not input, and
# a parameterised TOP is a driver-compatibility gamble for no benefit.
DELETE_SQL = (
    f"DELETE TOP ({int(BATCH_SIZE)}) FROM dbo.Logs "
    "WHERE [Timestamp] < DATEADD(minute, ?, GETDATE())"
)


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
    print(f"[prune-request-log] env={env} retention={RETENTION} (Timestamp older than {RETENTION})")

    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(TOTAL_SQL)
        row = cur.fetchone()
        total = row[0] if row else 0
        cur.execute(OLDEST_SQL)
        row = cur.fetchone()
        oldest = row[0] if row else None
        cur.execute(COUNT_SQL, (minutes,))
        row = cur.fetchone()
        stale = row[0] if row else 0

        print(f"[prune-request-log] {total} row(s) total, oldest {oldest}")

        if args.dry_run:
            print(f"[prune-request-log] would delete {stale} row(s); nothing written.")
            return 0

        if not stale:
            print(f"[prune-request-log] nothing to delete ({total} row(s) all within retention).")
            return 0

        deleted = 0
        for batch in range(MAX_BATCHES):
            cur.execute(DELETE_SQL, (minutes,))
            affected = cur.rowcount
            # Commit per batch so the first run over a large backlog is
            # interruptible and never holds a long transaction.
            conn.commit()
            if affected <= 0:
                break
            deleted += affected
            if batch and batch % 20 == 0:
                print(f"[prune-request-log] ... {deleted} deleted so far")
        else:
            print(
                f"[prune-request-log] stopped at the {MAX_BATCHES}-batch cap after "
                f"{deleted} row(s); re-run to continue."
            )

        print(f"[prune-request-log] deleted {deleted} row(s); {total - deleted} remain.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
