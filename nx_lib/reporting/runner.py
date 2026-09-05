"""Session-independent report execution for the scheduled-report runner.

The Flask view path (nx_lib.views.reporting) resolves permissions and process
scope from the request session. The scheduler has no session, so this module runs
a saved definition *as a given owner* using that owner's permission set (loaded
from the DB by the runner). It reuses the same builders/executors as the view —
no duplicated query logic — and must run inside a Flask app context (the runner
pushes one) because the reused helpers log via current_app.

Returns (columns, rows) where columns is a list of {field, header} suitable for
nx_lib.reporting.export.
"""

from .catalog import fetch_docprocessing_catalog
from .query import build_table_query
from .schema import (
    ReportDefinitionError,
    validate_report_definition,
    validate_sql_definition,
)
from .semantic import resolve_metrics
from .sources import DEFAULT_ROW_LIMIT, MAX_ROW_LIMIT
from .table_query import build_generic_query, table_source_catalog
from .tokens import date_fields_from_catalog, resolve_definition_tokens

_SCOPE_PREFIX = "reporting.scope.process."


def _allowed_processes_from_perms(perms):
    """The owner's processes in either code shape (see process_helpers)."""
    from ..process_helpers import process_grants  # local: keeps this module import-light

    return sorted(process_grants(perms, _SCOPE_PREFIX))


def _normalize_columns(definition, resolved_metrics=None, source_metrics=None):
    """Export columns: the definition's dims plus any resolved metric codes
    (the aggregate query projects dims + metric codes, in that order). Metric
    columns are headered with the registry label, so an exported or emailed
    table reads "Documents imported", not "docs_imported"."""
    from ..views import reporting as rv

    cols = [
        {"field": c["field"], "header": c.get("header") or c["field"]}
        for c in definition.get("columns") or []
    ]
    return cols + rv.metric_result_columns(resolved_metrics, source_metrics or {})


def execute_definition(definition, owner_perms, owner_id, owner_username, locale):
    """Run a saved report `definition` as the owner. Returns (columns, rows).

    Raises PermissionError (owner lacks the source/SQL permission),
    ReportDefinitionError / SqlSandboxError / TableQueryError (bad definition),
    or RuntimeError (an SQL source is not configured).
    """
    # Imported lazily to avoid a heavy import at module load and any import cycle.
    from ..views import reporting as rv

    owner_perms = set(owner_perms or [])

    if definition.get("kind") == "sql":
        validate_sql_definition(definition, allowed_targets=set(rv._SQL_TARGETS))
        if "reporting.sql.run" not in owner_perms:
            raise PermissionError("reporting.sql.run")
        perm = rv._SQL_TARGET_PERMISSION.get(definition["target"])
        if perm and perm not in owner_perms:
            raise PermissionError(perm)
        columns, rows = rv._run_sql(
            definition["target"], definition["sql"], userid=owner_id, username=owner_username
        )
        return columns, rows

    source = rv._get_effective_source(definition.get("source"))
    if source is None or source.get("kind") != "curated":
        raise ReportDefinitionError("unknown or unsupported source")
    if source["permission"] not in owner_perms:
        raise PermissionError(source["permission"])

    provider = source.get("provider") or "docprocessing"
    if provider == "docprocessing":
        allowed = _allowed_processes_from_perms(owner_perms)
        catalog = fetch_docprocessing_catalog(allowed, str(locale))
        catalog_fields = {f["field"] for f in catalog}
        filterable = {f["field"] for f in catalog if f["filterable"]}
        sortable = {f["field"] for f in catalog if f["sortable"]}
        grainable = {f["field"] for f in catalog if f.get("grainable")}
        source_metrics = rv._metrics_for_source(source["id"])
        validate_report_definition(
            definition,
            catalog_fields,
            filterable,
            sortable,
            max_row_limit=MAX_ROW_LIMIT,
            metric_codes=set(source_metrics),
            grainable_fields=grainable,
            date_fields=date_fields_from_catalog(catalog),
        )
        try:
            definition = resolve_definition_tokens(definition)
        except ValueError as e:
            raise ReportDefinitionError(str(e)) from e
        resolved = (
            resolve_metrics(definition.get("metrics"), source_metrics, catalog_fields)
            if definition.get("metrics")
            else None
        )
        # Same scope semantics as the interactive run (rv._effective_scope):
        # scope.clients UNION scope.processes, narrowed to what the owner is
        # granted. An empty scope means "all allowed"; a *non-empty* scope
        # that matches nothing must resolve to an empty selection, never
        # widen back to every allowed process -- that would silently email
        # data the schedule was never scoped to. build_table_query raises
        # QueryBuildError("no processes in scope") on an empty selection, so
        # the failure surfaces as a failed/errored run, not a silent leak.
        scope = rv._effective_scope(definition, allowed)
        configs = rv._load_process_configs(scope)
        col_maps = rv._load_field_col_maps(scope)
        sql, params = build_table_query(
            definition,
            configs,
            col_maps,
            row_cap=definition.get("rowLimit", DEFAULT_ROW_LIMIT),
            resolved_metrics=resolved,
        )
        return _normalize_columns(definition, resolved, source_metrics), rv._execute(
            rv.engine_statistics_db, sql, params
        )

    if provider == "table":
        catalog = table_source_catalog(source.get("columns"))
        catalog_fields = {f["field"] for f in catalog}
        filterable = {f["field"] for f in catalog if f["filterable"]}
        sortable = {f["field"] for f in catalog if f["sortable"]}
        source_metrics = rv._metrics_for_source(source["id"])
        validate_report_definition(
            definition,
            catalog_fields,
            filterable,
            sortable,
            max_row_limit=MAX_ROW_LIMIT,
            metric_codes=set(source_metrics),
            grainable_fields={f["field"] for f in catalog if f.get("grainable")},
            date_fields=date_fields_from_catalog(catalog),
        )
        try:
            definition = resolve_definition_tokens(definition)
        except ValueError as e:
            raise ReportDefinitionError(str(e)) from e
        resolved = (
            resolve_metrics(definition.get("metrics"), source_metrics, catalog_fields)
            if definition.get("metrics")
            else None
        )
        sql, params = build_generic_query(
            definition,
            source.get("baseObject"),
            catalog,
            row_cap=definition.get("rowLimit", DEFAULT_ROW_LIMIT),
            resolved_metrics=resolved,
        )
        engine = rv._CURATED_ENGINES.get(source.get("engine"))
        if engine is None:
            raise ReportDefinitionError("source engine is not configured")
        return _normalize_columns(definition, resolved, source_metrics), rv._execute(
            engine, sql, params
        )

    raise ReportDefinitionError("unsupported source provider")
