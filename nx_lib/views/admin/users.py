"""Admin sessions & users: session view, user CRUD, active sessions."""

import math
import secrets
from contextlib import suppress

import bcrypt
import pyodbc
from flask import abort, current_app, jsonify, redirect, render_template, request, session, url_for
from flask_babel import gettext as _
from werkzeug.exceptions import HTTPException

from ...db import engine_nexora_db
from ...security import (
    _revoke_session_by_id,
    assignable_profile_ids,
    group_permissions,
    has_permission,
    page_visibility,
    require_permission,
)


@require_permission("admin.sessions.view")
def admin_sessions_view():
    return render_template(
        "admin/sessions.html",
        logged_in_user=session.get("username"),
        userid=session.get("userid"),
        page_visibility=page_visibility(),
    )


@require_permission("admin.users.add")
def admin_add_user():
    from ..auth import _build_reset_email_message, send_reset_email

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

    hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("select accessid from accessprofile where name = ?", accessprofile)
        accessprofile_row = cursor.fetchone()
        if accessprofile_row is None:
            return jsonify({"success": False, "message": _("Unknown access profile.")}), 400
        accessid = accessprofile_row[0]

        if accessid not in assignable_profile_ids():
            current_app.logger.error(
                "assign-permission denied: profile=%r username=%r",
                str(accessprofile)[:100],
                str(username)[:100],
            )
            return jsonify(
                {"success": False, "message": _("Permission Denied for this action.")}
            ), 403

        cursor.execute(
            "select organizationcode from organizations where organization = ?", organization
        )
        organization_row = cursor.fetchone()
        if organization_row is None:
            return jsonify({"success": False, "message": _("Unknown organization.")}), 400
        organizationcode = organization_row[0]
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


@require_permission("admin.users.edit")
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

        cursor.execute("select accessid from accessprofile where name = ?", accessprofile)
        accessprofile_row = cursor.fetchone()
        if accessprofile_row is None:
            return jsonify({"success": False, "message": _("Unknown access profile.")}), 400
        accessid = accessprofile_row[0]

        if accessprofile != current_profile and accessid not in assignable_profile_ids():
            current_app.logger.error(
                f"User does not have Rank to assign accessprofile {accessprofile!r} for {user_id}"
            )
            return jsonify(
                {"success": False, "message": _("Permission Denied for this action.")}
            ), 403

        cursor.execute(
            "select organizationcode from organizations where organization = ?", organization
        )
        organization_row = cursor.fetchone()
        if organization_row is None:
            return jsonify({"success": False, "message": _("Unknown organization.")}), 400
        organizationcode = organization_row[0]

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


@require_permission("admin.profiles.view")
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
        assignable = assignable_profile_ids()
        assignable_profiles = [ap for ap in all_ap if ap["accessid"] in assignable]

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
            groups=group_permissions(all_permissions),
            can_edit_user=has_permission("admin.users.edit"),
            can_delete_user=has_permission("admin.users.delete"),
            can_edit_overrides=has_permission("admin.users.overrides.edit"),
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            page_visibility=page_visibility(),
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


@require_permission("admin.profiles.view")
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
        return jsonify(
            {
                "error": _("An unexpected error occurred"),
                "entries": [],
                "total": 0,
                "page": page,
                "pages": 0,
            }
        ), 500
    finally:
        if cursor:
            with suppress(Exception):
                cursor.close()
        if conn:
            with suppress(Exception):
                conn.close()


@require_permission("admin.users.delete")
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


@require_permission("admin.users.overrides.edit")
def admin_revoke_session(session_id):
    try:
        _revoke_session_by_id(session_id)
        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Failed to revoke session {session_id}: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@require_permission("admin.users.overrides.edit")
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


@require_permission("admin.users.view")
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
        return jsonify({"error": _("An unexpected error occurred")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.sessions.view")
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


@require_permission("admin.sessions.view")
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
        sessions = [
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
            for r in cursor.fetchall()
        ]
        return jsonify(sessions)
    except Exception as e:
        current_app.logger.error(f"Failed to fetch active sessions: {e}")
        return jsonify({"error": _("Could not fetch sessions")}), 500
    finally:
        if conn:
            conn.close()


def register_routes(app):
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
