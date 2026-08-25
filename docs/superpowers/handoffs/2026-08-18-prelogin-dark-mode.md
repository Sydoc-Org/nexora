# Handoff — Pre-login dark mode (6 pages) shipped; next up: rework the *existing* logged-in dark mode

**Date:** 2026-08-18 · **Branch:** `v3.2.1` · **already pushed to `origin/v3.2.1`** (all 9 commits
below are on GitHub — this session pushed directly at the owner's explicit request each time,
unlike the usual commit-only convention; see "Gotchas" for why some pushes used `--no-verify`)
**Prior handoff:** none — first session on this work.

## TL;DR

- Added a working sun/moon dark-mode toggle to **all six pre-login pages** (landing, login,
  forgot-password, reset-password, set-password, initial-password-reset, 2FA setup) that didn't
  have one before. Verified in both themes on every page reachable without a live DB session; the
  three DB/token-gated ones (reset/set-password, 2FA setup) were verified structurally (identical
  edits to a proven pattern, template renders cleanly, server doesn't error) since this dev
  machine has no `NEXORA_TEST` DB access.
- Along the way, fixed a pile of real bugs the toggle exposed — an invisible logo wordmark, an
  invisible subtitle, background glow blobs that were flat-out invisible or painted over entirely,
  a Tailwind CDN config-ordering bug that made *every* `dark:` utility on these pages silently
  ignore the toggle and follow the OS theme instead, and two missing Python dependencies
  (`matplotlib`, `pypdfium2`) that broke the test suite on a clean `uv sync` — unrelated to dark
  mode, found because the pre-push test gate actually ran for the first time on this fresh clone.
- Also fixed the broken dev environment itself (this was the *first* thing this session did,
  before any dark-mode work): `bin/nx.ps1` had the previous owner's personal machine path
  hardcoded in it, `uv` wasn't installed, and git had no identity configured on this machine at
  all. All fixed; see commit `58c4fbcc` and the "Dev environment" section below.
- **The owner's next task is bigger: rework the dark mode that *already exists* for logged-in
  pages** (dashboard, admin, reporting, etc. — a completely different, older system from what this
  session built) to "look like it's supposed to." **I do not know what that target look is** — the
  owner hasn't described it yet. First thing the next session should do is ask, not assume. See
  "Next steps" below for where that existing system lives and what to review first.

## This session's commits (oldest → newest, on `v3.2.1`, all pushed)

| Commit | What |
|---|---|
| `58c4fbcc` | fix(bootstrap): stop hardcoding a personal Python path in `nx.ps1`; make `bootstrap.ps1`'s `uv` install not depend on a working `python` |
| `222d40eb` | feat(login): dark mode toggle on `hero.html` (landing) and `index.html` (login) — the big one, most of the actual bug-finding happened here |
| `1ebe4903` | fix(reporting): declare `matplotlib` as a dependency (pre-existing gap, unrelated to dark mode) |
| `eb058c08` | fix(reporting): declare `pypdfium2` as a dependency; sync i18n catalogs (same class of gap, second package) |
| `7072b900` | feat(login): dark mode toggle on `forgot_password.html` |
| `418e1b88` | fix(login): brighten the black-hole logo icon's glow for dark mode |
| `df680430` | feat(login): dark mode toggle on `reset_password.html`, `set_password.html`, `init_reset.html` |
| `fd899ad8` | chore(i18n): refresh catalog file/line references (no new translations needed) |
| `4eca502e` | feat(login): dark mode toggle on `init_2FA.html`; fixed two more `auth.css` gaps (`text-gray-500`, the raw-Tailwind flash-error box pattern) |

## What shipped, and exactly how it works

### The mechanism (same on every page)

1. **A `dark` class on `<html>` is the entire switch.** Everything else is just CSS/JS reading
   that one thing.
2. **Pre-paint script**, first thing in `<head>`, before any stylesheet or the Tailwind CDN
   script: reads `localStorage['nexora-ui-prefs']` (JSON, `{theme: 'dark'|'light'}`) merged with
   the legacy key `localStorage['nexora-theme']` as fallback, adds the class before first paint so
   there's no flash of the wrong theme on reload.
3. **Tailwind Play CDN config — the ordering bug that cost real debugging time:**
   `cdn.tailwindcss.com` creates its own `window.tailwind` object *when its `<script>` tag runs*,
   overwriting anything set on that name beforehand. So:
   ```html
   <script src="https://cdn.tailwindcss.com"></script>
   <script nonce="{{ csp_nonce() }}">
       tailwind.config = { darkMode: 'class' };  <!-- AFTER, not before -->
   </script>
   ```
   Setting the config *before* the CDN script (which is what this repo's pages all did
   originally, and what I wrote initially too) gets silently discarded. Without
   `darkMode: 'class'`, Tailwind defaults to `'media'` — every `dark:` utility class on the page
   follows the OS's `prefers-color-scheme` instead of the toggle button. This bug was live for a
   while before being caught (the owner reported "light mode still shows white text" — that was
   this, not a color bug).
4. **Toggle button** — sun/moon Font Awesome icon pair, `dark:hidden` / `hidden dark:inline`, no
   JS needed to swap them once the config above is correct.
5. **Click handler** toggles the class and writes both localStorage keys. Two reusable partials
   handle this, both class-bound (not id-bound) so any page can just include one and add the
   matching button class:
   - `templates/js/_hero_js.html` — hero.html-specific (bundled with its other page JS)
   - `templates/js/_auth_theme_toggle_js.html` — **new this session**, binds `.auth-theme-toggle`,
     used by every pre-login page except hero.html
6. **Why localStorage and not the DB-backed prefs system:** logged-in pages already have a full
   theme system — `nx_lib/ui_prefs.py` (DB column `Users.ui_prefs`, mirrored to `session`),
   `_header.html`'s pre-paint script, `window.nxSetUiPref()`. Pre-login pages have no user row yet,
   so they're localStorage-only. **Same two keys as the logged-in system though** — a choice made
   before login is already picked up the moment the user signs in, because `_header.html`'s
   pre-paint script already reads the legacy `nexora-theme` key as one of its fallbacks. This was
   deliberate, not incidental — worth knowing before the next session touches either side.

### Where the actual colors live

- **`static/css/nexora-ui.css`** — the app-wide `--nx-*` token system (`:root` = light,
  `html.dark` = dark). This is the system the **logged-in** pages already use everywhere. Untouched
  this session except as a reference for token values.
- **`static/css/auth.css`** — shared across every pre-login page (login, forgot/reset/set
  password, 2FA, init-reset). Centralizes dark-mode rules as CSS-selector overrides
  (`html.dark .text-gray-700 { color: ...!important }` etc.) rather than inline `dark:` classes on
  each template, on purpose — a page with no toggle simply never gets the `html.dark` class, so
  the rules just sit there inert until it does. This is *why* `forgot_password.html` and the
  password-reset pages took almost no page-specific work: nearly everything was already covered
  once `index.html` (the first one) built out the rule set. **This file grew a lot this session** —
  read it top to bottom before touching it again, the comments explain each rule's origin.
- **`static/css/hero.css`** — landing-page-specific. Was already token-based
  (`var(--nx-*, fallback)`) before this session per its own header comment ("dark mode is a user
  preference, not the page default") — it just had never actually been wired up. Most of the work
  here was fixing the handful of places that *weren't* token-based (hardcoded light hex colors
  with no dark counterpart).
- **`static/css/_nexoraLogo.css`** — the logo partial (wordmark text + black-hole icon), shared by
  literally every page, logged-in or not. Two separate real bugs here, both now fixed:
  1. The "nexora" wordmark is gradient-clipped text (`background-clip: text; color: transparent`)
     — the light-mode gradient was near-black, so in dark mode it clipped to full transparency:
     **the logo text was completely invisible**, not just hard to read.
  2. The black-hole icon's depth/shadow pieces (core's outer glow, penumbra, disk's outer glow)
     were all near-black `rgba(0,0,0,*)` — a drop-shadow that reads as depth on a light page and is
     literally invisible on a dark one. Brightened to an indigo/violet glow in `html.dark`. The
     core itself stays black in both themes on purpose (it's a black hole).
- **`static/css/reset_password.css`**, **`forgot_password.css`** — page-specific, but had nothing
  to fix; both already had correct full-height flex layout from before this session
  (`body{display:flex;flex-direction:column;min-height:100vh} main{flex-grow:1}`). Their legacy
  `.error-message`/`.success-message`/`.bg-gradient-primary` rules are dead code, superseded by
  `auth.css`'s token-based versions which load after and use `!important` — left alone, not worth
  the diff.

### Templates touched, per page

| Page | Route | What was added |
|---|---|---|
| `hero.html` | `/` | Full build-out: toggle, pre-paint, Tailwind config fix, `dark:` variants across the whole page body, all the bug fixes above, a responsive fix (see below), small hover-scale on feature cards |
| `index.html` | `/login` | Same toggle infra + fixed `<section class="bg-white">` painting the *entire* content area opaque in both themes (a blanket `.bg-white` dark rule caught it, not just the header/card) + centered the login card vertically (`main` needed `flex items-center justify-center`) |
| `forgot_password.html` | `/forgot_password` | Just the toggle infra — everything else came free from `auth.css` |
| `reset_password.html` | `/reset_password/<token>` | Toggle infra only |
| `set_password.html` | rendered by `_set_password_template()` for invited users | Toggle infra only |
| `init_reset.html` | `/init_reset` | Toggle infra only |
| `init_2FA.html` | `/init_2FA` (needs `session['pre_2fa_userid']`) | Toggle infra + page-specific `dark:` variants for the QR-code border and the "enter code manually" chip (raw Tailwind, not covered by `auth.css`) |

"Toggle infra" = the 3-piece recipe: pre-paint+config script in `<head>`, `.auth-theme-toggle`
button in the header, `{% include 'js/_auth_theme_toggle_js.html' %}` before `</body>`.

### The one responsive fix (hero.html only)

The "Document Status" product-mock card was vertically centered (`items-center` on the grid)
against the *whole* left column (eyebrow+heading+CTA+trust row), which put it visually mid-heading
at `lg`/`xl` viewport widths (1024–1535px) — not literally overlapping text, but landing awkwardly
close, which is what the owner meant by "it breaks the website." Fixed with a breakpoint-scoped
`lg:mt-96 2xl:mt-0` on the card wrapper: nudges it down only in that cramped range, reverts to the
original (owner-approved) centered position at 1536px+. Verified with actual measured gaps at
1024px (+60px clearance) and 1920px (0px margin, unchanged), not just eyeballing it.

## Dev environment (fixed at the very start of this session, unrelated to dark mode)

- `bin/nx.ps1` had `C:\Users\bes\...\Python313\python.exe` (the *previous owner's own machine*)
  hardcoded as `$Python`. Every `nx` command failed outright on this clone. Fixed to resolve
  `.venv\Scripts\python.exe` instead — portable, matches what `bootstrap.ps1`/`uv sync` always
  creates.
- `uv` wasn't installed. Installed via the standalone installer
  (`irm https://astral.sh/uv/install.ps1 | iex`), not `pip install uv` — the latter needs a
  working `python`, which this Windows machine's Microsoft Store "app execution alias" was
  shadowing with a stub that errors instead of running (Settings → Apps → Advanced app settings →
  App execution aliases — **still not disabled**, not blocking since `uv` doesn't need it, but
  worth knowing if something else on this machine mysteriously can't find `python`).
- **git had no identity configured on this machine at all** — blocked every commit via `gitlint`.
  Set globally: `GRuoss` / `gregory.ruoss@sydoc.ch`.
- `python.bat` (a `py -3` forwarding shim, a workaround predating `uv`) was deleted — redundant
  now.

## Gotchas & notes

- **The pre-commit AND pre-push hooks shell out to bare `python`** (`language: system` in
  `.pre-commit-config.yaml`) — same Store-alias problem as above. Every commit/push this session
  needed `.venv\Scripts` prepended to `PATH` first:
  ```powershell
  $env:Path = "C:\Users\GRR\dev\nexora\.venv\Scripts;$env:Path"
  ```
  (bash sessions used `export PATH=".../.venv/Scripts:$PATH"`). Without it, `git commit` fails the
  `sql-migrate-int`/`sql-sync-check` hooks and `git push` fails the pytest pre-push gate, both with
  a garbled "Python wurde nicht gefunden" (German Store-alias error), not a real failure.
- **`SQL_SYNC_SKIP=1` was needed on every commit** — the SQL-sync hooks need a reachable INT DB
  connection this machine doesn't have (see next point).
- **This machine has no `NEXORA_TEST`/`INT` database access.** One integration test
  (`test_ai_build_accepts_prior_definition_without_question`) genuinely cannot pass without real
  credentials in `env/TEST.env` (per `CONTRIBUTING.md`'s bootstrap checklist, never completed on
  this machine). **Every `git push` this session used `--no-verify`**, each time with the owner's
  explicit in-chat sign-off, because the full pre-push suite (~10 min) fails on that one known,
  unrelated test every time. This is a real gap, not a rubber-stamp — if the DB becomes reachable,
  drop `--no-verify` and let the gate run for real again.
- **Screenshot/`computer` tooling didn't render in this session's browser pane** (pane not
  displayed on the owner's end) — every visual claim in the commits above was verified via
  `getComputedStyle()`/`getBoundingClientRect()` JS checks against the live dev server, not by
  looking at a screenshot. Worth knowing if the next session hits the same tooling gap: it's
  workable, just more verbose than a screenshot would be.
- **Dev server must be restarted after any `.html`/JS-partial edit** — Jinja templates are cached
  for the process's lifetime. Static `.css`/`.js` changes are picked up on reload, no restart
  needed. `nx -r --port:8001` (or whatever port `nx -u --no-conflict` picked).
- A full project-architecture reference (repo map, the page-constellation checklist, the design
  token table, the dev-workflow cheatsheet) was written up as a Claude Artifact mid-session and
  shared with the owner directly in chat — not a repo file, so it isn't linked here, but the owner
  has it. Worth asking them for it if broader context is needed before diving into the next task.

## Untracked / left for owner

- Nothing untracked — `git status` is clean, everything is committed **and pushed**.
- The `NEXORA_TEST` DB credentials gap (above) is the owner's to close whenever convenient — not
  blocking anything right now.

## How to verify

```powershell
cd C:\Users\GRR\dev\nexora
$env:Path = "C:\Users\GRR\dev\nexora\.venv\Scripts;$env:Path"
.\bin\nx.ps1 -u --no-conflict         # starts on next free port, doesn't disturb anything running
.\bin\nx.ps1 -u -b --no-conflict      # same, plus opens a browser at /
```
Then click the sun/moon icon top-right of the header on `/`, `/login`, `/forgot_password`,
`/init_reset`. `/reset_password/<token>`, the invite variant of `/set_new_password`, and
`/init_2FA` all need a real login/reset/invite flow to reach live — can't be driven directly
without DB access on this machine.

```powershell
python -m pytest tests/unit/test_translations.py tests/unit/test_octo_media.py tests/unit/test_reporting_chart_render.py -q
```
All green as of `4eca502e`. Full suite: 1 known failure
(`test_ai_build_accepts_prior_definition_without_question`, DB-credentials gap above), everything
else passes.

## Next steps

**The owner's own words: "the next task is going to be bigger because it includes the dark mode
that already exists and redoing it better" — make the dashboard "look like how it's supposed to."**

This is a *different* dark-mode system from everything in this handoff — the one this session
built is for pre-login pages only. The **existing, older** system is for logged-in pages
(dashboard, admin, reporting, workitems, profile, etc.) and lives in:

- `nx_lib/ui_prefs.py` — DB-backed prefs (`theme`, `accent`, `motion`, `density`, `sidebar`,
  `fontscale`, `radius`, `contrast`, `stripes`, `background`, and a custom-accent hex)
- `templates/_header.html` — the pre-paint script + `window.nxSetUiPref()`, loaded on every
  logged-in page
- `templates/js/_header_js.html` — the actual toggle button wiring for logged-in pages
- `templates/appearance.html` + `templates/js/_appearance_js.html` — the user-facing settings page
  for all of the above
- `static/css/nexora-ui.css` — the token system both old and new dark-mode work ultimately reads
  from

**Before writing any code, the next session needs to ask the owner what "how it's supposed to
look" actually means** — a reference screenshot, a specific page that's wrong, a design doc, or
just "go fix whatever looks bad" (in which case: audit each `--nx-*`-consuming component file for
the same class of bug this session found repeatedly — hardcoded light-only hex colors with no
`html.dark` pairing, blanket selectors that overreach onto elements they shouldn't touch, and
raw Tailwind utility classes that bypass the token system entirely). I do not know which of these
it is. Do not assume and start editing.

## Resuming in a fresh session

Nothing is blocked and nothing is mid-flight — every commit above is finished, tested, and pushed.
If you land here via `/reset-session`: read "Next steps" above first, ask the clarifying question
before touching any logged-in-page CSS, then use this handoff's "The mechanism" and "Where the
actual colors live" sections as the reference architecture — the new work should extend/repair the
*existing* `nexora-ui.css`/`_header.html` system, not replace it with the pre-login pattern built
this session (they're deliberately different systems for a reason: one has a DB-backed user, one
doesn't).
