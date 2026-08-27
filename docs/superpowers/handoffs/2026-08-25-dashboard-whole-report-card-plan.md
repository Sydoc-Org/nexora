# Handoff — Plan: dashboard "Whole report" card (+ Reporting BEFORE screenshots for Claude Design)

**Date:** 2026-08-25 · **Branch:** `plan/dashboard-whole-report-card` in worktree
`.claude/worktrees/plan-dashboard-whole-report-card` (cut from `v3.2.3.1` @ `33b42f4c`, then
**rebased onto the `v3.2.3.1` tip `b35feb23`** the same day — a plain fast-forward wasn't possible
because the plan commits had already landed) · **3 commits on the plan branch, unpushed** ·
commit-only (owner pushes) ·
**clean tree** (worktree). Main checkout `C:\dev\nexora` is on `v3.2.3.1`, clean, not touched by this
session.

**Prior handoff:**
[`2026-08-25-reporting-audit-wounds-fixed.md`](2026-08-25-reporting-audit-wounds-fixed.md)
(same day, a **peer** session — audit wounds fixed, `48a08364`; the plan below is written against
that tip). Three handoffs share today's date — `/reset-session` must be given this file's path
explicitly (the `var/handoff-pending` flag already carries it).

## TL;DR

- Owner asked (via `/write-plan`) for **two things**: (1) screenshots of the Reporting page *as it
  looks now* for Claude Design, in a folder named `_forclaudedesign`; (2) a **Sonnet-executable plan**
  so the editable dashboard on the Reporting page can import a saved report **whole** — not selected
  pieces (KPI / chart / table / donut) — i.e. everything the Simple tab shows.
- (1) done: **19 screenshots** in `var/screenshots/_forclaudedesign/` (gitignored; STAGING data,
  locale de, light + dark). Three were sent to the owner in-chat.
- (2) done: plan committed as `8a69e457` (rebased; originally `c8f7d917`) —
  `docs/superpowers/plans/2026-08-25-dashboard-whole-report-card.md` (1110 lines, 9 tasks, 2 phases,
  every anchor verified against `48a08364`, zero placeholders). **Not executed.**
- Architecture chosen: expose the Simple pane's result renderers as pure builders on
  `window.ReportingSimple` (`kpiBandHtml`, `statCardHtml`, `buildChartData`, `chartConfigFor`,
  `tableHtml`, `ensureCatalogs`, …) and make the dashboard's existing `'report'` card type render
  through them ("Whole report" pill). No backend, no migration, no new permission.

## This session's commits (plan branch)

| Hash | What |
|---|---|
| `8a69e457` | docs(plans): add dashboard-whole-report-card implementation plan (was `c8f7d917` before the rebase) |
| `811226ca` | docs(handoff): dashboard-whole-report-card plan (was `cb7ec529`) |
| *(this)* | docs(handoff): note the rebase onto v3.2.3.1 in plan + handoff |

## What shipped

**Plan** — `docs/superpowers/plans/2026-08-25-dashboard-whole-report-card.md`
- Phase 1 (Tasks 1–5, `templates/js/_reporting_simple_js.html`): split `renderKpiBand`,
  `fillStatCard`, `mountChart`, `renderChart`, `renderTable` into pure builders + thin DOM wrappers;
  expose on `window.ReportingSimple`; guard = a growing
  `test_reporting_simple_exposes_result_builders` e2e + slices of the 86-test Simple suite; Task 5 =
  full-suite gate.
- Phase 2 (Tasks 6–9, `templates/js/_reporting_dashboard_js.html`, `static/css/reporting.css`,
  `tests/e2e/test_reporting_dashboard.py`, help + guide + changelog, de/fr/it): rewrite
  `renderReportCard` (stat card via zero-column clone run, KPI band with `compare: true`, chart via
  `chartConfigFor` incl. saved colours/right axis/forecast, full table behind Show table, drill on
  chart + rows, `rdb-` prefixed testids), pill label "Whole report", docs, i18n cycle.
- Decisions D1–D9 + Owner actions in the plan header; the in-flight audit helpers
  (`noteDataQuality`, `appendChartNote`, `metricTotalModes`, `xCap`, partial-bucket `grain0`) are
  folded into the extraction tables as definite steps (they landed in `48a08364`).

**Screenshots** — `var/screenshots/_forclaudedesign/` (19 PNG, 1440×900, STAGING as `ben.streich`):
`01*` library (viewport/full) · `02` wizard step 1 · `03*` DEMO result view (+ colours/axes popover,
table open, ⋯ menu) · `04*` new dashboard edit mode, report picker, **today's lossy "Bericht" card =
BEFORE** · `05*` saved dashboard view/edit · `06*` Advanced tab · `07` help modal · `08*` dark mode.
Made with the scratchpad Playwright scripts (own headless Chromium; the Playwright MCP profile was
locked by a peer). Nothing was saved to the DB (dashboards closed via Back, no Done).

## Next steps (ordered)

1. ~~Fast-forward~~ **done** — the plan branch already sits on `b35feb23` (rebased 2026-08-25). Only if
   `v3.2.3.1` moves again: owner runs/authorizes `git rebase v3.2.3.1` in the worktree, because
   Tasks 2–3 extract function bodies that only exist in their current form after `48a08364`.
2. `/execute-plan` in the worktree → `docs/superpowers/plans/2026-08-25-dashboard-whole-report-card.md`,
   start at **Task 1**. Executor model per the owner: Sonnet (commit trailers in the plan already say
   `Claude Sonnet 5`). Do **not** pass `--merge-worktree` until execution finishes.
3. After execution: owner merges `plan/dashboard-whole-report-card` → `v3.2.3.1`, pushes, deletes
   worktree + branch (Owner action 2 in the plan).
4. Hand the `_forclaudedesign` folder to Claude Design (owner's separate flow; nothing in-repo).

## Gotchas & notes

- **Anchor drift risk:** the plan quotes code from `48a08364`. If more reporting commits land on
  `v3.2.3.1` before execution, re-Grep the Task 1–4 anchors (the plan says so in its header).
- **Peer activity is heavy on this branch today** — two other sessions (`nexora-c0` on worktree
  `C:\dev\nexora-c0` / `v3.2.3.2`, plus the owner's session) committed `3bbab717`, `33b42f4c`,
  `48a08364`, `b35feb23` while this plan was written. `ListAgents` before touching
  `_reporting_simple_js.html`; `nexora-c0` owns the AI caption fact-sheet rewrite (`caption_facts.py`,
  `fireCaption`) — the plan never touches those.
- **Dev servers:** port 8000 (PID 23852) is someone else's INT/STAGING instance — leave it. The port
  8001 instance (PID 13144) disappeared around the time this session stopped its own 8002 instance
  (`nx -d --port:8002` reported stopping PID 33228); most likely the peer stopped theirs, but if 8001
  was the owner's, restart with `& C:\dev\nexora\bin\nx.ps1 -u --env:staging --no-conflict`.
- **Playwright MCP** ("Browser is already in use … mcp-chrome-3a4f3d4") was held by a peer — don't
  kill it; use a `.venv` Playwright script instead (pattern in this session's scratchpad, or copy the
  e2e helpers).
- **Worktree has no `env/*.env`** (gitignored) → the `sql-migrate-int` / `sql-sync-check` hooks fail
  with "Missing DB_SERVER_PRD"; commit there with `SQL_SYNC_SKIP=1 git commit …` (never `--no-verify`).
- **Why no forward-pointer banner on the older same-date handoffs:** both live in the main checkout /
  `v3.2.3.1` history, not on this branch; editing them here would only create a merge conflict. The
  `var/handoff-pending` flag points at this file by path instead.
- Card model reminder: saved dashboards persist `type:'report'`; the plan upgrades that type in place
  — never rename `rdb-add-report` / `data-add-type="report"` / `DEFAULT_SPAN.report`.

## Untracked / left for owner

- `var/screenshots/_forclaudedesign/*.png` — gitignored evidence for Claude Design (19 files).
- Scratchpad scripts (`shoot_reporting.py`, `shoot_reporting2.py`, `verify_plan_anchors.py`) live in
  the session scratchpad, not in the repo — recreate from the plan's e2e helpers if needed.
- The worktree + branch stay open on purpose (execution vessel). Push is the owner's call.

## How to verify

```powershell
git -C C:\dev\nexora worktree list          # plan worktree present on plan/dashboard-whole-report-card
git -C C:\dev\nexora\.claude\worktrees\plan-dashboard-whole-report-card log --oneline -3
Get-ChildItem C:\dev\nexora\var\screenshots\_forclaudedesign | Measure-Object   # 19 files
```
No test suite was changed this session; nothing is red. (Full gates for the plan itself are listed
per task inside the plan.)

## Resuming in a fresh session

`/reset-session .claude/worktrees/plan-dashboard-whole-report-card/docs/superpowers/handoffs/2026-08-25-dashboard-whole-report-card-plan.md`
(explicit path — three handoffs share this date; the flag file already holds this path). Then
"Next steps" 1 → 2.
