"""Unit tests for the dashboard stats helpers.

Covers `_split_stat_configs` (partitions `dbo.Statconfig` rows by serving client
so the StatisticsDB T-SQL path only sees 'default' rows and the MS02 Postgres
path gets its own rows) and `_ms02_source` (resolves the MS02 stats table +
date columns from those rows, quoting the PascalCase Postgres identifiers).
"""

import types
from datetime import date
from unittest.mock import MagicMock

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


def test_kpi_stats_serves_ms02_and_backlog_when_statistics_db_dead(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning(_CONFIGS))
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(5, 2)])
    monkeypatch.setattr(dv, "total_backlog_count", lambda procs, clients: 3)

    with app.test_request_context("/api/dashboard/kpi_stats"):
        session["username"] = "u"
        session["userid"] = 990003
        session["permissions"] = _PERMS
        session["process_name_dashboard"] = "all"
        rv = dv.dashboard_kpi_stats.uncached()

    resp, status = rv if isinstance(rv, tuple) else (rv, rv.status_code)
    assert status == 200
    assert resp.get_json() == {"processed_today": 5, "imported_today": 2, "current_backlog": 3}


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
