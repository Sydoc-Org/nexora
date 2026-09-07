"""Generali tenant: Project Management.

The page view stays hand-written; every repeated endpoint family is generated
from the ``PROJECTMANAGEMENT`` descriptor by ``._crud`` and bound below under its
original function name (see that module's docstring).
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

# ----------------------------- Generali Project Management ------------------ #


@require_permission("tenant.generali.projectmanagement.view")
def generali_project_management():
    try:
        if "username" not in session:
            return redirect(url_for("login"))
        return render_template(
            "generali_projectmanagement.html",
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            page_visibility=page_visibility(),
            organizationcode=session.get("organizationcode"),
            can_add=has_permission("tenant.generali.projectmanagement.add"),
            can_add_bypass_deadline=has_permission(
                "tenant.generali.projectmanagement.add.pastdeadline"
            ),
            can_edit=has_permission("tenant.generali.projectmanagement.edit.org")
            or has_permission("tenant.generali.projectmanagement.edit.all"),
            can_edit_transorg=has_permission("tenant.generali.projectmanagement.edit.all"),
            can_delete=has_permission("tenant.generali.projectmanagement.delete.org")
            or has_permission("tenant.generali.projectmanagement.delete.all"),
            can_delete_transorg=has_permission("tenant.generali.projectmanagement.delete.all"),
            can_add_for_org=has_permission("tenant.generali.projectmanagement.add.org"),
            can_add_transorg=has_permission("tenant.generali.projectmanagement.add.all"),
        )
    except Exception as e:
        current_app.logger.error(f"Error loading Generali Project Management: {e}")
        return render_template("handlers/500.html"), 500


def _monthreport_summary(row):
    """Ungrouped: Project Management reports one total, never a per-category table."""
    return {
        "total_entries": row[0] or 0,
        "total_hours": round(float(row[1] or 0), 2),
    }


def _list_record(r, user_info):
    rec_id, effort, user_id, for_date, category_val, comment, recorded_at = r
    return {
        "id": rec_id,
        "effortInHours": float(effort) if effort is not None else None,
        "userId": user_id,
        "fullname": user_info.get("fullname"),
        "orgCode": user_info.get("orgCode"),
        "forDate": str(for_date) if for_date else None,
        "category": category_val,
        "comment": comment,
        "recordDateTime": recorded_at.isoformat() if recorded_at else None,
    }


PROJECTMANAGEMENT = CrudTable(
    slug="projectmanagement",
    table="[Generali].[dbo].[ProjectManagement]",
    user_column="UserID",
    perm_prefix="tenant.generali.projectmanagement",
    api_base="/api/generali/projectmanagement",
    label="Generali Project Management",
    user_lookup_label="project management",
    # historical log label -- compressed, unlike every sibling endpoint's
    filter_users_label="Generali ProjectManagement",
    monthreport_url="/generali/projectManagement/monthreport",
    monthreport_endpoint="generali_projectmanagement_monthreport",
    monthreport=CrudMonthReport(
        section="projectmanagement",
        section_title="Generali Project Management",
        back_endpoint="generali_project_management",
        date_column="ForDate",
        group_column=None,
        measures="COUNT(*) AS entries, ISNULL(SUM(EffortInHours), 0) AS total_hours",
        summary=_monthreport_summary,
    ),
    list_spec=CrudList(
        select="ID, EffortInHours, UserID, ForDate, Category, Comment, RecordDateTime",
        order_by="ForDate DESC, RecordDateTime DESC",
        filters=(
            Filter("startDate", "ForDate", "gte"),
            Filter("endDate", "ForDate", "lte"),
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
                "EffortInHours",
                json="effortInHours",
                kind="float",
                required=True,
                minimum=0,
                error="Invalid effort value",
            ),
            Field("Comment", json="comment", kind="opt_str"),
            # Project Management has no user-selectable category: every row is
            # inserted with this constant, and edit leaves the column alone.
            Field("Category", kind="const", const="Project Effort"),
        ),
        date_json="forDate",
        insert_order=(
            "EffortInHours",
            "UserID",
            "ForDate",
            "Category",
            "Comment",
            "RecordDateTime",
        ),
        update_order=("ForDate", "EffortInHours", "Comment"),
    ),
)

api_generali_projectmanagement_org_users = PROJECTMANAGEMENT.views["org_users"]
api_generali_projectmanagement_organizations = PROJECTMANAGEMENT.views["organizations"]
api_generali_projectmanagement_filter_users = PROJECTMANAGEMENT.views["filter_users"]
api_generali_projectmanagement_list = PROJECTMANAGEMENT.views["list"]
api_generali_projectmanagement_add = PROJECTMANAGEMENT.views["add"]
api_generali_projectmanagement_edit = PROJECTMANAGEMENT.views["edit"]
api_generali_projectmanagement_delete = PROJECTMANAGEMENT.views["delete"]
generali_projectmanagement_monthreport = PROJECTMANAGEMENT.views["monthreport"]

for _name, _fn in (
    ("api_generali_projectmanagement_org_users", api_generali_projectmanagement_org_users),
    ("api_generali_projectmanagement_organizations", api_generali_projectmanagement_organizations),
    ("api_generali_projectmanagement_filter_users", api_generali_projectmanagement_filter_users),
    ("api_generali_projectmanagement_list", api_generali_projectmanagement_list),
    ("api_generali_projectmanagement_add", api_generali_projectmanagement_add),
    ("api_generali_projectmanagement_edit", api_generali_projectmanagement_edit),
    ("api_generali_projectmanagement_delete", api_generali_projectmanagement_delete),
    ("generali_projectmanagement_monthreport", generali_projectmanagement_monthreport),
):
    _fn.__name__ = _name
    _fn.__qualname__ = _name
del _name, _fn


def register_routes(app):
    app.add_url_rule(
        "/generali/projectManagement",
        endpoint="generali_project_management",
        view_func=generali_project_management,
    )
    register_crud(app, PROJECTMANAGEMENT)
