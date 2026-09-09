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


# --------------------------------------------------------------------------- #
# The Task Scheduler definition. Without it the script ships to the server and
# never runs, which is how #227 originally landed.
# --------------------------------------------------------------------------- #

TASK_XML = MODULE_PATH.parent / "prune-active-sessions-task.xml"


def _task_xml_text() -> str:
    """UTF-16 LE with a BOM, like every Task Scheduler export."""
    raw = TASK_XML.read_bytes()
    assert raw[:2] == b"\xff\xfe", "task XML lost its UTF-16 LE BOM"
    assert len(raw) % 2 == 0, f"odd byte count ({len(raw)}) -- will not decode"
    return raw[2:].decode("utf-16-le")


def test_task_definition_exists_and_ships():
    """It has to reach the server to be importable from there, and ops/ is not
    in deploy.yml's /XD list -- same reasoning as the script itself."""
    assert TASK_XML.is_file(), "no importable task definition next to the script"


def test_task_xml_keeps_its_utf16_encoding():
    """Task Scheduler refuses UTF-8 ("unable to switch the encoding"), and
    .gitattributes marks *.xml binary precisely so normalisation cannot leave an
    odd byte count that no longer decodes. Both halves are asserted here because
    a well-meant `dos2unix` or an editor "fixing" the encoding is silent until
    someone tries to import it on the host."""
    text = _task_xml_text()
    assert "\r\n" in text, "CRLF line endings were normalised away"


def test_task_xml_is_wellformed_and_targets_this_script():
    import xml.etree.ElementTree as ET

    root = ET.fromstring(_task_xml_text())
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    args = root.find(".//t:Arguments", ns).text
    assert "prune_active_sessions.py" in args, "task does not run this script"
    assert "ENVIRONMENT=PROD" in args, (
        "an Exec action cannot set an env var, so the cmd.exe wrapper must; "
        "without it ENVIRONMENT is unset and the script targets the wrong database"
    )
    assert root.find(".//t:UserId", ns).text == "S-1-5-18", "must run as SYSTEM"


def test_task_runs_often_enough_for_the_retention_window():
    """A daily pass against an 8-day window leaves plenty of margin. A trigger
    interval longer than the retention would let rows outlive it."""
    import xml.etree.ElementTree as ET

    mod = _load()
    root = ET.fromstring(_task_xml_text())
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    days = root.find(".//t:ScheduleByDay/t:DaysInterval", ns)
    assert days is not None, "expected a daily calendar trigger"
    assert (
        int(days.text) * 24 * 60 < mod.RETENTION_MINUTES
    ), "the task runs less often than the retention window"


def test_deploy_registers_every_task_definition():
    """A task XML in the tree that deploy.yml never registers is inert -- which
    is exactly how the prune shipped and ran zero times. Any definition added
    later must be wired into the deploy step, so this discovers them rather than
    listing them."""
    repo = MODULE_PATH.parents[2]
    workflow = (repo / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    definitions = sorted(p.name for p in repo.glob("ops/**/*-task.xml"))
    assert definitions, "no task definitions found -- glob is wrong"
    unregistered = [name for name in definitions if name not in workflow]
    assert not unregistered, f"task definitions never registered by deploy.yml: {unregistered}"


def test_deploy_registration_is_idempotent_and_verified():
    """/f so re-running a deploy is safe, and a /query afterwards because
    'schtasks /create returned 0' and 'the task exists' are different claims."""
    repo = MODULE_PATH.parents[2]
    workflow = (repo / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    step = workflow.split("Register scheduled tasks", 1)
    assert len(step) == 2, "the deploy step is gone"
    body = step[1]
    assert "schtasks /create /xml $t.Xml /tn $t.Name /f" in body, "not idempotent"
    assert "schtasks /query" in body, "registration is claimed but never verified"
    assert "$LASTEXITCODE" in body, "schtasks is a native exe; $? does not report its failure"
