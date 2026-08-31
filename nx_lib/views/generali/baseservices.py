"""Generali tenant: Base Services.

The page view stays hand-written; every repeated endpoint family (month report,
org users, organizations, filter users, list, add/edit/delete) is generated from
the ``BASESERVICES`` descriptor by ``._crud`` and bound below under its original
function name, so ``gv.<fn>``, the URLs and the endpoint names are unchanged.
"""

from flask import current_app, redirect, render_template, session, url_for

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

# ----------------------------- Generali Base Services ----------------------- #


@require_permission("generali.baseservices.view")
def generali_base_services():
    try:
        if "username" not in session:
            return redirect(url_for("login"))
        return render_template(
            "generali_baseservices.html",
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            page_visibility=page_visibility(),
            organizationcode=session.get("organizationcode"),
            can_add=has_permission("generali.baseservices.add"),
            can_add_bypass_deadline=has_permission("generali.baseservices.add.bypass.deadline"),
            can_edit=has_permission("generali.baseservices.edit.organizational")
            or has_permission("generali.baseservices.edit.transorganizational"),
            can_edit_transorg=has_permission("generali.baseservices.edit.transorganizational"),
            can_delete=has_permission("generali.baseservices.delete.organizational")
            or has_permission("generali.baseservices.delete.transorganizational"),
            can_delete_transorg=has_permission("generali.baseservices.delete.transorganizational"),
            can_add_for_org=has_permission("generali.baseservices.add.organizational"),
            can_add_transorg=has_permission("generali.baseservices.add.transorganizational"),
        )
    except Exception as e:
        current_app.logger.error(f"Error loading Generali Base Services: {e}")
        return render_template("handlers/500.html"), 500


VALID_BASE_CATEGORIES = {"Physical Mailroom, AVOR & Scanning", "Nk1 & NK2", "POE", "PPR"}


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
    rec_id, effort, user_id, for_date, category_val, recorded_at = r
    return {
        "id": rec_id,
        "effortInHours": float(effort) if effort is not None else None,
        "userId": user_id,
        "fullname": user_info.get("fullname"),
        "orgCode": user_info.get("orgCode"),
        "forDate": str(for_date) if for_date else None,
        "category": category_val,
        "recordDateTime": recorded_at.isoformat() if recorded_at else None,
    }


BASESERVICES = CrudTable(
    slug="baseservices",
    table="[Generali].[dbo].[BaseServices]",
    user_column="UserID",
    perm_prefix="generali.baseservices",
    view_perm="generali.baseservices.view",
    api_base="/api/generali/baseservices",
    label="Generali Base Services",
    user_lookup_label="base services",
    # historical log label -- compressed, unlike every sibling endpoint's
    filter_users_label="Generali BaseServices",
    monthreport_url="/generali/baseServices/monthreport",
    monthreport_endpoint="generali_baseservices_monthreport",
    monthreport=CrudMonthReport(
        section="baseservices",
        section_title="Generali Base Services",
        back_endpoint="generali_base_services",
        date_column="ForDate",
        group_column="Category",
        measures="COUNT(*) AS entries, ISNULL(SUM(EffortInHours), 0) AS total_hours",
        row_builder=_monthreport_row,
        summary=_monthreport_summary,
    ),
    list_spec=CrudList(
        select="ID, EffortInHours, UserID, ForDate, Category, RecordDateTime",
        order_by="ForDate DESC, RecordDateTime DESC",
        filters=(
            Filter("startDate", "ForDate", "gte"),
            Filter("endDate", "ForDate", "lte"),
            Filter("category", "Category"),
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
            Field(
                "Category",
                json="category",
                required=True,
                allowed=VALID_BASE_CATEGORIES,
                error="Invalid category",
            ),
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
        insert_order=("EffortInHours", "UserID", "ForDate", "Category", "RecordDateTime"),
        update_order=("ForDate", "Category", "EffortInHours"),
    ),
)

api_generali_baseservices_org_users = BASESERVICES.views["org_users"]
api_generali_baseservices_organizations = BASESERVICES.views["organizations"]
api_generali_baseservices_filter_users = BASESERVICES.views["filter_users"]
api_generali_baseservices_list = BASESERVICES.views["list"]
api_generali_baseservices_add = BASESERVICES.views["add"]
api_generali_baseservices_edit = BASESERVICES.views["edit"]
api_generali_baseservices_delete = BASESERVICES.views["delete"]
generali_baseservices_monthreport = BASESERVICES.views["monthreport"]

for _name, _fn in (
    ("api_generali_baseservices_org_users", api_generali_baseservices_org_users),
    ("api_generali_baseservices_organizations", api_generali_baseservices_organizations),
    ("api_generali_baseservices_filter_users", api_generali_baseservices_filter_users),
    ("api_generali_baseservices_list", api_generali_baseservices_list),
    ("api_generali_baseservices_add", api_generali_baseservices_add),
    ("api_generali_baseservices_edit", api_generali_baseservices_edit),
    ("api_generali_baseservices_delete", api_generali_baseservices_delete),
    ("generali_baseservices_monthreport", generali_baseservices_monthreport),
):
    _fn.__name__ = _name
    _fn.__qualname__ = _name
del _name, _fn


def register_routes(app):
    app.add_url_rule(
        "/generali/baseServices",
        endpoint="generali_base_services",
        view_func=generali_base_services,
    )
    register_crud(app, BASESERVICES)
