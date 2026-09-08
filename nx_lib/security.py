"""Permissions, decorators, and session-revocation utilities.

The ``PermissionDenied`` exception and ``@require_permission`` /
``@require_any_permission`` decorators live here so any view module can import
them without dragging in the rest of the app.
"""

import re
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


# <area>[.<object>[.<sub>]].<action>[.<scope>] -- spec #238. External identifiers
# (process names, reporting source codes) may carry capitals and underscores.
PERMISSION_CODE_RE = re.compile(
    r"^[a-z]+(\.[a-z]+)?(\.[A-Za-z0-9_]+)*"
    r"\.(view|add|edit|delete|use|run|export|schedule|manage|bypass|import|restart)"
    r"(\.(org|all|pastdeadline))?$"
)


_ACTIONS = (
    "view",
    "add",
    "edit",
    "delete",
    "use",
    "run",
    "import",
    "export",
    "schedule",
    "manage",
    "bypass",
    "restart",
)
_SCOPES = ("", "org", "all", "pastdeadline")
_TWO_SEGMENT_AREAS = ("tenant",)


def _split_code(code):
    """-> (area, object_key, action, scope) per the #238 grammar. The object is
    the first segment after the area; area-level codes (admin.view,
    reporting.export) have object == area."""
    parts = code.split(".")
    n_area = 2 if parts[0] in _TWO_SEGMENT_AREAS and len(parts) > 2 else 1
    area = ".".join(parts[:n_area])
    tail = parts[n_area:]
    scope = tail.pop() if tail and tail[-1] in _SCOPES[1:] else ""
    action = tail.pop() if tail and tail[-1] in _ACTIONS else ""
    obj = f"{area}.{tail[0]}" if tail else area
    return area, obj, action, scope


def group_permissions(rows):
    """Area -> object -> permissions tree for the grid and the user-detail page.
    Each returned permission is a copy of its row plus ``gate``: the .view code
    (the object's, else the area's) the UI greys it behind, or None."""
    codes = {row["Code"] for row in rows}
    areas: dict[str, dict[str, list]] = {}
    for row in rows:
        area, obj, action, scope = _split_code(row["Code"])
        gate = next(
            (c for c in (f"{obj}.view", f"{area}.view") if c != row["Code"] and c in codes), None
        )
        areas.setdefault(area, {}).setdefault(obj, []).append(
            ({**row, "gate": gate}, action, scope)
        )
    tree = []
    for area in sorted(areas):
        objects = []
        for obj in sorted(areas[area], key=lambda k: (k != area, k)):
            perms = sorted(
                areas[area][obj],
                key=lambda t: (
                    _ACTIONS.index(t[1]) if t[1] in _ACTIONS else 99,
                    _SCOPES.index(t[2]),
                    t[0]["Code"],
                ),
            )
            objects.append(
                {"key": obj, "label": obj[len(area) + 1 :], "perms": [t[0] for t in perms]}
            )
        tree.append({"area": area, "objects": objects})
    return tree


def load_permissions_for_user(user_id):
    conn = engine_nexora_db.raw_connection()
    cur = conn.cursor()
    cur.execute("EXEC dbo.spGetUserPermissions ?", user_id)
    perms = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return perms


def assignable_profile_ids() -> set[int]:
    """AccessIDs the current user may assign: every profile whose Rank is at or
    below the rank of the user's own profile (spec #238 D5). No login or no
    profile -> nothing. Replaces the admin.assign.user.accessprofile.* codes."""
    uid = session.get("userid")
    if not uid:
        return set()
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ap.AccessID FROM dbo.AccessProfile ap
            WHERE ap.Rank <= (SELECT ISNULL(MAX(me.Rank), -1)
                              FROM dbo.Users u JOIN dbo.AccessProfile me ON me.AccessID = u.accessid
                              WHERE u.userID = ?)
            """,
            (uid,),
        )
        return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


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
        "generaliPagePerm": "generali_evaluation",
        "generaliDocumentsPerm": "generali_documents",
        "generaliReportingPerm": "generali_reporting",
        "generaliAdditionalServicesPerm": "generali_additional_services",
        "generaliBaseServicesPerm": "generali_base_services",
        "generaliProjectManagementPerm": "generali_project_management",
        "generaliPDQMPerm": "generali_pdqm",
        "adminPagePerm": "admin_dashboard",
        "apiDocsPagePerm": "api_docs",
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
        "preparedDocsPagePerm": has_permission("workitems.prepared.view"),
        # invoicesPagePerm removed with the archived invoices page (#177).
        "apiDocsPagePerm": has_permission("api.docs.view"),
        "generaliPagePerm": has_permission("tenant.generali.view"),
        "generaliDocumentsPerm": has_permission("tenant.generali.documents.view"),
        "generaliReportingPerm": has_permission("tenant.generali.reporting.view"),
        "generaliAdditionalServicesPerm": has_permission("tenant.generali.attendance.view"),
        "generaliBaseServicesPerm": has_permission("tenant.generali.baseservices.view"),
        "generaliProjectManagementPerm": has_permission("tenant.generali.projectmanagement.view"),
        "generaliPDQMPerm": has_permission("tenant.generali.pdqm.view"),
        "generaliImportStatusPerm": has_permission("tenant.generali.importstatus.view"),
        "adminStatusPagePerm": has_permission("admin.status.view"),
        "adminMaintenanceViewPerm": has_permission("admin.maintenance.view"),
        "adminMaintenanceEditPerm": has_permission("admin.maintenance.edit"),
        "adminMaintenanceBypassPerm": has_permission("admin.maintenance.bypass"),
        "adminClientsPagePerm": has_permission("admin.clients.view"),
        "adminProcessesPagePerm": has_permission("admin.processes.view"),
        "adminTenantsPagePerm": has_permission("admin.tenants.view"),
    }


def _revoke_session_by_id(session_id):
    """Delete a session's ActiveSessions row and its server-side data (if any).
    Returns True if the DB row existed.

    The before_request hook also enforces revocation by re-checking
    ActiveSessions on every request (via a short per-process cache), so stale session files alone cannot keep
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
