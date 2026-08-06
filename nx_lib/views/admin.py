"""Admin pages: overview, organizations, maintenance banners, logs, sessions,
user CRUD, access control, permissions."""

import csv
import math
import os
import secrets
import subprocess
from contextlib import suppress
from datetime import datetime

import bcrypt
import pyodbc
from flask import (
    Response,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_babel import gettext as _
from werkzeug.exceptions import HTTPException

from .. import status
from ..config import IS_PROD, REPO_ROOT
from ..db import (
    engine_generali_db,
    engine_ms02_docfields_pg,
    engine_ms02_pg,
    engine_ms02_stats_pg,
    engine_nexora_db,
    engine_octo_db,
    engine_statistics_db,
    ping_dbs_parallel,
)
from ..maintenance import (
    _MAINTENANCE_BLOCK_CACHE,
    _get_blocking_maintenance,
    _maintenance_parse_payload,
    _maintenance_row_to_dict,
)
from ..security import (
    _revoke_session_by_id,
    has_permission,
    load_permissions_for_user,
    page_visibility,
    require_permission,
)

# ----------------------------------- overview ---------------------------------- #


@require_permission("admin.view")
def admin_dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    user_count = 0
    org_count = 0
    active_sessions_count = None
    failed_logins_today = None

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM Users")
        row = cursor.fetchone()
        if row:
            user_count = row[0]

        cursor.execute("SELECT COUNT(*) FROM organizations")
        row = cursor.fetchone()
        if row:
            org_count = row[0]

        cursor.execute("""
            SELECT COUNT(*) FROM ActiveSessions
            WHERE LastSeenAt >= DATEADD(minute, -30, GETDATE())
        """)
        row = cursor.fetchone()
        if row:
            active_sessions_count = row[0]

        cursor.execute("""
            SELECT COUNT(*) FROM Logs
            WHERE Path IN ('/login', '/verify_2fa')
              AND HttpRequestMethod = 'POST'
              AND HttpResponseCode >= 400
              AND Timestamp >= CAST(GETDATE() AS DATE)
        """)
        row = cursor.fetchone()
        if row:
            failed_logins_today = row[0]
    except Exception as e:
        current_app.logger.error(f"Failed to load admin overview counts: {e}")
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

    db_health = ping_dbs_parallel(
        [
            (engine_nexora_db, "Nexora"),
            (engine_octo_db, "Octo"),
            (engine_statistics_db, "Stats"),
            (engine_generali_db, "Generali"),
            *([(engine_ms02_pg, "MS02 (PG)")] if engine_ms02_pg is not None else []),
            *(
                [(engine_ms02_stats_pg, "MS02 stats (PG)")]
                if engine_ms02_stats_pg is not None
                else []
            ),
            *(
                [(engine_ms02_docfields_pg, "MS02 docfields (PG)")]
                if engine_ms02_docfields_pg is not None
                else []
            ),
        ],
        timeout_s=0.8,
    )

    return render_template(
        "admin/admin_overview.html",
        user_count=user_count,
        org_count=org_count,
        active_sessions_count=active_sessions_count,
        failed_logins_today=failed_logins_today,
        db_health=db_health,
        current_env=os.environ.get("ENVIRONMENT", "?"),
        logged_in_user=session.get("username"),
        userid=session.get("userid"),
        pageV=page_visibility(),
    )


# ----------------------------------- organizations ---------------------------------- #


@require_permission("admin.view.organizations")
def admin_organizations_view():
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

        return render_template(
            "admin/organizations.html",
            organizations=organizations,
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            pageV=page_visibility(),
        )
    except Exception as e:
        current_app.logger.error(f"Failed to fetch organizations: {e}")
        return render_template("500.html")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.add.organization")
def admin_add_organization():
    import re as _re

    data = request.get_json()
    organization = data.get("organizationname")

    if not organization:
        return jsonify({"success": False, "message": _("All fields are required.")}), 400

    clean_name = _re.sub(r"[^A-Z0-9]", "", organization.upper())
    consonants = _re.sub(r"[AEIOU]", "", clean_name)
    vowels = _re.sub(r"[^AEIOU]", "", clean_name)
    code = consonants + vowels
    organizationcode = code[:4].ljust(4, "X")

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO organizations VALUES(?,?)", (organizationcode, organization))
        conn.commit()
        return jsonify({"success": True, "message": _("Organization created successfully.")})
    except pyodbc.IntegrityError:
        return jsonify({"success": False, "message": _("Organization already exists.")}), 409
    except Exception as e:
        current_app.logger.error(f"Error adding organization: {e}")
        return jsonify({"success": False, "message": _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.edit.organization")
def admin_edit_organization(organizationcode):
    data = request.get_json()
    organization = data.get("organizationname")
    current_user_id = session["userid"]

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE organizations SET organization=? WHERE organizationcode=?",
            (organization, organizationcode),
        )
        conn.commit()
        return jsonify({"success": True, "message": _("Organization updated successfully.")})
    except Exception as e:
        current_app.logger.error(f"Error editing Organization {current_user_id}: {e}")
        return jsonify({"success": False, "message": _("An error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.delete.organization")
def admin_delete_organization(organizationcode):
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM organizations WHERE organizationcode=?", (organizationcode,))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": _("Organization not found.")}), 404

        return jsonify({"success": True, "message": _("Organization deleted successfully.")})
    except Exception as e:
        current_app.logger.error(f"Error deleting Organization {organizationcode}: {e}")
        return jsonify({"success": False, "message": _("An error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.organizations")
def api_admin_organizations_list():
    if "username" not in session:
        return jsonify({"error": "Not authorized"}), 401
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT organizationcode, organization FROM organizations ORDER BY organization"
        )
        orgs = [
            dict(zip([c[0] for c in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        return jsonify(orgs)
    except Exception as e:
        current_app.logger.error(f"Failed to fetch organizations list: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ----------------------------------- status page ---------------------------------- #


@require_permission("admin.status.view")
def admin_status_view():
    """Component health + incident history, as recorded by ops/outage_monitor.py.

    Deliberately reads only what the monitor persisted (issue #167) instead of
    probing on page load: the point of the page is "what has been true since
    yesterday evening", which a request-scoped ping cannot answer. When the
    monitor has not reported recently the page says so rather than rendering a
    reassuring all-green grid from stale rows.
    """
    try:
        data = status.load_status(
            engine_nexora_db,
            maintenance=_get_blocking_maintenance() is not None,
        )
    except Exception as e:
        current_app.logger.error(f"Failed to load status page data: {e}")
        return render_template("handlers/500.html"), 500
    return render_template(
        "admin/status.html",
        status=data,
        stale_after_min=status.DEFAULT_STALE_AFTER_S // 60,
        logged_in_user=session.get("username"),
        userid=session.get("userid"),
        pageV=page_visibility(),
    )


# ----------------------------------- dev server restart ---------------------------------- #


_SWITCHABLE_ENVS = {"INT", "STAGING"}


@require_permission("admin.restart")
def api_admin_restart():
    """Restart the local dev server process (issue #184). Dev-only — 404s on PROD
    since PROD is IIS-hosted and restarting there means recycling the app pool,
    not killing a `python nx_main.py` process. Fires bin/nx.ps1 -r as a hidden
    background process; it kills this process and starts a fresh one, so the response has
    to make it back to the browser before that happens (nx.ps1 sleeps ~1s first).

    Optional JSON body {"env": "INT"|"STAGING"} switches ENVIRONMENT on the way
    back up (issue #187) via nx.ps1's existing --env: flag — PROD is refused by
    nx.ps1 itself, so no need to re-check it here."""
    if IS_PROD:
        abort(404)
    target_env = (request.get_json(silent=True) or {}).get("env")
    if target_env is not None and target_env not in _SWITCHABLE_ENVS:
        return jsonify({"success": False, "message": _("Unknown environment.")}), 400
    args = ["pwsh", "-File", str(REPO_ROOT / "bin" / "nx.ps1"), "-r"]
    if target_env:
        args.append(f"--env:{target_env}")
    subprocess.Popen(
        args,
        cwd=str(REPO_ROOT),
        # CREATE_NO_WINDOW, not DETACHED_PROCESS: pwsh exits 0 without running
        # the script when it has no console at all (#187); a hidden console
        # works and still survives this process being killed by nx.ps1.
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    return jsonify({"success": True})


# ----------------------------------- maintenance banner ---------------------------------- #


@require_permission("admin.maintenance.view")
def admin_maintenance_view():
    try:
        return render_template(
            "admin/maintenance.html",
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            pageV=page_visibility(),
        )
    except Exception as e:
        current_app.logger.error(f"Failed to load maintenance page: {e}")
        return render_template("handlers/500.html"), 500


@require_permission("admin.maintenance.view")
def api_admin_maintenance_list():
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ID, Title, Message, StartAt, EndAt, Severity, Active, BlockAccess, AnnounceMinutesBefore, CreatedBy, CreatedAt
            FROM MaintenanceBanner
            ORDER BY StartAt DESC, ID DESC
        """)
        cols = [c[0] for c in cursor.description]
        records = [_maintenance_row_to_dict(row, cols) for row in cursor.fetchall()]
        return jsonify({"success": True, "records": records})
    except Exception as e:
        current_app.logger.error(f"Maintenance list error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@require_permission("admin.maintenance.edit")
def api_admin_maintenance_add():
    body = request.get_json(force=True) or {}
    parsed, err = _maintenance_parse_payload(body)
    if err:
        return jsonify({"success": False, "error": err[0]}), err[1]

    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO MaintenanceBanner (Title, Message, StartAt, EndAt, Severity, Active, BlockAccess, AnnounceMinutesBefore, CreatedBy, CreatedAt)
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
        """,
            [
                parsed["title"],
                parsed["message"],
                parsed["start_at"],
                parsed["end_at"],
                parsed["severity"],
                parsed["active"],
                parsed["block_access"],
                parsed["announce_minutes"],
                session.get("userid"),
            ],
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        _MAINTENANCE_BLOCK_CACHE["expires_at"] = 0.0
        return jsonify({"success": True, "id": int(new_id)})
    except Exception as e:
        current_app.logger.error(f"Maintenance add error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@require_permission("admin.maintenance.edit")
def api_admin_maintenance_edit(banner_id):
    body = request.get_json(force=True) or {}
    parsed, err = _maintenance_parse_payload(body)
    if err:
        return jsonify({"success": False, "error": err[0]}), err[1]

    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE MaintenanceBanner
               SET Title = ?, Message = ?, StartAt = ?, EndAt = ?, Severity = ?,
                   Active = ?, BlockAccess = ?, AnnounceMinutesBefore = ?
             WHERE ID = ?
        """,
            [
                parsed["title"],
                parsed["message"],
                parsed["start_at"],
                parsed["end_at"],
                parsed["severity"],
                parsed["active"],
                parsed["block_access"],
                parsed["announce_minutes"],
                banner_id,
            ],
        )
        if cursor.rowcount == 0:
            return jsonify({"success": False, "error": "Banner not found"}), 404
        conn.commit()
        _MAINTENANCE_BLOCK_CACHE["expires_at"] = 0.0
        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Maintenance edit error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@require_permission("admin.maintenance.edit")
def api_admin_maintenance_delete(banner_id):
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM MaintenanceBanner WHERE ID = ?", [banner_id])
        if cursor.rowcount == 0:
            return jsonify({"success": False, "error": "Banner not found"}), 404
        conn.commit()
        _MAINTENANCE_BLOCK_CACHE["expires_at"] = 0.0
        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Maintenance delete error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


# ----------------------------------- logs ---------------------------------- #


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
        pageV=page_visibility(),
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
        total_count = cursor.fetchone()[0]

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
        return jsonify({"error": str(e)}), 500
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
        import io as _io

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


# ----------------------------------- sessions & users ---------------------------------- #


@require_permission("admin.view.active.sessions")
def admin_sessions_view():
    return render_template(
        "admin/sessions.html",
        logged_in_user=session.get("username"),
        userid=session.get("userid"),
        pageV=page_visibility(),
    )


@require_permission("admin.create.user")
def admin_add_user():
    from .auth import _build_reset_email_message, send_reset_email

    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    fullname = data.get("fullname")
    email = data.get("email")
    organization = data.get("organization")
    accessprofile = data.get("accessprofile")
    # Checkbox: an unticked box is simply absent from the posted form.
    send_invite = bool(data.get("send_invite"))

    if send_invite:
        # Nobody -- not the admin, not the mail -- ever sees this one. It is a
        # placeholder that keeps the account unusable until the invited user
        # sets their own password through the emailed link.
        password = secrets.token_urlsafe(32)

    if not all([username, password, fullname, email, organization, accessprofile]):
        return jsonify({"success": False, "message": _("All fields are required.")}), 400

    if not has_permission(f"admin.assign.user.accessprofile.{str(accessprofile).lower()}"):
        current_app.logger.error(
            "assign-permission denied: profile=%r username=%r",
            str(accessprofile)[:100],
            str(username)[:100],
        )
        return jsonify({"success": False, "message": _("Permission Denied for this action.")}), 403

    hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("select accessid from accessprofile where name = ?", accessprofile)
        accessid = cursor.fetchone()[0]
        cursor.execute(
            "select organizationcode from organizations where organization = ?", organization
        )
        organizationcode = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO Users (username, password, fullname, email, organizationcode, accessid, InitReset) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                username,
                hashed_password,
                fullname,
                email,
                organizationcode,
                accessid,
                # An invited user picks their own password through the emailed
                # link, so the forced first-login change (InitReset NULL) would
                # only make them do it twice. They still land on 2FA enrolment.
                1 if send_invite else None,
            ),
        )
        conn.commit()

        if send_invite:
            # Synchronous on purpose: the admin needs to know whether the mail
            # actually went out. No timing oracle to dodge here (unlike the
            # self-service reset), and Graph is capped at 10s per call.
            try:
                sent = send_reset_email(
                    email, message=_build_reset_email_message(email, invite=True)
                )
            except Exception as e:
                current_app.logger.error(f"Failed to send invite email to {email}: {e}")
                sent = False
            if not sent:
                return jsonify(
                    {
                        "success": True,
                        "message": _(
                            "User created, but the email could not be sent. "
                            "Ask them to use 'Forgot password'."
                        ),
                    }
                )
            return jsonify({"success": True, "message": _("User created and email sent.")})

        return jsonify({"success": True, "message": _("User created successfully.")})
    except pyodbc.IntegrityError:
        return jsonify({"success": False, "message": _("Username or email already exists.")}), 409
    except Exception as e:
        current_app.logger.error(f"Error adding user: {e}")
        return jsonify({"success": False, "message": _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.edit.user")
def admin_edit_user(user_id):
    data = request.get_json()
    username = data.get("username")
    fullname = data.get("fullname")
    email = data.get("email")
    password = data.get("password")
    organization = data.get("organization")
    accessprofile = data.get("accessprofile")

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        # The <select> only ever lists this admin's own assignable profiles
        # (see admin_user_detail). If the edited user's CURRENT profile isn't
        # in that set, the template still renders it as a selected-but-
        # unassignable option so an untouched form round-trips the same
        # value. Only require the assign-permission when the value actually
        # CHANGES — leaving it alone must never 403 or silently reassign it.
        cursor.execute(
            "select ap.name from users u left join accessprofile ap on u.accessid = ap.accessid where u.userid = ?",
            user_id,
        )
        row = cursor.fetchone()
        current_profile = row[0] if row else None

        # Defense-in-depth: the template always submits SOME accessprofile
        # value now (the current one, if the admin never touched the
        # dropdown -- see user_detail.html). A client that still omits the
        # key entirely (JSON body with no "accessprofile", not the normal
        # browser path) must be treated as "leave it unchanged", not as
        # "clear the profile" -- the latter would 403 an admin trying to
        # save an unrelated field.
        if accessprofile is None:
            accessprofile = current_profile

        if accessprofile != current_profile and not has_permission(
            f"admin.assign.user.accessprofile.{str(accessprofile).lower()}"
        ):
            current_app.logger.error(
                f"User does not have Permission: admin.assign.user.accessprofile.{str(accessprofile).lower()} for {user_id}"
            )
            return jsonify(
                {"success": False, "message": _("Permission Denied for this action.")}
            ), 403

        cursor.execute("select accessid from accessprofile where name = ?", accessprofile)
        accessid = cursor.fetchone()[0]
        cursor.execute(
            "select organizationcode from organizations where organization = ?", organization
        )
        organizationcode = cursor.fetchone()[0]

        if password:
            hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
                "utf-8"
            )
            cursor.execute(
                "UPDATE Users SET username=?, fullname=?, email=?, password=?, organizationcode=?,accessid=? WHERE userID=?",
                (username, fullname, email, hashed_password, organizationcode, accessid, user_id),
            )
        else:
            cursor.execute(
                "UPDATE Users SET username=?, fullname=?, email=?,  organizationcode=?,accessid=? WHERE userID=?",
                (username, fullname, email, organizationcode, accessid, user_id),
            )
        conn.commit()

        return jsonify({"success": True, "message": _("User updated successfully.")})
    except Exception as e:
        current_app.logger.error(f"Error editing user {user_id}: {e}")
        return jsonify({"success": False, "message": _("An error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.accessprofiles.useroverrides")
def admin_user_detail(user_id):
    if "username" not in session:
        return redirect(url_for("login"))

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT u.userID, u.username, u.fullname, u.email,
                   ap.Name AS AccessProfileName,
                   o.organization, o.organizationcode
            FROM Users u
            LEFT JOIN AccessProfile ap ON u.accessid = ap.AccessID
            LEFT JOIN Organizations o ON u.organizationcode = o.organizationcode
            WHERE u.userID = ?
        """,
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            abort(404)
        user = dict(zip([c[0] for c in cursor.description], row, strict=False))

        cursor.execute(
            "SELECT organizationcode, organization FROM Organizations ORDER BY organization"
        )
        organizations = [
            dict(zip([c[0] for c in cursor.description], r, strict=False))
            for r in cursor.fetchall()
        ]

        cursor.execute(
            "SELECT ap.name profile, ap.accessid accessid FROM AccessProfile ap ORDER BY ap.name"
        )
        all_ap = [
            dict(zip([c[0] for c in cursor.description], r, strict=False))
            for r in cursor.fetchall()
        ]
        assignable_profiles = [
            ap
            for ap in all_ap
            if has_permission(f'admin.assign.user.accessprofile.{str(ap["profile"]).lower()}')
        ]

        cursor.execute("""
            SELECT PermissionID, Code, Description FROM Permission
            ORDER BY
                LEFT(Code, LEN(Code) - CHARINDEX('.', REVERSE(Code))),
                CASE
                    WHEN Code LIKE '%.view'    THEN 1
                    WHEN Code LIKE '%.add'     THEN 2
                    WHEN Code LIKE '%.add.%'   THEN 3
                    WHEN Code LIKE '%.edit%'   THEN 4
                    WHEN Code LIKE '%.delete%' THEN 5
                    ELSE 6
                END,
                Code
        """)
        all_permissions = [
            dict(zip([c[0] for c in cursor.description], r, strict=False))
            for r in cursor.fetchall()
        ]

        return render_template(
            "admin/user_detail.html",
            user=user,
            organizations=organizations,
            assignable_profiles=assignable_profiles,
            all_permissions=all_permissions,
            can_edit_user=has_permission("admin.edit.user"),
            can_delete_user=has_permission("admin.delete.user"),
            can_edit_overrides=has_permission("admin.edit.user.override"),
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            pageV=page_visibility(),
        )
    except HTTPException:
        raise
    except Exception as e:
        current_app.logger.error(f"Error loading user detail {user_id}: {e}")
        return render_template("500.html")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.accessprofiles.useroverrides")
def api_admin_user_activity(user_id):
    """Recent log entries for one user. Last 7 days, paginated, 25 per page."""
    page = request.args.get("page", 1, type=int)
    per_page = 25
    offset = max(0, (page - 1) * per_page)

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT username FROM Users WHERE userID = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"entries": [], "total": 0, "page": page, "pages": 0})
        username = row[0]

        cursor.execute(
            """
            SELECT COUNT(*) FROM Logs
            WHERE Username = ?
              AND Timestamp >= DATEADD(day, -7, GETDATE())
        """,
            (username,),
        )
        total = (cursor.fetchone() or [0])[0] or 0

        cursor.execute(
            """
            SELECT Timestamp, HttpRequestMethod, Path, HttpResponseCode
            FROM Logs
            WHERE Username = ?
              AND Timestamp >= DATEADD(day, -7, GETDATE())
            ORDER BY Timestamp DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """,
            (username, offset, per_page),
        )

        entries = []
        for r in cursor.fetchall():
            ts = r.Timestamp
            if ts is None:
                ts_iso = None
            elif hasattr(ts, "isoformat"):
                ts_iso = ts.isoformat()
            else:
                ts_iso = str(ts).replace(" ", "T", 1)
            entries.append(
                {
                    "Timestamp": ts_iso,
                    "HttpRequestMethod": r.HttpRequestMethod,
                    "Path": r.Path,
                    "HttpResponseCode": r.HttpResponseCode,
                }
            )

        pages = max(1, math.ceil(total / per_page)) if total else 0

        return jsonify(
            {
                "entries": entries,
                "total": int(total),
                "page": page,
                "pages": pages,
            }
        )
    except Exception as e:
        current_app.logger.error(f"Failed to load activity for user {user_id}: {e}")
        return jsonify({"error": str(e), "entries": [], "total": 0, "page": page, "pages": 0}), 500
    finally:
        if cursor:
            with suppress(Exception):
                cursor.close()
        if conn:
            with suppress(Exception):
                conn.close()


@require_permission("admin.delete.user")
def admin_delete_user(user_id):
    current_user = session.get("userid")
    if str(user_id) == current_user:
        return jsonify({"success": False, "message": _("You cannot delete your own account.")}), 403

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        # Every child-row delete and the final Users delete run in ONE
        # transaction committed exactly once at the end. NexoraDB's FKs to
        # dbo.Users are all NO ACTION (no DB-level cascade), so the child rows
        # must be removed first. The previous code committed each child delete
        # individually, so any later failure — including the Users delete
        # itself — left a half-deleted, undeletable user. Ordering only
        # requires that every child delete precede `delete from users`.
        cursor.execute("delete from userpermissionoverride where userid = ?", (user_id,))

        # Reporting artifacts. FK_Reports_Users / FK_ReportSchedules_Users /
        # FK_ReportShares_Users are all NO ACTION and were previously omitted,
        # so deleting a report-owning user failed outright on the Users delete.
        # Remove, in FK-safe order: the shares the user holds and the schedules
        # they own; then any shares/schedules that reference reports the user
        # OWNS (regardless of who holds/owns them); then the reports; then the
        # Users row. Deleting the shares and schedules explicitly keeps this
        # correct even though FK_ReportShares_Reports / FK_ReportSchedules_
        # Reports are ON DELETE CASCADE — it does not rely on the DB cascade.
        cursor.execute("delete from ReportShares where SharedWithUserID = ?", (user_id,))
        cursor.execute(
            "delete from ReportShares where ReportID in "
            "(select ReportID from Reports where OwnerUserID = ?)",
            (user_id,),
        )
        cursor.execute("delete from ReportSchedules where OwnerUserID = ?", (user_id,))
        cursor.execute(
            "delete from ReportSchedules where ReportID in "
            "(select ReportID from Reports where OwnerUserID = ?)",
            (user_id,),
        )
        cursor.execute("delete from Reports where OwnerUserID = ?", (user_id,))

        cursor.execute("delete from users where userid = ?", (user_id,))
        deleted = cursor.rowcount

        conn.commit()

        if deleted == 0:
            return jsonify({"success": False, "message": _("User not found.")}), 404

        return jsonify({"success": True, "message": _("User deleted successfully.")})
    except Exception as e:
        if conn is not None:
            with suppress(Exception):
                conn.rollback()
        current_app.logger.error(f"Error deleting user {user_id}: {e}")
        return jsonify({"success": False, "message": _("An error occurred.")}), 500
    finally:
        if cursor:
            with suppress(Exception):
                cursor.close()
        if conn:
            with suppress(Exception):
                conn.close()


@require_permission("admin.edit.user.override")
def admin_revoke_session(session_id):
    try:
        _revoke_session_by_id(session_id)
        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Failed to revoke session {session_id}: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@require_permission("admin.edit.user.override")
def admin_revoke_all_sessions(user_id):
    sids = []
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT SessionID FROM ActiveSessions WHERE UserID = ?", (user_id,))
        sids = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        current_app.logger.error(f"Failed to list sessions for user {user_id}: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            with suppress(Exception):
                cursor.close()
        if conn:
            with suppress(Exception):
                conn.close()

    revoked = 0
    for sid in sids:
        try:
            if _revoke_session_by_id(sid):
                revoked += 1
        except Exception as e:
            current_app.logger.warning(f"Revoke failed for session {sid}: {e}")

    current_app.logger.info(
        f"Admin {session.get('username')} revoked {revoked} session(s) for user {user_id}"
    )
    return jsonify({"success": True, "revoked": revoked})


@require_permission("admin.view.users")
def api_admin_users_list():
    if "username" not in session:
        return jsonify({"error": "Not authorized"}), 401
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT userID, username, fullname, email, ap.name accessprofile, o.organization organization
            FROM Users u
            JOIN accessprofile ap ON ap.accessid = u.accessid
            JOIN organizations o ON o.organizationcode = u.organizationcode
            ORDER BY username
        """)
        users = [
            dict(zip([c[0] for c in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        return jsonify(users)
    except Exception as e:
        current_app.logger.error(f"Failed to fetch users list: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.active.sessions")
def admin_recent_logs():
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 20 Timestamp, Username, HttpRequestMethod, Path, HttpResponseCode
            FROM Logs
            ORDER BY Timestamp DESC
        """)
        logs = []
        for row in cursor.fetchall():
            # HttpResponseCode is NVARCHAR in the DB; coerce defensively rather
            # than compare a string against int bounds (guaranteed TypeError).
            try:
                status_code = int(row.HttpResponseCode)
            except (TypeError, ValueError):
                status_code = None
            logs.append(
                {
                    # Emit ISO-8601 explicitly so the client can pass it straight
                    # to `new Date(...)`. Flask's default JSON encoder uses RFC 1123
                    # which doesn't survive the +'Z' timezone-suffix hack.
                    "Timestamp": row.Timestamp.isoformat()
                    if hasattr(row.Timestamp, "isoformat")
                    else row.Timestamp,
                    "Username": row.Username,
                    "ActionType": f"{row.HttpRequestMethod} {row.Path}",
                    "ActionStatus": "SUCCESS"
                    if status_code is not None and 200 <= status_code < 300
                    else "FAILURE",
                }
            )
        return jsonify(logs)
    except Exception as e:
        current_app.logger.error(f"Failed to fetch recent logs: {e}")
        return jsonify({"error": _("Could not fetch logs")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("admin.view.active.sessions")
def admin_active_sessions():
    """Read currently-active sessions from ActiveSessions, joined to Users.
    Filtered to LastSeenAt (bumped on every request by _enforce_active_session)
    so this reflects actual recent activity, not just login time (issue #109)."""
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                a.SessionID,
                a.UserID    AS Userid,
                u.username  AS Username,
                a.IPAddress,
                a.CreatedAt AS LoggedInAt
            FROM ActiveSessions a
            LEFT JOIN Users u ON u.userID = a.UserID
            WHERE a.LastSeenAt >= DATEADD(minute, -30, GETDATE())
            ORDER BY a.CreatedAt DESC
        """)
        sessions = []
        for r in cursor.fetchall():
            sessions.append(
                {
                    "SessionID": r[0],
                    "Userid": r[1],
                    "Username": r[2],
                    "IPAddress": r[3],
                    # Emit ISO-8601 explicitly so the client can pass it straight
                    # to `new Date(...)`. Flask's default JSON encoder uses RFC 1123
                    # which doesn't survive the +'Z' timezone-suffix hack.
                    "LoggedInAt": r[4].isoformat() if r[4] else None,
                }
            )
        return jsonify(sessions)
    except Exception as e:
        current_app.logger.error(f"Failed to fetch active sessions: {e}")
        return jsonify({"error": _("Could not fetch sessions")}), 500
    finally:
        if conn:
            conn.close()


# ----------------------------------- access control & permissions ---------------------------------- #


@require_permission("admin.view.accessprofiles.useroverrides")
def admin_access_control():
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT ap.AccessID, ap.Name, ap.Description, COUNT(u.userID) AS UserCount
            FROM AccessProfile ap
            LEFT JOIN Users u ON u.accessID = ap.AccessID
            GROUP BY ap.AccessID, ap.Name, ap.Description
            ORDER BY ap.Name
        """)
        profiles = [
            dict(zip([column[0] for column in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]

        cursor.execute("""
            SELECT PermissionID, Code, Description FROM Permission
            ORDER BY
                LEFT(Code, LEN(Code) - CHARINDEX('.', REVERSE(Code))),
                CASE
                    WHEN Code LIKE '%.view'    THEN 1
                    WHEN Code LIKE '%.add'     THEN 2
                    WHEN Code LIKE '%.add.%'   THEN 3
                    WHEN Code LIKE '%.edit%'   THEN 4
                    WHEN Code LIKE '%.delete%' THEN 5
                    ELSE 6
                END,
                Code
        """)
        all_permissions = [
            dict(zip([column[0] for column in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]

        organizations = []
        assignable_profiles = []
        if has_permission("admin.view.users"):
            cursor.execute(
                "SELECT organizationcode, organization FROM Organizations ORDER BY organization"
            )
            organizations = [
                dict(zip([column[0] for column in cursor.description], row, strict=False))
                for row in cursor.fetchall()
            ]
            cursor.execute(
                "SELECT ap.name profile, ap.accessid accessid FROM AccessProfile ap ORDER BY ap.name"
            )
            all_ap = [
                dict(zip([column[0] for column in cursor.description], row, strict=False))
                for row in cursor.fetchall()
            ]
            for ap in all_ap:
                if has_permission(f'admin.assign.user.accessprofile.{str(ap["profile"]).lower()}'):
                    assignable_profiles.append(ap)

        return render_template(
            "admin/access_control.html",
            profiles=profiles,
            all_permissions=all_permissions,
            organizations=organizations,
            assignable_profiles=assignable_profiles,
            can_edit_accessprofile=has_permission("admin.edit.accessprofile"),
            can_view_users=has_permission("admin.view.users"),
            can_create_user=has_permission("admin.create.user"),
            can_edit_user=has_permission("admin.edit.user"),
            can_delete_user=has_permission("admin.delete.user"),
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            pageV=page_visibility(),
        )
    except Exception as e:
        current_app.logger.error(f"Error loading access control: {e}")
        return render_template("500.html")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.accessprofiles.useroverrides")
def get_users_admin_access_control():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    profile_filter = request.args.get("profile", "").strip()
    org_filter = request.args.get("organization", "").strip()

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        where_parts = ["1=1"]
        params = []
        if profile_filter:
            where_parts.append("ap.Name = ?")
            params.append(profile_filter)
        if org_filter:
            where_parts.append("o.organizationcode = ?")
            params.append(org_filter)
        where_clause = " AND ".join(where_parts)

        query = f"""
            SELECT
                u.userID, u.username, u.fullname, u.email,
                ap.Name AS AccessProfileName, ap.AccessID AS AccessProfileID,
                o.organizationcode,
                o.organization,
                (SELECT COUNT(*) FROM UserPermissionOverride upo WHERE upo.UserID = u.userID) AS OverrideCount
            FROM Users u
            LEFT JOIN AccessProfile ap ON u.accessid = ap.AccessID
            LEFT JOIN Organizations o ON u.organizationcode = o.organizationcode
            WHERE {where_clause}
            ORDER BY u.fullname
        """
        cursor.execute(query, params)

        users = [
            dict(zip([column[0] for column in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        return jsonify(users)
    except Exception as e:
        current_app.logger.error(f"Failed to fetch users for access control: {e}")
        return jsonify({"error": _("Could not fetch users")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.accessprofiles.useroverrides")
def get_profile_details(access_id):
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT PermissionID, Effect
            FROM AccessProfilePermission
            WHERE AccessID = ?
            """,
            (access_id,),
        )
        assigned_perms = [
            dict(zip([column[0] for column in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        return jsonify({"success": True, "permissions": assigned_perms})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.edit.accessprofile")
def save_access_profile():
    data = request.get_json()
    access_id = data.get("accessId")
    name = data.get("name")
    description = data.get("description")
    permissions = data.get("permissions")

    if not name:
        return jsonify({"success": False, "message": _("Name is required")}), 400

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        if access_id:
            cursor.execute(
                "UPDATE AccessProfile SET Name=?, Description=? WHERE AccessID=?",
                (name, description, access_id),
            )
            cursor.execute("DELETE FROM AccessProfilePermission WHERE AccessID=?", (access_id,))
        else:
            cursor.execute(
                "INSERT INTO AccessProfile (Name, Description) OUTPUT INSERTED.AccessID VALUES (?, ?)",
                (name, description),
            )
            access_id = cursor.fetchone()[0]

        if permissions:
            params = [(access_id, p["PermissionID"], p["Effect"]) for p in permissions]
            cursor.executemany(
                "INSERT INTO AccessProfilePermission (AccessID, PermissionID, Effect) VALUES (?, ?, ?)",
                params,
            )
        conn.commit()
        session["permissions"] = load_permissions_for_user(session["userid"])
        return jsonify({"success": True, "message": _("Profile saved successfully")})
    except Exception as e:
        current_app.logger.error(f"Error saving profile: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.accessprofiles.useroverrides")
def get_user_overrides(user_id):
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT AccessID FROM Users WHERE UserID = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"success": False, "message": "User not found"}), 404
        base_access_id = row[0]
        cursor.execute(
            "SELECT PermissionID, Effect FROM UserPermissionOverride WHERE UserID = ?", (user_id,)
        )
        overrides = {row.PermissionID: row.Effect for row in cursor.fetchall()}
        base_perms = {}
        if base_access_id:
            cursor.execute(
                "SELECT PermissionID, Effect FROM AccessProfilePermission WHERE AccessID = ?",
                (base_access_id,),
            )
            base_perms = {row.PermissionID: row.Effect for row in cursor.fetchall()}
        return jsonify(
            {
                "success": True,
                "overrides": overrides,
                "base_permissions": base_perms,
            }
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.accessprofiles.useroverrides")
def api_admin_user_effective_permissions(user_id):
    """Compute the merged permission set: profile-grant unless an override
    flips it. Source on each entry tells the UI whether it came from the
    profile or from an Allow override."""
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT u.userID, u.username, u.AccessID, ap.Name AS ProfileName
            FROM Users u
            LEFT JOIN AccessProfile ap ON ap.AccessID = u.AccessID
            WHERE u.userID = ?
        """,
            (user_id,),
        )
        u = cursor.fetchone()
        if not u:
            return jsonify({"success": False, "message": "User not found"}), 404

        cursor.execute(
            """
            SELECT p.PermissionID, p.Code, p.Description,
                   ap_perm.Effect AS ProfileEffect,
                   uo.Effect      AS OverrideEffect
            FROM Permission p
            LEFT JOIN AccessProfilePermission ap_perm
                   ON ap_perm.PermissionID = p.PermissionID
                  AND ap_perm.AccessID = ?
            LEFT JOIN UserPermissionOverride uo
                   ON uo.PermissionID = p.PermissionID
                  AND uo.UserID = ?
            ORDER BY
                LEFT(p.Code, LEN(p.Code) - CHARINDEX('.', REVERSE(p.Code))),
                CASE
                    WHEN p.Code LIKE '%.view'    THEN 1
                    WHEN p.Code LIKE '%.add'     THEN 2
                    WHEN p.Code LIKE '%.add.%'   THEN 3
                    WHEN p.Code LIKE '%.edit%'   THEN 4
                    WHEN p.Code LIKE '%.delete%' THEN 5
                    ELSE 6
                END,
                p.Code
        """,
            (u.AccessID, user_id),
        )

        granted = []
        denied = []
        for r in cursor.fetchall():
            override = r.OverrideEffect
            profile = r.ProfileEffect
            if override == "A":
                source = "override-allow"
                effective = True
            elif override == "D":
                source = "override-deny"
                effective = False
            elif profile == "A":
                source = "profile"
                effective = True
            elif profile == "D":
                source = "profile-deny"
                effective = False
            else:
                continue  # No grant, no override — irrelevant

            entry = {
                "PermissionID": r.PermissionID,
                "Code": r.Code,
                "Description": r.Description,
                "source": source,
            }
            (granted if effective else denied).append(entry)

        return jsonify(
            {
                "success": True,
                "user": {
                    "userID": u.userID,
                    "username": u.username,
                    "profile": u.ProfileName,
                },
                "granted": granted,
                "denied": denied,
            }
        )
    except Exception as e:
        current_app.logger.error(f"Failed to compute effective permissions for user {user_id}: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            with suppress(Exception):
                cursor.close()
        if conn:
            with suppress(Exception):
                conn.close()


@require_permission("admin.edit.user.override")
def save_user_overrides():
    data = request.get_json()
    user_id = data.get("userId")
    overrides = data.get("overrides")

    if not user_id:
        return jsonify({"success": False, "message": "User ID required"}), 400

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM UserPermissionOverride WHERE UserID=?", (user_id,))

        if overrides:
            params = [(user_id, p["PermissionID"], p["Effect"]) for p in overrides]
            cursor.executemany(
                "INSERT INTO UserPermissionOverride (UserID, PermissionID, Effect) VALUES (?, ?, ?)",
                params,
            )

        conn.commit()
        session["permissions"] = load_permissions_for_user(session["userid"])
        return jsonify({"success": True, "message": _("Overrides updated successfully")})
    except Exception as e:
        current_app.logger.error(f"Error saving overrides: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.accessprofiles.useroverrides")
def api_admin_permissions_list():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                p.PermissionID, p.Code, p.Description,
                (SELECT COUNT(*) FROM AccessProfilePermission a WHERE a.PermissionID = p.PermissionID) AS ProfileCount,
                (SELECT COUNT(*) FROM UserPermissionOverride o WHERE o.PermissionID = p.PermissionID) AS OverrideCount
            FROM Permission p
            ORDER BY
                LEFT(p.Code, LEN(p.Code) - CHARINDEX('.', REVERSE(p.Code))),
                CASE
                    WHEN p.Code LIKE '%.view'    THEN 1
                    WHEN p.Code LIKE '%.add'     THEN 2
                    WHEN p.Code LIKE '%.add.%'   THEN 3
                    WHEN p.Code LIKE '%.edit%'   THEN 4
                    WHEN p.Code LIKE '%.delete%' THEN 5
                    ELSE 6
                END,
                p.Code
        """)
        perms = [
            dict(zip([col[0] for col in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        return jsonify(perms)
    except Exception as e:
        current_app.logger.error(f"Error listing permissions: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.accessprofiles.useroverrides")
def api_admin_permission_users(perm_id):
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Code FROM Permission WHERE PermissionID = ?", (perm_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"success": False, "message": _("Permission not found")}), 404
        perm_code = row[0]
        cursor.execute(
            """
            SELECT
                u.userID, u.username, u.fullname,
                ap.Name AS AccessProfileName,
                CAST(dbo.fnUserHasPermission(u.userID, ?) AS INT) AS HasPermission,
                upo.Effect AS OverrideEffect,
                app.Effect AS ProfileEffect
            FROM Users u
            LEFT JOIN AccessProfile ap ON ap.AccessID = u.accessID
            LEFT JOIN UserPermissionOverride upo ON upo.UserID = u.userID AND upo.PermissionID = ?
            LEFT JOIN AccessProfilePermission app ON app.AccessID = u.accessID AND app.PermissionID = ?
            ORDER BY u.fullname
        """,
            (perm_code, perm_id, perm_id),
        )
        users = [
            dict(zip([col[0] for col in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        return jsonify({"success": True, "users": users})
    except Exception as e:
        current_app.logger.error(f"Error fetching users for permission {perm_id}: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.view.accessprofiles.useroverrides")
def api_admin_user_all_permissions(user_id):
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                p.PermissionID, p.Code, p.Description,
                CAST(dbo.fnUserHasPermission(?, p.Code) AS INT) AS IsEffective,
                upo.Effect AS OverrideEffect,
                app.Effect AS ProfileEffect
            FROM Permission p
            LEFT JOIN Users u ON u.userID = ?
            LEFT JOIN UserPermissionOverride upo ON upo.UserID = ? AND upo.PermissionID = p.PermissionID
            LEFT JOIN AccessProfilePermission app ON app.AccessID = u.accessID AND app.PermissionID = p.PermissionID
            ORDER BY p.Code
        """,
            (user_id, user_id, user_id),
        )
        perms = [
            dict(zip([col[0] for col in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        return jsonify({"success": True, "permissions": perms})
    except Exception as e:
        current_app.logger.error(f"Error fetching all permissions for user {user_id}: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.edit.accessprofile")
def api_admin_permission_add():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401
    data = request.get_json()
    code = (data.get("code") or "").strip()
    description = (data.get("description") or "").strip()
    if not code or not description:
        return jsonify({"success": False, "message": _("Code and description are required")}), 400
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Permission (Code, Description) OUTPUT INSERTED.PermissionID VALUES (?, ?)",
            (code, description),
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify(
            {
                "success": True,
                "message": _("Permission created successfully"),
                "permissionId": new_id,
            }
        )
    except Exception as e:
        current_app.logger.error(f"Error creating permission: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.edit.accessprofile")
def api_admin_permission_edit(perm_id):
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401
    data = request.get_json()
    code = (data.get("code") or "").strip()
    description = (data.get("description") or "").strip()
    if not code or not description:
        return jsonify({"success": False, "message": _("Code and description are required")}), 400
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE Permission SET Code=?, Description=? WHERE PermissionID=?",
            (code, description, perm_id),
        )
        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": _("Permission not found")}), 404
        conn.commit()
        return jsonify({"success": True, "message": _("Permission updated successfully")})
    except Exception as e:
        current_app.logger.error(f"Error updating permission {perm_id}: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.edit.accessprofile")
def api_admin_permission_delete(perm_id):
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM AccessProfilePermission WHERE PermissionID=?", (perm_id,)
        )
        profile_refs = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM UserPermissionOverride WHERE PermissionID=?", (perm_id,)
        )
        override_refs = cursor.fetchone()[0]
        if profile_refs > 0 or override_refs > 0:
            return jsonify(
                {
                    "success": False,
                    "message": _(
                        "Cannot delete: used in %(p)d profile(s) and %(o)d override(s). Remove all assignments first."
                    )
                    % {"p": profile_refs, "o": override_refs},
                }
            ), 400
        cursor.execute("DELETE FROM Permission WHERE PermissionID=?", (perm_id,))
        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": _("Permission not found")}), 404
        conn.commit()
        return jsonify({"success": True, "message": _("Permission deleted successfully")})
    except Exception as e:
        current_app.logger.error(f"Error deleting permission {perm_id}: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def register_routes(app):
    # overview
    app.add_url_rule("/admin", endpoint="admin_dashboard", view_func=admin_dashboard)

    # organizations
    app.add_url_rule(
        "/admin/organizations",
        endpoint="admin_organizations_view",
        view_func=admin_organizations_view,
    )
    app.add_url_rule(
        "/admin/organizations/add",
        endpoint="admin_add_organization",
        view_func=admin_add_organization,
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/organizations/edit/<organizationcode>",
        endpoint="admin_edit_organization",
        view_func=admin_edit_organization,
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/organizations/delete/<organizationcode>",
        endpoint="admin_delete_organization",
        view_func=admin_delete_organization,
        methods=["DELETE"],
    )
    app.add_url_rule(
        "/api/admin/organizations/list",
        endpoint="api_admin_organizations_list",
        view_func=api_admin_organizations_list,
    )

    # status page
    app.add_url_rule("/admin/status", endpoint="admin_status_view", view_func=admin_status_view)

    # dev server restart
    app.add_url_rule(
        "/api/admin/restart",
        endpoint="api_admin_restart",
        view_func=api_admin_restart,
        methods=["POST"],
    )

    # maintenance banner
    app.add_url_rule(
        "/admin/maintenance", endpoint="admin_maintenance_view", view_func=admin_maintenance_view
    )
    app.add_url_rule(
        "/api/admin/maintenance",
        endpoint="api_admin_maintenance_list",
        view_func=api_admin_maintenance_list,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/admin/maintenance",
        endpoint="api_admin_maintenance_add",
        view_func=api_admin_maintenance_add,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/admin/maintenance/<int:banner_id>",
        endpoint="api_admin_maintenance_edit",
        view_func=api_admin_maintenance_edit,
        methods=["PUT"],
    )
    app.add_url_rule(
        "/api/admin/maintenance/<int:banner_id>",
        endpoint="api_admin_maintenance_delete",
        view_func=api_admin_maintenance_delete,
        methods=["DELETE"],
    )

    # logs
    app.add_url_rule("/admin/logs", endpoint="admin_logs_view", view_func=admin_logs_view)
    app.add_url_rule(
        "/api/admin/logs/search", endpoint="api_admin_logs_search", view_func=api_admin_logs_search
    )
    app.add_url_rule(
        "/api/admin/logs/export.csv",
        endpoint="api_admin_logs_export",
        view_func=api_admin_logs_export,
    )

    # sessions & users
    app.add_url_rule(
        "/admin/sessions", endpoint="admin_sessions_view", view_func=admin_sessions_view
    )
    app.add_url_rule(
        "/admin/users/add", endpoint="admin_add_user", view_func=admin_add_user, methods=["POST"]
    )
    app.add_url_rule(
        "/admin/users/edit/<int:user_id>",
        endpoint="admin_edit_user",
        view_func=admin_edit_user,
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/users/<int:user_id>", endpoint="admin_user_detail", view_func=admin_user_detail
    )
    app.add_url_rule(
        "/api/admin/users/<int:user_id>/activity",
        endpoint="api_admin_user_activity",
        view_func=api_admin_user_activity,
    )
    app.add_url_rule(
        "/admin/users/delete/<int:user_id>",
        endpoint="admin_delete_user",
        view_func=admin_delete_user,
        methods=["DELETE"],
    )
    app.add_url_rule(
        "/admin/sessions/<string:session_id>/revoke",
        endpoint="admin_revoke_session",
        view_func=admin_revoke_session,
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/users/<int:user_id>/revoke_all",
        endpoint="admin_revoke_all_sessions",
        view_func=admin_revoke_all_sessions,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/admin/users/list", endpoint="api_admin_users_list", view_func=api_admin_users_list
    )
    app.add_url_rule(
        "/api/admin/recent_logs", endpoint="admin_recent_logs", view_func=admin_recent_logs
    )
    app.add_url_rule(
        "/api/admin/active_sessions",
        endpoint="admin_active_sessions",
        view_func=admin_active_sessions,
    )

    # access control & permissions
    app.add_url_rule(
        "/admin/access_control", endpoint="admin_access_control", view_func=admin_access_control
    )
    app.add_url_rule(
        "/api/admin/users",
        endpoint="get_users_admin_access_control",
        view_func=get_users_admin_access_control,
    )
    app.add_url_rule(
        "/api/admin/access_profile/<int:access_id>/details",
        endpoint="get_profile_details",
        view_func=get_profile_details,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/admin/access_profile/save",
        endpoint="save_access_profile",
        view_func=save_access_profile,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/admin/user_overrides/<int:user_id>",
        endpoint="get_user_overrides",
        view_func=get_user_overrides,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/admin/users/<int:user_id>/effective_permissions",
        endpoint="api_admin_user_effective_permissions",
        view_func=api_admin_user_effective_permissions,
    )
    app.add_url_rule(
        "/api/admin/user_overrides/save",
        endpoint="save_user_overrides",
        view_func=save_user_overrides,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/admin/permissions/list",
        endpoint="api_admin_permissions_list",
        view_func=api_admin_permissions_list,
    )
    app.add_url_rule(
        "/api/admin/permissions/<int:perm_id>/users",
        endpoint="api_admin_permission_users",
        view_func=api_admin_permission_users,
    )
    app.add_url_rule(
        "/api/admin/users/<int:user_id>/all_permissions",
        endpoint="api_admin_user_all_permissions",
        view_func=api_admin_user_all_permissions,
    )
    app.add_url_rule(
        "/api/admin/permissions/add",
        endpoint="api_admin_permission_add",
        view_func=api_admin_permission_add,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/admin/permissions/edit/<int:perm_id>",
        endpoint="api_admin_permission_edit",
        view_func=api_admin_permission_edit,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/admin/permissions/delete/<int:perm_id>",
        endpoint="api_admin_permission_delete",
        view_func=api_admin_permission_delete,
        methods=["DELETE"],
    )
