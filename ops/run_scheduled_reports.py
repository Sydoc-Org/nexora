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
from nx_lib.reporting.chart_render import render_chart_png
from nx_lib.reporting.export import rows_to_csv, rows_to_xlsx
from nx_lib.reporting.forecast import compute_forecast, forecast_export_rows
from nx_lib.reporting.runner import execute_definition
from nx_lib.reporting.schedule import (
    alert_trips,
    compute_next_run,
    parse_recipients,
    total_definition,
    utcnow,
)
from nx_lib.security import load_permissions_for_user
from nx_lib.views.reporting import invalidate_reporting_metrics, invalidate_reporting_sources
from nx_main import app

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _safe_name(title):
    return re.sub(r'[\x00-\x1f\x7f";\\/]', "_", (title or "report").strip()) or "report"


def _due_schedules(conn, now):
    cur = conn.cursor()
    cur.execute(
        "SELECT s.ScheduleID, s.ReportID, s.OwnerUserID, s.Recipients, s.Format, "
        "       s.Frequency, s.Hour, s.Minute, s.Weekday, s.DayOfMonth, "
        "       s.AlertOp, s.AlertThreshold, "
        "       r.Name, r.DefinitionJSON, u.username, u.locale "
        "FROM dbo.ReportSchedules s "
        "JOIN dbo.Reports r ON r.ReportID = s.ReportID "
        "JOIN dbo.Users u ON u.userID = s.OwnerUserID "
        "WHERE s.Enabled = 1 AND (s.NextRunAt IS NULL OR s.NextRunAt <= ?)",
        (now,),
    )
    return cur.fetchall()


def _advance(conn, row, now):
    """Record the run and move NextRunAt forward (shared by send and no-trip paths)."""
    nxt = compute_next_run(row.Frequency, row.Hour, row.Minute, row.Weekday, row.DayOfMonth, now)
    cur = conn.cursor()
    cur.execute(
        "UPDATE dbo.ReportSchedules SET LastRunAt = ?, NextRunAt = ?, "
        "UpdatedAt = SYSUTCDATETIME() WHERE ScheduleID = ?",
        (now, nxt, row.ScheduleID),
    )


def _alert_value(row, perms, definition, rows):
    """The number the alert condition checks: the grand total of the first metric
    (zero-column clone run as the owner — the Simple stat-card trick, correct
    for avg/count_distinct), or the row count for definitions without metrics."""
    td = total_definition(definition)
    if td is None:
        return len(rows)
    _cols, t_rows = execute_definition(td, perms, row.OwnerUserID, row.username, row.locale or "en")
    return t_rows[0][0] if t_rows and t_rows[0] else None


def _process(conn, row, now, dry_run):
    perms = load_permissions_for_user(row.OwnerUserID)
    definition = json.loads(row.DefinitionJSON)
    columns, rows = execute_definition(
        definition, perms, row.OwnerUserID, row.username, row.locale or "en"
    )
    if row.AlertOp:
        value = _alert_value(row, perms, definition, rows)
        if not alert_trips(row.AlertOp, row.AlertThreshold, value):
            if dry_run:
                print(
                    f"[dry-run] schedule {row.ScheduleID} '{row.Name}': alert "
                    f"{row.AlertOp} {row.AlertThreshold} not tripped (value={value}); no mail"
                )
                return None
            app.logger.info(
                f"schedule {row.ScheduleID}: alert not tripped (value={value}), mail skipped"
            )
            _advance(conn, row, now)
            return False
    png = None
    forecast = None
    fdef = definition.get("forecast") if isinstance(definition, dict) else None
    if isinstance(fdef, dict) and fdef.get("enabled"):
        try:
            fc = compute_forecast(definition, columns, rows)
            if fc and not fc.get("unavailable"):
                forecast = fc
        except Exception as e:
            app.logger.warning(f"schedule {row.ScheduleID}: forecast skipped: {e}")
    try:
        # The PNG must be rendered from the ORIGINAL columns/rows -- the
        # marker column added below would shift metric_idx.
        png = render_chart_png(definition, columns, rows, forecast=forecast)
    except Exception as e:  # the mail must go out even if the garnish fails
        app.logger.warning(f"schedule {row.ScheduleID}: chart render failed: {e}")
    forecast_start = None
    if forecast:
        try:
            columns, rows, forecast_start = forecast_export_rows(columns, rows, forecast)
        except Exception as e:
            app.logger.warning(f"schedule {row.ScheduleID}: forecast marking failed: {e}")
            forecast_start = None
    fmt = (row.Format or "xlsx").lower()
    if fmt == "csv":
        data, mime, ext = rows_to_csv(columns, rows), "text/csv", ".csv"
    else:
        data, mime, ext = (
            rows_to_xlsx(
                columns,
                rows,
                title=row.Name or "Report",
                chart_png=png,
                forecast_start=forecast_start,
            ),
            _XLSX_MIME,
            ".xlsx",
        )
    recipients = parse_recipients(row.Recipients)
    if dry_run:
        print(
            f"[dry-run] schedule {row.ScheduleID} '{row.Name}' -> {recipients} "
            f"({len(rows)} rows, {fmt}, chart={'yes' if png else 'no'})"
        )
        return None
    subject = f"nexora report: {row.Name}"
    body = (
        f"<p>Attached is your scheduled report "
        f"<strong>{html.escape(row.Name or 'Report')}</strong> "
        f"({len(rows)} rows), generated {now:%Y-%m-%d %H:%M} UTC.</p>"
    )
    inline = None
    if png:
        body += '<p><img src="cid:report-chart" alt="Report chart" style="max-width:640px"></p>'
        inline = [("report-chart", png, "image/png")]
    send_mail(
        recipients, subject, body, [(_safe_name(row.Name) + ext, data, mime)], inline_images=inline
    )
    _advance(conn, row, now)
    return True


def run_once(dry_run=False):
    now = utcnow()
    sent = failed = 0
    with app.app_context():
        # This is a fresh process each cron tick, so a stale 60s cache buys nothing here --
        # start from a guaranteed-fresh registry rather than trusting whatever a prior
        # in-process run (e.g. a long-lived test session reusing this module's `app`) cached.
        invalidate_reporting_sources()
        invalidate_reporting_metrics()
        conn = engine_nexora_db.raw_connection()
        due = []
        try:
            due = _due_schedules(conn, now)
            for row in due:
                try:
                    result = _process(conn, row, now, dry_run)
                    conn.commit()
                    if result:
                        sent += 1
                except Exception as e:  # one bad schedule must not block the rest
                    conn.rollback()
                    failed += 1
                    app.logger.error(f"scheduled report {row.ScheduleID} failed: {e}")
                    print(f"[error] schedule {row.ScheduleID}: {e}")
                    # Move on to the next slot anyway: a broken definition must
                    # not be retried (and error-logged) on every tick forever.
                    try:
                        _advance(conn, row, now)
                        conn.commit()
                    except Exception as e2:
                        conn.rollback()
                        app.logger.error(f"schedule {row.ScheduleID}: could not advance: {e2}")
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
