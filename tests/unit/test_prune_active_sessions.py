"""Retention arithmetic for the ActiveSessions pruner (#227).

The dangerous failure here is a threshold that dips below the session lifetime:
_enforce_active_session signs a user out the moment their SID is missing from
dbo.ActiveSessions, so deleting a row belonging to a live session would log a
working user out mid-request. These tests pin the arithmetic and the column the
delete keys on; the delete itself needs a database and is exercised by the
script's own --dry-run.
"""

import importlib.util
from datetime import timedelta
from pathlib import Path

from nx_lib import config as cfg

MODULE_PATH = Path(__file__).resolve().parents[2] / "ops" / "cleanup" / "prune_active_sessions.py"


def _load():
    spec = importlib.util.spec_from_file_location("prune_active_sessions", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_script_exists_and_is_deployed():
    """ops/ is NOT in deploy.yml's robocopy /XD list, so the script ships."""
    assert MODULE_PATH.is_file()
    workflow = (MODULE_PATH.parents[2] / ".github" / "workflows" / "deploy.yml").read_text(
        encoding="utf-8"
    )
    xd = next(line for line in workflow.splitlines() if "/XD" in line)
    assert " ops " not in xd, "ops/ became excluded from the deploy mirror"


def test_retention_exceeds_the_session_lifetime():
    mod = _load()
    # the whole point: never delete a row a live session still depends on
    assert mod.RETENTION > cfg.SESSION_LIFETIME


def test_retention_is_lifetime_plus_grace():
    mod = _load()
    assert mod.RETENTION == cfg.SESSION_LIFETIME + cfg.SESSION_ROW_RETENTION_GRACE


def test_current_values_are_24h_plus_7_days():
    """Documents today's numbers so a change to either is a deliberate edit."""
    assert timedelta(hours=24) == cfg.SESSION_LIFETIME
    assert timedelta(days=7) == cfg.SESSION_ROW_RETENTION_GRACE
    assert timedelta(days=8) == _load().RETENTION


def test_retention_clears_the_30_minute_read_window_by_a_wide_margin():
    """Both readers filter to LastSeenAt >= -30 minutes; retention must be far
    beyond that or the pruner could race a row still being displayed."""
    assert timedelta(minutes=30) * 100 < _load().RETENTION


def test_delete_keys_on_last_seen_not_created_at():
    """CreatedAt is login time; a long-lived session would be pruned while in
    use if the delete keyed on it. LastSeenAt is bumped on every request."""
    mod = _load()
    assert "LastSeenAt" in mod.DELETE_SQL
    assert "CreatedAt" not in mod.DELETE_SQL
    assert "LastSeenAt" in mod.COUNT_SQL


def test_delete_is_scoped_to_active_sessions():
    mod = _load()
    assert mod.DELETE_SQL.strip().upper().startswith("DELETE FROM DBO.ACTIVESESSIONS")
    assert "WHERE" in mod.DELETE_SQL.upper()


def test_app_lifetime_comes_from_the_shared_constant():
    """create_app must not restate the lifetime, or the pruner drifts from it."""
    src = (MODULE_PATH.parents[2] / "nx_lib" / "__init__.py").read_text(encoding="utf-8")
    assert 'app.config["PERMANENT_SESSION_LIFETIME"] = cfg.SESSION_LIFETIME' in src
    assert 'PERMANENT_SESSION_LIFETIME"] = timedelta(' not in src


def test_queried_window_is_not_floored_to_whole_days():
    """The bug this replaced: DATEADD took int(total_seconds() // 86400), so
    any sub-day part of the grace was discarded AFTER the guard had passed.

    RETENTION_MINUTES must equal the real window to the minute. With 24h + 7d
    the floor happened to be exact, which is why nothing was visibly wrong.
    """
    mod = _load()
    assert int(mod.RETENTION.total_seconds() // 60) == mod.RETENTION_MINUTES
    assert mod.RETENTION_MINUTES == 8 * 24 * 60


def test_delete_window_uses_minutes_not_days():
    """A day-granular DATEADD cannot express a window like 47 hours; asking for
    one silently got 24. Minutes carry every configuration exactly."""
    mod = _load()
    for sql in (mod.COUNT_SQL, mod.DELETE_SQL):
        assert "DATEADD(minute, ?, GETDATE())" in sql
        assert "DATEADD(day" not in sql, f"day-granular window reintroduced: {sql}"


def test_the_guard_checks_the_value_the_query_uses():
    """The old assert compared timedeltas while the query used a floored int,
    so it could pass on a window that had already collapsed. Both sides of the
    comparison must now be the minute counts."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "assert RETENTION_MINUTES > LIFETIME_MINUTES" in src


def test_a_sub_day_grace_would_still_outlast_a_live_session():
    """The failure mode, reproduced as arithmetic rather than as a claim.

    Flooring a 12-hour lifetime plus 6 hours of grace to whole days gives
    DATEADD(day, 0, ...) -- i.e. now -- which deletes every row and signs out
    every live session. Minute granularity keeps the window above the lifetime
    for every combination, which is what the guard is there to promise.
    """
    for lifetime, grace in (
        (timedelta(hours=24), timedelta(days=7)),
        (timedelta(hours=24), timedelta(hours=23)),
        (timedelta(hours=12), timedelta(hours=6)),
        (timedelta(minutes=90), timedelta(minutes=30)),
    ):
        floored_days = int((lifetime + grace).total_seconds() // 86400)
        minutes = int((lifetime + grace).total_seconds() // 60)
        assert minutes > lifetime.total_seconds() // 60, (lifetime, grace)
        if floored_days == 0:
            # exactly the case that wiped the table; unreachable now
            assert minutes > 0
