"""Backlog-history collector (driven by Windows Task Scheduler).

Snapshots the current C+A backlog per (source, client, process) across all
active workitem sources (default Octo SQL Server + MS02 Postgres when
configured) and appends the rows to dbo.BacklogHistory on the Statistics DB,
so backlog-over-time trends exist. Lives in ops/ because that directory ships
to the server (scripts/ does not).

The Statistics DB is a runtime surface, not schema we own (see CLAUDE.md), so
the table is created idempotently here rather than via sql/_migrations/.

Wiring (PROD): a Task Scheduler task running every 30 minutes:

    set ENVIRONMENT=PROD
    D:\\sydoc\\tools\\py\\python.exe D:\\sydoc\\nexora\\ops\\backlog_history.py --once

Flags:
    --once       take one snapshot and exit (default)
    --dry-run    query the sources and print what *would* be written; no insert
"""

import argparse
import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nx_lib.db import engine_statistics_db
from nx_lib.workitem_sources import active_sources
from nx_main import app

_ENSURE_TABLE = """
IF NOT EXISTS (
    SELECT 1 FROM sys.tables
    WHERE name = 'BacklogHistory' AND schema_id = SCHEMA_ID('dbo')
)
BEGIN
    CREATE TABLE dbo.BacklogHistory (
        BacklogHistoryID INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_BacklogHistory PRIMARY KEY,
        SnapshotAtUtc DATETIME2(0) NOT NULL,
        SourceCode NVARCHAR(50) NOT NULL,
        ClientName NVARCHAR(255) NULL,
        ProcessName NVARCHAR(255) NULL,
        BacklogCount INT NOT NULL
    );
    CREATE INDEX IX_BacklogHistory_SnapshotAtUtc
        ON dbo.BacklogHistory (SnapshotAtUtc);
END
"""

_INSERT = (
    "INSERT INTO dbo.BacklogHistory "
    "(SnapshotAtUtc, SourceCode, ClientName, ProcessName, BacklogCount) "
    "VALUES (?, ?, ?, ?, ?)"
)


def collect_snapshot():
    """[(source_code, client, process, count)] across all active sources.
    One failing source must not block the others."""
    rows = []
    for src in active_sources():
        try:
            for r in src.backlog_by_process():
                rows.append((src.code, r["client"], r["process"], r["count"]))
        except Exception as e:
            app.logger.error(f"backlog_history: source {src.code} failed: {e}")
    return rows


def write_snapshot(rows, now):
    conn = engine_statistics_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(_ENSURE_TABLE)
        for source_code, client, process, count in rows:
            cur.execute(_INSERT, (now, source_code, client, process, count))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_once(dry_run=False):
    now = datetime.now(UTC).replace(tzinfo=None)
    with app.app_context():
        rows = collect_snapshot()
        if dry_run:
            for source_code, client, process, count in rows:
                print(f"[dry-run] {source_code} {client}.{process}: {count}")
            print(f"[dry-run] {len(rows)} rows, nothing written")
            return 0
        write_snapshot(rows, now)
    print(f"backlog history: {len(rows)} rows written at {now:%Y-%m-%d %H:%M} UTC")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Snapshot the per-process C+A backlog.")
    ap.add_argument("--once", action="store_true", help="take one snapshot and exit (default)")
    ap.add_argument("--dry-run", action="store_true", help="print rows, do not write")
    args = ap.parse_args()
    sys.exit(run_once(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
