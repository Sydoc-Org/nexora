# Reporting AI Assistant — Phase 2 (NL → report definition, builder auto-fill) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a **"Build a report"** mode to the Reporting page's Ask-AI panel that turns a natural-language question into a **v1 report-definition** which auto-fills the builder wells (columns / filters / sort / source) — whitelist-safe, **no SQL permission required** — by routing the model's output through the *unchanged* `validate_report_definition` + `/api/reporting/run` path.

**Architecture:** This is **Surface A** from `docs/design/reporting-ai-assistant.md` §2: the LLM emits the v1 report-definition JSON (`source`, `columns`, `filters`, `sort`, `scope`, `rowLimit`), and nexora's *existing* whitelist validator disposes — every column/filter/sort field is checked against the chosen source's catalog, so an off-catalog hallucination is rejected with 400, never executed. Unlike Phase 1's Surface B (T-SQL, `reporting.sql.run`), Surface A keeps `reporting.scope.process.*` row-scoping and needs only `reporting.ai.use`. A new gated route `POST /api/reporting/ai/build` resolves the accessible source catalogs, prompts the provider-agnostic AI client for a definition, **self-validates server-side against the source catalog with one bounded self-repair retry**, audits to the existing `dbo.ReportingAiAudit` (`Surface='definition'`), and returns `{definition, explanation, valid}`. The frontend adds an **Open in builder** action that calls the existing `applyDefinition()` to fill the wells. **No new permission, no new table, no new migration.**

**Tech Stack:** Flask (Jinja + vanilla-JS inline partials), `requests` (provider HTTP — already present), the existing `nx_lib/reporting/schema.py` `validate_report_definition` (the Surface-A gate), pyodbc/SQLAlchemy, pytest, Flask-Babel (de/fr/it).

---

## Provider decision — already resolved

Phase 1 resolved this: **Azure OpenAI** (`AI_PROVIDER=azure`, `gpt-4o-mini` via `sydoc-ai-services`) is live on INT. Phase 2 inherits the exact same provider config and the same provider-agnostic client — **no env/secret changes for the provider**. Egress is unchanged in class: the question + **schema/catalog metadata only**, never result rows. (Surface A actually sends *less* than Surface B — curated field catalogs instead of raw `INFORMATION_SCHEMA`.)

---

## Phase-2 scope (from design §2 / §12 + Phase-1 decisions)

**In scope**
- "Build a report" sub-mode in the existing Ask-AI panel → a v1 **report definition** (no SQL).
- **Server-side** provider call (no CSP change), reusing the Phase-1 client and config.
- Catalog grounding from the **curated sources the caller can access** (their field keys, types, and which are filterable/sortable, plus the valid filter ops + the caller's allowed process scope) — bounded + logged, like Phase 1's schema serializer.
- **Self-validation server-side** through the *unchanged* `validate_report_definition`, with **one bounded self-repair retry** (feed the validation error back to the model once).
- Result action **Open in builder** → fills the wells via the existing `applyDefinition()`, then the user runs it through the *unchanged* `/api/reporting/run`.
- Gated by **`reporting.ai.use` only** (Surface A needs no SQL perm). Audited to `dbo.ReportingAiAudit` with `Surface='definition'`.
- Reuses, unchanged: `validate_report_definition` (gate), `/api/reporting/run` (run), `_audit_ai`, `_ai_daily_limit`/`_ai_asks_today` (the Phase-1 cost cap applies to both surfaces).

**Out of scope (later phases)** — Tier-2 agentic tool-loop + `compute_stats`, "explain these rows" / data egress (`reporting.ai.explain_data`), RAG/glossary (Tier 3), the semantic layer (Tier 4), aggregation/`groupBy` (the v1 builder is non-aggregating — Surface A inherits that limit), and conversational follow-ups. The optional **chart suggestion** is Task 6 and may be deferred.

**Phase-2 acceptance:** a user with **only** `reporting.ai.use` (no `reporting.ai.sql`) types a question, receives a report definition that **passes `validate_report_definition`** for a source they can access, clicks **Open in builder** to fill the wells, runs it via the existing `/api/reporting/run`, and the interaction is recorded in `dbo.ReportingAiAudit` (`Surface='definition'`). No new execution path; no data egress beyond the question + catalog metadata; row-scoping preserved.

---

## The v1 report-definition contract (what the model must emit)

Confirmed against `nx_lib/reporting/schema.py` (`validate_report_definition`) and the builder's `buildDefinition()` in `templates/js/_reporting_js.html`:

```jsonc
{
  "schemaVersion": 1,                 // must equal REPORT_SCHEMA_VERSION (1)
  "visualization": "table",           // only "table" is supported
  "source": "<source-id>",            // MUST be one of the catalog's source ids
  "title": "<short title>",           // required, non-empty
  "subtitle": null,                   // string or null
  "columns": [ { "field": "<key>", "header": "<label>" } ],   // >=1; field in catalog
  "filters": [ { "field": "<key>", "op": "<op>", "value": <v> } ], // field filterable; op in FILTER_OPS
  "sort":    [ { "field": "<key>", "dir": "asc|desc" } ],      // field sortable
  "scope":   { "clients": [], "processes": [ "<id>", ... ] },  // strings only; from the caller's allowed scope
  "rowLimit": 5000                    // int in [1, MAX_ROW_LIMIT]
}
```

`FILTER_OPS` (value-requiring unless noted): `eq, ne, in, not_in, gt, gte, lt, lte, between` (value is a 2-element list), `contains, starts_with`, and the value-free `is_null, is_not_null`. The route **normalizes** the validated definition to the full builder shape (adds `groupBy: []`, `sql: null`, `sqlTarget: null`) before returning, so the frontend `applyDefinition()` consumes it unchanged.

---

## File structure

**Create**
- `tests/unit/test_reporting_ai_definition.py` — unit tests for `ask_definition()`.
- (tests for the serializer go in the existing `tests/unit/test_reporting_ai_schema.py`.)
- (tests for the route go in the existing `tests/integration/test_reporting_ai_routes.py`.)

**Modify**
- `nx_lib/reporting/ai.py` — refactor provider dispatch to accept an arbitrary `system`/`user` prompt (regression-safe for `ask`), add `AiDefinitionResult` + `ask_definition()`.
- `nx_lib/reporting/ai_schema.py` — add `serialize_sources_catalog(sources, *, char_budget=...)`.
- `nx_lib/views/reporting.py` — add `_accessible_curated_sources()`, `_ai_catalog_text()`, `_validate_definition_for_user()`, the `api_ai_build` route + registration; pass `ai_sql_enabled` to the template.
- `templates/reporting.html` — sub-mode toggle (Build a report / Write SQL) inside the Ask-AI panel; a Surface-A result block with **Open in builder**; gate the SQL sub-mode on `ai_sql_enabled`.
- `templates/js/_reporting_ai_js.html` — Surface-A request/response + `applyDefinition()` wiring.
- `static/css/reporting.css` — minor styles for the definition summary block.
- `CHANGELOG.md`, `docs/howto/reporting.md`, `CLAUDE.md`, `docs/design/reporting-ai-assistant.md` (flip Phase 2 to "implemented").
- `messages.pot` + `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`).

**No change needed**
- `sql/_migrations/` — **no new migration.** No new permission (`reporting.ai.use` already covers Surface A) and the audit table is reused (`Surface='definition'`, definition JSON stored in the existing `GeneratedSql` column).
- `requirements.txt`, `.github/workflows/deploy.yml`, CSP — unchanged (server-side call; all runtime files under already-synced dirs).

---

## Task 1: Refactor `ai.py` provider dispatch to carry an arbitrary prompt

The Phase-1 `_call_anthropic`/`_call_azure` hardcode the SQL system prompt. Make them accept `system` + `user` strings so a second surface can reuse the exact same transport/auth/token-parsing. This must not change `ask()`'s behaviour — the existing `tests/unit/test_reporting_ai.py` is the regression guard.

**Files:**
- Modify: `nx_lib/reporting/ai.py`
- Test: `tests/unit/test_reporting_ai.py` (existing — must stay green)

- [ ] **Step 1: Add a focused failing test for the new dispatch seam**

Append to `tests/unit/test_reporting_ai.py`:

```python
def test_dispatch_passes_system_and_user_through():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["body"] = body
        return {"content": [{"type": "text", "text": "{}"}], "usage": {}}

    ai._dispatch(
        "SYS", "USR", provider="anthropic", model="m", api_key="k",
        transport=transport,
    )
    # Anthropic body carries system top-level and the user message verbatim.
    assert captured["body"]["system"] == "SYS"
    assert captured["body"]["messages"][0]["content"] == "USR"
```

- [ ] **Step 2: Run it — expect FAIL** (`AttributeError: module 'nx_lib.reporting.ai' has no attribute '_dispatch'`).

Run: `python -m pytest tests/unit/test_reporting_ai.py::test_dispatch_passes_system_and_user_through -o addopts="" -p no:cacheprovider -q`

- [ ] **Step 3: Refactor `ai.py`**

Change `_call_anthropic`/`_call_azure` to take `system, user` instead of `(question, schema_text)` building the prompt internally, and add a `_dispatch` that selects the provider. Keep `_user_prompt`/`_SYSTEM` for `ask()`.

```python
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
    parts = data.get("content") or []
    text = "".join(p.get("text", "") for p in parts if p.get("type", "text") == "text")
    usage = data.get("usage") or {}
    return text, usage.get("input_tokens"), usage.get("output_tokens")


def _call_azure(system, user, *, model, api_key, endpoint, deployment,
                api_version, max_tokens, timeout, transport):
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


def _dispatch(system, user, *, provider, model, api_key, endpoint=None, deployment=None,
              api_version="2024-10-21", url=None, max_tokens=DEFAULT_MAX_TOKENS,
              timeout=DEFAULT_TIMEOUT_S, transport=_http_post):
    """Provider-agnostic single round-trip. Returns (text, tokens_in, tokens_out)."""
    if not api_key:
        raise AiError("AI provider API key is not configured")
    provider = (provider or "").lower()
    if provider == "anthropic":
        return _call_anthropic(system, user, model=model, api_key=api_key, url=url,
                               max_tokens=max_tokens, timeout=timeout, transport=transport)
    if provider == "azure":
        return _call_azure(system, user, model=model, api_key=api_key, endpoint=endpoint,
                           deployment=deployment, api_version=api_version,
                           max_tokens=max_tokens, timeout=timeout, transport=transport)
    raise AiError(f"unknown AI provider: {provider!r}")
```

Then make `ask()` call `_dispatch(_SYSTEM, _user_prompt(question, schema_text), ...)` instead of dispatching inline. Keep the `AiError` for missing key inside `_dispatch` (so `ask`'s existing `test_ask_unknown_provider_raises` and the no-key path still raise `AiError`).

- [ ] **Step 4: Run the FULL ai unit suite — expect PASS (regression + new)**

Run: `python -m pytest tests/unit/test_reporting_ai.py -o addopts="" -p no:cacheprovider -q`
Expected: PASS (existing 6 + the new dispatch test).

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/ai.py tests/unit/test_reporting_ai.py
git commit -m "refactor(reporting): factor AI provider dispatch to carry an arbitrary prompt"
```

---

## Task 2: `ask_definition()` — NL → v1 report-definition JSON

A second entry point alongside `ask()`. It prompts for the v1 definition shape, parses the JSON, and returns it **without DB validation** (the route owns catalog validation + self-repair, since the catalog is Flask/DB-bound). Pure and network-isolated via the injected transport.

**Files:**
- Modify: `nx_lib/reporting/ai.py`
- Test: `tests/unit/test_reporting_ai_definition.py` (new)

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_reporting_ai_definition.py`:

```python
"""Unit tests for ask_definition() — NL -> v1 report-definition (no DB, no network)."""
import json

from nx_lib.reporting import ai


def _transport(body):
    def t(url, headers, body_, timeout):
        return body
    return t


def _anthropic_body(obj):
    return {"content": [{"type": "text", "text": json.dumps(obj)}],
            "usage": {"input_tokens": 100, "output_tokens": 40}}


def test_ask_definition_parses_definition_and_explanation():
    obj = {
        "definition": {
            "schemaVersion": 1, "visualization": "table", "source": "gen_pdqm",
            "title": "PDQM rejections", "columns": [{"field": "Outcome"}],
            "filters": [], "sort": [], "scope": {"clients": [], "processes": []},
            "rowLimit": 5000,
        },
        "explanation": "Rejections by outcome.",
    }
    res = ai.ask_definition(
        "pdqm rejections", "SOURCE gen_pdqm: Outcome:string(filterable,sortable)",
        provider="anthropic", model="m", api_key="k", transport=_transport(_anthropic_body(obj)),
    )
    assert res.definition["source"] == "gen_pdqm"
    assert res.definition["columns"][0]["field"] == "Outcome"
    assert res.explanation == "Rejections by outcome."
    assert res.tokens_in == 100 and res.tokens_out == 40
    assert res.model == "m" and res.provider == "anthropic"


def test_ask_definition_returns_none_definition_on_unparseable_reply():
    body = {"content": [{"type": "text", "text": "I cannot help with that."}], "usage": {}}
    res = ai.ask_definition(
        "junk", "(* none *)", provider="anthropic", model="m", api_key="k",
        transport=_transport(body),
    )
    assert res.definition is None  # route will treat as an invalid draft


def test_ask_definition_includes_prior_error_in_retry_prompt():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["user"] = body["messages"][0]["content"]
        return _anthropic_body({"definition": {}, "explanation": ""})

    ai.ask_definition(
        "q", "CATALOG", provider="anthropic", model="m", api_key="k",
        prior_error="unknown column field: 'Nope'", transport=transport,
    )
    assert "unknown column field" in captured["user"]
```

- [ ] **Step 2: Run — expect FAIL** (`AttributeError: ask_definition`).

Run: `python -m pytest tests/unit/test_reporting_ai_definition.py -o addopts="" -p no:cacheprovider -q`

- [ ] **Step 3: Implement in `ai.py`**

```python
from dataclasses import dataclass  # already imported

_SYSTEM_DEF = (
    "You are a careful analyst for an internal reporting tool. Given a list of "
    "available data SOURCES (each with a fixed set of fields, their types, and "
    "whether each field is filterable/sortable) and a question, return ONE report "
    "DEFINITION that answers it using ONLY one source and ONLY that source's "
    "fields. Do not invent fields or sources. Respond with STRICT JSON: "
    '{"definition": {"schemaVersion": 1, "visualization": "table", "source": '
    '"<id>", "title": "<short>", "subtitle": null, "columns": [{"field": "<key>", '
    '"header": "<label>"}], "filters": [{"field": "<key>", "op": "<op>", "value": '
    '<v>}], "sort": [{"field": "<key>", "dir": "asc"|"desc"}], "scope": {"clients": '
    '[], "processes": []}, "rowLimit": 5000}, "explanation": "<one sentence>"}. '
    "Valid filter ops: eq, ne, in, not_in, gt, gte, lt, lte, between (value is a "
    "2-element list), contains, starts_with, is_null, is_not_null (these two take "
    "no value). No prose outside JSON."
)


@dataclass
class AiDefinitionResult:
    definition: dict | None
    explanation: str
    model: str
    provider: str
    tokens_in: int | None
    tokens_out: int | None


def _definition_user_prompt(question, catalog_text, prior_error):
    base = (
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


def ask_definition(question, catalog_text, *, provider, model, api_key,
                   endpoint=None, deployment=None, api_version="2024-10-21",
                   url=None, prior_error=None, max_tokens=DEFAULT_MAX_TOKENS,
                   timeout=DEFAULT_TIMEOUT_S, transport=_http_post):
    """Draft one v1 report-definition for `question`. Returns AiDefinitionResult.

    No DB validation here: `definition` is the parsed JSON object (or None if the
    reply was not parseable). The caller validates it against the source catalog
    and may retry once with `prior_error` set.
    """
    text, tin, tout = _dispatch(
        _SYSTEM_DEF, _definition_user_prompt(question, catalog_text, prior_error),
        provider=provider, model=model, api_key=api_key, endpoint=endpoint,
        deployment=deployment, api_version=api_version, url=url,
        max_tokens=max_tokens, timeout=timeout, transport=transport,
    )
    definition, explanation = None, ""
    obj = _extract_json(text)
    if isinstance(obj, dict):
        d = obj.get("definition")
        if isinstance(d, dict):
            definition = d
        explanation = str(obj.get("explanation", "")).strip()
    return AiDefinitionResult(
        definition=definition, explanation=explanation,
        model=model, provider=provider, tokens_in=tin, tokens_out=tout,
    )
```

> Confirm `_extract_json` returns the parsed object (it does in the current `ai.py`); if its signature differs, adapt this to call it correctly. The three tests pin the behaviour.

- [ ] **Step 4: Run — expect PASS (3 tests).**

Run: `python -m pytest tests/unit/test_reporting_ai_definition.py -o addopts="" -p no:cacheprovider -q`

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/ai.py tests/unit/test_reporting_ai_definition.py
git commit -m "feat(reporting): ask_definition() — NL -> v1 report-definition (Surface A)"
```

---

## Task 3: Surface-A catalog serializer (`ai_schema.serialize_sources_catalog`)

Turn the caller's accessible curated sources into a compact, bounded text block the model grounds on: each source's id, label, fields (`name:type` + `filterable`/`sortable` flags), and the caller's allowed process scope. Bounded by a char budget; truncation logged (no silent caps), mirroring `serialize_schema`.

**Files:**
- Modify: `nx_lib/reporting/ai_schema.py`
- Test: `tests/unit/test_reporting_ai_schema.py` (existing file — append)

- [ ] **Step 1: Write the failing tests** — append to `tests/unit/test_reporting_ai_schema.py`:

```python
def test_serialize_sources_catalog_lists_ids_fields_and_flags():
    sources = [{
        "id": "gen_pdqm", "label": "Generali — PDQM",
        "fields": [
            {"field": "Outcome", "type": "string", "filterable": True, "sortable": True},
            {"field": "Qty", "type": "number", "filterable": False, "sortable": True},
        ],
        "processes": ["p1", "p2"],
    }]
    text, truncated = ai_schema.serialize_sources_catalog(sources, char_budget=10000)
    assert "gen_pdqm" in text and "Generali — PDQM" in text
    assert "Outcome" in text and "string" in text
    assert "filterable" in text and "sortable" in text
    assert "p1" in text and "p2" in text          # caller's allowed scope
    assert truncated is False


def test_serialize_sources_catalog_truncates_and_logs(caplog):
    big = [{
        "id": f"s{i}", "label": f"S{i}",
        "fields": [{"field": "F", "type": "string", "filterable": True, "sortable": True}],
        "processes": [],
    } for i in range(500)]
    text, truncated = ai_schema.serialize_sources_catalog(big, char_budget=300)
    assert len(text) <= 400
    assert truncated is True
    assert "truncated" in text.lower()
```

- [ ] **Step 2: Run — expect FAIL** (`AttributeError: serialize_sources_catalog`).

Run: `python -m pytest tests/unit/test_reporting_ai_schema.py -o addopts="" -p no:cacheprovider -q`

- [ ] **Step 3: Implement in `ai_schema.py`**

```python
def serialize_sources_catalog(sources, *, char_budget=DEFAULT_CHAR_BUDGET):
    """Compact, bounded text block of the caller's accessible curated sources.

    `sources`: list of {id, label, fields:[{field,type,filterable,sortable}],
    processes:[ids]}. Returns (text, truncated_bool); on overflow the text is cut
    to the budget with a visible marker and the truncation is logged.
    """
    lines = []
    for s in sources or []:
        flags_fields = []
        for f in s.get("fields", []):
            flags = []
            if f.get("filterable"):
                flags.append("filterable")
            if f.get("sortable"):
                flags.append("sortable")
            flag_txt = f" ({', '.join(flags)})" if flags else ""
            flags_fields.append(f"{f.get('field')}:{f.get('type', 'string')}{flag_txt}")
        lines.append(
            f'SOURCE {s.get("id")} "{s.get("label")}": ' + "; ".join(flags_fields)
        )
        procs = s.get("processes") or []
        if procs:
            lines.append(f"  allowed scope.processes: {', '.join(map(str, procs))}")
    text = "\n".join(lines)
    if len(text) > char_budget:
        logger.info("ai_schema: sources catalog truncated from %d to %d chars",
                    len(text), char_budget)
        return text[:char_budget] + "\n... (catalog truncated)", True
    return text, False
```

- [ ] **Step 4: Run — expect PASS.**

Run: `python -m pytest tests/unit/test_reporting_ai_schema.py -o addopts="" -p no:cacheprovider -q`

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/ai_schema.py tests/unit/test_reporting_ai_schema.py
git commit -m "feat(reporting): bounded curated-sources catalog serializer (Surface A)"
```

---

## Task 4: Route `POST /api/reporting/ai/build` — gated, self-validating, audited

Wire the catalog + client behind a route gated by `reporting.ai.use` **only** (no `reporting.ai.sql`). Build the catalog from the caller's accessible curated sources, draft a definition, **validate it server-side via `validate_report_definition`**, retry once with the error on failure, normalize to the full builder shape, and audit with `Surface='definition'`. The Phase-1 daily cap (`_ai_daily_limit`/`_ai_asks_today`) applies here too.

**Files:**
- Modify: `nx_lib/views/reporting.py`
- Test: `tests/integration/test_reporting_ai_routes.py` (existing file — append)

- [ ] **Step 1: Write the failing integration tests** — append to `tests/integration/test_reporting_ai_routes.py`:

```python
from nx_lib.reporting.ai import AiDefinitionResult


def _def_result(source="gen_pdqm"):
    return AiDefinitionResult(
        definition={"schemaVersion": 1, "visualization": "table", "source": source,
                    "title": "T", "columns": [{"field": "Outcome"}], "filters": [],
                    "sort": [], "scope": {"clients": [], "processes": []}, "rowLimit": 5000},
        explanation="by outcome", model="m", provider="anthropic",
        tokens_in=10, tokens_out=8,
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
        patch("nx_lib.views.reporting._ai_config",
              return_value={"provider": "anthropic", "api_key": "k", "model": "m"}),
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
    assert data["definition"]["groupBy"] == []   # normalized to builder shape
    assert "rows" not in data                     # schema-only egress
    audit.assert_called_once()
    assert audit.call_args.args[3] == "definition"   # Surface positional arg


def test_ai_build_retries_once_then_returns_invalid(user_client):
    # First draft fails validation; route retries once; still invalid -> valid:false (200).
    with (
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting._ai_config",
              return_value={"provider": "anthropic", "api_key": "k", "model": "m"}),
        patch("nx_lib.views.reporting._ai_daily_limit", return_value=0),
        patch("nx_lib.views.reporting._ai_catalog_text", return_value="CATALOG"),
        patch("nx_lib.views.reporting.ai_ask_definition", return_value=_def_result()) as draft,
        patch("nx_lib.views.reporting._validate_definition_for_user",
              return_value=(False, "unknown column field: 'Nope'")),
        patch("nx_lib.views.reporting._audit_ai"),
    ):
        resp = user_client.post("/api/reporting/ai/build", json={"question": "x"})
    assert resp.status_code == 200
    assert resp.get_json()["valid"] is False
    assert draft.call_count == 2                  # initial + one self-repair retry


def test_ai_build_503_when_provider_unconfigured(user_client):
    with (
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting._ai_config",
              return_value={"provider": "none", "api_key": None}),
    ):
        resp = user_client.post("/api/reporting/ai/build", json={"question": "hi"})
    assert resp.status_code == 503
```

- [ ] **Step 2: Run — expect FAIL** (route 404 / patched names absent).

Run: `python -m pytest tests/integration/test_reporting_ai_routes.py -o addopts="" -p no:cacheprovider -q`

- [ ] **Step 3: Add the import alias** near the Phase-1 AI imports (`nx_lib/views/reporting.py` ~line 49):

```python
from ..reporting.ai import ask_definition as ai_ask_definition
```

- [ ] **Step 4: Add the helpers** (near `_ai_schema_text`, ~line 243):

```python
def _accessible_curated_sources():
    """Curated sources the caller can access, shaped for the AI catalog serializer."""
    perms = set(session.get("permissions", []))
    out = []
    for s in accessible(_effective_sources(), perms):
        if s.get("kind") != "curated":
            continue
        catalog = table_source_catalog(s.get("columns")) if s.get("columns") else []
        if s.get("provider") in (None, "docprocessing"):
            # docprocessing fields come from the locale catalog; fall back to columns
            catalog = catalog or []
        out.append({
            "id": s.get("id"),
            "label": s.get("label"),
            "fields": catalog,
            "processes": s.get("processes") or [],
        })
    return out


def _ai_catalog_text():
    """Bounded catalog text for Surface A from the caller's accessible curated sources."""
    text, truncated = serialize_sources_catalog(_accessible_curated_sources())
    if truncated:
        current_app.logger.info("reporting.ai catalog truncated for user=%s", session.get("userid"))
    return text


def _validate_definition_for_user(definition):
    """Validate a model-drafted definition against its source catalog (Surface-A gate).

    Returns (ok, error_message). Reuses the exact validator + source resolution
    that /api/reporting/run uses, so an accepted definition is guaranteed runnable.
    """
    if not isinstance(definition, dict):
        return False, "definition must be an object"
    try:
        source = _get_effective_source(definition.get("source"))
        if source is None or source.get("kind") != "curated":
            return False, "unknown or unsupported source"
        if not has_permission(source["permission"]):
            return False, "not authorized for this source"
        provider = source.get("provider") or "docprocessing"
        if provider == "docprocessing":
            allowed = _allowed_processes()
            catalog = fetch_docprocessing_catalog(allowed, str(get_locale()))
        else:
            catalog = table_source_catalog(source.get("columns"))
        catalog_fields = {f["field"] for f in catalog}
        filterable = {f["field"] for f in catalog if f["filterable"]}
        sortable = {f["field"] for f in catalog if f["sortable"]}
        validate_report_definition(
            definition, catalog_fields, filterable, sortable, max_row_limit=MAX_ROW_LIMIT
        )
        return True, None
    except (ReportDefinitionError, PermissionError) as e:
        return False, str(e) or e.__class__.__name__
    except Exception as e:  # resolution failure degrades to "invalid", not 500
        current_app.logger.warning(f"reporting.ai build validation error: {e}")
        return False, "could not validate the drafted report"


def _normalize_definition(definition):
    """Fill the full builder shape so the frontend applyDefinition() consumes it as-is."""
    definition.setdefault("groupBy", [])
    definition.setdefault("subtitle", None)
    definition.setdefault("filters", [])
    definition.setdefault("sort", [])
    definition.setdefault("scope", {"clients": [], "processes": []})
    definition["sql"] = None
    definition["sqlTarget"] = None
    return definition
```

> Confirm the helper names `_get_effective_source`, `_allowed_processes`, `fetch_docprocessing_catalog`, `table_source_catalog`, `accessible`, `_effective_sources`, `MAX_ROW_LIMIT`, `ReportDefinitionError`, `validate_report_definition` are all already imported/defined in `reporting.py` (they are — they back `_prepare_run`). Match their exact signatures.

- [ ] **Step 5: Add the route** (after `api_ai_ask`, ~line 760):

```python
@require_permission("reporting.ai.use")
@limiter.limit("10 per minute")
def api_ai_build():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify({"error": _("A question is required")}), 400

    cfg = _ai_config()
    if cfg.get("provider") == "none" or not cfg.get("api_key"):
        return jsonify({"error": _("The AI assistant is not configured")}), 503

    userid, username = session.get("userid"), session.get("username")
    limit = _ai_daily_limit()
    if limit > 0 and _ai_asks_today(userid) >= limit:
        _audit_ai(userid, username, question, "definition", None, cfg.get("provider"),
                  cfg.get("model"), None, None, "na", "blocked", 0)
        return jsonify({"error": _(
            "You have reached the daily AI request limit (%(limit)s). "
            "Please try again tomorrow.", limit=limit)}), 429

    catalog_text = _ai_catalog_text()
    start = time.monotonic()
    prior_error = None
    result = None
    valid = False
    for attempt in range(2):  # initial draft + one bounded self-repair retry
        try:
            result = ai_ask_definition(
                question, catalog_text,
                provider=cfg["provider"], model=cfg.get("model"), api_key=cfg["api_key"],
                endpoint=cfg.get("endpoint"), deployment=cfg.get("deployment"),
                api_version=cfg.get("api_version", "2024-10-21"), url=cfg.get("url"),
                prior_error=prior_error,
            )
        except AiError as e:
            current_app.logger.warning(f"/api/reporting/ai/build config error: {e}")
            return jsonify({"error": _("The AI assistant is not configured")}), 503
        except Exception as e:
            current_app.logger.error(f"/api/reporting/ai/build provider error: {e}")
            _audit_ai(userid, username, question, "definition", None, cfg.get("provider"),
                      cfg.get("model"), None, None, "na", "error",
                      int((time.monotonic() - start) * 1000))
            return jsonify({"error": _("The AI assistant could not answer right now")}), 502
        valid, prior_error = _validate_definition_for_user(result.definition)
        if valid:
            break

    duration_ms = int((time.monotonic() - start) * 1000)
    definition = _normalize_definition(result.definition) if result.definition else None
    _audit_ai(userid, username, question, "definition",
              json.dumps(definition) if definition else None,
              result.provider, result.model, result.tokens_in, result.tokens_out,
              "valid" if valid else "invalid", "ok", duration_ms)
    return jsonify({
        "definition": definition,
        "explanation": result.explanation,
        "valid": valid,
        "error": None if valid else (prior_error or _("Could not build a valid report")),
    })
```

- [ ] **Step 6: Register the route** in `register_routes` (after the `reporting_ai_ask` rule, ~line 1523):

```python
    app.add_url_rule(
        "/api/reporting/ai/build",
        endpoint="reporting_ai_build",
        view_func=api_ai_build,
        methods=["POST"],
    )
```

- [ ] **Step 7: Pass `ai_sql_enabled` to the template** — in `reporting()` next to the existing `ai_enabled=...` kwarg (~line 437):

```python
        ai_sql_enabled=has_permission("reporting.ai.sql"),
```

- [ ] **Step 8: Run the AI route suite — expect PASS (Phase-1 + 4 new).**

Run: `python -m pytest tests/integration/test_reporting_ai_routes.py -o addopts="" -p no:cacheprovider -q`

- [ ] **Step 9: Run the full reporting sweep (no regressions).**

Run: `python -m pytest tests/unit/test_reporting_*.py tests/integration/test_reporting_routes.py tests/integration/test_reporting_ai_routes.py -o addopts="" -p no:cacheprovider -q`

- [ ] **Step 10: Commit**

```bash
git add nx_lib/views/reporting.py tests/integration/test_reporting_ai_routes.py
git commit -m "feat(reporting): POST /api/reporting/ai/build — Surface A NL->definition, gated + self-validating + audited"
```

---

## Task 5: Frontend — "Build a report" sub-mode + Open in builder

The Ask-AI panel gets two sub-modes: **Build a report** (Surface A, available to anyone with `reporting.ai.use`) and **Write SQL** (Surface B, the Phase-1 path, only when `ai_sql_enabled`). The Surface-A result shows a compact definition summary and an **Open in builder** button that calls the existing `applyDefinition()`.

**Files:**
- Modify: `templates/reporting.html`, `templates/js/_reporting_ai_js.html`, `static/css/reporting.css`

Frontend is verified manually/e2e (Step 6), not unit-tested.

- [ ] **Step 1: Add the sub-mode toggle + Surface-A result block** inside the existing `#rpAiPanel` (in `templates/reporting.html`), above the existing prompt bar:

```html
        <div class="reporting-ai-submode" data-testid="reporting-ai-submode">
          <button id="rpAiModeBuild" class="active" data-testid="reporting-ai-mode-build">{{ _("Build a report") }}</button>
          {% if ai_sql_enabled %}
          <button id="rpAiModeSql" data-testid="reporting-ai-mode-sql">{{ _("Write SQL") }}</button>
          {% endif %}
        </div>
```

And, after the existing SQL result block (`#rpAiResult`), add the definition result block:

```html
        <div id="rpAiDefResult" class="reporting-ai-result" hidden data-testid="reporting-ai-def-result">
          <p id="rpAiDefSummary" class="reporting-ai-explain" data-testid="reporting-ai-def-summary"></p>
          <p id="rpAiDefInvalid" class="reporting-ai-invalid" hidden>{{ _("⚠ The drafted report could not be validated — try rephrasing.") }}</p>
          <div class="reporting-ai-actions">
            <button id="rpAiOpenBuilder" class="reporting-btn" data-testid="reporting-ai-open-builder">{{ _("Open in builder") }}</button>
          </div>
        </div>
```

- [ ] **Step 2: Wire the sub-mode + Surface-A flow** in `templates/js/_reporting_ai_js.html`. Add near the top (after the existing element lookups):

```javascript
  var modeBuild = document.getElementById("rpAiModeBuild");
  var modeSqlBtn = document.getElementById("rpAiModeSql");          // may be absent (no ai.sql)
  var defResult = document.getElementById("rpAiDefResult");
  var defSummary = document.getElementById("rpAiDefSummary");
  var defInvalid = document.getElementById("rpAiDefInvalid");
  var openBuilderBtn = document.getElementById("rpAiOpenBuilder");
  var aiSurface = "build";                                          // "build" | "sql"
  var lastDef = null;

  function setSurface(s) {
    aiSurface = s;
    if (modeBuild) modeBuild.classList.toggle("active", s === "build");
    if (modeSqlBtn) modeSqlBtn.classList.toggle("active", s === "sql");
    // hide both result blocks on switch
    if (resultEl) resultEl.hidden = true;
    if (defResult) defResult.hidden = true;
    if (errorEl) errorEl.hidden = true;
  }
  if (modeBuild) modeBuild.addEventListener("click", function () { setSurface("build"); });
  if (modeSqlBtn) modeSqlBtn.addEventListener("click", function () { setSurface("sql"); });

  function summarize(def) {
    var cols = (def.columns || []).map(function (c) { return c.header || c.field; }).join(", ");
    var parts = ['"' + (def.title || "report") + '"', "source " + def.source, "columns: " + cols];
    if ((def.filters || []).length) parts.push((def.filters.length) + " filter(s)");
    if ((def.sort || []).length) parts.push("sorted");
    return parts.join(" · ");
  }
```

Change `ask()` to branch on `aiSurface`: keep the existing `POST /api/reporting/ai/ask` for `sql`, and call `POST /api/reporting/ai/build` for `build`, rendering into the definition block:

```javascript
  function askBuild(question) {
    askBtn.disabled = true;
    errorEl.hidden = true;
    fetch("/api/reporting/ai/build", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify({ question: question })
    }).then(function (r) {
      return r.json().then(function (data) { return { ok: r.ok, data: data }; });
    }).then(function (res) {
      askBtn.disabled = false;
      if (!res.ok) {
        errorEl.textContent = (res.data && res.data.error) || "Error";
        errorEl.hidden = false; defResult.hidden = true; return;
      }
      lastDef = res.data.definition;
      defSummary.textContent = lastDef ? summarize(lastDef) : (res.data.explanation || "");
      defInvalid.hidden = res.data.valid !== false;
      openBuilderBtn.disabled = !lastDef || res.data.valid === false;
      defResult.hidden = false;
    }).catch(function () {
      askBtn.disabled = false;
      errorEl.textContent = "Network error"; errorEl.hidden = false;
    });
  }
```

And dispatch in the existing `ask()` entry point:

```javascript
  function ask() {
    var question = (promptEl.value || "").trim();
    if (!question) { promptEl.focus(); return; }
    if (aiSurface === "build") return askBuild(question);
    return askSql(question);   // the existing Phase-1 body, renamed from ask()
  }
```

Wire **Open in builder** to the existing builder hook (the report JS exposes `applyDefinition`; if it is not already global, expose it via `window.Reporting = { applyDefinition }` in `_reporting_js.html` and call it here):

```javascript
  if (openBuilderBtn) openBuilderBtn.addEventListener("click", function () {
    if (!lastDef || !window.Reporting || !window.Reporting.applyDefinition) return;
    window.Reporting.applyDefinition(lastDef, lastDef.title || "AI report", null);
  });
```

> Confirm how the builder exposes `applyDefinition`. If `_reporting_js.html`'s IIFE does not expose it, add a single line at the end of that IIFE: `window.Reporting = Object.assign(window.Reporting || {}, { applyDefinition: applyDefinition, setMode: setMode });`. `applyDefinition` already switches to table mode and renders the wells.

- [ ] **Step 3: Add minimal CSS** to `static/css/reporting.css`:

```css
/* --- AI assistant: Surface-A sub-mode (Phase 2) --- */
.reporting-ai-submode { display: flex; gap: .25rem; margin-bottom: .5rem; }
.reporting-ai-submode button { padding: .25rem .6rem; border: 1px solid var(--rp-border, #d0d7de); background: #fff; border-radius: 6px; cursor: pointer; }
.reporting-ai-submode button.active { background: #eef2ff; border-color: #c7d2fe; font-weight: 600; }
```

- [ ] **Step 4: Restart the dev server and verify in a browser** (Jinja templates are cached for the process lifetime):

```powershell
& C:\dev\nexora\bin\nx.ps1 -d
& C:\dev\nexora\bin\nx.ps1 -u -b --loginas:ben.streich
```

Drive Playwright to `/reporting` → **Ask AI** → the **Build a report** sub-mode is selected by default; ask *"PDQM outcomes by subcategory"*; a definition summary appears; **Open in builder** fills the wells and switches to table mode; **Run** returns rows via the existing `/api/reporting/run`. Save screenshots to `var/screenshots/reporting_ai_build_0{1,2}.png`. (Live model responses require the provisioned RO logins for `docprocessing`/`table` catalogs — Generali/Octopus curated sources work from their own engines regardless.)

- [ ] **Step 5: Commit**

```bash
git add templates/reporting.html templates/js/_reporting_ai_js.html templates/js/_reporting_js.html static/css/reporting.css
git commit -m "feat(reporting): Ask-AI 'Build a report' sub-mode -> auto-fill the builder (Surface A)"
```

---

## Task 6 (optional): "Suggest a chart"

Small add-on from design §12: let the model hint a chart so the user can one-click into the existing chart view. Defer if time-boxed; it is not required for Phase-2 acceptance.

**Files:** `nx_lib/reporting/ai.py` (allow an optional `chartHint` in the definition system prompt), `templates/js/_reporting_ai_js.html` (after Open in builder, if `def.chartHint`, preselect the chart type via the existing `window.ReportingViz`).

- [ ] **Step 1:** Extend `_SYSTEM_DEF` to permit an optional `"chartHint": {"type": "bar|line|pie", "x": "<field>", "y": "<field>"}` in the definition, documented as optional.
- [ ] **Step 2:** In `_validate_definition_for_user`, ignore `chartHint` (it is not part of `validate_report_definition`; strip it before validation so it never causes a rejection, and re-attach after).
- [ ] **Step 3:** In the JS, if `lastDef.chartHint`, show a secondary **Make a chart** button that calls into `window.ReportingViz` with the hinted type after Open in builder.
- [ ] **Step 4:** Manual verify + screenshot `var/screenshots/reporting_ai_chart.png`.
- [ ] **Step 5:** Commit `feat(reporting): optional AI chart suggestion (Surface A)`.

---

## Task 7: Docs, CHANGELOG, CLAUDE.md, design doc, translations

**Files:** `CHANGELOG.md`, `docs/howto/reporting.md`, `CLAUDE.md`, `docs/design/reporting-ai-assistant.md`, `messages.pot`, `translations/{de,fr,it}/…`

- [ ] **Step 1: CHANGELOG** — under `## [Unreleased] → ### Added`:

```markdown
- **Reporting AI assistant (Phase 2 — Build a report):** a "Build a report" sub-mode
  in the Ask-AI panel turns a natural-language question into a v1 report definition
  that auto-fills the builder wells (whitelist-safe; row-scoping preserved; **no SQL
  permission required** — only `reporting.ai.use`). Route `POST /api/reporting/ai/build`
  self-validates the draft through `validate_report_definition` with one self-repair
  retry, and audits to `dbo.ReportingAiAudit` (`Surface='definition'`). No new
  permission or migration.
```

- [ ] **Step 2: `docs/howto/reporting.md`** — under the AI assistant section, add a "Build a report (Surface A)" subsection: the new route, that it needs only `reporting.ai.use`, the self-validate + one-retry behaviour, and that it reuses `/api/reporting/run` to execute.

- [ ] **Step 3: `CLAUDE.md`** — in the `reporting.*` paragraph, note the second AI route `POST /api/reporting/ai/build` (Surface A; `reporting.ai.use` only; auto-fills the builder) alongside the existing `/ai/ask`.

- [ ] **Step 4: `docs/design/reporting-ai-assistant.md`** — flip the Phase-2 row in §12 to implemented and tick Surface A in §2.

- [ ] **Step 5: Translations** — `pybabel extract -F babel.cfg -o messages.pot .` then `pybabel update -i messages.pot -d translations`; translate every new msgid (Build a report, Write SQL, Open in builder, the two warnings, "Could not build a valid report") non-fuzzy in de/fr/it; `pybabel compile -d translations`.

- [ ] **Step 6: Translation gate** — `python -m pytest tests/unit/test_translations.py -o addopts="" -p no:cacheprovider -q` → PASS.

- [ ] **Step 7: Commit** — `docs(reporting): document AI Phase 2 (Build a report) + de/fr/it translations`.

---

## Final verification (before handoff/merge)

- [ ] Full reporting suite green:
  `python scripts/test_db_reset.py && python -m pytest tests/unit/test_reporting_*.py tests/integration/test_reporting_*.py -o addopts="" -p no:cacheprovider -q`
- [ ] AI definition + schema unit suites green:
  `python -m pytest tests/unit/test_reporting_ai.py tests/unit/test_reporting_ai_definition.py tests/unit/test_reporting_ai_schema.py -o addopts="" -p no:cacheprovider -q`
- [ ] Translation gate green; **ruff clean**:
  `python -m ruff check nx_lib/reporting/ai.py nx_lib/reporting/ai_schema.py nx_lib/views/reporting.py`
- [ ] **Egress check (manual read):** confirm `api_ai_build` + `ask_definition` send only the question + `_ai_catalog_text()` — never result rows. The definition stored in the audit is metadata, not data.
- [ ] **Permission check (manual read):** `api_ai_build` is gated `reporting.ai.use` and never consults `reporting.ai.sql`; the SQL sub-mode button is gated by `ai_sql_enabled` in the template.
- [ ] Browser smoke as `ben.streich`: Build a report → Open in builder → Run; screenshots saved under `var/screenshots/`.

---

## Self-review (run against design §2 / §12 Phase 2)

**Spec coverage**
- NL → report definition (Surface A) → Tasks 2 + 4 (`ask_definition` + `/ai/build`). ✅
- Auto-fills wells → Task 5 (`applyDefinition` via Open in builder). ✅
- Whitelist-safe, no SQL perm → Task 4 (`validate_report_definition` gate; gated `reporting.ai.use` only). ✅
- Row-scoping preserved → Surface A runs through `/api/reporting/run` which applies `scope`/`_allowed_processes`. ✅
- Catalog grounding from accessible sources, bounded + logged → Task 3 + `_ai_catalog_text`. ✅
- Self-validate + self-repair (design §8.3) → Task 4's 2-attempt loop. ✅
- Audited (`ReportingAiAudit`, `Surface='definition'`) → Task 4 `_audit_ai`. ✅
- Cost cap applies → Task 4 reuses `_ai_daily_limit`/`_ai_asks_today`. ✅
- "Suggest a chart" → Task 6 (optional). ✅ (scoped as deferrable)

**Placeholder scan** — no "TBD/handle errors/etc."; every code step carries real code. Three explicit *confirm-against-codebase* notes (`_extract_json` signature; the `reporting.py` helper names; how the builder exposes `applyDefinition`) are verification steps, not placeholders.

**Type/name consistency** — `AiDefinitionResult` fields (`definition, explanation, model, provider, tokens_in, tokens_out`) are used consistently in Task 2 (def) and Task 4 (route + audit args). Route name `reporting_ai_build` / view `api_ai_build` / import alias `ai_ask_definition` are consistent. `_validate_definition_for_user` returns `(ok, error)` everywhere it's used. The audit `Surface` value is `'definition'` in the route and asserted at positional index 3 in the test.

**Open confirmations for the implementer (cheap, do at the step):**
1. `_extract_json` return shape (Task 2 note).
2. The `reporting.py` helper/import names backing `_validate_definition_for_user` (Task 4 note) — all already back `_prepare_run`.
3. How `_reporting_js.html` exposes `applyDefinition` to the AI partial (Task 5 note).
