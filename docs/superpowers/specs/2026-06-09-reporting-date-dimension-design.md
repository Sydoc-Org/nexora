# Design — Reporting: import/export date dimension (docprocessing)

- **Date:** 2026-06-09
- **Branch:** `feature/2.5.63`
- **Status:** design, pending user review → implementation plan
- **Scope:** Spec **1 of 2**. This adds a first-class date/time dimension to the
  docprocessing source. The **Simple/Advanced page restructure** (library +
  guided wizard + number/chart cards + AI helper) is **Spec 2** and consumes
  this; it is out of scope here. See "Spec 2 preview" at the end.
- **Origin:** handoff `2026-06-09-reporting-usability-gaps-handoff.md` Issue 2 +
  the brainstorming session that produced this doc.

## Problem

The docprocessing source has **no time dimension**. The field catalog
(`fetch_docprocessing_catalog`) is built only from `SearchConfig.col_*` columns;
the per-process import/export date columns live in a *different* table,
`Statconfig` (`ExportColumn` / `ImportColumn`). `_load_process_configs` already
loads `export_col` / `import_col` into `process_configs`, but the query builder
`build_table_query` never references them — they are dead inputs. So a report
cannot select, filter-by, sort-by, or group-by import/export date. "Documents
this month", "volume by day/week/month", and any date-range filter are
impossible — the bread-and-butter of a BI page.

## Goal

Make import & export dates first-class report fields on the docprocessing
source, so a user can:

- **filter** by a date range (e.g. import date in the last month),
- **sort** by date,
- **group / break down** by a **grain**: day, week, month, quarter, or year
  (e.g. "documents per month").

…uniformly across every in-scope process, despite per-process column-name and
column-type differences.

## Non-goals (this spec)

- The Simple/Advanced page restructure, report library, guided wizard, number +
  chart cards, AI-helper-in-Simple (all **Spec 2**).
- Teaching the AI Surfaces to *emit* a grain (the date fields appear in AI
  grounding for free because they are catalog fields; AI-authored grain grouping
  is a later nice-to-have, not required here).
- Date support for the generic `table` provider (Generali / Octo) — those
  sources have no date dimension; `grain` is simply ignored/invalid there.

## Data reality (INT, verified)

All five in-scope processes carry **both** an export and an import column in
`Statconfig`, but the names vary per process and the **values are SQL
expressions, not always bare columns**:

| Process | table | ExportColumn | ImportColumn |
|---|---|---|---|
| compass.01_Invoice_SAP | dbo.Compass_Invoice | `UploadDatetime` | `ImportDate` |
| elektromaterial.02_Invoice | dbo.EM_Invoice | `ExportEM_dt` | `ImportDatetime` |
| privera.02_InitialScan | dbo.PriveraInitialUndNeuzugaenge | `Export` | `ImportDatetime_dt` |
| privera.02_Posteingang | dbo.PriveraPosteingang | `exportdatetime_dt` | `ImportDatetime_dt` |
| privera.03_Invoice_New | dbo.PriveraInvoice | `ExportDate` | `ImportTime` |

The dashboard (`dashboard.py:300-301`) already normalises these defensively:

```python
convert = "convert" in str(row.ExportColumn).lower()
date_col = f"CAST({row.ExportColumn} AS DATE)" if not convert else row.ExportColumn
```

i.e. some processes store the date as a string and the `Statconfig` value is a
`CONVERT(...)` expression to be used **as-is**; otherwise the bare column is
`CAST(... AS DATE)`. Our resolution must mirror this exactly.

> Note: `dbo.PriveraPosteingang` and `dbo.PriveraInitialUndNeuzugaenge` do not
> exist on INT, so running those processes 500s — a **pre-existing
> data-surface gap**, independent of this work. The date dimension is unaffected
> (same tables either way); it simply lets a user scope away from broken
> processes.

## Design

### Bucketing model — grain modifier (chosen)

Two date fields per source — `import_date`, `export_date` — and a report
**column carries an optional `grain`** (`day` | `week` | `month` | `quarter` |
`year`). The query builder emits the matching truncation. This is the
"conformed time dimension" model: a clean field list (2 fields + a grain
control) that maps 1:1 to the Spec-2 wizard's grain dropdown.

(The rejected alternative was a fixed set of synthetic grain fields —
`import_month`, `import_week`, … — which needs no schema change but clutters the
field list with ~8 date fields.)

### 1. Catalog — synthesize the date fields (`nx_lib/reporting/catalog.py`)

- Add a **pure** helper `date_availability(statconfig_rows, allowed_processes)`
  → `{ "import_date": [proc, …], "export_date": [proc, …] }`, listing the
  processes whose `ImportColumn` / `ExportColumn` is non-null and in scope.
- `fetch_docprocessing_catalog` queries `Statconfig` (NexoraDB —
  `engine_nexora_db`) for `ProcessName, ExportColumn, ImportColumn` and feeds the
  helper, then **appends** two catalog entries:
  - `{field:"import_date", label:_("Import date"), type:"date", aggregable:false, sortable:true, filterable:true, grainable:true, processes:[…]}`
  - same for `export_date` / `_("Export date")`.
- `type:"date"` makes the existing builder filter row auto-mount the flatpickr
  date picker (`renderFilters` already keys on `/date/i.test(type)`).
- A new field attribute **`grainable:true`** flags that the field accepts a
  `grain` (only these date fields have it). Front-end + validator use it; it is
  additive to the existing catalog entry shape.
- Labels are i18n strings (synthetic fields are *not* in `Search_Field_Labels`).

### 2. Definition schema change (`nx_lib/reporting/schema.py`)

- A column entry MAY carry `grain`: `{field, header, agg, grain?}`. Validation:
  - `grain` allowed only when the column's field is **grainable** (a date field
    in the catalog); otherwise `ReportDefinitionError`.
  - `grain ∈ {day, week, month, quarter, year}` else `ReportDefinitionError`.
  - Absent/`null` grain = raw date (= day granularity at display, no
    truncation beyond `CAST AS date`).
- `validate_report_definition(...)` gains a `grainable_fields` set argument,
  derived by callers from the catalog (`{f.field for f in catalog if
  f.get("grainable")}`). All call sites (`_prepare_run`, the AI Surface A/C
  self-validation) pass it.
- Filters and sort do **not** carry grain: a date filter targets the raw date;
  sort references a projected column by its field key (which is already
  bucketed if that column has a grain).

### 3. Query builder — resolve dates per process (`nx_lib/reporting/query.py`)

Pure, still DB-free. For each `cfg` in `process_configs`, build a unified
`resolved` map combining the existing `field_col_maps[proc]` (bare column names)
with **date expressions** derived from `cfg`:

```
date_base(col_expr)  = col_expr if "convert" in col_expr.lower()
                       else f"CAST({col_expr} AS date)"
grain_sql(d, grain)  = {
    None|day : d,
    week     : f"DATEADD(week, DATEDIFF(week, 0, {d}), 0)",   # Monday-anchored, DATEFIRST-independent
    month    : f"DATEFROMPARTS(YEAR({d}), MONTH({d}), 1)",
    quarter  : f"DATEFROMPARTS(YEAR({d}), (DATEPART(quarter,{d})-1)*3+1, 1)",
    year     : f"DATEFROMPARTS(YEAR({d}), 1, 1)",
}[grain]
```

- `import_date` resolves to `grain_sql(date_base(cfg["import_col"]), grain)`,
  `export_date` likewise with `cfg["export_col"]`. The grain for each date column
  comes from `grain_by_field = {c["field"]: c.get("grain") for c in rd["columns"]}`.
- The date expressions are folded into the per-process `resolved` map, so the
  rest of the loop is unchanged: `all_known_fields`, the projection
  (`{expr} AS [field]`), the per-filter LHS, and the subquery-drop check all work
  uniformly — a bare column name and a date expression interpolate identically.
- A process whose `cfg` lacks the relevant column → the date field is absent from
  its `resolved` map → projected `NULL` (display) or the subquery dropped (if a
  date *filter* references it), matching today's behaviour for unmapped fields.
- **Aggregate / GROUP BY path is unchanged**: the inner UNION projects the
  truncated expression `AS [import_date]`; `build_aggregate_sql` groups by the
  alias `[import_date]`. So "documents per month" = metric `doc_count` + a
  dimension column `import_date` with `grain:month`. No change to `semantic.py`.
- A date field appears **at most once per report** (one grain); two grains of the
  same date in one report is unsupported in v1 (alias would collide) — documented.

### 4. Security

Date expressions originate **only** from `Statconfig` (server-side config),
never the client — identical trust model to the existing raw interpolation of
`cfg["table"]` and `cfg["condition"]`. The client supplies only the field key
(whitelisted against the catalog) and the `grain` (validated against a fixed
enum). Only filter *values* remain `?` parameters. The SQL-injection boundary is
preserved.

### 5. Advanced builder UI (`templates/js/_reporting_js.html`)

- When a **grainable** date field is added as a column, its Columns-well row
  gains a small grain `<select>` (Day / Week / Month / Quarter / Year) next to
  the header input. Default = Month (the most common BI grain) — or Day; decide
  in review.
- `buildDefinition` includes `grain` on those columns; `applyDefinition` restores
  it (carry `grain` + `type`/`grainable` into `state.columns`).
- Pivot, chart, CSV/XLSX export, save/share/schedule are **unchanged** — they
  operate on the aliased result column, whose values are simply bucketed.

### 6. AI grounding (free)

The two date fields appear in `_ai_catalog_text` / `_ai_schema_text` as
`type:date` automatically (they are catalog fields), improving grounding for all
AI surfaces. Teaching the AI to emit `grain` is deferred.

## Testing

Pure unit tests (no DB):

- `date_availability`: non-null/null columns, in-/out-of-scope filtering.
- date resolution in `build_table_query`: CONVERT-passthrough vs `CAST AS date`;
  each grain's SQL; a process missing the column → `NULL` projection; a date
  *filter* on a process missing the column → subquery dropped.
- aggregate path: dimension `import_date` `grain:month` + metric `doc_count`
  produces a correct GROUP BY over the bucketed alias.
- schema validator: `grain` on a non-grainable field rejected; bad grain enum
  rejected; absent grain accepted.

Plus an integration smoke test on `/api/reporting/run` with a date filter + a
month-grain group-by (guarded for the RO/data availability already used by the
reporting route tests).

## i18n + docs

- de/fr/it for `Import date`, `Export date`, and the grain labels
  (`Day/Week/Month/Quarter/Year`); run the extract→update→compile cycle and keep
  `test_translations` green.
- CHANGELOG `[Unreleased]`; `docs/howto/reporting.md` (new date-dimension
  subsection); CLAUDE.md reporting blurb (date fields + grain).

## Build order (for the plan)

1. `date_availability` + catalog synthesis (+ unit tests).
2. Query-builder date resolution + grain SQL (+ unit tests) — row path then
   aggregate path.
3. Schema validator `grain` rules (+ unit tests).
4. Advanced UI grain control (build/apply/render).
5. i18n + docs + changelog.
6. Browser verification on INT (filter by import-date range; group `doc_count`
   by `import_date` month) + screenshots.

## Risks / open questions

- **Column type variance.** `ImportTime`, `Export`, etc. may be `datetime`,
  `date`, or `varchar`. `CAST(... AS date)` covers datetime/date; string columns
  must already carry a `CONVERT(...)` in `Statconfig` (the dashboard relies on
  the same assumption). If a string column lacks `CONVERT`, that process's date
  errors at run — same failure mode as the dashboard; acceptable, and the
  process picker lets users avoid it.
- **Default grain** in the Advanced UI: Month vs Day — pick during review.
- **Quarter** grain: include or drop for v1? (Listed; trivial to cut.)
- **Week anchoring**: Monday-anchored via `DATEDIFF(week, 0, d)` (independent of
  `SET DATEFIRST`); confirm that matches stakeholder expectation vs ISO week.

## Spec 2 preview (not built here)

Two-tab page (**Simple** | **Advanced**). Simple = a **library** of ready-made
reports (reusing `dbo.Reports` + `ReportShares` + `Visibility='shared'`; a
"template" = a report shared org-wide) **+** a **guided wizard** (measure →
break down by [incl. this date dimension + grain] → time range → number + chart
**cards** with a "show table" toggle) **+** a small optional "ask AI" helper.
Advanced = today's full builder, untouched. No feature is removed — power
features just move under Advanced. Spec 2 gets its own design → plan cycle and
depends on this date dimension.
