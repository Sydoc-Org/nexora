# Handoff: Reporting Page Redesign + Dashboard Builder (nexora)

## Overview
Redesign of nexora's **Reporting** page (`/reporting`) into a flagship surface, plus a new **multi-card dashboard** capability. Four deliverables:

1. **Landing ("Indigo Studio")** — hero with AI command bar + report cards with live preview thumbnails (replaces the flat library list).
2. **Wizard** — one-step-at-a-time flow with a progress rail and live summary (replaces the stacked all-steps-visible page).
3. **Dashboard builder** — a saved view holding multiple cards (KPI / line / bar / donut / table) with **global filters**, **per-card filter overrides**, **drag-to-rearrange**, add/duplicate/remove cards, and an Edit/Done mode.
4. **Restyles** — result drill-through drawer, Advanced builder skin, and dark mode.

## About the Design Files
The bundled `.dc.html` files are **design references created in HTML** — prototypes showing intended look and behavior, **not production code to copy**. The task is to recreate them in the nexora codebase's existing environment: Flask/Jinja templates (`templates/`), plain CSS in `static/css/reporting.css` on top of the app-wide `nexora-ui.css` token system, vanilla JS IIFE partials in `templates/js/`, and Chart.js 4.x (already loaded). Keep all existing `data-testid` attributes and REST endpoints — the e2e suite depends on them.

**Retire the "Editorial Ledger" skin**: remove serif (`Georgia`) and monospace (`ui-monospace`) font treatments from `reporting.css` (the `body.reporting-ledger` block). Everything is Inter now. Also set `Chart.defaults.font.family = 'Inter'`.

## Fidelity
**High-fidelity.** Colors, type, spacing, radii and interactions are final. Recreate pixel-perfectly using the existing `--nx-*` tokens (values listed below map 1:1 to tokens already defined in `static/css/nexora-ui.css`).

## Files in this bundle
- `Reporting Dashboard Prototype.dc.html` — **working interactive prototype** of the dashboard builder (drag, add/remove/duplicate, filter chips, Edit/Done). The state model and handlers in its logic class are a direct spec for the JS.
- `Reporting Redesign.dc.html` — static mock canvas. Section ids: `2a` landing, `1d` wizard, `2b` dashboard (edit-mode visual spec), `3a` drill drawer, `3b` Advanced builder skin, `3c` dashboard dark mode, `1e` single-report result view. (`1a/1b/1c/1f` are superseded explorations — ignore.)
- `Reporting — Current.dc.html` — recreation of today's UI, for before/after reference only.

---

## Design Tokens
All exist in `nexora-ui.css`; light-mode values:

| Purpose | Value | Existing token |
|---|---|---|
| Page bg | `#f9fafb` | `--nx-page` |
| Card bg | `#ffffff` | `--nx-card` |
| Border | `#e5e7eb` | `--nx-border` |
| Border strong | `#d1d5db` | `--nx-border-strong` |
| Divider | `#f3f4f6` | `--nx-divider` |
| Text | `#1f2937` | `--nx-text` |
| Text secondary | `#6b7280` | `--nx-text-sec` |
| Text meta | `#9ca3af` | `--nx-text-meta` |
| Accent | `#4f46e5` | `--nx-accent` |
| Accent tint | `#eef2ff` | `--nx-accent-tint` |
| Violet (per-card filters) | `#7c3aed` / bg `#f5f3ff` / border `#ddd6fe` | `--nx-violet` (+ new tints) |
| Brand gradient | `linear-gradient(135deg,#4f46e5,#7c3aed)` | `--nx-brand-grad` |
| Success / Danger | `#059669` / `#dc2626` | `--nx-success` / `--nx-danger` |
| Radius: cards | `12px` (16px hero) | new; between `--nx-radius` and pill |
| Radius: controls | `7–8px` | `--nx-radius-sm` |
| Card hover | `border-color:#c7d2fe; box-shadow:0 8px 24px -8px rgba(79,70,229,.18); translateY(-2px)` | — |
| Primary btn shadow | `0 2px 8px -2px rgba(79,70,229,.45)` | existing `.nx-btn--primary` |
| Font | Inter (400/500/600/700) | `--nx-font` |

Dark mode: use the existing `html.dark` token values (`#0f172a` page, `#1e293b` card, `#334155` border, `#e2e8f0` text, accents `#818cf8`/`#a78bfa`, chip bg `#312e81` + `#c7d2fe` text). See mock `3c`.

Type scale: page title 20–22px/600/-0.4px · card title 13.5px/600 · KPI label 10.5px/600 uppercase +0.7px `#9ca3af` · KPI value 30px/600/-1px `tabular-nums` · meta line 11px `#9ca3af` · body/controls 12.5–13px · section head 16px/600.

---

## Screens

### 1. Landing — Simple tab (mock `2a`)
Replaces the current `#rsLibrary` layout in `templates/_reporting_simple.html`. Content column `max-width:1120px`, centered, `padding:32px 40px 64px`.

**Hero card**: `border-radius:16px; border:1px solid #e0e7ff; background:radial-gradient(1200px 320px at 50% -80px, #eef2ff 0%, #fff 70%); padding:44px 48px 36px; text-align:center`.
- H2 "Build a report in seconds" — 28px/600/-0.6px.
- Sub "Ask in plain language, or step through the guided builder." — 14px `#6b7280`.
- **AI command bar** (reuses `#rsAiPrompt`/`#rsAiAsk`): outer wrapper `max-width:660px; border-radius:14px; background:var(--nx-brand-grad); padding:1.5px; box-shadow:0 12px 32px -12px rgba(79,70,229,.4)`; inner `border-radius:12.5px; background:#fff; padding:5px 5px 5px 18px; display:flex` with violet wand icon, borderless input (13.5px), gradient "Ask AI" button (`border-radius:9px; padding:11px 20px`).
- 3 suggestion chips: `border:1px solid #e0e7ff; border-radius:999px; color:#4f46e5; font:500 12px; padding:6px 14px`; hover bg `#eef2ff`.
- Two secondary buttons: "New report — guided builder" (`#rsNewReport`) and "New dashboard" (new route/action).

**My reports** header: 16px/600 title + count pill (`border:1px solid #e5e7eb; border-radius:999px; font:600 11.5px; color:#4f46e5; padding:1px 9px`) + right-aligned search (`#rsSearch`, icon inside, `border-radius:8px`, width 200px).

**Report cards** grid `repeat(4,1fr); gap:14px` (auto-fill minmax(240px,1fr) responsive). Card: `border:1px solid #e5e7eb; border-radius:12px; overflow:hidden`; hover per token table above; whole card clickable (existing `openReport`).
- **Preview band** (top): `padding:14px 14px 0; background:linear-gradient(180deg,#fafaff,#fff); border-bottom:1px solid #f3f4f6; height:~78px`. Render a real thumbnail from the saved definition: line → area sparkline (`#4f46e5` stroke 2px, 12% opacity indigo fill, end-point dot); bar → 8 rounded bars `#a5b4fc` with max bar `#7c3aed`; donut → 2-segment ring; total-only → big number 30px `#4f46e5` + green trend. Type badge pinned top-right: white pill, uppercase 10px/600, violet type icon (e.g. "LINE · MONTH"). Cheapest implementation: tiny inline SVGs; do NOT spin up a Chart.js instance per card.
- **Body** (`padding:12px 14px`): name 13.5px/600, 2-line clamp, `min-height:36px`; meta row: 16px gradient avatar circle with initials (8px/600 white) + "owner · rel-time" 11.5px `#9ca3af` + right-aligned stat 11px/600 `#6b7280` (e.g. "1,204 ytd").

**Empty groups** (Library / Shared with me): dashed placeholder `border:1px dashed #d1d5db; border-radius:12px; padding:22px; text-align:center` — bold 13px name + 12.5px `#9ca3af` explanation.

**Tabs**: Simple/Advanced move into the masthead as a segmented control: track `padding:3px; background:#f3f4f6; border:1px solid #e5e7eb; border-radius:8px`; active segment `background:#fff; color:#4f46e5; font-weight:600; box-shadow:0 1px 2px rgba(16,24,40,.06)`. Keep `#rpTabSimple`/`#rpTabAdvanced` ids + ARIA.

### 2. Wizard (mock `1d`)
Same step data/logic (`rsStepMeasure/Scope/Breakdown/Time` in `_reporting_simple_js.html`), new presentation: **only the active step is visible**.

- **Header bar**: back-to-Library button, title "New report" 17px/600, right: "Step N of 4" 11.5px `#9ca3af`, close ×.
- **Two-column grid** `280px 1fr; gap:40px; max-width:1120px`.
- **Progress rail** (left): per step — 28px circle (done: `#eef2ff` bg, `#4338ca` ✓, `#c7d2fe` border; active: brand-gradient bg, white number; upcoming: white bg, `#e5e7eb` border, `#9ca3af` number), 2px connector line (`#c7d2fe` done / `#e5e7eb` upcoming), step title 13px/600 (active `#4338ca`), summary of chosen values 11.5px `#9ca3af` ("Document count", "5 of 5 selected"). Below: **Preview box** `background:#eef2ff; border:1px solid #e0e7ff; border-radius:10px; padding:13px 15px` with running sentence of the report ("Document count · 5 processes · by Export date (month) · this year").
- **Step card** (right): `border-radius:14px; padding:28px 32px`; step title 19px/600 + helper 13px `#6b7280`. Chips: `border-radius:999px; padding:8px 16px; 13px`; selected `1.5px solid #4f46e5; bg #eef2ff; #4338ca; 600` with leading ✓. Group chips under uppercase 10.5px labels ("Time", "Document fields", "Or").
- **Coverage indicator** (replaces the `n/5` pill): inside the chip, a 26×4px progress bar (track `#f3f4f6`, fill `#4f46e5` ≥80% / `#b45309` partial / `#94a3b8` ≤33%) + `n/5` 10.5px in matching color. Keep the existing tooltip listing providing processes.
- **Footer** inside card: Back (ghost) · spacer · "1 of 3 picked" 12px `#9ca3af` · Continue (gradient, with →). Step transition: 200ms fade/slide (see Motion).

### 3. Dashboard builder (prototype file = spec; mock `2b`)
A dashboard is a new saved-report kind (`kind: 'dashboard'`) whose definition is `{ title, globalFilters: [...], cards: [...] }`; each card = `{ id, type: 'kpi'|'line'|'bar'|'donut'|'table', span, title, definition | reportId, filterOverrides }`. Cards run through the existing `/api/reporting/run` per card.

- **Header**: back, editable title (pencil), meta line "N cards · refreshed X ago · shared with N people"; right: "Editing" status pill (`#eef2ff`/`#c7d2fe`/`#4338ca`, 7px indigo dot) shown only in edit mode; "Add card" (indigo-tint button `border:1px solid #c7d2fe; background:#eef2ff; color:#4338ca`); Export (secondary); **Done/Edit** (gradient primary).
- **Global filter bar**: white card `border-radius:12px; padding:12px 18px`; label "GLOBAL FILTERS" 10px/600 uppercase with violet funnel icon; vertical 1px divider; **indigo chips** (`#eef2ff` bg, `#e0e7ff` border, `#4338ca`) one per filter, click opens editor, × removes; dashed "Add filter" chip; right-aligned hint "apply to every card · a card can override them" 11px `#9ca3af`.
- **Grid**: `grid-template-columns:repeat(12,1fr); gap:14px`. Default spans: KPI 3, line 8, donut 4, bar/table 6.
- **Cards**: white, `border-radius:12px; padding:14px 18px`. Header row: grip icon (`fa-grip-vertical`, `#d3d9f8`, edit mode only) · title · optional **per-card filter chip in violet** (`#f5f3ff` bg, `#ddd6fe` border, `#7c3aed` text, funnel icon, ×-removable) · right "inherits global filters" 10.5px `#c4c4c9` when no override.
  - KPI: uppercase label, 30px value, trend line 11px/600 (`#059669` up / `#dc2626` down with trend arrow icon).
  - Line: Chart.js line — indigo `#4f46e5`, width 2.5, tension .4, no points, gradient fill 20%→0, y-grid `#f3f4f6` only, no borders, Inter 10.5px `#9ca3af` ticks. Optional comparison series `#c4b5fd` dashed 1.5px.
  - Bar: Chart.js — palette `#4f46e5 #6366f1 #7c3aed #8b5cf6 #a5b4fc`, `borderRadius:5`, barThickness ~26.
  - Donut: `cutout:'68%'`, palette `#4f46e5 #7c3aed #a5b4fc #e0e7ff`, 2px white borders; **HTML overlay** in the ring center (22px/600 total + 9px "TOTAL"); legend right/bottom with 9px rounded swatches.
  - Table: 2-col grid rows, `#f3f4f6` row rules, values right-aligned 600 tabular-nums.
- **Edit mode** (`editing` flag): shows grips, floating control cluster on hover at card top-right (`top:-11px; right:10px`): 22px square white buttons `border-radius:6px; shadow 0 2px 6px rgba(16,24,40,.1)` — duplicate (`fa-clone`) and remove (`fa-xmark`, red `#dc2626` + `#fecaca` border). Cards get `draggable`.
- **Drag & drop** (HTML5 DnD, as in prototype logic): dragstart → source card `opacity:.35`; dragover target → `border-color:#4f46e5; box-shadow:0 0 0 3px rgba(79,70,229,.15)`; drop → splice source before target in the cards array; dragend clears. (Mock `2b` also shows the aspirational dashed drop-slot + tilted lifted card treatment: `2px dashed #a5b4fc`, bg `rgba(238,242,255,.6)`, dragged card `rotate(2.5deg)` + `0 24px 48px -12px rgba(49,46,129,.35)` — nice-to-have via a custom drag image.)
- **Add-card tile** (last grid item, edit mode only, span 6): `2px dashed #d1d5db; border-radius:12px; min-height:180px`, centered: 40px indigo-tint plus circle, "Add a card" 13px/600, pill buttons Chart / KPI / Table / Donut (violet icons), hint "or drop a saved report here" 11px `#c4c4c9`. Hover: `border-color:#a5b4fc; background:rgba(238,242,255,.4)`.
- **View mode** (Done): all edit chrome hidden; filters chips remain (read-only unless user can edit).

### 4. Single-report result view (mock `1e`)
For reports opened from the library (non-dashboard): same header pattern (back, editable title + "2 rows · 765 ms · run just now" meta, Adjust / Export▾ / **Save** primary / ⋯), filter-chip row with dashed "+ Filter" and right-aligned AI refine pill input; left rail = gradient KPI card (brand gradient bg, white text, 38px value) + stacked secondary stats card (Buckets/Avg/Peak rows split by dividers); right = chart card with segmented chart-type control; below = table card with header row ("Table · N rows", drill hint "Click a row to see the documents behind it"), and a **query peek footer**: `background:#fcfcfd; border-top:1px solid #f3f4f6; font:11px; color:#9ca3af`, db icon + first line of SQL + "— show query"; hover `#4f46e5`; click expands existing `#rsSqlView`.

### 5. Drill-through drawer (mock `3a`)
Restyle of `#rdPanel`: width 640px, backdrop `rgba(15,23,42,.28)`, shadow `-24px 0 64px -24px rgba(15,23,42,.35)`.
- Header: 36px indigo-tint icon chip (`fa-magnifying-glass-chart`), title 16px/600 ("February 2026 — documents behind this point"), meta 11.5px `#9ca3af` ("2 documents · Export date 2026-02-01 → 2026-02-29 · from card "Documents per month""), bordered × button.
- Context chip row: indigo chips for inherited global filters, violet chip for the card override.
- Table: uppercase 10px header row, workitem ids as indigo underlined links (open existing `rdWiModal` preview), type as indigo-tint pill, pages right-aligned tabular-nums.
- Info callout: `border:1px solid #e0e7ff; background:#fafaff; border-radius:10px` with eye icon — "Click a workitem to open the read-only preview…".
- Footer: "Showing all N documents" + CSV/XLSX secondary buttons (green file icons).

### 6. Advanced builder skin (mock `3b`)
Layout untouched (260/1fr/300 grid). Chrome: panels → `border-radius:12px`, token borders, no ledger flatness; mode + view toggles → segmented controls (as tabs above); Run keeps gradient; field list rows get leading field-type icon (`#a5b4fc`) and trailing + on hover with `#eef2ff` hover bg; wells → chips (metrics indigo chip, filters violet chip, columns as draggable rows with grips) + dashed add buttons; results table gets the query-peek footer from §4.

## Interactions & Motion
- Durations: hovers 120–150ms `cubic-bezier(.4,0,.2,1)`; entrances 320–400ms rise (`opacity 0→1, translateY(8px)→0`), staggered 60–80ms per section (reuse `.nx-rise` pattern); wizard step change ~200ms; drawer slide-in 250ms from right. Respect `prefers-reduced-motion` (already handled globally).
- Card hover lift only in view mode; in edit mode hover reveals the control cluster instead.
- Global filter chip click → popover editor (prototype cycles values as a stand-in).
- All destructive actions (remove card) are immediate with the existing toast + an Undo affordance recommended.

## State (dashboard JS module)
`{ editing, dragId, overId, globalFilters: [{field, op, value}], cards: [...] }` — see the prototype's logic class for exact reorder/duplicate/remove/add handlers. Persist via the existing saved-reports API with `kind:'dashboard'`; autosave on Done.

## Assets
No new assets. Icons: Font Awesome 6.4.2 (already loaded) — `fa-wand-magic-sparkles, fa-grip-vertical, fa-clone, fa-xmark, fa-filter, fa-chart-line, fa-chart-column, fa-chart-pie, fa-table, fa-hashtag, fa-arrow-trend-up/down, fa-magnifying-glass-chart, fa-database, fa-file-export, fa-calendar, fa-diagram-project`. Font: Inter (already loaded).
