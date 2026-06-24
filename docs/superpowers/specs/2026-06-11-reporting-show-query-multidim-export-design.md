# Reporting: Show Query, Multi-Breakdowns, Rich Export — Design

**Date:** 2026-06-11
**Status:** Approved (owner answered the three open decisions; see "Decisions")
**Scope:** Reporting feature (Simple + Advanced tabs, export endpoints, scheduled delivery)

## Problem

Three usability gaps in the reporting feature, raised by the owner on 2026-06-11:

1. **No query transparency.** A report run never shows the SQL that was executed. Users
   (and developers debugging a wrong-looking number) cannot see what the definition
   compiled to.
2. **Single breakdown only.** The Simple wizard allows exactly one breakdown. The asked-for
   shape — *"Document count by document source over the last 3 months, per month, by export
   date"* — needs **two** group-by dimensions (a date dimension with a month grain plus a
   categorical dimension), which the wizard cannot express.
3. **Export is tables-only.** Export produces a bare CSV/XLSX of the result rows. No chart,
   no title, no context. Scheduled e-mails attach the same bare file with a one-line body.

## What recon established (2026-06-11, feature/2.5.63)

- The run pipeline already produces a fully **parameterized** `(sql, params)` pair:
  `_prepare_run()` in `nx_lib/views/reporting.py` returns `(columns, sql, params, engine)`
  and `api_run()` holds both at response time. The response JSON simply never includes them.
- The backend **already supports N group-by dimensions**: `definition.columns` is an
  unbounded list (`nx_lib/reporting/schema.py`), `build_aggregate_sql()` joins all dimension
  fields into `GROUP BY` (`nx_lib/reporting/semantic.py`), and the Advanced builder UI
  already lets users add multiple columns. The blockers are purely: the wizard's
  radio-style single `breakdown`, charts plotting only the first dimension, and **zero unit
  tests** for 2+ dimension GROUP BY.
- Export today: `/api/reporting/export` (server-side CSV via stdlib, XLSX via
  `openpyxl==3.1.5`); Advanced has a client-side chart-PNG download
  (`canvas.toDataURL`); Simple has none. Scheduled mail
  (`ops/run_scheduled_reports.py`) attaches the bare file. `pillow==11.3.0` is already in
  `requirements.txt`, so `openpyxl` image embedding works without new dependencies.
  No PDF library exists. `send_mail()` (`nx_lib/mail.py`) posts to Microsoft Graph
  `sendMail`; inline images only need `isInline` + `contentId` on the attachment entries.

## Decisions (owner, 2026-06-11)

| # | Question | Decision |
|---|----------|----------|
| 1 | Who sees the generated SQL? | **Everyone who can run reports.** No new permission. Accepted trade-off: the SQL text reveals the caller's own process scope (which processes were UNIONed) and per-process `additionalCondition` clauses. It contains no credentials; table names are already visible via the source catalog. |
| 2 | How many wizard breakdowns? | **Up to three** (at most one of them a date breakdown). Charts visualize the first two (axis + series); a third renders in the table only, with an explanatory note instead of a chart. |
| 3 | Which export upgrades? | **(a)** XLSX gains a styled title block and the current chart embedded as an image; **(b)** Simple gets a chart-PNG download button; **(c)** scheduled e-mails embed a server-rendered chart inline (and scheduled XLSX embeds it too). **PDF was explicitly not selected.** |

## Design

### A. Show the query that was run

`api_run()` adds two keys to its response: `sql` (the exact parameterized statement text)
and `params` (the bind values, passed through the same JSON-safe conversion the row values
already get). No new endpoint, no new permission — the response only ever describes the
query the caller was already authorized to run.

Both result views get a **"Show query"** toggle that reveals a read-only panel: the SQL in
a monospace `<pre>` (visually consistent with the sandbox's `reporting-sql-editor`), the
parameters as a numbered list beneath it (`1 = '2026-03-01'`, …), and a **Copy** button.
Parameters are displayed separately rather than spliced into the SQL — that is the honest
representation of what was sent to the server, and it avoids writing a client-side SQL
literal-quoting routine.

SQL-sandbox runs (`/api/reporting/sql/run`) are unchanged — the editor already *is* the
query. The toggle hides itself when the response carries no `sql` key.

### B. Up to three breakdowns in the Simple wizard

- `state.wiz.breakdown` (single object) becomes `state.wiz.breakdowns` (array, max 3,
  at most one `kind:'date'`). The breakdown step's buttons become **toggle chips** with an
  explicit **Continue** button (the current radio-style click-to-advance cannot express
  multi-select). "None — just the total" stays exclusive: picking it clears the rest.
- `wizardDefinition()` emits the date dimension first (it is the chart axis), then the
  categories in pick order. Sort: date ascending when a date breakdown exists, otherwise
  metric descending (unchanged from today).
- The reverse-mapper `wizardStateFromDefinition()` (in-flight Task 6 of the simple-guide
  plan) is widened from "reject >1 column" to "map up to 3 columns, at most one grained".
- **Charts:** with 2 dimensions the result is pivoted client-side — distinct first-dimension
  values become the X axis, distinct second-dimension values become colored series
  (capped at the 12 largest by total, with a note). Multi-series charts offer bar
  (grouped), **stacked bar** (new switcher option) and line; pie/doughnut are hidden
  (meaningless per-series). With 3 dimensions no chart is drawn — a note explains that
  charts support up to two breakdowns. We deliberately do **not** sum the metric across the
  third dimension to force a chart: that is wrong for distinct-count metrics.
- **Backend:** no changes needed, but the missing unit tests for multi-dimension
  `GROUP BY` (2-dim, date-grain + category mix, 3-dim) are added — they guard the exact
  SQL shapes the wizard will now generate.

### C. Rich export

1. **XLSX with the chart inside.** `rows_to_xlsx()` gains a styled layout: bold title row,
   a "Generated <UTC timestamp> — <n> rows" meta line, a styled header row with frozen
   panes — and an optional `chart_png` parameter that embeds the chart image above the
   data table (`openpyxl.drawing.image.Image`, Pillow already present). The web client
   sends the currently mounted chart as a base64 PNG (`chartImage` key in the export POST
   body, XLSX format only); the server validates the data-URL prefix and a 2 MB size cap and
   silently drops anything invalid (an export must never fail because of its garnish).
   CSV output is unchanged.
2. **Chart PNG on Simple.** A download button in the Simple chart toolbar reuses the
   Advanced pattern (copy canvas onto a white background, `toDataURL`, anchor download).
3. **Charts in scheduled e-mails.** A new server-side renderer
   `nx_lib/reporting/chart_render.py` draws the equivalent chart with **matplotlib**
   (`Agg` backend — no display server; `MPLCONFIGDIR` pointed into `var/` so the IIS/Task
   Scheduler service account has a writable cache, already inside the Defender exclusion).
   The scheduled runner embeds the PNG inline in the mail body
   (Graph `isInline` + `contentId`, `<img src="cid:report-chart">`) and passes the same PNG
   into the scheduled XLSX. Chart rendering failures are caught and logged — the mail still
   goes out without the chart. The renderer mirrors the frontend's caps (50 X-axis values,
   12 series) and its 1-dim/2-dim shapes; for ≥3 dimensions it returns `None`.

#### Export approaches considered and rejected

- **PDF report** (title + chart + table): needs a new heavyweight dependency
  (reportlab/weasyprint); owner did not select it. Can be added later on top of the same
  `chart_render` PNG.
- **Headless-browser / Node Chart.js rendering** for e-mails (pixel-identical to the web
  charts): a browser or Node runtime on the IIS box is a much bigger operational surface
  than one pip package. Rejected.
- **External chart-image service** (e.g. QuickChart): sends report data to a third party.
  Rejected outright — report rows are internal data.
- **SVG sparkline-style HTML e-mail charts** (hand-built markup): poor client support
  (Outlook strips SVG). Rejected.

## Non-interference with in-flight work

The **Simple-guide improvements plan** (`2026-06-11-reporting-simple-guide-improvements.md`)
still owes Tasks 6–11 and owns `templates/js/_reporting_simple_js.html`,
`templates/_reporting_simple.html`, `static/css/reporting.css` and
`tests/e2e/test_reporting_simple.py` until it lands. Therefore this work is split:

- **Phase 1 (backend — safe to start immediately):** SQL echo, multi-dim unit tests,
  `rows_to_xlsx` upgrade, `chart_render` module, mail inline-image support, scheduled-runner
  embedding. None of these files are touched by the in-flight plan.
- **Phase 2 (frontend — blocked until the in-flight plan's Tasks 6–11 are committed):**
  all template/JS/CSS/e2e work. The plan anchors on function names and quoted code, not
  line numbers, because the in-flight tasks will shift them. Phase 2 builds **on top of**
  the in-flight plan's deliverables (it extends `wizardStateFromDefinition()` and the
  chart-type switcher, which are in-flight Task 6/4 outputs).

## Security notes

- Exposing generated SQL: parameterized text only, no credentials; accepted leaks (own
  process scope, `additionalCondition` business logic) were explicitly accepted by the
  owner for an internal tool. The audit posture is unchanged (sandbox SQL remains audited;
  curated runs remain permission-gated per source and scope).
- `chartImage` upload: strict `data:image/png;base64,` prefix check, strict base64 decode,
  2 MB cap, embedded via openpyxl/Pillow only (never written to disk, never echoed back).
  Invalid input degrades to a chartless export.
- matplotlib renders from in-process data only; no user-controlled format strings or paths.

## Testing strategy

- **Unit:** multi-dim GROUP BY SQL shapes (query + table_query); `rows_to_xlsx` layout +
  image embedding (zip inspection); `chart_render` returns PNG magic bytes / `None` cases;
  `_build_message` inline-attachment shape (extracted pure function in `nx_lib/mail.py`).
- **Integration:** `/api/reporting/run` response carries `sql` + `params`;
  `/api/reporting/export` accepts and survives good/garbage `chartImage`.
- **E2E (table-provider sources — TEST env has no Statistics DB):** show-query toggle,
  two-breakdown wizard flow, multi-series chart presence (via a `data-series` testability
  attribute on the canvas), chart-PNG download event.
- **Manual on INT:** docprocessing wizard walkthrough ("doc count by source per month,
  last 3 months"), scheduled-report `--dry-run` plus one real send, screenshots.
