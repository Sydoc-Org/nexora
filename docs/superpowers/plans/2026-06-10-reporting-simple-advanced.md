# Reporting Simple/Advanced Restructure (Spec 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `/reporting` into a Simple tab (report library + guided wizard + ask-AI helper, card-based results) and an Advanced tab (today's builder, untouched), plus two backend slices: zero-dimension metric definitions (grand totals) and Surface-A AI grounding for metrics + grain.

**Architecture:** Two client-side panes under one route; the Advanced pane wraps the existing `main.reporting-main` unmoved so the builder IIFE's ~50 unguarded `getElementById` bindings keep working. Simple is a new self-contained IIFE partial that talks only to existing REST endpoints plus `window.Reporting` / `window.ReportingTabs`. Backend slice A relaxes the v1 schema (`columns: []` iff `metrics` non-empty) and routes through `semantic.build_aggregate_sql` with no GROUP BY; slice B teaches the Surface-A catalog + system prompt about metrics/grain **and fixes `_validate_definition_for_user` to pass `metric_codes`/`grainable_fields`** (verified gap: today it rejects any AI draft carrying metrics or grain).

**Tech Stack:** Flask/Jinja2, vanilla JS IIFE partials, Chart.js 4.5.1 (already on page), flatpickr (already on page), pytest + Playwright, Flask-Babel.

**Spec:** `docs/superpowers/specs/2026-06-09-reporting-simple-advanced-design.md`

**Conventions for every commit in this plan:**
- `SQL_SYNC_SKIP=1 git commit ...` (INT SchemaMigrations CRLF drift).
- gitlint: conventional type, subject ≤ 72 chars, **non-empty body**.
- If `ruff-format` modifies files during commit: `git add -u` and re-run the same commit.
- Restart the dev server after any template/JS-partial edit (Jinja caches per process).

---

## Phase 1 — Backend slice A: zero-dimension metric definitions

### Task 1: schema.py — accept `columns: []` iff metrics non-empty

**Files:**
- Modify: `nx_lib/reporting/schema.py:84-86`
- Test: `tests/unit/test_reporting_schema.py`

- [x] **Step 1: Write the failing tests** (append to `tests/unit/test_reporting_schema.py`; it already defines `_valid_def()`, `CATALOG_FIELDS`, `FILTERABLE`, `SORTABLE`)

```python
def test_zero_columns_with_metrics_accepted():
    d = _valid_def()
    d["columns"] = []
    d["sort"] = []
    d["metrics"] = [{"metric": "doc_count"}]
    validate_report_definition(
        d, CATALOG_FIELDS, FILTERABLE, SORTABLE,
        max_row_limit=50000, metric_codes={"doc_count"},
    )


def test_missing_columns_with_metrics_accepted():
    d = _valid_def()
    del d["columns"]
    d["sort"] = []
    d["metrics"] = [{"metric": "doc_count"}]
    validate_report_definition(
        d, CATALOG_FIELDS, FILTERABLE, SORTABLE,
        max_row_limit=50000, metric_codes={"doc_count"},
    )


def test_zero_columns_without_metrics_still_rejected():
    d = _valid_def()
    d["columns"] = []
    d["sort"] = []
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(
            d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000
        )


def test_zero_columns_with_empty_metrics_list_rejected():
    d = _valid_def()
    d["columns"] = []
    d["sort"] = []
    d["metrics"] = []
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(
            d, CATALOG_FIELDS, FILTERABLE, SORTABLE,
            max_row_limit=50000, metric_codes={"doc_count"},
        )
```

- [x] **Step 2: Run to verify the accept-tests fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_schema.py -q -k zero_columns or missing_columns`
Expected: the two `accepted` tests FAIL with `ReportDefinitionError: at least one column is required`; the two `rejected` tests pass.

- [x] **Step 3: Implement** — in `validate_report_definition`, replace the columns block (lines 84-86):

```python
    columns = rd.get("columns")
    if columns is None:
        columns = []
    metrics_list = rd.get("metrics")
    has_metrics = isinstance(metrics_list, list) and len(metrics_list) > 0
    if not isinstance(columns, list):
        raise ReportDefinitionError("columns must be a list")
    if not columns and not has_metrics:
        raise ReportDefinitionError("at least one column is required")
```

(The per-column loop below already iterates the possibly-empty list safely.)
Also update the module docstring's "at least one column" implication if stated, and the docstring of `validate_report_definition` with one clause: "columns may be empty iff metrics is non-empty (zero-dimension grand totals)."

- [x] **Step 4: Run the full schema suite**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_schema.py -q`
Expected: all pass.

- [x] **Step 5: Commit**

```bash
git add nx_lib/reporting/schema.py tests/unit/test_reporting_schema.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): accept zero-column definitions when metrics present" -m "Schema slice for the Simple tab's number cards: a definition with a
non-empty metrics list may have empty/missing columns (a global
aggregate with no GROUP BY). Definitions without metrics still require
at least one column."
```

### Task 2: semantic.py — omit GROUP BY when no dims

**Files:**
- Modify: `nx_lib/reporting/semantic.py:82-112` (`build_aggregate_sql`)
- Test: `tests/unit/test_reporting_semantic.py`

- [x] **Step 1: Write the failing test** (append; match the existing test style in that file)

```python
def test_build_aggregate_sql_zero_dims_omits_group_by():
    sql = build_aggregate_sql(
        inner_from="(SELECT 1 AS [_one] FROM [T]) t",
        dim_fields=[],
        resolved_metrics=[{"code": "doc_count", "aggregation": "count", "base_field": None}],
        sort=[],
        cap=100,
    )
    assert sql == "SELECT TOP (100) COUNT(*) AS [doc_count] FROM (SELECT 1 AS [_one] FROM [T]) t"
    assert "GROUP BY" not in sql


def test_build_aggregate_sql_zero_dims_sort_by_metric_allowed():
    sql = build_aggregate_sql(
        inner_from="[V]",
        dim_fields=[],
        resolved_metrics=[{"code": "total", "aggregation": "sum", "base_field": "amount"}],
        sort=[{"field": "total", "dir": "desc"}],
        cap=10,
    )
    assert sql.endswith("ORDER BY [total] DESC")
```

- [x] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_semantic.py -q -k zero_dims`
Expected: FAIL — current SQL ends with `GROUP BY ` (trailing empty clause).

- [x] **Step 3: Implement** — in `build_aggregate_sql` replace the sql assembly line:

```python
    sql = f"SELECT TOP ({int(cap)}) {select_list} FROM {inner_from}"
    if dim_fields:
        sql += f" GROUP BY {group_by}"
```

- [x] **Step 4: Run the semantic suite**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_semantic.py -q`
Expected: all pass.

- [x] **Step 5: Commit**

```bash
git add nx_lib/reporting/semantic.py tests/unit/test_reporting_semantic.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): aggregate SQL without GROUP BY for zero-dim metrics" -m "build_aggregate_sql now emits a plain global-aggregate SELECT when
dim_fields is empty, enabling grand-total (number card) queries. Sort
by a metric code still works; sorting by a non-projected field still
raises."
```

### Task 3: query.py — zero-dim branch for the docprocessing UNION

**Files:**
- Modify: `nx_lib/reporting/query.py` (`build_table_query`, subquery projection)
- Test: `tests/unit/test_reporting_query.py`

- [x] **Step 1: Write the failing tests** (append; the file has `_configs()`/`_col_maps()`-style helpers near the top — reuse the same fixtures the aggregate tests at `test_docprocessing_aggregate_wraps_union` use)

```python
def test_zero_dim_count_metric_global_total():
    rd = {
        "columns": [],
        "filters": [],
        "sort": [],
        "rowLimit": 100,
    }
    resolved = [{"code": "doc_count", "aggregation": "count", "base_field": None}]
    sql, params = build_table_query(
        rd, CONFIGS, COL_MAPS, row_cap=100, resolved_metrics=resolved
    )
    assert "GROUP BY" not in sql
    assert "COUNT(*) AS [doc_count]" in sql
    # every subquery must still project something
    assert "1 AS [_one]" in sql


def test_zero_dim_sum_metric_projects_base_field():
    rd = {"columns": [], "filters": [], "sort": [], "rowLimit": 100}
    resolved = [{"code": "total_pages", "aggregation": "sum", "base_field": "pages"}]
    sql, params = build_table_query(
        rd, CONFIGS, COL_MAPS, row_cap=100, resolved_metrics=resolved
    )
    assert "SUM([pages]) AS [total_pages]" in sql
    assert "AS [pages]" in sql  # base field projected in the union
    assert "GROUP BY" not in sql
```

(Adapt `CONFIGS`/`COL_MAPS` to the file's actual fixture names; the existing aggregate tests show them.)

- [x] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_query.py -q -k zero_dim`
Expected: FAIL — count-only case produces `SELECT  FROM` (empty projection) or the assert on `1 AS [_one]` fails.

- [x] **Step 3: Implement** — in `build_table_query`, after the per-process `select_exprs` loop, guard the empty projection:

```python
        if not select_exprs:
            # Zero-dimension + count-only metrics: nothing to project, but the
            # subquery still needs a SELECT list for the outer COUNT(*).
            select_exprs.append("1 AS [_one]")
```

No other change: `columns` is already `[]`-safe, the metrics branch routes through `build_aggregate_sql` (fixed in Task 2), and the row path is unreachable with empty columns (validator).

- [x] **Step 4: Run the query suite**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_query.py -q`
Expected: all pass.

- [x] **Step 5: Commit**

```bash
git add nx_lib/reporting/query.py tests/unit/test_reporting_query.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): zero-dim grand totals over the docprocessing union" -m "A definition with metrics and no columns now builds
SELECT AGG(...) FROM (union) t with no GROUP BY. Count-only metric
sets project a constant 1 AS [_one] per subquery so the SELECT list is
never empty."
```

### Task 4: table_query.py — zero-dim branch for the generic provider

**Files:**
- Modify: `nx_lib/reporting/table_query.py:116-135` (`build_generic_query`)
- Test: `tests/unit/test_reporting_table_query.py`

- [x] **Step 1: Write the failing test** (append; mirror the file's existing aggregate test fixtures)

```python
def test_zero_dim_metric_global_total_generic():
    rd = {"columns": [], "filters": [], "sort": [], "rowLimit": 100}
    resolved = [{"code": "n", "aggregation": "count", "base_field": None}]
    sql, params = build_generic_query(
        rd, "Db.dbo.V", COLUMNS, row_cap=100, resolved_metrics=resolved
    )
    assert sql == "SELECT TOP (100) COUNT(*) AS [n] FROM [Db].[dbo].[V]"


def test_zero_dim_without_metrics_still_rejected_generic():
    rd = {"columns": [], "filters": [], "sort": [], "rowLimit": 100}
    with pytest.raises(TableQueryError):
        build_generic_query(rd, "Db.dbo.V", COLUMNS, row_cap=100)
```

- [x] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_table_query.py -q -k zero_dim`
Expected: first test FAILS with `TableQueryError: no valid columns selected`.

- [x] **Step 3: Implement** — in `build_generic_query`, move the empty-projection guard into the row path only:

```python
    by_field = {c["field"]: c for c in columns}
    proj = [c.get("field") for c in rd.get("columns", [])]
    dim_fields = [f for f in proj if f in by_field]

    conds, params = _build_conditions(rd, by_field)

    if resolved_metrics:
        where = (" WHERE " + " AND ".join(conds)) if conds else ""
        inner_from = f"{_quote_object(base_object)}{where}"
        sql = build_aggregate_sql(
            inner_from=inner_from,
            dim_fields=dim_fields,
            resolved_metrics=resolved_metrics,
            sort=rd.get("sort") or [],
            cap=row_cap,
        )
        return sql, params

    select_cols = [_quote_ident(f) for f in dim_fields]
    if not select_cols:
        raise TableQueryError("no valid columns selected")
```

(The rest of the row path is unchanged.)

- [x] **Step 4: Run the table_query suite**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_table_query.py -q`
Expected: all pass.

- [x] **Step 5: Commit**

```bash
git add nx_lib/reporting/table_query.py tests/unit/test_reporting_table_query.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): zero-dim grand totals on the generic table provider" -m "build_generic_query routes empty-column metric definitions through the
no-GROUP-BY aggregate branch. The row path still rejects an empty
projection."
```

### Task 5: route round-trip — integration test for zero-dim runs

**Files:**
- Modify: `tests/integration/test_reporting_routes.py`
- Verify (no change expected): `nx_lib/views/reporting.py:736-738` (`out_columns` degrades to metric codes), `nx_lib/reporting/runner.py`

- [x] **Step 1: Read `test_table_source_end_to_end` (tests/integration/test_reporting_routes.py:498)** and reuse its seeding pattern (registered table source + a `dbo.ReportingMetrics` row) for a new test:

```python
def test_run_zero_dim_metric_returns_single_total_row(admin_client):
    # Seed pattern copied from test_table_source_end_to_end: register a table
    # source over a small seeded object + one count metric, then run a
    # zero-column definition and expect exactly the metric column back.
    ...  # (concrete seeding statements copied from that test at implementation)
    rd = {
        "schemaVersion": 1, "visualization": "table", "source": SOURCE_ID,
        "title": "Total", "columns": [], "filters": [], "sort": [],
        "scope": {"clients": [], "processes": []},
        "metrics": [{"metric": METRIC_CODE}], "rowLimit": 100,
    }
    res = admin_client.post("/api/reporting/run", json=rd)
    assert res.status_code == 200
    data = res.get_json()
    assert [c["field"] for c in data["columns"]] == [METRIC_CODE]
    assert data["rowCount"] == 1
```

(The `...` is resolved by copying the seeding block from `test_table_source_end_to_end` — same INSERT into `ReportingSources` + metric INSERT used by the metrics e2e; if that test seeds via API calls, do the same.)

- [x] **Step 2: Run to verify it exercises the new path**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_reporting_routes.py -q -k zero_dim`
Expected: PASS (backend slices already landed). If it fails, the failure is in `_prepare_run`/serialization — fix forward, do not touch the builders' tested contracts.

- [x] **Step 3: Run the whole integration file**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_reporting_routes.py -q`
Expected: all pass.

- [x] **Step 4: Commit**

```bash
git add tests/integration/test_reporting_routes.py
SQL_SYNC_SKIP=1 git commit -m "test(reporting): zero-dim metric run round-trip at the route level" -m "Covers /api/reporting/run accepting a columns-less metric definition
and returning a single grand-total row with only the metric column."
```

## Phase 2 — Backend slice B: Surface-A grounding (metrics + grain)

### Task 6: ai_schema.py — grainable flag + per-source metric lines

**Files:**
- Modify: `nx_lib/reporting/ai_schema.py:76-113` (`serialize_sources_catalog`)
- Modify: `nx_lib/views/reporting.py:336-366` (`_accessible_curated_sources` attaches metrics)
- Test: `tests/unit/test_reporting_ai_schema.py`

- [x] **Step 1: Write the failing tests** (append)

```python
def test_serialize_sources_catalog_marks_grainable_fields():
    sources = [{
        "id": "docprocessing", "label": "Doc Processing",
        "fields": [{
            "field": "import_date", "label": "Import date", "type": "date",
            "filterable": True, "sortable": True, "grainable": True,
        }],
        "processes": [],
    }]
    text, _tr = ai_schema.serialize_sources_catalog(sources, char_budget=10000)
    assert "grainable" in text


def test_serialize_sources_catalog_lists_source_metrics():
    sources = [{
        "id": "docprocessing", "label": "Doc Processing",
        "fields": [{"field": "client", "type": "string", "filterable": True, "sortable": True}],
        "processes": [],
        "metrics": [{"code": "doc_count", "label": "Documents", "aggregation": "count", "base_field": None}],
    }]
    text, _tr = ai_schema.serialize_sources_catalog(sources, char_budget=10000)
    assert 'metrics: doc_count "Documents" = count(*)' in text
```

- [x] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_ai_schema.py -q -k "grainable or source_metrics"`
Expected: FAIL (no grainable flag / no metrics line).

- [x] **Step 3: Implement** in `serialize_sources_catalog`:
  - In the per-field flag loop, after `sortable`: `if f.get("grainable"): flags.append("grainable")`.
  - After the `allowed scope.processes` line, append a metrics line when the source carries metrics:

```python
        mets = s.get("metrics") or []
        if mets:
            parts = []
            for m in mets:
                col = m.get("base_field") or "*"
                label = f' "{m.get("label")}"' if m.get("label") else ""
                parts.append(f"{m.get('code')}{label} = {m.get('aggregation')}({col})")
            lines.append(f"  metrics: {'; '.join(parts)}")
```

  - Document in the docstring: grainable fields accept a per-column `grain` of day/week/month/quarter/year.

- [x] **Step 4: Attach metrics in `_accessible_curated_sources`** (views/reporting.py) — before the loop build a map, then include it per source:

```python
    metrics_by_source = {}
    for m in _load_db_metrics().values():
        metrics_by_source.setdefault(m["source_id"], []).append(
            {
                "code": m["code"],
                "label": m["label"],
                "aggregation": m["aggregation"],
                "base_field": m["base_field"],
            }
        )
```

and in the `out.append({...})` dict add `"metrics": metrics_by_source.get(s.get("id"), []),`.

- [x] **Step 5: Run the ai_schema suite**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_ai_schema.py -q`
Expected: all pass.

- [x] **Step 6: Commit**

```bash
git add nx_lib/reporting/ai_schema.py nx_lib/views/reporting.py tests/unit/test_reporting_ai_schema.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): ground Surface A in metrics and grainable fields" -m "The AI sources catalog now marks grainable (date) fields and lists each
source's canonical metrics (code, label, aggregation) so 'Build a
report' can draft metric/grain definitions. Partially addresses
usability gap #3 (thin grounding)."
```

### Task 7: ai.py system prompt + `_validate_definition_for_user` metrics/grain

**Files:**
- Modify: `nx_lib/reporting/ai.py:195-214` (`_SYSTEM_DEF`)
- Modify: `nx_lib/views/reporting.py:377-421` (`_validate_definition_for_user`)
- Test: `tests/unit/test_reporting_ai_definition.py`, `tests/integration/test_reporting_routes.py`

- [x] **Step 1: Extend `_SYSTEM_DEF`** — append to the string (before the chartHint sentence):

```python
    ' A source may list canonical "metrics" (code = aggregation(column)). To '
    'aggregate, include "metrics": [{"metric": "<code>"}] in the definition — '
    "the selected columns then become the GROUP BY dims. For a single grand "
    'total, use "metrics" with "columns": []. Only metric codes from the '
    "source's metrics line are valid. Fields flagged (grainable) are date "
    'fields: a column for one may carry "grain": '
    '"day"|"week"|"month"|"quarter"|"year" to bucket it; filters always use '
    "the raw date."
```

- [x] **Step 2: Fix `_validate_definition_for_user`** — mirror `_prepare_run`'s validator args (this is the verified spec gap):

```python
        catalog_fields = {f["field"] for f in catalog}
        filterable = {f["field"] for f in catalog if f["filterable"]}
        sortable = {f["field"] for f in catalog if f["sortable"]}
        grainable = {f["field"] for f in catalog if f.get("grainable")}
        source_metrics = _metrics_for_source(source["id"])
        ...
        validate_report_definition(
            to_validate,
            catalog_fields,
            filterable,
            sortable,
            max_row_limit=MAX_ROW_LIMIT,
            metric_codes=set(source_metrics),
            grainable_fields=grainable,
        )
```

- [x] **Step 3: Tests.** In `tests/unit/test_reporting_ai_definition.py` add a prompt-contract assertion; in the integration file, find the existing Surface-A build-route test (search `api/reporting/ai/build`) and add a draft-with-metrics acceptance test using its mock-transport pattern:

```python
# unit (test_reporting_ai_definition.py)
def test_system_def_documents_metrics_and_grain():
    from nx_lib.reporting.ai import _SYSTEM_DEF
    assert '"metrics"' in _SYSTEM_DEF
    assert '"grain"' in _SYSTEM_DEF
```

Integration: a definition `{..., "columns": [], "metrics": [{"metric": <seeded code>}]}` returned by the mocked model must come back `valid: true` from `POST /api/reporting/ai/build` (copy the route test's existing mock/seed pattern).

- [x] **Step 4: Run both suites**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_ai_definition.py tests/integration/test_reporting_routes.py -q`
Expected: all pass.

- [x] **Step 5: Commit**

```bash
git add nx_lib/reporting/ai.py nx_lib/views/reporting.py tests/unit/test_reporting_ai_definition.py tests/integration/test_reporting_routes.py
SQL_SYNC_SKIP=1 git commit -m "fix(reporting): Surface A validates and documents metrics + grain" -m "_validate_definition_for_user now passes metric_codes and
grainable_fields exactly like _prepare_run, so AI drafts using
canonical metrics or date grains validate instead of bouncing. The
system prompt documents the metrics/grain contract including
zero-column grand totals."
```

## Phase 3 — Tab shell

### Task 8: tabs + panes + initial-tab head script + e2e nav updates

**Files:**
- Modify: `templates/reporting.html` (head script lines 15-27; body structure lines 33-202)
- Create: `templates/js/_reporting_tabs_js.html`
- Modify: `static/css/reporting.css` (append after AI block — order-dependent file)
- Modify: every e2e nav: `tests/e2e/test_reporting.py:17`, `test_reporting_curated.py:16`, `test_reporting_load.py:15,46`, `test_reporting_save.py:14,48`, `test_reporting_schedule.py:14,39`, `test_reporting_share.py:15,40`, `test_reporting_sql.py:18`, `test_reporting_viz.py:16`, `test_reporting_metrics.py` (its goto)

- [x] **Step 1: Head script** — replace the rp-anim IIFE so the entrance only arms when landing on Advanced (Simple containers use `.nx-rise` instead; landing on Simple must not pre-hide the hidden Advanced columns):

```html
  <script>
    // Resolve the initial tab synchronously (?tab= > localStorage > 'simple')
    // and enable the no-FOUC builder entrance only when landing on Advanced
    // with motion allowed. Simple uses the design system's .nx-rise entrance.
    (function () {
      try {
        var tab = new URLSearchParams(window.location.search).get('tab')
          || localStorage.getItem('nx.reporting.tab') || 'simple';
        window.__rpInitialTab = tab === 'advanced' ? 'advanced' : 'simple';
        if (window.__rpInitialTab === 'advanced' &&
            (!window.matchMedia ||
             !window.matchMedia('(prefers-reduced-motion: reduce)').matches)) {
          document.documentElement.classList.add('rp-anim');
        }
      } catch (e) { window.__rpInitialTab = 'simple'; }
    }());
  </script>
```

- [x] **Step 2: Body structure** — after the `.nx-page-head` div (line 52), insert the tab strip and wrap the panes. The existing `<main class="reporting-main">...</main>` moves INSIDE `#rpPaneAdvanced` **unchanged byte-for-byte**; the three modals stay outside both panes:

```html
  <div class="nx-tabs reporting-tabs" role="tablist" aria-label="{{ _('Reporting view') }}" data-testid="reporting-tabs">
    <button id="rpTabSimple" class="nx-tab" role="tab" aria-selected="false"
            aria-controls="rpPaneSimple" data-testid="reporting-tab-simple">
      <i class="fas fa-table-cells-large" aria-hidden="true"></i>{{ _("Simple") }}</button>
    <button id="rpTabAdvanced" class="nx-tab" role="tab" aria-selected="false"
            aria-controls="rpPaneAdvanced" data-testid="reporting-tab-advanced">
      <i class="fas fa-sliders" aria-hidden="true"></i>{{ _("Advanced") }}</button>
  </div>

  <div id="rpPaneSimple" role="tabpanel" aria-labelledby="rpTabSimple" hidden>
    {% include '_reporting_simple.html' %}
  </div>
  <div id="rpPaneAdvanced" role="tabpanel" aria-labelledby="rpTabAdvanced" hidden>
    <main class="reporting-main" data-testid="reporting-page">
      ... (existing content, unmoved)
    </main>
  </div>
```

For this task `_reporting_simple.html` is created as a stub so the include resolves (`<section class="reporting-simple nx-rise" data-testid="reporting-simple"></section>` — Task 9 fills it).

- [x] **Step 3: Tabs controller** — create `templates/js/_reporting_tabs_js.html`, include it at the END of the body include list (after `_reporting_ai_js.html`) so all markup + `window.Reporting` exist:

```html
<script>
(function () {
  var ORDER = ['simple', 'advanced'];
  var EL = {
    simple:   { tab: 'rpTabSimple',   pane: 'rpPaneSimple' },
    advanced: { tab: 'rpTabAdvanced', pane: 'rpPaneAdvanced' }
  };
  var current = null;

  function show(name) {
    if (!EL[name]) name = 'simple';
    current = name;
    ORDER.forEach(function (k) {
      var tab = document.getElementById(EL[k].tab);
      var pane = document.getElementById(EL[k].pane);
      var active = k === name;
      tab.classList.toggle('is-active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
      tab.tabIndex = active ? 0 : -1;
      pane.hidden = !active;
    });
    try { localStorage.setItem('nx.reporting.tab', name); } catch (e) {}
    try {
      var url = new URL(window.location.href);
      url.searchParams.set('tab', name);
      history.replaceState(null, '', url);
    } catch (e) {}
    document.dispatchEvent(new CustomEvent('rp:tabshown', { detail: { tab: name } }));
  }

  ORDER.forEach(function (k) {
    var el = document.getElementById(EL[k].tab);
    el.addEventListener('click', function () { show(k); });
    el.addEventListener('keydown', function (e) {
      var i = ORDER.indexOf(current), next = null;
      if (e.key === 'ArrowRight') next = ORDER[(i + 1) % ORDER.length];
      else if (e.key === 'ArrowLeft') next = ORDER[(i - 1 + ORDER.length) % ORDER.length];
      else if (e.key === 'Home') next = ORDER[0];
      else if (e.key === 'End') next = ORDER[ORDER.length - 1];
      if (next) { e.preventDefault(); show(next); document.getElementById(EL[next].tab).focus(); }
    });
  });

  window.ReportingTabs = { show: show, current: function () { return current; } };
  show(window.__rpInitialTab || 'simple');
}());
</script>
```

- [x] **Step 4: CSS** — append to `static/css/reporting.css` (AFTER the AI block; the file is order-dependent):

```css
/* --- Simple/Advanced tabs (Spec 2) --- */
.reporting-tabs { margin: 0 24px 12px; }
```

- [x] **Step 5: e2e navigation updates** — in each listed file change `"/reporting"` → `"/reporting?tab=advanced"` in `_login` helpers and direct `page.goto(...)` calls (NOT `"/reporting/sources"`). 12 lines total.

- [x] **Step 6: Verify in browser + run e2e reporting tests**

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | %{ Stop-Process -Id $_.OwningProcess -Force }
# then: nx -u  (restart so Jinja re-reads templates)
.venv\Scripts\python.exe -m pytest tests/e2e/test_reporting.py tests/e2e/test_reporting_viz.py -q
```
Expected: pass. Manually: `/reporting` shows the (stub) Simple pane with two tabs; `?tab=advanced` shows the full builder with its entrance animation; switching tabs persists across reload.

- [x] **Step 7: Commit**

```bash
git add templates/reporting.html templates/_reporting_simple.html templates/js/_reporting_tabs_js.html static/css/reporting.css tests/e2e/
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): Simple/Advanced tab shell on /reporting" -m "Two client-side tabpanels under one route: ?tab= deep link >
localStorage > Simple default. Advanced wraps the existing builder
markup unmoved so the builder IIFE and e2e testids keep working; the
rp-anim entrance arms only when landing on Advanced. e2e tests now
navigate to /reporting?tab=advanced."
```

## Phase 4 — Simple pane

### Task 9: Simple pane markup + CSS

**Files:**
- Modify: `templates/_reporting_simple.html` (replace stub)
- Modify: `static/css/reporting.css` (append Simple styles)

- [x] **Step 1: Markup** — full pane (library + wizard + result view + AI bar). All ids prefixed `rs`. Key blocks (complete file):

```html
<section class="reporting-simple nx-rise" data-testid="reporting-simple">
  <div class="reporting-simple-top">
    <button id="rsNewReport" class="nx-btn nx-btn--primary" data-testid="rs-new-report">
      <i class="fas fa-plus" aria-hidden="true"></i>{{ _("New report") }}</button>
    {% if ai_enabled %}
    <div class="reporting-simple-aibar" id="rsAiBar" data-testid="rs-ai-bar">
      <input id="rsAiPrompt" class="reporting-input"
             placeholder="{{ _('Ask AI — e.g. “documents per month this year”') }}"
             data-testid="rs-ai-prompt">
      <button id="rsAiAsk" class="nx-btn nx-btn--secondary" data-testid="rs-ai-ask">
        <i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i>{{ _("Ask AI") }}</button>
    </div>
    {% endif %}
    <input id="rsSearch" class="reporting-input reporting-simple-search"
           placeholder="{{ _('Search reports…') }}" data-testid="rs-search">
  </div>

  <div id="rsLibrary" data-testid="rs-library">
    <h3 class="reporting-simple-h">{{ _("Library") }}</h3>
    <div id="rsGroupShared" class="reporting-simple-grid" data-testid="rs-group-shared"></div>
    <h3 class="reporting-simple-h">{{ _("My reports") }}</h3>
    <div id="rsGroupMine" class="reporting-simple-grid" data-testid="rs-group-mine"></div>
    <h3 class="reporting-simple-h">{{ _("Shared with me") }}</h3>
    <div id="rsGroupDirect" class="reporting-simple-grid" data-testid="rs-group-direct"></div>
  </div>

  <div id="rsWizard" class="reporting-simple-wizard" hidden data-testid="rs-wizard">
    <button id="rsWizardBack" class="reporting-link">&larr; {{ _("Back") }}</button>
    <div class="reporting-simple-step" id="rsStepMeasure">
      <h3 class="reporting-simple-h">1. {{ _("What do you want to measure?") }}</h3>
      <div id="rsMeasureList" class="reporting-simple-choices" data-testid="rs-measure-list"></div>
    </div>
    <div class="reporting-simple-step" id="rsStepBreakdown" hidden>
      <h3 class="reporting-simple-h">2. {{ _("Break it down by…") }}</h3>
      <div id="rsBreakdownList" class="reporting-simple-choices" data-testid="rs-breakdown-list"></div>
      <label id="rsGrainWrap" hidden>{{ _("Granularity") }}
        <select id="rsGrain" class="reporting-input">
          <option value="day">{{ _("Day") }}</option>
          <option value="week">{{ _("Week") }}</option>
          <option value="month" selected>{{ _("Month") }}</option>
          <option value="quarter">{{ _("Quarter") }}</option>
          <option value="year">{{ _("Year") }}</option>
        </select></label>
      <details id="rsScopeWrap" class="reporting-simple-scope" hidden>
        <summary>{{ _("Limit to specific processes") }}</summary>
        <div id="rsScopeList" data-testid="rs-scope-list"></div>
      </details>
    </div>
    <div class="reporting-simple-step" id="rsStepTime" hidden>
      <h3 class="reporting-simple-h">3. {{ _("Time range") }}</h3>
      <div class="reporting-simple-choices" id="rsTimeList" data-testid="rs-time-list"></div>
      <div id="rsTimeCustom" hidden>
        <input id="rsTimeRange" class="reporting-input" placeholder="{{ _('Pick a date range') }}">
      </div>
      <label id="rsTimeFieldWrap" hidden>{{ _("Date field") }}
        <select id="rsTimeField" class="reporting-input"></select></label>
      <button id="rsWizardRun" class="nx-btn nx-btn--primary" hidden data-testid="rs-wizard-run">
        {{ _("Show result") }}</button>
    </div>
  </div>

  <div id="rsResult" class="reporting-simple-result" hidden data-testid="rs-result">
    <div class="reporting-simple-resultbar">
      <button id="rsBack" class="reporting-link" data-testid="rs-back">&larr; {{ _("Back") }}</button>
      <h3 id="rsResultTitle" class="reporting-simple-rtitle"></h3>
      <span class="reporting-simple-ractions">
        <input id="rsSaveName" class="reporting-input" hidden data-testid="rs-save-name">
        <button id="rsSave" class="reporting-btn" data-testid="rs-save">{{ _("Save") }}</button>
        <button id="rsOpenAdvanced" class="reporting-btn" data-testid="rs-open-advanced">{{ _("Open in Advanced") }}</button>
        {% if has_permission('reporting.export') %}
        <button id="rsExport" class="reporting-btn" data-testid="rs-export">{{ _("Export") }}</button>
        {% endif %}
      </span>
    </div>
    <p id="rsMsg" class="reporting-ai-explain" hidden data-testid="rs-msg"></p>
    <p id="rsError" class="reporting-ai-error" hidden data-testid="rs-error"></p>
    <div class="reporting-simple-cards">
      <div class="nx-card nx-card--pad nx-stat reporting-simple-stat" id="rsStatCard" hidden data-testid="rs-stat-card">
        <div>
          <p class="nx-stat__label" id="rsStatLabel"></p>
          <div class="nx-stat__value" id="rsStatValue"></div>
        </div>
        <i class="fas fa-chart-simple nx-stat__icon" aria-hidden="true"></i>
      </div>
      <div class="nx-card nx-card--pad reporting-simple-chartcard" id="rsChartCard" hidden data-testid="rs-chart-card">
        <canvas id="rsChartCanvas"></canvas>
      </div>
    </div>
    <button id="rsTableToggle" class="reporting-link" hidden data-testid="rs-table-toggle">{{ _("Show table") }}</button>
    <div id="rsTableWrap" class="reporting-table-wrap reporting-simple-table" hidden data-testid="rs-table"></div>
  </div>
</section>
{% include 'js/_reporting_simple_js.html' %}
```

(The JS include lives inside the pane partial so the pane is self-contained; create `templates/js/_reporting_simple_js.html` as an empty `<script>(function () {}());</script>` stub in this task — Tasks 10-13 fill it.)

- [x] **Step 2: CSS** — append to `static/css/reporting.css`:

```css
/* --- Simple pane (Spec 2) --- */
.reporting-simple { padding: 0 24px 32px; max-width: 1100px; margin: 0 auto; }
.reporting-simple-top { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 20px; }
.reporting-simple-aibar { display: flex; gap: 8px; flex: 1; min-width: 260px; }
.reporting-simple-aibar .reporting-input { flex: 1; }
.reporting-simple-search { max-width: 220px; margin-left: auto; }
.reporting-simple-h { font-size: 13px; font-weight: 600; color: #57606a; text-transform: uppercase; letter-spacing: .04em; margin: 18px 0 10px; }
.reporting-simple-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.reporting-simple-card { text-align: left; cursor: pointer; border: 1px solid var(--nx-border, #d0d7de); border-radius: 8px; padding: 12px 14px; background: #fff; font-family: inherit; }
.reporting-simple-card:hover { border-color: var(--nx-accent, #4f46e5); box-shadow: 0 2px 8px rgba(79,70,229,.12); }
.reporting-simple-card .rs-card-name { font-weight: 600; font-size: 14px; margin: 0 0 4px; }
.reporting-simple-card .rs-card-meta { font-size: 12px; color: #57606a; margin: 0; }
.reporting-simple-empty { font-size: 13px; color: #57606a; padding: 8px 0 4px; }
.reporting-simple-step { margin: 18px 0; }
.reporting-simple-choices { display: flex; flex-wrap: wrap; gap: 8px; }
.reporting-simple-choice { border: 1px solid var(--nx-border, #d0d7de); border-radius: 999px; background: #fff; padding: 7px 14px; font-size: 13px; cursor: pointer; font-family: inherit; }
.reporting-simple-choice.is-selected { border-color: var(--nx-accent, #4f46e5); background: #eef2ff; font-weight: 600; }
.reporting-simple-scope { margin-top: 10px; font-size: 13px; }
.reporting-simple-scope label { display: block; padding: 2px 0; }
.reporting-simple-resultbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
.reporting-simple-rtitle { margin: 0; font-size: 16px; flex: 1; }
.reporting-simple-ractions { display: flex; gap: 8px; align-items: center; }
.reporting-simple-cards { display: grid; grid-template-columns: 260px 1fr; gap: 14px; align-items: start; }
.reporting-simple-chartcard { min-height: 260px; }
.reporting-simple-table { margin-top: 12px; }
@media (max-width: 800px) { .reporting-simple-cards { grid-template-columns: 1fr; } }
```

- [x] **Step 3: Restart the dev server, eyeball `/reporting`** — pane renders (static markup, no behavior yet), no console errors.

- [x] **Step 4: Commit**

```bash
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html static/css/reporting.css
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): Simple pane markup and styles" -m "Library groups (org-shared / mine / shared-with-me), guided wizard
steps, card-based result view, and the optional Ask-AI bar — markup +
CSS only; behavior lands in the Simple pane IIFE next."
```

### Task 10: Simple JS — scaffold + library

**Files:**
- Modify: `templates/js/_reporting_simple_js.html`

- [x] **Step 1: Write the IIFE scaffold + library logic** (complete partial at this stage):

```html
<script>
(function () {
  var csrf = document.querySelector('meta[name="csrf-token"]').content;
  var EXPORT_ALLOWED = !!document.getElementById('rsExport');
  var state = {
    reports: [],            // /api/reporting/reports rows (kind!=='sql')
    sources: null,          // /api/reporting/sources cache
    metricsBySource: null,  // /api/reporting/metrics cache
    loaded: false,
    view: 'library',        // library | wizard | result
    current: null,          // { def, name, reportId, owned, canEdit, fromWizard }
    chart: null,            // private Chart.js instance
    wiz: null               // wizard state, see Task 12
  };

  function el(id) { return document.getElementById(id); }

  async function api(url, opts) {
    opts = opts || {};
    var res = await fetch(url, Object.assign(
      { headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf } }, opts));
    var data = null;
    try { data = await res.json(); } catch (e) { /* non-JSON */ }
    return { ok: res.ok, status: res.status, data: data };
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function relTime(iso) {
    var d = new Date(iso); if (isNaN(d)) return '';
    var days = Math.floor((Date.now() - d.getTime()) / 86400000);
    if (days <= 0) return '{{ _("today") }}';
    if (days === 1) return '{{ _("yesterday") }}';
    if (days < 7) return days + ' {{ _("days ago") }}';
    var w = Math.floor(days / 7);
    return w + (w === 1 ? ' {{ _("week ago") }}' : ' {{ _("weeks ago") }}');
  }

  function setView(view) {
    state.view = view;
    el('rsLibrary').hidden = view !== 'library';
    el('rsSearch').hidden = view !== 'library';
    el('rsWizard').hidden = view !== 'wizard';
    el('rsResult').hidden = view !== 'result';
    if (view !== 'result') destroyChart();
  }

  function destroyChart() {
    if (state.chart) { state.chart.destroy(); state.chart = null; }
  }

  // ---------- Library ----------
  function card(r) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'reporting-simple-card';
    b.setAttribute('data-testid', 'rs-card');
    b.innerHTML = '<p class="rs-card-name">' + esc(r.name) + '</p>' +
      '<p class="rs-card-meta">' + esc(r.ownerName || '') + ' · ' + relTime(r.updatedAt) + '</p>';
    b.addEventListener('click', function () { openReport(r); });
    return b;
  }

  function renderLibrary() {
    var q = (el('rsSearch').value || '').toLowerCase();
    var groups = { shared: el('rsGroupShared'), mine: el('rsGroupMine'), direct: el('rsGroupDirect') };
    Object.keys(groups).forEach(function (k) { groups[k].innerHTML = ''; });
    state.reports.forEach(function (r) {
      if (q && r.name.toLowerCase().indexOf(q) === -1) return;
      var g = r.visibility === 'shared' ? 'shared' : (r.owned ? 'mine' : 'direct');
      groups[g].appendChild(card(r));
    });
    Object.keys(groups).forEach(function (k) {
      if (!groups[k].children.length) {
        groups[k].innerHTML = '<p class="reporting-simple-empty">{{ _("Nothing here yet.") }}</p>';
      }
    });
  }

  async function loadLibrary() {
    var res = await api('/api/reporting/reports');
    if (!res.ok || !Array.isArray(res.data)) return;
    state.reports = res.data.filter(function (r) { return r.kind !== 'sql'; });
    renderLibrary();
  }

  async function openReport(r) {
    var res = await api('/api/reporting/reports/' + r.id);
    if (!res.ok || !res.data || !res.data.definition) {
      showResultError('{{ _("Could not load this report.") }}'); return;
    }
    state.current = {
      def: res.data.definition, name: res.data.name, reportId: r.id,
      owned: !!res.data.owned, canEdit: !!res.data.canEdit, fromWizard: false
    };
    runCurrent();  // Task 11
  }

  // ---------- init ----------
  function initOnce() {
    if (state.loaded) return;
    state.loaded = true;
    loadLibrary();
  }

  el('rsSearch').addEventListener('input', renderLibrary);
  el('rsBack').addEventListener('click', function () { setView('library'); loadLibrary(); });

  document.addEventListener('rp:tabshown', function (e) {
    if (e.detail.tab === 'simple') initOnce();
  });
  if (window.ReportingTabs && window.ReportingTabs.current() === 'simple') initOnce();
}());
</script>
```

**Note on include order:** the tabs controller (`_reporting_tabs_js.html`) is included at the END of body, AFTER this partial — so the initial `rp:tabshown` from its `show()` call fires after this listener is registered. Verify that ordering holds in `reporting.html`; the last include must be the tabs partial.

- [x] **Step 2: Browser-verify** — restart server; `/reporting` lists existing saved reports grouped; search filters; a `kind:'sql'` saved report does NOT appear; clicking a card calls `runCurrent` (stub it to `console.log` until Task 11 if needed).

- [x] **Step 3: Commit**

```bash
git add templates/js/_reporting_simple_js.html templates/reporting.html
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): Simple library — grouped report cards + search" -m "One fetch of /api/reporting/reports grouped client-side into Library
(org-shared), My reports, and Shared with me; sql-kind rows are hidden
from Simple. Lazy: a report only runs when opened."
```

### Task 11: Simple JS — result view (cards, chart, table, save, open-in-advanced, export)

**Files:**
- Modify: `templates/js/_reporting_simple_js.html`

- [x] **Step 1: Implement the result view** (add these functions; `runCurrent` replaces the Task-10 stub):

```javascript
  // ---------- Result view ----------
  function showResultError(msg) {
    setView('result');
    el('rsError').textContent = msg;
    el('rsError').hidden = false;
    el('rsStatCard').hidden = true;
    el('rsChartCard').hidden = true;
    el('rsTableToggle').hidden = true;
    el('rsTableWrap').hidden = true;
  }

  function friendlyRunError(status, data) {
    if (status === 403) return '{{ _("You don\'t have access to the data behind this report.") }}';
    if (status === 400) return '{{ _("This report is outdated — open it in Advanced to fix it.") }}';
    return (data && data.error) || '{{ _("Could not run this report.") }}';
  }

  function fmtNumber(v) {
    if (v == null) return '–';
    var n = Number(v);
    return isNaN(n) ? String(v) : n.toLocaleString();
  }

  function metricLabelFor(def) {
    var m = (def.metrics && def.metrics[0]) || null;
    if (!m || !state.metricsBySource) return m ? m.metric : '';
    var list = state.metricsBySource[def.source] || [];
    var hit = list.find(function (x) { return x.code === m.metric; });
    return hit ? hit.label : m.metric;
  }

  function renderTable(columns, rows) {
    var html = '<table class="reporting-table"><thead><tr>';
    columns.forEach(function (c) { html += '<th>' + esc(c.header || c.field) + '</th>'; });
    html += '</tr></thead><tbody>';
    rows.forEach(function (r) {
      html += '<tr>';
      r.forEach(function (v) { html += '<td>' + esc(v == null ? '' : v) + '</td>'; });
      html += '</tr>';
    });
    html += '</tbody></table>';
    el('rsTableWrap').innerHTML = html;
  }

  function mountChart(def, columns, rows) {
    destroyChart();
    var dims = (def.columns || []).length;
    if (!dims || !rows.length || rows.length > 50) { el('rsChartCard').hidden = true; return; }
    var firstCol = def.columns[0];
    var isDate = !!firstCol.grain ||
      /date/.test(firstCol.field);
    var metricIdx = columns.length - (def.metrics || []).length;
    var labels = rows.map(function (r) { return String(r[0] == null ? '' : r[0]).slice(0, 10); });
    var datasets = (def.metrics || []).map(function (m, i) {
      return {
        label: columns[metricIdx + i] ? (columns[metricIdx + i].header || m.metric) : m.metric,
        data: rows.map(function (r) { return Number(r[metricIdx + i]); }),
        borderColor: '#4f46e5', backgroundColor: 'rgba(79,70,229,.45)', tension: .25
      };
    });
    el('rsChartCard').hidden = false;
    state.chart = new Chart(el('rsChartCanvas'), {
      type: isDate ? 'line' : 'bar',
      data: { labels: labels, datasets: datasets },
      options: { responsive: true, maintainAspectRatio: false,
                 plugins: { legend: { display: datasets.length > 1 } } }
    });
  }

  async function runCurrent() {
    var cur = state.current;
    setView('result');
    el('rsError').hidden = true;
    el('rsMsg').hidden = true;
    el('rsResultTitle').textContent = cur.name || cur.def.title || '';
    el('rsSaveName').hidden = true;
    el('rsStatCard').hidden = true;
    el('rsChartCard').hidden = true;
    el('rsTableToggle').hidden = true;
    el('rsTableWrap').hidden = true;

    var def = cur.def;
    var hasMetrics = Array.isArray(def.metrics) && def.metrics.length > 0;

    // Grand total: zero-column clone (correct for every aggregation, unlike a
    // client-side sum over grouped rows).
    if (hasMetrics) {
      var totalDef = JSON.parse(JSON.stringify(def));
      totalDef.columns = [];
      totalDef.sort = [];
      var t = await api('/api/reporting/run', { method: 'POST', body: JSON.stringify(totalDef) });
      if (t.ok && t.data && t.data.rows && t.data.rows.length) {
        el('rsStatLabel').textContent = metricLabelFor(def);
        el('rsStatValue').textContent = fmtNumber(t.data.rows[0][0]);
        el('rsStatCard').hidden = false;
      }
    }

    // Breakdown run (or the plain table run for non-metric definitions).
    var res = await api('/api/reporting/run', { method: 'POST', body: JSON.stringify(def) });
    if (!res.ok) { showResultError(friendlyRunError(res.status, res.data)); return; }
    var columns = res.data.columns || [], rows = res.data.rows || [];
    if (!rows.length && el('rsStatCard').hidden) {
      el('rsTableWrap').innerHTML =
        '<div class="nx-empty"><div class="nx-empty__art"><i class="fas fa-inbox"></i></div>' +
        '<p class="nx-empty__title">{{ _("No data for this report") }}</p></div>';
      el('rsTableWrap').hidden = false;
      return;
    }
    if (hasMetrics && (def.columns || []).length) mountChart(def, columns, rows);
    renderTable(columns, rows);
    if (hasMetrics) {
      el('rsTableToggle').hidden = false;
      el('rsTableToggle').textContent = '{{ _("Show table") }}';
      el('rsTableWrap').hidden = true;
    } else {
      el('rsTableWrap').hidden = false;   // plain table reports: grid directly
    }
  }

  el('rsTableToggle').addEventListener('click', function () {
    var w = el('rsTableWrap');
    w.hidden = !w.hidden;
    el('rsTableToggle').textContent = w.hidden ? '{{ _("Show table") }}' : '{{ _("Hide table") }}';
  });

  // Save: always a NEW row (inline name input, no window.prompt).
  el('rsSave').addEventListener('click', async function () {
    var nameInput = el('rsSaveName');
    if (nameInput.hidden) {
      nameInput.hidden = false;
      nameInput.value = state.current.name || state.current.def.title || '';
      nameInput.focus();
      return;
    }
    var name = nameInput.value.trim();
    if (!name) return;
    var res = await api('/api/reporting/reports', {
      method: 'POST',
      body: JSON.stringify({ name: name, definition: state.current.def })
    });
    if (res.ok) {
      nameInput.hidden = true;
      el('rsMsg').textContent = '{{ _("Saved to My reports.") }}';
      el('rsMsg').hidden = false;
    } else {
      showResultError((res.data && res.data.error) || '{{ _("Could not save.") }}');
    }
  });

  // Open in Advanced. id:null for non-owned reports is LOAD-BEARING: CanEdit
  // shares mutate shared reports in place; a null id makes Advanced's Save
  // default to create-a-copy.
  el('rsOpenAdvanced').addEventListener('click', function () {
    var cur = state.current;
    if (!window.Reporting || !window.Reporting.applyDefinition) return;
    var id = (cur.owned && cur.canEdit) ? cur.reportId : null;
    window.Reporting.applyDefinition(cur.def, cur.name || cur.def.title, id);
    window.ReportingTabs.show('advanced');
  });

  if (EXPORT_ALLOWED) {
    el('rsExport').addEventListener('click', async function () {
      var body = Object.assign({}, state.current.def, { format: 'xlsx' });
      var res = await fetch('/api/reporting/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify(body)
      });
      if (!res.ok) { showResultError('{{ _("Could not export this report.") }}'); return; }
      var blob = await res.blob();
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = (state.current.name || 'report') + '.xlsx';
      a.click();
      URL.revokeObjectURL(a.href);
    });
  }
```

Also extend `initOnce` to prefetch the metrics catalog (needed by `metricLabelFor` + the wizard):

```javascript
  async function loadMetricsCatalog() {
    var res = await api('/api/reporting/metrics');
    if (res.ok && res.data) state.metricsBySource = res.data;
  }
  // in initOnce(): loadMetricsCatalog(); loadLibrary();
```

- [x] **Step 2: Browser-verify** — open a saved metric report from the library: number card + chart + table toggle work; a plain table report renders the grid directly; Save creates a new row (appears under My reports after Back); Open in Advanced pre-fills the builder and switches tab; Export downloads.

- [x] **Step 3: Commit**

```bash
git add templates/js/_reporting_simple_js.html
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): Simple result view — cards, chart, save, handoff" -m "Two-run result view: a zero-column clone for the correct grand total
plus the breakdown run for chart + table. Private Chart.js instance
(never ReportingViz.mountChart). Save always creates a new row; Open
in Advanced passes id:null for non-owned reports so Advanced's Save
defaults to create-a-copy. Friendly 403/400/empty states."
```

### Task 12: Simple JS — guided wizard

**Files:**
- Modify: `templates/js/_reporting_simple_js.html`

- [x] **Step 1: Implement the wizard** (add; uses `state.wiz`):

```javascript
  // ---------- Wizard ----------
  function choiceBtn(label, onpick) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'reporting-simple-choice';
    b.textContent = label;
    b.addEventListener('click', function () {
      Array.prototype.forEach.call(b.parentNode.children, function (s) {
        s.classList.remove('is-selected');
      });
      b.classList.add('is-selected');
      onpick();
    });
    return b;
  }

  async function loadSourcesCatalog() {
    if (state.sources) return state.sources;
    var res = await api('/api/reporting/sources');
    state.sources = (res.ok && Array.isArray(res.data)) ? res.data : [];
    return state.sources;
  }

  async function startWizard() {
    await loadSourcesCatalog();
    if (!state.metricsBySource) await loadMetricsCatalog();
    state.wiz = { measure: null, source: null, breakdown: null, grain: 'month',
                  scopeProcs: [], range: null, dateField: null };
    setView('wizard');
    el('rsStepBreakdown').hidden = true;
    el('rsStepTime').hidden = true;
    el('rsWizardRun').hidden = true;
    renderMeasureStep();
  }

  function renderMeasureStep() {
    var list = el('rsMeasureList');
    list.innerHTML = '';
    var multi = Object.keys(state.metricsBySource || {}).length > 1;
    Object.keys(state.metricsBySource || {}).forEach(function (sid) {
      var src = (state.sources || []).find(function (s) { return s.id === sid; });
      if (!src) return;  // metric's source not visible to this user
      (state.metricsBySource[sid] || []).forEach(function (m) {
        var label = multi ? (m.label + ' · ' + src.label) : m.label;
        list.appendChild(choiceBtn(label, function () {
          state.wiz.measure = m;
          state.wiz.source = src;   // picking a measure pins the source
          renderBreakdownStep();
        }));
      });
    });
    if (!list.children.length) {
      list.innerHTML = '<p class="reporting-simple-empty">' +
        '{{ _("No measures are configured yet — ask an administrator to add metrics.") }}</p>';
    }
  }

  function renderBreakdownStep() {
    el('rsStepBreakdown').hidden = false;
    var list = el('rsBreakdownList');
    list.innerHTML = '';
    el('rsGrainWrap').hidden = true;
    var fields = state.wiz.source.fields || [];
    var dateFields = fields.filter(function (f) { return f.grainable; });
    var catFields = fields.filter(function (f) { return f.type === 'string' && f.filterable; });

    dateFields.forEach(function (f) {
      list.appendChild(choiceBtn('{{ _("Over time") }} (' + f.label + ')', function () {
        state.wiz.breakdown = { kind: 'date', field: f };
        el('rsGrainWrap').hidden = false;
        renderTimeStep();
      }));
    });
    catFields.slice(0, 12).forEach(function (f) {
      list.appendChild(choiceBtn(f.label, function () {
        state.wiz.breakdown = { kind: 'category', field: f };
        el('rsGrainWrap').hidden = true;
        renderTimeStep();
      }));
    });
    list.appendChild(choiceBtn('{{ _("None — just the total") }}', function () {
      state.wiz.breakdown = { kind: 'none' };
      el('rsGrainWrap').hidden = true;
      renderTimeStep();
    }));

    // Optional collapsed process picker (docprocessing only).
    var scopeWrap = el('rsScopeWrap');
    var procs = state.wiz.source.processes || [];
    scopeWrap.hidden = !procs.length;
    if (procs.length) {
      var box = el('rsScopeList');
      box.innerHTML = '';
      procs.forEach(function (p) {
        var lbl = document.createElement('label');
        var cb = document.createElement('input');
        cb.type = 'checkbox'; cb.value = p; cb.checked = true;
        cb.addEventListener('change', function () {
          state.wiz.scopeProcs = Array.prototype.filter.call(
            box.querySelectorAll('input:checked'), function () { return true; }
          ).map(function (c) { return c.value; });
          // re-collect properly:
          state.wiz.scopeProcs = Array.prototype.map.call(
            box.querySelectorAll('input:checked'), function (c) { return c.value; });
        });
        lbl.appendChild(cb);
        lbl.appendChild(document.createTextNode(' ' + p));
        box.appendChild(lbl);
      });
      state.wiz.scopeProcs = procs.slice();
    }
  }

  function isoDate(d) { return d.toISOString().slice(0, 10); }

  function presetRange(key) {
    var now = new Date(), y = now.getFullYear(), m = now.getMonth();
    if (key === 'this_month') return [new Date(y, m, 1), new Date(y, m + 1, 0)];
    if (key === 'last_month') return [new Date(y, m - 1, 1), new Date(y, m, 0)];
    if (key === 'last_3_months') return [new Date(y, m - 2, 1), new Date(y, m + 1, 0)];
    if (key === 'this_year') return [new Date(y, 0, 1), new Date(y, 11, 31)];
    if (key === 'last_year') return [new Date(y - 1, 0, 1), new Date(y - 1, 11, 31)];
    return null;  // all_time
  }

  function renderTimeStep() {
    el('rsStepTime').hidden = false;
    el('rsWizardRun').hidden = false;
    var fields = state.wiz.source.fields || [];
    var dateFields = fields.filter(function (f) { return f.grainable; });
    // Skip the step when the source has no date field.
    if (!dateFields.length) {
      el('rsTimeList').innerHTML = '<p class="reporting-simple-empty">{{ _("This source has no date field — showing all data.") }}</p>';
      el('rsTimeFieldWrap').hidden = true;
      state.wiz.range = null;
      return;
    }
    // Date-field select: defaults to import_date when present.
    var sel = el('rsTimeField');
    sel.innerHTML = '';
    dateFields.forEach(function (f) {
      var o = document.createElement('option');
      o.value = f.field; o.textContent = f.label;
      sel.appendChild(o);
    });
    if (dateFields.some(function (f) { return f.field === 'import_date'; })) sel.value = 'import_date';
    el('rsTimeFieldWrap').hidden = dateFields.length < 2;
    state.wiz.dateField = sel.value;
    sel.onchange = function () { state.wiz.dateField = sel.value; };

    var list = el('rsTimeList');
    list.innerHTML = '';
    [['this_month', '{{ _("This month") }}'], ['last_month', '{{ _("Last month") }}'],
     ['last_3_months', '{{ _("Last 3 months") }}'], ['this_year', '{{ _("This year") }}'],
     ['last_year', '{{ _("Last year") }}'], ['all_time', '{{ _("All time") }}'],
     ['custom', '{{ _("Custom") }}']].forEach(function (p) {
      list.appendChild(choiceBtn(p[1], function () {
        el('rsTimeCustom').hidden = p[0] !== 'custom';
        if (p[0] === 'custom') {
          if (!state.wiz._fp && window.flatpickr) {
            state.wiz._fp = flatpickr(el('rsTimeRange'), {
              mode: 'range', dateFormat: 'Y-m-d',
              onChange: function (sel2) {
                if (sel2.length === 2) state.wiz.range = [isoDate(sel2[0]), isoDate(sel2[1])];
              }
            });
          }
          state.wiz.range = null;
        } else {
          var r = presetRange(p[0]);
          state.wiz.range = r ? [isoDate(r[0]), isoDate(r[1])] : null;
        }
      }));
    });
    // default: all time
    state.wiz.range = null;
  }

  function wizardDefinition() {
    var w = state.wiz;
    var columns = [], sort = [], filters = [];
    var title = w.measure.label;
    if (w.breakdown.kind === 'date') {
      columns.push({ field: w.breakdown.field.field, header: w.breakdown.field.label,
                     grain: el('rsGrain').value });
      sort.push({ field: w.breakdown.field.field, dir: 'asc' });
      title += ' {{ _("per") }} ' + el('rsGrain').options[el('rsGrain').selectedIndex].text.toLowerCase();
    } else if (w.breakdown.kind === 'category') {
      columns.push({ field: w.breakdown.field.field, header: w.breakdown.field.label });
      sort.push({ field: w.measure.code, dir: 'desc' });
      title += ' {{ _("by") }} ' + w.breakdown.field.label;
    }
    if (w.range && w.dateField) {
      filters.push({ field: w.dateField, op: 'between', value: w.range });
    }
    var scope = { clients: [], processes: [] };
    var allProcs = w.source.processes || [];
    if (allProcs.length && w.scopeProcs.length && w.scopeProcs.length < allProcs.length) {
      scope.processes = w.scopeProcs.slice();
    }
    return {
      schemaVersion: 1, source: w.source.id, visualization: 'table',
      title: title, subtitle: null,
      columns: columns,
      metrics: [{ metric: w.measure.code }],
      filters: filters, sort: sort, scope: scope, rowLimit: 5000
    };
  }

  el('rsNewReport').addEventListener('click', startWizard);
  el('rsWizardBack').addEventListener('click', function () { setView('library'); });
  el('rsWizardRun').addEventListener('click', function () {
    if (!state.wiz.measure || !state.wiz.breakdown) return;
    var def = wizardDefinition();
    state.current = { def: def, name: def.title, reportId: null,
                      owned: true, canEdit: true, fromWizard: true };
    runCurrent();
  });
```

Wizard invariants honored (validator-enforced server-side): sort fields ⊆ selected columns ∪ metric codes; grain only on grainable fields; metric codes from the registry; `between` filter always on the **raw** date field.

- [x] **Step 2: Browser-verify** — "+ New report" → pick a measure → breakdown choices show date + category + none → time presets → "Show result" renders the result view. Verify the zero-dim path ("None — just the total") shows only the number card.

- [x] **Step 3: Commit**

```bash
git add templates/js/_reporting_simple_js.html
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): Simple guided wizard — measure, breakdown, time" -m "Progressive-disclosure wizard assembling a standard v1 definition:
measure from the metrics registry (pins the source), breakdown over
time (grain select, default month) / by category / none, time-range
presets emitting a between filter on the raw date field, optional
collapsed process scope. Output is saveable and opens in Advanced."
```

### Task 13: Simple JS — ask-AI helper

**Files:**
- Modify: `templates/js/_reporting_simple_js.html`

- [x] **Step 1: Implement** (the bar exists only `{% if ai_enabled %}`, so guard on element presence):

```javascript
  // ---------- Ask-AI helper ----------
  var aiBar = el('rsAiBar');
  if (aiBar) {
    el('rsAiAsk').addEventListener('click', askAi);
    el('rsAiPrompt').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') askAi();
    });
  }

  async function askAi() {
    var q = el('rsAiPrompt').value.trim();
    if (!q) return;
    el('rsAiAsk').disabled = true;
    var res = await api('/api/reporting/ai/build', {
      method: 'POST', body: JSON.stringify({ question: q })
    });
    el('rsAiAsk').disabled = false;
    if (res.status === 503) { aiBar.hidden = true; return; }   // AI unconfigured
    if (res.status === 429) {
      showResultError('{{ _("The AI daily limit is reached — try again tomorrow.") }}');
      return;
    }
    // Check data.valid, not res.ok: the route returns 200 for invalid drafts.
    if (!res.ok || !res.data || !res.data.valid || !res.data.definition) {
      var why = (res.data && (res.data.explanation || res.data.error)) || '';
      showResultError('{{ _("The AI could not draft that report — try rephrasing.") }}' +
        (why ? ' (' + why + ')' : ''));
      return;
    }
    state.current = { def: res.data.definition, name: res.data.definition.title,
                      reportId: null, owned: true, canEdit: true, fromWizard: true };
    runCurrent();
  }
```

- [x] **Step 2: Browser-verify on INT** (AI is live on INT via Azure) — ask "how many documents per month this year"; expect the result view with a definition using `doc_count` + month grain (slice B grounding). Also verify the invalid-draft path shows the friendly message.

- [x] **Step 3: Commit**

```bash
git add templates/js/_reporting_simple_js.html
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): Simple ask-AI helper drafting straight to cards" -m "One input to /api/reporting/ai/build; a valid draft renders directly
in the Simple result view. Degrades: 503 hides the bar, 429 shows the
daily-cap message, invalid drafts ask to rephrase. Checks data.valid,
not res.ok."
```

## Phase 5 — Tests, i18n, docs, verify

### Task 14: new e2e — tabs + library

**Files:**
- Create: `tests/e2e/test_reporting_simple.py`

- [x] **Step 1: Write the tests** (mirror the `_login` helper + fixture style of `tests/e2e/test_reporting.py`):

```python
"""e2e: Simple/Advanced tabs + the Simple library."""

import re

from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")


def test_default_tab_is_simple(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    expect(page.get_by_test_id("reporting-simple")).to_be_visible()
    expect(page.get_by_test_id("reporting-field-panel")).to_be_hidden()


def test_tab_param_overrides_to_advanced(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    expect(page.get_by_test_id("reporting-field-panel")).to_be_visible()
    expect(page.get_by_test_id("reporting-simple")).to_be_hidden()


def test_tab_choice_sticks_across_reload(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    page.get_by_test_id("reporting-tab-advanced").click()
    expect(page.get_by_test_id("reporting-field-panel")).to_be_visible()
    page.goto(f"{nexora_server}/reporting")  # no ?tab param
    expect(page.get_by_test_id("reporting-field-panel")).to_be_visible()


def test_library_groups_and_hides_sql_kind(nexora_server, page):
    _login(page, nexora_server)
    # Create a table report + a sql-kind report via the API from the page
    # context (cookies + CSRF available in-page).
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const mk = (name, definition) => fetch('/api/reporting/reports', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify({name, definition})
          });
          await mk('e2e simple lib', {schemaVersion: 1, source: 'docprocessing',
            visualization: 'table', title: 'e2e simple lib',
            columns: [{field: 'processname'}], filters: [], sort: [],
            scope: {clients: [], processes: []}, rowLimit: 100});
          await mk('e2e sql hidden', {kind: 'sql', target: 'statistics',
            sql: 'SELECT 1', title: 'e2e sql hidden'});
        }"""
    )
    page.goto(f"{nexora_server}/reporting")
    expect(page.get_by_test_id("rs-group-mine")).to_contain_text("e2e simple lib")
    expect(page.get_by_test_id("reporting-simple")).not_to_contain_text("e2e sql hidden")
```

- [x] **Step 2: Run**

Run: `.venv\Scripts\python.exe -m pytest tests/e2e/test_reporting_simple.py -q`
Expected: all pass (requires the dev server fixture; same as other e2e).

- [x] **Step 3: Commit**

```bash
git add tests/e2e/test_reporting_simple.py
SQL_SYNC_SKIP=1 git commit -m "test(reporting): e2e for tab default, stickiness, and library" -m "Covers Simple as the default tab, ?tab=advanced deep link,
localStorage stickiness, library grouping, and sql-kind reports being
hidden from Simple."
```

### Task 15: i18n cycle

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.{po,mo}`

- [x] **Step 1: Extract + update**

```powershell
.venv\Scripts\pybabel.exe extract -F babel.cfg -o messages.pot .
.venv\Scripts\pybabel.exe update -i messages.pot -d translations
```

- [x] **Step 2: Translate the new msgids** in de/fr/it; **clear every `#, fuzzy` flag** pybabel auto-adds (last session they were wrong auto-matches). New msgids and translations:

| msgid | de | fr | it |
|---|---|---|---|
| Simple | Einfach | Simple | Semplice |
| Advanced | Erweitert | Avancé | Avanzato |
| Reporting view | Reporting-Ansicht | Vue du reporting | Vista reporting |
| New report | Neuer Bericht | Nouveau rapport | Nuovo report |
| Ask AI — e.g. “documents per month this year” | KI fragen — z. B. «Dokumente pro Monat dieses Jahr» | Demander à l'IA — p. ex. « documents par mois cette année » | Chiedi all'IA — ad es. «documenti al mese quest'anno» |
| Ask AI | KI fragen | Demander à l'IA | Chiedi all'IA |
| Search reports… | Berichte durchsuchen… | Rechercher des rapports… | Cerca report… |
| Library | Bibliothek | Bibliothèque | Libreria |
| My reports | Meine Berichte | Mes rapports | I miei report |
| Shared with me | Mit mir geteilt | Partagés avec moi | Condivisi con me |
| Nothing here yet. | Noch nichts vorhanden. | Rien ici pour l'instant. | Ancora niente qui. |
| What do you want to measure? | Was möchten Sie messen? | Que voulez-vous mesurer ? | Cosa vuoi misurare? |
| Break it down by… | Aufschlüsseln nach… | Ventiler par… | Suddividi per… |
| Granularity | Granularität | Granularité | Granularità |
| Limit to specific processes | Auf bestimmte Prozesse einschränken | Limiter à certains processus | Limita a processi specifici |
| Time range | Zeitraum | Période | Intervallo di tempo |
| This month | Dieser Monat | Ce mois-ci | Questo mese |
| Last month | Letzter Monat | Le mois dernier | Il mese scorso |
| Last 3 months | Letzte 3 Monate | Les 3 derniers mois | Ultimi 3 mesi |
| This year | Dieses Jahr | Cette année | Quest'anno |
| Last year | Letztes Jahr | L'année dernière | L'anno scorso |
| All time | Gesamter Zeitraum | Toute la période | Tutto il periodo |
| Custom | Benutzerdefiniert | Personnalisé | Personalizzato |
| Pick a date range | Zeitraum wählen | Choisir une période | Scegli un intervallo di date |
| Date field | Datumsfeld | Champ de date | Campo data |
| Show result | Ergebnis anzeigen | Afficher le résultat | Mostra risultato |
| Back | Zurück | Retour | Indietro |
| Open in Advanced | In Erweitert öffnen | Ouvrir dans Avancé | Apri in Avanzato |
| Show table | Tabelle anzeigen | Afficher le tableau | Mostra tabella |
| Hide table | Tabelle ausblenden | Masquer le tableau | Nascondi tabella |
| Saved to My reports. | Unter «Meine Berichte» gespeichert. | Enregistré dans « Mes rapports ». | Salvato in «I miei report». |
| Could not save. | Speichern fehlgeschlagen. | Échec de l'enregistrement. | Salvataggio non riuscito. |
| Could not load this report. | Bericht konnte nicht geladen werden. | Impossible de charger ce rapport. | Impossibile caricare questo report. |
| Could not run this report. | Bericht konnte nicht ausgeführt werden. | Impossible d'exécuter ce rapport. | Impossibile eseguire questo report. |
| Could not export this report. | Bericht konnte nicht exportiert werden. | Impossible d'exporter ce rapport. | Impossibile esportare questo report. |
| You don't have access to the data behind this report. | Sie haben keinen Zugriff auf die Daten hinter diesem Bericht. | Vous n'avez pas accès aux données de ce rapport. | Non hai accesso ai dati di questo report. |
| This report is outdated — open it in Advanced to fix it. | Dieser Bericht ist veraltet — öffnen Sie ihn in Erweitert, um ihn zu korrigieren. | Ce rapport est obsolète — ouvrez-le dans Avancé pour le corriger. | Questo report è obsoleto — aprilo in Avanzato per correggerlo. |
| No data for this report | Keine Daten für diesen Bericht | Aucune donnée pour ce rapport | Nessun dato per questo report |
| The AI could not draft that report — try rephrasing. | Die KI konnte diesen Bericht nicht entwerfen — formulieren Sie um. | L'IA n'a pas pu rédiger ce rapport — reformulez. | L'IA non è riuscita a creare questo report — riformula. |
| The AI daily limit is reached — try again tomorrow. | Das tägliche KI-Limit ist erreicht — versuchen Sie es morgen erneut. | La limite quotidienne de l'IA est atteinte — réessayez demain. | Il limite giornaliero dell'IA è raggiunto — riprova domani. |
| Over time | Im Zeitverlauf | Dans le temps | Nel tempo |
| None — just the total | Keine — nur das Total | Aucune — juste le total | Nessuna — solo il totale |
| No measures are configured yet — ask an administrator to add metrics. | Es sind noch keine Messgrössen konfiguriert — bitten Sie eine Administratorin, Metriken hinzuzufügen. | Aucune mesure n'est encore configurée — demandez à un administrateur d'ajouter des métriques. | Nessuna misura è ancora configurata — chiedi a un amministratore di aggiungere le metriche. |
| This source has no date field — showing all data. | Diese Quelle hat kein Datumsfeld — alle Daten werden angezeigt. | Cette source n'a pas de champ de date — toutes les données sont affichées. | Questa fonte non ha un campo data — vengono mostrati tutti i dati. |
| per | pro | par | per |
| by | nach | par | per |
| today | heute | aujourd'hui | oggi |
| yesterday | gestern | hier | ieri |
| days ago | Tage zuvor | jours | giorni fa |
| week ago | Woche zuvor | semaine | settimana fa |
| weeks ago | Wochen zuvor | semaines | settimane fa |

(Adjust the final extracted list to what pybabel actually finds — some of the table may already exist; translate whatever is new/fuzzy.)

- [x] **Step 3: Compile + test**

```powershell
.venv\Scripts\pybabel.exe compile -d translations
.venv\Scripts\python.exe -m pytest tests/unit/test_translations.py -q
```
Expected: PASS (pot in sync, no fuzzy, all msgids translated).

- [x] **Step 4: Commit**

```bash
git add messages.pot translations/
SQL_SYNC_SKIP=1 git commit -m "chore(reporting): i18n for the Simple/Advanced restructure (de/fr/it)" -m "Extract/update/translate/compile cycle for the Simple tab strings:
tabs, library groups, wizard steps, time presets, result view actions,
and the friendly error states."
```

### Task 16: docs

**Files:**
- Modify: `CHANGELOG.md` (`[Unreleased] → Added`)
- Modify: `docs/howto/reporting.md` (new "Simple and Advanced tabs" section near the top + zero-dim note in the metrics section)
- Modify: `CLAUDE.md` (reporting blurb: one clause about the Simple/Advanced tabs + zero-dim metrics + Surface-A metrics/grain grounding)

- [x] **Step 1: CHANGELOG** under `[Unreleased] / Added`:

```markdown
- Reporting: the page is now split into a **Simple** tab (report library grouped
  into org-shared / mine / shared-with-me, a guided wizard — measure, breakdown
  incl. date grain, time range — card-based results with grand-total number card
  and chart, and an optional ask-AI helper) and an **Advanced** tab (the full
  builder, unchanged). Deep link with `/reporting?tab=advanced`; the last-used
  tab is remembered per browser.
- Reporting: definitions with metrics may now have zero columns — a global
  aggregate (grand total) with no GROUP BY, on both the docprocessing and the
  generic table provider.
- Reporting AI: "Build a report" (Surface A) now knows the canonical metrics and
  grainable date fields of each source, and its validator accepts drafts using
  `metrics` / `grain`.
```

- [x] **Step 2: docs/howto/reporting.md** — add a "Simple and Advanced tabs" section (what each tab is, who it's for, the wizard flow, the library semantics incl. "a shared report runs against the viewer's grants — numbers can differ per user", the `?tab=` deep link) and extend the metrics section with the zero-dimension grand-total behavior.

- [x] **Step 3: CLAUDE.md** — in the reporting blurb, after the semantic-layer sentence, add: the Simple/Advanced restructure (Simple = library + wizard + ask-AI cards over the existing REST endpoints; Advanced = the builder; `?tab=` deep link; `templates/_reporting_simple.html` + `templates/js/_reporting_simple_js.html` + `_reporting_tabs_js.html`), zero-dim metric definitions, and the Surface-A metrics/grain grounding.

- [x] **Step 4: Commit**

```bash
git add CHANGELOG.md docs/howto/reporting.md CLAUDE.md
SQL_SYNC_SKIP=1 git commit -m "docs(reporting): document the Simple/Advanced restructure" -m "CHANGELOG entries plus a Simple-and-Advanced-tabs section in the howto
and the CLAUDE.md reporting blurb (tabs, zero-dim totals, Surface-A
metrics/grain grounding)."
```

### Task 17: full verification + browser screenshots on INT

- [x] **Step 1: Full local gates**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q
.venv\Scripts\python.exe -m ruff check nx_lib
```
Expected: all green.

- [x] **Step 2: Browser verify on INT** — kill stale :8000 listeners, `nx -u`, dev-login `ben.streich`, then:
  - `/reporting` → Simple tab default, library renders.
  - Wizard: measure → "Over time (Import date)" → grain Month → "This year" → Show result. (docprocessing runs 500 on INT — missing Statistics tables — so expect the friendly error here; the SQL is valid per the date-dimension handoff. Verify the happy path with a `table`-provider source/metric if one is seeded, else rely on the integration tests.)
  - "None — just the total" zero-dim path.
  - Open in Advanced → builder pre-filled, tab switches.
  - `?tab=advanced` deep link + entrance animation still plays.
  - Screenshots of Simple library, wizard, result view → `var/screenshots/reporting-simple-*.png`.

- [x] **Step 3: Final handoff** — report results to the user; then (user opted into push): `python scripts/test_db_reset.py` first, then `git push` (pre-push gate runs the FULL suite incl. e2e).

## Self-review notes

- Spec §1-§8 each map to Tasks 8 / 10 / 12 / 11 / 13 / 1-5 / 6-7 / (no-op — §8 needs no code).
- Spec §7's "no validation change needed" was WRONG — Task 7 fixes `_validate_definition_for_user` (verified against `nx_lib/views/reporting.py:413`).
- Type consistency: `window.ReportingTabs.show/current`, `rp:tabshown` event, `rs*` ids, `nx.reporting.tab` localStorage key used consistently across Tasks 8-14.
- Risks table from spec §11 is honored: Advanced markup always rendered (Task 8), private Chart instance (Task 11), `id:null` handoff (Task 11), `?tab=advanced` in e2e (Task 8), rp-anim armed only for Advanced landings (Task 8).
