# Handoff: Nexora Reporting — "Console" Redesign

## Overview
A redesign of the Nexora reporting area (report library, result view, new-report wizard, dashboards, scheduled runs). The chosen direction is **"Console"**: a light, dense, product-y workbench — persistent left nav + sources rail, content area per screen. This replaces the current reporting page (German UI, sidebar app shell) with a cleaner English-language reporting workspace.

## About the Design Files
The files in this bundle are **design references created in HTML** (`Redesign B - Console.dc.html`, opened in a browser with `support.js` alongside). They are prototypes showing intended look and behavior — **not production code to copy directly**. The task is to **recreate this design in the target codebase's existing environment** (React/Vue/etc.) using its established patterns and libraries. If no frontend environment exists yet, pick the most appropriate framework and implement the screens there.

## Fidelity
**High-fidelity.** Colors, typography, spacing and interactions are final intent. Recreate pixel-perfectly with the codebase's existing component library where equivalents exist.

## Design intent — the user's wishes from the design sessions
These are the decisions and intentions expressed while iterating; treat them as requirements:

1. **No global command/search bar** above the content — it was removed as redundant. Search lives inside the Library screen only.
2. **No vanity stats in the sidebar** — a "documents imported this month" card was explicitly removed. The sidebar holds only navigation and sources.
3. **Report cards must be compact** — original cards were "too big, too long". Single-line title with ellipsis, tight padding (10×12px), short 22px sparkline, slim footer.
4. **Card layout is user-switchable: 2 per row or 4 per row** (toggle next to the sort dropdown). No other densities.
5. **Hover animations must be subtle** — an earlier "draw the sparkline" sweep was rejected. Final: on card hover, the sparkline's area fill fades in (opacity 0 → 0.14, 0.45s ease) and an endpoint dot fades in. Nothing moves.
6. **Every report card has a "…" menu** with Share / Archive / Delete (Delete removes the card; Share opens the share modal).
7. **Share modal** — invite people/teams with view/edit permission, current access list (owner + team row), footer with org-wide link setting + "Copy link".
8. **IMPORTANT — Results caching:** the "Results" nav item must ALWAYS show the last rendered result from cache. Never an empty state; clicking it restores the most recent run without re-querying.
9. **Scheduled page** — full screen listing scheduled report deliveries: on/off toggle per row (off rows dim to 55% opacity), report name, cadence, delivers-to, format badge, last-run status (green dot), next run, row "…" menu. "New schedule" opens a modal (report picker, repeats + time, deliver-to, format chips PDF/CSV/Link only, footer shows computed next run).
10. **Sources get visual detail** — each source in the sidebar is a small card: type icon (database / connector plug), pulsing green status dot (2.4s box-shadow pulse), a 12-bar recent-activity strip (latest bar in accent color), doc count + latency footer.
11. **Result view chart** stretches the full height of its row — same bottom edge as the right column (AI insight / Anomalies / Query cards). Chart scales proportionally (`preserveAspectRatio="xMidYMid meet"`), never stretched/distorted.
12. **SQL snippet has syntax colors** — keywords indigo `#4f46e5` (bold), functions teal `#0e7490`, string literals amber `#b45309`.

## Screens / Views

### 1. Library (default)
- **Purpose**: browse, search, run and manage saved reports.
- **Header row**: `Library` title (19px/700), pill count badge ("5 reports"), spacer, secondary button "New dashboard", primary button "New report".
- **Filter row** (margin-top 12): full-width search input (33px tall, radius 8), sort `<select>` (Recently updated / Name / Most run), layout toggle (2-per-row / 4-per-row icon pair; active segment gets accent tint bg + accent icon).
- **Section header**: "MY REPORTS" (11px/700, 0.08em tracking, uppercase) + count + hairline rule filling the rest.
- **Card grid**: `display:grid; gap:12px; grid-template-columns: repeat(2 or 4, minmax(0,1fr))` per toggle.
- **Report card** (white, 1px `#e2e5ea` border, radius 10, padding 10×12, shadow `0 1px 2px rgba(16,22,35,0.04)`; hover: accent border + `0 4px 14px -4px rgba(79,70,229,0.25)`):
  - Row 1: type tag (LINE/DASHBOARD, 9.5px/700 uppercase chip w/ icon; line = accent on accent-tint, dashboard = gray) · "N runs" (right) · "…" kebab (22×22 hover square) opening the card menu.
  - Row 2: name, 13px/600, one line, ellipsis.
  - Row 3: sparkline SVG 22px tall (line reports) or 2×2 mini-dashboard placeholder rects (dashboards). Sparkline: accent 1.6px polyline; area fill + endpoint dot hidden at rest, fade in on card hover (see intent #5).
  - Footer (top hairline): 16px avatar circle (accent bg, initial), "ben.streich · {updated}" 11px gray.
  - Card menu (absolute, right-aligned, radius 9, shadow `0 8px 24px -6px rgba(16,22,35,0.18)`): Share, Archive, divider, Delete (red `#c92f42`, red-tint hover `#fdf0f2`).

### 2. Result view
- **Purpose**: a rendered report run.
- Breadcrumb-ish header: title "DEMO" + pencil edit, meta "8 rows · 32.1 s · just now"; right: "Run again" (accent-tint), "Export ▾" (white), "Save" (accent solid), "…" (icon button).
- Filter tokens row: chips `field value ✕` + dashed "+ Filter" button.
- **KPI row**: 5 cards (grid, gap 12) — uppercase 10px label, 21px/700 tabular value, optional delta (11px/700, red `#c92f42` for negative), 10.5px sub.
- **Main row**: grid `minmax(0,1fr) 292px`, gap 12, `align-items:stretch`.
  - **Chart card** (flex column so it fills full row height): toolbar (title "Volume over time", chart-type segmented control column/line/pie, Forecast toggle switch, horizon select, palette + download icon buttons), legend (Imported accent / Exported `#101623` / Backlog `#c92f42` right axis), SVG line chart (viewBox 780×268, fills remaining height, proportional scaling). Forecast region: 4%-opacity accent rect + dashed divider + "FORECAST" label; forecast series dashed.
  - **Right column** (flex column, gap 12): "AI insight" card (accent-tint header w/ wand icon, body text w/ bold figures), "Anomalies" card (dot-colored rows w/ values), "Query" card (header + Copy link; `<pre>` SQL in mono 10.5px on `#f7f8fa`, syntax-colored per intent #12).
- **Rows table**: card w/ header ("Rows", "8 actual · 3 forecast", hint "click a row to see the documents behind it"); 4-col grid (Date / Docs imported / Docs exported / Backlog), uppercase 10px header cells on `#f7f8fa`; numeric cells right-aligned tabular with accent-tint inline bar behind values; forecast rows tagged with FORECAST chip and muted color.

### 3. Wizard (new report)
4 steps (Measure / Processes / Breakdown / Time range) as step chips (active: accent tint bg, accent border/dot); measure list with coverage badges ("5/5"); summary panel on the right. Reached via "New report".

### 4. Dashboard
Dashboard view with widget grid (kept from the base design; secondary priority).

### 5. Scheduled
- **Purpose**: manage recurring report deliveries. See intent #9.
- Header: `Scheduled` title + "2 schedules" pill + primary "New schedule" (opens modal).
- Sub-line: "Reports run automatically and get delivered to your inbox or team." (12.5px `#8a93a6`).
- Table card, 8-col grid `44px 1.4fr 1.1fr 1.2fr 90px 1fr 110px 40px`: toggle / Report / Cadence / Delivers to / Format / Last run / Next run / kebab. Toggle: 26×15 pill switch, accent when on, `#cdd2da` off; off row opacity 0.55.

### Modals (shared pattern)
Fixed overlay `rgba(16,22,35,0.4)`, centered white card 440px, radius 12, shadow `0 24px 64px rgba(16,22,35,0.25)`, header row (accent icon + 13.5px/700 title + ✕), body padding 14×16, gray footer bar `#f7f8fa`. Backdrop click closes; card click does not.
- **Share modal**: invite input + permission select + "Invite" button; access list; footer "Anyone at Nexora with the link can view" + "Copy link".
- **New schedule modal**: Report select, Repeats + At (2-col), Deliver to input, Format chips (PDF active / CSV / Link only), footer "Next run: …" + Cancel + "Create schedule".
- Also existing: Help modal (560px) and AI chat popover (bottom-right, 372px).

## App shell (all screens)
- Top bar: 30px accent app icon (chart glyph), "Reporting" 15px/700, BETA chip (accent on accent tint, uppercase 10px), spacer, "2 sources · synced 2 m ago" w/ green dot, "Help" + "AI chat" white buttons.
- Body grid: `196px 1fr`, gap 24. Left rail is sticky (top 20px).
- **Nav** (Workspace group): Library (count), Results, Dashboards (count), Scheduled (count). Active item: white bg, `#101623` text, weight 700; inactive `#57617a`/500. 13px, radius 8, icon 15px column.
- **Sources group**: source cards per intent #10.

## Interactions & Behavior
- Nav switches screens; state is screen enum: `library | result | wizard | dashboard | scheduled`.
- **Results caching rule (intent #8)** — restore last rendered result, no empty state, no re-query.
- Card click → opens result. Kebab click stops propagation, toggles that card's menu (one open at a time). Delete removes the report from the list. Share opens share modal with the report's name in the title.
- Card hover: border → accent, lifted shadow, sparkline area/dot fade in (0.45s ease).
- Layout toggle persists per-session (component state; persist per user in production).
- Schedule toggle flips instantly; off rows dim.
- Source status dot: infinite 2.4s pulse (`box-shadow 0 0 0 0 → 0 0 0 5px transparent`, rgba(24,164,94,…)).
- Modals close on backdrop click, ✕, Cancel; "Create schedule" closes (wire to API in production).

## State Management
- `screen` (enum above), `overlay` (`help | chat | share | newSchedule | null`), `shareName` (string), `menuId` (open card menu), `removed` (deleted report ids), `layout` (`grid`=2-col | `list`=4-col), `schedOff` (disabled schedule ids).
- Data fetching: report list, report run result (cached last run), schedules, source health (status, latency, recent activity buckets, doc counts).

## Design Tokens
- **Accent**: `#4f46e5` (indigo; themeable — the prototype exposes it as an `accent` prop and derives a 9%-alpha tint). Accent tint: `rgba(79,70,229,0.09)` / `#edf0ff`.
- **Neutrals**: page bg `#f5f6f8`, card `#ffffff`, text `#101623`, secondary text `#57617a`, muted `#8a93a6`, border `#e2e5ea`, hairline `#f0f2f5`, table header bg `#f7f8fa`, disabled toggle `#cdd2da`.
- **Semantic**: success `#18a45e`, danger/negative `#c92f42`, warning `#d97706`, exported-series black `#101623`.
- **SQL syntax**: keyword `#4f46e5`, function `#0e7490`, string `#b45309`.
- **Type**: 'Schibsted Grotesk' (Google Fonts), system-ui fallback. Scale: 19px/700 page titles, 15px/700 app title, 13px nav, 12.5px body/buttons, 11–11.5px meta, 10px/700 uppercase labels (0.08–0.1em tracking), 21px/700 KPI values. Numbers always `font-variant-numeric: tabular-nums`. Mono for SQL: ui-monospace/SF Mono/Consolas.
- **Radii**: cards 10, modals 12, buttons/inputs 8, chips 7, tags 4–5, pills 99.
- **Shadows**: card `0 1px 2px rgba(16,22,35,0.04)`; card hover `0 4px 14px -4px rgba(79,70,229,0.25)`; menu `0 8px 24px -6px rgba(16,22,35,0.18)`; modal `0 24px 64px rgba(16,22,35,0.25)`.
- **Controls**: inputs/buttons 33px tall; icon set is Font Awesome 6 (swap for the codebase's icon library).

## Assets
- `assets/nexora-logo.png`, `assets/default-icon.png` (user avatar placeholder) — from the existing product.
- Icons: Font Awesome 6.4.2 classes in the prototype; map to your icon system.
- Charts are inline SVG in the prototype; implement with the codebase's charting library, matching series colors, dashed forecast styling and the shaded forecast region.

## Files
- `Redesign B - Console.dc.html` — the full prototype (all 5 screens + modals). Open in a browser; `support.js` must sit next to it. Markup is in the `<x-dc>` template; data/handlers in the `Component` class at the bottom.
- `support.js` — prototype runtime only; ignore for implementation.
- `assets/` — logo + avatar.
