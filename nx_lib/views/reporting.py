"""Self-service Reporting page (curated table sources) — Phase 1.

Routes:
  GET  /reporting                     builder page
  GET  /reporting/sources             source-registry admin page (reporting.admin.sources)
  GET  /api/reporting/sources         sources + field catalog the caller may use
  GET/POST/PUT/DELETE /api/reporting/admin/sources[/<id>]  registry CRUD (admin)
  POST /api/reporting/run             run a curated report definition -> rows
  POST /api/reporting/sql/run         run sandboxed live SQL -> rows (audited)
  POST /api/reporting/sql/ack         record the live-SQL acknowledgment
  POST /api/reporting/export          report definition -> .xlsx/.csv download
  POST /api/reporting/export/grid     client-supplied grid (pivot) -> .xlsx/.csv download
  GET  /api/reporting/reports         list reports the caller owns or may see
  POST /api/reporting/reports         create a saved report
  GET  /api/reporting/reports/<id>    load one (own / shared / shared-with-me)
  PUT  /api/reporting/reports/<id>    update (owner or share with CanEdit)
  DELETE /api/reporting/reports/<id>  delete (owner only)
  GET  /api/reporting/reports/<id>/shares          owner: visibility + shares
  POST /api/reporting/reports/<id>/shares          owner: set visibility / add share
  DELETE /api/reporting/reports/<id>/shares/<uid>  owner: remove a share
"""

import json
import re
import time

from flask import (
    Response,
    current_app,
    jsonify,
    render_template,
    request,
    session,
)
from flask_babel import gettext as _

from ..db import (
    engine_generali_db,
    engine_nexora_db,
    engine_octo_db,
    engine_octo_ro,
    engine_statistics_db,
    engine_statistics_ro,
)
from ..extensions import limiter
from ..i18n import get_locale
from ..reporting.catalog import fetch_docprocessing_catalog
from ..reporting.export import rows_to_csv, rows_to_xlsx
from ..reporting.query import QueryBuildError, build_table_query
from ..reporting.sandbox import SqlSandboxError, validate_select, wrap_with_cap
from ..reporting.schema import (
    ReportDefinitionError,
    validate_report_definition,
    validate_sql_definition,
)
from ..reporting.sources import (
    DEFAULT_ROW_LIMIT,
    MAX_ROW_LIMIT,
    SQL_ROW_CAP,
    SQL_TIMEOUT_S,
    accessible,
    code_sources,
    merge_sources,
)
from ..reporting.table_query import (
    TableQueryError,
    build_generic_query,
    table_source_catalog,
)
from ..security import has_permission, page_visibility, require_permission

_SCOPE_PREFIX = "reporting.scope.process."

_SQL_TARGET_ENGINES = {
    "statistics": engine_statistics_ro,
    "octopus": engine_octo_ro,
}
_SQL_TARGETS = set(_SQL_TARGET_ENGINES)

# Per-target permission. The base reporting.sql.run gate (on the routes) covers
# the Statistics target; Octopus — the runtime DB — additionally requires its
# own grant so SQL access and runtime-DB access can be separated.
_SQL_TARGET_PERMISSION = {
    "statistics": "reporting.sql.run",
    "octopus": "reporting.sql.target.octopus",
}


# Engines a curated source's generic 'table' provider may read from (SELECT-only).
_CURATED_ENGINES = {
    "nexora": engine_nexora_db,
    "statistics": engine_statistics_db,
    "generali": engine_generali_db,
    "octopus": engine_octo_db,
}


def _load_db_sources():
    """Read dbo.ReportingSources registry rows as descriptor dicts (best-effort).

    A missing table or read error yields an empty list, so the page degrades to
    the code-defined defaults rather than 500-ing.
    """
    try:
        conn = engine_nexora_db.raw_connection()
    except Exception as e:
        current_app.logger.warning(f"reporting sources: registry unavailable: {e}")
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT Code, Kind, Label, Permission, Engine, Target, Provider, "
            "BaseObject, ColumnsJSON, Enabled, SortOrder FROM dbo.ReportingSources"
        )
        rows = []
        for r in cur.fetchall():
            columns = None
            if r.ColumnsJSON:
                try:
                    columns = json.loads(r.ColumnsJSON)
                except (ValueError, TypeError):
                    columns = None
            rows.append(
                {
                    "code": r.Code,
                    "kind": r.Kind,
                    "label": r.Label,
                    "permission": r.Permission,
                    "engine": r.Engine,
                    "target": r.Target,
                    "provider": r.Provider,
                    "baseObject": r.BaseObject,
                    "columns": columns,
                    "enabled": bool(r.Enabled),
                    "sortOrder": r.SortOrder,
                }
            )
        return rows
    except Exception as e:
        current_app.logger.warning(f"reporting sources: registry read failed: {e}")
        return []
    finally:
        conn.close()


def _effective_sources():
    """Code defaults overlaid with the DB registry; enabled + sorted."""
    return merge_sources(code_sources(), _load_db_sources())


def _get_effective_source(source_id):
    for s in _effective_sources():
        if s.get("id") == source_id:
            return s
    return None


def _authorize_sql_target(target):
    """Raise PermissionError unless the caller may use this SQL target.

    Unknown targets are left for _run_sql to reject (ReportDefinitionError),
    so a bad target reads as 400 "unknown SQL target", not 403.
    """
    perm = _SQL_TARGET_PERMISSION.get(target)
    if perm is not None and not has_permission(perm):
        raise PermissionError(perm)


def _has_acked(userid):
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM ReportingSqlAck WHERE UserID = ?", (userid,))
        return cur.fetchone() is not None
    finally:
        conn.close()


def _audit_sql(userid, username, target, sql_text, rows_returned, status, duration_ms):
    try:
        conn = engine_nexora_db.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO ReportingSqlAudit "
                "(UserID, Username, TargetDB, SqlText, RowsReturned, Status, DurationMs) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (userid, username, target, sql_text, rows_returned, status, duration_ms),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        current_app.logger.error(f"reporting sql audit insert failed: {e}")
    current_app.logger.info(
        f"reporting.sql.run user={userid} target={target} status={status} "
        f"rows={rows_returned} ms={duration_ms}"
    )


def _run_sql(target, sql, *, userid, username):
    """Validate + execute sandboxed SQL on the RO engine. Returns (columns, rows).

    Raises ReportDefinitionError (bad target), SqlSandboxError (bad SQL),
    RuntimeError (RO engine unconfigured). Audits rejected/error/run paths.
    """
    if target not in _SQL_TARGETS:
        raise ReportDefinitionError("unknown SQL target")
    engine = _SQL_TARGET_ENGINES.get(target)
    if engine is None:
        current_app.logger.warning(
            f"reporting.sql.run blocked: target={target!r} read-only engine is "
            f"unconfigured (user={userid}) — set the DB_REPORTING_*_RO_* credentials"
        )
        raise RuntimeError("SQL source not configured")
    try:
        validated = validate_select(sql)
    except SqlSandboxError:
        _audit_sql(
            userid, username, target, sql if isinstance(sql, str) else "", None, "rejected", None
        )
        raise
    wrapped = wrap_with_cap(validated, SQL_ROW_CAP)
    start = time.monotonic()
    conn = engine.raw_connection()
    try:
        conn.dbapi_connection.timeout = SQL_TIMEOUT_S  # pyodbc query timeout (seconds)
        cur = conn.cursor()
        cur.execute(wrapped)
        col_names = [d[0] for d in cur.description] if cur.description else []
        rows = [list(r) for r in cur.fetchall()]
    except Exception:
        _audit_sql(
            userid,
            username,
            target,
            validated,
            None,
            "error",
            int((time.monotonic() - start) * 1000),
        )
        raise
    finally:
        conn.close()
    _audit_sql(
        userid,
        username,
        target,
        validated,
        len(rows),
        "run",
        int((time.monotonic() - start) * 1000),
    )
    columns = [{"field": c, "header": c} for c in col_names]
    return columns, rows


def _allowed_processes():
    """Processes the caller may include, from reporting.scope.process.* perms.

    Code shape: reporting.scope.process.<client>.<process> -> '<client>.<process>'.
    """
    perms = session.get("permissions", [])
    return sorted(
        {
            ".".join(p[len(_SCOPE_PREFIX) :].rsplit(".", 1))
            for p in perms
            if p.startswith(_SCOPE_PREFIX)
        }
    )


def _load_process_configs(target_processes):
    """Load Statconfig rows for the target processes as plain dicts."""
    if not target_processes:
        return []
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        ph = ",".join(["?"] * len(target_processes))
        cur.execute(
            f"SELECT ProcessName, TableName, ExportColumn, ImportColumn, additionalCondition "
            f"FROM Statconfig WHERE ProcessName IN ({ph})",
            target_processes,
        )
        return [
            {
                "process": r.ProcessName,
                "table": r.TableName,
                "export_col": r.ExportColumn,
                "import_col": r.ImportColumn,
                "condition": r.additionalCondition or "",
            }
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def _load_field_col_maps(target_processes):
    """Load per-process {field_key: actual_column} maps from SearchConfig."""
    maps = {}
    if not target_processes:
        return maps
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT TOP 0 * FROM SearchConfig")
        cols = [c[0] for c in cur.description if c[0].startswith("col_")]
        if not cols:
            return maps
        select_cols = ", ".join(cols)
        ph = ",".join(["?"] * len(target_processes))
        cur.execute(
            f"SELECT ProcessName, {select_cols} FROM SearchConfig WHERE ProcessName IN ({ph})",
            target_processes,
        )
        for row in cur.fetchall():
            m = {}
            for i, col in enumerate(cols):
                val = row[i + 1]
                if val:
                    m[col[len("col_") :]] = val
            maps[row.ProcessName] = m
        return maps
    finally:
        conn.close()


def _effective_scope(rd, allowed):
    """Intersection of requested scope.processes and the caller's allowed set."""
    requested = (rd.get("scope") or {}).get("processes") or []
    allowed_set = set(allowed)
    if not requested:
        return list(allowed)
    return [p for p in requested if p in allowed_set]


def _prepare_run(rd):
    """Validate + build a query for a curated report.

    Returns (columns, sql, params, engine). Dispatches on the source's provider:
    'docprocessing' (the Statconfig builder over Statistics) or 'table' (the
    generic single-object builder over the source's configured engine).

    Raises ReportDefinitionError / QueryBuildError / TableQueryError on bad input.
    """
    source = _get_effective_source(rd.get("source"))
    if source is None or source.get("kind") != "curated":
        raise ReportDefinitionError("unknown or unsupported source")
    if not has_permission(source["permission"]):
        raise PermissionError(source["permission"])

    provider = source.get("provider") or "docprocessing"
    if provider == "docprocessing":
        allowed = _allowed_processes()
        catalog = fetch_docprocessing_catalog(allowed, str(get_locale()))
        catalog_fields = {f["field"] for f in catalog}
        filterable = {f["field"] for f in catalog if f["filterable"]}
        sortable = {f["field"] for f in catalog if f["sortable"]}
        validate_report_definition(
            rd, catalog_fields, filterable, sortable, max_row_limit=MAX_ROW_LIMIT
        )
        scope = _effective_scope(rd, allowed)
        configs = _load_process_configs(scope)
        col_maps = _load_field_col_maps(scope)
        sql, params = build_table_query(
            rd, configs, col_maps, row_cap=rd.get("rowLimit", DEFAULT_ROW_LIMIT)
        )
        return rd["columns"], sql, params, engine_statistics_db

    if provider == "table":
        catalog = table_source_catalog(source.get("columns"))
        catalog_fields = {f["field"] for f in catalog}
        filterable = {f["field"] for f in catalog if f["filterable"]}
        sortable = {f["field"] for f in catalog if f["sortable"]}
        validate_report_definition(
            rd, catalog_fields, filterable, sortable, max_row_limit=MAX_ROW_LIMIT
        )
        sql, params = build_generic_query(
            rd,
            source.get("baseObject"),
            catalog,
            row_cap=rd.get("rowLimit", DEFAULT_ROW_LIMIT),
        )
        engine = _CURATED_ENGINES.get(source.get("engine"))
        if engine is None:
            raise ReportDefinitionError("source engine is not configured")
        return rd["columns"], sql, params, engine

    raise ReportDefinitionError("unsupported source provider")


def _execute(engine, sql, params):
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return [list(r) for r in cur.fetchall()]
    finally:
        conn.close()


_EXPORT_FORMATS = {"xlsx", "csv"}


def _safe_report_name(title):
    """Filesystem/header-safe base filename for an export download."""
    return re.sub(r'[\x00-\x1f\x7f";]', "_", (title or "report").strip()) or "report"


def _resolve_export_format(value):
    """Normalize a requested export format to a supported one (defaults to xlsx)."""
    fmt = (value or "xlsx").lower()
    return fmt if fmt in _EXPORT_FORMATS else "xlsx"


def _serialize_export(columns, rows, title, fmt):
    """Build a Flask download Response for `rows` in the requested format."""
    name = _safe_report_name(title)
    if fmt == "csv":
        return Response(
            rows_to_csv(columns, rows),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
        )
    return Response(
        rows_to_xlsx(columns, rows, title=title or "Report"),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'},
    )


@require_permission("reporting.view")
def reporting():
    return render_template(
        "reporting.html",
        logged_in_user=session.get("username", "Unknown"),
        userid=session.get("userid", "Unknown"),
        fullname=session.get("fullname"),
        pageV=page_visibility(),
    )


@require_permission("reporting.view")
def api_sources():
    perms = set(session.get("permissions", []))
    sources = accessible(_effective_sources(), perms)
    procs = _allowed_processes()
    out = []
    for s in sources:
        entry = {"id": s["id"], "label": s["label"], "kind": s["kind"]}
        if s["kind"] == "curated":
            provider = s.get("provider") or "docprocessing"
            if provider == "docprocessing":
                try:
                    entry["fields"] = fetch_docprocessing_catalog(procs, str(get_locale()))
                except Exception as e:
                    current_app.logger.warning(f"reporting sources: catalog unavailable: {e}")
                    entry["fields"] = []
                entry["processes"] = procs
            else:  # generic 'table' provider — catalog from the registry columns
                entry["fields"] = table_source_catalog(s.get("columns"))
                entry["processes"] = []
        elif s["kind"] == "sql":
            entry["target"] = s.get("target", "statistics")
            entry["acknowledged"] = _has_acked(session.get("userid"))
        out.append(entry)
    return jsonify(out)


@require_permission("reporting.view")
@limiter.limit("120 per minute")
def api_run():
    rd = request.get_json(silent=True)
    if not isinstance(rd, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    try:
        columns, sql, params, engine = _prepare_run(rd)
    except PermissionError:
        return jsonify({"error": _("Not authorized for this source")}), 403
    except (ReportDefinitionError, QueryBuildError, TableQueryError) as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"/api/reporting/run prepare error: {e}")
        return jsonify({"error": _("Could not build report")}), 500
    try:
        rows = _execute(engine, sql, params)
    except Exception as e:
        current_app.logger.error(f"/api/reporting/run exec error: {e}")
        return jsonify({"error": _("Could not run report")}), 500
    return jsonify(
        {
            "columns": [
                {"field": c["field"], "header": c.get("header") or c["field"]} for c in columns
            ],
            "rows": rows,
            "rowCount": len(rows),
            "truncated": len(rows)
            >= min(int(rd.get("rowLimit", DEFAULT_ROW_LIMIT)), MAX_ROW_LIMIT),
        }
    )


@require_permission("reporting.sql.run")
@limiter.limit("20 per minute")
def api_sql_run():
    rd = request.get_json(silent=True)
    if not isinstance(rd, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    userid = session.get("userid")
    username = session.get("username")
    if not userid:
        return jsonify({"error": _("Not authenticated")}), 401
    if not _has_acked(userid):
        return jsonify({"error": _("Acknowledgment required"), "needAck": True}), 409
    try:
        _authorize_sql_target(rd.get("target"))
        columns, rows = _run_sql(rd.get("target"), rd.get("sql"), userid=userid, username=username)
    except PermissionError:
        return jsonify({"error": _("Not authorized for this SQL target")}), 403
    except SqlSandboxError as e:
        return jsonify({"error": str(e), "rule": e.rule}), 400
    except ReportDefinitionError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError:
        return jsonify({"error": _("SQL source is not configured")}), 503
    except Exception as e:
        current_app.logger.error(f"/api/reporting/sql/run exec error: {e}")
        return jsonify({"error": _("Could not run query")}), 500
    return jsonify(
        {
            "columns": columns,
            "rows": rows,
            "rowCount": len(rows),
            "truncated": len(rows) >= SQL_ROW_CAP,
        }
    )


@require_permission("reporting.sql.run")
@limiter.limit("10 per minute")
def api_sql_ack():
    userid = session.get("userid")
    if not userid:
        return jsonify({"error": _("Not authenticated")}), 401
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "IF NOT EXISTS (SELECT 1 FROM ReportingSqlAck WHERE UserID = ?) "
            "INSERT INTO ReportingSqlAck (UserID) VALUES (?)",
            (userid, userid),
        )
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"/api/reporting/sql/ack error: {e}")
        return jsonify({"error": _("Could not record acknowledgment")}), 500
    finally:
        conn.close()


@require_permission("reporting.export")
@limiter.limit("30 per minute")
def api_export():
    rd = request.get_json(silent=True)
    if not isinstance(rd, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    fmt = _resolve_export_format(rd.get("format"))
    if rd.get("kind") == "sql":
        if not has_permission("reporting.sql.run"):
            return jsonify({"error": _("Not authorized for live SQL")}), 403
        userid = session.get("userid")
        if not _has_acked(userid):
            return jsonify({"error": _("Acknowledgment required"), "needAck": True}), 409
        try:
            validate_sql_definition(rd, allowed_targets=_SQL_TARGETS)
            _authorize_sql_target(rd["target"])
            columns, rows = _run_sql(
                rd["target"], rd["sql"], userid=userid, username=session.get("username")
            )
        except PermissionError:
            return jsonify({"error": _("Not authorized for this SQL target")}), 403
        except SqlSandboxError as e:
            return jsonify({"error": str(e), "rule": e.rule}), 400
        except ReportDefinitionError as e:
            return jsonify({"error": str(e)}), 400
        except RuntimeError:
            return jsonify({"error": _("SQL source is not configured")}), 503
        except Exception as e:
            current_app.logger.error(f"/api/reporting/export sql error: {e}")
            return jsonify({"error": _("Could not export query")}), 500
        return _serialize_export(columns, rows, rd.get("title") or "Report", fmt)
    try:
        columns, sql, params, engine = _prepare_run(rd)
        rows = _execute(engine, sql, params)
    except PermissionError:
        return jsonify({"error": _("Not authorized for this source")}), 403
    except (ReportDefinitionError, QueryBuildError, TableQueryError) as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"/api/reporting/export error: {e}")
        return jsonify({"error": _("Could not export report")}), 500
    return _serialize_export(columns, rows, rd.get("title") or "Report", fmt)


@require_permission("reporting.export")
@limiter.limit("30 per minute")
def api_export_grid():
    """Serialize a client-supplied result grid (e.g. a pivot matrix) to a file.

    The chart/pivot result views aggregate client-side, so the caller sends the
    already-computed {columns, rows} it is displaying. No DB access happens here;
    the same reporting.export permission and formula-injection guard still apply.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    raw_cols = payload.get("columns")
    rows = payload.get("rows")
    if not isinstance(raw_cols, list) or not raw_cols or not isinstance(rows, list):
        return jsonify({"error": _("columns and rows are required")}), 400
    columns = []
    for c in raw_cols:
        if isinstance(c, dict):
            header = c.get("header") or c.get("field") or ""
            columns.append({"field": c.get("field") or header, "header": header})
        else:
            columns.append({"field": str(c), "header": str(c)})
    rows = [list(r) if isinstance(r, list | tuple) else [r] for r in rows[:MAX_ROW_LIMIT]]
    fmt = _resolve_export_format(payload.get("format"))
    return _serialize_export(columns, rows, payload.get("title") or "Report", fmt)


@require_permission("reporting.view")
def api_reports_list():
    """List reports the caller owns, plus any shared with them.

    A report is visible when the caller owns it, its Visibility is 'shared'
    (everyone with reporting.view), or it is explicitly shared with the caller.
    Each row is tagged owned / canEdit and carries the owner's name.
    """
    userid = session.get("userid")
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT r.ReportID, r.Name, r.UpdatedAt, r.Visibility, r.OwnerUserID, "
            "       u.username AS OwnerName, "
            "       JSON_VALUE(r.DefinitionJSON, '$.kind') AS Kind, "
            "       CASE WHEN r.OwnerUserID = ? THEN 1 ELSE 0 END AS Owned, "
            "       CASE WHEN r.OwnerUserID = ? THEN 1 "
            "            WHEN s.CanEdit = 1 THEN 1 ELSE 0 END AS CanEdit "
            "FROM dbo.Reports r "
            "JOIN dbo.Users u ON u.userID = r.OwnerUserID "
            "LEFT JOIN dbo.ReportShares s "
            "       ON s.ReportID = r.ReportID AND s.SharedWithUserID = ? "
            "WHERE r.OwnerUserID = ? OR r.Visibility = 'shared' OR s.SharedWithUserID = ? "
            "ORDER BY Owned DESC, r.UpdatedAt DESC",
            (userid, userid, userid, userid, userid),
        )
        return jsonify(
            [
                {
                    "id": r.ReportID,
                    "name": r.Name,
                    "updatedAt": str(r.UpdatedAt),
                    "kind": r.Kind or "table",
                    "visibility": r.Visibility,
                    "owned": bool(r.Owned),
                    "canEdit": bool(r.CanEdit),
                    "ownerName": r.OwnerName,
                }
                for r in cur.fetchall()
            ]
        )
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports list error: {e}")
        return jsonify({"error": _("Could not list reports")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
def api_reports_get(report_id):
    userid = session.get("userid")
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT r.Name, r.DefinitionJSON, r.Visibility, r.OwnerUserID, "
            "       CASE WHEN r.OwnerUserID = ? THEN 1 ELSE 0 END AS Owned, "
            "       CASE WHEN r.OwnerUserID = ? THEN 1 "
            "            WHEN s.CanEdit = 1 THEN 1 ELSE 0 END AS CanEdit "
            "FROM dbo.Reports r "
            "LEFT JOIN dbo.ReportShares s "
            "       ON s.ReportID = r.ReportID AND s.SharedWithUserID = ? "
            "WHERE r.ReportID = ? "
            "  AND (r.OwnerUserID = ? OR r.Visibility = 'shared' OR s.SharedWithUserID = ?)",
            (userid, userid, userid, report_id, userid, userid),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": _("Not found")}), 404
        return jsonify(
            {
                "id": report_id,
                "name": row.Name,
                "definition": json.loads(row.DefinitionJSON),
                "visibility": row.Visibility,
                "owned": bool(row.Owned),
                "canEdit": bool(row.CanEdit),
            }
        )
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports get error: {e}")
        return jsonify({"error": _("Could not load report")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
@limiter.limit("60 per minute")
def api_reports_create():
    userid = session.get("userid")
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    rd = payload.get("definition")
    if not name or not isinstance(rd, dict):
        return jsonify({"error": _("name and definition are required")}), 400
    definition_json = json.dumps(rd, ensure_ascii=False)
    if len(definition_json) > 64_000:
        return jsonify({"error": _("Report definition too large")}), 400
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO Reports (OwnerUserID, Name, DefinitionJSON) OUTPUT INSERTED.ReportID VALUES (?, ?, ?)",
            (userid, name, definition_json),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({"id": new_id, "ok": True})
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports create error: {e}")
        return jsonify({"error": _("Could not save report")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
@limiter.limit("60 per minute")
def api_reports_update(report_id):
    userid = session.get("userid")
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    rd = payload.get("definition")
    if not name or not isinstance(rd, dict):
        return jsonify({"error": _("name and definition are required")}), 400
    definition_json = json.dumps(rd, ensure_ascii=False)
    if len(definition_json) > 64_000:
        return jsonify({"error": _("Report definition too large")}), 400
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        # Owner, or a colleague the owner shared it with for editing.
        cur.execute(
            "UPDATE r SET Name = ?, DefinitionJSON = ?, UpdatedAt = SYSUTCDATETIME() "
            "FROM dbo.Reports r "
            "WHERE r.ReportID = ? "
            "  AND (r.OwnerUserID = ? OR EXISTS ("
            "        SELECT 1 FROM dbo.ReportShares s "
            "        WHERE s.ReportID = r.ReportID AND s.SharedWithUserID = ? AND s.CanEdit = 1))",
            (name, definition_json, report_id, userid, userid),
        )
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports update error: {e}")
        return jsonify({"error": _("Could not update report")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
def api_reports_delete(report_id):
    userid = session.get("userid")
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM Reports WHERE ReportID = ? AND OwnerUserID = ?",
            (report_id, userid),
        )
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports delete error: {e}")
        return jsonify({"error": _("Could not delete report")}), 500
    finally:
        conn.close()


def _is_report_owner(report_id, userid):
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM dbo.Reports WHERE ReportID = ? AND OwnerUserID = ?",
            (report_id, userid),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def _resolve_user(identifier):
    """Resolve a username or email to {userId, name}, or None if unknown."""
    ident = (identifier or "").strip()
    if not ident:
        return None
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 1 userID, username, Fullname FROM dbo.Users "
            "WHERE username = ? OR Email = ?",
            (ident, ident),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"userId": row.userID, "name": row.Fullname or row.username}
    finally:
        conn.close()


def _shares_payload(report_id):
    """Current sharing state for a report: {visibility, shares:[...]}."""
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT Visibility FROM dbo.Reports WHERE ReportID = ?", (report_id,))
        row = cur.fetchone()
        visibility = row.Visibility if row else "private"
        cur.execute(
            "SELECT s.SharedWithUserID, s.CanEdit, u.username, u.Fullname "
            "FROM dbo.ReportShares s JOIN dbo.Users u ON u.userID = s.SharedWithUserID "
            "WHERE s.ReportID = ? ORDER BY u.username",
            (report_id,),
        )
        shares = [
            {
                "userId": r.SharedWithUserID,
                "name": r.Fullname or r.username,
                "username": r.username,
                "canEdit": bool(r.CanEdit),
            }
            for r in cur.fetchall()
        ]
    finally:
        conn.close()
    return {"visibility": visibility, "shares": shares}


@require_permission("reporting.view")
def api_reports_shares_get(report_id):
    userid = session.get("userid")
    # 404 (not 403) for non-owners so a report's existence isn't leaked.
    if not _is_report_owner(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    return jsonify(_shares_payload(report_id))


@require_permission("reporting.view")
@limiter.limit("60 per minute")
def api_reports_shares_set(report_id):
    """Owner sets a report's visibility and/or adds/updates one user share."""
    userid = session.get("userid")
    if not _is_report_owner(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    payload = request.get_json(silent=True) or {}
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        visibility = payload.get("visibility")
        if visibility is not None:
            if visibility not in ("private", "shared"):
                return jsonify({"error": _("Invalid visibility")}), 400
            cur.execute(
                "UPDATE dbo.Reports SET Visibility = ? WHERE ReportID = ?",
                (visibility, report_id),
            )
        user_ident = payload.get("user")
        if user_ident:
            target = _resolve_user(user_ident)
            if not target:
                return jsonify({"error": _("User not found")}), 404
            if str(target["userId"]) == str(userid):
                return jsonify({"error": _("Cannot share a report with yourself")}), 400
            can_edit = 1 if payload.get("canEdit") else 0
            cur.execute(
                "SELECT 1 FROM dbo.ReportShares WHERE ReportID = ? AND SharedWithUserID = ?",
                (report_id, target["userId"]),
            )
            if cur.fetchone():
                cur.execute(
                    "UPDATE dbo.ReportShares SET CanEdit = ? "
                    "WHERE ReportID = ? AND SharedWithUserID = ?",
                    (can_edit, report_id, target["userId"]),
                )
            else:
                cur.execute(
                    "INSERT INTO dbo.ReportShares (ReportID, SharedWithUserID, CanEdit) "
                    "VALUES (?, ?, ?)",
                    (report_id, target["userId"], can_edit),
                )
        conn.commit()
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports shares set error: {e}")
        return jsonify({"error": _("Could not update sharing")}), 500
    finally:
        conn.close()
    return jsonify(_shares_payload(report_id))


@require_permission("reporting.view")
def api_reports_shares_delete(report_id, share_user_id):
    userid = session.get("userid")
    if not _is_report_owner(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM dbo.ReportShares WHERE ReportID = ? AND SharedWithUserID = ?",
            (report_id, share_user_id),
        )
        conn.commit()
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports shares delete error: {e}")
        return jsonify({"error": _("Could not update sharing")}), 500
    finally:
        conn.close()
    return jsonify(_shares_payload(report_id))


# ---- Source-registry admin (reporting.admin.sources) ----------------------

_SOURCE_CODE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def _validate_source_payload(p):
    """Return an error string for an invalid registry payload, else None."""
    if not isinstance(p, dict):
        return _("Invalid body")
    if not _SOURCE_CODE_RE.match((p.get("code") or "").strip()):
        return _("code must be 1-64 chars: letters, digits, . _ -")
    if p.get("kind") not in ("curated", "sql"):
        return _("kind must be 'curated' or 'sql'")
    if not (p.get("label") or "").strip():
        return _("label is required")
    if not (p.get("permission") or "").strip():
        return _("permission is required")
    cols = p.get("columns")
    if isinstance(cols, str) and cols.strip():
        try:
            json.loads(cols)
        except (ValueError, TypeError):
            return _("columns must be valid JSON")
    return None


def _columns_to_json(columns):
    if columns is None or columns == "":
        return None
    if isinstance(columns, str):
        return columns if columns.strip() else None
    return json.dumps(columns, ensure_ascii=False)


def _source_insert_params(p):
    return (
        p["code"].strip(),
        p["kind"],
        p["label"].strip(),
        p["permission"].strip(),
        p.get("engine") or None,
        p.get("target") or None,
        p.get("provider") or None,
        p.get("baseObject") or None,
        _columns_to_json(p.get("columns")),
        1 if p.get("enabled", True) else 0,
        int(p.get("sortOrder") or 100),
    )


@require_permission("reporting.admin.sources")
def reporting_sources_admin():
    return render_template(
        "reporting_sources.html",
        logged_in_user=session.get("username", "Unknown"),
        fullname=session.get("fullname"),
        pageV=page_visibility(),
    )


@require_permission("reporting.admin.sources")
def api_admin_sources_list():
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT SourceID, Code, Kind, Label, Permission, Engine, Target, Provider, "
            "BaseObject, ColumnsJSON, Enabled, SortOrder FROM dbo.ReportingSources "
            "ORDER BY SortOrder, Label"
        )
        rows = [
            {
                "id": r.SourceID,
                "code": r.Code,
                "kind": r.Kind,
                "label": r.Label,
                "permission": r.Permission,
                "engine": r.Engine,
                "target": r.Target,
                "provider": r.Provider,
                "baseObject": r.BaseObject,
                "columnsJson": r.ColumnsJSON,
                "enabled": bool(r.Enabled),
                "sortOrder": r.SortOrder,
            }
            for r in cur.fetchall()
        ]
    except Exception as e:
        current_app.logger.error(f"reporting admin sources list error: {e}")
        return jsonify({"error": _("Could not list sources")}), 500
    finally:
        conn.close()
    return jsonify({"defaults": code_sources(), "rows": rows})


@require_permission("reporting.admin.sources")
@limiter.limit("60 per minute")
def api_admin_sources_create():
    p = request.get_json(silent=True) or {}
    err = _validate_source_payload(p)
    if err:
        return jsonify({"error": err}), 400
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.ReportingSources "
            "(Code, Kind, Label, Permission, Engine, Target, Provider, BaseObject, "
            " ColumnsJSON, Enabled, SortOrder) "
            "OUTPUT INSERTED.SourceID VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _source_insert_params(p),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({"id": new_id, "ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting admin sources create error: {e}")
        return jsonify({"error": _("Could not save source (code already exists?)")}), 500
    finally:
        conn.close()


@require_permission("reporting.admin.sources")
@limiter.limit("60 per minute")
def api_admin_sources_update(source_id):
    p = request.get_json(silent=True) or {}
    err = _validate_source_payload(p)
    if err:
        return jsonify({"error": err}), 400
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        params = (*_source_insert_params(p), source_id)
        cur.execute(
            "UPDATE dbo.ReportingSources SET Code=?, Kind=?, Label=?, Permission=?, "
            "Engine=?, Target=?, Provider=?, BaseObject=?, ColumnsJSON=?, Enabled=?, "
            "SortOrder=?, UpdatedAt=SYSUTCDATETIME() WHERE SourceID=?",
            params,
        )
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting admin sources update error: {e}")
        return jsonify({"error": _("Could not update source")}), 500
    finally:
        conn.close()


@require_permission("reporting.admin.sources")
def api_admin_sources_delete(source_id):
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.ReportingSources WHERE SourceID = ?", (source_id,))
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting admin sources delete error: {e}")
        return jsonify({"error": _("Could not delete source")}), 500
    finally:
        conn.close()


def register_routes(app):
    app.add_url_rule("/reporting", endpoint="reporting", view_func=reporting)
    app.add_url_rule(
        "/reporting/sources",
        endpoint="reporting_sources_admin",
        view_func=reporting_sources_admin,
    )
    app.add_url_rule(
        "/api/reporting/admin/sources",
        endpoint="reporting_admin_sources_list",
        view_func=api_admin_sources_list,
    )
    app.add_url_rule(
        "/api/reporting/admin/sources",
        endpoint="reporting_admin_sources_create",
        view_func=api_admin_sources_create,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/admin/sources/<int:source_id>",
        endpoint="reporting_admin_sources_update",
        view_func=api_admin_sources_update,
        methods=["PUT"],
    )
    app.add_url_rule(
        "/api/reporting/admin/sources/<int:source_id>",
        endpoint="reporting_admin_sources_delete",
        view_func=api_admin_sources_delete,
        methods=["DELETE"],
    )
    app.add_url_rule("/api/reporting/sources", endpoint="reporting_sources", view_func=api_sources)
    app.add_url_rule(
        "/api/reporting/run",
        endpoint="reporting_run",
        view_func=api_run,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/sql/run",
        endpoint="reporting_sql_run",
        view_func=api_sql_run,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/sql/ack",
        endpoint="reporting_sql_ack",
        view_func=api_sql_ack,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/export",
        endpoint="reporting_export",
        view_func=api_export,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/export/grid",
        endpoint="reporting_export_grid",
        view_func=api_export_grid,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/reports",
        endpoint="reporting_reports_list",
        view_func=api_reports_list,
    )
    app.add_url_rule(
        "/api/reporting/reports",
        endpoint="reporting_reports_create",
        view_func=api_reports_create,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>",
        endpoint="reporting_reports_get",
        view_func=api_reports_get,
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>",
        endpoint="reporting_reports_update",
        view_func=api_reports_update,
        methods=["PUT"],
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>",
        endpoint="reporting_reports_delete",
        view_func=api_reports_delete,
        methods=["DELETE"],
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/shares",
        endpoint="reporting_reports_shares_get",
        view_func=api_reports_shares_get,
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/shares",
        endpoint="reporting_reports_shares_set",
        view_func=api_reports_shares_set,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/shares/<int:share_user_id>",
        endpoint="reporting_reports_shares_delete",
        view_func=api_reports_shares_delete,
        methods=["DELETE"],
    )
