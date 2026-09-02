"""Unit tests for the reporting source-health probe (beautify-phase-2c fix
round, finding 2): a slow-to-connect engine must not saturate the small probe
pool for the ODBC driver's ~15s default, and a slow-but-eventually-healthy
engine must not be falsely marked down within the shared deadline."""

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from nx_lib.views.reporting import health as health_mod


def _fake_engine(odbc_connect="DRIVER={SQL Server};SERVER=x;DATABASE=y;UID=u;PWD=p;"):
    url = SimpleNamespace(query={"odbc_connect": odbc_connect})
    return SimpleNamespace(url=url)


def test_probe_engine_passes_login_timeout_to_pyodbc_connect():
    """_probe_engine must connect via pyodbc directly (not the pooled
    engine.raw_connection()) with the bounded login timeout, for any engine
    built from an odbc_connect string."""
    engine = _fake_engine()
    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = ["MyDb"]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    with patch.object(health_mod.pyodbc, "connect", return_value=fake_conn) as connect:
        ok, ms, db_name = health_mod._probe_engine(engine, login_timeout_s=5)

    assert ok is True
    assert db_name == "MyDb"
    connect.assert_called_once_with(engine.url.query["odbc_connect"], timeout=5)


def test_probe_engines_parallel_bounds_a_hanging_connect_within_deadline():
    """A probe whose underlying connect() blocks well past the shared 0.8s
    deadline must not make _probe_engines_parallel itself block past that
    deadline -- it reports ok=False for that engine and returns."""
    slow_engine = _fake_engine("DRIVER={SQL Server};SERVER=down;DATABASE=y;UID=u;PWD=p;")

    def _hangs_forever(*a, **k):
        time.sleep(5)  # much longer than the 0.8s shared deadline
        raise AssertionError("should never reach here inside the test's timeout")

    with patch.object(health_mod.pyodbc, "connect", side_effect=_hangs_forever):
        t0 = time.perf_counter()
        results = health_mod._probe_engines_parallel([slow_engine], timeout_s=0.8)
        elapsed = time.perf_counter() - t0

    assert elapsed < 2.0  # bounded by the shared deadline, not the 5s sleep
    ok, ms, db_name = results[id(slow_engine)]
    assert ok is False
    assert ms is None
    assert db_name is None


def test_probe_engines_parallel_does_not_falsely_mark_a_slow_but_healthy_engine_down():
    """An engine that takes a little while to connect but succeeds well
    within the shared deadline must report ok=True, not a false negative."""
    slow_but_healthy = _fake_engine()

    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = ["SlowButUp"]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    def _slow_connect(*a, **k):
        time.sleep(0.05)  # comfortably inside the 0.8s deadline
        return fake_conn

    with patch.object(health_mod.pyodbc, "connect", side_effect=_slow_connect):
        results = health_mod._probe_engines_parallel([slow_but_healthy], timeout_s=0.8)

    ok, ms, db_name = results[id(slow_but_healthy)]
    assert ok is True
    assert db_name == "SlowButUp"


def test_probe_engine_falls_back_to_raw_connection_when_not_odbc():
    """An engine with no odbc_connect in its URL (non-pyodbc dialect) keeps
    using engine.raw_connection() rather than guessing at a timeout param."""
    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = ["PgDb"]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    engine = SimpleNamespace(url=SimpleNamespace(query={}))
    engine.raw_connection = MagicMock(return_value=fake_conn)

    with patch.object(health_mod.pyodbc, "connect") as connect:
        ok, ms, db_name = health_mod._probe_engine(engine)

    connect.assert_not_called()
    engine.raw_connection.assert_called_once()
    assert ok is True
    assert db_name == "PgDb"


def test_probe_engine_none_engine_returns_not_ok():
    assert health_mod._probe_engine(None) == (False, None, None)
