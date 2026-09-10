"""Generali tenant: Import Status."""

from flask import current_app, jsonify, redirect, render_template, request, session, url_for
from flask_babel import gettext as _

from ...security import page_visibility, require_permission

# ----------------------------- Generali Import Status ---------------------- #


@require_permission("tenant.generali.importstatus.view")
def generali_import_status():
    try:
        if "username" not in session:
            return redirect(url_for("login"))
        return render_template(
            "generali_importstatus.html",
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            page_visibility=page_visibility(),
            organizationcode=session.get("organizationcode"),
        )
    except Exception as e:
        current_app.logger.error(f"Error loading Generali Import Status: {e}")
        return render_template("handlers/500.html"), 500


@require_permission("tenant.generali.importstatus.view")
def api_generali_importstatus_list():
    conn = None
    try:
        # local import: re-resolve against the live package object so test
        # monkeypatching of gv.engine_generali_db works consistently across
        # the generali package
        from . import engine_generali_db

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

        cursor.execute(f"SELECT COUNT(*) FROM [Generali].[dbo].[ImportRuns] {where_sql}", params)
        count_row = cursor.fetchone()
        assert count_row is not None  # SELECT COUNT(*) always returns exactly one row
        total_records = count_row[0] or 0
        total_pages = max(1, -(-total_records // per_page))

        cursor.execute(
            f"""
            SELECT ID, FileName, StartedAt, FinishedAt, CSVRowCount,
                   RowsInserted, RowsUpdated, MinScannedAt, MaxScannedAt, [Status]
            FROM [Generali].[dbo].[ImportRuns]
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
        "/generali/importStatus",
        endpoint="generali_import_status",
        view_func=generali_import_status,
    )
    app.add_url_rule(
        "/api/generali/importstatus",
        endpoint="api_generali_importstatus_list",
        view_func=api_generali_importstatus_list,
        methods=["GET"],
    )
