"""Self-service Reporting page (curated table sources) — Phase 1.

Routes:
  GET  /reporting                     builder page
  GET  /reporting/guide               in-app user guide (docs/howto/reporting-guide.md rendered)
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
  GET/POST/PUT/DELETE /api/reporting/reports/<id>/schedules[/<sid>]  owner: schedules

Split into a package (beautify-phase-2a, Task 1): the AI cluster
(``/api/reporting/ai/*`` — ask/build/agent/caption) now lives in ``ai.py``.
Every name it defines is re-exported below under its original import path
(``nx_lib.views.reporting.<name>``), so nothing changes for callers, tests,
or ``nx_lib/reporting/runner.py`` (which reads several *other* attributes off
this module at runtime). Later tasks split further; the names still defined
here that ``ai.py`` calls back into (source/metric registry helpers, the
live-SQL sandbox helpers, ``_get_effective_source``) move to a shared module
then.
"""

import json
import re
import time

from flask import (
    current_app,
    jsonify,
    render_template,
    request,
    session,
)
from flask_babel import gettext as _

from ... import mapping_config
from ...db import engine_nexora_db, engine_statistics_db
from ...extensions import cache, limiter
from ...i18n import get_locale
from ...reporting import db_schema
from ...reporting.catalog import fetch_docprocessing_catalog
from ...reporting.schedule import compute_next_run, utcnow, validate_schedule
from ...reporting.semantic import AGGREGATIONS
from ...reporting.sources import accessible, code_sources
from ...reporting.table_query import TableQueryError, build_distinct_query, table_source_catalog
from ...security import has_permission, page_visibility, require_permission
from . import ai, export, pages, run
from ._shared import (
    _CURATED_ENGINES,
    _METRIC_LABEL_ATTRS,
    _METRICS_CACHE_KEY,
    _SCOPE_PREFIX,
    _SOURCES_CACHE_KEY,
    _SQL_TARGET_ENGINES,
    _SQL_TARGET_PERMISSION,
    _SQL_TARGETS,
    _accessible_metrics,
    _allowed_processes,
    _audit_sql,
    _authorize_sql_target,
    _catalog_for_source,
    _client_of,
    _effective_scope,
    _effective_sources,
    _execute,
    _get_effective_source,
    _has_acked,
    _json_safe,
    _load_db_metrics,
    _load_db_sources,
    _load_field_col_maps,
    _load_process_configs,
    _metrics_for_source,
    _prepare_run,
    _resolve_definition_tokens_or_error,
    _run_sql,
    metric_result_columns,
)
from .ai import (
    _ai_asks_today,
    _ai_catalog_text,
    _ai_config,
    _ai_daily_limit,
    _ai_schema_text,
    _audit_ai,
    _caption_columns,
    _extract_agent_artifacts,
    _normalize_definition,
    _validate_definition_for_user,
    api_ai_agent,
    api_ai_ask,
    api_ai_build,
    api_ai_caption,
)
from .pages import _GUIDE_MD, _guide_render
from .run import _forecast_for, _rows_json_safe, _sandbox_error_message

# Names imported above purely for re-export (nx_lib.views.reporting.<name> must
# keep resolving for callers/tests/nx_lib/reporting/runner.py) rather than used
# in this module's own code. The AI cluster (ai.py, Task 1) and the shared
# run/registry core (_shared.py, Task 2) both live behind this re-export list.
__all__ = [
    "_accessible_metrics",
    "_ai_asks_today",
    "_ai_catalog_text",
    "_ai_config",
    "_ai_daily_limit",
    "_ai_schema_text",
    "_allowed_processes",
    "_audit_ai",
    "_audit_sql",
    "_authorize_sql_target",
    "_CURATED_ENGINES",
    "_caption_columns",
    "_catalog_for_source",
    "_client_of",
    "_effective_scope",
    "_effective_sources",
    "_execute",
    "_extract_agent_artifacts",
    "_forecast_for",
    "_get_effective_source",
    "_GUIDE_MD",
    "_guide_render",
    "_has_acked",
    "_json_safe",
    "_load_db_metrics",
    "_load_db_sources",
    "_load_field_col_maps",
    "_load_process_configs",
    "_METRIC_LABEL_ATTRS",
    "_metrics_for_source",
    "_normalize_definition",
    "_prepare_run",
    "_resolve_definition_tokens_or_error",
    "_rows_json_safe",
    "_run_sql",
    "_sandbox_error_message",
    "_SCOPE_PREFIX",
    "_SOURCES_CACHE_KEY",
    "_METRICS_CACHE_KEY",
    "_SQL_TARGET_ENGINES",
    "_SQL_TARGET_PERMISSION",
    "_SQL_TARGETS",
    "_validate_definition_for_user",
    "api_ai_agent",
    "api_ai_ask",
    "api_ai_build",
    "api_ai_caption",
    "metric_result_columns",
    "register_routes",
]


def invalidate_reporting_sources() -> None:
    """Drop the cached sources registry so the next _load_db_sources() re-queries."""
    cache.delete(_SOURCES_CACHE_KEY)


def invalidate_reporting_metrics() -> None:
    """Drop the cached metrics registry so the next _load_db_metrics() re-queries."""
    cache.delete(_METRICS_CACHE_KEY)


def _metric_label(m):
    """Locale-aware metric label with English fallback (mirrors the
    Search_Field_Labels convention: a missing translation falls back to Label).

    Request-context only (reads get_locale()); non-request callers — the AI
    catalogs and the scheduler's _metrics_for_source — keep using m['label'].
    """
    attr = _METRIC_LABEL_ATTRS.get(str(get_locale()))
    return (m.get(attr) if attr else None) or m["label"]


def _accessible_sql_targets():
    """RO SQL targets the caller may use -> RO connection factories (gated like the
    SQL sandbox). serialize_target() owns and closes each connection it yields."""
    out = {}
    for target, engine in _SQL_TARGET_ENGINES.items():
        perm = _SQL_TARGET_PERMISSION.get(target)
        if perm and not has_permission(perm):
            continue
        if engine is None:
            continue
        out[target] = lambda e=engine: e.raw_connection()
    return out


def _accessible_curated_sources():
    """Curated sources the caller can access, shaped for the AI catalog serializer."""
    perms = set(session.get("permissions", []))
    allowed_processes = _allowed_processes()
    # Canonical metrics per source so the model can draft metric definitions
    # (the serializer renders them as a per-source `metrics:` line).
    metrics_by_source = {}
    for m in _load_db_metrics().values():
        metrics_by_source.setdefault(m["source_id"], []).append(
            {
                "code": m["code"],
                "label": m["label"],
                "aggregation": m["aggregation"],
                "base_field": m["base_field"],
                "anchor": m.get("anchor"),
            }
        )
    out = []
    for s in accessible(_effective_sources(), perms):
        if s.get("kind") != "curated":
            continue
        provider = s.get("provider") or "docprocessing"
        if provider == "docprocessing":
            # Fields come from the locale-aware Statconfig catalog, scoped to the
            # caller's allowed processes (mirrors /api/reporting/run + api_sources),
            # so the model grounds on the same fields the validator will check.
            try:
                catalog = fetch_docprocessing_catalog(allowed_processes, str(get_locale()))
            except Exception as e:  # a catalog failure degrades to "no fields", never 500
                current_app.logger.warning(f"reporting.ai catalog: docprocessing unavailable: {e}")
                catalog = []
            processes = allowed_processes
        else:
            catalog = table_source_catalog(s.get("columns"))
            processes = s.get("processes") or []
        out.append(
            {
                "id": s.get("id"),
                "label": s.get("label"),
                "fields": catalog,
                "processes": processes,
                "metrics": metrics_by_source.get(s.get("id"), []),
            }
        )
    return out


def _preview_summary(defn):
    """Shape facts a library card can show next to its thumbnail.

    Ids and counts only -- the labels are resolved client-side against the
    source catalog so they stay translated. Type-guarded for the same reason
    _preview_kind is: a malformed saved definition must not take the listing
    down. The raw definition still never leaves this endpoint.
    """
    if not isinstance(defn, dict):
        return {}
    if defn.get("kind") == "dashboard":
        # Dashboard library card: a compact layout sketch ({t: card type,
        # s: 12-col span} per card) so the client can draw a true miniature of
        # the dashboard instead of a generic placeholder. Type-guarded like
        # everything else here — a malformed card is skipped, not fatal.
        cards = defn.get("cards") if isinstance(defn.get("cards"), list) else []
        mini = []
        for c in cards[:12]:
            if not isinstance(c, dict):
                continue
            t = c.get("type") if isinstance(c.get("type"), str) else "bar"
            try:
                s = int(c.get("span") or 6)
            except (TypeError, ValueError):
                s = 6
            mini.append({"t": t, "s": max(1, min(12, s))})
        return {"cards": mini, "cardCount": len(cards)}
    cols = defn.get("columns") if isinstance(defn.get("columns"), list) else []
    grain = ""
    for c in cols:
        if isinstance(c, dict) and isinstance(c.get("grain"), str):
            grain = c["grain"]
            break
    return {
        "source": defn.get("source") if isinstance(defn.get("source"), str) else "",
        "grain": grain,
        "dimensions": len(cols),
        "metrics": len(defn["metrics"]) if isinstance(defn.get("metrics"), list) else 0,
        "filters": len(defn["filters"]) if isinstance(defn.get("filters"), list) else 0,
    }


def _preview_kind(defn):
    """Derive the library card badge/preview kind from a report definition.

    Mirrors the frontend's previewKindOf (templates/js/_reporting_simple_js.html)
    exactly: no breakdown columns -> 'total'; a grain or a date-ish field name
    on the first column -> 'line'; a pie/donut visualization -> 'donut';
    otherwise -> 'bar'.

    Saved definitions come from a JSON blob a caller wrote through the report
    editor API, which only checks the top level is a dict (see
    api_reports_create). Anything under 'columns' can be malformed (a corrupt
    row, a hand-edited DB value, a future schema change) so every access below
    is type-guarded — malformed shape falls back to a sensible default kind
    instead of raising and taking the whole library listing down with it.
    """
    if not isinstance(defn, dict):
        return "bar"
    cols = defn.get("columns") or []
    if not isinstance(cols, list) or not cols:
        return "total"
    first = cols[0]
    if not isinstance(first, dict):
        return "bar"
    field = first.get("field") or ""
    if not isinstance(field, str):
        field = ""
    if first.get("grain") or re.search(r"date", field, re.I):
        return "line"
    if defn.get("visualization") in ("pie", "donut"):
        return "donut"
    return "bar"


@require_permission("reporting.view")
def api_reports_list():
    """List reports the caller owns, plus any shared with them.

    A report is visible when the caller owns it, its Visibility is 'shared'
    (everyone with reporting.view), or it is explicitly shared with the caller.
    Each row is tagged owned / canEdit and carries the owner's name, the
    owner-only sharedCount (explicit per-user grants), plus a
    server-computed previewKind for the library card badge/thumbnail (derived
    from DefinitionJSON — the raw definition itself is never sent here).
    """
    userid = session.get("userid")
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT r.ReportID, r.Name, r.UpdatedAt, r.Visibility, r.OwnerUserID, "
            "       u.username AS OwnerName, "
            "       JSON_VALUE(r.DefinitionJSON, '$.kind') AS Kind, "
            "       r.DefinitionJSON, "
            "       CASE WHEN r.OwnerUserID = ? THEN 1 ELSE 0 END AS Owned, "
            "       CASE WHEN r.OwnerUserID = ? THEN 1 "
            "            WHEN s.CanEdit = 1 THEN 1 ELSE 0 END AS CanEdit, "
            "       (SELECT COUNT(*) FROM dbo.ReportShares sc "
            "         WHERE sc.ReportID = r.ReportID) AS ShareCount "
            "FROM dbo.Reports r "
            "JOIN dbo.Users u ON u.userID = r.OwnerUserID "
            "LEFT JOIN dbo.ReportShares s "
            "       ON s.ReportID = r.ReportID AND s.SharedWithUserID = ? "
            "WHERE r.OwnerUserID = ? OR r.Visibility = 'shared' OR s.SharedWithUserID = ? "
            "ORDER BY Owned DESC, r.UpdatedAt DESC",
            (userid, userid, userid, userid, userid),
        )
        rows = []
        for r in cur.fetchall():
            try:
                defn = json.loads(r.DefinitionJSON or "{}")
            except (TypeError, ValueError):
                defn = {}
            # Defense-in-depth: _preview_kind type-guards known malformed
            # shapes internally, but one corrupt saved definition must never
            # be able to 500 the whole library for every user, so a row that
            # still fails to serialize for any other reason is skipped and
            # logged rather than propagating up to the route-level except.
            try:
                rows.append(
                    {
                        "id": r.ReportID,
                        "name": r.Name,
                        "updatedAt": str(r.UpdatedAt),
                        "kind": r.Kind or "table",
                        "visibility": r.Visibility,
                        "owned": bool(r.Owned),
                        "canEdit": bool(r.CanEdit),
                        "ownerName": r.OwnerName,
                        # Owner-only: how many colleagues it is shared with,
                        # so the library can tag a report that is shared by
                        # explicit grant while Visibility is still private.
                        "sharedCount": int(r.ShareCount) if r.Owned else 0,
                        "previewKind": _preview_kind(defn),
                        "summary": _preview_summary(defn),
                    }
                )
            except Exception as row_err:
                current_app.logger.warning(
                    f"/api/reporting/reports list: skipping malformed report "
                    f"{r.ReportID}: {row_err}"
                )
        return jsonify(rows)
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


# ---- Scheduled report delivery (reporting.schedule) -----------------------


def _serialize_schedule(r):
    return {
        "id": r.ScheduleID,
        "recipients": r.Recipients,
        "format": r.Format,
        "frequency": r.Frequency,
        "hour": r.Hour,
        "minute": r.Minute,
        "weekday": r.Weekday,
        "dayOfMonth": r.DayOfMonth,
        "enabled": bool(r.Enabled),
        "alertOp": r.AlertOp,
        "alertThreshold": r.AlertThreshold,
        "lastRunAt": str(r.LastRunAt) if r.LastRunAt else None,
        "nextRunAt": str(r.NextRunAt) if r.NextRunAt else None,
    }


def _schedule_fields(p):
    """Normalized (recipients, format, frequency, hour, minute, weekday, dom,
    enabled, next, alert_op, alert_threshold)."""
    freq = p.get("frequency")
    hour = int(p.get("hour"))
    minute = int(p.get("minute", 0))
    weekday = int(p["weekday"]) if freq == "weekly" else None
    dom = int(p["dayOfMonth"]) if freq == "monthly" else None
    enabled = 1 if p.get("enabled", True) else 0
    nxt = compute_next_run(freq, hour, minute, weekday, dom, utcnow())
    alert_op = p.get("alertOp") or None
    alert_threshold = float(p["alertThreshold"]) if alert_op else None
    return (
        p.get("recipients").strip(),
        (p.get("format") or "xlsx").lower(),
        freq,
        hour,
        minute,
        weekday,
        dom,
        enabled,
        nxt,
        alert_op,
        alert_threshold,
    )


@require_permission("reporting.schedule")
def api_reports_schedules_get(report_id):
    userid = session.get("userid")
    if not _is_report_owner(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT ScheduleID, Recipients, Format, Frequency, Hour, Minute, Weekday, "
            "DayOfMonth, Enabled, LastRunAt, NextRunAt, AlertOp, AlertThreshold "
            "FROM dbo.ReportSchedules "
            "WHERE ReportID = ? ORDER BY ScheduleID",
            (report_id,),
        )
        return jsonify([_serialize_schedule(r) for r in cur.fetchall()])
    except Exception as e:
        current_app.logger.error(f"reporting schedules list error: {e}")
        return jsonify({"error": _("Could not list schedules")}), 500
    finally:
        conn.close()


@require_permission("reporting.schedule")
@limiter.limit("60 per minute")
def api_reports_schedules_create(report_id):
    userid = session.get("userid")
    if not _is_report_owner(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    p = request.get_json(silent=True) or {}
    err = validate_schedule(p)
    if err:
        return jsonify({"error": err}), 400
    (recipients, fmt, freq, hour, minute, weekday, dom, enabled, nxt, alert_op, alert_thr) = (
        _schedule_fields(p)
    )
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.ReportSchedules "
            "(ReportID, OwnerUserID, Recipients, Format, Frequency, Hour, Minute, "
            " Weekday, DayOfMonth, Enabled, NextRunAt, AlertOp, AlertThreshold) "
            "OUTPUT INSERTED.ScheduleID VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                report_id,
                userid,
                recipients,
                fmt,
                freq,
                hour,
                minute,
                weekday,
                dom,
                enabled,
                nxt,
                alert_op,
                alert_thr,
            ),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({"id": new_id, "ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting schedules create error: {e}")
        return jsonify({"error": _("Could not save schedule")}), 500
    finally:
        conn.close()


@require_permission("reporting.schedule")
@limiter.limit("60 per minute")
def api_reports_schedules_update(report_id, schedule_id):
    userid = session.get("userid")
    if not _is_report_owner(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    p = request.get_json(silent=True) or {}
    err = validate_schedule(p)
    if err:
        return jsonify({"error": err}), 400
    (recipients, fmt, freq, hour, minute, weekday, dom, enabled, nxt, alert_op, alert_thr) = (
        _schedule_fields(p)
    )
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.ReportSchedules SET Recipients=?, Format=?, Frequency=?, Hour=?, "
            "Minute=?, Weekday=?, DayOfMonth=?, Enabled=?, NextRunAt=?, AlertOp=?, "
            "AlertThreshold=?, UpdatedAt=SYSUTCDATETIME() "
            "WHERE ScheduleID=? AND ReportID=?",
            (
                recipients,
                fmt,
                freq,
                hour,
                minute,
                weekday,
                dom,
                enabled,
                nxt,
                alert_op,
                alert_thr,
                schedule_id,
                report_id,
            ),
        )
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting schedules update error: {e}")
        return jsonify({"error": _("Could not update schedule")}), 500
    finally:
        conn.close()


@require_permission("reporting.schedule")
def api_reports_schedules_delete(report_id, schedule_id):
    userid = session.get("userid")
    if not _is_report_owner(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM dbo.ReportSchedules WHERE ScheduleID = ? AND ReportID = ?",
            (schedule_id, report_id),
        )
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting schedules delete error: {e}")
        return jsonify({"error": _("Could not delete schedule")}), 500
    finally:
        conn.close()


@require_permission("reporting.schedule")
def api_schedules_all():
    """Every schedule the caller owns, across all reports — feeds the
    Console 'Scheduled' screen. Owner-scoped like the per-report routes."""
    userid = session.get("userid")
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT s.ScheduleID, s.ReportID, r.Name AS ReportName, s.Recipients, "
            "s.Format, s.Frequency, s.Hour, s.Minute, s.Weekday, s.DayOfMonth, "
            "s.Enabled, s.LastRunAt, s.NextRunAt, s.AlertOp, s.AlertThreshold "
            "FROM dbo.ReportSchedules s "
            "JOIN dbo.Reports r ON r.ReportID = s.ReportID "
            "WHERE r.OwnerUserID = ? "
            "ORDER BY s.NextRunAt, s.ScheduleID",
            (userid,),
        )
        out = []
        for r in cur.fetchall():
            d = _serialize_schedule(r)
            d["reportId"] = r.ReportID
            d["reportName"] = r.ReportName
            out.append(d)
        return jsonify(out)
    except Exception as e:
        current_app.logger.error(f"reporting schedules overview error: {e}")
        return jsonify({"error": _("Could not list schedules")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
@limiter.limit("30 per minute")
def api_share_targets():
    """Typeahead for the share modal: up to 8 users matching by username,
    full name or email. Returns only username + display name — the share
    POST already accepts the username."""
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])
    like = f"%{q}%"
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 8 username, Fullname FROM dbo.Users "
            "WHERE username LIKE ? OR Fullname LIKE ? OR Email LIKE ? "
            "ORDER BY username",
            (like, like, like),
        )
        return jsonify(
            [{"username": r.username, "name": r.Fullname or r.username} for r in cur.fetchall()]
        )
    except Exception as e:
        current_app.logger.error(f"reporting share targets error: {e}")
        return jsonify([])
    finally:
        conn.close()


# ---- Source health (Console sources rail) ---------------------------------


def _probe_engine(engine):
    """(ok, latency_ms, db_name) for one probe round-trip; DB_NAME() rides
    along because the engines are built from odbc_connect strings whose
    SQLAlchemy URL carries no database attribute."""
    if engine is None:
        return False, None, None
    t0 = time.perf_counter()
    try:
        conn = engine.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT DB_NAME()")
            row = cur.fetchone()
        finally:
            conn.close()
        return True, (time.perf_counter() - t0) * 1000.0, (row[0] if row else None)
    except Exception:
        return False, None, None


@require_permission("reporting.view")
def api_sources_health():
    """Live status dot + latency per accessible source (Console rail).
    One SELECT-1 probe per distinct engine, shared across sources."""
    perms = set(session.get("permissions", []))
    sources = accessible(_effective_sources(), perms)
    probes = {}  # id(engine) -> (ok, ms)

    def probe(engine):
        key = id(engine)
        if key not in probes:
            probes[key] = _probe_engine(engine)
        return probes[key]

    out = []
    for s in sources:
        if s["kind"] == "sql":
            engine = _SQL_TARGET_ENGINES.get(s.get("target", "statistics"))
        else:
            engine = _CURATED_ENGINES.get(s.get("engine"), engine_statistics_db)
        ok, ms, db_name = probe(engine)
        out.append(
            {
                "id": s["id"],
                "ok": ok,
                "latencyMs": round(ms, 1) if ms is not None else None,
                "db": db_name,
            }
        )
    return jsonify({"sources": out})


def _source_used_tables(src):
    """Qualified table names the reporting layer actually reads for `src`.

    Two registries know this: the source's own `BaseObject` (the generic
    `table` provider's target) and `dbo.ProcessSources.TableName` (the
    statistik table per client/process, migration 0074). Names from a
    different database simply won't match anything when the payload is
    filtered, so all of them can be thrown in together.
    """
    names = set()
    if src.get("baseObject"):
        names.add(src["baseObject"])
    reg = mapping_config.registry()
    if reg is not None:
        names |= {ps.table for ps in reg.sources.values() if ps.table}
    return names


@require_permission("reporting.sources.schema")
def api_source_schema(source_id):
    """Tables, columns and foreign keys of the database behind one source.

    Feeds the Console's source visualizer (click a rail card): a filterable
    table list and an ER diagram. Read-only catalog queries on the same engine
    the source itself reads from, so no new credential surface -- but the
    schema of a whole database is more than the source's own fields, hence its
    own grant on top of the source's permission.
    """
    perms = set(session.get("permissions", []))
    src = next(
        (s for s in accessible(_effective_sources(), perms) if s.get("id") == source_id),
        None,
    )
    if src is None:
        return jsonify({"error": _("Not authorized for this source")}), 403
    if src["kind"] == "sql":
        engine = _SQL_TARGET_ENGINES.get(src.get("target", "statistics"))
    else:
        engine = _CURATED_ENGINES.get(src.get("engine"), engine_statistics_db)
    if engine is None:
        return jsonify({"error": _("This source's database is not configured.")}), 503
    try:
        conn = engine.raw_connection()
    except Exception as e:
        current_app.logger.warning(f"reporting schema: connect failed for {source_id}: {e}")
        return jsonify({"error": _("Could not reach this database.")}), 503
    try:
        payload = db_schema.filter_used(db_schema.introspect(conn), _source_used_tables(src))
    except Exception as e:
        current_app.logger.error(f"reporting schema: introspection failed for {source_id}: {e}")
        return jsonify({"error": _("Could not read this database's schema.")}), 502
    finally:
        conn.close()
    payload["source"] = source_id
    payload["label"] = src.get("label")
    return jsonify(payload)


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


# ---- Metrics-registry admin (reporting.semantic.admin) --------------------

_METRIC_CODE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_metric_payload(p):
    """Return an error string for an invalid metric payload, else None."""
    if not isinstance(p, dict):
        return _("Invalid body")
    if not _METRIC_CODE_RE.match((p.get("code") or "").strip()):
        return _("code must start with a letter/underscore: letters, digits, _")
    if not (p.get("sourceId") or "").strip():
        return _("sourceId is required")
    if not (p.get("label") or "").strip():
        return _("label is required")
    agg = (p.get("aggregation") or "").strip()
    if agg not in AGGREGATIONS:
        return _("aggregation must be one of: ") + ", ".join(sorted(AGGREGATIONS))
    if agg != "count" and not (p.get("baseField") or "").strip():
        return _("baseField is required unless aggregation is 'count'")
    return None


def _metric_insert_params(p):
    return (
        p["code"].strip(),
        p["sourceId"].strip(),
        p["label"].strip(),
        (p.get("labelDe") or "").strip() or None,
        (p.get("labelFr") or "").strip() or None,
        (p.get("labelIt") or "").strip() or None,
        p["aggregation"].strip(),
        (p.get("baseField") or "").strip() or None,
        p.get("format") or None,
        1 if p.get("enabled", True) else 0,
        int(p.get("sortOrder") or 100),
    )


@require_permission("reporting.admin.sources")
def reporting_sources_admin():
    return render_template(
        "reporting_sources.html",
        logged_in_user=session.get("username", "Unknown"),
        fullname=session.get("fullname"),
        page_visibility=page_visibility(),
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
        invalidate_reporting_sources()
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
        invalidate_reporting_sources()
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
        invalidate_reporting_sources()
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting admin sources delete error: {e}")
        return jsonify({"error": _("Could not delete source")}), 500
    finally:
        conn.close()


@require_permission("reporting.semantic.admin")
def reporting_metrics_admin():
    return render_template(
        "reporting_metrics.html",
        logged_in_user=session.get("username", "Unknown"),
        fullname=session.get("fullname"),
        page_visibility=page_visibility(),
    )


@require_permission("reporting.semantic.admin")
def api_admin_metrics_list():
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT MetricID, Code, SourceId, Label, GermanLabel, FrenchLabel, "
            "ItalianLabel, Aggregation, BaseField, Description, Format, Enabled, "
            "SortOrder FROM dbo.ReportingMetrics ORDER BY SortOrder, Label"
        )
        rows = [
            {
                "id": r.MetricID,
                "code": r.Code,
                "sourceId": r.SourceId,
                "label": r.Label,
                "labelDe": r.GermanLabel,
                "labelFr": r.FrenchLabel,
                "labelIt": r.ItalianLabel,
                "aggregation": r.Aggregation,
                "baseField": r.BaseField,
                "description": r.Description,
                "format": r.Format,
                "enabled": bool(r.Enabled),
                "sortOrder": r.SortOrder,
            }
            for r in cur.fetchall()
        ]
    except Exception as e:
        current_app.logger.error(f"reporting admin metrics list error: {e}")
        return jsonify({"error": _("Could not list metrics")}), 500
    finally:
        conn.close()
    sources = [{"id": s["id"], "label": s["label"]} for s in _effective_sources()]
    return jsonify({"rows": rows, "sources": sources})


@require_permission("reporting.semantic.admin")
@limiter.limit("60 per minute")
def api_admin_metrics_create():
    p = request.get_json(silent=True) or {}
    err = _validate_metric_payload(p)
    if err:
        return jsonify({"error": err}), 400
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.ReportingMetrics "
            "(Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, "
            "Aggregation, BaseField, Format, Enabled, SortOrder) "
            "OUTPUT INSERTED.MetricID VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _metric_insert_params(p),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        invalidate_reporting_metrics()
        return jsonify({"id": new_id, "ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting admin metrics create error: {e}")
        return jsonify({"error": _("Could not save metric (code already exists?)")}), 500
    finally:
        conn.close()


@require_permission("reporting.semantic.admin")
@limiter.limit("60 per minute")
def api_admin_metrics_update(metric_id):
    p = request.get_json(silent=True) or {}
    err = _validate_metric_payload(p)
    if err:
        return jsonify({"error": err}), 400
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        params = (*_metric_insert_params(p), metric_id)
        cur.execute(
            "UPDATE dbo.ReportingMetrics SET Code=?, SourceId=?, Label=?, GermanLabel=?, "
            "FrenchLabel=?, ItalianLabel=?, Aggregation=?, BaseField=?, Format=?, "
            "Enabled=?, SortOrder=?, UpdatedAt=SYSUTCDATETIME() WHERE MetricID=?",
            params,
        )
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        invalidate_reporting_metrics()
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting admin metrics update error: {e}")
        return jsonify({"error": _("Could not update metric")}), 500
    finally:
        conn.close()


@require_permission("reporting.semantic.admin")
def api_admin_metrics_delete(metric_id):
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.ReportingMetrics WHERE MetricID = ?", (metric_id,))
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        invalidate_reporting_metrics()
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting admin metrics delete error: {e}")
        return jsonify({"error": _("Could not delete metric")}), 500
    finally:
        conn.close()


def _labeled_field_values(rows, allowed=None):
    """(values, labels) from labelWith pair rows [(value, companion), ...]:
    label is "companion.value" (companion lowercased — the app's
    client.process idiom). `allowed` (a set of such labels, from the caller's
    grants) drops every value whose label isn't granted.
    ponytail: a value shared by several companions falls back to its bare
    name — split into per-companion filters if that ever matters."""
    values, labels = [], {}
    for r in rows:
        v = r[0]
        label = f"{str(r[1]).lower()}.{v}" if r[1] is not None else str(v)
        if v not in labels:
            values.append(v)
            labels[v] = label
        elif labels[v] != label:
            labels[v] = str(v)
    if allowed is not None:
        values = [v for v in values if labels.get(v) in allowed]
        labels = {v: labels[v] for v in values}
    return values, labels


@require_permission("reporting.view")
@limiter.limit("30 per minute")
def api_field_values():
    """Distinct values of one whitelisted field of a table source (#178) —
    powers the wizard's process-scope step for sources without a process
    registry. Source-permission-gated; table provider only."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    source = _get_effective_source((body.get("source") or "").strip())
    if (
        source is None
        or source.get("kind") != "curated"
        or (source.get("provider") or "docprocessing") != "table"
    ):
        return jsonify({"error": _("Unknown or unsupported source")}), 400
    if not has_permission(source["permission"]):
        return jsonify({"error": _("Not authorized for this source")}), 403
    engine = _CURATED_ENGINES.get(source.get("engine"))
    if engine is None:
        return jsonify({"error": _("Source engine is not configured")}), 503
    catalog, _fields, _filterable, _sortable = _catalog_for_source(source)
    try:
        field = (body.get("field") or "").strip()
        sql = build_distinct_query(field, source.get("baseObject"), catalog)
        rows = _execute(engine, sql, [])
    except TableQueryError as e:
        return jsonify({"error": _("This request is invalid."), "detail": str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"/api/reporting/field_values exec error: {e}")
        return jsonify({"error": _("Could not load values")}), 500
    if rows and len(rows[0]) > 1:
        meta = next((c for c in catalog if c.get("field") == field), None)
        # grantScoped: the snapshot table carries every Octo process; offer
        # only the ones the caller is granted (= the list the rest of the app
        # shows). UI curation on top of the source-level permission — the run
        # path stays gated by the source grant alone.
        allowed = set(_allowed_processes()) if meta and meta.get("grantScoped") else None
        values, labels = _labeled_field_values(rows, allowed)
        return jsonify({"values": values, "labels": labels})
    return jsonify({"values": [r[0] for r in rows]})


@require_permission("reporting.view")
def api_metrics():
    """Accessible metrics grouped by source id -> [{code,label,aggregation,...}].

    Only metrics bound to a source whose permission the caller holds are returned,
    so the builder offers exactly the metrics each visible source supports.
    """
    # _load_db_metrics() returns {code: {...}} including format; _accessible_metrics()
    # strips format for the AI catalog. Rebuild from _load_db_metrics filtered by the
    # same source gate so we keep the format field for the builder.
    perms = set(session.get("permissions", []))
    allowed_sources = {s["id"] for s in accessible(_effective_sources(), perms)}
    out = {}
    for m in _load_db_metrics().values():
        sid = m["source_id"]
        if sid not in allowed_sources:
            continue
        out.setdefault(sid, []).append(
            {
                "code": m["code"],
                "label": _metric_label(m),
                "aggregation": m["aggregation"],
                "baseField": m["base_field"],
                "format": m["format"],
                "totalMode": m.get("total_mode", "sum"),
                "anchor": m.get("anchor"),
            }
        )
    return jsonify(out)


def register_routes(app):
    pages.register_routes(app)
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
    app.add_url_rule(
        "/reporting/metrics",
        endpoint="reporting_metrics_admin",
        view_func=reporting_metrics_admin,
    )
    app.add_url_rule(
        "/api/reporting/admin/metrics",
        endpoint="reporting_admin_metrics_list",
        view_func=api_admin_metrics_list,
    )
    app.add_url_rule(
        "/api/reporting/admin/metrics",
        endpoint="reporting_admin_metrics_create",
        view_func=api_admin_metrics_create,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/admin/metrics/<int:metric_id>",
        endpoint="reporting_admin_metrics_update",
        view_func=api_admin_metrics_update,
        methods=["PUT"],
    )
    app.add_url_rule(
        "/api/reporting/admin/metrics/<int:metric_id>",
        endpoint="reporting_admin_metrics_delete",
        view_func=api_admin_metrics_delete,
        methods=["DELETE"],
    )
    app.add_url_rule(
        "/api/reporting/metrics",
        endpoint="reporting_metrics",
        view_func=api_metrics,
    )
    app.add_url_rule(
        "/api/reporting/field_values",
        endpoint="reporting_field_values",
        view_func=api_field_values,
        methods=["POST"],
    )
    run.register_routes(app)
    ai.register_routes(app)
    export.register_routes(app)
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
    app.add_url_rule(
        "/api/reporting/schedules",
        endpoint="reporting_schedules_all",
        view_func=api_schedules_all,
    )
    app.add_url_rule(
        "/api/reporting/sources/health",
        endpoint="reporting_sources_health",
        view_func=api_sources_health,
    )
    app.add_url_rule(
        "/api/reporting/sources/<source_id>/schema",
        endpoint="reporting_source_schema",
        view_func=api_source_schema,
    )
    app.add_url_rule(
        "/api/reporting/share_targets",
        endpoint="reporting_share_targets",
        view_func=api_share_targets,
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/schedules",
        endpoint="reporting_reports_schedules_get",
        view_func=api_reports_schedules_get,
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/schedules",
        endpoint="reporting_reports_schedules_create",
        view_func=api_reports_schedules_create,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/schedules/<int:schedule_id>",
        endpoint="reporting_reports_schedules_update",
        view_func=api_reports_schedules_update,
        methods=["PUT"],
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/schedules/<int:schedule_id>",
        endpoint="reporting_reports_schedules_delete",
        view_func=api_reports_schedules_delete,
        methods=["DELETE"],
    )
