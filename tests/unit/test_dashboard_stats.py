"""Unit tests for the dashboard stats helpers.

Covers `_split_stat_configs` (partitions `dbo.Statconfig` rows by serving client
so the StatisticsDB T-SQL path only sees 'default' rows and the MS02 Postgres
path gets its own rows) and `_ms02_source` (resolves the MS02 stats table +
date columns from those rows, quoting the PascalCase Postgres identifiers).
"""

import types
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from flask import session

import nx_lib.views.dashboard as dv
from nx_lib.views.dashboard import _ms02_source, _split_stat_configs


def _row(client_code, name="p", table=None, exp=None, imp=None):
    return types.SimpleNamespace(
        ClientCode=client_code,
        ProcessName=name,
        TableName=table,
        ExportColumn=exp,
        ImportColumn=imp,
    )


def test_all_default_rows():
    rows = [_row("default", "a"), _row("default", "b")]
    default_rows, ms02_rows = _split_stat_configs(rows)
    assert default_rows == rows
    assert ms02_rows == []


def test_mixed_default_and_ms02():
    d1 = _row("default", "a")
    d2 = _row("default", "b")
    m1 = _row("ms02", "c")
    default_rows, ms02_rows = _split_stat_configs([d1, m1, d2])
    assert default_rows == [d1, d2]
    assert ms02_rows == [m1]


def test_none_client_code_treated_as_default():
    r = _row(None, "a")
    default_rows, ms02_rows = _split_stat_configs([r])
    assert default_rows == [r]
    assert ms02_rows == []


def test_blank_client_code_treated_as_default():
    r = _row("", "a")
    default_rows, ms02_rows = _split_stat_configs([r])
    assert default_rows == [r]
    assert ms02_rows == []


def test_ms02_only():
    m1 = _row("ms02", "a")
    m2 = _row("ms02", "b")
    default_rows, ms02_rows = _split_stat_configs([m1, m2])
    assert default_rows == []
    assert ms02_rows == [m1, m2]


def test_missing_clientcode_attribute_treated_as_default():
    # A row object that doesn't even carry a ClientCode attribute (pre-0024
    # shaped data) must still count as 'default'.
    r = types.SimpleNamespace(ProcessName="a")
    default_rows, ms02_rows = _split_stat_configs([r])
    assert default_rows == [r]
    assert ms02_rows == []


def test_empty_configs():
    default_rows, ms02_rows = _split_stat_configs([])
    assert default_rows == []
    assert ms02_rows == []


# ----------------------------- _ms02_source ----------------------------- #


def test_ms02_source_none_when_empty():
    assert _ms02_source([]) is None


def test_ms02_source_quotes_pascalcase_columns():
    r = _row(
        "ms02", "sydoc.05_PDBS", 'public."DossierStatistik"', "DatumInTempExport", "ImportDate"
    )
    table, exp, imp = _ms02_source([r])
    # TableName passes through verbatim (already schema-qualified + quoted).
    assert table == 'public."DossierStatistik"'
    # Column names get wrapped as Postgres identifiers.
    assert exp == '"DatumInTempExport"'
    assert imp == '"ImportDate"'


def test_ms02_source_dedupes_to_first_row():
    # All MS02 rows point at the same table; we run one query off the first.
    r1 = _row("ms02", "a", 'public."DossierStatistik"', "DatumInTempExport", "ImportDate")
    r2 = _row("ms02", "b", 'public."Other"', "X", "Y")
    table, exp, imp = _ms02_source([r1, r2])
    assert (table, exp, imp) == ('public."DossierStatistik"', '"DatumInTempExport"', '"ImportDate"')


def test_ms02_source_escapes_embedded_quote():
    r = _row("ms02", "a", "public.t", 'we"ird', "ImportDate")
    _table, exp, _imp = _ms02_source([r])
    assert exp == '"we""ird"'


# ------------------- per-leg isolation (default T-SQL leg) ------------------- #
# The existing _row helper deliberately lacks additionalCondition; the route
# reads it, so config-row fakes for route-level tests need their own shape.


def _cfg_row(client, name, table, exp, imp, cond=None):
    return types.SimpleNamespace(
        ClientCode=client,
        ProcessName=name,
        TableName=table,
        ExportColumn=exp,
        ImportColumn=imp,
        additionalCondition=cond,
    )


def _engine_returning(rows):
    """Fake engine: raw_connection().cursor().fetchall() -> rows."""
    cur = MagicMock()
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value = cur
    eng = MagicMock()
    eng.raw_connection.return_value = conn
    return eng


def _dead_engine(msg="StatisticsDB down"):
    eng = MagicMock()
    eng.raw_connection.side_effect = RuntimeError(msg)
    return eng


_PERMS = [
    "dashboard.filter.process.sydoc.Alpha",
    "dashboard.filter.process.sydoc.05_PDBS",
]

_CONFIGS = [
    _cfg_row("default", "sydoc.Alpha", "dbo.tblAlpha", "ExportDate", "ImportDate"),
    _cfg_row(
        "ms02", "sydoc.05_PDBS", 'public."DossierStatistik"', "DatumInTempExport", "ImportDate"
    ),
]


def test_default_stat_rows_returns_rows(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_statistics_db", _engine_returning([(1,)]))
    with app.app_context():
        assert dv._default_stat_rows("SELECT 1") == [(1,)]


def test_default_stat_rows_swallows_and_logs_errors(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    with app.app_context():
        assert dv._default_stat_rows("SELECT 1") == []


def test_processed_over_time_serves_ms02_when_statistics_db_dead(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning(_CONFIGS))
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    today = date.today()
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(today, 7)])

    with app.test_request_context("/api/dashboard/processed_over_time"):
        session["username"] = "u"
        session["userid"] = 990001
        session["permissions"] = _PERMS
        session["process_name_dashboard"] = "all"
        rv = dv.dashboard_processed_over_time.uncached()

    resp, status = rv if isinstance(rv, tuple) else (rv, rv.status_code)
    assert status == 200
    body = resp.get_json()
    assert max(body["data"]) == 7  # the healthy MS02 leg still renders


def test_processed_over_time_default_leg_survives_dead_ms02(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning(_CONFIGS))
    today = date.today()
    monkeypatch.setattr(
        dv,
        "engine_statistics_db",
        _engine_returning([types.SimpleNamespace(d=today, total_count=5)]),
    )
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [])  # PG leg's existing degrade contract

    with app.test_request_context("/api/dashboard/processed_over_time"):
        session["username"] = "u"
        session["userid"] = 990002
        session["permissions"] = _PERMS
        session["process_name_dashboard"] = "all"
        rv = dv.dashboard_processed_over_time.uncached()

    resp, status = rv if isinstance(rv, tuple) else (rv, rv.status_code)
    assert status == 200
    assert max(resp.get_json()["data"]) == 5


def test_processed_over_time_survives_str_typed_default_leg_date(app, monkeypatch):
    # PROD's legacy `DRIVER={SQL Server}` pyodbc driver returns SQL Server DATE
    # columns as Python `str` (not `datetime.date`) — confirmed via live PROD
    # diagnosis, see docs/superpowers/plans/
    # 2026-07-13-dashboard-chart-recent-validations-404.md ("Diagnosis result
    # (2026-07-13, redone 2026-07-14)"). The route's zero-fill loop and the MS02
    # leg both contribute real `datetime.date` keys to the same `counts` dict, so
    # `sorted(counts.keys())` mixed `str` and `datetime.date` and raised
    # `TypeError: '<' not supported between instances of 'datetime.date' and
    # 'str'` on every request touching a default-leg process (83 PROD app.log
    # occurrences over two weeks).
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning(_CONFIGS))
    today = date.today()
    str_date = today.isoformat()  # what the legacy driver actually returns
    monkeypatch.setattr(
        dv,
        "engine_statistics_db",
        _engine_returning([types.SimpleNamespace(d=str_date, total_count=5)]),
    )
    yesterday = today - timedelta(days=1)
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(yesterday, 3)])

    with app.test_request_context("/api/dashboard/processed_over_time"):
        session["username"] = "u"
        session["userid"] = 990006
        session["permissions"] = _PERMS
        session["process_name_dashboard"] = "all"
        rv = dv.dashboard_processed_over_time.uncached()

    resp, status = rv if isinstance(rv, tuple) else (rv, rv.status_code)
    assert status == 200
    body = resp.get_json()
    assert body["labels"] == sorted(body["labels"])  # sort must not raise
    assert body["data"][body["labels"].index(today.isoformat())] == 5
    assert body["data"][body["labels"].index(yesterday.isoformat())] == 3


def test_kpi_stats_serves_ms02_and_backlog_when_statistics_db_dead(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning(_CONFIGS))
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(5, 2)])
    monkeypatch.setattr(dv, "total_backlog_count", lambda pairs: 3)

    with app.test_request_context("/api/dashboard/kpi_stats"):
        session["username"] = "u"
        session["userid"] = 990003
        session["permissions"] = _PERMS
        session["process_name_dashboard"] = "all"
        rv = dv.dashboard_kpi_stats.uncached()

    resp, status = rv if isinstance(rv, tuple) else (rv, rv.status_code)
    assert status == 200
    assert resp.get_json() == {"processed_today": 5, "imported_today": 2, "current_backlog": 3}


def test_kpi_stats_route_still_200s_on_genuinely_quiet_day(app, monkeypatch):
    # Task 58 regression check: the dashboard route's graceful degrade must
    # be untouched by the external API's new strict=True contract -- both a
    # dead Statistics DB (above) and a healthy-but-empty one (here) still
    # 200 through dashboard_kpi_stats (it calls compute_today_stats with no
    # strict kwarg, i.e. strict=False).
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning([_CONFIGS[0]]))
    monkeypatch.setattr(dv, "engine_statistics_db", _engine_returning([(None, None)]))
    monkeypatch.setattr(dv, "total_backlog_count", lambda pairs: 0)

    with app.test_request_context("/api/dashboard/kpi_stats"):
        session["username"] = "u"
        session["userid"] = 990011
        session["permissions"] = _PERMS
        session["process_name_dashboard"] = "all"
        rv = dv.dashboard_kpi_stats.uncached()

    resp, status = rv if isinstance(rv, tuple) else (rv, rv.status_code)
    assert status == 200
    assert resp.get_json() == {"processed_today": 0, "imported_today": 0, "current_backlog": 0}


# ---- Phase-review fix: dashboard_kpi_stats had the SAME cross-product bug
# Task 14 fixed for the workitems list (cc167e1), independently -- it built
# two separately-uniqued proc/client lists instead of granted (client,
# process) pairs. _PERMS above only ever grants one client ("sydoc"), which
# can't expose the bug (no second client to cross with); this test grants two
# DIFFERENT clients to prove only the granted pairs reach total_backlog_count.


def test_kpi_stats_backlog_derives_granted_pairs_not_cross_product(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning([]))
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [])

    calls = []

    def _fake_total_backlog(pairs):
        calls.append(pairs)
        return 0

    monkeypatch.setattr(dv, "total_backlog_count", _fake_total_backlog)

    with app.test_request_context("/api/dashboard/kpi_stats"):
        session["username"] = "u"
        session["userid"] = 990010
        session["permissions"] = [
            "dashboard.filter.process.A.P1",
            "dashboard.filter.process.B.P2",
        ]
        session["process_name_dashboard"] = "all"
        rv = dv.dashboard_kpi_stats.uncached()

    resp, status = rv if isinstance(rv, tuple) else (rv, rv.status_code)
    assert status == 200
    assert len(calls) == 1
    built_pairs = calls[0]
    assert sorted(built_pairs) == [("A", "P1"), ("B", "P2")]
    assert ("A", "P2") not in built_pairs
    assert ("B", "P1") not in built_pairs


def test_hourly_stats_serves_ms02_when_statistics_db_dead(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning(_CONFIGS))
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(9, 4)])

    with app.test_request_context("/api/dashboard/hourly_stats"):
        session["username"] = "u"
        session["userid"] = 990004
        session["permissions"] = _PERMS
        session["process_name_dashboard"] = "all"
        rv = dv.dashboard_hourly_stats.uncached()

    resp, status = rv if isinstance(rv, tuple) else (rv, rv.status_code)
    assert status == 200
    body = resp.get_json()
    assert body["data"][9] == 4
    assert sum(body["data"]) == 4


def test_avg_processing_time_serves_ms02_when_statistics_db_dead(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning(_CONFIGS))
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(120.0,)])

    with app.test_request_context("/api/dashboard/avg_processing_time"):
        session["username"] = "u"
        session["userid"] = 990005
        session["permissions"] = _PERMS
        session["process_name_dashboard"] = "all"
        rv = dv.dashboard_avg_processing_time.uncached()

    resp, status = rv if isinstance(rv, tuple) else (rv, rv.status_code)
    assert status == 200
    assert resp.get_json()["avg_display"] == "2min"


def test_cacheable_response_rejects_error_statuses():
    ok_resp = types.SimpleNamespace(status_code=200)
    assert dv._cacheable_response(ok_resp)
    assert dv._cacheable_response((ok_resp, 200))
    assert not dv._cacheable_response(("body", 500))
    assert not dv._cacheable_response(("body", 401))


# --------------------------- compute_today_stats --------------------------- #
# Session-free seam shared by the dashboard KPI card and the external API v1
# (/api/v1/stats/today). Extracted verbatim from dashboard_kpi_stats, so the
# numbers must match the route's previous inline computation exactly.


def test_compute_today_stats_sums_both_legs(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning(_CONFIGS))
    # T-SQL leg returns (processed, imported) = (5, 7); MS02 leg adds (2, 3).
    monkeypatch.setattr(dv, "engine_statistics_db", _engine_returning([(5, 7)]))
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(2, 3)])
    with app.app_context():
        assert dv.compute_today_stats(["sydoc.Alpha", "sydoc.05_PDBS"]) == (10, 7)


def test_compute_today_stats_ms02_leg_survives_dead_statistics_db(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning(_CONFIGS))
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(5, 2)])
    with app.app_context():
        assert dv.compute_today_stats(["sydoc.Alpha", "sydoc.05_PDBS"]) == (2, 5)


def test_compute_today_stats_null_sums_count_as_zero(app, monkeypatch):
    # A Statconfig table with no rows today yields SUM(...) = (NULL, NULL).
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning([_CONFIGS[0]]))
    monkeypatch.setattr(dv, "engine_statistics_db", _engine_returning([(None, None)]))
    with app.app_context():
        assert dv.compute_today_stats(["sydoc.Alpha"]) == (0, 0)


def test_compute_today_stats_raises_when_nexora_db_down(app, monkeypatch):
    # Fail-through contract: the Statconfig read must RAISE (not zero-fill) so
    # the dashboard's uncached-500 semantics and the API's JSON 500 both hold --
    # zeros here would be cached/reported as real numbers on a NexoraDB blip.
    monkeypatch.setattr(dv, "engine_nexora_db", _dead_engine("NexoraDB down"))
    with app.app_context(), pytest.raises(Exception):  # noqa: B017 -- any exception must propagate
        dv.compute_today_stats(["sydoc.Alpha"])


# --------------------- compute_today_stats(strict=...) (Task 58) -------------- #
# Task 58: a Statistics-DB outage must not be indistinguishable from a
# genuinely quiet day. Both stat-row legs' aggregate queries return exactly
# one row (of NULLs) even when zero rows match, so [] from a leg already
# meant "the query itself failed" -- the bug was that failure was always
# swallowed. strict=True (the external API's setting) re-raises instead;
# strict=False (the default, the dashboard's setting) keeps degrading.


def test_default_stat_rows_strict_reraises_on_failure(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    with app.app_context(), pytest.raises(Exception):  # noqa: B017
        dv._default_stat_rows("SELECT 1", strict=True)


def test_default_stat_rows_non_strict_still_swallows(app, monkeypatch):
    # Regression pin: omitting strict (the dashboard's call shape) must keep
    # the pre-existing degrade-to-[] contract.
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    with app.app_context():
        assert dv._default_stat_rows("SELECT 1") == []


def test_ms02_stat_rows_strict_reraises_on_failure(app, monkeypatch):
    eng = MagicMock()
    eng.raw_connection.side_effect = RuntimeError("ms02 down")
    monkeypatch.setattr(dv, "engine_ms02_stats_pg", eng)
    with app.app_context(), pytest.raises(Exception):  # noqa: B017
        dv._ms02_stat_rows("SELECT 1", strict=True)


def test_ms02_stat_rows_strict_still_empty_when_unconfigured(app, monkeypatch):
    # An unconfigured MS02 engine is "not applicable", never a failure --
    # strict must not turn that into a raise.
    monkeypatch.setattr(dv, "engine_ms02_stats_pg", None)
    with app.app_context():
        assert dv._ms02_stat_rows("SELECT 1", strict=True) == []


def test_compute_today_stats_strict_raises_on_dead_statistics_db(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning([_CONFIGS[0]]))
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine("Statistics DB down"))
    with app.app_context(), pytest.raises(Exception):  # noqa: B017
        dv.compute_today_stats(["sydoc.Alpha"], strict=True)


def test_compute_today_stats_strict_still_zeros_on_genuinely_quiet_day(app, monkeypatch):
    # A healthy engine with no matching rows today -- the aggregate query
    # still returns one row of NULLs (not []) -- must stay 200 zeros even
    # under strict=True. This is the case that proves the fix isn't just
    # "always 500 now".
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning([_CONFIGS[0]]))
    monkeypatch.setattr(dv, "engine_statistics_db", _engine_returning([(None, None)]))
    with app.app_context():
        assert dv.compute_today_stats(["sydoc.Alpha"], strict=True) == (0, 0)


def test_compute_today_stats_non_strict_default_still_degrades(app, monkeypatch):
    # Regression pin: the dashboard's call site (no strict kwarg) must keep
    # serving the healthy leg's numbers when Statistics DB is dead -- Task 58
    # only changes the external API's contract.
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning(_CONFIGS))
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(5, 2)])
    with app.app_context():
        assert dv.compute_today_stats(["sydoc.Alpha", "sydoc.05_PDBS"]) == (2, 5)


# ------------------------- backlog KPI: real C+A count ----------------------- #
# `status: "Ready"` means "current backlog" -- and the product owner defines the
# backlog, unambiguously, as "the workitems currently on the activity type
# 'C+A'". That is a LIVE Octo-runtime fact (the workitem's current
# ActivityInstance's ActivityType.Name), already implemented correctly by
# `total_backlog_count()` / `SqlServerSource.backlog_count` in
# workitem_sources.py (a join to `t_ActivityTypes.Name = 'C+A'`).
#
# `Statconfig` -- the widget engine's own config table -- has NO activity-type /
# stage column at all (only Import/Export "entered tracking"/"fully done"
# timestamps), so the Statistics-DB-driven `_build_kpi_sql` structurally cannot
# express "currently on C+A" for any process. An earlier fix approximated it as
# "entered, not yet exported" (`Import IS NOT NULL AND Export IS NULL`); that was
# based on a wrong assumption and is now removed. Instead `build_widget_query`
# routes the one shape `total_backlog_count` can honestly answer -- a plain
# count with no doc-field filter -- to that function, and `_build_kpi_sql`
# returns an explicit empty (honest no_data) for every other status:"Ready"
# shape rather than approximate a wrong headline number.


def _kpi_widget(kind="count"):
    return {"type": "kpi", "config": {"metric": {"kind": kind}}}


def test_backlog_kpi_routes_to_total_backlog_count(monkeypatch):
    # count + status:"Ready" + no docFilters is the ONLY shape total_backlog_count
    # can answer. build_widget_query must intercept it BEFORE touching Statconfig,
    # derive granted (client, process) pairs exactly like the legacy
    # dashboard_kpi_stats call site (client = segment before the dot, process =
    # segment after -- NEVER split into independent client/process lists, which
    # would authorize the cross product), and feed the C+A count through the
    # normal execution path as a literal select.
    calls = []

    def _fake_total_backlog(pairs):
        calls.append(pairs)
        return 7

    monkeypatch.setattr(dv, "total_backlog_count", _fake_total_backlog)
    widget = _kpi_widget("count")
    filters = {"status": "Ready"}
    allowed = ["zzztest.AlphaProc", "zzztest.BetaProc"]
    queries = dv.build_widget_query(widget, filters, allowed)

    assert len(queries) == 1
    engine, sql, params = queries[0]
    assert engine is dv.engine_nexora_db
    assert sql == "SELECT ?"
    assert params == [7]
    # Never the old wrong approximation, never an unconditional count.
    assert "1=1" not in sql
    assert "IS NULL" not in sql
    assert "IS NOT NULL" not in sql
    # Same (client, process) pair derivation as the existing correct
    # dashboard_kpi_stats site -- a plain list of tuples, not two independent
    # client/process lists.
    assert calls == [[("zzztest", "AlphaProc"), ("zzztest", "BetaProc")]]


def test_backlog_kpi_value_executes_via_run_widget_queries(app, monkeypatch):
    # The literal-select mechanism (`SELECT ?`) must actually execute through the
    # UNCHANGED _run_widget_queries KPI branch (engine_nexora_db.raw_connection()
    # + pyodbc) and yield exactly the C+A count -- not the old predicate, not 0.
    monkeypatch.setattr(dv, "total_backlog_count", lambda pairs: 7)
    widget = _kpi_widget("count")
    filters = {"status": "Ready"}
    allowed = ["zzztest.AlphaProc"]
    with app.app_context():
        queries = dv.build_widget_query(widget, filters, allowed)
        result = dv._run_widget_queries(widget, queries)

    assert result == {"value": 7.0, "unit": None}


def test_backlog_kpi_with_docfilters_does_not_call_total_backlog_count(monkeypatch):
    # A doc-field filter is something total_backlog_count has no notion of, so the
    # backlog shortcut must NOT fire; it falls through to Statconfig +
    # _build_kpi_sql, which returns an honest empty (build_widget_query -> []).
    called = MagicMock()
    monkeypatch.setattr(dv, "total_backlog_count", called)
    # A real Statconfig row is returned so the fall-through genuinely reaches
    # _build_kpi_sql (rather than bailing at the empty-configs guard).
    cfg = _cfg_row("default", "sydoc.Alpha", "dbo.tblAlpha", "ExportDate", "ImportDate")
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning([cfg]))

    widget = _kpi_widget("count")
    filters = {"status": "Ready", "docFilters": [{"field": "amount", "value": "5"}]}
    allowed = ["sydoc.Alpha"]
    queries = dv.build_widget_query(widget, filters, allowed)

    assert queries == []
    called.assert_not_called()


def test_build_kpi_sql_status_ready_count_returns_honest_empty():
    # A "Ready" count that still reaches _build_kpi_sql (i.e. was not intercepted
    # by build_widget_query) must NOT emit the old "entered, not yet exported"
    # predicate and must NOT emit WHERE 1=1 -- it returns an explicit empty.
    widget = _kpi_widget("count")
    filters = {"status": "Ready"}
    configs = [_cfg_row("default", "sydoc.Alpha", "dbo.tblAlpha", "ExportDate", "ImportDate")]
    assert dv._build_kpi_sql(widget, filters, configs) == ("", [])


def test_build_kpi_sql_status_ready_avg_returns_honest_empty(monkeypatch):
    # avg/sum/min/max + "Ready" cannot be a C+A backlog count -- honest empty.
    monkeypatch.setattr(dv, "_resolve_aggregation_column", lambda p, f: "AmountCol")
    widget = {"type": "kpi", "config": {"metric": {"kind": "avg", "field": "amount"}}}
    filters = {"status": "Ready"}
    configs = [_cfg_row("default", "sydoc.Alpha", "dbo.tblAlpha", "ExportDate", "ImportDate")]
    assert dv._build_kpi_sql(widget, filters, configs) == ("", [])


def test_build_kpi_sql_status_ready_with_docfilters_returns_honest_empty(monkeypatch):
    # docFilters + "Ready" -> honest empty (never the old backlog predicate).
    monkeypatch.setattr(dv, "_resolve_aggregation_column", lambda p, f: "SomeCol")
    widget = _kpi_widget("count")
    filters = {"status": "Ready", "docFilters": [{"field": "x", "value": "y"}]}
    configs = [_cfg_row("default", "sydoc.Alpha", "dbo.tblAlpha", "ExportDate", "ImportDate")]
    assert dv._build_kpi_sql(widget, filters, configs) == ("", [])


def test_kpi_status_done_unaffected_by_backlog_predicate():
    # Regression guard: only "Ready" gets the new backlog predicate. "Done"
    # (and any other/no status) must keep behaving like a plain count, still
    # respecting an explicit date range on the export column.
    widget = _kpi_widget()
    filters = {
        "status": "Done",
        "datePreset": "custom",
        "dateFrom": "2026-01-01",
        "dateTo": "2026-01-31",
    }
    configs = [_cfg_row("default", "sydoc.Alpha", "dbo.tblAlpha", "ExportDate", "ImportDate")]
    sql, params = dv._build_kpi_sql(widget, filters, configs)
    assert "ImportDate IS NOT NULL" not in sql
    assert "ExportDate IS NULL" not in sql
    assert "CAST(ExportDate AS DATE) >= ?" in sql
    assert "CAST(ExportDate AS DATE) <= ?" in sql


# --------------------- _build_categorical_sql GROUP BY --------------------- #
# Regression guard for a T-SQL correctness bug: when the widget's dimension
# resolves to the "?" bound-parameter sentinel (a constant label, e.g.
# dim=="processname"), the per-config subquery must NOT emit "GROUP BY 1" --
# in T-SQL that groups by the literal constant 1, not by ordinal position
# (unlike MySQL/Postgres/SQLite), so it 500s. A single-row aggregate with a
# bound constant label needs no GROUP BY at all. Real-column dimensions must
# keep grouping by the resolved column.


def _categorical_widget(dimension, kind="count", top_n=5, sort="desc"):
    return {
        "type": "categorical",
        "config": {"dimension": dimension, "metric": {"kind": kind}, "topN": top_n, "sort": sort},
    }


def _inner_subquery(sql):
    """Pull out the parenthesized UNION-ALL body `_build_categorical_sql` wraps
    as `t`, i.e. the part actually built by the buggy `group_by` line -- as
    opposed to the outer `GROUP BY dim` (grouping by a real column alias,
    always correct, untouched by this fix)."""
    return sql.split("FROM (", 1)[1].rsplit(") t", 1)[0]


def test_categorical_constant_dim_omits_group_by():
    widget = _categorical_widget("processname")
    filters = {}
    configs = [_cfg_row("default", "sydoc.Alpha", "dbo.tblAlpha", "ExportDate", "ImportDate")]
    sql, params = dv._build_categorical_sql(widget, filters, configs)
    inner = _inner_subquery(sql)
    assert "GROUP BY" not in inner
    assert "GROUP BY 1" not in sql
    # the constant label is still bound as a param, not inlined.
    assert "SELECT ? AS dim" in inner
    assert params == ["sydoc.Alpha"]


def test_categorical_real_column_dim_keeps_group_by(monkeypatch):
    monkeypatch.setattr(dv, "_resolve_aggregation_column", lambda p, f: "DocTypeCol")
    widget = _categorical_widget("doctype")
    filters = {}
    configs = [_cfg_row("default", "sydoc.Alpha", "dbo.tblAlpha", "ExportDate", "ImportDate")]
    sql, params = dv._build_categorical_sql(widget, filters, configs)
    inner = _inner_subquery(sql)
    assert "GROUP BY DocTypeCol" in inner
    assert "SELECT DocTypeCol AS dim" in inner


def test_categorical_dim_never_used_as_raw_sql_only_whitelisted_columns(monkeypatch):
    # `dim` is only ever (a) compared against the two fixed literals
    # "processname"/"status", or (b) passed to `_resolve_aggregation_column`,
    # which looks the field up in the DB-backed SearchConfig column map --
    # never string-formatted into the query itself. Simulate an
    # attacker-controlled/unmapped dimension string (not in the whitelist) and
    # confirm it never reaches the generated SQL: the resolver reports "no
    # mapping" (None), so the row is skipped and the query comes back honestly
    # empty, exactly as it would for any other unmapped field key.
    monkeypatch.setattr(dv, "_resolve_aggregation_column", lambda p, f: None)
    malicious_dim = "1; DROP TABLE dbo.Statconfig--"
    widget = _categorical_widget(malicious_dim)
    filters = {}
    configs = [_cfg_row("default", "sydoc.Alpha", "dbo.tblAlpha", "ExportDate", "ImportDate")]
    sql, params = dv._build_categorical_sql(widget, filters, configs)
    assert sql == ""
    assert params == []
    assert malicious_dim not in sql
