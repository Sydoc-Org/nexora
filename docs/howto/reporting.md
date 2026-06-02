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
report stores the full v1 definition JSON; loading it restores every column,
filter, sort, and scope setting. Each user can only access their own saved
reports.

### Excel export

POST to `/api/reporting/export` with the same report-definition JSON. Returns a
`.xlsx` file via `openpyxl`. Custom column headers are used in the spreadsheet
header row.

## Permissions (`reporting.*`)

| Code | Grants |
|------|--------|
| `reporting.view` | Page access — nav entry visible, `/reporting` route allowed. |
| `reporting.source.docprocessing` | Use the Document Processing curated source. |
| `reporting.export` | Export reports to Excel (`.xlsx`). |
| `reporting.scope.process.<client>.<process>` | Include a specific client/process in a report's row scope. |
| `reporting.sql.run` | Run live read-only SQL in the sandbox (see below). Grantable; admins seeded. |

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
directly against the Statistics database.

### Access

Gated by the `reporting.sql.run` permission. Admins have it seeded; grant it
per-user via the normal Permissions admin UI on request.

On first use the user must accept a one-time acknowledgment ("You are about to
run read-only SQL …"). This is recorded in `dbo.ReportingSqlAck` (NexoraDB) and
not shown again on subsequent runs.

### Safety

- **AST-validated:** `sqlglot` parses the submitted query and rejects anything
  that is not a single `SELECT` statement — no DML, DDL, or multi-statement
  batches pass the gate.
- **Read-only login:** queries execute on `engine_statistics_ro`, a dedicated
  `db_datareader`-only SQL login with no write permissions.
- **Row cap:** results are hard-limited to 50,000 rows.
- **Timeout:** a ~30-second statement timeout is enforced server-side.
- **Audit:** every run (query text, user, row count, duration, status) is
  written to `dbo.ReportingSqlAudit` (NexoraDB).

### Owner setup

Provision a read-only SQL login on the Statistics DB (`db_datareader` role only),
then set `DB_REPORTING_RO_USER` and `DB_REPORTING_RO_PWD` in both
`env/INT.env` and `env/PROD.env`.

Until these env vars are present the SQL source returns **503 "SQL source is
not configured"** and the SQL tab remains disabled for all users.

## See also

- `nx_lib/reporting/` — engine package (`schema.py`, `catalog.py`, `sources.py`,
  `query.py`, `export.py`, `sql_sandbox.py`).
- `nx_lib/views/reporting.py` — Flask routes.
- `sql/_migrations/NexoraDB/0004_create_reports_table.sql` — `dbo.Reports` DDL.
- `sql/_migrations/NexoraDB/0005_seed_reporting_permissions.sql` — permission seed.
- `sql/_migrations/NexoraDB/0006_create_reporting_sql_tables.sql` —
  `dbo.ReportingSqlAudit` and `dbo.ReportingSqlAck` DDL.
- `sql/_migrations/NexoraDB/0007_seed_reporting_sql_run_permission.sql` —
  `reporting.sql.run` permission + admin seed.
- `docs/superpowers/specs/2026-06-02-reporting-foundation-design.md` — full
  design spec (decisions, architecture, endpoint list, security model).
