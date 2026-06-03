# Handoff — Reporting AI Phase 2 ("Build a report", Surface A) implemented + live-verified

- **Date:** 2026-06-03
- **Branch:** `feature/2.5.63`. Git mode this session: **commit-only (remote)** — **nothing pushed**.
  The branch is now **14 commits ahead of `origin/feature/2.5.63`** (5 from the prior session +
  9 from this one). The owner pushes + opens the PR.
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-03-reporting-cost-cap-json-fix-ro-rotation-handoff.md`
- **Build spec:** `docs/superpowers/plans/2026-06-03-reporting-ai-phase2.md` (executed task-by-task, subagent-driven).

## TL;DR

Implemented **Reporting AI Phase 2** end-to-end: a **"Build a report"** sub-mode in the Ask-AI
panel that turns a natural-language question into a **v1 report definition** (not SQL), auto-fills
the builder wells, and runs through the *unchanged* `/api/reporting/run`. Whitelist-safe, gated by
**`reporting.ai.use` only**, self-validating with one self-repair retry, audited
(`Surface='definition'`). Also did the optional **"Make a chart"** add-on (`chartHint`). All 7 plan
tasks + 2 review fixes. **Verified live on INT** (Azure provider + Generali PDQM source) in a real
browser — see screenshots in `var/screenshots/reporting_ai_build_0{1..5}.png`.

## Commits this session (all local/unpushed, on `feature/2.5.63`)

```
c038d35 fix(reporting): docprocessing fields in AI build catalog; guard chart   (final-review fixes)
0a2c2a5 docs(reporting): AI Phase 2 (Build a report) + de/fr/it translations     (Task 7)
6552e07 feat(reporting): optional AI chart suggestion (Surface A chartHint)       (Task 6)
46ffdbe fix(reporting): use straight quotes in Ask-AI Build-mode panel markup     (Task 5 hotfix)
f3dcb87 feat(reporting): Ask-AI 'Build a report' sub-mode auto-fills the builder  (Task 5)
3126aad feat(reporting): POST /api/reporting/ai/build — Surface A NL->definition  (Task 4)
f8d6f76 feat(reporting): bounded curated-sources catalog serializer (Surface A)   (Task 3)
2c66d65 feat(reporting): ask_definition() NL->v1 report-definition (Surface A)    (Task 2)
bf6bc99 refactor(reporting): factor AI provider dispatch to take system+user      (Task 1)
```

## What shipped (by file)

| File | Change |
|---|---|
| `nx_lib/reporting/ai.py` | `_dispatch(system,user,...)` seam (Task 1, preserves `ask()` incl. the Anthropic error-envelope); `ask_definition()` + `AiDefinitionResult` + `_parse_json_object` (Task 2); `_SYSTEM_DEF` gains an optional `chartHint` (Task 6). |
| `nx_lib/reporting/ai_schema.py` | `serialize_sources_catalog()` — bounded, truncation-logged curated-source catalog text (Task 3). |
| `nx_lib/views/reporting.py` | `_accessible_curated_sources` (now grounds docprocessing on the Statconfig catalog — fix), `_ai_catalog_text`, `_validate_definition_for_user` (reuses `validate_report_definition`; strips `chartHint` before validating), `_normalize_definition`, route **`POST /api/reporting/ai/build`** (gated `reporting.ai.use` only; 2-attempt self-repair; audited `Surface='definition'`; honors `AI_DAILY_LIMIT`), registration, `ai_sql_enabled` template kwarg (Tasks 4+6). |
| `templates/reporting.html` | Ask-AI sub-mode toggle (Build/Write-SQL, SQL gated on `ai_sql_enabled`), mode-aware hints, definition-result block (summary + Open in builder + Make a chart) (Tasks 5+6). |
| `templates/js/_reporting_ai_js.html` | `setSurface`/`askBuild`/`askSql`/`summarize`, dispatch, Open-in-builder + Make-a-chart wiring (Tasks 5+6). |
| `templates/js/_reporting_js.html` | `run()` returns its promise; `applyDefinitionAndChart`; `window.Reporting` export (Tasks 5+6). |
| `templates/js/_reporting_viz_js.html` | stable chart-select IDs + `ReportingViz.applyChartHint` (Task 6). |
| `CHANGELOG.md`, `docs/howto/reporting.md`, `CLAUDE.md`, `docs/design/reporting-ai-assistant.md`, `messages.pot`, `translations/{de,fr,it}/…` (po+mo) | Docs + i18n; 7 new msgids translated non-fuzzy (Task 7). |

**No new permission, table, or migration.** No new top-level runtime files → no `deploy.yml` exclude change needed.

## Verification (all green at HEAD `c038d35`)

- `python -m pytest tests/unit/test_reporting_*.py tests/integration/test_reporting_*.py` → **189 passed**.
- AI/schema/json/translation suites → green; `test_translations.py` → **7 passed** (pot in sync, de/fr/it non-fuzzy).
- `ruff check nx_lib/reporting/ai.py nx_lib/reporting/ai_schema.py nx_lib/views/reporting.py` → clean.
- **Live browser smoke on INT** (logged in as `ben.streich` via `/dev/login`, Azure provider):
  - Build sub-mode toggle + mode-aware hint render (`reporting_ai_build_01_submode.png`).
  - "total quantity by subcategory" → `verdict=valid`, definition summary + Open in builder (`…02`).
  - Open in builder filled the wells + Run returned real rows via `/api/reporting/run` (`…03`,`…04`).
  - "bar chart of …" → Make-a-chart button → rendered the AI-hinted bar chart (`…05`).
  - docprocessing source: model now selects it (catalog fix) but its draft used label-style field
    names → correctly shown invalid + Open-in-builder disabled (graceful).

## Owner actions / next steps

1. **Push + PR.** 14 commits unpushed on `feature/2.5.63`. The pre-push gate runs the **full e2e
   (Playwright) suite** — run `python scripts/test_db_reset.py` first to avoid stale `NEXORA_TEST`
   state. Then PR → `main` → deploy (the prior session's items #1/#3/#4/#5 still apply: INT RO-login
   `ALTER LOGIN` unblock, PROD rollout incl. AI migrations 0013/0014 + `AI_*`/RO env on the prod box,
   rotate the exposed Azure key, wire the scheduled-reports Task Scheduler task).
2. **AI provider** is already live on INT (Azure) — Phase 2 needs nothing new there. Surface A does
   **not** need the RO SQL logins for the table-provider sources (Generali/Octopus run on their own
   engines); only the SQL sandbox (Surface B) + docprocessing catalog depend on them.

## Open items / known minors (not blockers)

1. **docprocessing field-key mismatch (model-side, not a bug).** The catalog now includes the
   docprocessing fields, but their keys are the internal Statconfig-mapped keys; the model tends to
   guess human labels ("Document Type") that don't match, so docprocessing "Build a report" often
   comes back invalid. Surface A degrades gracefully (invalid warning, Open-in-builder disabled).
   Improving this = friendlier field keys/labels in the docprocessing catalog or a prompt tweak.
2. **`summarize()` in `_reporting_ai_js.html` uses untranslated English fragments** ("source ",
   "columns: ", "filter(s)", "sorted") in the definition summary. Minor i18n gap (JS-side).
3. **`api_ai_build` AiError path writes no audit row** (a provider-misconfig 503 leaves no
   `ReportingAiAudit` trace) — matches `api_ai_ask`'s existing behavior; fix both together if wanted.
4. The `_audit_ai` logger line still says `reporting.ai.ask` for the build surface (cosmetic log
   label only; the DB row's `Surface` is correctly `definition`).

## Notes / gotchas

- **Smart-quote trap (fixed, watch for it):** a subagent corrupted `templates/reporting.html` with
  curly quotes as HTML/`_()` delimiters → Jinja 500 on `/reporting`. Caught by the browser smoke and
  fixed in `46ffdbe`. Templates must use straight ASCII quotes except inside display text.
- **Restart after template edits** — Jinja is cached for the process lifetime (`bin\nx.ps1 -r`).
- Dev server was left **running** (INT, port 8000). Screenshots are under `var/screenshots/` (gitignored).
- RO-login unblock was **deliberately skipped** this session (owner's call) and remains a prior-handoff
  owner action — it can't safely become a committed migration (would leak the live password into git;
  the runner also lacks `ALTER ANY LOGIN`).

## Resuming in a fresh session

Phase 2 is complete and verified; the realistic next task is the **push + PR + PROD rollout** (owner
machine), then optionally polishing the open minors above. The plan doc is the build spec of record.
