"""Generali tenant: documents/evaluation/stats/filter, reporting, attendance,
additional services, base services, project management, PDQM, import status."""

import math
from datetime import date, timedelta

from flask import (
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_babel import gettext as _

from ..db import engine_generali_db, engine_nexora_db
from ..i18n import get_locale
from ..security import (
    PermissionDenied,
    _check_add_deadline,
    _check_generali_record_org,
    has_permission,
    page_visibility,
    require_any_permission,
    require_permission,
)

# ----------------------------- Generali Evaluation -------------------------- #


@require_permission("generali.dashboard.view")
def generali_evaluation():
    try:
        if "username" not in session:
            return redirect(url_for("login"))
        return render_template(
            "generali-dashboard.html",
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            pageV=page_visibility(),
        )
    except Exception as e:
        current_app.logger.error(f"Error loading Generali Evaluation: {e}")
        return render_template("handlers/500.html"), 500


@require_permission("generali.documentlist.view")
def generali_documents():
    try:
        if "username" not in session:
            return redirect(url_for("login"))
        return render_template(
            "generali_documents.html",
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            pageV=page_visibility(),
        )
    except Exception as e:
        current_app.logger.error(f"Error loading Generali Documents: {e}")
        return render_template("handlers/500.html"), 500


@require_permission("generali.dashboard.view")
def api_generali_stats():
    conn = None
    try:
        raw_start_date = request.args.get("startDate")
        raw_end_date = request.args.get("endDate")
        if not raw_start_date or not raw_end_date:
            return (
                jsonify({"success": False, "error": _("startDate and endDate are required")}),
                400,
            )
        start_date = raw_start_date.replace("T", " ")
        end_date = raw_end_date.replace("T", " ")

        date_filter = ""
        date_params = []

        if start_date:
            date_filter += " AND DOC_SCANDATUM >= ?"
            date_params.append(start_date)
        if end_date:
            date_filter += " AND DOC_SCANDATUM <= ?"
            date_params.append(end_date)

        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            f"""
            SELECT
                COUNT(*) as TotalDocs,
                SUM(CASE WHEN DOC_NK1 = 'keineNachkontrolle' THEN 1 ELSE 0 END) as NK1_Pass,
                SUM(CASE WHEN DOC_NK2 = 'keineNachkontrolle' THEN 1 ELSE 0 END) as NK2_Pass,
                SUM(CASE WHEN DOC_NK1 = 'keineNachkontrolle' AND DOC_NK2 = 'keineNachkontrolle' THEN 1 ELSE 0 END) as NK1_NK2_Pass
            FROM [dbo].[v_ReportJobJoinDefinitions]
            WHERE 1=1 {date_filter}

        """,
            date_params,
        )
        kpi_row = cursor.fetchone()
        total = kpi_row[0] or 0
        kpis = {
            "total_docs": total,
            "nk1_rate": round((kpi_row[1] / total) * 100, 1) if total > 0 else 0,
            "nk2_rate": round((kpi_row[2] / total) * 100, 1) if total > 0 else 0,
            "nk1_nk2_rate": round((kpi_row[3] / total) * 100, 1) if total > 0 else 0,
        }

        trend_where = (
            "1=1" + date_filter if date_filter else "DOC_SCANDATUM >= DATEADD(day, -30, GETDATE())"
        )
        cursor.execute(
            f"""
            SELECT CAST(DOC_SCANDATUM AS DATE) as d,
                   ISNULL(DOC_KOMMUNIKATION, 'Unknown') as k,
                   COUNT(*) as c
            FROM [dbo].[v_ReportJobJoinDefinitions]
            WHERE {trend_where}
            GROUP BY CAST(DOC_SCANDATUM AS DATE), ISNULL(DOC_KOMMUNIKATION, 'Unknown')
            ORDER BY d
        """,
            date_params,
        )
        trend_rows = cursor.fetchall()

        labels = sorted({str(r[0]) for r in trend_rows})
        label_index = {d: i for i, d in enumerate(labels)}
        totals = [0] * len(labels)
        by_komm = {}
        for d, k, c in trend_rows:
            i = label_index[str(d)]
            totals[i] += c
            if k not in by_komm:
                by_komm[k] = [0] * len(labels)
            by_komm[k][i] += c

        trend_data = {"labels": labels, "values": totals, "byKommunikation": by_komm}

        kpis["avg_daily"] = round(total / len(labels), 1) if total > 0 and labels else 0

        cursor.execute(
            f"""
            SELECT TOP 15 ISNULL(DOC_DOKUMENTENTYP, 'Unknown') as t, COUNT(*) as c
            FROM [dbo].[v_ReportJobJoinDefinitions]
            WHERE 1=1 {date_filter}
            GROUP BY DOC_DOKUMENTENTYP
            ORDER BY c DESC
        """,
            date_params,
        )
        rows = cursor.fetchall()
        doctype_data = {"labels": [r[0] for r in rows], "values": [r[1] for r in rows]}

        cursor.execute(
            f"""
            SELECT ISNULL(DOC_EMPFAENGER, 'Unknown') as e, COUNT(*) as c
            FROM [dbo].[v_ReportJobJoinDefinitions]
            WHERE 1=1 {date_filter}
            GROUP BY DOC_EMPFAENGER
            ORDER BY c DESC
        """,
            date_params,
        )
        rows = cursor.fetchall()

        empfaenger_data = {"labels": [r[0] for r in rows], "values": [r[1] for r in rows]}

        cursor.execute(
            f"""
            SELECT ISNULL(DOC_SPRACHE, 'Unknown') as s, COUNT(*) as c
            FROM [dbo].[v_ReportJobJoinDefinitions]
            WHERE 1=1 {date_filter}
            GROUP BY DOC_SPRACHE
            ORDER BY c DESC
        """,
            date_params,
        )
        rows = cursor.fetchall()

        language_data = {"labels": [r[0] for r in rows], "values": [r[1] for r in rows]}

        cursor.execute(
            f"""
            SELECT ISNULL(DOC_EINGANGSKANAL, 'Unknown') as k, COUNT(*) as c
            FROM [dbo].[v_ReportJobJoinDefinitions]
            WHERE 1=1 {date_filter}
            GROUP BY DOC_EINGANGSKANAL
            ORDER BY c DESC
        """,
            date_params,
        )
        rows = cursor.fetchall()

        channel_data = {"labels": [r[0] for r in rows], "values": [r[1] for r in rows]}

        cursor.execute(
            f"""
            SELECT ISNULL(DOC_NK1,'Unknown') as nk1, ISNULL(DOC_NK2,'Unknown') as nk2, COUNT(*) as c
            FROM [dbo].[v_ReportJobJoinDefinitions]
            WHERE 1=1 {date_filter}
            GROUP BY DOC_NK1, DOC_NK2
            ORDER BY c DESC
        """,
            date_params,
        )
        rows = cursor.fetchall()

        nk_data = [{"nk1": r[0], "nk2": r[1], "count": r[2]} for r in rows]
        return jsonify(
            {
                "success": True,
                "kpis": kpis,
                "trend": trend_data,
                "doctype": doctype_data,
                "empfaenger": empfaenger_data,
                "language": language_data,
                "channel": channel_data,
                "nk": nk_data,
            }
        )
    except Exception as e:
        current_app.logger.error(f"Generali Stats API Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.documentlist.view")
def api_generali_filter_options():
    conn = None
    try:
        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        result = {}
        for col, key in [
            ("DOC_DOKUMENTENTYP", "doctype"),
            ("DOC_EMPFAENGER", "empfaenger"),
            ("DOC_SPRACHE", "sprache"),
            ("DOC_NK1", "nk1"),
            ("DOC_NK2", "nk2"),
            ("DOC_EINGANGSKANAL", "eingangskanal"),
            ("DOC_KOMMUNIKATION", "kommunikation"),
        ]:
            cursor.execute(
                f"SELECT DISTINCT {col} FROM [dbo].[v_ReportJobJoinDefinitions] WHERE {col} IS NOT NULL ORDER BY {col}"
            )
            result[key] = [r[0] for r in cursor.fetchall()]
        return jsonify({"success": True, "options": result})
    except Exception as e:
        current_app.logger.error(f"Generali Filter Options Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.documentlist.view")
def api_generali_documents():
    conn = None
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("perPage", 40, type=int)
        if per_page not in (40, 100, 200, 500, 1000):
            per_page = 40
        offset = (page - 1) * per_page

        doc_type = request.args.get("docType")
        empfaenger = request.args.get("empfaenger")
        sprache = request.args.get("sprache")
        nk1 = request.args.get("nk1")
        nk2 = request.args.get("nk2")
        eingangskanal = request.args.get("eingangskanal")
        kommunikation = request.args.get("kommunikation")
        start_date = request.args.get("startDate")
        end_date = request.args.get("endDate")
        search = request.args.get("search", "").strip()
        sort_by = request.args.get("sortBy", "DOC_SCANDATUM")
        sort_dir = request.args.get("sortDir", "DESC").upper()
        group_by = request.args.get("groupBy", "")

        allowed_sort_cols = {
            "DOC_SCANDATUM",
            "DOC_DOKUMENTENTYP",
            "DOC_EMPFAENGER",
            "DOC_SPRACHE",
            "DOC_EINGANGSKANAL",
            "DOC_NK1",
            "DOC_NK2",
            "DOC_BETRAG",
            "DOC_KOMMUNIKATION",
        }
        if sort_by not in allowed_sort_cols:
            sort_by = "DOC_SCANDATUM"
        if sort_dir not in ("ASC", "DESC"):
            sort_dir = "DESC"

        allowed_group_cols = {
            "DOC_DOKUMENTENTYP",
            "DOC_EMPFAENGER",
            "DOC_SPRACHE",
            "DOC_EINGANGSKANAL",
            "DOC_KOMMUNIKATION",
        }
        if group_by not in allowed_group_cols:
            group_by = ""

        where_clauses = ["1=1"]
        params = []

        if doc_type:
            where_clauses.append("DOC_DOKUMENTENTYP = ?")
            params.append(doc_type)
        if empfaenger:
            where_clauses.append("DOC_EMPFAENGER = ?")
            params.append(empfaenger)
        if sprache:
            where_clauses.append("DOC_SPRACHE = ?")
            params.append(sprache)
        if nk1:
            where_clauses.append("DOC_NK1 = ?")
            params.append(nk1)
        if nk2:
            where_clauses.append("DOC_NK2 = ?")
            params.append(nk2)
        if eingangskanal:
            where_clauses.append("DOC_EINGANGSKANAL = ?")
            params.append(eingangskanal)
        if kommunikation:
            where_clauses.append("DOC_KOMMUNIKATION = ?")
            params.append(kommunikation)
        if start_date:
            where_clauses.append("DOC_SCANDATUM >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("DOC_SCANDATUM <= ?")
            params.append(end_date)
        if search:
            where_clauses.append("""(
                DOC_ID LIKE ? OR CAST(CASE_ID AS NVARCHAR) LIKE ?
                OR DOC_BEZEICHNUNG LIKE ? OR DOC_KONTAKTPERSON LIKE ?
                OR DOC_POLICEN_NR LIKE ? OR DOC_SCHADEN_NR LIKE ?
            )""")
            s = f"%{search}%"
            params.extend([s, s, s, s, s, s])

        where_sql = " AND ".join(where_clauses)

        order_parts = []
        if group_by:
            order_parts.append(f"{group_by} ASC")
        if sort_by != group_by:
            order_parts.append(f"{sort_by} {sort_dir}")
        order_sql = ", ".join(order_parts) if order_parts else "DOC_SCANDATUM DESC"

        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            f"SELECT COUNT(*) FROM [dbo].[v_ReportJobJoinDefinitions] WHERE {where_sql}", params
        )
        total_items = cursor.fetchone()[0]
        total_pages = math.ceil(total_items / per_page)

        cursor.execute(
            f"""
            SELECT
                DOC_ID, CASE_ID, CASE_FOLDERNAME, DOC_SCANDATUM, DOC_DOKUMENTENTYP,
                DOC_EMPFAENGER, DOC_SPRACHE, DOC_KOMMUNIKATION, DOC_EINGANGSKANAL,
                DOC_BETRAG, DOC_WAEHRUNG, DOC_NK1, DOC_NK2, DOC_SCANORT,
                DOC_BEZEICHNUNG, DOC_NOTIFIKATIONSSTATUS, DOC_RICHTUNG, DOC_PENDING
            FROM [dbo].[v_ReportJobJoinDefinitions]
            WHERE {where_sql}
            ORDER BY {order_sql}
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """,
            [*params, offset, per_page],
        )

        cols = [
            "doc_id",
            "case_id",
            "case_foldername",
            "doc_scandatum",
            "doc_dokumententyp",
            "doc_empfaenger",
            "doc_sprache",
            "doc_kommunikation",
            "doc_eingangskanal",
            "doc_betrag",
            "doc_waehrung",
            "doc_nk1",
            "doc_nk2",
            "doc_scanort",
            "doc_bezeichnung",
            "doc_notifikationsstatus",
            "doc_richtung",
            "doc_pending",
        ]
        documents = []
        for row in cursor.fetchall():
            d = dict(zip(cols, row, strict=False))
            d["doc_scandatum"] = str(d["doc_scandatum"]) if d["doc_scandatum"] else None
            documents.append(d)

        return jsonify(
            {
                "success": True,
                "documents": documents,
                "group_by": group_by,
                "pagination": {
                    "currentPage": page,
                    "totalPages": total_pages,
                    "totalItems": total_items,
                    "perPage": per_page,
                },
            }
        )
    except Exception as e:
        current_app.logger.error(f"Generali Documents API Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.documentlist.view")
def api_generali_document_detail(doc_id):
    conn = None
    try:
        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM [dbo].[v_ReportJobJoinDefinitions]
            WHERE DOC_ID = ?
        """,
            [doc_id],
        )
        row = cursor.fetchone()
        if not row:
            return jsonify({"success": False, "error": "Not found"}), 404
        cols = [desc[0] for desc in cursor.description]
        doc = {}
        for k, v in zip(cols, row, strict=False):
            doc[k] = str(v) if v is not None else None
        return jsonify({"success": True, "document": doc})
    except Exception as e:
        current_app.logger.error(f"Generali Document Detail Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


# ----------------------------- Generali shared org helpers ------------------ #
def _generali_orgs_for_userids(user_ids):
    if not user_ids:
        return []
    nx_conn = engine_nexora_db.raw_connection()
    try:
        nx_cur = nx_conn.cursor()
        placeholders = ",".join(["?"] * len(user_ids))
        nx_cur.execute(
            f"""
            SELECT DISTINCT u.organizationcode, o.organization
            FROM Users u
            LEFT JOIN organizations o ON o.organizationcode = u.organizationcode
            WHERE u.userid IN ({placeholders}) AND u.organizationcode IS NOT NULL
            ORDER BY o.organization, u.organizationcode
        """,
            user_ids,
        )
        return [{"code": r[0], "name": r[1] or r[0]} for r in nx_cur.fetchall()]
    finally:
        nx_conn.close()


def _generali_userids_in_org(org_code):
    nx_conn = engine_nexora_db.raw_connection()
    try:
        nx_cur = nx_conn.cursor()
        nx_cur.execute("SELECT userid FROM Users WHERE organizationcode = ?", [org_code])
        return [r[0] for r in nx_cur.fetchall()]
    finally:
        nx_conn.close()


def _generali_scope_where(perm_prefix, user_column, requested_org_code):
    """WHERE fragment enforcing a Generali list query's org/self visibility from
    the caller's GRANTS -- never from a client-supplied organizationcode (#193
    cross-org read). Returns (clauses, params):

    - <perm>.edit.transorganizational: honour an optional requested org filter,
      otherwise no constraint (all orgs).
    - <perm>.edit.organizational only: clamp to the caller's SESSION org; any
      requested organizationcode is ignored.
    - neither grant: clamp to the caller's own user id.

    Emits a fail-closed "1=0" clause when the target org resolves to no users,
    so an empty/unknown org can never widen the result set.
    """
    if has_permission(f"{perm_prefix}.edit.transorganizational"):
        if not requested_org_code:
            return [], []
        org_scope = requested_org_code
    elif has_permission(f"{perm_prefix}.edit.organizational"):
        org_scope = session.get("organizationcode")
    else:
        return [f"{user_column} = ?"], [session.get("userid")]

    ids = _generali_userids_in_org(org_scope)
    if not ids:
        current_app.logger.info(
            f"Generali scope: org {org_scope!r} resolved to no users; failing closed"
        )
        return ["1=0"], []
    placeholders = ",".join(["?"] * len(ids))
    return [f"{user_column} IN ({placeholders})"], list(ids)


def _empty_paginated_response(extra=None):
    payload = {
        "success": True,
        "records": [],
        "pagination": {"page": 1, "per_page": 20, "total_records": 0, "total_pages": 1},
    }
    if extra:
        payload.update(extra)
    return jsonify(payload)


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
            pageV=page_visibility(),
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
            pageV=page_visibility(),
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


# ----------------------------- Generali Additional Services -------------------------- #
@require_permission("generali.additionalservices.view")
def generali_additional_services():
    try:
        if "username" not in session:
            return redirect(url_for("login"))
        return render_template(
            "generali_additionalservices.html",
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            pageV=page_visibility(),
            organizationcode=session.get("organizationcode"),
            can_add=has_permission("generali.attendance.add"),
            can_add_bypass_deadline=has_permission("generali.attendance.add.bypass.deadline"),
            can_edit=has_permission("generali.attendance.edit.organizational")
            or has_permission("generali.attendance.edit.transorganizational"),
            can_edit_transorg=has_permission("generali.attendance.edit.transorganizational"),
            can_delete=has_permission("generali.attendance.delete.organizational")
            or has_permission("generali.attendance.delete.transorganizational"),
            can_delete_transorg=has_permission("generali.attendance.delete.transorganizational"),
            can_add_for_org=has_permission("generali.attendance.add.organizational"),
            can_add_transorg=has_permission("generali.attendance.add.transorganizational"),
        )
    except Exception as e:
        current_app.logger.error(f"Error loading Generali Attendance: {e}")
        return render_template("handlers/500.html"), 500


@require_permission("generali.additionalservices.view")
def generali_additionalservices_monthreport():
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
        if not has_permission("generali.attendance.edit.organizational") and not has_permission(
            "generali.attendance.edit.transorganizational"
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
                   ISNULL(SUM(EffortInHours), 0) AS total_hours
            FROM [Generali].[dbo].[Attendance]
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
            pageV=page_visibility(),
            section="additionalservices",
            section_title="Generali Additional Services",
            back_url=url_for("generali_additionalServices"),
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
        current_app.logger.error(f"Error loading Generali Additional Services Month Report: {e}")
        return render_template("handlers/500.html"), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.additionalservices.view")
def api_generali_attendance_categories():
    conn = None
    try:
        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT ParentCategory, SubCategory
            FROM [Generali].[dbo].[AdditionalServices]
            ORDER BY ParentCategory, SubCategory
        """)
        rows = cursor.fetchall()
        cursor.close()

        grouped = {}
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
            for orig, trans in cursor2.fetchall():
                translations[orig] = trans
            cursor2.close()

        return jsonify({"success": True, "categories": grouped, "translations": translations})
    except Exception as e:
        current_app.logger.error(f"Generali Attendance Categories Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_any_permission(
    "generali.attendance.add.organizational", "generali.attendance.add.transorganizational"
)
def api_generali_attendance_org_users():
    conn = None
    try:
        transorg = has_permission("generali.attendance.add.transorganizational")
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
        current_app.logger.error(f"Generali Attendance OrgUsers Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.additionalservices.view")
def api_generali_attendance_organizations():
    conn = None
    try:
        restrict_to_self = not has_permission(
            "generali.attendance.edit.organizational"
        ) and not has_permission("generali.attendance.edit.transorganizational")
        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        if restrict_to_self:
            cursor.execute(
                "SELECT DISTINCT UserID FROM [Generali].[dbo].[Attendance] WHERE UserID IS NOT NULL AND UserID = ?",
                [session.get("userid")],
            )
        else:
            cursor.execute(
                "SELECT DISTINCT UserID FROM [Generali].[dbo].[Attendance] WHERE UserID IS NOT NULL"
            )
        user_ids = [r[0] for r in cursor.fetchall()]
        cursor.close()
        return jsonify({"success": True, "organizations": _generali_orgs_for_userids(user_ids)})
    except Exception as e:
        current_app.logger.error(f"Generali Attendance Organizations Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.additionalservices.view")
def api_generali_attendance_filter_users():
    try:
        transorg = has_permission("generali.attendance.edit.transorganizational")
        org_edit = has_permission("generali.attendance.edit.organizational")
        if not transorg and not org_edit:
            return jsonify({"success": True, "users": []})
        gen_conn = engine_generali_db.raw_connection()
        gen_cur = gen_conn.cursor()
        gen_cur.execute(
            "SELECT DISTINCT UserID FROM [Generali].[dbo].[Attendance] WHERE UserID IS NOT NULL"
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
        current_app.logger.error(f"Generali Attendance FilterUsers Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500


@require_permission("generali.additionalservices.view")
def api_generali_attendance_list():
    conn = None
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = 20
        offset = (page - 1) * per_page

        start_date = request.args.get("startDate", "").strip()
        end_date = request.args.get("endDate", "").strip()
        parent_cat = request.args.get("parentCategory", "").strip()
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
        if sub_cat:
            where_clauses.append("SubCategory = ?")
            params.append(sub_cat)

        scope_clauses, scope_params = _generali_scope_where(
            "generali.attendance", "UserID", org_code
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
            f"SELECT COUNT(*), SUM(EffortInHours) FROM [Generali].[dbo].[Attendance] {where_sql}",
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
            SELECT ID, EffortInHours, UserID, ForDate, ParentCategory, SubCategory, RecordDateTime
            FROM [Generali].[dbo].[Attendance]
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
                current_app.logger.warning(f"User lookup failed for attendance: {ue}")

        records = []
        for r in rows:
            rec_id, effort, user_id, for_date, parent, sub, recorded_at = r
            user_info = user_map.get(user_id, {})
            records.append(
                {
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
        current_app.logger.error(f"Generali Attendance List Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.attendance.add")
def api_generali_attendance_add():
    conn = None
    try:
        body = request.get_json(force=True)
        for_date = body.get("forDate", "").strip()
        parent_cat = body.get("parentCategory", "").strip()
        sub_cat_raw = body.get("subCategory")
        sub_cat = sub_cat_raw.strip() if sub_cat_raw else None
        effort = body.get("effortInHours")
        caller_id = session.get("userid")
        target_raw = body.get("userId")
        user_id = caller_id

        if target_raw is not None and str(target_raw) != str(caller_id):
            has_org_perm = has_permission("generali.attendance.add.organizational")
            has_transorg_perm = has_permission("generali.attendance.add.transorganizational")
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

        deadline_err = _check_add_deadline(for_date, "generali.attendance.add.bypass.deadline")
        if deadline_err:
            return jsonify({"success": False, "error": deadline_err}), 403
        if not for_date or not parent_cat or effort is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
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
            INSERT INTO [Generali].[dbo].[Attendance]
                (EffortInHours, UserID, ForDate, ParentCategory, SubCategory, RecordDateTime)
            VALUES (?, ?, ?, ?, ?, GETDATE())
        """,
            [effort, user_id, for_date, parent_cat, sub_cat],
        )
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Generali Attendance Add Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_any_permission(
    "generali.attendance.edit.organizational", "generali.attendance.edit.transorganizational"
)
def api_generali_attendance_edit(record_id):
    conn = None
    try:
        body = request.get_json(force=True)
        for_date = body.get("forDate", "").strip()
        parent_cat = body.get("parentCategory", "").strip()
        sub_cat_raw = body.get("subCategory")
        sub_cat = sub_cat_raw.strip() if sub_cat_raw else None
        effort = body.get("effortInHours")

        if not for_date or not parent_cat or effort is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        try:
            effort = float(effort)
            if effort <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid effort value"}), 400

        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        if not has_permission("generali.attendance.edit.transorganizational"):
            _check_generali_record_org(cursor, "[Generali].[dbo].[Attendance]", "UserID", record_id)
        cursor.execute(
            """
            UPDATE [Generali].[dbo].[Attendance]
            SET ForDate = ?, ParentCategory = ?, SubCategory = ?, EffortInHours = ?
            WHERE ID = ?
        """,
            [for_date, parent_cat, sub_cat, effort, record_id],
        )
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Generali Attendance Edit Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_any_permission(
    "generali.attendance.delete.organizational", "generali.attendance.delete.transorganizational"
)
def api_generali_attendance_delete(record_id):
    conn = None
    try:
        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        if not has_permission("generali.attendance.delete.transorganizational"):
            _check_generali_record_org(cursor, "[Generali].[dbo].[Attendance]", "UserID", record_id)
        cursor.execute("DELETE FROM [Generali].[dbo].[Attendance] WHERE ID = ?", [record_id])
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Generali Attendance Delete Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


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
            pageV=page_visibility(),
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
            pageV=page_visibility(),
            section="baseservices",
            section_title="Generali Base Services",
            back_url=url_for("generali_baseServices"),
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


# ----------------------------- Generali Project Management ------------------ #
@require_permission("generali.projectmanagement.view")
def generali_project_management():
    try:
        if "username" not in session:
            return redirect(url_for("login"))
        return render_template(
            "generali_projectmanagement.html",
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            pageV=page_visibility(),
            organizationcode=session.get("organizationcode"),
            can_add=has_permission("generali.projectmanagement.add"),
            can_add_bypass_deadline=has_permission(
                "generali.projectmanagement.add.bypass.deadline"
            ),
            can_edit=has_permission("generali.projectmanagement.edit.organizational")
            or has_permission("generali.projectmanagement.edit.transorganizational"),
            can_edit_transorg=has_permission("generali.projectmanagement.edit.transorganizational"),
            can_delete=has_permission("generali.projectmanagement.delete.organizational")
            or has_permission("generali.projectmanagement.delete.transorganizational"),
            can_delete_transorg=has_permission(
                "generali.projectmanagement.delete.transorganizational"
            ),
            can_add_for_org=has_permission("generali.projectmanagement.add.organizational"),
            can_add_transorg=has_permission("generali.projectmanagement.add.transorganizational"),
        )
    except Exception as e:
        current_app.logger.error(f"Error loading Generali Project Management: {e}")
        return render_template("handlers/500.html"), 500


@require_permission("generali.projectmanagement.view")
def generali_projectmanagement_monthreport():
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
        if not has_permission(
            "generali.projectmanagement.edit.organizational"
        ) and not has_permission("generali.projectmanagement.edit.transorganizational"):
            where_clauses.append("UserID = ?")
            params.append(session.get("userid"))
        where_sql = "WHERE " + " AND ".join(where_clauses)

        conn = None
        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT COUNT(*) AS entries,
                   ISNULL(SUM(EffortInHours), 0) AS total_hours
            FROM [Generali].[dbo].[ProjectManagement]
            {where_sql}
        """,
            params,
        )
        row = cursor.fetchone()
        cursor.close()

        summary = {
            "total_entries": row[0] or 0,
            "total_hours": round(float(row[1] or 0), 2),
        }

        return render_template(
            "generali_monthreport.html",
            logged_in_user=session.get("username"),
            pageV=page_visibility(),
            section="projectmanagement",
            section_title="Generali Project Management",
            back_url=url_for("generali_projectManagement"),
            year=year,
            month=month,
            month_label=month_label,
            prev_year=prev_year,
            prev_month=prev_month,
            next_year=next_year,
            next_month=next_month,
            is_current_month=is_current_month,
            summary=summary,
            rows=[],
        )
    except Exception as e:
        current_app.logger.error(f"Error loading Generali Project Management Month Report: {e}")
        return render_template("handlers/500.html"), 500
    finally:
        if conn:
            conn.close()


@require_any_permission(
    "generali.projectmanagement.add.organizational",
    "generali.projectmanagement.add.transorganizational",
)
def api_generali_projectmanagement_org_users():
    conn = None
    try:
        transorg = has_permission("generali.projectmanagement.add.transorganizational")
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
        current_app.logger.error(f"Generali Project Management OrgUsers Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.projectmanagement.view")
def api_generali_projectmanagement_organizations():
    conn = None
    try:
        restrict_to_self = not has_permission(
            "generali.projectmanagement.edit.organizational"
        ) and not has_permission("generali.projectmanagement.edit.transorganizational")
        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        if restrict_to_self:
            cursor.execute(
                "SELECT DISTINCT UserID FROM [Generali].[dbo].[ProjectManagement] WHERE UserID IS NOT NULL AND UserID = ?",
                [session.get("userid")],
            )
        else:
            cursor.execute(
                "SELECT DISTINCT UserID FROM [Generali].[dbo].[ProjectManagement] WHERE UserID IS NOT NULL"
            )
        user_ids = [r[0] for r in cursor.fetchall()]
        cursor.close()
        return jsonify({"success": True, "organizations": _generali_orgs_for_userids(user_ids)})
    except Exception as e:
        current_app.logger.error(f"Generali Project Management Organizations Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.projectmanagement.view")
def api_generali_projectmanagement_filter_users():
    try:
        transorg = has_permission("generali.projectmanagement.edit.transorganizational")
        org_edit = has_permission("generali.projectmanagement.edit.organizational")
        if not transorg and not org_edit:
            return jsonify({"success": True, "users": []})
        gen_conn = engine_generali_db.raw_connection()
        gen_cur = gen_conn.cursor()
        gen_cur.execute(
            "SELECT DISTINCT UserID FROM [Generali].[dbo].[ProjectManagement] WHERE UserID IS NOT NULL"
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
        current_app.logger.error(f"Generali ProjectManagement FilterUsers Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500


@require_permission("generali.projectmanagement.view")
def api_generali_projectmanagement_list():
    conn = None
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = 20
        offset = (page - 1) * per_page

        start_date = request.args.get("startDate", "").strip()
        end_date = request.args.get("endDate", "").strip()
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

        scope_clauses, scope_params = _generali_scope_where(
            "generali.projectmanagement", "UserID", org_code
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
            f"SELECT COUNT(*), SUM(EffortInHours) FROM [Generali].[dbo].[ProjectManagement] {where_sql}",
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
            SELECT ID, EffortInHours, UserID, ForDate, Category, Comment, RecordDateTime
            FROM [Generali].[dbo].[ProjectManagement]
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
                current_app.logger.warning(f"User lookup failed for project management: {ue}")

        records = []
        for r in rows:
            rec_id, effort, user_id, for_date, category_val, comment, recorded_at = r
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
                    "comment": comment,
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
        current_app.logger.error(f"Generali Project Management List Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("generali.projectmanagement.add")
def api_generali_projectmanagement_add():
    conn = None
    try:
        body = request.get_json(force=True)
        for_date = body.get("forDate", "").strip()
        effort = body.get("effortInHours")
        comment = body.get("comment")
        comment = comment.strip() if comment else None
        caller_id = session.get("userid")
        target_raw = body.get("userId")
        user_id = caller_id

        if target_raw is not None and str(target_raw) != str(caller_id):
            has_org_perm = has_permission("generali.projectmanagement.add.organizational")
            has_transorg_perm = has_permission("generali.projectmanagement.add.transorganizational")
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

        deadline_err = _check_add_deadline(
            for_date, "generali.projectmanagement.add.bypass.deadline"
        )
        if deadline_err:
            return jsonify({"success": False, "error": deadline_err}), 403
        if not for_date or effort is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
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
            INSERT INTO [Generali].[dbo].[ProjectManagement]
                (EffortInHours, UserID, ForDate, Category, Comment, RecordDateTime)
            VALUES (?, ?, ?, ?, ?, GETDATE())
        """,
            [effort, user_id, for_date, "Project Effort", comment],
        )
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Generali Project Management Add Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_any_permission(
    "generali.projectmanagement.edit.organizational",
    "generali.projectmanagement.edit.transorganizational",
)
def api_generali_projectmanagement_edit(record_id):
    conn = None
    try:
        body = request.get_json(force=True)
        for_date = body.get("forDate", "").strip()
        effort = body.get("effortInHours")
        comment = body.get("comment")
        comment = comment.strip() if comment else None

        if not for_date or effort is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        try:
            effort = float(effort)
            if effort <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid effort value"}), 400

        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        if not has_permission("generali.projectmanagement.edit.transorganizational"):
            _check_generali_record_org(
                cursor, "[Generali].[dbo].[ProjectManagement]", "UserID", record_id
            )
        cursor.execute(
            """
            UPDATE [Generali].[dbo].[ProjectManagement]
            SET ForDate = ?, EffortInHours = ?, Comment = ?
            WHERE ID = ?
        """,
            [for_date, effort, comment, record_id],
        )
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Generali Project Management Edit Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_any_permission(
    "generali.projectmanagement.delete.organizational",
    "generali.projectmanagement.delete.transorganizational",
)
def api_generali_projectmanagement_delete(record_id):
    conn = None
    try:
        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()
        if not has_permission("generali.projectmanagement.delete.transorganizational"):
            _check_generali_record_org(
                cursor, "[Generali].[dbo].[ProjectManagement]", "UserID", record_id
            )
        cursor.execute("DELETE FROM [Generali].[dbo].[ProjectManagement] WHERE ID = ?", [record_id])
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Generali Project Management Delete Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


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
            pageV=page_visibility(),
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
            pageV=page_visibility(),
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


# ----------------------------- Generali Import Status ---------------------- #
@require_permission("generali.importstatus.view")
def generali_import_status():
    try:
        if "username" not in session:
            return redirect(url_for("login"))
        return render_template(
            "generali_importstatus.html",
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            pageV=page_visibility(),
            organizationcode=session.get("organizationcode"),
        )
    except Exception as e:
        current_app.logger.error(f"Error loading Generali Import Status: {e}")
        return render_template("handlers/500.html"), 500


@require_permission("generali.importstatus.view")
def api_generali_importstatus_list():
    conn = None
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = 20
        offset = (page - 1) * per_page

        start_date = request.args.get("startDate", "").strip()
        end_date = request.args.get("endDate", "").strip()
        status = request.args.get("status", "").strip()
        search = request.args.get("search", "").strip()

        where_clauses = []
        params = []

        if start_date:
            where_clauses.append("StartedAt >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("StartedAt <= ?")
            params.append(end_date)
        if status in ("running", "success", "failed"):
            where_clauses.append("[Status] = ?")
            params.append(status)
        if search:
            where_clauses.append("FileName LIKE ?")
            params.append(f"%{search}%")

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(f"SELECT COUNT(*) FROM [Generali].[dbo].[CSVImportLog] {where_sql}", params)
        total_records = cursor.fetchone()[0] or 0
        total_pages = max(1, -(-total_records // per_page))

        cursor.execute(
            f"""
            SELECT ID, FileName, StartedAt, FinishedAt, CSVRowCount,
                   RowsInserted, RowsUpdated, MinScanDatum, MaxScanDatum, [Status]
            FROM [Generali].[dbo].[CSVImportLog]
            {where_sql}
            ORDER BY StartedAt DESC, ID DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """,
            [*params, offset, per_page],
        )
        rows = cursor.fetchall()
        cursor.close()

        records = []
        for r in rows:
            rec_id, fname, started_at, finished_at, csv_rows, ins, upd, min_scan, max_scan, st = r
            records.append(
                {
                    "id": rec_id,
                    "fileName": fname,
                    "startedAt": started_at.isoformat() if started_at else None,
                    "finishedAt": finished_at.isoformat() if finished_at else None,
                    "csvRowCount": int(csv_rows) if csv_rows is not None else None,
                    "rowsInserted": int(ins) if ins is not None else 0,
                    "rowsUpdated": int(upd) if upd is not None else 0,
                    "minScanDatum": min_scan.isoformat() if min_scan else None,
                    "maxScanDatum": max_scan.isoformat() if max_scan else None,
                    "status": st,
                }
            )

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
        current_app.logger.error(f"Generali Import Status List Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


def register_routes(app):
    app.add_url_rule(
        "/generali-dashboard", endpoint="generali_evaluation", view_func=generali_evaluation
    )
    app.add_url_rule(
        "/generali/documents", endpoint="generali_documents", view_func=generali_documents
    )
    app.add_url_rule(
        "/api/generali/stats", endpoint="api_generali_stats", view_func=api_generali_stats
    )
    app.add_url_rule(
        "/api/generali/filter_options",
        endpoint="api_generali_filter_options",
        view_func=api_generali_filter_options,
    )
    app.add_url_rule(
        "/api/generali/documents",
        endpoint="api_generali_documents",
        view_func=api_generali_documents,
    )
    app.add_url_rule(
        "/api/generali/documents/<path:doc_id>",
        endpoint="api_generali_document_detail",
        view_func=api_generali_document_detail,
    )
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
    app.add_url_rule(
        "/generali/additionalServices",
        endpoint="generali_additionalServices",
        view_func=generali_additional_services,
    )
    app.add_url_rule(
        "/generali/additionalServices/monthreport",
        endpoint="generali_additionalservices_monthreport",
        view_func=generali_additionalservices_monthreport,
    )
    app.add_url_rule(
        "/api/generali/attendance/categories",
        endpoint="api_generali_attendance_categories",
        view_func=api_generali_attendance_categories,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/attendance/orgUsers",
        endpoint="api_generali_attendance_org_users",
        view_func=api_generali_attendance_org_users,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/attendance/organizations",
        endpoint="api_generali_attendance_organizations",
        view_func=api_generali_attendance_organizations,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/attendance/filterUsers",
        endpoint="api_generali_attendance_filter_users",
        view_func=api_generali_attendance_filter_users,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/attendance",
        endpoint="api_generali_attendance_list",
        view_func=api_generali_attendance_list,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/attendance",
        endpoint="api_generali_attendance_add",
        view_func=api_generali_attendance_add,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/generali/attendance/<int:record_id>",
        endpoint="api_generali_attendance_edit",
        view_func=api_generali_attendance_edit,
        methods=["PUT"],
    )
    app.add_url_rule(
        "/api/generali/attendance/<int:record_id>",
        endpoint="api_generali_attendance_delete",
        view_func=api_generali_attendance_delete,
        methods=["DELETE"],
    )
    app.add_url_rule(
        "/generali/baseServices", endpoint="generali_baseServices", view_func=generali_base_services
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
    app.add_url_rule(
        "/generali/projectManagement",
        endpoint="generali_projectManagement",
        view_func=generali_project_management,
    )
    app.add_url_rule(
        "/generali/projectManagement/monthreport",
        endpoint="generali_projectmanagement_monthreport",
        view_func=generali_projectmanagement_monthreport,
    )
    app.add_url_rule(
        "/api/generali/projectmanagement/orgUsers",
        endpoint="api_generali_projectmanagement_org_users",
        view_func=api_generali_projectmanagement_org_users,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/projectmanagement/organizations",
        endpoint="api_generali_projectmanagement_organizations",
        view_func=api_generali_projectmanagement_organizations,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/projectmanagement/filterUsers",
        endpoint="api_generali_projectmanagement_filter_users",
        view_func=api_generali_projectmanagement_filter_users,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/projectmanagement",
        endpoint="api_generali_projectmanagement_list",
        view_func=api_generali_projectmanagement_list,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/generali/projectmanagement",
        endpoint="api_generali_projectmanagement_add",
        view_func=api_generali_projectmanagement_add,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/generali/projectmanagement/<int:record_id>",
        endpoint="api_generali_projectmanagement_edit",
        view_func=api_generali_projectmanagement_edit,
        methods=["PUT"],
    )
    app.add_url_rule(
        "/api/generali/projectmanagement/<int:record_id>",
        endpoint="api_generali_projectmanagement_delete",
        view_func=api_generali_projectmanagement_delete,
        methods=["DELETE"],
    )
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
    app.add_url_rule(
        "/generali/importStatus", endpoint="generali_importStatus", view_func=generali_import_status
    )
    app.add_url_rule(
        "/api/generali/importstatus",
        endpoint="api_generali_importstatus_list",
        view_func=api_generali_importstatus_list,
        methods=["GET"],
    )
