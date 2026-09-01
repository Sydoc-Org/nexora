"""Generali tenant: Reporting.

Reporting is the outlier of the five CRUD tables: it has no per-user "book for
someone else" flow, its add endpoint enforces a one-report-per-day/category rule,
and its edit takes the record id in the PUT body instead of the URL. Those three
views (plus the page) stay hand-written; the families that genuinely match the
siblings -- month report, organizations, filter users, list and delete -- are
generated from the ``REPORTING`` descriptor by ``._crud`` and bound below under
their original function names (see that module's docstring).
"""

from flask import current_app, jsonify, redirect, render_template, request, session, url_for
from flask_babel import gettext as _

from ...security import (
    _check_add_deadline,
    _check_generali_record_org,
    has_permission,
    page_visibility,
    require_any_permission,
    require_permission,
)
from ._crud import (
    SCOPE,
    CrudList,
    CrudMonthReport,
    CrudTable,
    Filter,
    register_crud,
)

# ----------------------------- Generali Reporting --------------------------- #
REPORTING_CATEGORIES = {
    "export_post",
    "export_post_scan",
    "provision_archive",
    "stray_document_digital",
    "stray_document_physical",
}
REPORTING_CATEGORY_LABELS = {
    "export_post": "KPI 1: Delivery physical post",
    "export_post_scan": "KPI 2: Delivery physical post with scanning",
    "provision_archive": "KPI 3: Provision of Archival Records",
    "stray_document_digital": "KPI 12: Stray document (digital)",
    "stray_document_physical": "KPI 13: Stray document (physical)",
}


@require_permission("generali.reporting.view")
def generali_reporting():
    try:
        if "username" not in session:
            return redirect(url_for("login"))
        return render_template(
            "generali_reporting.html",
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            page_visibility=page_visibility(),
            organizationcode=session.get("organizationcode"),
            can_add=has_permission("generali.reporting.add"),
            can_add_bypass_deadline=has_permission("generali.reporting.add.bypass.deadline"),
            can_edit=has_permission("generali.reporting.edit.organizational")
            or has_permission("generali.reporting.edit.transorganizational"),
            can_edit_transorg=has_permission("generali.reporting.edit.transorganizational"),
            can_delete=has_permission("generali.reporting.delete.organizational")
            or has_permission("generali.reporting.delete.transorganizational"),
            can_delete_transorg=has_permission("generali.reporting.delete.transorganizational"),
        )
    except Exception as e:
        current_app.logger.error(f"Error loading Generali Reporting: {e}")
        return render_template("handlers/500.html"), 500


def _monthreport_row(r):
    return {
        "category": REPORTING_CATEGORY_LABELS.get(r[0], r[0]),
        "entries": r[1],
        "on_time": r[2] or 0,
        "late": r[1] - (r[2] or 0),
        "pct": round((r[2] or 0) / r[1] * 100, 1) if r[1] else 0.0,
    }


def _monthreport_summary(rows):
    total_on_time = sum(r["on_time"] for r in rows)
    total_entries = sum(r["entries"] for r in rows)
    return {
        "total_entries": total_entries,
        "on_time": total_on_time,
        "late": total_entries - total_on_time,
        "pct_on_time": round(total_on_time / total_entries * 100, 1) if total_entries else 0.0,
    }


def _list_record(r, user_info):
    # , email_rcvd, delivery_ts, latest_ts, mailroom_ts
    rec_id, report_date, report_ts, user_id, ontime, cat = r
    return {
        "id": rec_id,
        "reportForDate": str(report_date) if report_date else None,
        "reportTimeStamp": report_ts.isoformat() if report_ts else None,
        "reportByUserID": user_id,
        "fullname": user_info.get("fullname"),
        "orgCode": user_info.get("orgCode"),
        "ontime": bool(ontime),
        "category": cat,
    }
    # 'emailReceivedTimeStamp':   email_rcvd.isoformat() if email_rcvd else None,
    #     'deliveryTimeStamp':        delivery_ts.isoformat() if delivery_ts else None,
    #     'latestDeliveryTimeStamp':  latest_ts.isoformat() if latest_ts else None,
    #     'mailRoomRequestTimeStamp': mailroom_ts.isoformat() if mailroom_ts else None,


REPORTING = CrudTable(
    slug="reporting",
    table="[dbo].[reportingiss]",
    user_column="ReportByUserID",
    perm_prefix="generali.reporting",
    view_perm="generali.reporting.view",
    api_base="/api/generali/reporting",
    label="Generali Reporting",
    user_lookup_label="reporting",
    # Reporting books only for the caller, so it has no orgUsers picker, and
    # its organizations list is deliberately NOT restricted to own records.
    has_org_users=False,
    organizations_restrict=False,
    monthreport_url="/generali/reporting/monthreport",
    monthreport_endpoint="generali_reporting_monthreport",
    monthreport=CrudMonthReport(
        section="reporting",
        section_title="Generali Reporting",
        back_endpoint="generali_reporting",
        date_column="ReportForDate",
        group_column="category",
        # on-time ratio, not an effort/quantity total
        measures="COUNT(*) AS entries, SUM(CAST(ontime AS INT)) AS on_time_count",
        row_builder=_monthreport_row,
        summary=_monthreport_summary,
        # the month report is org-wide for every viewer, unlike the siblings'
        self_restrict=False,
    ),
    list_spec=CrudList(
        select=(
            "ID, ReportForDate, ReportTimeStamp, ReportByUserID, ontime, category\n"
            "--,EmailReceivedTimeStamp, DeliveryTimeStamp, LatestDeliveryTimeStamp,"
            " MailRoomRequestTimeStamp"
        ),
        order_by="ReportForDate DESC, ReportTimeStamp DESC",
        filters=(
            Filter("startDate", "ReportForDate", "gte"),
            Filter("endDate", "ReportForDate", "lte"),
            Filter("category", "category", "eq_in_set", REPORTING_CATEGORIES),
            Filter("userId", "ReportByUserID"),
            Filter("onTime", "ontime", "bool"),
            SCOPE,
        ),
        # no effort/quantity column: the list reports counts only
        aggregate=None,
        user_index=3,
        record=_list_record,
    ),
)

api_generali_reporting_organizations = REPORTING.views["organizations"]
api_generali_reporting_filter_users = REPORTING.views["filter_users"]
api_generali_reporting_list = REPORTING.views["list"]
api_generali_reporting_delete = REPORTING.views["delete"]
generali_reporting_monthreport = REPORTING.views["monthreport"]

for _name, _fn in (
    ("api_generali_reporting_organizations", api_generali_reporting_organizations),
    ("api_generali_reporting_filter_users", api_generali_reporting_filter_users),
    ("api_generali_reporting_list", api_generali_reporting_list),
    ("api_generali_reporting_delete", api_generali_reporting_delete),
    ("generali_reporting_monthreport", generali_reporting_monthreport),
):
    _fn.__name__ = _name
    _fn.__qualname__ = _name
del _name, _fn


@require_permission("generali.reporting.add")
def api_generali_reporting_add():
    """Hand-written: books only for the caller and rejects a duplicate report for
    the same date+category, which no sibling table does."""
    conn = None
    try:
        # local import: re-resolve against the live package object so test
        # monkeypatching of gv.engine_generali_db works consistently across
        # the generali package
        from . import engine_generali_db

        body = request.get_json(force=True)
        report_for_date = body.get("reportForDate", "").strip()
        category = body.get("category", "").strip()
        ontime = bool(body.get("ontime", False))
        user_id = session.get("userid")
        # email_received    = body.get('emailReceivedTimeStamp') or None
        # mailroom_request  = body.get('mailRoomRequestTimeStamp') or None
        # delivery          = body.get('deliveryTimeStamp') or None
        # latest_delivery   = body.get('latestDeliveryTimeStamp') or None

        # email_received   = email_received.replace('T',' ') if email_received else None
        # mailroom_request = mailroom_request.replace('T',' ') if mailroom_request else None
        # delivery         = delivery.replace('T',' ') if delivery else None
        # latest_delivery  = latest_delivery.replace('T',' ') if latest_delivery else None

        if not report_for_date:
            return jsonify({"success": False, "error": "reportForDate is required"}), 400
        if category not in REPORTING_CATEGORIES:
            return jsonify({"success": False, "error": "Invalid category"}), 400
        deadline_err = _check_add_deadline(
            report_for_date, "generali.reporting.add.bypass.deadline"
        )
        if deadline_err:
            return jsonify({"success": False, "error": deadline_err}), 403

        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()

        multi_allowed = {"provision_archive", "stray_document_digital", "stray_document_physical"}
        if category not in multi_allowed:
            cursor.execute(
                """
                SELECT COUNT(*) FROM [dbo].[reportingiss]
                WHERE ReportForDate = ? AND ReportByUserID = ? AND category = ?
            """,
                [report_for_date, user_id, category],
            )
            if cursor.fetchone()[0] > 0:
                return jsonify(
                    {
                        "success": False,
                        "error": "A report for this date and category already exists.",
                    }
                ), 409

        cursor.execute(
            """
            INSERT INTO [dbo].[reportingiss]
                (ReportForDate, ReportTimeStamp, ReportByUserID, ontime, category
                 --,EmailReceivedTimeStamp, DeliveryTimeStamp, LatestDeliveryTimeStamp, MailRoomRequestTimeStamp
                       )
            VALUES (?, GETDATE(), ?, ?, ?)
        """,
            [
                report_for_date,
                user_id,
                1 if ontime else 0,
                category,
                #   ,email_received, delivery, latest_delivery, mailroom_request
            ],
        )
        conn.commit()

        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Generali Reporting Add Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_any_permission(
    "generali.reporting.edit.organizational", "generali.reporting.edit.transorganizational"
)
def api_generali_reporting_edit():
    """Hand-written: PUTs to the collection URL and takes the record id in the
    body, unlike every sibling's PUT /<int:record_id>."""
    conn = None
    try:
        # local import: re-resolve against the live package object so test
        # monkeypatching of gv.engine_generali_db works consistently across
        # the generali package
        from . import engine_generali_db

        body = request.get_json(force=True)
        record_id = body.get("id")
        report_for_date = (body.get("reportForDate") or "").strip()
        ontime = bool(body.get("ontime", False))
        # email_received  = body.get('emailReceivedTimeStamp') or None
        # mailroom_req    = body.get('mailRoomRequestTimeStamp') or None
        # delivery        = body.get('deliveryTimeStamp') or None
        # latest_delivery = body.get('latestDeliveryTimeStamp') or None

        if not record_id or not report_for_date:
            return jsonify({"success": False, "error": "id and reportForDate are required"}), 400

        # if email_received:  email_received  = email_received.replace('T', ' ')
        # if mailroom_req:    mailroom_req    = mailroom_req.replace('T', ' ')
        # if delivery:        delivery        = delivery.replace('T', ' ')
        # if latest_delivery: latest_delivery = latest_delivery.replace('T', ' ')

        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        if not has_permission("generali.reporting.edit.transorganizational"):
            _check_generali_record_org(cursor, "[dbo].[reportingiss]", "ReportByUserID", record_id)
        cursor.execute(
            """
            UPDATE [dbo].[reportingiss]
            SET ReportForDate            = ?,
                ontime                   = ?
                --,EmailReceivedTimeStamp   = ?,
                --MailRoomRequestTimeStamp = ?,
                --DeliveryTimeStamp        = ?,
                --LatestDeliveryTimeStamp  = ?
            WHERE ID = ?
        """,
            [
                report_for_date,
                1 if ontime else 0,
                #   email_received, mailroom_req, delivery, latest_delivery,
                record_id,
            ],
        )
        conn.commit()

        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Generali Reporting Edit Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


def register_routes(app):
    app.add_url_rule(
        "/generali/reporting", endpoint="generali_reporting", view_func=generali_reporting
    )
    app.add_url_rule(
        "/api/generali/reporting",
        endpoint="api_generali_reporting_add",
        view_func=api_generali_reporting_add,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/generali/reporting",
        endpoint="api_generali_reporting_edit",
        view_func=api_generali_reporting_edit,
        methods=["PUT"],
    )
    register_crud(app, REPORTING)
