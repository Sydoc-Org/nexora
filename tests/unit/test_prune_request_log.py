r"""Retention arithmetic for the dbo.Logs pruner (#283).

The dangerous failure here is not the one the session pruner has. Deleting a
session row logs somebody out; deleting a request-log row destroys audit
history that cannot be recovered. So the guard is on the *floor* of the window,
and the delete is batched -- dbo.Logs is unbounded and a single statement over
millions of rows would hold a long lock on a table the admin log viewer reads.

These pin the arithmetic, the batching and the schedule. The delete itself
needs a database and is exercised by the script's own --dry-run.
"""

import importlib.util
import re
import xml.etree.ElementTree as ET
from datetime import timedelta
from pathlib import Path

from nx_lib import config as cfg

MODULE_PATH = Path(__file__).resolve().parents[2] / "ops" / "cleanup" / "prune_request_log.py"
TASK_XML = MODULE_PATH.parent / "prune-request-log-task.xml"
REPO = MODULE_PATH.parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("prune_request_log", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _task_xml_text() -> str:
    raw = TASK_XML.read_bytes()
    assert raw[:2] == b"\xff\xfe", "task XML lost its UTF-16 LE BOM"
    assert len(raw) % 2 == 0, f"odd byte count ({len(raw)}) -- will not decode"
    return raw[2:].decode("utf-16-le")


def test_retention_is_six_months_expressed_in_days():
    """Six months as 180 days on purpose: a calendar month varies and this
    window has to be deterministic, because the same figure is quoted in the
    privacy notice (#260)."""
    assert timedelta(days=180) == cfg.REQUEST_LOG_RETENTION


def test_window_comes_from_config_not_a_restated_number():
    mod = _load()
    assert mod.RETENTION == cfg.REQUEST_LOG_RETENTION
    assert int(cfg.REQUEST_LOG_RETENTION.total_seconds() // 60) == mod.RETENTION_MINUTES


def test_a_too_short_retention_is_refused():
    """Audit history cannot be recovered, so a zero or negative window must trip
    the assert rather than being trusted."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "assert RETENTION_MINUTES >= 24 * 60" in src


def test_delete_keys_on_timestamp_and_uses_minutes():
    """Minutes, not days: expressing the window in days meant flooring it, and a
    floored window can silently collapse (#227)."""
    mod = _load()
    assert "DATEADD(minute, ?, GETDATE())" in mod.DELETE_SQL
    assert "DATEADD(day" not in mod.DELETE_SQL
    assert "[Timestamp]" in mod.DELETE_SQL


def test_delete_is_batched_and_scoped_to_dbo_logs():
    """One statement over millions of rows would hold a long lock on a table the
    admin log viewer queries, and bloat the transaction log."""
    mod = _load()
    assert re.search(r"DELETE TOP \(\d+\)", mod.DELETE_SQL), "delete is not batched"
    assert "FROM dbo.Logs" in mod.DELETE_SQL
    assert mod.BATCH_SIZE > 0
    assert mod.MAX_BATCHES > 0
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "conn.commit()" in src, "batches must commit, or the lock is held anyway"


def test_the_batch_cap_covers_a_plausible_backlog():
    """The cap exists to stop a runaway loop, not to limit real work -- it must
    be far above any backlog the table could hold."""
    mod = _load()
    assert mod.BATCH_SIZE * mod.MAX_BATCHES >= 1_000_000


def test_task_definition_exists_and_keeps_its_encoding():
    text = _task_xml_text()
    assert "\r\n" in text, "CRLF line endings were normalised away"
    root = ET.fromstring(text)
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    args = root.find(".//t:Arguments", ns).text
    assert "prune_request_log.py" in args
    assert "ENVIRONMENT=PROD" in args, (
        "an Exec action cannot set an env var; without the cmd.exe wrapper the "
        "script would target the wrong database"
    )
    assert root.find(".//t:UserId", ns).text == "S-1-5-18"


def test_schedule_does_not_collide_with_the_session_prune():
    """Both run daily; they must not start at the same minute, or two prunes
    contend on the same database at once."""
    ours = ET.fromstring(_task_xml_text())
    sibling_raw = (MODULE_PATH.parent / "prune-active-sessions-task.xml").read_bytes()
    sibling = ET.fromstring(sibling_raw[2:].decode("utf-16-le"))
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    a = ours.find(".//t:StartBoundary", ns).text
    b = sibling.find(".//t:StartBoundary", ns).text
    assert a != b, f"both prunes start at {a}"


def test_deploy_registers_this_task():
    """A task XML the deploy never registers is inert -- exactly how the session
    prune shipped and ran zero times (#280)."""
    workflow = (REPO / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    assert TASK_XML.name in workflow, "the deploy step does not register this task"
