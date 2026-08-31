"""Generali tenant: PDQM."""

from datetime import date, timedelta

from flask import current_app, jsonify, redirect, render_template, request, session, url_for
from flask_babel import gettext as _

from ...db import engine_generali_db, engine_nexora_db
from ...i18n import get_locale
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

# ----------------------------- Generali PDQM -------------------------------- #


@require_permission("generali.pdqm.view")
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
            can_add=has_permission("generali.pdqm.add"),
            can_add_bypass_deadline=has_permission("generali.pdqm.add.bypass.deadline"),
            can_edit=has_permission("generali.pdqm.edit.organizational")
            or has_permission("generali.pdqm.edit.transorganizational"),
            can_edit_transorg=has_permission("generali.pdqm.edit.transorganizational"),
            can_delete=has_permission("generali.pdqm.delete.organizational")
            or has_permission("generali.pdqm.delete.transorganizational"),
            can_delete_transorg=has_permission("generali.pdqm.delete.transorganizational"),
            can_add_for_org=has_permission("generali.pdqm.add.organizational"),
            can_add_transorg=has_permission("generali.pdqm.add.transorganizational"),
        )
    except Exception as e:
        current_app.logger.error(f"Error loading Generali PDQM: {e}")
        return render_template("handlers/500.html"), 500


@require_permission("generali.pdqm.view")
def generali_pdqm_monthreport():
    try:
        # local import: re-resolve against the live package object so test
        # monkeypatching of gv.engine_generali_db still works post-split
        # (nx_lib/views/generali/__init__.py owns this name; the top-of-file
        # import above would bind a stale copy at import time for this call
        # path).
        from . import engine_generali_db

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
        if not has_permission("generali.pdqm.edit.organizational") and not has_permission(
            "generali.pdqm.edit.transorganizational"
        ):
            where_clauses.append("UserID = ?")
            params.append(session.get("userid"))
        where_sql = "WHERE " + " AND ".join(where_clauses)

        conn = None
        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT ParentCategory,
                   COUNT(*) AS entries,
                   ISNULL(SUM(Quantity), 0) AS total_quantity
            FROM [Generali].[dbo].[PDQMReport]
            {where_sql}
            GROUP BY ParentCategory
            ORDER BY ParentCategory
        """,
            params,
        )
        rows_raw = cursor.fetchall()
        cursor.close()

        rows = [
            {
                "category": r[0] or "—",
                "entries": r[1],
                "total_quantity": int(r[2] or 0),
            }
            for r in rows_raw
        ]

        summary = {
            "total_entries": sum(r["entries"] for r in rows),
            "total_quantity": sum(r["total_quantity"] for r in rows),
        }

        return render_template(
            "generali_monthreport.html",
            logged_in_user=session.get("username"),
            page_visibility=page_visibility(),
            section="pdqm",
            section_title="Generali PDQM",
            back_url=url_for("generali_pdqm"),
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
        current_app.logger.error(f"Error loading Generali PDQM Month Report: {e}")
        return render_template("handlers/500.html"), 500
    finally:
        if conn:
            conn.close()


@require_any_permission("generali.pdqm.add.organizational", "generali.pdqm.add.transorganizational")
def api_generali_pdqm_org_users():
    conn = None
    try:
        transorg = has_permission("generali.pdqm.add.transorganizational")
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
        current_app.logger.error(f"Generali PDQM OrgUsers Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.pdqm.view")
def api_generali_pdqm_categories():
    conn = None
    try:
        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT ParentCategory, ParentSubCategory, SubCategory
            FROM [Generali].[dbo].[PDQMMapping]
            ORDER BY ParentCategory, ParentSubCategory, SubCategory
        """)
        rows = cursor.fetchall()
        cursor.close()

        # nested: { parent: { parentSub_or_"": [sub, ...] } }
        grouped = {}
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
                FROM [Generali].[dbo].[CategoryTranslation] WITH (NOLOCK)
                WHERE SourceTable = 'PDQMMapping' AND Locale = ?
            """,
                [locale],
            )
            for orig, trans in cursor2.fetchall():
                translations[orig] = trans
            cursor2.close()

        return jsonify({"success": True, "categories": grouped, "translations": translations})
    except Exception as e:
        current_app.logger.error(f"Generali PDQM Categories Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.pdqm.view")
def api_generali_pdqm_organizations():
    conn = None
    try:
        # local import: re-resolve against the live package object so test
        # monkeypatching of gv.engine_generali_db still works post-split
        # (nx_lib/views/generali/__init__.py owns this name; the top-of-file
        # import above would bind a stale copy at import time for this call
        # path).
        from . import engine_generali_db

        restrict_to_self = not has_permission(
            "generali.pdqm.edit.organizational"
        ) and not has_permission("generali.pdqm.edit.transorganizational")
        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        if restrict_to_self:
            cursor.execute(
                "SELECT DISTINCT UserID FROM [Generali].[dbo].[PDQMReport] WHERE UserID IS NOT NULL AND UserID = ?",
                [session.get("userid")],
            )
        else:
            cursor.execute(
                "SELECT DISTINCT UserID FROM [Generali].[dbo].[PDQMReport] WHERE UserID IS NOT NULL"
            )
        user_ids = [r[0] for r in cursor.fetchall()]
        cursor.close()
        return jsonify({"success": True, "organizations": _generali_orgs_for_userids(user_ids)})
    except Exception as e:
        current_app.logger.error(f"Generali PDQM Organizations Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.pdqm.view")
def api_generali_pdqm_filter_users():
    try:
        transorg = has_permission("generali.pdqm.edit.transorganizational")
        org_edit = has_permission("generali.pdqm.edit.organizational")
        if not transorg and not org_edit:
            return jsonify({"success": True, "users": []})
        gen_conn = engine_generali_db.raw_connection()
        gen_cur = gen_conn.cursor()
        gen_cur.execute(
            "SELECT DISTINCT UserID FROM [Generali].[dbo].[PDQMReport] WHERE UserID IS NOT NULL"
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
        current_app.logger.error(f"Generali PDQM FilterUsers Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500


@require_permission("generali.pdqm.view")
def api_generali_pdqm_list():
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
        parent_cat = request.args.get("parentCategory", "").strip()
        parent_sub_cat = request.args.get(
            "parentSubCategory", None
        )  # None = not filtered; "" = IS NULL
        sub_cat = request.args.get("subCategory", "").strip()
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
        if parent_cat:
            where_clauses.append("ParentCategory = ?")
            params.append(parent_cat)
        if parent_sub_cat is not None:
            if parent_sub_cat == "":
                where_clauses.append("ParentSubCategory IS NULL")
            else:
                where_clauses.append("ParentSubCategory = ?")
                params.append(parent_sub_cat)
        if sub_cat:
            where_clauses.append("SubCategory = ?")
            params.append(sub_cat)

        scope_clauses, scope_params = _generali_scope_where("generali.pdqm", "UserID", org_code)
        where_clauses.extend(scope_clauses)
        params.extend(scope_params)
        if user_id:
            where_clauses.append("UserID = ?")
            params.append(user_id)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            f"SELECT COUNT(*), SUM(Quantity) FROM [Generali].[dbo].[PDQMReport] {where_sql}", params
        )
        agg = cursor.fetchone()
        total_records = agg[0] or 0
        total_quantity = int(agg[1]) if agg[1] is not None else 0
        total_pages = max(1, -(-total_records // per_page))

        fetch_all = request.args.get("all", "").lower() == "true"
        pagination_sql = "" if fetch_all else "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        sql_params = params if fetch_all else [*params, offset, per_page]
        cursor.execute(
            f"""
            SELECT ID, Quantity, UserID, ForDate, ParentCategory, ParentSubCategory, SubCategory, RecordDateTime
            FROM [Generali].[dbo].[PDQMReport]
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
                current_app.logger.warning(f"User lookup failed for PDQM: {ue}")

        records = []
        for r in rows:
            rec_id, qty, user_id, for_date, parent, parent_sub, sub, recorded_at = r
            user_info = user_map.get(user_id, {})
            records.append(
                {
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
            )

        return jsonify(
            {
                "success": True,
                "records": records,
                "totalQuantity": total_quantity,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_records": total_records,
                    "total_pages": total_pages,
                },
            }
        )
    except Exception as e:
        current_app.logger.error(f"Generali PDQM List Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.pdqm.add")
def api_generali_pdqm_add():
    conn = None
    try:
        body = request.get_json(force=True)
        for_date = body.get("forDate", "").strip()
        parent_cat = body.get("parentCategory", "").strip()
        parent_sub_cat = body.get("parentSubCategory", "")  # "" means NULL
        sub_cat_raw = body.get("subCategory")
        sub_cat = sub_cat_raw.strip() if sub_cat_raw else None
        quantity = body.get("quantity")
        caller_id = session.get("userid")
        target_raw = body.get("userId")
        user_id = caller_id

        if target_raw is not None and str(target_raw) != str(caller_id):
            has_org_perm = has_permission("generali.pdqm.add.organizational")
            has_transorg_perm = has_permission("generali.pdqm.add.transorganizational")
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

        deadline_err = _check_add_deadline(for_date, "generali.pdqm.add.bypass.deadline")
        if deadline_err:
            return jsonify({"success": False, "error": deadline_err}), 403
        if not for_date or not parent_cat or quantity is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        try:
            quantity = int(quantity)
            if quantity < 1:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid quantity"}), 400

        db_parent_sub = parent_sub_cat if parent_sub_cat != "" else None

        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO [Generali].[dbo].[PDQMReport]
                (Quantity, ForDate, UserID, RecordDateTime, ParentCategory, ParentSubCategory, SubCategory)
            VALUES (?, ?, ?, GETDATE(), ?, ?, ?)
        """,
            [quantity, for_date, user_id, parent_cat, db_parent_sub, sub_cat],
        )
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Generali PDQM Add Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_any_permission(
    "generali.pdqm.edit.organizational", "generali.pdqm.edit.transorganizational"
)
def api_generali_pdqm_edit(record_id):
    conn = None
    try:
        body = request.get_json(force=True)
        for_date = body.get("forDate", "").strip()
        parent_cat = body.get("parentCategory", "").strip()
        parent_sub_cat = body.get("parentSubCategory", "")
        sub_cat_raw = body.get("subCategory")
        sub_cat = sub_cat_raw.strip() if sub_cat_raw else None
        quantity = body.get("quantity")

        if not for_date or not parent_cat or quantity is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        try:
            quantity = int(quantity)
            if quantity < 1:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid quantity"}), 400

        db_parent_sub = parent_sub_cat if parent_sub_cat != "" else None

        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        if not has_permission("generali.pdqm.edit.transorganizational"):
            _check_generali_record_org(cursor, "[Generali].[dbo].[PDQMReport]", "UserID", record_id)
        cursor.execute(
            """
            UPDATE [Generali].[dbo].[PDQMReport]
            SET ForDate = ?, ParentCategory = ?, ParentSubCategory = ?, SubCategory = ?, Quantity = ?
            WHERE ID = ?
        """,
            [for_date, parent_cat, db_parent_sub, sub_cat, quantity, record_id],
        )
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Generali PDQM Edit Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_any_permission(
    "generali.pdqm.delete.organizational", "generali.pdqm.delete.transorganizational"
)
def api_generali_pdqm_delete(record_id):
    conn = None
    try:
        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        if not has_permission("generali.pdqm.delete.transorganizational"):
            _check_generali_record_org(cursor, "[Generali].[dbo].[PDQMReport]", "UserID", record_id)
        cursor.execute("DELETE FROM [Generali].[dbo].[PDQMReport] WHERE ID = ?", [record_id])
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Generali PDQM Delete Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


def register_routes(app):
    app.add_url_rule("/generali/pdqm", endpoint="generali_pdqm", view_func=generali_pdqm)
    app.add_url_rule(
        "/generali/pdqm/monthreport",
        endpoint="generali_pdqm_monthreport",
        view_func=generali_pdqm_monthreport,
    )
    app.add_url_rule(
        "/api/generali/pdqm/orgUsers",
        endpoint="api_generali_pdqm_org_users",
        view_func=api_generali_pdqm_org_users,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/pdqm/categories",
        endpoint="api_generali_pdqm_categories",
        view_func=api_generali_pdqm_categories,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/pdqm/organizations",
        endpoint="api_generali_pdqm_organizations",
        view_func=api_generali_pdqm_organizations,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/pdqm/filterUsers",
        endpoint="api_generali_pdqm_filter_users",
        view_func=api_generali_pdqm_filter_users,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/pdqm",
        endpoint="api_generali_pdqm_list",
        view_func=api_generali_pdqm_list,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/pdqm",
        endpoint="api_generali_pdqm_add",
        view_func=api_generali_pdqm_add,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/generali/pdqm/<int:record_id>",
        endpoint="api_generali_pdqm_edit",
        view_func=api_generali_pdqm_edit,
        methods=["PUT"],
    )
    app.add_url_rule(
        "/api/generali/pdqm/<int:record_id>",
        endpoint="api_generali_pdqm_delete",
        view_func=api_generali_pdqm_delete,
        methods=["DELETE"],
    )
