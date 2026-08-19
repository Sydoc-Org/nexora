# Handoff — Logged-in dark mode rework + app-wide accent-color audit

**Date:** 2026-08-19 · **Branch:** `v3.2.1` · **already pushed to `origin/v3.2.1`** (all 12 commits
below are on GitHub — pushed directly at the owner's explicit request each time, same deviation from
the usual commit-only convention as the prior session; see "Gotchas" for why `--no-verify` was used
on every single one)

**Prior handoff:** [`2026-08-18-prelogin-dark-mode.md`](2026-08-18-prelogin-dark-mode.md) — that
session shipped dark mode for the six pre-login pages and explicitly punted "rework the dark mode
that already exists for logged-in pages" to next time, without knowing what "supposed to look like"
meant. **This session was that next time.** It turned out to be less "redesign" and more "hunt down
and fix real bugs in the existing `--nx-*`/`_header.html` system," driven by the owner reporting
specific things one at a time as they found them while using the app.

## TL;DR

- Recolored the existing dark-mode toggle and added an ambient "fireflies" effect, then — at the
  owner's request — turned fireflies into a proper **Appearance > Background** option (alongside
  Plain/Aurora/Grid) instead of a dashboard-only hardcode, fixing two real bugs along the way (a
  server-side allowlist rejecting the new value; a missing `fetch` `keepalive` that silently
  reverted *any* appearance pref if you navigated right after picking it).
- Did an app-wide sweep (~30 files) for a bug class first found on the profile page: UI elements
  that are supposed to reflect the user's chosen **accent color** but were hardcoded to indigo
  instead. Fixed sidebar chrome, buttons, focus rings, checkboxes, chart colors, and every
  Generali/Workitems/Reporting page that had it. Deliberately left the logo, one "locked spec
  palette" token, and a few chart "primary series" colors alone (see "What was deliberately not
  touched").
- Fixed a real dark-mode bug: `workitems_overview.css` had hardcoded-light rules (an ID selector, an
  `!important`) that were beating the otherwise-correct `.nx-table` dark styles — "the list is still
  white" was a literal, accurate bug report.
- Fixed a sidebar flash-of-wrong-state bug: `html.sidebar-pinned` (drives body's padding) is set
  pre-paint in `<head>`, but the sidebar's *own* open state was only set much later by
  `_header_js.html` on `DOMContentLoaded` — every page load, a pinned sidebar rendered collapsed for
  a beat, then snapped open.
- Two corner-radius bugs in `reporting.css` (accent-tinted border blending into an accent-tinted
  glow; an inner box's radius not scaling with the outer box's `--nx-radius-scale`).
- **Owner interrupted mid-report on a possible "unpin doesn't take effect until reload" bug and said
  it was a false alarm** (they were hovering, which explains the symptom) — not something to chase
  next session, but flagging in case it resurfaces for real.

## This session's commits (oldest → newest, on `v3.2.1`, all pushed)

| Commit | What |
|---|---|
| `3123eec3` | feat(dashboard): recolor dark-mode toggle (teal/orange, matching login), fix "Recent Validations" card's missing `dark:` variants |
| `43e470df` | feat(dashboard): sidebar resting-offset tweak (no more push-on-hover), ambient fireflies (dashboard-only at this point), fix forced `overflow-y: scroll` |
| `d8901132` | feat(appearance): promote fireflies to a real Background option; fix the server-side `ui_prefs` allowlist rejecting it; fix a badge text-wrap bug; fix a `zoom`-vs-`100vh` sidebar gap at non-default font scale |
| `70b4c737` | fix(header): account dropdown menu had zero `dark:` classes — white background regardless of theme |
| `f0659e98` | fix(profile): active nav pill + avatar ring were hardcoded indigo, ignoring the accent picker (`admin-tokens.css`'s `--a-b-indigo` wasn't wired to `--nx-accent-tint`) |
| `7b3c9ea5` | fix: the big one — app-wide accent-color sweep, ~30 files, see below |
| `1649a1fb` | fix(dashboard): trend chart had no `interaction` config (had to hover exactly on the line); line color was hardcoded uppercase hex, which is why the sweep above missed it |
| `710defd6` | fix(dashboard): trend chart tooltip reskinned to match the app instead of Chart.js's default black box |
| `c74cbb21` | fix(workitems): table/list stayed white in dark mode — ID selector + `!important` beating `.nx-table`'s dark styles |
| `c7874746` | fix(reporting): hero card's rounded corners invisible — accent-tinted border blending into the accent-tinted glow above it |
| `4bf5c6a6` | fix(reporting): Ask-AI bar's inner corners didn't nest with the outer gradient-border ring at non-default corner-style prefs |
| `9c267dc0` | fix(sidebar): pinned sidebar flashed collapsed-then-open on every page load |

## What shipped, in more detail

### 1. Fireflies became a real Appearance option

Started as a dashboard-only decorative background (16 randomly-positioned glowing dots, CSS
`@keyframes` + JS-set custom properties per dot). Owner asked for it to be a proper Background
choice like Aurora/Grid. Moved to:

- `templates/_header.html` — `#fireflyField` container, present on every page (was dashboard-only)
- `templates/js/_header_js.html` — spawn/teardown logic, reacts live to the pref via
  `window.__nxSyncFireflies` (called from `_header.html`'s `apply()`)
- `static/css/nexora-ui.css` — the actual dot/glow/drift keyframes, alongside the existing
  `html[data-bg="aurora"|"grid"]` rules
- `static/css/appearance.css` — static preview swatch in the settings page's mini canvas
- Colors: teal `rgb(61, 108, 122)` in light mode (same blue as the login page toggle, per owner
  request), warm amber in dark mode

**Two real bugs found and fixed while wiring this up:**
- `nx_lib/ui_prefs.py`'s `UI_PREF_CHOICES["background"]` was `("plain", "aurora", "grid")` — no
  `"fireflies"`. The save endpoint validates against this allowlist and 400s on anything not in it,
  silently, so the pref never reached the DB.
- The `POST /profile/ui_prefs` `fetch()` in `_header.html` had no `keepalive: true`. Picking any
  appearance setting and immediately navigating (e.g. clicking a sidebar link right after) let the
  browser abort the in-flight save — **this affects every appearance pref, not just background** —
  so the pick would silently revert on the next page. Fixed with one `keepalive: true`.

### 2. App-wide accent-color audit (commit `7b3c9ea5`, the big one)

Root pattern: `--nx-accent`/`--nx-accent-hover`/`--nx-accent-tint`/`--nx-accent-soft` are the tokens
that actually track the user's accent choice (preset or custom hex) — they're re-tinted per
`html[data-accent=...]` in `nexora-ui.css`. Lots of UI across the app was hardcoded to the *literal*
indigo value instead of referencing these tokens, so it silently ignored the accent picker.

Fixed via a dedicated Explore-agent sweep across every post-login template/CSS/JS file, then applied
by hand:
- **Plain CSS files** (`_header.css`, `dashboard.css`, `reporting.css`, `profile.css`,
  `workitems_overview.css`, `source-highlight.css`, `nexora-ui.css` itself): swapped hardcoded hex
  for `var(--nx-accent, <original-hex-as-fallback>)`, and `color-mix(in srgb, var(--nx-accent) N%,
  transparent)` for anything that needed a translucent glow/shadow (no per-accent alpha token
  existed for those, `color-mix()` derives it inline instead of adding more tokens).
- **Raw Tailwind classes in templates/JS partials** (`workitems_overview.html`,
  `_workitems_overview_js.html`, `_workitem_detail_panel_js.html`, all 7 `generali_*.html` pages +
  their JS partials, `admin/_access_control_js.html`, `admin/_user_management_js.html`,
  `prepared_documents.html`, `whats_new.html`): Tailwind arbitrary-value syntax, e.g.
  `text-indigo-600` → `text-[var(--nx-accent)]` — this is an existing pattern in the codebase
  (`dashboard.html` already had `[color:var(--nx-accent)]!` before this session), not a new one.

**Two real bugs surfaced by this work, not pre-planned:**
- `.sidebar-nav-item--active`'s `color` was losing a CSS specificity fight to
  `html.dark .sidebar-nav-item`'s idle-text-color rule (`(0,2,1)` beats a lone modifier class at
  `(0,1,0)`) — the active sidebar item's *text* was silently staying idle-gray in dark mode even
  before this session touched anything. Only became visible once the *background* started correctly
  tracking the accent and the mismatch became obvious. Fixed with a scoped
  `html.dark .sidebar-nav-item--active { color: var(--nx-accent); }`.
- `.sidebar-nav-group` had no `gap` between its header button and its subitems list (0px, vs 2px
  everywhere else via `.sidebar-nav`'s flex gap) — "Admin" + "Overview" rendered as one fused pill
  instead of two. Most visible once active items got a solid accent-tinted background instead of a
  barely-there light indigo tint. Also bumped `body.nx-app .nx-main`'s top padding 28px → 44px (a
  separate, unrelated owner request in the same screenshot).

**Deliberately NOT touched** (flagged as uncertain by the audit, or found to have an explicit
"locked spec" comment while editing, or confirmed with the owner directly):
- `_nexoraLogo.css` / `_header.css`'s dark logo-wordmark gradient — **confirmed with the owner**:
  the logo is deliberate brand artwork, not meant to re-tint with accent.
- `reporting.css`'s `--rl-navy: #312e81` (light mode) — has its own comment, *"Light values are the
  locked spec palette"* — same pattern as the chart colors below, found while editing this session,
  left alone on the same reasoning.
- Chart "primary series" colors in `_reporting_simple_js.html`/`_reporting_viz_js.html`/
  `_generali_dashboard_js.html` — explicitly commented as a "locked ink-navy/indigo-peak spec" or a
  deliberate categorical palette (the *first* series in a multi-metric chart stays indigo on
  purpose, to visually anchor it against the other series' rotating palette colors).
- Semantic/categorical badges (`nx-label--indigo`, `.sev-info`, `.mb-info`, `PROFILE_COLORS`
  rotation, etc.) — these are a fixed multi-hue category system (indigo/green/amber/red/...), same
  pattern as "success = green," not accent-tracking.
- `templates/archive/**` and `templates/js/archive/**` — retired, unrouted pages per `CLAUDE.md`.
- `_errorPages.css` — used by `templates/handlers/_error_base.html`, which doesn't include
  `_header.html` at all (standalone 403/404/500 pages, no accent system to hook into).
- `templates/maintenance.html` — turned out to be the standalone 503 "app is under maintenance"
  splash page (`nx_lib/hooks.py`/`views/core.py` render it directly, no `_header.html`), not the
  admin's Maintenance management page. Also out of scope.

### 3. Dashboard trend chart (commits `1649a1fb`, `710defd6`)

- No `interaction` config meant Chart.js defaulted to `mode: 'nearest', intersect: true` — cursor
  had to land exactly on the 3px line. Set `interaction: { mode: 'index', intersect: false }` so
  hovering anywhere at that x-position shows the tooltip.
- Line/point/gradient color was `'#4F46E5'` — **uppercase hex**, which is why the accent-color
  sweep's (lowercase) grep missed it. Worth remembering if anyone re-runs a similar grep sweep later
  — case-insensitive it next time.
- Canvas doesn't understand `var(--nx-accent)` as a literal color string (it needs a resolved
  value) — read it via `getComputedStyle(document.body).getPropertyValue('--nx-accent')`, same
  pattern this file's `nxAxis()` helper already used for grid/text colors.
- Tooltip reskin: Chart.js's default is a plain black box. Restyled via `plugins.tooltip` using the
  same `getComputedStyle` pattern to pull `--nx-card`/`--nx-border`/`--nx-text`/`--nx-text-meta`.

### 4. Workitems table dark mode (commit `c74cbb21`)

`workitems_overview.css` had zero `html.dark` rules in the entire file (confirmed via grep before
touching anything). The specific bugs:
- `#workitemsTable thead th { background-color: #f9fafb; ... }` — an **ID selector**, so it beat
  `.nx-table thead th`'s otherwise-correct `var(--nx-card)`-based dark styling outright, regardless
  of theme.
- `.workitem-row:hover { background-color: #fbfcfe !important; ... }` — `!important`, always
  near-white on hover no matter what.
- Also fixed: row border, the step-icon-wrapper's ring (`box-shadow: 0 0 0 4px white`, literally
  hardcoded white), the completed-step fill, the expanded-row detail-panel background, and the
  process-step label text colors — all flat light hex with no dark counterpart.

Pattern used throughout: swap the hardcoded hex for `var(--nx-alt|--nx-divider|--nx-card|--nx-text|
--nx-text-sec|--nx-success, <original-hex-as-fallback>)`, matching how `.nx-table` itself already
worked.

### 5. Reporting page corner bugs (commits `c7874746`, `4bf5c6a6`)

- `.reporting-hero`'s border and its background glow (a radial gradient centered *above* the box,
  `50% -80px`) were **both accent-derived** — right where the rounded top corners need to read
  clearly, an accent-tinted border blended into the also-accent-tinted glow and effectively
  disappeared. Fixed by switching the border to `var(--nx-border-strong)` — plain neutral slate,
  contrasts against the glow regardless of accent/theme. General lesson: don't use two
  accent-derived tokens where one needs to visually separate from the other.
- `.reporting-hero__aiwrap` (the "Ask AI" bar's outer gradient-border wrapper) scales its
  `border-radius` with `--nx-radius-scale` (the corner-style preference: Sharp/Standard/Round), but
  the nested `.reporting-simple-aibar` inside its 1.5px padding gap had a flat `12.5px` — only
  correct when scale=1 (Standard). At "Round" (1.6x) the outer ring came out to 22.4px while the
  inner bar stayed frozen at 12.5px, a visible mismatch. Fixed: inner radius is now
  `calc((var(--nx-radius-scale, 1) * 14px) - 1.5px)`, so it always nests concentrically regardless
  of corner-style pref. Verified live at "Round": outer 22.4px, inner 20.9px.

### 6. Sidebar pinned-state flash (commit `9c267dc0`)

`html.sidebar-pinned` (drives `body`'s `padding-left: 220px` reservation) is set **pre-paint**,
synchronously, in `_header.html`'s `<head>` script. But the sidebar's own open state — its width,
label opacity, logo-text opacity, and expanded-nav-group max-height — was only ever driven by
`#nexora-sidebar.pinned`, a class added **much later** by `_header_js.html` on `DOMContentLoaded`,
i.e. after the whole page (including several external CDN scripts: Tailwind Play CDN, Font Awesome,
Google Fonts, Tailwind Elements) finishes loading.

So on every page load with pin on: body already reserved 220px (correct, early), but the sidebar
itself rendered collapsed/unlabeled for that whole gap, then visibly snapped open once the late JS
finally ran. That's "unpinned, then pins itself a second later, rearranging the layout."

Fix: added `html.sidebar-pinned #nexora-sidebar ...` as an additional selector alongside every
`#nexora-sidebar:is(:hover, .pinned) ...` rule (there were 6: width, label opacity, logo text
opacity, three per-nav-group `max-height` rules). Purely additive — `#nexora-sidebar.pinned` still
works exactly as before for interactive toggling (the pin button, live pref changes); the new
selector just guarantees the *initial* state is also correct, since `html.sidebar-pinned` is
guaranteed present from the very first paint and the JS-set class no longer has to win the race.

**Owner then reported what sounded like a related bug** ("pin, reload, unpin — doesn't change state
until another reload") but interrupted their own message and said it was a false alarm — they'd been
hovering the sidebar, which explains the symptom without any code being wrong. Not fixed, not
confirmed broken — just noting it in case it comes back for real with a cleaner repro.

## Gotchas & notes

- **This machine's `python`/`python3` on `PATH` resolve to the Windows Store app-execution-alias
  stub**, not the real interpreter (`.venv\Scripts\python.exe` exists and works fine, it's just not
  first in `PATH`). This breaks the `sql-migrate-int`/`sql-sync-check` pre-commit hooks and the
  pytest pre-push gate with a garbled "Python wurde nicht gefunden" error, same class of problem as
  the prior handoff's Store-alias note but a **different symptom** (that one was about `uv`
  install; this one is about the hooks shelling out to bare `python`). **Every commit and push this
  session used `--no-verify`**, with the owner's explicit sign-off the first time this came up, not
  re-asked each time after. Prepending `.venv\Scripts` to `PATH` (see the prior handoff's fix) would
  let the hooks run for real — flagged to the owner as worth fixing, not done, since fixing it was
  never actually requested, just flagged.
- **Dev server must be restarted after any `.html`/JS-partial edit** — Jinja templates are cached
  for the process's lifetime (`nx -r --port:8001`, or whatever port is in use). Static `.css`/`.js`
  changes are picked up on next reload, no restart needed. Same as the prior handoff's note, just
  re-confirming it's still true and came up constantly this session.
- **The Browser pane's `computer`/screenshot tooling didn't render visible frames this session
  either** — same gap as the prior handoff. Went further than "just use `getComputedStyle`" this
  time: at one point a synthetic `:hover` (via the `computer` tool's hover action) made
  `element.matches(':hover')` return `true` while `getComputedStyle` kept reporting the *pre-hover*
  value even after a full second of real wall-clock wait — i.e. the pane's style/layout pipeline
  appears genuinely stalled while not visibly composited, not just "no screenshot." Confirmed by
  injecting a `width: 999px !important` rule directly and having it *still* read back the old value.
  **Workaround that actually works:** verify via the CSSOM directly (`document.styleSheets` →
  `cssRules` → `.selectorText`/`.cssText`, plus `element.matches(<selector>)`) instead of trusting
  `getComputedStyle` after any *dynamic* mutation (hover, class toggle, live pref change) in this
  pane — `getComputedStyle` was reliable for the page's *initial* load state, just not after
  simulated interaction.
- **`nx_lib/ui_prefs.py`'s `UI_PREF_CHOICES` allowlist is the thing to check first** whenever a new
  value for an existing pref key needs to persist — the save endpoint silently 400s on anything not
  listed, no error surfaced to the user, just a pref that "doesn't stick."
- **A stray `nul` file appeared in the repo root twice this session** — an artifact of running
  `cmd 2>nul` inside a Bash tool call (Git Bash interprets `nul` as a literal filename, not the null
  device, the way `cmd.exe` would). Deleted both times before committing; watch for it if it
  reappears — it's `rm -f nul`, not a real file to investigate.

## Untracked / left for owner

- `static/images/1060-icon.png` — **still untracked, deliberately not committed.** Appeared in
  `git status` partway through the session; not created by this session's own work (best guess: a
  cached avatar from the `/dev/login/<username>` dev-auth shortcut used throughout for verification,
  see `nx_lib/views/auth.py`'s `dev_login`). Flagged to the owner in-chat each time it showed up in
  `git status`; still sitting there. Worth a `git status` check + a decision (commit it, or delete
  it if it really is just a stale cache file) — not blocking anything.
- The `python`/`PATH` Store-alias gotcha above — flagged, not fixed, owner's call whether it's worth
  the five minutes.

## How to verify

```powershell
cd C:\Users\GRR\dev\nexora
$env:Path = "C:\Users\GRR\dev\nexora\.venv\Scripts;$env:Path"
.\bin\nx.ps1 -r --port:8001          # restart if a stale process is still running a pre-session build
.\bin\nx.ps1 -u -b --loginas:gregory.ruoss --port:8001   # or -u --no-conflict for a fresh port
```

Then, logged in:
- **Appearance page** (`/appearance`): cycle Background through Plain/Aurora/Grid/Fireflies, cycle
  Accent through the presets and a custom hex, toggle dark mode — confirm the sidebar, dashboard
  cards, workitems table, and reporting hero card all follow both without a reload.
- **Dashboard** (`/dashboard`): hover the "Documents Processed Over Time" chart anywhere near a data
  point (not just exactly on the line) — tooltip should appear, styled as a dark card not a plain
  black box.
- **Workitems** (`/workitems`): with dark mode on, confirm the table header/rows/hover-state are
  dark, not white.
- **Reporting** (`/reporting`): confirm the hero card's rounded corners are visible against its
  glow, and the "Ask AI" bar's inner corners nest with its outer ring (try Appearance's "Round"
  corner-style pref specifically — that's where the old bug was most visible).
- **Sidebar**: pin it (bottom-left "Keep sidebar open"), then navigate between two pages — it should
  stay open/labeled the whole time, no collapse-then-snap-open flash.

No test suite run this session (all CSS/template/JS changes, nothing Python-side except the one-line
`ui_prefs.py` allowlist fix, which has no dedicated test — worth a quick manual check if this
becomes a habit of skipping). Full suite has the same known DB-credentials gap as the prior handoff
(`test_ai_build_accepts_prior_definition_without_question`).

## Next steps

Nothing is queued or mid-flight. This session was almost entirely owner-driven ("here's a
screenshot, fix this") rather than following a plan document, so there's no plan file to resume from
Options for what's next, roughly in the order they'd likely come up:

1. **More of the same** — the owner has been walking through the app page-by-page reporting visual
   bugs as they find them (dashboard → appearance → profile → workitems → reporting → sidebar, in
   that order this session). If that pattern continues, just keep responding to what they report —
   the "Gotchas" section above (especially the CSSOM-over-`getComputedStyle` verification trick and
   the `ui_prefs.py` allowlist gotcha) should make the next few faster.
2. **The `static/images/1060-icon.png` file** — resolve what it actually is and either commit or
   delete it.
3. **The Store-alias `PATH` issue** — five-minute fix if the owner wants hooks to actually run
   instead of every commit/push using `--no-verify`.
4. Nothing else was flagged as broken or incomplete as of the last message this session.

## Resuming in a fresh session

If you land here via `/reset-session`: nothing is blocked. Read "What shipped" above for the
architecture context (the accent-token system, the `--nx-*` dark-mode pattern, where fireflies live
now), then just wait for the owner to report the next visual bug — that's been the whole workflow
this session and last. The CSSOM-verification workaround in "Gotchas" is worth internalizing before
trying to verify anything visual in this Browser pane; `getComputedStyle` alone will mislead you
after any dynamic interaction.
