# Workitem table / line-item source highlighting — design

**Date:** 2026-06-09
**Status:** Approved (brainstorming) — pending implementation
**Branch:** `feat/workitem-table-highlight` (worktree `C:\dev\nexora.wt\table-highlight`, off `feature/2.5.63`)
**Builds on:** `docs/superpowers/specs/2026-06-03-workitem-source-highlighting-design.md`
(the scalar-field "Show sources" feature, already shipped + merged into `feature/2.5.63`).

## Summary

Extend the workitems document viewer's read-only "Show sources" overlay from
scalar index fields to **table / line-item extractions**. Each extracted table
cell value renders a highlight box over the exact spot on the page where Octopus
found it, and the field panel grows a compact line-item grid whose cells (and
rows) are click-to-locate — directly parallel to how scalar fields work today.

The extracted data is **never modified** — purely a visualization of provenance.

## Goals

- Show, per extracted **table cell**, *where on the document* the value was found.
- Render cell boxes in the full-page lightbox **and** the page thumbnails, under
  the existing single "Show sources" toggle.
- Surface line-items as a compact grid in the field panel; click a cell — or a
  whole row — to jump to its page and pulse its box(es).
- Visually distinguish table-cell boxes from scalar-field boxes (distinct hue)
  while keeping the confidence colouring on the box border.
- Degrade gracefully when the data is coarser than per-cell (see "Graceful
  degradation").

## Non-goals (v1)

- No editing / verifying / confirming of cell values (strictly read-only).
- No write-back of any kind to Octopus or NexoraDB.
- No new tables, columns, or migrations.
- No new permission code (reuses `workitems.details.view.images` + `.fields`).
- No nested-table / merged-cell exotica beyond what the spike shows exists.

## Current architecture (as found)

- `get_extensions_urls_fields` (`nx_lib/octo.py:101`) calls the Octopus thin-document
  service with **`WithTables=false`** — table data is never fetched. It returns a
  4-tuple `(extensions, urls, fields, field_sources)`.
- `extract_field_locations` (`nx_lib/field_locations.py`) parses mapped scalar
  `IndexFields` into `field_sources` = `[{key,label,value,locations:[{page,rect}],confidence?}]`.
  `rect` is raw image pixels; the front-end normalizes against the page image's
  `naturalWidth/Height`. Batch docs get a per-child page offset.
- `api_get_media_info` (`nx_lib/views/workitems.py:975`) returns
  `{media_count, fields, field_sources}`, cached per workitem, with perm
  suppression: no `fields` perm → `field_sources: []`; no `images` perm →
  `locations` stripped.
- Front-end (`templates/js/_workitems_overview_js.html`): `window.__srcByWorkitem[wid]`
  holds `field_sources`; one `renderBoxes` loop draws boxes in the lightbox
  (`#srcHlLayer`, an `position:absolute` overlay sized to the modal image's
  **layout box** `offsetLeft/Top/Width/Height` ÷ `naturalWidth/Height` — *not*
  `getBoundingClientRect`, which returns the post-`transform` rect and, read
  mid open-zoom animation, used to strand the boxes in blank space)
  and on thumbnails; the field `<dl>` in `fields-container-${wid}` makes located
  rows click-to-locate and badges un-locatable ones; `#srcHlToggle` flips all
  boxes; state persists in `localStorage('srcHlOn')`.
- **Full-page split review:** `#imageModal` is a two-pane flex layout
  (`.src-modal-body`): the page + overlay + nav + toggle on the **left**
  (`.src-modal-page`, the `position:relative` containing block for `#srcHlLayer`),
  the extracted values on the **right** (`#srcReviewPanel`). The values markup is
  produced by one shared builder `buildSourceDetailsHtml(wid)` (scalar `<dl>` +
  `renderTableGrids`) reused by both the inline Document Details panel and the
  review panel, reading `window.__fieldsByWorkitem[wid]` — so the two never drift.
  Clicking a value/cell in the panel navigates the open view to that page and
  pulses its box (no re-open). The panel hides (`hidden`) for documents with no
  extracted values, so plain media viewing stays full-width.
- Three **other** callers of `get_extensions_urls_fields` discard `field_sources`
  and use only `fields`/`urls`: dashboard activity, CSV export, `api_get_media_raw`.

## Key decision — a table cell is "just another source"

The overlay already renders any `{value, locations, confidence?}` entry. Line-item
cells reuse that machinery: a `kind` discriminator (`field` vs `cell`) drives a
distinct box hue and the grid layout in the panel, so `renderBoxes` and the
thumbnail loop barely change.

## Technical decisions (forks)

### Fork 1 — Opt-in table fetch (chosen) ✅

Add `with_tables: bool = False` to `get_extensions_urls_fields`; only
`api_get_media_info` passes `True`. The three other callers keep `WithTables=false`
and pay **zero** extra payload. Table cells parse into a new `table_sources` key
returned alongside `field_sources`.

Rejected — **B: flip `WithTables=true` globally** (every caller pays the larger
payload for data only the viewer uses). Rejected — **C: a lazy on-toggle endpoint**
(second Octopus round-trip + new route/cache/loading-state; the media-info call is
already cached per workitem, so the idle saving isn't worth the complexity).

### Fork 2 — Front-end normalizes pixels (inherited) ✅

Same as the scalar feature: backend ships **raw image-pixel rects**; the client
divides by the page `<img>`'s `naturalWidth/Height`. Drops the page-dimension
dependency and the rotation risk. No backend normalization.

## Data contract

`api_get_media_info` gains a `table_sources` array (existing `fields` /
`field_sources` untouched):

```json
{
  "workitem_id": 123,
  "media_count": 3,
  "fields": { "...": "..." },
  "field_sources": [ ... ],
  "table_sources": [
    {
      "title": "Positionen",
      "columns": ["Description", "Qty", "UnitPrice", "Amount"],
      "rows": [
        [
          { "col": "Description", "value": "Widget A",
            "locations": [ { "page": 0, "rect": {"left":120,"top":880,"width":300,"height":28} } ],
            "confidence": 0.97 },
          { "col": "Qty", "value": "3", "locations": [ { "page": 0, "rect": {...} } ] }
        ]
      ]
    }
  ]
}
```

- `page` is the 0-based media index (aligns with `api_get_media_raw`).
- `rect` is raw image pixels, origin top-left (client normalizes).
- A cell with no usable coordinate has `locations: []` (un-locatable).
- `columns` may be empty / synthesized if the source has no header names.
- Malformed / degenerate (`width<=0 || height<=0`) rects are dropped server-side.

## Components

### Backend

1. **`nx_lib/octo.py` — `get_extensions_urls_fields(..., with_tables=False)`.**
   When `with_tables`, request `WithTables=true` and call `extract_table_locations`;
   otherwise behave exactly as today. Return a 5-tuple
   `(extensions, urls, fields, field_sources, table_sources)`; `table_sources` is
   `[]` unless `with_tables`. **Update all four call sites** (the three scalar-only
   callers ignore the new element / keep `with_tables=False`).

2. **`nx_lib/table_locations.py` (new, pure).** `extract_table_locations(doc_json)
   → table_sources`. Reuses `field_locations.py`'s rect validation
   (`_rect_from_octo`, degenerate drop), confidence normalization (`_confidence`),
   and Batch page-offset (`_count_image_media`) helpers — **imported from
   `field_locations.py`** (promote them to public names there if cleaner), never
   copy-pasted, so both parsers share one rect/confidence/offset implementation.
   The exact JSON path to tables/cells is confirmed by the spike (step 1) before
   this is finalized.

3. **`nx_lib/views/workitems.py` — `api_get_media_info`.** Call with
   `with_tables=True`; add `table_sources` to the response and to the cached dict;
   extend the perm `_suppress()` so `table_sources` is `[]` without `fields` perm
   and has `locations` stripped without `images` perm (mirror `field_sources`).

### Front-end (`_workitems_overview_js.html`, `workitems_overview.html`)

4. **Store** `window.__tableByWorkitem[wid] = mediaInfo.table_sources || []` when
   media-info loads, next to `__srcByWorkitem`.

5. **Boxes.** Flatten table cells into the existing render path tagged
   `kind:'cell'`; `renderBoxes` (lightbox) and the thumbnail loop draw them with a
   distinct hue (new class in `static/css/source-highlight.css`); confidence colour
   stays on the border. `hasAnyLocation()` / toggle visibility account for table
   cells too.

6. **Panel grid.** Under the scalar `<dl>` in `fields-container-${wid}`, render each
   table as a compact grid (title + header row + cell rows). Located cells are
   click-to-locate (reuse the existing locate/pulse path, keyed by page + a
   cell id); a located row offers a row-level locate (pulses all its cells).
   Un-locatable cells reuse the scalar "no source location" affordance.

7. **Toggle / persistence.** The single existing `#srcHlToggle` +
   `localStorage('srcHlOn')` controls field *and* table boxes (no second toggle).

## Permissions

Reuses `workitems.details.view.images` + `.fields`. No new code, no seeding —
identical suppression rules to `field_sources`.

## i18n

New UI strings (e.g. `Line items`, and any header fallback like `Column`) marked
with `{{ _('...') }}` / `_()`, extracted to `messages.pot`, translated non-fuzzy in
de/fr/it, `pybabel compile` before tests.

## Graceful degradation

Per-cell coordinates are an **assumption** until the spike confirms them
(`WithTables=false` today means the shape was never verified). The renderer draws
at the finest grain the data supports:

1. **Cells carry rects** → per-cell boxes (the target design).
2. **Only rows/tables carry a region** → row-level (or table-level) boxes; the grid
   still lists per-cell values, click-to-locate at row grain.
3. **No coordinates at all** → data-only line-item grid (no boxes), every cell
   badged un-locatable — still useful, consistent with un-locatable scalar fields.

`extract_table_locations` returns whatever grain exists; the front-end renders
whatever rects are present. No grain is hard-coded.

## Testing

- **Unit** (mocked Octopus table JSON): per-cell rects → boxes; cells without rects
  → `locations:[]`; row/table-only coords → degraded grain; multi-page tables;
  Batch page offset; malformed-rect dropping; confidence normalization; perm
  suppression (`table_sources` emptied / `locations` stripped).
- **e2e**: open a workitem with table media (or mocked media-info) → toggle "Show
  sources" → assert cell boxes render → click a line-item cell/row → assert the
  lightbox opens at the right page and the cell box pulses. Mirrors the base
  feature's e2e; mock so it doesn't depend on live Octopus.

## Risks

1. **Table coordinate shape/unit/origin/grain** — unknown until the step-1 INT
   spike. Biggest unknown; the contract above is the *expected* shape and is
   adjusted to reality after the spike. Graceful degradation bounds the downside.
2. **Payload size** — `WithTables=true` enlarges the thin-document response;
   measured in the spike. Mitigated by opt-in fetch (only the viewer path) + the
   existing per-workitem media-info cache.
3. **DOM volume** — many line-items × many columns = many overlay nodes. Render
   boxes only for the visible page in the lightbox (the existing loop already
   filters by current page); the panel grid is plain DOM.
4. **Finding test data** — the base feature noted real coords live on a process no
   detail-perm account can browse. The spike hits Octopus directly (not via the
   gated UI); screenshots may use injected representative cell coords on a real
   page if no accessible workitem carries real table coords (as the base feature
   did).

## Implementation sequence

1. **Live INT spike** — `WithTables=true` on an invoice with line items (e.g. the
   base feature's WID 18299); record where cell/row coords live, unit, origin, page
   index, and payload-size delta in this spec's "Verified shape" section. Adjust the
   contract, then build.
2. Pure `nx_lib/table_locations.py` + unit tests (shared helpers refactored out of
   `field_locations.py`).
3. `get_extensions_urls_fields(with_tables=...)` 5-tuple + update 4 call sites +
   `api_get_media_info` `table_sources` + perm suppression + tests.
4. Front-end: store, boxes (distinct hue), panel grid, click-to-locate.
5. i18n (extract → translate de/fr/it → compile).
6. e2e + CHANGELOG + CLAUDE.md doc note.

## Verified shape (INT spike, 2026-06-09)

Confirmed live against INT (WID 18299, the base feature's invoice). The shape
differs from the "Data contract" assumption above — implementation follows this.

- **Tables live at `doc["Tables"]`** (and at each `ChildDocuments[i]["Tables"]`),
  an array of `{ "Name": "TabVat", "Rows": [ {"ID": "...", "Cells": [ ... ]} ] }`.
  **`Name`, not `Title`. No `Columns` array** — columns are derived from the union
  (in first-seen order) of each cell's `ColumnName`.
- **A row is an object** `{ID, Cells:[...]}` — iterate `row["Cells"]`, not the row.
- **A cell** = `{ "ColumnName": "TabNetAmount", "CapturedValue": "236.82",
  "CellValue": {"Text": "236.82", "TypedValue": 236.82, "IsSet": true},
  "Confidence": 0.0, "CellType": 5, "Location": {DtoImageBasedLocation},
  "CapturedLocation": null }`.
  - **Value** = `CellValue.Text`, fallback `CapturedValue`. (Empty cells have both
    null → skipped, mirroring scalar `field_sources`.)
  - **Column key/label** = `ColumnName`.
  - **`Location`** is the *same* `DtoImageBasedLocation` as scalar fields:
    `PageIndex` (0-based), `Rectangle` / `Rectangles` `{Left,Top,Width,Height}` in
    image pixels, origin top-left. Derived/summary cells carry `{0,0,0,0}`
    (→ un-locatable, dropped by the shared `rect_from_octo`). Use `Location`,
    fall back to `CapturedLocation`.
  - **`Confidence`** on the cell (0..1 here; reuse `confidence_of`). Note many
    located table cells report `0.0` — the UI will colour them low/red, which is
    faithful to the data.
- **Payload:** `WithTables=true` added only ~24 KB / ~6% (412,690 → 437,311 bytes)
  and did **not** change the document decomposition. Opt-in fetch keeps even that
  off the three scalar-only callers. Risk #2 is effectively retired.

**Page-alignment finding (important).** WID 18299 is a `DPSI_Document` whose real
media, located `IndexFields`, *and* located table cells all live in
`ChildDocuments[1]` (root has `image_media=0`, `indexfields_real_rect=0`). The
shipped `get_extensions_urls_fields` / `extract_field_locations` iterate
**root-only** for non-`Batch` docs, so for such nested docs they surface nothing —
a **pre-existing** limitation affecting scalar fields too, *not* introduced here.
**Rule for this feature:** `extract_table_locations` reuses the **identical item
iteration** (`items_of`) and per-item page offset (`count_image_media`) as the
scalar parser, so table-cell `page` indices align with the `urls` list
`api_get_media_raw` serves *by construction*, whatever the document shape. Making
nested `DPSI_Document`s light up (media+fields+tables together, at child level) is
a larger shared change to `get_extensions_urls_fields` — **out of scope here**,
noted as a follow-up.

**Corrected internal contract** (supersedes the "Data contract" JSON above):
```python
table_sources = [
  { "title": "TabVat",                       # Octopus Tables[].Name
    "columns": ["TabNetAmount", "TabVatAmount", "TabVatRate", "TabVatCode"],
    "rows": [
      [ {"col": "TabNetAmount", "value": "236.82",
         "locations": [{"page": 1, "rect": {"left":851,"top":2407,"width":543,"height":544}}],
         "confidence": 0.0},
        {"col": "TabVatRate", "value": "7.7", "locations": []} ],   # {0,0,0,0} → un-locatable
    ] } ]
```

**Screenshots:** as with the base feature, no detail-perm-visible workitem carries
real *line-item* table coords (WID 18299 only populates the `TabVat` summary;
`TabOrderItems` is empty), so live screenshots use injected representative table
cell coords on a real page — data correctness is proven by the spike + unit tests.
