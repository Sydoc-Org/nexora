# Handoff — reporting flagship UI polish: PLAN written, ready to execute

**Date:** 2026-07-14 (evening) · **Branch:** `plan/reporting-flagship-ui-polish` (worktree
`.claude/worktrees/plan-reporting-flagship-ui-polish`, based on `feature/2.5.64` @ `d2d7205`) ·
**commit-only (remote session — owner pushes)**
**Prior handoff:** `2026-07-14-pr119-merge-docfield-bleed-fix.md` (same day; PR #119 shipped +
doc-field bleed fix)

## TL;DR

- **A complete 13-task implementation plan exists and is committed** (`0546572`):
  `docs/superpowers/plans/2026-07-14-reporting-flagship-ui-polish.md`. Nothing is implemented yet —
  this session was planning only.
- The feature (owner request + interactive Q&A): **WS1** inline the bind parameters into the
  show-query SQL (display/copy only, execution stays parameterized), **WS2** kill every EN/DE
  language mix via i18n + a new lint guard, **WS3** visual polish within the 2.5.63 design system,
  **WS4** smart UX (CTA empty states, toasts instead of `window.alert`, AI-unavailable notice,
  drill loader, all-time hint, locale numbers).
- Plan built by a 7-agent Fable workflow (explore ×3 → opposed drafts ×2 → red-team → merge;
  14 findings folded in), then **independently re-verified by a 4-agent sweep: 285 anchors checked,
  6 misses found and fixed in the plan** — incl. a must-fix decorator-ordering trap that would have
  silently stripped `@require_permission` off `api_sql_run`.
- **The worktree stays open on purpose** — it is the execution vessel for `/execute-plan`.

## This session's commits

- `0546572` docs(plans): add reporting-flagship-ui-polish implementation plan
- (plus this handoff commit)

## What shipped

| Artifact | Path |
|---|---|
| Implementation plan (13 tasks, 7 phases) | `docs/superpowers/plans/2026-07-14-reporting-flagship-ui-polish.md` |
| Planning worktree (KEEP — execution vessel) | `.claude/worktrees/plan-reporting-flagship-ui-polish` on `plan/reporting-flagship-ui-polish` |

Owner decisions locked in the plan (from AskUserQuestion): full polish **+ smart UX** scope; elevate
**within** the existing design system; SQL params **always inlined**, Kopieren copies the runnable
statement. Declared executor: **Sonnet** (commit blocks carry the Sonnet trailer + substitution
note).

## Next steps (ordered)

1. **`/execute-plan`** in a fresh session — it must run **inside the worktree**
   (`.claude/worktrees/plan-reporting-flagship-ui-polish`, branch `plan/reporting-flagship-ui-polish`)
   and start at Task 1 of the plan. Every task is RED→GREEN with paste-ready commits.
2. Before the FIRST execution commit: the worktree's `env/INT.env` + `env/TEST.env` were already
   copied from the main clone this session (gitignored) — the SQL hooks need them.
3. After execution: merge `plan/reporting-flagship-ui-polish` back into `feature/2.5.64`
   (execute-plan's `--merge-worktree` handoff does this), owner reviews and pushes.

## Gotchas & notes

- **INT drift, not ours:** the `sql-sync-check` hook regenerates `sql/NexoraDB/Tables/dbo.ApiKeys.sql`
  — INT carries an `ApiKeys` table from the **parallel external-api effort**
  (`plan/external-api-v1-today-stats` worktree). Do NOT commit that dump on this branch; commit with
  `SQL_SYNC_SKIP=1` when the hook flags it (this session did). The hook also churns ~68 other sql
  dumps (whitespace/CRLF regeneration) — `git restore sql/` cleans it.
- The plan **expects `tests/unit/test_translations.py` RED from Task 2 through Task 10** (single
  late pybabel cycle) — that is by design, don't "fix" it early.
- Sequencing: don't restructure `templates/js/_reporting_drill_js.html` beyond the plan's surgical
  edits (drill-through recently merged, still owes a live pass — plan Task 13 absorbs a spot-check);
  the parallel external-api plan may touch `nx_lib/views/reporting.py` — whoever merges second
  re-greps anchors.
- `feature/2.5.64` moved to `d2d7205` mid-session (another session committed a handoff) — this
  worktree is based on that tip.
- First workflow run died wholesale on a transient DNS outage (`ENOTFOUND`); relaunched with
  per-agent retry. Nothing was lost (no cached results existed).

## Untracked / left for owner

- Main clone still has the junk `package.json`/`package-lock.json` at repo root (prior handoff) —
  untouched.
- `var/handoff-pending` written in BOTH the main clone (pointing at this file via the worktree
  path) and the worktree — gitignored, never committed.

## How to verify (this handoff's claims)

```powershell
git -C C:\dev\nexora\.claude\worktrees\plan-reporting-flagship-ui-polish log --oneline -3
# 0546572 docs(plans)…, d2d7205 docs(handoff)…, 97678a0 docs(handoff)…
git -C C:\dev\nexora worktree list   # shows plan-reporting-flagship-ui-polish + external-api worktrees
# The plan itself: 2103 lines, 13 tasks, "Migrations needed: NO"
```

## Resuming in a fresh session

`/execute-plan` (or `/reset-session` first) — **five handoffs share 2026-07-14**; if the picker
grabs another, use
`/reset-session docs/superpowers/handoffs/2026-07-14-reporting-flagship-ui-polish-plan.md`.
Resume point: `docs/superpowers/plans/2026-07-14-reporting-flagship-ui-polish.md`, Task 1.
**Worktree:** `.claude/worktrees/plan-reporting-flagship-ui-polish` **Branch:**
`plan/reporting-flagship-ui-polish`.
