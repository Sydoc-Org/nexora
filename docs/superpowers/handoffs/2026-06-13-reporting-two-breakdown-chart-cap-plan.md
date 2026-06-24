> **Superseded** → see [`2026-06-13-reporting-two-breakdown-chart-cap-execution.md`](2026-06-13-reporting-two-breakdown-chart-cap-execution.md) (execution complete).

# Handoff — two-breakdown chart cap fix: plan written (ready for /execute-plan)

- **Date:** 2026-06-13
- **Branch:** `feature/2.5.63`. **149 commits ahead of `origin/feature/2.5.63`** — commit-only
  (remote); owner pushes + opens the PR.
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-12-write-plan-execute-plan-workflow.md`
- **This session's commit:**
  - `97f7960` docs(plans): add two-breakdown chart cap fix plan
- **No worktree** was created (clean tree, not in a linked worktree) — `/execute-plan` runs in the
  main checkout `C:\dev\nexora`.

---

## TL;DR

1. **Plan written and committed** for the GitHub-issue bug: *"Reporting: Simple Builder with two
   group by's are not working on graph — Too many data points to chart…"*. Resume at
   `docs/superpowers/plans/2026-06-13-reporting-two-breakdown-chart-cap.md`.
2. **Root cause (verified):** `mountChart(def, columns, rows)` in
   `templates/js/_reporting_simple_js.html` runs a pre-pivot guard `if (rows.length > 50) {` **before**
   the `if (dims === 2) {` pivot. For two breakdowns the raw rows are the `(dim1 × dim2)` cross-product
   (e.g. 12 months × 8 sources = 96 rows), so it bails with the too-many-points note even though the
   pivot collapses to ~12 x-points. The server (`chart_render.py`) is already correct — it caps
   `x_order[:MAX_X]` / top-12 series **after** pivoting.
3. **Fix is one line:** scope the guard to `if (dims === 1 && rows.length > 50)`. Two-dim then flows
   to the existing correct post-pivot `xOrder > 50` guard + 12-series cap. Plus a server
   characterization unit test, an e2e no-note smoke pin, a CHANGELOG `### Fixed` bullet, and a manual
   browser smoke (the only real proof — see gotchas).
4. **Next:** `/execute-plan` (Sonnet) against the plan above — 6 tasks across 4 phases.

---

## What shipped this session

### Planning run (`97f7960`)

| File | Change |
|------|--------|
| `docs/superpowers/plans/2026-06-13-reporting-two-breakdown-chart-cap.md` | New. Full implementation plan: explore ×3 → dual drafts → adversarial red-team → merge. 6 tasks, 4 phases. |

The plan was produced by the `/write-plan` 7-agent workflow. **Fable 5 was unavailable** in this
account (the US-only restriction the autopilot work hit on 2026-06-13), so the run used the session
**Opus 4.8** model — the top available tier — instead of Fable. Every file/symbol/snippet anchor in
the plan was re-verified against the live repo before commit (see "How to verify").

**Red-team's load-bearing catch:** the Phase-1 recon brief said "create a `### Fixed` subsection" in
the CHANGELOG. That is **wrong** — `## [Unreleased]` (lines 7–700) already has a `### Fixed`
subsection (line 347) with Reporting-AI bullets. The plan **appends** to it; creating a second header
would render two Fixed sections in one release. Verified.

---

## Next steps

**Primary:** execute the plan —
`docs/superpowers/plans/2026-06-13-reporting-two-breakdown-chart-cap.md`

| # | Task | Files |
|---|------|-------|
| 1 | Server characterization unit test (cap-after-pivot, GREEN from start) | `tests/unit/test_reporting_chart_render.py` |
| 2 | The fix — scope guard to `dims === 1 && rows.length > 50` | `templates/js/_reporting_simple_js.html` |
| 3 | e2e no-too-many-points-note smoke pin | `tests/e2e/test_reporting_simple.py` |
| 4 | CHANGELOG `### Fixed` bullet (append, do NOT create header) | `CHANGELOG.md` |
| 5 | **Browser smoke — HARD GATE** (restart server first) | manual / Playwright |
| 6 | Run affected suites, confirm clean, stop | — |

**After this fix:** push `feature/2.5.63` + open PR → `main` (owner).

---

## Gotchas & notes

- **No automated test goes red on the client bug.** The JS guard isn't directly unit-testable, the
  server is already correct (so its unit test is green-from-start characterization, not red-first),
  and TEST `dbo.Users` cardinality (Locale = 1 distinct X, Username = 3 series) **cannot** exceed 50
  pivoted x-points — so the e2e cannot reproduce it either. **Task 5's manual browser smoke is the
  only genuine proof** — treat it as a hard gate, not optional.
- **Anchor on the quoted `if (rows.length > 50) {` snippet, never a line number.** The `dims === 2`
  block is concurrently targeted by the in-flight drill-through plan
  (`docs/superpowers/plans/2026-06-11-reporting-drill-through.md`), which stashes
  `state.chartData.rawX = xOrder;` / `rawSeries` **inside** that block. The guard sits *above* it, so
  this fix lands cleanly/independently; whichever PR lands second re-anchors on the snippet.
- **Restart the dev server before browser-verifying** — Jinja caches templates for the process
  lifetime; without a restart you see the old `.html`.
- **Use verified seed columns only** in the e2e: `dbo.Users` has `username` + `locale` (both used by
  the existing `test_two_breakdown_chart_has_series`). There is **no** `Name` column on `Users`
  (`Name` belongs to `dbo.Reports`) and no `Format` column — inventing one 500s the source query.
- **`git commit -m '<subject>' -m '<body>'`, not `git commit -F -`** (the harness pipes nothing to
  stdin). The plan's per-task commit bodies contain no single quotes.
- **`SQL_SYNC_SKIP=1`** before commits is still the documented hatch — though this session's commit
  hooks actually **passed** (INT was reachable; the SchemaMigrations CRLF drift did not bite this
  time). Keep the hatch ready in case INT is down next session.

---

## Untracked / left for owner

- **`M bin/nx.ps1` and `M tools/autopilot/run-phase.ps1`** are uncommitted but **not mine** — they
  are pre-existing autopilot edits from the prior session. I deliberately staged **only** the plan
  file. Do not sweep them into an unrelated commit.
- **Push + PR**: 149 commits ahead of `origin/feature/2.5.63`. Owner pushes and opens the PR.

---

## How to verify

```powershell
cd C:\dev\nexora

# The plan file exists and its anchors are real (spot-check a few):
Get-Content docs\superpowers\plans\2026-06-13-reporting-two-breakdown-chart-cap.md -TotalCount 3
git log -1 --stat 97f7960

# The bug anchor + the server precedent (both verified this session):
#   client guard:
Select-String -Path templates\js\_reporting_simple_js.html -Pattern 'if \(rows.length > 50\) \{'
#   server caps post-pivot:
Select-String -Path nx_lib\reporting\chart_render.py -Pattern 'x_order = x_order\[:MAX_X\]'

# Affected suites (after executing the plan):
python -m pytest tests/unit/test_reporting_chart_render.py -q
```

---

## Resuming in a fresh session

```
/reset-session docs/superpowers/handoffs/2026-06-13-reporting-two-breakdown-chart-cap-plan.md
```

Then execute the plan (Sonnet recommended for execution):

```
/execute-plan
```

Read the plan before touching code:
`docs/superpowers/plans/2026-06-13-reporting-two-breakdown-chart-cap.md`

Start with Task 1 (server characterization unit test). TDD discipline: write the test, run it
(green-from-start here), then make the one-line client fix in Task 2.
