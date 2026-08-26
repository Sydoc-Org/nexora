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


def test_dispatch_passes_system_and_user_through():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["body"] = body
        return {"content": [{"type": "text", "text": "{}"}], "usage": {}}

    ai._dispatch(
        "SYS",
        "USR",
        provider="anthropic",
        model="m",
        api_key="k",
        transport=transport,
    )
    # Anthropic body carries system top-level and the user message verbatim.
    assert captured["body"]["system"] == "SYS"
    assert captured["body"]["messages"][0]["content"] == "USR"


# ---- caption() (Task 12 — auto AI captions over a result grid) -----------


def test_caption_returns_stripped_text():
    body = {
        "content": [{"type": "text", "text": "  Sales rose sharply in Q2.  "}],
        "usage": {"input_tokens": 40, "output_tokens": 12},
    }
    res = ai.caption(
        columns=[{"field": "month", "header": "Month"}, {"field": "sales", "header": "Sales"}],
        rows=[["Jan", 100], ["Feb", 120]],
        title="Monthly sales",
        date_label="2026",
        locale="en",
        cfg={"provider": "anthropic", "model": "m", "api_key": "k"},
        transport=_fake_transport(body),
    )
    assert res.caption == "Sales rose sharply in Q2."
    assert res.tokens_in == 40
    assert res.tokens_out == 12


def test_caption_prompt_is_a_fact_sheet_over_all_rows():
    """The model never sees raw rows; it gets facts computed over the WHOLE
    grid (the old rows[:50] slice of an ascending series showed it the
    NULL-date bucket plus 2020 and it called that an outlier)."""
    captured = {}

    def transport(url, headers, body, timeout):
        captured["body"] = body
        return {"content": [{"type": "text", "text": "ok"}], "usage": {}}

    rows = [
        [None, 74_182],
        *[[f"2026-01-{d:02d}", 100 + d] for d in range(1, 30)],
        ["2026-01-30", 999],
    ]
    ai.caption(
        columns=[{"field": "day", "header": "Day"}, {"field": "n", "header": "N"}],
        rows=rows,
        title="Pages",
        date_label="Jan 2026",
        level_fields=("N",),
        locale="en",
        cfg={"provider": "anthropic", "model": "m", "api_key": "k"},
        transport=transport,
    )
    user_msg = captured["body"]["messages"][0]["content"]
    assert user_msg.startswith("Report: Pages\nPeriod: Jan 2026\nFacts:\n")
    assert "Rows with NO Day (1): N 74182" in user_msg
    assert "peak 999 (2026-01-30)" in user_msg  # the last row counted, not sliced away
    assert "N: current level 999 (2026-01-30)" in user_msg  # level_fields honoured
    assert "Data (" not in user_msg  # no raw table any more


def test_caption_notes_reach_the_prompt():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["body"] = body
        return {"content": [{"type": "text", "text": "ok"}], "usage": {}}

    ai.caption(
        columns=[{"field": "d", "header": "Month"}, {"field": "backlog", "header": "Backlog"}],
        rows=[["2026-07-01", 338], ["2026-08-01", None]],
        notes="The bucket 2026-08-01 is the current, still-running period.",
        locale="en",
        cfg={"provider": "anthropic", "model": "m", "api_key": "k"},
        transport=transport,
    )
    user_msg = captured["body"]["messages"][0]["content"]
    assert "Notes: The bucket 2026-08-01 is the current" in user_msg
    assert "NO measurement are missing data" in captured["body"]["system"]
