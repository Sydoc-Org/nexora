"""nx --doctor: every curated table source must be readable (#329).

The rail's status dot only proves a database answers. Privera Neuzugaenge sat
green for weeks over a view bound to a database that does not exist, and two
Privera sources failed only in the SQL tab because the read-only login had no
rights on their database. These pin that the doctor tells all three apart.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from nx_lib import cli_doctor
from nx_lib import db as nx_db


def _registry(rows):
    engine = MagicMock()

    @contextmanager
    def connect():
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = rows
        yield conn

    engine.connect = connect
    return engine


@pytest.fixture
def engines(monkeypatch):
    main, ro = object(), object()
    monkeypatch.setattr(nx_db, "engine_statistics_db", main)
    monkeypatch.setattr(nx_db, "engine_statistics_ro", ro)
    return main, ro


def _run(monkeypatch, rows, broken=(), ro_broken=()):
    monkeypatch.setattr(nx_db, "engine_nexora_db", _registry(rows))
    main, ro = nx_db.engine_statistics_db, nx_db.engine_statistics_ro

    def probe(engine, quoted, select_list="*"):
        if engine is main and quoted in broken:
            return "Invalid object name 'X1.dbo.T'."
        if engine is ro and quoted in ro_broken:
            return "The server principal is not able to access the database"
        return None

    monkeypatch.setattr(cli_doctor, "_probe_object", probe)
    return {r.name: r for r in cli_doctor._check_reporting_sources()}


def test_all_readable_is_one_ok_line(monkeypatch, engines):
    got = _run(
        monkeypatch, [("a", "statistics", "dbo.A", None), ("b", "statistics", "01_Db.dbo.B", None)]
    )
    assert got["reporting sources"].status == "ok"
    assert "2 table sources" in got["reporting sources"].detail


def test_a_broken_view_fails_with_the_server_message(monkeypatch, engines):
    got = _run(
        monkeypatch,
        [
            ("privera_neuzugaenge", "statistics", "dbo.v_X", None),
            ("ok_src", "statistics", "dbo.A", None),
        ],
        broken={"[dbo].[v_X]"},
    )
    assert got["privera_neuzugaenge"].status == "fail"
    assert "Invalid object name" in got["privera_neuzugaenge"].detail
    assert "reporting sources" not in got, "no all-clear line when something failed"


def test_read_only_login_gap_is_a_warning_not_a_failure(monkeypatch, engines):
    got = _run(
        monkeypatch,
        [("privera_posteingang", "statistics", "01_Privera_Posteingang.dbo.R", None)],
        ro_broken={"[01_Privera_Posteingang].[dbo].[R]"},
    )
    assert got["reporting sources"].status == "ok"
    assert got["read-only login"].status == "warn"
    assert "privera_posteingang" in got["read-only login"].detail


def test_unconfigured_engine_fails(monkeypatch, engines):
    got = _run(monkeypatch, [("s", "nosuch", "dbo.A", None)])
    assert got["s"].status == "fail"
    assert "not configured" in got["s"].detail


def test_registry_unreachable_is_a_skip_warning(monkeypatch):
    monkeypatch.setattr(nx_db, "engine_nexora_db", None)
    (only,) = cli_doctor._check_reporting_sources()
    assert only.status == "warn"


def test_probe_object_returns_the_first_sql_server_message():
    class FakeOdbcError(Exception):
        pass

    engine = MagicMock()
    err = FakeOdbcError(
        "('42S02', \"[42S02] [Microsoft][ODBC SQL Server Driver][SQL Server]Invalid object name "
        "'SYDOC_Statistik1.dbo.T'. (208) (SQLExecDirectW); [42S02] [Microsoft][ODBC SQL Server "
        'Driver][SQL Server]Could not use view or function (4413)")'
    )
    engine.connect.side_effect = err
    assert (
        cli_doctor._probe_object(engine, "[dbo].[v]")
        == "Invalid object name 'SYDOC_Statistik1.dbo.T'."
    )


def test_probe_uses_the_configured_columns():
    """Probing the registry's columns, not *, catches a field the table lacks
    and works under a column-level grant to the read-only login."""
    cols = '[{"field":"ExportDate"},{"field":"Mandant"}]'
    assert cli_doctor._source_select_list(cols) == "[ExportDate], [Mandant]"
    assert cli_doctor._source_select_list(None) == "*"
    assert cli_doctor._source_select_list("not json") == "*"

    seen = []
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value.execute.side_effect = (
        lambda q: seen.append(str(q)) or MagicMock()
    )
    assert cli_doctor._probe_object(engine, "[dbo].[T]", "[ExportDate], [Mandant]") is None
    assert seen == ["SELECT TOP 0 [ExportDate], [Mandant] FROM [dbo].[T]"]


def test_doctor_runs_the_check():
    import inspect

    assert "_check_reporting_sources()" in inspect.getsource(cli_doctor.run)
