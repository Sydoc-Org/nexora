"""Integration tests for POST /api/reporting/ai/ask (perm gating + happy path)."""

from contextlib import ExitStack
from unittest.mock import patch

from nx_lib.reporting.ai import AiAgenticResult, AiDefinitionResult, AiError, AiResult

# The @require_permission decorator calls has_permission from nx_lib.security;
# inline calls inside api_ai_ask use the imported name in nx_lib.views.reporting.
# Both must be patched together when we want to bypass the permission checks.
_PERM_PATCHES = (
    "nx_lib.security.has_permission",
    "nx_lib.views.reporting.has_permission",
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
    with patch("nx_lib.views.reporting.has_permission", return_value=False):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "hi"})
    assert resp.status_code == 403


def test_ai_ask_503_when_provider_unconfigured(user_client):
    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config", return_value={"provider": "none", "api_key": None}
        ),
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "hi"})
    assert resp.status_code == 503


def test_ai_ask_happy_path_returns_sql_and_audits(user_client):
    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
        patch("nx_lib.views.reporting.ai_ask", return_value=_result()) as ask,
        patch("nx_lib.views.reporting._audit_ai") as audit,
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
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "   "})
    assert resp.status_code == 400


def test_ai_ask_502_on_provider_error(user_client):
    with (
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
        patch("nx_lib.views.reporting.ai_ask", side_effect=RuntimeError("boom")),
        patch("nx_lib.views.reporting._audit_ai") as audit,
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
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_daily_limit", return_value=5),
        patch("nx_lib.views.reporting._ai_asks_today", return_value=5),
        patch("nx_lib.views.reporting.ai_ask") as ask,
        patch("nx_lib.views.reporting._audit_ai") as audit,
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "x"})
    assert resp.status_code == 429
    ask.assert_not_called()  # never calls the provider -> no token cost
    audit.assert_called_once()
    assert audit.call_args.args[-2] == "blocked"  # status="blocked"


def test_ai_ask_allows_when_under_daily_limit(user_client):
    with (
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_daily_limit", return_value=5),
        patch("nx_lib.views.reporting._ai_asks_today", return_value=4),
        patch("nx_lib.views.reporting._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
        patch("nx_lib.views.reporting.ai_ask", return_value=_result()) as ask,
        patch("nx_lib.views.reporting._audit_ai"),
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "five ids"})
    assert resp.status_code == 200
    ask.assert_called_once()


def test_ai_ask_unlimited_when_limit_zero(user_client):
    # limit 0 disables the cap: the usage count is never queried.
    with (
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_daily_limit", return_value=0),
        patch("nx_lib.views.reporting._ai_asks_today") as count,
        patch("nx_lib.views.reporting._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
        patch("nx_lib.views.reporting.ai_ask", return_value=_result()) as ask,
        patch("nx_lib.views.reporting._audit_ai"),
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "five ids"})
    assert resp.status_code == 200
    ask.assert_called_once()
    count.assert_not_called()  # cap disabled -> no usage query


def _def_result(source="gen_pdqm"):
    return AiDefinitionResult(
        definition={
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
        explanation="by outcome",
        model="m",
        provider="anthropic",
        tokens_in=10,
        tokens_out=8,
    )


def test_ai_build_requires_use_permission(user_client):
    with patch("nx_lib.views.reporting.has_permission", return_value=False):
        resp = user_client.post("/api/reporting/ai/build", json={"question": "hi"})
    assert resp.status_code == 403


def test_ai_build_does_not_require_sql_permission(user_client):
    # Surface A: reporting.ai.use is enough; reporting.ai.sql is NOT consulted.
    def _has(code):
        return code != "reporting.ai.sql"

    with (
        patch("nx_lib.security.has_permission", side_effect=_has),
        patch("nx_lib.views.reporting.has_permission", side_effect=_has),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_daily_limit", return_value=0),
        patch("nx_lib.views.reporting._ai_catalog_text", return_value="SOURCE gen_pdqm ..."),
        patch("nx_lib.views.reporting.ai_ask_definition", return_value=_def_result()),
        patch("nx_lib.views.reporting._validate_definition_for_user", return_value=(True, None)),
        patch("nx_lib.views.reporting._audit_ai") as audit,
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
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_daily_limit", return_value=0),
        patch("nx_lib.views.reporting._ai_catalog_text", return_value="CATALOG"),
        patch("nx_lib.views.reporting.ai_ask_definition", return_value=_def_result()) as draft,
        patch(
            "nx_lib.views.reporting._validate_definition_for_user",
            return_value=(False, "unknown column field: 'Nope'"),
        ),
        patch("nx_lib.views.reporting._audit_ai"),
    ):
        resp = user_client.post("/api/reporting/ai/build", json={"question": "x"})
    assert resp.status_code == 200
    assert resp.get_json()["valid"] is False
    assert draft.call_count == 2  # initial + one self-repair retry


def test_ai_build_503_when_provider_unconfigured(user_client):
    with (
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config", return_value={"provider": "none", "api_key": None}
        ),
    ):
        resp = user_client.post("/api/reporting/ai/build", json={"question": "hi"})
    assert resp.status_code == 503


def test_ai_ask_audits_misconfig_on_aierror(user_client):
    # A configured-looking provider that raises AiError mid-call (e.g. unknown
    # provider / bad endpoint) -> 503, but it leaves a 'misconfig' audit trace so a
    # broken provider is debuggable. 'misconfig' (not 'error') keeps it off the cap.
    with (
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
        patch("nx_lib.views.reporting.ai_ask", side_effect=AiError("unknown provider")),
        patch("nx_lib.views.reporting._audit_ai") as audit,
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "x"})
    assert resp.status_code == 503
    audit.assert_called_once()
    assert audit.call_args.args[3] == "sql"  # Surface
    assert audit.call_args.args[-2] == "misconfig"  # Status


def test_ai_build_audits_misconfig_on_aierror(user_client):
    with (
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_daily_limit", return_value=0),
        patch("nx_lib.views.reporting._ai_catalog_text", return_value="CATALOG"),
        patch(
            "nx_lib.views.reporting.ai_ask_definition",
            side_effect=AiError("Azure OpenAI requires endpoint and deployment"),
        ),
        patch("nx_lib.views.reporting._audit_ai") as audit,
    ):
        resp = user_client.post("/api/reporting/ai/build", json={"question": "x"})
    assert resp.status_code == 503
    audit.assert_called_once()
    assert audit.call_args.args[3] == "definition"  # Surface
    assert audit.call_args.args[-2] == "misconfig"  # Status


# ---- POST /api/reporting/ai/agent (Phase 3d) -----------------------------


def _agentic_result(answer="Built a report by outcome.", definition_ok=True):
    trace = [
        {
            "name": "build_definition",
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
        if code == "reporting.ai.sql":
            return sql_perm
        if code == "reporting.ai.explain_data":
            return explain_perm
        if code == "reporting.sql.run":
            return run_perm
        return perm

    return [
        patch("nx_lib.security.has_permission", side_effect=_has),
        patch("nx_lib.views.reporting.has_permission", side_effect=_has),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_daily_limit", return_value=0),
        patch("nx_lib.views.reporting._ai_catalog_text", return_value="SOURCE gen_pdqm ..."),
        patch("nx_lib.views.reporting._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
    ]


def test_ai_agent_requires_use_permission(user_client):
    with patch("nx_lib.views.reporting.has_permission", return_value=False):
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "hi"})
    assert resp.status_code == 403


def test_ai_agent_503_when_provider_unconfigured(user_client):
    with (
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config", return_value={"provider": "none", "api_key": None}
        ),
    ):
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "hi"})
    assert resp.status_code == 503


def test_ai_agent_rejects_empty_question(user_client):
    with (
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
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
            patch("nx_lib.views.reporting.ask_agentic", return_value=_agentic_result())
        )
        es.enter_context(
            patch("nx_lib.views.reporting._validate_definition_for_user", return_value=(True, None))
        )
        audit = es.enter_context(patch("nx_lib.views.reporting._audit_ai"))
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


def test_ai_agent_429_when_daily_limit_reached(user_client):
    with (
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_daily_limit", return_value=5),
        patch("nx_lib.views.reporting._ai_asks_today", return_value=5),
        patch("nx_lib.views.reporting.ask_agentic") as loop,
        patch("nx_lib.views.reporting._audit_ai") as audit,
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
            patch("nx_lib.views.reporting.ask_agentic", side_effect=AiError("bad provider"))
        )
        audit = es.enter_context(patch("nx_lib.views.reporting._audit_ai"))
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
            patch("nx_lib.views.reporting.make_agent_step", side_effect=fake_make_step)
        )
        es.enter_context(
            patch("nx_lib.views.reporting.ask_agentic", return_value=_agentic_result())
        )
        es.enter_context(
            patch("nx_lib.views.reporting._validate_definition_for_user", return_value=(True, None))
        )
        es.enter_context(patch("nx_lib.views.reporting._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "x"})
    assert resp.status_code == 200
    assert "build_definition" in captured["tools"]
    assert "validate_sql" not in captured["tools"]  # gated on reporting.ai.sql


def test_ai_agent_binds_data_tools_with_explain_data_permission(user_client):
    """Phase 3e: reporting.ai.explain_data (+ reporting.sql.run) binds run_sql +
    compute_stats and injects the runner so result rows flow back to the model."""
    captured = {}

    def fake_make_step(**kwargs):
        captured["tools"] = [t["name"] for t in kwargs["tools"]]
        captured["system"] = kwargs["system"]
        return lambda messages: None

    def fake_loop(initial, *, registry, agent_step, **kw):
        captured["run_sql_bound"] = registry._run_sql is not None
        return _agentic_result()

    with ExitStack() as es:
        for p in _agent_patches(explain_perm=True, run_perm=True):
            es.enter_context(p)
        es.enter_context(
            patch("nx_lib.views.reporting.make_agent_step", side_effect=fake_make_step)
        )
        es.enter_context(patch("nx_lib.views.reporting.ask_agentic", side_effect=fake_loop))
        es.enter_context(
            patch("nx_lib.views.reporting._validate_definition_for_user", return_value=(True, None))
        )
        audit = es.enter_context(patch("nx_lib.views.reporting._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "how many?"})
    assert resp.status_code == 200
    assert resp.get_json()["explainData"] is True
    assert {"run_sql", "compute_stats"} <= set(captured["tools"])
    assert captured["run_sql_bound"] is True
    assert "run_sql" in captured["system"]  # explain suffix appended
    assert audit.call_args.args[-2] == "ok"


def test_ai_agent_no_data_tools_without_explain_data(user_client):
    """Default posture: without reporting.ai.explain_data the loop stays schema-only —
    run_sql / compute_stats are never bound and the runner is not injected."""
    captured = {}

    def fake_make_step(**kwargs):
        captured["tools"] = [t["name"] for t in kwargs["tools"]]
        captured["system"] = kwargs["system"]
        return lambda messages: None

    def fake_loop(initial, *, registry, agent_step, **kw):
        captured["run_sql_bound"] = registry._run_sql is not None
        return _agentic_result()

    with ExitStack() as es:
        for p in _agent_patches(explain_perm=False):
            es.enter_context(p)
        es.enter_context(
            patch("nx_lib.views.reporting.make_agent_step", side_effect=fake_make_step)
        )
        es.enter_context(patch("nx_lib.views.reporting.ask_agentic", side_effect=fake_loop))
        es.enter_context(
            patch("nx_lib.views.reporting._validate_definition_for_user", return_value=(True, None))
        )
        es.enter_context(patch("nx_lib.views.reporting._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "how many?"})
    assert resp.status_code == 200
    assert resp.get_json()["explainData"] is False
    assert "run_sql" not in captured["tools"]
    assert "compute_stats" not in captured["tools"]
    assert captured["run_sql_bound"] is False
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
            patch("nx_lib.views.reporting.make_agent_step", side_effect=fake_make_step)
        )
        es.enter_context(
            patch("nx_lib.views.reporting.ask_agentic", return_value=_agentic_result())
        )
        es.enter_context(
            patch("nx_lib.views.reporting._validate_definition_for_user", return_value=(True, None))
        )
        es.enter_context(patch("nx_lib.views.reporting._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "x"})
    assert resp.status_code == 200
    assert resp.get_json()["explainData"] is False
    assert "run_sql" not in captured["tools"]


def test_ai_agent_skips_data_tools_for_builder_only_source(user_client):
    """A builder-only curated source (table provider, e.g. Generali on GeneraliDB)
    is unreachable by run_sql, so the data tools are NOT bound even with
    explain_data + sql.run — the model must use build_definition instead of looping
    on run_sql 'invalid object name' errors against a source run_sql can't reach."""
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
            patch("nx_lib.views.reporting.make_agent_step", side_effect=fake_make_step)
        )
        es.enter_context(patch("nx_lib.views.reporting.ask_agentic", side_effect=fake_loop))
        es.enter_context(
            patch("nx_lib.views.reporting._validate_definition_for_user", return_value=(True, None))
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting._get_effective_source",
                return_value={
                    "id": "gen_pdqm",
                    "kind": "curated",
                    "provider": "generali",
                    "label": "Generali — PDQM Report",
                },
            )
        )
        es.enter_context(patch("nx_lib.views.reporting._audit_ai"))
        resp = user_client.post(
            "/api/reporting/ai/agent", json={"question": "how many?", "source": "gen_pdqm"}
        )
    assert resp.status_code == 200
    assert resp.get_json()["explainData"] is False
    assert "run_sql" not in captured["tools"]
    assert "compute_stats" not in captured["tools"]
    assert captured["run_sql_bound"] is False


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
            patch("nx_lib.views.reporting.make_agent_step", side_effect=fake_make_step)
        )
        es.enter_context(patch("nx_lib.views.reporting.ask_agentic", side_effect=fake_loop))
        es.enter_context(
            patch("nx_lib.views.reporting._validate_definition_for_user", return_value=(True, None))
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting._get_effective_source",
                return_value={
                    "id": "docproc",
                    "kind": "curated",
                    "provider": "docprocessing",
                    "label": "Document Processing",
                },
            )
        )
        es.enter_context(patch("nx_lib.views.reporting._audit_ai"))
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
    "permission": "reporting.source.generali.pdqm",
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
            patch("nx_lib.views.reporting._get_effective_source", return_value=_TABLE_SOURCE)
        )
        es.enter_context(patch("nx_lib.views.reporting.has_permission", return_value=True))
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
        "permission": "reporting.source.docprocessing",
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
            patch("nx_lib.views.reporting._get_effective_source", return_value=docproc_source)
        )
        es.enter_context(patch("nx_lib.views.reporting.has_permission", return_value=True))
        es.enter_context(patch("nx_lib.views.reporting.get_locale", return_value="en"))
        es.enter_context(
            patch(
                "nx_lib.views.reporting.fetch_docprocessing_catalog",
                return_value=catalog,
            )
        )
        es.enter_context(
            patch("nx_lib.views.reporting._allowed_processes", return_value=["acme.inv"])
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting._metrics_for_source",
                return_value={"doc_count": {"aggregation": "count", "base_field": None}},
            )
        )
        ok, err = _validate_definition_for_user(defn)

    assert (ok, err) == (True, None)


def test_validate_definition_zero_columns_with_metric_accepted():
    # The Simple wizard's "just the total": columns [] + a metric must validate.
    from nx_lib.views.reporting import _validate_definition_for_user

    docproc_source = {
        "id": "docprocessing",
        "kind": "curated",
        "label": "Document Processing",
        "permission": "reporting.source.docprocessing",
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
            patch("nx_lib.views.reporting._get_effective_source", return_value=docproc_source)
        )
        es.enter_context(patch("nx_lib.views.reporting.has_permission", return_value=True))
        es.enter_context(patch("nx_lib.views.reporting.get_locale", return_value="en"))
        es.enter_context(
            patch("nx_lib.views.reporting.fetch_docprocessing_catalog", return_value=[])
        )
        es.enter_context(
            patch("nx_lib.views.reporting._allowed_processes", return_value=["acme.inv"])
        )
        es.enter_context(
            patch(
                "nx_lib.views.reporting._metrics_for_source",
                return_value={"doc_count": {"aggregation": "count", "base_field": None}},
            )
        )
        ok, err = _validate_definition_for_user(defn)

    assert (ok, err) == (True, None)
