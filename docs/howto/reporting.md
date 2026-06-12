# Reporting

The `/reporting` page is Nexora's self-service report builder — a PowerBI
replacement for internal users. Phase 1 ships a **table/list** visualization
over the curated **Document Processing** source with full filter, sort, combine,
custom-header, save/load, and Excel-export support.

## Simple and Advanced tabs

`/reporting` opens as two tabs (one route, two client-side panes;
`templates/js/_reporting_tabs_js.html` is the controller):

- **Simple** — the default; built for report *viewers* and non-data-science
  stakeholders. It is purely a presentation layer over the existing REST
  endpoints (`templates/_reporting_simple.html` +
  `templates/js/_reporting_simple_js.html`):
  - **Library** — every report you can see, grouped into *Library*
    (org-shared, `Visibility='shared'`, any owner), *My reports*, and *Shared
    with me*. Click a card to run it (lazy — nothing runs until opened).
    Live-SQL (`kind:'sql'`) reports are hidden here (viewers can't run them);
    they stay fully usable in Advanced.
  - **+ New report (wizard)** — measure (from the metrics registry; picking a
    measure pins the source — admins grow the wizard's reach by adding rows at
    `/reporting/metrics`, zero code change) → break down by *over time* (with a
    grain select, default month) / a category / *none — just the total* → time
    range (presets or a custom flatpickr range; emits a `between` filter on the
    **raw** date field, defaulting to `import_date`).
    The category list is curated for the Document Processing source — preferred
    business dimensions (Document Source, Document Type, Forwarding, Owner no.,
    Property No., Registered, Tenancy no.) come first and technical noise (process
    name, Bank PK, creditor no., barcode, document date, workitem id) is hidden;
    other sources list their catalog fields unfiltered. The **"Limit to specific
    processes"** control is a prominent bordered row with a live selection badge
    ("All processes" or "n / m").
  - **Ask AI** — one input to Surface A; a valid draft renders straight to the
    result view. Hidden if AI is unconfigured.
  - **Result view** — a grand-total **number card** (computed by a zero-column
    clone run, so it is correct for every aggregation — avg/count_distinct
    included), a **chart card** (line for date breakdowns, bar for categories by default,
    with a bar/line/pie/doughnut switcher; the chosen type is saved with the report).
    The wizard supports **up to three breakdowns** (at most one date); the first breakdown is
    the chart axis, the second becomes the colored series (grouped bars or one line per
    series, with a stacked-bar option); a third breakdown shows in the table only. Charts cap
    at 50 axis values and 12 series; categories beyond 50 chart the top 50 with a note.
    When no chart is possible the result explains why (single total, too many date points,
    chart library unavailable). A **chart-PNG download** button in the chart toolbar saves
    the current chart as an image. A **Show query** toggle (collapsed by default,
    re-collapsed on every run) reveals the executed SQL — pretty-printed server-side
    (sqlglot) and syntax-highlighted — plus its bind parameters (visible to anyone who
    can run reports; the Copy button copies the raw executed statement). While a report
    runs, both tabs show a pulsing in-flight indicator (the Advanced **Run** button locks
    until the response lands), and the Advanced Ask-AI surfaces show the same indicator
    with rotating status lines.
    A **Show table** toggle, *Save* (always creates a new
    row under My reports), *Open in Advanced* (pre-fills the builder), and *Export*
    (downloads Excel with a title block and — when a chart is on screen — the chart image
    embedded above the data; needs `reporting.export`). For AI-built results, a
    **transparency line** below the report title shows the AI's explanation
    and the filters/processes it applied, so a wrong guess (bad date range,
    wrong process) is immediately visible.
    Every result (wizard-built, library-opened, or AI-built) shows **editable
    filter/process chips** and a **Refine** bar — use them to tweak any result
    without returning to the wizard or asking the AI again.
    Any result whose definition is wizard-shaped — including saved library reports
    and simple AI-built ones — shows an **"Adjust in wizard"** button that
    re-opens the walkthrough with the previous measure, breakdown, time and process
    choices pre-selected. **Back** on such a result returns to the wizard
    adjustment; the **✕** button (on both the result bar and the wizard header)
    exits to the library.
- **Advanced** — the full three-panel builder described below, unchanged.

Deep link with `/reporting?tab=advanced` (or `?tab=simple`); without a `?tab=`
parameter the last-used tab is restored per browser (`localStorage`).

> **Viewer semantics:** a shared library report runs against the *viewer's*
> grants (`reporting.scope.process.*`, per-source perms) — different users can
> legitimately see different numbers, or a friendly "you don't have access"
> message. This is existing run-path behavior, surfaced honestly in the UI.

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
field picker. Not every process populates every `SearchConfig.col_*`, so each
catalog field carries the `processes` that expose it; the left-panel list shows a
field only when at least one selected process exposes it (union — `All
processes` shows every field). This is purely client-side off the catalog already
loaded. Narrowing the scope also **prunes any already-added column / filter / sort**
whose field is no longer available, so a definition can't reference a field absent
from every scoped process (which the query builder would reject).

### Date dimension (import / export date)

The docprocessing source exposes two synthetic **date** fields, `import_date`
and `export_date`, derived from each process's `Statconfig.ImportColumn` /
`ExportColumn` (CONVERT-vs-CAST normalized like the dashboard). They are
filterable (date-range via the flatpickr filter row), sortable, and **grainable**:
a date column carries an optional `grain` (`day/week/month/quarter/year`, default
`month`) that the query builder truncates to — `DATEFROMPARTS(...)` for
month/quarter/year, Monday-anchored `DATEADD/DATEDIFF` for week. Grain applies to
projection/grouping only; a **filter** on a date field always compares the raw
date. Combined with a metric (e.g. `doc_count`) and a month-grain `import_date`
dimension, this produces "documents per month". Date expressions originate solely
from `Statconfig`, never the client — same trust boundary as the table/condition
interpolation.

### Workitem dimension & distinct count (`workitem_id` / `workitem_count`)

The docprocessing source exposes a synthetic **`workitem_id`** field mapped per
process by `StatConfig.WorkitemColumn` (migration `0020`; the underlying column
names vary — `WorkItem`, `WorkitemID`, `WID`, ...). The query builder CASTs
every mapping to `nvarchar(100)` so the cross-process UNION never mixes the
columns' native types (nvarchar vs int). A process whose `WorkitemColumn` is
NULL simply doesn't expose the field — set the column in `StatConfig` to add it
for a new process, no code change needed.

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

A recipient sees shared reports under **Shared with me** and can **Load** them.
**Save** overwrites in place only if they own the report or hold an edit grant;
otherwise it forks a copy (**Save as**). Only the owner can change visibility,
manage shares, rename, or delete. Endpoints:

| Endpoint | Who | Purpose |
|----------|-----|---------|
| `GET /api/reporting/reports` | any `reporting.view` | reports you own + shared-with-you (tagged `owned`/`canEdit`/`ownerName`) |
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

### Export (Excel / CSV, and what you see)

Pick the format (**Excel** or **CSV**) next to the **Export** button, then export
is **view-aware**:

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
| `reporting.semantic.admin` | Manage the canonical-metrics registry at `/reporting/metrics` (see below). Admins seeded. |
| `reporting.schedule` | Schedule a saved report to run and be emailed (see below). Admins seeded. |
| `reporting.ai.use` | Use the AI assistant — ask natural-language questions (see below). Admins seeded. |
| `reporting.ai.sql` | Receive AI-drafted read-only T-SQL into the SQL editor. Grant alongside `reporting.sql.run`. Admins seeded. |

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

- **`docprocessing`** — the bespoke Statconfig builder (the built-in source).
- **`table`** — a generic provider (`nx_lib/reporting/table_query.py`) that runs
  a **whitelist-built, parameterized `SELECT`** of the chosen columns over a
  single `BaseObject` (`Db.schema.object`) on the source's `Engine`
  (`nexora` / `statistics` / `generali` / `octopus`). Its field catalog is the
  source's `ColumnsJSON` (`[{field,label,type,filterable,sortable}]`). Every
  identifier (base object + columns) is validated against `^[A-Za-z_][A-Za-z0-9_]*$`
  and bracket-quoted; users only choose among catalogued columns and supply
  parameterized values — so a `table` source is safe to register from the UI.

**Built-in registered sources.** Migration `0011` seeds two `table`-provider
sources: **Generali — PDQM Report** (`generali_pdqm` over `dbo.PDQMReport`) and
**Workitems (Octopus)** (`workitems` over `dbo.t_Documents`), each gated by its
own permission (`reporting.source.generali.pdqm`, `reporting.source.workitems`).
Unlike the docprocessing source, the `table` provider does **not** apply
`reporting.scope.process.*` row scoping — the source permission is the whole
gate, so grant it deliberately. Tune the exposed columns/object at
`/reporting/sources`.

**Registering a generic source needs no code:** add a `ReportingSources` row with
`Kind=curated`, `Provider=table`, an `Engine`, a `BaseObject`, the `ColumnsJSON`
catalog, and a `Permission` — then grant that permission. A `Kind=sql` row adds a
SQL-sandbox source over an existing target. Use the code path below only when a
source needs bespoke query logic the `table` provider can't express.

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
display hint; `Enabled` and `SortOrder` control visibility/ordering. Migration
`0017` seeds a worked example, `doc_count` (a `count` over the docprocessing
source).

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
   `SearchConfig` / `FieldMetadata` mappings, never from user input.

4. **Wire the catalog + query into the view** (`nx_lib/views/reporting.py`).
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

6. **FieldMetadata / SearchConfig coverage** for curated sources: each
   `field` key the catalog exposes must have a corresponding row in
   `dbo.FieldMetadata` (data type, sortable/aggregable flags) and entries in
   `dbo.SearchConfig` for each process that maps `col_<field>` to the actual
   data column name in that process's statistics table. Labels come from
   `dbo.Search_Field_Labels`.

## Scheduled & emailed reports

A saved report you own can be delivered on a schedule (permission
`reporting.schedule`). The **Schedule** dialog manages per-report schedules:
**frequency** (daily / weekly / monthly), **time** (UTC), **format** (xlsx/csv),
and **recipients**. Schedules live in `dbo.ReportSchedules` (migration `0012`,
FK to `Reports` `ON DELETE CASCADE`); endpoints are under
`/api/reporting/reports/<id>/schedules` (owner-only).

Delivery is **not** in-process. `ops/run_scheduled_reports.py` (which ships to
the server because `ops/` is deployed) finds due rows
(`Enabled = 1 AND NextRunAt <= now`), runs each report **as its owner** —
`nx_lib/reporting/runner.py` loads the owner's permissions
(`spGetUserPermissions`) and process scope, then reuses the same builders as the
web path — renders the file, emails it via Microsoft Graph (`nx_lib/mail.py`,
ROPC + `/me/sendMail`), and advances `NextRunAt` (`compute_next_run`).

For reports with **1–2 breakdowns**, the runner server-renders a chart using
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

The **Ask AI** tab in the report builder offers two sub-modes: **Build a report**
(Surface A, default) and **Write SQL** (Surface B; only shown when the user also
holds `reporting.ai.sql`). Both modes send only the user's question and curated-source
catalog metadata to the model — never result rows.

### Build a report (Surface A)

Route: `POST /api/reporting/ai/build`

**Access:** only `reporting.ai.use` is required. `reporting.ai.sql` and
`reporting.sql.run` are **not** needed.

The model produces a v1 report definition (source, columns, filters, sort, scope,
rowLimit, optionally `metrics` + per-column `grain`). The catalog the model sees
marks **grainable** date fields and lists each source's canonical **metrics**
(code, label, aggregation), and the system prompt documents the metrics/grain
contract — including zero-column grand totals — so drafts can aggregate the same
way the builder does. The server validates the draft through
`validate_report_definition` — the same whitelist validator used by
`/api/reporting/run`, with the same `metric_codes`/`grainable_fields` — and
attempts one self-repair retry if the first draft fails validation.

**Prompt grounding (AI quality):**
- **Today's date** is injected into the user prompt so relative time expressions
  ("last month", "this year", "yesterday") resolve to correct absolute date ranges,
  not to training-data dates.
- **Distinct/different values:** the system prompt teaches the model that
  answering "different X" questions requires `columns: [X]` plus a count metric,
  which triggers GROUP BY so each value appears once (bare columns produce duplicate rows).
- **Process labels:** each process id in the catalog is shown with a derived human
  label in parentheses (e.g. `privera.03_Invoice_New ("privera Invoice New")`),
  and the model is instructed to match natural-language process names
  case-insensitively against both the id and the label, including all matches.

On success, the panel shows a summary and two buttons:

- **Open in builder** — calls `applyDefinition()` to fill the builder wells; the user
  then runs the report via the existing `POST /api/reporting/run` path (so row-scoping
  via `reporting.scope.process.*` and the source field whitelist still apply — no data
  bypass).
- **Make a chart** — appears only when the model returns a `chartHint`; one-click
  renders the hinted chart type via the existing chart view.

Every call is audited to `dbo.ReportingAiAudit` with `Surface='definition'`. The
per-user/day cap (`AI_DAILY_LIMIT`) applies. No new permission, table, or migration.

**Egress:** the model receives the question plus the curated-source field catalog
metadata only — never result rows.

### AI refine (Simple tab)

After an AI-built result renders, a **Refine** bar appears below the explanation.
Type a follow-up question (e.g. "break it down by month instead") and click
**Refine** to improve the report without starting over. The AI receives the original
question and definition as context so it can apply targeted changes rather than
rebuilding from scratch.

**Filter/process chips** appear below the explanation, showing every filter the AI
chose and which processes are in scope. Click a chip to edit the value inline; click
× to remove a filter. The process chip opens a checklist to narrow scope. Each change
re-runs the report immediately — no AI cost.

### Write SQL (Phase 1 — Surface B)

The **Ask AI** tab in the report builder lets a user ask a question in plain
language and receive a read-only T-SQL draft placed in the SQL editor. The user
then reviews and runs it via the normal SQL sandbox path — the assistant never
executes anything itself.

### Access

Two permissions control the feature:

| Code | Grants |
|------|--------|
| `reporting.ai.use` | See the **Ask AI** tab (question → model call). |
| `reporting.ai.sql` | Receive the AI-drafted SQL into the editor. Grant alongside `reporting.sql.run` so the user can then run it. |

Admins have both seeded; grant them per-user via the normal Permissions admin UI.
If neither permission is held the tab does not appear.

### Route

`POST /api/reporting/ai/ask` — accepts `{"question": "..."}`, returns
`{"sql": "...", "explanation": "...", "valid": true|false, "target": "statistics", "model": "..."}`,
where `target` is the default editor target the SQL is meant for (the user can
switch) and `model` is the model that drafted it. The sqlglot gate verdict and
token counts are **not** returned to the client — they are recorded only in the
`dbo.ReportingAiAudit` row. Every call is audited to `dbo.ReportingAiAudit`
(user, question, model, provider, duration, gate verdict, token counts).

### Agent (Surface C — Phase 3, drafter)

Route: `POST /api/reporting/ai/agent` — accepts `{"question": "..."}` and returns
`{"answer", "definition", "sql", "toolTrace", "turns", "stoppedReason", "explainData"}`.
Unlike Surfaces A/B (single draft + one retry), this runs a **Tier-2 agentic
tool-loop** (`nx_lib/reporting/ai.py: ask_agentic`): the model calls tools, sees
their results, and **self-repairs** until it has a validated artifact or hits a
hard turn cap. In the UI it is the **Agent** sub-mode of the Ask-AI panel, which
shows a conversation thread, a visible tool-step trace (each step + ok/error
chip + row count), and a follow-up input.

**Access:** `reporting.ai.use`. By default the loop binds only **data-free** tools
to the model — `build_definition` (always) and `validate_sql` (only with
`reporting.ai.sql`) — so egress stays **schema-only**: the model receives the
question plus the source catalog / SQL schema, and tool results are ok/error only.
The grounding prepends today's date and the system prompt instructs the model to
resolve relative time expressions against it; process matching, distinct-values,
and humanized process labels apply identically to Surface A (see above).
`AI_DAILY_LIMIT` applies; audited with `Surface='agent'` (and `Status='misconfig'`
if the provider is broken, `'blocked'` when the cap is hit). The last validated
definition/SQL in the tool trace is returned for one-click **Open in builder** /
**Insert SQL**.

> **Phase 3e — explain the data (opt-in).** When the caller holds
> `reporting.ai.explain_data` **and** `reporting.sql.run`, the loop additionally
> binds `run_sql` and `compute_stats` (`nx_lib/reporting/stats.py`), so the model
> runs validated read-only SELECTs and **narrates the actual numbers** — a
> deliberate **data-egress** path (result rows reach the model). Seeded to admins
> by migration `0015`; grantable per-user; **off by default** (then the loop stays
> schema-only as above). The response/audit carry an `explainData` flag. Glossary
> RAG (the other Phase 3e item) is still planned — it needs a curation owner.

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
| `AZURE_OPENAI_API_VERSION` | API version (optional; defaults to `2024-10-21`). |
| `AI_DAILY_LIMIT` | Per-user/day cap on AI asks (cost/abuse control). `0` (default) = unlimited. When the cap is hit the route returns **429** before any provider call, and the throttle is recorded in `dbo.ReportingAiAudit` with `Status='blocked'`. |

Until `AI_PROVIDER` is set (or is `none`) the route returns **503** and the tab
does not render. Sanitised key names are committed in `env/*.env.example`.

### Safety & privacy

- **Schema-only egress:** the model receives the user's question and schema
  metadata (table/column names and types) only — never result rows or user data.
  This is enforced in `nx_lib/reporting/ai_schema.py` (the bounded serializer
  strips everything beyond name/type/description).
- **sqlglot gate:** every AI-drafted query is validated by `sqlglot` (same gate
  as the SQL sandbox) before it is returned to the client. A draft that fails
  the read-only check is still shown to the user but flagged with a warning;
  it is never auto-inserted silently.
- **No new execution path:** the only action available from the AI panel is
  **Insert into SQL editor**. The user then runs it via the existing gated
  `POST /api/reporting/sql/run` path — the same read-only login, row cap,
  timeout, and audit trail as any other SQL sandbox run.
- **Audit:** every AI interaction (question, model, provider, gate verdict,
  token counts, duration, status) is written to `dbo.ReportingAiAudit`
  (migration `0013_create_reporting_ai_audit.sql`).
- **Cost/abuse control:** `flask_limiter` caps the route at 10/min/user, and the
  optional `AI_DAILY_LIMIT` enforces a per-user/day ceiling that is checked
  *before* any provider call (a throttled ask costs no tokens) and audited with
  `Status='blocked'`.

### Implementation

- `nx_lib/reporting/ai.py` — provider-agnostic client (Anthropic + Azure
  OpenAI); HTTP transport is injectable for tests.
- `nx_lib/reporting/ai_schema.py` — bounded schema serializer.
- `templates/reporting.html` + `templates/js/_reporting_ai_js.html` — Ask AI
  panel and JS.

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
- **Row cap:** results are hard-limited to 50,000 rows.
- **Timeout:** a ~30-second statement timeout is enforced server-side.
- **Audit:** every run (query text, user, row count, duration, status) is
  written to `dbo.ReportingSqlAudit` (NexoraDB).

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

- `nx_lib/reporting/` — engine package (`schema.py`, `catalog.py`, `sources.py`,
  `query.py`, `export.py`, `sandbox.py`, `ai.py`, `ai_schema.py`).
- `nx_lib/views/reporting.py` — Flask routes.
- `templates/js/_reporting_js.html` — builder UI; `templates/js/_reporting_viz_js.html`
  — chart + drag-and-drop pivot (`window.ReportingViz`);
  `templates/js/_reporting_ai_js.html` — Ask AI panel.
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
