"""Standalone backlog-history collector (Windows Task Scheduler, every 30 min).

Self-contained: no nexora imports — copy this folder anywhere (any prod
server), fill in `.env` next to this file, `pip install -r requirements.txt`,
and wire a scheduled task:

    <python.exe> <path>\\backlog_history.py --once

Snapshots the current C+A backlog per (source, client, process) from the Octo
runtime DB (SQL Server) and, when the MS02_* vars are set, the MS02 Postgres
runtime DB, then appends the rows to dbo.BacklogHistory on the Statistics DB
(table created idempotently on first run). SnapshotAt is server-local time.

Flags:
    --once       take one snapshot and exit (default)
    --dry-run    query the sources and print what *would* be written; no insert
"""

import argparse
import os
import sys
from datetime import datetime

import pyodbc
from dotenv import load_dotenv

# (ClientName, ProcessName) pairs that never make it into the history —
# reporting-only / template / retired processes with no operational backlog.
EXCLUDED = {
    ("Privera", "01_Reporting"),
    ("Privera", "02_Invoice"),
    ("Privera", "Zeus"),
    ("sydoc", "DPSI_Template"),
}

_BACKLOG_SQL_MSSQL = """
SELECT p.ClientName, p.Name, COUNT(*)
FROM t_WorkItems w
LEFT JOIN t_ActivityInstances a ON a.id = w.ActivityInstanceID
LEFT JOIN t_Processes p ON p.id = a.ProcessID
LEFT JOIN t_ActivityTypes act ON act.id = a.ActivityTypeID
WHERE act.Name = 'C+A'
GROUP BY p.ClientName, p.Name
"""

_BACKLOG_SQL_PG = """
SELECT p."ClientName", p."Name", COUNT(*)
FROM "t_WorkItems" w
LEFT JOIN "t_ActivityInstances" a ON a."ID" = w."ActivityInstanceID"
LEFT JOIN "t_Processes" p ON p."ID" = a."ProcessID"
LEFT JOIN "t_ActivityTypes" act ON act."ID" = a."ActivityTypeID"
WHERE act."Name" = 'C+A'
GROUP BY p."ClientName", p."Name"
"""

_ENSURE_TABLE = """
IF NOT EXISTS (
    SELECT 1 FROM sys.tables
    WHERE name = 'BacklogHistory' AND schema_id = SCHEMA_ID('dbo')
)
BEGIN
    CREATE TABLE dbo.BacklogHistory (
        BacklogHistoryID INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_BacklogHistory PRIMARY KEY,
        SnapshotAt DATETIME2(0) NOT NULL,
        SourceCode NVARCHAR(50) NOT NULL,
        ClientName NVARCHAR(255) NULL,
        ProcessName NVARCHAR(255) NULL,
        BacklogCount INT NOT NULL
    );
    CREATE INDEX IX_BacklogHistory_SnapshotAt
        ON dbo.BacklogHistory (SnapshotAt);
END
"""

_INSERT = (
    "INSERT INTO dbo.BacklogHistory "
    "(SnapshotAt, SourceCode, ClientName, ProcessName, BacklogCount) "
    "VALUES (?, ?, ?, ?, ?)"
)


def _mssql_connect(database):
    return pyodbc.connect(
        f"DRIVER={{SQL Server}};"
        f"SERVER={os.environ['DB_SERVER_PRD']},1433;"
        f"DATABASE={database};"
        f"UID={os.environ['DB_UID']};"
        f"PWD={os.environ['DB_PWD']};"
    )


def fetch_octo():
    """[(client, process, count)] from the default Octo SQL Server runtime."""
    conn = _mssql_connect(os.environ["DB_OCTO_RUNTIME"])
    try:
        cur = conn.cursor()
        cur.execute(_BACKLOG_SQL_MSSQL)
        return [(r[0], r[1], r[2] or 0) for r in cur.fetchall()]
    finally:
        conn.close()


def fetch_ms02():
    """[(client, process, count)] from the MS02 Postgres runtime; [] when the
    MS02_* env vars are not provisioned (graceful skip, same as the app)."""
    host = os.environ.get("MS02_DB_SERVER_PRD")
    name = os.environ.get("MS02_DB_OCTO_RUNTIME")
    user = os.environ.get("MS02_DB_UID")
    pwd = os.environ.get("MS02_DB_PWD")
    if not (host and name and user and pwd):
        return []
    import psycopg2

    conn = psycopg2.connect(
        host=host,
        port=int(os.environ.get("MS02_DB_PORT") or "5432"),
        dbname=name,
        user=user,
        password=pwd,
        sslmode=os.environ.get("MS02_DB_SSLMODE") or "require",
    )
    try:
        cur = conn.cursor()
        cur.execute(_BACKLOG_SQL_PG)
        return [(r[0], r[1], r[2] or 0) for r in cur.fetchall()]
    finally:
        conn.close()


def collect_snapshot():
    """[(source_code, client, process, count)] across both sources, minus the
    EXCLUDED pairs. One failing source must not block the other."""
    rows = []
    for code, fetch in (("default", fetch_octo), ("ms02", fetch_ms02)):
        try:
            rows.extend(
                (code, client, process, count)
                for client, process, count in fetch()
                if (client, process) not in EXCLUDED
            )
        except Exception as e:
            print(f"[error] source {code} failed: {e}", file=sys.stderr)
    return rows


def write_snapshot(rows, now):
    conn = _mssql_connect(os.environ["DB_STATISTICS"])
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
    now = datetime.now().replace(microsecond=0)
    rows = collect_snapshot()
    if dry_run:
        for source_code, client, process, count in rows:
            print(f"[dry-run] {source_code} {client}.{process}: {count}")
        print(f"[dry-run] {len(rows)} rows, nothing written")
        return 0
    write_snapshot(rows, now)
    print(f"backlog history: {len(rows)} rows written at {now:%Y-%m-%d %H:%M}")
    return 0


def main():
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    ap = argparse.ArgumentParser(description="Snapshot the per-process C+A backlog.")
    ap.add_argument("--once", action="store_true", help="take one snapshot and exit (default)")
    ap.add_argument("--dry-run", action="store_true", help="print rows, do not write")
    args = ap.parse_args()
    sys.exit(run_once(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
