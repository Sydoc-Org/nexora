# Handoff — autopilot-concurrent-issues plan written

**Date:** 2026-06-15 (plan-only session) · **Branch:** `feature/2.5.63` · **1 commit unpushed this session** · **commit-only (remote)**
**Prior handoff:** `docs/superpowers/handoffs/2026-06-15-clearer-execution-titles-plan.md`
**Durable context also in auto-memory:** `project_n8n_autopilot`, `project_autopilot_recovery_layer` (the autopilot loop + recovery layer this builds on).

## TL;DR

- A `/write-plan` run produced an implementation plan for the GitHub issue *"n8n multiple agents
  working on multiple issues at once"* — run the autopilot on **up to 3 issues concurrently**.
- **Deliverable is the plan only** — no code change yet. Resume at
  `docs/superpowers/plans/2026-06-15-autopilot-concurrent-issues.md`.
- The feature: a **3-slot semaphore** (replaces the global single-run lock); **one git worktree per
  issue** on a fresh `auto/issue-NN` branch off `feature/2.5.63`; plan+execute run **in that worktree
  on that branch**; **serialized merge-back** onto `feature/2.5.63` in **completion order** (one lane
  writes the shared branch at a time); a **separate merge-resolver `claude -p` agent** for conflicts;
  **per-issue pause-on-failure** (other lanes continue); a **serialized DB lock** for the build/test
  step (shared INT/TEST DB); excess issues beyond 3 just **queue**.

## This session's commits (only one authored here)

```
30523a2 docs(plans): add autopilot-concurrent-issues implementation plan
```

## What shipped

| Area | File | Commit |
|------|------|--------|
| Plan | `docs/superpowers/plans/2026-06-15-autopilot-concurrent-issues.md` (1411 lines) | `30523a2` |

The plan was produced by a 7-agent Workflow (3 explore → 2 dual drafts → red-team → merge).
**Fable 5 was unavailable** (Mythos-access outage), so the agents ran on **Opus** instead of Fable.
The first launch also crashed on a stray backtick in a template literal (fixed, then re-run). The
red-team agent attacked both drafts against the live repo; **all 14 findings were resolved** in the
merge. After the merge a dedicated verification agent re-checked **every** file path, quoted snippet,
symbol, and load-bearing claim against the live repo → **NO MISSES**.

## The load-bearing design decision (read before executing)

The spec (`docs/superpowers/specs/2026-06-14-autopilot-clarify-and-parallel-design.md`, Section 2)
originally chose **clones, not worktrees**. The **owner overrode to worktrees**. This is reconcilable
**only** because the plan makes `--merge-worktree` never fire in the lane path:

- A lane worktree is a *linked* worktree → `/write-plan` step 1.6 Condition B (`$gitDir -ne
  $gitCommon`) would fire → it would spawn a nested `plan/<slug>` worktree → `/execute-plan` would
  unconditionally call `handoff-session-state --merge-worktree` → which merges into the **base repo's
  current branch** (`feature/2.5.63`) **unserialized** = the exact corruption the spec feared.
- **Fix:** `run-phase.ps1 -Lane` sets `AUTOPILOT_LANE=1`; `write-plan.md` step 1.6 is taught to skip
  the nested-worktree creation when `AUTOPILOT_LANE` is set → plan+execute run in place on
  `auto/issue-NN`. Merge-back is owned **solely** by the new serialized `merge-back.ps1`.

## Next steps (ordered)

1. **Execute the plan** — `docs/superpowers/plans/2026-06-15-autopilot-concurrent-issues.md`. New
   scripts: `semaphore.ps1`, `lane-paths.ps1`, `lane.ps1`, `merge-back.ps1`, `merge-resolve.ps1`,
   `db-lock.ps1` (+ paired `*.assert.ps1`). Edits: `run-phase.ps1`, `recover.ps1`, `diagnose-halt.ps1`,
   `bin/nx.ps1`, `watchdog.ps1`, `start-n8n.ps1`, `write-plan.md`, the canvas, `README.md`, `SIGNALS.md`.
2. **Owner actions** (in the plan, can't run unattended): re-import the rewired
   `n8n-autopilot.workflow.json` via `start-n8n.ps1`; wire any new Telegram nodes; the Defender
   exclusion for the new `<repo-parent>\nexora-lanes` worktree root; the smoke gate.
3. **Smoke gate** (final plan phase, Owner): 2 trivial non-DB issues at lanes=2 → both build in own
   worktrees on `auto/issue-NN`, merge back serially clean, `.claude/worktrees/` stays empty; then 1
   DB-touch issue confirms the serial-DB rule.

## Gotchas & notes

- **Sequencing:** builds **on top** of the recently-shipped recovery layer + clarify loop + triage
  (all live on `feature/2.5.63`). Must NOT break the `route-recovery` Switch outputs
  (`comment-built-recovered` / `mark-blocked` / `notify-pause` / fallback) or the lock contract that
  `nx status`, `watchdog.ps1`, `start-n8n.ps1`, and `recover.ps1`'s `Test-Poison` read.
- **Live autopilot may run while you execute** — it stashes uncommitted edits and can commit onto the
  branch. Commit each task as soon as it's green; verify the queue is idle (`fetch-queue.ps1` prints
  `[]`, no `var/autopilot.lock`) before starting.
- **Nothing is broken right now** — this was a plan-only session; the live single-run autopilot is
  untouched.

## Untracked / left for owner

- Nothing untracked was left behind. Only the plan file was committed.
- **Not pushed** (remote/commit-only policy) — the owner pushes `30523a2` after review.

## How to verify

```powershell
git -C C:\dev\nexora log --oneline -1          # 30523a2 docs(plans): add autopilot-concurrent-issues...
git -C C:\dev\nexora status --porcelain        # clean
Get-Item C:\dev\nexora\docs\superpowers\plans\2026-06-15-autopilot-concurrent-issues.md
```

No test suite applies (docs-only session).

## Resuming in a fresh session

Point the next session at this file and the plan. **Same-date tie-break:** two handoffs share
2026-06-15, so `/reset-session` may pick the other one — run
`/reset-session docs/superpowers/handoffs/2026-06-15-autopilot-concurrent-issues-plan.md` to target
this one explicitly. Then execute
`docs/superpowers/plans/2026-06-15-autopilot-concurrent-issues.md` (subagent-driven-development).
