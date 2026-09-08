# Report layouts ("Report definitions") — design

**Date:** 2026-09-07 · **Status:** approved design, plan pending · **Branch:** reporting work branch

## Goal

Let a reporting user author reusable **report definitions** (internal name:
**layout**) — a named bundle of *derived measures* plus a drag-and-drop
*tile grid* — and pick one before building a report. A report that carries a
layout renders its result as that tile grid instead of the fixed chart + table.
The built-in **Standard** is "no layout" and renders exactly as today.

"Definition" already means the saved report JSON in code and docs
(`DefinitionJSON`, `/api/reporting/run`). To avoid the collision, code, JSON
keys and docs say **layout**; only user-facing labels say **Report definition**.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| What a layout contains | Derived measures **and** a tile layout. Source, columns, filters, scope stay in the report. |
| Where measures are computed | **Server**, post-processing run rows (like forecast). Exports, schedules, AI captions see them. |
| Entry point | Own page `/reporting/definitions` + a "Report definition" picker in the Simple and Advanced builders. The chosen `layoutId` is stored in the report. |
| Layout freedom | **12-column tile grid**, reorder + corner-resize, reusing the dashboard grid engine. |
| Ownership | **Per user, private.** No sharing, no admin publishing. |
| Measures v1 | Basics only: current, mean, min/max, range, std dev, percentile. |
| Charts v1 | Existing bar/line/pie/doughnut/table **plus** area, stacked bar, gauge, and a sparkline option on KPI tiles. |
| Where the tile grid applies | The report **result view**. Dashboards unchanged. |
| Approach | A — reuse the dashboard grid engine; store layouts as saved reports with `kind: 'layout'`. |

Out of scope, deliberately: change measures (delta, growth rate, trend, peak per
breakdown), target measures (goal, gap to target, expected line), dashboards
honouring layouts, sharing layouts, free canvas. The measure registry and tile
types are designed so each of these is one added entry later.

## 1. Data model

A layout is a **saved report row** whose definition has `kind: 'layout'` —
the same trick dashboards use. No migration, no new table, no new endpoint for
CRUD (`/api/reporting/reports` save/load/delete already work). The library
listing hides `kind: 'layout'` rows the way it hides dashboards; the
definitions page lists them.

```json
{
  "kind": "layout",
  "schemaVersion": 1,
  "title": "Ops standard",
  "measures": [
    { "id": "m1", "op": "current" },
    { "id": "m2", "op": "mean" },
    { "id": "m3", "op": "minmax" },
    { "id": "m4", "op": "range" },
    { "id": "m5", "op": "stddev" },
    { "id": "m6", "op": "percentile", "q": 0.95 }
  ],
  "tiles": [
    { "id": "t1", "type": "kpi",   "measure": "m1", "sparkline": true, "span": 3, "rows": 2 },
    { "id": "t2", "type": "chart", "chart": "area", "span": 9, "rows": 4 },
    { "id": "t3", "type": "table", "span": 12, "rows": 4 }
  ]
}
```

- `measures[].op` ∈ `current | mean | minmax | range | stddev | percentile`;
  `percentile` requires `q` in (0, 1). `id` is unique within the layout.
- `tiles[].type` ∈ `kpi | chart | table`. `kpi` requires `measure` referencing a
  measure id and may set `sparkline`. `chart` requires `chart` ∈
  `bar | stacked_bar | line | area | pie | doughnut | gauge`. `span` 1–12,
  `rows` 1–8, same semantics as dashboard cards (`grid-column: span N`,
  `--rdb-cardrows`). Tile order in the array is render order.
- Validation lives in `nx_lib/reporting/schema.py` next to the report and
  dashboard validators; a malformed layout is rejected on save (400) and
  ignored on run (falls back to Standard with a `layoutFallback` note).

A report references a layout with one optional key in its own v1 definition:

```json
{ "schemaVersion": 1, "source": "...", "layoutId": 57, ... }
```

`layoutId` absent → Standard. The validator accepts any positive integer; the
runner checks ownership at run time (see §2).

## 2. Measures engine

New module `nx_lib/reporting/derived.py`, Flask-free.

```python
OPS = {"current": _current, "mean": _mean, "minmax": _minmax,
       "range": _range, "stddev": _stddev, "percentile": _percentile}

def compute_derived(layout, columns, rows) -> dict
```

- Operates on the **first metric column** of the run result (the first column
  whose field is in the definition's `metrics`, else the first numeric column).
  Returns `{ measureId: {"op", "value" | {"min","max"}, "n"} }`; a measure
  that cannot be computed returns `{"unavailable": "<reason>"}` rather than
  raising, so one bad tile never kills the run.
- `current` = value of the row with the latest date when the definition has
  exactly one date dimension, else the sum of the column (grand total).
- Numeric coercion, percentile and describe helpers are reused from
  `nx_lib/reporting/stats.py` (`_as_numbers`, `_percentile`); `MAX_STATS_ROWS`
  applies.
- Sparkline data for KPI tiles is **not** computed server-side; the client
  draws it from `rows` when the result has a single date dimension.

Runner (`nx_lib/views/reporting/run.py`): when the posted definition carries
`layoutId`, load that saved report; if it is not `kind: 'layout'` or not owned
by the current user, respond 400 `{"error": "Unknown report definition"}`.
Otherwise `payload["derived"] = compute_derived(...)` and `payload["layout"]`
= the layout definition, so the result renderer needs no second request.
Export (`nx_lib/reporting/export.py`) appends a **Measures** block (label,
value) under the data when `derived` is present; schedules and AI captions get
`derived` for free because they call the same runner.

## 3. Editor page — `/reporting/definitions`

- Route in `nx_lib/views/reporting/pages.py`, template
  `templates/reporting_definitions.html` paired with
  `templates/js/_reporting_definitions_js.html` (shim: Jinja data +
  translated strings) and `static/js/reporting_definitions.js`. Permission:
  `reporting.view`. Nav entry under Reporting, next to Dashboards.
- The grid engine currently inside `static/js/reporting_dashboard.js`
  (drag-reorder via HTML5 DnD, corner-resize via Pointer Events, span/rows
  CSS vars, `rdb-grid` classes) moves into a shared
  `static/js/reporting_grid.js` exposing `window.ReportingGrid = {mount,
  render, setEditing}`; the dashboard keeps its behaviour unchanged and becomes
  the first consumer. `reporting.css` keeps the `rdb-*` class names.
- Page structure: left rail = **measure palette** (one button per op; click
  adds a measure and, by default, a KPI tile for it; percentile shows a `q`
  input) and **tile palette** (add chart / add table). Centre = the grid in
  edit mode with a **live preview**: a "Preview with" dropdown of the user's
  saved (non-dashboard, non-layout) reports; the preview runs that report with
  the draft layout via `/api/reporting/run` and renders tiles for real. Per
  tile toolbar: chart type picker, sparkline toggle, remove.
- List/edit/duplicate/delete of layouts uses the existing saved-report
  endpoints. Autosave on every change (debounced), as dashboards do.
- Charts: Chart.js 4 already loaded. `area` = line with `fill: true`;
  `stacked_bar` = bar with `stacked: true` scales; `gauge` = doughnut with
  `circumference: 180`, `rotation: 270`, needle-less, showing current value
  between the series min and max (target-aware later). Sparkline = tiny
  line chart, no axes, inside the KPI tile.

## 4. Builder and result view

- Simple wizard and Advanced builder get a **Report definition** dropdown at
  the top of the builder (`Standard` + the user's layouts, loaded once from
  the reports list). Selection writes `layoutId` into the definition; the
  Advanced JSON view shows it.
- Result pane: when the run response carries `layout`, `reporting_simple.js`
  and `reporting_advanced.js` render the tile grid (read-only) via
  `ReportingGrid` instead of the fixed chart + table. Tile feeds: `kpi` ←
  `derived[measure]`, `chart` ← `columns/rows` with the tile's chart type,
  `table` ← the existing table renderer. Comparison chips, forecast and
  drill-through keep working on the chart and table tiles because they hang
  off the same data objects.
- Layout deleted while reports still reference it: run responds with
  `layoutFallback: "missing"`, the client renders Standard and toasts once.
- A shared report whose layout belongs to another user renders Standard for
  the recipient with `layoutFallback: "foreign"` (layouts are private).

## 5. Error handling

| Case | Behaviour |
|---|---|
| Malformed layout on save | 400 from the schema validator, field-level message |
| `layoutId` unknown / not `kind: 'layout'` / foreign owner | run 400 `Unknown report definition` when the caller is the owner path; `layoutFallback` when reached via a shared report |
| Measure not computable (no numeric column, empty rows) | `{"unavailable": reason}` per measure; KPI tile shows "—" with the reason as tooltip |
| Too many rows for stats | `derived` omitted, `derivedUnavailable: "rows"` |
| Preview report fails in the editor | Tiles show placeholders; layout editing still works |

## 6. Testing

- `tests/unit/test_reporting_derived.py`: every op on a fixed dataset, empty
  rows, non-numeric rows, `current` with and without a date dimension,
  percentile bounds.
- `tests/unit/test_reporting_schema.py`: layout validator accept/reject cases;
  `layoutId` accepted on a report definition.
- Runner test: `layoutId` foreign owner → 400; valid → `derived` + `layout`
  in payload; missing layout via shared report → `layoutFallback`.
- `tests/unit/test_template_url_prefix.py` covers the new JS (API_PREFIX).
- One Playwright e2e: create a layout, add a measure, drag a tile, resize it,
  pick the layout in the Simple builder, run, assert tiles render and the KPI
  shows a number.
- Dashboard e2e must stay green after the grid extraction.

## 7. Docs & chores

`docs/howto/reporting.md` (new "Report layouts" section + JSON), the end-user
guide `docs/howto/reporting-guide.md` and the in-app tips panel
`templates/_reporting_help.html` (same commit), `CHANGELOG.md` under
Unreleased, translations for de/fr/it (`/nx-i18n`), nav entry, no deploy
exclude needed (all runtime paths).
