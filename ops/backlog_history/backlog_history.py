"""Standalone backlog-history collector (Windows Task Scheduler, every 30 min).

Self-contained: no nexora imports — copy this folder anywhere (any prod
server), fill in `.env` next to this file, `pip install -r requirements.txt`,
and wire a scheduled task:

    <python.exe> <path>\\backlog_history.py --once

Snapshots the current C+A backlog per (source, client, process) from the Octo
runtime DB (SQL Server) and, when the MS02_* vars are set, the MS02 Postgres
runtime DB, then appends the rows to dbo.BacklogHistory on the Statistics DB
(table created idempotently on first run). SnapshotAt is server-local time.

Logs to backlog_history.log next to this file (rotating, 1 MB x 3). On any
failure (a source query or the Statistics-DB write) it opens ONE consolidated
helpdesk ticket by mailing TICKET_TO via Microsoft Graph (same ROPC flow as
the ping monitor), throttled by TICKET_COOLDOWN_HOURS so a dead DB does not
raise a new ticket every 30 minutes, and exits non-zero.

Flags:
    --once       take one snapshot and exit (default)
    --dry-run    query the sources and print what *would* be written; no insert
"""

import argparse
import json
import logging
import logging.handlers
import os
import socket
import sys
import urllib.parse
import urllib.request
from datetime import datetime

import pyodbc
from dotenv import load_dotenv

_HERE = os.path.dirname(os.path.abspath(__file__))
log = logging.getLogger("backlog_history")

# (ClientName, ProcessName) pairs that never make it into the history —
# reporting-only / template / retired processes with no operational backlog.
EXCLUDED = {
    ("ELSY", "DigitalMailroom"),
    ("ElektroMaterial", "01_Stammdaten"),
    ("Geberit", "01_Garantiekarten"),
    ("Privera", "01_Reporting"),
    ("Privera", "01_Stammdaten"),
    ("Privera", "02_Invoice"),
    ("Privera", "03_Stammdaten"),
    ("Privera", "Zeus"),
    ("System", "System"),
    ("system", "system"),
    ("sydoc", "DPSI_Template"),
}

# Counted from the PROCESSES side so every process yields a row each snapshot,
# zero-backlog ones included — a process with nothing in C+A must still chart
# as 0, not vanish from the series.
_BACKLOG_SQL_MSSQL = """
SELECT p.ClientName, p.Name, COUNT(w.id)
FROM t_Processes p
LEFT JOIN t_ActivityInstances a ON a.ProcessID = p.id
LEFT JOIN t_ActivityTypes act ON act.id = a.ActivityTypeID
LEFT JOIN t_WorkItems w ON w.ActivityInstanceID = a.id AND act.Name = 'C+A'
GROUP BY p.ClientName, p.Name
"""

_BACKLOG_SQL_PG = """
SELECT p."ClientName", p."Name", COUNT(w."ID")
FROM "t_Processes" p
LEFT JOIN "t_ActivityInstances" a ON a."ProcessID" = p."ID"
LEFT JOIN "t_ActivityTypes" act ON act."ID" = a."ActivityTypeID"
LEFT JOIN "t_WorkItems" w ON w."ActivityInstanceID" = a."ID" AND act."Name" = 'C+A'
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
    """([(source_code, client, process, count)], [failure messages]) across
    both sources, minus the EXCLUDED pairs. One failing source must not block
    the other; its failure is reported instead."""
    rows, failures = [], []
    for code, fetch in (("default", fetch_octo), ("ms02", fetch_ms02)):
        try:
            rows.extend(
                (code, client, process, count)
                for client, process, count in fetch()
                if (client, process) not in EXCLUDED
            )
        except Exception as e:
            log.error(f"source {code} failed: {e}")
            failures.append(f"source {code} failed: {e}")
    return rows, failures


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


# ---- logging + helpdesk ticket on failure ----------------------------------

_COOLDOWN_STAMP = os.path.join(_HERE, "last_ticket.txt")


def setup_logging():
    handler = logging.handlers.RotatingFileHandler(
        os.path.join(_HERE, "backlog_history.log"),
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    log.setLevel(logging.INFO)
    log.addHandler(handler)
    log.addHandler(console)


def _graph_token():
    body = urllib.parse.urlencode(
        {
            "client_id": os.environ["GRAPH_CLIENT_ID"],
            "username": os.environ["GRAPH_USERNAME"],
            "password": os.environ["GRAPH_PASSWORD"],
            "client_secret": os.environ["GRAPH_CLIENT_SECRET"],
            "grant_type": "password",
            "scope": "Mail.Send",
        }
    ).encode()
    url = f"https://login.microsoftonline.com/{os.environ['GRAPH_TENANT_ID']}/oauth2/v2.0/token"
    with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=30) as resp:
        return json.load(resp)["access_token"]


def _ticket_cooldown_active(now):
    hours = float(os.environ.get("TICKET_COOLDOWN_HOURS") or "6")
    try:
        with open(_COOLDOWN_STAMP, encoding="utf-8") as f:
            last = datetime.fromisoformat(f.read().strip())
    except (OSError, ValueError):
        return False
    return (now - last).total_seconds() < hours * 3600


def open_ticket(failures, now):
    """Mail ONE consolidated failure ticket to the helpdesk via Graph. Never
    raises — a broken mailer must not mask the original failure — and skips
    while a previous ticket's cooldown window is still open."""
    to = os.environ.get("TICKET_TO")
    if not (to and os.environ.get("GRAPH_TENANT_ID")):
        log.warning("ticketing not configured (TICKET_TO / GRAPH_* unset), skipping ticket")
        return False
    if _ticket_cooldown_active(now):
        log.info("ticket cooldown active, not opening another ticket")
        return False
    host = socket.gethostname()
    lines = "".join(f"<li>{f}</li>" for f in failures)
    payload = json.dumps(
        {
            "message": {
                "subject": f"[backlog-history] collector failed on {host}",
                "body": {
                    "contentType": "HTML",
                    "content": (
                        f"<p>The backlog-history collector on <strong>{host}</strong> "
                        f"failed at {now:%Y-%m-%d %H:%M}:</p><ul>{lines}</ul>"
                        f"<p>Log: {os.path.join(_HERE, 'backlog_history.log')}</p>"
                    ),
                },
                "toRecipients": [{"emailAddress": {"address": to}}],
            },
            "saveToSentItems": True,
        }
    ).encode()
    try:
        token = _graph_token()
        req = urllib.request.Request(
            "https://graph.microsoft.com/v1.0/me/sendMail",
            data=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30):
            pass
        with open(_COOLDOWN_STAMP, "w", encoding="utf-8") as f:
            f.write(now.isoformat())
        log.info(f"helpdesk ticket opened ({to})")
        return True
    except Exception as e:
        log.error(f"could not open helpdesk ticket: {e}")
        return False


def run_once(dry_run=False):
    now = datetime.now().replace(microsecond=0)
    rows, failures = collect_snapshot()
    if dry_run:
        for source_code, client, process, count in rows:
            print(f"[dry-run] {source_code} {client}.{process}: {count}")
        print(f"[dry-run] {len(rows)} rows, nothing written")
        return 1 if failures else 0
    if rows:
        try:
            write_snapshot(rows, now)
            log.info(f"{len(rows)} rows written at {now:%Y-%m-%d %H:%M}")
        except Exception as e:
            log.error(f"Statistics-DB write failed: {e}")
            failures.append(f"Statistics-DB write failed: {e}")
    if failures:
        open_ticket(failures, now)
        return 1
    return 0


def main():
    load_dotenv(os.path.join(_HERE, ".env"))
    setup_logging()
    ap = argparse.ArgumentParser(description="Snapshot the per-process C+A backlog.")
    ap.add_argument("--once", action="store_true", help="take one snapshot and exit (default)")
    ap.add_argument("--dry-run", action="store_true", help="print rows, do not write")
    args = ap.parse_args()
    sys.exit(run_once(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
