> **Superseded same-day:** execution finished — see
> `docs/superpowers/handoffs/2026-08-05-reporting-forecast-toggle-execution-complete.md` for the
> current state (all 10 tasks done, merged into `feature/2.5.65`, worktree removed).

# Handoff — Reporting Forecast Toggle (#168): plan written, ready to execute

**Date:** 2026-08-05 · **Branch:** `plan/reporting-forecast-toggle` (worktree
`.claude/worktrees/plan-reporting-forecast-toggle`, cut from `feature/2.5.65` @ `e5eea54`) ·
**commit-only — owner pushes**
**Prior handoff:** `2026-08-03-issue-148-document-value-search.md`

## TL;DR

- **Issue #168** (Reporting: forecast toggle on time-series results) was interpreted, approved, and
  fully planned — **no implementation code written yet**.
- Owner locked two decisions: **pure-stdlib forecasting** (OLS trend + seasonal indices + 95 %
  prediction intervals in a new `nx_lib/reporting/forecast.py` — NO statsmodels/numpy) and
  **single-dimension only** (2+ breakdowns grey the toggle).
- The plan (10 tasks, 5 phases, TDD, all anchors Grep-verified) is committed at
  `docs/superpowers/plans/2026-08-05-reporting-forecast-toggle.md` — **execute it in this worktree**.
- Issue #168 labeled `inprogress`. No migration, no new permission, no deploy.yml change needed.

## This session's commits (oldest → newest)

- `33ebd30` docs(plans): add reporting-forecast-toggle implementation plan
- (this handoff commit)

## What shipped

| # | Item | File |
|---|---|---|
| 1 | Implementation plan: stdlib forecast engine → `/api/reporting/run` `forecast` block (comparison-block pattern) → Simple + Advanced toggle/horizon UI with dashed line + confidence band → marked table rows → marker-column exports → scheduled-mail PNG band + attachment rows → i18n/changelog/docs. Includes a drive-by fix task: `runner.py`'s table-provider validate is missing `grainable_fields` (any scheduled table-source report with a grain bounces today). | `docs/superpowers/plans/2026-08-05-reporting-forecast-toggle.md` |

## Next steps (ordered)

1. **Run `/execute-plan`** (or superpowers:subagent-driven-development) against
   `docs/superpowers/plans/2026-08-05-reporting-forecast-toggle.md`, **inside the worktree**
   (`.claude/worktrees/plan-reporting-forecast-toggle`, branch `plan/reporting-forecast-toggle`).
   Start at Phase 1 / Task 1. Tasks are strict TDD with paste-ready code + commit messages.
2. After execution: owner merges `plan/reporting-forecast-toggle` → `feature/2.5.65`, pushes, and
   closes #168 with the fix SHA (`gh issue close 168 --comment "…<sha>"`).

## Gotchas & notes

- **Worktree has no `env/INT.env`** (gitignored, lives only in the main checkout) — the SQL
  pre-commit hooks fail with "Missing DB_SERVER_PRD / DB_UID / DB_PWD in env". Prefix every commit
  in this worktree with `SQL_SYNC_SKIP=1`. The plan needs no migration, so nothing is lost.
- **Parallel session active in the main checkout** (status page #167 files uncommitted there) —
  stay inside the worktree, never touch the main checkout's working tree.
- The plan's "Context an engineer needs" section carries all execution gotchas (TEST env has no
  Statistics DB → patch/stub patterns; e2e needs `scripts/test_db_reset.py` first; one late pybabel
  cycle in Task 10; template-cache restart before manual checks).
- Decisions D1–D10 in the plan are owner-locked (stdlib engine, single-dim only, band only for
  single-metric, marker-column exports, drill excluded on predictions, schedule gating via the
  saved definition) — don't re-litigate them.
- `.venv` python for tests; dev server runs global Python — no new runtime deps in this feature, so
  the dual-python trap does not apply.

## Untracked / left for owner

- Nothing untracked in the worktree. Main-checkout modifications (status page #167 etc.) belong to
  another session — untouched.
- Deferred by design (plan "Owner actions"): multi-metric bands, exported bounds columns, AI
  assistant awareness of the forecast key.

## How to verify

```powershell
# from the worktree root
git log --oneline -3          # 33ebd30 plan + handoff on plan/reporting-forecast-toggle
git worktree list             # worktree registered against C:\dev\nexora
C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_schema.py -q   # green (pre-feature baseline)
```

No suites are red; no feature code exists yet.

## Resuming in a fresh session

`/reset-session` (the `var/handoff-pending` flag points here). Then open
`docs/superpowers/plans/2026-08-05-reporting-forecast-toggle.md` in the worktree and execute
task-by-task. If the flag was consumed already:
`/reset-session .claude/worktrees/plan-reporting-forecast-toggle/docs/superpowers/handoffs/2026-08-05-reporting-forecast-toggle-plan.md`.
