# Reporting: Drill-Through to Underlying Rows — Design

**Date:** 2026-06-11
**Status:** Approved (owner answered all open questions; see "Decisions")
**Scope:** Reporting feature (Simple + Advanced tabs, aggregate results)

## Problem

An aggregate report answers *how many*, never *which ones*. A user looking at "doc count by
docsource, last 3 months" sees Scan = 412 and has no way to find out which 412 documents
that is — the number is a dead end. Today the workaround is asking IT or hand-building a
raw-row report in the Advanced tab with the right filters, which most users cannot do.

Drill-through: click a chart element (bar, slice, line point) or an aggregate table row and
a panel opens with the raw document rows behind that number, each row deep-linking to the
workitems page.

## Decisions (owner, 2026-06-11)

| # | Question | Decision |
|---|----------|----------|
| 1 | Click targets | **Everything aggregate**: chart elements and aggregate-table rows, on both Simple and Advanced tabs. Not the zero-breakdown big-number card, not pivot cells (future). |
| 2 | Detail columns | **Fixed smart set**: `workitem_id` + `processname` + `import_date`/`export_date` + the definition's breakdown fields, intersected with what the source catalog actually exposes; generic table sources fall back to their first ~6 catalog columns plus the breakdown fields. No column picker. |
| 3 | Panel UX | **Slide-over drawer from the right** (~45% width, min 420px). Result stays visible; clicking another element replaces the drawer content. Esc and ✕ close. |
| 4 | Approach | **Client-side definition transform through the existing run endpoint**, plus one small backend symmetry fix (see below). No new endpoint, no migration, no new permission. |
| 5 | Sequencing | Spec + plan now; **implementation starts only after `feat/rich-export` merges** (it rewrites the same chart/result code). The backend symmetry fix may land earlier. |

## What recon established (2026-06-11, feature/2.5.63)

- **The filter vocabulary already covers drill-through.** `FILTER_OPS` in
  `nx_lib/reporting/schema.py` already contains `eq`, `gte`, `lt`, `is_null`,
  `is_not_null`; both builders emit SQL for them (`_filter_clause` in
  `nx_lib/reporting/query.py`, the op ladder in `nx_lib/reporting/table_query.py`).
  Nothing new is needed in the whitelist.
- **The metric-less raw-row path exists** in both builders (the
  `SELECT TOP (cap) cols FROM (union) t` branch in `build_table_query`). Raw-row reports
  are how the Advanced tab started; the validator accepts a definition with `columns` and
  no `metrics`.
- **Grain values are bucket starts.** The grain SQL truncates dates server-side (month →
  `2026-04-01`, week → Monday), so a clicked date bucket's lower bound is the cell value
  itself and the upper bound is "+ one grain unit" — trivial client-side date math, no
  calendar logic duplication.
- **One real asymmetry (the "(null)" group bug-in-waiting):** the docprocessing builder
  *projects* a field a process doesn't expose as `NULL AS [field]` (so its rows land in
  the "(null)" group of an aggregate), but a *filter* referencing that field drops the
  whole process subquery ("can never match here"). Drilling a "(null)" group with
  `is_null` would therefore under-report: it returns NULL-valued rows from processes that
  have the column, but silently omits rows from processes that lack it.
- **Synthetic fields:** `workitem_id` (catalog + `_workitem_exprs_for`), `processname`
  (constant projection per subquery), `import_date`/`export_date` (`_date_exprs_for`) are
  all projectable; `workitem_id` is filterable per migration `0020`.
- **Workitems deep link:** the workitems page accepts `?search=<workitem-id>` (applied for
  users holding `workitems.filter.workitemid`; the page enforces its own permissions).
- **No chart click handling exists today** — charts are display-only on both tabs, so all
  click wiring is new code, not a modification.
- **`feat/rich-export` worktree state:** Phase 1 (backend: SQL echo, styled XLSX,
  matplotlib renderer, inline-image mail) is committed; Phase 2 (frontend: show-query
  panels, up-to-three wizard breakdowns, **multi-series charts**) is pending and rewrites
  `mountChart()`/result panels in both JS partials. Drill-through's chart wiring must be
  built on top of the multi-series shapes (series index → second dimension value).

## Design

### A. The drill transform (client-side, pure function)

A new shared partial `templates/js/_reporting_drill_js.html` exposes
`window.ReportingDrill` with two members:

- `buildDrillDefinition(definition, catalog, clicked)` — **pure function**, unit-testable
  via `page.evaluate` in e2e. Input: the validated definition that produced the current
  result, the source's catalog entry (fields with `filterable`/`grainable` flags), and
  `clicked` = an ordered list of `{field, grain?, value}` — one entry per definition
  column. Output: a new definition or `null` when drilling is not possible.
- `open(ctx)` — fetch + drawer rendering (section C).

Transform rules:

1. Start from a deep copy of the source definition: same `source`, same `filters`
   (relative-date tokens copied verbatim — they re-resolve server-side to the same
   window), same scope semantics.
2. Drop `metrics` entirely.
3. For each definition column (dimension), append filters from the clicked group:
   - **grained date column** (value is the bucket start): `{field, op: "gte", value}` plus
     `{field, op: "lt", value: addGrain(value, grain)}` where `addGrain` adds one
     day/7 days/1 month/3 months/1 year for day/week/month/quarter/year.
   - **category column with a value**: `{field, op: "eq", value}`.
   - **category column shown as "(null)"/empty**: `{field, op: "is_null"}`.
4. `columns` = the smart set (Decision 2), deduplicated, capped at 8, **intersected with
   the source catalog** (a source without `workitem_id` simply doesn't get that column).
5. `sort` = `[{field: <export_date if present, else first column>, dir: "desc"}]` for
   docprocessing; first column `asc` for generic table sources.
6. `rowLimit` = 100.
7. **Guard:** if any dimension field is not `filterable` per the catalog, return `null` —
   the click surface for that result renders without drill affordance (no cursor, no
   handler) instead of failing on click.

The resulting definition is POSTed to the **existing** `/api/reporting/run`. The server
sees an ordinary raw-row report: `validate_report_definition`, per-source grants,
process/row scope, and the row cap all apply completely unchanged. No new trust surface.

### B. Backend symmetry fix: `is_null` on a field a process doesn't expose

In `build_table_query` (`nx_lib/reporting/query.py`), the subquery-drop rule changes from
"any filter field not resolved → drop the process" to:

- a filter with `op: "is_null"` on an unresolved field is **trivially true** for that
  process (its rows project that field as NULL) → keep the subquery and skip the clause;
- every other op on an unresolved field keeps today's behavior (drop the subquery —
  `eq`/`gte`/`is_not_null` etc. can genuinely never match).

This makes filter semantics symmetric with projection semantics and closes the "(null)"
group under-report. It is a small, independently shippable change with its own unit
tests, and it benefits the Advanced builder's filters generally — not just drill-through.
The generic table builder needs no change (single table; columns either exist or the
definition fails validation).

### C. The drawer

Markup lives once in `templates/reporting.html` (both tabs share the page), styled in
`static/css/reporting.css`:

- Right-edge slide-over, ~45% viewport (min 420px), full height, `nx-card` styling, over
  a click-to-close backdrop. Esc and a ✕ button close it. While a drill is loading the
  drawer shows the existing spinner idiom; a failed run shows the error message inside
  the drawer (the page behind is untouched). Clicking another chart element or row while
  open replaces the content.
- **Header:** a human-readable description of the clicked group — each dimension as
  `label = value` ("Document source = Scan · April 2026"), built from catalog labels.
- **Subtitle (metric honesty):** for a plain count, "the rows behind this number". For a
  `count_distinct` metric, "rows contributing to this number — the distinct count may be
  smaller". When the drill response has `truncated: true`, append "showing the first 100
  rows — export to get all".
- **Body:** the detail table, reusing the result-table cell rendering/escaping idiom of
  the host tab. `workitem_id` cells render as links to `/workitems?search=<id>`
  (new tab). Links render unconditionally; the workitems page enforces its own
  permissions.
- **Footer:** CSV and XLSX export buttons POSTing the *same* drill definition to the
  existing `/api/reporting/export` (its higher export row cap applies, so the export can
  contain more than the 100 displayed rows). Buttons render only for users with
  `reporting.export`, exactly like the host tab's export button.

### D. Click wiring per surface

All wiring happens after `feat/rich-export` Phase 2 lands and follows its shapes:

- **Simple chart** (`templates/js/_reporting_simple_js.html`): Chart.js `onClick` +
  `getElementsAtEventForMode('nearest')`. Single-dim: element index → dimension value
  from `state.chartData.labels`. Multi-series (2-dim): element index → first dimension,
  `datasetIndex` → second dimension (the series label). Pie/doughnut: index → value.
- **Advanced chart** (`templates/js/_reporting_viz_js.html` mount): same handler shape,
  reading the mounted chart's labels/datasets.
- **Aggregate tables** (Simple result table; Advanced grid view): rows get a click
  handler + pointer cursor + `tabindex="0"`/Enter handling when — and only when — the
  producing definition had at least one metric *and* at least one dimension and the drill
  guard (A.7) passes. Raw-row results never drill (they already are rows). A table-row
  click supplies *all* dimensions (including a third one that charts can't show).
- **Pivot cells: out of scope** for v1 (the client-side reshape would need a reverse
  mapping from cell to row/column keys). Noted as a natural follow-up.

### E. Affordance

Clickable chart elements set `cursor: pointer` via Chart.js `onHover`; clickable table
rows get a CSS class with hover highlight and a one-time hint line under the result
("Click a row or chart element to see the documents behind it") that the host tab already
has idioms for. The hint and all new strings are translated (de/fr/it).

## Security notes

- The drill definition goes through the same validation, source grants, process scope,
  and row caps as any user-built report — a user can only ever drill into rows they could
  already query via the Advanced tab. No new permission, endpoint, or migration.
- Export from the drawer is gated by the existing `reporting.export` permission.
- The `is_null` symmetry fix only *widens* a filter to match rows the same user already
  sees projected as NULL in the aggregate — no scope change.
- Workitem links lead to a page with its own permission regime; reporting does not
  pre-check those permissions (acceptable for an internal portal; the workitems page
  404s/403s appropriately).

## Approaches considered and rejected

- **Dedicated `/api/reporting/drill` endpoint** (server-side transform): unit-testable in
  Python and could hide the transform from the client, but adds a second run-shaped
  endpoint to permission-gate, audit, and maintain — for logic that is a pure data
  transform. Rejected; the pure-function client transform plus `page.evaluate` testing
  achieves the same confidence.
- **Pure frontend with "(null)" rows unclickable**: avoids touching the backend but bakes
  the projection/filter asymmetry into the UX. Rejected since the symmetry fix is small
  and generally useful.
- **Drill from pivot cells and the zero-dim number card**: deferred (owner decision —
  number card not selected; pivot needs reverse mapping).

## Testing strategy

- **Unit (backend):** the `is_null` symmetry fix in `tests/unit/test_reporting_query.py` —
  a two-process fixture where one process lacks the filtered field: `is_null` keeps both
  subqueries (and the lacking one carries no clause); `is_not_null` and `eq` still drop
  the lacking process; projection/filter agreement asserted on the generated SQL.
- **Transform (browser-unit via e2e):** `page.evaluate` calls
  `ReportingDrill.buildDrillDefinition` directly with fixture definitions — grain bounds
  (month/week/quarter), null → `is_null`, non-filterable dim → `null`, smart-set
  intersection — asserting on the returned JSON. This pins the pure function without
  needing chart pixel-clicks.
- **E2E (table-provider source — TEST env has no Statistics DB):** run a one-breakdown
  aggregate, click an aggregate table row → drawer visible (`data-testid`
  `reporting-drill-panel`), detail rows present, Esc closes; export buttons present for
  the seeded admin. Chart pixel-click path is browser-verified manually on INT (canvas
  coordinate clicks are too brittle for CI).
- **Manual on INT:** docprocessing "doc count by docsource per month" → click a month
  bar → drawer rows match the bar's period; `workitem_id` link opens the workitem;
  drill a "(null)" group and confirm rows from processes lacking the field appear
  (validates B end-to-end).

## Non-interference with in-flight work

`feat/rich-export` Phase 2 owns `templates/js/_reporting_simple_js.html`,
`templates/js/_reporting_js.html`, `templates/js/_reporting_viz_js.html`,
`templates/reporting.html`, `templates/_reporting_simple.html` and
`static/css/reporting.css` until it lands, and its multi-series `mountChart()` defines
the chart shapes drill clicks must interpret. Therefore:

- **Backend task (the `is_null` symmetry fix + tests) may start immediately** — rich-export
  touches `tests/unit/test_reporting_query.py` only additively; coordinate by using
  distinct test names.
- **All frontend tasks are blocked until `feat/rich-export` is merged** into
  `feature/2.5.63`. The implementation plan anchors on function names and quoted
  snippets, not line numbers.
