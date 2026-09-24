> **SUPERSEDED.** Start at
> [`2026-09-23-prod-caught-up-on-3-2-13.md`](2026-09-23-prod-caught-up-on-3-2-13.md).
> Every open item below is resolved: PROD is on v3.2.13 and current, and the staging
> sessions error was an expired session rather than a failure. Kept for history.

> **UPDATE — both headline items resolved after this was written.**
>
> **PROD is live on 3.2.11** (`9348b43`). The owner pushed the tag at 15:12; verified
> from the footer on nexora.sydoc.ch, not from a green workflow. Step 2 below is done.
>
> **The staging `/admin/sessions` error is not a failure** — it is an expired session.
> The API 302s to `/login`, `fetch` follows redirects, and the final response is a
> legitimate 200 HTML login page, so `if (!response.ok)` passes and `.json()` throws
> into the catch that prints "Could not load sessions". Reproduced exactly against a
> signed-out browser. Staging hits it easily because the nightly 01:00 restore from
> PROD wipes `dbo.ActiveSessions` out from under a live session. **Step 1 needs no
> DevTools status code.** A task is chipped to make `NX.api` treat a redirect as
> "signed out"; every fetch-based admin page shares the blind spot.

# Handoff — two PROD releases merged, one staging error unexplained

**Date:** 2026-09-22 · **Branch:** `feat/354-phone-tabbar` · **58 commits ahead of `origin/main`**,
**0 unpushed** · **commit-only (remote)** — everything below is pushed; nothing is waiting.

**Prior handoff:**
[`2026-09-22-phone-tabbar-carousel-plan.md`](2026-09-22-phone-tabbar-carousel-plan.md) — the third
handoff sharing this date. This one is the newest.

## TL;DR

- **Two releases merged to `main` and are on staging. Neither is on PROD** — PROD is still
  **v3.2.9** from 15 September and moves only when the owner pushes a `v*` tag.
- **One tag ships both:** `v3.2.11`. 3.2.10 was never tagged, so 3.2.11 carries the unlock panel
  *and* the Generali work.
- **Open and unexplained: `/admin/sessions` shows "Could not load sessions" on staging.** It works
  locally. I could not reproduce it and ran out of things to check without the browser's Network
  tab. **Start here.**
- The whole tab-bar carousel plan (all three phases) is built and on the phone branch, which is
  still deliberately **off PROD** pending the owner's decision about whether nexora should have a
  phone version at all.

## This session's commits

**Merged to `main` (both are on staging now):**

| PR | hash on main | what |
|---|---|---|
| [#374](https://github.com/Sydoc-Org/nexora/pull/374) | `3a0a19f8` | admin unlock panel — **3.2.10** |
| [#375](https://github.com/Sydoc-Org/nexora/pull/375) | `9348b438` | POE + accessibility labels — **3.2.11** |

**On `feat/354-phone-tabbar` (oldest → newest):**

| hash | what |
|---|---|
| `cddb0ef5` | safe-area tokens + `scripts/phone-sweep.py` + guard test |
| `b532cacb` | the three confirmed phone bugs |
| `bec26cb3` | reporting app icon back in the phone topbar |
| `4cd48d8c` | Generali: 80 unnamed controls, month report, tiny row buttons |
| `ab1b7132` | Generali: stat cards single-column |
| `4cdb496f` | the carousel + tenant picker plan |
| `292652d0` | prior handoff |
| `77ab9268` | **Task 7** — bar follows the tenant, slots window the whole list |
| `64b056a0` | **Phase 2** — tenant switcher at the top of the sheet |
| `5d8c78c0` | **Phase 3** — slots slide between windows |
| `fe56e630` | POE (superseded on main by the date-driven version) |
| `d2a671d0` | unlock panel (superseded on main by `8688e803`) |
| `5d948546` | **chore(release): 3.2.11** |
| `8afd8cc2` | the owner's editor reformat of `header.js`, alone |
| `2b5611df` | the owner's swipe spike, alone |

## What shipped

**The carousel plan is fully built** — all three phases, on the phone branch.

The bar now finds its tenant by **the page you are on**, not by `session['tenant_scope']`. The plan
said to use the scope and **the plan was wrong**: that scope is only written by routes calling
`apply_tenant_scope` (dashboard, workitems, the generated `tenant_page`), and Generali's pages are
*custom routes* that never touch it — so on `/generali/documents` the scope still named whichever
tenant you were in before. Even `?tenant=generali` changed nothing there.

One real ambiguity had to be handled: sydoc and MS02 both mount the shared `workitems_overview`
endpoint, so on `/workitems` the page alone cannot say whose it is. Claimed once → that tenant;
claimed twice → the viewer's own tenant breaks the tie; still undecided → the Global entries rather
than a guess. The rules are pure functions in **`nx_lib/tabbar.py`**, not Jinja.

`static/js/swipe_nav.js` is **not modified**. Centring the active page makes the three rendered
slots *be* `[prev, active, next]`, so its existing neighbour lookup delivers the carousel for free.
Verified end to end: swiping walks all eight Generali pages in order and stops at the last.

**Phase 3 is smaller than scoped.** Each slot carries a `view-transition-name` keyed on the **page**
rather than the position, so a page present in both windows morphs from its old slot to its new one
— the browser draws the slide. No keyframes, no transform, no JS, no direction tracking.

**Two PROD releases.** The unlock panel (`/admin/sessions`, see below) and the Generali work: POE
moving to Zusatzleistungen **by date** (`POE_CUTOVER` in
`nx_lib/views/generali/baseservices.py`, checked against the server's local date) plus 80 icon-only
controls that had no accessible name. Both were cut **from `main`**, not from the phone branch.

## Next steps

1. **The staging `/admin/sessions` error — start here.** The page shows *"Could not load
   sessions"*. What I ruled out: the query runs fine against `nexora_STAGING` and returns proper
   `datetime` objects; `ActiveSessions` exists with the right columns and 78 rows; the route is
   registered; `API_PREFIX` resolves to `/nexora/` correctly; the CSP allows same-origin fetch
   (`connect-src 'self'`); staging's `app.log` has **no** recent error, so it is not a 500; and the
   page **works locally on INT** with real sessions listed and no failed requests.
   **What is needed:** the owner opens DevTools on that staging page → Network → Refresh → the
   **status code** for `api/admin/active_sessions`. 403 = permission, 404 = URL under the prefix,
   500 = server (then read the log), nothing at all = the JS never ran, which would point at the
   `_sessions_js.html` change in `d2a671d0`/`8688e803`.
   It is *probably* pre-existing — that file's `fetchActiveSessions` was not touched, only added to
   — but do not claim that until the status code says so.
2. **PROD tag — the owner's, one command.**
   `git switch main && git pull && git tag v3.2.11 && git push origin v3.2.11`
   Ships both releases. ~34s app-pool restart. **The carve-out is Friday 2026-09-25**, so timing is
   theirs to pick.
3. **The eye toggle on the reset-password page — still unreproduced.** The owner reports the eye
   does not reveal the password on a **desktop** browser. It works in Chromium desktop, WebKit
   desktop, WebKit phone and Chromium phone, on all four password pages, and all four include
   `templates/js/_auth_pw_toggle_js.html`. Leading theory: a **password-manager browser extension**
   (1Password/Bitwarden) injecting its own icon at the right edge of the field, exactly where the
   button sits, swallowing the click. Playwright runs without extensions, which would explain the
   gap. **Test: open the reset page in a private/incognito window.** If it works there, the fix is
   raising the button's stacking order, not touching the handler.
4. **`feat/354-phone-tabbar` needs bumping to 3.2.12.** It sits on 3.2.11, which #375 took.
   `test_version.py` will go red the moment `main` is merged in. It also now conflicts with `main`
   in the usual regenerate-don't-merge files (`CHANGELOG.md`, `messages.pot`, `version.py`,
   `pyproject.toml`, the three catalogs).
5. **The phone version is still parked.** 53 of the 58 commits on this branch are the phone layout.
   The owner held it off PROD on 2026-09-17 to debate whether nexora should have a phone version at
   all. That decision has **not** been taken — do not ship it by default.
6. **Two spawned tasks are pending** as chips: *Clear the login lockout on password reset* and
   *Guard the password reset against silent no-op*. Both came out of the support case below.

## Gotchas & notes

- **A password reset does NOT clear `dbo.LoginLockout`.** This cost a colleague most of a morning:
  she locked herself out, her password was reset, and she still could not get in — the lockout check
  runs *before* `bcrypt.checkpw`, so the new correct password was never compared. Two `429`s in the
  request log with no `401` between them. **The lockout returns 429, not 401** — that is how you
  tell it apart in the logs, and the password-step message prints the *remaining* minutes while the
  2FA one prints a flat 15.
- **Login finds users by `username`; password reset finds them by `email`.** No email fallback at
  login. A successful reset followed by "Invalid credentials" is almost always someone typing their
  email address into the username field.
- **Staging serves under `/nexora`, like PROD** (`IS_PROD` is true for STAGING). I wasted a step
  reporting "staging returned no version" when I had simply fetched `/` instead of `/nexora/`.
- **The `mypy` pre-commit hook is broken in this environment.** Its entry is `python -m mypy` under
  `language: system`, which resolves to the system Python, and that has no mypy. Run it from
  `.venv` (clean, 106 files) and `SKIP=mypy git commit`. Never `--no-verify`.
- **`mixed-line-ending` and `ruff-format` rewrite files and fail the commit.** `git add` again and
  re-commit. Normal, not an error. Expect it on almost every commit.
- **`pybabel`'s default `.po` wrapping matters.** Writing catalogs with `write_po(width=None)`
  unwraps every string and produced a **6627-line deletion** diff in a hotfix PR. Regenerate with
  `pybabel update` and edit only the new entries textually.
- **`MSYS_NO_PATHCONV=1` in Git Bash** for `scripts/phone-sweep.py`, or MSYS rewrites
  `--pages /reporting` into a Windows path.
- **WebKit is installed now** (`webkit-2104`) and it earns its keep — `/reporting` overflowed 53px
  there at every width and 0px in Chromium.
- **The pre-push hook rejects branch names** outside
  `^(feat|fix|chore|refactor|docs|test|ci)/<slug>$`. `hotfix/` is not a type.
- **Auto-merge is not available** on this repo (private, Free plan).
- **Production DB reads and `gh run list` are blocked** by this session's permission classifier, as
  is copying `env/*.env` into a worktree. Hand those to the owner rather than retrying.
- **Nothing is red** in the suites. The only broken thing is the staging page in step 1.

## Untracked / left for owner

- **`t -L 3`** in the repo root — captured `less` pager help text. Junk; delete on their word. It has
  survived three handoffs now.
- `header.js` is **no longer** outstanding: committed as `8afd8cc2` (the editor reformat alone) and
  `2b5611df` (the owner's swipe spike alone). The spike only `console.log`s and is superseded by
  `swipe_nav.js`; its commit message says so and suggests deleting it.
- No worktree is open. The one used for PR #374 was removed along with its copied `env/TEST.env`.

## How to verify

```bash
export PATH=".venv/Scripts:$PATH"
./.venv/Scripts/python.exe -m pytest tests/unit -q -p no:randomly --no-cov
./.venv/Scripts/python.exe -m pytest tests/integration -q -p no:randomly --no-cov
./.venv/Scripts/python.exe -m pytest tests/e2e/test_mobile_nav.py -q -p no:randomly --no-cov
./.venv/Scripts/python.exe -m mypy nx_lib nx_main.py
```

Last run on this branch: unit **1902+**, integration **840**, `test_mobile_nav.py` **52 passed /
2 skipped**, mypy clean. On `main` at 3.2.11: unit **1902**, integration **840**.

Which host runs what:

```bash
for u in https://dev-nexora.sydoc.ch/ https://staging-nexora.sydoc.ch/nexora/ https://nexora.sydoc.ch/nexora/; do
  echo "$u $(curl -s -L --max-time 20 "$u" | grep -oE 'nexora v[0-9.]+' | head -1)"
done
```

At handoff time: dev **v3.2.11**, staging **v3.2.11** (`9348b43`), PROD **v3.2.9** (`3ef8967`).

The phone sweep needs the dev server up (`./bin/nx.ps1 -u`, port 8000):

```bash
MSYS_NO_PATHCONV=1 ./.venv/Scripts/python.exe scripts/phone-sweep.py
```

## Resuming in a fresh session

Read this file. **Three handoffs share 2026-09-22** — this is the newest;
`/reset-session docs/superpowers/handoffs/2026-09-22-two-prod-releases-and-a-staging-error.md`
targets it explicitly.

Then read [[feedback_owner_wants_to_write_the_code]] in memory. The arrangement from 2026-09-21 is
that the owner writes the code and wants to be taught — but they have consistently asked for things
to be implemented directly since, including all of this session. Follow what they ask for now; when
it is a learning task, explain and review instead of patching.

The plan for the phone work, now fully executed, is
[`../plans/2026-09-22-phone-tabbar-carousel-tenant-picker.md`](../plans/2026-09-22-phone-tabbar-carousel-tenant-picker.md).
Note it was wrong in two places, both recorded above — worth reading the commit messages of
`77ab9268` and `64b056a0` before trusting any of its remaining assumptions.
