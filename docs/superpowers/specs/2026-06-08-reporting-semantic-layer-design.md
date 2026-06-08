# Reporting Semantic Layer (AI roadmap Phase 4) — Design

- **Date:** 2026-06-08
- **Status:** Approved (brainstorming) — pending implementation plan
- **Branch:** `feature/2.5.63`
- **Roadmap entry:** `docs/design/reporting-ai-assistant.md` §12, "Phase 4 — Semantic
  layer: canonical metrics/dimensions → trustworthy, consistent numbers (`semantic.py`)".

## 1. Problem

Today a reporting **report definition is pure row projection** —
`{columns, filters, sort, rowLimit}` — built by `nx_lib/reporting/query.py`
(the docprocessing `UNION ALL` engine) or `nx_lib/reporting/table_query.py`
(single registered object). There are **no measures or aggregations** in the
definition; any aggregation happens client-side in the pivot view or via the
stdlib stats engine (`nx_lib/reporting/stats.py`).

Consequence: there is no single, blessed definition of a number. Two people
building "average handling time" or "on-time rate" can pick different
columns/filters and get different answers, and the AI assistant has nothing
canonical to anchor to. The semantic layer fixes this by introducing
**canonical metrics and dimensions** so the same metric means the same thing in
the builder, exports, scheduled emails, and the AI.

## 2. Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Ambition | **Full semantic model** (metrics + dimensions + cross-source relationships) as the target, built in slices. |
| Authoring / source of truth | **DB tables + admin UI**, like `dbo.ReportingSources` / `dbo.ReportSchedules`. Permission-gated + audited. |
| "Cross-source relationships" | **Conformed dimensions** — one canonical dimension maps to a column in each source so metrics from different sources can be grouped by the same dimension and compared side-by-side. **No live cross-server SQL JOIN** (sources live on separate SQL servers). |
| Aggregation integration | **Approach A** — extend the existing report definition with optional `metrics`; a new `semantic.py` resolver + aggregate query builder emits `GROUP BY` SQL, reusing the current whitelist + parameterized-value security boundary. Backward compatible. |

## 3. Target architecture (the "full model")

A governed layer with two registries plus an aggregation engine:

- **Metrics** — named aggregations: `aggregation × base field × optional locked
  filters`, bound to a source. Later: derived/ratio metrics.
- **Dimensions** — named groupings. "Conformed" = the same canonical dimension
  maps to a (possibly different) column in each source, so metrics from
  different sources align on it.
- **Aggregation engine** (`nx_lib/reporting/semantic.py`) — resolves canonical
  metric/dimension ids into concrete `(aggregation, column, filters)` against a
  source's whitelisted catalog and produces `GROUP BY` SQL. Cross-source
  side-by-side is composed **app-side** on the shared conformed dimension.

Because "cross-source" is conformed dimensions (not joins), the model collapses
to: **two registries + a resolver + an aggregate SQL builder** — no join graph.

## 4. Decomposition into slices

Each slice is independently shippable and gets its own spec → plan → build.
**This document details Slice 1**; Slices 2–3 are the roadmap to the full model.

- **Slice 1 — Metrics + aggregation engine** *(this spec)*: metrics registry,
  server-side `GROUP BY` engine, definition extension, builder + admin UI + AI
  catalog, validation/audit. Dimensions in this slice are **raw source fields**
  used as group-by (the existing `columns`); no conformance yet.
- **Slice 2 — Conformed dimensions**: `dbo.ReportingDimensions` + per-source
  conformance mappings; group-by by canonical dimension; cross-source
  side-by-side comparison aligned on a conformed dimension; metric/dimension
  glossary injected into AI grounding (delivers part of the parked Tier-3
  glossary goal).
- **Slice 3 — Derived metrics + governance**: ratio/derived metrics (e.g.
  on-time rate = on-time count ÷ total), units/formatting, semantic
  change-audit/versioning, metric-aware Surface C ("explain using blessed
  metrics").

## 5. Slice 1 — detailed design

### 5.1 Data model

New table on `NexoraDB`, created by migration
`sql/_migrations/NexoraDB/0017_create_reporting_metrics.sql`:

`dbo.ReportingMetrics`
- `Code` — stable identifier (the id used in a report definition), unique.
- `SourceId` — the registered source (`dbo.ReportingSources.Code` / code-default
  id) this metric belongs to.
- `Label` — human label.
- `Aggregation` — one of `count | count_distinct | sum | avg | min | max`
  (CHECK-constrained enum).
- `BaseField` — the source column key the aggregation applies to; `NULL` only
  for `count` (i.e. `COUNT(*)`).
- `FilterJson` — **reserved for Slice 3**: optional JSON array of locked filters
  baked into the metric. The column is created in Slice 1 (so no later migration)
  but is **not applied by the engine nor exposed in the admin form** until Slice 3.
- `Description` — optional; surfaced to users + the AI catalog.
- `Format` — `int | decimal | percent` (display hint; no engine effect in S1).
- `Enabled` — bit, default 1.
- `SortOrder` — int, default 100.
- audit columns (`CreatedAt`, `CreatedBy`, `UpdatedAt`, `UpdatedBy`).

Metrics are **DB-only** (no code defaults); the same migration seeds 2–3
worked examples against existing sources so the feature is demonstrable on
first deploy.

### 5.2 Permissions

- New **`reporting.semantic.admin`** — curate metrics (the `/reporting/metrics`
  admin page + write endpoints). Admins seeded via the migration, alongside the
  existing reporting admin seeds.
- **Use** is *inherited*: a metric is usable by anyone who already holds its
  source's `permission`. No new use-grant — using a metric reveals nothing the
  source didn't already.

### 5.3 Definition schema extension (Approach A)

The report definition gains one optional key:

```
metrics: [ { "metric": "<Code>" }, ... ]      // optional; default []
```

Semantics:
- `metrics` **empty/absent** → today's row-projection path, **byte-for-byte
  unchanged** (full backward compatibility; existing saved reports unaffected).
- `metrics` **non-empty** → aggregate path. The existing **`columns` become the
  GROUP BY dimensions**, each `metric` becomes an aggregated output column
  aliased to its `Code`. `filters` apply as `WHERE` (pre-aggregation),
  `sort` may target a group-by column **or** a metric alias, `rowLimit` caps
  the grouped output.

`nx_lib/reporting/schema.py: validate_report_definition` is extended to
validate `metrics`: each referenced `Code` must exist, be enabled, belong to
the report's source, and the caller must hold that source's permission; the
metric's `BaseField` (when set) must be in the source's whitelisted catalog.

### 5.4 Resolver + aggregate builders

New `nx_lib/reporting/semantic.py`:
- `resolve_metrics(metric_refs, registry, catalog_fields) -> [ResolvedMetric]` —
  looks up each Code, returns concrete `{code, aggregation, base_field}`; raises
  on unknown/duplicate/unsafe-code/whitelist miss. (Locked filters are Slice 3.)
- Helpers to emit a single aggregate `SELECT` expression
  (`AGG(<col>) AS [<Code>]`) from a `ResolvedMetric`, with `count` →
  `COUNT(*)`, `count_distinct` → `COUNT(DISTINCT <col>)`.

The two existing builders gain an aggregate branch (taken only when `metrics`
present), reusing their identifier-whitelisting and value-parameterization:
- **`table_query.build_generic_query`**: `SELECT <dim cols>, <agg exprs>
  FROM <obj> WHERE <filters + locked> GROUP BY <dim cols>` (+ `ORDER BY`,
  `TOP cap`).
- **`query.build_table_query`** (docprocessing): build the per-process
  `UNION ALL` subquery as today, then wrap:
  `SELECT <dims>, <agg exprs> FROM (<union>) t GROUP BY <dims>`.

Security boundary is unchanged: dimension and base-field identifiers are
whitelisted against the source catalog; aggregations come from the fixed enum;
locked-filter and user-filter **values** are the only `?` parameters.

### 5.5 Result + downstream

The aggregate query returns grouped rows; the existing grid, Chart.js, pivot,
CSV and Excel export paths render them with **no changes**. Save / Save-as /
Share / Schedule all flow through the report definition, so a metric report is
saved, shared, scheduled and emailed exactly like any other report — no new
plumbing.

### 5.6 UI

- **Builder** (`templates/reporting.html` + `templates/js/_reporting_js.html`):
  a **"Metrics" well** in the right-hand wells column (pick canonical metrics
  for the active source). When ≥1 metric is selected, the **Columns well acts
  as the group-by**; a hint communicates this. No metric selected → the builder
  behaves exactly as today.
- **Admin** (`/reporting/metrics`, gated `reporting.semantic.admin`): a registry
  page mirroring `/reporting/sources` (`templates/reporting_metrics.html` +
  `templates/js/_reporting_metrics_js.html`) — list/add/edit/enable/disable/
  reorder metrics, with the same branded `nx-page-head` header as the other
  reporting pages.

### 5.7 AI integration

`nx_lib/reporting/ai_schema.py` is extended to inject the caller's accessible
**metric catalog** into the serialized schema block, e.g.:

```
METRIC handling_time_avg "Avg handling time" = avg(duration_s) on docprocessing
METRIC doc_count "Document count" = count(*) on docprocessing
```

So Surfaces A (build a definition) and C (agent) can draft definitions that
**reference blessed metrics by Code** — improving accuracy and guaranteeing the
AI's numbers match the builder's. This is also a down payment on the deferred
Tier-3 glossary grounding. No new route; reuses `ReportingAiAudit`.

## 6. Trust & governance

- **Single definition:** the builder and the AI both resolve metrics through
  `semantic.py`, so they cannot diverge — that is the consistency guarantee.
- **Security:** the SQL-injection boundary (whitelist identifiers, parameterize
  values) is identical to the existing builders; the aggregate branch adds only
  fixed-enum aggregation functions.
- **Audit:** metric report runs land in the existing run/AI audit; curating
  metrics is permission-gated and stamped with the audit columns.

## 7. File constellation (nexora-feature checklist)

**New**
- `sql/_migrations/NexoraDB/0017_create_reporting_metrics.sql` — table + CHECK
  enum + `reporting.semantic.admin` permission + admin seeds + 2–3 example
  metrics.
- `nx_lib/reporting/semantic.py` — resolver + aggregate-expression helpers.
- `templates/reporting_metrics.html` + `templates/js/_reporting_metrics_js.html`
  — admin registry page.

**Changed**
- `nx_lib/reporting/query.py`, `nx_lib/reporting/table_query.py` — aggregate
  branch.
- `nx_lib/reporting/schema.py` — validate `metrics`.
- `nx_lib/reporting/sources.py` / registry glue + `nx_lib/views/reporting.py` —
  metrics registry load, `reporting_metrics_admin` route, run-path wiring.
- `nx_lib/reporting/ai_schema.py` — metric catalog serialization.
- `templates/reporting.html`, `templates/js/_reporting_js.html` — Metrics well.
- i18n catalogs (de/fr/it) + `messages.pot`.
- `CHANGELOG.md` ([Unreleased] → Added), `docs/howto/reporting.md`,
  `docs/design/reporting-ai-assistant.md` §12 (mark Slice 1 done).
- `.github/workflows/deploy.yml` `/XF`/`/XD` only if a new **top-level**
  dev-only file is added (none expected — all new files are runtime paths).

## 8. Testing strategy

- **Unit** (pure, DB-free): `semantic.py` resolver (unknown/duplicate/
  unsafe-code/whitelist-miss rejection); aggregate SQL +
  params for both builders (table + docprocessing UNION-wrap); `count` vs
  `count_distinct` vs binary aggs; sort-by-metric alias; backward-compat
  (empty `metrics` → identical SQL to today).
- **Integration**: `/api/reporting/run` with a metric definition (happy path +
  permission/whitelist rejection); metrics-admin CRUD; `reporting.semantic.admin`
  gating; `validate_report_definition` accepts/rejects metric refs.
- **E2e** (Playwright): build a metric report in the browser, run it, export it;
  metrics-admin page loads + adds a metric.
- **AI**: a seeded metric appears in `serialize_schema`; a definition that
  references a metric Code validates.
- **i18n**: `test_translations` stays green (all new strings translated).

## 9. Out of scope (Slice 1)

Conformed dimensions across sources (Slice 2), cross-source side-by-side
comparison (Slice 2), **per-metric locked filters** (`FilterJson` column exists
but is unused — Slice 3), derived/ratio metrics (Slice 3), units/percent
formatting beyond a display hint, semantic versioning/change history (Slice 3),
any live cross-server JOIN (never — conformed dimensions only).

## 10. Open questions

None blocking Slice 1. Deferred to their slices: the exact conformance-mapping
shape (Slice 2), and whether derived metrics are expressed as ratios of two
metrics or a small formula grammar (Slice 3).
