"""Reporting: scheduled report delivery routes (beautify-phase-2a, Task 3).

``/api/reporting/reports/<id>/schedules[/<sid>]`` (per-report CRUD, owner
gated via ``._is_report_owner`` from ``reports.py``) and
``/api/reporting/schedules`` (every schedule the caller owns, across all
reports -- feeds the Console 'Scheduled' screen). Split out of
``nx_lib/views/reporting/__init__.py`` — see that module's docstring for the
package's overall shape.
"""

from flask import current_app, jsonify, request, session
from flask_babel import gettext as _

from ...db import engine_nexora_db
from ...extensions import limiter
from ...reporting.schedule import compute_next_run, utcnow, validate_schedule
from ...security import require_permission
from .reports import _is_report_owner


def _serialize_schedule(r):
    return {
        "id": r.ScheduleID,
        "recipients": r.Recipients,
        "format": r.Format,
        "frequency": r.Frequency,
        "hour": r.Hour,
        "minute": r.Minute,
        "weekday": r.Weekday,
        "dayOfMonth": r.DayOfMonth,
        "enabled": bool(r.Enabled),
        "alertOp": r.AlertOp,
        "alertThreshold": r.AlertThreshold,
        "lastRunAt": str(r.LastRunAt) if r.LastRunAt else None,
        "nextRunAt": str(r.NextRunAt) if r.NextRunAt else None,
    }


def _schedule_fields(p):
    """Normalized (recipients, format, frequency, hour, minute, weekday, dom,
    enabled, next, alert_op, alert_threshold)."""
    freq = p.get("frequency")
    hour = int(p.get("hour"))
    minute = int(p.get("minute", 0))
    weekday = int(p["weekday"]) if freq == "weekly" else None
    dom = int(p["dayOfMonth"]) if freq == "monthly" else None
    enabled = 1 if p.get("enabled", True) else 0
    nxt = compute_next_run(freq, hour, minute, weekday, dom, utcnow())
    alert_op = p.get("alertOp") or None
    alert_threshold = float(p["alertThreshold"]) if alert_op else None
    return (
        p.get("recipients").strip(),
        (p.get("format") or "xlsx").lower(),
        freq,
        hour,
        minute,
        weekday,
        dom,
        enabled,
        nxt,
        alert_op,
        alert_threshold,
    )


@require_permission("reporting.schedule")
def api_reports_schedules_get(report_id):
    userid = session.get("userid")
    if not _is_report_owner(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT ScheduleID, Recipients, Format, Frequency, Hour, Minute, Weekday, "
            "DayOfMonth, Enabled, LastRunAt, NextRunAt, AlertOp, AlertThreshold "
            "FROM dbo.ReportSchedules "
            "WHERE ReportID = ? ORDER BY ScheduleID",
            (report_id,),
        )
        return jsonify([_serialize_schedule(r) for r in cur.fetchall()])
    except Exception as e:
        current_app.logger.error(f"reporting schedules list error: {e}")
        return jsonify({"error": _("Could not list schedules")}), 500
    finally:
        conn.close()


@require_permission("reporting.schedule")
@limiter.limit("60 per minute")
def api_reports_schedules_create(report_id):
    userid = session.get("userid")
    if not _is_report_owner(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    p = request.get_json(silent=True) or {}
    err = validate_schedule(p)
    if err:
        return jsonify({"error": err}), 400
    (recipients, fmt, freq, hour, minute, weekday, dom, enabled, nxt, alert_op, alert_thr) = (
        _schedule_fields(p)
    )
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.ReportSchedules "
            "(ReportID, OwnerUserID, Recipients, Format, Frequency, Hour, Minute, "
            " Weekday, DayOfMonth, Enabled, NextRunAt, AlertOp, AlertThreshold) "
            "OUTPUT INSERTED.ScheduleID VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                report_id,
                userid,
                recipients,
                fmt,
                freq,
                hour,
                minute,
                weekday,
                dom,
                enabled,
                nxt,
                alert_op,
                alert_thr,
            ),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({"id": new_id, "ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting schedules create error: {e}")
        return jsonify({"error": _("Could not save schedule")}), 500
    finally:
        conn.close()


@require_permission("reporting.schedule")
@limiter.limit("60 per minute")
def api_reports_schedules_update(report_id, schedule_id):
    userid = session.get("userid")
    if not _is_report_owner(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    p = request.get_json(silent=True) or {}
    err = validate_schedule(p)
    if err:
        return jsonify({"error": err}), 400
    (recipients, fmt, freq, hour, minute, weekday, dom, enabled, nxt, alert_op, alert_thr) = (
        _schedule_fields(p)
    )
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.ReportSchedules SET Recipients=?, Format=?, Frequency=?, Hour=?, "
            "Minute=?, Weekday=?, DayOfMonth=?, Enabled=?, NextRunAt=?, AlertOp=?, "
            "AlertThreshold=?, UpdatedAt=SYSUTCDATETIME() "
            "WHERE ScheduleID=? AND ReportID=?",
            (
                recipients,
                fmt,
                freq,
                hour,
                minute,
                weekday,
                dom,
                enabled,
                nxt,
                alert_op,
                alert_thr,
                schedule_id,
                report_id,
            ),
        )
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting schedules update error: {e}")
        return jsonify({"error": _("Could not update schedule")}), 500
    finally:
        conn.close()


@require_permission("reporting.schedule")
def api_reports_schedules_delete(report_id, schedule_id):
    userid = session.get("userid")
    if not _is_report_owner(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM dbo.ReportSchedules WHERE ScheduleID = ? AND ReportID = ?",
            (schedule_id, report_id),
        )
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting schedules delete error: {e}")
        return jsonify({"error": _("Could not delete schedule")}), 500
    finally:
        conn.close()


@require_permission("reporting.schedule")
def api_schedules_all():
    """Every schedule the caller owns, across all reports — feeds the
    Console 'Scheduled' screen. Owner-scoped like the per-report routes."""
    userid = session.get("userid")
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT s.ScheduleID, s.ReportID, r.Name AS ReportName, s.Recipients, "
            "s.Format, s.Frequency, s.Hour, s.Minute, s.Weekday, s.DayOfMonth, "
            "s.Enabled, s.LastRunAt, s.NextRunAt, s.AlertOp, s.AlertThreshold "
            "FROM dbo.ReportSchedules s "
            "JOIN dbo.Reports r ON r.ReportID = s.ReportID "
            "WHERE r.OwnerUserID = ? "
            "ORDER BY s.NextRunAt, s.ScheduleID",
            (userid,),
        )
        out = []
        for r in cur.fetchall():
            d = _serialize_schedule(r)
            d["reportId"] = r.ReportID
            d["reportName"] = r.ReportName
            out.append(d)
        return jsonify(out)
    except Exception as e:
        current_app.logger.error(f"reporting schedules overview error: {e}")
        return jsonify({"error": _("Could not list schedules")}), 500
    finally:
        conn.close()


def register_routes(app):
    app.add_url_rule(
        "/api/reporting/schedules",
        endpoint="reporting_schedules_all",
        view_func=api_schedules_all,
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/schedules",
        endpoint="reporting_reports_schedules_get",
        view_func=api_reports_schedules_get,
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/schedules",
        endpoint="reporting_reports_schedules_create",
        view_func=api_reports_schedules_create,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/schedules/<int:schedule_id>",
        endpoint="reporting_reports_schedules_update",
        view_func=api_reports_schedules_update,
        methods=["PUT"],
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/schedules/<int:schedule_id>",
        endpoint="reporting_reports_schedules_delete",
        view_func=api_reports_schedules_delete,
        methods=["DELETE"],
    )
