"""Reporting shared core — beautify-phase-2a, Task 2.

Split out of ``nx_lib/views/reporting/__init__.py``: the SQL-target
constants, the source/metric registry, the curated-report run pipeline, and
the live-SQL sandbox's auth/audit helpers that 5+ feature clusters
(``__init__.py``'s own routes, ``ai.py``, and ``nx_lib/reporting/runner.py``)
all depend on.

``__init__.py`` re-exports every name defined here under its original import
path (``nx_lib.views.reporting.<name>``), so nothing changes for callers,
tests, or ``runner.py`` (which reads a dozen of these attributes off the
package at runtime via ``from ..views import reporting as rv``). ``ai.py``
reaches these the same way it always has — a function-local ``from . import
...`` against the package namespace — so it is untouched by this move.
"""

import datetime
import decimal
import json
import time
import uuid

from flask import current_app, session

from ... import config as cfg
from ... import mapping_config
from ...db import (
    engine_generali_db,
    engine_generali_ro,
    engine_nexora_db,
    engine_octo_db,
    engine_octo_ro,
    engine_statistics_db,
    engine_statistics_ro,
)
from ...extensions import cache
from ...i18n import get_locale
from ...process_helpers import process_grants
from ...reporting.catalog import fetch_docprocessing_catalog
from ...reporting.query import build_table_query
from ...reporting.sandbox import (
    SqlSandboxError,
    fetch_capped,
    validate_select,
    wrap_with_cap,
)
from ...reporting.schema import (
    ReportDefinitionError,
    validate_layout_definition,
    validate_report_definition,
)
from ...reporting.semantic import resolve_metrics
from ...reporting.sources import (
    DEFAULT_ROW_LIMIT,
    MAX_ROW_LIMIT,
    SQL_ROW_CAP,
    SQL_TIMEOUT_S,
    accessible,
    code_sources,
    merge_sources,
)
from ...reporting.table_query import build_generic_query, table_source_catalog
from ...reporting.tokens import date_fields_from_catalog, resolve_definition_tokens
from ...security import has_permission

_SQL_TARGET_ENGINES = {
    "statistics": engine_statistics_ro,
    "octopus": engine_octo_ro,
    "generali": engine_generali_ro,
}
_SQL_TARGETS = set(_SQL_TARGET_ENGINES)

# Per-target permission. The base reporting.sql.run gate (on the routes) covers
# the Statistics target; every other database — the Octo runtime, the Generali
# tenant DB — additionally requires its own grant, so SQL access and access to
# a particular database stay separable. NexoraDB is deliberately absent: it
# holds the password hashes and TOTP secrets, so it is not a query target at
# any permission level.
_SQL_TARGET_PERMISSION = {
    "statistics": "reporting.sql.run",
    "octopus": "reporting.sql.target.octopus.use",
    "generali": "reporting.sql.target.generali.use",
}

# The database each target actually reads, for the UI's target picker. Resolved
# from config so INT and PROD each show their own real name.
_SQL_TARGET_DB = {
    "statistics": cfg.DB_STATISTICS,
    "octopus": cfg.DB_OCTO_RUNTIME,
    "generali": cfg.DB_GENERALI,
}


# Engines a curated source's generic 'table' provider may read from (SELECT-only).
_CURATED_ENGINES = {
    "nexora": engine_nexora_db,
    "statistics": engine_statistics_db,
    "generali": engine_generali_db,
    "octopus": engine_octo_db,
}


_SOURCES_CACHE_KEY = "reporting_sources_registry"
_METRICS_CACHE_KEY = "reporting_metrics_registry"
_REGISTRY_TTL = 60  # seconds; admin CRUD invalidates explicitly, so this only bounds staleness


def _load_db_sources():
    """Read dbo.ReportingSources registry rows as descriptor dicts (best-effort).

    Cached 60s (house TTL pattern, mirrors nx_lib/mapping_config.py) --
    success-only: a load error is logged and answered with the code-defined
    fallback (an empty list, so the page degrades to the code-defined defaults
    rather than 500-ing) but is NEVER cached, so the next call re-queries
    rather than pinning the outage for the full TTL. Admin CRUD routes call
    invalidate_reporting_sources() so an edit is visible immediately.
    """
    cached = cache.get(_SOURCES_CACHE_KEY)
    if cached is not None:
        return cached
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
        cache.set(_SOURCES_CACHE_KEY, rows, timeout=_REGISTRY_TTL)  # success-only, incl. empty
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

    Cached 60s (house TTL pattern, mirrors nx_lib/mapping_config.py) --
    success-only: a load error is logged and answered with the fallback (an
    empty dict, so the page degrades to "no metrics" rather than 500-ing —
    mirrors _load_db_sources) but is NEVER cached. Admin CRUD routes call
    invalidate_reporting_metrics() so an edit is visible immediately.
    """
    cached = cache.get(_METRICS_CACHE_KEY)
    if cached is not None:
        return cached
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
            "DateAnchor, FilterJson "
            "FROM dbo.ReportingMetrics WHERE Enabled = 1"
        )
        out = {}
        for r in cur.fetchall():
            filt = None
            if getattr(r, "FilterJson", None):
                try:
                    filt = json.loads(r.FilterJson)
                except ValueError:
                    # A malformed condition must not silently widen the metric to
                    # "everything": the resolver rejects a non-list, so the metric
                    # errors loudly at run time instead.
                    filt = "malformed"
            out[r.Code] = {
                "filter": filt,
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
        cache.set(_METRICS_CACHE_KEY, out, timeout=_REGISTRY_TTL)  # success-only, incl. empty
        return out
    except Exception as e:
        current_app.logger.warning(f"reporting metrics: registry read failed: {e}")
        return {}
    finally:
        conn.close()


_METRIC_LABEL_ATTRS = {"de": "label_de", "fr": "label_fr", "it": "label_it"}


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
            "filter": m.get("filter"),
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


def _load_owned_layout(layout_id, userid):
    """The parsed kind:'layout' definition `userid` owns under `layout_id`, else None.
    Layouts are private (spec D-ownership): shares and Visibility='shared' do not count."""
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT r.DefinitionJSON FROM dbo.Reports r "
            "WHERE r.ReportID = ? AND r.OwnerUserID = ? "
            "  AND JSON_VALUE(r.DefinitionJSON, '$.kind') = 'layout'",
            (layout_id, userid),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return None


def _layout_block(rd, userid):
    """(layout, fallback) for a run request. `layoutId` wins over an inline
    `layout` (the editor's unsaved-preview path). fallback is 'missing' when the
    id resolves to nothing the caller owns, 'invalid' when the layout fails
    validation, None otherwise."""
    layout_id = rd.get("layoutId")
    if layout_id is not None:
        layout = _load_owned_layout(layout_id, userid)
        if layout is None:
            return None, "missing"
    else:
        layout = rd.get("layout")
        if layout is None:
            return None, None
    try:
        validate_layout_definition(layout)
    except ReportDefinitionError:
        return None, "invalid"
    return layout, None


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
        assert conn.dbapi_connection is not None  # fresh from the pool, not invalidated
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


_SCOPE_PREFIX = "reporting.scope.process."


def _allowed_processes():
    """Processes the caller may include: ``process.<client>.<process>.view``
    grants (0087) or the legacy ``reporting.scope.process.*`` family. Reporting
    is not a tenant-scoped page, so this deliberately skips the tenant scope
    ``granted_processes`` applies for the dashboard and workitems."""
    return sorted(process_grants(session.get("permissions", []), _SCOPE_PREFIX))


def _load_process_configs(target_processes):
    """ProcessSource rows (mapping_config #98 registry) for the target
    processes, scoped to non-ms02 clients, as plain dicts (build_table_query's
    expected shape) -- successor to the direct Statconfig cursor read.

    Raises if the registry itself failed to load: a genuine NexoraDB/config
    outage must surface as an error here (via _prepare_run's generic-exception
    500, or _ai_schema_text's own try/except), never be silently reshaped into
    an empty catalog / a QueryBuildError("no processes in scope") 400 that
    misrepresents a system failure as bad input -- the contract the legacy
    per-call SELECT gave for free by always hitting NexoraDB directly. See
    nx_lib/views/dashboard.py's `_statconfig_sources` for the same pattern.
    """
    if not target_processes:
        return []
    if mapping_config.registry() is None:
        raise RuntimeError("mapping_config registry unavailable")
    sources = [
        s
        for s in mapping_config.sources_for(None, target_processes)
        if (s.client or "default") != "ms02"
    ]
    return [
        {
            "process": s.process,
            "table": s.table,
            "export_col": s.export_column,
            "import_col": s.import_column,
            "condition": s.extra_condition or "",
            "workitem_col": s.workitem_column,
        }
        for s in sources
    ]


def _load_field_col_maps(target_processes):
    """Per-process {field_key: actual_column} maps from the mapping_config
    #98 registry's ProcessFieldMappings -- successor to the direct
    SearchConfig col_* cursor read. Same fail-loud contract as
    `_load_process_configs` (registry load failure raises, never degrades to
    an empty map that looks like "no fields configured").

    The legacy SELECT had no ClientCode filter (SearchConfig's ProcessName
    already disambiguates within a client's rows), so this reads across all
    clients too -- mappings_for() requires one client per call, so build the
    dict by iterating every client present in the registry's sources rather
    than guessing which ones matter.
    """
    maps: dict = {}
    if not target_processes:
        return maps
    reg = mapping_config.registry()
    if reg is None:
        raise RuntimeError("mapping_config registry unavailable")
    clients = {client for client, _process in reg.sources}
    for client in clients:
        for m in mapping_config.mappings_for(client, target_processes):
            maps.setdefault(m.process, {})[m.field_key] = m.column
    return maps


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
    dropped — the `process.<client>.<name>.view` grant is the security boundary.
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


def _latest_of(resolved, source_metrics, catalog):
    """The single grainable date column a 'latest'-mode metric set pins to, or None.

    Shared by the interactive run and the session-less runner (scheduler, AI
    run_definition) so both aggregate the newest snapshot, not every snapshot.
    """
    if not resolved:
        return None
    modes = {(source_metrics.get(m["code"]) or {}).get("total_mode", "sum") for m in resolved}
    date_candidates = [f["field"] for f in catalog if f.get("grainable")]
    if modes == {"latest"} and len(date_candidates) == 1:
        return date_candidates[0]
    return None


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
        if anchored and len(anchored) != len(resolved or []):
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
        latest_of = _latest_of(resolved, source_metrics, catalog)
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
