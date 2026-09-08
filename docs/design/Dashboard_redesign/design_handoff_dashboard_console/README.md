# Handoff: Dashboard redesign (console layout, option 1a)

## Overview
Redesign of the nexora Dashboard (`templates/dashboard.html`) so it reads as an operations
console in the same visual family as the Reporting console, while staying clearly a different
page. The page loses its card-grid look: KPIs become one borderless strip separated by
hairlines, the "over time" chart spans the full content width with underline tabs, and a single
backlog card at the bottom shows a 14-day multi-series trend. The right-hand "Recent
Validations" column and the separate hourly chart card are gone — hourly is now a tab on the
main chart.

## About the design files
The files in this bundle are **design references created in HTML** (a Design Component
prototype), not production code. They show the intended look, density, and behavior. The task
is to recreate the design in nexora's existing environment — Jinja templates +
`static/css/*.css` + Chart.js 4.5.1 + the `nx-*` token/component system in
`static/css/nexora-ui.css` — not to port the prototype's inline styles.

Open `Dashboard Redesign.dc.html` in a browser (keep `support.js` next to it). Three layout
options are in the file; **option 1a (the top-left one) is the approved design**. 1b and 1c are
kept only as context for why 1a looks the way it does.

## Fidelity
**High fidelity.** Colors, type sizes, spacing, and chart geometry in 1a are final intent. The
prototype hardcodes colors as hex; in nexora these must be expressed through the existing
`--nx-*` custom properties so light/dark theming and tenant branding keep working. Where a
prototype hex has no token, add one rather than hardcoding.

## Screen: Dashboard (single view)
Target: `templates/dashboard.html`, styles in `static/css/dashboard.css`, behavior in
`templates/js/_dashboard_js.html`. Content width in the prototype is 1180px with 22px side
padding (1136px of content); in the app it should follow the existing `.nx-main` width.

### 1. Page head (row 1)
- Left: existing `nx-page-icon` square, 36×36, radius 10, amber gradient
  (`#d97706` → `#ea580c`), white `fa-gauge-high` glyph, shadow `0 8px 20px -6px rgba(217,119,6,.55)`.
- Title "Dashboard": 22px / 600 / letter-spacing −0.5px / `#1f2937`.
- Next to it, one muted line, 11.5px `#9ca3af`: user name + last sign-in
  ("Ben Streich · letzte Anmeldung 31.08.2026 21:05"). This replaces the current two-line
  title + subtitle block — the marketing subtitle is dropped.
- Right: live indicator (7px green `#059669` dot + "Aktualisiert 06:47:12 · neu in {n}s",
  11.5px `#9ca3af`, tabular-nums) and a secondary "Aktualisieren" button
  (height 31, padding 0 11, radius 8, `#fff` on `1px solid #e5e7eb`, 12.5px/600,
  hover border `#d1d5db`, `fa-rotate` icon in `#9ca3af`).
- All of row 1 is one flex row, `gap:12px`, `align-items:center`, spacer before the right group.

### 2. Filter row (row 2)
- Flex row, `gap:8px`, `margin-top:18px`, `padding-bottom:14px`, `border-bottom:1px solid #e5e7eb`.
- Label "Prozess": 10px / 700 / uppercase / letter-spacing .1em / `#9ca3af`.
- Scope picker: reuse the existing `.nx-scope` component (`NexoraProcessPicker`) unchanged,
  restyled to height 29, radius 8, 12.5px/500 text, hover border `rgba(217,119,6,.35)`,
  min-width 260px, summary text truncated with ellipsis. Menu: white, radius 8,
  `1px solid #e5e7eb`, shadow `0 8px 24px rgba(16,24,40,.12)`, rows 12.5px with a
  15px amber checkbox (`accent-color:#d97706`), client rows bold, process rows indented,
  today's count right-aligned in 11px `#9ca3af`. Row hover `#fef7ed`.
- Right: range segmented control 14 T / 30 T / 90 T — one bordered group, height 29,
  radius 8, active segment `#fef3e2` background with `#b45309` text, inactive white with
  `#9ca3af`, 11.5px/600, 1px dividers between segments. This is **new** and drives the range
  of the main chart and the backlog trend.

### 3. KPI strip (row 3) — borderless
- 4-column grid, no gaps, no cards: `grid-template-columns:repeat(4,minmax(0,1fr))`,
  `border-bottom:1px solid #e5e7eb`, each cell `padding:18px 30px 16px` and
  `border-left:1px solid #f3f4f6` (the leading hairline on the first cell is acceptable;
  drop it if you prefer `:first-child`).
- Cell content: label 10px / 700 / uppercase / .09em / `#9ca3af`; below it a flex row
  (`align-items:flex-end; justify-content:space-between; gap:16px`) with
  - left: value in monospace, tabular-nums, 32px / 600 / letter-spacing −1.4px / line-height 1 /
    `#1f2937`; under it 11px/600 delta in `#059669` (good) or `#b45309` (bad) followed by
    "vs. gestern" in 400 `#9ca3af`.
  - right: 120×36 sparkline (no axes), 1.6px stroke, filled area at 14% opacity of the stroke
    color, `stroke-linejoin:round`, whole svg at `opacity:.9`.
- The four KPIs, in order, with sparkline colors:
  1. **Heute importiert** — value 595, delta +12% (good), stroke `#d97706`
  2. **Heute verarbeitet** — value 60, delta −38% (bad), stroke `#059669`
  3. **Aktueller Rückstand** — value 1,247, delta +4% (bad), stroke `#d97706`
  4. **Durchschn. Verarbeitungszeit** — value 15h, delta −1.5h (good), stroke `#059669`
- Deltas are day-over-day; "good" is direction-aware (fewer backlog / lower time = green).
- Loading: keep the existing `skeleton-shimmer` blocks for value and sparkline.

### 4. Main chart (row 4) — full width, no card
- Container `padding:16px 0 8px`, no border, no background.
- Header flex row, `gap:10px`: title 15px / 700 / −0.02em / `#1f2937`
  ("Verarbeitete Dokumente im Zeitverlauf" / "Heute verarbeitete Dokumente nach Stunde"),
  then meta 11px `#9ca3af` tabular-nums ("14 Tage · Spitze 2,650" / "Spitze 130 um 08:00"),
  spacer, then two **underline tabs** (`gap:16px`): transparent buttons, 12px/600,
  `padding:0 0 5px`, `border-bottom:2px solid` — active `#d97706` border with `#1f2937`
  text, inactive transparent border with `#9ca3af` text.
- Body: full content width (1136px in the prototype), height ~290px, `margin-top:14px`.
- Tab 1 "Zeitverlauf": line/area chart of processed documents per day over the selected range.
  Y grid every quarter of a rounded max, labels in `#9ca3af`, x labels every other day
  (`08-18 … 09-01`), amber line with a soft amber area fill.
- Tab 2 "Heute nach Stunde": bar chart per hour of today, same axis treatment.
- In nexora both remain Chart.js canvases (`processedOverTimeChart`, `hourlyChart`) —
  the second canvas moves into this tabbed area instead of its own card at the bottom.
  Keep the existing empty state for the hourly view.

### 5. Backlog trend (row 5) — borderless
- No card: `padding:18px 0 4px`, `margin-top:10px`, separated only by
  `border-top:1px solid #e5e7eb`. The page has no card frames at all.
- Header flex row: "Rückstand" 15px/700/−0.02em; meta 11px `#9ca3af` "1,247 offen · +48 seit gestern";
  spacer; legend (wrapping flex, `gap:12px`) with one entry per process: a 16px line swatch
  (`border-top:2.5px`, style matching the series' line style) + process name 11px `#6b7280`
  + current count 11px `#9ca3af`.
- Body: eyebrow "VERLAUF 14 TAGE" (10px/700/uppercase/.09em/`#9ca3af`) then a multi-series
  line chart, ~1080×200, y axis rounded to 400s, x labels every other day.
- Series (color + line style + today's count):
  | Process | Color | Line style | Today |
  |---|---|---|---|
  | 02_Posteingang | `#d97706` amber | solid | 612 |
  | 03_Invoice_New | `#7c3aed` violet | dashed | 341 |
  | 01_Scan_Eingang | `#0891b2` cyan | dotted | 188 |
  | 04_Archiv | `#db2777` pink | double/solid-thin | 106 |
- When the scope filter resolves to a single process, the chart falls back to one
  "Rückstand" series (amber, solid) instead of the per-process breakdown.
- Data source: `dbo.BacklogHistory` on the Statistics DB, written every 30 min by
  `ops/backlog_history/backlog_history.py` (per source/client/process snapshots). A new
  endpoint is needed — see State & data below.

### Removed from the current page
- The right-hand "Recent Validations" card and `#activity-feed` (and its
  `api/dashboard/recent_activity` call, unless kept elsewhere).
- The standalone "Documents Processed by Hour (Today)" card — folded into the chart tabs.
- All card frames (`nx-card`) on this page — KPI cards, chart card, feed card
- The four `nx-stat` KPI cards with icon chips — replaced by the borderless strip; the
  `nx-stat__chip` icons are dropped entirely.
- The "Here's a real-time overview…" subtitle.

## Interactions & behavior
- **Chart tabs**: client-side only, no refetch of the other series; active tab is the amber
  underline. Default "Zeitverlauf".
- **Range 14/30/90 T**: refetches `processed_over_time` and the backlog trend with the new
  window; persist the choice per user (the app already has `nx_lib/ui_prefs.py`).
- **Scope picker**: unchanged behavior — on change POST `api/dashboard/set_filter` and
  refresh KPIs, main chart and backlog trend.
- **Auto refresh**: existing polling stays; the header shows last refresh time and a
  countdown to the next one. The "Aktualisieren" button forces an immediate refresh.
- KPI values keep the existing count-up animation (`animateValue`, 1500ms).
- Hover on chart points/bars: existing Chart.js tooltip styling from the reporting console.
- Responsive: below ~1024px the KPI strip becomes 2×2 (keep the hairlines as a grid),
  charts go full width, legend wraps.

## State & data
Existing endpoints (keep):
- `GET api/dashboard/kpi_stats` — imported today, processed today, current_backlog
- `GET api/dashboard/avg_processing_time`
- `GET api/dashboard/processed_over_time` — needs a `range` (days) parameter
- `GET api/dashboard/hourly_stats`
- `POST api/dashboard/set_filter`

New/changed:
- **KPI deltas + sparklines**: `kpi_stats` must also return, per KPI, the previous-day value
  (for the delta) and a 7-point daily series (for the sparkline).
- **Backlog trend**: new `GET api/dashboard/backlog_trend?range=14` returning
  `{ labels: [...], series: [{ name, values: [...] }] }` from `dbo.BacklogHistory`,
  scoped by the active client/process filter, one series per process (max 4-5, rest folded
  into "Andere") or a single total series when one process is selected.

Client state: `view: 'time' | 'hour'`, `range: 14 | 30 | 90`, active scope selection,
last-refresh timestamp + countdown.

## Design tokens (prototype values → nexora)
Map to `--nx-*` in `static/css/nexora-ui.css`; add tokens where none exist.
- Text: `#1f2937` primary, `#6b7280` secondary, `#9ca3af` meta
- Surfaces: `#fff` page, `#f9fafb` sunken, `#fef7ed` accent tint, `#fef3e2` active segment
- Borders: `#e5e7eb` standard, `#f3f4f6` hairline/divider
- Accent: `#d97706` (with `#ea580c` for the gradient, `#b45309` for accent text)
- Status: `#059669` success/green, `#b45309` warning text
- Chart series: `#d97706`, `#7c3aed`, `#0891b2`, `#db2777`
- Radius: 8 (controls), 10 (page icon), 99 (dots/pills)
- Shadows: only `0 8px 24px rgba(16,24,40,.12)` on the scope menu
- Type: UI sans (Inter in the app) 10 / 11 / 11.5 / 12.5 / 14 / 15 / 22px;
  numbers in the mono stack (`--nx-mono`) with `font-variant-numeric: tabular-nums`;
  KPI value 32px/600/−1.4px
- Spacing rhythm: 14px between rows, 18-30px inside KPI cells, 22px page side padding

## Assets
No new assets. Icons are Font Awesome 6.4.2 (`fa-gauge-high`, `fa-rotate`, `fa-chevron-down`),
already loaded. Charts are drawn as SVG in the prototype only for convenience — implement
them with the already-bundled Chart.js 4.5.1.

## Files in this bundle
- `Dashboard Redesign.dc.html` — the design prototype; **option 1a is the approved layout**
- `support.js` — runtime needed to open the prototype locally
- `ISSUE.md` — a ready-to-paste issue description
- `design_system/` — the nexora "slim" UI kit this page is the first instance of:
  - `readme.md` — the design guide (the one rule, type, colour, spacing, states, migration steps)
  - `tokens/*.css` + `styles.css` — the CSS custom properties; `--nx-*` names match `nexora-ui.css`, plus new semantic tokens (`--ctl-h`, `--nx-series-*`, `--fs-*`, `--sp-*`) to add there
  - `components/<group>/<Name>.jsx` — reference implementations with a `.d.ts` props contract and a `.prompt.md` usage note per component; lift the exact values from these, they are not meant to run in the Jinja app
  - `ui_kits/nexora_app/index.html` — the dashboard composed from those components (open directly; the page needs a local server for the component loader)
  - `SKILL.md` — drop the whole `design_system/` folder into your Claude Code skills directory to make it invocable

## How to implement against the kit
Build the CSS classes for the new page from the component sources: each `.jsx` is a
one-to-one map to a class family (`KpiStrip` → `.nx-kpi-strip`/`.nx-kpi`, `FilterRow` →
`.nx-filter-row`, `SectionRule` → `.nx-section-rule`, `UnderlineTabs` → `.nx-tabs--underline`,
`SegmentedControl` → `.nx-segmented`, `ChartHeader` → `.nx-chart-head`, `SeriesLegend` →
`.nx-legend`). Put them in `nexora-ui.css` (not `dashboard.css`) so the next migrated page
reuses them.

## Files to touch in nexora
- `templates/dashboard.html` — markup
- `static/css/dashboard.css` — new KPI strip, chart header, backlog trend styles
- `templates/js/_dashboard_js.html` — tabs, range control, backlog trend chart
- `nx_lib/views/` (dashboard API blueprint) — KPI deltas/series, `range` param, `backlog_trend`
- `translations/{de,fr,it}` — new strings ("Prozess", "Zeitverlauf", "Heute nach Stunde",
  "Rückstand", "Verlauf 14 Tage", "Aktualisieren", "vs. gestern")
- `tests/e2e` — the removed `#activity-feed` and hourly card selectors will need updating

---

## Implementation status (2026-09-05)

Implemented per `docs/superpowers/plans/2026-09-04-dashboard-redesign-console.md`.
Deliberate divergences from the text above:

- **Colour.** The prototype's amber `#d97706` is `var(--nx-accent)` in the app, not a
  fixed hue — the app ships indigo by default and amber is one of seven user-selectable
  accents. Only the chart series keep fixed colours, as `--nx-series-1..5`.
- **Copy.** English is the source locale, so every string entered the code in English
  and the German wording above lives in `translations/de/LC_MESSAGES/messages.po`.
- **Range persistence** rides the session (like the process filter), not `ui_prefs.py`.
- **Page title** stays tenant-aware (`<Tenant> Dashboard` / `Global Dashboard`, #255 /
  migration `0097`); only the marketing subtitle was dropped.
- **e2e** work was additive — the pre-existing dashboard e2e never referenced the
  activity feed or the hourly card.

Further deviations discovered during execution:

- **Format strings use brace placeholders** (`{days}`), not `%(days)s`. Jinja's `_()`
  always applies `rv % variables`, so a bare `%(days)s` in a translated string raised
  `KeyError` and 500'd the page.
- **The sign-in note keeps its `{% if login_at %}` guard**, so it stays a
  once-per-login greeting (#146) rather than permanent chrome.
- **Sparkline colour is per-KPI** (accent, success, accent, success), following this
  README's own list, rather than being derived from whether lower is better.
- **Both charts label their x axis with raw ISO dates** and cap the tick count.
- **The KPI strip omits the sparkline entirely** for an all-zero series.
