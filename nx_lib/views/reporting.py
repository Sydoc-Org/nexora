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
  GET/POST/PUT/DELETE /api/reporting/reports/<id>/schedules[/<sid>]  owner: schedules
"""

import datetime
import decimal
import json
import os
import re
import time
import uuid

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
from ..reporting.ai import AiError, ask_agentic
from ..reporting.ai import _make_agent_step as make_agent_step
from ..reporting.ai import ask as ai_ask
from ..reporting.ai import ask_definition as ai_ask_definition
from ..reporting.ai_schema import serialize_schema, serialize_sources_catalog
from ..reporting.ai_tools import TOOL_SPECS, ToolRegistry
from ..reporting.catalog import fetch_docprocessing_catalog
from ..reporting.export import rows_to_csv, rows_to_xlsx
from ..reporting.query import QueryBuildError, build_table_query
from ..reporting.sandbox import SqlSandboxError, validate_select, wrap_with_cap
from ..reporting.schedule import compute_next_run, utcnow, validate_schedule
from ..reporting.schema import (
    ReportDefinitionError,
    coerce_definition,
    validate_report_definition,
    validate_sql_definition,
)
from ..reporting.semantic import AGGREGATIONS, MetricResolveError, resolve_metrics
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


def _load_db_metrics():
    """Read enabled dbo.ReportingMetrics as {code: {...}} (best-effort).

    A missing table or read error yields an empty dict, so the page degrades to
    "no metrics" rather than 500-ing — mirrors _load_db_sources.
    """
    try:
        conn = engine_nexora_db.raw_connection()
    except Exception as e:
        current_app.logger.warning(f"reporting metrics: registry unavailable: {e}")
        return {}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT Code, SourceId, Label, Aggregation, BaseField, Description, "
            "Format, Enabled, SortOrder FROM dbo.ReportingMetrics WHERE Enabled = 1"
        )
        out = {}
        for r in cur.fetchall():
            out[r.Code] = {
                "code": r.Code,
                "source_id": r.SourceId,
                "label": r.Label,
                "aggregation": r.Aggregation,
                "base_field": r.BaseField,
                "description": r.Description,
                "format": r.Format,
                "sort_order": r.SortOrder,
            }
        return out
    except Exception as e:
        current_app.logger.warning(f"reporting metrics: registry read failed: {e}")
        return {}
    finally:
        conn.close()


def _metrics_for_source(source_id):
    """Enabled metrics bound to `source_id` as {code: {aggregation, base_field}}."""
    return {
        code: {"aggregation": m["aggregation"], "base_field": m["base_field"]}
        for code, m in _load_db_metrics().items()
        if m["source_id"] == source_id
    }


def _accessible_metrics():
    """Flat list of enabled metric dicts the caller may use, filtered to accessible sources.

    Each dict carries {code, label, aggregation, base_field, source_id} — the shape
    serialize_metrics_catalog expects. Only metrics whose source_id belongs to a source
    the caller can access (same permission gate as api_metrics) are included.
    """
    perms = set(session.get("permissions", []))
    allowed_sources = {s["id"] for s in accessible(_effective_sources(), perms)}
    return [
        {
            "code": m["code"],
            "label": m["label"],
            "aggregation": m["aggregation"],
            "base_field": m["base_field"],
            "source_id": m["source_id"],
        }
        for m in _load_db_metrics().values()
        if m["source_id"] in allowed_sources
    ]


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


def _ai_config():
    """Resolve AI provider settings from env. provider 'none' => unconfigured (503)."""
    provider = (os.environ.get("AI_PROVIDER") or "none").lower()
    if provider == "anthropic":
        return {
            "provider": "anthropic",
            "api_key": os.environ.get("ANTHROPIC_API_KEY"),
            "model": os.environ.get("AI_MODEL", "claude-sonnet-4-6"),
            "url": os.environ.get("ANTHROPIC_API_URL"),
        }
    if provider == "azure":
        return {
            "provider": "azure",
            "api_key": os.environ.get("AZURE_OPENAI_KEY"),
            "model": os.environ.get("AZURE_OPENAI_DEPLOYMENT", ""),
            "endpoint": os.environ.get("AZURE_OPENAI_ENDPOINT"),
            "deployment": os.environ.get("AZURE_OPENAI_DEPLOYMENT"),
            "api_version": os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        }
    return {"provider": "none", "api_key": None}


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


def _ai_schema_text():
    """Build the schema grounding text from accessible RO targets + curated catalogs + metrics."""
    targets = _accessible_sql_targets()
    perms = set(session.get("permissions", []))
    curated = []
    for s in accessible(_effective_sources(), perms):
        if s.get("kind") == "curated" and s.get("provider") not in (None, "docprocessing"):
            curated.append(
                {"label": s.get("label"), "fields": table_source_catalog(s.get("columns"))}
            )
    metrics = _accessible_metrics()
    text, truncated = serialize_schema(targets=targets, curated=curated, metrics=metrics or None)
    if truncated:
        current_app.logger.info("reporting.ai schema truncated for user=%s", session.get("userid"))
    return text


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


def _ai_catalog_text():
    """Bounded catalog text for Surface A from the caller's accessible curated sources."""
    text, truncated = serialize_sources_catalog(_accessible_curated_sources())
    if truncated:
        current_app.logger.info("reporting.ai catalog truncated for user=%s", session.get("userid"))
    return text


def _validate_definition_for_user(definition):
    """Validate a model-drafted definition against its source catalog (Surface-A gate).

    Returns (ok, error_message). Reuses the exact validator + source resolution
    that /api/reporting/run uses, so an accepted definition is guaranteed runnable.
    """
    if not isinstance(definition, dict):
        return False, "definition must be an object"
    try:
        source = _get_effective_source(definition.get("source"))
        if source is None or source.get("kind") != "curated":
            return False, "unknown or unsupported source"
        if not has_permission(source["permission"]):
            return False, "not authorized for this source"
        provider = source.get("provider") or "docprocessing"
        if provider == "docprocessing":
            allowed = _allowed_processes()
            catalog = fetch_docprocessing_catalog(allowed, str(get_locale()))
        else:
            catalog = table_source_catalog(source.get("columns"))
        catalog_fields = {f["field"] for f in catalog}
        filterable = {f["field"] for f in catalog if f["filterable"]}
        sortable = {f["field"] for f in catalog if f["sortable"]}
        # Mirror _prepare_run's validator args exactly: without metric_codes and
        # grainable_fields an AI draft using canonical metrics or a date grain
        # would bounce here despite being runnable.
        grainable = {f["field"] for f in catalog if f.get("grainable")}
        source_metrics = _metrics_for_source(source["id"])
        # Repair common small-model near-misses in place (labels-for-keys, missing
        # schemaVersion/title) so an otherwise-correct AI draft is accepted, not
        # bounced. Whitelist-safe: only resolves labels that map to a real field.
        # Mutating `definition` here propagates to what the caller returns/applies
        # (Surface A's result.definition; the agent's build_definition trace args).
        coerce_definition(
            definition,
            catalog,
            default_title=source.get("label"),
            default_row_limit=DEFAULT_ROW_LIMIT,
            max_row_limit=MAX_ROW_LIMIT,
        )
        to_validate = {k: v for k, v in definition.items() if k != "chartHint"}
        validate_report_definition(
            to_validate,
            catalog_fields,
            filterable,
            sortable,
            max_row_limit=MAX_ROW_LIMIT,
            metric_codes=set(source_metrics),
            grainable_fields=grainable,
        )
        return True, None
    except (ReportDefinitionError, PermissionError) as e:
        return False, str(e) or e.__class__.__name__
    except Exception as e:  # resolution failure degrades to "invalid", not 500
        current_app.logger.warning(f"reporting.ai build validation error: {e}")
        return False, "could not validate the drafted report"


def _normalize_definition(definition):
    """Fill the full builder shape so the frontend applyDefinition() consumes it as-is."""
    definition.setdefault("groupBy", [])
    definition.setdefault("subtitle", None)
    definition.setdefault("filters", [])
    definition.setdefault("sort", [])
    definition.setdefault("scope", {"clients": [], "processes": []})
    definition["sql"] = None
    definition["sqlTarget"] = None
    return definition


def _audit_ai(
    userid,
    username,
    prompt,
    surface,
    generated_sql,
    provider,
    model,
    tokens_in,
    tokens_out,
    gate_verdict,
    status,
    duration_ms,
):
    try:
        conn = engine_nexora_db.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO ReportingAiAudit (UserID, Username, Prompt, Surface, "
                "GeneratedSql, Provider, Model, TokensIn, TokensOut, GateVerdict, "
                "Status, DurationMs) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    userid,
                    username,
                    prompt,
                    surface,
                    generated_sql,
                    provider,
                    model,
                    tokens_in,
                    tokens_out,
                    gate_verdict,
                    status,
                    duration_ms,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        current_app.logger.error(f"reporting ai audit insert failed: {e}")
    current_app.logger.info(
        f"reporting.ai surface={surface} user={userid} provider={provider} "
        f"verdict={gate_verdict} status={status} ms={duration_ms}"
    )


def _ai_daily_limit():
    """Per-user/day cap on AI asks. 0 (or unset/invalid) = unlimited (disabled)."""
    try:
        return max(0, int(os.environ.get("AI_DAILY_LIMIT", "0")))
    except (TypeError, ValueError):
        return 0


def _ai_asks_today(userid):
    """Count this user's AI provider calls (ok|error) since UTC midnight.

    Only rows that represent an actual provider call count toward the cap;
    'blocked' throttle rows are excluded so a hit cap never compounds itself.
    """
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM ReportingAiAudit "
            "WHERE UserID = ? AND Status IN ('ok', 'error') "
            "AND CreatedAt >= CAST(SYSUTCDATETIME() AS date)",
            (userid,),
        )
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        conn.close()


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
        # SELECT * so a pre-0020 Statconfig (no WorkitemColumn yet) still
        # serves the date columns; WorkitemColumn is read defensively.
        cur.execute(
            f"SELECT * FROM Statconfig WHERE ProcessName IN ({ph})",
            target_processes,
        )
        return [
            {
                "process": r.ProcessName,
                "table": r.TableName,
                "export_col": r.ExportColumn,
                "import_col": r.ImportColumn,
                "condition": r.additionalCondition or "",
                "workitem_col": getattr(r, "WorkitemColumn", None),
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


def _client_of(process):
    """Client prefix of a '<client>.<process>' scope string (text before the
    first dot). Mirrors process_helpers' `<client>.<process>` convention."""
    i = process.find(".")
    return process[:i] if i >= 0 else process


def _effective_scope(rd, allowed):
    """Caller's allowed processes narrowed to the requested clients/processes.

    `scope.clients` and `scope.processes` compose by UNION: an allowed process
    is in scope when its client is listed in `scope.clients` OR it is named in
    `scope.processes`. Empty clients AND empty processes means "all allowed"
    (the default). Anything requested that the caller isn't granted is silently
    dropped — the `reporting.scope.process.*` grant is the security boundary.
    """
    scope = rd.get("scope") or {}
    requested_procs = set(scope.get("processes") or [])
    requested_clients = set(scope.get("clients") or [])
    if not requested_procs and not requested_clients:
        return list(allowed)
    return [p for p in allowed if p in requested_procs or _client_of(p) in requested_clients]


def _catalog_for_source(source):
    """Build the field catalog + field sets for a curated source.

    Returns (catalog, catalog_fields, filterable, sortable). Dispatches on the
    source's provider so callers (the run builder and the metrics-admin form)
    share one definition of "what columns this source exposes".
    """
    provider = source.get("provider") or "docprocessing"
    if provider == "docprocessing":
        allowed = _allowed_processes()
        catalog = fetch_docprocessing_catalog(allowed, str(get_locale()))
    elif provider == "table":
        catalog = table_source_catalog(source.get("columns"))
    else:
        raise ReportDefinitionError("unsupported source provider")
    catalog_fields = {f["field"] for f in catalog}
    filterable = {f["field"] for f in catalog if f["filterable"]}
    sortable = {f["field"] for f in catalog if f["sortable"]}
    return catalog, catalog_fields, filterable, sortable


def _prepare_run(rd):
    """Validate + build a query for a curated report.

    Returns (columns, sql, params, engine). Dispatches on the source's provider:
    'docprocessing' (the Statconfig builder over Statistics) or 'table' (the
    generic single-object builder over the source's configured engine). When the
    definition carries `metrics`, the metric codes are validated against the
    source's metric registry and resolved into aggregation specs; the returned
    columns are then the dims + metric codes.

    Raises ReportDefinitionError / QueryBuildError / TableQueryError /
    MetricResolveError on bad input.
    """
    source = _get_effective_source(rd.get("source"))
    if source is None or source.get("kind") != "curated":
        raise ReportDefinitionError("unknown or unsupported source")
    if not has_permission(source["permission"]):
        raise PermissionError(source["permission"])

    provider = source.get("provider") or "docprocessing"
    if provider == "docprocessing":
        catalog, catalog_fields, filterable, sortable = _catalog_for_source(source)
        grainable = {f["field"] for f in catalog if f.get("grainable")}
        source_metrics = _metrics_for_source(source["id"])
        validate_report_definition(
            rd,
            catalog_fields,
            filterable,
            sortable,
            max_row_limit=MAX_ROW_LIMIT,
            metric_codes=set(source_metrics),
            grainable_fields=grainable,
        )
        resolved = (
            resolve_metrics(rd.get("metrics"), source_metrics, catalog_fields)
            if rd.get("metrics")
            else None
        )
        allowed = _allowed_processes()
        scope = _effective_scope(rd, allowed)
        configs = _load_process_configs(scope)
        col_maps = _load_field_col_maps(scope)
        sql, params = build_table_query(
            rd,
            configs,
            col_maps,
            row_cap=rd.get("rowLimit", DEFAULT_ROW_LIMIT),
            resolved_metrics=resolved,
        )
        rd_columns = rd.get("columns") or []
        out_columns = (
            rd_columns + [{"field": m["code"]} for m in resolved] if resolved else rd_columns
        )
        return out_columns, sql, params, engine_statistics_db

    if provider == "table":
        catalog, catalog_fields, filterable, sortable = _catalog_for_source(source)
        source_metrics = _metrics_for_source(source["id"])
        validate_report_definition(
            rd,
            catalog_fields,
            filterable,
            sortable,
            max_row_limit=MAX_ROW_LIMIT,
            metric_codes=set(source_metrics),
        )
        resolved = (
            resolve_metrics(rd.get("metrics"), source_metrics, catalog_fields)
            if rd.get("metrics")
            else None
        )
        sql, params = build_generic_query(
            rd,
            source.get("baseObject"),
            catalog,
            row_cap=rd.get("rowLimit", DEFAULT_ROW_LIMIT),
            resolved_metrics=resolved,
        )
        engine = _CURATED_ENGINES.get(source.get("engine"))
        if engine is None:
            raise ReportDefinitionError("source engine is not configured")
        rd_columns = rd.get("columns") or []
        out_columns = (
            rd_columns + [{"field": m["code"]} for m in resolved] if resolved else rd_columns
        )
        return out_columns, sql, params, engine

    raise ReportDefinitionError("unsupported source provider")


def _execute(engine, sql, params):
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return [list(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _json_safe(value):
    """Coerce one DB result cell to a JSON-serializable value.

    Flask's default JSON encoder handles None/bool/int/float/str and
    date/datetime/Decimal/UUID, but NOT bytes/bytearray/memoryview (varbinary,
    rowversion/timestamp, image) or datetime.time (TIME) — those raise
    "Object of type X is not JSON serializable" and 500 the run. Map the crashy
    types to readable strings, pass the Flask-native ones through unchanged, and
    stringify anything else as a last resort (a result cell must never 500).
    """
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, bytes | bytearray | memoryview):
        return "0x" + bytes(value).hex()
    if isinstance(value, datetime.time):
        return value.isoformat()
    if isinstance(value, datetime.date | decimal.Decimal | uuid.UUID):
        return value  # Flask's DefaultJSONProvider serializes these
    return str(value)


def _rows_json_safe(rows):
    """Apply _json_safe to every cell of every row (JSON response boundary)."""
    return [[_json_safe(v) for v in row] for row in rows]


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
        ai_enabled=has_permission("reporting.ai.use"),
        ai_sql_enabled=has_permission("reporting.ai.sql"),
        ai_explain_enabled=has_permission("reporting.ai.explain_data")
        and has_permission("reporting.sql.run"),
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
    except (ReportDefinitionError, QueryBuildError, TableQueryError, MetricResolveError) as e:
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
            "rows": _rows_json_safe(rows),
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
            "rows": _rows_json_safe(rows),
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


@require_permission("reporting.ai.use")
@limiter.limit("10 per minute")
def api_ai_ask():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify({"error": _("A question is required")}), 400
    # Phase 1 produces Surface B (runnable T-SQL); that requires reporting.ai.sql.
    if not has_permission("reporting.ai.sql"):
        return jsonify({"error": _("Not authorized to receive AI-drafted SQL")}), 403

    cfg = _ai_config()
    if cfg.get("provider") == "none" or not cfg.get("api_key"):
        return jsonify({"error": _("The AI assistant is not configured")}), 503

    userid, username = session.get("userid"), session.get("username")
    # Cost/abuse control: a per-user/day cap, enforced BEFORE any provider call
    # (so a throttled ask costs no tokens). 0 disables it. The block is audited.
    limit = _ai_daily_limit()
    if limit > 0 and _ai_asks_today(userid) >= limit:
        current_app.logger.info(
            f"reporting.ai.ask blocked: user={userid} reached daily limit {limit}"
        )
        _audit_ai(
            userid,
            username,
            question,
            "sql",
            None,
            cfg.get("provider"),
            cfg.get("model"),
            None,
            None,
            "na",
            "blocked",
            0,
        )
        return (
            jsonify(
                {
                    "error": _(
                        "You have reached the daily AI request limit (%(limit)s). "
                        "Please try again tomorrow.",
                        limit=limit,
                    )
                }
            ),
            429,
        )
    schema_text = _ai_schema_text()
    start = time.monotonic()
    try:
        result = ai_ask(
            question,
            schema_text,
            provider=cfg["provider"],
            model=cfg.get("model"),
            api_key=cfg["api_key"],
            endpoint=cfg.get("endpoint"),
            deployment=cfg.get("deployment"),
            api_version=cfg.get("api_version", "2024-10-21"),
            url=cfg.get("url"),
        )
    except AiError as e:
        current_app.logger.warning(f"/api/reporting/ai/ask config error: {e}")
        # Misconfig leaves a trace too, but as 'misconfig' (not 'error') so a broken
        # provider never burns the user's daily quota (_ai_asks_today counts ok|error).
        _audit_ai(
            userid,
            username,
            question,
            "sql",
            None,
            cfg.get("provider"),
            cfg.get("model"),
            None,
            None,
            "na",
            "misconfig",
            int((time.monotonic() - start) * 1000),
        )
        return jsonify({"error": _("The AI assistant is not configured")}), 503
    except Exception as e:
        current_app.logger.error(f"/api/reporting/ai/ask provider error: {e}")
        _audit_ai(
            userid,
            username,
            question,
            "sql",
            None,
            cfg.get("provider"),
            cfg.get("model"),
            None,
            None,
            "na",
            "error",
            int((time.monotonic() - start) * 1000),
        )
        return jsonify({"error": _("The AI assistant could not answer right now")}), 502

    duration_ms = int((time.monotonic() - start) * 1000)
    _audit_ai(
        userid,
        username,
        question,
        "sql",
        result.sql,
        result.provider,
        result.model,
        result.tokens_in,
        result.tokens_out,
        result.gate_verdict,
        "ok",
        duration_ms,
    )
    return jsonify(
        {
            "sql": result.sql,
            "explanation": result.explanation,
            "valid": result.valid,
            "target": "statistics",  # default editor target; user can switch
            "model": result.model,
        }
    )


@require_permission("reporting.ai.use")
@limiter.limit("10 per minute")
def api_ai_build():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify({"error": _("A question is required")}), 400

    cfg = _ai_config()
    if cfg.get("provider") == "none" or not cfg.get("api_key"):
        return jsonify({"error": _("The AI assistant is not configured")}), 503

    userid, username = session.get("userid"), session.get("username")
    limit = _ai_daily_limit()
    if limit > 0 and _ai_asks_today(userid) >= limit:
        _audit_ai(
            userid,
            username,
            question,
            "definition",
            None,
            cfg.get("provider"),
            cfg.get("model"),
            None,
            None,
            "na",
            "blocked",
            0,
        )
        return jsonify(
            {
                "error": _(
                    "You have reached the daily AI request limit (%(limit)s). "
                    "Please try again tomorrow.",
                    limit=limit,
                )
            }
        ), 429

    catalog_text = _ai_catalog_text()
    start = time.monotonic()
    prior_error = None
    result = None
    valid = False
    for _attempt in range(2):  # initial draft + one bounded self-repair retry
        try:
            result = ai_ask_definition(
                question,
                catalog_text,
                provider=cfg["provider"],
                model=cfg.get("model"),
                api_key=cfg["api_key"],
                endpoint=cfg.get("endpoint"),
                deployment=cfg.get("deployment"),
                api_version=cfg.get("api_version", "2024-10-21"),
                url=cfg.get("url"),
                prior_error=prior_error,
            )
        except AiError as e:
            current_app.logger.warning(f"/api/reporting/ai/build config error: {e}")
            # 'misconfig' (not 'error') so a broken provider never counts against the
            # user's daily cap (_ai_asks_today counts only ok|error).
            _audit_ai(
                userid,
                username,
                question,
                "definition",
                None,
                cfg.get("provider"),
                cfg.get("model"),
                None,
                None,
                "na",
                "misconfig",
                int((time.monotonic() - start) * 1000),
            )
            return jsonify({"error": _("The AI assistant is not configured")}), 503
        except Exception as e:
            current_app.logger.error(f"/api/reporting/ai/build provider error: {e}")
            _audit_ai(
                userid,
                username,
                question,
                "definition",
                None,
                cfg.get("provider"),
                cfg.get("model"),
                None,
                None,
                "na",
                "error",
                int((time.monotonic() - start) * 1000),
            )
            return jsonify({"error": _("The AI assistant could not answer right now")}), 502
        valid, prior_error = _validate_definition_for_user(result.definition)
        if valid:
            break

    duration_ms = int((time.monotonic() - start) * 1000)
    definition = _normalize_definition(result.definition) if result.definition else None
    _audit_ai(
        userid,
        username,
        question,
        "definition",
        json.dumps(definition) if definition else None,
        result.provider,
        result.model,
        result.tokens_in,
        result.tokens_out,
        "valid" if valid else "invalid",
        "ok",
        duration_ms,
    )
    return jsonify(
        {
            "definition": definition,
            "explanation": result.explanation,
            "valid": valid,
            "error": None if valid else (prior_error or _("Could not build a valid report")),
        }
    )


_AGENT_SYSTEM = (
    "You are a careful analyst for an internal reporting tool. Use the provided "
    "TOOLS to answer the question, grounded ONLY in the data SOURCES/SCHEMA given "
    "— never invent fields, tables, or sources. Prefer build_definition for any "
    "report the builder can express (it validates against the source field "
    "catalog). If validate_sql is available, draft ONE read-only SELECT and "
    "validate it before presenting. When a tool returns an error, fix your input "
    "and try again. Stop once you have a validated artifact and give a one- or "
    "two-sentence plain-language answer. Do not ask the user questions."
)

# Appended to the system prompt only when the caller holds reporting.ai.explain_data
# (Phase 3e). It unlocks the data-returning tools: run_sql feeds real result rows
# back to the model and compute_stats gives exact aggregates over them, so the model
# may narrate concrete numbers instead of only drafting an artifact.
_AGENT_EXPLAIN_SUFFIX = (
    " You may run validated read-only SELECTs with run_sql and summarise the actual "
    "rows returned, and use compute_stats for exact aggregates (describe, group_by, "
    "percentiles, value_counts, correlation, top_n) over rows you fetched. Always "
    "validate_sql before run_sql. Report only concrete numbers taken from the data "
    "you fetched — never estimate or fabricate values."
    " run_sql can ONLY query the SQL-schema targets named below (e.g. statistics, "
    "octopus). NEVER pass a report SOURCE id as a table name, and NEVER call run_sql "
    "for a source marked 'builder-only' — answer those with build_definition instead. "
    "If a builder-only source needs a calculation build_definition cannot express, say "
    "so plainly rather than retrying run_sql."
)


def _extract_agent_artifacts(tool_trace):
    """Pull the last validated definition / SQL out of the loop's tool trace.

    A build_definition call that returned ok=True carries a runnable definition in
    its args; a validate_sql ok=True carries gate-approved SQL. These let the UI
    offer one-click 'Open in builder' / 'Insert SQL' just like Surfaces A/B.
    """
    definition, sql = None, None
    for step in tool_trace:
        if not (step.get("result") or {}).get("ok"):
            continue
        if step.get("name") == "build_definition":
            d = (step.get("args") or {}).get("definition")
            if isinstance(d, dict):
                definition = _normalize_definition(dict(d))
        elif step.get("name") == "validate_sql":
            sql = (step.get("args") or {}).get("sql")
    return definition, sql


@require_permission("reporting.ai.use")
@limiter.limit("10 per minute")
def api_ai_agent():
    """Surface C — the Tier-2 agentic loop (Phase 3d).

    A self-repairing drafter: the model uses data-free tools (build_definition,
    and validate_sql when the caller holds reporting.ai.sql) to produce a
    validated artifact, grounded in the source catalog / SQL schema passed in the
    prompt. Egress stays schema-only — run_sql / compute_stats (whose results
    would flow back to the model) are Phase 3e, behind reporting.ai.explain_data.
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify({"error": _("A question is required")}), 400

    cfg = _ai_config()
    if cfg.get("provider") == "none" or not cfg.get("api_key"):
        return jsonify({"error": _("The AI assistant is not configured")}), 503

    userid, username = session.get("userid"), session.get("username")
    limit = _ai_daily_limit()
    if limit > 0 and _ai_asks_today(userid) >= limit:
        _audit_ai(
            userid,
            username,
            question,
            "agent",
            None,
            cfg.get("provider"),
            cfg.get("model"),
            None,
            None,
            "na",
            "blocked",
            0,
        )
        return jsonify(
            {
                "error": _(
                    "You have reached the daily AI request limit (%(limit)s). "
                    "Please try again tomorrow.",
                    limit=limit,
                )
            }
        ), 429

    # Tool binding follows the caller's permissions. build_definition is always
    # data-free. validate_sql (also data-free — a gate check) needs reporting.ai.sql.
    # run_sql / compute_stats feed real result rows/stats back to the model, so they
    # are bound ONLY with reporting.ai.explain_data (Phase 3e data-egress grant) AND
    # reporting.sql.run (the live-SQL gate). Without explain_data the loop stays
    # schema-only: no result rows ever reach the model.
    # The client sends the active builder source so the data tools can be gated on
    # whether run_sql can actually reach it. A curated table-provider source (e.g.
    # Generali on GeneraliDB) has no RO SQL target, so binding run_sql for it only
    # makes the model loop on "invalid object name" — bind build_definition instead.
    active_source = None
    source_id = (body.get("source") or "").strip()
    if source_id:
        active_source = _get_effective_source(source_id)
    source_blocks_run_sql = bool(
        active_source
        and active_source.get("kind") == "curated"
        and (active_source.get("provider") or "docprocessing") != "docprocessing"
    )

    has_sql = has_permission("reporting.ai.sql")
    explain = (
        has_permission("reporting.ai.explain_data")
        and has_permission("reporting.sql.run")
        and not source_blocks_run_sql
    )
    tool_names = {"build_definition"}
    if has_sql:
        tool_names.add("validate_sql")
    if explain:
        tool_names.update({"run_sql", "compute_stats"})
    tools = [t for t in TOOL_SPECS if t["name"] in tool_names]

    run_sql_bound = None
    if explain:

        def run_sql_bound(target, sql):
            return _run_sql(target, sql, userid=userid, username=username)

    registry = ToolRegistry(
        run_sql=run_sql_bound, validate_definition=_validate_definition_for_user
    )

    grounding = f"Available report sources and fields:\n{_ai_catalog_text()}"
    if has_sql or explain:
        grounding += f"\n\nSQL schema (for validate_sql / run_sql):\n{_ai_schema_text()}"
    if active_source:
        grounding += (
            f'\n\nThe user\'s selected source is "{active_source.get("label")}" '
            f'(id {active_source.get("id")}); "this source" in the question means it.'
        )
        if source_blocks_run_sql:
            grounding += (
                " It is builder-only — answer it with build_definition; run_sql cannot " "reach it."
            )
    initial = f"{grounding}\n\nQuestion: {question}"
    system_prompt = _AGENT_SYSTEM + (_AGENT_EXPLAIN_SUFFIX if explain else "")

    start = time.monotonic()
    try:
        step = make_agent_step(
            system=system_prompt,
            tools=tools,
            provider=cfg["provider"],
            model=cfg.get("model"),
            api_key=cfg["api_key"],
            endpoint=cfg.get("endpoint"),
            deployment=cfg.get("deployment"),
            api_version=cfg.get("api_version", "2024-10-21"),
            url=cfg.get("url"),
        )
        result = ask_agentic(initial, registry=registry, agent_step=step)
    except AiError as e:
        current_app.logger.warning(f"/api/reporting/ai/agent config error: {e}")
        _audit_ai(
            userid,
            username,
            question,
            "agent",
            None,
            cfg.get("provider"),
            cfg.get("model"),
            None,
            None,
            "na",
            "misconfig",
            int((time.monotonic() - start) * 1000),
        )
        return jsonify({"error": _("The AI assistant is not configured")}), 503
    except Exception as e:
        current_app.logger.error(f"/api/reporting/ai/agent provider error: {e}")
        _audit_ai(
            userid,
            username,
            question,
            "agent",
            None,
            cfg.get("provider"),
            cfg.get("model"),
            None,
            None,
            "na",
            "error",
            int((time.monotonic() - start) * 1000),
        )
        return jsonify({"error": _("The AI assistant could not answer right now")}), 502

    duration_ms = int((time.monotonic() - start) * 1000)
    definition, sql = _extract_agent_artifacts(result.tool_trace)
    _audit_ai(
        userid,
        username,
        question,
        "agent",
        json.dumps(
            {
                "answer": result.answer,
                "tools": [t["name"] for t in result.tool_trace],
                "explainData": explain,
            }
        )[:4000],
        cfg.get("provider"),
        cfg.get("model"),
        result.tokens_in,
        result.tokens_out,
        result.stopped_reason,
        "ok",
        duration_ms,
    )
    return jsonify(
        {
            "answer": result.answer,
            "definition": definition,
            "sql": sql,
            "toolTrace": result.tool_trace,
            "turns": result.turns,
            "stoppedReason": result.stopped_reason,
            "explainData": explain,
        }
    )


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
    except (ReportDefinitionError, QueryBuildError, TableQueryError, MetricResolveError) as e:
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
        "lastRunAt": str(r.LastRunAt) if r.LastRunAt else None,
        "nextRunAt": str(r.NextRunAt) if r.NextRunAt else None,
    }


def _schedule_fields(p):
    """Normalized (recipients, format, frequency, hour, minute, weekday, dom, enabled, next)."""
    freq = p.get("frequency")
    hour = int(p.get("hour"))
    minute = int(p.get("minute", 0))
    weekday = int(p["weekday"]) if freq == "weekly" else None
    dom = int(p["dayOfMonth"]) if freq == "monthly" else None
    enabled = 1 if p.get("enabled", True) else 0
    nxt = compute_next_run(freq, hour, minute, weekday, dom, utcnow())
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
            "DayOfMonth, Enabled, LastRunAt, NextRunAt FROM dbo.ReportSchedules "
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
    recipients, fmt, freq, hour, minute, weekday, dom, enabled, nxt = _schedule_fields(p)
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.ReportSchedules "
            "(ReportID, OwnerUserID, Recipients, Format, Frequency, Hour, Minute, "
            " Weekday, DayOfMonth, Enabled, NextRunAt) "
            "OUTPUT INSERTED.ScheduleID VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (report_id, userid, recipients, fmt, freq, hour, minute, weekday, dom, enabled, nxt),
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
    recipients, fmt, freq, hour, minute, weekday, dom, enabled, nxt = _schedule_fields(p)
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.ReportSchedules SET Recipients=?, Format=?, Frequency=?, Hour=?, "
            "Minute=?, Weekday=?, DayOfMonth=?, Enabled=?, NextRunAt=?, UpdatedAt=SYSUTCDATETIME() "
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


@require_permission("reporting.semantic.admin")
def reporting_metrics_admin():
    return render_template(
        "reporting_metrics.html",
        logged_in_user=session.get("username", "Unknown"),
        fullname=session.get("fullname"),
        pageV=page_visibility(),
    )


@require_permission("reporting.semantic.admin")
def api_admin_metrics_list():
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT MetricID, Code, SourceId, Label, Aggregation, BaseField, "
            "Description, Format, Enabled, SortOrder FROM dbo.ReportingMetrics "
            "ORDER BY SortOrder, Label"
        )
        rows = [
            {
                "id": r.MetricID,
                "code": r.Code,
                "sourceId": r.SourceId,
                "label": r.Label,
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
            "(Code, SourceId, Label, Aggregation, BaseField, Format, Enabled, SortOrder) "
            "OUTPUT INSERTED.MetricID VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            _metric_insert_params(p),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
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
            "UPDATE dbo.ReportingMetrics SET Code=?, SourceId=?, Label=?, Aggregation=?, "
            "BaseField=?, Format=?, Enabled=?, SortOrder=?, UpdatedAt=SYSUTCDATETIME() "
            "WHERE MetricID=?",
            params,
        )
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
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
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting admin metrics delete error: {e}")
        return jsonify({"error": _("Could not delete metric")}), 500
    finally:
        conn.close()


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
                "label": m["label"],
                "aggregation": m["aggregation"],
                "baseField": m["base_field"],
                "format": m["format"],
            }
        )
    return jsonify(out)


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
        "/api/reporting/ai/ask",
        endpoint="reporting_ai_ask",
        view_func=api_ai_ask,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/ai/build",
        endpoint="reporting_ai_build",
        view_func=api_ai_build,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/ai/agent",
        endpoint="reporting_ai_agent",
        view_func=api_ai_agent,
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
