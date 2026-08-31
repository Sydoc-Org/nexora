"""Generali tenant: Base Services."""

from datetime import date, timedelta

from flask import current_app, jsonify, redirect, render_template, request, session, url_for
from flask_babel import gettext as _

from ...db import engine_generali_db, engine_nexora_db
from ...security import (
    PermissionDenied,
    _check_add_deadline,
    _check_generali_record_org,
    has_permission,
    page_visibility,
    require_any_permission,
    require_permission,
)
from ._scope import _generali_orgs_for_userids, _generali_scope_where

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


@require_permission("generali.baseservices.view")
def generali_baseservices_monthreport():
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

        where_clauses = ["ForDate >= ?", "ForDate <= ?"]
        params = [str(first_day), str(last_day)]
        if not has_permission("generali.baseservices.edit.organizational") and not has_permission(
            "generali.baseservices.edit.transorganizational"
        ):
            where_clauses.append("UserID = ?")
            params.append(session.get("userid"))
        where_sql = "WHERE " + " AND ".join(where_clauses)

        conn = None
        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT Category,
                   COUNT(*) AS entries,
                   ISNULL(SUM(EffortInHours), 0) AS total_hours
            FROM [Generali].[dbo].[BaseServices]
            {where_sql}
            GROUP BY Category
            ORDER BY Category
        """,
            params,
        )
        rows_raw = cursor.fetchall()
        cursor.close()

        rows = [
            {
                "category": r[0] or "—",
                "entries": r[1],
                "total_hours": round(float(r[2] or 0), 2),
            }
            for r in rows_raw
        ]

        summary = {
            "total_entries": sum(r["entries"] for r in rows),
            "total_hours": round(sum(r["total_hours"] for r in rows), 2),
        }

        return render_template(
            "generali_monthreport.html",
            logged_in_user=session.get("username"),
            page_visibility=page_visibility(),
            section="baseservices",
            section_title="Generali Base Services",
            back_url=url_for("generali_base_services"),
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
        current_app.logger.error(f"Error loading Generali Base Services Month Report: {e}")
        return render_template("handlers/500.html"), 500
    finally:
        if conn:
            conn.close()


@require_any_permission(
    "generali.baseservices.add.organizational", "generali.baseservices.add.transorganizational"
)
def api_generali_baseservices_org_users():
    conn = None
    try:
        transorg = has_permission("generali.baseservices.add.transorganizational")
        org_code = session.get("organizationcode")
        if not transorg and not org_code:
            return jsonify({"success": False, "error": "No organization on session"}), 400

        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        if transorg:
            cursor.execute("SELECT userid, fullname FROM Users ORDER BY fullname")
        else:
            cursor.execute(
                "SELECT userid, fullname FROM Users WHERE organizationcode = ? ORDER BY fullname",
                [org_code],
            )
        users = [{"userId": row[0], "fullname": row[1]} for row in cursor.fetchall()]
        cursor.close()
        return jsonify({"success": True, "users": users})
    except Exception as e:
        current_app.logger.error(f"Generali Base Services OrgUsers Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.baseservices.view")
def api_generali_baseservices_organizations():
    conn = None
    try:
        restrict_to_self = not has_permission(
            "generali.baseservices.edit.organizational"
        ) and not has_permission("generali.baseservices.edit.transorganizational")
        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        if restrict_to_self:
            cursor.execute(
                "SELECT DISTINCT UserID FROM [Generali].[dbo].[BaseServices] WHERE UserID IS NOT NULL AND UserID = ?",
                [session.get("userid")],
            )
        else:
            cursor.execute(
                "SELECT DISTINCT UserID FROM [Generali].[dbo].[BaseServices] WHERE UserID IS NOT NULL"
            )
        user_ids = [r[0] for r in cursor.fetchall()]
        cursor.close()
        return jsonify({"success": True, "organizations": _generali_orgs_for_userids(user_ids)})
    except Exception as e:
        current_app.logger.error(f"Generali Base Services Organizations Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.baseservices.view")
def api_generali_baseservices_filter_users():
    try:
        transorg = has_permission("generali.baseservices.edit.transorganizational")
        org_edit = has_permission("generali.baseservices.edit.organizational")
        if not transorg and not org_edit:
            return jsonify({"success": True, "users": []})
        gen_conn = engine_generali_db.raw_connection()
        gen_cur = gen_conn.cursor()
        gen_cur.execute(
            "SELECT DISTINCT UserID FROM [Generali].[dbo].[BaseServices] WHERE UserID IS NOT NULL"
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
        current_app.logger.error(f"Generali BaseServices FilterUsers Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500


@require_permission("generali.baseservices.view")
def api_generali_baseservices_list():
    conn = None
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = 20
        offset = (page - 1) * per_page

        start_date = request.args.get("startDate", "").strip()
        end_date = request.args.get("endDate", "").strip()
        category = request.args.get("category", "").strip()
        org_code = request.args.get("organizationcode", "").strip()
        user_id = request.args.get("userId", "").strip()

        where_clauses = []
        params = []

        if start_date:
            where_clauses.append("ForDate >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("ForDate <= ?")
            params.append(end_date)
        if category:
            where_clauses.append("Category = ?")
            params.append(category)

        scope_clauses, scope_params = _generali_scope_where(
            "generali.baseservices", "UserID", org_code
        )
        where_clauses.extend(scope_clauses)
        params.extend(scope_params)
        if user_id:
            where_clauses.append("UserID = ?")
            params.append(user_id)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            f"SELECT COUNT(*), SUM(EffortInHours) FROM [Generali].[dbo].[BaseServices] {where_sql}",
            params,
        )
        agg = cursor.fetchone()
        total_records = agg[0] or 0
        total_hours = float(agg[1]) if agg[1] is not None else 0.0
        total_pages = max(1, -(-total_records // per_page))

        fetch_all = request.args.get("all", "").lower() == "true"
        pagination_sql = "" if fetch_all else "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        sql_params = params if fetch_all else [*params, offset, per_page]
        cursor.execute(
            f"""
            SELECT ID, EffortInHours, UserID, ForDate, Category, RecordDateTime
            FROM [Generali].[dbo].[BaseServices]
            {where_sql}
            ORDER BY ForDate DESC, RecordDateTime DESC
            {pagination_sql}
        """,
            sql_params,
        )

        rows = cursor.fetchall()
        cursor.close()

        user_ids = list({r[2] for r in rows if r[2] is not None})
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
                current_app.logger.warning(f"User lookup failed for base services: {ue}")

        records = []
        for r in rows:
            rec_id, effort, user_id, for_date, category_val, recorded_at = r
            user_info = user_map.get(user_id, {})
            records.append(
                {
                    "id": rec_id,
                    "effortInHours": float(effort) if effort is not None else None,
                    "userId": user_id,
                    "fullname": user_info.get("fullname"),
                    "orgCode": user_info.get("orgCode"),
                    "forDate": str(for_date) if for_date else None,
                    "category": category_val,
                    "recordDateTime": recorded_at.isoformat() if recorded_at else None,
                }
            )

        return jsonify(
            {
                "success": True,
                "records": records,
                "totalHours": total_hours,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_records": total_records,
                    "total_pages": total_pages,
                },
            }
        )
    except Exception as e:
        current_app.logger.error(f"Generali Base Services List Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


VALID_BASE_CATEGORIES = {"Physical Mailroom, AVOR & Scanning", "Nk1 & NK2", "POE", "PPR"}


@require_permission("generali.baseservices.add")
def api_generali_baseservices_add():
    conn = None
    try:
        body = request.get_json(force=True)
        for_date = body.get("forDate", "").strip()
        category = body.get("category", "").strip()
        effort = body.get("effortInHours")
        caller_id = session.get("userid")
        target_raw = body.get("userId")
        user_id = caller_id

        if target_raw is not None and str(target_raw) != str(caller_id):
            has_org_perm = has_permission("generali.baseservices.add.organizational")
            has_transorg_perm = has_permission("generali.baseservices.add.transorganizational")
            if not has_org_perm and not has_transorg_perm:
                raise PermissionDenied()
            try:
                target_id = int(target_raw)
            except (TypeError, ValueError):
                return jsonify({"success": False, "error": "Invalid userId"}), 400

            if not has_transorg_perm:
                nx_conn = engine_nexora_db.raw_connection()
                nx_cur = nx_conn.cursor()
                nx_cur.execute("SELECT organizationcode FROM Users WHERE userid = ?", [target_id])
                row = nx_cur.fetchone()
                nx_cur.close()
                nx_conn.close()
                if not row or row[0] != session.get("organizationcode"):
                    return jsonify(
                        {"success": False, "error": "Target user not in your organization"}
                    ), 403
            user_id = target_id

        deadline_err = _check_add_deadline(for_date, "generali.baseservices.add.bypass.deadline")
        if deadline_err:
            return jsonify({"success": False, "error": deadline_err}), 403
        if not for_date or not category or effort is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        if category not in VALID_BASE_CATEGORIES:
            return jsonify({"success": False, "error": "Invalid category"}), 400
        try:
            effort = float(effort)
            if effort <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid effort value"}), 400

        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO [Generali].[dbo].[BaseServices]
                (EffortInHours, UserID, ForDate, Category, RecordDateTime)
            VALUES (?, ?, ?, ?, GETDATE())
        """,
            [effort, user_id, for_date, category],
        )
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Generali Base Services Add Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_any_permission(
    "generali.baseservices.edit.organizational", "generali.baseservices.edit.transorganizational"
)
def api_generali_baseservices_edit(record_id):
    conn = None
    try:
        body = request.get_json(force=True)
        for_date = body.get("forDate", "").strip()
        category = body.get("category", "").strip()
        effort = body.get("effortInHours")

        if not for_date or not category or effort is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        if category not in VALID_BASE_CATEGORIES:
            return jsonify({"success": False, "error": "Invalid category"}), 400
        try:
            effort = float(effort)
            if effort <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid effort value"}), 400

        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        if not has_permission("generali.baseservices.edit.transorganizational"):
            _check_generali_record_org(
                cursor, "[Generali].[dbo].[BaseServices]", "UserID", record_id
            )
        cursor.execute(
            """
            UPDATE [Generali].[dbo].[BaseServices]
            SET ForDate = ?, Category = ?, EffortInHours = ?
            WHERE ID = ?
        """,
            [for_date, category, effort, record_id],
        )
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Generali Base Services Edit Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_any_permission(
    "generali.baseservices.delete.organizational",
    "generali.baseservices.delete.transorganizational",
)
def api_generali_baseservices_delete(record_id):
    conn = None
    try:
        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        if not has_permission("generali.baseservices.delete.transorganizational"):
            _check_generali_record_org(
                cursor, "[Generali].[dbo].[BaseServices]", "UserID", record_id
            )
        cursor.execute("DELETE FROM [Generali].[dbo].[BaseServices] WHERE ID = ?", [record_id])
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Generali Base Services Delete Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


def register_routes(app):
    app.add_url_rule(
        "/generali/baseServices",
        endpoint="generali_base_services",
        view_func=generali_base_services,
    )
    app.add_url_rule(
        "/generali/baseServices/monthreport",
        endpoint="generali_baseservices_monthreport",
        view_func=generali_baseservices_monthreport,
    )
    app.add_url_rule(
        "/api/generali/baseservices/orgUsers",
        endpoint="api_generali_baseservices_org_users",
        view_func=api_generali_baseservices_org_users,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/baseservices/organizations",
        endpoint="api_generali_baseservices_organizations",
        view_func=api_generali_baseservices_organizations,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/baseservices/filterUsers",
        endpoint="api_generali_baseservices_filter_users",
        view_func=api_generali_baseservices_filter_users,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/baseservices",
        endpoint="api_generali_baseservices_list",
        view_func=api_generali_baseservices_list,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/baseservices",
        endpoint="api_generali_baseservices_add",
        view_func=api_generali_baseservices_add,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/generali/baseservices/<int:record_id>",
        endpoint="api_generali_baseservices_edit",
        view_func=api_generali_baseservices_edit,
        methods=["PUT"],
    )
    app.add_url_rule(
        "/api/generali/baseservices/<int:record_id>",
        endpoint="api_generali_baseservices_delete",
        view_func=api_generali_baseservices_delete,
        methods=["DELETE"],
    )
