"""Admin logs: search + CSV export."""

import csv
import io as _io
import math
from datetime import datetime

from flask import Response, current_app, jsonify, render_template, request, session
from flask_babel import gettext as _

from ...db import engine_nexora_db
from ...security import page_visibility, require_permission


@require_permission("admin.view.system.logs")
def admin_logs_view():
    organizations = []
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("select organizationcode, organization from organizations")
        organizations = [
            dict(zip([column[0] for column in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
    except Exception as e:
        current_app.logger.error(f"Failed to load organizations for logs page: {e}")
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass
    return render_template(
        "admin/logs.html",
        organizations=organizations,
        logged_in_user=session.get("username"),
        userid=session.get("userid"),
        page_visibility=page_visibility(),
    )


def _build_logs_where_clause():
    """Pull filter args from request and produce (where_clause, params).
    Shared between /api/admin/logs/search and /api/admin/logs/export.csv."""
    username = request.args.get("username", "").strip()
    method = request.args.get("method", "").strip()
    path = request.args.get("path", "").strip()
    status = request.args.get("status", "").strip()
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    organization = request.args.get("organization", "").strip()

    parts = ["1=1"]
    params = []

    if username:
        parts.append("Username LIKE ?")
        params.append(f"%{username}%")
    if method:
        parts.append("HttpRequestMethod = ?")
        params.append(method)
    if path:
        parts.append("Path LIKE ?")
        params.append(f"%{path}%")
    if status == "SUCCESS":
        parts.append("HttpResponseCode BETWEEN 200 AND 299")
    elif status == "FAILURE":
        parts.append("HttpResponseCode >= 400")
    if start_date:
        parts.append("Timestamp >= ?")
        params.append(start_date)
    if end_date:
        parts.append("Timestamp <= ?")
        # Day-granularity filters (e.g. "Today", "Last 7 days") send a bare
        # "YYYY-MM-DD" date and rely on us rounding up to end-of-day. Sub-day
        # presets (e.g. "Last hour") send a full "YYYY-MM-DD HH:MM:SS"
        # timestamp already — don't append another time onto it.
        end_bound = end_date if " " in end_date else f"{end_date} 23:59:59"
        params.append(end_bound)
    if organization:
        parts.append("Username IN (SELECT username FROM Users WHERE organizationcode = ?)")
        params.append(organization)

    return " AND ".join(parts), params


@require_permission("admin.view.system.logs")
def api_admin_logs_search():
    page = request.args.get("page", 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page

    where_clause, params = _build_logs_where_clause()

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(f"SELECT COUNT(*) FROM Logs WHERE {where_clause}", params)
        count_row = cursor.fetchone()
        assert count_row is not None  # SELECT COUNT(*) always returns exactly one row
        total_count = count_row[0]

        sql = f"""
            SELECT LogID, Timestamp, Username, HttpRequestMethod, Path,
                   HttpResponseCode, Args, RequestIpAddress, durationSeconds
            FROM Logs
            WHERE {where_clause}
            ORDER BY Timestamp DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """
        cursor.execute(sql, [*params, offset, per_page])

        logs = []
        for row in cursor.fetchall():
            logs.append(
                {
                    "LogID": row.LogID,
                    # Emit ISO-8601 explicitly so the client can pass it straight
                    # to `new Date(...)`. Flask's default JSON encoder uses RFC 1123
                    # which doesn't survive the +'Z' timezone-suffix hack.
                    "Timestamp": row.Timestamp.isoformat()
                    if hasattr(row.Timestamp, "isoformat")
                    else row.Timestamp,
                    "Username": row.Username,
                    "HttpRequestMethod": row.HttpRequestMethod,
                    "Path": row.Path,
                    "HttpResponseCode": row.HttpResponseCode,
                    "Args": row.Args,
                    "RequestIpAddress": row.RequestIpAddress,
                    "durationSeconds": row.durationSeconds,
                }
            )

        return jsonify(
            {
                "logs": logs,
                "total": total_count,
                "page": page,
                "pages": math.ceil(total_count / per_page),
            }
        )
    except Exception as e:
        current_app.logger.error(f"Log search error: {e}")
        return jsonify({"error": _("An unexpected error occurred")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.system.logs")
def api_admin_logs_export():
    """Stream the filtered log set as CSV. Capped at 50k rows so a wide-open
    filter doesn't yank the whole table."""
    max_rows = 50000
    where_clause, params = _build_logs_where_clause()

    sql = f"""
        SELECT TOP ({max_rows}) LogID, Timestamp, Username, HttpRequestMethod, Path,
               HttpResponseCode, RequestIpAddress, durationSeconds, Args
        FROM Logs
        WHERE {where_clause}
        ORDER BY Timestamp DESC
    """

    def generate():
        buf = _io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(
            [
                "LogID",
                "Timestamp",
                "Username",
                "Method",
                "Path",
                "StatusCode",
                "IPAddress",
                "DurationSeconds",
                "Args",
            ]
        )
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

        conn = engine_nexora_db.raw_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            while True:
                rows = cursor.fetchmany(500)
                if not rows:
                    break
                for row in rows:
                    ts = row.Timestamp
                    if ts is None:
                        ts_iso = ""
                    elif hasattr(ts, "isoformat"):
                        ts_iso = ts.isoformat()
                    else:
                        ts_iso = str(ts).replace(" ", "T", 1)
                    writer.writerow(
                        [
                            row.LogID,
                            ts_iso,
                            row.Username or "",
                            row.HttpRequestMethod or "",
                            row.Path or "",
                            row.HttpResponseCode if row.HttpResponseCode is not None else "",
                            row.RequestIpAddress or "",
                            row.durationSeconds if row.durationSeconds is not None else "",
                            row.Args or "",
                        ]
                    )
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate(0)
            cursor.close()
        finally:
            conn.close()

    filename = f"nexora-logs-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    return Response(
        generate(),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


def register_routes(app):
    app.add_url_rule("/admin/logs", endpoint="admin_logs_view", view_func=admin_logs_view)
    app.add_url_rule(
        "/api/admin/logs/search", endpoint="api_admin_logs_search", view_func=api_admin_logs_search
    )
    app.add_url_rule(
        "/api/admin/logs/export.csv",
        endpoint="api_admin_logs_export",
        view_func=api_admin_logs_export,
    )
