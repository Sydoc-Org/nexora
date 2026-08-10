---
description: End-of-task cleanup — merge/remove own worktrees+branches, tidy uncommitted files, close the issue, sync changelog/docs, leave the repo ready for the next task
argument-hint: "[issue_number]"
---

Wrap up the task that was just finished so a fresh task can start clean. Only clean up things **this session created** — never touch worktrees, branches, stashes, or file changes from other/parallel sessions (note them in one line instead).

1. **Worktrees + temp branches:** if this session created a worktree and/or working branch, merge the finished work back into the session's main working branch, then remove the worktree and delete the merged branch (worktree removal + branch delete of your own creations are authorized as part of this command). `git worktree list` / `git branch` to find leftovers — but leave anything you didn't create alone.
2. **Uncommitted files:** `git status --short`. For files this task created or modified:
   - Work that belongs to the task but isn't committed → commit it now (conventional-commit message, changelog entry if user-visible).
   - Scratch/debug/test artifacts in the repo (stray test scripts, dumps, `.tmp`, screenshots outside `var/screenshots/`) → delete them.
   - Files you did not touch this session → leave them, mention them in the report.
3. **Test infra:** stop any `--no-conflict` nexora instance this session started (`nx -d --port:<n>`), kill any Playwright/Chromium the session left running, and remove leftover scratchpad temp servers/processes. Never touch port 8000.
4. **Issue bookkeeping** (use `$1` if given, else the issue worked on this session): close it with a comment containing the fix commit SHA(s), remove the `inprogress` label. Skip silently if no issue was involved.
5. **Docs in sync:** verify CHANGELOG.md has an `[Unreleased]` entry for the change; verify touched docs (CLAUDE.md path references, `docs/howto/*`, in-app help) were updated; fix and commit anything missing in one `docs:`/amendless follow-up commit.
6. **Translations:** if new `_('...')` strings were added this task, run the `/nx-i18n` cycle and commit.
7. **Deploy excludes:** if new top-level files/dirs not needed at runtime were added, confirm they're in the robocopy excludes in `.github/workflows/deploy.yml`.
8. **Final state check:** `git status` clean (except intentionally-left foreign changes), `git log --oneline -3` shown, no stray processes. Do **not** push and do **not** open a PR — the user does that.
9. **Report:** ≤5 lines — what was merged/deleted/closed/committed, plus anything deliberately left alone.
