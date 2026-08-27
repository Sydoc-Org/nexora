---
description: Consolidate all worktrees/branches into one clean version branch, push, open a PR, then babysit CI checks through merge and the production deploy
argument-hint: "[optional: version branch name, defaults to the current branch]"
---

Get the repo to a single clean state on one version branch, pushed, PR'd, merged, and deployed —
babysitting every step that can fail silently. `$ARGUMENTS` optionally names the version branch to
consolidate onto; default to the current branch (`git branch --show-current`).

**Nexora git policy applies throughout** (CLAUDE.md "Git — Branch-based policy"): never stage,
commit, or push on `main`; never force-push; never delete a branch that isn't a safe fast-forward
merge (`git branch -d`, never `-D`); never skip hooks. If the current branch IS `main`, stop
immediately and tell the user to name a version branch instead — do not proceed with any step below.

## 1. Inventory everything that exists

```powershell
git worktree list
git branch --list
git branch --list -r          # what's already on origin
git status --short            # current tree
```

Build a picture: the target version branch, every linked worktree and its branch, every local
branch, and whether the current tree has uncommitted changes. Note anything that looks like another
session's active work (a worktree/branch you didn't create this session, an uncommitted file you
don't recognize) — call it out to the user before touching it rather than guessing.

## 2. Commit everything that belongs here

For the main checkout and every worktree in turn:

- `git status --short` — for each modified/untracked file, decide: does it belong to finished work
  on this branch? If yes, stage and commit it (conventional-commit message; add a `CHANGELOG.md`
  `[Unreleased]` entry if the change is user-visible, per CLAUDE.md "Keeping docs in sync").
- Scratch/debug artifacts (stray test scripts, screenshots outside `var/screenshots/`, `.tmp` files)
  → delete them, don't commit them.
- A file that's clearly someone else's in-flight work (see step 1) → leave it, list it in the final
  report, do not commit or stash it out from under them.
- If new translatable strings were added and never went through the `/nx-i18n` cycle, run it now and
  commit the result.
- Use `SQL_SYNC_SKIP=1` on any commit if the `sql-migrate-int`/`sql-sync-check` pre-commit hooks
  block on unrelated INT drift (same escape hatch `/handoff-session-state` uses) — never `--no-verify`.

## 3. Fold every worktree and branch into the one version branch

For each linked worktree (from `git worktree list`) other than the main checkout:

- If its branch is fully merged into the version branch already, just remove the worktree
  (`git worktree remove <path>`, add `--force` only if it's clean-but-flagged, never to discard real
  changes) and delete the branch (`git branch -d`).
- If it has unmerged work, merge it into the version branch first (`git merge --no-ff
  <worktree-branch> -m "..."`), resolve conflicts if any (stop and ask the user if a conflict isn't
  mechanical), then remove the worktree and delete the branch as above.

Do the same for any local branch that isn't the version branch and isn't `main`: merge into the
version branch if it has unmerged commits, then `git branch -d` it. Never touch remote branches
other than the version branch itself.

End state: `git worktree list` shows only the main checkout, `git branch --list` shows only the
version branch (and `main`), `git status` is clean.

## 4. Push

```powershell
git push -u origin <version-branch>
```

Never force-push. If the push is rejected (remote has diverged), stop and tell the user — do not
`--force` or `--force-with-lease` without them explicitly asking for it in this turn.

## 5. Open the PR (or reuse an existing one)

```powershell
gh pr list --head <version-branch> --json number,url,state
```

If an open PR already targets `main` from this branch, reuse it. Otherwise:

```powershell
gh pr create --base main --head <version-branch> --title "<short title>" --body "$(cat <<'EOF'
## Summary
<1-3 bullets from the commits landing in this PR>

## Test plan
<checklist: relevant test suites / manual verification done>
EOF
)"
```

Summarize from `git log main..<version-branch> --oneline` and `git diff main...<version-branch>
--stat`, not from guesswork.

## 6. Babysit CI to green

```powershell
gh pr checks <pr-number> --watch
```

This blocks until every check finishes. If anything fails:

- Read the failing check's log (`gh run view <run-id> --log-failed`).
- Fix the root cause on the version branch (never skip the check, never disable it).
- Commit, push, and re-run `gh pr checks <pr-number> --watch` until green.

## 7. Merge — confirm first

Merging this PR pushes to `main`, and per CLAUDE.md, a push to `main` makes `deploy.yml` apply
pending migrations and deploy to **PROD** before the app pool stops. That is a real production
action, not a routine merge — confirm with the user before merging even if they invoked this
command, unless they've already said "merge it" in this same turn.

Once confirmed:

```powershell
gh pr merge <pr-number> --merge --delete-branch=false
```

(`--delete-branch=false`: the version branch is the team's ongoing branch, not a disposable PR
branch — don't delete it after merge.)

## 8. Babysit the production deploy

```powershell
gh run list --workflow deploy.yml --branch main --limit 1
gh run watch <run-id>
```

Watch it to completion. If it fails, read the failing step's log (`gh run view <run-id>
--log-failed`) and report exactly what broke and where (migration step vs. app-pool restart vs.
robocopy mirror) — do not attempt to SSH/RDP into SYAPP01 or take remediation action without the
user's explicit go-ahead, since that's PROD.

## 9. Report

Finish with a short summary: what got merged/deleted (worktrees, branches), the PR number and URL,
the CI result, the deploy run result, and anything left alone (other sessions' work, unresolved
conflicts, a deploy failure needing the user's attention). Do not claim "deployed" unless step 8's
workflow run actually completed successfully.
