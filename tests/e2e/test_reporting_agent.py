"""e2e: the shared AI chat panel, opened from the Advanced tab.

Task 3 retired the old Advanced "Ask AI" mode toggle (`#rpModeAi` /
`reporting-mode-ai`) and its Build/Agent submodes entirely, replaced by the
single page-level `rpChatToggle` chat panel (`window.ReportingChat`). This
file used to cover that removed toggle's Agent submode (a "Try again"
affordance for max-turns/no-artifact answers, and resetting it on mode
switch); both premises are gone with the UI they tested. What remains here
drives the chat panel instead -- Simple-tab chat coverage lives in
test_reporting_simple.py, this file keeps the Advanced-tab entry point plus
the multi-turn / history / open-in-builder path the brief calls for.
"""

import json
import time

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


def _open_chat_from_advanced(page, base):
    page.goto(f"{base}/reporting?tab=advanced")
    page.get_by_test_id("reporting-chat-toggle").click()


def _stub_agent_sequence(page, responses):
    """Fulfil /api/reporting/ai/agent with `responses` (a list of
    {"body": <payload>, "delay_s": <optional float>}) in call order,
    repeating the last entry for any calls beyond the list. Returns the list
    of captured request JSON bodies, appended live as each call fires, so a
    test can assert exactly what a given call sent -- e.g. that a follow-up's
    `history` field carries the prior turns."""
    calls = []

    def handler(route):
        idx = min(len(calls), len(responses) - 1)
        spec = responses[idx]
        calls.append(json.loads(route.request.post_data or "{}"))
        delay = spec.get("delay_s") or 0
        if delay:
            time.sleep(delay)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(spec["body"]))

    page.route("**/api/reporting/ai/agent", handler)
    return calls


def _stub_run_ok(page):
    """Stub /api/reporting/run with a deterministic success (copied from
    test_reporting_simple.py's helper of the same name) -- opening an agent
    definition into the Simple result view fires a real runCurrent(), whose
    /api/reporting/run can error intermittently on the test DB (stale
    NEXORA_TEST state); stubbing keeps the result UI up regardless."""

    def _handler(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "columns": [{"field": "processname", "header": "Process"}],
                    "rows": [["acme.inv"]],
                    "truncated": False,
                    "rowCount": 1,
                    "sql": None,
                    "params": [],
                    "resolvedDates": [],
                }
            ),
        )

    page.route("**/api/reporting/run", _handler)


def test_chat_panel_open_send_followup_history_and_report_opens_in_simple(nexora_server, page):
    """Full round trip against a stubbed agent endpoint: open the chat panel
    from Advanced, send a question, see the user + AI bubbles, cleared input
    and an "Open report" chip, click a follow-up chip (asserting the
    SECOND stub call's request body carries the running history), then open
    the definition -- which now lands in the Simple result view (#178 A4),
    not the Advanced builder."""
    _login(page, nexora_server)
    question = "documents per month"
    answer = "Here are your documents per month."

    payload = {
        "answer": answer,
        "toolTrace": [],
        "turns": 1,
        "stoppedReason": "final",
        "definition": AGENT_DEFINITION,
        "sql": None,
    }
    # Stub BEFORE opening the panel/sending -- ReportingChat.send() fires the
    # request the instant the form submits.
    calls = _stub_agent_sequence(page, [{"body": payload}])
    _open_chat_from_advanced(page, nexora_server)

    expect(page.get_by_test_id("reporting-chat-panel")).to_be_visible()
    chat_input = page.get_by_test_id("reporting-chat-input")
    chat_input.fill(question)
    page.get_by_test_id("reporting-chat-send").click()

    expect(page.get_by_test_id("rp-chat-msg-user")).to_contain_text(question)
    expect(page.get_by_test_id("rp-chat-msg-ai")).to_contain_text(answer)
    expect(chat_input).to_have_value("")
    open_builder = page.get_by_test_id("rp-chat-open-builder")
    expect(open_builder).to_be_visible()

    # Follow-up chip resends through the same endpoint, carrying the running
    # history -- assert the SECOND captured call's body has both prior turns.
    # The assistant turn carries its produced artifact too (#178 A3): the
    # client appends a "[report definition from this answer]" block (no SQL
    # block here since the stub's "sql" is None) so a presentation-only
    # follow-up stays on the same definition instead of re-deriving one.
    page.get_by_test_id("rp-chat-followup").first.click()
    expect(page.get_by_test_id("rp-chat-msg-user")).to_have_count(2)
    assert len(calls) == 2, "the follow-up chip did not fire a second /agent call"
    definition_json = json.dumps(AGENT_DEFINITION, separators=(",", ":"))
    assert calls[1]["history"] == [
        {"role": "user", "content": question},
        {
            "role": "assistant",
            "content": answer + "\n[report definition from this answer]\n" + definition_json,
        },
    ], calls[1]["history"]

    # Open the definition -- lands in the Simple result view (#178 A4).
    _stub_run_ok(page)
    open_builder.first.click()
    expect(page.get_by_test_id("reporting-chat-panel")).to_be_hidden()
    expect(page.get_by_test_id("rs-result")).to_be_visible()
    expect(page.get_by_test_id("rs-chips")).to_be_visible()
    page.screenshot(path="var/screenshots/reporting_chat_panel_smoke.png")


def test_chat_panel_recovers_after_max_turns_with_no_artifact(nexora_server, page):
    """The retired Advanced AI panel needed a dedicated "Try again" button
    because a max-turns/no-artifact answer locked the whole panel. The chat
    panel has no separate retry control at all: a failed/limit-reached turn
    still renders (with its trace, no "Open report" chip) and the same
    plain input keeps working for the next question -- staying disabled only
    for the duration of that next in-flight request (the old double-submit
    guard, now on the ordinary send button)."""
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
    success_payload = {
        "answer": "Here is your report.",
        "toolTrace": [],
        "turns": 2,
        "stoppedReason": "final",
        "definition": AGENT_DEFINITION,
        "sql": None,
    }
    _stub_agent_sequence(
        page,
        [
            {"body": fail_payload},
            # Delay the retry so there is a real in-flight window: the send
            # button must be disabled while the request is pending.
            {"body": success_payload, "delay_s": 0.8},
        ],
    )
    _open_chat_from_advanced(page, nexora_server)

    chat_input = page.get_by_test_id("reporting-chat-input")
    send_btn = page.get_by_test_id("reporting-chat-send")
    chat_input.fill(question)
    send_btn.click()

    expect(page.get_by_test_id("rp-chat-msg-ai")).to_contain_text(
        "I could not find a definitive answer."
    )
    expect(page.get_by_test_id("rp-chat-open-builder")).to_have_count(0)
    expect(page.locator(".reporting-ai-trace-wrap")).to_be_visible()
    expect(send_btn).to_be_enabled()

    # Observe the disabled flip from INSIDE the page (same idiom as the old
    # retry test's __retryWasDisabled): the blocking route handler stalls the
    # sync Playwright protocol, so an expect() poll can never see the
    # transient in-flight state from outside.
    page.evaluate("""() => {
        window.__sendWasDisabled = false;
        const el = document.getElementById('rpChatSend');
        if (!el) return;
        if (el.disabled) { window.__sendWasDisabled = true; return; }
        const obs = new MutationObserver(() => {
            if (el.disabled) { window.__sendWasDisabled = true; obs.disconnect(); }
        });
        obs.observe(el, { attributes: true, attributeFilter: ['disabled'] });
    }""")

    chat_input.fill(question)
    send_btn.click()

    expect(page.get_by_test_id("rp-chat-msg-ai")).to_have_count(2)
    expect(page.get_by_test_id("rp-chat-msg-ai").last).to_contain_text("Here is your report.")
    assert page.evaluate(
        "() => window.__sendWasDisabled"
    ), "send button was never disabled while the retry request was in flight"
    expect(send_btn).to_be_enabled()
    expect(page.get_by_test_id("rp-chat-open-builder")).to_be_visible()
    page.screenshot(path="var/screenshots/reporting_chat_panel_recovers_after_max_turns.png")


def test_chat_panel_reads_the_ndjson_progress_stream(nexora_server, page):
    """The panel asks for the stream and renders its final `done` line.

    Progress events drive the ticker while the agent works (the point of the
    stream); the `done` line carries the same payload plain JSON would have
    returned, so the finished turn must look identical either way.
    """
    question = "documents per month"
    answer = "Here are your documents per month."
    lines = [
        {"phase": "thinking", "turn": 1},
        {"phase": "note", "text": "Let me check the schema."},
        {"phase": "tool", "name": "run_sql"},
        {
            "done": True,
            "answer": answer,
            "toolTrace": [],
            "turns": 2,
            "stoppedReason": "final",
            "definition": AGENT_DEFINITION,
            "sql": None,
        },
    ]
    sent = []

    def handler(route):
        sent.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(
            status=200,
            content_type="application/x-ndjson",
            body="".join(json.dumps(x) + "\n" for x in lines),
        )

    _login(page, nexora_server)
    page.route("**/api/reporting/ai/agent", handler)
    _open_chat_from_advanced(page, nexora_server)
    page.get_by_test_id("reporting-chat-input").fill(question)
    page.get_by_test_id("reporting-chat-send").click()

    expect(page.get_by_test_id("rp-chat-msg-ai")).to_contain_text(answer)
    expect(page.get_by_test_id("rp-chat-open-builder")).to_be_visible()
    assert sent and sent[0]["stream"] is True, "the panel did not request the stream"
    page.screenshot(path="var/screenshots/reporting_chat_stream.png")


def test_agent_stream_renders_build_steps(nexora_server, page):
    """#178 A1: each streamed `tool` event appends a row to the "Building
    your report..." card (rp-build-steps), flipping the previous running row
    to done when the next one starts.

    Playwright's route.fulfill() delivers the whole NDJSON body in one shot,
    so the rows resolve (ticker removed) before an expect() polling from
    outside the page could ever observe the transient running/done classes --
    same race the earlier stream test's comment already calls out. A
    MutationObserver registered in the page itself does not have that
    problem: it records every DOM mutation as it happens, including ones
    that only exist for a tick, so it can assert the live row-building/
    flip logic in `tickerEvent()` directly rather than only the post-hoc
    "ticker gone, answer present" outcome (which a broken tickerEvent would
    also often produce, since a JS exception there aborts the read loop
    before `done` and lands on the same generic error bubble either way).
    """
    question = "documents per month"
    answer = "Here are your documents per month."
    lines = [
        {"phase": "thinking", "turn": 1},
        {"phase": "tool", "name": "build_definition"},
        {"phase": "tool", "name": "validate_sql"},
        {"phase": "tool", "name": "run_sql"},
        {
            "done": True,
            "answer": answer,
            "toolTrace": [],
            "turns": 2,
            "stoppedReason": "final",
            "definition": AGENT_DEFINITION,
            "sql": None,
        },
    ]

    def handler(route):
        route.fulfill(
            status=200,
            content_type="application/x-ndjson",
            body="".join(json.dumps(x) + "\n" for x in lines),
        )

    _login(page, nexora_server)
    page.route("**/api/reporting/ai/agent", handler)
    _open_chat_from_advanced(page, nexora_server)

    # Observe from INSIDE the page (see docstring) -- registered before the
    # send that triggers the stream.
    page.evaluate("""() => {
        window.__buildStats = { added: 0, sawRunning: false, sawDone: false };
        const thread = document.getElementById('rpChatThread');
        const obs = new MutationObserver((records) => {
            records.forEach((rec) => {
                rec.addedNodes.forEach((n) => {
                    if (n.nodeType === 1 && n.classList && n.classList.contains('rp-build-step')) {
                        window.__buildStats.added++;
                        // className is set before appendChild, so the initial
                        // is-running class arrives as part of this addedNodes
                        // record, not a later attribute mutation.
                        if (n.classList.contains('is-running')) window.__buildStats.sawRunning = true;
                    }
                });
                if (rec.type === 'attributes' && rec.attributeName === 'class' &&
                    rec.target.classList && rec.target.classList.contains('rp-build-step')) {
                    if (rec.target.classList.contains('is-running')) window.__buildStats.sawRunning = true;
                    if (rec.target.classList.contains('is-done')) window.__buildStats.sawDone = true;
                }
            });
        });
        obs.observe(thread, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
    }""")

    page.get_by_test_id("reporting-chat-input").fill(question)
    page.get_by_test_id("reporting-chat-send").click()

    expect(page.get_by_test_id("rp-chat-msg-ai")).to_contain_text(answer)
    # The card is transient -- gone once the turn completes.
    expect(page.get_by_test_id("rp-chat-ticker")).to_have_count(0)

    stats = page.evaluate("() => window.__buildStats")
    assert stats["added"] == 3, f"expected one row per tool event, got {stats}"
    assert stats["sawRunning"], f"no row was ever marked running: {stats}"
    assert stats["sawDone"], f"no row was ever flipped to done: {stats}"


def test_chat_panel_surfaces_a_mid_stream_failure(nexora_server, page):
    """A stream that fails after headers reports it in the `done` line, not a
    status code -- the panel must still show an error bubble, not a blank turn."""
    _login(page, nexora_server)
    page.route(
        "**/api/reporting/ai/agent",
        lambda route: route.fulfill(
            status=200,
            content_type="application/x-ndjson",
            body=json.dumps({"phase": "thinking", "turn": 1})
            + "\n"
            + json.dumps({"done": True, "error": "The AI assistant could not answer right now"})
            + "\n",
        ),
    )
    _open_chat_from_advanced(page, nexora_server)
    page.get_by_test_id("reporting-chat-input").fill("boom")
    page.get_by_test_id("reporting-chat-send").click()

    expect(page.get_by_test_id("rp-chat-msg-ai")).to_contain_text("could not answer")
    expect(page.get_by_test_id("reporting-chat-send")).to_be_enabled()


def test_chat_ticker_shows_eddard_building_a_report(nexora_server, page):
    """Issue #212: while a turn is in flight the ticker carries Eddard's build
    stage, and the build loop reveals the report piece by piece.

    Two halves, because a stubbed answer resolves far faster than the 1300ms
    build beat: a MutationObserver (same trick as the build-steps test above)
    proves the stage really is mounted into the ticker on send, then the build
    controller is driven directly to check the reveal order. That second half
    also pins the <svg> trend slot -- `hidden` is an HTMLElement-only IDL
    property, so toggling it by assignment leaves the line invisible forever.
    """
    _login(page, nexora_server)
    _stub_agent_sequence(
        page,
        [
            {
                "body": {
                    "answer": "done",
                    "toolTrace": [],
                    "turns": 1,
                    "stoppedReason": "final",
                    "definition": None,
                    "sql": None,
                },
            }
        ],
    )
    _open_chat_from_advanced(page, nexora_server)

    page.evaluate("""() => {
        window.__sawStage = false;
        const obs = new MutationObserver((records) => {
            records.forEach((rec) => rec.addedNodes.forEach((n) => {
                if (n.nodeType === 1 && n.querySelector && n.querySelector('.ed-stage')) {
                    window.__sawStage = true;
                }
            }));
        });
        obs.observe(document.getElementById('rpChatThread'), { childList: true, subtree: true });
    }""")

    page.get_by_test_id("reporting-chat-input").fill("build me something")
    page.get_by_test_id("reporting-chat-send").click()
    expect(page.get_by_test_id("rp-chat-msg-ai")).to_contain_text("done")
    assert page.evaluate("() => window.__sawStage"), "no Eddard stage in the progress ticker"
    # The stage leaves with the ticker -- nothing keeps painting afterwards.
    expect(page.get_by_test_id("reporting-chat-build-stage")).to_have_count(0)

    # Drive the build loop itself and record which slots are on screen at each
    # step. 8s covers the full 0->5 walk at the handoff's 1300ms beat.
    steps = page.evaluate("""() => new Promise((resolve) => {
        const stage = document.getElementById('rpChatWorkingMascot').content.cloneNode(true)
            .querySelector('.ed-stage');
        document.getElementById('rpChatThread').appendChild(stage);
        const shown = () => Array.from(stage.querySelectorAll('[data-ed-slot]'))
            .filter((el) => el.getBoundingClientRect().height > 0)
            .map((el) => el.dataset.edSlot);
        const seen = [];
        window.NexoraEddard.startBuild(stage);
        const t = setInterval(() => {
            const now = shown().join(',');
            if (seen[seen.length - 1] !== now) seen.push(now);
            if (now.includes('badge')) {
                clearInterval(t);
                window.NexoraEddard.stopBuild(stage);
                stage.remove();
                resolve(seen);
            }
        }, 100);
    })""")

    assert steps[0] == "empty", steps
    assert steps[-1] == "title,kpi,bars,line,badge", steps
