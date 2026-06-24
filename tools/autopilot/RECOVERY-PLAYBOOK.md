# Autopilot recovery playbook (nexora-specific)

The fixer (`fix-attempt.ps1`) reads the section matching the diagnosed `class`. Use
**systematic-debugging** discipline: find the root cause, fix it, re-verify — do not paper over.

## i18n catalog drift (test-gate: `test_translations` fails)
- Run the extract -> update -> compile cycle (Flask-Babel) for de/fr/it (`nx-i18n` skill).
- Commit BOTH the `.po` sources and the compiled `.mo` files.

## CRLF / SQL migration checksum drift (commit blocked by `sql-migrate-int`)
- `SQL_SYNC_SKIP=1` is already set in your env — **commit with it; never `--no-verify`**
  (that would skip the line-ending normaliser too).
- Durable fix (only if you actually touched `sql/`): add `*.sql eol=lf` to `.gitattributes`
  after a controlled `git add --renormalize sql/` pass. Do NOT renormalize as a side effect.

## Flaky / order-dependent e2e (test-gate: Playwright/e2e fails non-deterministically)
- Run `python scripts/test_db_reset.py` FIRST to clear stale `NEXORA_TEST` state, then re-run.

## Leftover `plan-*` worktree (mechanical / plan-ok-execute-failed)
- Re-enter the **execute** phase; do NOT delete the worktree blindly.
- `git worktree remove` ONLY after `git merge-base --is-ancestor <worktreeHEAD> <branchHEAD>`
  confirms it holds no unmerged commits. An unmerged worktree is data loss => classify
  `genuine-blocker`.

## Lane merge conflict (`merge-resolve` returned UNRESOLVED)
- `merge-resolve.ps1` already aborted the merge clean. Worktree is intact at
  `C:\dev\nexora-lanes\lane-K` on branch `auto/issue-NN`.
- Inspect: `git -C C:\dev\nexora-lanes\lane-K diff HEAD feature/2.5.63` to see what conflicted.
- Options:
  - **Resolve by hand:** checkout the branch, resolve, commit, then `merge-back.ps1 -Force` (or merge manually into `feature/2.5.63`).
  - **Re-queue:** fix the conflicting code in `feature/2.5.63` first, then remove `autopilot-blocked` to re-queue.
- After resolving: `git -C C:\dev\nexora worktree remove --force C:\dev\nexora-lanes\lane-K` then `git -C C:\dev\nexora branch -D auto/issue-NN`.

## All slots wedged (semaphore full, no progress)
- Usually means 3 lanes crashed without releasing slots.
- Emergency: remove `C:\dev\nexora\var\autopilot\slots\` (all `.lock` files) and inspect the
  lane worktrees (`git worktree list`) before pruning — do NOT remove unmerged worktrees.
- `start-n8n.ps1` does this automatically (ancestor-checked) on next n8n startup.

## Always
- Commit on the current branch; stop at commit; never push; never `--no-verify`.
