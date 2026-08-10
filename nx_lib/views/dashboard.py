"""Dashboard page, KPI/time-series endpoints and the recent-activity feed.

The customizable-widget engine (per-user layouts, widget_data/widget_compare,
field metadata) was removed in 2.5.65: it never had a frontend and its
FieldMetadata / DashboardLayouts tables were never migrated to any
environment."""

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
from ..extensions import cache
from ..octo import get_extensions_urls_fields, get_workitemdata_param
from ..process_helpers import (
    get_activity_instances_to_ignore,
    normalize_process_selection,
)
from ..security import page_visibility, require_permission
from ..workitem_sources import (
    get_domain_for_workitem,
    recent_activity_rows,
    total_backlog_count,
)
from .workitems import sensitive_blocked_tokens, strip_sensitive_fields


def make_cache_key(*args, **kwargs):
    return f"{request.path}_{session.get('userid')}_{session.get('process_name_dashboard', 'all')}"


def _cacheable_response(rv):
    """response_filter for @cache.cached on the four legacy KPI endpoints:
    never pin an error response — a transient 500 would otherwise be served
    for the full TTL per user+filter, stretching outages and confusing
    diagnosis."""
    status = rv[1] if isinstance(rv, tuple) and len(rv) == 2 else getattr(rv, "status_code", 200)
    return status < 400


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


def _ms02_stat_rows(sql, *, strict=False):
    """Run a read-only query on the MS02 stats engine; return rows, or [] if the
    engine is unconfigured/unreachable or the query errors. Centralises the
    connection handling + error swallowing for the dashboard's MS02 branches: a
    failure here must never break the default-client numbers, so by default it
    logs and yields no rows. MS02 Statconfig conditions (additionalCondition) are
    Postgres-syntax and currently NULL, so they are not applied here.

    strict: the external API's opt-in (compute_today_stats(..., strict=True))
    -- a genuine query failure is re-raised instead of swallowed, so an outage
    surfaces as a 500 rather than silent zeros. An unconfigured engine
    (engine_ms02_stats_pg is None) is NOT a failure either way -- MS02 simply
    not being wired up for this deployment still yields [].
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
        if strict:
            raise
        return []


def _default_stat_rows(sql, *, strict=False):
    """Run a read-only query on the default StatisticsDB engine; return rows,
    or [] if the server is unreachable or the query errors (e.g. a stale
    Statconfig row pointing at a dropped table). Mirror of _ms02_stat_rows for
    the T-SQL leg: by default a leg failure must never blank the other leg's
    numbers -- log and yield no rows so each leg degrades independently.

    strict: see _ms02_stat_rows -- re-raise instead of swallowing so
    compute_today_stats(..., strict=True) (the external API) turns a genuine
    outage into a 500 instead of reporting a quiet day."""
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
        if strict:
            raise
        return []


def compute_today_stats(target_processes, *, strict=False):
    """Session-free 'today' KPI computation shared by the dashboard KPI card
    (dashboard_kpi_stats) and the external API v1 (nx_lib/views/api_external.py).

    target_processes: NON-EMPTY list of full Statconfig ProcessName values
    (e.g. 'sydoc.05_PDBS'); both callers guard the empty case. Returns
    (imported_today, processed_today): imported = import-date-column is today,
    processed = export-date-column is today. Long-standing dashboard semantics
    inherited verbatim: the default T-SQL leg counts export-today only among
    rows whose import date is also today (its WHERE clause), while the MS02
    leg counts export-today unconditionally. 'Today' is server-local --
    GETDATE() on the T-SQL leg, CURRENT_DATE on the MS02 Postgres leg.

    The Statconfig read (NexoraDB) always RAISES on failure -- callers own the
    error surface (the dashboard's except->500 stays uncached via
    _cacheable_response; the API returns a JSON 500).

    strict (default False, the dashboard's setting): the two stat-row legs
    keep their swallow-and-degrade contract (_default_stat_rows /
    _ms02_stat_rows return [] on failure), so a dead Statistics DB still
    yields the healthy leg's numbers -- a genuine outage is indistinguishable
    from a quiet day with no matching rows (both legs' aggregate queries
    return one row of NULLs, not []). The external API passes strict=True: a
    stat-row leg failure then RAISES instead of degrading to zeros, so an
    outage surfaces as the documented 500 rather than a false "all quiet"
    200. An unconfigured MS02 engine still yields [] either way -- that's
    "not applicable", not a failure. Deliberately NOT cached here -- the
    dashboard view's @cache.cached (session-keyed) stays on the view.
    Deliberately lives in THIS module: it must resolve engine_nexora_db /
    engine_statistics_db / _ms02_stat_rows as nx_lib.views.dashboard
    attributes, which the existing tests monkeypatch.
    """
    processed_today = 0
    imported_today = 0

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
    finally:
        if cursor_nex:
            cursor_nex.close()
        if conn_nex:
            conn_nex.close()

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
            # strict is only ever forwarded as a kwarg when True -- existing
            # (and test) call sites that replace these legs with a
            # single-argument callable (sql) keep working unchanged in the
            # strict=False (dashboard) case.
            srows = (
                _default_stat_rows(full_stat_query, strict=True)
                if strict
                else _default_stat_rows(full_stat_query)
            )
            if srows:
                processed_today += srows[0][0] or 0
                imported_today += srows[0][1] or 0

    ms02_src = _ms02_source(ms02_rows)
    if ms02_src:
        tbl, exp, imp = ms02_src
        ms02_sql = (
            f"SELECT "
            f"COUNT(*) FILTER (WHERE {exp}::date = CURRENT_DATE), "
            f"COUNT(*) FILTER (WHERE {imp}::date = CURRENT_DATE) "
            f"FROM {tbl}"
        )
        mrows = _ms02_stat_rows(ms02_sql, strict=True) if strict else _ms02_stat_rows(ms02_sql)
        if mrows:
            processed_today += mrows[0][0] or 0
            imported_today += mrows[0][1] or 0

    return imported_today, processed_today


def compute_avg_processing_time(target_processes, *, strict=False):
    """Session-free average processing-time computation shared by the dashboard
    KPI card (dashboard_avg_processing_time) and the external API v1
    (nx_lib/views/api_external.py). Mirror of compute_today_stats -- see its
    docstring for the strict/error-surface contract.

    target_processes: NON-EMPTY list of full Statconfig ProcessName values;
    both callers guard the empty case. Returns the average number of seconds
    between import and export for rows exported "today" (server-local), or
    None if no matching rows exist. Per source, AVG(export - import) is taken
    across matching rows; the default-client and MS02 sources then contribute
    one average each, combined as a plain mean-of-means (NOT weighted by row
    count) -- a source with 2000 rows counts the same as one with 2."""
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
    finally:
        if cursor_nex:
            cursor_nex.close()
        if conn_nex:
            conn_nex.close()

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
        srows = (
            _default_stat_rows(full_query, strict=True)
            if strict
            else _default_stat_rows(full_query)
        )
        if srows and srows[0][0] is not None:
            avg_values.append(srows[0][0])

    # MS02 contributes one client-level average (export - import seconds),
    # weighted equally with the default bucket -- same mean-of-means the
    # default path already applies across its processes.
    ms02_src = _ms02_source(ms02_rows)
    if ms02_src:
        tbl, exp, imp = ms02_src
        ms02_sql = (
            f"SELECT AVG(EXTRACT(EPOCH FROM ({exp} - {imp}))) "
            f"FROM {tbl} "
            f"WHERE {exp}::date = CURRENT_DATE "
            f"AND {imp} IS NOT NULL AND {exp} > {imp}"
        )
        mrows = _ms02_stat_rows(ms02_sql, strict=True) if strict else _ms02_stat_rows(ms02_sql)
        if mrows and mrows[0][0] is not None:
            avg_values.append(float(mrows[0][0]))

    if not avg_values:
        return None

    return sum(avg_values) / len(avg_values)


def format_avg_processing_display(avg_sec):
    """Render compute_avg_processing_time's seconds figure the same way for
    both the dashboard KPI card and the external API -- 's' under a minute,
    'min' under an hour, 'h' above. Shared so the two never drift apart."""
    avg_minutes = avg_sec / 60
    if avg_minutes < 1:
        display = f"{int(avg_sec)}s"
    elif avg_minutes < 60:
        display = f"{avg_minutes:.0f}min"
    else:
        display = f"{avg_minutes / 60:.1f}h"
    return round(avg_minutes, 1), display


# ----------------------------- legacy KPI endpoints (still used by the templates) ----- #


@require_permission("dashboard.view")
@cache.cached(timeout=300, key_prefix=make_cache_key, response_filter=_cacheable_response)
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

    target_processes = normalize_process_selection(process_name, allowed_processes)[1]

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
        return jsonify({"error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("dashboard.view")
@cache.cached(
    timeout=60,
    key_prefix=lambda: f"kpi_stats_{session.get('userid')}_{session.get('process_name_dashboard','all')}",
    response_filter=_cacheable_response,
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

    target_processes = normalize_process_selection(process_name, allowed_processes)[1]

    if not target_processes:
        return jsonify(
            {"processed_today": 0, "processed_week": 0, "current_backlog": 0, "imported_today": 0}
        )

    try:
        imported_today, processed_today = compute_today_stats(target_processes)

        current_backlog = 0
        if target_processes:
            # (client, process) pairs, NOT two independent client/process
            # IN-lists -- see _pair_predicate's docstring in workitem_sources.py
            # for why that shape authorizes the full cross product instead of
            # only the granted pairs.
            pairs = sorted(
                {(p.split(".")[0], p.split(".")[-1]) for p in target_processes if "." in p}
            )
            current_backlog += total_backlog_count(pairs)

        return jsonify(
            {
                "processed_today": processed_today,
                "imported_today": imported_today,
                "current_backlog": current_backlog,
            }
        )

    except Exception as e:
        current_app.logger.error(f"Failed to fetch kpi_stats report: {e}")
        return jsonify({"error": _("An unexpected error occurred")}), 500


@require_permission("dashboard.view")
@cache.cached(
    timeout=120,
    key_prefix=lambda: f"hourly_stats_{session.get('userid')}_{session.get('process_name_dashboard','all')}",
    response_filter=_cacheable_response,
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
    target_processes = normalize_process_selection(process_name, allowed_processes)[1]

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
        return jsonify({"error": _("An unexpected error occurred")}), 500
    finally:
        if cursor_nex:
            cursor_nex.close()
        if conn_nex:
            conn_nex.close()


@require_permission("dashboard.view")
@cache.cached(
    timeout=300,
    key_prefix=lambda: f"avg_proc_time_{session.get('userid')}_{session.get('process_name_dashboard','all')}",
    response_filter=_cacheable_response,
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
    target_processes = normalize_process_selection(process_name, allowed_processes)[1]

    if not target_processes:
        return jsonify({"avg_minutes": None, "avg_display": "—"})

    try:
        avg_sec = compute_avg_processing_time(target_processes)
        if avg_sec is None:
            return jsonify({"avg_minutes": None, "avg_display": "—"})

        avg_minutes, display = format_avg_processing_display(avg_sec)
        return jsonify({"avg_minutes": avg_minutes, "avg_display": display})

    except Exception as e:
        current_app.logger.error(f"Failed to fetch avg_processing_time: {e}")
        return jsonify({"error": _("An unexpected error occurred")}), 500


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
        # Sign-in note shows once, on the first dashboard render after login (issue #146).
        show_note = session.pop("show_login_note", False)
        login_at = session.get("login_at") if show_note else None
        prev_login_at = session.get("prev_login_at") if show_note else None

        prefix = "dashboard.filter.process."
        allowed_processes = sorted(
            {
                (perm.split(".")[-2] + "." + perm.split(".")[-1])
                for perm in perms
                if perm.startswith(prefix)
            }
        )

        process_name = normalize_process_selection(
            request.args.get("prcfD", "all"), allowed_processes
        )[0]
        session["process_name_dashboard"] = process_name

        return render_template(
            "dashboard.html",
            logged_in_user=logged_in_user,
            userid=userid,
            process_name=process_name,
            allowed_processes=allowed_processes,
            pageV=page_visibility(),
            fullname=fullname,
            login_at=login_at,
            prev_login_at=prev_login_at,
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
    process_name = normalize_process_selection(
        request.json.get("process_name", "all"), allowed_processes
    )[0]
    session["process_name_dashboard"] = process_name
    return jsonify({"ok": True, "process_name": process_name})


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
        target_processes = normalize_process_selection(process_name, allowed_processes)[1]

        if not target_processes:
            return jsonify([])

        # (client, process) pairs, NOT two independent client/process
        # IN-lists -- see _pair_predicate's docstring in workitem_sources.py.
        pairs = sorted({(p.split(".")[0], p.split(".")[-1]) for p in target_processes if "." in p})
        activity_instances_to_ignore = get_activity_instances_to_ignore()
        raw_rows = recent_activity_rows(pairs, activity_instances_to_ignore, top=3)

        # Same sensitive-doc-field gate enforced at every other surface that
        # shows doc-fields (workitems.filter.documentfields.sensitive) --
        # this feed was reading raw Octo fields straight through.
        blocked_tokens = sensitive_blocked_tokens()

        activity = []
        for row in raw_rows:
            domain = get_domain_for_workitem(row["id"], client_hint=row.get("client"))
            returndata = get_workitemdata_param(row["id"], domain)
            if not returndata:
                current_app.logger.warning(
                    f"Activity feed: skipping workitem {row['id']} (Octo lookup failed)"
                )
                continue
            workitemdata, doc_id = returndata
            _ext, _urls, fields, _fs, _ts = get_extensions_urls_fields(workitemdata, doc_id, domain)
            fields = {k: v for k, v in fields.items() if v}
            fields = strip_sensitive_fields(fields, blocked_tokens)
            activity.append(
                {
                    "id": row["id"],
                    "time": row["modifiedat"].strftime("%H:%M"),
                    "process": row["process"],
                    "client": row.get("client"),
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

    # recent activity
    app.add_url_rule(
        "/api/dashboard/recent_activity",
        endpoint="api_recent_activity",
        view_func=api_recent_activity,
    )
