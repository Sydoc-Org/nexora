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
  GET/POST/DELETE /api/reporting/reports/<id>/annotations[/<aid>]  owner/view: annotations

Split into a package (beautify-phase-2a, Tasks 1-3): the shared run/registry
core (SQL-target constants, source/metric registry, run pipeline, auth/audit)
lives in ``_shared.py``; every other feature cluster is its own submodule --
``ai.py`` (``/api/reporting/ai/*``), ``pages.py`` (guide + builder pages),
``run.py`` (sources listing + curated run + SQL sandbox), ``export.py``,
``reports.py`` (CRUD + shares + share-target typeahead), ``schedules.py``,
``admin_registry.py`` (sources/metrics admin), ``health.py`` (source health +
schema), ``catalog.py`` (field-values + metrics API). This module is now just
imports, the re-export list below, and ``register_routes``'s fan-out.

Every name any submodule defines is re-exported here under its original
import path (``nx_lib.views.reporting.<name>``), so nothing changes for
callers, tests, or ``nx_lib/reporting/runner.py`` (which reads several
attributes off this module at runtime) -- some submodules also import a
sibling's helper directly (e.g. ``ai.py`` imports ``_accessible_sql_targets``
from ``run.py``), which is why a few names are imported here purely for
re-export rather than any use in this module's own code.
"""

from ...db import engine_statistics_db
from . import (
    admin_registry,
    ai,
    annotations,
    catalog,
    export,
    health,
    pages,
    reports,
    run,
    schedules,
)
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
from .catalog import _accessible_curated_sources, _labeled_field_values
from .pages import _GUIDE_MD, _guide_render
from .reports import _preview_kind, _preview_summary
from .run import (
    _accessible_sql_targets,
    _forecast_for,
    _resolved_dates_meta,
    _rows_json_safe,
    _sandbox_error_message,
)

# Names imported above purely for re-export (nx_lib.views.reporting.<name> must
# keep resolving for callers/tests/nx_lib/reporting/runner.py) rather than used
# in this module's own code. The AI cluster (ai.py, Task 1) and the shared
# run/registry core (_shared.py, Task 2) both live behind this re-export list.
__all__ = [
    "_accessible_curated_sources",
    "_accessible_metrics",
    "_accessible_sql_targets",
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
    "engine_statistics_db",
    "_extract_agent_artifacts",
    "_forecast_for",
    "_get_effective_source",
    "_GUIDE_MD",
    "_guide_render",
    "_has_acked",
    "_json_safe",
    "_labeled_field_values",
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
    "_resolved_dates_meta",
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


def register_routes(app):
    pages.register_routes(app)
    admin_registry.register_routes(app)
    catalog.register_routes(app)
    run.register_routes(app)
    ai.register_routes(app)
    export.register_routes(app)
    reports.register_routes(app)
    schedules.register_routes(app)
    annotations.register_routes(app)
    health.register_routes(app)
