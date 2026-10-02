# Phone tab bar: carousel through all tenant pages, plus a tenant picker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Anchor on **function names and quoted snippets**, never line numbers — re-Grep before every edit.

**Goal:** On a phone, the bottom bar's three page slots stop being "the first three pages" and become a moving window over the user's *whole* page list — Generali has eight — with the page you are on always in the middle slot and **More** pinned on the right. Staff who can see more than one tenant get a way to point the bar at one.

**Architecture:** No new route, no new session key, no JavaScript. The window is computed in Jinja from the active page's index and rendered as a three-item slice, so the three `<a>` slots are always `[previous, active, next]`. `static/js/swipe_nav.js` already reads the bar's own slots and needs **no change at all** — its neighbour lookup keeps working because the neighbours are exactly what is rendered. The tenant picker is a list of links carrying `?tenant=<code>` in the existing "More" bottom sheet; `nx_lib/views/tenant.py::apply_tenant_scope` already turns that parameter into `session['tenant_scope']`, with the 404/403/stale-scope rules already written.

**Tech Stack:** Jinja2 (`templates/_header.html`), CSS (`static/css/_header.css`), Flask session (existing `tenant_scope`), Flask-Babel, pytest + Playwright (`tests/e2e/test_mobile_nav.py`).

**Spec:** none authored for this feature. Related background: `docs/superpowers/specs/2026-08-31-tenant-platform-design.md` (there is no `docs/design/tenant-platform-design.md` — the tenant design lives in the spec). Issue: none yet — **open one before Task 1** (see Owner actions).

---

## Global Constraints

- **Nothing on a phone may be draggable sideways.** `tests/e2e/test_mobile_nav.py::test_nothing_scrolls_sideways_on_a_phone` asserts no element has `overflow-x: auto|scroll` with content wider than its box, across five paths, because "left and right belong to moving between views". The carousel must never become a scroll-snap strip. **This plan's design sidesteps it entirely by rendering three slots, not by clipping eight.**
- **The outer 30px of the screen belong to the platform** (`EDGE` in `swipe_nav.js`). In an installed app the back gesture is the only way out of a page. Do not take it, do not `preventDefault`, keep both listeners `{ passive: true }`.
- **A slot a user may not open is never rendered** — the bar reuses the sidebar's permission-filtered sources and never re-implements permission logic. That contract must survive this change.
- **A `tenant_solo` user's UI never names their tenant** (#255). No picker, no tenant label, no "Generali Dashboard" heading for them. The tenant simply *is* their portal.
- **Restart after a template edit** (`nx -r`); `.css` and `.js` need only a reload. This has produced false "the fix didn't work" readings twice in this effort.
- Never `--no-verify`. If the SQL pre-commit hooks block on unrelated INT drift, `SQL_SYNC_SKIP=1 git commit ...`.
- **Commit only — no push, no PR** unless the owner says otherwise.

---

## Context an engineer needs (read first)

- **Branch:** planned on `feat/354-phone-tabbar`, the branch carrying the whole phone effort (49+ commits ahead of `main`). No worktree was cut: the only uncommitted file is the owner's own `static/js/header.js`, which is parked deliberately and **must not be touched, committed or discarded**. There is also a junk file named `t -L 3` in the repo root — leave it.
- **The bar today** — `templates/_header.html`, the block after the comment `{# ========== PHONE TAB BAR (#354) ==========`. It defines `{% macro tabbar_item(url, icon, label, on, testid) -%}` and then branches:
  - `{% if tenant_solo and tenant_nav %}` → `{% set t = tenant_nav[0] %}` and `{% for p in t.pages[:3] %}` — **this `[:3]` is the thing this plan removes.**
  - `{% else %}` → `{% for item in nav_items if item.perm %}`, the three Global entries.
  - Then, outside both branches, `<button type="button" id="nx-tabbar-more" class="nx-tabbar-item" ...>`.
- **`nav_items`** is set further up the same file (`{% set nav_items = [` …) with keys `perm`, `key`, `url`, `icon`, `label`, `short`, `active`, and `always: true` on Reporting. It must stay defined *above* the tab-bar block — the existing comment says so.
- **Active-slot matching is not `item.active`.** The bar deliberately re-derives it, because a tenant-mounted Dashboard sets `active_page` to `tenant_<code>_dashboard` and Workitems to `tenant_<code>_workitems`, neither of which equals `'dashboard'` / `'workitems_overview'`. The existing expression is:
  ```jinja
  {% set on = (item.key == 'dashboard' and (ap == 'dashboard' or ap.endswith('_dashboard')))
           or (item.key == 'workitems' and (ap == 'workitems_overview' or ap.endswith('_workitems')))
           or (item.key == 'reporting' and ap == 'reporting') %}
  ```
  and for tenant pages:
  ```jinja
  {% set on = (active_page == p.active) if p.active != p.endpoint else (tenant_scoped == t.code and active_page == p.endpoint) %}
  ```
  **Keep both. The window index depends on getting `on` right** — an unmatched active page must fall back gracefully (see D5).
- **Tenant context** — `nx_lib/hooks.py::_inject_tenant_nav` supplies `tenant_nav` (`[{"code", "label", "pages"}]`), `tenant_scoped` and `tenant_solo`. `tenant_solo` is `bool(scoped) and len(nav) == 1 and nav[0]["code"] == scoped`.
- **`visible_tenant_nav()`** in `nx_lib/views/tenant.py` returns every tenant the session can view (membership **or** a `tenant.<code>.view` grant), each page already carrying a resolved `url` and a display `label`; an unresolvable page is omitted by `_tenant_nav_page`. **So the page list is already permission-filtered — do not filter again.**
- **`session['tenant_scope']` already exists and already does the persistence.** `nx_lib/views/tenant.py::apply_tenant_scope` reads `?tenant=<code>`:
  ```python
  raw = request.args.get("tenant")
  explicit = raw is not None
  ```
  `?tenant=<code>` selects, `?tenant=` (present, empty) means the global view, **absent keeps the current scope**. Unknown tenant → 404, one the session may not view → 403, a remembered scope that no longer resolves is dropped silently. The picker therefore needs **no new route and no new session key** — only links.
- **`swipe_nav.js` reads the bar, by design.** Its `slots()` is `Array.from(document.querySelectorAll(".nx-tabbar a.nx-tabbar-item"))` and `neighbourHref(step)` finds the active slot then returns `items[i + step]`. Its own docstring says it reads the bar "rather than keeping a second list of pages that could drift out of step with it". **With the active page centred, `items` is `[prev, active, next]`, so `i` is 1 and `i ± 1` is exactly right. No change to this file.**
- **Phone gate** is `@media (max-width: 768px) and (pointer: coarse)` in both the CSS and `swipe_nav.js`. Never width alone — a half-screen desktop window and 200% zoom both drop under 768px and must keep the desktop drawer.
- **CSP:** `style-src` in `nx_lib/config.py` includes `'unsafe-inline'`, so an inline `style="…"` attribute is allowed if a later phase needs one. `script-src` is **nonce-gated** (`content_security_policy_nonce_in=["script-src"]`) — any inline script needs `nonce="{{ csp_nonce() }}"`.
- **View transitions are already on for phones** — `@view-transition { navigation: auto; }` in `nexora-ui.css`, cancelled to `animation: none` under `html.nx-motion-reduced` and `prefers-reduced-motion`.
- **Migrations needed: NO.** **New permission: NO** (reuses `tenant.<code>.view`). **i18n needed: NO if you reuse existing msgids** — `Tenants` and `Global` both already exist (checked in `translations/de/LC_MESSAGES/messages.po`). Only a genuinely new string pulls in the `/nx-i18n` cycle. **Deploy excludes: nothing new** (no new top-level file).
- **Generali's eight pages**, in registry order: `/generali-dashboard`, `/generali/additionalServices`, `/generali/baseServices`, `/generali/documents`, `/generali/importStatus`, `/generali/pdqm`, `/generali/projectManagement`, `/generali/reporting`. A staff account (`ben.streich`) sees three tenants: `generali`, `ms02`, `sydoc`.

---

## Decisions locked in

| # | Decision | Rationale |
|---|---|---|
| D1 | **Three slots are rendered, not eight-clipped.** The window is a Jinja slice `pages[start:start + 3]`. | With the active page centred, the three slots *are* `[prev, active, next]`. A clipped eight-wide track with a transform would render five invisible slots, need the transform plumbed through CSP, and buy nothing a slice does not — and it is the shape that risks becoming finger-draggable and breaking `test_nothing_scrolls_sideways_on_a_phone`. |
| D2 | **Window rule: `start = max(0, min(active_index - 1, total - 3))`.** | Owner chose "you in the middle" (option A). The `min` clamps at the right-hand end so the last window is the final three; the `max` clamps at the left so the first window is the first three. With `total <= 3` it degenerates to "render them all", which is today's behaviour. |
| D3 | **No wrap at either end.** | Matches #368 as shipped: arriving back at the first view from the last reads as having gone the wrong way, with no visual cue that you looped. |
| D4 | **`swipe_nav.js` is not modified.** | Its contract is "the bar is the list". Centring the active page makes that contract deliver the carousel for free. A change here would be a second source of truth — the exact thing its docstring exists to prevent. |
| D5 | **No active slot → window starts at 0.** | On a page that is not one of the bar's views (profile, an admin sub-page) `neighbourHref` already returns `null` and nothing navigates. The bar should then look like it always did: the first three. |
| D6 | **The bar's list has three cases**, in order: `tenant_solo` → that tenant's pages; a resolvable `tenant_scoped` for a multi-tenant user → that tenant's pages; otherwise `nav_items` (Global). | Extends the existing two-branch shape by one case rather than reworking it. A staff user who has not picked a tenant keeps exactly today's bar. |
| D7 | **The tenant picker is links with `?tenant=<code>` in the More sheet.** No new route, no new session key, no JS. | `apply_tenant_scope` already implements selection, memory, permission checks and the 404/403 rules. Anything else duplicates it. |
| D8 | **`tenant_solo` users never see the picker and their tenant is never named.** | #255. For them there is nothing to pick, and naming it leaks an internal concept. |
| D9 | **Phase 3 (the sliding animation) is optional and separable.** | Phases 1–2 deliver the behaviour the owner asked for. The slide is motion polish; if it fights view transitions it can be dropped without losing the feature. |
| D10 | **"More" stays a sibling of the slots and is never part of the window.** | Owner's explicit requirement, and it is what keeps random access when the slots move. |

---

## Owner actions

- **Open a GitHub issue** for this and put its number in the branch/commit subjects (house rule: never a bare `#NNN` — always `#NNN — short description`).
- **Decide whether the picker also belongs on desktop.** This plan scopes it to the phone sheet only. The desktop sidebar already lists every tenant as its own group, so there is nothing missing there — but if you want an explicit "current tenant" affordance on desktop, that is a separate change.
- **`static/js/header.js`** is still uncommitted and is yours: your step-1a swipe handler (superseded by `swipe_nav.js`) plus a whole-file editor reformat, 727 insertions / 575 deletions. Nothing in this plan touches it, but it will keep showing in `git status` until you decide.

---

# PHASE 1 — The carousel

Goal: the three slots become a window over the whole list, active centred, for a `tenant_solo` user. No tenant picker yet, no animation.

### Task 1: A test that fails because the bar shows the first three

- [ ] Re-read the bar block in `templates/_header.html` (Grep `PHONE TAB BAR (#354)`) and `tests/e2e/test_mobile_nav.py` around `def test_nothing_scrolls_sideways_on_a_phone` for the fixture idiom (`phone_page`, `_login`).
- [ ] Add `test_tabbar_centres_the_active_page` to `tests/e2e/test_mobile_nav.py`: log in as a tenant user, visit a tenant page that is **fifth** in the list, and assert the bar's `a.nx-tabbar-item` slots are exactly three and that the one carrying `aria-current="page"` is at **index 1**.
- [ ] Run it and watch it fail: `./.venv/Scripts/python.exe -m pytest tests/e2e/test_mobile_nav.py -q -p no:randomly --no-cov -k centres`
- [ ] Commit the failing test.
  ```
  test(phone): pin the active page to the middle tab slot

  Fails today: the bar renders pages[:3], so a page further down the list
  lights no slot at all and swiping from it does nothing.

  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  ```

### Task 2: Compute the window in Jinja

- [ ] In `templates/_header.html`, inside the `{% if tenant_solo and tenant_nav %}` branch, replace `{% for p in t.pages[:3] %}` with a windowed slice. Compute the active index first with a namespace (Jinja loop variables do not escape their loop):
  ```jinja
  {% set ns = namespace(active=-1) %}
  {% for p in t.pages %}
    {% set on = (active_page == p.active) if p.active != p.endpoint else (tenant_scoped == t.code and active_page == p.endpoint) %}
    {% if on %}{% set ns.active = loop.index0 %}{% endif %}
  {% endfor %}
  {% set total = t.pages | length %}
  {% set start = 0 if ns.active < 0 else [[ns.active - 1, 0] | max, [total - 3, 0] | max] | min %}
  {% for p in t.pages[start:start + 3] %}
  ```
- [ ] Keep the existing per-page `on` / `icon` derivation inside the render loop unchanged.
- [ ] Restart (`nx -r` — this is a template edit) and run the test green.
- [ ] Commit.
  ```
  feat(phone): centre the active page in the tab bar's window

  The bar rendered pages[:3], so five of Generali's eight pages lit no slot
  and could only be reached through More. It now renders a three-wide
  window over the whole list with the active page in the middle, clamped at
  both ends.

  swipe_nav.js is untouched on purpose: it reads the bar's own slots, so
  with the active page centred the slots ARE [prev, active, next] and its
  neighbour lookup keeps working -- which is what its docstring means by
  never keeping a second list of pages.

  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  ```

### Task 3: Prove swiping now reaches every page

- [ ] Add `test_swipe_walks_the_whole_tenant_list` to `tests/e2e/test_mobile_nav.py`, modelled on the existing swipe test (Grep `touchstart` in that file for the synthetic-gesture helper around `target.dispatchEvent(mk('touchstart', x1, y1));`).
- [ ] Walk forward from the first page, asserting the URL changes each time, and that after `total - 1` swipes you are on the last page and one more swipe changes nothing (D3, no wrap).
- [ ] Run it. **If it fails, do not touch `swipe_nav.js` first** — check the rendered slots, because the likely cause is the active-index derivation in Task 2, not the gesture.
- [ ] Commit.

### Task 4: Keep the sideways rule green

- [ ] Run `./.venv/Scripts/python.exe -m pytest tests/e2e/test_mobile_nav.py -q -p no:randomly --no-cov` in full.
- [ ] Run the phone sweep over the tenant pages and confirm no page gained a draggable region:
  ```bash
  MSYS_NO_PATHCONV=1 ./.venv/Scripts/python.exe scripts/phone-sweep.py --pages /generali-dashboard,/generali/documents,/generali/pdqm
  ```
  `slide=0` on every row is the pass condition.
- [ ] No commit if nothing changed; otherwise fix and commit.

---

# PHASE 2 — The tenant picker

Goal: a staff user who can see more than one tenant can point the bar at one, from the More sheet.

### Task 5: A test for the picker

- [ ] Add `test_more_sheet_lists_tenants_for_staff` to `tests/e2e/test_mobile_nav.py`: log in as a staff account, open the More sheet (`#nx-tabbar-more`), and assert a link per viewable tenant carrying `?tenant=<code>`.
- [ ] Add `test_tenant_solo_user_sees_no_picker`: assert the picker block is absent **and** that the tenant's display name appears nowhere in the rendered page (#255).
- [ ] Run both, watch them fail, commit.

### Task 6: Render the picker in the sheet

- [ ] In `templates/_header.html`, inside the sidebar/sheet markup (Grep `tenant_page_link` for the existing per-tenant group macro), add a picker block guarded by `{% if tenant_nav | length > 1 and not tenant_solo %}`.
- [ ] Each entry is `<a href="?tenant={{ t.code }}">{{ t.label }}</a>`, marked current when `tenant_scoped == t.code`. Add one global entry linking `?tenant=` (present, empty) — that is how `apply_tenant_scope` is told "global view".
- [ ] **Heading string — reuse, do not invent.** Checked against `translations/de/LC_MESSAGES/messages.po`: `Tenant`, `Tenants`, `Workspace`, `Organization` and `Global` all already exist as msgids; `Switch` and `All tenants` do **not**. Prefer `Tenants` for the heading and `Global` for the un-scoped entry, which needs no translation work at all. If you do add a new msgid, run `/nx-i18n` in the same commit — `test_translations.py` fails the build on any msgid not translated (non-fuzzy) in de, fr **and** it.
- [ ] Restart, run the Phase 2 tests green, commit.

### Task 7: Point the bar at the scoped tenant

- [ ] Extend the bar's branch selection to D6's three cases. The new middle case is a multi-tenant user with a resolvable `tenant_scoped`:
  ```jinja
  {% set bar_tenant = (tenant_nav | selectattr('code', 'equalto', tenant_scoped) | list | first) if tenant_scoped else none %}
  ```
  Use `tenant_nav[0]` for `tenant_solo`, `bar_tenant` when it resolves, and fall through to `nav_items` otherwise.
- [ ] **Do not re-filter permissions** — `visible_tenant_nav()` already returned only viewable tenants, so a `tenant_scope` the user may not view cannot appear in `tenant_nav`, and `apply_tenant_scope` would have 403'd it anyway.
- [ ] Add `test_bar_follows_the_picked_tenant`: pick a tenant, assert the bar's slots are that tenant's pages.
- [ ] Restart, run green, commit.

### Task 8: Full suites

- [ ] `./.venv/Scripts/python.exe -m pytest tests/unit -q -p no:randomly --no-cov`
- [ ] `./.venv/Scripts/python.exe -m pytest tests/e2e/test_mobile_nav.py -q -p no:randomly --no-cov`
- [ ] `./.venv/Scripts/python.exe -m pytest tests/integration -q -p no:randomly --no-cov -k "tenant or generali"`
- [ ] `CHANGELOG.md` entry under `[Unreleased]`, and a line in `docs/howto/white-label.md` describing how a staff user switches the bar's tenant.
- [ ] Commit the docs and changelog together with the final green run.

---

# PHASE 3 — The slide (optional polish)

Only start this if Phases 1–2 are merged and the owner still wants motion. **The feature is complete without it.**

### Task 9: Decide whether it is worth it

- [ ] Watch a swipe on a real phone first. Cross-document view transitions are already on, so the bar already cross-fades between windows. If that reads well enough, **stop here and delete this phase.**
- [ ] If a directional slide is wanted, the mechanism is a `view-transition-name` on the slot row plus a pair of keyframes — *not* a transform on a clipped eight-wide track, which would reintroduce the draggable-strip risk D1 avoids.
- [ ] Whatever is added must be cancelled under `html.nx-motion-reduced` **and** `@media (prefers-reduced-motion: reduce)`, matching the existing block in `nexora-ui.css`.

---

## Gotchas & notes

- **Jinja loop variables do not escape the loop** — that is why Task 2 uses `{% set ns = namespace(...) %}`. Setting a plain `{% set %}` inside a `{% for %}` and reading it after will silently give you the value from before the loop.
- **`t.pages[start:start + 3]` is safe past the end** in Jinja (Python slicing), so a tenant with fewer than three pages needs no special case — it renders what it has, which is today's behaviour.
- **`tenant_scoped` is a code, `tenant_nav` entries carry `code`** — compare like with like. `tenant_scoped` may be set from the user's own organization even when they never picked anything (see `apply_tenant_scope`'s fallback to `organization_tenant(...)`), so D6's middle case can fire without the user having touched the picker. That is intended: it means a staff member who belongs to an organization inside a tenant gets that tenant's bar by default.
- **Do not add a `min-width` to the slots.** `.nx-tabbar-item` is `flex: 1 1 0; min-width: 0` precisely so four items share the bar evenly at 375px; a minimum would push "More" off the edge on the narrowest phone.
- **Restart after every template edit.** Jinja caches. This has produced two false "the fix didn't work" readings in this effort already.
- **Measure at more than one width.** Every number in the original phone work was taken at 390×844, which is how a toolbar that was draggable at 375 shipped looking fine. `scripts/phone-sweep.py` runs seven iPhone geometries in both Chromium and WebKit; in Git Bash it needs `MSYS_NO_PATHCONV=1` or MSYS rewrites `--pages /reporting` into a Windows path.
- **WebKit is not optional for this.** The reporting page overflowed by 53px in WebKit at every width and by 0 in Chromium. Install once with `./.venv/Scripts/python.exe -m playwright install webkit`.
- **The bar is rendered on every page and hidden by CSS**, never by user-agent sniffing — so nothing here may vary by cache key or by a UA string.
- **`aria-current="page"`** is what both the CSS and `swipe_nav.js` fall back to for finding the active slot. If Task 2 changes how `on` is derived, keep emitting it.
