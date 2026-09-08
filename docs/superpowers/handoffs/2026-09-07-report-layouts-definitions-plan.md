# Handoff — report layouts ("Report definitions"): spec approved, plan written, ready to execute

**Date:** 2026-09-07 · **Branch:** `plan/report-layouts` in worktree
`.claude/worktrees/plan-report-layouts` (cut from `refactor/255-admin-nav-tenancy-labels` @ `49a400c5`)
· 2 commits ahead of the parent branch, nothing pushed · commit-only — the owner pushes.

**Prior handoff:** [`2026-09-07-wizard-curation-and-dashboard-pieces.md`](2026-09-07-wizard-curation-and-dashboard-pieces.md)
(same date — pass this file's path to `/reset-session` explicitly).

## This session's commits (oldest → newest)

| Commit | Where | What |
|---|---|---|
| `49a400c5` | `refactor/255-admin-nav-tenancy-labels` (main checkout) | `docs/superpowers/specs/2026-09-07-report-layouts-design.md` — approved design |
| `0d999776` | `plan/report-layouts` (worktree) | `docs/superpowers/plans/2026-09-07-report-layouts-definitions.md` — 16-task implementation plan |

## TL;DR

1. **Owner asked for user-authored "report definitions"**: reusable bundles of derived measures
   (delta, growth, mean, min/max, percentile, target gap …) plus a drag-and-drop layout, picked
   before building a report. Brainstormed → scope locked (see spec table) → spec written and approved
   → plan written, anchors verified, committed. **No product code changed.**
2. **Code name is `layout`** (`kind: 'layout'` saved report, `layoutId` on a report definition,
   `derived` in the run payload); only UI strings say "Report definition". "Definition" already means
   the saved report JSON everywhere in code.
3. **v1 scope**: basics only (current, mean, minmax, range, stddev, percentile); charts bar /
   stacked bar / line / area / pie / doughnut / gauge + KPI sparkline; 12-col tile grid reusing the
   dashboard engine; private per user; computed server-side; applies to the result view (not
   dashboards). Change/target measures, sharing, dashboards-honouring-layouts are explicit follow-ups.
4. **Two plan-time deviations from the spec**, recorded as D1/D2 in the plan: the editor is a fifth
   Simple-pane Console screen (`definitions`) with `/reporting/definitions` redirecting into it, not a
   separate template; layouts are validated on save (nothing else is today).

## What shipped

Docs only:

| File | Commit |
|---|---|
| `docs/superpowers/specs/2026-09-07-report-layouts-design.md` | `49a400c5` |
| `docs/superpowers/plans/2026-09-07-report-layouts-definitions.md` | `0d999776` |
| this handoff | (see below) |

## Next steps (ordered)

1. `/execute-plan` on **`docs/superpowers/plans/2026-09-07-report-layouts-definitions.md`**, inside
   the worktree `.claude/worktrees/plan-report-layouts` (branch `plan/report-layouts`). Start at
   **Task 1** (`nx_lib/reporting/derived.py`).
2. **Before Task 1**: `cp ../../../env/INT.env ../../../env/TEST.env env/` into the worktree and
   `git log --oneline HEAD..refactor/255-admin-nav-tenancy-labels` — if non-empty, merge the parent
   in first. Two peer sessions were committing reporting work there during this session; Tasks 5–12
   edit `run.py`, `reporting_simple.js`, `reporting_advanced.js`, `reporting_dashboard.js`.
3. Repeat the merge check before Task 6 (grid extraction) and before merging back.
4. When done: `/handoff-session-state --merge-worktree` merges `plan/report-layouts` into the parent
   and deletes the worktree.

## Gotchas & notes

- **Dashboards are the precedent for everything.** A dashboard is a `kind:'dashboard'` saved
  report living as a Simple-pane view with its own drag/resize grid in `reporting_dashboard.js`.
  Layouts copy that exactly; Task 6 lifts the grid engine into `static/js/reporting_grid.js` and the
  20-test dashboard e2e is the gate.
- **`kind: 'layout'` rows leak into every report-list consumer** (`navTo`, `loadLibrary` grouping,
  rail counts, Advanced saved-reports dropdown). Plan Tasks 7/8/11 filter each; Grep
  `kind !== 'dashboard'` once more at the end.
- **No JS test runner exists.** The plan adds the repo's first Node-driven JS tests
  (`tests/unit/test_reporting_grid_js.py`, `test_reporting_layout_view_js.py`) — pure helpers only,
  `node -e` harness with a stub `window`. Node 22 is installed.
- **Schedules do not get `derived`** (plan D5): `runner.py::execute_definition` is a separate
  pipeline. Export and Ask-Eddard do.
- **Worktree pre-commit**: SQL hooks passed here without `SQL_SYNC_SKIP` (INT reachable), but a
  fresh worktree has no `env/*.env`, so use `SQL_SYNC_SKIP=1` if they fail.
- Peer sessions active at the time: two interactive sessions on the main checkout with uncommitted
  reporting changes. Never stage files in the main checkout from the worktree session.

## Untracked / left for owner

- Main checkout `C:\dev\nexora` carries peer sessions' uncommitted work (`docs/*.drawio`,
  `docs/architecture/`, reporting JS/CSS/run.py). Not touched, not committed here.
- Owner decision parked in the plan's "Owner actions": whether scheduled mails should carry the
  Measures block.

## How to verify

Nothing runnable landed. Sanity:

```bash
git -C C:/dev/nexora worktree list          # plan-report-layouts on plan/report-layouts
git -C C:/dev/nexora/.claude/worktrees/plan-report-layouts log --oneline -3
```

## Resuming in a fresh session

`/reset-session docs/superpowers/handoffs/2026-09-07-report-layouts-definitions-plan.md` (explicit path —
three handoffs share this date). Then read the plan and run `/execute-plan` in the worktree.
