"""Provider-agnostic AI client for the Reporting assistant (Phase 1: NL -> T-SQL).

Pure and network-isolated for tests: the HTTP transport is injectable. The model
only *drafts* SQL; this module self-validates the draft through the existing
sqlglot gate (`sandbox.validate_select`) so the caller knows whether it is a
single read-only query before it ever reaches a database. Egress is schema-only:
the prompt carries the user's question + schema metadata, never result rows.
"""

import json
import re
from dataclasses import dataclass

import requests

from .sandbox import SqlSandboxError, validate_select

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TIMEOUT_S = 30

_SQL_FENCE = re.compile(r"```(?:sql|json)?\s*(.+?)```", re.IGNORECASE | re.DOTALL)

_SYSTEM = (
    "You are a careful Microsoft SQL Server (T-SQL) analyst for an internal "
    "reporting tool. Given a database schema and a question, return ONE read-only "
    "SELECT query that answers it. Rules: SELECT/WITH only; never INSERT, UPDATE, "
    "DELETE, MERGE, EXEC, or DDL; use only tables/columns present in the schema; "
    "prefer TOP (n) to bound large results. Respond with STRICT JSON: "
    '{"sql": "<the query>", "explanation": "<one sentence>"}. No prose outside JSON.'
)


class AiError(RuntimeError):
    """Raised when the AI client is misconfigured or the provider call fails."""


@dataclass
class AiResult:
    sql: str
    explanation: str
    valid: bool
    gate_verdict: str  # "valid" | "invalid"
    model: str
    provider: str
    tokens_in: int | None
    tokens_out: int | None


def _http_post(url, headers, body, timeout):
    resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _user_prompt(question, schema_text):
    return (
        f"Database schema (names/types/descriptions only):\n{schema_text}\n\n"
        f"Question: {question}\n\n"
        'Return STRICT JSON {"sql": ..., "explanation": ...}.'
    )


def _call_anthropic(system, user, *, model, api_key, url, max_tokens, timeout, transport):
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    data = transport(url or DEFAULT_ANTHROPIC_URL, headers, body, timeout)
    if isinstance(data, dict) and data.get("type") == "error":
        msg = (data.get("error") or {}).get("message", "unknown")
        raise AiError(f"provider error: {msg}")
    parts = data.get("content") or []
    text = "".join(p.get("text", "") for p in parts if p.get("type", "text") == "text")
    usage = data.get("usage") or {}
    return text, usage.get("input_tokens"), usage.get("output_tokens")


def _call_azure(
    system,
    user,
    *,
    model,
    api_key,
    endpoint,
    deployment,
    api_version,
    max_tokens,
    timeout,
    transport,
):
    if not endpoint or not deployment:
        raise AiError("Azure OpenAI requires endpoint and deployment")
    url = (
        f"{endpoint.rstrip('/')}/openai/deployments/{deployment}"
        f"/chat/completions?api-version={api_version}"
    )
    body = {
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    headers = {"api-key": api_key, "content-type": "application/json"}
    data = transport(url, headers, body, timeout)
    choices = data.get("choices") or [{}]
    text = (choices[0].get("message") or {}).get("content", "")
    usage = data.get("usage") or {}
    return text, usage.get("prompt_tokens"), usage.get("completion_tokens")


def _dispatch(
    system,
    user,
    *,
    provider,
    model,
    api_key,
    endpoint=None,
    deployment=None,
    api_version="2024-10-21",
    url=None,
    max_tokens=DEFAULT_MAX_TOKENS,
    timeout=DEFAULT_TIMEOUT_S,
    transport=_http_post,
):
    """Provider-agnostic single round-trip. Returns (text, tokens_in, tokens_out)."""
    if not api_key:
        raise AiError("AI provider API key is not configured")
    provider = (provider or "").lower()
    if provider == "anthropic":
        return _call_anthropic(
            system,
            user,
            model=model,
            api_key=api_key,
            url=url,
            max_tokens=max_tokens,
            timeout=timeout,
            transport=transport,
        )
    if provider == "azure":
        return _call_azure(
            system,
            user,
            model=model,
            api_key=api_key,
            endpoint=endpoint,
            deployment=deployment,
            api_version=api_version,
            max_tokens=max_tokens,
            timeout=timeout,
            transport=transport,
        )
    raise AiError(f"unknown AI provider: {provider!r}")


def _extract_json(text):
    """Return (sql, explanation) if `text` is a JSON object with an `sql` key, else None."""
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        return None
    if isinstance(obj, dict) and obj.get("sql"):
        return str(obj["sql"]).strip(), str(obj.get("explanation", "")).strip()
    return None


def _extract(text):
    """Pull (sql, explanation) from the model text: JSON first, then a fenced block.

    A fenced block may itself contain JSON (e.g. a ```json {...} ``` wrapper), so
    its inner content is re-parsed as JSON before falling back to the raw query.
    """
    text = (text or "").strip()
    found = _extract_json(text)
    if found:
        return found
    m = _SQL_FENCE.search(text)
    if m:
        inner = m.group(1).strip()
        return _extract_json(inner) or (inner, "")
    return text, ""


_SYSTEM_DEF = (
    "You are a careful analyst for an internal reporting tool. Given a list of "
    "available data SOURCES (each with a fixed set of fields, their types, and "
    "whether each field is filterable/sortable) and a question, return ONE report "
    "DEFINITION that answers it using ONLY one source and ONLY that source's "
    "fields. Do not invent fields or sources. Each field is listed as "
    '`key "Human Label":type`; every "field" value in your definition MUST be the '
    "exact key (the token before the quoted label), NEVER the label — the quoted "
    "label only helps you choose the right field and may be reused as a column "
    '"header". Respond with STRICT JSON: '
    '{"definition": {"schemaVersion": 1, "visualization": "table", "source": '
    '"<id>", "title": "<short>", "subtitle": null, "columns": [{"field": "<key>", '
    '"header": "<label>"}], "filters": [{"field": "<key>", "op": "<op>", "value": '
    '<v>}], "sort": [{"field": "<key>", "dir": "asc"|"desc"}], "scope": {"clients": '
    '[], "processes": []}, "rowLimit": 5000}, "explanation": "<one sentence>"}. '
    "Valid filter ops: eq, ne, in, not_in, gt, gte, lt, lte, between (value is a "
    "2-element list), contains, starts_with, is_null, is_not_null (these two take "
    "no value). No prose outside JSON."
    ' A source may list canonical "metrics" (code = aggregation(column)). To '
    'aggregate, include "metrics": [{"metric": "<code>"}] in the definition - '
    "the selected columns then become the GROUP BY dims. For a single grand "
    'total, use "metrics" with "columns": []. Only metric codes from the '
    "source's metrics line are valid. Fields flagged (grainable) are date "
    'fields: a column for one may carry "grain": '
    '"day"|"week"|"month"|"quarter"|"year" to bucket it; filters always use '
    "the raw date."
    ' Optionally include "chartHint": {"type": "bar"|"line"|"pie"|"doughnut", "x": "<category field>", "y": "<numeric field>"} inside the definition when a chart would help; omit it otherwise.'
    " When the question asks for the DISTINCT/different/unique values of a"
    ' field, put that field in "columns" AND add a count metric in "metrics" —'
    " with metrics present the selected columns become GROUP BY dimensions, so"
    " each value appears once (with its count). Never answer a distinct-values"
    " question with bare columns and no metrics: that returns duplicate rows."
    ' Process ids in "allowed scope.processes" follow <client>.<NN_Name>; a'
    " humanized label is shown in parentheses next to each id. Match the"
    " user's process words case-insensitively against the whole id and its"
    ' label (e.g. "Privera Invoice" matches privera.03_Invoice_New). If'
    " several ids match, include ALL of them in scope.processes; if none"
    " clearly match, leave scope.processes empty (= all allowed) rather than"
    " guessing one."
)


@dataclass
class AiDefinitionResult:
    definition: dict | None
    explanation: str
    model: str
    provider: str
    tokens_in: int | None
    tokens_out: int | None


def _parse_json_object(text):
    """Parse model text into a JSON object (dict), tolerating a ```json fence. None if not parseable."""
    text = (text or "").strip()
    m = _SQL_FENCE.search(text)
    candidates = [text, m.group(1).strip() if m else None]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            obj = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _definition_user_prompt(question, catalog_text, prior_error, today=None):
    base = ""
    if today:
        base += (
            f"Today's date is {today}. Resolve relative time expressions "
            '("last month", "this year", "yesterday") against this date, '
            "never against your training data.\n\n"
        )
    base += (
        f"Available sources and fields:\n{catalog_text}\n\n"
        f"Question: {question}\n\n"
        'Return STRICT JSON {"definition": {...}, "explanation": ...}.'
    )
    if prior_error:
        base += (
            f"\n\nYour previous attempt was REJECTED by the validator with: "
            f"{prior_error}\nFix it and return corrected STRICT JSON."
        )
    return base


def ask_definition(
    question,
    catalog_text,
    *,
    provider,
    model,
    api_key,
    endpoint=None,
    deployment=None,
    api_version="2024-10-21",
    url=None,
    prior_error=None,
    today=None,
    max_tokens=DEFAULT_MAX_TOKENS,
    timeout=DEFAULT_TIMEOUT_S,
    transport=_http_post,
):
    """Draft one v1 report-definition for `question`. Returns AiDefinitionResult.

    No DB validation here: `definition` is the parsed JSON object (or None if the
    reply was not parseable). The caller validates it against the source catalog
    and may retry once with `prior_error` set.
    """
    text, tin, tout = _dispatch(
        _SYSTEM_DEF,
        _definition_user_prompt(question, catalog_text, prior_error, today),
        provider=provider,
        model=model,
        api_key=api_key,
        endpoint=endpoint,
        deployment=deployment,
        api_version=api_version,
        url=url,
        max_tokens=max_tokens,
        timeout=timeout,
        transport=transport,
    )
    definition, explanation = None, ""
    obj = _parse_json_object(text)
    if isinstance(obj, dict):
        d = obj.get("definition")
        if isinstance(d, dict):
            definition = d
        explanation = str(obj.get("explanation", "")).strip()
    return AiDefinitionResult(
        definition=definition,
        explanation=explanation,
        model=model,
        provider=provider,
        tokens_in=tin,
        tokens_out=tout,
    )


def ask(
    question,
    schema_text,
    *,
    provider,
    model,
    api_key,
    endpoint=None,
    deployment=None,
    api_version="2024-10-21",
    url=None,
    max_tokens=DEFAULT_MAX_TOKENS,
    timeout=DEFAULT_TIMEOUT_S,
    transport=_http_post,
):
    """Draft one read-only SELECT for `question`. Returns an AiResult.

    Network is reached only through `transport` (injected in tests). The drafted
    SQL is validated through the sqlglot gate; an invalid draft is still returned
    (so the user can see/fix it) but flagged valid=False.
    """
    provider = (provider or "").lower()
    text, tin, tout = _dispatch(
        _SYSTEM,
        _user_prompt(question, schema_text),
        provider=provider,
        model=model,
        api_key=api_key,
        endpoint=endpoint,
        deployment=deployment,
        api_version=api_version,
        url=url,
        max_tokens=max_tokens,
        timeout=timeout,
        transport=transport,
    )

    sql, explanation = _extract(text)
    try:
        validate_select(sql)
        valid, verdict = True, "valid"
    except SqlSandboxError:
        valid, verdict = False, "invalid"
    return AiResult(
        sql=sql,
        explanation=explanation,
        valid=valid,
        gate_verdict=verdict,
        model=model,
        provider=provider,
        tokens_in=tin,
        tokens_out=tout,
    )


# ---------------------------------------------------------------------------
# Phase 3 — agentic tool-loop (Tier 2). The loop (`ask_agentic`) is provider-
# agnostic and drives model -> tool -> model until a final answer or a hard turn
# cap. Provider tool-calling parsing lives in `_make_agent_step`; both layers are
# unit-tested offline via injected seams (`agent_step` / `transport`). Egress
# stays schema-only: result rows fetched by run_sql are NOT sent back to the
# model here — narration over rows is Phase 3e (gated reporting.ai.explain_data).
# ---------------------------------------------------------------------------

DEFAULT_MAX_TURNS = 6

_AGENT_SYSTEM = (
    "You are a careful analyst for an internal reporting tool. Use the provided "
    "TOOLS to answer the question, grounded ONLY in the data SOURCES/SCHEMA given "
    "— never invent fields, tables, or sources. Prefer build_definition for any "
    "report the builder can express (it validates against the source field "
    "catalog). If validate_sql is available, draft ONE read-only SELECT and "
    "validate it before presenting. When a tool returns an error, fix your input "
    "and try again — but after 2 failed attempts on the same tool stop calling it "
    "and write your final answer explaining what you could and could not do. "
    "Once any tool returns ok:true, stop calling tools immediately and give a "
    "one- or two-sentence plain-language answer. Do not ask the user questions."
    " The grounding states today's date; resolve relative time expressions"
    ' ("last month", "this year") against it, never against your training data.'
    " For distinct/unique-values questions, build a definition with that field"
    ' in "columns" plus a count metric — metrics make the columns GROUP BY'
    " dimensions. Match process words against whole process ids and their"
    " humanized labels; include all matches, or none rather than a guess."
)

# Appended to the system prompt only when the caller holds reporting.ai.explain_data
# (Phase 3e). It unlocks the data-returning tools: run_sql feeds real result rows
# back to the model and compute_stats gives exact aggregates over them, so the model
# may narrate concrete numbers instead of only drafting an artifact.
_AGENT_EXPLAIN_SUFFIX = (
    " You may run validated read-only SELECTs with run_sql and summarise the actual "
    "rows returned, and use compute_stats for exact aggregates (describe, group_by, "
    "percentiles, value_counts, correlation, top_n) over rows you fetched. Always "
    "validate_sql before run_sql. Once run_sql returns ok:true stop calling tools "
    "and write your summary immediately from the data returned — do not call "
    "validate_sql or run_sql again after a successful run. Report only concrete "
    "numbers taken from the data you fetched — never estimate or fabricate values."
    " run_sql can ONLY query the SQL-schema targets named below (e.g. statistics, "
    "octopus). NEVER pass a report SOURCE id as a table name, and NEVER call run_sql "
    "for a source marked 'builder-only' — answer those with build_definition instead. "
    "If a builder-only source needs a calculation build_definition cannot express, say "
    "so plainly rather than retrying run_sql."
)


@dataclass
class AssistantTurn:
    """One normalized model turn: free text and/or a list of tool calls."""

    text: str = ""
    tool_calls: list | None = None  # [{"id", "name", "args"}]
    tokens_in: int | None = None
    tokens_out: int | None = None

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []


@dataclass
class AiAgenticResult:
    answer: str
    turns: int
    tool_trace: list  # [{"name", "args", "result"}]
    stopped_reason: str  # "final" | "max_turns"
    tokens_in: int
    tokens_out: int


def ask_agentic(question, *, registry, agent_step, max_turns=DEFAULT_MAX_TURNS):
    """Drive the model->tool->model loop until a final answer or the turn cap.

    `agent_step(messages) -> AssistantTurn` is the injected provider round-trip
    (scripted in tests, built by `_make_agent_step` in production). `registry` is
    a ToolRegistry. Returns AiAgenticResult. No network/provider code lives here.

    `messages` is the neutral conversation: user/assistant strings, an assistant
    turn carrying `tool_calls`, and a `tool` turn whose content is the list of
    `{tool_call_id, name, result}` envelopes. `_make_agent_step` translates this
    into each provider's wire format.
    """
    messages = [{"role": "user", "content": question}]
    trace, tin, tout, turns, stopped = [], 0, 0, 0, "max_turns"
    while turns < max_turns:
        turns += 1
        turn = agent_step(messages)
        tin += turn.tokens_in or 0
        tout += turn.tokens_out or 0
        if not turn.tool_calls:
            stopped = "final"
            messages.append({"role": "assistant", "content": turn.text})
            return AiAgenticResult(turn.text, turns, trace, stopped, tin, tout)
        messages.append({"role": "assistant", "content": turn.text, "tool_calls": turn.tool_calls})
        results = []
        for call in turn.tool_calls:
            result = registry.call(call["name"], call.get("args"))
            trace.append({"name": call["name"], "args": call.get("args"), "result": result})
            results.append({"tool_call_id": call.get("id"), "name": call["name"], "result": result})
        messages.append({"role": "tool", "content": results})
    return AiAgenticResult("", turns, trace, stopped, tin, tout)


def _azure_tools(tools):
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in tools
    ]


def _anthropic_tools(tools):
    return [
        {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
        for t in tools
    ]


def _to_azure_messages(system, messages):
    out = [{"role": "system", "content": system}]
    for m in messages:
        role = m["role"]
        if role == "tool":
            for r in m["content"]:
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": r.get("tool_call_id"),
                        "content": json.dumps(r.get("result"), default=str),
                    }
                )
        elif role == "assistant" and m.get("tool_calls"):
            out.append(
                {
                    "role": "assistant",
                    "content": m.get("content") or None,
                    "tool_calls": [
                        {
                            "id": c["id"],
                            "type": "function",
                            "function": {
                                "name": c["name"],
                                "arguments": json.dumps(c.get("args") or {}),
                            },
                        }
                        for c in m["tool_calls"]
                    ],
                }
            )
        else:
            out.append({"role": role, "content": m.get("content") or ""})
    return out


def _to_anthropic_messages(messages):
    out = []
    for m in messages:
        role = m["role"]
        if role == "tool":
            out.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": r.get("tool_call_id"),
                            "content": json.dumps(r.get("result"), default=str),
                        }
                        for r in m["content"]
                    ],
                }
            )
        elif role == "assistant" and m.get("tool_calls"):
            content = []
            if m.get("content"):
                content.append({"type": "text", "text": m["content"]})
            for c in m["tool_calls"]:
                content.append(
                    {
                        "type": "tool_use",
                        "id": c["id"],
                        "name": c["name"],
                        "input": c.get("args") or {},
                    }
                )
            out.append({"role": "assistant", "content": content})
        else:
            out.append({"role": role, "content": m.get("content") or ""})
    return out


def _parse_azure_turn(data):
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    usage = data.get("usage") or {}
    tin, tout = usage.get("prompt_tokens"), usage.get("completion_tokens")
    tool_calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except (ValueError, TypeError):
            args = {}
        tool_calls.append({"id": tc.get("id"), "name": fn.get("name"), "args": args})
    return AssistantTurn(
        text=msg.get("content") or "", tool_calls=tool_calls, tokens_in=tin, tokens_out=tout
    )


def _parse_anthropic_turn(data):
    if isinstance(data, dict) and data.get("type") == "error":
        msg = (data.get("error") or {}).get("message", "unknown")
        raise AiError(f"provider error: {msg}")
    parts = data.get("content") or []
    text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
    tool_calls = [
        {"id": p.get("id"), "name": p.get("name"), "args": p.get("input") or {}}
        for p in parts
        if p.get("type") == "tool_use"
    ]
    usage = data.get("usage") or {}
    return AssistantTurn(
        text=text,
        tool_calls=tool_calls,
        tokens_in=usage.get("input_tokens"),
        tokens_out=usage.get("output_tokens"),
    )


def _make_agent_step(
    *,
    system,
    tools,
    provider,
    model,
    api_key,
    endpoint=None,
    deployment=None,
    api_version="2024-10-21",
    url=None,
    max_tokens=DEFAULT_MAX_TOKENS,
    timeout=DEFAULT_TIMEOUT_S,
    transport=_http_post,
):
    """Build an `agent_step(messages) -> AssistantTurn` bound to a provider.

    Each call translates the neutral message list + tool specs into the provider's
    tool-calling wire format, POSTs via `transport`, and parses the reply back into
    an AssistantTurn. Network is reached only through `transport` (injected in tests).
    """
    if not api_key:
        raise AiError("AI provider API key is not configured")
    provider = (provider or "").lower()

    if provider == "azure":
        if not endpoint or not deployment:
            raise AiError("Azure OpenAI requires endpoint and deployment")
        azure_url = (
            f"{endpoint.rstrip('/')}/openai/deployments/{deployment}"
            f"/chat/completions?api-version={api_version}"
        )
        azure_tools = _azure_tools(tools)
        headers = {"api-key": api_key, "content-type": "application/json"}

        def step(messages):
            body = {
                "max_tokens": max_tokens,
                "messages": _to_azure_messages(system, messages),
                "tools": azure_tools,
            }
            return _parse_azure_turn(transport(azure_url, headers, body, timeout))

        return step

    if provider == "anthropic":
        anthropic_url = url or DEFAULT_ANTHROPIC_URL
        anthropic_tools = _anthropic_tools(tools)
        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        def step(messages):
            body = {
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": _to_anthropic_messages(messages),
                "tools": anthropic_tools,
            }
            return _parse_anthropic_turn(transport(anthropic_url, headers, body, timeout))

        return step

    raise AiError(f"unknown AI provider: {provider!r}")
