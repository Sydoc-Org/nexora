"""Generali tenant: PDQM.

The page view and the nested category lookup stay hand-written; every repeated
endpoint family is generated from the ``PDQM`` descriptor by ``._crud`` and bound
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

# ----------------------------- Generali PDQM -------------------------------- #


@require_permission("tenant.generali.pdqm.view")
def generali_pdqm():
    try:
        if "username" not in session:
            return redirect(url_for("login"))
        return render_template(
            "generali_pdqm.html",
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            page_visibility=page_visibility(),
            organizationcode=session.get("organizationcode"),
            can_add=has_permission("tenant.generali.pdqm.add"),
            can_add_bypass_deadline=has_permission("tenant.generali.pdqm.add.pastdeadline"),
            can_edit=has_permission("tenant.generali.pdqm.edit.org")
            or has_permission("tenant.generali.pdqm.edit.all"),
            can_edit_transorg=has_permission("tenant.generali.pdqm.edit.all"),
            can_delete=has_permission("tenant.generali.pdqm.delete.org")
            or has_permission("tenant.generali.pdqm.delete.all"),
            can_delete_transorg=has_permission("tenant.generali.pdqm.delete.all"),
            can_add_for_org=has_permission("tenant.generali.pdqm.add.org"),
            can_add_transorg=has_permission("tenant.generali.pdqm.add.all"),
        )
    except Exception as e:
        current_app.logger.error(f"Error loading Generali PDQM: {e}")
        return render_template("handlers/500.html"), 500


@require_permission("tenant.generali.pdqm.view")
def api_generali_pdqm_categories():
    conn = None
    try:
        # local import: re-resolve against the live package object so test
        # monkeypatching of gv.engine_generali_db works consistently across
        # the generali package
        from . import engine_generali_db

        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT ParentCategory, ParentSubCategory, SubCategory
            FROM [Generali].[dbo].[QualityCheckCategories]
            ORDER BY ParentCategory, ParentSubCategory, SubCategory
        """)
        rows = cursor.fetchall()
        cursor.close()

        # nested: { parent: { parentSub_or_"": [sub, ...] } }
        grouped: dict[str, dict] = {}
        for parent, parent_sub, sub in rows:
            if parent not in grouped:
                grouped[parent] = {}
            key = parent_sub if parent_sub is not None else ""
            if key not in grouped[parent]:
                grouped[parent][key] = []
            if sub:
                grouped[parent][key].append(sub)

        locale = str(get_locale() or "de").split("_")[0]
        translations = {}
        if locale != "de":
            cursor2 = conn.cursor()
            cursor2.execute(
                """
                SELECT OriginalValue, TranslatedValue
                FROM [Generali].[dbo].[CategoryTranslations] WITH (NOLOCK)
                WHERE SourceTable = 'QualityCheckCategories' AND Locale = ?
            """,
                [locale],
            )
            translations = dict(cursor2.fetchall())
            cursor2.close()

        return jsonify({"success": True, "categories": grouped, "translations": translations})
    except Exception as e:
        current_app.logger.error(f"Generali PDQM Categories Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


def _monthreport_row(r):
    return {
        "category": r[0] or "—",
        "entries": r[1],
        "total_quantity": int(r[2] or 0),
    }


def _monthreport_summary(rows):
    return {
        "total_entries": sum(r["entries"] for r in rows),
        "total_quantity": sum(r["total_quantity"] for r in rows),
    }


def _list_record(r, user_info):
    rec_id, qty, user_id, for_date, parent, parent_sub, sub, recorded_at = r
    return {
        "id": rec_id,
        "quantity": int(qty) if qty is not None else None,
        "userId": user_id,
        "fullname": user_info.get("fullname"),
        "orgCode": user_info.get("orgCode"),
        "forDate": str(for_date) if for_date else None,
        "parentCategory": parent,
        "parentSubCategory": parent_sub,
        "subCategory": sub,
        "recordDateTime": recorded_at.isoformat() if recorded_at else None,
    }


PDQM = CrudTable(
    slug="pdqm",
    table="[Generali].[dbo].[QualityCheckEntries]",
    user_column="UserID",
    perm_prefix="tenant.generali.pdqm",
    api_base="/api/generali/pdqm",
    label="Generali PDQM",
    user_lookup_label="PDQM",
    monthreport_url="/generali/pdqm/monthreport",
    monthreport_endpoint="generali_pdqm_monthreport",
    monthreport=CrudMonthReport(
        section="pdqm",
        section_title="Generali PDQM",
        back_endpoint="generali_pdqm",
        date_column="ForDate",
        group_column="ParentCategory",
        # PDQM counts items, not hours -- quantity is an integer throughout
        measures="COUNT(*) AS entries, ISNULL(SUM(Quantity), 0) AS total_quantity",
        row_builder=_monthreport_row,
        summary=_monthreport_summary,
    ),
    list_spec=CrudList(
        select=(
            "ID, Quantity, UserID, ForDate, ParentCategory, ParentSubCategory, "
            "SubCategory, RecordDateTime"
        ),
        order_by="ForDate DESC, RecordDateTime DESC",
        filters=(
            Filter("startDate", "ForDate", "gte"),
            Filter("endDate", "ForDate", "lte"),
            Filter("parentCategory", "ParentCategory"),
            # tri-state: absent = unfiltered, "" = IS NULL, else equality
            Filter("parentSubCategory", "ParentSubCategory", "eq_or_null"),
            Filter("subCategory", "SubCategory"),
            SCOPE,
            Filter("userId", "UserID"),
        ),
        aggregate=("SUM(Quantity)", "totalQuantity", lambda v: int(v) if v is not None else 0),
        user_index=2,
        record=_list_record,
    ),
    write=CrudWrite(
        fields=(
            Field("ForDate", json="forDate", required=True),
            Field("ParentCategory", json="parentCategory", required=True),
            Field("ParentSubCategory", json="parentSubCategory", kind="blank_null"),
            Field("SubCategory", json="subCategory", kind="opt_str"),
            Field(
                "Quantity",
                json="quantity",
                kind="int",
                required=True,
                minimum=1,
                error="Invalid quantity",
            ),
        ),
        date_json="forDate",
        insert_order=(
            "Quantity",
            "ForDate",
            "UserID",
            "RecordDateTime",
            "ParentCategory",
            "ParentSubCategory",
            "SubCategory",
        ),
        update_order=("ForDate", "ParentCategory", "ParentSubCategory", "SubCategory", "Quantity"),
    ),
)

api_generali_pdqm_org_users = PDQM.views["org_users"]
api_generali_pdqm_organizations = PDQM.views["organizations"]
api_generali_pdqm_filter_users = PDQM.views["filter_users"]
api_generali_pdqm_list = PDQM.views["list"]
api_generali_pdqm_add = PDQM.views["add"]
api_generali_pdqm_edit = PDQM.views["edit"]
api_generali_pdqm_delete = PDQM.views["delete"]
generali_pdqm_monthreport = PDQM.views["monthreport"]

for _name, _fn in (
    ("api_generali_pdqm_org_users", api_generali_pdqm_org_users),
    ("api_generali_pdqm_organizations", api_generali_pdqm_organizations),
    ("api_generali_pdqm_filter_users", api_generali_pdqm_filter_users),
    ("api_generali_pdqm_list", api_generali_pdqm_list),
    ("api_generali_pdqm_add", api_generali_pdqm_add),
    ("api_generali_pdqm_edit", api_generali_pdqm_edit),
    ("api_generali_pdqm_delete", api_generali_pdqm_delete),
    ("generali_pdqm_monthreport", generali_pdqm_monthreport),
):
    _fn.__name__ = _name
    _fn.__qualname__ = _name
del _name, _fn


def register_routes(app):
    app.add_url_rule("/generali/pdqm", endpoint="generali_pdqm", view_func=generali_pdqm)
    app.add_url_rule(
        "/api/generali/pdqm/categories",
        endpoint="api_generali_pdqm_categories",
        view_func=api_generali_pdqm_categories,
        methods=["GET"],
    )
    register_crud(app, PDQM)
