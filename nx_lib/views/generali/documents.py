"""Generali tenant: Evaluation/Documents (dashboard, document list, stats API)."""

import math
from datetime import date, timedelta

from flask import current_app, jsonify, redirect, render_template, request, session, url_for
from flask_babel import gettext as _

from ...extensions import cache
from ...security import page_visibility, require_permission


def days_in_range(start_date, end_date):
    """Every calendar day in ``[start_date, end_date]`` as ``YYYY-MM-DD`` strings.

    The dashboard's daily average and its trend x-axis both have to run over
    the days the user *selected*, not the days that happened to return rows --
    see ``api_generali_stats``. Accepts either bound with or without a time
    part (``2026-07-01`` / ``2026-07-01 00:00:00``).

    Returns ``[]`` for an unparsable bound or an inverted range, so callers
    fall back to the observed days instead of crashing on a shape we did not
    anticipate.
    """
    try:
        start = date.fromisoformat(str(start_date)[:10])
        end = date.fromisoformat(str(end_date)[:10])
    except (TypeError, ValueError):
        return []
    if end < start:
        return []
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


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


@require_permission("tenant.generali.view")
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


@require_permission("tenant.generali.documents.view")
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


@require_permission("tenant.generali.view")
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
            date_filter += " AND ScannedAt >= ?"
            date_params.append(start_date)
        if end_date:
            date_filter += " AND ScannedAt <= ?"
            date_params.append(end_date)

        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            f"""
            SELECT
                COUNT(*) as TotalDocs,
                SUM(CASE WHEN PostCheck1 = 'keineNachkontrolle' THEN 1 ELSE 0 END) as NK1_Pass,
                SUM(CASE WHEN PostCheck2 = 'keineNachkontrolle' THEN 1 ELSE 0 END) as NK2_Pass,
                SUM(CASE WHEN PostCheck1 = 'keineNachkontrolle' AND PostCheck2 = 'keineNachkontrolle' THEN 1 ELSE 0 END) as NK1_NK2_Pass
            FROM [dbo].[v_Documents]
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
            "1=1" + date_filter if date_filter else "ScannedAt >= DATEADD(day, -30, GETDATE())"
        )
        cursor.execute(
            f"""
            SELECT CAST(ScannedAt AS DATE) as d,
                   ISNULL(CommunicationType, 'Unknown') as k,
                   COUNT(*) as c
            FROM [dbo].[v_Documents]
            WHERE {trend_where}
            GROUP BY CAST(ScannedAt AS DATE), ISNULL(CommunicationType, 'Unknown')
            ORDER BY d
        """,
            date_params,
        )
        trend_rows = cursor.fetchall()

        observed = {str(r[0]) for r in trend_rows}
        # Every day in the selected range, including the ones with no rows.
        # Deriving the axis from the result set instead produced two bugs
        # (#249): a month missing 11 days was divided by 20 and so scored a
        # HIGHER daily average than a complete month -- the worse the
        # coverage, the better the KPI looked -- and the chart drew 03.07
        # adjacent to 15.07 as though they were consecutive, hiding the gap.
        # Falls back to the observed days if the bounds will not parse.
        labels = days_in_range(start_date, end_date) or sorted(observed)
        label_index = {d: i for i, d in enumerate(labels)}
        totals = [0] * len(labels)
        by_komm = {}
        for d, k, c in trend_rows:
            # A row outside the parsed range is dropped rather than raising:
            # labels no longer come from these rows, so membership is not
            # guaranteed the way it was when the axis was built from them.
            i = label_index.get(str(d))
            if i is None:
                continue
            totals[i] += c
            if k not in by_komm:
                by_komm[k] = [0] * len(labels)
            by_komm[k][i] += c

        trend_data = {"labels": labels, "values": totals, "byKommunikation": by_komm}

        kpis["avg_daily"] = round(total / len(labels), 1) if total > 0 and labels else 0
        # Coverage of the selected range, so the UI can qualify the average
        # rather than presenting a gap-inflated number as comparable.
        kpis["days_in_range"] = len(labels)
        # days_with_data is narrowed to the settled days a few lines below,
        # once the newest imported day is known.

        # Newest day the dashboard has any data for. The CSV import runs daily
        # and lags reality by a couple of days, so a range ending "today"
        # always trails off into days that are not in yet -- which reads as a
        # drop in volume rather than as data that has not arrived. Bounded to
        # 90 days so this stays an index-friendly probe, not a full scan.
        cursor.execute(
            """
            SELECT MAX(CAST(ScannedAt AS DATE))
            FROM [dbo].[v_Documents]
            WHERE ScannedAt >= DATEADD(day, -90, GETDATE())
        """
        )
        latest_row = cursor.fetchone()
        latest_day = latest_row[0] if latest_row else None
        kpis["latest_data_day"] = str(latest_day)[:10] if latest_day else None

        # "Not imported yet" and "that day produced nothing" are different
        # facts and must not be conflated. A range running to today trails off
        # into days the daily import has not reached; counting those as empty
        # days reported them as an outage, and kept the warning up until the
        # end date was dragged back behind the last genuinely empty day.
        latest_str = kpis["latest_data_day"]
        settled = [d for d in labels if d <= latest_str] if latest_str else list(labels)
        kpis["days_settled"] = len(settled)
        kpis["days_pending"] = len(labels) - len(settled)
        kpis["days_with_data"] = len(observed.intersection(settled))

        cursor.execute(
            f"""
            SELECT TOP 15 ISNULL(DocumentType, 'Unknown') as t, COUNT(*) as c
            FROM [dbo].[v_Documents]
            WHERE 1=1 {date_filter}
            GROUP BY DocumentType
            ORDER BY c DESC
        """,
            date_params,
        )
        rows = cursor.fetchall()
        doctype_data = {"labels": [r[0] for r in rows], "values": [r[1] for r in rows]}

        cursor.execute(
            f"""
            SELECT ISNULL(Recipient, 'Unknown') as e, COUNT(*) as c
            FROM [dbo].[v_Documents]
            WHERE 1=1 {date_filter}
            GROUP BY Recipient
            ORDER BY c DESC
        """,
            date_params,
        )
        rows = cursor.fetchall()

        empfaenger_data = {"labels": [r[0] for r in rows], "values": [r[1] for r in rows]}

        cursor.execute(
            f"""
            SELECT ISNULL(Language, 'Unknown') as s, COUNT(*) as c
            FROM [dbo].[v_Documents]
            WHERE 1=1 {date_filter}
            GROUP BY Language
            ORDER BY c DESC
        """,
            date_params,
        )
        rows = cursor.fetchall()

        language_data = {"labels": [r[0] for r in rows], "values": [r[1] for r in rows]}

        cursor.execute(
            f"""
            SELECT ISNULL(InboundChannel, 'Unknown') as k, COUNT(*) as c
            FROM [dbo].[v_Documents]
            WHERE 1=1 {date_filter}
            GROUP BY InboundChannel
            ORDER BY c DESC
        """,
            date_params,
        )
        rows = cursor.fetchall()

        channel_data = {"labels": [r[0] for r in rows], "values": [r[1] for r in rows]}

        cursor.execute(
            f"""
            SELECT ISNULL(PostCheck1,'Unknown') as nk1, ISNULL(PostCheck2,'Unknown') as nk2, COUNT(*) as c
            FROM [dbo].[v_Documents]
            WHERE 1=1 {date_filter}
            GROUP BY PostCheck1, PostCheck2
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


@require_permission("tenant.generali.documents.view")
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
            ("DocumentType", "doctype"),
            ("Recipient", "empfaenger"),
            ("Language", "sprache"),
            ("PostCheck1", "nk1"),
            ("PostCheck2", "nk2"),
            ("InboundChannel", "eingangskanal"),
            ("CommunicationType", "kommunikation"),
        ]:
            cursor.execute(
                f"SELECT DISTINCT {col} FROM [dbo].[v_Documents] WHERE {col} IS NOT NULL ORDER BY {col}"
            )
            result[key] = [r[0] for r in cursor.fetchall()]
        return jsonify({"success": True, "options": result})
    except Exception as e:
        current_app.logger.error(f"Generali Filter Options Error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("tenant.generali.documents.view")
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
        sort_by = request.args.get("sortBy", "ScannedAt")
        sort_dir = request.args.get("sortDir", "DESC").upper()
        group_by = request.args.get("groupBy", "")

        allowed_sort_cols = {
            "ScannedAt",
            "DocumentType",
            "Recipient",
            "Language",
            "InboundChannel",
            "PostCheck1",
            "PostCheck2",
            "AmountText",
            "CommunicationType",
        }
        if sort_by not in allowed_sort_cols:
            sort_by = "ScannedAt"
        if sort_dir not in ("ASC", "DESC"):
            sort_dir = "DESC"

        allowed_group_cols = {
            "DocumentType",
            "Recipient",
            "Language",
            "InboundChannel",
            "CommunicationType",
        }
        if group_by not in allowed_group_cols:
            group_by = ""

        where_clauses = ["1=1"]
        params = []

        if doc_type:
            where_clauses.append("DocumentType = ?")
            params.append(doc_type)
        if empfaenger:
            where_clauses.append("Recipient = ?")
            params.append(empfaenger)
        if sprache:
            where_clauses.append("Language = ?")
            params.append(sprache)
        if nk1:
            where_clauses.append("PostCheck1 = ?")
            params.append(nk1)
        if nk2:
            where_clauses.append("PostCheck2 = ?")
            params.append(nk2)
        if eingangskanal:
            where_clauses.append("InboundChannel = ?")
            params.append(eingangskanal)
        if kommunikation:
            where_clauses.append("CommunicationType = ?")
            params.append(kommunikation)
        if start_date:
            where_clauses.append("ScannedAt >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("ScannedAt <= ?")
            params.append(end_date)
        if search:
            where_clauses.append("""(
                DocumentId LIKE ? OR CAST(ScanCaseId AS NVARCHAR) LIKE ?
                OR Description LIKE ? OR ContactPerson LIKE ?
                OR PolicyNo LIKE ? OR ClaimNo LIKE ?
            )""")
            s = f"%{search}%"
            params.extend([s, s, s, s, s, s])

        where_sql = " AND ".join(where_clauses)

        order_parts = []
        if group_by:
            order_parts.append(f"{group_by} ASC")
        if sort_by != group_by:
            order_parts.append(f"{sort_by} {sort_dir}")
        order_sql = ", ".join(order_parts) if order_parts else "ScannedAt DESC"

        conn = engine_generali_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(f"SELECT COUNT(*) FROM [dbo].[v_Documents] WHERE {where_sql}", params)
        count_row = cursor.fetchone()
        assert count_row is not None  # SELECT COUNT(*) always returns exactly one row
        total_items = count_row[0]
        total_pages = math.ceil(total_items / per_page)

        cursor.execute(
            f"""
            SELECT
                DocumentId, ScanCaseId, ScanCaseFolderName, ScannedAt, DocumentType,
                Recipient, Language, CommunicationType, InboundChannel,
                AmountText, Currency, PostCheck1, PostCheck2, ScanLocation,
                Description, NotificationStatus, Direction, PendingText
            FROM [dbo].[v_Documents]
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


@require_permission("tenant.generali.documents.view")
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
            SELECT * FROM [dbo].[v_Documents]
            WHERE DocumentId = ?
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
