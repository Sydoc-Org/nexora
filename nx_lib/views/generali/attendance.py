"""Generali tenant: Additional Services (attendance).

The page view and the category lookup stay hand-written; every repeated endpoint
family is generated from the ``ATTENDANCE`` descriptor by ``._crud`` and bound
below under its original function name (see that module's docstring).
"""

from flask import current_app, jsonify, redirect, render_template, session, url_for
from flask_babel import gettext as _

from ...i18n import get_locale
from ...security import has_permission, page_visibility, require_permission
from ._crud import (
    SCOPE,
    CrudList,
    CrudMonthReport,
    CrudTable,
    CrudWrite,
    Field,
    Filter,
    register_crud,
)

# ----------------------------- Generali Additional Services -------------------------- #


@require_permission("tenant.generali.attendance.view")
def generali_additional_services():
    try:
        if "username" not in session:
            return redirect(url_for("login"))
        return render_template(
            "generali_additionalservices.html",
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            page_visibility=page_visibility(),
            organizationcode=session.get("organizationcode"),
            can_add=has_permission("tenant.generali.attendance.add"),
            can_add_bypass_deadline=has_permission("tenant.generali.attendance.add.pastdeadline"),
            can_edit=has_permission("tenant.generali.attendance.edit.org")
            or has_permission("tenant.generali.attendance.edit.all"),
            can_edit_transorg=has_permission("tenant.generali.attendance.edit.all"),
            can_delete=has_permission("tenant.generali.attendance.delete.org")
            or has_permission("tenant.generali.attendance.delete.all"),
            can_delete_transorg=has_permission("tenant.generali.attendance.delete.all"),
            can_add_for_org=has_permission("tenant.generali.attendance.add.org"),
            can_add_transorg=has_permission("tenant.generali.attendance.add.all"),
        )
    except Exception as e:
        current_app.logger.error(f"Error loading Generali Attendance: {e}")
        return render_template("handlers/500.html"), 500


@require_permission("tenant.generali.attendance.view")
def api_generali_attendance_categories():
    conn = None
    try:
        # local import: re-resolve against the live package object so test
        # monkeypatching of gv.engine_generali_db works consistently across
        # the generali package
        from . import engine_generali_db

        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT ParentCategory, SubCategory
            FROM [Generali].[dbo].[AdditionalServices]
            ORDER BY ParentCategory, SubCategory
        """)
        rows = cursor.fetchall()
        cursor.close()

        grouped: dict[str, list] = {}
        for parent, sub in rows:
            if parent not in grouped:
                grouped[parent] = []
            if sub:
                grouped[parent].append(sub)

        locale = str(get_locale() or "de").split("_")[0]
        translations = {}
        if locale != "de":
            cursor2 = conn.cursor()
            cursor2.execute(
                """
                SELECT OriginalValue, TranslatedValue
                FROM [Generali].[dbo].[CategoryTranslation] WITH (NOLOCK)
                WHERE SourceTable = 'AdditionalServices' AND Locale = ?
            """,
                [locale],
            )
            translations = dict(cursor2.fetchall())
            cursor2.close()

        return jsonify({"success": True, "categories": grouped, "translations": translations})
    except Exception as e:
        current_app.logger.error(f"Generali Attendance Categories Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


def _monthreport_row(r):
    return {
        "category": r[0] or "—",
        "entries": r[1],
        "total_hours": round(float(r[2] or 0), 2),
    }


def _monthreport_summary(rows):
    return {
        "total_entries": sum(r["entries"] for r in rows),
        "total_hours": round(sum(r["total_hours"] for r in rows), 2),
    }


def _list_record(r, user_info):
    rec_id, effort, user_id, for_date, parent, sub, recorded_at = r
    return {
        "id": rec_id,
        "effortInHours": float(effort) if effort is not None else None,
        "userId": user_id,
        "fullname": user_info.get("fullname"),
        "orgCode": user_info.get("orgCode"),
        "forDate": str(for_date) if for_date else None,
        "parentCategory": parent,
        "subCategory": sub,
        "recordDateTime": recorded_at.isoformat() if recorded_at else None,
    }


ATTENDANCE = CrudTable(
    slug="attendance",
    table="[Generali].[dbo].[Attendance]",
    user_column="UserID",
    perm_prefix="tenant.generali.attendance",
    api_base="/api/generali/attendance",
    label="Generali Attendance",
    user_lookup_label="attendance",
    monthreport_url="/generali/additionalServices/monthreport",
    monthreport_endpoint="generali_additionalservices_monthreport",
    monthreport_label="Generali Additional Services",
    monthreport=CrudMonthReport(
        section="additionalservices",
        section_title="Generali Additional Services",
        back_endpoint="generali_additional_services",
        date_column="ForDate",
        group_column="ParentCategory",
        measures="COUNT(*) AS entries, ISNULL(SUM(EffortInHours), 0) AS total_hours",
        row_builder=_monthreport_row,
        summary=_monthreport_summary,
    ),
    list_spec=CrudList(
        select="ID, EffortInHours, UserID, ForDate, ParentCategory, SubCategory, RecordDateTime",
        order_by="ForDate DESC, RecordDateTime DESC",
        filters=(
            Filter("startDate", "ForDate", "gte"),
            Filter("endDate", "ForDate", "lte"),
            Filter("parentCategory", "ParentCategory"),
            Filter("subCategory", "SubCategory"),
            SCOPE,
            Filter("userId", "UserID"),
        ),
        aggregate=(
            "SUM(EffortInHours)",
            "totalHours",
            lambda v: float(v) if v is not None else 0.0,
        ),
        user_index=2,
        record=_list_record,
    ),
    write=CrudWrite(
        fields=(
            Field("ForDate", json="forDate", required=True),
            Field("ParentCategory", json="parentCategory", required=True),
            # optional, and unlike BaseServices' Category not validated against
            # a fixed set -- the sub categories are data-driven
            Field("SubCategory", json="subCategory", kind="opt_str"),
            Field(
                "EffortInHours",
                json="effortInHours",
                kind="float",
                required=True,
                minimum=0,
                error="Invalid effort value",
            ),
        ),
        date_json="forDate",
        insert_order=(
            "EffortInHours",
            "UserID",
            "ForDate",
            "ParentCategory",
            "SubCategory",
            "RecordDateTime",
        ),
        update_order=("ForDate", "ParentCategory", "SubCategory", "EffortInHours"),
    ),
)

api_generali_attendance_org_users = ATTENDANCE.views["org_users"]
api_generali_attendance_organizations = ATTENDANCE.views["organizations"]
api_generali_attendance_filter_users = ATTENDANCE.views["filter_users"]
api_generali_attendance_list = ATTENDANCE.views["list"]
api_generali_attendance_add = ATTENDANCE.views["add"]
api_generali_attendance_edit = ATTENDANCE.views["edit"]
api_generali_attendance_delete = ATTENDANCE.views["delete"]
generali_additionalservices_monthreport = ATTENDANCE.views["monthreport"]

for _name, _fn in (
    ("api_generali_attendance_org_users", api_generali_attendance_org_users),
    ("api_generali_attendance_organizations", api_generali_attendance_organizations),
    ("api_generali_attendance_filter_users", api_generali_attendance_filter_users),
    ("api_generali_attendance_list", api_generali_attendance_list),
    ("api_generali_attendance_add", api_generali_attendance_add),
    ("api_generali_attendance_edit", api_generali_attendance_edit),
    ("api_generali_attendance_delete", api_generali_attendance_delete),
    ("generali_additionalservices_monthreport", generali_additionalservices_monthreport),
):
    _fn.__name__ = _name
    _fn.__qualname__ = _name
del _name, _fn


def register_routes(app):
    app.add_url_rule(
        "/generali/additionalServices",
        endpoint="generali_additional_services",
        view_func=generali_additional_services,
    )
    app.add_url_rule(
        "/api/generali/attendance/categories",
        endpoint="api_generali_attendance_categories",
        view_func=api_generali_attendance_categories,
        methods=["GET"],
    )
    register_crud(app, ATTENDANCE)
