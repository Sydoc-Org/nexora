"""Generali tenant: Reporting."""

from datetime import date, timedelta

from flask import current_app, jsonify, redirect, render_template, request, session, url_for
from flask_babel import gettext as _

from ...db import engine_generali_db, engine_nexora_db
from ...security import (
    _check_add_deadline,
    _check_generali_record_org,
    has_permission,
    page_visibility,
    require_any_permission,
    require_permission,
)
from ._scope import _generali_orgs_for_userids, _generali_scope_where

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


@require_permission("generali.reporting.view")
def generali_reporting_monthreport():
    try:
        if "username" not in session:
            return redirect(url_for("login"))

        today = date.today()
        try:
            year = int(request.args.get("year", today.year))
            month = int(request.args.get("month", today.month))
        except (TypeError, ValueError):
            year, month = today.year, today.month
        month = max(1, min(12, month))
        year = max(2000, min(today.year, year))

        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)

        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        is_current_month = year == today.year and month == today.month
        month_label = first_day.strftime("%B %Y")

        conn = None
        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT category,
                   COUNT(*) AS entries,
                   SUM(CAST(ontime AS INT)) AS on_time_count
            FROM [dbo].[reportingiss]
            WHERE ReportForDate >= ? AND ReportForDate <= ?
            GROUP BY category
            ORDER BY category
        """,
            [str(first_day), str(last_day)],
        )
        rows_raw = cursor.fetchall()
        cursor.close()

        rows = [
            {
                "category": REPORTING_CATEGORY_LABELS.get(r[0], r[0]),
                "entries": r[1],
                "on_time": r[2] or 0,
                "late": r[1] - (r[2] or 0),
                "pct": round((r[2] or 0) / r[1] * 100, 1) if r[1] else 0.0,
            }
            for r in rows_raw
        ]

        total_on_time = sum(r["on_time"] for r in rows)
        total_entries = sum(r["entries"] for r in rows)
        summary = {
            "total_entries": total_entries,
            "on_time": total_on_time,
            "late": total_entries - total_on_time,
            "pct_on_time": round(total_on_time / total_entries * 100, 1) if total_entries else 0.0,
        }

        return render_template(
            "generali_monthreport.html",
            logged_in_user=session.get("username"),
            page_visibility=page_visibility(),
            section="reporting",
            section_title="Generali Reporting",
            back_url=url_for("generali_reporting"),
            year=year,
            month=month,
            month_label=month_label,
            prev_year=prev_year,
            prev_month=prev_month,
            next_year=next_year,
            next_month=next_month,
            is_current_month=is_current_month,
            summary=summary,
            rows=rows,
        )
    except Exception as e:
        current_app.logger.error(f"Error loading Generali Reporting Month Report: {e}")
        return render_template("handlers/500.html"), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.reporting.view")
def api_generali_reporting_organizations():
    conn = None
    try:
        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT ReportByUserID FROM [dbo].[reportingiss] WHERE ReportByUserID IS NOT NULL"
        )
        user_ids = [r[0] for r in cursor.fetchall()]
        cursor.close()
        return jsonify({"success": True, "organizations": _generali_orgs_for_userids(user_ids)})
    except Exception as e:
        current_app.logger.error(f"Generali Reporting Organizations Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.reporting.view")
def api_generali_reporting_filter_users():
    try:
        transorg = has_permission("generali.reporting.edit.transorganizational")
        org_edit = has_permission("generali.reporting.edit.organizational")
        if not transorg and not org_edit:
            return jsonify({"success": True, "users": []})
        gen_conn = engine_generali_db.raw_connection()
        gen_cur = gen_conn.cursor()
        gen_cur.execute(
            "SELECT DISTINCT ReportByUserID FROM [dbo].[reportingiss] WHERE ReportByUserID IS NOT NULL"
        )
        user_ids = [r[0] for r in gen_cur.fetchall()]
        gen_cur.close()
        gen_conn.close()
        if not user_ids:
            return jsonify({"success": True, "users": []})
        placeholders = ",".join(["?"] * len(user_ids))
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        if transorg:
            cursor.execute(
                f"SELECT userid, fullname FROM Users WHERE userid IN ({placeholders}) ORDER BY fullname",
                user_ids,
            )
        else:
            cursor.execute(
                f"SELECT userid, fullname FROM Users WHERE userid IN ({placeholders}) AND organizationcode = ? ORDER BY fullname",
                [*user_ids, session.get("organizationcode")],
            )
        users = [{"userId": row[0], "fullname": row[1]} for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return jsonify({"success": True, "users": users})
    except Exception as e:
        current_app.logger.error(f"Generali Reporting FilterUsers Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500


@require_permission("generali.reporting.view")
def api_generali_reporting_list():
    conn = None
    try:
        # local import: re-resolve against the live package object so test
        # monkeypatching of gv.engine_generali_db / gv.engine_nexora_db still
        # works post-split (nx_lib/views/generali/__init__.py owns these
        # names; the top-of-file import above would bind a stale copy at
        # import time for this call path).
        from . import engine_generali_db, engine_nexora_db

        page = max(1, int(request.args.get("page", 1)))
        per_page = 20
        offset = (page - 1) * per_page

        start_date = request.args.get("startDate", "").strip()
        end_date = request.args.get("endDate", "").strip()
        category = request.args.get("category", "").strip()
        org_code = request.args.get("organizationcode", "").strip()
        user_id = request.args.get("userId", "").strip()
        on_time_str = request.args.get("onTime", "").strip().lower()

        where_clauses = []
        params = []

        if start_date:
            where_clauses.append("ReportForDate >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("ReportForDate <= ?")
            params.append(end_date)
        if category and category in REPORTING_CATEGORIES:
            where_clauses.append("category = ?")
            params.append(category)
        if user_id:
            where_clauses.append("ReportByUserID = ?")
            params.append(user_id)
        if on_time_str in ("true", "false"):
            where_clauses.append("ontime = ?")
            params.append(1 if on_time_str == "true" else 0)

        scope_clauses, scope_params = _generali_scope_where(
            "generali.reporting", "ReportByUserID", org_code
        )
        where_clauses.extend(scope_clauses)
        params.extend(scope_params)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(f"SELECT COUNT(*) FROM [dbo].[reportingiss] {where_sql}", params)
        total_records = cursor.fetchone()[0]
        total_pages = max(1, -(-total_records // per_page))

        fetch_all = request.args.get("all", "").lower() == "true"
        pagination_sql = "" if fetch_all else "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        sql_params = params if fetch_all else [*params, offset, per_page]
        cursor.execute(
            f"""
            SELECT ID, ReportForDate, ReportTimeStamp, ReportByUserID, ontime, category
                   --,EmailReceivedTimeStamp, DeliveryTimeStamp, LatestDeliveryTimeStamp, MailRoomRequestTimeStamp
            FROM [dbo].[reportingiss]
            {where_sql}
            ORDER BY ReportForDate DESC, ReportTimeStamp DESC
            {pagination_sql}
        """,
            sql_params,
        )

        rows = cursor.fetchall()
        cursor.close()

        user_ids = list({r[3] for r in rows if r[3] is not None})
        user_map = {}
        if user_ids:
            try:
                nx_conn = engine_nexora_db.raw_connection()
                nx_cur = nx_conn.cursor()
                placeholders = ",".join(["?"] * len(user_ids))
                nx_cur.execute(
                    f"SELECT userid, fullname, organizationcode FROM Users WHERE userid IN ({placeholders})",
                    user_ids,
                )
                for uid, fullname, orgcode in nx_cur.fetchall():
                    user_map[uid] = {"fullname": fullname, "orgCode": orgcode}
                nx_cur.close()
                nx_conn.close()
            except Exception as ue:
                current_app.logger.warning(f"User lookup failed for reporting: {ue}")

        records = []
        for r in rows:
            # , email_rcvd, delivery_ts, latest_ts, mailroom_ts
            rec_id, report_date, report_ts, user_id, ontime, cat = r
            user_info = user_map.get(user_id, {})
            records.append(
                {
                    "id": rec_id,
                    "reportForDate": str(report_date) if report_date else None,
                    "reportTimeStamp": report_ts.isoformat() if report_ts else None,
                    "reportByUserID": user_id,
                    "fullname": user_info.get("fullname"),
                    "orgCode": user_info.get("orgCode"),
                    "ontime": bool(ontime),
                    "category": cat,
                }
            )
            # 'emailReceivedTimeStamp':   email_rcvd.isoformat() if email_rcvd else None,
            #     'deliveryTimeStamp':        delivery_ts.isoformat() if delivery_ts else None,
            #     'latestDeliveryTimeStamp':  latest_ts.isoformat() if latest_ts else None,
            #     'mailRoomRequestTimeStamp': mailroom_ts.isoformat() if mailroom_ts else None,

        return jsonify(
            {
                "success": True,
                "records": records,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_records": total_records,
                    "total_pages": total_pages,
                },
            }
        )
    except Exception as e:
        current_app.logger.error(f"Generali Reporting List Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.reporting.add")
def api_generali_reporting_add():
    conn = None
    try:
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
    conn = None
    try:
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


@require_any_permission(
    "generali.reporting.delete.organizational", "generali.reporting.delete.transorganizational"
)
def api_generali_reporting_delete(record_id):
    conn = None
    try:
        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        if not has_permission("generali.reporting.delete.transorganizational"):
            _check_generali_record_org(cursor, "[dbo].[reportingiss]", "ReportByUserID", record_id)
        cursor.execute("DELETE FROM [dbo].[reportingiss] WHERE ID = ?", [record_id])
        conn.commit()
        cursor.close()
        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Generali Reporting Delete Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


def register_routes(app):
    app.add_url_rule(
        "/generali/reporting", endpoint="generali_reporting", view_func=generali_reporting
    )
    app.add_url_rule(
        "/generali/reporting/monthreport",
        endpoint="generali_reporting_monthreport",
        view_func=generali_reporting_monthreport,
    )
    app.add_url_rule(
        "/api/generali/reporting/organizations",
        endpoint="api_generali_reporting_organizations",
        view_func=api_generali_reporting_organizations,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/reporting/filterUsers",
        endpoint="api_generali_reporting_filter_users",
        view_func=api_generali_reporting_filter_users,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/reporting",
        endpoint="api_generali_reporting_list",
        view_func=api_generali_reporting_list,
        methods=["GET"],
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
    app.add_url_rule(
        "/api/generali/reporting/<int:record_id>",
        endpoint="api_generali_reporting_delete",
        view_func=api_generali_reporting_delete,
        methods=["DELETE"],
    )
