# Handoff — nexora works on a phone: tab bar, installable app, and the bugs that came with it

**Date:** 2026-09-16 · **Branch:** `feat/354-phone-tabbar` · **19 commits ahead of `main`**,
0 unpushed (the branch is on the remote and deploying to **dev**) · **nothing merged, no PR, no
tag** — the owner asked repeatedly to keep this on dev only.

**Prior handoff:**
[`2026-09-14-dev-staging-envs-shipped.md`](2026-09-14-dev-staging-envs-shipped.md)
(unrelated work; the `2026-09-14-billing-sources-and-reporting-ui.md` pending-flag handoff was
never consumed — see "Untracked / left for owner").

**Issue:** [#354 — Phone navigation: bottom tab bar + More sheet, gated on touch](https://github.com/Sydoc-Org/nexora/issues/354)

## TL;DR

- nexora now has a **phone layout**: a bottom tab bar, the sidebar as a bottom sheet, and every
  page family swept at 390px — dashboard, login/landing, workitems, 13 Generali pages, 12 admin
  pages, 5 reporting pages, the public maintenance page.
- It is also **installable** as an app on Android, Windows and iOS (web app manifest + icons
  rendered from the real CSS logo). No App Store, no cost, nothing to update — it is the live site.
- **The phone layout can never appear on a desktop.** Gated on `(max-width: 768px) and
  (pointer: coarse)` — width alone cannot tell a phone from a half-screen window or a display at
  200% zoom. This was an explicit owner requirement; both directions are pinned by tests.
- Several bugs found along the way were **pre-existing and not phone-specific**: HTML was served
  with no cache headers at all, there was no `CSRFError` handler, and non-PROD session cookies had
  no expiry. All fixed.

## This session's commits (oldest → newest)

| hash | what |
|---|---|
| `4f973ceb` | phone tab bar + bottom sheet, gated on touch |
| `a994a89b` | raise the sheet for users who pinned the sidebar (specificity bug) |
| `5b31961a` | stop caching rendered pages; widen the phone gate |
| `5a658d6d` | dashboard fits a phone |
| `744e8a71` | make nexora installable as an app |
| `f8ff6014` | phone sizing for login + landing |
| `dc6129b2` | workitems overview layout + touch targets |
| `fa623836` | Generali pages touch targets |
| `2b8bba45` | admin pages touch targets |
| `3f08d3b6` | render CSRF failures as a page people can act on |
| `c181b759` | reporting layout + touch targets |
| `9c5422cb` | taller tab bar; unclip the segmented control |
| `ce171d98` | in-app Reload for the installed app |
| `8f699c4f` | clear the iPhone home indicator; mark the active tab |
| `608fdb84` | Eddard's chat panel fits a phone |
| `82b5ad06` | stop the tab bar behaving like selectable text |
| `a3b46705` | lay the phone toolbars out for a phone |
| `be788e95` | stop the active tab's icon disappearing |
| `5c0d1e16` | keep the installed app signed in; recheck session on resume |

## What shipped

**Phone navigation** — `templates/_header.html`, `static/css/_header.css`, `static/js/header.js`
Bottom tab bar with up to three permission-filtered slots plus **More**, which raises the existing
`#nexora-sidebar` as a bottom sheet (same element, so group expand/collapse, the profile menu and
the build stamp all come along). Slots come from the sidebar's own `nav_items` / `tenant_nav` — no
second copy of the permission logic, and no dead tabs. `--nx-tabbar-h: 64px` is the single knob the
bar, the body's bottom padding, the sheet's padding and `scroll-padding-bottom` all read.

**Installable app** — `nx_lib/views/core.py` (`web_app_manifest`), `templates/_app_manifest.html`,
`scripts/make-app-icons.py`, `static/images/icon-*.png`
Manifest served as a **route, not a static file**: `start_url`/`scope` must carry `/nexora` on
PROD/STAGING but not INT, and the app `name` carries the environment so an installed dev icon can
never be mistaken for production. Icons are rendered from the live CSS logo by a committed script
(a home-screen icon cannot animate). **No service worker, deliberately.**

**Pre-existing bugs fixed** — `nx_lib/__init__.py`, `nx_lib/hooks.py`, `templates/handlers/csrf.html`
- HTML had **no `Cache-Control` at all** → pinned home-screen apps froze on an old page, which also
  pinned stale `?v=` asset URLs and made deploys look like no-ops. Now `no-store`.
- **No `CSRFError` handler** → a legitimate refusal rendered Werkzeug's raw "Bad Request". Now a
  proper page with a working **Try again**; enforcement unchanged, API still gets JSON.
- **Non-PROD session cookies had no expiry** → an installed app was signed out every time iOS
  evicted it. `SESSION_PERMANENT` sat inside `if IS_PROD:`. Authenticated sessions are now
  permanent everywhere; the 24h lifetime is unchanged and signed-out visitors stay non-persistent.

**Per-page phone work** — `static/css/{nexora-ui,workitems_overview,reporting,reporting-console,admin,hero,auth}.css`
Shared control sizing (`.nx-btn`, `.nx-input`, `.nx-select`, `.nx-tab`, `.nx-segmented__btn`,
`.pagination-link`) fixed once in `nexora-ui.css`, which cleaned 12 of 13 Generali pages and all 12
admin pages. Reporting needed its own pass because it has a separate `rc-*` / `rs-*` component set.

**Tests** — `tests/e2e/test_mobile_nav.py` (23 tests), `tests/unit/test_{app_manifest,cache_headers,csrf_error_page,session_cookie}.py`

## Next steps

1. **Owner decides when this leaves dev.** Nothing is merged. `main` → staging, tag → PROD. The
   owner has said "keep it on dev" several times — do not open a PR without asking.
2. **Rebase/merge `main` first when that happens.** `main` moved during this work (v3.2.7, 3.2.8,
   3.2.9 all shipped). The branch is 19 commits from an older base.
3. **Follow-up issues not yet filed:** the reporting Advanced tab / report builder / workitem
   document viewer were deliberately left as "works best on a larger screen" rather than
   redesigned; that note has not been written. Also unfiled: the PWA research (see #354 comments in
   conversation, not the issue body).
4. The **workitem document viewer** is the one page family never measured at phone width. I twice
   predicted reporting "needed a redesign" and was twice wrong once measured — measure before
   claiming.

## Gotchas & notes

- **The phone gate is load-bearing.** `(max-width: 768px) and (pointer: coarse)`. Do **not** add
  `hover: none` back (some real phones report `hover: hover`), and do **not** use `any-pointer`
  (a touchscreen laptop reports `any-pointer: coarse` while its trackpad keeps `pointer: fine`).
  Documented in `docs/design/architecture-conventions.md`.
- **`viewport-fit=cover` is now on all 46 page templates.** Without it `env(safe-area-inset-*)`
  returns **zero** and safe-area padding silently does nothing. It has knock-ons: content reaches
  every physical edge, so anything anchored near one needs insets. It broke Eddard's chat panel
  (`100dvh` started counting the status bar) — if something sits oddly near an edge, suspect this.
- **Font Awesome draws glyphs in `.fas::before` via `content`.** Any rule targeting that
  pseudo-element *replaces* the icon. Cost one bug (active tab icon vanished, 0×0).
- **`getBoundingClientRect` returns scaled pixels under Playwright mobile emulation** (~1.1×; a 1px
  border computes as `0.909px`) while `getComputedStyle` returns CSS pixels. Comparing the two
  invents discrepancies — cost one phantom "7px gap" fix that was reverted. Compare rect-to-rect.
- **A bare `1fr` grid track has an automatic minimum** and grows to its content instead of clamping
  to the container. Four mobile overrides in reporting dropped the `minmax(0, …)` their own desktop
  rules have; that single slip was most of a 212px horizontal overflow.
- **Jinja caches templates** unless the app runs in debug. A template edit needs a real restart —
  and on Windows `pkill`/backgrounded `&` starts do **not** reliably free port 8123, so a "restart"
  can silently leave the old server running and you read stale code. Kill via PowerShell by port
  **and confirm the port is free**. This wasted time twice.
- **pybabel fuzzy-matches new strings onto unrelated ones.** It produced "Erneut ausführen" for
  "Try again" and "Laden"/"Charger"/"Carica" for "Reload". Check every new msgid by hand.
- **dev is last-push-wins.** Three releases shipped during this work and each stole the dev slot.
  `gh run list --workflow Deploy --limit 5` before debugging "my change isn't showing".
- Deliberately left under 44px: workitems per-row checkbox (26) and details chevron (35), the
  reporting registry Edit/Delete (44×32), and the `/admin/tenants` card links. Taking them to 44
  would set every table row's height. Reasoning is in the CSS so nobody "fixes" it by reflex.

## Untracked / left for owner

- **`var/handoff-pending` from 2026-09-14** (`billing-sources-and-reporting-ui`) was never consumed
  — this session started unrelated work, so the flag was correctly left alone. It has now been
  overwritten by this handoff's path. That earlier handoff is still unread if it mattered.
- **INT DB change made by hand, not a migration:** `dbo.Users` row for `gregory.ruoss` had
  `twoFA = 0` and `twoFASecret = NULL` set on **INT only**, so the owner could sign in to dev via
  the forgot-password flow. Not a schema change, so no migration. PROD and STAGING untouched.
- `var/screenshots/*.png` from this session are gitignored and not committed.

## How to verify

```powershell
# the gate, both directions, plus every phone test
.venv\Scripts\python.exe -m pytest tests/e2e/test_mobile_nav.py -q
.venv\Scripts\python.exe -m pytest tests/unit -q          # 1928 passed at handoff

# dev is serving this branch (not someone else's)
gh run list --workflow Deploy --limit 5

# the three pre-existing fixes, live
curl -sI https://dev-nexora.sydoc.ch/login | Select-String 'Cache-Control'     # no-store
curl -s  https://dev-nexora.sydoc.ch/manifest.webmanifest                      # name: "nexora (dev)"
curl -sI https://dev-nexora.sydoc.ch/static/images/icon-180.png | Select-String '^HTTP'
```

All suites green at handoff. Nothing is red.

## Resuming in a fresh session

`/reset-session docs/superpowers/handoffs/2026-09-16-phone-ui-and-installable-app.md`
(`/reset-session` takes a specific file path when several handoffs share a date).

Decision record is issue #354 plus this file. The owner drives what happens next — the standing
instruction all session was **keep it on dev**, so do not merge, tag or open a PR without asking.
