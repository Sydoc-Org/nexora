# Reporting (self-service BI) — Foundation Design

- **Date:** 2026-06-02
- **Branch:** feature/2.5.63
- **Status:** Approved (brainstorming) — pending implementation plan
- **Author:** benstreich (with Claude)

## 1. Background & motivation

Sydoc currently uses **PowerBI** as its BI tool. The goal is to retire PowerBI and
move reporting into Nexora so that **internal** users can build almost any report
themselves: lists, matrices, charts, combining clients, custom headers, and as many
filters as possible. The owner will then compare Nexora vs PowerBI to find gaps.

This document specifies only the **foundation** ("ground work"): the engine plus the
**table/list** visualization done properly, so the remaining visualizations and
features layer on without rework. Generali is **out of scope** for now.

### What already exists (reused, not rebuilt)

Nexora's **Dashboard** (`nx_lib/views/dashboard.py`) already contains a mini
self-service engine: KPI / time-series / categorical widgets, global filters,
per-user saved layouts (JSON in DB), and a **field-catalog layer**:

- `FieldMetadata` — `FieldKey, DataType, Aggregable, Sortable`
- `SearchConfig` — per-`ProcessName` `col_<field>` → actual data column name
- `Search_Field_Labels` — i18n labels (EN/DE/FR/IT) per `FieldKey`
- `Statconfig` — per-`ProcessName` `TableName / ExportColumn / ImportColumn / additionalCondition`

Per-client/process scoping uses string permissions (`dashboard.filter.process.<client>.<process>`).
Stack: Flask + Jinja (page template paired with a `templates/js/_*_js.html` partial),
Tailwind + Chart.js + flatpickr (all CDN, no build step), vanilla JS.

## 2. Goals (this foundation)

- New internal-only **`/reporting`** page, PowerBI-style **Layout A** (field panel ·
  results · config wells).
- A **data-source registry** + **field catalog** abstraction (heterogeneous sources).
- A **query engine** producing tabular results from a saved report definition.
- **Table / list** visualization with: column picker, **custom headers** + report
  title/subtitle, rich **filters**, sorting, and **combine clients/processes**.
- **Save & name** reports per user; load/list/delete.
- **Excel (.xlsx)** export.
- A **live read-only SQL** source for power users (sandboxed).
- Separate **`reporting.*`** permission scope (independent of the dashboard perms).
- **Document Processing** wired up **live** end-to-end as the first source.

## 3. Non-goals (explicitly deferred)

- Charts (bar/line/pie), matrix / pivot tables — designed for, not built yet.
- Scheduled / emailed reports; cross-user sharing & report library.
- DB-backed source-registration UI (registry is code-defined for now).
- CSV export (chosen format is Excel only).
- Generali sources.
- Wiring Workitems/Octopus as a *curated* source (only reachable via live SQL in this cut).

## 4. Decisions (locked during brainstorming)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Data sources PowerBI covers | Document-processing stats, Workitems/operational, Custom SQL (not invoices) |
| D2 | First visualization | **Data table / list** |
| D3 | First-cut must-haves | Save & name, Export, Custom headers, Combine clients/processes — **all** |
| D4 | Permission model | **Separate `reporting.*` scope perms** |
| D5 | Engine architecture | **Curated registry + live SQL now** (Approach 2) |
| D6 | First live source | **Document Processing** (Statistics DB) |
| D7 | Builder layout | **A — PowerBI-style fields + config wells** |
| D8 | Live-SQL target DBs | **Statistics + Octopus**, read-only |
| D9 | Live-SQL auth | **Dedicated read-only login** (`db_datareader` only); secrets provisioned by owner |
| D10 | Export format | **Excel only** (`.xlsx` via `openpyxl`) |

## 5. Architecture

New engine package keeps logic out of the views (testable; avoids bloating
`dashboard.py`).

```
nx_lib/
  reporting/                 (new package)
    __init__.py
    sources.py               source registry (built-ins: docprocessing, sql)
    catalog.py               field catalog (reuses FieldMetadata/SearchConfig/labels)
    query.py                 curated query builder (parameterized, whitelisted)
    sandbox.py               live-SQL validation + execution guards
    export.py                rows -> .xlsx (openpyxl)
    schema.py                report-definition validation (v1)
  views/
    reporting.py             routes (register in nx_lib/__init__.py)
  db.py                      + engine_*_ro read-only engine(s)
templates/
  reporting.html
  js/_reporting_js.html
static/css/reporting.css
```

### Data flow

Browser (Layout A) → `nx_lib/views/reporting.py` → `nx_lib/reporting/*` engine →
engines in `nx_lib/db.py`:
- curated `docprocessing` → `engine_statistics_db` (rows) + `engine_nexora_db` (catalog)
- live `sql` → `engine_*_ro` (dedicated read-only login) → Statistics + Octopus
- saved reports → `engine_nexora_db` (`Reports` table)

## 6. Data sources & field catalog

Built-in sources are defined in code (a registry list), designed so a DB-backed
registration table can replace/augment it later:

- **`docprocessing`** (curated): field catalog derived from the existing
  `FieldMetadata` + `SearchConfig` + `Search_Field_Labels` for processes the caller is
  permitted to see. Query target: `engine_statistics_db` via `Statconfig` mappings.
- **`sql`** (live SQL): no static field catalog; columns come from the executed query.

Each catalog field: `{ field, label (localized), type, filterable, aggregable, sortable }`.
**Only catalog fields are trusted.** No client-supplied column/table name reaches SQL
without passing the whitelist.

## 7. Report definition (v1 JSON)

Stored per user and posted to `/api/reporting/run`:

```json
{
  "schemaVersion": 1,
  "source": "docprocessing",
  "visualization": "table",
  "title": "string", "subtitle": "string|null",
  "columns": [{ "field": "doctype", "header": "Document type", "agg": null }],
  "groupBy": ["client"],
  "filters": [{ "field": "status", "op": "eq", "value": "Done" }],
  "sort": [{ "field": "date", "dir": "desc" }],
  "scope": { "clients": ["..."], "processes": ["..."] },
  "rowLimit": 5000,
  "sql": null, "sqlTarget": null
}
```
For `source:"sql"`, `sql` + `sqlTarget` ("statistics"|"octo") are used and
`columns/filters/groupBy/scope` are ignored.

Filter ops (initial set): `eq, ne, in, not_in, gt, gte, lt, lte, between, contains,
starts_with, is_null, is_not_null`. Validation rejects ops incompatible with a field's
type.

## 8. Query engine (curated path)

1. Resolve source + its field catalog.
2. Validate every `columns/filters/sort/groupBy` entry against the catalog; reject unknown
   fields or type-incompatible ops.
3. Compute effective row-scope = **intersection** of requested `scope` and the caller's
   `reporting.scope.process.*` grants. Empty scope → empty result (no leak).
4. Build **parameterized** SQL. Combining clients/processes uses a safe `IN (...)` /
   `UNION ALL` over the permitted set (mirrors the dashboard's existing multi-process
   query construction; column names come from `SearchConfig`, never from the client).
5. Apply `rowLimit` (server-capped) and return `{ columns, rows, rowCount, truncated }`.

Custom **headers** and **title/subtitle** are presentation-only (applied to the response
labels and the export), never used in SQL.

## 9. Live-SQL sandbox (security-critical)

Gated by `reporting.sql.run` (power users only). Layers:

1. **Parse/lint:** must be a single `SELECT` or `WITH … SELECT`. Reject multiple
   statements (no stray `;`), comments stripping bypass attempts, and a keyword
   **blocklist**: `INSERT, UPDATE, DELETE, MERGE, DROP, ALTER, CREATE, TRUNCATE, GRANT,
   REVOKE, EXEC, EXECUTE, INTO, BACKUP, RESTORE, SHUTDOWN, OPENROWSET, OPENQUERY,
   OPENDATASOURCE, xp_, sp_`.
2. **Row cap:** execute as `SELECT TOP (cap) * FROM ( <user sql> ) AS _q` so the cap holds
   regardless of the inner query.
3. **Statement timeout:** connection/cursor timeout to kill long queries.
4. **Dedicated read-only login (defense in depth):** runs on `engine_*_ro` whose SQL
   login has **`db_datareader` only** — writes are impossible even if a guard is bypassed.
   Allowed targets: **Statistics + Octopus**.
5. **Audit:** log `userid + target + sql` for every execution.
6. **Rate limit:** stricter `@limiter.limit` than the curated endpoint.

New env vars (added to `env/*.env.example`; real secrets provisioned by owner):
`DB_REPORTING_RO_USER`, `DB_REPORTING_RO_PWD` (server reuses `DB_SERVER_PRD`). Exact
names finalized in the plan to match `nx_lib/config.py` conventions.

## 10. Permissions (`reporting.*`)

- `reporting.view` — page access (nav + route guard).
- `reporting.sql.run` — may use the live-SQL source.
- `reporting.source.<id>` — access to a given curated source (e.g. `reporting.source.docprocessing`).
- `reporting.scope.process.<client>.<process>` — which clients/processes a user may include
  (row scope), independent of `dashboard.filter.process.*`.

Wire-up: `page_visibility()` gains `reportingPagePerm`; `_header.html` adds a nav entry
gated on it; `startpage_redirect_to` includes the reporting route. Seeded via migration
per the existing Permissions schema (confirmed against live tables during planning).

## 11. Endpoints (`nx_lib/views/reporting.py`)

All require auth + appropriate permission, CSRF-protected, rate-limited:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/reporting` | builder page |
| GET | `/api/reporting/sources` | sources + field catalogs the caller may use |
| POST | `/api/reporting/run` | run a curated report definition → rows |
| POST | `/api/reporting/sql/run` | run live SQL (perm `reporting.sql.run`) → rows |
| POST | `/api/reporting/export` | report definition → `.xlsx` download |
| GET | `/api/reporting/reports` | list caller's saved reports |
| GET | `/api/reporting/reports/<id>` | load one |
| POST | `/api/reporting/reports` | create/save |
| PUT | `/api/reporting/reports/<id>` | update |
| DELETE | `/api/reporting/reports/<id>` | delete |

## 12. Database migrations (`sql/_migrations/NexoraDB/`)

- **`Reports`** table: `Id, OwnerUserId, Name, DefinitionJSON, CreatedAt, UpdatedAt`
  (per-user private; sharing deferred).
- Seed `reporting.*` permission codes + grants for the initial internal user/role.

(DDL finalized against the live Permissions schema during planning. Migrations applied
via the standard pre-commit hook / `scripts/db-migrate.py`.)

## 13. Frontend (Layout A)

`templates/reporting.html` + `templates/js/_reporting_js.html` + `static/css/reporting.css`,
vanilla JS consistent with the codebase. Three regions:

- **Left — Field panel:** source selector, searchable field list.
- **Center — Results:** toolbar (Table ⇄ SQL toggle, report title, Save, Export), results table.
- **Right — Config wells:** Columns, Filters, Sort, Format (custom headers + title/subtitle).

flatpickr for date filters. Saved-reports access from the toolbar (a left "Saved" rail can
arrive with Layout C ideas later). i18n via `{{ _('…') }}` / `gettext`.

## 14. Dependencies

- `openpyxl` added to `requirements.txt` (Excel export).

## 15. Testing

- **Unit:** catalog validation; curated SQL builder output; scope intersection (no leak on
  empty/over-broad scope); sandbox accepts a benign SELECT and rejects each blocklisted
  pattern, multi-statement, and over-cap row counts.
- **Browser:** Playwright via `nx -u -b --loginas:<user>` — build a report, add filters,
  combine two clients, rename a header, save, reload, export `.xlsx`. Screenshots to
  `var/screenshots/`.

## 16. Docs (part of the change)

- `CHANGELOG.md` → `[Unreleased]` Added entries.
- New `docs/howto/reporting.md` (page usage + how to add a source + SQL sandbox rules).
- `CLAUDE.md` → new view module, `reporting.*` perms, read-only env vars, `openpyxl` dep.
- `env/*.env.example` → read-only login vars.
- Confirm `deploy.yml` excludes (no new top-level dir expected → likely no change).

## 17. Implementation phasing (for the plan)

One spec, sequenced as two reviewable milestones:

1. **Curated table engine:** registry + catalog + query builder + `docprocessing` live +
   filters/combine/headers/sort + save/load + Excel export + page/nav/perms (`reporting.view`,
   `reporting.source.docprocessing`, `reporting.scope.*`) + `Reports` table.
2. **Live-SQL sandbox:** `engine_*_ro` read-only engines + sandbox + `/api/reporting/sql/run`
   + `reporting.sql.run` + SQL toggle in the UI + audit log + env vars.

## 18. Prerequisites / open items for planning

- Provision the **dedicated read-only SQL login** (`db_datareader` on Statistics + Octopus)
  and add its secrets to `env/INT.env` / `env/PROD.env` (owner action).
- Confirm the exact **Permissions tables** + `spGetUserPermissions` shape for the seed migration.
- Confirm the **rowLimit** cap defaults (curated vs SQL).
