"""e2e: the Advanced AI panel's Agent sub-mode (Surface C) — Task 7 retry affordance.

A failed agent run (turn cap, or an answer with no artifacts) must offer a
"Try again" button that resends the same question. It hides again once a run
succeeds with an artifact.
"""

import json

from playwright.sync_api import expect

AGENT_DEFINITION = {
    "schemaVersion": 1,
    "source": "docprocessing",
    "visualization": "table",
    "title": "agent stub report",
    "subtitle": None,
    "columns": [{"field": "processname"}],
    "filters": [],
    "sort": [],
    "scope": {"clients": [], "processes": []},
    "rowLimit": 100,
    "groupBy": [],
    "sql": None,
    "sqlTarget": None,
}


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")


def _stub_agent(page, body):
    def handler(route):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    page.route("**/api/reporting/ai/agent", handler)


def _open_agent_mode(page, base):
    page.goto(f"{base}/reporting")
    page.get_by_test_id("reporting-tab-advanced").click()
    page.get_by_test_id("reporting-mode-ai").click()
    page.get_by_test_id("reporting-ai-mode-agent").click()


def test_agent_retry_shown_on_max_turns_then_hidden_after_success(nexora_server, page):
    _login(page, nexora_server)
    question = "how many docs last week"

    fail_payload = {
        "answer": "I could not find a definitive answer.",
        "toolTrace": [{"name": "run_sql", "result": {"ok": False, "error": "boom"}}],
        "turns": 10,
        "stoppedReason": "max_turns",
        "definition": None,
        "sql": None,
    }
    # Stub BEFORE goto — the panel can fire requests as soon as it mounts.
    _stub_agent(page, fail_payload)
    _open_agent_mode(page, nexora_server)

    page.get_by_test_id("reporting-ai-prompt").fill(question)
    page.get_by_test_id("reporting-ai-ask").click()

    retry_btn = page.get_by_test_id("reporting-ai-retry")
    expect(retry_btn).to_be_visible()
    thread = page.get_by_test_id("reporting-ai-agent-thread")
    expect(thread).to_contain_text(question)

    success_payload = {
        "answer": "Here is your report.",
        "toolTrace": [],
        "turns": 2,
        "stoppedReason": "final",
        "definition": AGENT_DEFINITION,
        "sql": None,
    }
    page.unroute("**/api/reporting/ai/agent")
    _stub_agent(page, success_payload)

    retry_btn.click()

    expect(page.get_by_test_id("reporting-ai-retry")).to_be_hidden()
    # Both turns carry the identical question text.
    turns = thread.locator(".reporting-ai-turn")
    expect(turns).to_have_count(2)
    for i in range(2):
        expect(turns.nth(i)).to_contain_text(question)
    page.screenshot(path="var/screenshots/reporting_agent_retry.png")


def test_agent_retry_hidden_on_mode_switch(nexora_server, page):
    """Switching AI submode/surface resets the retry affordance, mirroring the
    errorEl.hidden reset at the same spot."""
    _login(page, nexora_server)
    question = "how many docs last week"

    fail_payload = {
        "answer": "I could not find a definitive answer.",
        "toolTrace": [],
        "turns": 10,
        "stoppedReason": "max_turns",
        "definition": None,
        "sql": None,
    }
    _stub_agent(page, fail_payload)
    _open_agent_mode(page, nexora_server)

    page.get_by_test_id("reporting-ai-prompt").fill(question)
    page.get_by_test_id("reporting-ai-ask").click()
    expect(page.get_by_test_id("reporting-ai-retry")).to_be_visible()

    page.get_by_test_id("reporting-ai-mode-build").click()
    expect(page.get_by_test_id("reporting-ai-retry")).to_be_hidden()
