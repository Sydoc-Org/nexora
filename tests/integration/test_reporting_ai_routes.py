"""Integration tests for POST /api/reporting/ai/ask (perm gating + happy path)."""

import datetime
import json
from contextlib import ExitStack
from unittest.mock import patch

from nx_lib.reporting.ai import (
    AiAgenticResult,
    AiCaptionResult,
    AiDefinitionResult,
    AiError,
    AiResult,
)

# The @require_permission decorator calls has_permission from nx_lib.security;
# inline calls inside api_ai_ask use the name nx_lib.views.reporting.ai imports
# for itself (moved there in beautify-phase-2a Task 1 along with the route).
# Both must be patched together when we want to bypass the permission checks.
_PERM_PATCHES = (
    "nx_lib.security.has_permission",
    "nx_lib.views.reporting.ai.has_permission",
)


def _result(sql="SELECT TOP (5) Id FROM dbo.Foo", valid=True):
    return AiResult(
        sql=sql,
        explanation="five ids",
        valid=valid,
        gate_verdict="valid" if valid else "invalid",
        model="m",
        provider="anthropic",
        tokens_in=10,
        tokens_out=5,
    )


def test_ai_ask_requires_use_permission(user_client):
    with patch("nx_lib.views.reporting.ai.has_permission", return_value=False):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "hi"})
    assert resp.status_code == 403


def test_ai_ask_503_when_provider_unconfigured(user_client):
    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "none", "api_key": None},
        ),
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "hi"})
    assert resp.status_code == 503


def test_ai_ask_happy_path_returns_sql_and_audits(user_client):
    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting.ai._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
        patch("nx_lib.views.reporting.ai.ai_ask", return_value=_result()) as ask,
        patch("nx_lib.views.reporting.ai._audit_ai") as audit,
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "five ids"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["sql"].startswith("SELECT TOP (5)")
    assert data["valid"] is True
    assert "rows" not in data  # schema-only egress; never returns data
    ask.assert_called_once()
    audit.assert_called_once()


def test_ai_ask_rejects_empty_question(user_client):
    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "   "})
    assert resp.status_code == 400


def test_ai_ask_502_on_provider_error(user_client):
    with (
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting.ai._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
        patch("nx_lib.views.reporting.ai.ai_ask", side_effect=RuntimeError("boom")),
        patch("nx_lib.views.reporting.ai._audit_ai") as audit,
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "x"})
    assert resp.status_code == 502
    audit.assert_called_once()
    # error path audits with status="error" (the second-to-last positional arg)
    assert "error" in audit.call_args.args
    assert audit.call_args.args[-2] == "error"


def test_ai_ask_429_when_daily_limit_reached(user_client):
    # When the per-user daily cap is hit, the route blocks BEFORE calling the
    # provider (no token cost), records the throttle, and never reaches ai_ask.
    with (
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting.ai._ai_daily_limit", return_value=5),
        patch("nx_lib.views.reporting.ai._ai_asks_today", return_value=5),
        patch("nx_lib.views.reporting.ai.ai_ask") as ask,
        patch("nx_lib.views.reporting.ai._audit_ai") as audit,
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "x"})
    assert resp.status_code == 429
    ask.assert_not_called()  # never calls the provider -> no token cost
    audit.assert_called_once()
    assert audit.call_args.args[-2] == "blocked"  # status="blocked"


def test_ai_ask_allows_when_under_daily_limit(user_client):
    with (
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting.ai._ai_daily_limit", return_value=5),
        patch("nx_lib.views.reporting.ai._ai_asks_today", return_value=4),
        patch("nx_lib.views.reporting.ai._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
        patch("nx_lib.views.reporting.ai.ai_ask", return_value=_result()) as ask,
        patch("nx_lib.views.reporting.ai._audit_ai"),
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "five ids"})
    assert resp.status_code == 200
    ask.assert_called_once()


def test_ai_ask_unlimited_when_limit_zero(user_client):
    # limit 0 disables the cap: the usage count is never queried.
    with (
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting.ai._ai_daily_limit", return_value=0),
        patch("nx_lib.views.reporting.ai._ai_asks_today") as count,
        patch("nx_lib.views.reporting.ai._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
        patch("nx_lib.views.reporting.ai.ai_ask", return_value=_result()) as ask,
        patch("nx_lib.views.reporting.ai._audit_ai"),
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "five ids"})
    assert resp.status_code == 200
    ask.assert_called_once()
    count.assert_not_called()  # cap disabled -> no usage query


def _def_result(source="gen_pdqm", definition=None, explanation="by outcome"):
    return AiDefinitionResult(
        definition=definition
        or {
            "schemaVersion": 1,
            "visualization": "table",
            "source": source,
            "title": "T",
            "columns": [{"field": "Outcome"}],
            "filters": [],
            "sort": [],
            "scope": {"clients": [], "processes": []},
            "rowLimit": 5000,
        },
        explanation=explanation,
        model="m",
        provider="anthropic",
        tokens_in=10,
        tokens_out=8,
    )


def test_ai_build_requires_use_permission(user_client):
    with patch("nx_lib.views.reporting.ai.has_permission", return_value=False):
        resp = user_client.post("/api/reporting/ai/build", json={"question": "hi"})
    assert resp.status_code == 403


def test_ai_build_does_not_require_sql_permission(user_client):
    # Surface A: reporting.ai.use is enough; reporting.ai.sql.use is NOT consulted.
    def _has(code):
        return code != "reporting.ai.sql.use"

    with (
        patch("nx_lib.security.has_permission", side_effect=_has),
        patch("nx_lib.views.reporting.ai.has_permission", side_effect=_has),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting.ai._ai_daily_limit", return_value=0),
        patch("nx_lib.views.reporting.ai._ai_catalog_text", return_value="SOURCE gen_pdqm ..."),
        patch("nx_lib.views.reporting.ai.ai_ask_definition", return_value=_def_result()),
        patch("nx_lib.views.reporting.ai._validate_definition_for_user", return_value=(True, None)),
        patch("nx_lib.views.reporting.ai._audit_ai") as audit,
    ):
        resp = user_client.post("/api/reporting/ai/build", json={"question": "pdqm"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["valid"] is True
    assert data["definition"]["source"] == "gen_pdqm"
    assert data["definition"]["groupBy"] == []  # normalized to builder shape
    assert "rows" not in data  # schema-only egress
    audit.assert_called_once()
    assert audit.call_args.args[3] == "definition"  # Surface positional arg


def test_ai_build_retries_once_then_returns_invalid(user_client):
    # First draft fails validation; route retries once; still invalid -> valid:false (200).
    with (
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting.ai._ai_daily_limit", return_value=0),
        patch("nx_lib.views.reporting.ai._ai_catalog_text", return_value="CATALOG"),
        patch("nx_lib.views.reporting.ai.ai_ask_definition", return_value=_def_result()) as draft,
        patch(
            "nx_lib.views.reporting.ai._validate_definition_for_user",
            return_value=(False, "unknown column field: 'Nope'"),
        ),
        patch("nx_lib.views.reporting.ai._audit_ai"),
    ):
        resp = user_client.post("/api/reporting/ai/build", json={"question": "x"})
    assert resp.status_code == 200
    assert resp.get_json()["valid"] is False
    assert draft.call_count == 2  # initial + one self-repair retry


def test_ai_build_503_when_provider_unconfigured(user_client):
    with (
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "none", "api_key": None},
        ),
    ):
        resp = user_client.post("/api/reporting/ai/build", json={"question": "hi"})
    assert resp.status_code == 503


def test_ai_ask_audits_misconfig_on_aierror(user_client):
    # A configured-looking provider that raises AiError mid-call (e.g. unknown
    # provider / bad endpoint) -> 503, but it leaves a 'misconfig' audit trace so a
    # broken provider is debuggable. 'misconfig' (not 'error') keeps it off the cap.
    with (
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting.ai._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
        patch("nx_lib.views.reporting.ai.ai_ask", side_effect=AiError("unknown provider")),
        patch("nx_lib.views.reporting.ai._audit_ai") as audit,
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "x"})
    assert resp.status_code == 503
    audit.assert_called_once()
    assert audit.call_args.args[3] == "sql"  # Surface
    assert audit.call_args.args[-2] == "misconfig"  # Status


def test_ai_build_audits_misconfig_on_aierror(user_client):
    with (
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting.ai._ai_daily_limit", return_value=0),
        patch("nx_lib.views.reporting.ai._ai_catalog_text", return_value="CATALOG"),
        patch(
            "nx_lib.views.reporting.ai.ai_ask_definition",
            side_effect=AiError("Azure OpenAI requires endpoint and deployment"),
        ),
        patch("nx_lib.views.reporting.ai._audit_ai") as audit,
    ):
        resp = user_client.post("/api/reporting/ai/build", json={"question": "x"})
    assert resp.status_code == 503
    audit.assert_called_once()
    assert audit.call_args.args[3] == "definition"  # Surface
    assert audit.call_args.args[-2] == "misconfig"  # Status


# ---- POST /api/reporting/ai/agent (Phase 3d) -----------------------------


def _agentic_result(
    answer="Built a report by outcome.", definition_ok=True, tool_name="build_definition"
):
    trace = [
        {
            "name": tool_name,
            "args": {
                "definition": {
                    "schemaVersion": 1,
                    "visualization": "table",
                    "source": "gen_pdqm",
                    "title": "By outcome",
                    "columns": [{"field": "Outcome"}],
                }
            },
            "result": {"ok": definition_ok, **({} if definition_ok else {"error": "bad field"})},
        }
    ]
    return AiAgenticResult(
        answer=answer,
        turns=2,
        tool_trace=trace,
        stopped_reason="final",
        tokens_in=20,
        tokens_out=12,
    )


def _agent_patches(perm=True, sql_perm=True, explain_perm=False, run_perm=True):
    """Common patches for the agent route, entered via ExitStack (helper tuple
    can't be star-unpacked inside a parenthesized `with`)."""

    def _has(code):
        if code == "reporting.ai.sql.use":
            return sql_perm
        if code == "reporting.ai.explain.use":
            return explain_perm
        if code == "reporting.sql.run":
            return run_perm
        return perm

    return [
        patch("nx_lib.security.has_permission", side_effect=_has),
        patch("nx_lib.views.reporting.ai.has_permission", side_effect=_has),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting.ai._ai_daily_limit", return_value=0),
        patch("nx_lib.views.reporting.ai._ai_catalog_text", return_value="SOURCE gen_pdqm ..."),
        patch("nx_lib.views.reporting.ai._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
    ]


def test_ai_agent_grounding_states_todays_date(user_client):
    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        loop = es.enter_context(
            patch("nx_lib.views.reporting.ai.ask_agentic", return_value=_agentic_result())
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._validate_definition_for_user",
                return_value=(True, None),
            )
        )
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        user_client.post("/api/reporting/ai/agent", json={"question": "docs last month"})
    initial = loop.call_args.args[0]
    assert initial.startswith(f"Today's date is {datetime.date.today().isoformat()}")


def test_ai_agent_requires_use_permission(user_client):
    with patch("nx_lib.views.reporting.ai.has_permission", return_value=False):
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "hi"})
    assert resp.status_code == 403


def test_ai_agent_503_when_provider_unconfigured(user_client):
    with (
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "none", "api_key": None},
        ),
    ):
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "hi"})
    assert resp.status_code == 503


def test_ai_agent_rejects_empty_question(user_client):
    with (
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
    ):
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "  "})
    assert resp.status_code == 400


def test_ai_agent_happy_path_returns_answer_and_audits(user_client):
    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        es.enter_context(
            patch("nx_lib.views.reporting.ai.ask_agentic", return_value=_agentic_result())
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._validate_definition_for_user", return_value=(True, None)
            )
        )
        audit = es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "report by outcome"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["answer"] == "Built a report by outcome."
    assert data["turns"] == 2
    assert data["stoppedReason"] == "final"
    assert data["toolTrace"][0]["name"] == "build_definition"
    # the last validated definition is extracted + normalized for "open in builder"
    assert data["definition"]["source"] == "gen_pdqm"
    assert data["definition"]["groupBy"] == []
    audit.assert_called_once()
    assert audit.call_args.args[3] == "agent"  # Surface positional arg
    assert audit.call_args.args[-2] == "ok"  # Status


def test_ai_agent_extracts_definition_from_run_definition_call(user_client):
    # run_definition validates the same shape as build_definition before
    # executing it, so an ok=True run_definition call must offer "Open in
    # builder" too — not just build_definition.
    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai.ask_agentic",
                return_value=_agentic_result(tool_name="run_definition"),
            )
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._validate_definition_for_user", return_value=(True, None)
            )
        )
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "report by outcome"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["toolTrace"][0]["name"] == "run_definition"
    assert data["definition"]["source"] == "gen_pdqm"


# ---- Issue #127: an empty final answer must never reach the chat as-is ------


def test_ai_agent_empty_answer_gets_artifact_aware_fallback(user_client):
    # Loop produced a valid definition but no prose (post-nudge) — the payload
    # must point at the artifact instead of shipping an empty string.
    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        es.enter_context(
            patch("nx_lib.views.reporting.ai.ask_agentic", return_value=_agentic_result(answer=""))
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._validate_definition_for_user", return_value=(True, None)
            )
        )
        audit = es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "report by outcome"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["answer"].strip()
    assert "Open report" in data["answer"]
    assert data["definition"]["source"] == "gen_pdqm"
    # the audit keeps the raw (empty) answer — only the payload gets the fallback
    audited = json.loads(audit.call_args.args[4])
    assert audited["answer"] == ""


def test_ai_agent_empty_answer_no_artifacts_gets_generic_fallback(user_client):
    bare = AiAgenticResult(
        answer="",
        turns=1,
        tool_trace=[],
        stopped_reason="final",
        tokens_in=5,
        tokens_out=0,
    )
    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        es.enter_context(patch("nx_lib.views.reporting.ai.ask_agentic", return_value=bare))
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "anything"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["answer"].strip()
    assert data["definition"] is None
    assert data["sql"] is None


def test_ai_agent_caps_history_to_8_turns_and_12000_chars(user_client):
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 600} for i in range(10)
    ]
    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        loop = es.enter_context(
            patch("nx_lib.views.reporting.ai.ask_agentic", return_value=_agentic_result())
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._validate_definition_for_user", return_value=(True, None)
            )
        )
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post(
            "/api/reporting/ai/agent",
            json={"question": "report by outcome", "history": history},
        )
    assert resp.status_code == 200
    sent = loop.call_args.kwargs["history"]
    assert len(sent) <= 8
    assert sum(len(h["content"]) for h in sent) <= 12000
    # oldest turns dropped first: survivors are the tail of the original list
    assert sent == history[-len(sent) :]


def test_agent_history_keeps_long_artifact_context(admin_client):
    """#178 A3: an 11KB two-entry history must reach the loop intact (the old
    4000-char cap silently dropped the artifact-bearing assistant turn)."""
    from nx_lib.reporting.ai import AssistantTurn

    big_sql = "SELECT " + ("x" * 5000)
    history = [
        {"role": "user", "content": "wie viele dokumente diesen monat"},
        {"role": "assistant", "content": "Antwort…\n[sql from this answer]\n" + big_sql},
    ]
    seen = {}

    def fake_step(messages):
        seen["messages"] = messages
        return AssistantTurn(text="ok")

    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        es.enter_context(patch("nx_lib.views.reporting.ai.make_agent_step", return_value=fake_step))
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = admin_client.post(
            "/api/reporting/ai/agent",
            json={"question": "show it as a chart", "history": history},
        )
    assert resp.status_code == 200
    assert any(
        "[sql from this answer]" in m.get("content", "")
        for m in seen["messages"]
        if m["role"] == "assistant"
    )


def test_ai_agent_rejects_non_list_history(user_client):
    with (
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
    ):
        resp = user_client.post(
            "/api/reporting/ai/agent",
            json={"question": "hi", "history": "not-a-list"},
        )
    assert resp.status_code == 400


def test_ai_agent_drops_invalid_history_entries(user_client):
    history = [
        {"role": "tool", "content": "ignored"},
        {"role": "user", "content": 123},
        {"role": "assistant", "content": "kept"},
    ]
    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        loop = es.enter_context(
            patch("nx_lib.views.reporting.ai.ask_agentic", return_value=_agentic_result())
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._validate_definition_for_user", return_value=(True, None)
            )
        )
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post(
            "/api/reporting/ai/agent",
            json={"question": "report by outcome", "history": history},
        )
    assert resp.status_code == 200
    sent = loop.call_args.kwargs["history"]
    assert sent == [{"role": "assistant", "content": "kept"}]


def test_ai_agent_429_when_daily_limit_reached(user_client):
    with (
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting.ai._ai_daily_limit", return_value=5),
        patch("nx_lib.views.reporting.ai._ai_asks_today", return_value=5),
        patch("nx_lib.views.reporting.ai.ask_agentic") as loop,
        patch("nx_lib.views.reporting.ai._audit_ai") as audit,
    ):
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "x"})
    assert resp.status_code == 429
    loop.assert_not_called()
    assert audit.call_args.args[-2] == "blocked"


def test_ai_agent_audits_misconfig_on_aierror(user_client):
    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        es.enter_context(
            patch("nx_lib.views.reporting.ai.ask_agentic", side_effect=AiError("bad provider"))
        )
        audit = es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "x"})
    assert resp.status_code == 503
    audit.assert_called_once()
    assert audit.call_args.args[3] == "agent"
    assert audit.call_args.args[-2] == "misconfig"


def test_ai_agent_binds_sql_tool_only_with_sql_perm(user_client):
    captured = {}

    def fake_make_step(**kwargs):
        captured["tools"] = [t["name"] for t in kwargs["tools"]]
        return lambda messages: None

    with ExitStack() as es:
        for p in _agent_patches(sql_perm=False):
            es.enter_context(p)
        es.enter_context(
            patch("nx_lib.views.reporting.ai.make_agent_step", side_effect=fake_make_step)
        )
        es.enter_context(
            patch("nx_lib.views.reporting.ai.ask_agentic", return_value=_agentic_result())
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._validate_definition_for_user", return_value=(True, None)
            )
        )
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "x"})
    assert resp.status_code == 200
    assert "build_definition" in captured["tools"]
    assert "validate_sql" not in captured["tools"]  # gated on reporting.ai.sql.use


def test_ai_agent_binds_data_tools_with_explain_data_permission(user_client):
    """Phase 3e: reporting.ai.explain.use (+ reporting.sql.run) binds run_sql +
    compute_stats and injects the runner so result rows flow back to the model."""
    captured = {}

    def fake_make_step(**kwargs):
        captured["tools"] = [t["name"] for t in kwargs["tools"]]
        captured["system"] = kwargs["system"]
        return lambda messages: None

    def fake_loop(initial, *, registry, agent_step, **kw):
        captured["run_sql_bound"] = registry._run_sql is not None
        captured["run_definition_bound"] = registry._run_definition is not None
        return _agentic_result()

    with ExitStack() as es:
        for p in _agent_patches(explain_perm=True, run_perm=True):
            es.enter_context(p)
        es.enter_context(
            patch("nx_lib.views.reporting.ai.make_agent_step", side_effect=fake_make_step)
        )
        es.enter_context(patch("nx_lib.views.reporting.ai.ask_agentic", side_effect=fake_loop))
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._validate_definition_for_user", return_value=(True, None)
            )
        )
        audit = es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "how many?"})
    assert resp.status_code == 200
    assert resp.get_json()["explainData"] is True
    assert {"run_sql", "compute_stats", "run_definition"} <= set(captured["tools"])
    assert captured["run_sql_bound"] is True
    assert captured["run_definition_bound"] is True
    assert "run_sql" in captured["system"]  # explain suffix appended
    assert "run_definition" in captured["system"]
    assert audit.call_args.args[-2] == "ok"


def test_ai_agent_no_data_tools_without_explain_data(user_client):
    """Default posture: without reporting.ai.explain.use the loop stays schema-only —
    run_sql / compute_stats are never bound and the runner is not injected."""
    captured = {}

    def fake_make_step(**kwargs):
        captured["tools"] = [t["name"] for t in kwargs["tools"]]
        captured["system"] = kwargs["system"]
        return lambda messages: None

    def fake_loop(initial, *, registry, agent_step, **kw):
        captured["run_sql_bound"] = registry._run_sql is not None
        captured["run_definition_bound"] = registry._run_definition is not None
        return _agentic_result()

    with ExitStack() as es:
        for p in _agent_patches(explain_perm=False):
            es.enter_context(p)
        es.enter_context(
            patch("nx_lib.views.reporting.ai.make_agent_step", side_effect=fake_make_step)
        )
        es.enter_context(patch("nx_lib.views.reporting.ai.ask_agentic", side_effect=fake_loop))
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._validate_definition_for_user", return_value=(True, None)
            )
        )
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "how many?"})
    assert resp.status_code == 200
    assert resp.get_json()["explainData"] is False
    assert "run_sql" not in captured["tools"]
    assert "compute_stats" not in captured["tools"]
    assert "run_definition" not in captured["tools"]
    assert captured["run_sql_bound"] is False
    assert captured["run_definition_bound"] is False
    assert "run_sql" not in captured["system"]


def test_ai_agent_explain_data_inert_without_sql_run(user_client):
    """explain_data without reporting.sql.run does NOT bind run_sql — you can't let
    the model run SQL the user isn't allowed to run."""
    captured = {}

    def fake_make_step(**kwargs):
        captured["tools"] = [t["name"] for t in kwargs["tools"]]
        return lambda messages: None

    with ExitStack() as es:
        for p in _agent_patches(explain_perm=True, run_perm=False):
            es.enter_context(p)
        es.enter_context(
            patch("nx_lib.views.reporting.ai.make_agent_step", side_effect=fake_make_step)
        )
        es.enter_context(
            patch("nx_lib.views.reporting.ai.ask_agentic", return_value=_agentic_result())
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._validate_definition_for_user", return_value=(True, None)
            )
        )
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "x"})
    assert resp.status_code == 200
    assert resp.get_json()["explainData"] is False
    assert "run_sql" not in captured["tools"]


def test_ai_agent_keeps_data_tools_but_flags_builder_only_source(user_client):
    """A builder-only curated source (table provider, e.g. Generali on GeneraliDB)
    is unreachable by run_sql — but it is only the builder's UI default, not the
    question's subject. The data tools stay bound (explain_data + sql.run) so a
    question about a run_sql-able source still gets real numbers; the grounding
    marks the selected source builder-only to steer run_sql away from it."""
    captured = {}

    def fake_make_step(**kwargs):
        captured["tools"] = [t["name"] for t in kwargs["tools"]]
        return lambda messages: None

    def fake_loop(initial, *, registry, agent_step, **kw):
        captured["run_sql_bound"] = registry._run_sql is not None
        captured["initial"] = initial
        return _agentic_result()

    with ExitStack() as es:
        for p in _agent_patches(explain_perm=True, run_perm=True):
            es.enter_context(p)
        es.enter_context(
            patch("nx_lib.views.reporting.ai.make_agent_step", side_effect=fake_make_step)
        )
        es.enter_context(patch("nx_lib.views.reporting.ai.ask_agentic", side_effect=fake_loop))
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._validate_definition_for_user", return_value=(True, None)
            )
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._get_effective_source",
                return_value={
                    "id": "gen_pdqm",
                    "kind": "curated",
                    "provider": "generali",
                    "label": "Generali — PDQM Report",
                },
            )
        )
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post(
            "/api/reporting/ai/agent", json={"question": "how many?", "source": "gen_pdqm"}
        )
    assert resp.status_code == 200
    assert resp.get_json()["explainData"] is True
    assert {"run_sql", "compute_stats"} <= set(captured["tools"])
    assert captured["run_sql_bound"] is True
    assert "builder-only" in captured["initial"]


def test_ai_agent_binds_data_tools_for_run_sql_able_source(user_client):
    """The source-aware gate only blocks builder-only sources: a run_sql-able source
    (docprocessing → statistics RO target) still binds the data tools with explain_data."""
    captured = {}

    def fake_make_step(**kwargs):
        captured["tools"] = [t["name"] for t in kwargs["tools"]]
        return lambda messages: None

    def fake_loop(initial, *, registry, agent_step, **kw):
        captured["run_sql_bound"] = registry._run_sql is not None
        return _agentic_result()

    with ExitStack() as es:
        for p in _agent_patches(explain_perm=True, run_perm=True):
            es.enter_context(p)
        es.enter_context(
            patch("nx_lib.views.reporting.ai.make_agent_step", side_effect=fake_make_step)
        )
        es.enter_context(patch("nx_lib.views.reporting.ai.ask_agentic", side_effect=fake_loop))
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._validate_definition_for_user", return_value=(True, None)
            )
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._get_effective_source",
                return_value={
                    "id": "docproc",
                    "kind": "curated",
                    "provider": "docprocessing",
                    "label": "Document Processing",
                },
            )
        )
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post(
            "/api/reporting/ai/agent", json={"question": "how many?", "source": "docproc"}
        )
    assert resp.status_code == 200
    assert resp.get_json()["explainData"] is True
    assert {"run_sql", "compute_stats"} <= set(captured["tools"])
    assert captured["run_sql_bound"] is True


# ---- _validate_definition_for_user coercion wiring (table sources) --------
# The AI surfaces (build + agent) share this validator. It must repair the
# common small-model mistakes — labels-for-keys, missing schemaVersion/title —
# so a near-miss draft for a curated table source is accepted, not bounced.

_TABLE_SOURCE = {
    "id": "gen_pdqm",
    "kind": "curated",
    "provider": "table",
    "permission": "reporting.source.generali_pdqm.use",
    "label": "Generali — PDQM",
    "engine": "generali",
    "baseObject": "GeneraliDB.dbo.PdqmReport",
    "columns": [
        {"field": "ForDate", "label": "Date", "filterable": True, "sortable": True},
        {
            "field": "ParentCategory",
            "label": "Parent category",
            "filterable": True,
            "sortable": True,
        },
    ],
}


def test_validate_definition_coerces_table_source_labels_and_defaults():
    from nx_lib.views.reporting import _validate_definition_for_user

    # A model draft that used LABELS and omitted schemaVersion + title.
    defn = {
        "source": "gen_pdqm",
        "columns": [{"field": "Date"}, {"field": "Parent category"}],
        "sort": [{"field": "Date", "dir": "desc"}],
    }
    with ExitStack() as es:
        es.enter_context(
            patch("nx_lib.views.reporting.ai._get_effective_source", return_value=_TABLE_SOURCE)
        )
        es.enter_context(patch("nx_lib.views.reporting.ai.has_permission", return_value=True))
        ok, err = _validate_definition_for_user(defn)

    assert (ok, err) == (True, None)
    # labels were resolved to keys in place, and headers backfilled from the label
    assert defn["columns"] == [
        {"field": "ForDate", "header": "Date"},
        {"field": "ParentCategory", "header": "Parent category"},
    ]
    assert defn["sort"][0]["field"] == "ForDate"
    assert defn["schemaVersion"] == 1
    assert defn["title"] == "Generali — PDQM"  # synthesized from the source label


def test_validate_definition_accepts_metrics_and_grain_draft():
    # Surface-A drafts may use canonical metrics + a date grain; the validator
    # must pass metric_codes/grainable_fields exactly like _prepare_run does.
    from nx_lib.views.reporting import _validate_definition_for_user

    docproc_source = {
        "id": "docprocessing",
        "kind": "curated",
        "label": "Document Processing",
        "permission": "reporting.source.docprocessing.use",
        "engine": "statistics",
        "provider": "docprocessing",
    }
    catalog = [
        {
            "field": "import_date",
            "label": "Import date",
            "type": "date",
            "filterable": True,
            "sortable": True,
            "grainable": True,
        },
    ]
    defn = {
        "schemaVersion": 1,
        "source": "docprocessing",
        "visualization": "table",
        "title": "Documents per month",
        "columns": [{"field": "import_date", "header": "Import date", "grain": "month"}],
        "metrics": [{"metric": "doc_count"}],
        "filters": [],
        "sort": [{"field": "import_date", "dir": "asc"}],
        "scope": {"clients": [], "processes": []},
        "rowLimit": 5000,
    }
    with ExitStack() as es:
        es.enter_context(
            patch("nx_lib.views.reporting.ai._get_effective_source", return_value=docproc_source)
        )
        es.enter_context(patch("nx_lib.views.reporting.ai.has_permission", return_value=True))
        es.enter_context(patch("nx_lib.views.reporting.ai.get_locale", return_value="en"))
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai.fetch_docprocessing_catalog",
                return_value=catalog,
            )
        )
        es.enter_context(
            patch("nx_lib.views.reporting.ai._allowed_processes", return_value=["acme.inv"])
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._metrics_for_source",
                return_value={"doc_count": {"aggregation": "count", "base_field": None}},
            )
        )
        ok, err = _validate_definition_for_user(defn)

    assert (ok, err) == (True, None)


def test_ai_build_passes_today_to_drafter(user_client):
    stub = AiDefinitionResult(
        definition=None,
        explanation="",
        model="m",
        provider="anthropic",
        tokens_in=1,
        tokens_out=1,
    )
    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting.ai._ai_daily_limit", return_value=0),
        patch("nx_lib.views.reporting.ai._ai_catalog_text", return_value="CATALOG"),
        patch(
            "nx_lib.views.reporting.ai._validate_definition_for_user",
            return_value=(False, "no def"),
        ),
        patch("nx_lib.views.reporting.ai._audit_ai"),
        patch("nx_lib.views.reporting.ai.ai_ask_definition", return_value=stub) as drafter,
    ):
        resp = user_client.post("/api/reporting/ai/build", json={"question": "docs last month"})
    assert resp.status_code == 200
    assert drafter.call_args.kwargs["today"] == datetime.date.today().isoformat()


def test_validate_definition_zero_columns_with_metric_accepted():
    # The Simple wizard's "just the total": columns [] + a metric must validate.
    from nx_lib.views.reporting import _validate_definition_for_user

    docproc_source = {
        "id": "docprocessing",
        "kind": "curated",
        "label": "Document Processing",
        "permission": "reporting.source.docprocessing.use",
        "engine": "statistics",
        "provider": "docprocessing",
    }
    defn = {
        "schemaVersion": 1,
        "source": "docprocessing",
        "visualization": "table",
        "title": "Total documents",
        "columns": [],
        "metrics": [{"metric": "doc_count"}],
        "filters": [],
        "sort": [],
        "scope": {"clients": [], "processes": []},
        "rowLimit": 5000,
    }
    with ExitStack() as es:
        es.enter_context(
            patch("nx_lib.views.reporting.ai._get_effective_source", return_value=docproc_source)
        )
        es.enter_context(patch("nx_lib.views.reporting.ai.has_permission", return_value=True))
        es.enter_context(patch("nx_lib.views.reporting.ai.get_locale", return_value="en"))
        es.enter_context(
            patch("nx_lib.views.reporting.ai.fetch_docprocessing_catalog", return_value=[])
        )
        es.enter_context(
            patch("nx_lib.views.reporting.ai._allowed_processes", return_value=["acme.inv"])
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._metrics_for_source",
                return_value={"doc_count": {"aggregation": "count", "base_field": None}},
            )
        )
        ok, err = _validate_definition_for_user(defn)

    assert (ok, err) == (True, None)


# ---- F2-T2: /ai/build refine context (priorQuestion / priorDefinition) ------


def _build_patches():
    stub = AiDefinitionResult(
        definition=None,
        explanation="",
        model="m",
        provider="anthropic",
        tokens_in=1,
        tokens_out=1,
    )
    return stub, [
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting.ai._ai_daily_limit", return_value=0),
        patch("nx_lib.views.reporting.ai._ai_catalog_text", return_value="CATALOG"),
        patch(
            "nx_lib.views.reporting.ai._validate_definition_for_user",
            return_value=(False, "no def"),
        ),
        patch("nx_lib.views.reporting.ai._audit_ai"),
    ]


def test_ai_build_passes_refine_context_to_drafter(user_client):
    stub, patches = _build_patches()
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patch("nx_lib.views.reporting.ai.ai_ask_definition", return_value=stub) as drafter,
    ):
        resp = user_client.post(
            "/api/reporting/ai/build",
            json={
                "question": "only May",
                "priorQuestion": "docs last month",
                "priorDefinition": {"schemaVersion": 1, "title": "t"},
            },
        )
    assert resp.status_code == 200
    assert drafter.call_args.kwargs["prior_question"] == "docs last month"
    assert drafter.call_args.kwargs["prior_definition"] == {"schemaVersion": 1, "title": "t"}


def test_ai_build_without_refine_context_passes_none(user_client):
    stub, patches = _build_patches()
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patch("nx_lib.views.reporting.ai.ai_ask_definition", return_value=stub) as drafter,
    ):
        resp = user_client.post("/api/reporting/ai/build", json={"question": "q"})
    assert resp.status_code == 200
    assert drafter.call_args.kwargs["prior_question"] is None
    assert drafter.call_args.kwargs["prior_definition"] is None


def test_ai_build_rejects_malformed_refine_context(user_client):
    stub, patches = _build_patches()
    bad_bodies = [
        {"question": "q", "priorQuestion": 7},
        {"question": "q", "priorDefinition": "not-an-object"},
        {"question": "q", "priorQuestion": "x" * 2001},
        {"question": "q", "priorDefinition": {"big": "y" * 20001}},
    ]
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patch("nx_lib.views.reporting.ai.ai_ask_definition", return_value=stub),
    ):
        for body in bad_bodies:
            resp = user_client.post("/api/reporting/ai/build", json=body)
            assert resp.status_code == 400, body


# ---- Task 6: deterministic shadow-column guard --------------------------------


def test_ai_build_drops_column_shadowing_distinct_metric(user_client):
    drafted = {
        "schemaVersion": 1,
        "visualization": "table",
        "source": "docprocessing",
        "title": "Distinct workitems per process",
        "columns": [{"field": "processname"}, {"field": "workitem_id"}],
        "metrics": [{"metric": "workitem_count"}],
        "filters": [],
        "sort": [],
        "scope": {"clients": [], "processes": []},
        "rowLimit": 5000,
    }
    catalog = [
        {
            "field": "processname",
            "label": "Processname",
            "type": "string",
            "filterable": True,
            "sortable": True,
        },
        {
            "field": "workitem_id",
            "label": "Workitem ID",
            "type": "string",
            "filterable": True,
            "sortable": True,
        },
    ]
    metrics = {"workitem_count": {"aggregation": "count_distinct", "base_field": "workitem_id"}}
    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch(
            "nx_lib.views.reporting.ai._ai_catalog_text", return_value="SOURCE docprocessing ..."
        ),
        patch(
            "nx_lib.views.reporting.ai.ai_ask_definition",
            return_value=_def_result(definition=drafted, explanation="x"),
        ),
        patch(
            "nx_lib.views.reporting.ai._allowed_processes", return_value=["compass.01_Invoice_SAP"]
        ),
        patch("nx_lib.views.reporting.ai.fetch_docprocessing_catalog", return_value=catalog),
        patch("nx_lib.views.reporting.ai._metrics_for_source", return_value=metrics),
        patch("nx_lib.views.reporting.ai._audit_ai"),
    ):
        resp = user_client.post(
            "/api/reporting/ai/build", json={"question": "distinct per process"}
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["valid"] is True
    assert [c["field"] for c in data["definition"]["columns"]] == ["processname"]


# ---- Task 7: Agent knows the run_sql targets --------------------------------


def test_ai_build_accepts_prior_definition_without_question(user_client):
    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting.ai._ai_catalog_text", return_value="SOURCE gen_pdqm ..."),
        patch("nx_lib.views.reporting.ai.ai_ask_definition", return_value=_def_result()) as draft,
        patch("nx_lib.views.reporting.ai._validate_definition_for_user", return_value=(True, None)),
        patch("nx_lib.views.reporting.ai._audit_ai"),
    ):
        resp = user_client.post(
            "/api/reporting/ai/build",
            json={
                "question": "add a breakdown by process",
                "priorDefinition": {
                    "schemaVersion": 1,
                    "source": "gen_pdqm",
                    "columns": [],
                    "filters": [],
                },
            },
        )
    assert resp.status_code == 200
    assert resp.get_json()["valid"] is True
    assert draft.call_args.kwargs.get("prior_definition") is not None
    assert draft.call_args.kwargs.get("prior_question") in (None, "")


def test_run_sql_unknown_target_error_lists_allowed_targets():
    import pytest

    from nx_lib.reporting.schema import ReportDefinitionError
    from nx_lib.views.reporting import _run_sql

    with pytest.raises(ReportDefinitionError) as e:
        _run_sql("nope", "SELECT 1", userid="1", username="t")
    msg = str(e.value)
    assert "octopus" in msg and "statistics" in msg


def test_ai_agent_tool_trace_error_is_humanized(user_client):
    """Task 6: a raw pyodbc/ODBC failure from the bound run_sql runner must reach
    the tool trace (and hence the model + UI) humanized — no driver noise, plus
    the teaching hint for known SQL Server error codes (1033)."""
    from nx_lib.reporting.ai import AssistantTurn

    odbc_text = (
        "('42000', '[42000] [Microsoft][ODBC SQL Server Driver][SQL Server]"
        "The ORDER BY clause is invalid in views, inline functions, derived "
        "tables, subqueries, and common table expressions, unless TOP, OFFSET "
        "or FOR XML is also specified. (1033) (SQLExecDirectW)')"
    )

    turns = iter(
        [
            AssistantTurn(
                text="",
                tool_calls=[
                    {"id": "t1", "name": "run_sql", "args": {"target": "statistics", "sql": "S"}}
                ],
            ),
            AssistantTurn(text="Could not run the query."),
        ]
    )

    with ExitStack() as es:
        for p in _agent_patches(explain_perm=True, run_perm=True):
            es.enter_context(p)
        es.enter_context(
            patch("nx_lib.views.reporting.ai.make_agent_step", return_value=lambda m: next(turns))
        )
        # Clears the auth/ack gates so this test stays focused on humanization,
        # not D-RUNSQL's gate behavior (covered separately below).
        es.enter_context(patch("nx_lib.views.reporting.ai._has_acked", return_value=True))
        es.enter_context(
            patch("nx_lib.views.reporting.ai._authorize_sql_target", return_value=None)
        )
        es.enter_context(
            patch("nx_lib.views.reporting.ai._run_sql", side_effect=Exception(odbc_text))
        )
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "how many?"})
    assert resp.status_code == 200
    trace = resp.get_json()["toolTrace"]
    run_sql_result = next(t["result"] for t in trace if t["name"] == "run_sql")
    assert run_sql_result["ok"] is False
    assert "SQLExecDirectW" not in run_sql_result["error"]
    assert "[Microsoft]" not in run_sql_result["error"]
    assert "Hint:" in run_sql_result["error"]


# ---- Task 18 (D-RUNSQL): run_sql_bound must enforce the HTTP run view's exact
# auth + ack gates before touching _run_sql -------------------------------


def test_ai_agent_run_sql_blocks_without_target_permission(user_client):
    """A user who holds the general reporting.ai.explain.use + reporting.sql.run
    grants (enough to get the run_sql tool bound) but NOT the Octopus target's own
    permission must get a graceful tool-result error — no SQL executes, and the
    refusal is audited with a distinct status. No raised exception reaches Flask."""
    from nx_lib.reporting.ai import AssistantTurn

    def _has(code):
        # explain_data, sql.run, ai.use, ai.sql, etc all granted; only the
        # Octopus target's own permission is withheld.
        return code != "reporting.sql.target.octopus.use"

    turns = iter(
        [
            AssistantTurn(
                text="",
                tool_calls=[
                    {
                        "id": "t1",
                        "name": "run_sql",
                        "args": {"target": "octopus", "sql": "SELECT 1"},
                    }
                ],
            ),
            AssistantTurn(text="Could not run the query."),
        ]
    )

    with ExitStack() as es:
        es.enter_context(patch("nx_lib.security.has_permission", side_effect=_has))
        es.enter_context(patch("nx_lib.views.reporting.ai.has_permission", side_effect=_has))
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._ai_config",
                return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
            )
        )
        es.enter_context(patch("nx_lib.views.reporting.ai._ai_daily_limit", return_value=0))
        es.enter_context(
            patch("nx_lib.views.reporting.ai._ai_catalog_text", return_value="SOURCE gen_pdqm ...")
        )
        es.enter_context(
            patch("nx_lib.views.reporting.ai._ai_schema_text", return_value="TABLE dbo.Foo(Id int)")
        )
        es.enter_context(patch("nx_lib.views.reporting.ai._has_acked", return_value=True))
        es.enter_context(
            patch("nx_lib.views.reporting.ai.make_agent_step", return_value=lambda m: next(turns))
        )
        run_sql_spy = es.enter_context(patch("nx_lib.views.reporting.ai._run_sql"))
        audit_spy = es.enter_context(patch("nx_lib.views.reporting.ai._audit_sql"))
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "octopus events?"})

    assert resp.status_code == 200  # never a raise-through 500
    trace = resp.get_json()["toolTrace"]
    run_sql_result = next(t["result"] for t in trace if t["name"] == "run_sql")
    assert run_sql_result["ok"] is False
    assert "not authorized" in run_sql_result["error"].lower()
    run_sql_spy.assert_not_called()  # no SQL executed
    audit_spy.assert_called_once()
    assert audit_spy.call_args.args[-2] == "refused_auth"  # distinct status


def test_ai_agent_run_sql_blocks_without_ack(user_client):
    """A user who holds run_sql-tool-binding permissions but has NOT acknowledged
    the sandbox terms must get a graceful tool-result error — no SQL executes, and
    the refusal is audited with a distinct status. No raised exception reaches
    Flask."""
    from nx_lib.reporting.ai import AssistantTurn

    turns = iter(
        [
            AssistantTurn(
                text="",
                tool_calls=[
                    {
                        "id": "t1",
                        "name": "run_sql",
                        "args": {"target": "statistics", "sql": "SELECT 1"},
                    }
                ],
            ),
            AssistantTurn(text="Could not run the query."),
        ]
    )

    with ExitStack() as es:
        for p in _agent_patches(explain_perm=True, run_perm=True):
            es.enter_context(p)
        es.enter_context(patch("nx_lib.views.reporting.ai._has_acked", return_value=False))
        es.enter_context(
            patch("nx_lib.views.reporting.ai.make_agent_step", return_value=lambda m: next(turns))
        )
        run_sql_spy = es.enter_context(patch("nx_lib.views.reporting.ai._run_sql"))
        audit_spy = es.enter_context(patch("nx_lib.views.reporting.ai._audit_sql"))
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "how many?"})

    assert resp.status_code == 200  # never a raise-through 500
    trace = resp.get_json()["toolTrace"]
    run_sql_result = next(t["result"] for t in trace if t["name"] == "run_sql")
    assert run_sql_result["ok"] is False
    assert "acknowledg" in run_sql_result["error"].lower()
    run_sql_spy.assert_not_called()  # no SQL executed
    audit_spy.assert_called_once()
    assert audit_spy.call_args.args[-2] == "refused_ack"  # distinct status


def test_agent_grounding_names_run_sql_targets(user_client):
    from types import SimpleNamespace

    captured = {}

    def _fake_agentic(initial, *, registry, agent_step, **kw):
        captured["initial"] = initial
        return SimpleNamespace(
            answer="ok",
            stopped_reason="final",
            tool_trace=[],
            turns=1,
            tokens_in=1,
            tokens_out=1,
        )

    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch(
            "nx_lib.views.reporting.ai._ai_catalog_text", return_value="SOURCE docprocessing ..."
        ),
        patch("nx_lib.views.reporting.ai._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
        patch("nx_lib.views.reporting.ai.make_agent_step", return_value=lambda m: None),
        patch("nx_lib.views.reporting.ai.ask_agentic", side_effect=_fake_agentic),
        patch("nx_lib.views.reporting.ai._audit_ai"),
    ):
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "how many?"})
    assert resp.status_code == 200
    assert "statistics" in captured["initial"] and "octopus" in captured["initial"]
    assert "target" in captured["initial"]


# ---- POST /api/reporting/ai/caption (Task 12 — auto AI captions) ---------


def _caption_result(text="Sales rose sharply in Q2 across all regions."):
    return AiCaptionResult(
        caption=text,
        model="m",
        provider="anthropic",
        tokens_in=18,
        tokens_out=9,
    )


_CAPTION_BODY = {
    "columns": [{"field": "month", "header": "Month"}, {"field": "sales", "header": "Sales"}],
    "rows": [["Jan", 100], ["Feb", 120]],
    "title": "Monthly sales",
    "dateLabel": "2026",
}


def test_ai_caption_requires_explain_data_permission(user_client):
    # noperm@test.local (the user_client fixture) holds no reporting.* grants at
    # all, so the decorator's real has_permission check already denies this —
    # the explicit patch just matches the sibling ai/agent 403 test's shape.
    with patch("nx_lib.views.reporting.ai.has_permission", return_value=False):
        resp = user_client.post("/api/reporting/ai/caption", json=_CAPTION_BODY)
    assert resp.status_code == 403


def test_ai_caption_happy_path_returns_caption_and_audits(user_client):
    with (
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting.ai._ai_daily_limit", return_value=0),
        patch("nx_lib.views.reporting.ai.ai_caption", return_value=_caption_result()) as cap,
        patch("nx_lib.views.reporting.ai._audit_ai") as audit,
    ):
        resp = user_client.post("/api/reporting/ai/caption", json=_CAPTION_BODY)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["caption"] == "Sales rose sharply in Q2 across all regions."
    cap.assert_called_once()
    audit.assert_called_once()
    assert audit.call_args.args[3] == "caption"  # Surface positional arg
    assert audit.call_args.args[-2] == "ok"  # Status


def test_ai_caption_502_on_provider_error(user_client):
    with (
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting.ai._ai_daily_limit", return_value=0),
        patch("nx_lib.views.reporting.ai.ai_caption", side_effect=RuntimeError("boom")),
        patch("nx_lib.views.reporting.ai._audit_ai") as audit,
    ):
        resp = user_client.post("/api/reporting/ai/caption", json=_CAPTION_BODY)
    assert resp.status_code == 502
    data = resp.get_json()
    assert data["error"]  # translated error message present
    audit.assert_called_once()
    assert audit.call_args.args[-2] == "error"  # Status


def test_ai_caption_429_when_daily_limit_reached(user_client):
    with (
        patch("nx_lib.views.reporting.ai.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting.ai._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting.ai._ai_daily_limit", return_value=5),
        patch("nx_lib.views.reporting.ai._ai_asks_today", return_value=5),
        patch("nx_lib.views.reporting.ai.ai_caption") as cap,
        patch("nx_lib.views.reporting.ai._audit_ai") as audit,
    ):
        resp = user_client.post("/api/reporting/ai/caption", json=_CAPTION_BODY)
    assert resp.status_code == 429
    cap.assert_not_called()  # never calls the provider -> no token cost
    audit.assert_called_once()
    assert audit.call_args.args[-2] == "blocked"  # Status


# ---- POST /api/reporting/ai/agent — NDJSON progress stream ---------------


def test_ai_agent_streams_progress_then_done(user_client):
    """`stream: true` yields the loop's real steps, then one `done` payload."""
    events = [
        {"phase": "thinking", "turn": 1},
        {"phase": "note", "text": "Let me check the schema."},
        {"phase": "tool", "name": "build_definition"},
        {"result": _agentic_result()},
    ]
    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        es.enter_context(
            patch("nx_lib.views.reporting.ai.ask_agentic_iter", return_value=iter(events))
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._validate_definition_for_user",
                return_value=(True, None),
            )
        )
        audit = es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post(
            "/api/reporting/ai/agent", json={"question": "docs last month", "stream": True}
        )
        assert resp.mimetype == "application/x-ndjson"
        lines = [json.loads(x) for x in resp.get_data(as_text=True).splitlines() if x.strip()]

    assert [e.get("phase") for e in lines[:3]] == ["thinking", "note", "tool"]
    assert lines[2]["name"] == "build_definition"
    final = lines[-1]
    assert final["done"] is True
    assert final["answer"] == "Built a report by outcome."
    assert final["stoppedReason"] == "final"
    assert final["definition"]["title"] == "By outcome"
    audit.assert_called_once()
    assert audit.call_args.args[-2] == "ok"  # Status


def test_ai_agent_stream_reports_provider_failure_in_the_done_line(user_client):
    """Headers are already sent, so a mid-stream failure rides the last line."""

    def blow_up(*a, **kw):
        yield {"phase": "thinking", "turn": 1}
        raise RuntimeError("provider exploded")

    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        es.enter_context(patch("nx_lib.views.reporting.ai.ask_agentic_iter", side_effect=blow_up))
        audit = es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post(
            "/api/reporting/ai/agent", json={"question": "boom", "stream": True}
        )
        assert resp.status_code == 200  # status was committed before the failure
        lines = [json.loads(x) for x in resp.get_data(as_text=True).splitlines() if x.strip()]

    assert lines[0] == {"phase": "thinking", "turn": 1}
    assert lines[-1]["done"] is True
    assert lines[-1]["error"]
    audit.assert_called_once()
    assert audit.call_args.args[-2] == "error"  # Status


def test_ai_agent_without_stream_flag_still_returns_plain_json(user_client):
    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        es.enter_context(
            patch("nx_lib.views.reporting.ai.ask_agentic", return_value=_agentic_result())
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._validate_definition_for_user",
                return_value=(True, None),
            )
        )
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "docs"})
    assert resp.mimetype == "application/json"
    assert resp.get_json()["answer"] == "Built a report by outcome."


# ---- Issue #153: "Continue" past a max_turns/budget dead-end ---------------


def _stopped_result(reason):
    return AiAgenticResult(
        answer="",
        turns=10,
        tool_trace=[],
        stopped_reason=reason,
        tokens_in=20,
        tokens_out=12,
    )


def test_ai_agent_can_continue_when_stopped_on_max_turns(user_client):
    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai.ask_agentic",
                return_value=_stopped_result("max_turns"),
            )
        )
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "hard question"})
    data = resp.get_json()
    assert data["stoppedReason"] == "max_turns"
    assert data["continueAttempt"] == 0
    assert data["canContinue"] is True


def test_ai_agent_cannot_continue_when_stopped_on_final(user_client):
    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        es.enter_context(
            patch("nx_lib.views.reporting.ai.ask_agentic", return_value=_agentic_result())
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai._validate_definition_for_user",
                return_value=(True, None),
            )
        )
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "easy question"})
    data = resp.get_json()
    assert data["stoppedReason"] == "final"
    assert data["canContinue"] is False


def test_ai_agent_continue_attempt_raises_turn_and_budget_caps(user_client):
    from nx_lib.reporting.ai import CONTINUE_BUDGET_S, CONTINUE_MAX_TURNS

    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        ask = es.enter_context(
            patch(
                "nx_lib.views.reporting.ai.ask_agentic",
                return_value=_stopped_result("budget"),
            )
        )
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post(
            "/api/reporting/ai/agent",
            json={"question": "hard question", "continueAttempt": 1},
        )
    data = resp.get_json()
    assert data["continueAttempt"] == 1
    ask.assert_called_once()
    assert ask.call_args.kwargs["max_turns"] == CONTINUE_MAX_TURNS
    assert ask.call_args.kwargs["budget_s"] == CONTINUE_BUDGET_S


def test_ai_agent_continue_attempt_clamped_to_ceiling(user_client):
    from nx_lib.reporting.ai import MAX_CONTINUE_ATTEMPTS

    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        es.enter_context(
            patch(
                "nx_lib.views.reporting.ai.ask_agentic",
                return_value=_stopped_result("max_turns"),
            )
        )
        es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
        resp = user_client.post(
            "/api/reporting/ai/agent",
            json={"question": "hard question", "continueAttempt": 999},
        )
    data = resp.get_json()
    assert data["continueAttempt"] == MAX_CONTINUE_ATTEMPTS
    assert data["canContinue"] is False  # already at the ceiling


def test_ai_agent_report_context_is_grounded_and_rows_need_explain(user_client):
    """`report` in the body lands in the grounding; the fact sheet rides only on
    reporting.ai.explain.use, the definition summary always."""
    report = {
        "title": "Effort by category",
        "definition": {
            "schemaVersion": 1,
            "visualization": "table",
            "source": "docprocessing",
            "columns": [{"field": "processname"}],
            "metrics": [{"metric": "doc_count"}],
            "filters": [],
        },
        "columns": [
            {"field": "processname", "header": "Process"},
            {"field": "doc_count", "header": "Documents"},
        ],
        "rows": [["A", 3], ["B", 5]],
    }
    for explain in (False, True):
        with ExitStack() as es:
            for p in _agent_patches(explain_perm=explain):
                es.enter_context(p)
            loop = es.enter_context(
                patch("nx_lib.views.reporting.ai.ask_agentic", return_value=_agentic_result())
            )
            es.enter_context(
                patch(
                    "nx_lib.views.reporting.ai._get_effective_source",
                    return_value={
                        "id": "docprocessing",
                        "label": "Document Processing",
                        "kind": "curated",
                        "permission": "reporting.source.docprocessing.use",
                    },
                )
            )
            es.enter_context(
                patch(
                    "nx_lib.views.reporting.ai._load_db_metrics",
                    return_value={
                        "doc_count": {
                            "label": "Documents",
                            "aggregation": "count",
                            "base_field": None,
                            "description": "Number of documents",
                        },
                    },
                )
            )
            es.enter_context(
                patch(
                    "nx_lib.views.reporting.ai._validate_definition_for_user",
                    return_value=(True, None),
                )
            )
            es.enter_context(patch("nx_lib.views.reporting.ai._audit_ai"))
            user_client.post(
                "/api/reporting/ai/agent", json={"question": "what am I seeing", "report": report}
            )
        initial = loop.call_args.args[0]
        assert "currently looking at this report" in initial
        assert "Title: Effort by category" in initial
        assert "Documents [doc_count]: count -- Number of documents" in initial
        assert ("fact sheet" in initial) is explain
        assert ("Rows: 2" in initial) is explain
