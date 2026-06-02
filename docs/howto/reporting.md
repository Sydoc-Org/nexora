# Reporting

The `/reporting` page is Nexora's self-service report builder — a PowerBI
replacement for internal users. Phase 1 ships a **table/list** visualization
over the curated **Document Processing** source with full filter, sort, combine,
custom-header, save/load, and Excel-export support.

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

### Combine clients/processes

The scope wells let users include rows from multiple clients or processes in a
single table. The engine intersects the user's requested `scope` with their
`reporting.scope.process.*` grants — selecting a process the user has no grant
for silently excludes it (no data leak).

### Save & load

Reports are saved per user in the `dbo.Reports` table (NexoraDB). A saved
report stores the full v1 definition JSON. The **Saved reports** dropdown on the
toolbar groups **My reports** and **Shared with me** (the latter tagged with the
owner). **Load** restores a curated definition into the builder (source, columns,
filters, sort, scope, title/subtitle) or a SQL definition into the SQL editor +
target, switching mode by the saved `kind`. **Rename** and **Delete** act on the
selected report (owner only).

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
  the encoding). Custom column headers are used in the header row.
- **Pivot** → the computed pivot matrix. The client posts the displayed
  `{columns, rows}` to `/api/reporting/export/grid` (`reporting.export`; no DB
  access — pure serialization with the same formula-injection guard) in the
  chosen format.
- **Chart** → a **PNG** image of the current chart, rendered client-side from the
  Chart.js canvas (flattened onto white). The format selector does not apply.

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
  "rowLimit": 5000
}
```

**Filter ops (Phase 1):** `eq`, `ne`, `in`, `not_in`, `gt`, `gte`, `lt`,
`lte`, `between` (value is a 2-element list), `contains`, `starts_with`,
`is_null`, `is_not_null`. The validator rejects ops incompatible with a field's
declared type.

Custom `header` on a column is presentation-only — it appears as the column
label in the results table and in the Excel export; it is never used in SQL.

## How to add a new curated source

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

## See also

- `nx_lib/reporting/` — engine package (`schema.py`, `catalog.py`, `sources.py`,
  `query.py`, `export.py`, `sandbox.py`).
- `nx_lib/views/reporting.py` — Flask routes.
- `templates/js/_reporting_js.html` — builder UI; `templates/js/_reporting_viz_js.html`
  — chart + drag-and-drop pivot (`window.ReportingViz`).
- `sql/_migrations/NexoraDB/0004_create_reports_table.sql` — `dbo.Reports` DDL.
- `sql/_migrations/NexoraDB/0005_seed_reporting_permissions.sql` — permission seed.
- `sql/_migrations/NexoraDB/0006_create_reporting_sql_tables.sql` —
  `dbo.ReportingSqlAudit` and `dbo.ReportingSqlAck` DDL.
- `sql/_migrations/NexoraDB/0007_seed_reporting_sql_permission.sql` —
  `reporting.sql.run` permission + admin seed.
- `sql/_migrations/NexoraDB/0008_seed_reporting_sql_octopus_permission.sql` —
  `reporting.sql.target.octopus` permission + admin seed.
- `docs/superpowers/specs/2026-06-02-reporting-foundation-design.md` — full
  design spec (decisions, architecture, endpoint list, security model).
