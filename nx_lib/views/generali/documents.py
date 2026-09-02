"""Generali tenant: Evaluation/Documents (dashboard, document list, stats API)."""

import math

from flask import current_app, jsonify, redirect, render_template, request, session, url_for
from flask_babel import gettext as _

from ...extensions import cache
from ...security import page_visibility, require_permission

# ----------------------------- Generali Evaluation -------------------------- #


def _generali_stats_cache_key():
    """Per-user + per-filter cache key for api_generali_stats, mirroring
    dashboard.py's make_cache_key precedent (request.path + userid + the
    request's own filter dimensions -- here startDate/endDate, the only
    query args the view's SQL actually consumes)."""
    return (
        f"{request.path}_{session.get('userid')}_"
        f"{request.args.get('startDate', '')}_{request.args.get('endDate', '')}"
    )


def _generali_filter_options_cache_key():
    """Per-user cache key for api_generali_filter_options. The view takes no
    query-string filters, so there is no filter dimension to fold in."""
    return f"{request.path}_{session.get('userid')}"


def _cacheable_response(rv):
    """response_filter for @cache.cached on the two Generali dashboard
    endpoints below -- same contract as dashboard.py's _cacheable_response:
    never pin an error (or validation-failure) response, or a transient 500 /
    a missing-date 400 would otherwise be served for the full TTL per
    user+filter."""
    status = rv[1] if isinstance(rv, tuple) and len(rv) == 2 else getattr(rv, "status_code", 200)
    return status < 400


@require_permission("generali.dashboard.view")
def generali_evaluation():
    try:
        if "username" not in session:
            return redirect(url_for("login"))
        return render_template(
            "generali-dashboard.html",
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            page_visibility=page_visibility(),
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
            page_visibility=page_visibility(),
        )
    except Exception as e:
        current_app.logger.error(f"Error loading Generali Documents: {e}")
        return render_template("handlers/500.html"), 500


@require_permission("generali.dashboard.view")
@cache.cached(
    timeout=120,
    key_prefix=_generali_stats_cache_key,  # type: ignore[arg-type]  # callable prefix, stubs say str
    response_filter=_cacheable_response,
)
def api_generali_stats():
    conn = None
    try:
        # local import: re-resolve against the live package object so test
        # monkeypatching of gv.engine_generali_db works consistently across
        # the generali package
        from . import engine_generali_db

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
        assert kpi_row is not None  # aggregate SELECT always returns exactly one row
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
@cache.cached(
    timeout=120,
    key_prefix=_generali_filter_options_cache_key,  # type: ignore[arg-type]  # callable prefix, stubs say str
    response_filter=_cacheable_response,
)
def api_generali_filter_options():
    conn = None
    try:
        # local import: re-resolve against the live package object so test
        # monkeypatching of gv.engine_generali_db works consistently across
        # the generali package
        from . import engine_generali_db

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
        # local import: re-resolve against the live package object so test
        # monkeypatching of gv.engine_generali_db works consistently across
        # the generali package
        from . import engine_generali_db

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
        count_row = cursor.fetchone()
        assert count_row is not None  # SELECT COUNT(*) always returns exactly one row
        total_items = count_row[0]
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
        # local import: re-resolve against the live package object so test
        # monkeypatching of gv.engine_generali_db works consistently across
        # the generali package
        from . import engine_generali_db

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
