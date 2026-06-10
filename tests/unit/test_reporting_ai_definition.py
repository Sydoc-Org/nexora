"""Unit tests for ask_definition() — NL -> v1 report-definition (no DB, no network)."""

import json

from nx_lib.reporting import ai


def _transport(body):
    def t(url, headers, body_, timeout):
        return body

    return t


def _anthropic_body(obj):
    return {
        "content": [{"type": "text", "text": json.dumps(obj)}],
        "usage": {"input_tokens": 100, "output_tokens": 40},
    }


def test_ask_definition_parses_definition_and_explanation():
    obj = {
        "definition": {
            "schemaVersion": 1,
            "visualization": "table",
            "source": "gen_pdqm",
            "title": "PDQM rejections",
            "columns": [{"field": "Outcome"}],
            "filters": [],
            "sort": [],
            "scope": {"clients": [], "processes": []},
            "rowLimit": 5000,
        },
        "explanation": "Rejections by outcome.",
    }
    res = ai.ask_definition(
        "pdqm rejections",
        "SOURCE gen_pdqm: Outcome:string(filterable,sortable)",
        provider="anthropic",
        model="m",
        api_key="k",
        transport=_transport(_anthropic_body(obj)),
    )
    assert res.definition["source"] == "gen_pdqm"
    assert res.definition["columns"][0]["field"] == "Outcome"
    assert res.explanation == "Rejections by outcome."
    assert res.tokens_in == 100 and res.tokens_out == 40
    assert res.model == "m" and res.provider == "anthropic"


def test_ask_definition_returns_none_definition_on_unparseable_reply():
    body = {"content": [{"type": "text", "text": "I cannot help with that."}], "usage": {}}
    res = ai.ask_definition(
        "junk",
        "(* none *)",
        provider="anthropic",
        model="m",
        api_key="k",
        transport=_transport(body),
    )
    assert res.definition is None  # route will treat as an invalid draft


def test_ask_definition_includes_prior_error_in_retry_prompt():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["user"] = body["messages"][0]["content"]
        return _anthropic_body({"definition": {}, "explanation": ""})

    ai.ask_definition(
        "q",
        "CATALOG",
        provider="anthropic",
        model="m",
        api_key="k",
        prior_error="unknown column field: 'Nope'",
        transport=transport,
    )
    assert "unknown column field" in captured["user"]


def test_system_def_documents_metrics_and_grain():
    from nx_lib.reporting.ai import _SYSTEM_DEF

    assert '"metrics"' in _SYSTEM_DEF
    assert '"grain"' in _SYSTEM_DEF
    assert "grainable" in _SYSTEM_DEF


def test_agent_system_prompt_stops_after_repeated_failures():
    from nx_lib.reporting.ai import _AGENT_SYSTEM

    # gpt-4o-mini loops forever when build_definition keeps failing;
    # the prompt must tell it to stop and explain after a bounded number of retries.
    assert "2 failed" in _AGENT_SYSTEM


def test_agent_system_prompt_stops_after_successful_tool():
    from nx_lib.reporting.ai import _AGENT_SYSTEM

    # After any tool returns ok:true the model must give a final text answer,
    # not call more tools.
    assert "ok:true" in _AGENT_SYSTEM or "ok: true" in _AGENT_SYSTEM


def test_agent_explain_suffix_stops_after_run_sql():
    from nx_lib.reporting.ai import _AGENT_EXPLAIN_SUFFIX

    # After run_sql returns data the model must stop looping and write its summary.
    lower = _AGENT_EXPLAIN_SUFFIX.lower()
    assert "stop" in lower and "run_sql" in lower


def test_system_def_teaches_distinct_via_metrics():
    s = ai._SYSTEM_DEF
    assert "distinct" in s.lower()
    assert "GROUP BY" in s
    assert "duplicate rows" in s


def test_system_def_teaches_process_matching():
    s = ai._SYSTEM_DEF
    assert "scope.processes" in s
    assert "include ALL of them" in s


def test_ask_definition_includes_today_in_prompt():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["user"] = body["messages"][0]["content"]
        return _anthropic_body({"definition": {}, "explanation": ""})

    ai.ask_definition(
        "docs last month",
        "CATALOG",
        provider="anthropic",
        model="m",
        api_key="k",
        today="2026-06-10",
        transport=transport,
    )
    assert "Today's date is 2026-06-10" in captured["user"]
    # The date line precedes the catalog so the model reads it first.
    assert captured["user"].index("Today's date") < captured["user"].index("CATALOG")


def test_ask_definition_omits_date_line_without_today():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["user"] = body["messages"][0]["content"]
        return _anthropic_body({"definition": {}, "explanation": ""})

    ai.ask_definition(
        "q",
        "CATALOG",
        provider="anthropic",
        model="m",
        api_key="k",
        transport=transport,
    )
    assert "Today's date" not in captured["user"]


def test_system_def_teaches_relative_date_tokens():
    s = ai._SYSTEM_DEF
    assert '{"token": "last_month"}' in s
    assert "last_n_days" in s
    assert "resolved against the CURRENT date" in s


def test_ask_definition_includes_refine_context():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["user"] = body["messages"][0]["content"]
        return _anthropic_body({"definition": {}, "explanation": ""})

    ai.ask_definition(
        "only the Privera invoice process",
        "CATALOG",
        provider="anthropic",
        model="m",
        api_key="k",
        prior_question="docs last month",
        prior_definition={"schemaVersion": 1, "title": "t"},
        transport=transport,
    )
    assert 'The user previously asked: "docs last month"' in captured["user"]
    # Compact JSON (no spaces) keeps the prompt small.
    assert '{"schemaVersion":1,"title":"t"}' in captured["user"]
    # The refine block precedes the catalog so the model reads it first.
    assert captured["user"].index("previously asked") < captured["user"].index("CATALOG")


def test_ask_definition_omits_refine_context_by_default():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["user"] = body["messages"][0]["content"]
        return _anthropic_body({"definition": {}, "explanation": ""})

    ai.ask_definition(
        "q",
        "CATALOG",
        provider="anthropic",
        model="m",
        api_key="k",
        transport=transport,
    )
    assert "previously asked" not in captured["user"]


def test_ask_definition_refine_context_requires_both_priors():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["user"] = body["messages"][0]["content"]
        return _anthropic_body({"definition": {}, "explanation": ""})

    ai.ask_definition(
        "q",
        "CATALOG",
        provider="anthropic",
        model="m",
        api_key="k",
        prior_question="docs last month",  # definition missing -> no refine block
        transport=transport,
    )
    assert "previously asked" not in captured["user"]
