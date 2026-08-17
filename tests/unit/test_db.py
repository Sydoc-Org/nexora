"""Unit tests for nx_lib.db — engine URL builder + ping probes."""

import threading
import time
from unittest.mock import patch

from sqlalchemy import create_engine

from nx_lib.db import (
    _ping_db_probe,
    engine_nexora_db,
    get_db_url,
    ping_db,
    ping_dbs_parallel,
)


def test_get_db_url_uses_default_server():
    url = get_db_url("NEXORA_TEST")
    assert url.startswith("mssql+pyodbc:///?odbc_connect=")
    assert "DATABASE%3DNEXORA_TEST" in url
    # default server (DB_SERVER_PRD from config) must end up in the URL
    assert "SERVER" in url


def test_get_db_url_uses_explicit_server():
    url = get_db_url("NEXORA_TEST", s="custom.host.local")
    assert "custom.host.local" in url
    assert "DATABASE%3DNEXORA_TEST" in url


def test_get_db_url_encodes_password_in_odbc_string():
    # The URL is URL-encoded; raw password chars never appear as-is at the
    # query layer. Just verify it's a quoted blob, not raw odbc=foo.
    url = get_db_url("X")
    assert "DRIVER%3D" in url  # %3D == '='
    assert "{SQL Server}" not in url  # would mean unencoded braces leaked


def test_ping_db_probe_works_on_live_engine():
    """Direct probe path — no timeout wrapper. Should succeed on NEXORA_TEST."""
    # No assertion needed; just must not raise.
    _ping_db_probe(engine_nexora_db)


def test_ping_db_ok_for_live_engine():
    result = ping_db(engine_nexora_db, "nexora", timeout_s=5.0)
    assert result["ok"] is True
    assert result["label"] == "nexora"
    assert result["error"] is None
    assert isinstance(result["latency_ms"], int)
    assert result["latency_ms"] >= 0


def test_ping_db_error_for_unreachable_engine():
    bad = create_engine(
        "mssql+pyodbc:///?odbc_connect="
        "DRIVER%3D%7BSQL+Server%7D%3B"
        "SERVER%3Ddoes-not-exist.invalid%2C1433%3B"
        "DATABASE%3Dnone%3B"
        "UID%3Du%3B"
        "PWD%3Dp%3B"
    )
    result = ping_db(bad, "bad", timeout_s=2.0)
    assert result["ok"] is False
    assert result["error"]  # non-empty error string
    assert result["label"] == "bad"


def test_ping_db_timeout_when_probe_slow():
    """If the probe takes longer than timeout_s, return ok=False, error='timeout'."""

    # The probe blocks until the test explicitly releases it — it never
    # completes while ping_db is waiting. This is deliberate: a fixed-duration
    # sleep raced against the timeout is flaky, because Future.result(timeout)
    # only waits *up to* timeout for a notification, then re-checks state. Under
    # load (e.g. the full pre-push suite) the main thread can be descheduled
    # past the sleep, so the future is already FINISHED at the re-check and
    # result() returns success instead of raising TimeoutError. Blocking until
    # release means the future is never FINISHED during the wait, so the timeout
    # path fires deterministically regardless of scheduling.
    release = threading.Event()

    def blocking_probe(_engine):
        release.wait(timeout=30)  # 30s is a safety cap; finally releases first

    try:
        with patch("nx_lib.db._ping_db_probe", side_effect=blocking_probe):
            result = ping_db(engine_nexora_db, "slow", timeout_s=0.1)
        assert result["ok"] is False
        assert result["error"] == "timeout"
        assert result["latency_ms"] == 100  # int(timeout_s * 1000)
    finally:
        # Unblock the worker thread so it doesn't linger on the shared executor.
        release.set()


def test_ping_dbs_parallel_runs_concurrently():
    targets = [
        (engine_nexora_db, "a"),
        (engine_nexora_db, "b"),
        (engine_nexora_db, "c"),
    ]
    t0 = time.perf_counter()
    results = ping_dbs_parallel(targets, timeout_s=5.0)
    elapsed = time.perf_counter() - t0
    assert len(results) == 3
    assert all(r["ok"] for r in results)
    # Concurrent execution: total should be well under 3x single ping.
    # Each ping is sub-100ms locally; concurrent total should fit in 1.5s.
    assert elapsed < 1.5, f"parallel ping took {elapsed:.2f}s — looks sequential"


def test_ping_dbs_parallel_preserves_label_order():
    targets = [(engine_nexora_db, f"label_{i}") for i in range(4)]
    results = ping_dbs_parallel(targets, timeout_s=5.0)
    assert [r["label"] for r in results] == [f"label_{i}" for i in range(4)]


def test_ping_dbs_parallel_records_individual_errors():
    """Mix one good engine with one bad engine — only the bad one fails."""
    bad = create_engine(
        "mssql+pyodbc:///?odbc_connect="
        "DRIVER%3D%7BSQL+Server%7D%3B"
        "SERVER%3Ddoes-not-exist.invalid%2C1433%3B"
        "DATABASE%3Dnone%3B"
        "UID%3Du%3B"
        "PWD%3Dp%3B"
    )
    targets = [(engine_nexora_db, "good"), (bad, "bad")]
    results = ping_dbs_parallel(targets, timeout_s=2.0)
    by_label = {r["label"]: r for r in results}
    assert by_label["good"]["ok"] is True
    assert by_label["bad"]["ok"] is False
    assert by_label["bad"]["error"]


def test_ping_dbs_parallel_bounded_by_single_shared_deadline():
    """Regression for the serial-wait bug: the old code awaited
    fut.result(timeout=timeout_s) one future at a time, so N down engines took
    N x timeout_s wall time instead of the documented ~timeout_s. With 3
    engines all blocking past the timeout, total elapsed must stay close to
    ONE timeout_s (not three), and every result must report timed-out status.

    Uses the same blocking-Event pattern as test_ping_db_timeout_when_probe_slow
    (not a fixed sleep) so the probe is deterministically still running when
    the shared deadline fires, regardless of scheduler noise.
    """
    release = threading.Event()

    def blocking_probe(_engine):
        release.wait(timeout=30)  # safety cap; test always releases first

    targets = [
        (engine_nexora_db, "a"),
        (engine_nexora_db, "b"),
        (engine_nexora_db, "c"),
    ]
    timeout_s = 0.2
    try:
        with patch("nx_lib.db._ping_db_probe", side_effect=blocking_probe):
            t0 = time.perf_counter()
            results = ping_dbs_parallel(targets, timeout_s=timeout_s)
            elapsed = time.perf_counter() - t0
    finally:
        release.set()  # unblock the worker threads so they don't linger

    assert len(results) == 3
    assert all(r["ok"] is False and r["error"] == "timeout" for r in results)
    # Bounded by ~one timeout (with slack for scheduling), not 3x serial waits.
    assert elapsed < timeout_s * 2, (
        f"parallel ping of 3 timed-out engines took {elapsed:.2f}s "
        f"(timeout_s={timeout_s}) — looks like serial per-future waiting"
    )
