"""Unit tests for the dashboard stats helpers.

Covers `_split_stat_configs` (partitions `mapping_config.ProcessSource` rows
by serving client so the StatisticsDB T-SQL path only sees 'default' rows
and the MS02 Postgres path gets its own rows), `_ms02_source` (resolves the
MS02 stats table + date columns from those rows, quoting the PascalCase
Postgres identifiers) and `_statconfig_sources` (the mapping_config-backed
successor to the legacy per-call Statconfig cursor read, #98)."""

import types
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from flask import session

import nx_lib.views.dashboard as dv
from nx_lib.mapping_config import ProcessSource
from nx_lib.views.dashboard import _ms02_source, _split_stat_configs


def _row(client_code, name="p", table=None, exp=None, imp=None):
    return ProcessSource(
        client=client_code,
        process=name,
        table=table,
        alias=None,
        join_condition=None,
        time_filter=None,
        suggestion_time_filter=None,
        export_column=exp,
        import_column=imp,
        workitem_column=None,
        extra_condition=None,
        id_column_type=None,
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
    # table passes through verbatim (already schema-qualified + quoted).
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


# ------------------------- _statconfig_sources ------------------------- #
# Successor to the legacy per-call Statconfig cursor read: reads through
# nx_lib.mapping_config.registry()/sources_for(client=None, ...), raising if
# the registry itself failed to load (parity with the old "Statconfig read
# always RAISES on failure" contract the external API's strict callers and
# the dashboard's uncached-500 depend on).


def test_statconfig_sources_raises_when_registry_unavailable(app, monkeypatch):
    monkeypatch.setattr(dv.mapping_config, "registry", lambda: None)
    with app.app_context(), pytest.raises(Exception):  # noqa: B017
        dv._statconfig_sources(["sydoc.Alpha"])


def test_statconfig_sources_delegates_to_sources_for(app, monkeypatch):
    sentinel = [_row("default", "sydoc.Alpha")]
    monkeypatch.setattr(dv.mapping_config, "registry", lambda: object())
    calls = []

    def _fake_sources_for(client, processes=None):
        calls.append((client, processes))
        return sentinel

    monkeypatch.setattr(dv.mapping_config, "sources_for", _fake_sources_for)
    with app.app_context():
        assert dv._statconfig_sources(["sydoc.Alpha"]) == sentinel
    assert calls == [(None, ["sydoc.Alpha"])]


# ------------------- per-leg isolation (default T-SQL leg) ------------------- #


def _cfg_row(client, name, table, exp, imp, cond=None):
    return ProcessSource(
        client=client,
        process=name,
        table=table,
        alias=None,
        join_condition=None,
        time_filter=None,
        suggestion_time_filter=None,
        export_column=exp,
        import_column=imp,
        workitem_column=None,
        extra_condition=cond,
        id_column_type=None,
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


def _stub_sources(monkeypatch, configs):
    """Replace mapping_config.registry()/sources_for() so _statconfig_sources
    returns `configs` -- the direct successor to monkeypatching
    dv.engine_nexora_db with a fake cursor around the legacy Statconfig SELECT."""
    monkeypatch.setattr(dv.mapping_config, "registry", lambda: object())
    monkeypatch.setattr(
        dv.mapping_config, "sources_for", lambda client, processes=None: list(configs)
    )


def _stub_sources_dead(monkeypatch, msg="NexoraDB down"):
    def _boom():
        raise RuntimeError(msg)

    monkeypatch.setattr(dv.mapping_config, "registry", _boom)


def test_default_stat_rows_returns_rows(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_statistics_db", _engine_returning([(1,)]))
    with app.app_context():
        assert dv._default_stat_rows("SELECT 1") == [(1,)]


def test_default_stat_rows_swallows_and_logs_errors(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    with app.app_context():
        assert dv._default_stat_rows("SELECT 1") == []


def test_processed_over_time_serves_ms02_when_statistics_db_dead(app, monkeypatch):
    _stub_sources(monkeypatch, _CONFIGS)
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
    _stub_sources(monkeypatch, _CONFIGS)
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
    _stub_sources(monkeypatch, _CONFIGS)
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
    _stub_sources(monkeypatch, _CONFIGS)
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
    _stub_sources(monkeypatch, [_CONFIGS[0]])
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
    _stub_sources(monkeypatch, [])
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
    _stub_sources(monkeypatch, _CONFIGS)
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
    _stub_sources(monkeypatch, _CONFIGS)
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
    _stub_sources(monkeypatch, _CONFIGS)
    # T-SQL leg returns (processed, imported) = (5, 7); MS02 leg adds (2, 3).
    monkeypatch.setattr(dv, "engine_statistics_db", _engine_returning([(5, 7)]))
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(2, 3)])
    with app.app_context():
        assert dv.compute_today_stats(["sydoc.Alpha", "sydoc.05_PDBS"]) == (10, 7)


def test_compute_today_stats_ms02_leg_survives_dead_statistics_db(app, monkeypatch):
    _stub_sources(monkeypatch, _CONFIGS)
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(5, 2)])
    with app.app_context():
        assert dv.compute_today_stats(["sydoc.Alpha", "sydoc.05_PDBS"]) == (2, 5)


def test_compute_today_stats_null_sums_count_as_zero(app, monkeypatch):
    # A stat-config source with no rows today yields SUM(...) = (NULL, NULL).
    _stub_sources(monkeypatch, [_CONFIGS[0]])
    monkeypatch.setattr(dv, "engine_statistics_db", _engine_returning([(None, None)]))
    with app.app_context():
        assert dv.compute_today_stats(["sydoc.Alpha"]) == (0, 0)


def test_compute_today_stats_raises_when_registry_unavailable(app, monkeypatch):
    # Fail-through contract: a mapping_config registry load failure (e.g. a
    # dead NexoraDB) must RAISE (not zero-fill) so the dashboard's
    # uncached-500 semantics and the API's JSON 500 both hold -- zeros here
    # would be cached/reported as real numbers on a NexoraDB blip.
    _stub_sources_dead(monkeypatch, "NexoraDB down")
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
    _stub_sources(monkeypatch, [_CONFIGS[0]])
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine("Statistics DB down"))
    with app.app_context(), pytest.raises(Exception):  # noqa: B017
        dv.compute_today_stats(["sydoc.Alpha"], strict=True)


def test_compute_today_stats_strict_still_zeros_on_genuinely_quiet_day(app, monkeypatch):
    # A healthy engine with no matching rows today -- the aggregate query
    # still returns one row of NULLs (not []) -- must stay 200 zeros even
    # under strict=True. This is the case that proves the fix isn't just
    # "always 500 now".
    _stub_sources(monkeypatch, [_CONFIGS[0]])
    monkeypatch.setattr(dv, "engine_statistics_db", _engine_returning([(None, None)]))
    with app.app_context():
        assert dv.compute_today_stats(["sydoc.Alpha"], strict=True) == (0, 0)


def test_compute_today_stats_non_strict_default_still_degrades(app, monkeypatch):
    # Regression pin: the dashboard's call site (no strict kwarg) must keep
    # serving the healthy leg's numbers when Statistics DB is dead -- Task 58
    # only changes the external API's contract.
    _stub_sources(monkeypatch, _CONFIGS)
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(5, 2)])
    with app.app_context():
        assert dv.compute_today_stats(["sydoc.Alpha", "sydoc.05_PDBS"]) == (2, 5)


def test_kpi_daily_counts_sums_both_legs_and_zero_fills(app, monkeypatch):
    """Same predicates as compute_today_stats, one row per day. The default leg
    groups by import date (imported = every row, processed = those exported the
    same day); the MS02 leg counts each column independently."""
    today = date.today()
    monkeypatch.setattr(
        dv,
        "_statconfig_sources",
        lambda tp: [
            _row("default", "t1", "dbo.t1", "ExportDate", "ImportDate"),
            _row("ms02", "p", 'public."D"', "DatumInTempExport", "ImportDate"),
        ],
    )
    monkeypatch.setattr(
        dv,
        "_default_stat_rows",
        lambda sql: [(today, 10, 4), (today - timedelta(days=1), 6, 6)],
    )
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(today, 3)])

    with app.test_request_context():
        out = dv._kpi_daily_counts(["c.p"], 3)

    assert len(out) == 3  # zero-filled window
    assert out[today] == {"imported": 13, "processed": 7}  # 10+3 imported, 4+3 processed
    assert out[today - timedelta(days=1)] == {"imported": 6, "processed": 6}
    assert out[today - timedelta(days=2)] == {"imported": 0, "processed": 0}


def test_kpi_daily_counts_normalizes_str_typed_dates(app, monkeypatch):
    """The legacy `DRIVER={SQL Server}` pyodbc driver returns DATE columns as
    str on PROD -- same trap dashboard_processed_over_time already guards."""
    today = date.today()
    monkeypatch.setattr(
        dv,
        "_statconfig_sources",
        lambda tp: [_row("default", "t1", "dbo.t1", "ExportDate", "ImportDate")],
    )
    monkeypatch.setattr(dv, "_default_stat_rows", lambda sql: [(today.isoformat(), 5, 2)])
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [])

    with app.test_request_context():
        out = dv._kpi_daily_counts(["c.p"], 2)

    assert out[today] == {"imported": 5, "processed": 2}
