# Handoff — Reporting AI Owner Feedback (#178): plan written, ready to execute

**Date:** 2026-08-06 · **Branch:** `plan/reporting-ai-owner-feedback` (worktree
`.claude/worktrees/plan-reporting-ai-owner-feedback`, cut from `v3.1` @ `4856eed`) ·
**commit-only — owner pushes**
**Prior handoff:** `2026-08-05-reporting-forecast-toggle-execution-complete.md`

## TL;DR

- **Issue #178** (Reporting AI Owner Testing — a ten-gripe umbrella across the AI agent, Simple
  pane, semantics and dashboards) was read (all 11 screenshots), broken into groups A–D, and the
  owner approved **all four groups** in one batch.
- The plan (**16 tasks, 8 phases**, TDD, all anchors Grep-verified against `4856eed`) is committed
  at `docs/superpowers/plans/2026-08-06-reporting-ai-owner-feedback.md` — **execute it in this
  worktree**.
- One migration (`0056` — `ReportingMetrics.TotalMode`), one new endpoint
  (`POST /api/reporting/field_values`), no new permission, no deploy.yml change.
- Issue #178 already labeled `inprogress`. Gripe A5 ("Live SQL geht nicht") is deliberately a
  repro-first task (Task 15), not a speculative fix.

## This session's commits (oldest → newest)

- `157286b` docs(plans): add reporting-ai-owner-feedback implementation plan
- (this handoff commit)

## What shipped

| # | Item | File |
|---|---|---|
| 1 | Implementation plan: live build-step ticker over the existing NDJSON stream (A1) · artifact-carrying chat history + 12k cap + presentation-follow-up prompt rule (A3) · T-SQL hints 156/205/209 + prompt discipline (A2) · AI reports open in Simple via new `ReportingSimple.openDefinition` (A4) · hero hidden outside library (B6) · granularity chip (B7) · wizard grain always visible + process scope step for table sources via new field-values endpoint (B8) · `TotalMode='latest'` grand totals server+client for backlog (C10, migration 0056) · forecast history lookback via `widened_definition_for_forecast` (C9) · dashboard card type `report` adopting a saved report 1:1 (D11) · Live-SQL repro task (A5) · i18n/changelog/docs (Task 16). | `docs/superpowers/plans/2026-08-06-reporting-ai-owner-feedback.md` |

## Next steps (ordered)

1. **Run `/execute-plan`** (or superpowers:subagent-driven-development) against
   `docs/superpowers/plans/2026-08-06-reporting-ai-owner-feedback.md`, **inside the worktree**
   (`.claude/worktrees/plan-reporting-ai-owner-feedback`, branch `plan/reporting-ai-owner-feedback`).
   Start at Phase 1 / Task 1. Ordering constraints (plan "Gotchas"): Task 4 before Task 2 (test
   seam), 8→9→10, 12 before 13; everything else independent.
2. Before Task 8's commit: `Copy-Item C:\dev\nexora\env\INT.env .\env\INT.env` (worktrees lack the
   gitignored env file; the migration hook needs INT creds).
3. After execution: owner merges `plan/reporting-ai-owner-feedback` → `v3.1`, pushes, closes #178
   with the fix SHA.

## Gotchas & notes

- **Worktree has no `env/*.env`** — SQL pre-commit hooks fail with "Missing DB_SERVER_PRD…". For
  docs/JS-only commits prefix `SQL_SYNC_SKIP=1`; for Task 8 (real migration) copy `env/INT.env` in
  first (step 2 above) so the hook actually applies `0056` to INT.
- **Parallel sessions own the main checkout** — `static/css/reporting.css` and
  `tools/reporting_ai_eval/prompts.json` are modified (uncommitted) there. Stay inside the
  worktree; all CSS in the plan appends at file END to keep the merge trivial.
- **Live checks:** `nx -u`/`nx -r` serve the MAIN checkout — run Flask directly from the worktree
  instead (see plan "Gotchas", first bullet), own browser, own port, kill it when done.
- Decisions D1–D13 in the plan are locked (notably: NO server-side SQL compile check; chat history
  carries artifacts client-side; `TotalMode` registry-driven with admin UI deliberately untouched;
  forecast lookback token-filters-only) — don't re-litigate.
- The plan's "Context an engineer needs" section carries the full execution contract (TEST env has
  no Statistics DB → stub/patch patterns; `scripts/test_db_reset.py` before e2e; ONE late pybabel
  cycle in Task 16 with the malformed-msgstr diff-sweep; template-cache restart; screenshots to
  `var/screenshots/` + SendUserFile as tasks land).

## Untracked / left for owner

- Nothing untracked in the worktree. Main-checkout modifications belong to other sessions —
  untouched.
- Deferred by design (plan "Owner actions"): SQL compile-check in validate_sql, literal-range
  forecast lookback, TotalMode admin UI, latest-mode + forecast/caption/drill inside dashboard
  cards.

## How to verify

```powershell
# from the worktree root
git log --oneline -3          # 157286b plan + this handoff on plan/reporting-ai-owner-feedback
git worktree list             # worktree registered against C:\dev\nexora
C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_table_query.py -q  # green baseline
```

No suites are red; no feature code exists yet.

## Resuming in a fresh session

`/reset-session` (the `var/handoff-pending` flag points here). Then open
`docs/superpowers/plans/2026-08-06-reporting-ai-owner-feedback.md` in the worktree and execute
task-by-task. If the flag was consumed already:
`/reset-session .claude/worktrees/plan-reporting-ai-owner-feedback/docs/superpowers/handoffs/2026-08-06-reporting-ai-owner-feedback-plan.md`.
