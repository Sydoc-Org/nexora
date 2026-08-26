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
"""

import base64
import datetime
import decimal
import json
import os
import re
import time
import uuid
from pathlib import Path

from flask import (
    Response,
    current_app,
    jsonify,
    render_template,
    request,
    session,
    stream_with_context,
)
from flask_babel import gettext as _
from markdown_it import MarkdownIt

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
from ..reporting.ai import (
    _AGENT_EXPLAIN_SUFFIX,
    _AGENT_SYSTEM,
    CAPTION_MAX_ROWS,
    CONTINUE_BUDGET_S,
    CONTINUE_MAX_TURNS,
    MAX_CONTINUE_ATTEMPTS,
    AiError,
    ask_agentic,
    ask_agentic_iter,
)
from ..reporting.ai import _make_agent_step as make_agent_step
from ..reporting.ai import ask as ai_ask
from ..reporting.ai import ask_definition as ai_ask_definition
from ..reporting.ai import caption as ai_caption
from ..reporting.ai_schema import serialize_schema, serialize_sources_catalog
from ..reporting.ai_tools import RUN_DEFINITION_ROW_CAP, TOOL_SPECS, ToolRegistry
from ..reporting.catalog import fetch_docprocessing_catalog
from ..reporting.export import rows_to_csv, rows_to_xlsx
from ..reporting.forecast import compute_forecast, forecast_export_rows
from ..reporting.query import QueryBuildError, build_table_query
from ..reporting.runner import execute_definition
from ..reporting.sandbox import (
    MAX_SQL_LEN,
    SqlSandboxError,
    fetch_capped,
    humanize_sql_error,
    validate_select,
    wrap_with_cap,
)
from ..reporting.schedule import compute_next_run, utcnow, validate_schedule
from ..reporting.schema import (
    ReportDefinitionError,
    coerce_definition,
    validate_report_definition,
    validate_sql_definition,
)
from ..reporting.semantic import (
    AGGREGATIONS,
    MetricResolveError,
    drop_columns_shadowing_distinct_metrics,
    resolve_metrics,
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
from ..reporting.sqlformat import format_sql, inline_sql_params
from ..reporting.table_query import (
    TableQueryError,
    build_distinct_query,
    build_generic_query,
    table_source_catalog,
)
from ..reporting.tokens import (
    date_fields_from_catalog,
    resolve_definition_tokens,
    resolve_token,
    shifted_definition_for_comparison,
    widened_definition_for_forecast,
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
            "SELECT Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, "
            "Aggregation, BaseField, Description, Format, Enabled, SortOrder, TotalMode, "
            "DateAnchor "
            "FROM dbo.ReportingMetrics WHERE Enabled = 1"
        )
        out = {}
        for r in cur.fetchall():
            out[r.Code] = {
                "code": r.Code,
                "source_id": r.SourceId,
                "label": r.Label,
                "label_de": r.GermanLabel,
                "label_fr": r.FrenchLabel,
                "label_it": r.ItalianLabel,
                "aggregation": r.Aggregation,
                "base_field": r.BaseField,
                "description": r.Description,
                "format": r.Format,
                "sort_order": r.SortOrder,
                "total_mode": (getattr(r, "TotalMode", None) or "sum"),
                "anchor": getattr(r, "DateAnchor", None),
            }
        return out
    except Exception as e:
        current_app.logger.warning(f"reporting metrics: registry read failed: {e}")
        return {}
    finally:
        conn.close()


_METRIC_LABEL_ATTRS = {"de": "label_de", "fr": "label_fr", "it": "label_it"}


def _metric_label(m):
    """Locale-aware metric label with English fallback (mirrors the
    Search_Field_Labels convention: a missing translation falls back to Label).

    Request-context only (reads get_locale()); non-request callers — the AI
    catalogs and the scheduler's _metrics_for_source — keep using m['label'].
    """
    attr = _METRIC_LABEL_ATTRS.get(str(get_locale()))
    return (m.get(attr) if attr else None) or m["label"]


def _metrics_for_source(source_id, locale=None):
    """Enabled metrics bound to `source_id` as {code: {aggregation, base_field}}.

    `label` is the metric's display name, used as the result column header so a
    run never shows the raw code (`docs_imported`). It is only locale-swapped
    when `locale` is passed — the scheduler calls this outside a request, where
    get_locale() would raise, so it keeps the English label.
    """
    attr = _METRIC_LABEL_ATTRS.get(str(locale)) if locale else None
    return {
        code: {
            "aggregation": m["aggregation"],
            "base_field": m["base_field"],
            "total_mode": m.get("total_mode", "sum"),
            "anchor": m.get("anchor"),
            "label": (m.get(attr) if attr else None) or m["label"],
        }
        for code, m in _load_db_metrics().items()
        if m["source_id"] == source_id
    }


def metric_result_columns(resolved_metrics, source_metrics):
    """Result columns for a run's metric projection — the metric codes the
    aggregate query appends after the dims, headered with their labels."""
    return [
        {
            "field": m["code"],
            "header": (source_metrics.get(m["code"]) or {}).get("label") or m["code"],
        }
        for m in resolved_metrics or []
    ]


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
    # Mark the Statconfig tables as per-process partial views, so the agent stops
    # answering company-wide questions from whichever single one it found in the
    # flat INFORMATION_SCHEMA dump (issue #128). Statconfig being unavailable just
    # drops the block — never a 500.
    partial_tables = {}
    try:
        allowed = _allowed_processes()
        field_maps = _load_field_col_maps(allowed)
        for cfg in _load_process_configs(allowed):
            if not cfg.get("table"):
                continue
            entry = partial_tables.setdefault(
                cfg["table"],
                {
                    "processes": [],
                    "import_col": cfg.get("import_col"),
                    "export_col": cfg.get("export_col"),
                    "fields": field_maps.get(cfg["process"]) or {},
                },
            )
            entry["processes"].append(cfg["process"])
    except Exception as e:
        current_app.logger.warning(f"reporting.ai schema: Statconfig unavailable: {e}")
    text, truncated = serialize_schema(
        targets=targets,
        curated=curated,
        metrics=metrics or None,
        partial_tables=partial_tables,
    )
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
        # A count_distinct metric grouped by its own base field always yields
        # 1 per row — drop the shadowing column instead of bouncing the draft.
        drop_columns_shadowing_distinct_metrics(definition, source_metrics)
        to_validate = {k: v for k, v in definition.items() if k != "chartHint"}
        validate_report_definition(
            to_validate,
            catalog_fields,
            filterable,
            sortable,
            max_row_limit=MAX_ROW_LIMIT,
            metric_codes=set(source_metrics),
            grainable_fields=grainable,
            date_fields=date_fields_from_catalog(catalog),
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
        raise ReportDefinitionError(
            f"unknown SQL target {target!r} — allowed targets: " + ", ".join(sorted(_SQL_TARGETS))
        )
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
        # Fetch-side cap, uniform on every path (D-CTE): a plain SELECT's TOP
        # wrap already limits the driver's result set, but a WITH-rooted or
        # top-level-ORDER-BY query is passed through unwrapped by
        # wrap_with_cap() (neither construct is legal inside a derived-table
        # subquery, see issue #129) — this fetchmany(cap + 1) is the only
        # row-count enforcement for that path.
        rows, _truncated = fetch_capped(cur, SQL_ROW_CAP)
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
            f"SELECT * FROM Statconfig WHERE ProcessName IN ({ph}) AND ISNULL(ClientCode, 'default') <> 'ms02'",
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


def _resolve_definition_tokens_or_error(rd):
    """Token -> absolute dates at run time. A malformed token cannot pass the
    validator, but saved JSON is not immutable — surface it as a definition
    error (HTTP 400), never a 500."""
    try:
        return resolve_definition_tokens(rd)
    except ValueError as e:
        raise ReportDefinitionError(str(e)) from e


def _resolved_dates_meta(rd):
    """[{field, token, n?, start, end}] for each token filter (inclusive display
    range) — the run response's transparency metadata."""
    out = []
    for f in rd.get("filters") or []:
        value = f.get("value")
        if not isinstance(value, dict):
            continue
        try:
            start, end = resolve_token(value)
        except ValueError as e:
            current_app.logger.warning(
                f"reporting: _resolved_dates_meta could not resolve token {value!r}: {e}"
            )
            continue
        item = {
            "field": f.get("field"),
            "token": value.get("token"),
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        if value.get("n") is not None:
            item["n"] = value["n"]
        out.append(item)
    return out


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
        source_metrics = _metrics_for_source(source["id"], get_locale())
        validate_report_definition(
            rd,
            catalog_fields,
            filterable,
            sortable,
            max_row_limit=MAX_ROW_LIMIT,
            metric_codes=set(source_metrics),
            grainable_fields=grainable,
            date_fields=date_fields_from_catalog(catalog),
        )
        rd = _resolve_definition_tokens_or_error(rd)
        resolved = (
            resolve_metrics(rd.get("metrics"), source_metrics, catalog_fields)
            if rd.get("metrics")
            else None
        )
        # Date-anchored measures (imported/exported/backlog) share ONE time
        # axis (activity_date) — each measure buckets its own date onto it.
        # Teach the incoherent combinations away instead of emitting bad SQL.
        anchored = [m for m in (resolved or []) if m.get("anchor")]
        col_fields = {c.get("field") for c in rd.get("columns") or []}
        filt_fields = {f.get("field") for f in rd.get("filters") or []}
        if anchored and len(anchored) != len(resolved):
            raise ReportDefinitionError(
                "anchored measures (imported/exported/backlog) cannot be mixed "
                "with unanchored ones — pick one kind"
            )
        if anchored and col_fields & {"import_date", "export_date"}:
            raise ReportDefinitionError(
                "anchored measures plot on the shared 'activity_date' axis — "
                "use it instead of import_date/export_date columns"
            )
        if anchored and filt_fields & {"import_date", "export_date"}:
            raise ReportDefinitionError(
                "filter anchored reports on 'activity_date' — the range then "
                "applies to each measure's own date"
            )
        if "activity_date" in (col_fields | filt_fields) and not anchored:
            raise ReportDefinitionError(
                "'activity_date' is only valid with date-anchored measures "
                "(imported/exported/backlog)"
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
            rd_columns + metric_result_columns(resolved, source_metrics) if resolved else rd_columns
        )
        return out_columns, sql, params, engine_statistics_db

    if provider == "table":
        catalog, catalog_fields, filterable, sortable = _catalog_for_source(source)
        grainable = {f["field"] for f in catalog if f.get("grainable")}
        source_metrics = _metrics_for_source(source["id"], get_locale())
        validate_report_definition(
            rd,
            catalog_fields,
            filterable,
            sortable,
            max_row_limit=MAX_ROW_LIMIT,
            metric_codes=set(source_metrics),
            grainable_fields=grainable,
            date_fields=date_fields_from_catalog(catalog),
        )
        rd = _resolve_definition_tokens_or_error(rd)
        resolved = (
            resolve_metrics(rd.get("metrics"), source_metrics, catalog_fields)
            if rd.get("metrics")
            else None
        )
        latest_of = None
        if resolved:
            modes = {
                (source_metrics.get(m["code"]) or {}).get("total_mode", "sum") for m in resolved
            }
            date_candidates = [f["field"] for f in catalog if f.get("grainable")]
            if modes == {"latest"} and len(date_candidates) == 1:
                latest_of = date_candidates[0]
        sql, params = build_generic_query(
            rd,
            source.get("baseObject"),
            catalog,
            row_cap=rd.get("rowLimit", DEFAULT_ROW_LIMIT),
            resolved_metrics=resolved,
            latest_of=latest_of,
        )
        engine = _CURATED_ENGINES.get(source.get("engine"))
        if engine is None:
            raise ReportDefinitionError("source engine is not configured")
        rd_columns = rd.get("columns") or []
        out_columns = (
            rd_columns + metric_result_columns(resolved, source_metrics) if resolved else rd_columns
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


def _forecast_for(rd, columns, rows):
    """Forecast block for one run result — shared by /api/reporting/run and
    /api/reporting/export so both surfaces produce the same forecast (#178).

    Refits on a widened lookback window when the definition qualifies (real
    history beats the visible window for fit quality), falling back to the
    visible rows on any failure. The auto horizon still resolves from the
    VISIBLE `rows` (via compute_forecast's `visible_rows` param) so widening
    the lookback changes fit quality only, never how many buckets project.
    """
    fit_columns, fit_rows = columns, rows
    widened = widened_definition_for_forecast(rd)
    if widened is not None:
        try:
            w_columns, w_sql, w_params, w_engine = _prepare_run(widened)
            fit_columns, fit_rows = w_columns, _execute(w_engine, w_sql, w_params)
        except Exception as e:
            current_app.logger.warning(f"reporting forecast lookback skipped: {e}")
    return compute_forecast(
        rd, fit_columns, fit_rows, visible_rows=rows, carry_forward=_level_metric_indexes(rd)
    )


def _level_metric_indexes(rd):
    """Indexes (within rd['metrics']) of latest-mode metrics — levels such as
    the backlog, whose missing buckets the forecast carries forward rather
    than zero-fills. Empty for anything that can't be resolved."""
    try:
        source = _get_effective_source(rd.get("source"))
        modes = _metrics_for_source(source["id"]) if source else {}
        return {
            i
            for i, m in enumerate(rd.get("metrics") or [])
            if (modes.get(m.get("metric")) or {}).get("total_mode") == "latest"
        }
    except Exception:
        return set()


def _json_safe(value):
    """Coerce one DB result cell to a JSON-serializable value.

    Flask's default JSON encoder handles None/bool/int/float/str and
    date/datetime/Decimal/UUID, but NOT bytes/bytearray/memoryview (varbinary,
    rowversion/timestamp, image) or datetime.time (TIME) — those raise
    "Object of type X is not JSON serializable" and 500 the run. Map the crashy
    types to readable strings, pass the Flask-native ones through unchanged, and
    stringify anything else as a last resort (a result cell must never 500).

    Dates are the exception to "pass Flask-native through": DefaultJSONProvider
    emits the HTTP-date form ("Thu, 26 Mar 2026 08:56:28 GMT"), which is what
    ended up in result tables (issue #175). Format them here instead —
    yyyy-MM-dd HH:mm:ss / yyyy-MM-dd, sortable and locale-free. Nothing parses
    these back: the front end renders result cells as text, and xlsx/csv export
    serializes the raw rows, not these.
    """
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, bytes | bytearray | memoryview):
        return "0x" + bytes(value).hex()
    if isinstance(value, datetime.time):
        return value.isoformat()
    if isinstance(value, datetime.datetime):  # before date — datetime subclasses it
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, datetime.date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, decimal.Decimal | uuid.UUID):
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


_CHART_IMAGE_PREFIX = "data:image/png;base64,"
_CHART_IMAGE_MAX = 2_000_000  # decoded bytes


def _parse_chart_image(value):
    """Decode a client-supplied chart data-URL; returns PNG bytes or None on anything dubious."""
    if not isinstance(value, str) or not value.startswith(_CHART_IMAGE_PREFIX):
        return None
    try:
        raw = base64.b64decode(value[len(_CHART_IMAGE_PREFIX) :], validate=True)
    except Exception:
        return None
    if len(raw) > _CHART_IMAGE_MAX or raw[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return raw


def _serialize_export(columns, rows, title, fmt, chart_png=None, forecast_start=None):
    """Build a Flask download Response for `rows` in the requested format."""
    name = _safe_report_name(title)
    if fmt == "csv":
        return Response(
            rows_to_csv(columns, rows),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
        )
    return Response(
        rows_to_xlsx(
            columns,
            rows,
            title=title or "Report",
            chart_png=chart_png,
            forecast_start=forecast_start,
        ),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'},
    )


# The user guide is authored in git as docs/howto/reporting-guide.md and
# served in-app here (English only; the Confluence mirror stays for the team).
# The deploy workflow copies this one docs file onto the server — see the
# "Sync to deploy folder" step in .github/workflows/deploy.yml.
_GUIDE_MD = Path(__file__).resolve().parents[2] / "docs" / "howto" / "reporting-guide.md"


def _guide_render(md_text):
    """reporting-guide.md -> (html, toc list of {slug, title}). Pure.

    Drops the H1 (the page chrome carries the title), unwraps links to other
    .md files (their targets are not routable in-app), and stamps slug ids on
    <h2> headings so the on-page TOC can anchor-link them.
    """
    lines = md_text.splitlines()
    body = [ln for i, ln in enumerate(lines) if not (ln.startswith("# ") and i < 5)]
    text = re.sub(r"\[([^\]]+)\]\([^)\s]*\.md\)", r"\1", "\n".join(body))
    html = MarkdownIt("commonmark").enable(["table", "strikethrough"]).render(text)
    toc = []

    def _anchor(match):
        title = re.sub(r"<[^>]+>", "", match.group(1))
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        toc.append({"slug": slug, "title": title})
        return f'<h2 id="{slug}">{match.group(1)}</h2>'

    return re.sub(r"<h2>(.*?)</h2>", _anchor, html), toc


@require_permission("reporting.view")
def reporting_guide():
    try:
        guide_html, guide_toc = _guide_render(_GUIDE_MD.read_text(encoding="utf-8"))
    except OSError:
        current_app.logger.error("reporting guide source missing: %s", _GUIDE_MD)
        guide_html, guide_toc = None, []
    return render_template(
        "reporting_guide.html",
        guide_html=guide_html,
        guide_toc=guide_toc,
        logged_in_user=session.get("username", "Unknown"),
        fullname=session.get("fullname"),
        pageV=page_visibility(),
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
        ai_caption_enabled=has_permission("reporting.ai.explain_data"),
        details_images_perm=has_permission("workitems.details.view.images"),
        details_audit_perm=has_permission("workitems.details.view.audit"),
        details_fields_perm=has_permission("workitems.details.view.fields"),
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
        return jsonify(
            {"error": _("This report definition is invalid or outdated."), "detail": str(e)}
        ), 400
    except Exception as e:
        current_app.logger.error(f"/api/reporting/run prepare error: {e}")
        return jsonify({"error": _("Could not build report")}), 500
    try:
        rows = _execute(engine, sql, params)
    except Exception as e:
        current_app.logger.error(f"/api/reporting/run exec error: {e}")
        return jsonify({"error": _("Could not run report")}), 500
    pretty = format_sql(sql)
    payload = {
        "columns": [
            {"field": c["field"], "header": c.get("header") or c["field"]} for c in columns
        ],
        "rows": _rows_json_safe(rows),
        "rowCount": len(rows),
        "truncated": len(rows) >= min(int(rd.get("rowLimit", DEFAULT_ROW_LIMIT)), MAX_ROW_LIMIT),
        "sql": sql,
        "sqlPretty": pretty,
        "sqlDisplay": inline_sql_params(pretty, params),
        "params": [_json_safe(p) for p in params],
    }
    if rd.get("compare"):
        shifted = shifted_definition_for_comparison(rd)
        if shifted is not None:
            shifted_rd, prior_start, prior_end = shifted
            try:
                c_columns, c_sql, c_params, c_engine = _prepare_run(shifted_rd)
                c_rows = _execute(c_engine, c_sql, c_params)
                payload["comparison"] = {
                    "columns": [
                        {"field": c["field"], "header": c.get("header") or c["field"]}
                        for c in c_columns
                    ],
                    "rows": _rows_json_safe(c_rows),
                    "priorStart": prior_start.isoformat(),
                    "priorEnd": prior_end.isoformat(),
                }
            except Exception as e:
                current_app.logger.warning(f"/api/reporting/run comparison skipped: {e}")
    fc_req = rd.get("forecast")
    if isinstance(fc_req, dict) and fc_req.get("enabled"):
        try:
            payload["forecast"] = _forecast_for(rd, columns, rows)
        except Exception as e:  # a forecast must never take down the run
            current_app.logger.warning(f"/api/reporting/run forecast skipped: {e}")
    # rd is the original request body (tokens intact) — _prepare_run resolves
    # its own local copy. _resolved_dates_meta needs the tokens to produce labels.
    resolved_dates = _resolved_dates_meta(rd)
    if resolved_dates:
        payload["resolvedDates"] = resolved_dates
    return jsonify(payload)


def _sandbox_error_message(e):
    """Translated user-facing message for a SqlSandboxError, keyed by rule.

    The raw English message stays in the response's `detail` field; dynamic
    bits (keyword / construct name) arrive via e.token. Unknown rules fall
    back to the raw message rather than hiding information.
    """
    token = getattr(e, "token", None) or ""
    messages = {
        "empty": _("SQL is required."),
        "too_long": _("The SQL exceeds {n} characters.").format(n=MAX_SQL_LEN),
        "blocked_keyword": _("Disallowed keyword: {kw}").format(kw=token),
        "parse": _("The SQL could not be parsed."),
        "multi_statement": _("Exactly one statement is allowed."),
        "not_select": _("Only SELECT / WITH / set operations are allowed."),
        "forbidden_node": _("Disallowed construct: {kw}").format(kw=token),
        "tsql_limit": _("T-SQL does not support LIMIT — use TOP (n) instead."),
    }
    return messages.get(e.rule, str(e))


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
        return jsonify({"error": _sandbox_error_message(e), "rule": e.rule, "detail": str(e)}), 400
    except ReportDefinitionError as e:
        return jsonify({"error": _("Invalid SQL request."), "detail": str(e)}), 400
    except RuntimeError:
        return jsonify({"error": _("SQL source is not configured")}), 503
    except Exception as e:
        current_app.logger.error(f"/api/reporting/sql/run exec error: {e}")
        return jsonify(
            {"error": _("Could not run query"), "detail": humanize_sql_error(str(e))}
        ), 500
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
        return jsonify({"error": _("Eddard could not answer right now")}), 502

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

    # Refine context (optional): prompt grounding ONLY — never executed, never
    # trusted. The model's output still passes _validate_definition_for_user,
    # so a crafted prior definition cannot widen access; its risk class equals
    # free text in `question`. Size caps keep the prompt bounded.
    prior_question = body.get("priorQuestion")
    prior_definition = body.get("priorDefinition")
    if prior_question is not None and (
        not isinstance(prior_question, str) or len(prior_question) > 2000
    ):
        return jsonify({"error": _("Invalid refine context")}), 400
    if prior_definition is not None:
        if not isinstance(prior_definition, dict):
            return jsonify({"error": _("Invalid refine context")}), 400
        try:
            _pd_json = json.dumps(prior_definition)
        except (RecursionError, ValueError):
            return jsonify({"error": _("Invalid refine context")}), 400
        if len(_pd_json) > 20000:
            return jsonify({"error": _("Invalid refine context")}), 400

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
                today=datetime.date.today().isoformat(),
                prior_question=prior_question or None,
                prior_definition=prior_definition or None,
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
            return jsonify({"error": _("Eddard could not answer right now")}), 502
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


def _extract_agent_artifacts(tool_trace):
    """Pull the last validated definition / SQL out of the loop's tool trace.

    A build_definition OR run_definition call that returned ok=True carries a
    runnable definition in its args (run_definition validates the same way before
    executing); a validate_sql ok=True carries gate-approved SQL. These let the UI
    offer one-click 'Open in builder' / 'Insert SQL' just like Surfaces A/B.
    """
    definition, sql = None, None
    for step in tool_trace:
        if not (step.get("result") or {}).get("ok"):
            continue
        if step.get("name") in ("build_definition", "run_definition"):
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

    raw_history = body.get("history")
    if raw_history is not None and not isinstance(raw_history, list):
        return jsonify({"error": _("Invalid history")}), 400
    history = []
    for h in raw_history or []:
        if (
            isinstance(h, dict)
            and h.get("role") in ("user", "assistant")
            and isinstance(h.get("content"), str)
            and h["content"].strip()
        ):
            history.append({"role": h["role"], "content": h["content"]})
    history = history[-8:]
    while history and sum(len(h["content"]) for h in history) > 12000:
        history.pop(0)

    # Issue #153: "Continue" past a max_turns/budget dead-end re-runs the same
    # question with raised caps rather than resuming the loop mid-flight (the
    # transcript isn't persisted). continueAttempt is clamped, not rejected
    # out of range, so a stale/tampered client value can't grant more than the
    # ceiling.
    try:
        continue_attempt = int(body.get("continueAttempt") or 0)
    except (TypeError, ValueError):
        continue_attempt = 0
    continue_attempt = max(0, min(continue_attempt, MAX_CONTINUE_ATTEMPTS))
    agent_max_turns = CONTINUE_MAX_TURNS if continue_attempt else None
    agent_budget_s = CONTINUE_BUDGET_S if continue_attempt else None

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
    # The client sends the active builder source only as prompt grounding. It is a
    # UI default, not the question's subject: a curated table-provider source (e.g.
    # Generali on GeneraliDB) has no RO SQL target, but the grounding marks such
    # sources builder-only and the system prompt steers run_sql away from them —
    # the data tools stay bound so questions about run_sql-able sources still get
    # real numbers even while the builder happens to sit on a curated source.
    active_source = None
    source_id = (body.get("source") or "").strip()
    if source_id:
        active_source = _get_effective_source(source_id)
    source_is_builder_only = bool(
        active_source
        and active_source.get("kind") == "curated"
        and (active_source.get("provider") or "docprocessing") != "docprocessing"
    )

    has_sql = has_permission("reporting.ai.sql")
    explain = has_permission("reporting.ai.explain_data") and has_permission("reporting.sql.run")
    tool_names = {"build_definition"}
    if has_sql:
        tool_names.add("validate_sql")
    if explain:
        tool_names.update({"run_sql", "compute_stats", "run_definition"})
    tools = [t for t in TOOL_SPECS if t["name"] in tool_names]

    run_definition_bound = None
    if explain:

        def run_definition_bound(definition):
            """Run a v1 definition for real and hand back its rows, so the agent
            can quote actual numbers instead of stopping at "definition built,
            not run". Same repair/validate pass as build_definition (a near-miss
            draft is coerced, not bounced), then the exact query the interactive
            builder would run. Capped so one runaway (ungrouped) definition can't
            blow the tool-result context — grouped/anchored reports are naturally
            small (a handful of buckets)."""
            ok, error = _validate_definition_for_user(definition)
            if not ok:
                raise ReportDefinitionError(error or "invalid definition")
            perms = set(session.get("permissions") or [])
            columns, rows = execute_definition(definition, perms, userid, username, get_locale())
            return columns, rows[:RUN_DEFINITION_ROW_CAP]

    run_sql_bound = None
    if explain:

        def run_sql_bound(target, sql):
            """Enforce the same gates api_sql_run applies before touching _run_sql.

            Mirrors api_sql_run's exact composition/order: ack check first, then
            per-target authorization (_authorize_sql_target). D-RUNSQL: binding
            run_sql on reporting.ai.explain_data + reporting.sql.run is not itself
            proof the caller may use THIS target, nor that they've acked the
            sandbox terms — those are checked here, same as the HTTP route.
            Both failures raise (audited with a distinct status first);
            ToolRegistry.call() catches any tool exception and turns it into a
            {"ok": False, "error": ...} result, so this never raises through to a
            500 on /api/reporting/ai/agent — the agent gets a relayable error.
            """
            sql_text = sql if isinstance(sql, str) else ""
            if not _has_acked(userid):
                _audit_sql(userid, username, target, sql_text, None, "refused_ack", None)
                raise PermissionError("Acknowledgment required before running SQL")
            try:
                _authorize_sql_target(target)
            except PermissionError as e:
                _audit_sql(userid, username, target, sql_text, None, "refused_auth", None)
                raise PermissionError(f"Not authorized for SQL target {target!r}") from e
            return _run_sql(target, sql, userid=userid, username=username)

    registry = ToolRegistry(
        run_sql=run_sql_bound,
        validate_definition=_validate_definition_for_user,
        run_definition=run_definition_bound,
    )

    grounding = (
        f"Today's date is {datetime.date.today().isoformat()}.\n\n"
        f"Available report sources and fields:\n{_ai_catalog_text()}"
    )
    if has_sql or explain:
        grounding += f"\n\nSQL schema (for validate_sql / run_sql):\n{_ai_schema_text()}"
        grounding += (
            '\nrun_sql "target" argument MUST be one of: '
            + ", ".join(sorted(_SQL_TARGETS))
            + ". Any other value is rejected."
        )
    if active_source:
        grounding += (
            f'\n\nThe user\'s selected source is "{active_source.get("label")}" '
            f'(id {active_source.get("id")}); "this source" in the question means it. '
            "It is only a UI default — when the question neither says \"this source\" "
            "nor names it, choose the best-fitting source from the catalog instead "
            "(for counting/aggregation questions, one that lists metrics)."
        )
        if source_is_builder_only:
            grounding += (
                " It is builder-only — answer it with build_definition; run_sql cannot " "reach it."
            )
    initial = f"{grounding}\n\nQuestion: {question}"
    system_prompt = _AGENT_SYSTEM + (_AGENT_EXPLAIN_SUFFIX if explain else "")

    loop_kwargs = {}
    if agent_max_turns is not None:
        loop_kwargs["max_turns"] = agent_max_turns
    if agent_budget_s is not None:
        loop_kwargs["budget_s"] = agent_budget_s

    start = time.monotonic()

    def _finish(result):
        """Audit a completed loop and shape its response payload.

        Shared by both delivery modes: the plain JSON response and the NDJSON
        progress stream's final `done` line.
        """
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
        # Issue #127: never ship an empty answer — the chat panel would render
        # a blank bubble. The audit above keeps the raw (empty) answer; only
        # the user-facing payload gets the fallback. The in-loop nudge
        # (ask_agentic_iter) already retried once, so this is the last resort:
        # point at whatever artifact the loop did produce, or admit defeat.
        answer = (result.answer or "").strip()
        if not answer:
            if definition is not None and sql:
                answer = _(
                    "I couldn't write a summary this time, but I did produce a "
                    "report draft and a validated SQL query — use the actions "
                    "below to open them."
                )
            elif definition is not None:
                answer = _(
                    "I couldn't write a summary this time, but I did produce a "
                    "report draft — use “Open report” below to run it."
                )
            elif sql:
                answer = _(
                    "I couldn't write a summary this time, but I did draft a SQL "
                    "query — use the actions below to review it."
                )
            else:
                answer = _(
                    "I couldn't complete this request. Please try rephrasing the "
                    "question or narrowing it down."
                )
        return {
            "answer": answer,
            "definition": definition,
            "sql": sql,
            "toolTrace": result.tool_trace,
            "turns": result.turns,
            "stoppedReason": result.stopped_reason,
            "explainData": explain,
            "continueAttempt": continue_attempt,
            "canContinue": (
                result.stopped_reason in ("max_turns", "budget")
                and continue_attempt < MAX_CONTINUE_ATTEMPTS
            ),
        }

    def _audit_failure(status):
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
            status,
            int((time.monotonic() - start) * 1000),
        )

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
        # Streaming mode: the client asked to watch the loop work. NDJSON, one
        # object per line — {"phase": ...} progress events as they happen, then
        # exactly one {"done": true, ...} line carrying the same payload the
        # plain-JSON mode returns. Headers are already sent by then, so a
        # mid-stream failure rides in that final line instead of an HTTP status.
        if body.get("stream"):

            def emit():
                result = None
                try:
                    for event in ask_agentic_iter(
                        initial,
                        registry=registry,
                        agent_step=step,
                        history=history,
                        **loop_kwargs,
                    ):
                        if "result" in event:
                            result = event["result"]
                            break
                        yield json.dumps(event) + "\n"
                except Exception as e:
                    current_app.logger.error(f"/api/reporting/ai/agent provider error: {e}")
                    _audit_failure("error")
                    yield (
                        json.dumps(
                            {
                                "done": True,
                                "error": _("Eddard could not answer right now"),
                            }
                        )
                        + "\n"
                    )
                    return
                yield json.dumps({"done": True, **_finish(result)}) + "\n"

            return Response(
                stream_with_context(emit()),
                mimetype="application/x-ndjson",
                headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
            )

        result = ask_agentic(
            initial, registry=registry, agent_step=step, history=history, **loop_kwargs
        )
    except AiError as e:
        current_app.logger.warning(f"/api/reporting/ai/agent config error: {e}")
        _audit_failure("misconfig")
        return jsonify({"error": _("The AI assistant is not configured")}), 503
    except Exception as e:
        current_app.logger.error(f"/api/reporting/ai/agent provider error: {e}")
        _audit_failure("error")
        return jsonify({"error": _("Eddard could not answer right now")}), 502

    return jsonify(_finish(result))


def _caption_columns(raw):
    """Normalize a client-supplied column list to [{field, header}] dicts.

    Mirrors api_export_grid's column normalization: bare strings are accepted
    too (field == header == str(c)) so a caller need not always ship the full
    {field, header} shape.
    """
    out = []
    for c in raw:
        if isinstance(c, dict):
            header = c.get("header") or c.get("field") or ""
            out.append({"field": c.get("field") or header, "header": header})
        else:
            out.append({"field": str(c), "header": str(c)})
    return out


@require_permission("reporting.ai.explain_data")
@limiter.limit("10 per minute")
def api_ai_caption():
    """Surface D — a 1-2 sentence auto-caption over a result grid (Task 12).

    Unlike ask/build/agent, this surface's egress is NOT schema-only: `rows`
    are the actual values a Simple/Advanced result is displaying, so it is
    gated by reporting.ai.explain_data (the data-egress grant) rather than the
    weaker reporting.ai.use. It still counts toward the shared daily AI cap and
    is rate limited like the other AI endpoints. Rows never reach the model
    raw: caption() reduces the WHOLE grid to a fact sheet
    (nx_lib/reporting/caption_facts) — CAPTION_MAX_ROWS only bounds the request
    payload. Fired by fireCaption() (Task 13): the Simple tab after every
    successful run render, the Advanced tab on chart mount.
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    raw_columns = body.get("columns")
    rows = body.get("rows")
    if not isinstance(raw_columns, list) or not raw_columns or not isinstance(rows, list):
        return jsonify({"error": _("columns and rows are required")}), 400
    columns = _caption_columns(raw_columns)
    rows = [list(r) if isinstance(r, list | tuple) else [r] for r in rows[:CAPTION_MAX_ROWS]]
    title = (body.get("title") or "").strip() or None
    date_label = (body.get("dateLabel") or "").strip() or None
    # Client-side facts about the grid the model can't see (partial current
    # bucket, NULL = no snapshot); bounded like title.
    notes = str(body.get("notes") or "").strip()[:400] or None
    # Level measures (backlog): the fact sheet headlines their latest value
    # instead of summing buckets. Names only, bounded.
    raw_levels = body.get("levelFields")
    level_fields = (
        tuple(str(x)[:100] for x in raw_levels[:20] if isinstance(x, str))
        if isinstance(raw_levels, list)
        else ()
    )

    cfg = _ai_config()
    if cfg.get("provider") == "none" or not cfg.get("api_key"):
        return jsonify({"error": _("The AI assistant is not configured")}), 503

    userid, username = session.get("userid"), session.get("username")
    limit = _ai_daily_limit()
    if limit > 0 and _ai_asks_today(userid) >= limit:
        _audit_ai(
            userid,
            username,
            title or "",
            "caption",
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

    start = time.monotonic()
    try:
        result = ai_caption(
            columns,
            rows,
            title,
            date_label,
            notes=notes,
            level_fields=level_fields,
            locale=str(get_locale()),
            cfg=cfg,
        )
    except AiError as e:
        current_app.logger.warning(f"/api/reporting/ai/caption config error: {e}")
        _audit_ai(
            userid,
            username,
            title or "",
            "caption",
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
        current_app.logger.error(f"/api/reporting/ai/caption provider error: {e}")
        _audit_ai(
            userid,
            username,
            title or "",
            "caption",
            None,
            cfg.get("provider"),
            cfg.get("model"),
            None,
            None,
            "na",
            "error",
            int((time.monotonic() - start) * 1000),
        )
        return jsonify({"error": _("Eddard could not answer right now")}), 502

    duration_ms = int((time.monotonic() - start) * 1000)
    _audit_ai(
        userid,
        username,
        title or "",
        "caption",
        None,
        result.provider,
        result.model,
        result.tokens_in,
        result.tokens_out,
        "na",
        "ok",
        duration_ms,
    )
    return jsonify({"caption": result.caption})


@require_permission("reporting.export")
@limiter.limit("30 per minute")
def api_export():
    rd = request.get_json(silent=True)
    if not isinstance(rd, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    chart_png = _parse_chart_image(rd.pop("chartImage", None))
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
            return jsonify(
                {"error": _sandbox_error_message(e), "rule": e.rule, "detail": str(e)}
            ), 400
        except ReportDefinitionError as e:
            return jsonify({"error": _("Invalid SQL request."), "detail": str(e)}), 400
        except RuntimeError:
            return jsonify({"error": _("SQL source is not configured")}), 503
        except Exception as e:
            current_app.logger.error(f"/api/reporting/export sql error: {e}")
            return jsonify({"error": _("Could not export query")}), 500
        return _serialize_export(
            columns, rows, rd.get("title") or _("Report"), fmt, chart_png=chart_png
        )
    try:
        columns, sql, params, engine = _prepare_run(rd)
        rows = _execute(engine, sql, params)
    except PermissionError:
        return jsonify({"error": _("Not authorized for this source")}), 403
    except (ReportDefinitionError, QueryBuildError, TableQueryError, MetricResolveError) as e:
        return jsonify(
            {"error": _("This report definition is invalid or outdated."), "detail": str(e)}
        ), 400
    except Exception as e:
        current_app.logger.error(f"/api/reporting/export error: {e}")
        return jsonify({"error": _("Could not export report")}), 500
    forecast_start = None
    fc_req = rd.get("forecast")
    if isinstance(fc_req, dict) and fc_req.get("enabled"):
        try:
            fc = _forecast_for(rd, columns, rows)
            if fc and not fc.get("unavailable"):
                columns, rows, forecast_start = forecast_export_rows(
                    columns, rows, fc, marker_header=_("Forecast")
                )
        except Exception as e:
            current_app.logger.warning(f"/api/reporting/export forecast skipped: {e}")
    return _serialize_export(
        columns,
        rows,
        rd.get("title") or _("Report"),
        fmt,
        chart_png=chart_png,
        forecast_start=forecast_start,
    )


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
    chart_png = _parse_chart_image(payload.pop("chartImage", None))
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
    return _serialize_export(
        columns, rows, payload.get("title") or _("Report"), fmt, chart_png=chart_png
    )


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
    app.add_url_rule("/reporting", endpoint="reporting", view_func=reporting)
    app.add_url_rule("/reporting/guide", endpoint="reporting_guide", view_func=reporting_guide)
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
        "/api/reporting/ai/caption",
        endpoint="reporting_ai_caption",
        view_func=api_ai_caption,
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
