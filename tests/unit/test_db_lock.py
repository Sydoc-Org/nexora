"""The shared-database lock must actually exclude a second holder (#235).

Only scripts/test_db_reset.py still takes the real `nexora_test_suite` (when
resetting the shared NEXORA_TEST by hand); pytest runs on a private per-run
database since #235 and needs no lock. Throwaway resource names keep these
tests independent of whatever else is running.
"""

from __future__ import annotations

import os
import uuid

import pytest

from scripts.db_lock import RESOURCE, SKIP_ENV, hold

pytestmark = pytest.mark.usefixtures()


def _conn():
    """Second, independent SQL session -- the lock is per-session, so a single
    connection could re-acquire its own lock and prove nothing."""
    try:
        from scripts.test_db_reset import connect_test_db

        return connect_test_db()
    except Exception as e:
        pytest.skip(f"NEXORA_TEST unreachable: {e}")


def test_second_holder_is_refused_while_first_holds():
    resource = f"nexora_test_lock_probe_{uuid.uuid4().hex[:12]}"
    first, second = _conn(), _conn()
    try:
        # Entered left to right: first takes the lock, then the second ask for
        # the same resource must be refused. timeout_ms=0 makes that immediate.
        with (
            hold(first, label="first", resource=resource, timeout_ms=0),
            pytest.raises(RuntimeError, match="could not acquire"),
            hold(second, label="second", resource=resource, timeout_ms=0),
        ):
            pytest.fail("second holder acquired a lock the first was holding")
    finally:
        first.close()
        second.close()


def test_lock_is_released_when_the_block_exits():
    resource = f"nexora_test_lock_probe_{uuid.uuid4().hex[:12]}"
    first, second = _conn(), _conn()
    try:
        with hold(first, label="first", resource=resource, timeout_ms=0):
            pass
        # Released, so an unrelated session takes it without waiting.
        with hold(second, label="second", resource=resource, timeout_ms=0) as state:
            assert state != "skipped"
    finally:
        first.close()
        second.close()


def test_skip_env_bypasses_locking(monkeypatch):
    """The escape hatch must not touch the database at all -- it is what you
    reach for when the lock itself is the problem."""
    monkeypatch.setenv(SKIP_ENV, "1")

    class Exploding:
        def cursor(self):
            raise AssertionError("skip must not open a cursor")

    with hold(Exploding(), label="skipped", resource=RESOURCE) as state:
        assert state == "skipped"


def test_real_resource_name_is_stable():
    """CI, the reset script and the suite must contend on the same string;
    a rename that reaches only one of them silently stops serialising."""
    assert RESOURCE == "nexora_test_suite"
    assert SKIP_ENV == "NEXORA_TEST_LOCK_SKIP"
    assert os.environ.get(SKIP_ENV) != "1", "unset NEXORA_TEST_LOCK_SKIP to run this suite"
