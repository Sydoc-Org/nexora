# Reporting: Pages-Processed Metric + Process-Coverage Marking — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Executor model: Sonnet. Single-session planning run (recon → draft → self-red-team); **every file path, symbol, and quoted snippet below was Grep/Read-verified against `feature/2.5.64` HEAD (`f20466d`) on 2026-07-15** — trust the anchors, but re-Grep before editing since line numbers drift (this plan quotes code, never line numbers). Plan file: `docs/superpowers/plans/2026-07-15-reporting-metrics-process-groupby-marking.md`.

**Goal:** The Simple-tab reporting wizard grows a second measure — **`page_count` = SUM(pagecount)** ("Pages processed") — backed by safe numeric aggregation over the varchar stats columns, metric labels become **DB-localized in all four languages** (new `GermanLabel`/`FrenchLabel`/`ItalianLabel` columns on `dbo.ReportingMetrics`), and both wizard steps get **process-coverage marking**: breakdown chips and measure cards whose field only *some* processes provide show an **"n/m" badge with a tooltip naming the providing processes**, and the chip list reacts to the "Limit to specific processes" picker exactly like the Advanced tab's field list (out-of-scope chips hide, stranded selections prune).

**Architecture:** Metrics are already a zero-code DB registry (`dbo.ReportingMetrics`, admin page `/reporting/metrics`), so the new metric is a data seed in migration `0039` — the only backend query change is in `nx_lib/reporting/query.py`: fields serving as a `sum`/`avg` metric base are projected as `TRY_CAST(<col> AS float)` per UNION-ALL subquery (doc-extraction stat columns are varchar; a raw SUM would implicit-convert and blow up on the first non-numeric cell — TRY_CAST turns bad cells into NULLs, which SUM/AVG ignore). The cast lives in the **docprocessing projection**, NOT in the shared `semantic.metric_select_expr` — that helper also serves PG table sources via `table_query.py`, and `TRY_CAST` is T-SQL-only. Label localization mirrors the `Search_Field_Labels` convention (NULL falls back to the English `Label`), picked per-locale in `nx_lib/views/reporting.py` at the one user-facing serialization point (`api_metrics`); the AI catalogs keep the English `Label` for prompt-grounding stability. The wizard marking is entirely client-side in `templates/js/_reporting_simple_js.html`: the catalog already ships a `processes` list per field, mirroring the Advanced tab's `isFieldAvailable()` convention (a field with no `processes` tag — table sources — is universal).

**Tech Stack:** Python 3.13 / Flask (`nx_lib/views/reporting.py`, `nx_lib/reporting/query.py`), SQL Server migration under `sql/_migrations/NexoraDB/` + `sql/test/schema.sql` mirror, Jinja2 JS partials (`templates/js/_reporting_simple_js.html`, `templates/js/_reporting_metrics_js.html`), `static/css/reporting.css` (`--nx-*` tokens), pytest unit/integration + Playwright e2e (network-stub pattern — TEST env has no Statistics DB), Flask-Babel de/fr/it cycle.

---

## Context an engineer needs (read first)

- **Where you work:** the already-created worktree `.claude/worktrees/plan-reporting-metrics-process-groupby-marking` (absolute: `C:\dev\nexora\.claude\worktrees\plan-reporting-metrics-process-groupby-marking`) on branch `plan/reporting-metrics-process-groupby-marking`, based on `feature/2.5.64` at `f20466d`. Merged back into `feature/2.5.64` after execution. **Commit per task. Do NOT `git push` and do NOT open a PR** — the owner reviews, merges and pushes (the pre-push gate runs the FULL suite incl. Playwright e2e).
- **Python for tests:** this worktree has **no `.venv`**. Run every test command from the worktree root with the main clone's interpreter: `C:\dev\nexora\.venv\Scripts\python -m pytest …`. The dev server (`nx -u`) runs global Python — the `.venv` is test-only.
- **FIRST-COMMIT BLOCKER:** the `sql-migrate-int` / `sql-sync-check` pre-commit hooks run on every commit and this worktree's `env/` has only `*.env.example`. Before the FIRST commit run `Copy-Item C:\dev\nexora\env\INT.env env\INT.env` and `Copy-Item C:\dev\nexora\env\TEST.env env\TEST.env` (gitignored, safe). Only if INT itself is unreachable, fall back to `$env:SQL_SYNC_SKIP="1"` for that one commit — **never** `--no-verify`.
- **Anchor on quoted snippets + function names, NEVER line numbers.** Every step quotes the exact code to find; re-`Grep` it if it has moved.
- **TDD is the house rule.** Backend tasks are strict RED→GREEN. Frontend tasks write the failing Playwright test first; template/CSS cosmetics are verified by the e2e suites plus the live browser pass (Task 10).
- **TEST env has NO Statistics DB** — the docprocessing source can never *run* in e2e. Wizard e2e uses the established network-stub helpers in `tests/e2e/test_reporting_simple.py`: `_login(page, nexora_server)`, `_stub_wiz_catalogs(page, sources, metrics)` (stubs `**/api/reporting/sources` + `**/api/reporting/metrics`; **register before `page.goto`** — catalogs are fetched at page load).
- **TEST DB shape comes from `sql/test/schema.sql` + `seed.sql`** (applied by `scripts/test_db_reset.py`), NOT from migrations. Any `ALTER` in a migration must be mirrored into `sql/test/schema.sql`'s CREATE, or every integration/e2e test touching the table fails on the missing columns (Task 2 does both in one commit).
- **e2e locale is English** — JS/Jinja translations render as msgids in tests, so e2e asserts English text.
- **Jinja template cache is process-lifetime.** The e2e harness spawns a fresh server per run (fine), but restart the dev server (`nx -u -b --loginas:<user>`) before ANY manual browser check.
- **Before running any e2e tier:** `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py` (stale NEXORA_TEST state fails order-dependent e2e tests).
- **Migrations needed: YES — one migration, target number `0039`** (directory currently tops out at `0038_create_api_keys.sql`; **re-list `sql/_migrations/NexoraDB/` at execution time** — the owner has an unrelated validation-user re-map queued that may take 0039 first; bump if taken and adjust the filename everywhere in Task 2). Idempotent (`COL_LENGTH` / `IF NOT EXISTS` guards). `*.sql` is pinned to LF — write it with the Write tool, not shell heredocs. Accented label text is safe: `scripts/db-migrate.py` probes classic-vs-go sqlcmd and forces UTF-8 (`-f 65001`) on classic (the `0011` mojibake lesson is already fixed).
- **The `ALTER TABLE dbo.ReportingMetrics` is DDL** — the pre-commit `sql-sync-check` will regenerate `sql/NexoraDB/Tables/dbo.ReportingMetrics.sql`; `git add` the regenerated dump into the same commit (never hand-edit it).
- **i18n: ONE late pybabel cycle (Task 7).** New msgids land in Tasks 4–6 (three admin-form labels + two tooltip strings); `tests/unit/test_translations.py` is expected RED from Task 4 until Task 7. Use `pytest tests --ignore=tests/e2e --deselect tests/unit/test_translations.py` for the fast tier in between; Task 9 proves the whole suite green. Metric label *values* are DB-driven i18n (the new columns), NOT gettext.
- **Sequencing vs in-flight 2.5.64 work:** PRs #119/#122 are merged and deployed; nothing else is in flight on the reporting partials right now, but the main clone carries two stray untracked files (`package.json`/`package-lock.json` — not this plan's concern; do not commit them). The 2026-07-14 flagship-polish visual contract applies: NEVER rename a `.reporting-*` class; preserve every `data-testid`/`id`; append new CSS rules to `static/css/reporting.css` in place (append-wins); `.nx-rise*` fill-mode stays `backwards`.
- **No new permission.** Metrics visibility stays gated by the existing source permissions (`reporting.source.docprocessing`) and the admin page by `reporting.semantic.admin`. `page_visibility()` untouched. **No `deploy.yml` changes** (only `sql/`, `nx_lib/`, `templates/`, `static/`, `translations/`, `tests/`, `docs/` are touched — all already handled).
- **gitlint:** conventional-commit title, imperative, ≤72 chars, no trailing period; allowed types are exactly `feat,fix,chore,refactor,docs,test,ci,perf,style,build,revert` (use `chore(i18n): …`, `i18n` is NOT a type); non-empty body wrapped ≤100 chars. Commit with `git commit -F - <<'EOF' … EOF` via the Bash tool. If `ruff-format` rewrites a file the first commit attempt fails — `git add -u` and recommit.
- **Commit trailer names the EXECUTING model.** The blocks below use `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` for the declared Sonnet executor; if a different model executes this plan, substitute its real name — never stamp a model that didn't run the work.
- **Remote-session rules:** screenshots to `var/screenshots/` (never the repo root) and `SendUserFile` them proactively as you go; stop at `git commit`.

---

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D-metric (owner) | Add ONLY `page_count` = `SUM(pagecount)` ("Pages processed") now. Distinct-count metrics (creditors, properties, …) and amount totals (gross/net/VAT) were offered and **declined** — they become Owner actions, not tasks. | Locked via interactive Q&A 2026-07-15. |
| D-chips (owner) | Breakdown chips get a coverage **badge + tooltip** AND react to the scope picker (hide at zero coverage, prune stranded selections) — Advanced-tab parity plus visible marking. | Locked. |
| D-labels (owner) | Metric labels localize via **three new nullable columns** on `dbo.ReportingMetrics` (`GermanLabel`/`FrenchLabel`/`ItalianLabel`), NULL falling back to `Label` — the `Search_Field_Labels` convention. | Locked. A German UI must not read "Pages processed" (flagship-polish no-mixing rule). |
| D-measures (delegated) | Measure cards get the same coverage badge, and a metric whose base field NO allowed process provides is **not offered at all**. | Owner said "no preference" — included because `page_count` is itself the partial-coverage case (`col_pagecount` is not mapped for every process), and an unrunnable measure would 400 (`resolve_metrics` raises `metric base field not in catalog`). Reuses the chip helper. |
| D1 | **The numeric cast lives in `query.py`'s per-subquery projection** (`TRY_CAST(<col> AS float)` when the field is a `sum`/`avg` metric base), NOT in `semantic.metric_select_expr`. | `metric_select_expr`/`build_aggregate_sql` are shared with `table_query.py`, which serves PG table sources (MS02) — `TRY_CAST` is T-SQL-only. Table sources aggregate real typed columns and need no cast; the varchar problem is a docprocessing quirk. |
| D2 | **`float`, not `decimal(18,2)`.** | Page counts are small integers — float is exact below 2^53 and keeps JSON/`fmtNumber` trivial. `# ponytail:` comment marks the ceiling: switch to `decimal(18,2)` when money metrics (amount totals) arrive. |
| D3 | **Coverage semantics mirror the Advanced tab's `isFieldAvailable()`:** a field with no `processes` tag (table sources, old stubs) is universal — no badge, never hidden; otherwise coverage = `f.processes ∩ selected scope`, empty selection meaning "all allowed" (the serializer's existing convention). | One convention across both tabs; zero effect on table sources and on every existing e2e stub (their fields carry no `processes` key). |
| D4 | **Scope changes re-render only the chip list** (extracted `renderChipList()` inside `renderBreakdownStep`), never the whole step — time step / Run visibility is untouched. | Re-running `renderBreakdownStep()` would collapse the time step a user already advanced to. No existing e2e touches the scope list (verified), so the extraction is free. |
| D5 | **Only `api_metrics` localizes labels** (via a `_metric_label()` helper). `_accessible_metrics` / `_accessible_curated_sources` (AI catalogs) keep the English `Label`; the admin list returns all four columns verbatim. | The AI grounds on codes with English prompts — stable grounding beats localized prompts. The run response's metric columns carry only `{"field": code}` (client resolves display labels from `state.metricsBySource`), so the run path needs nothing. `_metrics_for_source` (used by the scheduler outside request context) carries no label — no `get_locale()` outside a request. |
| D6 | **Migration `0039` also backfills `doc_count` and `workitem_count` translations** and seeds `page_count` with all four labels, `Format='int'`, `SortOrder=30`, enabled. | One migration, one review. `workitem_count` is disabled but still visible in the admin table. |
| D7 | **`sql/test/schema.sql` gets the three columns in the same commit as the migration.** | The TEST DB is rebuilt from `schema.sql`, not migrations — without the mirror every ReportingMetrics integration/e2e test breaks on the INSERT/SELECT of the new columns. |
| D8 | **Advanced tab is untouched.** | The user's words: the Advanced tab already "does good" (its scope filtering). Its metrics dropdown offering a zero-coverage metric is a pre-existing edge the Simple-tab hiding does not share — noted as Owner action 5, YAGNI here. |

---

## Owner actions (not for the executor)

1. **Review, merge `plan/reporting-metrics-process-groupby-marking` back into `feature/2.5.64`, and push** (this session is commit-only; your push runs the full pre-push gate).
2. **`col_pagecount` coverage on INT/PROD.** `page_count` only counts pages from processes whose `SearchConfig.col_pagecount` is mapped. If Task 10 shows the measure hidden (no process maps it) or covering too few processes, map `col_pagecount` for the relevant `SearchConfig` rows — env-specific data config, not a migration. The measure card's badge shows exactly the current coverage.
3. **Distinct-count metrics (declined this round).** When wanted, they are pure data: add rows at `/reporting/metrics` (e.g. `distinct_creditors` = `count_distinct` over `crdname`, `distinct_properties` over `propertynr`, `distinct_validationusers` over `validationuser`) — zero code after this plan; the coverage badges apply automatically.
4. **Amount totals (declined this round).** The TRY_CAST infrastructure from Task 1 makes `SUM(grossamount)` etc. one registry row away — but decide data quality first (are extracted amounts clean numbers?) and switch the cast to `decimal(18,2)` for money (see the `ponytail:` comment in `query.py`).
5. **Advanced tab metrics dropdown** still offers a metric whose base field the current scope can't provide (run then 400s with a translated message). Say the word if you want the Simple-tab hiding mirrored there.
6. **Metric label wording.** Shipped: "Pages processed" / "Verarbeitete Seiten" / "Pages traitées" / "Pagine elaborate". Re-wording is a data-only UPDATE (or the admin form).

---

# PHASE 1 — Backend: safe numeric aggregation

### Task 1: TRY_CAST projection for sum/avg metric bases

**Files:**
- Modify: `nx_lib/reporting/query.py` (one set-comprehension + a two-line projection branch)
- Test: `tests/unit/test_reporting_query.py` (append)

**Interfaces:**
- Consumes: `resolved_metrics` (already passed to `build_table_query` — `[{code, aggregation, base_field}]` from `semantic.resolve_metrics`).
- Produces: per-subquery projection `TRY_CAST(<actual col> AS float) AS [field]` whenever `field` is the `base_field` of a `sum`/`avg` metric; everything else (dims, `count_distinct`/`min`/`max` bases, NULL fallback for processes lacking the field) is byte-identical. Later tasks rely on nothing else from this task — it makes the `0039`-seeded `page_count` metric actually runnable.

- [ ] **Step 1 — Write the failing unit tests.** Append to `tests/unit/test_reporting_query.py` (module fixtures `PROCESS_CONFIGS` / `FIELD_COL_MAPS` / `_rd` already exist at the top; `pages` is deliberately mapped only in `acme.inv` as `PageCount`):

```python
def test_sum_metric_base_projected_with_try_cast():
    # Doc-extraction stat columns are varchar: SUM over the raw column would
    # implicit-convert and fail on the first non-numeric cell. sum/avg bases
    # are therefore projected as TRY_CAST(col AS float) per subquery (bad
    # cells become NULL, which SUM/AVG ignore).
    rd = _rd(columns=[{"field": "doctype"}], filters=[], sort=[])
    resolved = [{"code": "page_count", "aggregation": "sum", "base_field": "pages"}]
    sql, params = build_table_query(
        rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100, resolved_metrics=resolved
    )
    assert "TRY_CAST(PageCount AS float) AS [pages]" in sql  # acme.inv maps it
    assert "NULL AS [pages]" in sql                          # acme.hr doesn't
    assert "SUM([pages]) AS [page_count]" in sql
    assert "GROUP BY [doctype]" in sql


def test_avg_metric_base_projected_with_try_cast():
    rd = _rd(columns=[], filters=[], sort=[])
    resolved = [{"code": "avg_pages", "aggregation": "avg", "base_field": "pages"}]
    sql, _params = build_table_query(
        rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100, resolved_metrics=resolved
    )
    assert "TRY_CAST(PageCount AS float) AS [pages]" in sql
    assert "AVG([pages]) AS [avg_pages]" in sql


def test_count_distinct_base_is_not_cast():
    # Only sum/avg need numbers; count_distinct/min/max keep the raw column.
    rd = _rd(columns=[{"field": "doctype"}], filters=[], sort=[])
    resolved = [{"code": "d_status", "aggregation": "count_distinct", "base_field": "status"}]
    sql, _params = build_table_query(
        rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100, resolved_metrics=resolved
    )
    assert "TRY_CAST" not in sql
    assert "COUNT(DISTINCT [status]) AS [d_status]" in sql
```

- [ ] **Step 2 — Run, expect RED:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_query.py -k "try_cast or not_cast" -q`
Expected: 2 failed (`TRY_CAST(PageCount AS float)` not in sql), 1 passed (`test_count_distinct_base_is_not_cast` — pins existing behavior; if IT fails, stop and investigate)

- [ ] **Step 3 — Implement.** In `nx_lib/reporting/query.py`, inside `build_table_query`, find:

```python
    metric_base_fields = [m["base_field"] for m in (resolved_metrics or []) if m.get("base_field")]
    # Fields to project in each subquery: the group-by dims plus any metric base
    # fields (deduped, order-stable). For the row path this is just `columns`.
    projected_fields = list(dict.fromkeys(columns + metric_base_fields))
```

Replace with:

```python
    metric_base_fields = [m["base_field"] for m in (resolved_metrics or []) if m.get("base_field")]
    # Fields to project in each subquery: the group-by dims plus any metric base
    # fields (deduped, order-stable). For the row path this is just `columns`.
    projected_fields = list(dict.fromkeys(columns + metric_base_fields))

    # SUM/AVG bases are projected as TRY_CAST(col AS float): the doc-extraction
    # stat columns are varchar, and a raw SUM would implicit-convert and fail on
    # the first non-numeric cell — TRY_CAST yields NULL there and SUM/AVG ignore
    # NULLs. T-SQL only, which is fine: this builder targets the SQL Server
    # statistics engine (table sources aggregate typed columns in table_query).
    # ponytail: float is exact for page counts (< 2^53); switch to
    # decimal(18,2) when money metrics arrive.
    numeric_bases = {
        m["base_field"]
        for m in (resolved_metrics or [])
        if m.get("base_field") and m["aggregation"] in ("sum", "avg")
    }
```

Then find (the per-subquery projection):

```python
                actual = proj_resolved.get(field)
                if actual:
                    select_exprs.append(f"{actual} AS [{field}]")
                else:
                    select_exprs.append(f"NULL AS [{field}]")
```

Replace with:

```python
                actual = proj_resolved.get(field)
                if actual and field in numeric_bases:
                    select_exprs.append(f"TRY_CAST({actual} AS float) AS [{field}]")
                elif actual:
                    select_exprs.append(f"{actual} AS [{field}]")
                else:
                    select_exprs.append(f"NULL AS [{field}]")
```

- [ ] **Step 4 — Run GREEN + the whole file:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_query.py -q`
Expected: all passed

- [ ] **Step 5 — Commit:**

```bash
git add nx_lib/reporting/query.py tests/unit/test_reporting_query.py
git commit -F - <<'EOF'
feat(reporting): TRY_CAST sum/avg metric bases to float per subquery

Fields serving as the base of a sum/avg canonical metric are projected
as TRY_CAST(<col> AS float) in each docprocessing UNION-ALL subquery.
The stat columns are varchar, so a raw SUM would implicit-convert and
fail on the first non-numeric cell; TRY_CAST maps bad cells to NULL,
which SUM/AVG ignore. Deliberately in the docprocessing projection and
NOT in semantic.metric_select_expr, which is shared with the (possibly
PostgreSQL) table-source builder where TRY_CAST does not exist.
Groundwork for the page_count (pages processed) metric seeded in 0039.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 2 — Migration: localized metric labels + page_count seed

### Task 2: Migration 0039 + TEST-schema mirror

**Files:**
- Create: `sql/_migrations/NexoraDB/0039_metric_labels_and_page_count.sql` (re-check the number is free first)
- Modify: `sql/test/schema.sql` (three columns in the `ReportingMetrics` CREATE)
- Expect regenerated: `sql/NexoraDB/Tables/dbo.ReportingMetrics.sql` (`git add` it when the hook flags drift — never hand-edit)

**Interfaces:**
- Produces: columns `GermanLabel`/`FrenchLabel`/`ItalianLabel` (`NVARCHAR(120) NULL`) on `dbo.ReportingMetrics`; translated labels for `doc_count`/`workitem_count`; enabled row `page_count` (`sum` over `pagecount`, Format `int`, SortOrder 30) with all four labels. Tasks 3–6 depend on the columns and the row.

- [ ] **Step 1 — Re-verify the number is free:** list `sql/_migrations/NexoraDB/`; the directory currently tops out at `0038_create_api_keys.sql`. If `0039_*` exists (the owner has an unrelated validation-user re-map queued), use the next integer and adjust the filename in this task and its commit message.
- [ ] **Step 2 — Write the migration** (Write tool — UTF-8, LF; accented text is safe, `db-migrate.py` forces UTF-8 on classic sqlcmd and go-sqlcmd is natively UTF-8):

```sql
-- 0039_metric_labels_and_page_count.sql
-- Localized labels for canonical metrics + the "Pages processed" metric.
--
-- dbo.ReportingMetrics gains German/French/Italian label columns (mirrors
-- Search_Field_Labels: NULL falls back to the English Label). Backfills the
-- two existing rows and seeds page_count = SUM(pagecount) on docprocessing.
-- The query builder projects sum/avg bases as TRY_CAST(col AS float), so a
-- non-numeric cell or a process without col_pagecount contributes NULL --
-- i.e. nothing -- to the sum. Idempotent.

IF COL_LENGTH(N'dbo.ReportingMetrics', N'GermanLabel') IS NULL
BEGIN
    ALTER TABLE dbo.ReportingMetrics ADD
        GermanLabel  NVARCHAR(120) NULL,
        FrenchLabel  NVARCHAR(120) NULL,
        ItalianLabel NVARCHAR(120) NULL;
END;
GO

UPDATE dbo.ReportingMetrics
SET GermanLabel  = N'Anzahl Dokumente',
    FrenchLabel  = N'Nombre de documents',
    ItalianLabel = N'Numero di documenti'
WHERE Code = 'doc_count' AND GermanLabel IS NULL;

UPDATE dbo.ReportingMetrics
SET GermanLabel  = N'Anzahl Workitems (eindeutig)',
    FrenchLabel  = N'Nombre de workitems (distincts)',
    ItalianLabel = N'Numero di workitem (distinti)'
WHERE Code = 'workitem_count' AND GermanLabel IS NULL;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics WHERE Code = 'page_count')
    INSERT INTO dbo.ReportingMetrics
        (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel,
         Aggregation, BaseField, Description, Format, SortOrder)
    VALUES
        ('page_count', 'docprocessing', 'Pages processed',
         N'Verarbeitete Seiten', N'Pages traitées', N'Pagine elaborate',
         'sum', 'pagecount',
         'Total scanned pages in scope (sum of the per-document page count; only processes with a mapped pagecount field contribute)',
         'int', 30);
GO
```

- [ ] **Step 3 — Mirror into the TEST schema.** In `sql/test/schema.sql`, inside the `CREATE TABLE dbo.ReportingMetrics` block (comment above it reads `-- Canonical metrics registry (mirrors 0017_create_reporting_metrics.sql).`), find:

```sql
        Label        NVARCHAR(120) NOT NULL,
        Aggregation  NVARCHAR(16) NOT NULL,
```

Replace with:

```sql
        Label        NVARCHAR(120) NOT NULL,
        GermanLabel  NVARCHAR(120) NULL,
        FrenchLabel  NVARCHAR(120) NULL,
        ItalianLabel NVARCHAR(120) NULL,
        Aggregation  NVARCHAR(16) NOT NULL,
```

Also update the comment above the CREATE to `-- Canonical metrics registry (mirrors 0017_create_reporting_metrics.sql + 0039 label columns).`

- [ ] **Step 4 — Reset the TEST DB so later tasks' integration tests see the new columns:**

Run: `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py`
Expected: exits 0

- [ ] **Step 5 — Commit** (the `sql-migrate-int` hook auto-applies `0039` to INT; the ALTER is DDL, so `sql-sync-check` regenerates `sql/NexoraDB/Tables/dbo.ReportingMetrics.sql` — `git add` the regenerated dump and recommit if the hook flags it):

```bash
git add sql/_migrations/NexoraDB/0039_metric_labels_and_page_count.sql sql/test/schema.sql
git commit -F - <<'EOF'
feat(db): localized metric labels + page_count metric (0039)

dbo.ReportingMetrics gains nullable GermanLabel/FrenchLabel/
ItalianLabel columns (Search_Field_Labels convention: NULL falls back
to the English Label), backfills doc_count and the disabled
workitem_count, and seeds the enabled page_count metric --
SUM(pagecount) on docprocessing, Format int, SortOrder 30, labels in
all four languages. sql/test/schema.sql mirrors the new columns (the
TEST DB is rebuilt from schema.sql, not migrations). Idempotent.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

**Verify:** on INT (read-only), `SELECT Code, Label, GermanLabel FROM dbo.ReportingMetrics ORDER BY SortOrder` → three rows, `page_count | Pages processed | Verarbeitete Seiten` present.

---

# PHASE 3 — Localized labels: backend plumbing + admin UI

### Task 3: Locale-aware `api_metrics` + admin CRUD columns

**Files:**
- Modify: `nx_lib/views/reporting.py` (7 surgical edits, all quoted below)
- Test: `tests/integration/test_reporting_metrics_routes.py` (append)

**Interfaces:**
- Produces: `_load_db_metrics()` entries gain `label_de`/`label_fr`/`label_it`; new helper `_metric_label(m)` (locale-aware with English fallback, request-context only); `/api/reporting/metrics` serves the localized `label`; the admin list returns `labelDe`/`labelFr`/`labelIt`; admin create/update accept the same three optional keys. Task 4's form and Task 6's wizard consume these.
- Consumes: migration `0039` columns (Task 2). `get_locale` is already imported in the module (`from ..i18n import get_locale`).

- [ ] **Step 1 — Write the failing integration tests.** Append to `tests/integration/test_reporting_metrics_routes.py` (the file already uses the `admin_client` fixture and this create/cleanup pattern — see `test_metrics_api_groups_by_accessible_source`):

```python
def test_admin_metrics_roundtrip_localized_labels(admin_client):
    create = admin_client.post(
        "/api/reporting/admin/metrics",
        json={
            "code": "api_l10n_metric",
            "sourceId": "docprocessing",
            "label": "Pages processed",
            "labelDe": "Verarbeitete Seiten",
            "labelFr": "Pages traitées",
            "aggregation": "sum",
            "baseField": "pagecount",
            "format": "int",
        },
    )
    assert create.status_code == 200
    mid = create.get_json()["id"]
    try:
        rows = admin_client.get("/api/reporting/admin/metrics").get_json()["rows"]
        row = next(r for r in rows if r["code"] == "api_l10n_metric")
        assert row["labelDe"] == "Verarbeitete Seiten"
        assert row["labelFr"] == "Pages traitées"
        assert row["labelIt"] is None
        upd = admin_client.put(
            f"/api/reporting/admin/metrics/{mid}",
            json={
                "code": "api_l10n_metric",
                "sourceId": "docprocessing",
                "label": "Pages processed",
                "labelDe": "Verarbeitete Seiten",
                "labelIt": "Pagine elaborate",
                "aggregation": "sum",
                "baseField": "pagecount",
            },
        )
        assert upd.status_code == 200
        rows = admin_client.get("/api/reporting/admin/metrics").get_json()["rows"]
        row = next(r for r in rows if r["code"] == "api_l10n_metric")
        assert row["labelIt"] == "Pagine elaborate"
        assert row["labelFr"] is None  # update replaces all three
    finally:
        admin_client.delete(f"/api/reporting/admin/metrics/{mid}")


def test_metrics_api_label_follows_session_locale_with_fallback(admin_client):
    create = admin_client.post(
        "/api/reporting/admin/metrics",
        json={
            "code": "api_l10n_pick",
            "sourceId": "docprocessing",
            "label": "Pages processed",
            "labelDe": "Verarbeitete Seiten",
            "aggregation": "sum",
            "baseField": "pagecount",
        },
    )
    assert create.status_code == 200
    mid = create.get_json()["id"]
    try:
        with admin_client.session_transaction() as sess:
            sess["locale"] = "de"
        data = admin_client.get("/api/reporting/metrics").get_json()
        entry = next(m for m in data["docprocessing"] if m["code"] == "api_l10n_pick")
        assert entry["label"] == "Verarbeitete Seiten"
        # No Italian translation -> falls back to the English Label.
        with admin_client.session_transaction() as sess:
            sess["locale"] = "it"
        data = admin_client.get("/api/reporting/metrics").get_json()
        entry = next(m for m in data["docprocessing"] if m["code"] == "api_l10n_pick")
        assert entry["label"] == "Pages processed"
    finally:
        with admin_client.session_transaction() as sess:
            sess["locale"] = "en"
        admin_client.delete(f"/api/reporting/admin/metrics/{mid}")
```

- [ ] **Step 2 — Run, expect RED** (unknown `labelDe` key is ignored today, so the first failure is `row["labelDe"]` KeyError):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/integration/test_reporting_metrics_routes.py -k l10n -q`
Expected: `2 failed`

- [ ] **Step 3 — Implement in `nx_lib/views/reporting.py`.** Seven find/replace edits:

(a) In `_load_db_metrics`, find:

```python
        cur.execute(
            "SELECT Code, SourceId, Label, Aggregation, BaseField, Description, "
            "Format, Enabled, SortOrder FROM dbo.ReportingMetrics WHERE Enabled = 1"
        )
        out = {}
        for r in cur.fetchall():
            out[r.Code] = {
                "code": r.Code,
                "source_id": r.SourceId,
                "label": r.Label,
```

Replace with:

```python
        cur.execute(
            "SELECT Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, "
            "Aggregation, BaseField, Description, Format, Enabled, SortOrder "
            "FROM dbo.ReportingMetrics WHERE Enabled = 1"
        )
        out = {}
        for r in cur.fetchall():
            out[r.Code] = {
                "code": r.Code,
                "source_id": r.SourceId,
                "label": r.Label,
                "label_de": r.GermanLabel,
                "label_fr": r.FrenchLabel,
                "label_it": r.ItalianLabel,
```

(b) Directly below `_load_db_metrics` (before `def _metrics_for_source(source_id):`), insert:

```python
_METRIC_LABEL_ATTRS = {"de": "label_de", "fr": "label_fr", "it": "label_it"}


def _metric_label(m):
    """Locale-aware metric label with English fallback (mirrors the
    Search_Field_Labels convention: a missing translation falls back to Label).

    Request-context only (reads get_locale()); non-request callers — the AI
    catalogs and the scheduler's _metrics_for_source — keep using m['label'].
    """
    attr = _METRIC_LABEL_ATTRS.get(str(get_locale()))
    return (m.get(attr) if attr else None) or m["label"]
```

(c) In `api_metrics`, find:

```python
        out.setdefault(sid, []).append(
            {
                "code": m["code"],
                "label": m["label"],
```

Replace with:

```python
        out.setdefault(sid, []).append(
            {
                "code": m["code"],
                "label": _metric_label(m),
```

(d) In `api_admin_metrics_list`, find:

```python
        cur.execute(
            "SELECT MetricID, Code, SourceId, Label, Aggregation, BaseField, "
            "Description, Format, Enabled, SortOrder FROM dbo.ReportingMetrics "
            "ORDER BY SortOrder, Label"
        )
```

Replace with:

```python
        cur.execute(
            "SELECT MetricID, Code, SourceId, Label, GermanLabel, FrenchLabel, "
            "ItalianLabel, Aggregation, BaseField, Description, Format, Enabled, "
            "SortOrder FROM dbo.ReportingMetrics ORDER BY SortOrder, Label"
        )
```

and, in the same function's row dict, find:

```python
                "id": r.MetricID,
                "code": r.Code,
                "sourceId": r.SourceId,
                "label": r.Label,
```

Replace with:

```python
                "id": r.MetricID,
                "code": r.Code,
                "sourceId": r.SourceId,
                "label": r.Label,
                "labelDe": r.GermanLabel,
                "labelFr": r.FrenchLabel,
                "labelIt": r.ItalianLabel,
```

(e) In `api_admin_metrics_create`, find:

```python
            "INSERT INTO dbo.ReportingMetrics "
            "(Code, SourceId, Label, Aggregation, BaseField, Format, Enabled, SortOrder) "
            "OUTPUT INSERTED.MetricID VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
```

Replace with:

```python
            "INSERT INTO dbo.ReportingMetrics "
            "(Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, "
            "Aggregation, BaseField, Format, Enabled, SortOrder) "
            "OUTPUT INSERTED.MetricID VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
```

(f) In `api_admin_metrics_update`, find:

```python
            "UPDATE dbo.ReportingMetrics SET Code=?, SourceId=?, Label=?, Aggregation=?, "
            "BaseField=?, Format=?, Enabled=?, SortOrder=?, UpdatedAt=SYSUTCDATETIME() "
            "WHERE MetricID=?",
```

Replace with:

```python
            "UPDATE dbo.ReportingMetrics SET Code=?, SourceId=?, Label=?, GermanLabel=?, "
            "FrenchLabel=?, ItalianLabel=?, Aggregation=?, BaseField=?, Format=?, "
            "Enabled=?, SortOrder=?, UpdatedAt=SYSUTCDATETIME() WHERE MetricID=?",
```

(g) In `_metric_insert_params`, find:

```python
    return (
        p["code"].strip(),
        p["sourceId"].strip(),
        p["label"].strip(),
        p["aggregation"].strip(),
```

Replace with:

```python
    return (
        p["code"].strip(),
        p["sourceId"].strip(),
        p["label"].strip(),
        (p.get("labelDe") or "").strip() or None,
        (p.get("labelFr") or "").strip() or None,
        (p.get("labelIt") or "").strip() or None,
        p["aggregation"].strip(),
```

- [ ] **Step 4 — Run GREEN + collateral:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/integration/test_reporting_metrics_routes.py tests/integration/test_reporting_routes.py -q`
Expected: all passed

- [ ] **Step 5 — Commit:**

```bash
git add nx_lib/views/reporting.py tests/integration/test_reporting_metrics_routes.py
git commit -F - <<'EOF'
feat(reporting): serve locale-aware metric labels

_load_db_metrics reads the new GermanLabel/FrenchLabel/ItalianLabel
columns; a _metric_label helper picks the session locale's label with
English fallback (Search_Field_Labels convention) and /api/reporting/
metrics serves it, so the wizard measure cards and the Advanced
metrics well render translated names. Admin list/create/update round-
trip the three optional labelDe/labelFr/labelIt keys. The AI catalogs
and the scheduler path deliberately keep the English Label (prompt-
grounding stability; no get_locale() outside a request).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

### Task 4: Admin form — three localized-label inputs

**Files:**
- Modify: `templates/reporting_metrics.html` (three inputs)
- Modify: `templates/js/_reporting_metrics_js.html` (payload/fillForm/reset)
- Test: `tests/e2e/test_reporting_metrics.py` (extend the existing form test)

**Interfaces:**
- Consumes: Task 3's `labelDe`/`labelFr`/`labelIt` API keys.
- Produces: form fields `rpmLabelDe`/`rpmLabelFr`/`rpmLabelIt` (`data-testid` `rpm-label-de`/`-fr`/`-it`). **New msgids** ("German label", "French label", "Italian label") — `tests/unit/test_translations.py` goes RED here; expected until Task 7.

- [ ] **Step 1 — Extend the failing e2e.** In `tests/e2e/test_reporting_metrics.py`, inside `test_metrics_admin_add_and_list`, find:

```python
    page.fill('[data-testid="rpm-label"]', "E2E Metric")
```

Replace with:

```python
    page.fill('[data-testid="rpm-label"]', "E2E Metric")
    page.fill('[data-testid="rpm-label-de"]', "E2E Metrik")
```

and find:

```python
    expect(page.locator('[data-testid="reporting-metrics-rows"]')).to_contain_text("e2e_metric")
```

Replace with:

```python
    expect(page.locator('[data-testid="reporting-metrics-rows"]')).to_contain_text("e2e_metric")
    # The German label round-trips through save -> list -> edit form.
    page.locator('[data-testid="reporting-metrics-rows"] tr', has_text="e2e_metric").get_by_text(
        "Edit"
    ).click()
    expect(page.locator('[data-testid="rpm-label-de"]')).to_have_value("E2E Metrik")
```

Run:
```
C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py
C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_metrics.py::test_metrics_admin_add_and_list -q
```
Expected: `1 failed` (no `rpm-label-de` element)

- [ ] **Step 2 — Template.** In `templates/reporting_metrics.html`, find:

```html
        <label>{{ _("Label") }}<input id="rpmLabel" class="reporting-input" data-testid="rpm-label"></label>
```

Replace with:

```html
        <label>{{ _("Label") }}<input id="rpmLabel" class="reporting-input" data-testid="rpm-label"></label>
        <label>{{ _("German label") }}<input id="rpmLabelDe" class="reporting-input" data-testid="rpm-label-de"></label>
        <label>{{ _("French label") }}<input id="rpmLabelFr" class="reporting-input" data-testid="rpm-label-fr"></label>
        <label>{{ _("Italian label") }}<input id="rpmLabelIt" class="reporting-input" data-testid="rpm-label-it"></label>
```

- [ ] **Step 3 — JS partial.** In `templates/js/_reporting_metrics_js.html`:

(a) In `fillForm`, find:

```js
    document.getElementById('rpmLabel').value = r.label;
```

Replace with:

```js
    document.getElementById('rpmLabel').value = r.label;
    document.getElementById('rpmLabelDe').value = r.labelDe || '';
    document.getElementById('rpmLabelFr').value = r.labelFr || '';
    document.getElementById('rpmLabelIt').value = r.labelIt || '';
```

(b) In `reset`, find:

```js
    ['rpmCode', 'rpmLabel', 'rpmBaseField']
      .forEach(function (i) { document.getElementById(i).value = ''; });
```

Replace with:

```js
    ['rpmCode', 'rpmLabel', 'rpmLabelDe', 'rpmLabelFr', 'rpmLabelIt', 'rpmBaseField']
      .forEach(function (i) { document.getElementById(i).value = ''; });
```

(c) In `payload`, find:

```js
      label: val('rpmLabel'),
```

Replace with:

```js
      label: val('rpmLabel'),
      labelDe: val('rpmLabelDe') || null,
      labelFr: val('rpmLabelFr') || null,
      labelIt: val('rpmLabelIt') || null,
```

- [ ] **Step 4 — Run GREEN + the whole file:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_metrics.py -q`
Expected: all passed

- [ ] **Step 5 — Commit:**

```bash
git add templates/reporting_metrics.html templates/js/_reporting_metrics_js.html tests/e2e/test_reporting_metrics.py
git commit -F - <<'EOF'
feat(reporting): localized-label inputs on the metrics admin form

Three optional inputs (German/French/Italian label) on the
/reporting/metrics form, wired through payload/fillForm/reset to the
labelDe/labelFr/labelIt API keys from the previous commit. e2e extends
the add-and-list test with a German-label round-trip through the edit
form. test_translations stays red on the three new msgids until the
late pybabel cycle.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 4 — Wizard: process-coverage badges + scope filtering

### Task 5: Breakdown chips — badge, tooltip, scope reactivity

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (I18N entries + `renderBreakdownStep` rework)
- Modify: `static/css/reporting.css` (one appended rule)
- Test: `tests/e2e/test_reporting_simple.py` (stub data + two new tests)

**Interfaces:**
- Consumes: catalog fields' existing `processes` arrays (`/api/reporting/sources`), `state.wiz.scopeProcs` (empty = all allowed — the serializer's convention).
- Produces: badge element `span.reporting-simple-chip-cov` inside partially-covered chips (`textContent` like `1/2`, chip `title` names the providing processes); chips with zero coverage under the selected scope are not rendered and stranded selections are pruned; inner function `renderChipList()` re-invoked from the scope checkbox handler (Task 6 reuses the badge CSS + the `I18N.measureCoverage` string added here). **Two new msgids** — `test_translations` stays RED until Task 7.

- [ ] **Step 1 — Write the failing e2e tests.** Append to `tests/e2e/test_reporting_simple.py` (after the existing `_stub_wiz_catalogs` helper block; `_login`, `expect`, `json` are already module-level):

```python
# ---------------------------------------------------------------------------
# Process-coverage marking: chips/measures whose field only some processes
# provide get an "n/m" badge; the chip list follows the scope picker like the
# Advanced tab's field list. Fields WITHOUT a `processes` tag are universal
# (table sources; also why the older wizard stubs above are unaffected).
# ---------------------------------------------------------------------------

COV_WIZ_SOURCES = [{
    "id": "docprocessing", "label": "Document processing", "kind": "curated",
    "processes": ["acme.inv", "acme.hr"],
    "fields": [
        {"field": "import_date", "label": "Import date", "type": "date",
         "grainable": True, "filterable": True,
         "processes": ["acme.inv", "acme.hr"]},
        {"field": "doctype", "label": "Document Type", "type": "string",
         "grainable": False, "filterable": True,
         "processes": ["acme.inv", "acme.hr"]},
        {"field": "propertynr", "label": "Property No.", "type": "string",
         "grainable": False, "filterable": True,
         "processes": ["acme.inv"]},
    ],
}]
COV_WIZ_METRICS = {
    "docprocessing": [
        {"code": "doc_count", "label": "Cov count stub", "aggregation": "count",
         "baseField": None, "format": "int"},
    ]
}


def test_wizard_chip_coverage_badge(nexora_server, page):
    """A chip whose field only some selected processes provide shows an n/m
    badge and a tooltip naming the providers; full-coverage chips stay plain."""
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, COV_WIZ_SOURCES, COV_WIZ_METRICS)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Cov count stub").click()
    bklist = page.get_by_test_id("rs-breakdown-list")
    prop = bklist.locator('[data-bd-field="propertynr"]')
    expect(prop.locator(".reporting-simple-chip-cov")).to_have_text("1/2")
    assert "acme.inv" in prop.get_attribute("title")
    expect(
        bklist.locator('[data-bd-field="doctype"] .reporting-simple-chip-cov')
    ).to_have_count(0)
    expect(
        bklist.locator('[data-bd-field="import_date"] .reporting-simple-chip-cov')
    ).to_have_count(0)


def test_wizard_scope_filters_chips_and_prunes_selection(nexora_server, page):
    """Unticking the only process that provides a field hides its chip and
    drops it from the selected breakdowns (Advanced-tab parity); re-ticking
    brings the chip back (unselected)."""
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, COV_WIZ_SOURCES, COV_WIZ_METRICS)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Cov count stub").click()
    bklist = page.get_by_test_id("rs-breakdown-list")
    bklist.locator('[data-bd-field="propertynr"]').click()
    expect(bklist.locator('[data-bd-field="propertynr"]')).to_have_class(
        re.compile(r"\bis-selected\b")
    )
    page.locator("#rsScopeWrap summary").click()
    page.get_by_test_id("rs-scope-list").locator('input[value="acme.inv"]').uncheck()
    expect(bklist.locator('[data-bd-field="propertynr"]')).to_have_count(0)
    expect(bklist.locator('[data-bd-field="doctype"]')).to_be_visible()
    page.get_by_test_id("rs-scope-list").locator('input[value="acme.inv"]').check()
    prop = bklist.locator('[data-bd-field="propertynr"]')
    expect(prop).to_be_visible()
    expect(prop).not_to_have_class(re.compile(r"\bis-selected\b"))
```

(`re` is already imported at the top of the file — verify with Grep, it is used by other tests; if not, add `import re`.)

- [ ] **Step 2 — Reset DB, run RED:**

Run:
```
C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py
C:\dev\nexora\.venv\Scripts\python -m pytest "tests/e2e/test_reporting_simple.py::test_wizard_chip_coverage_badge" "tests/e2e/test_reporting_simple.py::test_wizard_scope_filters_chips_and_prunes_selection" -q
```
Expected: `2 failed` (no `.reporting-simple-chip-cov`; chip still present after untick)

- [ ] **Step 3 — Add the I18N strings.** In `templates/js/_reporting_simple_js.html`, find (the last I18N entry):

```js
    copied: {{ _("Copied")|tojson }}
  };
```

Replace with:

```js
    copied: {{ _("Copied")|tojson }},
    chipCoverage: {{ _("Only {n} of {m} selected processes provide this field — documents from the other processes show an empty value here. Provided by:")|tojson }},
    measureCoverage: {{ _("Only {n} of {m} processes provide this field — the measure only counts documents from these processes:")|tojson }}
  };
```

- [ ] **Step 4 — Rework `renderBreakdownStep`.** In the same file, replace the ENTIRE function (find `function renderBreakdownStep() {` and replace through its closing brace — the function currently ends with the scope-picker block whose last lines are `if (!prior.length) state.wiz.scopeProcs = procs.slice();` / `updateScopeBadge();` / `}` / `}`) with:

```js
  function renderBreakdownStep() {
    el('rsStepBreakdown').hidden = false;
    el('rsStepTime').hidden = true;
    el('rsWizardRun').hidden = true;
    var w = state.wiz;
    if (!Array.isArray(w.breakdowns)) w.breakdowns = [];
    var allProcs = w.source.processes || [];

    function isSelected(bd) {
      if (bd.kind === 'none') return w.breakdowns.length === 0;
      var i;
      for (i = 0; i < w.breakdowns.length; i++) {
        var b = w.breakdowns[i];
        if (b.kind === bd.kind && b.field && bd.field && b.field.field === bd.field.field) return true;
      }
      return false;
    }

    function refreshChips() {
      var chips = el('rsBreakdownList').querySelectorAll('button[data-bd-kind]');
      var ci;
      for (ci = 0; ci < chips.length; ci++) {
        var btn = chips[ci];
        var bd = { kind: btn.dataset.bdKind,
                   field: btn.dataset.bdField ? { field: btn.dataset.bdField } : null };
        var sel = isSelected(bd);
        btn.classList.toggle('is-selected', sel);
        btn.setAttribute('aria-pressed', String(sel));
      }
      var hasDate = false;
      for (ci = 0; ci < w.breakdowns.length; ci++) {
        if (w.breakdowns[ci].kind === 'date') { hasDate = true; break; }
      }
      el('rsGrainWrap').hidden = !hasDate;
    }

    function toggleBreakdown(bd) {
      if (bd.kind === 'none') {
        w.breakdowns = [];
        refreshChips();
        return;
      }
      var idx = -1, i;
      for (i = 0; i < w.breakdowns.length; i++) {
        var b = w.breakdowns[i];
        if (b.kind === bd.kind && b.field && bd.field && b.field.field === bd.field.field) {
          idx = i; break;
        }
      }
      if (idx !== -1) { w.breakdowns.splice(idx, 1); refreshChips(); return; }
      if (bd.kind === 'date') {
        w.breakdowns = w.breakdowns.filter(function (b) { return b.kind !== 'date'; });
      }
      if (w.breakdowns.length >= 3) { refreshChips(); return; }
      w.breakdowns.push(bd);
      refreshChips();
    }

    // --- process coverage (docprocessing) --------------------------------
    // Mirrors the Advanced tab's isFieldAvailable(): a field with no
    // `processes` tag (table sources) is universal. The effective scope is
    // the picker selection; empty selection = all allowed (the same
    // convention the definition serializer uses).
    function scopeSel() {
      return (w.scopeProcs && w.scopeProcs.length) ? w.scopeProcs : allProcs;
    }
    function coveredBy(f) {
      if (!allProcs.length || !f.processes || !f.processes.length) return null;
      var sel = scopeSel();
      return f.processes.filter(function (p) { return sel.indexOf(p) !== -1; });
    }
    function inScope(f) {
      var cov = coveredBy(f);
      return cov === null || cov.length > 0;
    }
    function applyCoverageBadge(btn, f) {
      var cov = coveredBy(f);
      if (cov === null || cov.length >= scopeSel().length) return;
      var b = document.createElement('span');
      b.className = 'reporting-simple-chip-cov';
      b.textContent = cov.length + '/' + scopeSel().length;
      btn.appendChild(b);
      btn.title = I18N.chipCoverage.replace('{n}', cov.length).replace('{m}', scopeSel().length)
        + '\n' + cov.join('\n');
    }

    // The chip list is re-rendered whenever the process scope changes: a chip
    // whose field no selected process provides is hidden and its selection
    // pruned (the query would only produce NULL groups for it).
    function renderChipList() {
      var list = el('rsBreakdownList');
      list.innerHTML = '';
      var fields = w.source.fields || [];
      var dateFields = fields.filter(function (f) { return f.grainable; }).filter(inScope);
      var catFields = fields.filter(function (f) {
        return f.type === 'string' && f.filterable;
      }).filter(inScope);

      if (w.source.id === 'docprocessing') {
        catFields = catFields.filter(function (f) { return !DOCPROC_DIM_HIDE[f.field]; });
        catFields.sort(function (a, b) {
          var ia = DOCPROC_DIM_ORDER.indexOf(a.field), ib = DOCPROC_DIM_ORDER.indexOf(b.field);
          if (ia === -1) ia = DOCPROC_DIM_ORDER.length;
          if (ib === -1) ib = DOCPROC_DIM_ORDER.length;
          return (ia - ib) || a.label.localeCompare(b.label);
        });
      }

      // Scope narrowing can strand a selected breakdown on a hidden field.
      w.breakdowns = w.breakdowns.filter(function (b) { return !b.field || inScope(b.field); });

      dateFields.forEach(function (f) {
        var bd = { kind: 'date', field: f };
        var btn = choiceBtn(I18N.overTime + ' (' + f.label + ')', function () {
          toggleBreakdown(bd);
        }, isSelected(bd));
        btn.dataset.bdKind = 'date';
        btn.dataset.bdField = f.field;
        applyCoverageBadge(btn, f);
        list.appendChild(btn);
      });
      // Cap 16 = headroom over docprocessing's current 13 candidates (the 12
      // previously-visible chips + Process). An exactly-saturated cap silently
      // evicts the newest chip -- that trap is why this was raised from 12.
      // Keep slack when adding doc-fields; the cap is pinned by
      // test_wizard_caps_category_chips_at_16.
      catFields.slice(0, 16).forEach(function (f) {
        var bd = { kind: 'category', field: f };
        var btn = choiceBtn(f.label, function () {
          toggleBreakdown(bd);
        }, isSelected(bd));
        btn.dataset.bdKind = 'category';
        btn.dataset.bdField = f.field;
        applyCoverageBadge(btn, f);
        list.appendChild(btn);
      });
      var noneBtn = choiceBtn(I18N.justTotal, function () {
        toggleBreakdown({ kind: 'none' });
      }, w.breakdowns.length === 0);
      noneBtn.dataset.bdKind = 'none';
      list.appendChild(noneBtn);
    }

    renderChipList();

    // Wire Continue button
    var nextBtn = el('rsBreakdownNext');
    if (nextBtn) {
      nextBtn.onclick = function () { renderTimeStep(); };
    }

    // Optional collapsed process picker (docprocessing only). Emits the same
    // scope serialisation as the Advanced picker; empty/full = all allowed
    // (the server clamps to grants either way).
    var scopeWrap = el('rsScopeWrap');
    var procs = state.wiz.source.processes || [];
    scopeWrap.hidden = !procs.length;
    if (procs.length) {
      var box = el('rsScopeList');
      box.innerHTML = '';
      var prior = state.wiz.scopeProcs || [];
      var updateScopeBadge = function () {
        var picked = (state.wiz.scopeProcs || []).length;
        el('rsScopeBadge').textContent =
          (!picked || picked === procs.length) ? I18N.allProcesses : picked + ' / ' + procs.length;
      };
      procs.forEach(function (p) {
        var lbl = document.createElement('label');
        var cb = document.createElement('input');
        cb.type = 'checkbox'; cb.value = p;
        cb.checked = !prior.length || prior.indexOf(p) !== -1;
        cb.addEventListener('change', function () {
          state.wiz.scopeProcs = Array.prototype.map.call(
            box.querySelectorAll('input:checked'), function (c) { return c.value; });
          updateScopeBadge();
          renderChipList();
        });
        lbl.appendChild(cb);
        lbl.appendChild(document.createTextNode(' ' + p));
        box.appendChild(lbl);
      });
      if (!prior.length) state.wiz.scopeProcs = procs.slice();
      updateScopeBadge();
    }
  }
```

(This is the existing function with four additions: the `allProcs` var, the coverage helper block, the `renderChipList()` extraction with `.filter(inScope)` + `applyCoverageBadge` + the pruning line, and the `renderChipList();` call in the checkbox handler. `refreshChips` now reads `el('rsBreakdownList')` instead of the closed-over `list` var. Everything else is byte-identical — diff your edit against git to confirm.)

- [ ] **Step 5 — CSS.** Append to the END of `static/css/reporting.css` (append-wins file; do not insert mid-file):

```css
/* Process-coverage badge on wizard chips/measure cards: "n/m" processes
   provide this field (tooltip on the chip names them). */
.reporting-simple-chip-cov { margin-left: 6px; font-size: 11px; font-weight: 600; background: var(--nx-accent-tint); color: var(--nx-accent); border-radius: 999px; padding: 1px 7px; }
```

- [ ] **Step 6 — Run GREEN + the whole Simple e2e file** (proves the older stubs — whose fields carry no `processes` key — render unchanged, incl. the Process-chip and cap tests):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -q`
Expected: all passed

- [ ] **Step 7 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html static/css/reporting.css tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
feat(reporting): mark process-specific breakdown chips in the wizard

Breakdown chips whose field only some selected processes provide show
an "n/m" coverage badge with a tooltip naming the providers, and the
chip list now follows the "Limit to specific processes" picker the way
the Advanced tab's field list does: zero-coverage chips hide and
stranded selections are pruned (their groups would only ever be the
NULL bucket). Coverage mirrors isFieldAvailable(): fields without a
processes tag (table sources) are universal, so non-docprocessing
sources and all existing stubs are untouched. Chip rendering is
extracted into renderChipList() so a scope change re-renders chips
without collapsing the time step. test_translations stays red on the
two new tooltip msgids until the late pybabel cycle.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

### Task 6: Measure cards — coverage badge + unrunnable-metric hiding

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (`renderMeasureStep` body)
- Test: `tests/e2e/test_reporting_simple.py` (one new test + metric stub rows)

**Interfaces:**
- Consumes: `m.baseField` from `/api/reporting/metrics` (Task 3 keeps serving it), `src.fields[].processes`, `I18N.measureCoverage` and `.reporting-simple-chip-cov` from Task 5.
- Produces: measure cards with partial base-field coverage get the same badge (vs ALL allowed processes — no scope exists yet at the measure step); a metric whose base field is absent from the source's field catalog is not offered (running it would 400: `resolve_metrics` raises `metric base field not in catalog`).

- [ ] **Step 1 — Write the failing e2e test.** Append to `tests/e2e/test_reporting_simple.py`:

```python
def test_wizard_measure_coverage_badge_and_unrunnable_hidden(nexora_server, page):
    """A sum measure over a partially-covered base field gets the n/m badge;
    a metric whose base field no allowed process provides is not offered at
    all (it could never run); count metrics stay plain."""
    metrics = {
        "docprocessing": [
            {"code": "doc_count", "label": "Cov count stub", "aggregation": "count",
             "baseField": None, "format": "int"},
            {"code": "page_sum", "label": "Pages stub", "aggregation": "sum",
             "baseField": "propertynr", "format": "int"},
            {"code": "ghost_sum", "label": "Ghost stub", "aggregation": "sum",
             "baseField": "ghostfield", "format": "int"},
        ]
    }
    _login(page, nexora_server)
    _stub_wiz_catalogs(page, COV_WIZ_SOURCES, metrics)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    mlist = page.get_by_test_id("rs-measure-list")
    pages_btn = mlist.locator("button", has_text="Pages stub")
    expect(pages_btn.locator(".reporting-simple-chip-cov")).to_have_text("1/2")
    assert "acme.inv" in pages_btn.get_attribute("title")
    count_btn = mlist.locator("button", has_text="Cov count stub")
    expect(count_btn.locator(".reporting-simple-chip-cov")).to_have_count(0)
    expect(mlist.get_by_text("Ghost stub")).to_have_count(0)
```

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest "tests/e2e/test_reporting_simple.py::test_wizard_measure_coverage_badge_and_unrunnable_hidden" -q`
Expected: `1 failed`

- [ ] **Step 2 — Implement.** In `templates/js/_reporting_simple_js.html`, inside `renderMeasureStep`, find:

```js
      (bySource[sid] || []).forEach(function (m) {
        // Sources without metrics never appear; admins grow the wizard's
        // reach by adding rows in the metrics registry, zero code change.
        var label = multi ? (m.label + ' · ' + src.label) : m.label;
        list.appendChild(choiceBtn(label, function () {
          state.wiz.measure = m;
          state.wiz.source = src;   // picking a measure pins the source
          renderBreakdownStep();
        }, !!(state.wiz.measure && state.wiz.measure.code === m.code
              && state.wiz.source && state.wiz.source.id === src.id)));
      });
```

Replace with:

```js
      (bySource[sid] || []).forEach(function (m) {
        // Sources without metrics never appear; admins grow the wizard's
        // reach by adding rows in the metrics registry, zero code change.
        var srcProcs = src.processes || [];
        var fld = m.baseField
          ? (src.fields || []).find(function (f) { return f.field === m.baseField; })
          : null;
        // A metric whose base field no allowed process provides can never run
        // for this user (resolve_metrics 400s) — don't offer it.
        if (m.baseField && !fld) return;
        var label = multi ? (m.label + ' · ' + src.label) : m.label;
        var btn = choiceBtn(label, function () {
          state.wiz.measure = m;
          state.wiz.source = src;   // picking a measure pins the source
          renderBreakdownStep();
        }, !!(state.wiz.measure && state.wiz.measure.code === m.code
              && state.wiz.source && state.wiz.source.id === src.id));
        // Partial coverage (vs ALL allowed processes — no scope exists yet at
        // this step): same badge as the breakdown chips.
        if (fld && fld.processes && fld.processes.length && srcProcs.length
            && fld.processes.length < srcProcs.length) {
          var cov = document.createElement('span');
          cov.className = 'reporting-simple-chip-cov';
          cov.textContent = fld.processes.length + '/' + srcProcs.length;
          btn.appendChild(cov);
          btn.title = I18N.measureCoverage.replace('{n}', fld.processes.length)
            .replace('{m}', srcProcs.length) + '\n' + fld.processes.join('\n');
        }
        list.appendChild(btn);
      });
```

- [ ] **Step 3 — Run GREEN + the whole file:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -q`
Expected: all passed

- [ ] **Step 4 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
feat(reporting): coverage badge on wizard measures, hide unrunnable

Measure cards whose base field only some allowed processes provide get
the same n/m coverage badge and provider tooltip as the breakdown
chips (the new page_count metric is exactly this case: only processes
with a mapped col_pagecount contribute pages). A metric whose base
field is absent from the source catalog entirely is no longer offered
-- resolve_metrics would reject it with a 400 on run. count metrics
and untagged fields stay plain.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 5 — i18n cycle

### Task 7: pybabel extract → update → translate → compile

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` + compiled `.mo` (committed)

**Interfaces:** none — makes `tests/unit/test_translations.py` green again. Five new msgids (three from Task 4, two from Task 5).

- [ ] **Step 1 — Run the cycle** (from the worktree root; the venv has pybabel):

```
C:\dev\nexora\.venv\Scripts\pybabel extract -F babel.cfg -o messages.pot .
C:\dev\nexora\.venv\Scripts\pybabel update -i messages.pot -d translations
```

- [ ] **Step 2 — Hand-translate the five new msgids** in each `translations/<lang>/LC_MESSAGES/messages.po`, removing every `#, fuzzy` marker the update added. Use exactly:

| msgid | de | fr | it |
|---|---|---|---|
| `German label` | `Deutsche Bezeichnung` | `Libellé allemand` | `Etichetta tedesca` |
| `French label` | `Französische Bezeichnung` | `Libellé français` | `Etichetta francese` |
| `Italian label` | `Italienische Bezeichnung` | `Libellé italien` | `Etichetta italiana` |
| `Only {n} of {m} selected processes provide this field — documents from the other processes show an empty value here. Provided by:` | `Nur {n} von {m} ausgewählten Prozessen liefern dieses Feld — Dokumente der übrigen Prozesse erscheinen hier mit leerem Wert. Geliefert von:` | `Seuls {n} des {m} processus sélectionnés fournissent ce champ — les documents des autres processus apparaissent ici avec une valeur vide. Fourni par :` | `Solo {n} su {m} processi selezionati forniscono questo campo — i documenti degli altri processi appaiono qui con un valore vuoto. Fornito da:` |
| `Only {n} of {m} processes provide this field — the measure only counts documents from these processes:` | `Nur {n} von {m} Prozessen liefern dieses Feld — die Kennzahl zählt nur Dokumente dieser Prozesse:` | `Seuls {n} des {m} processus fournissent ce champ — l'indicateur ne compte que les documents de ces processus :` | `Solo {n} su {m} processi forniscono questo campo — la metrica conta solo i documenti di questi processi:` |

- [ ] **Step 3 — Compile + prove green:**

```
C:\dev\nexora\.venv\Scripts\pybabel compile -d translations
C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_translations.py -q
```
Expected: all passed

- [ ] **Step 4 — Commit:**

```bash
git add messages.pot translations
git commit -F - <<'EOF'
chore(i18n): translate metric-label form and coverage-badge strings

Extract/update/compile cycle for the five msgids added by the
localized-metric-labels admin form (German/French/Italian label) and
the process-coverage tooltips on wizard chips and measure cards; de/fr/
it hand-translated, non-fuzzy. Restores test_translations to green.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 6 — Docs & changelog

### Task 8: Update reporting howto + changelog

**Files:**
- Modify: `docs/howto/reporting.md` (three passages)
- Modify: `CHANGELOG.md` (`[Unreleased]` → `### Added`)

**Interfaces:** none (docs only).

- [ ] **Step 1 — Wizard bullet.** In `docs/howto/reporting.md`, find (inside the `+ New report (wizard)` bullet):

```
    **✕** (on both the wizard header and the result bar) exits straight to the
    library without discarding anything already saved.
```

Replace with:

```
    **✕** (on both the wizard header and the result bar) exits straight to the
    library without discarding anything already saved.
    Measures and category/date chips whose field only *some* processes provide
    carry an **"n/m" coverage badge** (tooltip names the providing processes —
    documents from the others land in the empty-value bucket, and a partial
    measure counts only its providers' documents). The chip list follows the
    **"Limit to specific processes"** picker like the Advanced tab's field
    list: chips with zero coverage under the picked scope hide, and stranded
    selections are pruned. A metric whose base field no allowed process
    provides is not offered at all.
```

- [ ] **Step 2 — Metrics registry section.** Find:

```
`max`), and a `BaseField` (a whitelisted column of that source — required for
every aggregation except `count`). `Format` (`int`/`decimal`/`percent`) is a
display hint; `Enabled` and `SortOrder` control visibility/ordering. Migration
`0017` seeds a worked example, `doc_count` (a `count` over the docprocessing
source).
```

Replace with:

```
`max`), and a `BaseField` (a whitelisted column of that source — required for
every aggregation except `count`). `Format` (`int`/`decimal`/`percent`) is a
display hint; `Enabled` and `SortOrder` control visibility/ordering. Labels are
DB-driven i18n: `Label` (English) plus nullable `GermanLabel`/`FrenchLabel`/
`ItalianLabel` (migration `0039`; NULL falls back to `Label`, the
`Search_Field_Labels` convention) — `/api/reporting/metrics` serves the session
locale's label, while the AI catalogs deliberately keep the English `Label` for
prompt-grounding stability. Migration `0017` seeds a worked example, `doc_count`
(a `count` over the docprocessing source); migration `0039` adds **`page_count`**
("Pages processed", `SUM` over `pagecount`, `SortOrder` 30). For `sum`/`avg`
metrics the docprocessing query builder projects the base field as
`TRY_CAST(<col> AS float)` per UNION-ALL subquery — the stat columns are
varchar, so non-numeric cells become NULL and drop out of the aggregate instead
of erroring; only processes with the mapped `col_*` contribute.
```

- [ ] **Step 3 — Changelog.** In `CHANGELOG.md` under `## [Unreleased]` → `### Added`, append (matching the existing "Reporting: …" entry style):

```
- Reporting: **Pages processed** (`page_count`) metric — `SUM` over the
  `pagecount` doc field (migration `0039`); the query builder now `TRY_CAST`s
  `sum`/`avg` metric bases to float so varchar stat columns aggregate safely.
- Reporting: metric labels are localized — `dbo.ReportingMetrics` gains
  German/French/Italian label columns (migration `0039`, admin form updated);
  `/api/reporting/metrics` serves the session locale's label with English
  fallback.
- Reporting: the Simple wizard marks **process coverage** — measures and
  breakdown chips whose field only some processes provide show an "n/m" badge
  with a tooltip naming the providers; the chip list follows the process-scope
  picker (zero-coverage chips hide, stranded selections prune), and metrics
  whose base field no allowed process provides are not offered.
```

- [ ] **Step 4 — Commit:**

```bash
git add docs/howto/reporting.md CHANGELOG.md
git commit -F - <<'EOF'
docs(reporting): document page_count, metric i18n and coverage badges

Update the wizard walkthrough (coverage badges, scope-reactive chips,
unrunnable-measure hiding) and the metrics-registry section (localized
label columns from 0039, the page_count seed, and the TRY_CAST float
projection for sum/avg bases) in docs/howto/reporting.md; add the
three changelog entries under Unreleased.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 7 — Full gate + live verification on INT

### Task 9: Full local test gate

**Files:** none (verification only).

- [ ] **Step 1 — Non-e2e tiers:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests --ignore=tests/e2e -q`
Expected: all passed, 0 failed (incl. `test_translations.py` and `test_reporting_i18n_lint.py`)

- [ ] **Step 2 — e2e tier for the touched surfaces:**

Run:
```
C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py
C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py tests/e2e/test_reporting_metrics.py -q
```
Expected: all passed

- [ ] **Step 3 — `git log --oneline -8`:** confirm the seven commits from Tasks 1–8 are present, in order, on `plan/reporting-metrics-process-groupby-marking`. Nothing to commit in this task.

### Task 10: Live browser verification on INT (+ screenshots)

**Files:** none (verification only; screenshots go to `var/screenshots/`, never the repo root).

**Prereq:** migration `0039` was auto-applied to INT by Task 2's pre-commit hook. Confirm with the read-only query from Task 2's Verify line first.

- [ ] **Step 1 — Restart the dev server with auto-login** (Jinja templates are process-cached): `nx -u -b --loginas:<a user with reporting.view + the docprocessing grant + several reporting.scope.process.* grants — the owner's usual admin login qualifies>`.
- [ ] **Step 2 — Measure step:** Reporting → Simple → **New report**. Verify TWO measures now show: "Document count" and "Pages processed" (German locale user: "Anzahl Dokumente" / "Verarbeitete Seiten"). If "Pages processed" carries a coverage badge, hover it — the tooltip must list the processes with a mapped `col_pagecount`; if the measure is MISSING entirely, no process maps `col_pagecount` on INT → record it for Owner action 2 and continue with the badge checks on chips. Screenshot → `var/screenshots/reporting-measures-page-count.png`.
- [ ] **Step 3 — Pages result:** pick "Pages processed" → breakdown *Process* → All time → run. The chart/table must show summed page numbers (not row counts), the grand-total card a plausible total, and the Show-query panel a `SUM([pagecount])` with `TRY_CAST(... AS float)` in the subqueries. Screenshot → `var/screenshots/reporting-page-count-result.png`.
- [ ] **Step 4 — Chip badges:** with "Document count", open the breakdown step. Partially-covered chips (e.g. Property No., Tenancy no. — fields only some processes map) must show `n/m` badges; hover one to see the provider list. Screenshot → `var/screenshots/reporting-chip-coverage.png`.
- [ ] **Step 5 — Scope reactivity:** open "Limit to specific processes", untick processes until a badged chip loses all providers → the chip disappears (and its selection, if selected, is dropped); re-tick → it returns. Time step visibility must NOT change while ticking.
- [ ] **Step 6 — Locale check:** switch the profile locale to German (or use a German-locale user), reload → measure cards read "Anzahl Dokumente" / "Verarbeitete Seiten"; the admin page `/reporting/metrics` shows the three new label inputs and the seeded translations when editing `page_count`. Screenshot → `var/screenshots/reporting-metrics-admin-l10n.png`.
- [ ] **Step 7 — If this is a remote session, `SendUserFile` the four screenshots** (remote frontend rule: send them proactively).

---

## Gotchas & notes

- **`TRY_CAST` is T-SQL.** It belongs in `query.py`'s docprocessing projection ONLY. Never move it into `semantic.metric_select_expr` / `build_aggregate_sql` — `table_query.py` shares those for table sources, which can be PostgreSQL (MS02). A table-source `sum` metric aggregates a real typed column and needs no cast.
- **`float`, deliberately** (`ponytail:` comment in the code): exact for page counts (< 2^53), trivial JSON. When amount metrics (money) arrive, switch the cast to `decimal(18,2)` — that is the upgrade path, not a today-problem.
- **A field that is BOTH a dim and a sum-base** gets the cast (it is projected once, deduped) — grouping then buckets by the numeric value. Harmless and arguably more correct; noted so nobody "fixes" it into a double projection.
- **TEST DB ≠ migrations.** `scripts/test_db_reset.py` rebuilds NEXORA_TEST from `sql/test/schema.sql` + `seed.sql`. Forgetting the Task 2 schema.sql mirror makes Tasks 3–6 fail on missing columns with a confusing pyodbc error — check there first.
- **Migration number 0039 may be taken** by the owner's queued validation-user re-map — re-list `sql/_migrations/NexoraDB/` before Task 2 and bump.
- **The ALTER regenerates `sql/NexoraDB/Tables/dbo.ReportingMetrics.sql`** via the pre-commit sync hook — `git add` the regenerated dump into Task 2's commit; never hand-edit it.
- **Accented SQL is safe** — `db-migrate.py` probes classic-vs-go sqlcmd and forces `-f 65001` on classic (the `0011` mojibake fix). Still: write the migration with the Write tool (UTF-8, LF).
- **Coverage convention:** `f.processes` missing/empty ⇒ universal (no badge, never hidden). This is what makes every pre-existing e2e stub and all table sources immune. The synthesized `processname` field carries ALL allowed processes ⇒ never badged.
- **Empty `scopeProcs` = all allowed** — the wizard serializer's existing convention; the coverage helpers reuse it. Unticking EVERY process leaves `scopeProcs` empty, which re-renders as "all selected" (checkboxes re-tick) — truthful, since the serializer treats none-picked as all.
- **`renderChipList()` on scope change must NOT touch step visibility** — re-running the whole `renderBreakdownStep()` would hide the time step a user already advanced to. That is why the function is extracted (D4).
- **`refreshChips` reads `el('rsBreakdownList')` directly after the rework** (it used to close over a `list` var that now lives inside `renderChipList`). If you see `list is not defined` in the console, this is the line you missed.
- **Measure badges compare against ALL allowed processes** (`src.processes`), not the scope — no scope exists yet at the measure step. Chip badges compare against the SELECTED scope. Both tooltips name the providers, so the difference is self-explaining.
- **`test_translations.py` is expected RED from Task 4 until Task 7** (five new msgids). Use `--deselect tests/unit/test_translations.py` for fast in-between tiers; Task 9 proves the full suite.
- **e2e asserts English msgids** (TEST server runs English) — the badge text `1/2` is language-neutral, tooltips assert via `get_attribute("title")` substring, never translated text.
- **Chip `to_have_text` pins elsewhere in the suite are safe:** badges only appear on fields WITH a partial `processes` tag; the pre-existing wizard stubs (`WIZ_STUB_SOURCES`, `DOCPROC_WIZ_FIELDS`, `CAP_WIZ_SOURCES`) declare none, so their chips render text-identical.
- **`page_count` on INT/PROD counts only processes with `col_pagecount` mapped** in `SearchConfig` — a NULL-mapped process contributes `NULL AS [pagecount]` rows, i.e. nothing. The measure badge makes this visible; expanding coverage is a SearchConfig data edit (Owner action 2), not code.
- **Values like `12345.0`:** SUM over float returns float; `fmtNumber` → `Number(v).toLocaleString(APP_LANG)` renders `12'345`/`12.345` correctly — no trailing `.0` in the UI.
- **Advanced tab untouched (D8):** its metrics dropdown may still offer a zero-coverage metric (400 with a translated message on run) — known, Owner action 5.
- **Do not commit the main clone's stray `package.json`/`package-lock.json`** — they predate this plan and live outside the worktree anyway.
