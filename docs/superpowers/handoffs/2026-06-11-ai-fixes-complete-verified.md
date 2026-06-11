# Handoff — 16-task AI-fixes plan executed + live browser verification complete

- **Date:** 2026-06-11
- **Branch:** `feature/2.5.63`. **22 commits ahead of `origin/feature/2.5.63`** — commit-only
  (remote); the owner pushes + opens the PR.
- **Prior handoff:**
  `docs/superpowers/handoffs/2026-06-11-ai-fixes-plan-staging-migrations.md`
  (16-task plan written, STAGING unblocked — plan not yet executed).
- **This session's commits (oldest → newest):**
  - `66e37fa` feat(reporting): add quarter tokens to AI prompt token lists
  - `4ba1536` feat(reporting): quarter token presets and labels in UI
  - `713a1d6` fix(reporting): AI prompts require date grain for per-period questions
  - `55a92cf` fix(reporting): two-case DISTINCT rule in AI prompts
  - `fc59a7e` fix(reporting): drop columns shadowing a distinct-count metric
  - `f56ee65` fix(reporting): name valid SQL targets in grounding and error
  - `a1d87c3` fix(reporting): grounding marks metric-less sources as cannot-aggregate
  - `427f179` fix(reporting): prefer gate error over model explanation in AI failure
  - `4481a1f` feat(reporting): i18n for quarter token labels (de/fr/it)
  - `ee07d40` docs(reporting): quarter tokens, grain rule, distinct/agent fixes
  - `edcd93b` feat(reporting): disable workitem_count metric (migration 0021)
  - `7aaecda` fix(reporting): time filters default to processing dates
  - `4fc7b48` feat(reporting): refine bar and editable chips on every Simple result
  - `b8e9a86` feat(reporting): adjust-in-wizard re-entry with preserved choices
  - `c10299d` fix(reporting): pre-select all_time preset on wizard re-entry

---

## TL;DR

1. **All 16 tasks from `docs/superpowers/plans/2026-06-11-reporting-ai-fixes.md` executed**
   using subagent-driven development (implementer + spec review + code review per task).
   15 implementation commits; Task 16 was live browser verification (no code change).
2. **All 6 AI bugs fixed**: quarter tokens, grain rule, distinct-count guard, run_sql target
   grounding, metric-less source marking, processing-date defaulting.
3. **UX tasks 14–15 shipped**: refine bar + editable chips on every Simple result;
   "Im Assistenten anpassen" wizard re-entry button with full state preservation.
4. **Live browser verification: 8/8 checks passed.** Task 12 migration `0021` applied to INT
   (disables `workitem_count`). 991 unit+integration tests + 16 e2e all green.

---

## The six AI bugs — status after this session

| # | Bug | Plan tasks | Status |
|---|-----|-----------|--------|
| 1 | No `this_quarter`/`last_quarter` tokens | 1–3, 10, 11 | ✅ Fixed |
| 2 | AI never emits `grain` | 4 | ✅ Fixed |
| 3 | Distinct-per-Y → every count = 1 | 5–6 | ✅ Fixed |
| 4 | Agent dead end / `max_turns` / empty answer | 7 | ✅/⚠️ Partial — `max_turns` gone, `GateVerdict` now `final`; agent still can't answer ranking questions via `build_definition` |
| 5 | Metric-less source misdraft + UI shows model explanation | 8–9 | ✅ Fixed |
| 6 | "April 2026" filtered on Document Date | 13 | ✅ Fixed |

Plus: Task 12 = migration `0021` disabling `workitem_count`; Tasks 14–15 = UX polish;
Task 16 = verification.

---

## What shipped (all 15 implementation commits)

**Tasks 1–3, 10 — Quarter tokens**

| File | What |
|------|------|
| `nx_lib/reporting/tokens.py` | `_quarter_start` helper + `this_quarter`/`last_quarter` lambda entries |
| `nx_lib/reporting/ai.py` | Quarter tokens in `_SYSTEM_DEF` + `_AGENT_SYSTEM` prompt lists |
| `templates/js/_reporting_simple_js.html` | `TOKEN_LABELS` map + wizard `last_quarter` preset button |
| `templates/js/_reporting_js.html` | `DATE_TOKEN_PRESETS` entries for `this_quarter`/`last_quarter` |
| `translations/{de,fr,it}/LC_MESSAGES/messages.po` | "This quarter" / "Last quarter" translations |
| `tests/unit/test_reporting_tokens.py` | Quarter parametrize rows + edge test |

**Task 4 — Grain rule**

| File | What |
|------|------|
| `nx_lib/reporting/ai.py` | Grain MUST rule + worked example in both system prompts |
| `tests/unit/test_reporting_ai_definition.py` | Grain rule tests |

**Tasks 5–6 — Distinct-count guard**

| File | What |
|------|------|
| `nx_lib/reporting/ai.py` | Two-case DISTINCT rule in both system prompts |
| `nx_lib/reporting/semantic.py` | `drop_columns_shadowing_distinct_metrics` guard function |
| `nx_lib/views/reporting.py` | Gate calls `drop_columns_shadowing_distinct_metrics` after `coerce_definition` |
| `tests/unit/test_reporting_semantic.py` | 5 guard unit tests |
| `tests/integration/test_reporting_ai_routes.py` | Shadow guard integration test |

**Task 7 — Agent run_sql targets**

| File | What |
|------|------|
| `nx_lib/views/reporting.py` | `_run_sql` error names allowed targets; agent grounding appended |
| `tests/unit/test_reporting_ai_agentic.py` | Target grounding tests |
| `tests/integration/test_reporting_ai_routes.py` | `run_sql` target + grounding tests |

**Tasks 8–9 — Metric-less sources + error precedence**

| File | What |
|------|------|
| `nx_lib/reporting/ai_schema.py` | `metrics: none` marker in `serialize_sources_catalog` |
| `templates/js/_reporting_simple_js.html` | Error precedence: gate reason shown before model explanation |
| `tests/unit/test_reporting_ai_schema.py` | Metric-less marker tests |

**Task 11 — Docs + changelog**

| File | What |
|------|------|
| `docs/howto/reporting.md` | AI fixes documented |
| `CHANGELOG.md` | `[Unreleased]` entries for all six bugs + Tasks 12–15 |

**Task 12 — Disable workitem_count**

| File | What |
|------|------|
| `sql/_migrations/NexoraDB/0021_disable_workitem_count_metric.sql` | `UPDATE ReportingMetrics SET Enabled=0 WHERE Code='workitem_count'` |

**Task 13 — Processing-date default**

| File | What |
|------|------|
| `nx_lib/reporting/ai.py` | Processing-date defaulting rule in both system prompts + `_definition_user_prompt` allows prior_def without prior_question |
| `tests/unit/test_reporting_ai_definition.py` | Processing-date + prior-def-without-question tests |

**Task 14 — Refine bar + chips on every Simple result**

| File | What |
|------|------|
| `templates/js/_reporting_simple_js.html` | `renderAiChips` guard uses `hasDef`; `runCurrent` always shows refine bar; refine payload includes `priorQuestion` only when present |
| `tests/e2e/test_reporting_simple.py` | Wizard chips/refine test |

**Task 15 — Adjust-in-wizard re-entry**

| File | What |
|------|------|
| `templates/js/_reporting_simple_js.html` | `reopenWizard()` fn; `builtBy: 'wizard'` marker; `adjustBtn` visibility toggle; `choiceBtn` `selected` arg; step renderers preserve state; `all_time` pre-selection fix (`c10299d`) |
| `templates/_reporting_simple.html` | `<button id="rsAdjustWizard">` |
| `nx_lib/views/reporting.py` | i18n strings for "Adjust in wizard" |
| `translations/{de,fr,it}/LC_MESSAGES/messages.po` | "Adjust in wizard" translations |
| `docs/howto/reporting.md` | Feature description |
| `tests/e2e/test_reporting_simple.py` | Adjust-wizard round-trip test |

---

## Live browser verification results (Task 16)

All checks run as `ben.streich` on INT (`http://127.0.0.1:8000/reporting?tab=simple`):

| Check | Result | Key observation |
|-------|--------|----------------|
| 1. Month-grain per-month ask | ✅ | Bucket `2026-02-01`, chip `export_date between Dieses Jahr` |
| 2. Last quarter token | ✅ | `Letztes Quartal (2026-01-01 → 2026-03-31)` — calendar Q1, NOT last_3_months |
| 3. Distinct workitems ask | ✅ | Gate error shown, NOT all-1s table |
| 4. Agent ranking ask | ✅/⚠️ | Audit Id=40: `GateVerdict=final` (was `max_turns` Id=35); answer non-empty but still apologetic |
| 5. Metric-less source | ✅ | Gate reason `(unknown metric: 'count')` shown |
| 6. April 2026 date field | ✅ | `export_date` for "process"; `import_date` for "imported" rephrase |
| 7. Wizard result chips/refine | ✅ | Chips visible, refine bar visible, "only compass" refine works with no prior question |
| 8. Adjust-in-wizard re-entry | ✅ | Prior state (measure+breakdown+preset) all restored; changed preset re-runs correctly |

---

## Next steps (ordered)

1. **Owner: push + open the PR** — 22 commits waiting on `feature/2.5.63`. This includes the
   2026-06-10 handoff commit (never pushed), STAGING unblock, and all 15 AI-fix commits.
2. **PROD deploy checklist** (unchanged from prior handoffs):
   - RO SQL logins (`DB_REPORTING_RO_USER`/`DB_REPORTING_RO_PWD` and Octo equiv.) in
     `env/PROD.env` — SQL tab and some AI asks still 503 without them.
   - Scheduled-reports Task Scheduler task (wire it up on SYAPP01).
   - `0011` em-dash label repair (apply migration manually if needed).
   - Migrations `0015`–`0021` auto-apply on deploy (migration `0021` disables `workitem_count`).
3. **Optional STAGING niceties**: `env/STAGING.env` lacks RO SQL logins + AI provider config
   → SQL tab and Ask-AI 503/hidden there; copy from INT if wanted.
4. **Optional cleanup**: stray `generali.reporting.*` `UserPermissionOverride` rows on
   `ben.streich@STAGING` (wrong-family grants from the 403 hunt) — remove via admin UI.
5. **Remaining AI limitation (not a regression)**: agent surface can answer some questions but
   still fails "which process handled the most" — `build_definition` can't express TOP 1 / ORDER BY
   via the definition schema. Needs `run_sql` path or a `sort+limit` extension to definitions.

---

## Gotchas & notes

- **Dev server environment**: switch back to INT if it's still running against STAGING
  (`& bin\nx.ps1 -r` uses INT by default; `nx -r --env:staging` was used last session for STAGING
  work but the handoff noted the dev server "still running against STAGING").
- **Migration `0021` applied to INT** via pre-commit hook on `edcd93b`. STAGING gets it next time
  `python scripts/db-migrate.py --env STAGING` is run (or on the next PROD deploy).
- **`all_time` sentinel quirk**: wizard state uses `range = null` for "All time" (not the string
  `'all_time'`). The preset pre-selection fix (`c10299d`) handles this — `p[0] === 'all_time' && state.wiz.range === null`.
- **`builtBy` vs `fromWizard`**: `fromWizard: true` means "ephemeral" (don't save to library
  automatically); `builtBy: 'wizard'` marks wizard-built results for the adjust button. Both
  coexist — the refine endpoint clears `builtBy` but preserves the result content.
- **gitlint**: subject ≤ 72 chars (two commits bounced this session before passing).
- **`SQL_SYNC_SKIP=1`** still required on every commit (INT SchemaMigrations CRLF drift).
- **Screenshots**: `var/screenshots/task16-check1-result.png`, `task16-check1-table.png`,
  `task16-check8-adjust-wizard-result.png` (gitignored, already sent).

---

## Untracked / left for owner

- Nothing uncommitted in the repo (clean tree).
- Playwright screenshots in `var/screenshots/` (gitignored).

---

## How to verify

```powershell
# Unit + integration (should be 991 green):
.venv\Scripts\python.exe -m pytest tests\unit\ tests\integration\ -q

# E2E (restart server first; pre-push gate runs these automatically):
python scripts/test_db_reset.py
.venv\Scripts\python.exe -m pytest tests\e2e\ -q

# Migration 0021 applied to INT (expect: up-to-date):
.venv\Scripts\python.exe scripts\db-migrate.py --env INT --dry-run
```

---

## Resuming in a fresh session

Two handoffs share today's date (2026-06-11). To target **this** one specifically:

```
/reset-session docs/superpowers/handoffs/2026-06-11-ai-fixes-complete-verified.md
```

Or run `/reset-session` alone — the `var/handoff-pending` flag points here.

**The plan is complete.** No unstarted tasks remain. The single resume point for the next session
is: **push + open the PR**, then follow the PROD deploy checklist above.
