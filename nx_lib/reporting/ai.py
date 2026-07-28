"""Provider-agnostic AI client for the Reporting assistant (Phase 1: NL -> T-SQL).

Pure and network-isolated for tests: the HTTP transport is injectable. The model
only *drafts* SQL; this module self-validates the draft through the existing
sqlglot gate (`sandbox.validate_select`) so the caller knows whether it is a
single read-only query before it ever reaches a database. Egress is schema-only:
the prompt carries the user's question + schema metadata, never result rows.
"""

import json
import os
import re
import time
from dataclasses import dataclass

import requests

from .sandbox import SqlSandboxError, validate_select

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
# Reasoning models (GPT-5 family) spend hidden reasoning tokens inside this
# budget before emitting output — 1024 truncates them to empty replies.
DEFAULT_MAX_TOKENS = 4096
# Per-turn HTTP read timeout. Reasoning models (GPT-5 family) routinely spend
# 30s+ on a single hard question, so a tight timeout turns a good answer into a
# generic 502. Override with AI_TIMEOUT_S when a deployment is slower still.
DEFAULT_TIMEOUT_S = int(os.environ.get("AI_TIMEOUT_S") or 120)
# Wall-clock ceiling for a whole agentic loop, so a slow model can't pin a
# worker for max_turns * DEFAULT_TIMEOUT_S.
DEFAULT_BUDGET_S = int(os.environ.get("AI_AGENT_BUDGET_S") or 180)

_SQL_FENCE = re.compile(r"```(?:sql|json)?\s*(.+?)```", re.IGNORECASE | re.DOTALL)

_SYSTEM = (
    "You are a careful Microsoft SQL Server (T-SQL) analyst for an internal "
    "reporting tool. Given a database schema and a question, return ONE read-only "
    "SELECT query that answers it. Rules: SELECT/WITH only; never INSERT, UPDATE, "
    "DELETE, MERGE, EXEC, or DDL; use only tables/columns present in the schema; "
    "prefer TOP (n) to bound large results. When the question asks for several "
    "counts/totals under DIFFERENT conditions (e.g. imported today and exported "
    "today), return one row with one column per number using conditional "
    "aggregation (SUM(CASE WHEN <condition> THEN 1 ELSE 0 END)) or scalar "
    "subqueries - NEVER combine the conditions with AND in a shared WHERE "
    "clause. Respond with STRICT JSON: "
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
        # GPT-5-family deployments reject `max_tokens`; `max_completion_tokens`
        # is accepted by every model from api-version 2024-10-21 on.
        "max_completion_tokens": max_tokens,
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
    "source's metrics line are valid."
    ' A source marked "metrics: none" cannot aggregate at all — for any'
    " counting/summing/averaging question prefer a source that lists metrics"
    " instead of inventing a code."
    " Fields flagged (grainable) are date "
    'fields: a column for one may carry "grain": '
    '"day"|"week"|"month"|"quarter"|"year" to bucket it; filters always use '
    "the raw date."
    ' When the question groups by a time period ("per month", "monthly",'
    ' "per week", "by quarter", "over the years"), the date column MUST carry'
    ' the matching "grain" — e.g. for "<things> per month this year":'
    ' "columns": [{"field": "<date key>", "header": "Month", "grain": "month"}],'
    ' "metrics": [{"metric": "<count code>"}], "filters": [{"field":'
    ' "<date key>", "op": "between", "value": {"token": "this_year"}}].'
    " A date column WITHOUT grain buckets per raw day, which contradicts any"
    " per-month/per-week/per-quarter/per-year question."
    ' Optionally include "chartHint": {"type": "bar"|"line"|"pie"|"doughnut", "x": "<category field>", "y": "<numeric field>"} inside the definition when a chart would help; omit it otherwise.'
    " Distinct/unique questions come in two shapes — pick the right one."
    ' (1) "List the distinct values of X": put X in "columns" and add a plain'
    " count metric — with metrics present the columns become GROUP BY"
    " dimensions, so each value appears once with its row count (bare columns"
    " with no metrics would return duplicate rows)."
    ' (2) "How many distinct X per Y": put ONLY Y in "columns" and use a'
    ' distinct-count metric of X — NEVER also add X to "columns": grouping by'
    " the very field being counted forces every count to 1. With no Y at all"
    ' ("how many distinct X in total"), use the distinct-count metric with'
    ' "columns": [].'
    ' Process ids in "allowed scope.processes" follow <client>.<NN_Name>; a'
    " humanized label is shown in parentheses next to each id. Match the"
    " user's process words case-insensitively against the whole id and its"
    ' label (e.g. "Privera Invoice" matches privera.03_Invoice_New). If'
    " several ids match, include ALL of them in scope.processes; if none"
    " clearly match, leave scope.processes empty (= all allowed) rather than"
    " guessing one."
    ' For RELATIVE time ranges ("last month", "this year", "letzte Woche"),'
    " set the date filter value to a relative-date token object instead of"
    ' literal dates: {"field": "<date key>", "op": "between", "value":'
    ' {"token": "last_month"}}. Valid tokens: today, yesterday, this_week,'
    " last_week, this_month, last_month, this_quarter, last_quarter,"
    " this_year, last_year, last_3_months,"
    ' and {"token": "last_n_days", "n": <1-366>}. "Last quarter" means the'
    " previous CALENDAR quarter — use last_quarter, never last_3_months (a"
    " rolling window that includes the current month). Token values are resolved"
    " against the CURRENT date on every run, so a saved report stays fresh."
    " Only grainable/date-typed fields accept tokens. For EXPLICIT dates"
    ' ("May 2026", "2026-01-01 to 2026-03-31") keep literal ISO dates.'
    " When a question constrains a TIME PERIOD without naming a specific date"
    " field, put the filter on a (grainable) processing-date field — default"
    " to the export date (export_date); use the import date (import_date)"
    " when the question says imported/received/arrived. Content dates such as"
    ' "Document Date" (the date printed on the document) are correct ONLY'
    " when the user names that field explicitly."
    " A definition has ONE shared filter set, so it CANNOT express several"
    ' numbers under DIFFERENT conditions (e.g. "how many imported today and'
    ' how many exported today" needs one count filtered on import_date and'
    " another filtered on export_date). NEVER AND-combine such conditions"
    " into filters — that counts only rows matching ALL of them, which"
    " answers a different question. Instead build the definition for the"
    " FIRST number only and use the explanation to tell the user this report"
    " answers that number and each remaining number needs its own report"
    " (one question per number)."
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


def _definition_user_prompt(
    question,
    catalog_text,
    prior_error,
    today=None,
    prior_question=None,
    prior_definition=None,
):
    base = ""
    if today:
        base += (
            f"Today's date is {today}. For relative time expressions "
            '("last month", "this year", "yesterday") emit a relative-date '
            "token as instructed; resolve explicit dates against this date, "
            "never against your training data.\n\n"
        )
    if prior_definition:
        compact = json.dumps(prior_definition, separators=(",", ":"))
        if prior_question:
            base += f'The user previously asked: "{prior_question}". You answered with this definition: {compact}\n'
        else:
            base += f"The user is viewing a report built from this definition: {compact}\n"
        base += "Modify the previous definition to satisfy the new request; keep everything the user did not ask to change.\n\n"
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
    prior_question=None,
    prior_definition=None,
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
        _definition_user_prompt(
            question,
            catalog_text,
            prior_error,
            today,
            prior_question=prior_question,
            prior_definition=prior_definition,
        ),
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
# Surface D — auto AI captions over a result grid (Task 12). Unlike ask() /
# ask_definition() (schema-only egress), `rows` here are the actual values a
# Simple/Advanced result is displaying, so callers must gate this behind
# reporting.ai.explain_data (the same data-egress grant used for run_sql /
# compute_stats in the agentic loop).
# ---------------------------------------------------------------------------

CAPTION_MAX_ROWS = 50

_CAPTION_SYSTEM = (
    "You are a concise data analyst for an internal reporting tool. Given a "
    "small table of report results, write ONE short caption that states the "
    "most notable pattern, standout value, or takeaway. Rules: 1-2 sentences, "
    'no preamble ("Here is...", "Looking at the data..."), no restating the '
    "question, no code fences or markdown, plain prose only. Answer in {locale}."
)


@dataclass
class AiCaptionResult:
    caption: str
    model: str
    provider: str
    tokens_in: int | None
    tokens_out: int | None


def _caption_user_prompt(columns, rows, title, date_label):
    headers = [c.get("header") or c.get("field") or "" for c in (columns or [])]
    lines = [", ".join(headers)] if headers else []
    for row in rows:
        cells = row if isinstance(row, list | tuple) else [row]
        lines.append(", ".join("" if v is None else str(v) for v in cells))
    table_text = "\n".join(lines)
    prefix = ""
    if title:
        prefix += f"Report: {title}\n"
    if date_label:
        prefix += f"Period: {date_label}\n"
    return f"{prefix}Data ({len(rows)} rows):\n{table_text}"


def caption(
    columns,
    rows,
    title=None,
    date_label=None,
    *,
    locale="en",
    cfg,
    max_tokens=DEFAULT_MAX_TOKENS,
    timeout=DEFAULT_TIMEOUT_S,
    transport=_http_post,
):
    """Draft a 1-2 sentence caption over a small result grid.

    `cfg` bundles the resolved provider settings the same way `_ai_config()` in
    the view module produces them (provider/api_key/model/endpoint/deployment/
    api_version/url) so the caller does not need to unpack it field-by-field.
    Rows are truncated to CAPTION_MAX_ROWS before the prompt is built, so an
    oversized grid never balloons the prompt or the bill — this is the single
    source of truth for the 50-row cap; the caller does not need to pre-slice.
    """
    rows = list(rows)[:CAPTION_MAX_ROWS]
    provider = (cfg.get("provider") or "").lower()
    text, tin, tout = _dispatch(
        _CAPTION_SYSTEM.format(locale=locale or "en"),
        _caption_user_prompt(columns, rows, title, date_label),
        provider=provider,
        model=cfg.get("model"),
        api_key=cfg.get("api_key"),
        endpoint=cfg.get("endpoint"),
        deployment=cfg.get("deployment"),
        api_version=cfg.get("api_version", "2024-10-21"),
        url=cfg.get("url"),
        max_tokens=max_tokens,
        timeout=timeout,
        transport=transport,
    )
    return AiCaptionResult(
        caption=(text or "").strip(),
        model=cfg.get("model"),
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

# 10 turns: with the data tools bound a full run is commonly build_definition
# (1-2 self-repairs) -> validate_sql -> run_sql -> final answer; 6 clipped the
# answer off exactly when the agent was doing its job.
DEFAULT_MAX_TURNS = 10

_AGENT_SYSTEM = (
    "You are a careful analyst for an internal reporting tool. Use the provided "
    "TOOLS to answer the question, grounded ONLY in the data SOURCES/SCHEMA given "
    "— never invent fields, tables, or sources. Prefer build_definition for any "
    "report the builder can express (it validates against the source field "
    "catalog). Pick the source whose fields fit the question best: for any "
    "counting/summing/averaging question use a source that lists metrics — a "
    'source marked "metrics: none" cannot aggregate at all. '
    "If validate_sql is available, draft ONE read-only SELECT and "
    "validate it before presenting. A definition's filters apply to the WHOLE "
    "report, so the builder CANNOT put two differently-filtered measures side by "
    'side (e.g. "imported documents and exported documents per month"). For such '
    "a question do NOT split it into two reports and do NOT give up: draft ONE "
    "T-SQL SELECT that groups by the period and uses conditional aggregation "
    "(SUM(CASE WHEN <condition> THEN 1 ELSE 0 END)) — one column per measure — "
    "and validate_sql it instead. When a tool returns an error, fix your input "
    "and try again — but after 2 failed attempts on the same tool stop calling it "
    "and write your final answer explaining what you could and could not do. "
    "Once a tool returns ok:true for the artifact that actually answers the whole "
    "question, stop calling tools immediately and give a one- or two-sentence "
    "plain-language answer. Do not ask the user questions."
    " The grounding states today's date; resolve relative time expressions"
    ' ("last month", "this year") against it, never against your training data.'
    ' For "list the distinct values of X" build a definition with X in'
    ' "columns" plus a plain count metric — metrics make the columns GROUP BY'
    ' dimensions. For "how many distinct X per Y" put ONLY Y in "columns" and'
    " use a distinct-count metric of X; never group by the counted field"
    " itself — that forces every count to 1."
    " Match process words against whole process ids and their"
    " humanized labels; include all matches, or none rather than a guess."
    " When you draft SQL over per-process tables and the question names no"
    " process, name in your answer which table(s) the numbers come from."
    " When a question groups by a time period (per day/week/month/quarter/"
    "year), the date column in the definition MUST carry the matching"
    ' "grain" (e.g. {"field": "<date key>", "grain": "month"}).'
    " Time-period filters go on a (grainable) processing-date field — export"
    " date by default, import date when the question says imported/received —"
    " never on content dates like Document Date unless the user names that"
    " field."
    " For relative time ranges set the date filter value to a token object,"
    ' e.g. {"field": "<date field>", "op": "between", "value": {"token": "last_month"}} (tokens: today,'
    " yesterday, this_week, last_week, this_month, last_month, this_quarter,"
    ' last_quarter, this_year, last_year, last_3_months, last_n_days with "n";'
    ' "last quarter" = the previous calendar quarter, i.e. last_quarter, not'
    " last_3_months) — these resolve at run"
    " time; keep literal ISO dates for explicit dates."
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
    "validate_sql or run_sql again after a successful run. After a failed run_sql, "
    "never resubmit the identical SQL; change the query before retrying. Report "
    "only concrete numbers taken from the data you fetched — never estimate or "
    "fabricate values."
    " run_sql can ONLY query the SQL-schema targets named below (e.g. statistics, "
    "octopus). NEVER pass a report SOURCE id as a table name, and NEVER call run_sql "
    "for a source marked 'builder-only' — answer those with build_definition instead. "
    "If a builder-only source needs a calculation build_definition cannot express, say "
    "so plainly rather than retrying run_sql."
    " When the question asks for concrete values (how many, which had the most, "
    "top N) about data run_sql can reach, a successful build_definition does NOT "
    "answer it — go on to validate_sql and run_sql and report the actual numbers; "
    "stop only once run_sql has returned the data."
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
    stopped_reason: str  # "final" | "max_turns" | "budget"
    tokens_in: int
    tokens_out: int


def ask_agentic(
    question,
    *,
    registry,
    agent_step,
    max_turns=DEFAULT_MAX_TURNS,
    history=None,
    budget_s=DEFAULT_BUDGET_S,
):
    """Drive the model->tool->model loop until a final answer or the turn cap.

    `agent_step(messages) -> AssistantTurn` is the injected provider round-trip
    (scripted in tests, built by `_make_agent_step` in production). `registry` is
    a ToolRegistry. Returns AiAgenticResult. No network/provider code lives here.

    `history` is an optional pre-validated list of prior `{"role": "user"|
    "assistant", "content": str}` turns, seeded ahead of the new question so a
    chat-style caller can carry conversation context into the loop. The caller
    is responsible for sanitizing/capping it; this function trusts it as-is.

    `messages` is the neutral conversation: user/assistant strings, an assistant
    turn carrying `tool_calls`, and a `tool` turn whose content is the list of
    `{tool_call_id, name, result}` envelopes. `_make_agent_step` translates this
    into each provider's wire format.
    """
    messages = [*(history or []), {"role": "user", "content": question}]
    trace, tin, tout, turns, stopped = [], 0, 0, 0, "max_turns"
    deadline = time.monotonic() + budget_s if budget_s else None
    while turns < max_turns:
        if deadline and turns and time.monotonic() > deadline:
            stopped = "budget"
            break
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
                "max_completion_tokens": max_tokens,
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
