"""Unit tests for the Reporting AI agentic loop (Phase 3c).

The loop (`ask_agentic`) is separated from provider parsing: it consumes an
injected ``agent_step(messages) -> AssistantTurn``. These tests script that
callable directly (Task 4) and, for the real provider round-trip, inject a fake
HTTP ``transport`` (Task 5). No network.
"""

from nx_lib.reporting.ai import AssistantTurn, _make_agent_step, ask_agentic
from nx_lib.reporting.ai_tools import TOOL_SPECS, ToolRegistry


def _script(*turns):
    """Return an agent_step that yields the given turns in order."""
    seq = iter(turns)

    def step(messages):
        return next(seq)

    return step


# ---- Task 4: loop logic --------------------------------------------------


def test_loop_runs_tool_then_returns_final_answer():
    reg = ToolRegistry()
    step = _script(
        AssistantTurn(
            text="",
            tool_calls=[{"id": "1", "name": "validate_sql", "args": {"sql": "SELECT 1"}}],
            tokens_in=10,
            tokens_out=5,
        ),
        AssistantTurn(text="It is valid.", tool_calls=[], tokens_in=4, tokens_out=3),
    )
    res = ask_agentic("is this ok?", registry=reg, agent_step=step, max_turns=5)
    assert res.answer == "It is valid."
    assert res.turns == 2
    assert res.stopped_reason == "final"
    assert res.tool_trace[0]["name"] == "validate_sql"
    assert res.tool_trace[0]["result"]["ok"] is True
    assert res.tokens_in == 14 and res.tokens_out == 8


def test_self_repair_feeds_error_back():
    reg = ToolRegistry()
    step = _script(
        AssistantTurn(
            tool_calls=[{"id": "1", "name": "validate_sql", "args": {"sql": "DELETE FROM t"}}]
        ),
        AssistantTurn(
            tool_calls=[{"id": "2", "name": "validate_sql", "args": {"sql": "SELECT 1"}}]
        ),
        AssistantTurn(text="Fixed."),
    )
    res = ask_agentic("q", registry=reg, agent_step=step, max_turns=5)
    assert res.answer == "Fixed."
    assert res.tool_trace[0]["result"]["ok"] is False  # first rejected
    assert res.tool_trace[1]["result"]["ok"] is True


def test_turn_cap_stops_runaway_loop():
    reg = ToolRegistry()
    forever = AssistantTurn(
        tool_calls=[{"id": "x", "name": "validate_sql", "args": {"sql": "SELECT 1"}}]
    )
    res = ask_agentic("q", registry=reg, agent_step=lambda m: forever, max_turns=3)
    assert res.turns == 3
    assert res.stopped_reason == "max_turns"
    assert res.answer == ""


def test_loop_passes_tool_results_into_next_messages():
    """The assistant turn + tool results are appended so the model sees them."""
    seen = []

    def step(messages):
        seen.append([m["role"] for m in messages])
        if len(seen) == 1:
            return AssistantTurn(
                tool_calls=[{"id": "1", "name": "validate_sql", "args": {"sql": "SELECT 1"}}]
            )
        return AssistantTurn(text="done")

    ask_agentic("q", registry=ToolRegistry(), agent_step=step, max_turns=5)
    # second call must see: user, assistant, tool
    assert seen[1] == ["user", "assistant", "tool"]


# ---- Task 5: provider tool-calling round-trip ----------------------------


def test_azure_tool_call_parsed():
    def fake_transport(url, headers, body, timeout):
        assert body["tools"][0]["type"] == "function"  # azure tool shape
        return {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "c1",
                                "type": "function",
                                "function": {
                                    "name": "validate_sql",
                                    "arguments": '{"sql": "SELECT 1"}',
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7},
        }

    step = _make_agent_step(
        system="s",
        tools=TOOL_SPECS,
        provider="azure",
        model="m",
        api_key="k",
        endpoint="https://e",
        deployment="d",
        transport=fake_transport,
    )
    turn = step([{"role": "user", "content": "q"}])
    assert turn.tool_calls[0]["name"] == "validate_sql"
    assert turn.tool_calls[0]["args"] == {"sql": "SELECT 1"}
    assert turn.tokens_in == 11 and turn.tokens_out == 7


def test_azure_final_answer_parsed():
    def fake_transport(url, headers, body, timeout):
        return {"choices": [{"message": {"content": "done"}}], "usage": {}}

    step = _make_agent_step(
        system="s",
        tools=TOOL_SPECS,
        provider="azure",
        model="m",
        api_key="k",
        endpoint="https://e",
        deployment="d",
        transport=fake_transport,
    )
    turn = step([{"role": "user", "content": "q"}])
    assert turn.text == "done" and turn.tool_calls == []


def test_azure_translates_prior_tool_results():
    """A neutral 'tool' message becomes Azure assistant.tool_calls + role:tool msgs."""
    captured = {}

    def fake_transport(url, headers, body, timeout):
        captured["messages"] = body["messages"]
        return {"choices": [{"message": {"content": "ok"}}], "usage": {}}

    step = _make_agent_step(
        system="s",
        tools=TOOL_SPECS,
        provider="azure",
        model="m",
        api_key="k",
        endpoint="https://e",
        deployment="d",
        transport=fake_transport,
    )
    messages = [
        {"role": "user", "content": "q"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "name": "validate_sql", "args": {"sql": "SELECT 1"}}],
        },
        {
            "role": "tool",
            "content": [{"tool_call_id": "c1", "name": "validate_sql", "result": {"ok": True}}],
        },
    ]
    step(messages)
    roles = [m["role"] for m in captured["messages"]]
    assert roles == ["system", "user", "assistant", "tool"]
    assert captured["messages"][2]["tool_calls"][0]["id"] == "c1"
    assert captured["messages"][3]["tool_call_id"] == "c1"


def test_anthropic_tool_use_parsed():
    def fake_transport(url, headers, body, timeout):
        assert "input_schema" in body["tools"][0]  # anthropic tool shape
        return {
            "content": [
                {"type": "text", "text": "let me check"},
                {
                    "type": "tool_use",
                    "id": "tu1",
                    "name": "validate_sql",
                    "input": {"sql": "SELECT 1"},
                },
            ],
            "usage": {"input_tokens": 3, "output_tokens": 9},
        }

    step = _make_agent_step(
        system="s",
        tools=TOOL_SPECS,
        provider="anthropic",
        model="m",
        api_key="k",
        transport=fake_transport,
    )
    turn = step([{"role": "user", "content": "q"}])
    assert turn.text == "let me check"
    assert turn.tool_calls[0] == {"id": "tu1", "name": "validate_sql", "args": {"sql": "SELECT 1"}}
    assert turn.tokens_in == 3 and turn.tokens_out == 9


def test_agent_system_prompt_teaches_distinct_and_processes():
    from nx_lib.reporting.ai import _AGENT_SYSTEM

    s = _AGENT_SYSTEM
    assert "distinct" in s.lower()
    assert "GROUP BY" in s


def test_agent_system_prompt_grounds_relative_dates():
    from nx_lib.reporting.ai import _AGENT_SYSTEM

    assert "today's date" in _AGENT_SYSTEM.lower()


def test_anthropic_translates_prior_tool_results():
    captured = {}

    def fake_transport(url, headers, body, timeout):
        captured["messages"] = body["messages"]
        return {"content": [{"type": "text", "text": "ok"}], "usage": {}}

    step = _make_agent_step(
        system="s",
        tools=TOOL_SPECS,
        provider="anthropic",
        model="m",
        api_key="k",
        transport=fake_transport,
    )
    messages = [
        {"role": "user", "content": "q"},
        {
            "role": "assistant",
            "content": "checking",
            "tool_calls": [{"id": "tu1", "name": "validate_sql", "args": {"sql": "SELECT 1"}}],
        },
        {
            "role": "tool",
            "content": [{"tool_call_id": "tu1", "name": "validate_sql", "result": {"ok": True}}],
        },
    ]
    step(messages)
    msgs = captured["messages"]
    # assistant turn carries a tool_use block; the tool result is a user turn with tool_result
    assert any(
        isinstance(m["content"], list) and any(b.get("type") == "tool_use" for b in m["content"])
        for m in msgs
        if m["role"] == "assistant"
    )
    assert any(
        isinstance(m["content"], list) and any(b.get("type") == "tool_result" for b in m["content"])
        for m in msgs
        if m["role"] == "user"
    )


def test_agent_system_prompt_teaches_relative_date_tokens():
    from nx_lib.reporting.ai import _AGENT_SYSTEM

    s = _AGENT_SYSTEM
    assert '"token"' in s
    assert "last_n_days" in s
