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

from .caption_facts import build_facts
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
# Reasoning effort for Azure GPT-5-family deployments. Left unset, they run at
# the API default (medium) on every call: gpt-5-mini averaged 54.8s per agent
# run and 8.0s to caption a one-line label, 7-9x the gpt-4o-mini it replaced.
# Single-shot surfaces (caption/definition/sql) need no deliberation; only the
# agent loop, which chains tool calls, earns the extra thinking.
EFFORT_SINGLE_SHOT = "low"
EFFORT_AGENT = "medium"
# `reasoning_effort` is accepted by GPT-5/o-series deployments and rejected
# with a 400 by everything else (gpt-4o-mini included), so it can't be sent
# unconditionally the way `max_completion_tokens` is. The deployment name is
# the only signal available client-side.
# ponytail: prefix match on the deployment name — an off-pattern name just
# gets today's behaviour (no param, API default). If someone names a
# reasoning deployment 'eddard', add an AZURE_REASONING_EFFORT env override.
_REASONING_DEPLOYMENT_PREFIXES = ("gpt-5", "o1", "o3", "o4")

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


def _reasoning_body(deployment, effort):
    """`{"reasoning_effort": effort}` for reasoning deployments, else `{}`."""
    name = (deployment or "").lower()
    if effort and name.startswith(_REASONING_DEPLOYMENT_PREFIXES):
        return {"reasoning_effort": effort}
    return {}


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
    effort=EFFORT_SINGLE_SHOT,
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
        **_reasoning_body(deployment, effort),
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
    effort=EFFORT_SINGLE_SHOT,
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
            effort=effort,
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

# Payload guard only. Rows never reach the model raw any more: the whole grid
# is reduced to a fact sheet (caption_facts.build_facts) and that is what the
# prompt carries. Before (cap 50, rows[:50] of an ascending time series) the
# model saw the NULL-date bucket plus 2020 and called it "a clear outlier".
CAPTION_MAX_ROWS = 5000

_CAPTION_SYSTEM = (
    "You are a concise data analyst for an internal reporting tool. You get a "
    "FACT SHEET computed exactly over the complete result — not the raw table. "
    "Write ONE caption, at most 2 sentences and about 40 words, giving a manager "
    "the single most useful takeaway: the headline total (or, for a level such "
    "as a backlog, its latest value; with several measures name each headline "
    "briefly), then the one thing that matters most — trend, peak, "
    "concentration, or a caveat the facts flag. Rules: use only "
    "numbers from the facts, rounded sensibly and formatted for {locale} "
    "(thousands separators); never invent, extrapolate, or recite every fact; "
    "buckets with NO measurement are missing data, never zero or a drop; rows "
    "with NO <dimension> are not a period or category — mention them, if at all, "
    "as rows without a date; a still-running bucket is incomplete — never call it "
    "a decline or compare it with finished ones; a percentage on a near-zero "
    "baseline is noise; follow any Notes. No preamble, no restating the report "
    "title, no code fences or markdown, plain prose only. Answer in {locale}."
)


@dataclass
class AiCaptionResult:
    caption: str
    model: str
    provider: str
    tokens_in: int | None
    tokens_out: int | None


def _caption_user_prompt(columns, rows, title, date_label, notes=None, level_fields=()):
    prefix = ""
    if title:
        prefix += f"Report: {title}\n"
    if date_label:
        prefix += f"Period: {date_label}\n"
    if notes:
        prefix += f"Notes: {notes}\n"
    facts = build_facts(columns, rows, level_fields=level_fields)
    return f"{prefix}Facts:\n{facts}"


def caption(
    columns,
    rows,
    title=None,
    date_label=None,
    *,
    notes=None,
    level_fields=(),
    locale="en",
    cfg,
    max_tokens=DEFAULT_MAX_TOKENS,
    timeout=DEFAULT_TIMEOUT_S,
    transport=_http_post,
):
    """Draft a 1-2 sentence caption over a result grid.

    The model never sees the rows: `caption_facts.build_facts` reduces the whole
    grid to exact facts (totals, peak, latest vs previous, missing vs zero
    buckets, the NULL-key rows, the still-running bucket) and the prompt
    carries those, so it cannot mis-aggregate a truncated sample.

    `notes`: optional caller-supplied context the model must honour — e.g.
    "the last bucket is the current, still-running month" or "empty cells are
    buckets with no snapshot" — so it doesn't narrate artefacts as findings.
    `level_fields`: field/header names of level measures (backlog) whose
    headline is the latest value, not a sum.

    `cfg` bundles the resolved provider settings the same way `_ai_config()` in
    the view module produces them (provider/api_key/model/endpoint/deployment/
    api_version/url) so the caller does not need to unpack it field-by-field.
    Rows are truncated to CAPTION_MAX_ROWS (a payload guard; the fact sheet's
    size does not grow with the row count) — the caller need not pre-slice.
    """
    rows = list(rows)[:CAPTION_MAX_ROWS]
    provider = (cfg.get("provider") or "").lower()
    text, tin, tout = _dispatch(
        _CAPTION_SYSTEM.format(locale=locale or "en"),
        _caption_user_prompt(columns, rows, title, date_label, notes, level_fields),
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

# Issue #153: raised caps for a user-initiated "Continue" retry after the loop
# hit max_turns/budget the first time. Double the default rather than
# unbounded — cross-process aggregate questions (post-#128) can legitimately
# need more turns, but this still isn't a resume, just a fresh run with more
# room, so it stays finite. MAX_CONTINUE_ATTEMPTS caps how many times a single
# question can be retried this way.
CONTINUE_MAX_TURNS = DEFAULT_MAX_TURNS * 2
CONTINUE_BUDGET_S = DEFAULT_BUDGET_S * 2
MAX_CONTINUE_ATTEMPTS = 2

# Issue #127: sent once when the model ends its turn with neither tool calls
# nor text. Model-facing, English by design (like the tool results).
_EMPTY_FINAL_NUDGE = (
    "You returned no answer text. Write your final answer for the user now, "
    "based on the work above. If you could not complete the task, say so "
    "briefly, describe what you tried, and mention any query or report "
    "definition you produced."
)

_AGENT_SYSTEM = (
    "You are a careful analyst for an internal reporting tool. Use the provided "
    "TOOLS to answer the question, grounded ONLY in the data SOURCES/SCHEMA given "
    "— never invent fields, tables, or sources. Prefer build_definition for any "
    "report the builder can express (it validates against the source field "
    "catalog). Pick the source whose fields fit the question best: for any "
    "counting/summing/averaging question use a source that lists metrics — a "
    'source marked "metrics: none" cannot aggregate at all. '
    "If validate_sql is available, draft ONE read-only SELECT and "
    "validate it before presenting. Metrics whose catalog line carries "
    '"anchor=<date>" (documents/pages imported, documents/pages exported, '
    "backlog) each count on their OWN date and plot together on the shared "
    '"activity_date" field: for imported-vs-exported-vs-backlog over time, '
    "the imported/exported/backlog totals, or any question about the backlog, "
    "ALWAYS use build_definition with those metrics, "
    '"columns": [{"field": "activity_date", "grain": <period>}] and the time '
    "filter on activity_date. That definition IS the business definition "
    "(process scope, deleted-document rules, newest snapshot per bucket); never "
    "re-derive a backlog or an import/export comparison in raw SQL when the "
    "source lists anchored metrics — SQL there gives different numbers than "
    "the reports users see. Anchored metrics cannot be mixed with plain "
    "metrics in one definition. For OTHER pairs of differently-filtered "
    "measures the builder cannot express, do NOT split them into two reports "
    "and do NOT give up: draft ONE T-SQL SELECT that groups by the period and "
    "uses conditional aggregation (SUM(CASE WHEN <condition> THEN 1 ELSE 0 END)) "
    "— one column per measure — and validate_sql it instead. When a tool "
    "returns an error, fix your input "
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
    " The SQL schema marks some tables as per-process PARTIAL tables: each holds"
    " ONE process, not the company. A totals question that names no process"
    ' ("our volume", "the numbers", "how many documents", "total") is'
    " company-wide — answer it from the source that unions all processes"
    " (build_definition), not from one process table. When raw SQL is genuinely"
    " needed, UNION every relevant partial table rather than picking one — but"
    " these tables do NOT share column names, so if the UNION fails twice, stop"
    " and answer with build_definition instead, saying why. Every SQL answer must"
    " name which processes its numbers cover, and an empty or zero result from a"
    " single partial table must be reported as zero FOR THAT PROCESS — never as"
    " zero company-wide."
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
    # Issue #132 case 17: "show me the numbers for the last quarter" got a
    # silently-picked reading (calendar Q2, two arbitrary metrics, one process
    # table) presented as "the numbers". Asking is off the table here — the rule
    # above forbids it — so the interpretation has to be visible in the answer.
    " When the question underdetermines the answer — which metric, calendar"
    " versus rolling period, or which processes/scope — do NOT silently pick"
    " one and present it as the answer. Take the most reasonable reading, and"
    " open your answer with one sentence naming the reading you used and the"
    " main alternative (\"Reading 'last quarter' as the calendar quarter and"
    " showing document volume across all processes — say so if you meant the"
    ' rolling last 3 months").'
    # Issue #132: the caveats a stakeholder needs were missing across cases 1, 4,
    # 8, 11, 13 and 15 — a partial current month reported as a drop, +200% off a
    # baseline of 3, assumed-NULL columns inflating a backlog, "yes it's
    # seasonal" from a single TOP 1 row.
    " Before you finish, check these four and state in ONE short sentence any"
    " that apply (say nothing if none do): (a) PARTIAL PERIOD — the current"
    " month/quarter/week is still running, so its number is incomplete and not"
    " comparable to a finished one unless you aligned the windows; (b) SMALL"
    " N — a percentage resting on a tiny or near-zero baseline is noise, so"
    " give the underlying counts alongside it; (c) ASSUMPTIONS — rows or"
    " tables you excluded, skipped or treated as NULL, and fields only some"
    " processes populate; (d) THIN EVIDENCE — a single top row, or two years"
    " of history, does not establish a trend or seasonality, so describe what"
    " the data shows instead of asserting the pattern."
    # Issue #132 cases 9, 18, 20: quit at turn 5 of 10 telling the user to run
    # the comparison themselves, or shipped a query it never executed as if the
    # numbers were real.
    " Never present a query you did not execute as though it produced numbers:"
    " if you only drafted or validated SQL, say plainly that it has not been"
    " run. And do not hand the question back — while turns remain and the"
    " question is unanswered, try a different angle yourself (a simpler query,"
    " a definition, fewer parts at a time) rather than giving the user"
    " instructions to run it."
    " When a follow-up only changes HOW the previous answer is presented"
    " (as a chart, as a table, a different breakdown of the SAME data), stay"
    " on the same source and data as that answer — reuse the"
    " [sql from this answer] / [report definition from this answer] context"
    " carried in the conversation. Switching to a different source for a"
    " presentation-only follow-up is wrong."
)

# Appended to the system prompt only when the caller holds reporting.ai.explain_data
# (Phase 3e). It unlocks the data-returning tools: run_sql feeds real result rows
# back to the model, run_definition executes a build_definition-shaped definition
# for real, and compute_stats gives exact aggregates over them, so the model may
# narrate concrete numbers instead of only drafting an artifact.
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
    " A build_definition that returns ok:true has only validated the SHAPE — it has"
    " NOT run. When the question wants concrete values (anchored metrics like"
    " imported/exported/backlog, or any other business-definition question),"
    " call run_definition with that same definition to fetch the real rows before"
    " you answer — this runs the exact query the report builder would run, so the"
    " numbers match what users see on the report. Once run_definition returns"
    " ok:true, answer from its rows and stop calling tools; never present a"
    " validated-but-unexecuted definition's shape as though it were the answer."
    " run_sql can ONLY query the SQL-schema targets named below (e.g. statistics, "
    "octopus). NEVER pass a report SOURCE id as a table name, and NEVER call run_sql "
    "for a source marked 'builder-only' — answer those with build_definition instead. "
    "If a builder-only source needs a calculation build_definition cannot express, say "
    "so plainly rather than retrying run_sql."
    " When the question asks for concrete values (how many, which had the most, "
    "top N) about data run_sql can reach, a successful build_definition does NOT "
    "answer it — go on to validate_sql and run_sql and report the actual numbers; "
    "stop only once run_sql has returned the data."
    " This never licenses narrowing the universe: SQL that reaches one per-process"
    " partial table does NOT answer a company-wide question — UNION them or use"
    " build_definition, and state the coverage either way."
    " T-SQL discipline for drafted SQL: alias every table and derived table;"
    " qualify every column that appears in more than one table, CTE or UNION"
    " branch; give every computed column an explicit alias; in a set"
    " operation put ORDER BY only after the LAST branch (never inside inner"
    " branches or a derived table without TOP)."
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


def ask_agentic_iter(
    question,
    *,
    registry,
    agent_step,
    max_turns=DEFAULT_MAX_TURNS,
    history=None,
    budget_s=DEFAULT_BUDGET_S,
):
    """Same loop as `ask_agentic`, yielded step by step so a caller can stream it.

    Yields progress events as plain dicts while the loop runs — `{"phase":
    "thinking", "turn": n}` before each provider round-trip, `{"phase": "note",
    "text": ...}` for the model's own preamble on a tool turn, and `{"phase":
    "tool", "name": ...}` before each tool call — and finally exactly one
    `{"result": AiAgenticResult}`. The final event is always yielded, so a
    consumer can just read until it sees `"result"`.
    """
    messages = [*(history or []), {"role": "user", "content": question}]
    trace, tin, tout, turns, stopped = [], 0, 0, 0, "max_turns"
    nudged = False
    deadline = time.monotonic() + budget_s if budget_s else None
    while turns < max_turns:
        if deadline and turns and time.monotonic() > deadline:
            stopped = "budget"
            break
        turns += 1
        yield {"phase": "thinking", "turn": turns}
        turn = agent_step(messages)
        tin += turn.tokens_in or 0
        tout += turn.tokens_out or 0
        if not turn.tool_calls:
            # Issue #127: the model sometimes ends a turn with no tool calls
            # AND no text — accepted as-is, that surfaces as a blank chat
            # bubble. Nudge it exactly once to write the answer it owes;
            # a second silent turn falls through to the normal final path
            # (the view layer substitutes a fallback message for the empty
            # answer).
            if not (turn.text or "").strip() and not nudged and turns < max_turns:
                nudged = True
                messages.append({"role": "assistant", "content": turn.text or ""})
                messages.append({"role": "user", "content": _EMPTY_FINAL_NUDGE})
                continue
            stopped = "final"
            messages.append({"role": "assistant", "content": turn.text})
            yield {"result": AiAgenticResult(turn.text, turns, trace, stopped, tin, tout)}
            return
        messages.append({"role": "assistant", "content": turn.text, "tool_calls": turn.tool_calls})
        if (turn.text or "").strip():
            yield {"phase": "note", "text": turn.text.strip()}
        results = []
        for call in turn.tool_calls:
            yield {"phase": "tool", "name": call["name"]}
            result = registry.call(call["name"], call.get("args"))
            trace.append({"name": call["name"], "args": call.get("args"), "result": result})
            results.append({"tool_call_id": call.get("id"), "name": call["name"], "result": result})
            # Carries the RAW tool output -- for the view layer to distill
            # into the tiny build-stage preview (stage_preview below).
            # Consumers that forward events to a client must map or drop it,
            # never relay it. Key is "output", NOT "result": every consumer
            # detects the loop's final event via `"result" in event`.
            yield {
                "phase": "tool_result",
                "name": call["name"],
                "args": call.get("args"),
                "output": result,
            }
        messages.append({"role": "tool", "content": results})
    yield {"result": AiAgenticResult("", turns, trace, stopped, tin, tout)}


def stage_preview(name, args, result):
    """Distill one tool call into the compact preview the chat's build-stage
    mascot animates with real numbers: {"title"?, "total"?, "series"?}.

    Returns None when the call carries nothing previewable. The series is the
    first numeric cell per row (label/value result shapes), capped to the last
    12 rows; a numeric-less result still previews its row count as the total.
    Pure -- safe to unit test without a provider."""
    if not isinstance(result, dict) or not result.get("ok"):
        return None
    if name == "build_definition":
        defn = (args or {}).get("definition")
        title = defn.get("title") if isinstance(defn, dict) else None
        return {"title": title} if isinstance(title, str) and title.strip() else None
    if name in ("run_definition", "run_sql"):
        rows = result.get("rows") or []
        series = []
        for row in rows:
            if not isinstance(row, list | tuple):
                continue
            for v in row:
                if isinstance(v, int | float) and not isinstance(v, bool):
                    series.append(float(v))
                    break
        if not series:
            return {"total": len(rows)} if rows else None
        series = series[-12:]
        return {"total": sum(series), "series": series}
    return None


def ask_agentic(question, **kwargs):
    """Drive the model->tool->model loop until a final answer or the turn cap.

    `agent_step(messages) -> AssistantTurn` is the injected provider round-trip
    (scripted in tests, built by `_make_agent_step` in production). `registry` is
    a ToolRegistry. Returns AiAgenticResult. No network/provider code lives here.
    Progress-reporting callers want `ask_agentic_iter` instead; this drains it.

    `history` is an optional pre-validated list of prior `{"role": "user"|
    "assistant", "content": str}` turns, seeded ahead of the new question so a
    chat-style caller can carry conversation context into the loop. The caller
    is responsible for sanitizing/capping it; this function trusts it as-is.

    `messages` is the neutral conversation: user/assistant strings, an assistant
    turn carrying `tool_calls`, and a `tool` turn whose content is the list of
    `{tool_call_id, name, result}` envelopes. `_make_agent_step` translates this
    into each provider's wire format.
    """
    for event in ask_agentic_iter(question, **kwargs):
        if "result" in event:
            return event["result"]
    raise AssertionError("agentic loop ended without a result")  # unreachable


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
    effort=EFFORT_AGENT,
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
                **_reasoning_body(deployment, effort),
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
