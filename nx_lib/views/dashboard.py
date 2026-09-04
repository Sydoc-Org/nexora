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

from .. import mapping_config
from ..config import DB_STATISTICS
from ..db import engine_ms02_stats_pg, engine_statistics_db
from ..extensions import cache
from ..octo import get_extensions_urls_fields, get_workitemdata_param
from ..process_helpers import (
    get_activity_instances_to_ignore,
    granted_processes,
    normalize_process_selection,
)
from ..security import page_visibility, require_permission
from ..workitem_sources import (
    get_domain_for_workitem,
    recent_activity_rows,
    total_backlog_count,
)
from .tenant import apply_tenant_scope
from .workitems import sensitive_blocked_tokens, strip_sensitive_fields

# The 14 / 30 / 90-day windows the range control offers. Anything else
# normalizes to 14 -- the value reaches SQL by string interpolation (a
# server-side int, never user text), so the allowlist IS the sanitizer.
RANGE_CHOICES = (14, 30, 90)


def normalize_range(value):
    """One of RANGE_CHOICES, or 14. Accepts str or int; never raises."""
    try:
        days = int(value)
    except (TypeError, ValueError):
        return RANGE_CHOICES[0]
    return days if days in RANGE_CHOICES else RANGE_CHOICES[0]


def _allowed_processes():
    """Sorted ``dashboard.filter.process.*`` grants inside the session's tenant
    scope (0097) -- see process_helpers.granted_processes."""
    return sorted(granted_processes("dashboard.filter.process."))


def make_cache_key(*args, **kwargs):
    return f"{request.path}_{session.get('userid')}_{session.get('process_name_dashboard','all')}_{session.get('tenant_scope','')}"


def _cacheable_response(rv):
    """response_filter for @cache.cached on the four legacy KPI endpoints:
    never pin an error response — a transient 500 would otherwise be served
    for the full TTL per user+filter, stretching outages and confusing
    diagnosis."""
    status = rv[1] if isinstance(rv, tuple) and len(rv) == 2 else getattr(rv, "status_code", 200)
    return status < 400


def _split_stat_configs(configs):
    """Partition ProcessSource rows (mapping_config #98) by serving client.
    Returns (default_rows, ms02_rows). Rows with a blank/missing client code
    count as 'default' (back-compat with pre-0024 data)."""
    default_rows = []
    ms02_rows = []
    for r in configs:
        code = r.client or "default"
        if code == "ms02":
            ms02_rows.append(r)
        else:
            default_rows.append(r)
    return default_rows, ms02_rows


def _statconfig_sources(target_processes):
    """All ProcessSource rows (any client) for ``target_processes``, from the
    mapping_config registry (#98) -- successor to the direct per-call legacy
    stat-config-table cursor read. Raises if the registry itself failed to
    load: a genuine NexoraDB/config outage must surface as an error here
    (dashboard view: uncached 500 via its except-block; external API strict
    callers: JSON 500), never be swallowed into a false 'quiet day' zero --
    the contract the legacy per-call SELECT gave for free by always hitting
    NexoraDB directly. mapping_config.registry() is cached 60s on success,
    so most calls never round-trip NexoraDB at all."""
    if mapping_config.registry() is None:
        raise RuntimeError("mapping_config registry unavailable")
    return mapping_config.sources_for(client=None, processes=target_processes)


def _ms02_source(ms02_rows):
    """Resolve the single MS02 stats source from its ProcessSource row(s).

    Returns (table, export_expr, import_expr) or None. MS02 rows all point at the
    same table (no per-process split), so we dedupe to the first row. table is
    used verbatim (already schema-qualified, e.g. public."DossierStatistik"); the
    column names are admin-controlled ProcessSources values, quoted as Postgres
    identifiers because they are PascalCase. The old hardcoded
    'public.batchtracking'/'datuminexport' literals never existed in the MS02 DB."""
    if not ms02_rows:
        return None
    r = ms02_rows[0]

    def q(col):
        return '"' + str(col).replace('"', '""') + '"'

    return r.table, q(r.export_column), q(r.import_column)


def _ms02_stat_rows(sql, *, strict=False):
    """Run a read-only query on the MS02 stats engine; return rows, or [] if the
    engine is unconfigured/unreachable or the query errors. Centralises the
    connection handling + error swallowing for the dashboard's MS02 branches: a
    failure here must never break the default-client numbers, so by default it
    logs and yields no rows. MS02 ProcessSources conditions (extra_condition) are
    Postgres-syntax and currently NULL, so they are not applied here.

    strict: the external API's opt-in (compute_today_stats(..., strict=True))
    -- a genuine query failure is re-raised instead of swallowed, so an outage
    surfaces as a 500 rather than silent zeros. An unconfigured engine
    (engine_ms02_stats_pg is None) is NOT a failure either way -- MS02 simply
    not being wired up for this deployment still yields [].
    # ponytail: no per-call extra_condition; add when an MS02 row needs one."""
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


def _default_stat_rows(sql, params=None, *, strict=False):
    """Run a read-only query on the default StatisticsDB engine; return rows,
    or [] if the server is unreachable or the query errors (e.g. a stale
    ProcessSources row pointing at a dropped table). Mirror of _ms02_stat_rows for
    the T-SQL leg: by default a leg failure must never blank the other leg's
    numbers -- log and yield no rows so each leg degrades independently.

    params: optional positional query parameters (resolve_import_datetimes
    passes the id list; the KPI legs interpolate config-derived SQL only).

    strict: see _ms02_stat_rows -- re-raise instead of swallowing so
    compute_today_stats(..., strict=True) (the external API) turns a genuine
    outage into a 500 instead of reporting a quiet day."""
    try:
        conn = engine_statistics_db.raw_connection()
        try:
            cur = conn.cursor()
            if params:
                cur.execute(sql, params)
            else:
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

    target_processes: NON-EMPTY list of full ProcessSources process-name values
    (e.g. 'sydoc.05_PDBS'); both callers guard the empty case. Returns
    (imported_today, processed_today): imported = import-date-column is today,
    processed = export-date-column is today. Long-standing dashboard semantics
    inherited verbatim: the default T-SQL leg counts export-today only among
    rows whose import date is also today (its WHERE clause), while the MS02
    leg counts export-today unconditionally. 'Today' is server-local --
    GETDATE() on the T-SQL leg, CURRENT_DATE on the MS02 Postgres leg.

    The mapping_config registry read (NexoraDB) always RAISES on failure --
    callers own the error surface (the dashboard's except->500 stays
    uncached via _cacheable_response; the API returns a JSON 500).

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
    Deliberately lives in THIS module: it must resolve mapping_config /
    engine_statistics_db / _ms02_stat_rows as nx_lib.views.dashboard
    attributes, which the existing tests monkeypatch.
    """
    processed_today = 0
    imported_today = 0

    configs = _statconfig_sources(target_processes)
    default_configs, ms02_rows = _split_stat_configs(configs)

    if default_configs:
        sub_queries = []
        for row in default_configs:
            col_export = row.export_column
            col_import = row.import_column
            condition = f" {row.extra_condition}" if row.extra_condition else ""
            sub_queries.append(f"""
                SELECT
                    SUM(CASE WHEN CAST({col_export} AS DATE) = CAST(GETDATE() AS DATE) THEN 1 ELSE 0 END) as TodayCountExport,
                    SUM(CASE WHEN CAST({col_import} AS DATE) = CAST(GETDATE() AS DATE) THEN 1 ELSE 0 END) as TodayCountExportImport
                FROM [{DB_STATISTICS}].{row.table}
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


def _kpi_daily_counts(target_processes, days):
    """{date: {"imported": n, "processed": n}} for the trailing ``days`` days,
    zero-filled so a sparse client still draws a continuous sparkline.

    Per-day generalization of compute_today_stats using its EXACT predicates:
    the default T-SQL leg groups by import date (imported = every row in scope,
    processed = the subset exported that same day), the MS02 leg counts each
    column independently. That equality is the point -- each sparkline's last
    point is then the same number as the KPI above it.

    ponytail: a sibling rather than a refactor of compute_today_stats -- eight
    tests fake _default_stat_rows with bare (imported, processed) 2-tuples and
    would break on a changed row shape. Upgrade path: fold the two together
    when those fakes are rewritten to yield dated rows.
    """
    days = max(1, int(days))
    out = {}

    configs = _statconfig_sources(target_processes)
    default_configs, ms02_rows = _split_stat_configs(configs)

    sub_queries = []
    for row in default_configs:
        condition = f" {row.extra_condition}" if row.extra_condition else ""
        sub_queries.append(f"""
            SELECT CAST({row.import_column} AS DATE) as d,
                   COUNT(*) as imported,
                   SUM(CASE WHEN CAST({row.export_column} AS DATE) = CAST({row.import_column} AS DATE)
                            THEN 1 ELSE 0 END) as processed
            FROM [{DB_STATISTICS}].{row.table}
            WHERE CAST({row.import_column} AS DATE) >= CAST(DATEADD(day, -{days - 1}, GETDATE()) AS DATE)
            {condition}
            GROUP BY CAST({row.import_column} AS DATE)
        """)

    if sub_queries:
        full_query = f"""
            SELECT d, SUM(imported), SUM(processed)
            FROM ({" UNION ALL ".join(sub_queries)}) as combined
            GROUP BY d
        """
        for row in _default_stat_rows(full_query):
            d = row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0])[:10])
            cell = out.setdefault(d, {"imported": 0, "processed": 0})
            cell["imported"] += row[1] or 0
            cell["processed"] += row[2] or 0

    ms02_src = _ms02_source(ms02_rows)
    if ms02_src:
        tbl, exp, imp = ms02_src
        for col, key in ((imp, "imported"), (exp, "processed")):
            for d, c in _ms02_stat_rows(
                f"SELECT {col}::date AS d, COUNT(*) AS c "
                f"FROM {tbl} "
                f"WHERE {col} >= CURRENT_DATE - {days - 1} "
                f"GROUP BY {col}::date"
            ):
                out.setdefault(d, {"imported": 0, "processed": 0})[key] += c or 0

    today = datetime.now().date()
    for i in range(days):
        out.setdefault(today - timedelta(days=i), {"imported": 0, "processed": 0})
    return {d: out[d] for d in sorted(out) if d >= today - timedelta(days=days - 1)}


def _avg_processing_by_day(target_processes, days, *, strict=False):
    """{date: avg_seconds} over the trailing ``days`` days -- per source,
    AVG(export - import) grouped by export date; the default-client and MS02
    buckets then contribute one average each per day, combined as a plain
    mean-of-means (NOT weighted by row count). Days with no matching rows are
    ABSENT rather than zero: a zero average would draw a cliff in the
    sparkline where the truth is "no documents finished that day"."""
    days = max(1, int(days))
    per_day = {}

    configs = _statconfig_sources(target_processes)
    default_configs, ms02_rows = _split_stat_configs(configs)

    sub_queries = []
    for row in default_configs:
        if not row.import_column:
            continue
        condition = f" {row.extra_condition}" if row.extra_condition else ""
        sub_queries.append(f"""
            SELECT CAST({row.export_column} AS DATE) as d,
                   AVG(CAST(DATEDIFF(second, {row.import_column}, {row.export_column}) AS FLOAT)) as avg_sec
            FROM [{DB_STATISTICS}].{row.table}
            WHERE CAST({row.export_column} AS DATE) >= CAST(DATEADD(day, -{days - 1}, GETDATE()) AS DATE)
            AND {row.import_column} IS NOT NULL
            AND {row.export_column} > {row.import_column}
            {condition}
            GROUP BY CAST({row.export_column} AS DATE)
        """)

    if sub_queries:
        full_query = f"""
            SELECT d, AVG(avg_sec) as overall_avg
            FROM ({' UNION ALL '.join(sub_queries)}) as combined
            WHERE avg_sec IS NOT NULL
            GROUP BY d
        """
        srows = (
            _default_stat_rows(full_query, strict=True)
            if strict
            else _default_stat_rows(full_query)
        )
        for row in srows:
            if row[1] is None:
                continue
            d = row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0])[:10])
            per_day.setdefault(d, []).append(float(row[1]))

    ms02_src = _ms02_source(ms02_rows)
    if ms02_src:
        tbl, exp, imp = ms02_src
        ms02_sql = (
            f"SELECT {exp}::date AS d, AVG(EXTRACT(EPOCH FROM ({exp} - {imp}))) "
            f"FROM {tbl} "
            f"WHERE {exp} >= CURRENT_DATE - {days - 1} "
            f"AND {imp} IS NOT NULL AND {exp} > {imp} "
            f"GROUP BY {exp}::date"
        )
        mrows = _ms02_stat_rows(ms02_sql, strict=True) if strict else _ms02_stat_rows(ms02_sql)
        for row in mrows:
            if row[1] is None:
                continue
            per_day.setdefault(row[0], []).append(float(row[1]))

    return {d: sum(v) / len(v) for d, v in per_day.items()}


_BACKLOG_HISTORY_SQL = """
SELECT SnapshotAt, SourceCode, ClientName, ProcessName, BacklogCount
FROM dbo.BacklogHistory
WHERE SnapshotAt >= CAST(DATEADD(day, ?, CAST(GETDATE() AS DATE)) AS DATETIME2(0))
ORDER BY SnapshotAt
"""


def _backlog_history(target_processes, days):
    """{date: {"<client>.<process>": count}} from dbo.BacklogHistory (Statistics
    DB), one point per day per process: the LAST snapshot of that day, summed
    across SourceCodes (a pair can be served by both the Octo and MS02
    runtimes). Rows outside ``target_processes`` are dropped here in Python --
    14 days x a handful of processes is a few hundred rows, and a Python
    membership test beats interpolating a pair list into the WHERE clause.

    Matching is CASE-INSENSITIVE and that is load-bearing, not defensive:
    BacklogHistory.ClientName comes from Octo's t_Processes.ClientName and is
    display-cased ('Privera', 'ElektroMaterial', 'Compass'), while
    target_processes comes from dbo.ProcessSources.ProcessName and is
    lower-cased ('privera.03_Invoice_New'). Verified on INT 2026-09-04. An
    exact match silently drops every non-MS02 process and leaves a chart that
    looks plausible but is missing most of the backlog.

    The collector (ops/backlog_history/backlog_history.py, every 30 min) owns
    the table; nexora only reads it. A dead Statistics DB yields {} through
    _default_stat_rows' swallow-and-log contract, which the callers render as
    an empty chart."""
    days = max(1, int(days))
    # Keep the canonical (ProcessSources) spelling as the output key, looked up
    # by its folded form, so the API returns names the rest of the app knows.
    wanted = {p.casefold(): p for p in target_processes}

    # (date, client.process) -> {source_code: (snapshot_at, count)} -- keep the
    # latest snapshot per source before summing, so an early-morning row from
    # one source never outranks an evening row from another.
    latest = {}
    for snapshot_at, source_code, client, process, count in _default_stat_rows(
        _BACKLOG_HISTORY_SQL, (-(days - 1),)
    ):
        name = wanted.get(f"{client}.{process}".casefold())
        if name is None:
            continue
        at = (
            snapshot_at
            if isinstance(snapshot_at, datetime)
            else datetime.fromisoformat(str(snapshot_at))
        )
        slot = latest.setdefault((at.date(), name), {})
        prev = slot.get(source_code)
        if prev is None or at >= prev[0]:
            slot[source_code] = (at, count or 0)

    out = {}
    for (day, name), by_source in latest.items():
        out.setdefault(day, {})[name] = sum(c for _at, c in by_source.values())
    return {d: out[d] for d in sorted(out)}


def compute_avg_processing_time(target_processes, *, strict=False):
    """Session-free average processing-time computation shared by the dashboard
    KPI card (dashboard_avg_processing_time) and the external API v1
    (nx_lib/views/api_external.py). Mirror of compute_today_stats -- see its
    docstring for the strict/error-surface contract.

    target_processes: NON-EMPTY list of full ProcessSources process-name values;
    both callers guard the empty case. Returns the average number of seconds
    between import and export for rows exported "today" (server-local), or
    None if no matching rows exist. Per source, AVG(export - import) is taken
    across matching rows; the default-client and MS02 sources then contribute
    one average each, combined as a plain mean-of-means (NOT weighted by row
    count) -- a source with 2000 rows counts the same as one with 2.

    Today's slice of _avg_processing_by_day -- one implementation, so the KPI
    number and its sparkline can never disagree."""
    return _avg_processing_by_day(target_processes, 1, strict=strict).get(datetime.now().date())


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


def resolve_import_datetimes(workitem_ids, target_processes, *, strict=False):
    """Batch import-datetime lookup for a page of workitem ids (issue #197,
    external API v1 /workitems -- supersedes issue #195's single-invoice
    helper). Default client only: each default-client ProcessSources row names the
    stat table plus its workitem_column/import_column; one UNION query over
    those tables maps every id it can. Ids are compared and returned as
    strings (stat tables mix int and NVARCHAR id columns). Ids without a
    match are simply absent from the result -- MS02 rows and unmapped
    processes never appear. strict mirrors compute_today_stats: a
    StatisticsDB failure raises instead of degrading to "no data"."""
    if not workitem_ids or not target_processes:
        return {}

    configs = _statconfig_sources(target_processes)
    default_configs, _ms02_rows = _split_stat_configs(configs)

    legs = []
    for row in default_configs:
        if not row.workitem_column or not row.import_column:
            continue
        # CAST + COLLATE on the id column: the UNION legs span stat tables with
        # mixed id types/collations (same reason the doc-field search casts).
        wid_expr = f"CAST({row.workitem_column} AS NVARCHAR(50)) COLLATE DATABASE_DEFAULT"
        legs.append((wid_expr, row.import_column, row.table))

    if not legs:
        return {}

    # Every leg repeats the full id list as parameters, so a statement carries
    # len(legs) * chunk params -- chunk to stay under SQL Server's 2100-param
    # cap (a 1000-row page over 3+ legs would otherwise blow it). Ids are
    # partitioned across chunks, so per-chunk MAX-per-wid stays correct.
    str_ids = [str(w) for w in workitem_ids]
    chunk_size = max(1, 2000 // len(legs))
    result = {}
    for start in range(0, len(str_ids), chunk_size):
        chunk = str_ids[start : start + chunk_size]
        id_placeholders = ",".join(["?"] * len(chunk))
        sub_queries = [
            f"SELECT {wid_expr} AS wid, {import_col} AS import_dt "
            f"FROM [{DB_STATISTICS}].{table} "
            f"WHERE {wid_expr} IN ({id_placeholders})"
            for wid_expr, import_col, table in legs
        ]
        params = chunk * len(legs)
        full_query = (
            f"SELECT wid, MAX(import_dt) AS import_dt "
            f"FROM ({' UNION ALL '.join(sub_queries)}) t "
            f"WHERE import_dt IS NOT NULL GROUP BY wid"
        )
        rows = (
            _default_stat_rows(full_query, params, strict=True)
            if strict
            else _default_stat_rows(full_query, params)
        )
        result.update({str(r[0]): r[1] for r in rows})
    return result


def compute_undelivered_count(target_processes, days, *, strict=False):
    """Session-free count of workitems imported in the last `days` days whose
    export-date column is still NULL ("not delivered yet"), for the external
    API v1 (nx_lib/views/api_external.py, issue #196). Mirror of
    compute_today_stats -- see its docstring for the strict/error-surface
    contract and why this lives in this module.

    target_processes: NON-EMPTY list of full ProcessSources process-name values;
    the caller guards the empty case. days: a validated int (the API allows
    only 7 or 10) -- inlined into the SQL, never raw request input. The
    import window is calendar-day based and includes today (import date >=
    today - days, server-local). ProcessSources rows without an import_column
    cannot answer this metric and are skipped (same rule as the avg
    processing-time KPI)."""
    days = int(days)
    total = 0

    configs = _statconfig_sources(target_processes)
    default_configs, ms02_rows = _split_stat_configs(configs)

    sub_queries = []
    for row in default_configs:
        if not row.import_column:
            continue
        condition = f" {row.extra_condition}" if row.extra_condition else ""
        sub_queries.append(f"""
            SELECT COUNT(*) as c
            FROM [{DB_STATISTICS}].{row.table}
            WHERE CAST({row.import_column} AS DATE) >= CAST(DATEADD(day, -{days}, GETDATE()) AS DATE)
            AND {row.export_column} IS NULL
            {condition}
        """)

    if sub_queries:
        full_query = f"SELECT SUM(c) FROM ({' UNION ALL '.join(sub_queries)}) as combined"
        srows = (
            _default_stat_rows(full_query, strict=True)
            if strict
            else _default_stat_rows(full_query)
        )
        if srows:
            total += srows[0][0] or 0

    ms02_src = _ms02_source(ms02_rows)
    if ms02_src:
        tbl, exp, imp = ms02_src
        ms02_sql = (
            f"SELECT COUNT(*) FROM {tbl} "
            f"WHERE {imp}::date >= CURRENT_DATE - {days} "
            f"AND {exp} IS NULL"
        )
        mrows = _ms02_stat_rows(ms02_sql, strict=True) if strict else _ms02_stat_rows(ms02_sql)
        if mrows:
            total += mrows[0][0] or 0

    return total


# ----------------------------- legacy KPI endpoints (still used by the templates) ----- #


@require_permission("dashboard.view")
@cache.cached(
    timeout=300,
    key_prefix=make_cache_key,  # type: ignore[arg-type]  # callable prefix, stubs say str
    response_filter=_cacheable_response,
)
def dashboard_processed_over_time():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    allowed_processes = _allowed_processes()
    process_name = session.get("process_name_dashboard", "all")

    target_processes = normalize_process_selection(process_name, allowed_processes)[1]

    if not target_processes:
        return jsonify({"labels": [], "data": []})

    try:
        configs = _statconfig_sources(target_processes)

        if not configs:
            return jsonify({"labels": [], "data": []})

        default_configs, ms02_rows = _split_stat_configs(configs)

        sub_queries = []
        for row in default_configs:
            convert = "convert" in str(row.export_column).lower()
            date_col = f"CAST({row.export_column} AS DATE)" if not convert else row.export_column
            condition = f" {row.extra_condition}" if row.extra_condition else ""
            sub_queries.append(f"""
                SELECT {date_col} as d, COUNT(*) as c
                FROM [{DB_STATISTICS}].{row.table}
                WHERE {row.export_column} >= DATEADD(day, -14, GETDATE()) {condition}
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


@require_permission("dashboard.view")
@cache.cached(
    timeout=60,
    key_prefix=lambda: f"kpi_stats_{session.get('userid')}_{session.get('process_name_dashboard','all')}_{session.get('tenant_scope','')}",  # type: ignore[arg-type]
    response_filter=_cacheable_response,
)
def dashboard_kpi_stats():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    allowed_processes = _allowed_processes()
    process_name = session.get("process_name_dashboard", "all")

    target_processes = normalize_process_selection(process_name, allowed_processes)[1]

    if not target_processes:
        return jsonify(
            {
                "processed_today": 0,
                "imported_today": 0,
                "current_backlog": 0,
                "prev_imported": 0,
                "prev_processed": 0,
                "prev_backlog": 0,
                "series": {"imported": [], "processed": [], "backlog": []},
            }
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

        # 7 points including today, oldest first -- the sparkline window.
        counts = _kpi_daily_counts(target_processes, 7)
        cdays = sorted(counts)
        backlog_hist = _backlog_history(target_processes, 7)
        bdays = sorted(backlog_hist)
        # Live number for today, snapshots for the past: the collector's most
        # recent row is up to 30 min old, so today's own point uses the value
        # actually shown above it.
        backlog_series = [sum(backlog_hist[d].values()) for d in bdays]
        if backlog_series:
            backlog_series[-1] = current_backlog
        prev_backlog = backlog_series[-2] if len(backlog_series) > 1 else 0

        return jsonify(
            {
                "processed_today": processed_today,
                "imported_today": imported_today,
                "current_backlog": current_backlog,
                "prev_imported": counts[cdays[-2]]["imported"] if len(cdays) > 1 else 0,
                "prev_processed": counts[cdays[-2]]["processed"] if len(cdays) > 1 else 0,
                "prev_backlog": prev_backlog,
                "series": {
                    "imported": [counts[d]["imported"] for d in cdays],
                    "processed": [counts[d]["processed"] for d in cdays],
                    "backlog": backlog_series,
                },
            }
        )

    except Exception as e:
        current_app.logger.error(f"Failed to fetch kpi_stats report: {e}")
        return jsonify({"error": _("An unexpected error occurred")}), 500


@require_permission("dashboard.view")
@cache.cached(
    timeout=120,
    key_prefix=lambda: f"hourly_stats_{session.get('userid')}_{session.get('process_name_dashboard','all')}_{session.get('tenant_scope','')}",  # type: ignore[arg-type]
    response_filter=_cacheable_response,
)
def dashboard_hourly_stats():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    allowed_processes = _allowed_processes()
    process_name = session.get("process_name_dashboard", "all")
    target_processes = normalize_process_selection(process_name, allowed_processes)[1]

    if not target_processes:
        return jsonify({"labels": [f"{h:02d}:00" for h in range(24)], "data": [0] * 24})

    try:
        configs = _statconfig_sources(target_processes)

        if not configs:
            return jsonify({"labels": [f"{h:02d}:00" for h in range(24)], "data": [0] * 24})

        default_configs, ms02_rows = _split_stat_configs(configs)

        sub_queries = []
        for row in default_configs:
            condition = f" {row.extra_condition}" if row.extra_condition else ""
            sub_queries.append(f"""
                SELECT DATEPART(hour, {row.export_column}) as h, COUNT(*) as c
                FROM [{DB_STATISTICS}].{row.table}
                WHERE CAST({row.export_column} AS DATE) = CAST(GETDATE() AS DATE) {condition}
                GROUP BY DATEPART(hour, {row.export_column})
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


@require_permission("dashboard.view")
@cache.cached(
    timeout=300,
    key_prefix=lambda: f"avg_proc_time_{session.get('userid')}_{session.get('process_name_dashboard','all')}_{session.get('tenant_scope','')}",  # type: ignore[arg-type]
    response_filter=_cacheable_response,
)
def dashboard_avg_processing_time():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    allowed_processes = _allowed_processes()
    process_name = session.get("process_name_dashboard", "all")
    target_processes = normalize_process_selection(process_name, allowed_processes)[1]

    if not target_processes:
        return jsonify({"avg_minutes": None, "avg_display": "—"})

    try:
        series_sec = _avg_processing_by_day(target_processes, 7)
        today = datetime.now().date()
        window = [today - timedelta(days=i) for i in range(6, -1, -1)]
        avg_sec = series_sec.get(today)
        prev_sec = series_sec.get(today - timedelta(days=1))

        avg_minutes, avg_display = (
            format_avg_processing_display(avg_sec) if avg_sec is not None else (None, "—")
        )
        return jsonify(
            {
                "avg_minutes": avg_minutes,
                "avg_display": avg_display,
                "prev_avg_minutes": round(prev_sec / 60, 1) if prev_sec is not None else None,
                # minutes, None where no documents finished that day
                "series": [
                    round(series_sec[d] / 60, 1) if d in series_sec else None for d in window
                ],
            }
        )

    except Exception as e:
        current_app.logger.error(f"Failed to fetch avg_processing_time: {e}")
        return jsonify({"error": _("An unexpected error occurred")}), 500


_BACKLOG_SERIES_CAP = 4


@require_permission("dashboard.view")
@cache.cached(
    timeout=300,
    key_prefix=make_cache_key,  # type: ignore[arg-type]  # callable prefix, stubs say str
    response_filter=_cacheable_response,
)
def dashboard_backlog_trend():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    empty = {"labels": [], "series": [], "total": 0, "prev_total": 0}
    allowed_processes = _allowed_processes()
    process_name = session.get("process_name_dashboard", "all")
    target_processes = normalize_process_selection(process_name, allowed_processes)[1]
    if not target_processes:
        return jsonify(empty)

    days = normalize_range(request.args.get("range") or session.get("dashboard_range"))

    try:
        history = _backlog_history(target_processes, days)
        if not history:
            return jsonify(empty)

        today = datetime.now().date()
        window = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]

        current = history.get(max(history), {})
        ranked = sorted(current, key=lambda n: (-current[n], n))
        if len(target_processes) == 1:
            groups = [(_("Backlog"), list(current))]
        elif len(ranked) > _BACKLOG_SERIES_CAP:
            groups = [(n, [n]) for n in ranked[:_BACKLOG_SERIES_CAP]]
            groups.append((_("Other"), ranked[_BACKLOG_SERIES_CAP:]))
        else:
            groups = [(n, [n]) for n in ranked]

        series = [
            {
                "name": label,
                "values": [sum(history.get(d, {}).get(n, 0) for n in members) for d in window],
                "current": sum(current.get(n, 0) for n in members),
            }
            for label, members in groups
        ]
        totals = [sum(s["values"][i] for s in series) for i in range(len(window))]
        return jsonify(
            {
                "labels": [d.isoformat() for d in window],
                "series": series,
                "total": totals[-1] if totals else 0,
                "prev_total": totals[-2] if len(totals) > 1 else 0,
            }
        )
    except Exception as e:
        current_app.logger.error(f"Failed to fetch backlog_trend: {e}")
        return jsonify({"error": _("An unexpected error occurred")}), 500


# ----------------------------- dashboard page + filter ----------------------------- #


@require_permission("dashboard.view")
def dashboard():
    scoped_tenant = apply_tenant_scope()  # 0097; before the try, see its docstring
    try:
        if "username" not in session:
            return redirect(url_for("login"))

        logged_in_user = session.get("username", "Unknown")
        userid = session.get("userid", "Unknown")
        fullname = session.get("fullname")
        # Sign-in note shows once, on the first dashboard render after login (issue #146).
        show_note = session.pop("show_login_note", False)
        login_at = session.get("login_at") if show_note else None
        prev_login_at = session.get("prev_login_at") if show_note else None

        allowed_processes = _allowed_processes()

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
            dashboard_tenant=scoped_tenant,
            page_visibility=page_visibility(),
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
    allowed_processes = _allowed_processes()
    process_name = normalize_process_selection(
        request.json.get("process_name", "all"), allowed_processes
    )[0]
    session["process_name_dashboard"] = process_name
    return jsonify({"ok": True, "process_name": process_name})


# ----------------------------- recent activity ----------------------------- #


@require_permission("dashboard.view")
@cache.cached(
    timeout=120,
    key_prefix=lambda: f"recent_activity_{session.get('userid')}_{session.get('process_name_dashboard','all')}_{session.get('tenant_scope','')}",  # type: ignore[arg-type]
)
def api_recent_activity():
    try:
        process_name = session.get("process_name_dashboard", "all")
        allowed_processes = _allowed_processes()
        target_processes = normalize_process_selection(process_name, allowed_processes)[1]

        if not target_processes:
            return jsonify([])

        # (client, process) pairs, NOT two independent client/process
        # IN-lists -- see _pair_predicate's docstring in workitem_sources.py.
        pairs = sorted({(p.split(".")[0], p.split(".")[-1]) for p in target_processes if "." in p})
        activity_ignore_map = get_activity_instances_to_ignore()
        raw_rows = recent_activity_rows(pairs, activity_ignore_map, top=3)

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
        # exc_info: the bare message alone ("'NoneType' object has no attribute
        # 'get'") named neither the file nor the workitem, which is what made
        # the Octo null-body crash so slow to place.
        current_app.logger.error(f"Activity feed error: {e}", exc_info=True)
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
    app.add_url_rule(
        "/api/dashboard/backlog_trend",
        endpoint="dashboard_backlog_trend",
        view_func=dashboard_backlog_trend,
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
