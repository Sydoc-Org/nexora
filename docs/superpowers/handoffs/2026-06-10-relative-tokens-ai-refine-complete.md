# Handoff — Relative-date tokens + AI refine + editable chips (F1 & F2 complete)

- **Date:** 2026-06-10 (afternoon / evening session)
- **Branch:** `feature/2.5.63`. **0 commits ahead of `origin/feature/2.5.63`** — pushed this
  session; pre-push gate (incl. full Playwright e2e) passed clean.
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-09-reporting-date-dimension-complete.md`
  (date-dimension plan complete; Spec 2 Simple/Advanced tabs shipped in an earlier session today).
- **This session's commits (oldest → newest):**
  - `5fc7c0e` fix(reporting): ground agent surface in today's date
  - `eeb33b6` fix(reporting): ground AI definition drafting in today's date
  - `1174784` fix(reporting): move agent prompts to ai.py with stop-condition guidance
  - `d04f80c` fix(reporting): coerce grain/op/dir case in AI-drafted definitions
  - `192b4a8` feat(reporting): distinct workitem count metric + workitem_id field
  - `6f76881` fix(reporting): scheduled runner now resolves metric definitions
  - `58251cb` fix(reporting): teach AI prompts distinct-values and process matching
  - `4508946` feat(reporting): humanize process ids in AI catalog grounding
  - `6f9da69` feat(reporting): show AI explanation and filters on Simple results
  - `a31fae7` docs(reporting): i18n + docs for AI grounding fixes
  - `5b6b754` refactor(reporting): tighten token guard + use explicit None check — **F1-T1**
  - `32cda98` fix(reporting): query builders reject unresolved token values — **F1-T3**
  - `00d8c71` feat(reporting): resolve relative-date tokens at run time — **F1-T4**
  - `474191a` refactor(reporting): harden resolved-dates meta path
  - `88c3105` feat(reporting): teach AI prompts relative-date tokens — **F1-T5**
  - `6d69e55` fix(reporting): add field key to agent token example; strengthen test
  - `205b9e0` feat(reporting): wizard emits relative-date tokens + resolved-range line — **F1-T6**
  - `6badd6f` fix(reporting): guard tokenLabel against missing token field
  - `e659af3` feat(reporting): advanced filter presets for relative dates — **F1-T7**
  - `6b21eb5` fix(reporting): e2e token preset test — cleanup + dom wait
  - `9b123b5` docs(reporting): i18n + docs for relative-date tokens — **F1-T8**
  - `78671b3` feat(reporting): refine context in AI definition drafting — **F2-T1**
  - `949ce5e` feat(reporting): /ai/build accepts refine context — **F2-T2**
  - `988d4ae` fix(reporting): refine context depth guard + messages.pot sync
  - `7f77537` feat(reporting): AI thinking indicator on Simple tab — **F2-T3**
  - `52dca74` fix(reporting): wire delay_s in AI stub handler for test timing
  - `129c91b` feat(reporting): conversational refine on Simple results — **F2-T4**
  - `60ae577` feat(reporting): editable AI filter/process chips — **F2-T5**
  - `9d26304` fix(reporting): guard stale chip DOM and single-value filter edit
  - `356bd4e` feat(reporting): i18n, changelog, docs for AI refine and chips — **F2-T6**

---

## TL;DR

1. **Two full plans executed end-to-end:** F1 (relative-date tokens, 8 tasks) and F2 (AI refine
   + chips, 6 tasks). All 14 tasks done, all tests green, pushed.
2. **F1:** Saved/scheduled reports now use symbolic tokens (`{"token": "last_month"}`) that
   resolve server-side at run time — reports never go stale. The AI emits tokens; the Simple
   wizard's time-range presets emit tokens; the Advanced builder shows token presets for date
   fields. The `resolvedDates` key in `api_run` responses tells the client what range was used.
3. **F2:** Simple tab results have a **Refine** bar (type a follow-up, AI applies targeted
   changes using the original question + definition as context), a **thinking indicator**
   (Asking / Drafting / Checking steps), and **editable filter/process chips** (click to edit a
   filter in place, × to remove, process chip opens a checklist — all re-run instantly, no AI cost).
4. **Also landed this session:** AI grounding fixes (today's date injected, agent prompts in
   `ai.py`, DISTINCT guidance, human-readable process IDs in grounding, filter/process transparency
   line on Simple results, distinct workitem count metric, scheduled runner metric resolution).

---

## What shipped

### AI grounding fixes (`5fc7c0e` – `a31fae7`)

| Commit | What |
|--------|------|
| `5fc7c0e` | Agent (Surface B) prompt grounded in today's date |
| `eeb33b6` | AI definition drafter grounded in today's date |
| `1174784` | Agent stop-condition and system-prompt guidance moved to `ai.py` |
| `d04f80c` | `coerce_definition` normalizes grain/op/dir to lowercase |
| `192b4a8` | `distinct_workitem_count` metric + `workitem_id` field in catalog |
| `6f76881` | Scheduled runner resolves metric definitions (was broken) |
| `58251cb` | Agent system prompt: DISTINCT + GROUP BY + process-matching guidance |
| `4508946` | Process IDs humanized in AI catalog grounding |
| `6f9da69` | AI explanation + filters shown in Simple result view |
| `a31fae7` | i18n/docs for the grounding fixes |

### F1 — Relative-date tokens (`5b6b754` – `9b123b5`)

| File | Role |
|------|------|
| `nx_lib/reporting/tokens.py` | New module — 10 tokens, `validate_token_value`, `resolve_token`, `resolve_definition_tokens`, `date_fields_from_catalog` |
| `nx_lib/reporting/schema.py` | Validator accepts token dict-values; `coerce_definition` normalizes them |
| `nx_lib/reporting/query.py` + `table_query.py` | Defense-in-depth: raise if unresolved token reaches SQL layer |
| `nx_lib/reporting/runner.py` + `nx_lib/views/reporting.py` | Resolve tokens at execution; `api_run` returns `resolvedDates` |
| `nx_lib/reporting/ai.py` | System prompts teach token syntax with valid example |
| `templates/js/_reporting_simple_js.html` | `TOKEN_LABELS`, `isTokenValue`, `tokenLabel`; wizard presets emit tokens; resolved-range display in `rsMsg` |
| `templates/js/_reporting_js.html` | Advanced builder: token preset `<select>` for date fields |
| `messages.pot` + 3× `.po/.mo` | Yesterday / This week / Last week / Last {n} days / Custom dates… |
| `CHANGELOG.md` + `docs/howto/reporting.md` + `docs/design/reporting-ai-assistant.md` | Documented |

Token vocabulary: `today`, `yesterday`, `this_week`, `last_week`, `this_month`, `last_month`,
`this_quarter`, `last_quarter`, `this_year`, `last_year`. Resolution is server-local, half-open
`[gte, lt)` interval.

### F2 — AI refine + chips (`78671b3` – `356bd4e`)

| File | Role |
|------|------|
| `nx_lib/reporting/ai.py` | `ask_definition(prior_question, prior_definition)` — refine context injected into user-turn prompt |
| `nx_lib/views/reporting.py` | `api_ai_build` reads + validates `priorQuestion`/`priorDefinition` (size-capped: 2 000 / 20 000 chars; recursion guard) |
| `templates/_reporting_simple.html` | `rsAiLoading`, `rsRefineBar`, `rsChips` elements added |
| `templates/js/_reporting_simple_js.html` | `showAiLoading`/`hideAiLoading`, generalized `askAi(refineQuestion)`, `chip()`, `filterChipEditor`, `processChipEditor`, `renderAiChips`; `aiSummaryLine` deleted |
| `static/css/reporting.css` | Chip pill styles + loading indicator animation |
| `messages.pot` + 3× `.po/.mo` | Refine / Refine your question… / Asking the AI… / Drafting your report… / Checking the result… / Apply / All processes / Invalid refine context |
| `CHANGELOG.md` + docs | Documented |

---

## Next steps (ordered)

1. **Owner: open the PR** — branch is pushed (`origin/feature/2.5.63`), pre-push gate clean.
2. **PROD deploy checklist** (from earlier handoffs, still pending):
   - Migrations `0015` / `0016` / `0017` / `0018` / `0019` auto-apply on deploy.
   - Provision the two reporting RO SQL logins (`scripts/provision-reporting-ro-logins.sql`) —
     without these, `api_run` returns 503 for the docprocessing source.
   - Wire the scheduled-reports Task Scheduler task (see semantic-Slice1 handoff).
   - Repair the `0011` em-dash label (noted in the branch-consolidation handoff).
3. **Future work — no open plan files:** both F1 and F2 are fully done. Next effort would be a
   new brainstorm/spec/plan cycle.

---

## Gotchas & notes

- **Token guard narrowed:** `resolve_definition_tokens` uses `isinstance(f.get("value"), dict)
  and "token" in f.get("value", {})` to detect tokens. Any dict value without a `"token"` key
  passes through untouched.
- **`priorDefinition` is prompt context only** — never executed. Model output from a refine call
  still goes through full `_validate_definition_for_user`. The size cap (20 000 JSON chars) exists
  to prevent prompt DoS.
- **`processChipEditor` is async** (calls `loadSourcesCatalog()`). Includes an
  `if (!chipEl.isConnected) return;` guard post-await so a stale DOM reference silently aborts.
- **filterChipEditor single-value fallback:** if the user types a plain value (no `→` separator)
  when editing a token/between filter, the fix applies it as `f.op = 'eq'; f.value = parts[0]`
  rather than silently discarding it (quality fix `9d26304`).
- **Commit hooks:** `SQL_SYNC_SKIP=1` required on every commit (INT `SchemaMigrations` CRLF drift,
  memory `project_int_migration_crlf_drift`).
- **docprocessing/privera on INT returns 500** (pre-existing: missing Statistics tables). Scope to
  **compass** or **elektromaterial** for live testing of AI features.

---

## How to verify

```powershell
# Full unit + integration suite:
.venv\Scripts\python.exe -m pytest tests\unit\ tests\integration\ -q

# Token-specific:
.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_tokens.py -v

# AI refine routes:
.venv\Scripts\python.exe -m pytest tests\integration\test_reporting_ai_routes.py -v

# e2e (run db reset first):
python scripts\test_db_reset.py
.venv\Scripts\python.exe -m pytest tests\e2e\test_reporting_simple.py -v
.venv\Scripts\python.exe -m pytest tests\e2e\test_reporting.py -v

# Translations:
.venv\Scripts\python.exe -m pytest tests\unit\test_translations.py -v
```

All suites are **GREEN** as of the push.

---

## Resuming in a fresh session

Run `/reset-session` (reads `var/handoff-pending`) or
`/reset-session docs/superpowers/handoffs/2026-06-10-relative-tokens-ai-refine-complete.md`
to target this file directly. Both F1 and F2 plans are **complete** — no resume point within a
plan. Next work needs a new plan.
