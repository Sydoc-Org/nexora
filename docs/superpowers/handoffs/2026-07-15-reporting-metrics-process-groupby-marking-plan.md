> **Superseded same-day:** execution is now complete — see
> `docs/superpowers/handoffs/2026-07-15-reporting-metrics-process-groupby-marking-execution-complete.md`.

# Handoff — reporting metrics + process-coverage marking: PLAN written, ready to execute

**Date:** 2026-07-15 · **Branch:** `plan/reporting-metrics-process-groupby-marking` (worktree
`.claude/worktrees/plan-reporting-metrics-process-groupby-marking`, based on `feature/2.5.64` @
`f20466d`) · **commit-only (remote session — owner pushes)**
**Prior handoff:** `2026-07-14-reporting-flagship-ui-polish-execution-complete.md` (flagship polish
executed + merged into 2.5.64)

## TL;DR

- **A complete 10-task implementation plan exists and is committed** (`5923f0e`):
  `docs/superpowers/plans/2026-07-15-reporting-metrics-process-groupby-marking.md`. Nothing is
  implemented yet — this session was planning only (single-session recon → draft → self-red-team;
  every anchor Grep/Read-verified against `f20466d`).
- The feature (owner request + interactive Q&A): a **`page_count` = SUM(pagecount)** metric
  ("Pages processed") with TRY_CAST-safe numeric aggregation, **DB-localized metric labels**
  (new de/fr/it columns on `dbo.ReportingMetrics`, migration `0039`), and **process-coverage
  marking** in the Simple wizard — "n/m" badge + provider tooltip on partially-covered breakdown
  chips AND measure cards, chip list follows the scope picker like the Advanced tab (hide + prune).
- Owner **declined** distinct-count metrics and amount totals for now — they are Owner actions in
  the plan (pure registry rows / a decimal-cast swap once this plan lands).
- **The worktree stays open on purpose** — it is the execution vessel for `/execute-plan`.

## This session's commits

- `5923f0e` docs(plans): add reporting-metrics-process-groupby-marking plan
- (plus this handoff commit)

## What shipped

| Artifact | Path |
|---|---|
| Implementation plan (10 tasks, 7 phases) | `docs/superpowers/plans/2026-07-15-reporting-metrics-process-groupby-marking.md` |
| Planning worktree (KEEP — execution vessel) | `.claude/worktrees/plan-reporting-metrics-process-groupby-marking` on `plan/reporting-metrics-process-groupby-marking` |

Owner decisions locked in the plan (from AskUserQuestion): metric family = **pages processed only**;
chips = **badge + scope filtering**; metric labels = **localized via 4-column schema** (measure
badges were "no preference" → included, since `page_count` is itself the partial-coverage case).
Declared executor: **Sonnet** (commit blocks carry the Sonnet trailer + substitution note).

## Next steps (ordered)

1. **`/execute-plan`** in a fresh session — it must run **inside the worktree**
   (`.claude/worktrees/plan-reporting-metrics-process-groupby-marking`, branch
   `plan/reporting-metrics-process-groupby-marking`) and start at Task 1 of the plan. Every task is
   RED→GREEN with paste-ready commits.
2. The worktree's `env/INT.env` + `env/TEST.env` were already copied from the main clone this
   session (gitignored) — the SQL hooks need them.
3. Task 2 is the migration (**target `0039` — re-list `sql/_migrations/NexoraDB/` first**, the
   owner's queued validation-user re-map may take the number) and MUST also mirror the three new
   columns into `sql/test/schema.sql` (TEST DB is rebuilt from schema.sql, not migrations).
4. After execution: merge back into `feature/2.5.64` (execute-plan's `--merge-worktree` handoff
   does this), owner reviews and pushes.

## Gotchas & notes

- **~70 modified `sql/**` per-object dumps sit uncommitted in the worktree** — the pre-commit
  sync hook's CRLF/whitespace regeneration churn (same as the 07-14 session; the check itself
  Passed). Do NOT commit them wholesale; `git restore sql/` cleans it. Task 2's commit legitimately
  regenerates `sql/NexoraDB/Tables/dbo.ReportingMetrics.sql` — `git add` just that one.
- The plan **expects `tests/unit/test_translations.py` RED from Task 4 through Task 7** (single
  late pybabel cycle, five new msgids) — by design, don't "fix" it early.
- **TRY_CAST stays in `query.py`'s docprocessing projection** — never move it into
  `semantic.metric_select_expr`/`build_aggregate_sql` (shared with the possibly-PostgreSQL
  table-source builder).
- Coverage convention: a field with **no `processes` tag is universal** (no badge, never hidden) —
  that is what keeps every pre-existing e2e stub and all table sources untouched.
- `page_count` on INT/PROD only counts processes with `col_pagecount` mapped in `SearchConfig` —
  Task 10 checks live coverage; expanding it is owner data-config, not code (plan Owner action 2).
- AI catalogs deliberately keep the **English** metric `Label` (prompt-grounding stability); only
  `/api/reporting/metrics` localizes.

## Untracked / left for owner

- Main clone still has the junk `package.json`/`package-lock.json` at repo root (prior handoffs) —
  untouched.
- The uncommitted `sql/**` dump churn in the worktree (see Gotchas) — deliberately not committed.
- `var/handoff-pending` written in BOTH the main clone (pointing at this file via the worktree
  path) and the worktree — gitignored, never committed.

## How to verify (this handoff's claims)

```powershell
git -C C:\dev\nexora\.claude\worktrees\plan-reporting-metrics-process-groupby-marking log --oneline -3
# <handoff-commit>, 5923f0e docs(plans)…, f20466d feat(reporting)…
git -C C:\dev\nexora worktree list   # shows plan-reporting-metrics-process-groupby-marking
# The plan itself: 10 tasks, "Migrations needed: YES — target 0039"
```

## Resuming in a fresh session

`/execute-plan` (or `/reset-session` first) — this is the only 2026-07-15 handoff so the picker
should grab it; if not, use
`/reset-session docs/superpowers/handoffs/2026-07-15-reporting-metrics-process-groupby-marking-plan.md`.
Resume point: `docs/superpowers/plans/2026-07-15-reporting-metrics-process-groupby-marking.md`,
Task 1. **Worktree:** `.claude/worktrees/plan-reporting-metrics-process-groupby-marking`
**Branch:** `plan/reporting-metrics-process-groupby-marking`.
