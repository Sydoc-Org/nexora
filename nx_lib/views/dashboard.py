"""Dashboard pages, KPIs, time-series charts, layout persistence and
the dashboard widget engine."""

import hashlib
import json
from datetime import date, datetime, timedelta

from flask import (
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_babel import gettext as _

from ..config import DB_STATISTICS
from ..db import engine_ms02_stats_pg, engine_nexora_db, engine_statistics_db
from ..extensions import cache, limiter
from ..i18n import get_locale
from ..octo import get_extensions_urls_fields, get_workitemdata_param
from ..process_helpers import (
    get_activity_instances_to_ignore,
)
from ..security import page_visibility, require_permission
from ..workitem_sources import (
    get_domain_for_workitem,
    recent_activity_rows,
    total_backlog_count,
)


def make_cache_key(*args, **kwargs):
    return f"{request.path}_{session.get('userid')}_{session.get('process_name_dashboard', 'all')}"


def _split_stat_configs(configs):
    """Partition Statconfig rows by serving client. Returns (default_rows, ms02_rows).
    Rows with a blank/missing ClientCode count as 'default' (back-compat with
    pre-0024 data)."""
    default_rows = []
    ms02_rows = []
    for r in configs:
        code = getattr(r, "ClientCode", None) or "default"
        if code == "ms02":
            ms02_rows.append(r)
        else:
            default_rows.append(r)
    return default_rows, ms02_rows


def _ms02_source(ms02_rows):
    """Resolve the single MS02 stats source from its Statconfig row(s).

    Returns (table, export_expr, import_expr) or None. MS02 rows all point at the
    same table (no per-process split), so we dedupe to the first row. TableName is
    used verbatim (already schema-qualified, e.g. public."DossierStatistik"); the
    column names are admin-controlled Statconfig values, quoted as Postgres
    identifiers because they are PascalCase. The old hardcoded
    'public.batchtracking'/'datuminexport' literals never existed in the MS02 DB."""
    if not ms02_rows:
        return None
    r = ms02_rows[0]

    def q(col):
        return '"' + str(col).replace('"', '""') + '"'

    return r.TableName, q(r.ExportColumn), q(r.ImportColumn)


def _ms02_stat_rows(sql):
    """Run a read-only query on the MS02 stats engine; return rows, or [] if the
    engine is unconfigured/unreachable or the query errors. Centralises the
    connection handling + error swallowing for the dashboard's MS02 branches: a
    failure here must never break the default-client numbers, so it logs and
    yields no rows. MS02 Statconfig conditions (additionalCondition) are
    Postgres-syntax and currently NULL, so they are not applied here.
    # ponytail: no per-call additionalCondition; add when an MS02 row needs one."""
    if engine_ms02_stats_pg is None:
        return []
    try:
        mconn = engine_ms02_stats_pg.raw_connection()
        try:
            mcur = mconn.cursor()
            mcur.execute(sql)
            return mcur.fetchall()
        finally:
            mconn.close()
    except Exception as e:
        current_app.logger.error(f"ms02 dashboard stats query failed: {e}")
        return []


def _default_stat_rows(sql):
    """Run a read-only query on the default StatisticsDB engine; return rows,
    or [] if the server is unreachable or the query errors (e.g. a stale
    Statconfig row pointing at a dropped table). Mirror of _ms02_stat_rows for
    the T-SQL leg: a default-leg failure must never blank the MS02 numbers —
    log and yield no rows so each leg degrades independently."""
    try:
        conn = engine_statistics_db.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql)
            return cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        current_app.logger.error(f"default dashboard stats query failed: {e}")
        return []


DASHBOARD_LAYOUT_SCHEMA_VERSION = 1
DASHBOARD_DATE_PRESETS = {"today", "yesterday", "last_7d", "last_30d", "this_month", "custom"}
DASHBOARD_WIDGET_TYPES = {"kpi", "timeseries", "categorical"}
DASHBOARD_TIMESERIES_BUCKETS = {"hour", "day", "week", "month"}
DASHBOARD_CHART_TYPES = {
    "timeseries": {"line", "area", "bar"},
    "categorical": {"bar", "hbar", "pie", "doughnut"},
}
DASHBOARD_METRIC_KINDS = {"count", "sum", "avg", "min", "max", "proc_time_avg"}


class DashboardLayoutError(ValueError):
    """Raised by validate_dashboard_layout when the JSON shape is bad."""

    pass


def dashboard_default_layout():
    """Hard-coded starter layout used when a user has no saved row.
    Mirrors the legacy fixed dashboard so first-time users get continuity."""
    today = datetime.now().date()
    fourteen_days_ago = today - timedelta(days=13)
    return {
        "schemaVersion": DASHBOARD_LAYOUT_SCHEMA_VERSION,
        "globalFilters": {
            "process": "all",
            "datePreset": "today",
            "dateFrom": None,
            "dateTo": None,
            "docFilters": [],
        },
        "grid": [
            {
                "id": "wid_starter_imported",
                "x": 0,
                "y": 0,
                "w": 3,
                "h": 2,
                "type": "kpi",
                "title": _("Imported today"),
                "config": {"metric": {"kind": "count"}},
                "ignoreGlobalFilters": False,
                "filterOverrides": None,
                "compare": {"enabled": False, "shift": "previous_period"},
            },
            {
                "id": "wid_starter_processed",
                "x": 3,
                "y": 0,
                "w": 3,
                "h": 2,
                "type": "kpi",
                "title": _("Processed today"),
                "config": {"metric": {"kind": "count"}},
                "ignoreGlobalFilters": False,
                "filterOverrides": {"status": "Done"},
                "compare": {"enabled": False, "shift": "previous_period"},
            },
            {
                "id": "wid_starter_backlog",
                "x": 6,
                "y": 0,
                "w": 3,
                "h": 2,
                "type": "kpi",
                "title": _("Current backlog"),
                "config": {"metric": {"kind": "count"}},
                "ignoreGlobalFilters": False,
                "filterOverrides": {"status": "Ready", "datePreset": None},
                "compare": {"enabled": False, "shift": "previous_period"},
            },
            {
                "id": "wid_starter_avgtime",
                "x": 9,
                "y": 0,
                "w": 3,
                "h": 2,
                "type": "kpi",
                "title": _("Avg processing time"),
                "config": {"metric": {"kind": "proc_time_avg"}},
                "ignoreGlobalFilters": False,
                "filterOverrides": None,
                "compare": {"enabled": False, "shift": "previous_period"},
            },
            {
                "id": "wid_starter_overtime",
                "x": 0,
                "y": 2,
                "w": 8,
                "h": 4,
                "type": "timeseries",
                "title": _("Documents Processed Over Time"),
                "config": {
                    "chartType": "line",
                    "bucket": "day",
                    "metric": {"kind": "count"},
                    "groupBy": None,
                },
                "ignoreGlobalFilters": False,
                "filterOverrides": {
                    "datePreset": "custom",
                    "dateFrom": fourteen_days_ago.isoformat(),
                    "dateTo": today.isoformat(),
                },
                "compare": {"enabled": False, "shift": "previous_period"},
            },
            {
                "id": "wid_starter_topdoctypes",
                "x": 8,
                "y": 2,
                "w": 4,
                "h": 4,
                "type": "categorical",
                "title": _("Top doctypes today"),
                "config": {
                    "chartType": "bar",
                    "dimension": "doctype",
                    "metric": {"kind": "count"},
                    "topN": 5,
                    "sort": "desc",
                },
                "ignoreGlobalFilters": False,
                "filterOverrides": None,
                "compare": {"enabled": False, "shift": "previous_period"},
            },
        ],
    }


def validate_dashboard_layout(layout, allowed_processes, valid_field_keys, aggregable_field_keys):
    """Validate a layout dict against the v1 schema. Raises DashboardLayoutError."""
    if not isinstance(layout, dict):
        raise DashboardLayoutError("layout must be an object")
    if layout.get("schemaVersion") != DASHBOARD_LAYOUT_SCHEMA_VERSION:
        raise DashboardLayoutError(f"schemaVersion must be {DASHBOARD_LAYOUT_SCHEMA_VERSION}")

    gf = layout.get("globalFilters") or {}
    if not isinstance(gf, dict):
        raise DashboardLayoutError("globalFilters must be an object")
    process = gf.get("process", "all")
    if process != "all" and process not in allowed_processes:
        raise DashboardLayoutError(f"globalFilters.process '{process}' not allowed")
    if gf.get("datePreset") not in DASHBOARD_DATE_PRESETS:
        raise DashboardLayoutError("globalFilters.datePreset invalid")
    for f in gf.get("docFilters") or []:
        if not isinstance(f, dict) or "field" not in f or "value" not in f:
            raise DashboardLayoutError("docFilters items must be {field, value}")
        if f["field"] not in valid_field_keys:
            raise DashboardLayoutError(f"docFilter field '{f['field']}' unknown")

    grid = layout.get("grid")
    if not isinstance(grid, list):
        raise DashboardLayoutError("grid must be a list")

    seen_ids = set()
    for w in grid:
        wid = w.get("id")
        if not wid or wid in seen_ids:
            raise DashboardLayoutError(f"widget id missing or duplicate: {wid!r}")
        seen_ids.add(wid)
        if w.get("type") not in DASHBOARD_WIDGET_TYPES:
            raise DashboardLayoutError(f"widget {wid}: unknown type {w.get('type')!r}")
        for k in ("x", "y", "w", "h"):
            v = w.get(k)
            if not isinstance(v, int) or v < 0 or v > 12:
                raise DashboardLayoutError(f"widget {wid}: {k} must be int in [0,12]")

        cfg = w.get("config") or {}
        if w["type"] == "kpi":
            metric = cfg.get("metric") or {}
            kind = metric.get("kind")
            if kind not in DASHBOARD_METRIC_KINDS:
                raise DashboardLayoutError(f"widget {wid}: metric.kind invalid")
            if kind in {"sum", "avg", "min", "max"} and (
                metric.get("field") not in aggregable_field_keys
            ):
                raise DashboardLayoutError(
                    f"widget {wid}: metric.field must be an aggregable numeric field"
                )
        elif w["type"] == "timeseries":
            if cfg.get("chartType") not in DASHBOARD_CHART_TYPES["timeseries"]:
                raise DashboardLayoutError(f"widget {wid}: chartType invalid")
            if cfg.get("bucket") not in DASHBOARD_TIMESERIES_BUCKETS:
                raise DashboardLayoutError(f"widget {wid}: bucket invalid")
            metric = cfg.get("metric") or {}
            if metric.get("kind") not in DASHBOARD_METRIC_KINDS:
                raise DashboardLayoutError(f"widget {wid}: metric.kind invalid")
            if (
                metric.get("kind") in {"sum", "avg", "min", "max"}
                and metric.get("field") not in aggregable_field_keys
            ):
                raise DashboardLayoutError(f"widget {wid}: metric.field must be aggregable")
            if cfg.get("groupBy") is not None and cfg["groupBy"] not in valid_field_keys:
                raise DashboardLayoutError(f"widget {wid}: groupBy field unknown")
        elif w["type"] == "categorical":
            if cfg.get("chartType") not in DASHBOARD_CHART_TYPES["categorical"]:
                raise DashboardLayoutError(f"widget {wid}: chartType invalid")
            if cfg.get("dimension") not in valid_field_keys:
                raise DashboardLayoutError(f"widget {wid}: dimension unknown")
            metric = cfg.get("metric") or {}
            if metric.get("kind") not in DASHBOARD_METRIC_KINDS:
                raise DashboardLayoutError(f"widget {wid}: metric.kind invalid")
            if (
                metric.get("kind") in {"sum", "avg", "min", "max"}
                and metric.get("field") not in aggregable_field_keys
            ):
                raise DashboardLayoutError(f"widget {wid}: metric.field must be aggregable")
            topn = cfg.get("topN", 10)
            if topn != "all" and (not isinstance(topn, int) or topn < 1 or topn > 100):
                raise DashboardLayoutError(f"widget {wid}: topN invalid")
            if cfg.get("sort") not in {"desc", "asc", "alpha"}:
                raise DashboardLayoutError(f"widget {wid}: sort invalid")

        compare = w.get("compare") or {}
        if compare.get("enabled") and compare.get("shift") != "previous_period":
            raise DashboardLayoutError(
                f"widget {wid}: compare.shift only 'previous_period' supported in v1"
            )


# ----------------------------- legacy KPI endpoints (still used by the templates) ----- #


@cache.cached(timeout=300, key_prefix=make_cache_key)
def dashboard_processed_over_time():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    perms = session.get("permissions", [])
    prefix = "dashboard.filter.process."
    allowed_processes = sorted(
        {
            (perm.split(".")[-2] + "." + perm.split(".")[-1])
            for perm in perms
            if perm.startswith(prefix)
        }
    )
    process_name = session.get("process_name_dashboard", "all")

    target_processes = allowed_processes if process_name == "all" else [process_name]

    if not target_processes:
        return jsonify({"labels": [], "data": []})

    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        placeholders = ",".join(["?"] * len(target_processes))
        config_query = f"""
            SELECT ProcessName, TableName, ExportColumn, ImportColumn, additionalCondition, ClientCode
            FROM Statconfig
            WHERE ProcessName IN ({placeholders})
        """
        cursor.execute(config_query, target_processes)
        configs = cursor.fetchall()
        cursor.close()
        conn.close()
        conn = None

        if not configs:
            return jsonify({"labels": [], "data": []})

        default_configs, ms02_rows = _split_stat_configs(configs)

        sub_queries = []
        for row in default_configs:
            convert = "convert" in str(row.ExportColumn).lower()
            date_col = f"CAST({row.ExportColumn} AS DATE)" if not convert else row.ExportColumn
            condition = f" {row.additionalCondition}" if row.additionalCondition else ""
            sub_queries.append(f"""
                SELECT {date_col} as d, COUNT(*) as c
                FROM [{DB_STATISTICS}].{row.TableName}
                WHERE {row.ExportColumn} >= DATEADD(day, -14, GETDATE()) {condition}
                GROUP BY {date_col}
            """)

        counts = {}
        if sub_queries:
            full_query = f"""
                SELECT d, SUM(c) as total_count
                FROM ({' UNION ALL '.join(sub_queries)}) as combined_data
                GROUP BY d
                ORDER BY d
            """
            for row in _default_stat_rows(full_query):
                # The legacy `DRIVER={SQL Server}` pyodbc driver returns SQL Server
                # DATE columns as `str`, not `datetime.date` (confirmed on PROD);
                # normalize here so this leg's keys match the MS02/zero-fill legs'
                # native `date` keys before they share the `counts` dict.
                d = row.d if isinstance(row.d, date) else date.fromisoformat(str(row.d)[:10])
                counts[d] = counts.get(d, 0) + row.total_count

        ms02_src = _ms02_source(ms02_rows)
        if ms02_src:
            tbl, exp, _imp = ms02_src
            for d, c in _ms02_stat_rows(
                f"SELECT {exp}::date AS d, COUNT(*) AS c "
                f"FROM {tbl} "
                f"WHERE {exp} >= CURRENT_DATE - 14 "
                f"GROUP BY {exp}::date"
            ):
                counts[d] = counts.get(d, 0) + c

        # Zero-fill the trailing 14-day window so a sparse client (e.g. a freshly
        # onboarded MS02 with only today's rows) renders a continuous trend line
        # instead of a single, invisible point — the chart was "showing only the date".
        today = datetime.now().date()
        for i in range(15):
            counts.setdefault(today - timedelta(days=i), 0)

        sorted_dates = sorted(counts.keys())
        return jsonify(
            {
                "labels": [d.isoformat() for d in sorted_dates],
                "data": [counts[d] for d in sorted_dates],
            }
        )

    except Exception as e:
        current_app.logger.error(f"Failed to fetch processed_over_time report: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@cache.cached(
    timeout=60,
    key_prefix=lambda: f"kpi_stats_{session.get('userid')}_{session.get('process_name_dashboard','all')}",
)
def dashboard_kpi_stats():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    prefix = "dashboard.filter.process."
    perms = session.get("permissions", [])
    allowed_processes = sorted(
        {
            (perm.split(".")[-2] + "." + perm.split(".")[-1])
            for perm in perms
            if perm.startswith(prefix)
        }
    )
    process_name = session.get("process_name_dashboard", "all")

    target_processes = allowed_processes if process_name == "all" else [process_name]

    if not target_processes:
        return jsonify(
            {"processed_today": 0, "processed_week": 0, "current_backlog": 0, "imported_today": 0}
        )

    processed_today = 0
    imported_today = 0
    current_backlog = 0

    conn_nex = None
    cursor_nex = None

    try:
        conn_nex = engine_nexora_db.raw_connection()
        cursor_nex = conn_nex.cursor()
        placeholders = ",".join(["?"] * len(target_processes))

        cursor_nex.execute(
            f"SELECT ProcessName, TableName, ExportColumn, ImportColumn, additionalCondition, ClientCode FROM Statconfig WHERE ProcessName IN ({placeholders})",
            target_processes,
        )
        configs = cursor_nex.fetchall()

        default_configs, ms02_rows = _split_stat_configs(configs)

        if default_configs:
            sub_queries = []
            for row in default_configs:
                col_export = row.ExportColumn
                col_import = row.ImportColumn
                condition = f" {row.additionalCondition}" if row.additionalCondition else ""
                sub_queries.append(f"""
                    SELECT
                        SUM(CASE WHEN CAST({col_export} AS DATE) = CAST(GETDATE() AS DATE) THEN 1 ELSE 0 END) as TodayCountExport,
                        SUM(CASE WHEN CAST({col_import} AS DATE) = CAST(GETDATE() AS DATE) THEN 1 ELSE 0 END) as TodayCountExportImport
                    FROM [{DB_STATISTICS}].{row.TableName}
                    WHERE CAST({col_import} as date) = cast(GETDATE() as date)
                    {condition}
                """)

            if sub_queries:
                full_stat_query = f"""
                    SELECT SUM(TodayCountExport), SUM(TodayCountExportImport)
                    FROM ({' UNION ALL '.join(sub_queries)}) as combined
                """
                srows = _default_stat_rows(full_stat_query)
                if srows:
                    processed_today += srows[0][0] or 0
                    imported_today += srows[0][1] or 0

        ms02_src = _ms02_source(ms02_rows)
        if ms02_src:
            tbl, exp, imp = ms02_src
            mrows = _ms02_stat_rows(
                f"SELECT "
                f"COUNT(*) FILTER (WHERE {exp}::date = CURRENT_DATE), "
                f"COUNT(*) FILTER (WHERE {imp}::date = CURRENT_DATE) "
                f"FROM {tbl}"
            )
            if mrows:
                processed_today += mrows[0][0] or 0
                imported_today += mrows[0][1] or 0

        if target_processes:
            proc_params = sorted({p.split(".")[-1] for p in target_processes if "." in p})
            cli_params = sorted({p.split(".")[0] for p in target_processes if "." in p})
            current_backlog += total_backlog_count(proc_params, cli_params)

        return jsonify(
            {
                "processed_today": processed_today,
                "imported_today": imported_today,
                "current_backlog": current_backlog,
            }
        )

    except Exception as e:
        current_app.logger.error(f"Failed to fetch kpi_stats report: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor_nex:
            cursor_nex.close()
        if conn_nex:
            conn_nex.close()


@cache.cached(
    timeout=120,
    key_prefix=lambda: f"hourly_stats_{session.get('userid')}_{session.get('process_name_dashboard','all')}",
)
def dashboard_hourly_stats():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    prefix = "dashboard.filter.process."
    perms = session.get("permissions", [])
    allowed_processes = sorted(
        {
            (perm.split(".")[-2] + "." + perm.split(".")[-1])
            for perm in perms
            if perm.startswith(prefix)
        }
    )
    process_name = session.get("process_name_dashboard", "all")
    target_processes = allowed_processes if process_name == "all" else [process_name]

    if not target_processes:
        return jsonify({"labels": [f"{h:02d}:00" for h in range(24)], "data": [0] * 24})

    conn_nex = None
    cursor_nex = None
    try:
        conn_nex = engine_nexora_db.raw_connection()
        cursor_nex = conn_nex.cursor()
        placeholders = ",".join(["?"] * len(target_processes))
        cursor_nex.execute(
            f"SELECT ProcessName, TableName, ExportColumn, ImportColumn, additionalCondition, ClientCode FROM Statconfig WHERE ProcessName IN ({placeholders})",
            target_processes,
        )
        configs = cursor_nex.fetchall()

        if not configs:
            return jsonify({"labels": [f"{h:02d}:00" for h in range(24)], "data": [0] * 24})

        default_configs, ms02_rows = _split_stat_configs(configs)

        sub_queries = []
        for row in default_configs:
            condition = f" {row.additionalCondition}" if row.additionalCondition else ""
            sub_queries.append(f"""
                SELECT DATEPART(hour, {row.ExportColumn}) as h, COUNT(*) as c
                FROM [{DB_STATISTICS}].{row.TableName}
                WHERE CAST({row.ExportColumn} AS DATE) = CAST(GETDATE() AS DATE) {condition}
                GROUP BY DATEPART(hour, {row.ExportColumn})
            """)

        hourly = {}

        if sub_queries:
            full_query = f"""
                SELECT h, SUM(c) as total
                FROM ({' UNION ALL '.join(sub_queries)}) as combined
                GROUP BY h
                ORDER BY h
            """
            for row in _default_stat_rows(full_query):
                hourly[row.h] = hourly.get(row.h, 0) + row.total

        ms02_src = _ms02_source(ms02_rows)
        if ms02_src:
            tbl, exp, _imp = ms02_src
            for h, c in _ms02_stat_rows(
                f"SELECT EXTRACT(HOUR FROM {exp})::int AS h, COUNT(*) AS c "
                f"FROM {tbl} "
                f"WHERE {exp}::date = CURRENT_DATE "
                f"GROUP BY EXTRACT(HOUR FROM {exp})"
            ):
                hourly[int(h)] = hourly.get(int(h), 0) + c

        return jsonify(
            {
                "labels": [f"{h:02d}:00" for h in range(24)],
                "data": [hourly.get(h, 0) for h in range(24)],
            }
        )

    except Exception as e:
        current_app.logger.error(f"Failed to fetch hourly_stats: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor_nex:
            cursor_nex.close()
        if conn_nex:
            conn_nex.close()


@cache.cached(
    timeout=300,
    key_prefix=lambda: f"avg_proc_time_{session.get('userid')}_{session.get('process_name_dashboard','all')}",
)
def dashboard_avg_processing_time():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    prefix = "dashboard.filter.process."
    perms = session.get("permissions", [])
    allowed_processes = sorted(
        {
            (perm.split(".")[-2] + "." + perm.split(".")[-1])
            for perm in perms
            if perm.startswith(prefix)
        }
    )
    process_name = session.get("process_name_dashboard", "all")
    target_processes = allowed_processes if process_name == "all" else [process_name]

    if not target_processes:
        return jsonify({"avg_minutes": None, "avg_display": "—"})

    conn_nex = None
    cursor_nex = None
    try:
        conn_nex = engine_nexora_db.raw_connection()
        cursor_nex = conn_nex.cursor()
        placeholders = ",".join(["?"] * len(target_processes))
        cursor_nex.execute(
            f"SELECT ProcessName, TableName, ExportColumn, ImportColumn, additionalCondition, ClientCode FROM Statconfig WHERE ProcessName IN ({placeholders})",
            target_processes,
        )
        configs = cursor_nex.fetchall()

        default_configs, ms02_rows = _split_stat_configs(configs)

        sub_queries = []
        for row in default_configs:
            if not row.ImportColumn:
                continue
            condition = f" {row.additionalCondition}" if row.additionalCondition else ""
            sub_queries.append(f"""
                SELECT AVG(CAST(DATEDIFF(second, {row.ImportColumn}, {row.ExportColumn}) AS FLOAT)) as avg_sec
                FROM [{DB_STATISTICS}].{row.TableName}
                WHERE CAST({row.ExportColumn} AS DATE) = CAST(GETDATE() AS DATE)
                AND {row.ImportColumn} IS NOT NULL
                AND {row.ExportColumn} > {row.ImportColumn}
                {condition}
            """)

        avg_values = []

        if sub_queries:
            full_query = f"""
                SELECT AVG(avg_sec) as overall_avg
                FROM ({' UNION ALL '.join(sub_queries)}) as combined
                WHERE avg_sec IS NOT NULL
            """
            srows = _default_stat_rows(full_query)
            if srows and srows[0][0] is not None:
                avg_values.append(srows[0][0])

        # MS02 contributes one client-level average (export - import seconds),
        # weighted equally with the default bucket — same mean-of-means the
        # default path already applies across its processes.
        ms02_src = _ms02_source(ms02_rows)
        if ms02_src:
            tbl, exp, imp = ms02_src
            mrows = _ms02_stat_rows(
                f"SELECT AVG(EXTRACT(EPOCH FROM ({exp} - {imp}))) "
                f"FROM {tbl} "
                f"WHERE {exp}::date = CURRENT_DATE "
                f"AND {imp} IS NOT NULL AND {exp} > {imp}"
            )
            if mrows and mrows[0][0] is not None:
                avg_values.append(float(mrows[0][0]))

        if not avg_values:
            return jsonify({"avg_minutes": None, "avg_display": "—"})

        avg_sec = sum(avg_values) / len(avg_values)

        avg_minutes = avg_sec / 60
        if avg_minutes < 1:
            display = f"{int(avg_sec)}s"
        elif avg_minutes < 60:
            display = f"{avg_minutes:.0f}min"
        else:
            display = f"{avg_minutes / 60:.1f}h"

        return jsonify({"avg_minutes": round(avg_minutes, 1), "avg_display": display})

    except Exception as e:
        current_app.logger.error(f"Failed to fetch avg_processing_time: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor_nex:
            cursor_nex.close()
        if conn_nex:
            conn_nex.close()


# ----------------------------- dashboard page + filter ----------------------------- #


@require_permission("dashboard.view")
def dashboard():
    try:
        if "username" not in session:
            return redirect(url_for("login"))

        logged_in_user = session.get("username", "Unknown")
        userid = session.get("userid", "Unknown")
        perms = session.get("permissions", [])
        fullname = session.get("fullname")

        prefix = "dashboard.filter.process."
        allowed_processes = sorted(
            {
                (perm.split(".")[-2] + "." + perm.split(".")[-1])
                for perm in perms
                if perm.startswith(prefix)
            }
        )

        process_name = request.args.get("prcfD", "all")
        if process_name != "all" and process_name not in allowed_processes:
            process_name = "all"

        session["process_name_dashboard"] = process_name

        return render_template(
            "dashboard.html",
            logged_in_user=logged_in_user,
            userid=userid,
            process_name=process_name,
            allowed_processes=allowed_processes,
            pageV=page_visibility(),
            fullname=fullname,
        )
    except Exception:
        return render_template("500.html")


@require_permission("dashboard.view")
def dashboard_set_filter():
    if "username" not in session:
        return jsonify({"error": "Not authorized"}), 401
    perms = session.get("permissions", [])
    prefix = "dashboard.filter.process."
    allowed_processes = sorted(
        {
            (perm.split(".")[-2] + "." + perm.split(".")[-1])
            for perm in perms
            if perm.startswith(prefix)
        }
    )
    process_name = request.json.get("process_name", "all")
    if process_name != "all" and process_name not in allowed_processes:
        process_name = "all"
    session["process_name_dashboard"] = process_name
    return jsonify({"ok": True, "process_name": process_name})


# ----------------------------- field metadata / layout ----------------------------- #


@require_permission("dashboard.view")
@cache.cached(
    timeout=3600, key_prefix=lambda: f"dash_fieldmeta_{session.get('userid')}_{get_locale()!s}"
)
def dashboard_field_metadata():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    perms = session.get("permissions", [])
    prefix = "dashboard.filter.process."
    allowed_processes = sorted(
        {(p.split(".")[-2] + "." + p.split(".")[-1]) for p in perms if p.startswith(prefix)}
    )

    current_lang = str(get_locale())
    lang_col = {"de": "GermanLabel", "fr": "FrenchLabel", "it": "ItalianLabel"}.get(
        current_lang, "EnglishLabel"
    )

    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()

        cur.execute("SELECT FieldKey, DataType, Aggregable, Sortable FROM FieldMetadata")
        meta_rows = cur.fetchall()
        meta_by_key = {
            r.FieldKey: {
                "field": r.FieldKey,
                "type": r.DataType,
                "aggregable": bool(r.Aggregable),
                "sortable": bool(r.Sortable),
            }
            for r in meta_rows
        }

        cur.execute(
            "SELECT FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel FROM Search_Field_Labels"
        )
        for r in cur.fetchall():
            if r.FieldKey in meta_by_key:
                meta_by_key[r.FieldKey]["label"] = getattr(r, lang_col) or r.EnglishLabel

        cur.execute("SELECT TOP 0 * FROM SearchConfig")
        cols = [c[0] for c in cur.description if c[0].startswith("col_")]
        select_cols = ", ".join(cols)
        cur.execute(f"SELECT ProcessName, {select_cols} FROM SearchConfig")
        availability = {}
        for row in cur.fetchall():
            if row.ProcessName not in allowed_processes:
                continue
            for i, col in enumerate(cols):
                if row[i + 1]:
                    fk = col[len("col_") :]
                    availability.setdefault(fk, []).append(row.ProcessName)

        for fk in ("processname", "status"):
            availability[fk] = allowed_processes[:]

        out = []
        for fk, meta in meta_by_key.items():
            if fk not in availability:
                continue
            entry = dict(meta)
            entry.setdefault("label", fk.replace("_", " ").title())
            entry["processes"] = sorted(availability[fk])
            out.append(entry)

        out.sort(key=lambda e: e["label"])
        return jsonify(out)

    except Exception as e:
        current_app.logger.error(f"/api/dashboard/field_metadata error: {e}")
        return jsonify({"error": _("Could not fetch field metadata")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("dashboard.view")
def dashboard_get_layout():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401
    userid = session.get("userid")
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        cur.execute("SELECT LayoutJSON FROM DashboardLayouts WHERE UserID = ?", (userid,))
        row = cur.fetchone()
        if row:
            return jsonify(json.loads(row.LayoutJSON))
        return jsonify(dashboard_default_layout())
    except Exception as e:
        current_app.logger.error(f"/api/dashboard/layout GET error: {e}")
        return jsonify({"error": _("Could not load layout")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("dashboard.view")
def dashboard_put_layout():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401
    userid = session.get("userid")
    perms = session.get("permissions", [])
    prefix = "dashboard.filter.process."
    allowed_processes = {
        (p.split(".")[-2] + "." + p.split(".")[-1]) for p in perms if p.startswith(prefix)
    }

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400

    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        cur.execute("SELECT FieldKey, Aggregable FROM FieldMetadata")
        rows = cur.fetchall()
        valid_fields = {r.FieldKey for r in rows}
        aggregable_fields = {r.FieldKey for r in rows if r.Aggregable}

        try:
            validate_dashboard_layout(payload, allowed_processes, valid_fields, aggregable_fields)
        except DashboardLayoutError as e:
            return jsonify({"error": str(e)}), 400

        layout_str = json.dumps(payload, ensure_ascii=False)

        cur.execute(
            """
            MERGE DashboardLayouts AS t
            USING (SELECT ? AS UserID, ? AS LayoutJSON) AS s
            ON t.UserID = s.UserID
            WHEN MATCHED THEN UPDATE SET LayoutJSON = s.LayoutJSON, UpdatedAt = SYSUTCDATETIME()
            WHEN NOT MATCHED THEN INSERT (UserID, LayoutJSON) VALUES (s.UserID, s.LayoutJSON);
        """,
            (userid, layout_str),
        )
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"/api/dashboard/layout PUT error: {e}")
        return jsonify({"error": _("Could not save layout")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("dashboard.view")
def dashboard_reset_layout():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401
    userid = session.get("userid")
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM DashboardLayouts WHERE UserID = ?", (userid,))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"/api/dashboard/layout/reset error: {e}")
        return jsonify({"error": _("Could not reset layout")}), 500
    finally:
        if conn:
            conn.close()


# ------------------------- dashboard query builder -------------------------- #


def _resolve_date_range(date_preset, date_from=None, date_to=None):
    """Returns (start_date, end_date) as datetime.date or (None, None) if no date filter applies.
    None means 'do not filter by date' (used by point-in-time KPIs like backlog)."""
    if date_preset is None:
        return (None, None)
    today = datetime.now().date()
    if date_preset == "today":
        return (today, today)
    if date_preset == "yesterday":
        y = today - timedelta(days=1)
        return (y, y)
    if date_preset == "last_7d":
        return (today - timedelta(days=6), today)
    if date_preset == "last_30d":
        return (today - timedelta(days=29), today)
    if date_preset == "this_month":
        return (today.replace(day=1), today)
    if date_preset == "custom":
        s = date.fromisoformat(date_from) if date_from else None
        e = date.fromisoformat(date_to) if date_to else None
        return (s, e)
    return (None, None)


def _effective_filters(widget, global_filters):
    base = {} if widget.get("ignoreGlobalFilters") else dict(global_filters or {})
    overrides = widget.get("filterOverrides") or {}
    base.update(overrides)
    return base


def _process_scope(filters, allowed_processes):
    proc = filters.get("process", "all") if isinstance(filters, dict) else "all"
    if proc == "all":
        return list(allowed_processes)
    return [proc] if proc in allowed_processes else []


_search_config_cache = {}  # ProcessName -> {field_key: actual_col_name}


def _resolve_aggregation_column(process_name, field_key):
    """Look up SearchConfig.col_<field> (which stores the *actual* data column name) for this process.
    Returns None if the process or field isn't mapped."""
    if process_name in _search_config_cache:
        return _search_config_cache[process_name].get(field_key)
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT TOP 0 * FROM SearchConfig")
        cols = [c[0] for c in cur.description if c[0].startswith("col_")]
        select_cols = ", ".join(cols)
        cur.execute(
            f"SELECT {select_cols} FROM SearchConfig WHERE ProcessName = ?", (process_name,)
        )
        row = cur.fetchone()
        if not row:
            _search_config_cache[process_name] = {}
            return None
        mapping = {}
        for i, col in enumerate(cols):
            val = row[i]
            if val:
                mapping[col[len("col_") :]] = val
        _search_config_cache[process_name] = mapping
        return mapping.get(field_key)
    finally:
        conn.close()


def _build_kpi_sql(widget, filters, configs):
    metric = widget["config"]["metric"]
    kind = metric["kind"]
    field = metric.get("field")
    start_date, end_date = _resolve_date_range(
        filters.get("datePreset"), filters.get("dateFrom"), filters.get("dateTo")
    )
    status = filters.get("status")

    if not configs:
        return "", []
    sub_qs = []
    params = []
    for row in configs:
        tbl = row.TableName
        export_col = row.ExportColumn
        import_col = row.ImportColumn
        cond = f" {row.additionalCondition}" if row.additionalCondition else ""

        if kind == "count":
            expr = "COUNT(*)"
        elif kind == "proc_time_avg":
            expr = f"AVG(CAST(DATEDIFF(SECOND, {import_col}, {export_col}) AS BIGINT))"
        elif kind in ("sum", "avg", "min", "max"):
            col_actual = _resolve_aggregation_column(row.ProcessName, field)
            if not col_actual:
                continue
            expr = f"{kind.upper()}(CAST({col_actual} AS DECIMAL(18,4)))"
        else:
            continue

        where = []
        if start_date is not None and status != "Ready":
            where.append(f"CAST({export_col} AS DATE) >= ?")
            params.append(start_date.isoformat())
        if end_date is not None and status != "Ready":
            where.append(f"CAST({export_col} AS DATE) <= ?")
            params.append(end_date.isoformat())
        for f in filters.get("docFilters") or []:
            col = _resolve_aggregation_column(row.ProcessName, f["field"])
            if not col:
                continue
            where.append(f"{col} = ?")
            params.append(f["value"])
        where_sql = (" WHERE " + " AND ".join(where) + cond) if where else (" WHERE 1=1" + cond)
        sub_qs.append(f"SELECT {expr} AS v FROM [{DB_STATISTICS}].{tbl}{where_sql}")
    if not sub_qs:
        return "", []
    outer_agg = {
        "count": "SUM",
        "sum": "SUM",
        "avg": "AVG",
        "min": "MIN",
        "max": "MAX",
        "proc_time_avg": "AVG",
    }[kind]
    full = f"SELECT {outer_agg}(v) FROM ({' UNION ALL '.join(sub_qs)}) t"
    return full, params


def _bucket_expr(col, bucket):
    if bucket == "hour":
        return f"DATEADD(hour, DATEPART(hour, {col}), CAST(CAST({col} AS DATE) AS DATETIME2))"
    if bucket == "day":
        return f"CAST({col} AS DATE)"
    if bucket == "week":
        return f"DATEADD(day, 1 - DATEPART(weekday, {col}), CAST({col} AS DATE))"
    if bucket == "month":
        return f"DATEFROMPARTS(YEAR({col}), MONTH({col}), 1)"
    raise ValueError(f"unknown bucket {bucket!r}")


def _metric_expr(metric, process_name):
    """Return a SQL fragment for the metric expression. Returns None if the field isn't exposed
    by this process — caller skips the subquery."""
    kind = metric["kind"]
    if kind == "count":
        return "COUNT(*)"
    if kind == "proc_time_avg":
        return None  # caller injects DATEDIFF directly because it needs both cols
    field = metric.get("field")
    col = _resolve_aggregation_column(process_name, field) if field else None
    if not col:
        return None
    return f"{kind.upper()}(CAST({col} AS DECIMAL(18,4)))"


def _doc_filter_clauses(filters, process_name, params_out):
    clauses = []
    for f in filters.get("docFilters") or []:
        col = _resolve_aggregation_column(process_name, f["field"])
        if not col:
            continue
        clauses.append(f"{col} = ?")
        params_out.append(f["value"])
    return clauses


def _build_timeseries_sql(widget, filters, configs):
    cfg = widget["config"]
    bucket = cfg["bucket"]
    metric = cfg["metric"]
    start_date, end_date = _resolve_date_range(
        filters.get("datePreset"), filters.get("dateFrom"), filters.get("dateTo")
    )

    if not configs:
        return "", []
    sub_qs = []
    params = []
    for row in configs:
        tbl = row.TableName
        export_col = row.ExportColumn
        import_col = row.ImportColumn
        cond = f" {row.additionalCondition}" if row.additionalCondition else ""
        bucket_sql = _bucket_expr(export_col, bucket)
        if metric["kind"] == "proc_time_avg":
            metric_sql = f"AVG(CAST(DATEDIFF(SECOND, {import_col}, {export_col}) AS BIGINT))"
        else:
            metric_sql = _metric_expr(metric, row.ProcessName)
            if metric_sql is None:
                continue
        where = []
        if start_date is not None:
            where.append(f"CAST({export_col} AS DATE) >= ?")
            params.append(start_date.isoformat())
        if end_date is not None:
            where.append(f"CAST({export_col} AS DATE) <= ?")
            params.append(end_date.isoformat())
        where += _doc_filter_clauses(filters, row.ProcessName, params)
        where_sql = (" WHERE " + " AND ".join(where) + cond) if where else (" WHERE 1=1" + cond)
        sub_qs.append(
            f"SELECT {bucket_sql} AS bucket, {metric_sql} AS v "
            f"FROM [{DB_STATISTICS}].{tbl}{where_sql} GROUP BY {bucket_sql}"
        )
    if not sub_qs:
        return "", []
    outer_agg = {
        "count": "SUM",
        "sum": "SUM",
        "avg": "AVG",
        "min": "MIN",
        "max": "MAX",
        "proc_time_avg": "AVG",
    }[metric["kind"]]
    full = (
        f"SELECT bucket, {outer_agg}(v) AS v "
        f"FROM ({' UNION ALL '.join(sub_qs)}) t "
        f"GROUP BY bucket ORDER BY bucket"
    )
    return full, params


def _build_categorical_sql(widget, filters, configs):
    cfg = widget["config"]
    dim = cfg["dimension"]
    metric = cfg["metric"]
    top_n = cfg.get("topN", 10)
    sort = cfg.get("sort", "desc")
    start_date, end_date = _resolve_date_range(
        filters.get("datePreset"), filters.get("dateFrom"), filters.get("dateTo")
    )

    if not configs:
        return "", []
    sub_qs = []
    params = []
    for row in configs:
        tbl = row.TableName
        export_col = row.ExportColumn
        cond = f" {row.additionalCondition}" if row.additionalCondition else ""

        if dim == "processname":
            dim_sql = "?"
            params.append(row.ProcessName)
        elif dim == "status":
            continue
        else:
            dim_col = _resolve_aggregation_column(row.ProcessName, dim)
            if not dim_col:
                continue
            dim_sql = dim_col

        if metric["kind"] == "proc_time_avg":
            metric_sql = f"AVG(CAST(DATEDIFF(SECOND, {row.ImportColumn}, {export_col}) AS BIGINT))"
        else:
            metric_sql = _metric_expr(metric, row.ProcessName)
            if metric_sql is None:
                continue

        where = []
        if start_date is not None:
            where.append(f"CAST({export_col} AS DATE) >= ?")
            params.append(start_date.isoformat())
        if end_date is not None:
            where.append(f"CAST({export_col} AS DATE) <= ?")
            params.append(end_date.isoformat())
        where += _doc_filter_clauses(filters, row.ProcessName, params)
        where_sql = (" WHERE " + " AND ".join(where) + cond) if where else (" WHERE 1=1" + cond)

        group_by = dim_sql if dim_sql != "?" else "1"
        sub_qs.append(
            f"SELECT {dim_sql} AS dim, {metric_sql} AS v "
            f"FROM [{DB_STATISTICS}].{tbl}{where_sql} GROUP BY {group_by}"
        )
    if not sub_qs:
        return "", []
    outer_agg = {
        "count": "SUM",
        "sum": "SUM",
        "avg": "AVG",
        "min": "MIN",
        "max": "MAX",
        "proc_time_avg": "AVG",
    }[metric["kind"]]
    order_sql = {"desc": "v DESC", "asc": "v ASC", "alpha": "dim ASC"}[sort]
    top_sql = "" if top_n == "all" else f"TOP {int(top_n)} "
    full = (
        f"SELECT {top_sql}dim, {outer_agg}(v) AS v "
        f"FROM ({' UNION ALL '.join(sub_qs)}) t "
        f"GROUP BY dim ORDER BY {order_sql}"
    )
    return full, params


def build_widget_query(widget, global_filters, allowed_processes):
    """Translate (widget, filters) -> a list of (engine, sql, params) tuples."""
    filters = _effective_filters(widget, global_filters)
    target_processes = _process_scope(filters, allowed_processes)
    if not target_processes:
        return []

    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        placeholders = ",".join(["?"] * len(target_processes))
        cur.execute(
            f"SELECT ProcessName, TableName, ExportColumn, ImportColumn, additionalCondition "
            f"FROM Statconfig WHERE ProcessName IN ({placeholders}) "
            f"AND ISNULL(ClientCode, 'default') <> 'ms02'",
            target_processes,
        )
        configs = cur.fetchall()
    finally:
        conn.close()
    if not configs:
        return []

    builder = {
        "kpi": _build_kpi_sql,
        "timeseries": _build_timeseries_sql,
        "categorical": _build_categorical_sql,
    }[widget["type"]]
    sql, params = builder(widget, filters, configs)
    return [(engine_statistics_db, sql, params)] if sql else []


def _run_widget_queries(widget, queries, label_override=None):
    """Run pre-built (engine, sql, params) tuples and merge into a result dict.
    Returns {value, unit?} for KPI, {labels, series} for chart widgets."""
    series_label = label_override or widget.get("title", "")

    if not queries:
        if widget["type"] == "kpi":
            return {
                "value": 0,
                "unit": "seconds"
                if widget["config"]["metric"]["kind"] == "proc_time_avg"
                else None,
                "warnings": ["no_data_in_scope"],
            }
        return {
            "labels": [],
            "series": [{"label": series_label, "data": []}],
            "warnings": ["no_data_in_scope"],
        }

    if widget["type"] == "kpi":
        kind = widget["config"]["metric"]["kind"]
        total_value = 0.0
        avg_values = []
        min_value = None
        max_value = None
        for engine, sql, params in queries:
            conn = engine.raw_connection()
            try:
                cur = conn.cursor()
                cur.execute(sql, params)
                row = cur.fetchone()
                v = row[0] if row else None
                if v is None:
                    continue
                v = float(v)
                if kind in ("count", "sum"):
                    total_value += v
                elif kind in ("avg", "proc_time_avg"):
                    avg_values.append(v)
                elif kind == "min":
                    min_value = v if min_value is None else min(min_value, v)
                elif kind == "max":
                    max_value = v if max_value is None else max(max_value, v)
            finally:
                conn.close()
        if kind in ("count", "sum"):
            value = total_value
        elif kind in ("avg", "proc_time_avg"):
            value = (sum(avg_values) / len(avg_values)) if avg_values else 0
        elif kind == "min":
            value = min_value if min_value is not None else 0
        elif kind == "max":
            value = max_value if max_value is not None else 0
        else:
            value = 0
        return {"value": value, "unit": "seconds" if kind == "proc_time_avg" else None}

    if widget["type"] == "timeseries":
        merged = {}
        for engine, sql, params in queries:
            conn = engine.raw_connection()
            try:
                cur = conn.cursor()
                cur.execute(sql, params)
                for r in cur.fetchall():
                    bucket = r[0]
                    v = float(r[1]) if r[1] is not None else 0.0
                    merged[bucket] = merged.get(bucket, 0.0) + v
            finally:
                conn.close()
        labels = sorted(merged.keys())
        return {
            "labels": [str(b) for b in labels],
            "series": [{"label": series_label, "data": [merged[b] for b in labels]}],
        }

    # categorical
    merged = {}
    for engine, sql, params in queries:
        conn = engine.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            for r in cur.fetchall():
                dim = r[0]
                v = float(r[1]) if r[1] is not None else 0.0
                merged[dim] = merged.get(dim, 0.0) + v
        finally:
            conn.close()
    sort = widget["config"].get("sort", "desc")
    top_n = widget["config"].get("topN", 10)
    items = list(merged.items())
    if sort == "desc":
        items.sort(key=lambda kv: kv[1], reverse=True)
    elif sort == "asc":
        items.sort(key=lambda kv: kv[1])
    else:
        items.sort(key=lambda kv: str(kv[0]))
    if top_n != "all":
        items = items[: int(top_n)]
    return {
        "labels": [str(k) for k, _v in items],
        "series": [{"label": series_label, "data": [v for _k, v in items]}],
    }


def _hash_widget_request(userid, widget, global_filters, allowed_processes):
    key_obj = {
        "u": userid,
        "w": widget,
        "gf": global_filters,
        "ap": sorted(allowed_processes),
    }
    return hashlib.sha256(json.dumps(key_obj, sort_keys=True, default=str).encode()).hexdigest()


@require_permission("dashboard.view")
@limiter.limit("120 per minute")
def dashboard_widget_data():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401
    userid = session.get("userid")
    perms = session.get("permissions", [])
    prefix = "dashboard.filter.process."
    allowed_processes = sorted(
        {(p.split(".")[-2] + "." + p.split(".")[-1]) for p in perms if p.startswith(prefix)}
    )

    payload = request.get_json(silent=True) or {}
    widget = payload.get("widget")
    global_filters = payload.get("globalFilters") or {}
    if not isinstance(widget, dict) or widget.get("type") not in DASHBOARD_WIDGET_TYPES:
        return jsonify({"error": _("Invalid widget")}), 400

    cache_ttl = 60 if widget["type"] == "kpi" else 300
    cache_key = (
        f"dash_widget_{_hash_widget_request(userid, widget, global_filters, allowed_processes)}"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return jsonify(cached)

    try:
        queries = build_widget_query(widget, global_filters, allowed_processes)
    except DashboardLayoutError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"widget_data build error: {e}")
        return jsonify({"error": _("Could not build query")}), 500

    try:
        result = _run_widget_queries(widget, queries)
    except Exception as e:
        current_app.logger.error(f"widget_data run error: {e}")
        return jsonify({"error": _("Could not run query")}), 500

    cache.set(cache_key, result, timeout=cache_ttl)
    return jsonify(result)


@require_permission("dashboard.view")
@limiter.limit("60 per minute")
def dashboard_widget_compare():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401
    payload = request.get_json(silent=True) or {}
    widget = payload.get("widget")
    global_filters = payload.get("globalFilters") or {}
    if not isinstance(widget, dict) or widget.get("type") not in DASHBOARD_WIDGET_TYPES:
        return jsonify({"error": _("Invalid widget")}), 400

    filters = _effective_filters(widget, global_filters)
    s, e = _resolve_date_range(
        filters.get("datePreset"), filters.get("dateFrom"), filters.get("dateTo")
    )
    if s is None or e is None:
        return jsonify(
            {"labels": [], "series": [], "warnings": ["compare_unavailable_no_date_range"]}
        )
    span_days = (e - s).days + 1
    new_e = s - timedelta(days=1)
    new_s = new_e - timedelta(days=span_days - 1)

    shifted_widget = json.loads(json.dumps(widget))  # deep copy
    shifted_widget["filterOverrides"] = dict(shifted_widget.get("filterOverrides") or {})
    shifted_widget["filterOverrides"]["datePreset"] = "custom"
    shifted_widget["filterOverrides"]["dateFrom"] = new_s.isoformat()
    shifted_widget["filterOverrides"]["dateTo"] = new_e.isoformat()

    perms = session.get("permissions", [])
    prefix = "dashboard.filter.process."
    allowed_processes = sorted(
        {(p.split(".")[-2] + "." + p.split(".")[-1]) for p in perms if p.startswith(prefix)}
    )
    try:
        queries = build_widget_query(shifted_widget, global_filters, allowed_processes)
        result = _run_widget_queries(shifted_widget, queries, label_override=_("Previous period"))
    except Exception as ex:
        current_app.logger.error(f"widget_compare error: {ex}")
        return jsonify({"error": _("Could not build comparison")}), 500
    return jsonify(result)


# ----------------------------- recent activity ----------------------------- #


@require_permission("dashboard.view")
@cache.cached(
    timeout=120,
    key_prefix=lambda: f"recent_activity_{session.get('userid')}_{session.get('process_name_dashboard','all')}",
)
def api_recent_activity():
    try:
        prefix = "dashboard.filter.process."
        process_name = session.get("process_name_dashboard", "all")

        perms = session.get("permissions", [])
        allowed_processes = sorted(
            {
                (perm.split(".")[-2] + "." + perm.split(".")[-1])
                for perm in perms
                if perm.startswith(prefix)
            }
        )
        target_processes = (
            allowed_processes
            if process_name == "all"
            else ([process_name] if process_name in allowed_processes else [])
        )

        if not target_processes:
            return jsonify([])

        proc_params = sorted({p.split(".")[-1] for p in target_processes if "." in p})
        cli_params = sorted({p.split(".")[0] for p in target_processes if "." in p})
        activity_instances_to_ignore = get_activity_instances_to_ignore()
        raw_rows = recent_activity_rows(
            proc_params, cli_params, activity_instances_to_ignore, top=3
        )

        activity = []
        for row in raw_rows:
            domain = get_domain_for_workitem(row["id"])
            workitemdata, doc_id = get_workitemdata_param(row["id"], domain)
            _ext, _urls, fields, _fs, _ts = get_extensions_urls_fields(workitemdata, doc_id, domain)
            fields = {k: v for k, v in fields.items() if v}
            activity.append(
                {
                    "id": row["id"],
                    "time": row["modifiedat"].strftime("%H:%M"),
                    "process": row["process"],
                    "fields": fields,
                }
            )

        return jsonify(activity)
    except Exception as e:
        current_app.logger.error(f"Activity feed error: {e}")
        return jsonify([])


def register_routes(app):
    # legacy KPI endpoints
    app.add_url_rule(
        "/api/dashboard/processed_over_time",
        endpoint="dashboard_processed_over_time",
        view_func=dashboard_processed_over_time,
    )
    app.add_url_rule(
        "/api/dashboard/kpi_stats", endpoint="dashboard_kpi_stats", view_func=dashboard_kpi_stats
    )
    app.add_url_rule(
        "/api/dashboard/hourly_stats",
        endpoint="dashboard_hourly_stats",
        view_func=dashboard_hourly_stats,
    )
    app.add_url_rule(
        "/api/dashboard/avg_processing_time",
        endpoint="dashboard_avg_processing_time",
        view_func=dashboard_avg_processing_time,
    )

    # dashboard page + filter
    app.add_url_rule("/dashboard", endpoint="dashboard", view_func=dashboard)
    app.add_url_rule(
        "/api/dashboard/set_filter",
        endpoint="dashboard_set_filter",
        view_func=dashboard_set_filter,
        methods=["POST"],
    )

    # field metadata + layout
    app.add_url_rule(
        "/api/dashboard/field_metadata",
        endpoint="dashboard_field_metadata",
        view_func=dashboard_field_metadata,
    )
    app.add_url_rule(
        "/api/dashboard/layout", endpoint="dashboard_get_layout", view_func=dashboard_get_layout
    )
    app.add_url_rule(
        "/api/dashboard/layout",
        endpoint="dashboard_put_layout",
        view_func=dashboard_put_layout,
        methods=["PUT"],
    )
    app.add_url_rule(
        "/api/dashboard/layout/reset",
        endpoint="dashboard_reset_layout",
        view_func=dashboard_reset_layout,
        methods=["POST"],
    )

    # widget engine
    app.add_url_rule(
        "/api/dashboard/widget_data",
        endpoint="dashboard_widget_data",
        view_func=dashboard_widget_data,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/dashboard/widget_compare",
        endpoint="dashboard_widget_compare",
        view_func=dashboard_widget_compare,
        methods=["POST"],
    )

    # recent activity
    app.add_url_rule(
        "/api/dashboard/recent_activity",
        endpoint="api_recent_activity",
        view_func=api_recent_activity,
    )
