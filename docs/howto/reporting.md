# Reporting

> **Looking for how to *use* the page?** This file is the developer /
> architecture reference. The plain-language, task-shaped user guide is
> [`reporting-guide.md`](reporting-guide.md) — keep it current whenever you
> change user-visible behaviour here. That guide is **served in-app** at
> `/reporting/guide` (rendered server-side by `nx_lib/views/reporting/pages.py`
> with markdown-it-py; the deploy workflow copies the one docs file to the
> server, and a guide-only push to `main` still triggers a deploy). The
> page's **Help** button opens an in-app tips panel
> (`templates/_reporting_help.html`) mirroring the guide's "Tips" section —
> update it in the same commit too (the `reporting-help-sync` pre-commit hook
> nudges when forgotten).

The `/reporting` page is Nexora's self-service report builder — a PowerBI
replacement for internal users. Phase 1 ships a **table/list** visualization
over the curated **Document Processing** source with full filter, sort, combine,
custom-header, save/load, and Excel-export support.

## The Console shell (navigation + screens)

`/reporting` is one route rendering a **Console** workspace (design:
`docs/design/design_handoff_reporting_console/README.md`, superseding the
"Indigo Studio" hero/tab layout): a compact top bar (app icon, **Reporting**,
Beta chip, the run's `N rows · M ms` timing badge, a sources sync line,
**Help**, **Eddard**) over a body grid — a sticky 196px left rail and the
content area. `templates/js/_reporting_tabs_js.html` is the nav controller
(still exported as `window.ReportingTabs` for compat).

- **Workspace nav**: `Library`, `Results`, `Dashboards`, `Scheduled`
  (perm-gated on `reporting.schedule`), `Advanced`. The first three map into
  the old Simple pane's internal views (`window.ReportingSimple.navTo`);
  `Scheduled` and `Advanced` are their own containers. The `?tab=` URL param
  and the `nx.reporting.tab` storage key keep their historical names and now
  carry the screen name (`simple` stays accepted as an alias for `library`);
  `rp:tabshown` still fires with `simple|advanced` for the Simple pane's
  init contract, and `rc:screenshown` fires with the real screen name.
- **Results is a cache, not a runner** (design intent #8): it restores the
  last rendered result from `state.lastRun` without re-querying (only the
  Chart.js instance is re-mounted — the rest of the result DOM never left).
  With nothing rendered yet this session it opens the most recent report.
- **Sources rail**: one card per accessible source (`/api/reporting/sources`
  for the list, **`GET /api/reporting/sources/health`** for the green pulse
  dot, the probe latency and the real database name — one timed
  `SELECT DB_NAME()` per distinct engine, shared across sources; the URL
  carries no database attribute because the engines are built from
  `odbc_connect` strings). The admin-only registry link is the gear next to
  the SOURCES label. With `reporting.sources.schema` each card becomes a
  button opening the **source visualizer** (below). The **Advanced** nav entry is currently parked
  (`hidden` in `reporting.html`) — the pane stays reachable via
  `?tab=advanced`, Open-in-Advanced and `ReportingTabs.show('advanced')`.
- **One fetch per catalog per page load.** The page is five independent IIFEs
  (tabs rail, Simple, Advanced, dashboard builder, drill drawer) that cannot
  read each other's state, and each used to fetch its own copy of the same
  registries — `GET /api/reporting/sources` **3×** and `/api/reporting/measures`
  **3×** per visit, serialised behind one another. They now share one in-flight
  promise via `window.ReportingCatalog` (`templates/js/_reporting_catalog_js.html`,
  included before every consumer): `ReportingCatalog.sources()` /
  `.metrics()` each resolve to a **fresh parse** per caller, so a module that
  decorates its own copy can't corrupt another's. `/api/reporting/reports` is
  deliberately not memoised — it changes on every save, rename and delete.
- Everything still runs through `.reporting-shell` (1600px max-width /
  40px inset) so the page lines up with the rest of the app. The Console
  skin lives in **`static/css/reporting-console.css`**, loaded after
  `reporting.css` and scoped under `body.reporting-console`; it rides the
  `nexora-ui.css` tokens, so the user's accent pick and dark mode apply
  without page-specific code. Page type is Schibsted Grotesk.
- `_header.html` links `nexora-ui.css` from the `<body>`, i.e. *after* the
  reporting stylesheets — an equal-specificity override silently loses, so
  Console overrides are prefixed with `body.reporting-console`.

- **Library screen** — header row (title, count pill, **New dashboard**,
  **New report**), a filter row (search, sort: recently-updated/name, a
  2-or-4-cards-per-row layout toggle persisted in
  `localStorage['nx.reporting.layout']`), then the three grouped card grids.
  Cards are compact: type tag, one-line name, a 22px preview strip, owner
  footer, and an owner-only `…` menu (Share / Delete —
  `window.Reporting.openShareFor(id)` drives the existing share modal). The
  old landing hero + global Ask-AI bar are gone (design intent #1); the AI
  entry point is the top-bar **Eddard** button.
- **Report cards with live-preview thumbnails** — every card in the Library/
  My reports/Shared-with-me groups renders a small preview (a chart curve,
  a big-number total, or a mini table) from the report's last cached run
  result (`nx.reporting.preview.<id>` in `localStorage`, written on every
  successful run) rather than from re-running the report on landing load; a
  card with no cache yet shows a deterministic decorative placeholder seeded
  from the report id. A definition edit without a re-run keeps showing the
  previous shape until the next run.
- **Wizard step chips + summary** (`#rsWizardRail`, `#rsWizSummary`) — the
  four steps render as horizontal chips (active = accent tint, done = check
  dot) with a running "Step N of 4" indicator, and the chosen values collect
  in a **"So far"** panel beside the step card; the step renderers, ids,
  testids and flow are unchanged from Phase 1 — only the chrome around them
  changed. Coverage badges on measure/breakdown chips render as a small
  colour-tiered progress bar (same amber/muted convention).
- **KPI stat band** above the results — **one labelled total card per
  metric** (`Total · <metric label>`), followed by bucket count, average per
  bucket and peak for the primary measure under a heading naming it; hidden
  for zero-row or non-numeric results. Every caption names the measure it
  belongs to: the label is the result column's own `header`, which
  `_prepare_run` fills from the metrics registry (`metric_result_columns` in
  `views/reporting/_shared.py`), so a run's table, export and KPI band all read
  "Documents imported" rather than `docs_imported`. A bare "Total" used to
  hold whichever metric happened to come first, with nothing saying which.
  - **Totals are the server's, not the browser's.** The band renders
    `state.grandTotals` — the zero-column clone run's row (or, for a
    zero-dimension definition, the single row the main run returns), which is
    correct for every aggregation. Summing the grouped rows in the browser is
    only right for additive metrics; it is the fallback for a result with no
    semantic metrics (SQL / plain grid). The separate `rsStatCard` that used
    to repeat these totals just above the band is retired.
  - **Distribution stats need a distribution.** Buckets / average per bucket /
    peak render only when the definition has at least one dimension — a
    zero-dimension run is a single grand total per metric.
  - **Levels.** When a metric's registry row has **`TotalMode = 'latest'`**,
    its card's caption adds a **"· last bucket &lt;bucket&gt;"** suffix,
    naming the bucket the number actually covers, and the fallback total is
    that bucket's value rather than a sum across buckets (point-in-time
    metrics like backlog are wrong to add up). Each metric is judged by its
    **own** total mode, so a summed count and a levelled backlog can share one
    band. The suffix is the client's own zero-filled last bucket, so the
    wording is deliberately bucket-honest rather than implying snapshot
    precision (`kpiLatestSuffix` in `reporting_simple.js`).  When the definition carries a **single relative-date token filter**, the run request
  sets `compare: true` and each stat renders a **delta chip** (↑/↓/— plus a
  percentage) against the immediately preceding period of the same length —
  see **Comparison & delta chips** below for the exact semantics (why it's
  not always "last calendar month", and when the average chip is suppressed).
  An **AI caption** (a 1–2 sentence auto-narration, gated by
  `reporting.ai.explain_data`) can also appear under the chart — see
  **AI assistant → Auto captions**.
- **Timing badge** in the masthead — "N rows · M ms", the row count from the
  run response and the elapsed time measured client-side around the fetch;
  appears after the first successful run.
- **Query side card** (`#rsSqlView`) — the result's chart card stretches
  beside a 292px side column holding the AI-insight caption card and an
  always-visible, syntax-coloured **Query** card (the inlined `sqlDisplay`
  SQL, rendered on every successful run). The old one-line SQL peek footer
  is retired; the `⋯` menu's `Show query` entry stays as a scroll-to
  shortcut. Hidden whenever `sqlDisplay` is absent (the WS1 inliner-degrade
  fallback keeps working).
- **Result header** — a `Library / <name>` breadcrumb with a green **Saved**
  chip for persisted reports, a **Run again** tint button, then Adjust /
  Export / **Save** (primary) / the `⋯` overflow menu (`#rsMoreMenu`,
  hosting `Open in Advanced`, `Show query` and `Delete report`). The
  error-state "Open in Advanced" escape hatch stays a visible inline
  button. `Open in Advanced` restores the current definition into the
  builder **and runs it** (`window.Reporting.run()` right after
  `applyDefinition()`) — it used to only pre-fill the wells, leaving
  Advanced showing no results and "Show query" hidden/stale until the user
  pressed Run themselves (#178, Task 15).

Single-series bar/line charts render in ink-navy with a brand-indigo accent
on the peak value; multi-series charts keep the existing categorical
palette. Dark mode lifts the single-series ink-navy family to a lighter
indigo (`#818cf8`/`#c7d2fe`) rather than reusing the locked light-mode hex
values, and re-themes every new hero/card/chip/dashboard colour plus the
Chart.js grid/tick colours at chart-build time — toggling dark mode with a
chart already on screen re-themes on the next render, not live.

- **Simple** — the default; built for report *viewers* and non-data-science
  stakeholders. It is purely a presentation layer over the existing REST
  endpoints (`templates/_reporting_simple.html` +
  `static/js/reporting_simple.js`). It opens on the **landing hero**
  (AI command bar + suggestion chips + "New report"/"New dashboard" —
  see **Indigo Studio identity** above), then the library below it:
  - **Library** — every report you can see, grouped into *Library*
    (org-shared, `Visibility='shared'`, any owner), *My reports*, and *Shared
    with me*, each card showing a live-preview thumbnail. Click a card to
    run it (lazy — nothing runs until opened); a `kind:'dashboard'` card
    instead opens the **dashboard** view (see **Dashboards** below).
    Live-SQL (`kind:'sql'`) reports are hidden here (viewers can't run them);
    they stay fully usable in Advanced.
  - **+ New report (wizard)** — measures (from the metrics registry;
    **multi-select** — the first pick pins the source and other sources'
    chips disable until the selection is cleared; the result carries one
    column/series per metric and the KPI band one labelled total per metric; admins
    grow the wizard's reach by adding rows at `/reporting/metrics`, zero code
    change) → **which processes?** (own step, checkbox list all pre-checked;
    skipped for sources without processes — step headings auto-number via CSS
    counters so no gap shows) → break down by *over time* (with a grain
    select, default month) / a category / *none — just the total* → time
    range (presets or a custom flatpickr range; emits a `between` filter on the
    **raw** date field, defaulting to `import_date`). The grain select is
    **always visible** once the source has any date field at all, not only
    after a time breakdown is picked — it starts disabled with a
    "Pick a time breakdown first to choose its granularity." tooltip, so the
    control is discoverable up front instead of appearing to not exist (#178).
    A **table** source with no process registry but a filterable string field
    whose name/label matches `/process/i` (formerly
    `backlog_history.ProcessName`; the source is retired but the mechanism
    stays for future table sources)
    gets the same "which processes?" step in spirit — a **field-scope step**:
    it POSTs the field's up-to-100 distinct values from the new
    `POST /api/reporting/field_values` endpoint (`reporting.view`-gated,
    source-permission-checked, whitelisted-filterable-field only, `SELECT
    DISTINCT TOP (100)`) and renders them as the same pre-checked checkbox
    list. A column entry may declare `"labelWith": "<OtherField>"` in
    `ColumnsJSON` (was seeded for `backlog_history.ProcessName` →
    `ClientName`, migration `0065`): the endpoint then returns a `labels`
    map alongside `values`, labelling each distinct value
    `"<companion>.<value>"` (lowercased companion — `privera.03_Invoice_New`,
    matching the app-wide client.process idiom); the filter value stays the
    bare column value. A second flag `"grantScoped": true` (was seeded by
    migration `0066`) additionally drops every value whose client.process
    label is **not** in the caller's `reporting.scope.process.*` grants — the
    snapshot collector records every Octo process, but the picker should only
    offer the ones the rest of the app shows. This is UI curation, not a
    security boundary: the run path stays gated by the source-level
    permission alone. A partial pick serializes to a plain `{"op": "in"}`
    filter on that field — not `scope.processes` — which the result view
    renders as the **process chip** ("Processes: a, b" — clicking it opens a
    checkbox picker; picking everything removes the filter). All `in`/
    `not_in` filter chips likewise edit through a checkbox picker fed by
    `field_values` (or the process registry for `processname`), falling back
    to the free-text editor when no values are available. If the endpoint is
    unreachable or the field has no values, the step is silently skipped
    (graceful degrade — the same behaviour production sees when StatisticsDB
    is down). Time presets include **This
    week** and **This quarter** (both stored as tokens in `WIZ_TOKENS`, so saved
    and scheduled reports stay relative). Any wizard-shaped result shows an
    **"Adjust in wizard"** button that reopens the walkthrough with all prior
    picks pre-selected. **Back** steps back through wizard steps preserving picks;
    **✕** (on both the wizard header and the result bar) exits straight to the
    library without discarding anything already saved.
    Measures and category/date chips whose field only *some* of the selected
    processes provide carry an **"n/m" coverage badge**, colour-tiered —
    amber for partial coverage, muted for low (≤ ⅓ of the scope) — with a
    tooltip naming the providing processes (documents from the others land in
    the empty-value bucket, and a partial measure counts only its providers'
    documents). The chip list follows the process step live: chips with zero
    coverage under the picked scope hide, stranded selections are pruned, and
    the remaining chips **sort by coverage** (full coverage first, `1/x` at
    the bottom). A metric whose base field no allowed process provides is not
    offered at all.
    The category list is curated for the Document Processing source — within
    the same coverage tier **Process** leads (one value per Octo process; in
    this deployment each process corresponds to a client, so it delivers
    per-client numbers), then the preferred business dimensions (Document
    Source, Document Type, Forwarding, Owner no., Property No., Registered,
    Tenancy no.), and technical noise (Bank PK, creditor no., barcode,
    document date, workitem id) is hidden; other sources list their catalog
    fields unfiltered. There is **no chip cap** — every filterable string
    field the Advanced tab offers renders as a chip.
  - **Ask Eddard** — the hero bar and its suggestion chips are a shortcut into the
    shared **Eddard chat panel** (`window.ReportingChat.open()` + `.send()`):
    typing a question and pressing enter opens the panel and sends it there
    rather than running its own one-shot ask. See **AI assistant** below.
    Hidden if AI is unconfigured.
  - **Result view** — a grand-total **number card** (computed by a zero-column
    clone run, so it is correct for every aggregation — avg/count_distinct
    included), a **chart card** (line for date breakdowns, bar for categories by default,
    with a bar/line/pie/doughnut switcher; the chosen type is saved with the report).
    The wizard supports **up to three breakdowns**, including more than one date
    (export date *and* import date together, #164 — all dates share the one grain
    select, so a per-date grain still needs the Advanced tab); the first breakdown is
    the chart axis and every remaining breakdown joins into the composite colored series
    ("Process · Source" — grouped bars or one line per series, with a stacked-bar option),
    exact for every aggregation since nothing collapses in the pivot. Charts cap
    at 50 axis values and 12 series; categories beyond 50 chart the top 50 with a note.
    When no chart is possible the result explains why (single total, too many date points,
    chart library unavailable). A **chart-PNG download** button in the chart toolbar saves
    the current chart as an image. A **Show query** toggle (collapsed by default,
    re-collapsed on every run) reveals the executed SQL — pretty-printed server-side
    (sqlglot), syntax-highlighted, and with the bind-parameter values inlined as
    literals, so the statement reads (and copies) as runnable SQL. Execution itself
    stays fully parameterized; the Copy button copies the inlined statement (visible
    to anyone who can run reports). While a report
    runs, both tabs show a pulsing in-flight indicator (the Advanced **Run** button locks
    until the response lands), and the Advanced Ask-AI surfaces show the same indicator
    with rotating status lines.
    A **Show table** toggle, *Save* (always creates a new
    row under My reports), *Open in Advanced* (pre-fills the builder **and
    runs it**, see **Result header** above), and *Export*
    (downloads Excel with a title block and — when a chart is on screen — the chart image
    embedded above the data; needs `reporting.export`). For AI-built results, a
    **transparency line** below the report title shows the AI's explanation
    and the filters/processes it applied, so a wrong guess (bad date range,
    wrong process) is immediately visible.
    Every result (wizard-built or library-opened) shows **editable filter/process
    chips** — click one to edit its value inline, or × to remove it; each change
    re-runs the report immediately, no AI involved. Whenever the definition has a
    date column that is (or *could be*) grain-broken-down, a **Granularity chip**
    joins that row — `Granularity: Month` etc. — click it to change grain the same
    way as any other chip, so the breakdown's time resolution is always visible
    and editable on the result itself, not only back inside the wizard (#178).
    (The AI-specific **Refine**
    bar that used to sit alongside these chips is gone — a follow-up question now
    just continues the conversation in the **AI chat panel**, see below.) When the
    server row limit is hit, both tabs show "Showing the first N rows — narrow the
    filters or time range to see the rest."
- **Advanced** — the full three-panel builder described below, unchanged.

Deep link with `/reporting?tab=advanced` (or `?tab=simple`); without a `?tab=`
parameter the last-used tab is restored per browser (`localStorage`).

## Comparison & delta chips

**Simple tab only** (the Advanced KPI band does not have this — see
**Dashboards → KPI trend** above for the unrelated dashboard-card mechanism).
When the current definition's filters contain **exactly one relative-date
token filter** (`{"token": "this_month"}` etc. — a literal date-range pair, no
token filter at all, or more than one token filter, are all ambiguous and get
no comparison), the Simple result run sends `compare: true` on
`POST /api/reporting/run`. The server (`shifted_definition_for_comparison` in
`nx_lib/reporting/tokens.py`) reruns the **same** definition with that one
token filter replaced by a literal window shifted back by **the current
window's own length in days**: `[start − length, start)`. The response gains
a `comparison` block:

```json
{ "comparison": { "columns": [...], "rows": [...], "priorStart": "2026-06-01", "priorEnd": "2026-06-30" } }
```

**This is not a calendar-aligned "last month"/"last quarter" shift** — a
31-day month shifted back 31 days lands one day short of the 1st of a
30-day prior month. The delta chip's tooltip therefore only ever shows the
literal `priorStart`–`priorEnd` range, never a calendar label. The KPI
band's **Total**, **Avg per bucket**, and **Peak** tiles each get a chip —
an arrow (↑/↓/flat "—") plus a percentage — computed client-side
(`computeDelta`/`deltaChipHtml` in `reporting_simple.js`) from the
current value vs. the same stat over `comparison.rows`:

- **Flat** when the prior value is `0`/non-finite (no percentage is
  meaningful) or the magnitude of change is under 0.5%.
- **Colour is directional, never inverted** — more of a "more is good" metric
  going up renders the same "up" colour as more of a "more is bad" metric
  going up; the chip never guesses which direction is actually good for a
  given metric, it only ever reports the raw direction.
- **The Avg-per-bucket chip is suppressed** (Total and Peak still render)
  whenever the current and prior periods zero-fill to a **different number of
  buckets** — a day-length shift that isn't aligned to the chart's grain
  (e.g. a calendar-quarter preset against a month grain) can land the prior
  window's start mid-month, producing a different bucket count than the
  current period. Averaging `total/bucket-count` across two genuinely
  different-length periods would fabricate a percentage, so that one chip is
  dropped rather than shown misleadingly; Total and Peak are unaffected
  because an extra all-zero bucket contributes `0` to both.
- The Simple KPI band's headline total card also gets a small inline **sparkline**
  (a hand-rolled SVG polyline, not a Chart.js instance) of the metric series
  — gated to the same single-dimension date-grain case the zero-fill already
  special-cases.

> **Viewer semantics:** a shared library report runs against the *viewer's*
> grants (`reporting.scope.process.*`, per-source perms) — different users can
> legitimately see different numbers, or a friendly "you don't have access"
> message. This is existing run-path behavior, surfaced honestly in the UI.

## Forecast

Any result shaped like **exactly one date-grained breakdown plus one or more
metrics** — the same D2 shape the zero-fill and comparison chips key off —
can be projected forward. This is an **owner-locked single-dim rule**: two or
three breakdowns, a dimension without a grain, or zero metrics all leave the
Forecast control disabled (the Simple toggle button and the Advanced
`rpForecastWrap` checkbox both call the same `forecastEligible(def)` check
client-side; the server independently re-checks the shape in
`compute_forecast` and never trusts the flag alone).

**Persistence.** The toggle and horizon live in the report definition as an
optional `forecast` block — `{ "enabled": true, "horizon": "auto" }` — so a
saved or scheduled report remembers whether forecasting was on. `horizon` is
`"auto"` or an integer number of buckets in `[1, 60]`; the Simple/Advanced UI
only offers Auto/+7/+14/+30, but the schema accepts any value in range for
forward compatibility. `compare` (delta chips) and `forecast` are independent
blocks on the same payload and can both be set at once.

**Method.** `nx_lib/reporting/forecast.py` fits an **OLS linear trend** over
the zero-filled bucket series and, once there are at least two full seasonal
cycles for the grain (7 buckets/period for `day`, 12 for `month`, 4 for
`quarter` — `week`/`year` stay trend-only), layers on **additive seasonal
indices** from classical decomposition (mean residual per calendar position,
centered to net to zero). Each projected point carries a **95% prediction
interval** from the residual standard error and the two-sided Student-t
quantile at the fit's degrees of freedom (falling back to `1.96` past 30 df),
widening with distance from the fitted window; an all-nonnegative history
clamps projections and bounds at zero. A series needs at least 5 zero-filled
buckets to fit at all, and seasonal decomposition only engages when it would
leave at least 3 residual degrees of freedom — short or sparse series
silently fall back to trend-only rather than fail. Deliberately stdlib-only
(no numpy/scipy/statsmodels), matching the `stats.py` rule; see the
`# ponytail:` note in `forecast.py` for swapping in a heavier library later.

**History window (lookback).** The fit does not only see the rows the visible
result already returned — a **day-grain** report over "this month" would hand
the seasonal fit under four weeks of daily buckets, nowhere near the two
weekday cycles it needs. When the definition's single date filter is a
**relative-date token** (the same token-only ceiling `compare` uses),
`widened_definition_for_forecast` (`nx_lib/reporting/tokens.py`) reruns the
query with that filter's start pushed back by a grain-dependent number of
days — `day`: 56, `week`: 182, `month`: 730, `quarter`: 1460, `year`: 2190
(`_FORECAST_LOOKBACK_DAYS`) — purely to fit on; the widened rerun is discarded
and only its fitted trend/seasonality feed the chart, which still extends
only from the original visible window. A literal (non-token) date range is
left as-is — there's no "back" to extend a range the user typed explicitly —
and a failed widened rerun falls back to fitting on the visible rows alone
rather than failing the run (#178).

**`unavailable` reasons.** `compute_forecast` never raises on user data —
a shape or data problem returns `{"unavailable": "<reason>"}` instead of a
projection: `"shape"` (the D2 gate above isn't met — shouldn't normally reach
the server since the UI disables the toggle first), `"bad_buckets"` (a bucket
value doesn't parse as a date, or the filled range doesn't land on the last
real bucket — a grain/data mismatch), and `"insufficient_history"` (fewer
than 5 buckets after zero-fill, a degenerate all-identical-x series, or an
absurd bucket count from a huge date range). The UI collapses all reasons
into one user-facing message, *"Not enough history to forecast this
series."*, shown as the chart note when the toggle is on but no dashed line
appears.

**Charting and table rows.** The chart extends past the last actual bucket
with a dashed prediction line plus a shaded 95% band (`_forecast`/`_band`
flagged Chart.js datasets, filtered out of the legend and excluded from
`state.chartData.datasets` — the actual-only array the chart-type switcher
and preview cache read). The results table appends the predicted buckets as
extra rows carrying a small "Forecast" badge; the anchor bucket
(`forecast.anchor`) is the last real data point, not the first predicted one.

**Drill-through never fires on predicted points.** Both the chart's point
`onClick` and the table's row click bail out before opening the drill drawer
whenever the point/row is forecast-flagged — there is no underlying query to
drill into for a number the server invented. This is enforced at the click
sites, not inside the shared drill drawer module.

**Exports.** `forecast_export_rows` appends a trailing **`Forecast` marker
column** to CSV/XLSX exports — empty string on actual rows, `"forecast"` on
projected rows — rather than a separate sheet or file, so a spreadsheet
consumer can filter or highlight predicted rows without out-of-band
knowledge. Only `yhat` is exported; the confidence bounds are chart/UI-only
(D7). The XLSX export additionally styles forecast rows grey-italic as a
visual cue matching the chart's dashed/shaded treatment.

**Scheduled mails.** `ops/run_scheduled_reports.py` computes the forecast
block the same way the interactive run does, whenever the saved definition's
`forecast.enabled` is `true` — the emailed chart PNG carries the dashed
line/band and the attached export carries the marker column, with no
schedule-level opt-in beyond what's already saved in the definition. A
forecast failure (bad data shape, an exception) degrades to no-forecast
rather than blocking the mail.

## Dashboards

A **dashboard** is a saved report whose definition has
`kind: 'dashboard'` instead of the usual curated/SQL shape — no schema
change, no new endpoint, no new permission. It lives entirely in the Simple
pane (`static/js/reporting_dashboard.js`, exposing
`window.ReportingDashboard = {openNew, open, close}`) as a fourth pane view
alongside library/wizard/result, and is built out of multiple **cards**
(KPI / line / bar / donut / table / report), each running the existing
curated-source `POST /api/reporting/run` path independently.

**Definition shape (`schemaVersion: 1`):**

```json
{
  "kind": "dashboard",
  "schemaVersion": 1,
  "title": "My Dashboard",
  "globalFilters": [
    { "field": "import_date", "op": "between", "value": { "token": "this_month" } }
  ],
  "cards": [
    {
      "id": "n100",
      "type": "kpi",
      "span": 3,
      "title": "Documents this month",
      "definition": { "source": "docprocessing", "columns": [], "metrics": [{ "metric": "doc_count" }], "filters": [] },
      "filterOverrides": []
    }
  ]
}
```

`type` is one of `kpi` / `line` / `bar` / `donut` / `table` / `report`; `span`
is the card's grid width; `definition` is a normal report-definition fragment
(same shape as **Report-definition v1 JSON** below) run through the same
validator and query builder as any other report; `filterOverrides` are
per-card filters that layer on top of the dashboard's `globalFilters`.

- **Access model** — identical to any other saved report: the dashboard row
  lives in `dbo.Reports` like every other `kind`, gated by `Visibility`
  (private/shared) and `dbo.ReportShares` (per-user, optional edit grant).
  There is no separate dashboard permission or sharing mechanism — Save,
  Save as, Rename, Delete and the Share dialog all work exactly as
  documented in **Save & load** / **Sharing & the shared library** above.
- **Per-card runs** — each card runs independently against
  `POST /api/reporting/run` using its **effective filters**: the card's own
  `definition.filters`, merged with the dashboard's `globalFilters`, merged
  with the card's `filterOverrides` — keyed by field, later sources winning
  on a collision. Concretely: a `filterOverrides` entry on a field beats a
  `globalFilters` entry on the same field, which beats the card's own base
  `definition.filters` entry on that field; fields that appear in only one
  source are simply included. This means edits to the global filter bar
  propagate to every card *except* the fields a card has explicitly
  overridden (shown with a small "This card overrides the global filters"
  chip), and a card with no override at all shows "inherits global
  filters".
- **Edit mode** — an Edit/Done toggle exposes drag-to-rearrange (native
  HTML5 drag-and-drop), add/duplicate/remove-card, and the global-filter
  popover (field/op/value, from the same run catalog the card definitions
  use); every change autosaves through the normal report CRUD — `POST
  /api/reporting/reports` (`api_reports_create`) the first time, `PUT
  /api/reporting/reports/<id>` (`api_reports_update`) on every save after —
  there is no separate "dashboard save" endpoint.
- **KPI trend** — a KPI card shows a "vs previous period" delta only when
  its **effective filters contain exactly one `between` date-range filter**;
  the client re-runs the card with that range shifted back one period
  (`this_month` → `last_month`, `this_quarter` → `last_quarter`, `this_week`
  → `last_week`, `this_year` → `last_year`) and computes the percentage
  change. Any other shape (no date filter, a literal date-range pair without
  a shiftable token, more than one date filter) hides the trend rather than
  guessing.
- **Export** is **per-card only, v1** — the dashboard header's Export menu
  lists every card; picking one POSTs that card's effective definition to
  the existing `/api/reporting/export` (gated by `reporting.export`, same
  as everywhere else). A whole-workbook (one sheet per card) export is not
  built yet.
- **Two-dimension reports** — a line or bar card whose report has a second
  dimension ("per month **/ process**") pivots it exactly like the Simple
  result view: first dimension on the axis, one named, colored series per
  remaining-dimension combination, legend below the chart. Series are ordered
  by total descending and capped at 8 (a 190 px card body cannot carry
  Simple's 12 legibly); when more exist the card says how many it is showing.
  Donut/table cards have no axis to pivot against, so they name the
  combination instead — the label joins every dimension ("Jan · Invoice") and
  each row stays one exact aggregate value. KPI cards never see a breakdown
  at all: their run clears `definition.columns` (see **KPI trend** above).
- **Drill-through** works per card exactly as it does on a normal aggregate
  result (see **Drill-through** below) — clicking a chart element or table
  row on an eligible card opens the same slide-over drawer, with one chip per
  dimension (on a pivoted card, the clicked bucket **and** its series); donut
  cards are excluded from click-drill (their >8-category "Other" rollup breaks
  the 1:1 index-to-row mapping the drawer needs).
- **`report` card ("Whole report") — a saved report 1:1** (#178). In Edit
  mode, the "Whole report" add-pill opens a picker of the current user's own
  saved non-SQL, non-dashboard reports (`GET /api/reporting/reports`,
  filtered client-side); picking one copies that report's `definition` and
  name straight into the card verbatim. Unlike `kpi`/`line`/`bar`/`donut`,
  this card is not a dashboard-authored chart type — it renders the adopted
  report exactly as the Simple tab would: the KPI band with one labelled
  total per measure (fed by a zero-column aggregate clone, correct for every
  aggregation including `avg`/`count_distinct`, not a client-side sum of
  already-grouped rows) plus prior-period delta chips — the same band Simple
  shows, including its `TotalMode='latest'` handling for metrics like
  `backlog_total` (see **Metrics registry** below) — a chart using the
  report's own saved `chartType`/colours/right-axis/forecast settings, and
  the full result table (behind a "Show table" toggle when a chart is drawn,
  shown directly otherwise) with row drill-through. All of this is drawn
  through the Simple pane's own pure builders, exposed on
  `window.ReportingSimple` (`kpiBandHtml`, `buildChartData`,
  `chartConfigFor`, `tableHtml`, …), so the dashboard card and the Simple
  result view cannot drift apart. Because it carries the source report's
  full definition rather than a dashboard-authored one, a `report` card still
  participates normally in `filterOverrides`/`globalFilters` layering and
  drill-through like any other card. One real cost worth knowing: the card
  typically fires two `/api/reporting/run` requests per render — the
  breakdown run plus a zero-column totals clone (skipped only when the
  report has zero dimensions, where the breakdown run's own result already
  is the total) — mirroring what the Simple tab itself does on every visit,
  so a dashboard with several whole-report cards can be slower to load than
  one built entirely from `kpi`/`line`/`bar`/`donut` cards.

Migration history: the dashboard builder **supersedes**
`docs/superpowers/plans/2026-07-15-reporting-pin-to-dashboard.md` (a
different, never-executed design that would have added a `dbo.ReportingPins`
table and a "pin a report to the dashboard" affordance) — that plan is
stamped superseded; this multi-card dashboard covers the same underlying
need ("my saved reports as live tiles") without any new table.

## What the page does

Users arrive at a three-panel Layout A builder:

- **Left — Field panel:** source selector, searchable field list. Drag or
  double-click a field to add it as a column.
- **Centre — Results:** toolbar (report title, Save, Export), results table
  rendered after running the report.
- **Right — Config wells:** Columns (order + custom display headers), Filters,
  Sort, Format (report title/subtitle).

Each report run POSTs a **report definition** (v1 JSON — see below) to
`/api/reporting/run`. The server validates every column, filter field, sort
field, and scope entry against a server-side whitelist (the source's field
catalog); nothing user-supplied reaches SQL unchecked.

> **Motion:** the page has a thin, additive animation layer
> (`templates/js/_reporting_anim_js.html`, built on [Motion](https://motion.dev)
> loaded via a pinned + SRI'd `<script>`): a staggered column entrance, rows
> that stream in after **Run**, fade-in chart/pivot views, spring-in modals, and
> hover/press button feedback. It only observes the DOM the builder produces, so
> the page behaves identically with it removed, and it no-ops under
> `prefers-reduced-motion` or if the CDN is unavailable.

### Pick clients / processes (process scope)

The **Processes** picker in the left panel (below **Source**, docprocessing only)
is a multi-select dropdown of the caller's allowed `<client>.<process>` grants,
grouped by client. Tick a whole client to include all its processes, or tick
individual processes; the summary shows **All processes** or `selected / total`.
Default is everything (= no scope restriction). Table sources (e.g. Generali,
Octo) carry no processes, so the control is hidden for them.

The picker serialises to the definition's `scope`: a fully-ticked client is
emitted under `scope.clients` (durable — it auto-includes processes added under
that client later), a partially-ticked client emits its picked
`scope.processes`. Server-side, `_effective_scope` narrows the caller's allowed
set to **(client ∈ `scope.clients`) ∪ (process ∈ `scope.processes`)**; empty
clients *and* processes means all allowed. The grant set is always the boundary —
requesting a client/process the user has no `reporting.scope.process.*` grant for
silently excludes it (no data leak). The selection is saved with the report and
restored on load.

The **field list scopes to the selected process(es)**, mirroring the workitems
field picker. Not every process populates every field mapped in
`nx_lib/mapping_config.py`'s registry (`dbo.ProcessFieldMappings`, migration `0074`), so each
catalog field carries the `processes` that expose it; the left-panel list shows a
field only when at least one selected process exposes it (union — `All
processes` shows every field). This is purely client-side off the catalog already
loaded. Narrowing the scope also **prunes any already-added column / filter / sort**
whose field is no longer available, so a definition can't reference a field absent
from every scoped process (which the query builder would reject).

### Date dimension (import / export date)

The docprocessing source exposes two synthetic **date** fields, `import_date`
and `export_date`, derived from each process's `ProcessSources.ImportColumn` /
`ExportColumn` (`nx_lib/mapping_config.py`, migration `0074`; CONVERT-vs-CAST
normalized like the dashboard). They are
filterable (date-range via the flatpickr filter row), sortable, and **grainable**:
a date column carries an optional `grain` (`day/week/month/quarter/year`, default
`month`) that the query builder truncates to — `DATEFROMPARTS(...)` for
month/quarter/year, Monday-anchored `DATEADD/DATEDIFF` for week. Grain applies to
projection/grouping only; a **filter** on a date field always compares the raw
date. Combined with a metric (e.g. `doc_count`) and a month-grain `import_date`
dimension, this produces "documents per month". Date expressions originate solely
from the `ProcessSources` registry row, never the client — same trust boundary as
the table/condition interpolation.

### Workitem dimension & distinct count (`workitem_id` / `workitem_count`)

The docprocessing source exposes a synthetic **`workitem_id`** field mapped per
process by `ProcessSources.WorkitemColumn` (`nx_lib/mapping_config.py`, migration
`0074`; originally `StatConfig.WorkitemColumn` from migration `0020`, decapitated
by `0075`; the underlying column names vary — `WorkItem`, `WorkitemID`, `WID`,
...). The query builder CASTs every mapping to `nvarchar(100)` so the
cross-process UNION never mixes the columns' native types (nvarchar vs int). A
process whose `WorkitemColumn` is NULL simply doesn't expose the field — set the
column in `ProcessSources` (via a migration) to add it for a new process, no
code change needed.

Its companion metric **`workitem_count`** (`COUNT(DISTINCT workitem_id)`,
registered in `dbo.ReportingMetrics`) was intended to answer "how many workitems"
where `doc_count` counts *rows*. The `workitem_count` metric is currently
**disabled** (see migration `0021`) — all four count variants (`COUNT(*)`,
`COUNT(WorkitemID)`, `COUNT(DISTINCT WorkItemID)`, `COUNT(Barcode)`) are
identical on the Statistics tables because there is one row per workitem and no
NULL workitem ids. The picker therefore offers only `doc_count`. Re-enable the
metric row in `dbo.ReportingMetrics` if a multi-row-per-workitem source ever
appears. Rows from a process without a workitem mapping still contribute nothing
to the `workitem_id` column (it projects as NULL), and the `workitem_id`
dimension/filter field remains fully available.

### Save & load

Reports are saved per user in the `dbo.Reports` table (NexoraDB). A saved
report stores the full v1 definition JSON. The **Saved reports** dropdown on the
toolbar groups **My reports** and **Shared with me** (the latter tagged with the
owner). **Load** restores a curated definition into the builder (source, columns,
filters, sort, scope, title/subtitle) or a SQL definition into the SQL editor +
target, switching mode by the saved `kind`. **Rename** and **Delete** act on the
selected report (owner only). **Save as** and **Rename** open an in-page name dialog (the browser's
`window.prompt` has been replaced).

### Sharing & the shared library

Reports are private by default. The **Share** dialog (enabled for a report you
own) controls two independent mechanisms, both held in NexoraDB:

- **Visibility** (`dbo.Reports.Visibility`): `private` (only you) or `shared`
  (read-only to *everyone* who can open the Reporting page).
- **Explicit per-user grants** (`dbo.ReportShares`): share with named colleagues
  by email/username, optionally **Can edit** (read-write). FK to `Reports` is
  `ON DELETE CASCADE`, so deleting a report removes its shares.

A named share leaves `Visibility` at `private`, so the owner's own card would
look untouched — the list endpoint therefore returns an owner-only
`sharedCount` (number of `ReportShares` rows) and both panes tag such a report
`· shared`, exactly like an org-wide one. It stays under **My reports**; only
`Visibility='shared'` moves a card to the **Library** shelf.

A recipient sees shared reports under **Shared with me** and can **Load** them.
**Save** overwrites in place only if they own the report or hold an edit grant;
otherwise it forks a copy (**Save as**). Only the owner can change visibility,
manage shares, rename, or delete. Endpoints:

| Endpoint | Who | Purpose |
|----------|-----|---------|
| `GET /api/reporting/reports` | any `reporting.view` | reports you own + shared-with-you (tagged `owned`/`canEdit`/`ownerName`/`sharedCount`) |
| `GET /api/reporting/reports/<id>` | owner / recipient | load (404 if not visible to you) |
| `PUT /api/reporting/reports/<id>` | owner / edit-grant | overwrite |
| `DELETE /api/reporting/reports/<id>` | owner | delete (cascades shares) |
| `GET /api/reporting/reports/<id>/shares` | owner | `{visibility, shares}` |
| `POST /api/reporting/reports/<id>/shares` | owner | set `visibility` and/or add a `user` share (`canEdit`) |
| `DELETE /api/reporting/reports/<id>/shares/<uid>` | owner | remove a share |

**Save vs Save as.** With a report loaded, **Save** overwrites it in place
(`PUT /api/reporting/reports/<id>`); **Save as** always creates a new copy
(`POST`). With nothing loaded, **Save** behaves like Save as and prompts for a
name. The current report's title field doubles as its name on an in-place save,
so editing the title then **Save** also renames it.

The Console result view follows the same rule (it used to `POST` unconditionally,
so Save duplicated the open report and the rename pencil forked a second copy
under the new name): `persistCurrent()` in `static/js/reporting_simple.js` `PUT`s
whenever `canUpdateCurrent()` — a `reportId` plus `owned || canEdit`, the same
pair the endpoint accepts — and `POST`s otherwise, which is the wizard/AI
result's first save. The rename pencil is that same call with a different name.
⋯ → **Save as copy** (`#rsSaveCopy`, shown only for an already-saved report)
arms the one-shot `saveAsCopy` flag to force the `POST`, then adopts the new id
as the open report so a following Save doesn't write back to the original.

### Result views — chart & pivot

After a run returns rows, a **Grid / Chart / Pivot** toggle appears above the
results and re-visualizes the current result set (curated *or* SQL) in place —
no re-query:

- **Chart** (Chart.js): bar, line, pie, or doughnut. Pick a **category** column
  and a **value** column; values are summed per category and the top 50
  categories are shown.
- **Pivot**: a drag-and-drop **matrix**. Drag fields into **Rows**, **Columns**,
  or **Values**; each Values field gets an aggregation (sum / avg / count / min /
  max). Multiple Row/Column fields nest into a multi-dimension matrix, with
  per-row and grand totals. Column dimensions render as **nested, multi-level
  column headers** (one grouped header row per Column field plus a measure row);
  rows and columns are sorted for stable, grouped output. Computation is
  client-side over the rows already in the grid.

The viz code lives in `templates/js/_reporting_viz_js.html` (exposes
`window.ReportingViz`); it operates purely on the `{columns, rows}` the grid is
showing.

### Drill-through

For **aggregate** results (a report with at least one metric and at least one
dimension, curated source — not live SQL), clicking a chart element or an
aggregate-table/grid row opens a slide-over drawer showing the underlying
document rows for that data point. Available on both the Simple and Advanced
tabs:

- **Clickable:** chart bars/points/segments, and rows of the Simple result
  table or the Advanced grid *when the result is an aggregate* (metric +
  dimension present). A cursor/hover affordance (and, on Simple, a hint line)
  only appears when a row or chart is actually drillable.
- **Not clickable:** raw-row table results (no metric), the big-number
  summary card, pivot-matrix cells, and SQL-sandbox results (a live-SQL
  definition carries no source/columns to transform into a drill query).
- The drawer re-runs the same curated source through `/api/reporting/run`
  with a synthesized raw-row definition — filters echo the clicked
  dimension value(s) (an exact date range for a grained date click, `eq` for
  a category, `is_null` for a null/"(empty)" group) plus any filters and row
  scope already on the parent report. This means drill rows obey the exact
  same grants, source permissions, and process scope as the report that
  produced them — there is no new trust surface.
- **Columns shown:** for sources that expose the smart-set fields
  (`workitem_id`, `processname`, `import_date`, `export_date`), those four
  come first, followed by the clicked breakdown field(s). Generic sources
  without the smart fields instead top up with up to ~6 leading catalog
  columns. `workitem_id` values render as links: a plain click opens the
  shared workitem detail panel (the same read-only view used by the Prepared
  Documents register preview) in a modal over the drawer, permission-gated
  the same way that panel is gated elsewhere; Ctrl-click or middle-click
  still opens the workitem in a new `/workitems` tab.
- **Row cap:** the drawer displays up to **100 rows** and shows a truncation
  note when more exist; use the drawer's **CSV** / **XLSX** export buttons
  (same `/api/reporting/export` endpoint used elsewhere) to get the full set.
- **Distinct-count caveat:** when the clicked number came from a
  `count_distinct` (or similar distinct) aggregation, the drawer shows a note
  that the rows displayed are those *contributing* to the number — the row
  count can exceed the distinct count because the same distinct value may
  appear on multiple rows.

Shared code lives in `templates/js/_reporting_drill_js.html`
(`window.ReportingDrill` — `buildDrillDefinition`, drawer open/close/render,
export), wired into `static/js/reporting_simple.js` (Simple: chart
`onClick`/`onHover` + result-row clicks) and `templates/js/_reporting_js.html`
(Advanced: chart `onElementClick` + grid-row clicks), with drawer markup/CSS
in `templates/reporting.html` and `static/css/reporting.css`.

### Contribution analysis ("Why did it move?")

When the Simple KPI band shows a **Total** delta chip (see *Comparison & delta
chips*), the chip is a button. Clicking it POSTs the current definition
(tokens intact) to `POST /api/reporting/contribution` and opens the drill
slide-over with one tab per dimension, each listing the values ranked by
their contribution to the change vs. the same shifted prior window the chip
used. Dashboard whole-report cards get the same button because they render
the Simple KPI band.

- **Dimensions** are picked automatically (`pick_dimensions` in
  `nx_lib/reporting/contribution.py`): `processname` first when the source
  has it, then string-typed catalog columns in catalog order, never
  `workitem_id`, never a field an `eq` filter already pins; at most three.
- **Rows** are the first metric grouped by that one column, run once for the
  current window and once for the prior one through the ordinary
  `_prepare_run` path (same grants, source permission and process scope as
  the report), joined on value, sorted by `|delta|`, top 8 plus `(other)`.
  `share` is `delta / (currentTotal − priorTotal)`; it is `null` for ratio
  metrics (`avg`, `min`, `max`, `count_distinct`) and when the total did not
  change. Header totals come from the zero-column clone (`total_definition`),
  so they always equal the band's Total.
- A dimension whose query fails is dropped and listed under `skipped`
  (footer note "Not shown: …"); the endpoint never 500s because one column
  is unqueryable. 400 without metrics or without exactly one relative-date
  token filter; 403 without the source permission.
- Clicking a row opens the normal drill-through for that value on the
  current window (`eq`, or `is_null` for "(empty)"); `(other)` is not
  clickable.

Code: `nx_lib/reporting/contribution.py` (pure), `api_contribution` in
`nx_lib/views/reporting/run.py`, `static/js/reporting_contribution.js` +
shim `templates/js/_reporting_contribution_js.html`, wired in
`static/js/reporting_simple_result.js` and `static/js/reporting_dashboard.js`.

### Export (Excel / CSV, and what you see)

Pick the format (**Excel** or **CSV**) next to the **Export** button. The Simple
result bar carries the same format select as Advanced — CSV downloads data rows
only; chart embedding (in both the browser-triggered XLSX and the server-rendered
scheduled-mail XLSX) applies to Excel exports only. Then export is **view-aware**:

- **Grid** → the raw result rows. POST the report-definition JSON to
  `/api/reporting/export`; add `"format": "csv"` for CSV (default `xlsx`).
  Returns `.xlsx` via `openpyxl` or UTF-8 `.csv` (BOM-prefixed so Excel detects
  the encoding). Custom column headers are used in the header row. The XLSX
  includes a **title block** (report title, source, generation timestamp) above
  the frozen header row; when a chart is visible in the browser, the chart image
  is **embedded above the data table** in the XLSX. CSV is unchanged (data rows
  only).
- **Pivot** → the computed pivot matrix. The client posts the displayed
  `{columns, rows}` to `/api/reporting/export/grid` (`reporting.export`; no DB
  access — pure serialization with the same formula-injection guard) in the
  chosen format.
- **Chart** → a **PNG** image of the current chart, rendered client-side from the
  Chart.js canvas (flattened onto white). The format selector does not apply.
  A dedicated **chart PNG download** button also appears in the Simple tab's chart
  toolbar for one-click image saves without exporting the full dataset.

Both serialization paths neutralize spreadsheet formula injection (leading
`= + - @` are prefixed with `'`).

## Permissions (`reporting.*`)

| Code | Grants |
|------|--------|
| `reporting.view` | Page access — nav entry visible, `/reporting` route allowed. |
| `reporting.source.docprocessing` | Use the Document Processing curated source. |
| `reporting.export` | Export reports to Excel (`.xlsx`). |
| `reporting.scope.process.<client>.<process>` | Include a specific client/process in a report's row scope. |
| `reporting.sql.run` | Run live read-only SQL in the sandbox against **Statistics** (see below). Grantable; admins seeded. |
| `reporting.sql.target.octopus` | Additionally target the **Octopus** runtime DB in the SQL sandbox. Independent of `reporting.sql.run`; grantable; admins seeded. |
| `reporting.admin.sources` | Manage the data-source registry at `/reporting/sources` (see below). Admins seeded. |
| `reporting.sources.schema` | Open the **source visualizer** on a Sources rail card — the tables, columns and foreign keys of the database behind a source (see below). Still requires that source's own permission. Migration `0079`; admins seeded. |
| `reporting.semantic.admin` | Manage the canonical-metrics registry at `/reporting/metrics` (see below). Admins seeded. |
| `reporting.schedule` | Schedule a saved report to run and be emailed (see below). Admins seeded. |
| `reporting.ai.use` | Use the AI assistant (Eddard) — see the chat toggle, ask natural-language questions (see below). Admins seeded. |
| `reporting.ai.sql` | Receive AI-drafted read-only T-SQL into the SQL editor. Grant alongside `reporting.sql.run`. Admins seeded. |
| `reporting.ai.explain_data` | Let a result's rows reach the model: gates **auto captions** alone, and — combined with `reporting.sql.run` — the chat agent's `run_sql`/`compute_stats` tools (live-query narration). Grantable; admins seeded (see below). |

**Scope permissions mirror the dashboard.** Migration
`0005_seed_reporting_permissions.sql` auto-creates a
`reporting.scope.process.<client>.<process>` entry for every existing
`dashboard.filter.process.<client>.<process>` and grants it to the same access
profiles. A user who can see a process on the dashboard can therefore include it
in a report without any manual grant work.

The base permissions (`reporting.view`, `reporting.source.docprocessing`,
`reporting.export`) are seeded to every access profile that already grants
`admin.view`. Adjust via the normal Permissions admin UI as needed.

## Report-definition v1 JSON

This is the shape saved in `dbo.Reports.DefinitionJSON` and sent to
`/api/reporting/run` and `/api/reporting/export`:

```json
{
  "schemaVersion": 1,
  "source": "docprocessing",
  "visualization": "table",
  "title": "My Report",
  "subtitle": null,
  "columns": [
    { "field": "doctype", "header": "Document type" },
    { "field": "status", "header": null }
  ],
  "filters": [
    { "field": "status", "op": "eq", "value": "Done" }
  ],
  "sort": [
    { "field": "date", "dir": "desc" }
  ],
  "scope": {
    "clients": ["clientA"],
    "processes": ["clientA.process1", "clientB.process2"]
  },
  "metrics": [
    { "metric": "doc_count" }
  ],
  "forecast": { "enabled": true, "horizon": "auto" },
  "rowLimit": 5000
}
```

**Metrics (optional, semantic layer — Slice 1).** When `metrics` is present and
non-empty, the report runs in **aggregate mode**: the selected `columns` become
the `GROUP BY` dimensions and each referenced metric adds an aggregated column.
Each entry is `{ "metric": "<code>" }` referencing a canonical metric from the
registry (see **Metrics registry** below). The server validates every code
against the source's enabled metrics and resolves it through
`nx_lib/reporting/semantic.py` into a safe `AGG(col) AS [code]` expression
(`MetricResolveError` → HTTP 400). Absent or empty `metrics` keeps today's
row-projection behaviour, unchanged.

**`forecast` (optional — see Forecast above).** `{ "enabled": bool, "horizon":
"auto" | 1–60 }`. Both keys are optional and `horizon` defaults to `"auto"`;
an unrecognized key or an out-of-range/non-integer `horizon` is a validation
error. Only takes effect on the single-date-dim + metrics shape — set on any
other definition it validates fine but `compute_forecast` returns
`{"unavailable": "shape"}` at run time.

**Filter ops (Phase 1):** `eq`, `ne`, `in`, `not_in`, `gt`, `gte`, `lt`,
`lte`, `between` (value is a 2-element list), `contains`, `starts_with`,
`is_null`, `is_not_null`. The validator rejects ops incompatible with a field's
declared type.

**Relative-date tokens.** Instead of a hard-coded date pair, a `between` filter
on a date field may carry a token value so the range resolves at run time — saved
and scheduled reports never go stale.

Token shapes:
- `{ "token": "<name>" }` — named preset
- `{ "token": "last_n_days", "n": <1–366> }` — rolling N-day window

Full token vocabulary:

| Token | Period covered |
|---|---|
| `today` | Current calendar day |
| `yesterday` | Previous calendar day |
| `this_week` | Mon–Sun of the current week |
| `last_week` | Mon–Sun of the previous week |
| `this_month` | Full current calendar month |
| `last_month` | Full previous calendar month |
| `this_quarter` | Full current calendar quarter (Q1 = Jan–Mar, Q2 = Apr–Jun, Q3 = Jul–Sep, Q4 = Oct–Dec) |
| `last_quarter` | Full previous calendar quarter |
| `last_3_months` | Rolling 3-month window (today − 3 months to today) |
| `this_year` | Full current calendar year (Jan 1 – Dec 31, incl. future days) |
| `last_year` | Full previous calendar year |
| `last_n_days` | Today − N days to today (N: 1–366) |

Tokens resolve to the server-local date at the moment the run request is
processed. The run response includes a `resolvedDates` list (one item per
token filter) showing the concrete `from`/`to` dates for transparency.

The Simple wizard's presets and the Advanced filter-panel preset dropdown emit
tokens automatically. The AI assistant drafts tokens for relative-time
questions.

Custom `header` on a column is presentation-only — it appears as the column
label in the results table and in the Excel export; it is never used in SQL.

## Source registry (admin)

The source list is **code defaults overlaid with a DB registry**. Built-in
sources live in `nx_lib/reporting/sources.py`; rows in `dbo.ReportingSources`
(migration `0010`) augment or override them at request time via
`merge_sources(code_sources(), db_rows)`. Admins (`reporting.admin.sources`)
manage the registry at **`/reporting/sources`**: relabel, enable/disable,
reorder (`SortOrder`), change the required permission, or register a brand-new
source — no code change for the common cases.

Each curated source binds to a **provider**:

- **`docprocessing`** — the bespoke builder over `nx_lib/mapping_config.py`'s
  registry (`dbo.ProcessSources` / `ProcessFieldMappings`, migration `0074`; the
  built-in source).
- **`table`** — a generic provider (`nx_lib/reporting/table_query.py`) that runs
  a **whitelist-built, parameterized `SELECT`** of the chosen columns over a
  single `BaseObject` (`Db.schema.object`) on the source's `Engine`
  (`nexora` / `statistics` / `generali` / `octopus`). Its field catalog is the
  source's `ColumnsJSON`
  (`[{field,label,type,filterable,sortable,grainable}]` — `grainable` marks a
  date/datetime column as eligible for the Simple wizard's "over time"
  breakdown and AI date-token filters; `table_source_catalog()` and the run
  path's `grainable_fields` both key off it, and `build_generic_query` applies
  the actual `DATEFROMPARTS`/`DATEADD` bucketing expression per the column's
  `grain`). Every identifier (base object + columns) is validated against
  `^[A-Za-z_][A-Za-z0-9_]*$` and bracket-quoted; users only choose among
  catalogued columns and supply parameterized values — so a `table` source is
  safe to register from the UI.

**Built-in registered sources.** Migration `0011` seeds two `table`-provider
sources: **Generali — PDQM Report** (`generali_pdqm` over `dbo.PDQMReport`) and
**Workitems (Octopus)** (`workitems` over `dbo.t_Documents`). A third,
**Backlog History** (`backlog_history` over `StatisticsDB.dbo.BacklogHistory`
with a `backlog_total` metric, migrations `0053`–`0056`/`0065`/`0066`/`0068`),
was **retired by migration `0069`**: the date-anchored **Backlog** measure on
the docprocessing source (see **`DateAnchor`** below) supersedes it, and the
collector + table it read stay in place. Each source is gated by its own
permission (`reporting.source.generali.pdqm`, `reporting.source.workitems`).
Unlike the docprocessing source, the `table` provider does **not** apply
`reporting.scope.process.*` row scoping — the source permission is the whole
gate, so grant it deliberately. Tune the exposed columns/object at
`/reporting/sources`.

**Registering a generic source needs no code:** add a `ReportingSources` row with
`Kind=curated`, `Provider=table`, an `Engine`, a `BaseObject`, the `ColumnsJSON`
catalog, and a `Permission` — then grant that permission. A `Kind=sql` row adds a
SQL-sandbox source over an existing target. Use the code path below only when a
source needs bespoke query logic the `table` provider can't express.

## Source visualizer (`reporting.sources.schema`)

Clicking a Sources rail card opens a slide-over showing the **database behind
that source** — a filterable table list and an ER diagram. Structure only: no
row of data is ever returned.

**Route.** `GET /api/reporting/sources/<source_id>/schema` →
`{db, label, source, tables[], relations[], truncated, filter, hidden}`.

- `tables[]`: `{schema, name, kind: table|view, rows, columns[{name, type,
  nullable, pk, fk?}]}`, sorted by row count desc. `rows` is the
  `sys.partitions` approximation (no `VIEW DATABASE STATE` needed); views get
  `null`. `fk` is `{table, column}` on the child column.
- `relations[]`: `{name, from, to, fromColumns[], toColumns[], kind}` —
  `kind: "fk"` is a foreign key (multi-column keys grouped into one edge),
  `kind: "view"` is a view→table dependency from
  `sys.sql_expression_dependencies` (no columns; drawn dashed).
- `filter` / `hidden`: which narrowing rule ran and how many tables it dropped
  (see **Only what the source reads** below).
- `truncated`: how many tables the 400-object cap dropped (`0` normally).
  Edges pointing outside the cap are dropped with them, so the diagram never
  references a table that isn't there.

**Only what the source reads.** The full database is not what anyone came to
see — `filter_used()` narrows the payload to the tables the reporting layer
actually queries, and reports the drop count rather than hiding it:

1. **Seed** — the source's `BaseObject` plus every `dbo.ProcessSources.TableName`
   (migration 0074), matched on the *bare* object name because the registries
   qualify them inconsistently (`dbo.PriveraInvoice`, `public."DossierStatistik"`).
   Names belonging to another database simply match nothing.
2. **Expand** — transitively, whatever a seeded **view** reads (a view's tables
   are as used as the view), then **one hop** across foreign keys, so a used
   table arrives with the lookups it joins to instead of as a lonely box.
3. **Fall back** — a seed that matches nothing in this database (a source whose
   SQL is hand-written) drops tables holding zero rows instead. `filter` says
   which rule ran: `used` or `nonempty`.

Today that turns SYDOC_Statistik's 53 objects into the 5 statistik tables the
registry names plus the 5 field-statistic views over them, and RuntimeDatabase's
31 into `t_Documents` + its two FK neighbours.

**Two gates, not one.** The route carries `@require_permission(
"reporting.sources.schema")` *and* re-checks that `source_id` is in the
caller's `accessible()` set (403 otherwise). The grant therefore widens what
you see *of* a database you already read — it never adds a database.

**Engine reuse.** The same engine the source itself queries
(`_SQL_TARGET_ENGINES` for `kind=sql`, `_CURATED_ENGINES` otherwise), so no new
credential and no new connection string. An unconfigured engine is a 503, a
failed catalog read a 502 — never a 500.

**Introspection** lives in `nx_lib/reporting/db_schema.py` (`introspect(conn)`,
connection injected → unit-testable, `tests/unit/test_reporting_db_schema.py`).
Three `sys.*` catalog queries: objects+columns with the PK flag, row counts,
foreign keys. SQL Server only — every engine behind a reporting source is SQL
Server today; a Postgres source (MS02) would need a dialect branch here.

**Front end**: `static/js/reporting_schema.js` + the string shim
`templates/js/_reporting_schema_js.html`, markup in `reporting.html` behind the
same permission check (no grant → no markup, no script, and the rail cards stay
plain `<div>`s). The diagram is hand-rolled SVG, no graph library: nodes are
laid out by a BFS per connected component (depth → column), which tolerates
cycles and keeps parents beside children; a database with **no** foreign keys
grids its biggest tables instead of stacking them in one column. Pan is a
pointer drag, zoom is the wheel, **Fit** re-frames. Caps: 60 nodes (by degree),
8 columns per box — both reported in the diagram's note rather than silently
applied.

## Metrics registry (semantic layer, admin)

A **metric** is a named, blessed server-side aggregation (an `Aggregation` over a
`BaseField`) bound to a registered source, so the builder and the AI assistant
produce the **same numbers** for the same business question. Metrics live in
`dbo.ReportingMetrics` (migration `0017`) and are curated at **`/reporting/metrics`**
by admins holding `reporting.semantic.admin`.

Each metric has a `Code` (`^[A-Za-z_][A-Za-z0-9_]*$`, referenced from a
definition's `metrics` list), a `SourceId` (which source it aggregates), a
`Label`, an `Aggregation` (`count`, `count_distinct`, `sum`, `avg`, `min`,
`max`), and a `BaseField` (a whitelisted column of that source — required for
every aggregation except `count`). `Format` (`int`/`decimal`/`percent`) is a
display hint; `Enabled` and `SortOrder` control visibility/ordering. Labels are
DB-driven i18n: `Label` (English) plus nullable `GermanLabel`/`FrenchLabel`/
`ItalianLabel` (migration `0039`; NULL falls back to `Label`, the same
NULL-falls-back-to-English convention `dbo.FieldLabels` uses in
`nx_lib/mapping_config.py`'s registry) — `/api/reporting/measures` serves the session
locale's label, while the AI catalogs deliberately keep the English `Label` for
prompt-grounding stability. Migration `0017` seeds a worked example, `doc_count`
(a `count` over the docprocessing source); migration `0039` adds **`page_count`**
("Pages processed", `SUM` over `pagecount`, `SortOrder` 30). For `sum`/`avg`
metrics the docprocessing query builder projects the base field as
`TRY_CAST(<col> AS float)` per UNION-ALL subquery — the stat columns are
varchar, so non-numeric cells become NULL and drop out of the aggregate instead
of erroring; only processes with the mapped `col_*` contribute.

In the builder, the **Metrics well** (top of the wells column) lets a user add
canonical metrics for the selected source; once at least one is picked, the
**Columns** above become the grouping. Selected metrics travel in the definition
as `metrics: [{ "metric": code }]` (see the JSON above) and the AI assistant is
told about the accessible metrics so Surfaces A/C can reference them by code.

**Zero-dimension grand totals:** a definition with a non-empty `metrics` list
may have **zero columns** — both query builders then emit a global aggregate
`SELECT AGG(...)` with **no GROUP BY**, returning a single total row (the
docprocessing union projects a constant `1 AS [_one]` per subquery when the
metric set is count-only so the SELECT list is never empty). This powers the
Simple tab's number card and works identically in Advanced and the AI surfaces.

**`TotalMode`** (`sum` default / `latest`, migration `0056`, `table`-provider
sources only) governs how aggregates over a metric backed by a
**point-in-time snapshot series** are computed — the seeded case was
`backlog_total` on the since-retired `backlog_history` source
(`dbo.BacklogHistory`, 30-minute backlog snapshots; retired `0069`, the
machinery stays for future snapshot sources): summing snapshots across time
is meaningless for a gauge. When a request's metrics are **all** `TotalMode = 'latest'` and
the source has **exactly one** grainable date field, `_prepare_run` passes
that field as `latest_of` into `build_generic_query`, which restricts the
row set before aggregating:

- **no date dimension** (zero-column grand total, or a category-only
  breakdown like "Backlog by process"): only rows at the **newest snapshot
  instant** in the filtered range count;
- **grained date dimension** ("Backlog per day/week/month"): only rows at
  the newest snapshot instant **within each bucket** count, so a day bucket
  shows the day's closing backlog, not the sum of its 30-minute snapshots
  (all rows of one collector run share one `SnapshotAt`, which is what makes
  the per-bucket `MAX` restriction exact);
- a **raw** (ungrained) date dimension needs no restriction — every snapshot
  instant is its own group.

Any mixed `sum`/`latest` metric set, or more than one date candidate, falls
back to the safe default (`sum` over everything) rather than guessing which
metric should win. Relatedly, the generic builder truncates a `day`-grained
`datetime` dimension via `CAST(... AS date)` (an untruncated day grain would
bucket per timestamp), and both builders exclude SQL Server's `1900-01-01`
zero-date sentinel from grained date dimensions (NULL buckets stay — "no
date yet" is a real group). The Simple KPI band's "· last bucket" caption on
the Total tile remains a separate, client-computed number — see **Simple and
Advanced tabs → KPI stat band** above.

**`DateAnchor`** (migration `0067`, docprocessing only) marks a metric as
**date-anchored**: *Documents/Pages imported* count on the import date,
*Documents/Pages exported* on the export date, and *Backlog* reads
`dbo.BacklogHistory` (same Statistics engine). Anchored metrics plot on the
shared synthetic **`activity_date`** axis — each metric buckets its OWN date
onto it — which is what makes "import line + export line + backlog line in
one chart" a single-SQL report. Mechanics (`query.py:_build_anchored_query`):
one UNION-ALL leg per (process, used date anchor) plus one BacklogHistory
leg, each projecting the axis and one **counter column per metric** (1 / the
value column / `BacklogCount` on the matching-anchor leg, `0` elsewhere);
the outer query GROUPs BY the dims and SUMs the counters
(`resolve_metrics` aliases an anchored metric's `base_field` to its own
code; the registry `BaseField`, e.g. `pagecount`, becomes `value_field`).
The backlog leg concatenates `LOWER(ClientName)+'.'+ProcessName` so its
process vocabulary matches the docprocessing `client.process` constants, is
restricted to the report's effective process scope, and keeps only the
newest snapshot instant per bucket. Rules, enforced with teaching errors in
`_prepare_run`: anchored and unanchored metrics never mix; anchored reports
use `activity_date` (never `import_date`/`export_date`) for both columns and
filters; `activity_date` is invalid without anchored metrics. Like
`TotalMode`, `DateAnchor` is migration-managed (not writable via the admin
metrics API). v1 limits: drill-through is unavailable on anchored results
(the axis is not a physical column), and buckets without a backlog snapshot
render as 0.

> Per-metric locked filters (`FilterJson`) are stored in the table but **not yet
> applied** by the engine in Slice 1 (reserved for a later slice). Report-level
> `filters` still apply pre-aggregation.

## How to add a new *bespoke* curated source (code)

1. **Register the source** in `nx_lib/reporting/sources.py`:

   ```python
   _SOURCES = {
       "docprocessing": { ... },          # existing
       "mynewthing": {
           "id": "mynewthing",
           "kind": "curated",
           "label": "My New Thing",
           "permission": "reporting.source.mynewthing",
           "engine": "statistics",        # or another engine key
       },
   }
   ```

2. **Implement the catalog fetch** in `nx_lib/reporting/catalog.py` (a
   function analogous to `fetch_docprocessing_catalog`). The catalog must
   return a list of field dicts: `{field, label, type, filterable, aggregable,
   sortable}` — only fields in this list can be referenced in a report
   definition.

3. **Implement the query builder** in `nx_lib/reporting/query.py` (or extend
   `build_table_query` to handle the new source). Column names must come from
   `nx_lib/mapping_config.py`'s registry (`dbo.ProcessFieldMappings`), never
   from user input.

4. **Wire the catalog + query into the view** (`nx_lib/views/reporting/run.py`).
   The `/api/reporting/sources` endpoint returns the catalog for each source
   the caller has access to; add a branch for the new source id.

5. **Add the permission code** via a migration in
   `sql/_migrations/NexoraDB/NNNN_add_reporting_source_mynewthing.sql`:

   ```sql
   IF NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'reporting.source.mynewthing')
       INSERT INTO dbo.Permission (Code, Description)
       VALUES ('reporting.source.mynewthing', 'Reporting: use the My New Thing source');
   GO
   ```

6. **Mapping-registry coverage** for curated sources: `nx_lib/mapping_config.py`'s
   registry (`dbo.ProcessFieldMappings`, migration `0074`) is what defines the
   field set — each process needs a row mapping a `FieldKey` to the actual data
   column name in that process's statistics table. Labels come from
   `dbo.FieldLabels`. `dbo.FieldMetadata` (data type,
   sortable/aggregable flags) is *optional* enrichment that
   `nx_lib/reporting/catalog.py` merges in when present — it exists on no
   environment today, so every field falls back to
   `type=string, aggregable=False, sortable=True`.

## Scheduled & emailed reports

A saved report you own can be delivered on a schedule (permission
`reporting.schedule`). The **Scheduled** screen (Console left nav,
`templates/js/_reporting_scheduled_js.html`) lists every schedule the caller
owns across all reports — **`GET /api/reporting/schedules`** joins
`dbo.ReportSchedules` with the report names — with an instant on/off toggle
(a full-field `PUT` with `enabled` flipped; off rows dim to 55%), per-row
delete, and a **New schedule** modal (report picker over the owned reports +
the same cadence/format/recipients fields). The Advanced builder's per-report
**Schedule** dialog still exists and manages the same rows. Fields:
**frequency** (daily / weekly / monthly), **time** (UTC), **format** (xlsx/csv),
and **recipients**. Schedules live in `dbo.ReportSchedules` (migration `0012`,
FK to `Reports` `ON DELETE CASCADE`); per-report endpoints are under
`/api/reporting/reports/<id>/schedules` (owner-only).

### Alert-only schedules

A schedule can carry an **alert condition** so it only mails when a threshold is
tripped. The **Send** select in the Schedule dialog offers:

- **Always** (default) — every run mails the report regardless of the result.
- **Only when the total is above / at least / below / at most \<N\>** — the runner
  does a zero-column re-run first (the same grand-total the Simple stat card
  shows — correct for `avg`/`count_distinct`), then compares it against the
  threshold. For plain-table and SQL reports that have no metrics, the threshold
  compares against the **row count** instead. If the condition is not met, the run
  sends nothing but still advances `LastRunAt`/`NextRunAt` so the schedule does
  not re-fire on the next tick. The alert condition is stored in the new
  `AlertOp` and `AlertThreshold` columns (migration `0022`).

Schedules can also be **enabled or disabled** directly from the schedule list in
the modal (the toggle next to each row). Any PUT to a schedule (including the
enable/disable toggle) recomputes `NextRunAt` from the current time.

Delivery is **not** in-process. `ops/run_scheduled_reports.py` (which ships to
the server because `ops/` is deployed) finds due rows
(`Enabled = 1 AND NextRunAt <= now`), runs each report **as its owner** —
`nx_lib/reporting/runner.py` loads the owner's permissions
(`spGetUserPermissions`) and process scope, then reuses the same builders as the
web path — renders the file, emails it via Microsoft Graph (`nx_lib/mail.py`,
ROPC + `/me/sendMail`), and advances `NextRunAt` (`compute_next_run`).

For reports with **breakdowns**, the runner server-renders a chart using
**matplotlib** (Agg backend, no display required) and embeds it in two places:
inline in the HTML mail body (as a `cid:` image) and above the data table in
the attached XLSX. Chart rendering failures degrade gracefully — the mail is
still sent and the XLSX still contains the full data, just without the chart image.

Wire it with Windows Task Scheduler (e.g. every 15 minutes):

```
set ENVIRONMENT=PROD
D:\sydoc\tools\py\python.exe D:\sydoc\nexora\ops\run_scheduled_reports.py --once
```

`--dry-run` builds each due report and logs what *would* be sent without mailing
or advancing `NextRunAt` — useful for a first smoke test. Graph mail uses the
existing `GRAPH_*` credentials (the same ones the password-reset mail uses); if
Graph is unconfigured the runner logs the failure per-schedule and continues.

## AI assistant

The AI surface is a single chat panel — branded **Eddard** in the UI (issue
 #212) — shared by both the Simple and Advanced tabs, talking to the agentic
drafter (`POST /api/reporting/ai/agent`).
The earlier per-mode UI (an "Ask AI" tab with **Build a report** / **Write SQL** /
**Agent** sub-modes, plus a Simple-tab **Refine** bar) is retired — see
**AI chat panel** below for what replaced it, and **Legacy single-shot endpoints**
for what's left of the old surfaces server-side.

### Eddard, the mascot

Every AI surface carries **Eddard**: an animated version of the Nexora
black-hole logo (black core, accent accretion ring, two dot eyes) that floats,
blinks, looks around, winks and hops. Files:

- `templates/_eddard.html` — two macros: `mark(size, state)` renders the SVG
  mascot, `stage()` renders the "builds a report" loading stage.
- `static/css/eddard.css` — geometry-independent styling + every keyframe. The
  accent follows `--nx-accent`, so the mascot re-tints with the user's accent
  picker; the core stays black in both themes (same rule as `.bh-core`).
- `templates/js/_eddard_js.html` — one shared timer walking the idle mood
  sequence, plus `window.NexoraEddard.startBuild/stopBuild(stage)` for the
  build loop (0→5, 1300 ms per step, wraps).

Placements: the top-bar toggle (22px), the chat panel header (24px), the empty
thread (88px) and the AI-insight card head on Simple (20px). The three inline
marks pass `cls='ed--calm'`: they only breathe (a 2px `edBreathe`) and blink,
because a mark sitting in a text row must not shove its label around — the
mood loop skips `.ed--calm` entirely, so the hops and eye darting stay on the
big empty-thread mascot. That big mark also opts into `ed--track` (eyes follow
the pointer, rAF-throttled; the mood loop yields the eye vars while the
pointer is fresh) and `sparks=true` (the handoff's three drifting ambient
dots). Hovering a calm mark's parent perks him up (1px lift, wide eyes).

While a turn runs, the progress ticker gets the `stage()` macro, which flings
a report together (title → KPI → bars → trend → Ready badge) beside the real
agent steps, with per-piece choreography: a one-shot `edThrow` fling and card
settle as each piece lands, an orbiting spark while working, and the handoff's
celebrate pose on Ready. The stage starts with placeholder copy but becomes a
**live preview of the actual answer**: `ask_agentic_iter` yields a
`tool_result` event after every tool call (key `output`, never `result` — that
key terminates every consumer's loop), the view distills it through
`stage_preview()` (`nx_lib/reporting/ai.py`; title from `build_definition`,
total + series from `run_definition`/`run_sql` rows — first numeric cell per
row, capped to the last 12) into a `{"phase": "preview"}` NDJSON line, and
`NexoraEddard.setPreview()` swaps the mock report's title, compact-formatted
total (the canned +8.3% delta hides next to real data), bar heights and trend
line for the real numbers. Raw tool output never reaches the client from a
progress line. Everything is `aria-hidden` (decorative; the visible
status text carries the meaning) and `prefers-reduced-motion` holds each loop
on its resting frame. Source of truth for geometry, mood table and timings:
`docs/design/design_handoff_eddard_mascot/README.md`.

### AI chat panel

**Toggle:** an **"Eddard"** button (`#rpChatToggle`, mascot mark) is the
masthead's action, on both tabs, whenever `reporting.ai.use` is held
(`ai_enabled`). (**Sources** is not next to it — it sits at the right end of the
Simple/Advanced tab rail below, see *Page layout*.) Clicking it — or, on Simple, typing into the landing hero's
**Ask Eddard** bar or clicking one of its suggestion chips — opens a docked
right-side slide-over (`#rpChatPanel`) with an empty state offering three
example questions. It closes any open drill-through drawer first (the two
panels share the same slide-over real estate) and closes on **×**, clicking the
backdrop, or **Escape**.

**Conversation & history.** Every question is sent with the running
conversation as `history`: an array of `{role: "user"|"assistant", content}`
pairs, one entry per prior turn (the current question is sent separately as
`question`, never folded into `history`). The client keeps the whole session's
history in memory; the server (`nx_lib/views/reporting/ai.py: api_ai_agent`)
**caps what it actually uses** to the **last 8 entries**, then trims further
from the front until the total character count of the kept entries is at most
**12000** — so a long-running chat degrades to "recent context only" rather
than growing the prompt without bound. History is **text-only** (`role`/
`content` strings — anything else is dropped) and never carries schema/
grounding text; that stays attached to the current turn's `question` only, so
it isn't repeated once per history entry. Each **assistant** turn the client
records also appends its own produced artifact — `\n[sql from this
answer]\n<sql, first 1500 chars>` and/or `\n[report definition from this
answer]\n<definition JSON, first 1200 chars>` — so a presentation-only
follow-up ("show it as a chart", "break that down by process") can be
answered by re-shaping the **same** query/definition instead of the model
re-deriving it (or silently switching source) from the English answer alone;
see `docs/design/reporting-ai-assistant.md` for the full mechanism and why
the cap went from 4000 to 12000 to fit these artifacts.

While a request is in flight, a **live build-step list** narrates what the
agent is actually doing turn by turn (a title line — "Asking the AI…", the
model's own preamble when it wrote one, or "Thinking… (N)" on later turns —
plus a growing list of steps such as "Building the report…", "Checking the
query…", "Running the query…", "Crunching the numbers…", one per tool call,
the previous one flipping to done as the next starts). See **Agent endpoint
contract → Live progress** below for the underlying NDJSON stream this
renders; `docs/design/reporting-ai-assistant.md` documents the exact
phase-to-label mapping. Each reply renders as:

- The **answer** text.
- A collapsed **"How the agent worked"** `<details>` — one line per tool call,
  an ok/error chip, and a row count where applicable.
- Action chips, shown only when the reply actually produced the artifact:
  **Open report** (only if the reply carries a `definition` — switches to the
  Simple tab and opens it straight into the result view via
  `window.ReportingSimple.openDefinition()` (#178 A4), which runs it through
  the normal `/api/reporting/run` path, so row-scoping and the field
  whitelist still apply; falls back to the Advanced builder's
  `applyDefinition()` **followed by `run()`** if the Simple seam isn't
  loaded — the fallback used to stop at `applyDefinition()`, leaving
  Advanced showing no results until Run was pressed by hand, fixed
  alongside the equivalent Simple-side bug, #178 Task 15), **Insert into SQL
  editor** / **Show query**
  (only if the reply carries `sql`, which in turn only happens when the caller
  holds `reporting.ai.sql` — see **Access** below).
- Three canned **follow-up** suggestion chips ("Only this quarter", "Break down
  by process", "Show it as a chart") that, when clicked, send that exact text as
  the next turn.

**Access:** `reporting.ai.use` to see the toggle/panel at all. Whether a turn
*can* return SQL depends on `reporting.ai.sql` (gates the agent's `validate_sql`
tool — without it, no SQL is ever drafted, so the SQL-related chips never
appear). Whether a turn can narrate **real numbers** from a live query depends
on `reporting.ai.explain_data` **and** `reporting.sql.run` together — see
**Agent endpoint contract** below.

### Auto captions

Route: `POST /api/reporting/ai/caption` — accepts
`{"columns": [...], "rows": [...], "title": "...", "dateLabel": "...", "notes": "...", "levelFields": [...]}`
and returns `{"caption": "..."}`.

The **trigger point differs per tab**: the Simple tab fires this after
**every** successful run render that actually has rows — an empty (zero-row)
result returns before reaching the caption call, so no request goes out and
no caption box appears; the Advanced tab fires it only on **chart mount**
(switching to the Chart view) — not on every grid run — so re-running a
report while sitting in Grid view does not itself request a new caption
(see `resetViews()`/`fireCaption()` in `_reporting_js.html` vs. the end of
`runCurrent()` in `reporting_simple.js`). Either way, the request goes
out in the background with the columns and the **whole grid** just rendered
(payload-capped at `CAPTION_MAX_ROWS` = 5000 rows), and — if it returns a
caption — the result view shows a small "shimmer in" 1–2 sentence narration
under the chart/KPI band, prefixed with an **AI** chip.

**The model never sees the rows.** `caption()` reduces the grid to an exact
**fact sheet** (`nx_lib/reporting/caption_facts.py::build_facts`): total (or,
for a level measure such as the backlog, the *latest* value — the client
names those in `levelFields`), buckets with a value vs. buckets with **no
measurement** (never read as zero), peak/low, latest vs. previous, first-half
vs. second-half average, the recent tail and an evenly spaced sample across
the range, top categories with shares, the NULL-key rows reported separately
as "rows with no `<dimension>`" (never a period, never an outlier), and the
still-running current bucket flagged and kept out of peak/latest/averages.
The prompt carries those facts plus the client's `notes` (partial bucket,
NULL = no snapshot). Before this, the route sliced `rows[:50]` off the top of
an ascending time series, so the model judged 313 weeks from the NULL-date
bucket plus 2020 — "a clear outlier of 74,182 pages", "at most 3,712 in the
latest weeks" (2026-08-25 audit). Unlike the chat panel's schema-only default, this endpoint's whole
purpose is to send the rows already on screen to the model, so it is gated by
`reporting.ai.explain_data` **alone** — deliberately **not** also requiring
`reporting.sql.run` (there's no live query involved; the rows already left the
database through the ordinary, already-scoped `/api/reporting/run` call, this
just narrates them). This makes `reporting.ai.explain_data` control two
distinct things with two distinct blast radii: captions (any accessible
result's rows, no live SQL) and the chat agent's `run_sql`/`compute_stats`
tools (arbitrary read-only queries the model itself writes, which additionally
needs `reporting.sql.run`).

The caption call is entirely **silent-fail**: a network error, a `503`
(unconfigured), a `429` (daily cap hit), or any other failure just hides the
caption box — it never surfaces an error to the user, since a missing caption
is not a broken report. It still counts toward the shared per-user/day AI cap
and is rate-limited (10/min) like the other AI routes, and is audited to
`dbo.ReportingAiAudit` with `Surface='caption'`.

### Comparison / delta chips

Not an AI feature — see **Comparison & delta chips** above (`compare` request
flag, `comparison` response block, delta-chip semantics). It's documented
separately from this section because no model call is involved.

### Agent endpoint contract

Route: `POST /api/reporting/ai/agent` — accepts
`{"question": "...", "history": [...], "source": "<sourceId>|null", "stream": bool, "continueAttempt": int}`
and returns
`{"answer", "definition", "sql", "toolTrace", "turns", "stoppedReason", "explainData", "continueAttempt", "canContinue"}`.
This runs a **Tier-2 agentic tool-loop** (`nx_lib/reporting/ai.py: ask_agentic`):
the model calls tools, sees their results, and **self-repairs** until it has a
validated artifact or hits a hard turn cap.

**Continue past a dead-end (#153).** When the loop stops on `"max_turns"` or
`"budget"` without a final answer, `canContinue` is `true` (while
`continueAttempt < MAX_CONTINUE_ATTEMPTS`) and the chat panel renders a
**Continue** chip. Clicking it re-sends the exact same question with
`continueAttempt` incremented — not a mid-loop resume (the tool-call
transcript isn't persisted), just a fresh run with the turn/budget caps
doubled (`CONTINUE_MAX_TURNS` / `CONTINUE_BUDGET_S` in `nx_lib/reporting/ai.py`).
`continueAttempt` is capped server-side at `MAX_CONTINUE_ATTEMPTS` (2) and
clamped rather than rejected, so a stale/tampered client value can't grant
more than the ceiling.

**Live progress (`"stream": true`).** A loop turn can take a minute on a
reasoning model, so the chat panel asks the server to narrate it. With the flag
the response is **NDJSON** (`application/x-ndjson`), one object per line:

```
{"phase": "thinking", "turn": 1}
{"phase": "note", "text": "Let me check the schema."}
{"phase": "tool", "name": "run_sql"}
{"done": true, "answer": "...", "definition": {...}, "sql": "...", "toolTrace": [...], ...}
```

`phase` events come straight out of the loop (`ask_agentic_iter`, the generator
`ask_agentic` drains) — `thinking` before each provider round-trip, `note` for
the model's own preamble on a tool turn, `tool` before each tool call. Exactly
one `done` line closes the stream, carrying the same payload the plain-JSON mode
returns. **Headers are already sent by then**, so a mid-stream failure arrives as
`{"done": true, "error": "..."}` on that last line rather than a 502 — a client
must treat a stream that ends *without* a `done` line as a failure too. Without
the flag (or from any other caller) the route answers plain JSON exactly as
before. The chat panel picks its reader off the response `Content-Type`, so
stubbed tests that answer `application/json` keep working unchanged.

**Tool binding follows permissions:** `build_definition` is always bound
(data-free — the same whitelist validator `/api/reporting/run` uses).
`validate_sql` (data-free — a gate check only) is bound only with
`reporting.ai.sql`. `run_sql` / `run_definition` / `compute_stats`
(`nx_lib/reporting/stats.py`) — which feed real result rows back to the model —
are bound **only** when the caller holds **both** `reporting.ai.explain_data`
**and** `reporting.sql.run`; otherwise the loop stays fully schema-only
(question + source catalog + SQL schema in, ok/error-only tool results out,
never a result row). `run_definition` takes the same v1-definition shape as
`build_definition` but actually executes it (`nx_lib.reporting.runner.execute_definition`
— the same path the scheduled-report runner uses) and returns the real rows,
capped to `RUN_DEFINITION_ROW_CAP` (500); it exists so an anchored-metrics or
other business-definition question ends with real numbers instead of a
validated-but-unexecuted definition ("definition built, numbers not run").

The grounding prepends today's date (so relative time expressions resolve to
real dates, not training-data dates) and includes the `source` the client's
builder currently has selected as a hint only — not a gate; a builder-only
curated source (e.g. Generali) is marked as such so the model steers `run_sql`
to a real read-only target instead. Process-name matching (case-insensitive,
against both id and humanized label) and "different X" → `columns + count
metric` GROUP BY guidance apply the same way they did for the old Surface A/C
prompts. `AI_DAILY_LIMIT` applies before any provider call; audited with
`Surface='agent'` (`Status='misconfig'` if the provider is broken, `'blocked'`
when the cap is hit). The last validated definition/SQL anywhere in the tool
trace is what the chat panel's **Open report** / **Insert SQL** chips act
on.

Tool and SQL-sandbox errors surfaced to the model (and to the visible tool-step
trace) go through `humanize_sql_error`, which strips ODBC driver noise
(`[Microsoft][ODBC Driver 17 for SQL Server]…`-style prefixes) and adds a
teaching hint for SQL Server error 1033 (`ORDER BY` used inside a derived
table/subquery without `TOP`/`OFFSET`) so the model — and a human reading the
trace — sees the actual fix instead of a raw driver message. The system prompt
also forbids resubmitting SQL that just failed unchanged, pushing the model to
actually address the error on the next tool call.

> **Data egress (opt-in).** When the caller holds `reporting.ai.explain_data`
> **and** `reporting.sql.run`, the loop binds `run_sql`/`compute_stats` so the
> model runs validated read-only SELECTs and **narrates the actual numbers** —
> a deliberate **data-egress** path (result rows reach the model). Seeded to
> admins by migration `0015`; grantable per-user; **off by default** (then the
> loop stays schema-only). The response/audit carry an `explainData` flag.
> Glossary RAG (a separately planned accuracy improvement) is not built —
> needs a curation owner.

### Legacy single-shot endpoints (not reachable from any UI)

`POST /api/reporting/ai/build` (single-draft "build a report", `reporting.ai.use`,
optionally with `priorQuestion`/`priorDefinition` refine context, audited
`Surface='definition'`) and `POST /api/reporting/ai/ask` (single-draft "write
SQL", requires `reporting.ai.sql` in addition to `reporting.ai.use`,
`{"question"}` → `{"sql", "explanation", "valid", "target", "model"}`, audited
`Surface='sql'`) still exist as routes — unchanged, still permission-gated,
still audited — but no template or JS file calls either of them any more; the
chat panel's agent endpoint is the only UI path today. They're documented here
only so the routes aren't a mystery if you go looking for their caller and
don't find one.

### Configuration (`AI_*` env vars)

Set these in `env/INT.env` and `env/PROD.env`:

| Var | Purpose |
|-----|---------|
| `AI_PROVIDER` | `anthropic`, `azure`, or `none`. Route returns 503 until set to a real provider. |
| `AI_MODEL` | Model name (defaults to `claude-sonnet-4-6` for Anthropic; for Azure the deployment name is used instead, via `AZURE_OPENAI_DEPLOYMENT`). |
| `ANTHROPIC_API_KEY` | Anthropic API key (required when `AI_PROVIDER=anthropic`). |
| `ANTHROPIC_API_URL` | Override the Anthropic endpoint (optional; defaults to `https://api.anthropic.com/v1/messages`). |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI resource endpoint (required when `AI_PROVIDER=azure`). |
| `AZURE_OPENAI_KEY` | Azure OpenAI API key (required when `AI_PROVIDER=azure`). |
| `AZURE_OPENAI_DEPLOYMENT` | Deployment name (required when `AI_PROVIDER=azure`). |
| `AZURE_OPENAI_API_VERSION` | API version (optional; defaults to `2024-10-21`). GPT-5-family deployments need a newer one, e.g. `2025-01-01-preview`. |
| `AI_DAILY_LIMIT` | Per-user/day cap on AI asks (cost/abuse control). `0` (default) = unlimited. When the cap is hit the route returns **429** before any provider call, and the throttle is recorded in `dbo.ReportingAiAudit` with `Status='blocked'`. |
| `AI_TIMEOUT_S` | HTTP read timeout for a single model round-trip (default `120`). Reasoning deployments (GPT-5 family) regularly spend 30–60 s on one hard question; too tight a value surfaces as *"Eddard could not answer right now"* (502) with a `Read timed out` line in `var/logs/system/app.log`. |
| `AI_AGENT_BUDGET_S` | Wall-clock ceiling for a whole agentic (chat) run (default `180`). Checked between turns, so a slow model can't hold a worker for `max_turns × AI_TIMEOUT_S`; a run that hits it returns what it has with `stoppedReason: "budget"`. |

Until `AI_PROVIDER` is set (or is `none`) the route returns **503** and the tab
does not render. Sanitised key names are committed in `env/*.env.example`.

**Reasoning effort (Azure GPT-5 family).** Reasoning deployments run at the API
default (`medium`) unless told otherwise, which is far more deliberation than a
one-line chart caption needs — on INT that cost 8 s per caption and 55 s per
agent run against gpt-4o-mini's 0.9 s / 7.7 s. `nx_lib/reporting/ai.py` therefore
sends `reasoning_effort` per surface: `low` for the single-shot surfaces
(caption, definition, sql) and `medium` for the agentic chat loop, which chains
tool calls and earns the extra thinking. There is no env var — the levels are
`EFFORT_SINGLE_SHOT` / `EFFORT_AGENT` in that module. The parameter is sent only
when `AZURE_OPENAI_DEPLOYMENT` starts with a known reasoning prefix (`gpt-5`,
`o1`, `o3`, `o4`), because every other Azure model rejects it with a 400; a
deployment named off-pattern silently keeps the API default.

The agent surface also lets the **user** pick. The chat composer is one
rounded container (`.rp-composer`) holding the textarea over a control bar;
the depth picker is a trigger pill (`#rpChatEffortBtn`) that opens a popover
(`#rpChatEffortMenu`) at bottom-left, with the send button at bottom-right —
the shape a model picker takes. Markup in `templates/reporting.html`,
behaviour in `templates/js/_reporting_ai_js.html`, styles `.rp-composer` /
`.rp-effort*` in `static/css/reporting.css`. Each level carries a three-bar
meter (`data-bars`) rather than a glyph, because the choice is a scale.
Quick / Balanced / Deep map to `low` / `medium` / `high` and ride along as
`effort` in the `/api/reporting/ai/agent` body; an unknown level falls back
to `EFFORT_AGENT` rather than 400.

The control is capability-gated by `supports_effort(provider, model)`: the
page passes `ai_effort_enabled` and the markup is simply absent when the
configured model cannot honour a level. Anthropic spells the same knob
`output_config.effort` and accepts it only on the Opus / Sonnet-5 / Fable
class — **Claude Haiku 4.5 rejects it**, which is why the picker has to
disappear rather than grey out. `_effort_body()` drops the field a second
time server-side, so a stale client cannot 400 a question.

The pick lives for the life of the panel and resets to Balanced on reload;
persisting it would mean an `aieffort` key in `UI_PREF_CHOICES`
(`nx_lib/ui_prefs.py`).

### Safety & privacy

- **Schema-only egress:** the model receives the user's question and schema
  metadata (table/column names and types) only — never result rows or user data.
  This is enforced in `nx_lib/reporting/ai_schema.py` (the bounded serializer
  strips everything beyond name/type/description).
- **sqlglot gate:** every AI-drafted query is validated by `sqlglot` (same gate
  as the SQL sandbox) before it is returned to the client. A draft that fails
  the read-only check is still shown to the user but flagged with a warning;
  it is never auto-inserted silently.
- **No unmediated execution path:** the chat panel itself never runs anything —
  **Insert into SQL editor** only stages a draft for the user to review and run
  via the existing gated `POST /api/reporting/sql/run` path (same read-only
  login, row cap, timeout, audit trail); **Open report** only stages a
  definition for a normal, whitelisted `/api/reporting/run` call. The one path
  where the model itself triggers a read against real data is the opt-in
  `run_sql`/`compute_stats` tool binding (`reporting.ai.explain_data` +
  `reporting.sql.run`), which still goes through the same sqlglot gate and RO
  login as everything else.
- **Audit:** every AI interaction (question, model, provider, gate verdict,
  token counts, duration, status) is written to `dbo.ReportingAiAudit`
  (migration `0013_create_reporting_ai_audit.sql`), including chat turns
  (`Surface='agent'`) and captions (`Surface='caption'`).
- **Cost/abuse control:** `flask_limiter` caps every AI route at 10/min/user,
  and the optional `AI_DAILY_LIMIT` enforces a per-user/day ceiling that is
  checked *before* any provider call (a throttled ask costs no tokens) and
  audited with `Status='blocked'`.

### Implementation

- `nx_lib/reporting/ai.py` — provider-agnostic client (Anthropic + Azure
  OpenAI); HTTP transport is injectable for tests; `ai_caption` drafts the
  1–2 sentence result narration.
- `nx_lib/reporting/ai_schema.py` — bounded schema serializer.
- `nx_lib/reporting/tokens.py` — `shifted_definition_for_comparison` (the
  comparison-window shift; not AI, just lives next to the other date-token
  helpers).
- `templates/reporting.html` — chat panel markup (`#rpChatPanel` and friends).
- `templates/js/_reporting_ai_js.html` — the chat module (`window.ReportingChat`).
- `static/js/reporting_simple.js` — Simple's hero-bar shortcut into
  the chat panel, the KPI delta chips/sparkline, and the auto-caption fetch.
- `templates/js/_reporting_js.html` — the Advanced grid's own auto-caption
  fetch (no delta chips/comparison there — Simple-tab only, see
  **Comparison & delta chips**).
- `static/css/reporting.css` — `.reporting-chat-*` panel styles, `.rp-delta*`
  chip styles, `.rp-caption*` styles.

See `docs/design/reporting-ai-assistant.md` for the full design spec.

## Live SQL sandbox

The **SQL** tab in the report builder is a power-user escape hatch for when the
curated builder does not cover your query. It runs a single read-only `SELECT`
against a chosen target database. The **Target** dropdown lists every target the
caller may reach: **Statistics** always (with `reporting.sql.run`), and
**Octopus** when the caller also holds `reporting.sql.target.octopus`.

### Access

Gated by the `reporting.sql.run` permission for the Statistics target; the
Octopus target additionally requires `reporting.sql.target.octopus` (enforced
server-side on both run and export). Admins have both seeded; grant them
per-user via the normal Permissions admin UI on request.

On first use the user must accept a one-time acknowledgment ("You are about to
run read-only SQL …"). This is recorded in `dbo.ReportingSqlAck` (NexoraDB) and
not shown again on subsequent runs.

### Safety

- **AST-validated:** `sqlglot` parses the submitted query and rejects anything
  that is not a single `SELECT` statement — no DML, DDL, or multi-statement
  batches pass the gate.
- **Read-only login:** queries execute on a dedicated `db_datareader`-only SQL
  login with no write permissions — `engine_statistics_ro` for Statistics,
  `engine_octo_ro` for Octopus. Each target requires the matching permission
  before its query runs.
- **Row cap:** results are hard-limited to 50,000 rows. Plain `SELECT`s get a
  SQL-side `SELECT TOP (n) * FROM (…) AS _q` wrap; `WITH`-rooted queries and
  queries ending in a top-level `ORDER BY` run unwrapped (neither is legal
  inside a derived table, #129) with the cap enforced fetch-side instead —
  either way you never get more than the cap.
- **Timeout:** a ~30-second statement timeout is enforced server-side.
- **Audit:** every run (query text, user, row count, duration, status) is
  written to `dbo.ReportingSqlAudit` (NexoraDB).
- **Error detail:** a query that fails on the target server (not just the
  sqlglot gate) returns a generic 500 whose `detail` is run through
  `humanize_sql_error` — ODBC driver-prefix noise is stripped and SQL Server
  error 1033 (`ORDER BY` in a derived table) gets a plain-language hint —
  instead of the raw pyodbc exception text.

### Owner setup

Each SQL target needs its own read-only SQL login (`db_datareader` role only),
set in both `env/INT.env` and `env/PROD.env`:

| Target | Login on | Env vars |
|--------|----------|----------|
| Statistics | Statistics DB | `DB_REPORTING_RO_USER` / `DB_REPORTING_RO_PWD` |
| Octopus | Octopus runtime DB | `DB_REPORTING_OCTO_RO_USER` / `DB_REPORTING_OCTO_RO_PWD` |

Until a target's env vars are present, that target's engine stays unconfigured
and a run against it returns **503 "SQL source is not configured"** (a warning is
logged). The SQL tab itself enables as soon as the caller holds a SQL
permission, regardless of provisioning; each target only returns data once its
login is set.

To create both `db_datareader`-only logins in one shot, run
`scripts/provision-reporting-ro-logins.sql` against `DB_SERVER_PRD` in SSMS
(SQLCMD Mode; edit the database names + passwords at the top first). It is
idempotent. Then set the four `DB_REPORTING_*_RO_*` vars in `env/INT.env` +
`env/PROD.env` and restart nexora. These logins also unblock the AI assistant's
live schema grounding and scheduled-report delivery.

## See also

- [`reporting-guide.md`](reporting-guide.md) — the end-user guide (how to build,
  read, share, export and schedule a report). Update it in the same commit
  whenever user-visible behaviour changes here.
- `nx_lib/reporting/` — engine package (`schema.py`, `catalog.py`, `sources.py`,
  `query.py`, `export.py`, `sandbox.py`, `ai.py`, `ai_schema.py`).
- `nx_lib/views/reporting/` — Flask routes, split by feature cluster
  (`ai.py`, `pages.py`, `run.py`, `export.py`, `reports.py`, `schedules.py`,
  `admin_registry.py`, `health.py`, `catalog.py`) plus shared helpers in
  `_shared.py`.
- `templates/js/_reporting_js.html` — builder UI; `templates/js/_reporting_viz_js.html`
  — chart + drag-and-drop pivot (`window.ReportingViz`);
  `templates/js/_reporting_ai_js.html` — the AI chat panel (`window.ReportingChat`);
  `templates/_eddard.html` + `templates/js/_eddard_js.html` + `static/css/eddard.css`
  — the Eddard mascot and its build-a-report loading stage;
  `static/js/reporting_dashboard.js` — dashboard builder
  (`window.ReportingDashboard`).
- `sql/_migrations/NexoraDB/0004_create_reports_table.sql` — `dbo.Reports` DDL.
- `sql/_migrations/NexoraDB/0005_seed_reporting_permissions.sql` — permission seed.
- `sql/_migrations/NexoraDB/0006_create_reporting_sql_tables.sql` —
  `dbo.ReportingSqlAudit` and `dbo.ReportingSqlAck` DDL.
- `sql/_migrations/NexoraDB/0007_seed_reporting_sql_permission.sql` —
  `reporting.sql.run` permission + admin seed.
- `sql/_migrations/NexoraDB/0008_seed_reporting_sql_octopus_permission.sql` —
  `reporting.sql.target.octopus` permission + admin seed.
- `sql/_migrations/NexoraDB/0013_create_reporting_ai_audit.sql` —
  `dbo.ReportingAiAudit` DDL + `reporting.ai.use` / `reporting.ai.sql` seed.
- `docs/design/reporting-ai-assistant.md` — AI assistant design spec.
- `docs/superpowers/specs/2026-06-02-reporting-foundation-design.md` — full
  design spec (decisions, architecture, endpoint list, security model).
- `docs/superpowers/specs/2026-07-15-reporting-editorial-ledger-design.md` —
  "Editorial Ledger" visual identity design spec (masthead, KPI band, timing
  badge, query footer, single-series chart colors) — **superseded** by the
  Indigo Studio redesign below; kept for the historical record.
- `docs/superpowers/specs/2026-07-20-reporting-redesign-handoff.md` — the
  "Indigo Studio" design handoff (token table, type scale, per-screen specs)
  + `docs/superpowers/specs/2026-07-20-reporting-dashboard-prototype.dc.html`
  — the dashboard JS state-model prototype (its logic class is the literal
  spec for `reporting_dashboard.js`).
- `docs/superpowers/plans/2026-07-20-reporting-redesign-dashboard-builder.md` —
  the redesign + dashboard-builder implementation plan; supersedes
  `docs/superpowers/plans/2026-07-15-reporting-pin-to-dashboard.md`.
