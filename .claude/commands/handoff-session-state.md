---
description: Write a zero-context session handoff doc, commit it (no push), then prompt /clear
argument-hint: "[optional focus/slug, e.g. 'reporting date dimension']"
---

Wrap up the current work session so the **next** session can resume with zero context. Do this
**fully autonomously, in order** — don't ask questions unless genuinely blocked (e.g. you're on
`main`). Optional focus from the user: `$ARGUMENTS`.

Run this **unprompted** when a batch of work is done (committed, tests green, nothing queued) or
the conversation is getting heavy — see "Session handoff loop" in `docs/howto/claude-workflow.md`.

## 1. Reconstruct what happened

Run `git branch --show-current`, `git status`, `git log --oneline -15`, and `git diff --stat`.
Establish: the branch, which commits landed **this session**, and what's still uncommitted. Skim the
conversation for decisions/gotchas that aren't obvious from the diff. **Do not fetch or push.**

## 2. `main` guard

If on `main`: do **not** stage/commit/modify any ref (nexora policy — `main` is read-only even with
per-turn permission). Stop, say so, tell the user to switch to a feature branch, and skip steps 3–6.

## 3. Write the handoff

- Location: `docs/superpowers/handoffs/` (create if missing). **Read the most recent existing handoff
  there first** and match its structure/tone.
- New file: `docs/superpowers/handoffs/YYYY-MM-DD-<slug>.md` (today's date; `<slug>` from `$ARGUMENTS`
  if given, else the session's main work). Assume the reader has **zero context**. Include:
  - **Header** — date, branch, ahead/unpushed count, "commit-only (remote)".
  - **This session's commits** — the relevant short hashes, oldest→newest, one line each.
  - **Prior handoff** — link the previous one.
  - **TL;DR** — 2–4 bullets.
  - **What shipped** — table/list of files + commits, grouped logically.
  - **Next steps** — concrete + ordered (point at any plan/spec file and the exact resume point).
  - **Gotchas & notes** — incl. anything red/broken right now and why.
  - **Untracked / left for owner** — call out anything you deliberately didn't commit.
  - **How to verify** — exact commands (flag any currently-failing suite).
  - **Resuming in a fresh session** — point the next session here (and at the plan/spec).
- **Same-date tie-break:** if another handoff already shares today's date, `/reset-session` may not
  pick yours. Add a one-line forward-pointer banner to the TOP of the older same-date handoff pointing
  at the new file, and in the new file's "Resuming" section note that `/reset-session <path>` targets
  a specific file.

## 4. Commit (nexora policy — see CLAUDE.md "Git")

- Feature branch only (step 2 handled `main`). Stage **just the handoff file(s)** (plus the
  forward-pointer edit). **Don't** bundle unrelated untracked files — e.g. a stray
  `sql/_migrations/**` migration gets its **own** commit; call it out in the handoff instead.
- Message: `docs(handoff): <slug>` when only the handoff is new; otherwise cover the bundled work.
  **gitlint will reject** (avoid retries): subject **imperative, ≤ 72 chars, no trailing period**;
  a **non-empty body** (blank line, then wrapped prose ≤ ~80 chars/line). End with the trailer
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Use `git commit -F -` with a here-doc.
- **Commit hooks need `SQL_SYNC_SKIP=1`** prefixed (INT `SchemaMigrations` CRLF drift blocks the
  `sql-migrate-int` hook on Windows). If `ruff-format` reflows a file, `git add -u` and re-commit.
- **Do NOT `git push` and do NOT open a PR** — the owner pushes themselves (remote/commit-only rule),
  even if `$ARGUMENTS` asks to push (only commit; tell them to push).
- After committing, show `git log -1 --stat` and capture the short hash.

## 5. Worktree cleanup (only when `$ARGUMENTS` contains `--merge-worktree`)

**Skip this step entirely** unless `$ARGUMENTS` contains the literal string `--merge-worktree`.

- Called by `/write-plan` → **no flag** — worktree stays open for `/execute-plan` to use next.
- Called by `/execute-plan` → **`--merge-worktree` flag** — merge + delete now.

When the flag IS present, detect whether the current working directory is a linked worktree:

```powershell
$gitDir    = git rev-parse --git-dir
$gitCommon = git rev-parse --git-common-dir
# If $gitDir -ne $gitCommon → linked worktree
```

**If not in a linked worktree:** nothing to clean up — skip the sub-steps below.

**If in a linked worktree**, do all of the following in order:

1. **Capture names** — record the current worktree path (`git rev-parse --show-toplevel`) and
   branch name (`git branch --show-current`).

2. **Merge into the parent branch** — from the **base repo root** (`git rev-parse --git-common-dir`
   minus `/.git`), run:
   ```powershell
   $base   = (git -C $baseRoot branch --show-current)   # e.g. feature/2.5.63
   $SQL_SYNC_SKIP = "1"
   git -C $baseRoot merge --no-ff $worktreeBranch -m "feat(...): merge <worktree-branch> into $base"
   ```
   If `git merge` reports **Already up to date**, the commits were already in the parent — nothing
   to do, continue to removal.  If there are **conflicts**, stop, surface them to the user, and
   skip removal.

3. **Remove the worktree** — from the base repo root:
   ```powershell
   git -C $baseRoot worktree remove --force $worktreePath
   ```

4. **Delete the worktree branch**:
   ```powershell
   git -C $baseRoot branch -d $worktreeBranch
   ```
   Use `-d` (safe delete, not `-D`) — it will refuse if somehow the branch is not fully merged, which
   is the right guard.

5. **Verify** — run `git -C $baseRoot worktree list` and confirm the removed worktree is gone.

Note the outcome in the handoff ("worktree removed and branch deleted") so the next session doesn't
look for it.

## 6. Drop the resume flag

Write the handoff's repo-relative path (e.g. `docs/superpowers/handoffs/2026-06-09-foo.md`) as the
single line of `var/handoff-pending` (gitignored — never commit it). The SessionStart hook
(`.claude/helpers/check-handoff-pending.ps1`) reads this flag in the next fresh session and points
it at `/reset-session`, which consumes the flag.

## 7. Prompt to clear

Only the user can run `/clear`. **End your entire response** with one prominent line and nothing
after it:

> ✅ Handoff written & committed (`<short-hash>`). **Type `/clear` now to start fresh.**
