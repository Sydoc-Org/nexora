# Handoff — beautification Phase 0+1 planned, ready for /execute-plan

**Date:** 2026-08-31 · **Branch:** `v3.2.4.1` (main checkout, no worktree) · **2 commits ahead of
origin, unpushed** · owner pushes · plan-only session, nothing executed yet.

**Prior handoffs:** the pending flag pointed at
[`2026-08-27-reporting-dashboard-mask-resize-delete-label.md`](2026-08-27-reporting-dashboard-mask-resize-delete-label.md)
(**never consumed** — this session did unrelated work; check whether that reporting-dashboard work
still needs finishing). Newest before that:
[`2026-08-27-v323-release-prep-gate-red.md`](2026-08-27-v323-release-prep-gate-red.md) (6 red
dashboard tests blocking a deploy — status unknown to this session, v3.2.3 may have shipped since).

## TL;DR

- Five parallel audit agents measured the whole codebase (views structure, dead code, frontend JS,
  lint/typing gap, performance with live timings). Findings are distilled into the plan — the raw
  audit detail beyond it lived only in this session.
- **The deliverable:** `docs/superpowers/plans/2026-08-31-beautify-phase-0-1.md` (commit
  `e03c320d`) — Phase 0 (dead code, perf freebies, lint ratchet) + Phase 1 (nx_core.js dedupe,
  generali/admin view packages, descriptor CRUD factory = the white-label tenant-module pattern).
- Owner decisions locked: delete `tools/autopilot/`; keep `/jdvance` + the Anthropic AI path;
  **generali split runs BEFORE the #220 Generali DB restructure** (its executor re-greps anchors).
- Phase 2/3 (reporting/workitems splits, shim-ification, `COUNT(*) OVER()` perf, typing ratchet)
  are named in the plan's follow-on section — not yet green-lit.

## What shipped

| Commit | What |
|---|---|
| `e03c320d` | the Phase 0+1 implementation plan (docs only) |
| this file | handoff |

## Next steps

1. `/execute-plan` on `docs/superpowers/plans/2026-08-31-beautify-phase-0-1.md` — start at
   Task 1. Work in a worktree cut from `v3.2.4.1` (plan's Context section has the command).
2. Owner, separately: **revoke the June autopilot PAT** (plan's Owner actions — deleting the
   directory does not revoke the token).
3. **The full campaign queue is planned** (commit `f60909bd`), execute in this order after 0+1:
   `2026-08-31-beautify-phase-2a-backend-splits.md` (reporting/workitems splits),
   `2026-08-31-beautify-phase-2b-frontend-shims.md` (#191 shim-ification + reporting_simple split),
   `2026-08-31-beautify-phase-2c-perf-mediums.md` (independent — may run parallel in own worktree),
   `2026-08-31-beautify-phase-3-typing-ratchet.md` (last). Re-grep all anchors at execution time.
4. Passkey login is captured as issue #237 — sequenced after the campaign, post-Cloudflare cutover.

## Gotchas & notes

- **Working tree carries peer-session noise, deliberately uncommitted:** 11 modified
  `sql/NexoraDB/Tables/*.sql` dumps + 2 untracked (`dbo.KundenmagazinIssues.sql`,
  `dbo.KundenmagazinIssueOrganizations.sql`) — the sql-sync hook re-dumped INT during this
  session's commit and someone's Kundenmagazin tables came along. They belong to whatever session
  created those tables; do **not** bundle them into beautification commits. Both plan and handoff
  commits used `SQL_SYNC_SKIP=1` for this reason.
- The plan's every path/symbol was verified against `v3.2.4.1` HEAD `0da9f522` on 2026-08-31 —
  re-grep anchors before editing, as always.

## How to verify

```
git log --oneline -3          # e03c320d + the handoff commit on v3.2.4.1
ls docs/superpowers/plans/2026-08-31-beautify-phase-0-1.md
```

## Resuming in a fresh session

`/reset-session docs/superpowers/handoffs/2026-08-31-beautify-phase-0-1-plan.md`, then read the
plan file and `/execute-plan`. No other 2026-08-31 handoff exists; the pending flag points here.
