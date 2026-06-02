"""Scheduled-report runner (driven by Windows Task Scheduler).

Finds due rows in dbo.ReportSchedules, runs each saved report *as its owner*
(reusing nx_lib.reporting.runner), renders xlsx/csv, emails it via Microsoft
Graph, and advances NextRunAt. Lives in ops/ because that directory ships to the
server (scripts/ does not).

Wiring (PROD): a Task Scheduler task running, say, every 15 minutes:

    set ENVIRONMENT=PROD
    D:\\sydoc\\tools\\py\\python.exe D:\\sydoc\\nexora\\ops\\run_scheduled_reports.py --once

Flags:
    --once       process all currently-due schedules and exit (default)
    --dry-run    build each report and log what *would* be sent; no mail, no
                 NextRunAt advance
"""

import argparse
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nx_lib.db import engine_nexora_db
from nx_lib.mail import send_mail
from nx_lib.reporting.export import rows_to_csv, rows_to_xlsx
from nx_lib.reporting.runner import execute_definition
from nx_lib.reporting.schedule import compute_next_run, parse_recipients, utcnow
from nx_lib.security import load_permissions_for_user
from nx_main import app

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _safe_name(title):
    return re.sub(r'[\x00-\x1f\x7f";\\/]', "_", (title or "report").strip()) or "report"


def _due_schedules(conn, now):
    cur = conn.cursor()
    cur.execute(
        "SELECT s.ScheduleID, s.ReportID, s.OwnerUserID, s.Recipients, s.Format, "
        "       s.Frequency, s.Hour, s.Minute, s.Weekday, s.DayOfMonth, "
        "       r.Name, r.DefinitionJSON, u.username, u.locale "
        "FROM dbo.ReportSchedules s "
        "JOIN dbo.Reports r ON r.ReportID = s.ReportID "
        "JOIN dbo.Users u ON u.userID = s.OwnerUserID "
        "WHERE s.Enabled = 1 AND (s.NextRunAt IS NULL OR s.NextRunAt <= ?)",
        (now,),
    )
    return cur.fetchall()


def _process(conn, row, now, dry_run):
    perms = load_permissions_for_user(row.OwnerUserID)
    definition = json.loads(row.DefinitionJSON)
    columns, rows = execute_definition(
        definition, perms, row.OwnerUserID, row.username, row.locale or "en"
    )
    fmt = (row.Format or "xlsx").lower()
    if fmt == "csv":
        data, mime, ext = rows_to_csv(columns, rows), "text/csv", ".csv"
    else:
        data, mime, ext = (
            rows_to_xlsx(columns, rows, title=row.Name or "Report"),
            _XLSX_MIME,
            ".xlsx",
        )
    recipients = parse_recipients(row.Recipients)
    if dry_run:
        print(
            f"[dry-run] schedule {row.ScheduleID} '{row.Name}' -> {recipients} "
            f"({len(rows)} rows, {fmt})"
        )
        return
    subject = f"nexora report: {row.Name}"
    body = (
        f"<p>Attached is your scheduled report "
        f"<strong>{html.escape(row.Name or 'Report')}</strong> "
        f"({len(rows)} rows), generated {now:%Y-%m-%d %H:%M} UTC.</p>"
    )
    send_mail(recipients, subject, body, [(_safe_name(row.Name) + ext, data, mime)])
    nxt = compute_next_run(row.Frequency, row.Hour, row.Minute, row.Weekday, row.DayOfMonth, now)
    cur = conn.cursor()
    cur.execute(
        "UPDATE dbo.ReportSchedules SET LastRunAt = ?, NextRunAt = ?, "
        "UpdatedAt = SYSUTCDATETIME() WHERE ScheduleID = ?",
        (now, nxt, row.ScheduleID),
    )


def run_once(dry_run=False):
    now = utcnow()
    sent = failed = 0
    with app.app_context():
        conn = engine_nexora_db.raw_connection()
        try:
            due = _due_schedules(conn, now)
            for row in due:
                try:
                    _process(conn, row, now, dry_run)
                    conn.commit()
                    sent += 1
                except Exception as e:  # one bad schedule must not block the rest
                    conn.rollback()
                    failed += 1
                    app.logger.error(f"scheduled report {row.ScheduleID} failed: {e}")
                    print(f"[error] schedule {row.ScheduleID}: {e}")
        finally:
            conn.close()
    print(f"scheduled reports: {sent} sent, {failed} failed, {len(due)} due")
    return failed


def main():
    ap = argparse.ArgumentParser(description="Run due scheduled reports.")
    ap.add_argument("--once", action="store_true", help="process due schedules and exit (default)")
    ap.add_argument("--dry-run", action="store_true", help="build + log, do not email or advance")
    args = ap.parse_args()
    failed = run_once(dry_run=args.dry_run)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
