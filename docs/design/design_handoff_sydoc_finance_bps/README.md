# Handoff: Sydoc Finance + Sydoc BPS redesign (option 1a on both)

## Overview
Sydoc Finance (`templates/finance.html`) and Sydoc BPS (`templates/bps.html`) are Sydoc's own internal books, not tenant pages. The redesign gives both pages a shared identity so they read as a mirrored pair and stand apart from the rest of nexora:

- a dark **ink header band** carrying the Sydoc brand mark and Sydoc orange,
- the **period as the headline** (big month, prev/next arrows, click opens a picker modal),
- Finance: a **ledger** layout (one row per client: identity column left, statement lines right) and a **timeline** for billable bookings,
- BPS: totals + a **composition bar** in the band, a daily chart, and a **drill-down with Table (default) / Treemap** views, month-over-month gain/loss, and a compact **per-day bookings list** at the leaf.

The app shell (sidebar, `.nx-main`, fonts, icons) is unchanged.

## About the design files
The two `.dc.html` files are **design references built in HTML** (Design Component prototypes, open in a browser with `support.js` next to them). They are not production code. Recreate them in nexora's environment: Jinja templates + `static/css/finance.css` / `static/css/bps.css` + `static/js/finance.js` / `static/js/bps.js` + the `--nx-*` tokens in `static/css/nexora-ui.css`. Do not port the inline styles; turn them into `nx-fin-*` / `nx-bps-*` classes (and shared `nx-sydoc-*` classes for the band + picker, see below).

Each file has two turns on a canvas:
- **1a (top) = the approved design.** Build this.
- **0a (below) = the current page**, recreated for comparison only.

All numbers, names, comments and bookings in the prototypes are **sample data**. The real data comes from the existing endpoints (`/api/finance/section/<key>`, `/api/bps/summary`, `/api/bps/entries`) and the section specs in `nx_lib/finance.py`.

## Fidelity
**High fidelity.** Layout, type sizes, spacing, colours and interactions in 1a are final intent. The user wants it "exactly like this on the site." Hex values below are light theme. Express them through `--nx-*` tokens and add the new tokens listed under Design tokens. Dark theme is not designed yet; the band is already dark, so on dark mode keep it `#0b0d12` (a step darker than `--nx-page` dark `#0f172a`) and use the existing dark tokens for everything below the band.

---

## Shared pieces (both pages)

### Shell (unchanged)
- `body` padding-left 100px (collapsed 64px sidebar), `.nx-main` padding. The prototype uses `36px 40px 40px` for the main padding; keep the app's `.nx-main` but reduce the top padding to 36px on these two pages.
- Sidebar: unchanged, except the active-item bar (`.sidebar-nav-item--active::before`) is **Sydoc orange `#e3633f`** on these two pages only (`body.nx-sydoc` modifier).

### Ink band — `.nx-sydoc-band`
- Background `#111318`, radius 16px (`--nx-radius-hero`), text `#e5e7eb`, overflow hidden. Finance padding `22px 30px 0` (the jump index sits flush at the bottom); BPS padding `22px 30px 26px`.
- **Row 1** (flex, `align-items:center`, gap 10px):
  - Sydoc mark: a 22×26px crop of `static/images/sydoc-logo.png` showing only the orange document glyph. Use `background-size:152.5px auto; background-position:-114.4px -14.3px; background-repeat:no-repeat`. Better: export the glyph as its own small SVG/PNG.
  - Eyebrow "Sydoc internal": 10px/700, uppercase, letter-spacing .12em, `#f08a6c`.
  - Second eyebrow, same style but `#6b7280`: "Accounting" (Finance) / "BPS" (BPS).
  - Spacer, then actions (height 32px, radius 8px, 12.5px/600, gap 7px, icon colour `#9ca3af`):
    - **Finance:** "Close month" primary (`fa-lock`): background `#e3633f`, **text `#111318`** (white on orange fails contrast), hover `#ec7656`. It becomes "Reopen month" (`fa-lock-open`) when the month is closed. Then "CSV" (`fa-file-csv`) and "Print" (`fa-print`), both ghost-outline: transparent, `1px solid rgba(255,255,255,.14)`, text `#e5e7eb`, hover background `rgba(255,255,255,.06)`.
    - **BPS:** "Sydoc Finance" link (`fa-file-invoice-dollar`, no border, `#d1d5db`, hover `rgba(255,255,255,.06)` + white), then "CSV" ghost-outline.
    - Permission gating stays as today (`can_close`, `can_finance`).
- **Row 2** (margin-top 22px, flex, `align-items:flex-end`, gap 40px, wraps):
  - Left block (`flex:1 1 520px`):
    - h1 "Sydoc Finance" / "Sydoc BPS": 14px/600, `#9ca3af`, letter-spacing −.01em.
    - Headline row (margin-top 6px, gap 14px): prev button · period button · next button.
      - Prev/next: 36×36, radius 99px, `1px solid rgba(255,255,255,.14)`, transparent, `#d1d5db`, `fa-chevron-left/right` 12px, hover `rgba(255,255,255,.08)`. Opacity .35 and inert at the range ends.
      - Period button: no border or background, `white-space:nowrap`, baseline-aligned, gap 12px. Main word at **54px/600, letter-spacing −2.2px, line-height 1, white**. Year at 54px/400, `#6b7280`, tabular-nums. Then `fa-chevron-down` 14px `#6b7280`, centred. Click opens the picker modal.
    - Hint line (margin-top 12px): 12.5px/1.5, `#9ca3af`, max-width 64ch.
      - Finance: the existing three-state hint (running / closed / live).
      - BPS: "Every hour booked in the BPS timetool, by task, customer and person, down to the single booking."
  - Right block: a 2-column grid (gap 4px 36px). Row 1 holds eyebrows (10px/700, uppercase, .1em, `#6b7280`). Row 2 holds values (14px/600, `#f3f4f6`, nowrap).
    - Finance: **Status** = 8px dot + "Open · live" (dot `#34d399`). Closed month: `fa-lock` + "Closed {when} by {who}". Running month: amber dot + "Running". **Sources** = "11 of 11 loaded" (the existing load counter; danger colour on failures).
    - BPS: **Period** = the date range text ("1 – 31 Aug 2026"). **Source** = green dot + "{n} bookings loaded".

### Period picker modal — `.nx-sydoc-picker`
- Overlay: `position:fixed; inset:0`, `rgba(17,19,24,.45)`, panel centred horizontally, ~150px from the top. Click outside or Esc closes. Focus is trapped; return focus to the headline button on close.
- Panel: white, radius 14px, shadow `0 24px 64px rgba(16,24,40,.28), 0 0 0 1px rgba(16,24,40,.06)`. Width 440px (Finance) / 460px (BPS).
- Header (padding `16px 18px 14px`, bottom border `#f3f4f6`): title 15px/700/−.02em `#1f2937` ("Choose month" / "Choose period"), close button 28×28 radius 7px `fa-xmark` `#9ca3af`, hover `#f3f4f6`.
- **BPS only**, a "Quick" section (padding `14px 18px 0`): eyebrow, then pills (height 30px, radius 99px, 12px/600, gap 6px): Last month / This month / Last week / Last 3 months. Inactive: white, `1px #e5e7eb`, text `#374151`. Active: `#111318` background + border, white text. These are the existing `PRESETS` in `bps.js`.
- Year switcher (padding `16px 18px 6px`): 30×30 round buttons (`1px #e5e7eb`) around the year (22px/600/−.8px, tabular).
- Month grid: 3 columns, gap 8px, margin-top 14–16px. Each cell is a button, height 62px (Finance) / 58px (BPS), padding `10px 12px`, radius 10px, `1px #e5e7eb`, white. It holds the month short name (14px/600 `#1f2937`) above a status line (11px):
  - Finance status: `fa-lock` + "Closed" (`#9ca3af`); a dot + "Open" (`#047857`) for the latest invoiceable month that isn't closed; a dot + "Running" (`#b45309`) for the current month. Real state comes from the month-close table.
  - BPS status: total hours of that month (e.g. "1,300.5 h"), "Running · {h} h" for the current month, and "No data" before the first BPS export month (3 Aug 2026).
  - Selected cell: `#111318` background + border, white name, status `#f08a6c`.
  - Disabled (future, before `EARLIEST` / outside `MONTH_OPTIONS`, BPS no data): opacity .4, not clickable.
- Finance footer legend (padding `12px 18px 16px`, 11px `#6b7280`, gap 14px): lock "Closed, figures frozen" · green dot "Open, live" · amber dot "Still running".
- BPS footer (top border `#f3f4f6`, padding `14px 18px 18px`): From and To date inputs (height 32px, `1px #d1d5db`, radius 7px, with 10px uppercase labels above) plus a "Show range" button (32px, `#111318`, white, radius 8px).
- Picking a month (or preset, or range) navigates: `?month=YYYY-MM` for Finance, `?from=&to=` for BPS. The URL stays the source of truth, as today.
- BPS headline text by period: a month shows "August" + "2026"; last week shows "Week 39" + year; last 3 months shows "Jun – Aug" + year; a custom range shows "1 – 31 Aug" + year.

---

## Screen: Sydoc Finance (1a)

### Jump index (bottom of the band)
- One **horizontal row, never wrapping**: `display:flex; flex-wrap:nowrap; overflow:hidden`, padding `0 16px`, top border `rgba(255,255,255,.08)`, margin-top 22px.
- Items are anchors to `#fin-<key>`: height 44px, padding `0 7px`, gap 6px, 12px/500 `#d1d5db`, `border-bottom:2px solid transparent`, hover white + border `#e3633f`. Each item is `flex:0 1 auto; min-width:0`, so the label shrinks with an ellipsis if space runs out. `title` = full name.
- Each item starts with a 20×20 tile (radius 6px, 9.5px/700) holding the first two letters of the client:
  - internal: background `rgba(129,140,248,.2)`, text `#c7d2fe`
  - external: background `rgba(96,165,250,.2)`, text `#bfdbfe`
  - services: background `rgba(227,99,63,.22)`, text `#f6b19c`
- Groups are separated by a 1×18px divider `rgba(255,255,255,.12)` with 6px margin. No group labels.
- Short nav labels: Elektro-Material, Compass, Posteingang, **Rechnungen**, **Zustellung**, Neuzugänge · Frigemo, **Xpert**, **EasyTax**, MediaMarkt · Billable services. Add an optional `nav` label to `Section` in `nx_lib/finance.py`; it falls back to the title, then the client.

### Group headers
Flex row, gap 12px, margin-top 34px (first) / 38px: h2 12px/700, uppercase, .1em, `#6b7280` ("Internal customers" / "External clients" / "Sydoc services"). Then the section count in mono 11px/600 `#9ca3af`, then a flex:1 rule `1px #e5e7eb`.

### Client section (ledger row) — `.nx-fin-section`
- Grid `260px minmax(0,1fr)`, gap 48px, padding 26px 0, bottom border `1px #e5e7eb`. **No initials tile and no logo** (deliberately removed).
- **Left column:**
  - Client: 18px/700/−.02em `#1f2937`.
  - Title (e.g. "Posteingang"): 13px/500 `#6b7280`, margin-top 2px.
  - Meta (source label · basis): 11px `#9ca3af`, margin-top 8px.
  - State pill (margin-top 10px): `.nx-label--green` "Live" (or the closed / drift states that exist today).
  - Note, if the section has one: 11.5px/1.5 `#6b7280`, margin-top 12px, `text-wrap:pretty`. It moves here from under the figures.
- **Right column, statement lines:**
  - Header row: grid `minmax(0,1fr) 150px 110px 170px`, padding-bottom 8px, bottom border `#e5e7eb`. Eyebrows (10px/700/.09em uppercase `#9ca3af`): "Figure", **{selected month name}**, **{previous month name}**, "Change". The last three are right-aligned.
  - One line per figure: same grid, padding 12px 0, bottom border `#f3f4f6`, items centred.
    - Label: 13px/500 `#1f2937`.
    - Value: mono, tabular, **17px/600, letter-spacing −.5px**, `#1f2937`, right-aligned. (It was 22px; the user asked for it smaller.)
    - Previous value: mono, 13px `#9ca3af`, right-aligned.
    - Change: right-aligned flex, gap 10px.
      - A comparison bar: 64×6px track `#f3f4f6`, radius 3px. The fill is `#1f2937` at width = value / max(value, prev). A prev marker 2px wide, 12px tall (top/bottom −3px), `#e3633f`, sits at left = prev / max − 1px.
      - The delta text is 12px/600 `#1f2937`, min-width 48px: "▲ +5%" / "▼ −3%" / "Unchanged" / "▲ New". Keep the existing `deltaHtml` rules. It stays neutral ink, no red or green.
  - Multi-block sections (Bucherer: import date / export date) keep a basis eyebrow above each block's lines.
  - **Breakdowns** (margin-top 20px): grid `repeat(auto-fit, minmax(300px, 1fr))`, gap 28px.
    - Head: eyebrow "Per {dim}" plus "{n} rows" (11px `#9ca3af`).
    - Rows: grid `minmax(0,1fr) 80px 110px`, gap 10px, padding 6px 0, bottom border `#f3f4f6`, 12.5px. Key (ellipsis), value (mono), and a share cell: a 56×4px bar with fill **`#e3633f`** plus the pct in mono 11.5px `#6b7280`, width 40px.
    - Keep the existing collapse after 12 rows, the "Show all n" link, the totals, and the matrix (`nx-fin-matrix`) for register × branch.

### Sydoc · Billable services section — `#fin-bps`
- Same ledger grid, padding `26px 0`, no bottom border (last section).
- **Left column:** "Sydoc" / "Billable services" / meta "Sydoc — Project Hours · by booking date" / Live pill / the existing note from `finance.py` (the full billable rule text). Then the button **"All hours in Sydoc BPS"**: height 30px, padding `0 12px`, radius 8px, `#111318` background, white 12px/600, `fa-arrow-right` 11px `#f08a6c`, hover `#1f2937`. It links to `bps` for this month's dates (the existing `data-role="month-link"` logic). Only show it with `bpsPagePerm`.
- **Right column:**
  1. Statement lines, same as other sections: **Billable hours**, **Billable bookings** (from `bookings.figures`).
  2. Two breakdowns side by side (auto-fit minmax 300px, gap 28px, margin-top 20px), row grid `minmax(0,1fr) 70px 70px 110px` (key · hours · bookings in `#9ca3af` · share):
     - **Per Task**: `bookings.by_task`.
     - **Per Customer**: `bookings.groups` (hours, count). Each row is an anchor to that customer's timeline (`#bk-<n>`), hover text `#b2401f`.
  3. Divider row (margin-top 30px): eyebrow "Billable bookings" + 11px `#9ca3af` "one list per customer, as on the invoice" + flex rule.
  4. **Timeline per customer** (list gap 28px, margin-top 18px). This replaces the per-customer `nx-fin-bk` tables, which the user explicitly disliked.
     - Customer head: flex baseline, padding-bottom 10px, bottom border `#e5e7eb`. Name 14px/700 `#1f2937` · "{n} bookings" 11px `#9ca3af` · spacer · "{hours} h" mono 16px/600/−.4px.
     - Per **day** (group the customer's rows by `Datum`): grid `84px 18px minmax(0,1fr)`, column-gap 10px.
       - Date column: right-aligned, padding-top 14px. "3 Aug" 12.5px/600 `#1f2937`; weekday "MON" 10.5px/600/.06em uppercase `#9ca3af`.
       - Rail column: a 1px vertical line `#e5e7eb` over the full height, and a 9×9px dot (white fill, `2px solid #e3633f`, radius 99px) at margin-top 19px.
       - Items column (padding 8px 0): one item per booking, grid `minmax(0,1fr) 72px`, gap 16px, padding 6px 0, baseline.
         - Line 1 = **comment** (`Beschreibung`): 13px/1.45 `#1f2937`, `text-wrap:pretty`. If empty, show "No comment" in `#9ca3af` italic.
         - Line 2 = "{Aufgabe} · {Projektpaket} · {Benutzer}": 11.5px `#9ca3af`, margin-top 2px.
         - Right = "{hours} h": mono 13px/600, 2 decimals.
     - Footer: padding `10px 0 0 112px`, top border `#f3f4f6`, holding the "Show all {n}" / "Show fewer" button (11.5px/600 `#b2401f`, `white-space:nowrap; flex-shrink:0`, underline on hover). Show the first 4 bookings, then collapse.
     - Keep the `truncated` message ("The list stops at 5,000 bookings…") under the timelines.

### Removed / changed vs today (Finance)
- The page-head icon chip, `.nx-fin-filter` row and month `<select>` are replaced by the band and the picker. The month nav links keep their URLs.
- The 2-letter section tiles (`.nx-fin-section__tile`) are removed.
- The KPI strip (`.nx-kpi-strip.nx-fin-kpis`) is replaced by statement lines.
- The per-customer bookings tables are replaced by the timeline.
- The in-page close/reopen confirmation (`#fin-confirm`) stays. Place it directly under the band.
- Print CSS: hide the band actions, prev/next and the jump index. Print the month headline small (e.g. 20px, black). Expand all collapsed lists.

---

## Screen: Sydoc BPS (1a)

### Band (below Row 2)
- A 1px divider `rgba(255,255,255,.08)` bleeding to the band edges (`margin:24px -30px 0`).
- **Totals row** (margin-top 22px, flex end-aligned, gap 48px):
  - "TOTAL HOURS" eyebrow (`#6b7280`), then "1,300.5" at **40px/600/−1.6px white tabular** + "h" 18px/500 `#6b7280`.
  - A 3-column grid (gap 4px 40px) of eyebrows + values (20px/600/−.6px `#f3f4f6` + 12px/500 `#9ca3af` suffix):
    - Service hours "1,086.5" + "84% of all hours"
    - Bookings "2,184"
    - People "14" + "with service hours"
- **Composition bar** (margin-top 24px): height 14px, radius 7px, overflow hidden, gap 3px. Segments are widths in % of total hours: billable `#8b5cf6`, other service `#0891b2`, absence `#d97706`.
- Labels under the bar (margin-top 10px): a grid whose columns are the same three percentages. Each cell: swatch 10×10 radius 3 + label 11.5px `#d1d5db`, then "{h} h" 15px/600 white + suffix 11.5px/500 `#9ca3af`. Billable's suffix is "{pct} of service hours"; the others show "{pct}" of all hours.

### Hours per day (margin-top 30px)
- Head: "Hours per day" 15px/700/−.02em + meta 11px `#9ca3af` "31 days · 1,300.5 h · weekends shaded".
- Chart: height 220px, margin-top 16px, bottom border `#e5e7eb`, dashed gridlines at 0% and 50% (`1px dashed #f3f4f6`). One column per day, flex:1, gap 6px. Weekend columns get a `#f3f4f6` background with radius `4px 4px 0 0`.
- Stacked segments from the bottom: billable `#7c3aed`, other service `#0891b2`, absence `#d97706` (top segment radius `3px 3px 0 0`), with a 2px gap between segments.
- X labels: day number, 10.5px `#9ca3af`, centred under each column.
- Implement with the existing Chart.js 4.5.1 stacked bar (`drawChart`), styled to match: `maxBarThickness` ≈ the column width minus 6px, a weekend background plugin, no y axis labels, and 2 dashed grid lines. Keep the tooltip.

### Drill-down (margin-top 34px)
- **Toolbar** (flex, gap 12px, wraps):
  - "Drill-down" 15px/700.
  - **Order switch**: a track `#f3f4f6` with padding 3px and radius 10px. Buttons are 27px high, padding `0 11px`, radius 7px, 11.5px/600, nowrap. Active: white + shadow `0 1px 2px rgba(16,24,40,.1)` + `#1f2937`. Inactive: transparent, `#6b7280`. Options: "Task › Customer › Person", "Customer › Task › Person", "Person › Customer › Task".
  - Spacer.
  - Filter chips "Billable only" (violet swatch) and "Hide absences" (amber swatch, on by default): height 31px, radius 99px, 11.5px/600, nowrap. Off: `1px #e5e7eb`, white, `#6b7280`. On: border `#c4b5fd`, background `#f5f3ff`, text `#5b21b6`.
  - Search input: 240×31px, radius 99px, `1px #d1d5db`, 12.5px, magnifier icon at left 11px, placeholder "Filter task, customer, person…".
- **Breadcrumb row** (margin-top 16px, min-height 32px, flex, gap 8px):
  - Back button (only when zoomed in): 30×30 round, `1px #e5e7eb`, `fa-arrow-left` 11px.
  - Crumbs separated by `fa-chevron-right` 9px `#d1d5db`. The first crumb is "All tasks" / "All customers" / "All people" by order. The current crumb is 14px/700 `#1f2937`; earlier crumbs are 13px/500 `#6b7280` and clickable.
  - Spacer, then level meta 11.5px `#9ca3af` tabular: "{n} tasks · {h} h" (at a leaf: "{h} h · {n} bookings").
  - **View switch** at the far right: same track style as the order switch. Options are "Table" (`fa-list`, **default**) and "Treemap" (`fa-table-cells-large`). Persist the choice per user (`ui_prefs`) or in localStorage.
- Zoom rule: clicking a row or tile appends its key to the path; the depth is 3 (dims = the order). Changing the order or typing in search resets the path. The filters apply to every level. This is the existing `state.order` / `buildTree` logic, with the tree expanded one level at a time instead of inline.

#### Table view (default)
- Header: grid `minmax(0,1fr) 100px 100px 90px 120px 220px 28px`, gap `0 12px`, padding-bottom 8px, bottom border `#e5e7eb`. Eyebrows: {Task|Customer|Person} · Hours · Billable · Bookings · **vs. July** (the previous period's month name) · Split · (empty).
- Each row is a full-width button with the same grid, min-height 46px, bottom border `#f3f4f6`, hover `#f9fafb`:
  - Name cell: an 8×8 radius-2 marker + name 13px/600 (ellipsis). Marker colours: fully billable `#7c3aed`, partly `#a78bfa`, none `#0891b2`, mostly absence `#d97706`.
  - Hours: mono 14px/600 `#1f2937`. Billable: mono 12.5px `#6b7280` ("·" when 0). Bookings: mono 12.5px `#6b7280`.
  - **vs. July**, right-aligned, 2 lines:
    - Line 1: trend icon (`fa-arrow-trend-up` / `fa-arrow-trend-down` / `fa-minus`, 10px) + pct, 12.5px/600. Colour **`#047857` for up, `#b91c1c` for down**, `#6b7280` for flat. "New" (up colour) when the previous period is 0.
    - Line 2: hour delta "+12.5 h" / "−3.0 h", 10.5px `#9ca3af`, or "not booked in July".
  - Split: a flex:1 track (8px, radius 4px, `#f3f4f6`) holding a bar of width = hours / largest row's hours. Inside it, three flex segments (billable / other / absence, same hues, 1px gaps). Then the pct of the level total in mono 11.5px `#6b7280`, width 36px.
  - Last cell: `fa-chevron-right` 10px `#d1d5db`.
- Total row: same grid, min-height 42px, 12.5px/700, holding "Total" (padding-left 18px), hours, billable, bookings, and the total's vs-previous figure.

#### Treemap view
- Area: 100% × 440px, margin-top 10px. **Squarified** layout (Bruls et al.) of the current level's groups by hours, sorted desc, with a 4px gap between tiles.
- Tile: a button with radius 10px and no border, hover `filter:brightness(.96)`. Colour by category (background / text / subtext):
  - fully billable: `#ede9fe` / `#3b0764` / `#6d28d9`
  - partly billable: `#f1ecfd` / `#2e1065` / `#6b7280`
  - other service: `#e0f5f9` / `#083344` / `#0e7490`
  - mostly absence (>50%): `#fef3c7` / `#78350f` / `#92400e`
- Text block at top-left (12px inset, top 11px), shown only when the tile is > 70×46px:
  - Name: 650 weight, ellipsis. 15px on big tiles (> 220×110), otherwise 12.5px.
  - Hours: mono 600, 22px on big tiles / 14px, followed by "h · {pct}" at 11px.
  - Delta pill, when the tile is > 110×70: padding `2px 7px`, radius 99px, `rgba(255,255,255,.7)`, 11px/600 in the up/down colour, e.g. "↗ +8% vs. July".
- A split strip along the bottom of every tile: 5px tall, three flex segments.
- `title` attribute: "{name} · {h} h · {n} bookings".

#### Leaf level (after the 3rd click) — per-day bookings
Load from `/api/bps/entries` as today. Built for **many bookings per day**:
- Container: top border `#e5e7eb`, margin-top 10px.
- One block per day: grid `96px minmax(0,1fr)`, column-gap 20px, padding 12px 0, bottom border `#f3f4f6`.
  - Left (sticky top): "3 Aug" 13px/700 + "MON" 10.5px/600 uppercase `#9ca3af` on one line; the day total "{h} h" in mono 15px/600; "{n} bookings" 11px `#9ca3af`.
  - Right: one **30px single-line row** per booking, grid `minmax(0,1fr) 180px 64px`, gap 14px, bottom border `#f9fafb`:
    - comment 12.5px `#1f2937` with ellipsis (empty → "No comment" italic `#9ca3af`), full text in `title`
    - package 11.5px `#9ca3af` with ellipsis
    - hours in mono 12.5px/600 (2 decimals, right-aligned)
  - Show the first 5 bookings of a day, then a per-day "Show {n} more" / "Show fewer" (11.5px/600 `#b2401f`, nowrap).
- The breadcrumb meta must equal the sum of the listed bookings (hours and count).

#### Under the drill-down
- Legend row (margin-top 12px, gap 18px, 11px `#6b7280`): Billable / Other service / Absence swatches, plus a hint in `#9ca3af`:
  - Table: "Bar length is hours relative to the largest row; colours are its split. Click a row to zoom in."
  - Treemap: "Tile size is hours; the strip under each tile is its split. Click a tile to zoom in."
- Rule note (`fa-circle-info`, 11px `#9ca3af`, max 90ch): the existing billable rule text, rendered from `bps.BILLABLE_RULES` as today.

### Removed / changed vs today (BPS)
- The page-head icon chip, the period `<form>` row with segmented presets and the date inputs, and the 6-tile KPI strip are replaced by the band, the picker and the composition bar. The form semantics (GET `from`/`to`) stay.
- The inline expanding tree table (`.nx-bps-tree`) is replaced by the zoomable Table / Treemap views. Keyboard: rows and tiles are buttons, Backspace or Alt+← goes up one level, Enter zooms in.

---

## Interactions & behaviour (summary)
- Period headline click → picker modal. Prev/next arrows → previous/next month (Finance: within `MONTH_OPTIONS`, not past the current month; BPS: not before the first data month).
- Everything is a navigation (URL) except the drill-down state, view switch, filters, search, and the "show more" toggles, which are client-side.
- Loading: skeleton shimmer in the statement-line values and the BPS totals. The band renders immediately from Jinja.
- Errors: the existing per-section error block (`nx-fin-error`) sits in the right column of the ledger row.
- Motion: keep `nx-rise` entrances. The modal fades in (opacity 0→1, 150ms, `--nx-ease`). Respect reduced motion.
- Responsive: under 1024px the ledger grid becomes one column (the identity block above the lines). The statement-line grid drops the "Change" bar and keeps the pct. The band's right status grid wraps under the headline, and the headline scales to 40px. The jump index keeps one row with ellipsis.

## State
- Finance: `month` (URL), `closed` state (server), `sections[]` payloads (per-section fetch, as today), per-customer expanded flags for the timeline, picker `{open, viewYear}`.
- BPS: `from/to` (URL), summary payload, `order`, `path[]`, `view: 'table'|'map'` (persisted), `billableOnly`, `hideAbsences`, `query`, the per-day expanded set at the leaf, picker `{open, viewYear}`.
- **New data needed:**
  - BPS drill-down needs **previous-period hours per group** for the "vs. July" column and pills. Extend `/api/bps/summary` with `prev_rows` (same shape, for the preceding equal-length period, or the previous calendar month when the period is a month) and compute per-group deltas client-side.
  - The BPS picker's month cells need **hours per month** (a small `GROUP BY year, month` query), and the Finance picker needs **close state per month** (the existing close table).

## Design tokens
Add to `nexora-ui.css` (both themes), and use the existing tokens for everything else:
```
--nx-sydoc:          #e3633f;  /* brand orange: primary action, active nav bar, share bars, timeline dot, prev marker */
--nx-sydoc-hover:    #ec7656;
--nx-sydoc-soft:     #f08a6c;  /* eyebrow + accents on ink */
--nx-sydoc-ink-text: #b2401f;  /* orange text on white (links, "show more") */
--nx-sydoc-band:     #111318;  /* dark: #0b0d12 */
--nx-sydoc-band-line: rgba(255,255,255,.08);
--nx-sydoc-band-ctl:  rgba(255,255,255,.14);
--nx-gain: #047857;  --nx-loss: #b91c1c;   /* dark: #34d399 / #f87171 */
```
- BPS category hues stay `--bps-billable #7c3aed` (band bar `#8b5cf6`), `--bps-service #0891b2`, `--bps-absence #d97706`. Treemap tints: `#ede9fe`, `#f1ecfd`, `#e0f5f9`, `#fef3c7`.
- Text `#1f2937` / `#6b7280` / `#9ca3af`. On ink: `#fff`, `#f3f4f6`, `#e5e7eb`, `#d1d5db`, `#9ca3af`, `#6b7280`.
- Borders `#e5e7eb`, hairlines `#f3f4f6`, row hover `#f9fafb`.
- Radii: 16 (band), 14 (modal), 10 (month cells, tiles, switch tracks), 8 (buttons), 7 (switch buttons), 99 (pills, round buttons).
- Type: Inter; numbers in `--nx-mono` + tabular-nums. Scale: 54 headline · 40 BPS total · 20 band stat · 18 client name · 17 figure value · 15 section title · 14 · 13 · 12.5 · 11.5 · 11 · 10.5 · 10 eyebrow.
- Shadows: modal only (see above).
- **Accent note:** these two pages intentionally use Sydoc orange instead of the user's accent pick. Only controls outside the band (focus rings, checkbox fill) keep `--nx-accent`.

## Assets
- `assets/sydoc-logo.png` = `static/images/sydoc-logo.png`, cropped to the glyph for the band mark.
- Icons: Font Awesome 6.4.2 (already loaded): `fa-lock`, `fa-lock-open`, `fa-file-csv`, `fa-print`, `fa-file-invoice-dollar`, `fa-chevron-left/right/down`, `fa-xmark`, `fa-arrow-right`, `fa-arrow-left`, `fa-list`, `fa-table-cells-large`, `fa-magnifying-glass`, `fa-arrow-trend-up/down`, `fa-minus`, `fa-circle-info`.
- No client logos (dropped on purpose).

## Files in this bundle
- `Sydoc Finance.dc.html` — prototype; **1a is approved**, 0a is the current page for reference.
- `Sydoc BPS.dc.html` — prototype; **1a is approved**, 0a is the current page for reference.
- `support.js` — runtime needed to open the prototypes.
- `assets/` — images used by the prototypes.
- `ISSUE.md` — ready-to-paste issue text.

## Files to touch in nexora
- `templates/finance.html`, `templates/bps.html` — band, picker, ledger / drill-down markup; add `body.nx-sydoc`.
- `static/css/finance.css`, `static/css/bps.css` — page layout. Put the shared band, picker, switch-track and pill classes in `nexora-ui.css` as `nx-sydoc-*` / `nx-track`.
- `static/js/finance.js` — statement lines, timeline, picker, jump index.
- `static/js/bps.js` — picker, totals + composition bar, zoomable table / treemap (squarify), leaf per-day list, deltas.
- `nx_lib/finance.py` — optional `nav` label per section.
- `nx_lib/views/bps.py` — previous-period rows and per-month totals.
- `translations/{de,fr,it}` — new strings: "Sydoc internal", "Accounting", "Choose month", "Choose period", "Quick", "Show range", "Closed, figures frozen", "Open, live", "Still running", "Running", "No data", "Figure", "Change", "Billable bookings", "one list per customer, as on the invoice", "All hours in Sydoc BPS", "No comment", "Show {n} more", "Treemap", "Table", "vs. {month}", "not booked in {month}", "New", "Split", "Tile size is hours…", "Bar length is hours…", "All tasks/customers/people", "Week {n}".
- `tests/e2e` — update the selectors for the removed month select, KPI strips, bookings tables and tree table. Keep the `data-testid`s on their new equivalents (`finance-month-prev/next`, `finance-close-toggle`, `bps-kpis` → the band totals, `bps-tree` → the drill-down container, etc.).
