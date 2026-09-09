# Handoff: Workitems overview redesign (console layout)

## Overview
Redesign of the Workitems overview (`templates/workitems_overview.html`) in the same visual
family as the redesigned Dashboard (`docs/design/Dashboard_redesign/…`, implemented 2026-09-05):
borderless white page, hairline rules instead of card frames, console page head, underline tabs,
quiet status colors. The heavy filter card, boxed table and count pill are gone. New since the
old page: status underline tabs, a table/documents view toggle, an inline expanding detail per
row (stage stepper, extracted fields with confidence, audit timeline, page previews with a
"Full mode"), and a floating selection bar.

## About the design files
`Workitems Redesign.dc.html` is a **design reference created in HTML** (a Design Component
prototype), not production code. Open it in a browser with `support.js` and `image-slot.js`
next to it. The task is to recreate the design in nexora's existing environment — Jinja +
`static/css/*.css` + the `nx-*` token/component system — not to port inline styles.
`image-slot.js` is prototype-only (droppable image placeholders); in the app those areas render
real page previews from the media endpoint.

## Fidelity
High fidelity: type sizes, spacing, and hierarchy are final intent. As with the dashboard,
prototype hexes map to `--nx-*` tokens; the prototype's accent is a tweak (owner previews it
amber `#d97706`) and must stay `var(--nx-accent)` in the app. Reuse the classes the dashboard
migration already added to `nexora-ui.css` (`.nx-filter-row`, `.nx-section-rule`,
`.nx-tabs--underline`, `.nx-segmented`, `.nx-chart-head`) wherever they fit.

## Screen: Workitems overview

### 1. Page head (row 1)
Same construction as the dashboard head: 36×36 radius-10 accent-gradient icon square
(`fa-layer-group`), title 22px/600/−0.5px ("Global Workitems" / tenant-aware per #255 +
migration 0098), one muted 11.5px subtitle line, spacer, then live meta
(7px green dot + "Total 1,038 · updated 06:47:12", tabular-nums), a secondary
"Export CSV" button (h31, radius 8, `fa-download`), and a primary accent "Import" button
(`fa-upload`). Import keeps the existing drop-zone overlay + process modal behavior.

### 2. Filter row (row 2)
One flex row (`gap:8px; margin-top:18px; padding-bottom:14px; border-bottom:1px solid #e5e7eb`):
- "PROCESS" eyebrow + the existing `.nx-scope` picker (`NexoraProcessPicker`), restyled to
  h29/radius 8 like the dashboard's; menu rows show today's count right-aligned.
- Search input (h29, icon-left, 220px) — replaces the old 4-column filter grid's search cell.
- Stage select (h29).
- "Advanced" as an **underline toggle** (12px/600, 2px accent underline when open), not a button.
- Spacer, then secondary "Save view" (bookmark icon) and a text-only "Reset".
- The old Status select is gone — status filtering moved to the tabs (row 4).

### 3. Advanced panel (collapsed by default)
Opens below the filter row, closed by a matching hairline (`border-bottom`), no card:
- 3-column grid: Date range preset select, From, To (mono placeholders `yyyy-mm-dd hh:mm:ss`,
  keep flatpickr).
- "DOCUMENT VALUE SEARCH" eyebrow, then query rows on the same 3-column grid
  (field combobox / operator select / value input with an inline ✕). Row 2+ is preceded by an
  AND/OR segmented pill pair + hairline (one combinator for the group, as today). "+ Add filter"
  accent text button. Same serialization contract as the current form
  (`doccomb`/`docfield`/`docop`/`docvalue` index-aligned, hidden-input quirks preserved).

### 4. List header (row 4)
"Workitems" 15px/700, meta 11px `#9ca3af` ("{n} shown · sorted by last movement"), spacer,
**status underline tabs** — All / Ready / In progress / Done, each with a muted count —
active = 2px accent underline + `#1f2937` text (deleted status stays permission-gated; add it
as a fifth tab only when `deleted_status_perm`). Right of the tabs: a bordered icon segmented
control (h27) switching **Table / Documents** views; active segment accent-tinted.

### 5. Table view
Grid `36px | minmax(0,1fr) | 150px | 190px | 32px`, hairline rows only (`#f3f4f6`, header rule
`#e5e7eb`), comfortable density (13px vertical padding). No zebra, no box.
- Col 1: checkbox (accent `accent-color`), header checkbox = select-all-filtered.
- Col 2 "Workitem": two-line cell — ID 13px/600 `#1f2937` (UI sans + tabular-nums, **not** mono,
  not accent-colored), below it the stage ticks (5 segments 13×3px, filled = accent, rest
  `#e5e7eb`) + stage label 11px `#9ca3af`.
- Col 3 "Status": quiet — 12px/500 `#6b7280` text with a 7px dot + 3px halo. Dots: Ready gray
  `#9ca3af`, In Progress amber `#d97706`, Done green `#059669`. No colored text, no pills.
- Col 4 "Last movement" (default sort desc): timestamp 12.5px `#1f2937` tabular-nums, relative
  "{n} min ago" 11px `#9ca3af` beneath.
- Col 5: chevron `#d1d5db`; rotates 90° accent when the row's detail is open.
- Row hover `#f9fafb`; selected row background = accent tint.
- Empty state: centered magnifier + "No workitems match the current filters."

### 6. Documents view
5-across card grid (`gap:14px`). Card: radius 10, `#e5e7eb` border (accent border when
selected), hover lifts (`border #d1d5db` + soft shadow). Top: 5:4 gray well (`#f3f4f6`) with
the document's first-page preview rendered as a paper sheet (white, 1px border, small shadow) —
real thumbnail from the media endpoint. Checkbox overlaid top-left. Bottom (padding 9-11px):
ID 12px/600 + status dot (title tooltip) on line 1; stage ticks (9×3px) + stage label +
right-aligned "{n} ago" on line 2. Click = same detail as table view.

### 7. Inline detail (expands under the clicked row)
Full-width `#f9fafb` band closed by a `#e5e7eb` rule, padding 18-20px. One open at a time.
- Head: ID 13px/700, "In register ↗" accent link (existing `nx-label` deep link).
- Stage stepper: 5 steps (Imported → Classified → Extracted → Validated → Exported), 22px
  circle icons (`fa-file-import, fa-tags, fa-wand-magic-sparkles, fa-circle-check,
  fa-file-export`) — done = accent fill/white glyph, current = white fill/accent border+glyph +
  bold label, upcoming = gray; connectors 1.5px, accent when crossed. Closed by a hairline.
- Body grid `172px | 1px rule | fields | 1px rule | audit` (prototype: `172px 1.3fr 1px 1fr`):
  - **Document**: eyebrow row with a right-aligned "Full mode" ghost button (h24, `fa-expand`);
    172×222 page preview; 3 page thumbs (52px, active thumb accent border); meta line
    "Page 1 of 3 · 240 KB".
  - **Document details**: eyebrow row with right-aligned "Show sources" ghost button (wires to
    the existing source-highlight lightbox). Two-column key/value list, rows hover-white +
    click-to-locate (existing behavior); per field a 30px confidence bar **and** the percentage
    (10.5px/600, green `#059669` ≥90, amber `#d97706` below). Permission-gated content keeps
    the existing "Restricted" fallbacks.
  - **Audit** (renamed from History): timeline newest-first — 7px dot (accent on the latest
    event while in flight, gray otherwise) + 1.5px tail, "**Step** · activity" 11.5px,
    "timestamp · actor" 10.5px meta. Keep "Load more" paging.
- **Full mode**: toggling swaps the body grid for a "DOCUMENT · {n} PAGES" header (right-aligned
  accent-tinted "Compact" button) + all pages side by side (3-up, 172:222 aspect ratio, contain).
  Fields/audit are hidden while in full mode; stepper stays.

### 8. Selection bar + pagination
- Floating bar (fixed bottom-center, `#1f2937`, radius 12) when ≥1 selected: "{n} selected",
  divider, ghost "Export CSV" and "Deselect" buttons. Replaces the old `#bulk-action-bar`
  styling, same behavior.
- Footer row: "Showing x of y results" left; right: per-page select (h27) + bordered segmented
  pager (prev / numbered / next, active page accent-tinted). Replaces `#paginationControls`.
- Export modal: same options as today (always-included line, three gated extras incl. the
  base64/PowerShell helper, "all matching filters" note) restyled flat — hairline header/footer,
  h31 buttons. Keep every existing id/testid contract where practical.

## Removed from the current page
- The filter **card** (grid of labeled selects) and its Status select (→ tabs).
- The Total count pill (→ live meta line in the head).
- Boxed table wrapper, `nx-rise` entrance animations, per-page select in the filter row
  (→ footer), "Prepared documents" link stays but moves next to Import (secondary, gated as
  today).
- Mono font for IDs/timestamps in rows (tabular-nums UI sans instead).

## Interactions & behavior
- Status tabs, view toggle, Advanced open/close, detail expand, Full mode: client-side only.
- Tab counts come from the filtered result set (server aggregates per status).
- Detail data loads lazily on expand (existing `workitem_detail_panel.js` endpoints); the panel
  is a redesign of `buildPanelMarkup` — keep the shared module shared (reporting drill drawer
  and prepared_documents consume it too; migrate its markup, not its wiring).
- Selection survives view switches (table ↔ documents share one selection set).
- Sorting: existing column-sort behavior on Workitem / Status / Last movement (header carets).
- Saved views (#170/#186) live behind "Save view"; chips render in the filter row's spacer zone.

## Design tokens
Same palette as the dashboard handoff — text `#1f2937`/`#6b7280`/`#9ca3af`, borders
`#e5e7eb`/`#f3f4f6`, sunken `#f9fafb`, accent `var(--nx-accent)` + tint, success `#059669`,
warning `#d97706`. Status dots are semantic, not accent-derived. Radius 8 (controls),
10 (cards), 99 (dots). Type scale 10/10.5/11/11.5/12/12.5/13/15/22. Comfortable row density:
13px vertical padding, detail band 18-20px.

## Files to touch in nexora
- `templates/workitems_overview.html` — markup
- `static/css/workitems_overview.css` — new list/detail styles; shared families
  (`.nx-tabs--underline`, `.nx-segmented`, ghost buttons) belong in `nexora-ui.css`
- `templates/js/_workitems_overview_js.html` + `static/js/workitem_detail_panel.js` —
  tabs, view toggle, inline detail redesign, full mode
- `nx_lib/` workitems API — per-status counts for the tab row
- `translations/{de,fr,it}` — new strings (tabs, "Documents", "Full mode", "Compact",
  "Show sources", "Audit", "Save view", "{n} min ago")
- `tests/e2e` — selectors for removed filter card / status select / count pill

## Design intent (decisions from review)
1. Follow the approved dashboard console style (option 1a), **no KPI strip** on this page.
2. Table rows: two-line "pick 4" treatment, comfortable density.
3. No mono typography in rows; tabular-nums UI sans.
4. Status colors quiet: gray text + small semantic dot with halo (Ready was indigo → too loud;
   then cyan → replaced by the dot-only treatment).
5. Process name removed from rows — process scoping lives only in the scope picker.
6. Status filter = underline tabs with counts, not a select.
7. Two result views: table and 5-up document-card grid sharing selection + detail.
8. Detail is inline under the row (not a side panel), one open at a time.
9. Confidence shown as bar **and** percentage.
10. "Audit" not "History"; "In register" deep link kept.
11. "Full mode" button lives on the Document column header; "Show sources" on the Document
    details header (both moved out of the panel head for proximity).
12. Owner previews the accent as amber `#d97706`; ship `var(--nx-accent)`.
