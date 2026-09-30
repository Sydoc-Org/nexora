r"""The session-file cleanup is scheduled, not just present (#260 review).

cleanup_expired_sessionFiles.ps1 existed for months, but no task definition
and no deploy step pointed at it -- so on PROD it ran only if someone had set it
up by hand, and the var\session files (name, e-mail, permissions per user)
had no guaranteed end. These pin the definition and its registration, the same
way test_prune_request_log.py does for the request-log prune.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

CLEANUP = Path(__file__).resolve().parents[2] / "ops" / "cleanup"
TASK_XML = CLEANUP / "cleanup-session-files-task.xml"
SCRIPT = CLEANUP / "cleanup_expired_sessionFiles.ps1"
REPO = CLEANUP.parents[1]
NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


def _utf16(path: Path) -> str:
    raw = path.read_bytes()
    assert raw[:2] == b"\xff\xfe", f"{path.name} lost its UTF-16 LE BOM"
    assert len(raw) % 2 == 0, f"odd byte count ({len(raw)}) -- will not decode"
    return raw[2:].decode("utf-16-le")


def test_task_definition_runs_the_script_as_system():
    text = _utf16(TASK_XML)
    assert "\r\n" in text, "CRLF line endings were normalised away"
    root = ET.fromstring(text)
    args = root.find(".//t:Arguments", NS).text
    assert SCRIPT.name in args
    assert "-ExecutionPolicy Bypass" in args
    assert root.find(".//t:UserId", NS).text == "S-1-5-18"
    assert root.find(".//t:URI", NS).text == r"\sydoc\nexora\Cleanup Session Files"


def test_schedule_does_not_collide_with_the_prunes():
    ours = ET.fromstring(_utf16(TASK_XML)).find(".//t:StartBoundary", NS).text
    for sibling in ("prune-active-sessions-task.xml", "prune-request-log-task.xml"):
        theirs = ET.fromstring(_utf16(CLEANUP / sibling)).find(".//t:StartBoundary", NS).text
        assert ours != theirs, f"cleanup and {sibling} both start at {ours}"


def test_script_keeps_the_24_hour_window():
    """SESSION_LIFETIME is 24 hours; the script must not delete a live session."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert "AddHours(-24)" in src
    assert "exit 1" in src, "a failed delete must show in the Task Scheduler history"


def test_deploy_registers_this_task():
    workflow = (REPO / ".github" / "workflows" / "deploy-env.yml").read_text(encoding="utf-8")
    assert TASK_XML.name in workflow, "the deploy step does not register this task"
