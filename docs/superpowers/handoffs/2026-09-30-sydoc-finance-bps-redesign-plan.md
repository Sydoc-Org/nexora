> **Superseded:** the next handoff is [`2026-09-30-sydoc-bps-redesign-shipped.md`](2026-09-30-sydoc-bps-redesign-shipped.md). Resume from there.

# Handoff — Sydoc Finance + BPS redesign: plan written, not started

**Date:** 2026-09-30 · **Branch:** `plan/sydoc-finance-bps-redesign` in the worktree
`.claude/worktrees/plan-sydoc-finance-bps-redesign` (cut from `main` @ `fd17c21b`, after #425) ·
3 ahead of `main`, **nothing pushed** · this handoff is commit-only (remote) · no issue yet.

**Prior handoff:** [`2026-09-29-sydoc-finance-page-shipped.md`](2026-09-29-sydoc-finance-page-shipped.md)

## This session's commits

- `87a74c0c` docs(design): add the Sydoc Finance + BPS redesign handoff: the design bundle from
  `Sydoc pages redesign.zip` (Downloads) → `docs/design/design_handoff_sydoc_finance_bps/`
- `08b4df61` docs(plans): add sydoc-finance-bps-redesign implementation plan
- (this handoff)

## TL;DR

- The owner handed over a high-fidelity redesign of `/finance` and `/bps`. The approved option is
  **1a** in the two `.dc.html` prototypes, and `README.md` there is the spec with every px and hex.
  The two pages get a shared ink header band with the Sydoc mark and orange accent, the period as
  a 54px headline and a picker modal. Finance gets a ledger layout and a timeline of billable
  bookings. BPS gets totals, a composition bar and a zoomable Table/Treemap drill-down with
  gain/loss vs the previous period.
- **The plan is written** (`docs/superpowers/plans/2026-09-30-sydoc-finance-bps-redesign.md`, 29
  tasks in 6 phases). Owner decision: branch off `main` (not the Bexio branch). **No code has been
  written.**
- **The sequencing constraint is #423.** The uncommitted Bexio panel work on
  `feat/423-finance-bexio` edits `finance.html`, `_finance_js.html`, `finance.css` and
  `finance.py`, which are the same files PHASE 4 rewrites. So BPS (PHASE 1–3) can start now, and
  Finance (PHASE 4) is gated on #423 merging (plan Task 21).
- No migration, no new permission. Backend additions: `bps.previous_range/next_range`,
  `bps.months_query/months_payload`, `prev` on `/api/bps/summary`, a new `GET /api/bps/months`,
  and `Section.nav` in `nx_lib/finance.py`.

## What shipped

| what | files | commit |
|---|---|---|
| Design bundle (prototypes, spec README, ISSUE.md, assets) | `docs/design/design_handoff_sydoc_finance_bps/*` | `87a74c0c` |
| Implementation plan | `docs/superpowers/plans/2026-09-30-sydoc-finance-bps-redesign.md` | `08b4df61` |
| This handoff | `docs/superpowers/handoffs/2026-09-30-sydoc-finance-bps-redesign-plan.md` | (this commit) |

## Next steps

1. **Owner: file the issue** from `docs/design/design_handoff_sydoc_finance_bps/ISSUE.md` (plan →
   Owner actions 1). Its number names the branch `feat/<n>-sydoc-redesign` and the `(#<n>)` in
   every commit and changelog entry.
2. **Owner:** copy `env/INT.env` + `env/TEST.env` into the worktree's `env/` before the first
   browser check (plan Task 20). Optionally install Node LTS so the JS unit tests stop skipping.
3. **Execute** with `/execute-plan`, starting at **plan Task 0** (cut `feat/<n>-sydoc-redesign`
   from `plan/sydoc-finance-bps-redesign` in this worktree). Run PHASE 1 → 3 (shared foundation,
   BPS backend, BPS front end; Tasks 1–20).
4. **Stop at Task 21** unless #423 is on `main`. Then rebase, regenerate translations (never
   hand-merge `.po`), and do PHASE 4 (Finance, Tasks 22–27) and PHASE 5 (docs, Tasks 28–29).

## Gotchas & notes

- **Never touch `C:\dev\nexora`.** That checkout is on `feat/423-finance-bexio` with ~30
  uncommitted files of Bexio work (`nx_lib/bexio.py`, migration `0141`, etc.). Everything for this
  feature happens in the worktree.
- **The README is stale on BPS history.** It says there is "No data before 3 Aug 2026", but #424
  moved the start to **3 Jan 2025**. The plan derives "No data" from per-month hours instead (D5)
  and fixes the old `emptyPeriod` string in `_bps_js.html` (Task 12).
- **No e2e covers `/finance` or `/bps`.** The README's "update e2e selectors" has no target. The
  integration tests (`tests/integration/test_{finance,bps}_routes.py`) pin the markup instead and
  are updated in the plan, but they only run in CI (placeholder `TEST.env` locally).
- **Node is missing on the dev box.** The new JS tests follow `test_reporting_layout_view_js.py`
  and skip without it.
- **Commits here need** `$env:PATH = "C:\dev\nexora\.venv\Scripts;$env:PATH"` and
  `SQL_SYNC_SKIP=1`. `mssql-scripter` is not installed, so `sql-sync-check` crashes. The
  `mixed-line-ending` hook rewrites CRLF in new `.md` files: re-`git add` and commit again.
- The `superpowers:writing-plans` SKILL.md was not found on this machine (a background `find`
  over `/` was started and never used). The plan follows the format of the two most recent plans.
- Planning verified the `months_query` SQL (`DATEFROMPARTS(YEAR([Datum]), MONTH([Datum]), 1)`,
  `params == []`, a NULL-month bucket possible) and the `previous_range` / `next_range` logic by
  execution. All plan anchors were grepped against the tree.

## Untracked / left for owner

- Nothing untracked in the worktree. The extracted zip copy in the session scratchpad is
  disposable.
- The issue is **not filed**: posting it is visible to others, so it is left to the owner.

## How to verify

```powershell
Set-Location C:\dev\nexora\.claude\worktrees\plan-sydoc-finance-bps-redesign
git log --oneline main..HEAD          # 3 commits: bundle, plan, handoff
git ls-files docs/design/design_handoff_sydoc_finance_bps
```

No code changed, so there is no test suite to run. The unit tier is green on `main` @ `fd17c21b`
per CI.

## Resuming in a fresh session

`/reset-session` picks this file (newest date). Read it, then
`docs/superpowers/plans/2026-09-30-sydoc-finance-bps-redesign.md` (Context + Decisions + Owner
actions first), then `docs/design/design_handoff_sydoc_finance_bps/README.md`. Resume at **plan
Task 0**, in the worktree above, once the owner has filed the issue.
