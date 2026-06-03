# Workitem source highlighting — design

**Date:** 2026-06-03
**Status:** Approved (brainstorming) — pending spec review
**Branch:** feature/2.5.63.2

## Summary

Add a read-only "show sources" capability to the workitems document viewer. Each
extracted index-field value that carries a location renders a highlight box over
the exact spot on the page image where Octopus extracted it. A toggle reveals all
boxes on a page at once; clicking a field in the value list jumps to its page and
pulses its box.

The extracted data is **never modified** — this is purely a visualization of where
each value came from.

## Goals

- Show, per extracted field, *where on the document* the value was found (page + position).
- A toggle button that overlays every locatable field's box on the current page.
- Click a field value to jump to its page and highlight just that field.
- Honest handling of fields with no coordinates (manually keyed / derived values).
- Works in the full-page lightbox **and** the page thumbnails.

## Non-goals (v1)

- No editing, verifying, or confirming of field values (strictly read-only).
- No write-back of any kind to Octopus or NexoraDB.
- No new tables, columns, or migrations.
- No new permission code (reuses existing `workitems.details.view.*`).

## Current architecture (as found)

- **Documents render page-by-page as images.** `api_get_media_raw/{workitem_id}/{media_index}`
  (workitems.py) returns one image per page; `.tif` is converted to JPEG at the same
  pixel dimensions via Pillow, `.jpg`/`.png` pass through.
- **`api_get_media_info/{workitem_id}`** returns `{ media_count, fields }` where `fields`
  is a flat `label → text` dict. Backed by `get_extensions_urls_fields` (octo.py:100).
- **`get_extensions_urls_fields`** calls the Octopus document service
  (`documentService/thin/Document/{id}?WithDocumentStructure=true&...`) and currently
  keeps **only** `IndexFields[].FieldValue.Text`, mapped through `IndexFieldMappings`
  (`SourceFieldName → TargetKey`). All positional data in the response is discarded.
- **Front-end** (`templates/js/_workitems_overview_js.html`, `templates/workitems_overview.html`):
  - Thumbnails render at 160×160 with `object-cover` (crops the page), class
    `workitem-image cursor-pointer`.
  - A lightbox modal `#imageModal` (with `#modalImage`, `.modal-prev`, `.modal-next`)
    shows the full-size page with prev/next navigation.
  - Fields render as a `<dl>` (label → value) in `fields-container-${workitemid}`.
  - Field/image visibility is gated by `workitems.details.view.images` and
    `workitems.details.view.fields`.

The feature reuses all of this; the positional data is already being fetched and
thrown away, so capturing it costs no extra Octopus round-trip.

## Technical decisions (forks)

### Fork 1 — Coordinates ride the existing call (eager) ✅

Capture coordinates from the **same** document-service response already made in
`get_extensions_urls_fields`, and return them alongside values in `api_get_media_info`.

Rejected alternative: a separate "fetch locations on toggle" endpoint — adds latency
and a second Octopus call for data we already hold.

### Fork 2 — Backend normalizes to 0–1 ✅

The backend converts every bounding box to fractions of page width/height
(`x, y, w, h ∈ [0,1]`, origin top-left). The front-end multiplies by the *currently
rendered* image size. This is what lets the **same** boxes render correctly in both
the large lightbox and the small thumbnail.

Rejected alternative: ship raw coords + page dimensions and normalize in JS — pushes
Octopus-specific units/origin quirks into the front-end.

## Data contract

`api_get_media_info` response gains a `field_sources` array (the existing `fields`
dict stays untouched for backward compatibility):

```json
{
  "workitem_id": 123,
  "media_count": 3,
  "fields": { "Invoice number": "INV-001", "Total": "1 234.50" },
  "field_sources": [
    {
      "key": "Invoice number",
      "label": "Invoice number",
      "value": "INV-001",
      "locations": [ { "page": 0, "rect": { "x": 0.62, "y": 0.08, "w": 0.18, "h": 0.03 } } ]
    },
    {
      "key": "Total",
      "value": "1 234.50",
      "locations": []
    }
  ]
}
```

- `page` is the 0-based media index (aligns with `api_get_media_raw` indexing).
- `rect` is normalized 0–1, origin top-left.
- `locations` is a **list**: a value can span multiple lines/zones/pages → multiple
  boxes. An empty list means the field is **un-locatable** (manually keyed / derived).
- Malformed or out-of-`[0,1]` boxes are dropped server-side so a bad coordinate can
  never break the viewer.

## Components

### Backend

1. **`octo.py` — extract positions.** Extend `get_extensions_urls_fields` (or add a
   focused helper it calls) to also emit, per mapped index field: the page index, the
   bounding rectangle normalized to 0–1, and the field value. Page pixel dimensions
   come from the document structure already requested (`WithDocumentStructure=true`).
   - **Implementation step 1 (live verification):** before building anything, hit the
     INT document service for a real workitem and confirm (a) exactly where per-field
     coordinates live in the JSON, (b) their unit (pixels / points / normalized),
     (c) the origin (top-left vs bottom-left), and (d) whether page dimensions are
     present. If a different request flag is needed (e.g. `WithExtensions=true`),
     measure the payload impact. Adjust the contract if reality differs, then build.

2. **`workitems.py` — `api_get_media_info`.** Include `field_sources`, gated behind the
   existing `view.images` **and** `view.fields` perms (you need the page image *and*
   the field to see a box). Rides the existing `media_info_{workitem_id}` cache. When
   `view.images` is absent, `field_sources` locations are suppressed (boxes need the
   image); when `view.fields` is absent, `field_sources` is empty (consistent with how
   `fields` is already suppressed).

### Front-end (`_workitems_overview_js.html`, `workitems_overview.html`)

3. **Store** `field_sources` per workitem when media_info loads.

4. **Lightbox** (`#imageModal`): wrap `#modalImage` in a positioned container. On image
   `load` and on window `resize`, compute the rendered image rect and draw
   absolutely-positioned highlight `<div>`s for the **current page** from
   `rect × renderedSize`. Add a "Show sources" toggle button to the modal toolbar. The
   modal already tracks the current page via prev/next.

5. **Field list** (`fields-container`): rows whose field has ≥1 location become
   clickable → open the lightbox at that field's first page and pulse its box(es).
   Rows with no location get a subtle "no source location" badge and are not clickable.

6. **Thumbnails**: switch from `object-cover` to `object-contain` (full page visible,
   letterboxed) so normalized boxes land correctly; render boxes over thumbnails when
   the toggle is on. *(This is the one small existing-UX change required by the
   "thumbnails too" decision.)*

7. **Toggle state** persists in `localStorage` so it stays on as the user moves between
   workitems.

## Permissions

Reuses `workitems.details.view.images` + `workitems.details.view.fields`. No new
permission code, no seeding. Highlighting is only available when the user can see both
the page image and the fields.

## i18n

New UI strings — `Show sources`, `Hide sources`, `No source location` (and any helper
copy) — marked with `{{ _('...') }}` / `_()`, extracted to `messages.pot`, and
translated (non-fuzzy) in de/fr/it. `pybabel compile` before tests.

## Testing

- **Unit** (mocked Octopus JSON): normalization (raw coords → 0–1), un-locatable
  fields (empty `locations`), multi-zone/multi-page fields (multiple boxes),
  Batch/ChildDocuments handling, malformed-coordinate dropping, perm suppression
  (`field_sources` empty/locations-stripped when perms missing).
- **e2e**: open a workitem with media → open lightbox → toggle "Show sources" →
  assert highlight boxes render on the page → click a field row → assert the lightbox
  opens at the right page and that field's box pulses. Drive with a fixture or mocked
  media_info so the test doesn't depend on live Octopus.

## Risks

1. **Coordinate shape/unit/origin** — unknown until step-1 live verification. Biggest
   unknown; the contract above is the expected shape and may be adjusted after
   verification.
2. **Page rotation/orientation** — if Octopus coordinates predate an orientation Pillow
   applies during TIF→JPEG conversion, boxes will misalign. Must be checked in step 1;
   if present, the normalization must account for the applied rotation.
3. **Thumbnail `object-cover` → `object-contain`** — small change to existing thumbnail
   appearance; verify it doesn't break existing e2e assertions on the workitems page.
4. **DOM volume** — documents with very many fields/zones produce many overlay nodes;
   acceptable for typical documents, but render boxes only for the visible page in the
   lightbox.

## Out of scope / future

- Click-to-verify or inline edit of extracted values (explicitly excluded; read-only).
- Highlighting tables/line-items (current call uses `WithTables=false`).
- Confidence-score visualization (e.g. color boxes by extraction confidence) — possible
  follow-up if Octopus returns per-field confidence.
