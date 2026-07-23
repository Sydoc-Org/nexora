"""Permissions, decorators, and session-revocation utilities.

The ``PermissionDenied`` exception and ``@require_permission`` /
``@require_any_permission`` decorators live here so any view module can import
them without dragging in the rest of the app.
"""

from contextlib import suppress
from datetime import date
from functools import wraps

from flask import current_app, redirect, session, url_for
from flask_babel import gettext as _
from werkzeug.exceptions import HTTPException

from .db import engine_nexora_db


class PermissionDenied(HTTPException):
    code = 403
    description = "Forbidden"


def load_permissions_for_user(user_id):
    conn = engine_nexora_db.raw_connection()
    cur = conn.cursor()
    cur.execute("EXEC dbo.spGetUserPermissions ?", user_id)
    perms = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return perms


def has_permission(code: str) -> bool:
    perms = set(session.get("permissions", []))
    return code.lower() in {p.lower() for p in perms}


def require_permission(code):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "username" not in session:
                return redirect(url_for("login"))
            if not has_permission(code):
                raise PermissionDenied()
            return f(*args, **kwargs)

        return wrapper

    return decorator


def require_any_permission(*codes):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "username" not in session:
                return redirect(url_for("login"))
            if not any(has_permission(c) for c in codes):
                raise PermissionDenied()
            return f(*args, **kwargs)

        return wrapper

    return decorator


def _check_generali_record_org(cursor, table, user_id_col, record_id):
    """Raises PermissionDenied if record belongs to a user outside the current user's org."""
    cursor.execute(f"SELECT {user_id_col} FROM {table} WHERE ID = ?", [record_id])
    rec = cursor.fetchone()
    if not rec:
        return  # record not found — UPDATE/DELETE will affect 0 rows
    record_uid = rec[0]
    if str(record_uid) == str(session.get("userid")):
        return  # own record always allowed
    nx_conn = engine_nexora_db.raw_connection()
    nx_cur = nx_conn.cursor()
    nx_cur.execute("SELECT organizationcode FROM Users WHERE userid = ?", [record_uid])
    org_row = nx_cur.fetchone()
    nx_cur.close()
    nx_conn.close()
    if not org_row or org_row[0] != session.get("organizationcode"):
        raise PermissionDenied()


def _get_add_min_date():
    today = date.today()
    if today.day <= 3:
        return date(
            today.year if today.month > 1 else today.year - 1,
            today.month - 1 if today.month > 1 else 12,
            1,
        )
    return date(today.year, today.month, 1)


def _check_add_deadline(for_date_str, bypass_perm_code):
    if has_permission(bypass_perm_code):
        return None
    try:
        entry_date = date.fromisoformat(for_date_str)
    except (ValueError, TypeError):
        return _("Invalid date")
    if entry_date < _get_add_min_date():
        return _("Date is outside the allowed entry window")
    return None


def startpage_redirect_to(page_v):
    perm_to_function = {
        "dashboardPagePerm": "dashboard",
        "reportingPagePerm": "reporting",
        "workitemsPagePerm": "workitems_overview",
        "invoicesPagePerm": "invoices",
        "generaliPagePerm": "generali_evaluation",
        "generaliDocumentsPerm": "generali_documents",
        "generaliReportingPerm": "generali_reporting",
        "generaliAdditionalServicesPerm": "generali_additionalServices",
        "generaliBaseServicesPerm": "generali_baseServices",
        "generaliProjectManagementPerm": "generali_projectManagement",
        "generaliPDQMPerm": "generali_pdqm",
        "adminPagePerm": "admin_dashboard",
    }
    for perm_key in perm_to_function:
        if page_v[perm_key]:
            return perm_to_function[perm_key]
    return "login"


def page_visibility():
    return {
        "adminPagePerm": has_permission("admin.view"),
        "dashboardPagePerm": has_permission("dashboard.view"),
        "reportingPagePerm": has_permission("reporting.view"),
        "workitemsPagePerm": has_permission("workitems.view"),
        "preparedDocsPagePerm": has_permission("workitems.import.preparedaudit"),
        "invoicesPagePerm": has_permission("invoices.view"),
        "generaliPagePerm": has_permission("generali.dashboard.view"),
        "generaliDocumentsPerm": has_permission("generali.documentlist.view"),
        "generaliReportingPerm": has_permission("generali.reporting.view"),
        "generaliAdditionalServicesPerm": has_permission("generali.additionalservices.view"),
        "generaliBaseServicesPerm": has_permission("generali.baseservices.view"),
        "generaliProjectManagementPerm": has_permission("generali.projectmanagement.view"),
        "generaliPDQMPerm": has_permission("generali.pdqm.view"),
        "generaliImportStatusPerm": has_permission("generali.importstatus.view"),
        "adminMaintenanceViewPerm": has_permission("admin.maintenance.view"),
        "adminMaintenanceEditPerm": has_permission("admin.maintenance.edit"),
        "adminMaintenanceBypassPerm": has_permission("admin.maintenance.bypass"),
    }


def _revoke_session_by_id(session_id):
    """Delete a session's ActiveSessions row and its server-side data (if any).
    Returns True if the DB row existed.

    The before_request hook also enforces revocation by re-checking
    ActiveSessions on every request, so stale session files alone cannot keep
    someone logged in.
    """
    deleted = 0
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ActiveSessions WHERE SessionID = ?", (str(session_id),))
        deleted = cursor.rowcount
        conn.commit()
    except Exception as e:
        current_app.logger.warning(f"Could not delete ActiveSessions row for {session_id}: {e}")
    finally:
        if cursor:
            with suppress(Exception):
                cursor.close()
        if conn:
            with suppress(Exception):
                conn.close()

    # Best-effort: nuke the server-side session data via Flask-Session's
    # internal store. Works for filesystem, cachelib, redis, etc. Falls back
    # silently on backends that don't expose these helpers.
    try:
        si = current_app.session_interface
        get_store_id = getattr(si, "_get_store_id", None)
        delete_session = getattr(si, "_delete_session", None)
        if callable(get_store_id) and callable(delete_session):
            delete_session(get_store_id(str(session_id)))
    except Exception as e:
        current_app.logger.warning(f"Could not delete session store entry for {session_id}: {e}")

    return deleted > 0
