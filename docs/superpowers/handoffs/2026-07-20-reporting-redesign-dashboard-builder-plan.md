# Handoff — Indigo Studio reporting redesign + dashboard builder: PLAN written, ready to execute

**Date:** 2026-07-20 · **Branch:** `feature/2.5.64` (no worktree — branch was clean at planning
time) · **4 commits ahead of origin, unpushed** · **commit-only — owner pushes**
**Prior handoff:** `2026-07-15-reporting-metrics-process-groupby-marking-execution-complete.md`

## TL;DR

- **A complete 17-task / 8-phase implementation plan exists and is committed** (`e45559e`):
  `docs/superpowers/plans/2026-07-20-reporting-redesign-dashboard-builder.md`. Nothing is
  implemented yet — this session was planning only (single-session recon → draft → self-red-team;
  every anchor Grep/Read-verified against `ba2e499`).
- The feature: the owner's **design handoff** (from `C:\Users\bes\Downloads\Reporting page
  redesign`) — full "Indigo Studio" restyle of `/reporting` (landing hero + AI command bar +
  live-preview report cards, progress-rail wizard, refined result view, drill-drawer + Advanced
  reskins, dark mode, Editorial-Ledger retirement) **plus a new multi-card dashboard builder**
  (`kind:'dashboard'` saved reports: KPI/line/bar/donut/table cards, global filters, per-card
  overrides, HTML5 drag-reorder, Edit/Done autosave). **Zero backend changes** — `kind` already
  lives in `DefinitionJSON`.
- The design spec is **in-repo now**: `docs/superpowers/specs/2026-07-20-reporting-redesign-handoff.md`
  (values/fidelity contract) + `…-reporting-dashboard-prototype.dc.html` (the dashboard JS state
  model spec). The big static mock stays in the owner's Downloads folder (pixel reference).
- Owner decisions (AskUserQuestion): **supersede** the un-executed 2026-07-15 pin-to-dashboard
  plan (Task 17 stamps it); **one phased plan**, redesign first, dashboard builder after.

## ⚠️ Concurrent-session warning (read before touching the tree)

At commit time a **second session was actively editing this same clone**: uncommitted changes to
`CHANGELOG.md`, `nx_lib/views/generali.py`, `templates/js/_generali_base_services_js.html`
(generali POE/PPR category split) and `static/css/nexora-ui.css` (nx-table `th` alignment fix,
issue #121). **Do not stage, revert, or "clean up" those files** — they belong to the other
session. The first commit attempt here failed because pre-commit's stash/restore collided with
those writes; committing with `SQL_SYNC_SKIP=1` (shorter hook window) worked. If they're still
uncommitted when execution starts, keep every `git add` in this plan **path-explicit** (the plan
already writes them that way — never `git add -u` / `git add .`).

## This session's commits

- `e45559e` docs(plans): add reporting-redesign-dashboard-builder plan (+ the two spec files)
- (plus this handoff commit)

The three other unpushed commits (`efe13d8`, `1ff7361`, `ba2e499` — workitems fixes) predate this
session; they ride along when the owner pushes.

## What shipped

| Artifact | Path |
|---|---|
| Implementation plan (17 tasks, 8 phases) | `docs/superpowers/plans/2026-07-20-reporting-redesign-dashboard-builder.md` |
| Design spec (fidelity contract, committed copy of the handoff README) | `docs/superpowers/specs/2026-07-20-reporting-redesign-handoff.md` |
| Dashboard prototype (JS state-model spec) | `docs/superpowers/specs/2026-07-20-reporting-dashboard-prototype.dc.html` |

Key locked decisions (full table in the plan): dashboards are saved reports with
`kind:'dashboard'` definitions through the existing CRUD (no migration, no new endpoints, no new
permissions); dashboards render as a **fourth Simple-pane view** via a new
`templates/js/_reporting_dashboard_js.html` partial; library previews come from a localStorage
last-run cache (never N runs on landing); result header gains a `⋯` menu hosting
`rsOpenAdvanced`/`rsShowSql` (ids kept, a few e2e tests gain one menu-click); ledger skin is
rewritten **in place** (class names survive); every `data-testid` survives.

## Next steps (ordered)

1. **`/execute-plan`** in a fresh session, directly on `feature/2.5.64`, starting at
   **Phase 1 / Task 1** of the plan. Tasks are bite-sized with paste-ready commit blocks
   (`Claude Fable 5` trailers — substitute the real executor).
2. Read the two spec files before Task 1 — the plan references them as "spec §…" throughout.
3. Phases 1–6 are the restyle (each independently shippable); Phases 7–8 are the dashboard
   builder + dark mode/chores. `/execute-plan` reviews per phase.
4. After execution: owner reviews, pushes (pre-push gate runs the FULL suite — run
   `scripts/test_db_reset.py` first, per memory).

## Gotchas & notes

- **i18n is ONE late cycle (Task 17)** — `tests/unit/test_translations.py` is expected RED from
  Task 3 onward; the fast tier deselects it. Don't "fix" it early.
- **The 61-test `test_reporting_simple.py` suite is the contract** — presentational assertion
  updates are allowed (menu-open step, group order), flow changes are not.
- The plan's Task 14 approximates "drop a saved report here" with a click-to-pick list (real
  cross-view drag is an upgrade path — the prototype doesn't implement it either).
- KPI trends (Task 15) only render when a card's effective filters hold exactly one date-range
  filter — second shifted run, "vs previous period". Honest numbers or nothing.
- `DefinitionJSON` cap is `64_000` chars (`api_reports_create`) — bounds dashboards at ~10–15
  cards; no client-side pre-check in v1.
- The un-executed **pin-to-dashboard plan is superseded** but its file is only stamped in
  Task 17 — until then don't accidentally execute it.

## Untracked / left for owner

- The concurrent session's four modified files (see warning above) — **theirs, not ours**.
- Two stray root files (`package.json`, `package-lock.json`) may exist — never commit them.
- Owner keeps `Reporting Redesign.dc.html` in Downloads until execution finishes (mock reference).

## How to verify

```powershell
git log --oneline -3          # e45559e (plan) + this handoff on top
git show e45559e --stat       # 3 files, ~1486 insertions, docs only
.\.venv\Scripts\python -m pytest tests/unit -q   # untouched — green baseline
```

No code changed this session — the full suite state is whatever `ba2e499` left (green at its
commit time).

## Resuming in a fresh session

`/reset-session` lands here via `var/handoff-pending`. Then: open
`docs/superpowers/plans/2026-07-20-reporting-redesign-dashboard-builder.md`, read the two spec
files, and start `/execute-plan` at Task 1. (If another 2026-07-20 handoff appears later,
`/reset-session docs/superpowers/handoffs/2026-07-20-reporting-redesign-dashboard-builder-plan.md`
targets this file explicitly.)
