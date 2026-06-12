# Reporting AI: Plain-Language Understanding, Clarify Round & Tweak Suggestions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The reporting AI understands people who are not data people: every surface (Simple Ask-AI + refine, Advanced Build / Write-SQL / Agent) translates stakeholder wording ("split up by", "how many", "per week") into correct drafts and explains results jargon-free in the user's language; when a question is genuinely ambiguous the AI asks ONE short plain-language clarify question with 2–4 clickable "did you mean…?" choices (click = automatic stateless re-ask, plus a "None of these" escape chip); and AI-drafted reports come back with up to 3 catalog-validated tweak chips ("Show this per week", "Use the import date instead") that re-ask as a refine when clicked.

**Architecture:** Everything is additive on the existing stateless pipes. The system prompts in `nx_lib/reporting/ai.py` gain stakeholder-vocabulary + clarify + suggestion rules (each pinned by a prompt-content unit test, the established pattern); the strict-JSON replies gain optional `clarify`/`suggestions` keys parsed into the existing result dataclasses; a new pure module `nx_lib/reporting/ai_followups.py` whitelists both (shape-caps for clarify, catalog-gating for suggestions — owner rule: never show a chip for a field/grain the source lacks). The three routes attach `clarify`/`suggestions` as optional response keys (presence-gated by the frontend exactly like `chartHint`/`resolvedDates`), and thread the user locale into the prompts so AI text comes back in en/de/fr/it. A clarify-choice click and a tweak-chip click are just new `POST`s to the same endpoints (chip text as `question`, tweak clicks riding the existing `priorQuestion`/`priorDefinition` refine fields), so rate limits, the daily cap, auditing and permissions all apply unchanged. One shared XSS-safe ES5 partial (`window.ReportingFollowups`) renders the choice pills and tweak chips on both tabs.

**Tech Stack:** Flask + Jinja2, vanilla ES5 IIFE partials, Azure OpenAI gpt-4o-mini behind the injectable-transport client (no SDK), Flask-Babel (de/fr/it), pytest + Playwright. **Zero new dependencies, zero migrations, zero new permissions.**

**There is NO spec document for this feature — this plan stands alone.** It encodes the owner's verbatim feature request plus three locked decisions (see table below); anything the owner did not decide is listed under Owner actions, never silently assumed.

---

## Context an engineer needs (read first)

- **Branch / worktree:** work executes on `plan/reporting-ai-plain-language-clarifications`, a worktree branched off `feature/2.5.63` at `f085cc2`. Conventional-commit subjects (imperative, ≤72 chars, no trailing period) **with a non-empty body** — gitlint's `body-is-missing` rule is active, so every commit below uses two `-m` flags. **Remote-session policy: stop at `git commit` — never push, never open a PR.** The owner pushes after review (the pre-push hook runs the FULL suite incl. Playwright then).
- **SEQUENCING vs in-flight plans — verified live on 2026-06-12, do not skip:**
  1. **`plan/reporting-page-improvement-options` is DONE and MERGED.** `feature/2.5.63` now sits at `e9afaae` ("feat(reporting): merge improvement-options branch into feature/2.5.63"); the sibling worktree directory is empty and its branch is deleted. **First action of this plan: `git rebase feature/2.5.63`** (or `git merge feature/2.5.63`) so the base includes it. The merge was diffed against `f085cc2`: in `nx_lib/views/reporting.py` it touches ONLY the schedule region (`_serialize_schedule` / `_schedule_fields` / schedule CRUD hunks); `nx_lib/reporting/ai.py` is untouched; `templates/_reporting_simple.html` gained only the `rsExportFormat` select; `templates/reporting.html` gained only schedule-modal markup; the e2e file gained `test_simple_truncation_note`; the `## AI assistant` doc section is untouched. **Every quoted anchor in this plan was verified at `f085cc2` and re-checked to survive `e9afaae`.** It also took migration number `0022` (`0022_report_schedule_alerts` is on `feature/2.5.63`) — this plan needs NO migration, but if one ever becomes necessary the next free number is **0023**.
  2. **Drill-through Tasks 2–8 (`docs/superpowers/plans/2026-06-11-reporting-drill-through.md`) are still PENDING** and will edit `templates/reporting.html`, `templates/js/_reporting_simple_js.html`, `static/css/reporting.css`, `tests/e2e/test_reporting_simple.py`, i18n and docs — plus `nx_lib/views/reporting.py`, but in a different region (drill endpoint near the run/export routes, not the AI routes). The file overlap is region-level, not "never touches the file": git auto-merge is expected to succeed, but rebase + full test rerun is mandatory after either plan lands. **Concrete order: execute THIS plan now. Phases 1–2 (backend: `nx_lib/reporting/ai.py`, new `ai_followups.py`, the AI routes in `views/reporting.py`, unit/integration tests) touch regions no in-flight plan edits. Before starting Phase 3, check `git log feature/2.5.63 --oneline -10` — if drill-through Tasks 2–8 have landed, rebase and re-verify every quoted frontend anchor against the post-merge tree before editing; if not, proceed, and the closing handoff MUST instruct the drill-through executor to re-verify its quoted anchors against this plan's edits.** The i18n task (Task 11) runs LAST to minimize `.po`/`.pot` conflicts with drill-through Task 7; `CHANGELOG.md`/`docs/howto/reporting.md` (Task 12) collide with drill-through Task 8 — small additive insertions, easy to re-resolve.
- **Anchor on quoted code snippets, never line numbers.** Every anchor below is a function name plus a verbatim snippet, verified against this worktree at planning time.
- **Migrations: NO. New permissions: NO.** Clarify is stateless (owner decision 2), suggestions ride the JSON response, and the existing `ReportingAiAudit.GateVerdict NVARCHAR(16)` column absorbs the new `'clarify'` verdict value with zero DDL. Clarify clicks and tweak clicks re-POST the same three endpoints, inheriting `reporting.ai.use` (+ `reporting.ai.sql` on Surface B) and the `@limiter.limit("10 per minute")` throttle.
- **Cost model:** every clarify round and every chip click is one fresh provider call, counted by the flask-limiter AND by the per-user `AI_DAILY_LIMIT` cap (`_ai_asks_today` counts `Status IN ('ok','error')`). A clarified question therefore costs 2 quota units — accepted (the clarify reply is short, so token cost is small): clarify replies audit as `status='ok'`, `gate_verdict='clarify'`. Nothing here adds retries — the Surface-A self-repair retry is explicitly **skipped** when the model clarifies. `/ai/build` gets `max_tokens=1536` (default elsewhere stays `DEFAULT_MAX_TOKENS = 1024`): definition + explanation + up to 3 suggestions in one strict-JSON reply needs headroom, and a truncated reply fails `_parse_json_object` entirely, burning the self-repair retry for nothing.
- **Jinja template cache:** nexora caches templates for the process lifetime. Restart the dev server (`nx -u`, or `nx -u -b --loginas:<user>` for Playwright) after every template/JS-partial edit **before manual browser checks**. The pytest e2e fixture spawns its own fresh server per session, so test runs never need a restart.
- **E2E constraints:** the TEST env has `AI_PROVIDER=none` — e2e never reaches the real AI; all AI traffic is stubbed client-side via `page.route("**/api/reporting/ai/build", handler)` (helper `_stub_ai_build` + `STUB_AI_DEFINITION` in `tests/e2e/test_reporting_simple.py`); new `clarify`/`suggestions` keys go into those stub bodies, so **server-side suggestion validation is proven by integration tests, not e2e**. TEST has no Statistics DB — e2e seeds table-provider sources over `dbo.Users`. Run `python scripts/test_db_reset.py` before e2e sessions and kill stale port-8765 servers: `Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | % { Stop-Process -Id $_.OwningProcess -Force }`. `NEXORA_DISABLE_RATELIMIT=1` is set by the e2e conftest, so the 10/min limiter never trips tests. The merged loading-state tests (`test_ai_ask_shows_loading_then_result`, `test_advanced_ai_ask_shows_loading`) use a MutationObserver latch on the loading element — they are regression constraints: a clarify response must still terminate the loading state.
- **Pre-commit:** ruff + ruff-format run on commit; if ruff-format reformats, the first attempt fails — `git add -u` and commit again. The INT SchemaMigrations CRLF drift makes the `sql-migrate-int` hook fail on Windows even for SQL-free commits — prefix every commit with `$env:SQL_SYNC_SKIP = "1"` (the documented escape hatch; **never** `--no-verify`).
- **i18n:** every new user-visible template string goes through the pybabel cycle (Task 11) or `tests/unit/test_translations.py` fails the suite. This plan adds exactly **two** new msgids, both in the shared follow-ups partial. AI-emitted text (clarify questions, choice texts, suggestion labels, explanations) is localized by a new prompt directive built from `str(get_locale())` (en/de/fr/it per `nx_lib/i18n.py`) — there is currently NO language instruction anywhere in the three system prompts. Until Task 11 runs, `test_translations.py` fails — expected mid-plan, nothing is pushed before then.
- **Verified facts** (checked against this working tree): `_AGENT_SYSTEM` contains the two source lines `"Once any tool returns ok:true, stop calling tools immediately and give a "` / `"one- or two-sentence plain-language answer. Do not ask the user questions."` and **no test pins the ban sentence** (grep over `tests/` for `Do not ask the user questions` returns zero matches). The `"2 failed"` and `"ok:true"` prompt pins live in `tests/unit/test_reporting_ai_definition.py` (`test_agent_system_prompt_stops_after_repeated_failures` / `_stops_after_successful_tool`); `tests/unit/test_reporting_ai_agentic.py` carries the OTHER `_AGENT_SYSTEM` pins (`"GROUP BY"`, `this_quarter`/`last_quarter`, `today's date`, `forces every count to 1`, `'"grain"'`, `processing-date`, `Document Date`, token fragments) — all preserved by this plan's edits, and Task 3 runs both files. `ask_definition`'s parse tail reads only `definition`/`explanation` (extra keys silently dropped today); `api_ai_build`'s loop is `for _attempt in range(2):  # initial draft + one bounded self-repair retry` ending in `valid, prior_error = _validate_definition_for_user(result.definition)`; `_validate_definition_for_user` resolves the catalog via `fetch_docprocessing_catalog(allowed, str(get_locale()))` / `table_source_catalog(source.get("columns"))` and its error tail is `except (ReportDefinitionError, PermissionError) as e: return False, str(e) or e.__class__.__name__`; the views AI import line is `from ..reporting.ai import _AGENT_EXPLAIN_SUFFIX, _AGENT_SYSTEM, AiError, ask_agentic`; `_audit_ai` takes 12 positional args (`gate_verdict` = `args[-3]`, `status` = `args[-2]`); the 3-line call tail `api_version=cfg.get("api_version", "2024-10-21"),` / `url=cfg.get("url"),` / 8-space `)` is byte-identical in `api_ai_ask` AND in `api_ai_agent`'s `make_agent_step(` call — Task 6's anchor is therefore extended through the route-specific `except` line to be unique; `test_ai_agent_grounding_states_todays_date` pins `initial.startswith("Today's date is ...")` (agent language line must be APPENDED, never prepended); Simple `askAi(refineQuestion)` posts `{question, priorQuestion?, priorDefinition?}` and treats `!res.data.valid || !res.data.definition` as failure (a clarify reply is definition-less — the clarify branch must run **before** that check); `.reporting-simple-choice` / `.reporting-simple-choices` pill CSS already ships; `_stub_ai_build` fulfills `{"definition", "explanation", "valid", "error"}`; `tests/e2e/test_reporting_simple.py` imports `json` at module level and already contains a `page.screenshot(path="var/screenshots/...")` precedent; `tests/integration/test_reporting_ai_routes.py` does NOT import `json` yet (its imports start `import datetime`); `_build_patches()` returns `(stub, [7 patches])` with the validator stub `(False, "no def")` at index 5 and `_audit_ai` last; `_agent_patches()` returns 6 patches (no `ask_agentic`/`_audit_ai`); `_agentic_result()` carries an ok build_definition trace, so `_extract_agent_artifacts` yields a definition for it; `GRAINS = {"day", "week", "month", "quarter", "year"}` lives in `nx_lib/reporting/schema.py` (which imports nothing from `ai.py` — no cycle); `_metrics_for_source(source_id)` returns `{code: {...}}`; `{% include 'js/_reporting_sqlformat_js.html' %}` is directly followed by `{% include '_reporting_simple.html' %}` inside `rpPaneSimple` (unconditional — `window.ReportingFollowups` will exist on every /reporting load); the Agent submode button `reporting-ai-mode-agent` renders unconditionally inside `{% if ai_enabled %}` and TEST seed grants `reporting.ai.use`.
- **Housekeeping:** the stray unstaged deletion of `env/CONFLUENCE.env.example` in `git status` belongs to the `feat/confluence-docs-sync` worktree — do **not** commit or restore it here. The ruflo background agent can stash uncommitted edits and drop 0-byte junk files named after code tokens — commit early and often; `rm` junk files, never commit them.

### Decisions locked in

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Scope (OWNER) | ALL AI surfaces get the plain-language + clarify treatment: Simple Ask-AI card + AI refine, AND Advanced Build, Write-SQL, Agent | Owner decision 2026-06-12, verbatim — not up for debate |
| 2 | Clarify UX (OWNER) | ONE clarify round with clickable chips: short plain-language question + 2–4 "did you mean…?" choices; clicking re-asks automatically with that meaning folded in; NO chat thread, NO stored conversation state — a still-unclear follow-up simply clarifies again (stateless loop) | Owner decision 2026-06-12, verbatim |
| 3 | Tweak suggestions (OWNER) | After AI-DRAFTED reports only; ride along in the AI draft response; render as clickable chips under/near the result; every suggestion validated against the source catalog before display; no deterministic engine for manual wizard runs | Owner decision 2026-06-12, verbatim |
| 4 | Clarify wire shape | Optional top-level `clarify: {question: str, choices: [str×2..4]}` on all three responses; each choice is a complete, self-contained rephrasing the client re-sends as the next `question` | A choice that IS the refined ask needs zero new request fields and zero server state — the exact `agentContext()`/refine precedent |
| 5 | Suggestion wire shape | Model emits `{label, ask, field, grain?, metric?}`; server validates `field` (must exist in the draft's source catalog), `grain` (∈ `GRAINS` AND field grainable), optional `metric` (∈ source metric codes), caps at 3, then strips to `{label, ask}` for the client | `ask` (a full refined question) reuses the proven refine pipe wholesale; requiring `field` on EVERY suggestion makes the owner's catalog-validation rule enforceable rather than advisory |
| 6 | Suggestion click semantics | Simple: `askAi(ask)` (a refine — carries `priorQuestion`/`priorDefinition`); Advanced Build: re-POST with the same refine fields | The validator re-checks the result either way; refine context keeps the model anchored on the draft being tweaked |
| 7 | Tweak chips on Write-SQL & Agent surfaces | NO — clarify yes, tweak chips no (Surface-A consumers only: Simple ask/refine + Advanced Build) | Decision 3 says "AI-drafted REPORTS"; a SQL draft is not a report and has no source catalog to validate against. Flagged as an open question for the owner |
| 8 | Clarify vs self-repair retry | A clarify reply (no definition) **breaks out** of the 2-attempt loop before validation; the validator retry stays reserved for actually-invalid drafts | The retry re-prompts with "Your previous attempt was REJECTED" — nonsense for a question the model asked; also halves the cost of a clarify round |
| 9 | Clarify precedence | `clarify` is honored only when the reply carries no `definition`/`sql` artifact; with an artifact present the artifact wins — enforced in `ask()` (sql wins) and in BOTH routes that parse free text (`api_ai_build` gates on `definition is None`; `api_ai_agent` gates on `not definition and not sql`) | Belt-and-braces against a model that emits both; keeps `valid` semantics untouched |
| 10 | Validation home | New pure module `nx_lib/reporting/ai_followups.py` (`sanitize_clarify`, `clarify_from_text`, `validate_suggestions`) + a views-level `_resolve_source_catalog()` extracted from `_validate_definition_for_user` and shared with the new `_validated_ai_suggestions()` | One catalog-resolution code path = drafts and chips are checked against EXACTLY the same fields; the pure module is unit-testable without Flask/DB |
| 11 | AI answer language | Prompt directive built from `str(get_locale())` → "Write every human-readable text … in German/French/Italian/English"; threaded as a `locale=` kwarg into `ask`/`ask_definition` and appended to the agent grounding (never prepended — a test pins `startswith("Today's date")`) | Server knows the locale (already used for catalog labels); client-side translation of free-form model text is impossible |
| 12 | Frontend chips UI | Shared partial `templates/js/_reporting_followups_js.html` (`window.ReportingFollowups`), XSS-safe `createElement`/`textContent`, pills reuse the existing `.reporting-simple-choice` CSS; mounts `#rsClarify`/`#rsSuggest` (Simple) and `#rpAiClarify`/`#rpAiSuggest` (Advanced); every clarify panel ends with a "None of these — ask differently" escape pill that hands focus back to the prompt | Both tabs need identical rendering; model text must never hit `innerHTML`; the escape pill honors the owner's "ask again or give suggestions" without trapping the user (on Simple fresh asks the prompt lives in another view) |
| 13 | Old-client compatibility | All response keys are additive and presence-gated; `definition/explanation/valid/error`, `sql/.../model`, `answer/.../explainData` are byte-identical for non-clarify replies | The verified contract-ripple list stays green; e2e stubs only gain optional keys |
| 14 | Audit | Clarify replies audit as `status='ok'`, `gate_verdict='clarify'` (fits `NVARCHAR(16)`); agent audit unchanged (its verdict slot carries `stopped_reason`) | Real provider call ⇒ counts toward the daily cap; the verdict makes clarify rates measurable in `ReportingAiAudit` |
| 15 | `/ai/build` max_tokens | Pass `max_tokens=1536` on this surface only (pinned by an integration test) | Definition + explanation + up to 3 suggestions in one strict-JSON reply; a truncated JSON breaks the whole parse and burns the self-repair retry — headroom is free when unused |
| 16 | Stale-chip hygiene | `showAiLoading`, `showResultError` and `runCurrent` (Simple) and `setSurface` + every ask function (Advanced) clear both clarify and suggestion containers | Chips from a previous draft must never sit beside a loading indicator, an error, or a fresh clarify question |

### Owner actions

1. **Decide:** should tweak chips ALSO appear under Write-SQL drafts and under agent answers that produced a definition? This plan ships them on Surface-A consumers only (Decision 7) — extending later is additive.
2. **Decide:** is 2× daily-quota burn per clarified question acceptable, or should clarify replies be excluded from `AI_DAILY_LIMIT` (would need a new audit status instead of `'ok'`)? This plan keeps them counted.
3. **After merge, on INT:** sanity-ask the live gpt-4o-mini something ambiguous ("zeig mir die dokumente") and something German to confirm the clarify round and the language directive behave on the real model — stubs cannot prove prompt efficacy. INT has transient DB outages; a failure there may be infrastructure.
4. Standing debt (push + PR for `feature/2.5.63`, PROD migrations 0015–0018, RO SQL logins, scheduled-reports task) is unchanged by this plan.

---

# PHASE 1 — Pure backend: follow-up validation module + model-client changes

### Task 0: Rebase onto the merged feature branch

**Files:** none (git only)

- [ ] **Step 1: Rebase**

```powershell
git fetch . feature/2.5.63 2>$null; git rebase feature/2.5.63
```
Expected: clean fast-forward-style rebase (this branch has no commits yet beyond `f085cc2`); `git log --oneline -1` now shows `e9afaae` or later as the parent.

- [ ] **Step 2: Sanity-run the suites this plan extends**

```powershell
python -m pytest tests/unit/test_reporting_ai.py tests/unit/test_reporting_ai_definition.py tests/unit/test_reporting_ai_agentic.py tests/integration/test_reporting_ai_routes.py -q
```
Expected: all PASS (baseline green before any edit).

### Task 1: `ai_followups` module — clarify sanitizing + suggestion catalog-gating

**Files:**
- Create: `nx_lib/reporting/ai_followups.py`
- Test: `tests/unit/test_reporting_ai_followups.py` (new)

- [ ] **Step 1: Write the clarify-side failing tests.** Create `tests/unit/test_reporting_ai_followups.py`:

```python
"""Unit tests for AI follow-up validation (clarify rounds + tweak suggestions).

Pure module: no Flask, no DB. sanitize_clarify shape-caps a model-proposed
"did you mean...?" round; validate_suggestions enforces the owner rule that a
tweak chip may never name a field/grain the source catalog does not have.
"""

import json

from nx_lib.reporting.ai_followups import (
    clarify_from_text,
    sanitize_clarify,
    validate_suggestions,
)

CATALOG = [
    {"field": "export_date", "label": "Export date", "type": "date",
     "filterable": True, "sortable": True, "grainable": True},
    {"field": "import_date", "label": "Import date", "type": "date",
     "filterable": True, "sortable": True, "grainable": True},
    {"field": "docsource", "label": "Document Source", "type": "string",
     "filterable": True, "sortable": True},
]


def test_sanitize_clarify_accepts_well_formed_round():
    out = sanitize_clarify(
        {"question": " Which date do you mean? ",
         "choices": ["documents imported last month", "documents exported last month"]}
    )
    assert out == {
        "question": "Which date do you mean?",
        "choices": ["documents imported last month", "documents exported last month"],
    }


def test_sanitize_clarify_caps_at_four_choices_and_dedupes():
    out = sanitize_clarify(
        {"question": "q?", "choices": ["a", "A ", "b", "c", "d", "e"]}
    )
    assert out["choices"] == ["a", "b", "c", "d"]  # case-insensitive dedupe, max 4


def test_sanitize_clarify_rejects_garbage():
    assert sanitize_clarify(None) is None
    assert sanitize_clarify("not a dict") is None
    assert sanitize_clarify({"question": "", "choices": ["a", "b"]}) is None
    assert sanitize_clarify({"question": "q", "choices": ["only one"]}) is None
    assert sanitize_clarify({"question": "q", "choices": [1, 2, 3]}) is None
    assert sanitize_clarify({"question": "x" * 301, "choices": ["a", "b"]}) is None
    # Oversized choices are dropped; if fewer than 2 survive, the round dies.
    assert sanitize_clarify({"question": "q", "choices": ["a", "y" * 301]}) is None


def test_clarify_from_text_parses_plain_and_fenced_json():
    obj = {"clarify": {"question": "Which process?", "choices": ["all", "Privera only"]}}
    assert clarify_from_text(json.dumps(obj))["question"] == "Which process?"
    fenced = "```json\n" + json.dumps(obj) + "\n```"
    assert clarify_from_text(fenced)["choices"] == ["all", "Privera only"]
    assert clarify_from_text("The answer is 42 documents.") is None
    assert clarify_from_text("") is None
    assert clarify_from_text(None) is None
```

- [ ] **Step 2: Append the suggestion-side failing tests** to the same file:

```python
def test_validate_suggestions_keeps_only_catalog_true_claims():
    raw = [
        {"label": "Use the import date instead", "ask": "docs per month by import date",
         "field": "import_date"},
        {"label": "Break it down to weeks", "ask": "docs per week",
         "field": "export_date", "grain": "week"},
        # invalid: field not in catalog
        {"label": "By warehouse", "ask": "docs by warehouse", "field": "warehouse"},
        # invalid: grain on a non-grainable field
        {"label": "Source per week", "ask": "x", "field": "docsource", "grain": "week"},
        # invalid: grain claim without naming its field
        {"label": "Weekly", "ask": "weekly", "grain": "week"},
        # invalid: no field claim at all -> cannot be catalog-verified
        {"label": "Top 10 only", "ask": "top 10 docs"},
    ]
    out = validate_suggestions(raw, catalog=CATALOG)
    assert out == [
        {"label": "Use the import date instead", "ask": "docs per month by import date"},
        {"label": "Break it down to weeks", "ask": "docs per week"},
    ]


def test_validate_suggestions_checks_metric_codes_and_caps_at_three():
    raw = [
        {"label": f"s{i}", "ask": f"a{i}", "field": "docsource"} for i in range(5)
    ]
    assert len(validate_suggestions(raw, catalog=CATALOG)) == 3
    with_metric = [{"label": "Count distinct", "ask": "x", "field": "docsource",
                    "metric": "doc_count"}]
    assert validate_suggestions(with_metric, catalog=CATALOG) == []
    assert validate_suggestions(
        with_metric, catalog=CATALOG, metric_codes={"doc_count"}
    ) == [{"label": "Count distinct", "ask": "x"}]


def test_validate_suggestions_rejects_malformed_items_and_non_lists():
    assert validate_suggestions(None, catalog=CATALOG) == []
    assert validate_suggestions("nope", catalog=CATALOG) == []
    raw = [
        "not a dict",
        {"label": "", "ask": "a", "field": "docsource"},
        {"label": "ok", "ask": "", "field": "docsource"},
        {"label": "x" * 81, "ask": "a", "field": "docsource"},
        {"label": "ok", "ask": "y" * 301, "field": "docsource"},
        {"label": "dupe", "ask": "a", "field": "docsource"},
        {"label": "DUPE", "ask": "b", "field": "docsource"},
    ]
    assert validate_suggestions(raw, catalog=CATALOG) == [{"label": "dupe", "ask": "a"}]
```

- [ ] **Step 3: Run them, watch them fail**

```powershell
python -m pytest tests/unit/test_reporting_ai_followups.py -v
```
Expected: collection error — `ModuleNotFoundError: No module named 'nx_lib.reporting.ai_followups'`.

- [ ] **Step 4: Implement.** Create `nx_lib/reporting/ai_followups.py`:

```python
"""Validation for AI follow-up artifacts: clarify rounds + tweak suggestions.

Pure module (no Flask, no DB, must NOT import .ai — ai.py imports from here).
Everything whitelists model output before it reaches a response contract:

- sanitize_clarify / clarify_from_text shape-cap a "did you mean...?" round
  (one short question + 2-4 complete rephrasings the client re-asks verbatim).
- validate_suggestions catalog-gates tweak chips: a suggestion survives only
  if the catalog field it names exists, any grain it claims is legal AND the
  field is grainable, and any metric it names is a real source metric code.
  Suggestions without a field claim are dropped — that requirement is what
  makes "never show a chip for a field/grain the source does not have"
  enforceable instead of advisory.
"""

import json
import re

from .schema import GRAINS

MAX_CLARIFY_QUESTION_LEN = 300
MAX_CHOICE_LEN = 300
MIN_CHOICES = 2
MAX_CHOICES = 4

MAX_SUGGESTIONS = 3
MAX_SUGGESTION_LABEL_LEN = 80
MAX_SUGGESTION_ASK_LEN = 300

_FENCE = re.compile(r"```(?:json)?\s*(.+?)```", re.IGNORECASE | re.DOTALL)


def sanitize_clarify(raw):
    """Shape-check a model-proposed clarify object. Returns a clean
    {"question", "choices"} dict or None (malformed rounds are dropped, never
    repaired into something the model did not say)."""
    if not isinstance(raw, dict):
        return None
    question = raw.get("question")
    choices = raw.get("choices")
    if not isinstance(question, str) or not question.strip():
        return None
    if len(question) > MAX_CLARIFY_QUESTION_LEN:
        return None
    if not isinstance(choices, list):
        return None
    clean, seen = [], set()
    for c in choices:
        if not isinstance(c, str):
            continue
        c = c.strip()
        if not c or len(c) > MAX_CHOICE_LEN:
            continue
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        clean.append(c)
        if len(clean) >= MAX_CHOICES:
            break
    if len(clean) < MIN_CHOICES:
        return None
    return {"question": question.strip(), "choices": clean}


def clarify_from_text(text):
    """Parse a model's free-text reply; return a sanitized clarify dict when
    the text is a {"clarify": ...} JSON object (bare or ```json fenced), else
    None. Used for the agent surface, whose final answer is plain text."""
    text = (text or "").strip()
    if not text:
        return None
    m = _FENCE.search(text)
    for candidate in (text, m.group(1).strip() if m else None):
        if not candidate:
            continue
        try:
            obj = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            return sanitize_clarify(obj.get("clarify"))
    return None


def validate_suggestions(raw, *, catalog, metric_codes=frozenset()):
    """Whitelist-filter model-proposed tweak suggestions against a source
    catalog. Each raw item: {"label", "ask", "field", "grain"?, "metric"?}.
    Returns at most MAX_SUGGESTIONS of {"label", "ask"} — the structured
    claims are validation-only and stripped from the wire."""
    if not isinstance(raw, list):
        return []
    fields = {
        f.get("field"): f for f in catalog if isinstance(f, dict) and f.get("field")
    }
    out, seen = [], set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        label, ask = item.get("label"), item.get("ask")
        if not isinstance(label, str) or not label.strip():
            continue
        if len(label) > MAX_SUGGESTION_LABEL_LEN:
            continue
        if not isinstance(ask, str) or not ask.strip():
            continue
        if len(ask) > MAX_SUGGESTION_ASK_LEN:
            continue
        meta = fields.get(item.get("field"))
        if meta is None:  # no (valid) field claim -> not catalog-verifiable
            continue
        grain = item.get("grain")
        if grain is not None and (grain not in GRAINS or not meta.get("grainable")):
            continue
        metric = item.get("metric")
        if metric is not None and metric not in metric_codes:
            continue
        key = label.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"label": label.strip(), "ask": ask.strip()})
        if len(out) >= MAX_SUGGESTIONS:
            break
    return out
```

- [ ] **Step 5: Run green**

```powershell
python -m pytest tests/unit/test_reporting_ai_followups.py -v
```
Expected: 7 passed.

- [ ] **Step 6: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add nx_lib/reporting/ai_followups.py tests/unit/test_reporting_ai_followups.py
git commit -m "feat(reporting): AI follow-up validation module (clarify + tweaks)" -m "Pure whitelist layer for model-proposed clarify rounds and tweak suggestions: shape caps for the did-you-mean round, catalog gating for tweak chips (field must exist, grain must be legal and grainable, metric must be a real code). No Flask/DB imports."
```

---

### Task 2: Parse `clarify`/`suggestions` out of model replies (`ask_definition` + `ask`)

**Files:**
- Modify: `nx_lib/reporting/ai.py` (dataclasses, `ask_definition` tail, `ask` body, one import)
- Test: `tests/unit/test_reporting_ai_definition.py`, `tests/unit/test_reporting_ai.py`

- [ ] **Step 1: Write the failing `ask_definition` tests.** Append to `tests/unit/test_reporting_ai_definition.py` (the file's helpers `_transport`/`_anthropic_body` are at the top; it imports `from nx_lib.reporting import ai`):

```python
def test_ask_definition_parses_clarify_round():
    obj = {
        "clarify": {
            "question": "Which date do you mean?",
            "choices": ["documents imported last month", "documents exported last month"],
        }
    }
    res = ai.ask_definition(
        "documents last month",
        "CATALOG",
        provider="anthropic",
        model="m",
        api_key="k",
        transport=_transport(_anthropic_body(obj)),
    )
    assert res.definition is None
    assert res.clarify == obj["clarify"]


def test_ask_definition_drops_malformed_clarify():
    obj = {"clarify": {"question": "q?", "choices": ["only one"]}}
    res = ai.ask_definition(
        "q", "CATALOG", provider="anthropic", model="m", api_key="k",
        transport=_transport(_anthropic_body(obj)),
    )
    assert res.clarify is None


def test_ask_definition_passes_raw_suggestions_through():
    obj = {
        "definition": {"schemaVersion": 1, "source": "s", "title": "t",
                       "columns": [], "filters": [], "sort": [],
                       "scope": {"clients": [], "processes": []}, "rowLimit": 100},
        "explanation": "x",
        "suggestions": [{"label": "Per week", "ask": "docs per week",
                         "field": "export_date", "grain": "week"}],
    }
    res = ai.ask_definition(
        "docs", "CATALOG", provider="anthropic", model="m", api_key="k",
        transport=_transport(_anthropic_body(obj)),
    )
    # Raw passthrough: catalog validation happens in the route, which owns
    # the catalog. Non-list suggestions become None.
    assert res.suggestions == obj["suggestions"]


def test_ask_definition_defaults_clarify_and_suggestions_to_none():
    res = ai.ask_definition(
        "q", "CATALOG", provider="anthropic", model="m", api_key="k",
        transport=_transport(_anthropic_body({"definition": {}, "explanation": ""})),
    )
    assert res.clarify is None and res.suggestions is None
```

- [ ] **Step 2: Write the failing `ask` tests.** Append to `tests/unit/test_reporting_ai.py` (uses that file's `_fake_transport`; `json` is imported at its top):

```python
def test_ask_returns_clarify_round_instead_of_sql():
    answer = {
        "clarify": {
            "question": "Which table do you mean?",
            "choices": ["user logins this week", "user signups this week"],
        }
    }
    body = {"content": [{"type": "text", "text": json.dumps(answer)}], "usage": {}}
    res = ai.ask(
        "users this week", "TABLE dbo.Foo(Name)",
        provider="anthropic", model="m", api_key="k",
        transport=_fake_transport(body),
    )
    assert res.clarify == answer["clarify"]
    assert res.sql == ""
    assert res.valid is False
    assert res.gate_verdict == "clarify"


def test_ask_ignores_clarify_when_sql_present():
    answer = {"sql": "SELECT 1 AS X", "explanation": "c",
              "clarify": {"question": "q?", "choices": ["a", "b"]}}
    body = {"content": [{"type": "text", "text": json.dumps(answer)}], "usage": {}}
    res = ai.ask(
        "one", "(* none *)", provider="anthropic", model="m", api_key="k",
        transport=_fake_transport(body),
    )
    assert res.sql == "SELECT 1 AS X"
    assert res.clarify is None  # artifact wins over a stray clarify
```

- [ ] **Step 3: Run them, watch them fail**

```powershell
python -m pytest tests/unit/test_reporting_ai_definition.py tests/unit/test_reporting_ai.py -k "clarify or suggestions" -v
```
Expected: FAIL — `AttributeError: 'AiDefinitionResult' object has no attribute 'clarify'` and `AttributeError: 'AiResult' object has no attribute 'clarify'`. (Single `-k` expression covering both files — pytest takes only one `-k` value per invocation.)

- [ ] **Step 4: Implement.** In `nx_lib/reporting/ai.py`:

  (a) Below the existing import `from .sandbox import SqlSandboxError, validate_select`, add:

```python
from .ai_followups import sanitize_clarify
```

  (b) Extend `AiResult` — find:

```python
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
```

  replace with:

```python
@dataclass
class AiResult:
    sql: str
    explanation: str
    valid: bool
    gate_verdict: str  # "valid" | "invalid" | "clarify"
    model: str
    provider: str
    tokens_in: int | None
    tokens_out: int | None
    clarify: dict | None = None  # sanitized {"question", "choices"} or None
```

  (c) Extend `AiDefinitionResult` — find:

```python
@dataclass
class AiDefinitionResult:
    definition: dict | None
    explanation: str
    model: str
    provider: str
    tokens_in: int | None
    tokens_out: int | None
```

  replace with:

```python
@dataclass
class AiDefinitionResult:
    definition: dict | None
    explanation: str
    model: str
    provider: str
    tokens_in: int | None
    tokens_out: int | None
    clarify: dict | None = None      # sanitized {"question", "choices"} or None
    suggestions: list | None = None  # RAW model list — the route catalog-gates it
```

  (Defaulted fields appended — every existing constructor call and test helper keeps working unchanged.)

  (d) In `ask_definition`, find the reply-parsing tail:

```python
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
```

  replace with:

```python
    definition, explanation, clarify, suggestions = None, "", None, None
    obj = _parse_json_object(text)
    if isinstance(obj, dict):
        d = obj.get("definition")
        if isinstance(d, dict):
            definition = d
        explanation = str(obj.get("explanation", "")).strip()
        clarify = sanitize_clarify(obj.get("clarify"))
        s = obj.get("suggestions")
        if isinstance(s, list):
            suggestions = s
    return AiDefinitionResult(
        definition=definition,
        explanation=explanation,
        model=model,
        provider=provider,
        tokens_in=tin,
        tokens_out=tout,
        clarify=clarify,
        suggestions=suggestions,
    )
```

  (e) In `ask`, find:

```python
    sql, explanation = _extract(text)
    try:
        validate_select(sql)
```

  and insert the clarify branch directly above it:

```python
    obj = _parse_json_object(text)
    if isinstance(obj, dict) and not obj.get("sql"):
        clarify = sanitize_clarify(obj.get("clarify"))
        if clarify is not None:
            # The model asked back instead of drafting — no SQL to gate.
            return AiResult(
                sql="",
                explanation=str(obj.get("explanation", "")).strip(),
                valid=False,
                gate_verdict="clarify",
                model=model,
                provider=provider,
                tokens_in=tin,
                tokens_out=tout,
                clarify=clarify,
            )

    sql, explanation = _extract(text)
    try:
        validate_select(sql)
```

- [ ] **Step 5: Run the AI unit files green (defaults must not break anything)**

```powershell
python -m pytest tests/unit/test_reporting_ai.py tests/unit/test_reporting_ai_definition.py tests/unit/test_reporting_ai_followups.py -q
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add nx_lib/reporting/ai.py tests/unit/test_reporting_ai_definition.py tests/unit/test_reporting_ai.py
git commit -m "feat(reporting): parse clarify and suggestions from AI replies" -m "AiResult/AiDefinitionResult gain optional clarify (sanitized in the client) and raw suggestions fields. Surface B returns gate_verdict 'clarify' with empty SQL when the model asks back; an sql/definition artifact always wins over a stray clarify key."
```

---

### Task 3: System-prompt upgrade — stakeholder vocabulary, clarify rules, suggestion rules, agent rewrite

**Files:**
- Modify: `nx_lib/reporting/ai.py` (`_SYSTEM_DEF`, `_SYSTEM`, `_AGENT_SYSTEM`)
- Test: `tests/unit/test_reporting_ai_definition.py`, `tests/unit/test_reporting_ai.py`, `tests/unit/test_reporting_ai_agentic.py`

- [ ] **Step 1: Write the failing Surface-A prompt pins.** Append to `tests/unit/test_reporting_ai_definition.py`:

```python
def test_system_def_teaches_stakeholder_vocabulary():
    s = ai._SYSTEM_DEF
    assert "broken down by" in s          # group-by translation
    assert '"how many"' in s              # count-metric translation
    assert "free of jargon" in s          # plain-language explanation rule


def test_system_def_teaches_clarify_round():
    s = ai._SYSTEM_DEF
    assert '"clarify"' in s
    assert "do NOT guess" in s
    assert "2-4 choices" in s
    assert "complete, self-contained rephrasing" in s


def test_system_def_teaches_catalog_grounded_suggestions():
    s = ai._SYSTEM_DEF
    assert '"suggestions"' in s
    assert '"ask"' in s and '"label"' in s
    assert "Never suggest a field or grain the source does not list" in s
```

- [ ] **Step 2: Write the failing Surface-B pin.** Append to `tests/unit/test_reporting_ai.py`:

```python
def test_sql_system_prompt_teaches_clarify_and_plain_language():
    s = ai._SYSTEM
    assert '"clarify"' in s
    assert "free of jargon" in s
```

- [ ] **Step 3: Write the failing agent pins.** Append to `tests/unit/test_reporting_ai_agentic.py`:

```python
def test_agent_system_clarifies_instead_of_guessing():
    from nx_lib.reporting.ai import _AGENT_SYSTEM

    assert '"clarify"' in _AGENT_SYSTEM
    assert "do not call tools" in _AGENT_SYSTEM
    # The blanket ban is gone; the success/stop rules survive untouched.
    assert "Do not ask the user questions." not in _AGENT_SYSTEM
    assert "ok:true" in _AGENT_SYSTEM
    assert "2 failed" in _AGENT_SYSTEM


def test_agent_system_demands_jargon_free_answers():
    from nx_lib.reporting.ai import _AGENT_SYSTEM

    assert "business audience" in _AGENT_SYSTEM
```

- [ ] **Step 4: Run them, watch them fail**

```powershell
python -m pytest tests/unit/test_reporting_ai_definition.py tests/unit/test_reporting_ai.py tests/unit/test_reporting_ai_agentic.py -k "stakeholder or clarif or suggestion or jargon" -v
```
Expected: FAIL on every new assertion (none of the strings exist yet).

- [ ] **Step 5: Extend `_SYSTEM_DEF`.** In `nx_lib/reporting/ai.py`, the `_SYSTEM_DEF` string literal ends with:

```python
    ' "Document Date" (the date printed on the document) are correct ONLY'
    " when the user names that field explicitly."
)
```

  Replace those closing lines with (everything before stays byte-identical):

```python
    ' "Document Date" (the date printed on the document) are correct ONLY'
    " when the user names that field explicitly."
    " Your audience is business stakeholders, not data people. They say"
    ' "split up by", "broken down by", "for each", "per <thing>" when they'
    ' mean GROUP BY dimensions, and "how many" / "number of" when they mean a'
    " count metric — translate their wording; never expect technical terms."
    ' Keep "explanation" free of jargon: no "group by", "aggregation",'
    ' "distinct count" or "definition" — describe the result in everyday'
    ' words, e.g. "Shows how many documents arrived each month this year,'
    ' split by source.".'
    " If the question is AMBIGUOUS — you cannot tell which source, field,"
    " date, or time range is meant, or it has several reasonable readings —"
    " do NOT guess. Instead return STRICT JSON"
    ' {"clarify": {"question": "<ONE short plain-language question>",'
    ' "choices": ["<reading 1>", "<reading 2>"]}} with 2-4 choices and NO'
    ' "definition". Each choice must be a complete, self-contained rephrasing'
    " of the user's request that you could answer directly if asked. Only"
    " clarify when genuinely stuck — answer every clear question with a"
    " definition."
    ' When you return a valid definition you may also add "suggestions": up'
    " to 3 optional tweaks the user might like, each"
    ' {"label": "<short plain offer, e.g. Show this per week>", "ask": "<the'
    ' full request with that tweak applied>", "field": "<the exact catalog'
    ' field key the tweak concerns>", "grain": "<only for time-bucket'
    ' tweaks>"}. Good tweaks: switch between import and export date, add or'
    " change a breakdown field, change the time bucket (day/week/month/"
    "quarter/year). Never suggest a field or grain the source does not list."
    ' Omit "suggestions" when nothing useful comes to mind.'
)
```

- [ ] **Step 6: Extend `_SYSTEM` (Surface B).** Find the closing lines:

```python
    "prefer TOP (n) to bound large results. Respond with STRICT JSON: "
    '{"sql": "<the query>", "explanation": "<one sentence>"}. No prose outside JSON.'
)
```

  replace with:

```python
    "prefer TOP (n) to bound large results. Respond with STRICT JSON: "
    '{"sql": "<the query>", "explanation": "<one sentence>"}. No prose outside JSON.'
    ' Keep "explanation" free of jargon — say what the result shows in'
    " everyday words, for people who do not know databases."
    " If the question is too ambiguous to write ONE correct query — and only"
    " then — return STRICT JSON"
    ' {"clarify": {"question": "<one short plain-language question>",'
    ' "choices": ["<reading 1>", "<reading 2>"]}} with 2-4 complete,'
    ' self-contained rephrasings instead of "sql".'
)
```

- [ ] **Step 7: Rewrite the `_AGENT_SYSTEM` ban sentence.** Find (verbatim — these are two source lines):

```python
    "Once any tool returns ok:true, stop calling tools immediately and give a "
    "one- or two-sentence plain-language answer. Do not ask the user questions."
```

  replace with:

```python
    "Once any tool returns ok:true, stop calling tools immediately and give a "
    "one- or two-sentence plain-language answer written for a business "
    "audience — no jargon like GROUP BY, aggregation, or definition. "
    "If the QUESTION ITSELF is too ambiguous to act on (you cannot tell which "
    "source, field, date, or time range is meant), do not guess and do not "
    "call tools: reply with STRICT JSON "
    '{"clarify": {"question": "<one short plain-language question>", '
    '"choices": ["<reading 1>", "<reading 2>"]}} and nothing else — 2-4 '
    "choices, each a complete, self-contained rephrasing of the request. "
    "Otherwise never ask the user questions."
```

  (Everything after — the line starting `" The grounding states today's date; ..."` — stays untouched, so the pinned `"2 failed"`, `"ok:true"`, grain/distinct/process/token/processing-date fragments all survive.)

- [ ] **Step 8: Run the full AI unit suite green (old pins must survive — the `"2 failed"`/`"ok:true"` pins live in the DEFINITION test file, the rest in the agentic file; this command covers both)**

```powershell
python -m pytest tests/unit/test_reporting_ai.py tests/unit/test_reporting_ai_definition.py tests/unit/test_reporting_ai_agentic.py -q
```
Expected: all PASS — including every pre-existing prompt-content test.

- [ ] **Step 9: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add nx_lib/reporting/ai.py tests/unit/test_reporting_ai_definition.py tests/unit/test_reporting_ai.py tests/unit/test_reporting_ai_agentic.py
git commit -m "feat(reporting): teach AI prompts plain language, clarify, tweaks" -m "All three system prompts: stakeholder vocabulary mapping (split up by / how many), jargon-free explanations, a strict-JSON clarify round for ambiguous asks (2-4 complete rephrasings), and catalog-grounded tweak suggestions on Surface A. The agent's blanket 'Do not ask the user questions.' becomes 'clarify without tools when stuck, otherwise never ask'. Each new rule pinned by a prompt-content unit test; all prior pins green."
```

---

### Task 4: User-language directive (`locale` kwarg) for `ask` / `ask_definition`

**Files:**
- Modify: `nx_lib/reporting/ai.py` (`language_name`, `_language_line`, `_user_prompt`, `_definition_user_prompt`, `ask`, `ask_definition`)
- Test: `tests/unit/test_reporting_ai_definition.py`, `tests/unit/test_reporting_ai.py`

- [ ] **Step 1: Write the failing tests.** Append to `tests/unit/test_reporting_ai_definition.py`:

```python
def test_ask_definition_demands_user_language_when_locale_given():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["user"] = body["messages"][0]["content"]
        return _anthropic_body({"definition": {}, "explanation": ""})

    ai.ask_definition(
        "dokumente pro monat", "CATALOG",
        provider="anthropic", model="m", api_key="k",
        locale="de", transport=transport,
    )
    assert "in German" in captured["user"]
    # The directive precedes the catalog so the model reads it first.
    assert captured["user"].index("in German") < captured["user"].index("CATALOG")


def test_ask_definition_omits_language_line_without_locale():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["user"] = body["messages"][0]["content"]
        return _anthropic_body({"definition": {}, "explanation": ""})

    ai.ask_definition(
        "q", "CATALOG", provider="anthropic", model="m", api_key="k",
        transport=transport,
    )
    assert "human-readable" not in captured["user"]


def test_language_name_maps_locales_and_defaults_to_english():
    assert ai.language_name("de") == "German"
    assert ai.language_name("fr") == "French"
    assert ai.language_name("it") == "Italian"
    assert ai.language_name("en") == "English"
    assert ai.language_name("de_CH") == "German"
    assert ai.language_name(None) == "English"
    assert ai.language_name("xx") == "English"
```

  And append to `tests/unit/test_reporting_ai.py`:

```python
def test_ask_demands_user_language_when_locale_given():
    captured = {}

    def transport(url, headers, body, timeout):
        captured["user"] = body["messages"][0]["content"]
        return {"content": [{"type": "text", "text": json.dumps({"sql": "SELECT 1 AS x", "explanation": "e"})}], "usage": {}}

    ai.ask(
        "combien de documents", "TABLE dbo.Foo(Id int)",
        provider="anthropic", model="m", api_key="k",
        locale="fr", transport=transport,
    )
    assert "in French" in captured["user"]
```

- [ ] **Step 2: Run them, watch them fail**

```powershell
python -m pytest tests/unit/test_reporting_ai_definition.py tests/unit/test_reporting_ai.py -k "language or locale" -v
```
Expected: FAIL — `AttributeError: module 'nx_lib.reporting.ai' has no attribute 'language_name'` / `TypeError: ask() got an unexpected keyword argument 'locale'`.

- [ ] **Step 3: Implement.** In `nx_lib/reporting/ai.py`:

  (a) Below the line `_SQL_FENCE = re.compile(r"```(?:sql|json)?\s*(.+?)```", re.IGNORECASE | re.DOTALL)`, add:

```python
_LANG_NAMES = {"en": "English", "de": "German", "fr": "French", "it": "Italian"}


def language_name(locale):
    """Human language name for an app locale (en/de/fr/it, 'de_CH' tolerated).
    Defaults to English."""
    return _LANG_NAMES.get(str(locale or "en").strip().lower()[:2], "English")


def _language_line(locale):
    """Prompt directive demanding user-language output. Empty when no locale."""
    if not locale:
        return ""
    return (
        "Write every human-readable text you return - explanation, clarify "
        f"question and choices, suggestion labels and asks - in {language_name(locale)}.\n\n"
    )
```

  (b) Replace `_user_prompt` wholesale — find:

```python
def _user_prompt(question, schema_text):
    return (
        f"Database schema (names/types/descriptions only):\n{schema_text}\n\n"
        f"Question: {question}\n\n"
        'Return STRICT JSON {"sql": ..., "explanation": ...}.'
    )
```

  replace with:

```python
def _user_prompt(question, schema_text, locale=None):
    return (
        _language_line(locale)
        + f"Database schema (names/types/descriptions only):\n{schema_text}\n\n"
        f"Question: {question}\n\n"
        'Return STRICT JSON {"sql": ..., "explanation": ...}.'
    )
```

  (c) In `_definition_user_prompt`, change the signature and the first statement — find:

```python
def _definition_user_prompt(
    question,
    catalog_text,
    prior_error,
    today=None,
    prior_question=None,
    prior_definition=None,
):
    base = ""
```

  replace with:

```python
def _definition_user_prompt(
    question,
    catalog_text,
    prior_error,
    today=None,
    prior_question=None,
    prior_definition=None,
    locale=None,
):
    base = _language_line(locale)
```

  (The rest of the function — `if today:` onward — stays byte-identical; the existing pin `Today's date` < `CATALOG` ordering survives a prepended language line.)

  (d) In `ask_definition`'s signature, insert `locale=None,` directly after `prior_definition=None,`; in its `_dispatch(` call, find:

```python
            prior_question=prior_question,
            prior_definition=prior_definition,
        ),
```

  replace with:

```python
            prior_question=prior_question,
            prior_definition=prior_definition,
            locale=locale,
        ),
```

  (e) In `ask`'s signature, insert `locale=None,` directly after `url=None,`; change its dispatch argument `_user_prompt(question, schema_text),` to `_user_prompt(question, schema_text, locale=locale),`.

- [ ] **Step 4: Run green (incl. the pre-existing today/refine ordering pins)**

```powershell
python -m pytest tests/unit/test_reporting_ai.py tests/unit/test_reporting_ai_definition.py -q
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add nx_lib/reporting/ai.py tests/unit/test_reporting_ai_definition.py tests/unit/test_reporting_ai.py
git commit -m "feat(reporting): AI answers in the user's language (locale kwarg)" -m "ask/ask_definition accept locale=en|de|fr|it and prepend a user-language directive covering explanations, clarify questions/choices and suggestion labels. No directive without a locale - existing callers unchanged."
```

---

# PHASE 2 — Routes: additive contract extensions on all three endpoints

### Task 5: `/api/reporting/ai/build` — clarify short-circuit, catalog-gated suggestions, locale, max_tokens

**Files:**
- Modify: `nx_lib/views/reporting.py` (`_resolve_source_catalog` extraction, `_validated_ai_suggestions`, `api_ai_build`, imports)
- Test: `tests/integration/test_reporting_ai_routes.py`

- [ ] **Step 1: Add the missing `json` import to the test file.** `tests/integration/test_reporting_ai_routes.py` currently has no `import json` (its imports start `import datetime`). Add `import json` directly below `import datetime` (ruff/isort will settle ordering; if the hook rewrites on commit, `git add -u` and rerun the identical commit). Task 7's agent clarify test needs it too — one edit now.

- [ ] **Step 2: Write the failing clarify tests.** Append to `tests/integration/test_reporting_ai_routes.py` (reuses the file's `_build_patches()` helper — `(stub, [7 patches])`, validator stub `(False, "no def")`, `_audit_ai` last; `AiDefinitionResult` is imported at the top):

```python
# ---- Clarify round + tweak suggestions (plain-language feature) ----------------


def _clarify_result():
    return AiDefinitionResult(
        definition=None,
        explanation="",
        model="m",
        provider="anthropic",
        tokens_in=5,
        tokens_out=5,
        clarify={
            "question": "Which date do you mean?",
            "choices": ["documents imported last month", "documents exported last month"],
        },
    )


def test_ai_build_returns_clarify_without_retry(user_client):
    stub, patches = _build_patches()
    with ExitStack() as es:
        for p in patches:
            es.enter_context(p)
        drafter = es.enter_context(
            patch("nx_lib.views.reporting.ai_ask_definition", return_value=_clarify_result())
        )
        resp = user_client.post("/api/reporting/ai/build", json={"question": "docs last month"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["clarify"]["question"] == "Which date do you mean?"
    assert len(data["clarify"]["choices"]) == 2
    assert data["definition"] is None
    assert data["valid"] is False
    assert data["error"] is None  # a clarify is not a failure
    # The self-repair retry is for invalid drafts, not for questions the model asked.
    drafter.assert_called_once()


def test_ai_build_audits_clarify_verdict(user_client):
    stub, patches = _build_patches()
    with ExitStack() as es:
        for p in patches[:-1]:  # all but the _audit_ai patch, replaced below
            es.enter_context(p)
        audit = es.enter_context(patch("nx_lib.views.reporting._audit_ai"))
        es.enter_context(
            patch("nx_lib.views.reporting.ai_ask_definition", return_value=_clarify_result())
        )
        resp = user_client.post("/api/reporting/ai/build", json={"question": "x"})
    assert resp.status_code == 200
    audit.assert_called_once()
    assert audit.call_args.args[-3] == "clarify"  # gate_verdict
    assert audit.call_args.args[-2] == "ok"       # status (counts toward the cap)
```

- [ ] **Step 3: Write the failing suggestion + locale/max_tokens tests.** Append:

```python
def test_ai_build_returns_only_catalog_valid_suggestions(user_client):
    drafted = AiDefinitionResult(
        definition={
            "schemaVersion": 1, "visualization": "table", "source": "docprocessing",
            "title": "T", "columns": [{"field": "docsource"}], "filters": [],
            "sort": [], "scope": {"clients": [], "processes": []}, "rowLimit": 100,
        },
        explanation="x", model="m", provider="anthropic", tokens_in=1, tokens_out=1,
        suggestions=[
            {"label": "Per week", "ask": "docs per week",
             "field": "export_date", "grain": "week"},
            {"label": "By warehouse", "ask": "docs by warehouse", "field": "warehouse"},
        ],
    )
    catalog = [
        {"field": "docsource", "label": "Source", "type": "string",
         "filterable": True, "sortable": True},
        {"field": "export_date", "label": "Export date", "type": "date",
         "filterable": True, "sortable": True, "grainable": True},
    ]
    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_daily_limit", return_value=0),
        patch("nx_lib.views.reporting._ai_catalog_text", return_value="CATALOG"),
        patch("nx_lib.views.reporting.ai_ask_definition", return_value=drafted),
        patch("nx_lib.views.reporting._validate_definition_for_user", return_value=(True, None)),
        patch(
            "nx_lib.views.reporting._resolve_source_catalog",
            return_value=({"id": "docprocessing", "label": "X"}, catalog),
        ),
        patch("nx_lib.views.reporting._metrics_for_source", return_value={}),
        patch("nx_lib.views.reporting._audit_ai"),
    ):
        resp = user_client.post("/api/reporting/ai/build", json={"question": "docs"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["valid"] is True
    # The bogus-field suggestion is dropped; survivors are stripped to label+ask.
    assert data["suggestions"] == [{"label": "Per week", "ask": "docs per week"}]


def test_ai_build_omits_suggestions_key_for_invalid_draft(user_client):
    stub, patches = _build_patches()  # validator patched to (False, "no def")
    stub.suggestions = [{"label": "x", "ask": "y", "field": "f"}]
    with ExitStack() as es:
        for p in patches:
            es.enter_context(p)
        es.enter_context(
            patch("nx_lib.views.reporting.ai_ask_definition", return_value=stub)
        )
        resp = user_client.post("/api/reporting/ai/build", json={"question": "q"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "suggestions" not in data
    assert "clarify" not in data


def test_ai_build_passes_locale_and_max_tokens_to_drafter(user_client):
    stub, patches = _build_patches()
    with ExitStack() as es:
        for p in patches:
            es.enter_context(p)
        es.enter_context(patch("nx_lib.views.reporting.get_locale", return_value="de"))
        drafter = es.enter_context(
            patch("nx_lib.views.reporting.ai_ask_definition", return_value=stub)
        )
        resp = user_client.post("/api/reporting/ai/build", json={"question": "q"})
    assert resp.status_code == 200
    assert drafter.call_args.kwargs["locale"] == "de"
    # Headroom for definition + explanation + 3 suggestions in ONE strict-JSON
    # reply — a truncated reply fails the whole parse (Decision 15).
    assert drafter.call_args.kwargs["max_tokens"] == 1536
```

- [ ] **Step 4: Run them, watch them fail**

```powershell
python -m pytest tests/integration/test_reporting_ai_routes.py -k "clarify or suggestion or locale" -v
```
Expected: FAIL — `clarify`/`suggestions` keys absent (`KeyError`), `AttributeError: ... does not have the attribute '_resolve_source_catalog'`, `KeyError: 'locale'`, and `drafter.assert_called_once()` fails with `call_count == 2`.

- [ ] **Step 5: Implement the view helpers.** In `nx_lib/views/reporting.py`:

  (a) Imports — the AI import line currently reads:

```python
from ..reporting.ai import _AGENT_EXPLAIN_SUFFIX, _AGENT_SYSTEM, AiError, ask_agentic
```

  change to (Tasks 6–7 need `language_name`/`clarify_from_text` too — one edit; let ruff-format/isort settle layout):

```python
from ..reporting.ai import (
    _AGENT_EXPLAIN_SUFFIX,
    _AGENT_SYSTEM,
    AiError,
    ask_agentic,
    language_name,
)
from ..reporting.ai_followups import clarify_from_text, validate_suggestions
```

  (b) Extract `_resolve_source_catalog`. `_validate_definition_for_user` currently begins:

```python
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
```

  Replace that opening with:

```python
    if not isinstance(definition, dict):
        return False, "definition must be an object"
    try:
        source, catalog = _resolve_source_catalog(definition.get("source"))
        catalog_fields = {f["field"] for f in catalog}
```

  and add the two new functions directly ABOVE `def _validate_definition_for_user(definition):`:

```python
def _resolve_source_catalog(source_id):
    """Resolve a curated source + its locale-aware field catalog for the caller.

    Shared by the Surface-A draft validator and the tweak-suggestion gate so
    both check against exactly the same fields. Raises ReportDefinitionError /
    PermissionError for unknown or unauthorized sources (messages match the
    validator's historical return values).
    """
    source = _get_effective_source(source_id)
    if source is None or source.get("kind") != "curated":
        raise ReportDefinitionError("unknown or unsupported source")
    if not has_permission(source["permission"]):
        raise PermissionError("not authorized for this source")
    provider = source.get("provider") or "docprocessing"
    if provider == "docprocessing":
        catalog = fetch_docprocessing_catalog(_allowed_processes(), str(get_locale()))
    else:
        catalog = table_source_catalog(source.get("columns"))
    return source, catalog


def _validated_ai_suggestions(definition, raw):
    """Catalog-gate model-proposed tweak suggestions (owner rule: never show a
    chip for a field/grain the source does not have). Never raises — they are
    optional sugar; any resolution failure drops them all."""
    if not raw or not isinstance(definition, dict):
        return []
    try:
        source, catalog = _resolve_source_catalog(definition.get("source"))
        return validate_suggestions(
            raw, catalog=catalog, metric_codes=set(_metrics_for_source(source["id"]))
        )
    except Exception as e:
        current_app.logger.warning(f"reporting.ai suggestions dropped: {e}")
        return []
```

  (The existing `except (ReportDefinitionError, PermissionError) as e: return False, str(e) or e.__class__.__name__` tail of `_validate_definition_for_user` catches the raised errors with identical messages — no test churn.)

  (c) `api_ai_build` draft loop — find:

```python
    catalog_text = _ai_catalog_text()
    start = time.monotonic()
    prior_error = None
    result = None
    valid = False
    for _attempt in range(2):  # initial draft + one bounded self-repair retry
```

  replace with:

```python
    catalog_text = _ai_catalog_text()
    start = time.monotonic()
    prior_error = None
    result = None
    valid = False
    clarify = None
    for _attempt in range(2):  # initial draft + one bounded self-repair retry
```

  then the `ai_ask_definition(` call tail — find:

```python
                prior_question=prior_question or None,
                prior_definition=prior_definition or None,
            )
```

  replace with:

```python
                prior_question=prior_question or None,
                prior_definition=prior_definition or None,
                locale=str(get_locale()),
                max_tokens=1536,
            )
```

  and the loop tail — find:

```python
        valid, prior_error = _validate_definition_for_user(result.definition)
        if valid:
            break
```

  replace with:

```python
        clarify = result.clarify
        if clarify and not result.definition:
            # The model asked back instead of drafting. That is not a
            # validation failure — don't burn the self-repair retry telling
            # the model to "fix" a question it asked (Decision 8).
            valid, prior_error = False, None
            break
        valid, prior_error = _validate_definition_for_user(result.definition)
        if valid:
            break
```

  (d) `api_ai_build` response tail — find:

```python
    duration_ms = int((time.monotonic() - start) * 1000)
    definition = _normalize_definition(result.definition) if result.definition else None
    _audit_ai(
        userid,
        username,
        question,
        "definition",
        json.dumps(definition) if definition else None,
        result.provider,
        result.model,
        result.tokens_in,
        result.tokens_out,
        "valid" if valid else "invalid",
        "ok",
        duration_ms,
    )
    return jsonify(
        {
            "definition": definition,
            "explanation": result.explanation,
            "valid": valid,
            "error": None if valid else (prior_error or _("Could not build a valid report")),
        }
    )
```

  replace with:

```python
    duration_ms = int((time.monotonic() - start) * 1000)
    definition = _normalize_definition(result.definition) if result.definition else None
    # Clarify only counts when no definition came back; with an artifact the
    # validator verdict wins (Decision 9). Suggestions only ride VALID drafts.
    clarify = clarify if (clarify and definition is None) else None
    suggestions = _validated_ai_suggestions(definition, result.suggestions) if valid else []
    _audit_ai(
        userid,
        username,
        question,
        "definition",
        json.dumps(definition) if definition else None,
        result.provider,
        result.model,
        result.tokens_in,
        result.tokens_out,
        "clarify" if clarify else ("valid" if valid else "invalid"),
        "ok",
        duration_ms,
    )
    payload = {
        "definition": definition,
        "explanation": result.explanation,
        "valid": valid,
        "error": None
        if (valid or clarify)
        else (prior_error or _("Could not build a valid report")),
    }
    if clarify:
        payload["clarify"] = clarify
    if suggestions:
        payload["suggestions"] = suggestions
    return jsonify(payload)
```

- [ ] **Step 6: Run the whole route file green (40+ pre-existing tests must survive)**

```powershell
python -m pytest tests/integration/test_reporting_ai_routes.py -q
```
Expected: all PASS — incl. `test_ai_build_retries_once_then_returns_invalid` (the clarify break never triggers for clarify-less results) and the refine-context tests.

- [ ] **Step 7: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add nx_lib/views/reporting.py tests/integration/test_reporting_ai_routes.py
git commit -m "feat(reporting): clarify round and tweak chips on /ai/build" -m "Additive contract: optional clarify {question, choices} when the model asks back (skips the self-repair retry, audits gate_verdict=clarify) and optional suggestions [{label, ask}] on valid drafts, catalog-gated via the extracted _resolve_source_catalog shared with the draft validator. Locale threaded so AI text returns in the user's language; max_tokens raised to 1536 on this surface for the larger strict-JSON reply."
```

---

### Task 6: `/api/reporting/ai/ask` (Write-SQL) — clarify passthrough + locale

**Files:**
- Modify: `nx_lib/views/reporting.py` (`api_ai_ask` call + return)
- Test: `tests/integration/test_reporting_ai_routes.py`

- [ ] **Step 1: Write the failing tests.** Append to `tests/integration/test_reporting_ai_routes.py`:

```python
def test_ai_ask_returns_clarify_round(user_client):
    clarified = AiResult(
        sql="", explanation="", valid=False, gate_verdict="clarify",
        model="m", provider="anthropic", tokens_in=4, tokens_out=4,
        clarify={"question": "Which table?", "choices": ["logins", "signups"]},
    )
    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
        patch("nx_lib.views.reporting.ai_ask", return_value=clarified),
        patch("nx_lib.views.reporting._audit_ai") as audit,
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "users this week"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["clarify"]["choices"] == ["logins", "signups"]
    assert data["sql"] == "" and data["valid"] is False
    audit.assert_called_once()
    assert audit.call_args.args[-3] == "clarify"


def test_ai_ask_omits_clarify_key_on_normal_draft(user_client):
    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_schema_text", return_value="TABLE dbo.Foo(Id int)"),
        patch("nx_lib.views.reporting.ai_ask", return_value=_result()),
        patch("nx_lib.views.reporting._audit_ai"),
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "five ids"})
    assert "clarify" not in resp.get_json()


def test_ai_ask_passes_locale(user_client):
    with (
        patch("nx_lib.security.has_permission", return_value=True),
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._ai_config",
            return_value={"provider": "anthropic", "api_key": "k", "model": "m"},
        ),
        patch("nx_lib.views.reporting._ai_schema_text", return_value="T"),
        patch("nx_lib.views.reporting.get_locale", return_value="it"),
        patch("nx_lib.views.reporting.ai_ask", return_value=_result()) as ask,
        patch("nx_lib.views.reporting._audit_ai"),
    ):
        resp = user_client.post("/api/reporting/ai/ask", json={"question": "q"})
    assert resp.status_code == 200
    assert ask.call_args.kwargs["locale"] == "it"
```

- [ ] **Step 2: Run them, watch them fail**

```powershell
python -m pytest tests/integration/test_reporting_ai_routes.py -k "ai_ask and (clarify or locale)" -v
```
Expected: FAIL — no `clarify` key, no `locale` kwarg.

- [ ] **Step 3: Implement.** In `api_ai_ask`:

  (a) The 3-line call tail `api_version=... / url=... / )` is byte-identical in `api_ai_agent`'s `make_agent_step(` call, so anchor through the route-specific `except` line. Find (verbatim, unique — the log message names `/ai/ask`):

```python
            api_version=cfg.get("api_version", "2024-10-21"),
            url=cfg.get("url"),
        )
    except AiError as e:
        current_app.logger.warning(f"/api/reporting/ai/ask config error: {e}")
```

  replace with:

```python
            api_version=cfg.get("api_version", "2024-10-21"),
            url=cfg.get("url"),
            locale=str(get_locale()),
        )
    except AiError as e:
        current_app.logger.warning(f"/api/reporting/ai/ask config error: {e}")
```

  **Never touch the byte-identical tail inside `api_ai_agent`'s `make_agent_step(` call** — `make_agent_step` has no `locale` kwarg.

  (b) The return — find:

```python
    return jsonify(
        {
            "sql": result.sql,
            "explanation": result.explanation,
            "valid": result.valid,
            "target": "statistics",  # default editor target; user can switch
            "model": result.model,
        }
    )
```

  replace with:

```python
    payload = {
        "sql": result.sql,
        "explanation": result.explanation,
        "valid": result.valid,
        "target": "statistics",  # default editor target; user can switch
        "model": result.model,
    }
    if result.clarify:
        payload["clarify"] = result.clarify
    return jsonify(payload)
```

  (The audit call above it already passes `result.gate_verdict` positionally — `"clarify"` flows into `ReportingAiAudit.GateVerdict` with zero change.)

- [ ] **Step 4: Run green**

```powershell
python -m pytest tests/integration/test_reporting_ai_routes.py -q
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add nx_lib/views/reporting.py tests/integration/test_reporting_ai_routes.py
git commit -m "feat(reporting): clarify round on the Write-SQL surface" -m "Optional clarify key on /ai/ask when the model asks back instead of drafting (sql empty, valid false, gate_verdict clarify); locale threaded so explanations and clarify text return in the user's language. Existing response keys byte-identical."
```

---

### Task 7: `/api/reporting/ai/agent` — clarify from the final answer + answer-language grounding

**Files:**
- Modify: `nx_lib/views/reporting.py` (`api_ai_agent` grounding + response)
- Test: `tests/integration/test_reporting_ai_routes.py`

- [ ] **Step 1: Write the failing tests.** Append to `tests/integration/test_reporting_ai_routes.py` (uses `_agent_patches()` and the `AiAgenticResult` import; `json` was added in Task 5):

```python
def test_ai_agent_returns_clarify_from_answer(user_client):
    clarify_answer = json.dumps(
        {"clarify": {"question": "Which process?",
                     "choices": ["the Privera invoice process", "all processes"]}}
    )
    looped = AiAgenticResult(
        answer=clarify_answer, turns=1, tool_trace=[],
        stopped_reason="final", tokens_in=5, tokens_out=5,
    )
    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        es.enter_context(patch("nx_lib.views.reporting.ask_agentic", return_value=looped))
        es.enter_context(patch("nx_lib.views.reporting._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "how many docs?"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["clarify"]["question"] == "Which process?"
    assert data["answer"] == ""  # raw clarify JSON never shown as prose
    assert data["definition"] is None and data["sql"] is None


def test_ai_agent_artifact_wins_over_clarify_text(user_client):
    # A misbehaving model that completed a build AND emitted clarify JSON as
    # its final answer: the artifact wins (Decision 9) — no clarify key, the
    # answer passes through untouched for the thread.
    clarify_answer = json.dumps({"clarify": {"question": "q?", "choices": ["a", "b"]}})
    looped = _agentic_result(answer=clarify_answer)  # carries an ok build trace
    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        es.enter_context(patch("nx_lib.views.reporting.ask_agentic", return_value=looped))
        es.enter_context(
            patch("nx_lib.views.reporting._validate_definition_for_user", return_value=(True, None))
        )
        es.enter_context(patch("nx_lib.views.reporting._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "docs?"})
    data = resp.get_json()
    assert "clarify" not in data
    assert data["definition"] is not None
    assert data["answer"] == clarify_answer


def test_ai_agent_plain_answer_has_no_clarify_key(user_client):
    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        es.enter_context(
            patch("nx_lib.views.reporting.ask_agentic", return_value=_agentic_result())
        )
        es.enter_context(
            patch("nx_lib.views.reporting._validate_definition_for_user", return_value=(True, None))
        )
        es.enter_context(patch("nx_lib.views.reporting._audit_ai"))
        resp = user_client.post("/api/reporting/ai/agent", json={"question": "docs?"})
    data = resp.get_json()
    assert "clarify" not in data
    assert data["answer"]  # untouched


def test_ai_agent_grounding_demands_answer_language(user_client):
    with ExitStack() as es:
        for p in _agent_patches():
            es.enter_context(p)
        es.enter_context(patch("nx_lib.views.reporting.get_locale", return_value="fr"))
        loop = es.enter_context(
            patch("nx_lib.views.reporting.ask_agentic", return_value=_agentic_result())
        )
        es.enter_context(
            patch("nx_lib.views.reporting._validate_definition_for_user", return_value=(True, None))
        )
        es.enter_context(patch("nx_lib.views.reporting._audit_ai"))
        user_client.post("/api/reporting/ai/agent", json={"question": "combien?"})
    initial = loop.call_args.args[0]
    assert "in French" in initial
    # Appended, never prepended: the today's-date pin must survive.
    assert initial.startswith("Today's date is")
```

- [ ] **Step 2: Run them, watch them fail**

```powershell
python -m pytest tests/integration/test_reporting_ai_routes.py -k "agent and (clarify or language or artifact)" -v
```
Expected: FAIL — no `clarify` key, `data["answer"] == ""` fails (raw JSON echoed), no language line in the grounding.

- [ ] **Step 3: Implement.** In `api_ai_agent`:

  (a) Language line — find:

```python
    initial = f"{grounding}\n\nQuestion: {question}"
```

  replace with:

```python
    grounding += (
        "\n\nWrite your final answer — and any clarify question and choices — "
        f"in {language_name(str(get_locale()))}."
    )
    initial = f"{grounding}\n\nQuestion: {question}"
```

  (b) Clarify extraction — find:

```python
    duration_ms = int((time.monotonic() - start) * 1000)
    definition, sql = _extract_agent_artifacts(result.tool_trace)
```

  replace with:

```python
    duration_ms = int((time.monotonic() - start) * 1000)
    definition, sql = _extract_agent_artifacts(result.tool_trace)
    # Clarify only when the loop produced NO artifact (Decision 9: with a
    # definition or SQL present the artifact wins). The clarify path is the
    # model replying with a {"clarify": ...} JSON object instead of prose —
    # surface it as chips, never as a raw-JSON "answer".
    clarify = None
    if not definition and not sql and result.answer:
        clarify = clarify_from_text(result.answer)
```

  (c) Response — find:

```python
    return jsonify(
        {
            "answer": result.answer,
            "definition": definition,
            "sql": sql,
            "toolTrace": result.tool_trace,
            "turns": result.turns,
            "stoppedReason": result.stopped_reason,
            "explainData": explain,
        }
    )
```

  replace with:

```python
    payload = {
        "answer": "" if clarify else result.answer,
        "definition": definition,
        "sql": sql,
        "toolTrace": result.tool_trace,
        "turns": result.turns,
        "stoppedReason": result.stopped_reason,
        "explainData": explain,
    }
    if clarify:
        payload["clarify"] = clarify
    return jsonify(payload)
```

  (The `_audit_ai` call between (b) and (c) keeps `result.answer` inside its JSON blob — the audit sees what the model actually said.)

- [ ] **Step 4: Run green (incl. `test_ai_agent_grounding_states_todays_date`), then the full backend sweep**

```powershell
python -m pytest tests/integration/test_reporting_ai_routes.py -q
python -m pytest tests/unit tests/integration -q
```
Expected: all PASS (`test_translations.py` does not fail yet — no template msgids added so far).

- [ ] **Step 5: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add nx_lib/views/reporting.py tests/integration/test_reporting_ai_routes.py
git commit -m "feat(reporting): agent surface clarifies and answers in user language" -m "When the loop produced no artifact, the agent's final answer is checked for a strict-JSON clarify object (surfaced as an additive clarify key, answer blanked so raw JSON never renders as prose); with an artifact present the artifact wins. Grounding appends a user-language directive after the catalog so the today's-date pin survives."
```

---

# PHASE 3 — Frontend: shared chips module + both panes wired

**Gate before starting:** check `git log feature/2.5.63 --oneline -10` — if drill-through Tasks 2–8 have merged, rebase this branch and re-verify every quoted snippet below against the post-merge files before editing. Restart the dev server after every template edit before manual checks (Jinja caches templates for the process lifetime); the pytest e2e fixture spawns its own server.

### Task 8: `ReportingFollowups` shared partial + mount markup + CSS

**Files:**
- Create: `templates/js/_reporting_followups_js.html`
- Modify: `templates/reporting.html` (include + Advanced mounts), `templates/_reporting_simple.html` (Simple mounts), `static/css/reporting.css`
- Test: `tests/e2e/test_reporting_simple.py` (pure-function tests via `page.evaluate`)

- [ ] **Step 1: Write the failing e2e tests.** Append to `tests/e2e/test_reporting_simple.py`:

```python
def test_followups_clarify_renderer_is_xss_safe(nexora_server, page):
    """ReportingFollowups.renderClarify builds DOM via textContent — model text
    can never reach innerHTML — and renders one pill per choice plus the
    'None of these' escape pill."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    out = page.evaluate(
        """() => {
          const d = document.createElement('div');
          d.hidden = true;
          const ok = window.ReportingFollowups.renderClarify(d,
            {question: 'Which date?',
             choices: ['imported <b>docs</b>', 'exported docs']},
            () => {}, () => {});
          return {ok: ok, hidden: d.hidden, html: d.innerHTML,
                  chips: d.querySelectorAll('[data-testid="ai-clarify-choice"]').length,
                  nones: d.querySelectorAll('[data-testid="ai-clarify-none"]').length};
        }"""
    )
    assert out["ok"] is True and out["hidden"] is False
    assert out["chips"] == 2 and out["nones"] == 1
    assert "<b>" not in out["html"]
    assert "imported &lt;b&gt;docs&lt;/b&gt;" in out["html"]


def test_followups_reject_malformed_and_render_suggestions(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    out = page.evaluate(
        """() => {
          const bad = document.createElement('div');
          const badOk = window.ReportingFollowups.renderClarify(bad, {question: 'q'}, () => {}, () => {});
          const s = document.createElement('div');
          let picked = null;
          window.ReportingFollowups.renderSuggestions(s,
            [{label: 'Per week', ask: 'docs per week'}, {nope: 1}],
            (ask) => { picked = ask; });
          s.querySelector('[data-testid="ai-suggest-chip"]').click();
          return {badOk: badOk, badHidden: bad.hidden,
                  chips: s.querySelectorAll('[data-testid="ai-suggest-chip"]').length,
                  picked: picked};
        }"""
    )
    assert out["badOk"] is False and out["badHidden"] is True
    assert out["chips"] == 1
    assert out["picked"] == "docs per week"
```

- [ ] **Step 2: Run them, watch them fail**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_simple.py -k "followups" -v
```
Expected: FAIL — `window.ReportingFollowups is undefined` (evaluate error). If the server fixture fails to bind, kill stale port-8765 listeners first (command in Context).

- [ ] **Step 3: Create `templates/js/_reporting_followups_js.html`** (one new file, one Write):

```html
<script>
/* Shared AI follow-up UI: "did you mean…?" clarify choices and tweak-suggestion
   chips, used by the Simple pane and the Advanced AI panel. Pure DOM factories —
   model text only ever flows through textContent, never innerHTML (XSS). The
   pills reuse the wizard's .reporting-simple-choice styling. Exposed on window
   so page.evaluate e2e tests can reach the pure functions. */
window.ReportingFollowups = (function () {
  'use strict';
  var I18N = {
    noneOfThese: {{ _("None of these — ask differently")|tojson }},
    tryTweak: {{ _("Try a tweak:")|tojson }}
  };

  function pill(label, onpick, testid) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'reporting-simple-choice';
    b.setAttribute('data-testid', testid);
    b.textContent = label;
    b.addEventListener('click', onpick);
    return b;
  }

  function clear(container) {
    if (!container) return;
    container.innerHTML = '';
    container.hidden = true;
  }

  /* clarify: {question, choices[]} from an AI response. onPick(choiceText)
     re-asks with the chosen meaning (one stateless round — the server keeps
     nothing). onNone() is the escape hatch behind the "None of these" pill
     (owner: clarify must never trap the user). Returns false (and renders
     nothing) for malformed objects, so callers fall back to their normal
     error path. */
  function renderClarify(container, clarify, onPick, onNone) {
    if (!container) return false;
    clear(container);
    if (!clarify || typeof clarify.question !== 'string' || !clarify.question ||
        !Array.isArray(clarify.choices)) return false;
    var choices = clarify.choices.filter(function (c) {
      return typeof c === 'string' && c;
    }).slice(0, 4);
    if (choices.length < 2) return false;
    var q = document.createElement('p');
    q.className = 'reporting-ai-clarify-q';
    q.setAttribute('data-testid', 'ai-clarify-question');
    q.textContent = clarify.question;
    container.appendChild(q);
    var list = document.createElement('div');
    list.className = 'reporting-simple-choices';
    choices.forEach(function (c) {
      list.appendChild(pill(c, function () { onPick(c); }, 'ai-clarify-choice'));
    });
    var none = pill(I18N.noneOfThese, function () {
      clear(container);
      if (onNone) onNone();
    }, 'ai-clarify-none');
    none.classList.add('reporting-ai-clarify-none');
    list.appendChild(none);
    container.appendChild(list);
    container.hidden = false;
    return true;
  }

  /* suggestions: [{label, ask}] (already catalog-validated server-side).
     onPick(askText) re-asks with the tweak folded in. */
  function renderSuggestions(container, suggestions, onPick) {
    if (!container) return false;
    clear(container);
    if (!Array.isArray(suggestions)) return false;
    var shown = 0;
    var head = document.createElement('span');
    head.className = 'reporting-ai-suggest-head';
    head.textContent = I18N.tryTweak;
    container.appendChild(head);
    suggestions.slice(0, 3).forEach(function (s) {
      if (!s || typeof s.label !== 'string' || !s.label ||
          typeof s.ask !== 'string' || !s.ask) return;
      var b = pill(s.label, function () { onPick(s.ask); }, 'ai-suggest-chip');
      b.classList.add('reporting-ai-suggest-chip');
      container.appendChild(b);
      shown++;
    });
    if (!shown) { clear(container); return false; }
    container.hidden = false;
    return true;
  }

  return { renderClarify: renderClarify, renderSuggestions: renderSuggestions, clear: clear };
})();
</script>
```

- [ ] **Step 4: Include the partial.** In `templates/reporting.html`, find:

```jinja
    {% include 'js/_reporting_sqlformat_js.html' %}
    {% include '_reporting_simple.html' %}
```

  replace with:

```jinja
    {% include 'js/_reporting_sqlformat_js.html' %}
    {% include 'js/_reporting_followups_js.html' %}
    {% include '_reporting_simple.html' %}
```

- [ ] **Step 5: Mount divs.** (a) In `templates/_reporting_simple.html`, find:

```html
    <div id="rsRunLoading" class="reporting-ai-loading" hidden data-testid="rs-run-loading">
      <span class="reporting-ai-dots" aria-hidden="true"><i></i><i></i><i></i></span>
      <span role="status">{{ _("Running your report…") }}</span>
    </div>
    <p id="rsMsg" class="reporting-ai-explain" hidden data-testid="rs-msg"></p>
    <div id="rsChips" class="reporting-simple-chips" hidden data-testid="rs-chips"></div>
```

  replace with:

```html
    <div id="rsRunLoading" class="reporting-ai-loading" hidden data-testid="rs-run-loading">
      <span class="reporting-ai-dots" aria-hidden="true"><i></i><i></i><i></i></span>
      <span role="status">{{ _("Running your report…") }}</span>
    </div>
    <div id="rsClarify" class="reporting-ai-clarify" hidden data-testid="rs-clarify"></div>
    <p id="rsMsg" class="reporting-ai-explain" hidden data-testid="rs-msg"></p>
    <div id="rsChips" class="reporting-simple-chips" hidden data-testid="rs-chips"></div>
    <div id="rsSuggest" class="reporting-ai-suggest" hidden data-testid="rs-suggest"></div>
```

  (b) In `templates/reporting.html`, inside `rpAiPanel`, find:

```html
        <div id="rpAiLoading" class="reporting-ai-loading" hidden data-testid="reporting-ai-loading">
          <span class="reporting-ai-dots" aria-hidden="true"><i></i><i></i><i></i></span>
          <span id="rpAiLoadingText" role="status"></span>
        </div>
```

  and add directly below it:

```html
        <div id="rpAiClarify" class="reporting-ai-clarify" hidden data-testid="reporting-ai-clarify"></div>
```

  (c) Still in `templates/reporting.html`, inside `rpAiDefResult`, find:

```html
          <div class="reporting-ai-actions">
            <button id="rpAiOpenBuilder" class="reporting-btn" data-testid="reporting-ai-open-builder">{{ _("Open in builder") }}</button>
            <button id="rpAiMakeChart" class="reporting-btn" hidden data-testid="reporting-ai-make-chart">{{ _("Make a chart") }}</button>
          </div>
```

  and add directly below it (still inside the `rpAiDefResult` div):

```html
          <div id="rpAiSuggest" class="reporting-ai-suggest" hidden data-testid="reporting-ai-suggest"></div>
```

- [ ] **Step 6: CSS.** Append at the end of `static/css/reporting.css`:

```css
/* AI follow-ups: clarify choices + tweak-suggestion chips (both tabs). The
   pills themselves reuse .reporting-simple-choice / .reporting-simple-choices. */
.reporting-ai-clarify { margin: .4rem 0 .6rem; }
.reporting-ai-clarify-q { font-weight: 600; margin: 0 0 .5rem; }
.reporting-ai-clarify-none { border-style: dashed; color: #6b7280; }
.reporting-ai-suggest { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem; margin: .3rem 0 .6rem; }
.reporting-ai-suggest-head { font-size: 12px; font-weight: 600; color: #6b7280; }
```

- [ ] **Step 7: Run green**

```powershell
python -m pytest tests/e2e/test_reporting_simple.py -k "followups" -v
```
Expected: 2 passed.

- [ ] **Step 8: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add templates/js/_reporting_followups_js.html templates/reporting.html templates/_reporting_simple.html static/css/reporting.css tests/e2e/test_reporting_simple.py
git commit -m "feat(reporting): shared clarify/suggestion chip renderer" -m "window.ReportingFollowups: XSS-safe pill factories for the did-you-mean round (incl. a None-of-these escape pill) and tweak chips, mount divs on both tabs (rsClarify/rsSuggest, rpAiClarify/rpAiSuggest), pills reuse the wizard choice styling. Pure functions pinned by page.evaluate e2e tests."
```

---

### Task 9: Simple pane — clarify round + tweak chips wired into `askAi`/`runCurrent`

**Files:**
- Modify: `templates/js/_reporting_simple_js.html`
- Test: `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Write the failing clarify e2e test.** Append to `tests/e2e/test_reporting_simple.py`:

```python
def test_ai_clarify_choice_reasks(nexora_server, page):
    """An ambiguous ask renders the clarify question + choice pills instead of
    a result; clicking a pill re-asks automatically with that meaning as the
    question (one stateless round, no thread)."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    seen = []

    def handler(route):
        seen.append(route.request.post_data_json)
        if len(seen) == 1:
            body = json.dumps({
                "definition": None, "explanation": "", "valid": False, "error": None,
                "clarify": {"question": "Which date do you mean?",
                            "choices": ["documents imported last month",
                                        "documents exported last month"]},
            })
        else:
            body = json.dumps({"definition": STUB_AI_DEFINITION,
                               "explanation": "stubbed explanation",
                               "valid": True, "error": None})
        route.fulfill(status=200, content_type="application/json", body=body)

    page.route("**/api/reporting/ai/build", handler)
    page.get_by_test_id("rs-ai-prompt").fill("documents last month")
    page.get_by_test_id("rs-ai-ask").click()

    clarify = page.get_by_test_id("rs-clarify")
    expect(clarify).to_be_visible()
    expect(clarify).to_contain_text("Which date do you mean?")
    chips = clarify.get_by_test_id("ai-clarify-choice")
    expect(chips).to_have_count(2)
    expect(clarify.get_by_test_id("ai-clarify-none")).to_be_visible()
    expect(page.get_by_test_id("rs-error")).to_be_hidden()
    page.screenshot(path="var/screenshots/reporting_simple_clarify.png")

    chips.first.click()
    expect(page.get_by_test_id("rs-msg")).to_contain_text("stubbed explanation")
    expect(page.get_by_test_id("rs-clarify")).to_be_hidden()
    assert seen[1]["question"] == "documents imported last month"
    assert seen[1].get("priorQuestion") is None  # fresh ask carried no refine context
```

- [ ] **Step 2: Write the failing tweak-chip e2e test.** Append:

```python
def test_ai_suggestion_chip_refines_the_draft(nexora_server, page):
    """Tweak chips render under an AI-drafted result; a click re-asks with the
    suggestion's machine-usable ask, threaded as a refine of the draft."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    seen = []

    def handler(route):
        seen.append(route.request.post_data_json)
        body = json.dumps({
            "definition": STUB_AI_DEFINITION if len(seen) == 1
            else dict(STUB_AI_DEFINITION, title="weekly report"),
            "explanation": "stubbed explanation", "valid": True, "error": None,
            "suggestions": [{"label": "Show this per week",
                             "ask": "docs by process per week"}],
        })
        route.fulfill(status=200, content_type="application/json", body=body)

    page.route("**/api/reporting/ai/build", handler)
    page.get_by_test_id("rs-ai-prompt").fill("docs by process")
    page.get_by_test_id("rs-ai-ask").click()

    sugg = page.get_by_test_id("rs-suggest")
    expect(sugg).to_be_visible()
    chip = sugg.get_by_test_id("ai-suggest-chip")
    expect(chip).to_have_count(1)
    expect(chip.first).to_contain_text("Show this per week")
    page.screenshot(path="var/screenshots/reporting_simple_tweak_chips.png")

    chip.first.click()
    expect(page.get_by_test_id("rs-result-title")).to_contain_text("weekly report")
    assert seen[1]["question"] == "docs by process per week"
    assert seen[1]["priorQuestion"] == "docs by process"
    assert seen[1]["priorDefinition"]["title"] == "stub ai report"
```

- [ ] **Step 3: Run them, watch them fail**

```powershell
python -m pytest tests/e2e/test_reporting_simple.py -k "clarify_choice or suggestion_chip" -v
```
Expected: FAIL — `rs-clarify` / `rs-suggest` never become visible (a clarify reply currently falls into the `!res.data.valid` error branch).

- [ ] **Step 4: Implement.** In `templates/js/_reporting_simple_js.html`:

  (a) In `showAiLoading`, find:

```js
    el('rsRunLoading').hidden = true;
    var lines = [I18N.aiThinking, I18N.aiDrafting, I18N.aiChecking];
```

  replace with:

```js
    el('rsRunLoading').hidden = true;
    if (window.ReportingFollowups) {
      ReportingFollowups.clear(el('rsClarify'));
      ReportingFollowups.clear(el('rsSuggest'));
    }
    var lines = [I18N.aiThinking, I18N.aiDrafting, I18N.aiChecking];
```

  (b) In `showResultError`, find:

```js
  function showResultError(msg) {
    hideAiLoading();
    el('rsRunLoading').hidden = true;
```

  replace with:

```js
  function showResultError(msg) {
    hideAiLoading();
    el('rsRunLoading').hidden = true;
    if (window.ReportingFollowups) {
      ReportingFollowups.clear(el('rsClarify'));
      ReportingFollowups.clear(el('rsSuggest'));
    }
```

  (c) In `runCurrent`, find:

```js
    renderAiChips(cur);
    var refineBar = el('rsRefineBar');
```

  replace with:

```js
    renderAiChips(cur);
    if (window.ReportingFollowups) {
      ReportingFollowups.clear(el('rsClarify'));
      // Tweak chips ride AI-drafted results only (owner decision 3):
      // aiSuggestions is set solely by a successful askAi(); wizard/library
      // runs never have it, so they never render chips.
      ReportingFollowups.renderSuggestions(el('rsSuggest'), cur.aiSuggestions || [],
        function (ask) { askAi(ask); });
    }
    var refineBar = el('rsRefineBar');
```

  (d) Add `showClarify` directly ABOVE `async function askAi(refineQuestion) {`:

```js
  // One stateless clarify round (owner decision 2): show the model's question
  // + 2-4 readings as pills; a click re-asks with that meaning folded in. A
  // clarified refine keeps its prior context; a still-unclear follow-up just
  // clarifies again — nothing is stored anywhere. The "None of these" escape
  // pill hands focus back to the prompt (library view for fresh asks).
  function showClarify(clarify, fromRefine, prior) {
    setView('result');
    el('rsResultTitle').textContent = '';
    el('rsError').hidden = true;
    el('rsMsg').hidden = true;
    el('rsChips').hidden = true;
    var isRefine = !!(fromRefine && prior && prior.def);
    if (el('rsRefineBar')) el('rsRefineBar').hidden = !isRefine;
    var ok = window.ReportingFollowups && ReportingFollowups.renderClarify(
      el('rsClarify'), clarify,
      function (choice) {
        ReportingFollowups.clear(el('rsClarify'));
        if (isRefine) {
          askAi(choice);                    // same refine context as the clarified ask
        } else {
          el('rsAiPrompt').value = choice;  // fresh ask: fold the meaning into the prompt
          askAi();
        }
      },
      function () {                          // "None of these" escape
        if (isRefine) { el('rsRefineInput').focus(); return; }
        setView('library');
        el('rsAiPrompt').focus();
      });
    if (!ok) showResultError(I18N.aiInvalid);
  }
```

  (e) In `askAi`, find the failure-branch opener:

```js
    if (res.status === 429) { showResultError(I18N.aiLimit); return; }
    if (!res.ok || !res.data || !res.data.valid || !res.data.definition) {
```

  replace with:

```js
    if (res.status === 429) { showResultError(I18N.aiLimit); return; }
    if (res.ok && res.data && res.data.clarify) {
      // Must run BEFORE the validity check: a clarify reply is definition-less
      // with valid:false by design, not a failure.
      showClarify(res.data.clarify, fromRefine, prior);
      return;
    }
    if (!res.ok || !res.data || !res.data.valid || !res.data.definition) {
```

  (f) Still in `askAi`, find the success assignment:

```js
    state.current = { def: res.data.definition, name: res.data.definition.title,
                      reportId: null, owned: true, canEdit: true, fromWizard: true,
                      aiExplanation: res.data.explanation || '',
                      aiQuestion: q };
```

  replace with:

```js
    state.current = { def: res.data.definition, name: res.data.definition.title,
                      reportId: null, owned: true, canEdit: true, fromWizard: true,
                      aiExplanation: res.data.explanation || '',
                      aiQuestion: q,
                      aiSuggestions: res.data.suggestions || [] };
```

- [ ] **Step 5: Run green (new tests + the AI regression set)**

```powershell
python -m pytest tests/e2e/test_reporting_simple.py -k "clarify_choice or suggestion_chip or ai_ask_shows_loading or refine_sends_prior or chips_edit or wizard_result_shows" -v
```
Expected: all PASS — the MutationObserver loading-latch, refine round-trip and chip e2e are the regression constraints for this file (a clarify response terminates the loading state; wizard results show no tweak chips).

- [ ] **Step 6: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -m "feat(reporting): Simple-tab clarify round and tweak chips" -m "askAi handles the additive clarify key before the validity check (a clarify reply is definition-less by design): renders the question + choice pills + a None-of-these escape, a click re-asks statelessly with the chosen meaning, preserving refine context. Valid drafts carry aiSuggestions rendered as tweak chips under the result; a chip click is a refine re-ask. Stale chips cleared on every ask, error and run."
```

---

### Task 10: Advanced AI panel — clarify on Build/Write-SQL/Agent + tweak chips on Build

**Files:**
- Modify: `templates/js/_reporting_ai_js.html` (vars, `setSurface`, full rewrites of `askBuild`/`askSql`/`askAgent`)
- Test: `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Write the failing Build-surface e2e test.** Append to `tests/e2e/test_reporting_simple.py`:

```python
def test_advanced_ai_build_clarify_and_suggestions(nexora_server, page):
    """Advanced Build surface: a clarify response renders choice pills (no def
    result); the pick re-asks; the resulting draft shows tweak chips whose
    click re-asks with refine context."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.get_by_test_id("reporting-mode-ai").click()
    seen = []

    def handler(route):
        seen.append(route.request.post_data_json)
        if len(seen) == 1:
            body = json.dumps({
                "definition": None, "explanation": "", "valid": False, "error": None,
                "clarify": {"question": "Which date do you mean?",
                            "choices": ["imported docs per month",
                                        "exported docs per month"]},
            })
        else:
            body = json.dumps({
                "definition": STUB_AI_DEFINITION, "explanation": "stubbed explanation",
                "valid": True, "error": None,
                "suggestions": [{"label": "Per week instead", "ask": "docs per week"}],
            })
        route.fulfill(status=200, content_type="application/json", body=body)

    page.route("**/api/reporting/ai/build", handler)
    page.get_by_test_id("reporting-ai-prompt").fill("docs per month")
    page.get_by_test_id("reporting-ai-ask").click()

    clarify = page.get_by_test_id("reporting-ai-clarify")
    expect(clarify).to_be_visible()
    expect(page.get_by_test_id("reporting-ai-def-result")).to_be_hidden()
    page.screenshot(path="var/screenshots/reporting_advanced_clarify.png")
    clarify.get_by_test_id("ai-clarify-choice").first.click()

    expect(page.get_by_test_id("reporting-ai-def-result")).to_be_visible()
    expect(clarify).to_be_hidden()
    assert seen[1]["question"] == "imported docs per month"

    sugg = page.get_by_test_id("reporting-ai-suggest")
    expect(sugg).to_be_visible()
    page.screenshot(path="var/screenshots/reporting_advanced_tweak_chips.png")
    sugg.get_by_test_id("ai-suggest-chip").first.click()
    expect(page.get_by_test_id("reporting-ai-def-summary")).to_contain_text("stub ai report")
    assert seen[2]["question"] == "docs per week"
    assert seen[2]["priorQuestion"] == "imported docs per month"
    assert seen[2]["priorDefinition"]["title"] == "stub ai report"
```

- [ ] **Step 2: Write the failing Agent-surface e2e test.** Append:

```python
def test_advanced_agent_clarify_choice_reasks(nexora_server, page):
    """Agent surface clarify: pills render instead of a thread turn; the pick
    re-asks; the clarify round never enters the client-side thread."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.get_by_test_id("reporting-mode-ai").click()
    page.get_by_test_id("reporting-ai-mode-agent").click()
    seen = []

    def handler(route):
        seen.append(route.request.post_data_json)
        if len(seen) == 1:
            body = json.dumps({
                "answer": "", "definition": None, "sql": None, "toolTrace": [],
                "turns": 1, "stoppedReason": "final", "explainData": False,
                "clarify": {"question": "Which process?",
                            "choices": ["the Privera invoice process", "all processes"]},
            })
        else:
            body = json.dumps({
                "answer": "42 documents.", "definition": None, "sql": None,
                "toolTrace": [], "turns": 1, "stoppedReason": "final",
                "explainData": False,
            })
        route.fulfill(status=200, content_type="application/json", body=body)

    page.route("**/api/reporting/ai/agent", handler)
    page.get_by_test_id("reporting-ai-prompt").fill("how many docs?")
    page.get_by_test_id("reporting-ai-ask").click()

    clarify = page.get_by_test_id("reporting-ai-clarify")
    expect(clarify).to_be_visible()
    expect(page.get_by_test_id("reporting-ai-agent-result")).to_be_hidden()
    clarify.get_by_test_id("ai-clarify-choice").first.click()

    expect(page.get_by_test_id("reporting-ai-agent-thread")).to_contain_text("42 documents.")
    expect(clarify).to_be_hidden()
    # Stateless: the clarify round produced no thread turn, so the re-ask
    # carries no "(Continuing our conversation...)" prefix.
    assert seen[1]["question"] == "the Privera invoice process"
```

- [ ] **Step 3: Run them, watch them fail**

```powershell
python -m pytest tests/e2e/test_reporting_simple.py -k "advanced_ai_build_clarify or advanced_agent_clarify" -v
```
Expected: FAIL — `reporting-ai-clarify` never becomes visible.

- [ ] **Step 4: Implement.** In `templates/js/_reporting_ai_js.html`:

  (a) New element refs + state — find:

```js
  var aiSurface = "build";                                          // "build" | "sql" | "agent"
  var lastDef = null;
```

  replace with:

```js
  var aiSurface = "build";                                          // "build" | "sql" | "agent"
  var lastDef = null;
  var lastBuildQuestion = "";
  // Follow-up containers (clarify shared by all three surfaces; suggestions
  // live inside the Build def-result block).
  var clarifyEl = document.getElementById("rpAiClarify");
  var suggestEl = document.getElementById("rpAiSuggest");
```

  (b) Clear on surface switch — in `setSurface`, find:

```js
    if (errorEl) errorEl.hidden = true;
```

  replace with:

```js
    if (errorEl) errorEl.hidden = true;
    if (window.ReportingFollowups) {
      ReportingFollowups.clear(clarifyEl);
      ReportingFollowups.clear(suggestEl);
    }
```

  (c) Replace `askBuild` wholesale (the three ask functions share non-unique then/catch snippets — same reason the loading-states plan replaced them wholesale; find `function askBuild(question) {` and replace the whole function through its closing `  }`):

```js
  function askBuild(question, priorQuestion, priorDefinition) {
    askBtn.disabled = true;
    errorEl.hidden = true;
    if (window.ReportingFollowups) ReportingFollowups.clear(clarifyEl);
    showAiLoading(AI_LINES);
    var body = { question: question };
    if (priorQuestion && priorDefinition) {
      // A tweak-chip click is a refine of the previous draft — same optional
      // fields the Simple tab's refine sends; the server validates the result
      // against the catalog either way.
      body.priorQuestion = priorQuestion;
      body.priorDefinition = priorDefinition;
    }
    fetch("/api/reporting/ai/build", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().then(function (data) { return { ok: r.ok, data: data }; });
    }).then(function (res) {
      askBtn.disabled = false;
      hideAiLoading();
      if (!res.ok) {
        errorEl.textContent = (res.data && res.data.error) || '{{ _("Error") }}';
        errorEl.hidden = false; defResult.hidden = true; return;
      }
      if (res.data.clarify && window.ReportingFollowups &&
          ReportingFollowups.renderClarify(clarifyEl, res.data.clarify, function (choice) {
            promptEl.value = choice;
            askBuild(choice);
          }, function () { promptEl.focus(); })) {
        defResult.hidden = true;
        return;
      }
      lastDef = res.data.definition;
      lastBuildQuestion = question;
      defSummary.textContent = lastDef ? summarize(lastDef) : (res.data.explanation || "");
      defInvalid.hidden = res.data.valid !== false;
      openBuilderBtn.disabled = !lastDef || res.data.valid === false;
      defResult.hidden = false;
      if (makeChartBtn) makeChartBtn.hidden = !(lastDef && lastDef.chartHint && res.data.valid !== false);
      if (window.ReportingFollowups) {
        ReportingFollowups.renderSuggestions(suggestEl, res.data.suggestions || [], function (ask) {
          promptEl.value = ask;
          askBuild(ask, lastBuildQuestion, lastDef);
        });
      }
    }).catch(function () {
      askBtn.disabled = false;
      hideAiLoading();
      errorEl.textContent = '{{ _("Network error") }}'; errorEl.hidden = false;
    });
  }
```

  (d) Replace `askSql` wholesale:

```js
  function askSql(question) {
    askBtn.disabled = true;
    errorEl.hidden = true;
    if (window.ReportingFollowups) ReportingFollowups.clear(clarifyEl);
    showAiLoading(AI_LINES);
    fetch("/api/reporting/ai/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify({ question: question })
    }).then(function (r) {
      return r.json().then(function (data) { return { ok: r.ok, status: r.status, data: data }; });
    }).then(function (res) {
      askBtn.disabled = false;
      hideAiLoading();
      if (!res.ok) {
        errorEl.textContent = (res.data && res.data.error) || '{{ _("Error") }}';
        errorEl.hidden = false;
        resultEl.hidden = true;
        return;
      }
      if (res.data.clarify && window.ReportingFollowups &&
          ReportingFollowups.renderClarify(clarifyEl, res.data.clarify, function (choice) {
            promptEl.value = choice;
            askSql(choice);
          }, function () { promptEl.focus(); })) {
        resultEl.hidden = true;
        return;
      }
      lastSql = res.data.sql || "";
      ReportingSqlFormat.render(sqlEl, lastSql);
      explainEl.textContent = res.data.explanation || "";
      invalidEl.hidden = res.data.valid !== false;
      resultEl.hidden = false;
    }).catch(function () {
      askBtn.disabled = false;
      hideAiLoading();
      errorEl.textContent = '{{ _("Network error") }}';
      errorEl.hidden = false;
    });
  }
```

  (e) Replace `askAgent` wholesale:

```js
  function askAgent(question) {
    askBtn.disabled = true;
    errorEl.hidden = true;
    if (window.ReportingFollowups) ReportingFollowups.clear(clarifyEl);
    showAiLoading(AGENT_LINES);
    fetch("/api/reporting/ai/agent", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify({
        question: agentContext() + question,
        // Active source lets the server gate run_sql to sources it can reach.
        source: (document.getElementById("rpSource") || {}).value || null
      })
    }).then(function (r) {
      return r.json().then(function (data) { return { ok: r.ok, data: data }; });
    }).then(function (res) {
      askBtn.disabled = false;
      hideAiLoading();
      if (!res.ok) {
        errorEl.textContent = (res.data && res.data.error) || '{{ _("Error") }}';
        errorEl.hidden = false; agentResult.hidden = true; return;
      }
      if (res.data.clarify && window.ReportingFollowups &&
          ReportingFollowups.renderClarify(clarifyEl, res.data.clarify, function (choice) {
            promptEl.value = choice;
            askAgent(choice);
          }, function () { promptEl.focus(); })) {
        // A clarify is not an answer — keep it off the thread (stateless
        // round; the next ask carries no bogus "previous answer").
        return;
      }
      var d = res.data;
      agentThread.push({ q: question, a: d.answer || "" });
      renderAgentThread();
      renderAgentTrace(d.toolTrace, d.turns);
      lastAgentDef = d.definition || null;
      lastAgentSql = d.sql || "";
      if (agentOpenBuilderBtn) agentOpenBuilderBtn.hidden = !lastAgentDef;
      if (agentInsertSqlBtn) agentInsertSqlBtn.hidden = !(lastAgentSql && sqlEditor);
      if (agentInvalid)
        agentInvalid.hidden = !!(d.answer && (lastAgentDef || lastAgentSql));
      agentResult.hidden = false;
      promptEl.value = "";
      askBtn.textContent = '{{ _("Ask follow-up") }}';
    }).catch(function () {
      askBtn.disabled = false;
      hideAiLoading();
      errorEl.textContent = '{{ _("Network error") }}'; errorEl.hidden = false;
    });
  }
```

- [ ] **Step 5: Run green (new tests + the Advanced loading regression)**

```powershell
python -m pytest tests/e2e/test_reporting_simple.py -k "advanced" -v
```
Expected: all PASS — incl. the pre-existing `test_advanced_ai_ask_shows_loading` (clarify renders only after `hideAiLoading()`).

- [ ] **Step 6: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add templates/js/_reporting_ai_js.html tests/e2e/test_reporting_simple.py
git commit -m "feat(reporting): Advanced AI panel clarify round and tweak chips" -m "All three surfaces render the additive clarify key as choice pills in a shared rpAiClarify container; a pick re-asks the same surface statelessly (agent clarifies never enter the thread) and a None-of-these escape returns focus to the prompt. Build drafts show catalog-validated tweak chips that re-ask with priorQuestion/priorDefinition refine context."
```

---

# PHASE 4 — i18n, docs, full verification

### Task 11: i18n cycle (two new msgids)

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`)

New msgids introduced by this plan (everything else is AI-emitted text localized by the prompt directive, or reuses existing translations); both live in `templates/js/_reporting_followups_js.html` (babel.cfg extracts `[jinja2: **/templates/**.html]`):

1. `None of these — ask differently` (clarify escape pill)
2. `Try a tweak:` (suggestion header)

**Rebase first** if drill-through's i18n task has merged since Phase 3 started — running pybabel on a stale base creates avoidable `.po` conflicts. This task runs LAST among code tasks for exactly that reason.

- [ ] **Step 1: Extract + update**

```powershell
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
```
Expected: `messages.pot` gains exactly the two msgids above.

- [ ] **Step 2: Translate both msgids** in `translations/{de,fr,it}/LC_MESSAGES/messages.po` (sweep `git diff translations` for `#, fuzzy` markers pybabel introduced near similar strings — resolve and remove the fuzzy flag):

| msgid | de | fr | it |
|---|---|---|---|
| None of these — ask differently | Nichts davon — anders fragen | Aucune de ces options — reformulez la question | Nessuna di queste — riformula la domanda |
| Try a tweak: | Etwas anpassen: | Essayer une variante : | Prova una variante: |

- [ ] **Step 3: Compile + verify**

```powershell
pybabel compile -d translations
python -m pytest tests/unit/test_translations.py -v
```
Expected: all PASS (pot in sync, de/fr/it complete and non-fuzzy).

- [ ] **Step 4: Commit**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add messages.pot translations
git commit -m "chore(i18n): translate AI clarify/tweak chip strings (de/fr/it)" -m "Two new msgids from the shared follow-ups partial: the None-of-these escape pill and the tweak-chip header. AI-emitted text (questions, choices, labels) is localized by the new prompt language directive, not by gettext."
```

---

### Task 12: Docs, changelog, full verification

**Files:**
- Modify: `docs/howto/reporting.md`, `docs/design/reporting-ai-assistant.md`, `CHANGELOG.md`

- [ ] **Step 1: Howto — new subsection.** In `docs/howto/reporting.md`, insert directly BEFORE the line `### Write SQL (Phase 1 — Surface B)` (i.e. at the end of the `### AI refine (Simple tab)` section):

```markdown
### Clarify round & tweak chips (all AI surfaces)

The assistant is tuned for people who are not data people: it maps everyday
wording ("split up by", "for each", "how many") onto the right definition,
keeps its explanations jargon-free, and answers in your UI language (en/de/fr/it).

When a question is genuinely ambiguous, the AI does not guess. The response
carries an optional `clarify` object — one short plain-language question plus
2–4 clickable "did you mean…?" choices and a "None of these — ask differently"
escape chip. Clicking a choice re-asks automatically with that meaning as the
question. The round is **stateless**: nothing is stored server-side, there is
no chat thread, and a still-unclear follow-up simply clarifies again. Clarify
replies are audited (`GateVerdict='clarify'`) and count toward the daily AI
cap like any other provider call. This works on the Simple Ask-AI card and
refine bar, and on all three Advanced surfaces (Build, Write SQL, Agent — the
agent clarifies without calling tools).

After a **valid AI-drafted report** (Simple ask/refine and Advanced Build),
the response may also carry up to 3 `suggestions` — tweak chips such as
"Use the import date instead" or "Break this down to weeks". Every suggestion
is validated server-side against the draft's source catalog (a chip can never
name a field or grain the source does not have); clicking one re-asks as a
refine of the current draft. Manual wizard runs never get suggestions — they
ride the AI draft response only.
```

- [ ] **Step 2: Howto — Safety & privacy bullet.** In the `### Safety & privacy` subsection, the list currently ends with the `- **Cost/abuse control:** ...` bullet (before `### Implementation`). Append one bullet after it:

```markdown
- **Clarify rounds & chip clicks:** each is a full provider call — audited in
  `ReportingAiAudit` (`GateVerdict='clarify'` for clarify replies) and counted
  against `AI_DAILY_LIMIT`. Egress stays schema-only: clarify questions and
  tweak suggestions are generated from the user's question and the field
  catalog, never from result rows.
```

- [ ] **Step 3: Design doc.** Append at the end of `docs/design/reporting-ai-assistant.md`:

```markdown
## Response-contract extensions: clarify + suggestions (2026-06)

All three AI endpoints gained ADDITIVE optional keys; every pre-existing key
is byte-identical for non-clarify replies, so old clients keep working.

- `POST /api/reporting/ai/build` → `clarify: {question, choices[2..4]}` when
  the model asks back instead of drafting (`definition:null`, `valid:false`,
  `error:null`; the self-repair retry is skipped); `suggestions:
  [{label, ask}]` on valid drafts, whitelisted by
  `ai_followups.validate_suggestions` against the same catalog the draft
  validator uses (shared `_resolve_source_catalog`). The model emits
  `{label, ask, field, grain?, metric?}`; claims are verified, then stripped.
  `max_tokens` is 1536 on this surface (larger strict-JSON reply).
- `POST /api/reporting/ai/ask` → `clarify` (sql empty, valid false,
  `GateVerdict='clarify'` — the sqlglot gate is skipped, there is nothing to
  gate).
- `POST /api/reporting/ai/agent` → when the loop produced no artifact, the
  final answer is parsed for a strict-JSON clarify object
  (`ai_followups.clarify_from_text`); when found, `answer` is blanked and
  `clarify` is attached. With an artifact present the artifact wins.

Language: `ask`/`ask_definition` take `locale=` (en/de/fr/it) and prepend a
user-language directive; the agent grounding appends one (a test pins
`startswith("Today's date")`). A choice/tweak click is a fresh stateless POST
(chip text as `question`; tweak clicks reuse `priorQuestion`/`priorDefinition`),
so rate limits, the daily cap, audit and permissions apply unchanged.
`ai_followups.sanitize_clarify` is the trust boundary: whitelist-strict shape,
2–4 deduped choices, bounded lengths; anything malformed degrades to the
ordinary invalid-draft path. The frontend renders all chips via
`window.ReportingFollowups` (textContent only — model text never reaches
innerHTML).
```

- [ ] **Step 4: Changelog.** In `CHANGELOG.md` under `## [Unreleased]` → `### Added`, append:

```markdown
- Reporting AI: plain-language understanding across all surfaces — stakeholder wording ("split up by", "how many") maps onto correct drafts, explanations stay jargon-free, and AI answers come back in the user's language (de/fr/it/en).
- Reporting AI: "did you mean…?" clarify round — an ambiguous ask returns one short question with 2–4 clickable choices plus a "None of these" escape; a click re-asks automatically (stateless, no chat thread). Works on the Simple Ask-AI card/refine and the Advanced Build, Write-SQL and Agent surfaces.
- Reporting AI: tweak-suggestion chips under AI-drafted reports ("Use the import date instead", "Break this down to weeks") — validated against the source catalog server-side; clicking applies the tweak as a refine and re-runs.
```

- [ ] **Step 5: Full test suite**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/unit tests/integration -q
python -m pytest tests/e2e/test_reporting_simple.py tests/e2e/test_reporting.py tests/e2e/test_reporting_sql.py -v
```
Expected: all PASS. If the e2e server fixture fails to bind, kill stale port-8765 listeners first: `Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | % { Stop-Process -Id $_.OwningProcess -Force }`.

- [ ] **Step 6: Screenshots (remote session: SendUserFile without being asked).** The e2e run in Step 5 reproduced the four review artifacts via the scripted `page.screenshot(...)` calls baked into the tests (Tasks 9–10) — send all four:
  - `var/screenshots/reporting_simple_clarify.png`
  - `var/screenshots/reporting_simple_tweak_chips.png`
  - `var/screenshots/reporting_advanced_clarify.png`
  - `var/screenshots/reporting_advanced_tweak_chips.png`

  Live-model behavior (does gpt-4o-mini actually emit good clarifies/suggestions in German?) cannot be verified in TEST (`AI_PROVIDER=none`; e2e stubs the route) — that is the owner's INT spot-check (Owner actions #3). For an optional manual layout pass, restart the dev server first (`nx -u -b --loginas:<admin user>`) — Jinja caches templates for the process lifetime.

- [ ] **Step 7: Commit & STOP**

```powershell
$env:SQL_SYNC_SKIP = "1"
git add docs/howto/reporting.md docs/design/reporting-ai-assistant.md CHANGELOG.md
git commit -m "docs(reporting): clarify round, tweak chips and AI language" -m "Howto gains the clarify/tweak-chip subsection plus a Safety & privacy bullet (clarify calls are audited and quota-counted; egress stays schema-only); design doc records the additive response-contract extensions and the sanitize_clarify trust boundary; changelog entries under [Unreleased] Added."
```

  **STOP at commit.** Do not push, do not open a PR (remote-session policy — the owner reviews locally; the pre-push hook runs the full suite then). Note in the handoff that the drill-through executor (Tasks 2–8) must re-verify its quoted anchors against this plan's edits to `askAi`, `runCurrent`, `showAiLoading`, `showResultError`, `askBuild`/`askSql`/`askAgent`, `setSurface`, `_reporting_simple.html`, `reporting.html` and `reporting.css`.

---

## Gotchas & notes

- **Clarify branch order in `askAi` matters:** the existing failure check `!res.data.valid || !res.data.definition` would swallow every clarify reply (they are definition-less with `valid:false`) — the clarify check must run first, and `error` is `null` on clarify so the "(why)" suffix logic never fires.
- **The Surface-A self-repair retry must NOT fire on clarify** — `_validate_definition_for_user(None)` returns "definition must be an object", which would re-prompt the model with "your attempt was REJECTED" about a question it asked. The `break` before validation (Task 5) is load-bearing.
- **Artifact wins over clarify everywhere (Decision 9):** `ask()` checks `not obj.get("sql")` before honoring clarify; `api_ai_build` re-gates with `clarify if (clarify and definition is None) else None`; `api_ai_agent` only parses the answer when `not definition and not sql` — a model that builds an artifact AND emits clarify JSON keeps its artifact, pinned by `test_ai_agent_artifact_wins_over_clarify_text`.
- **The byte-identical `api_version=.../url=.../)` call tail exists TWICE** in `views/reporting.py`: in `api_ai_ask` (the `result = ai_ask(` call) and in `api_ai_agent` (the `step = make_agent_step(` call). Task 6's anchor is extended through the `/api/reporting/ai/ask config error` log line to be unique. Never add `locale=` to `make_agent_step` — it has no such kwarg; the agent's language directive lives in the grounding (Task 7).
- **Prompt-pin locations:** the `"2 failed"` / `"ok:true"` `_AGENT_SYSTEM` pins live in `tests/unit/test_reporting_ai_definition.py`; the grain/distinct/quarter/processing-date/token pins live in `tests/unit/test_reporting_ai_agentic.py`. Task 3 runs both files; never reword existing prompt fragments while appending. New pins added by this plan: `'"clarify"'`, `"do NOT guess"`, `"2-4 choices"`, `"complete, self-contained rephrasing"`, `"free of jargon"`, `"Never suggest a field or grain the source does not list"`, `"do not call tools"`, `"business audience"`, and the ABSENCE of `"Do not ask the user questions."`.
- **`test_ai_agent_grounding_states_todays_date` pins `initial.startswith("Today's date is ...")`** — the agent language directive is appended after the catalog, never prepended.
- **`ai_followups` must never import `.ai`** — `ai.py` imports `sanitize_clarify` from it; a back-import is a cycle. `clarify_from_text` carries its own fence regex for exactly this reason. `schema.py` (source of `GRAINS`) imports only `.tokens` — no cycle there either.
- **`_resolve_source_catalog` raises where the old code returned** — the messages ("unknown or unsupported source", "not authorized for this source") are preserved verbatim so `_validate_definition_for_user`'s `except (ReportDefinitionError, PermissionError)` tail returns identical strings and no integration test churns.
- **Suggestions without a `field` claim are dropped by design** (Decision 5) — that is the enforcement mechanism for "never show a chip for a field/grain the source does not have"; the system prompt tells the model to always name the field. e2e stubs bypass the server, so catalog validation is proven ONLY by the integration + `ai_followups` unit tests — never claim e2e covers it.
- **Model text never hits `innerHTML`** — `ReportingFollowups` builds pills with `createElement`/`textContent`; `test_followups_clarify_renderer_is_xss_safe` pins it. Keep it that way in any future chip work.
- **The three Advanced ask functions share non-unique snippets** (`askBtn.disabled = false;` ×6) — replace them wholesale, as written, never patch lines inside them.
- **Stale-chip hygiene is three-pronged on Simple** (`showAiLoading`, `showResultError`, `runCurrent` all clear `rsClarify`/`rsSuggest`) and two-pronged on Advanced (`setSurface` + the top of every ask function) — chips from a previous draft must never sit beside a loading indicator, an error, or a fresh clarify.
- **Suggestion chips persist across manual filter-chip edits on Simple** (re-rendered from `state.current.aiSuggestions` by every `runCurrent`) — intentional: filter edits don't change catalog validity. The next AI draft replaces them.
- **Loading-state regression:** clarify renders only after `hideAiLoading()`; the MutationObserver latch tests (`test_ai_ask_shows_loading_then_result`, `test_advanced_ai_ask_shows_loading`) are run explicitly in Tasks 9/10.
- **Audit args are positional:** `(userid, username, prompt, surface, generated_sql, provider, model, tokens_in, tokens_out, gate_verdict, status, duration_ms)` — tests assert `args[-3]` (GateVerdict) and `args[-2]` (Status). The agent route's verdict slot carries `stopped_reason`, unchanged.
- **ruff/isort may reorder the new import names** in `views/reporting.py` and the test file's `import json` on the first commit attempt — `git add -u`, re-run the identical commit.
- **`$env:SQL_SYNC_SKIP = "1"` before every commit** (INT CRLF checksum drift makes the sql-migrate-int hook fail on Windows even for SQL-free commits); never `--no-verify`.
- **Mid-plan `test_translations.py` failures are expected** between Task 8 (first new msgids) and Task 11 (pybabel cycle) — nothing is pushed before then.
- **Jinja template cache:** restart the dev server (`nx -u` / `nx -u -b --loginas:<user>`) before any manual browser check; the pytest e2e fixture spawns its own server.
- **Migration numbering:** `0022` is taken by the merged improvement-options work; if a migration ever becomes necessary here (it should not), use `0023+` and mirror into `sql/test/schema.sql`.
- **Stray `D env/CONFLUENCE.env.example`** in `git status` belongs to another worktree — never stage, commit, or restore it here.
- **Remote session:** stop at `git commit`; screenshots go to `var/screenshots/` (scripted into the e2e tests, so they regenerate on every run) and are sent via SendUserFile unasked; drive Playwright yourself rather than asking the owner to test. The ruflo background agent can stash uncommitted edits and drop 0-byte junk files named after code tokens — commit early and often.
