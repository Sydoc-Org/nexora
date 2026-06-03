"""Unit tests for the provider-agnostic reporting AI client (no DB, no network)."""

import json

import pytest

from nx_lib.reporting import ai


def _fake_transport(payload):
    """Return a transport() that yields a canned provider HTTP JSON body."""

    def transport(url, headers, body, timeout):
        return payload

    return transport


def test_ask_anthropic_extracts_sql_and_validates():
    # Anthropic /v1/messages response shape: content[].text + usage.
    answer = {"sql": "SELECT TOP (10) Name FROM dbo.Foo", "explanation": "Top 10 names."}
    body = {
        "content": [{"type": "text", "text": json.dumps(answer)}],
        "usage": {"input_tokens": 120, "output_tokens": 30},
    }
    res = ai.ask(
        "first 10 names",
        "TABLE dbo.Foo(Name nvarchar)",
        provider="anthropic",
        model="claude-sonnet-4-6",
        api_key="k",
        transport=_fake_transport(body),
    )
    assert res.sql == "SELECT TOP (10) Name FROM dbo.Foo"
    assert res.explanation == "Top 10 names."
    assert res.valid is True
    assert res.gate_verdict == "valid"
    assert res.tokens_in == 120 and res.tokens_out == 30
    assert res.model == "claude-sonnet-4-6"


def test_ask_azure_response_shape():
    answer = {"sql": "SELECT 1 AS X", "explanation": "constant"}
    body = {
        "choices": [{"message": {"content": json.dumps(answer)}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 8},
    }
    res = ai.ask(
        "give me one",
        "(* no schema *)",
        provider="azure",
        model="gpt-4o",
        api_key="k",
        endpoint="https://x.openai.azure.com",
        deployment="gpt-4o",
        transport=_fake_transport(body),
    )
    assert res.sql == "SELECT 1 AS X"
    assert res.valid is True
    assert res.tokens_in == 50 and res.tokens_out == 8


def test_ask_marks_invalid_when_model_emits_non_select():
    answer = {"sql": "DROP TABLE dbo.Foo", "explanation": "oops"}
    body = {"content": [{"type": "text", "text": json.dumps(answer)}], "usage": {}}
    res = ai.ask(
        "drop it",
        "TABLE dbo.Foo(Name)",
        provider="anthropic",
        model="m",
        api_key="k",
        transport=_fake_transport(body),
    )
    assert res.valid is False
    assert res.gate_verdict == "invalid"
    assert res.sql == "DROP TABLE dbo.Foo"  # still returned so the user sees it


def test_ask_falls_back_to_fenced_block_when_not_json():
    text = "Here you go:\n```sql\nSELECT 2 AS Y\n```\nThat returns 2."
    body = {"content": [{"type": "text", "text": text}], "usage": {}}
    res = ai.ask(
        "two",
        "(* none *)",
        provider="anthropic",
        model="m",
        api_key="k",
        transport=_fake_transport(body),
    )
    assert res.sql == "SELECT 2 AS Y"
    assert res.valid is True


def test_ask_unknown_provider_raises():
    with pytest.raises(ai.AiError):
        ai.ask("q", "s", provider="bogus", model="m", api_key="k", transport=_fake_transport({}))


def test_ask_raises_on_missing_api_key():
    with pytest.raises(ai.AiError):
        ai.ask(
            "q", "s", provider="anthropic", model="m", api_key=None, transport=_fake_transport({})
        )


def test_ask_azure_requires_endpoint_and_deployment():
    with pytest.raises(ai.AiError):
        ai.ask(
            "q",
            "s",
            provider="azure",
            model="gpt-4o",
            api_key="k",
            endpoint=None,
            deployment="gpt-4o",
            transport=_fake_transport({}),
        )


def test_ask_raises_on_anthropic_error_envelope():
    body = {"type": "error", "error": {"type": "overloaded_error", "message": "overloaded"}}
    with pytest.raises(ai.AiError):
        ai.ask(
            "q",
            "s",
            provider="anthropic",
            model="m",
            api_key="k",
            transport=_fake_transport(body),
        )


def test_ask_extracts_from_json_fence():
    text = '```json\n{"sql":"SELECT 3 AS Z","explanation":"three"}\n```'
    body = {"content": [{"type": "text", "text": text}], "usage": {}}
    res = ai.ask(
        "three",
        "(* none *)",
        provider="anthropic",
        model="m",
        api_key="k",
        transport=_fake_transport(body),
    )
    assert res.sql == "SELECT 3 AS Z"
    assert res.valid is True
