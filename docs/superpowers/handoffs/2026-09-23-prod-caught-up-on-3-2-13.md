# Handoff — PROD caught up on 3.2.13, everything shipped

**Date:** 2026-09-23 · **Branch:** `feat/354-phone-tabbar` · **0 unpushed** ·
**Owner's checkout is on `main`** — they switched there to tag and it was left that way
deliberately.

**Prior handoff:**
[`2026-09-22-two-prod-releases-and-a-staging-error.md`](2026-09-22-two-prod-releases-and-a-staging-error.md)
— its open items are all resolved; this file supersedes it.

## TL;DR

- **PROD is on v3.2.13 and current.** Everything from the last two days is live: the admin
  unlock panel, the always-visible locked-accounts panel, POE, and 80 Generali accessibility
  labels. Verified from the footer (`1b949f9`), not from a green workflow.
- **Nothing is open, nothing is unpushed, nothing is broken.** The three open PRs (#361, #360,
  #359) all predate this work.
- **The phone version is still parked** and still off PROD. 53 of the phone branch's commits are
  the phone layout; the owner has not taken the decision about whether nexora should have one.
- **New standing instruction: merge their PRs on green without asking** — see
  [[feedback-merge-on-green-without-asking]]. Tagging PROD remains theirs.

## Where each host is

| host | version | build |
|---|---|---|
| PROD `nexora.sydoc.ch/nexora/` | **v3.2.13** | `1b949f9` |
| staging `staging-nexora.sydoc.ch/nexora/` | v3.2.13 | `1b949f9 (main)` |
| dev `dev-nexora.sydoc.ch` | v3.2.10 | `d2a671d (feat/354-phone-tabbar)` |

Dev's v3.2.10 is **not** stale for features — `d2a671d` sits after all three carousel phases. The
five commits it lacks are a release chore, the owner's `header.js` commits and two handoff docs.

## This session's releases

| PR | merge | release | what |
|---|---|---|---|
| [#374](https://github.com/Sydoc-Org/nexora/pull/374) | `3a0a19f8` | 3.2.10 | admin unlock panel |
| [#375](https://github.com/Sydoc-Org/nexora/pull/375) | `9348b438` | 3.2.11 | POE (date-driven) + 80 accessibility labels |
| [#376](https://github.com/Sydoc-Org/nexora/pull/376) | `7d6a3727` | 3.2.12 | locked-accounts panel always visible |
| [#377](https://github.com/Sydoc-Org/nexora/pull/377) | `1b949f98` | 3.2.13 | version bump only (see the tag note) |

## Next steps

1. **The eye toggle on the reset-password page — the only real open item.** The owner reports the
   eye does not reveal the password on a **desktop** browser. It works in Chromium desktop, WebKit
   desktop, WebKit phone and Chromium phone, on all four password pages, and all four include
   `templates/js/_auth_pw_toggle_js.html`. Leading theory: a **password-manager browser extension**
   (1Password/Bitwarden) injecting its own icon at the right edge of the field, exactly where the
   button sits, swallowing the click — Playwright runs without extensions, which would explain the
   gap. **Ask them to try a private/incognito window.** If it works there, the fix is raising the
   button's stacking order, not touching the handler.
2. **Three chipped tasks are pending**, all from the same support case:
   - *Clear the login lockout on password reset* — the reset path never clears
     `dbo.LoginLockout`, so the fix meant to unstick someone leaves them locked and their new
     password is never compared.
   - *Guard the password reset against silent no-op* — it updates by email with no rowcount check.
   - *Say "signed out" instead of "could not load"* — an expired session redirects to `/login`,
     `fetch` follows it, and a 200 HTML page passes the `response.ok` guard, so every fetch-based
     admin page reports a server error instead of sending you to log in.
3. **The phone version decision.** Unchanged and still theirs. Do not ship it by default.
4. **`feat/354-phone-tabbar` will need re-bumping past 3.2.13** and will conflict with `main` in
   the usual regenerate-don't-merge files when it is eventually merged.

## Gotchas & notes

- **`v3.2.12` is a dud tag.** It was pushed before #376 merged, so it points at `9348b438` — the
  same commit `v3.2.11` already tagged. Its deploy re-shipped code PROD already had. Harmless, but
  do not be puzzled by it, and do not try to reuse or move it. That is why the release chain skips
  from 3.2.11 to 3.2.13 on PROD.
- **Dev is last-push-wins across ALL branches.** It was taken over three times today by the
  release-chain branches. If dev looks wrong, read the footer — it names the branch.
- **A docs-only push does not deploy.** `deploy.yml`'s `paths` filter excludes `docs/**` and
  `*.md`, so pushing a handoff leaves dev on whatever was there. This looked like a bug twice.
- **`gh run rerun` replays the ORIGINAL commit**, not the branch tip. Fine for restoring dev, but
  it will not pick up newer commits — push a code change for that.
- **The owner's PowerShell 5.1 has no `&&`.** Give them one command per line. This broke a PROD
  release command once already — see [[reference-nexora-shell-environment-traps]].
- **`SKIP=mypy SQL_SYNC_SKIP=1 git commit`** is needed on nearly every commit here; the hooks run
  under a system Python that has neither mypy nor dotenv. Never `--no-verify`.
- **`mixed-line-ending` and `ruff-format` rewrite files and fail the commit.** `git add` again and
  re-commit. Expect it every time.
- **Nothing is red.** No failing suite, no half-finished edit.

## Untracked / left for owner

- **`t -L 3`** in the repo root — captured `less` pager help. Junk; it has now survived four
  handoffs. Delete on their word.
- The owner's checkout is on **`main`**, clean. Left as found.

## How to verify

```bash
export PATH=".venv/Scripts:$PATH"
./.venv/Scripts/python.exe -m pytest tests/unit -q -p no:randomly --no-cov
./.venv/Scripts/python.exe -m pytest tests/integration -q -p no:randomly --no-cov
```

Last run on `main` at 3.2.12: unit **1902**, integration **842**, ruff clean.

Which host runs what:

```bash
for u in https://nexora.sydoc.ch/nexora/ https://staging-nexora.sydoc.ch/nexora/ https://dev-nexora.sydoc.ch/; do
  echo "$u $(curl -s -L --max-time 20 "$u" | grep -oE 'nexora v[0-9.]+' | head -1)"
done
```

## Resuming in a fresh session

Read this file. It supersedes the two dated 2026-09-22, both of which carry forward-pointers.

Then read [[feedback-merge-on-green-without-asking]] and
[[feedback-owner-wants-to-write-the-code]]. The second is from 2026-09-21 and says the owner
writes the code and wants to be taught — but they have asked for direct implementation in every
session since, including all of this one. Follow what they ask for now; when it is genuinely a
learning task, explain and review rather than patch.

The phone plan, fully executed, is
[`../plans/2026-09-22-phone-tabbar-carousel-tenant-picker.md`](../plans/2026-09-22-phone-tabbar-carousel-tenant-picker.md).
It was wrong in two places — both about `session['tenant_scope']` — so read the commit messages of
`77ab9268` and `64b056a0` before trusting its remaining assumptions.
