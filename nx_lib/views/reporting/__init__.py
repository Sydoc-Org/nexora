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

import time

from flask import (
    current_app,
    jsonify,
    request,
    session,
)
from flask_babel import gettext as _

from ... import mapping_config
from ...db import engine_statistics_db
from ...extensions import limiter
from ...i18n import get_locale
from ...reporting import db_schema
from ...reporting.catalog import fetch_docprocessing_catalog
from ...reporting.sources import accessible
from ...reporting.table_query import TableQueryError, build_distinct_query, table_source_catalog
from ...security import has_permission, require_permission
from . import admin_registry, ai, export, pages, reports, run, schedules
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
from .admin_registry import invalidate_reporting_metrics, invalidate_reporting_sources
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
from .reports import _preview_kind, _preview_summary
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
    "invalidate_reporting_metrics",
    "invalidate_reporting_sources",
    "_load_db_metrics",
    "_load_db_sources",
    "_load_field_col_maps",
    "_load_process_configs",
    "_METRIC_LABEL_ATTRS",
    "_metrics_for_source",
    "_preview_kind",
    "_preview_summary",
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
    admin_registry.register_routes(app)
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
    reports.register_routes(app)
    schedules.register_routes(app)
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
