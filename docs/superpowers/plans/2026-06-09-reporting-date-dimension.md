# Reporting Date Dimension — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class import/export **date dimension** to the docprocessing reporting source — filter by date range, sort by date, and group by a `day/week/month/quarter/year` **grain**.

**Architecture:** Two synthetic catalog fields (`import_date`, `export_date`) are derived from `Statconfig` (CONVERT-vs-CAST aware, mirroring the dashboard). A report **column** carries an optional `grain`; the pure query builder resolves date fields to per-process SQL expressions (and truncates for the grain) in both the row and aggregate/GROUP BY paths. Filters on a date field always use the **raw** date; grain affects only projection/grouping. The SQL-injection boundary is unchanged — date expressions come only from `Statconfig`, never the client.

**Tech Stack:** Python 3 / Flask, pyodbc + SQL Server (T-SQL), pytest, Jinja2 JS partials, Flask-Babel.

**Spec:** `docs/superpowers/specs/2026-06-09-reporting-date-dimension-design.md`

---

## File structure

| File | Responsibility | Change |
|---|---|---|
| `nx_lib/reporting/catalog.py` | docprocessing field catalog | + `date_availability`, `date_catalog_entries` (pure); `fetch_docprocessing_catalog` appends date fields |
| `nx_lib/reporting/query.py` | definition → SQL (pure) | + grain/date helpers; `build_table_query` resolves date fields |
| `nx_lib/reporting/schema.py` | definition validation | + `GRAINS`, `grainable_fields` param, grain rules |
| `nx_lib/views/reporting.py` | run + AI orchestration | pass `grainable_fields` at the docprocessing run validate |
| `nx_lib/reporting/runner.py` | scheduled-report runner | pass `grainable_fields` for docprocessing |
| `templates/js/_reporting_js.html` | Advanced builder | grain `<select>` on date columns; carry `grain` in build/apply |
| `static/css/reporting.css` | builder styles | grain select styling in the Columns well |
| `translations/{de,fr,it}/…` | i18n | new labels |
| `CHANGELOG.md`, `docs/howto/reporting.md`, `CLAUDE.md` | docs | date-dimension notes |

**Conventions (match existing code):** pure builders raise `QueryBuildError` / `ReportDefinitionError`; only filter *values* are `?` params; run pytest via `.venv/Scripts/python.exe -m pytest …`; commits go through pre-commit (use `SQL_SYNC_SKIP=1 git commit …` per the INT-CRLF-drift memory). Remote session → **commit only, no push**.

---

## Task 1: Catalog — date availability + entries (pure)

**Files:**
- Modify: `nx_lib/reporting/catalog.py`
- Test: `tests/unit/test_reporting_catalog.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_reporting_catalog.py`:

```python
from nx_lib.reporting.catalog import date_availability, date_catalog_entries


class _Row:
    def __init__(self, ProcessName, ImportColumn, ExportColumn):
        self.ProcessName = ProcessName
        self.ImportColumn = ImportColumn
        self.ExportColumn = ExportColumn


def test_date_availability_filters_nulls_and_scope():
    rows = [
        _Row("compass.01_Invoice_SAP", "ImportDate", "UploadDatetime"),
        _Row("privera.03_Invoice_New", "ImportTime", None),   # no export col
        _Row("other.99_Hidden", "X", "Y"),                    # out of scope
    ]
    avail = date_availability(rows, ["compass.01_Invoice_SAP", "privera.03_Invoice_New"])
    assert avail == {
        "import_date": ["compass.01_Invoice_SAP", "privera.03_Invoice_New"],
        "export_date": ["compass.01_Invoice_SAP"],
    }


def test_date_catalog_entries_shape():
    entries = date_catalog_entries(
        {"import_date": ["b.p", "a.p"]},
        {"import_date": "Import date", "export_date": "Export date"},
    )
    assert entries == [{
        "field": "import_date", "label": "Import date", "type": "date",
        "aggregable": False, "sortable": True, "filterable": True,
        "grainable": True, "processes": ["a.p", "b.p"],
    }]
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_reporting_catalog.py -q`
Expected: FAIL — `ImportError: cannot import name 'date_availability'`.

- [ ] **Step 3: Implement the helpers**

In `nx_lib/reporting/catalog.py`, add after `_LANG_COLS`:

```python
# Synthetic date fields, derived from Statconfig (not SearchConfig.col_*).
# field_key -> the Statconfig column attribute holding its date expression.
_DATE_FIELDS = (("import_date", "ImportColumn"), ("export_date", "ExportColumn"))


def date_availability(statconfig_rows, allowed_processes):
    """{date_field: [process, ...]} for processes (in scope) whose Statconfig
    Import/Export column is non-null. Pure: rows are objects with ProcessName +
    ImportColumn/ExportColumn (or dicts with those keys)."""
    allowed = set(allowed_processes)
    out = {}
    for r in statconfig_rows:
        proc = r["ProcessName"] if isinstance(r, dict) else r.ProcessName
        if proc not in allowed:
            continue
        for field, attr in _DATE_FIELDS:
            val = r[attr] if isinstance(r, dict) else getattr(r, attr)
            if val:
                out.setdefault(field, []).append(proc)
    return out


def date_catalog_entries(date_avail, labels):
    """Catalog entries for the synthetic date fields. `labels` maps field_key ->
    localized label. Sorted by label; processes sorted for stable output."""
    entries = []
    for field, _attr in _DATE_FIELDS:
        procs = date_avail.get(field)
        if not procs:
            continue
        entries.append({
            "field": field,
            "label": labels.get(field, field),
            "type": "date",
            "aggregable": False,
            "sortable": True,
            "filterable": True,
            "grainable": True,
            "processes": sorted(procs),
        })
    entries.sort(key=lambda e: e["label"])
    return entries
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_reporting_catalog.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/catalog.py tests/unit/test_reporting_catalog.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): pure date-field catalog helpers"
```

---

## Task 2: Catalog — wire date fields into `fetch_docprocessing_catalog`

**Files:**
- Modify: `nx_lib/reporting/catalog.py` (`fetch_docprocessing_catalog`)

DB glue (no pure unit test); verified by the route/browser steps in Task 10.

- [ ] **Step 1: Add the Statconfig query + append date entries**

In `fetch_docprocessing_catalog`, add the babel import at the top of the file:

```python
from flask_babel import gettext as _
```

Then, inside `fetch_docprocessing_catalog`, replace the final `return build_catalog(...)` (the one after `availability["processname"] = ...`) with:

```python
        catalog = build_catalog(
            meta_rows, label_rows, availability, lang_col=lang_col_for(locale_str)
        )

        # Synthetic date dimension from Statconfig (different table from SearchConfig).
        try:
            cur.execute("SELECT ProcessName, ImportColumn, ExportColumn FROM Statconfig")
            statconfig_rows = cur.fetchall()
        except Exception:
            current_app.logger.warning("reporting catalog: Statconfig unavailable")
            statconfig_rows = []
        date_avail = date_availability(statconfig_rows, allowed_processes)
        catalog += date_catalog_entries(
            date_avail, {"import_date": _("Import date"), "export_date": _("Export date")}
        )
        catalog.sort(key=lambda e: e["label"])
        return catalog
```

(The early `return build_catalog(..., {}, ...)` for the no-`col_*` case stays as-is — that environment has no SearchConfig and we keep its behaviour unchanged.)

- [ ] **Step 2: Sanity check import + syntax**

Run: `.venv/Scripts/python.exe -c "import nx_lib.reporting.catalog"`
Expected: no error.

- [ ] **Step 3: Commit**

```bash
git add nx_lib/reporting/catalog.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): expose import/export date fields in the docprocessing catalog"
```

---

## Task 3: Query builder — grain + date-expression helpers (pure)

**Files:**
- Modify: `nx_lib/reporting/query.py`
- Test: `tests/unit/test_reporting_query.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_reporting_query.py`:

```python
from nx_lib.reporting.query import _date_base, _grain_sql, _date_exprs_for


def test_date_base_cast_vs_convert_passthrough():
    assert _date_base("ImportDate") == "CAST(ImportDate AS date)"
    # A Statconfig value already containing CONVERT is used as-is.
    expr = "CONVERT(date, SomeStr, 104)"
    assert _date_base(expr) == expr


def test_grain_sql_each_grain():
    d = "CAST(ImportDate AS date)"
    assert _grain_sql(d, None) == d
    assert _grain_sql(d, "day") == d
    assert _grain_sql(d, "week") == f"DATEADD(week, DATEDIFF(week, 0, {d}), 0)"
    assert _grain_sql(d, "month") == f"DATEFROMPARTS(YEAR({d}), MONTH({d}), 1)"
    assert _grain_sql(d, "quarter") == f"DATEFROMPARTS(YEAR({d}), (DATEPART(quarter, {d}) - 1) * 3 + 1, 1)"
    assert _grain_sql(d, "year") == f"DATEFROMPARTS(YEAR({d}), 1, 1)"


def test_grain_sql_rejects_unknown():
    import pytest
    with pytest.raises(QueryBuildError):
        _grain_sql("x", "fortnight")


def test_date_exprs_for_uses_cfg_columns_and_grain():
    cfg = {"process": "acme.inv", "import_col": "ImportDate", "export_col": "ExpD"}
    out = _date_exprs_for(cfg, {"import_date": "month"})
    assert out["import_date"] == "DATEFROMPARTS(YEAR(CAST(ImportDate AS date)), MONTH(CAST(ImportDate AS date)), 1)"
    assert out["export_date"] == "CAST(ExpD AS date)"     # no grain -> raw
    # A cfg missing a column omits that date field entirely.
    assert _date_exprs_for({"process": "p", "import_col": None, "export_col": "E"}, {}) == {"export_date": "CAST(E AS date)"}
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_reporting_query.py -q -k "date or grain"`
Expected: FAIL — `cannot import name '_date_base'`.

- [ ] **Step 3: Implement the helpers**

In `nx_lib/reporting/query.py`, add after the `_SPECIAL_OPS` constant:

```python
_DATE_GRAINS = {"day", "week", "month", "quarter", "year"}

# Synthetic date field -> the process-config key holding its raw column expression.
_DATE_FIELD_COL = {"import_date": "import_col", "export_date": "export_col"}


def _date_base(col_expr):
    """Normalize a Statconfig date column to a DATE-typed expression, mirroring
    the dashboard: a value already containing CONVERT(...) is trusted as-is;
    otherwise wrap with CAST(... AS date). The expression originates only from
    Statconfig (server config), never the client."""
    return col_expr if "convert" in col_expr.lower() else f"CAST({col_expr} AS date)"


def _grain_sql(d, grain):
    """Wrap a DATE expression `d` for the requested grain. None/'day' = raw.
    Month/quarter/year via DATEFROMPARTS; week is Monday-anchored and
    DATEFIRST-independent."""
    if grain in (None, "day"):
        return d
    if grain == "week":
        return f"DATEADD(week, DATEDIFF(week, 0, {d}), 0)"
    if grain == "month":
        return f"DATEFROMPARTS(YEAR({d}), MONTH({d}), 1)"
    if grain == "quarter":
        return f"DATEFROMPARTS(YEAR({d}), (DATEPART(quarter, {d}) - 1) * 3 + 1, 1)"
    if grain == "year":
        return f"DATEFROMPARTS(YEAR({d}), 1, 1)"
    raise QueryBuildError(f"unsupported date grain: {grain!r}")


def _date_exprs_for(cfg, grain_by_field):
    """{date_field: sql_expr} for the date fields this process exposes, applying
    each field's grain (grain_by_field maps field -> grain; missing = raw)."""
    out = {}
    for field, cfg_key in _DATE_FIELD_COL.items():
        col = cfg.get(cfg_key)
        if col:
            out[field] = _grain_sql(_date_base(col), grain_by_field.get(field))
    return out
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_reporting_query.py -q -k "date or grain"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/query.py tests/unit/test_reporting_query.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): date-expression + grain SQL helpers"
```

---

## Task 4: Query builder — resolve date fields in `build_table_query`

**Files:**
- Modify: `nx_lib/reporting/query.py` (`build_table_query`)
- Test: `tests/unit/test_reporting_query.py`

The existing module fixtures (`PROCESS_CONFIGS`, `FIELD_COL_MAPS`, `_rd`) already carry `export_col`/`import_col` (`acme.inv`: `ExportDate`/`ImportDate`; `acme.hr`: `ExpD`/`ImpD`).

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_reporting_query.py`:

```python
def test_projects_raw_import_date():
    rd = _rd(columns=[{"field": "import_date", "header": "Imported", "agg": None}], sort=[])
    sql, _ = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "CAST(ImportDate AS date) AS [import_date]" in sql   # acme.inv
    assert "CAST(ImpD AS date) AS [import_date]" in sql         # acme.hr


def test_projects_month_grain_import_date():
    rd = _rd(columns=[{"field": "import_date", "header": "Month", "agg": None, "grain": "month"}], sort=[])
    sql, _ = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "DATEFROMPARTS(YEAR(CAST(ImportDate AS date)), MONTH(CAST(ImportDate AS date)), 1) AS [import_date]" in sql


def test_date_filter_uses_raw_even_when_column_grained():
    # import_date column is month-grained, but a filter on it compares the RAW date.
    rd = _rd(
        columns=[{"field": "import_date", "header": "Month", "agg": None, "grain": "month"}],
        filters=[{"field": "import_date", "op": "gte", "value": "2026-01-01"}],
        sort=[],
    )
    sql, params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "CAST(ImportDate AS date) >= ?" in sql               # raw in WHERE
    assert "DATEFROMPARTS(YEAR(CAST(ImportDate AS date))" in sql # month in SELECT
    assert "2026-01-01" in params


def test_unknown_date_like_field_still_rejected():
    import pytest
    rd = _rd(columns=[{"field": "nope_date", "header": "x", "agg": None}], sort=[])
    with pytest.raises(QueryBuildError):
        build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)


def test_aggregate_groups_by_month_grain_dim():
    rd = _rd(
        columns=[{"field": "import_date", "header": "Month", "agg": None, "grain": "month"}],
        sort=[],
    )
    resolved = [{"code": "doc_count", "aggregation": "count", "base_field": None}]
    sql, _ = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100, resolved_metrics=resolved)
    assert "COUNT(*) AS [doc_count]" in sql
    assert "GROUP BY [import_date]" in sql
    assert "DATEFROMPARTS(YEAR(CAST(ImportDate AS date)), MONTH(CAST(ImportDate AS date)), 1) AS [import_date]" in sql
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_reporting_query.py -q -k "import_date or month_grain or aggregate_groups"`
Expected: FAIL — date fields not resolved (`unknown column field: 'import_date'`).

- [ ] **Step 3: Modify `build_table_query`**

In `build_table_query`, immediately after `cap = min(...)` add:

```python
    # Per-column grain (date fields only); raw date otherwise.
    grain_by_field = {c["field"]: c.get("grain") for c in rd["columns"]}
```

Replace the `all_known_fields` block (currently builds from `field_col_maps` only) with:

```python
    all_known_fields = {"processname"}
    for colmap in field_col_maps.values():
        all_known_fields.update(colmap.keys())
    for cfg in process_configs:
        all_known_fields.update(_date_exprs_for(cfg, grain_by_field).keys())
    for field in columns:
        if field not in all_known_fields:
            raise QueryBuildError(f"unknown column field: {field!r}")
```

Then in the per-`cfg` loop, replace the body up to `select_exprs = []` with:

```python
    for cfg in process_configs:
        colmap = field_col_maps.get(cfg["process"], {})
        # Projection uses the column grain; filters always use the RAW date.
        proj_resolved = {**colmap, **_date_exprs_for(cfg, grain_by_field)}
        filt_resolved = {**colmap, **_date_exprs_for(cfg, {})}

        # A filter referencing a field this process doesn't expose can never
        # match here — drop the whole subquery for correctness.
        if any(f["field"] not in filt_resolved for f in col_filters):
            continue

        select_exprs = []
        for field in projected_fields:
            if field == "processname":
                select_exprs.append("? AS [processname]")
                params.append(cfg["process"])
            else:
                actual = proj_resolved.get(field)
                if actual:
                    select_exprs.append(f"{actual} AS [{field}]")
                else:
                    select_exprs.append(f"NULL AS [{field}]")

        where = ["1 = 1"]
        for f in col_filters:
            col = filt_resolved.get(f["field"])
            if not col:
                continue
            where.append(_filter_clause(col, f["op"], f.get("value"), params))
        cond = f" {cfg['condition']}" if cfg.get("condition") else ""
        sub_queries.append(
            f"SELECT {', '.join(select_exprs)} FROM [{cfg['table']}] "
            f"WHERE {' AND '.join(where)}{cond}"
        )
```

(The lines after this — `if not sub_queries`, the `inner` join, the aggregate/row output — are unchanged.)

- [ ] **Step 4: Run, verify pass (and no regressions)**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_reporting_query.py -q`
Expected: PASS (new + all existing query tests).

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/query.py tests/unit/test_reporting_query.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): resolve import/export date fields + grain in the query builder"
```

---

## Task 5: Schema — validate `grain`

**Files:**
- Modify: `nx_lib/reporting/schema.py`
- Test: `tests/unit/test_reporting_schema.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_reporting_schema.py` (reuse the module's existing `_def`/builder helper if present; otherwise build a minimal valid dict inline):

```python
import pytest
from nx_lib.reporting.schema import validate_report_definition, ReportDefinitionError

_CATALOG = {"doctype", "import_date"}
_GRAINABLE = {"import_date"}


def _base(**over):
    d = {
        "schemaVersion": 1, "visualization": "table", "source": "docprocessing",
        "title": "t", "subtitle": None,
        "columns": [{"field": "doctype", "header": "Type", "agg": None}],
        "filters": [], "sort": [], "scope": {"clients": [], "processes": []},
        "rowLimit": 100,
    }
    d.update(over)
    return d


def _validate(d):
    validate_report_definition(
        d, _CATALOG, _CATALOG, _CATALOG, max_row_limit=5000, grainable_fields=_GRAINABLE
    )


def test_valid_grain_accepted():
    _validate(_base(columns=[{"field": "import_date", "header": "Month", "agg": None, "grain": "month"}]))


def test_grain_on_non_grainable_field_rejected():
    with pytest.raises(ReportDefinitionError):
        _validate(_base(columns=[{"field": "doctype", "header": "T", "agg": None, "grain": "month"}]))


def test_unknown_grain_rejected():
    with pytest.raises(ReportDefinitionError):
        _validate(_base(columns=[{"field": "import_date", "header": "M", "agg": None, "grain": "fortnight"}]))


def test_absent_grain_accepted():
    _validate(_base(columns=[{"field": "import_date", "header": "Raw", "agg": None}]))
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_reporting_schema.py -q -k grain`
Expected: FAIL — `grainable_fields` is not a parameter / grain not validated.

- [ ] **Step 3: Implement**

In `nx_lib/reporting/schema.py`, after `SORT_DIRS = {"asc", "desc"}` add:

```python
GRAINS = {"day", "week", "month", "quarter", "year"}
```

Change the signature of `validate_report_definition` to add a keyword-only param:

```python
def validate_report_definition(
    rd,
    catalog_fields,
    filterable_fields,
    sortable_fields,
    *,
    max_row_limit,
    metric_codes=frozenset(),
    grainable_fields=frozenset(),
):
```

In the `for c in columns:` loop, after the `header` check, add:

```python
        grain = c.get("grain")
        if grain is not None:
            if c.get("field") not in grainable_fields:
                raise ReportDefinitionError(f"field not grainable: {c.get('field')!r}")
            if grain not in GRAINS:
                raise ReportDefinitionError(f"unknown grain: {grain!r}")
```

- [ ] **Step 4: Run, verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_reporting_schema.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/schema.py tests/unit/test_reporting_schema.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): validate the date-column grain modifier"
```

---

## Task 6: Wire `grainable_fields` into the run + scheduled-runner validate calls

**Files:**
- Modify: `nx_lib/views/reporting.py` (`_prepare_run`, docprocessing branch ~line 708-717)
- Modify: `nx_lib/reporting/runner.py` (docprocessing branch ~line 77-83)

No new unit test (covered by existing route tests + Task 10). The other validate sites (table provider, AI Surface A/C at reporting.py:413) keep the default empty `grainable_fields` — table sources have no date fields, and the AI does not emit `grain` in v1, so grain is correctly rejected there.

- [ ] **Step 1: reporting.py — derive + pass grainable**

In `_prepare_run`, docprocessing branch, replace:

```python
        catalog, catalog_fields, filterable, sortable = _catalog_for_source(source)
        source_metrics = _metrics_for_source(source["id"])
        validate_report_definition(
            rd,
            catalog_fields,
            filterable,
            sortable,
            max_row_limit=MAX_ROW_LIMIT,
            metric_codes=set(source_metrics),
        )
```

with:

```python
        catalog, catalog_fields, filterable, sortable = _catalog_for_source(source)
        grainable = {f["field"] for f in catalog if f.get("grainable")}
        source_metrics = _metrics_for_source(source["id"])
        validate_report_definition(
            rd,
            catalog_fields,
            filterable,
            sortable,
            max_row_limit=MAX_ROW_LIMIT,
            metric_codes=set(source_metrics),
            grainable_fields=grainable,
        )
```

- [ ] **Step 2: runner.py — derive + pass grainable**

In `nx_lib/reporting/runner.py`, docprocessing branch, replace:

```python
        sortable = {f["field"] for f in catalog if f["sortable"]}
        validate_report_definition(
            definition, catalog_fields, filterable, sortable, max_row_limit=MAX_ROW_LIMIT
        )
```

with:

```python
        sortable = {f["field"] for f in catalog if f["sortable"]}
        grainable = {f["field"] for f in catalog if f.get("grainable")}
        validate_report_definition(
            definition, catalog_fields, filterable, sortable,
            max_row_limit=MAX_ROW_LIMIT, grainable_fields=grainable,
        )
```

- [ ] **Step 3: Run the reporting route + runner tests**

Run: `.venv/Scripts/python.exe -m pytest tests/integration/test_reporting_routes.py tests/unit/test_reporting_schedule.py -q`
Expected: PASS (no regressions).

- [ ] **Step 4: Commit**

```bash
git add nx_lib/views/reporting.py nx_lib/reporting/runner.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): pass grainable date fields to the run + scheduler validators"
```

---

## Task 7: Advanced builder UI — grain `<select>` on date columns

**Files:**
- Modify: `templates/js/_reporting_js.html` (`renderFields` add-column, `renderWells`, `buildDefinition`, `applyDefinition`)
- Modify: `static/css/reporting.css`

No JS unit-test harness in the repo — verified in the browser in Task 10. Restart the dev server before testing (Jinja caches the partial).

- [ ] **Step 1: Default a grainable column to month when added**

In `renderFields`, the field-click handler currently does:

```js
        if (!state.columns.find(function (c) { return c.field === f.field; })) {
          state.columns.push(Object.assign({}, f, { header: f.label }));
          renderWells();
        }
```

Replace the `push` line with:

```js
          state.columns.push(Object.assign({}, f, {
            header: f.label,
            grain: f.grainable ? 'month' : undefined,
          }));
```

- [ ] **Step 2: Render the grain select in `renderWells`**

In `renderWells`, inside `state.columns.forEach`, after `inp.oninput = ...` and before `var rm = ...`, insert:

```js
      var grainSel = null;
      if (c.grainable) {
        grainSel = document.createElement('select');
        grainSel.className = 'reporting-grain';
        [['day', '{{ _("Day") }}'], ['week', '{{ _("Week") }}'], ['month', '{{ _("Month") }}'],
         ['quarter', '{{ _("Quarter") }}'], ['year', '{{ _("Year") }}']].forEach(function (g) {
          var opt = document.createElement('option');
          opt.value = g[0]; opt.textContent = g[1];
          grainSel.appendChild(opt);
        });
        grainSel.value = c.grain || 'month';
        grainSel.onchange = function (e) { c.grain = e.target.value; };
      }
```

and change the append block from:

```js
      li.appendChild(inp);
      li.appendChild(rm);
```

to:

```js
      li.appendChild(inp);
      if (grainSel) li.appendChild(grainSel);
      li.appendChild(rm);
```

- [ ] **Step 3: Carry `grain` in `buildDefinition`**

In `buildDefinition`, the `columns` map currently returns `{ field, header, agg: null }`. Replace with:

```js
      columns: state.columns.map(function (c) {
        var col = { field: c.field, header: c.header || c.label, agg: null };
        if (c.grain) col.grain = c.grain;
        return col;
      }),
```

- [ ] **Step 4: Restore `grain` in `applyDefinition`**

In `applyDefinition`, the column re-hydration currently maps each `def.columns` entry to `Object.assign({}, meta, { header: ... })`. Replace that map body with:

```js
    state.columns = (def.columns || []).map(function (c) {
      var meta = state.fields.find(function (f) { return f.field === c.field; })
        || { field: c.field, label: c.field };
      var col = Object.assign({}, meta, { header: c.header || meta.label });
      if (c.grain) col.grain = c.grain;
      return col;
    });
```

- [ ] **Step 5: Style the grain select**

In `static/css/reporting.css`, after the `.reporting-scope-proc` block (or near the other well-input rules), add:

```css
.reporting-grain {
  font-size: 12px;
  padding: 2px 4px;
  border: 1px solid var(--nx-border);
  border-radius: var(--nx-radius-sm);
  background: var(--nx-card);
  color: var(--nx-text);
}
```

- [ ] **Step 6: Commit**

```bash
git add templates/js/_reporting_js.html static/css/reporting.css
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): grain selector on date columns in the Advanced builder"
```

---

## Task 8: i18n — labels for the date fields + grains

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po(.mo)`

New msgids: `Import date`, `Export date`, `Day`, `Week`, `Month`, `Quarter`, `Year`. (Some may already exist — extract will dedupe.)

- [ ] **Step 1: Extract + update**

```bash
.venv/Scripts/pybabel.exe extract -F babel.cfg -o messages.pot .
.venv/Scripts/pybabel.exe update -i messages.pot -d translations
```

- [ ] **Step 2: Translate the new (and any fuzzy) msgids** in each `translations/<lang>/LC_MESSAGES/messages.po`, removing `#, fuzzy` flags:

| msgid | de | fr | it |
|---|---|---|---|
| Import date | Importdatum | Date d'import | Data di importazione |
| Export date | Exportdatum | Date d'export | Data di esportazione |
| Day | Tag | Jour | Giorno |
| Week | Woche | Semaine | Settimana |
| Month | Monat | Mois | Mese |
| Quarter | Quartal | Trimestre | Trimestre |
| Year | Jahr | Année | Anno |

- [ ] **Step 3: Compile + verify**

```bash
.venv/Scripts/pybabel.exe compile -d translations
.venv/Scripts/python.exe -m pytest tests/unit/test_translations.py -q
```
Expected: PASS (pot in sync; all msgids translated non-fuzzy in de/fr/it).

- [ ] **Step 4: Commit**

```bash
git add messages.pot translations
SQL_SYNC_SKIP=1 git commit -m "i18n(reporting): date dimension + grain labels (de/fr/it)"
```

---

## Task 9: Docs + changelog

**Files:**
- Modify: `CHANGELOG.md` (`[Unreleased]` → Added)
- Modify: `docs/howto/reporting.md` (new "Date dimension" subsection)
- Modify: `CLAUDE.md` (reporting blurb)

- [ ] **Step 1: CHANGELOG** — add under `### Added`:

```markdown
- **Reporting date dimension (docprocessing).** Import & export dates are now
  first-class report fields (`import_date` / `export_date`), synthesized from
  `Statconfig` (CONVERT-vs-CAST aware, mirroring the dashboard). Date columns
  take an optional **grain** (`day/week/month/quarter/year`, default month) that
  the query builder resolves in both the row and aggregate/GROUP BY paths;
  filters on a date field always use the raw date. Enables date-range filtering
  and "documents per day/week/month" reporting. Security boundary unchanged
  (date expressions come only from `Statconfig`). de/fr/it translated.
```

- [ ] **Step 2: `docs/howto/reporting.md`** — add a subsection after the process-scope section:

```markdown
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
```

- [ ] **Step 3: `CLAUDE.md`** — in the reporting paragraph, append to the docprocessing/source description a clause:

```
docprocessing also exposes synthetic date fields `import_date`/`export_date` (from `Statconfig`, CONVERT/CAST-normalized) with an optional per-column `grain` (day/week/month/quarter/year) resolved in `query.py` for both the row and aggregate paths; date filters always use the raw date.
```

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md docs/howto/reporting.md CLAUDE.md
SQL_SYNC_SKIP=1 git commit -m "docs(reporting): document the date dimension + grain"
```

---

## Task 10: Browser verification on INT (+ screenshots)

**Files:** none (verification).

- [ ] **Step 1: Restart the dev server** (clears the Jinja partial cache):

```bash
# kill any listener on 8000, then:
ENVIRONMENT=INT FLASK_RUN_PORT=8000 .venv/Scripts/python.exe nx_main.py   # background
```

- [ ] **Step 2: Drive Playwright** — dev-login `ben.streich`, open `/reporting`, switch source to Document Processing. Verify:
  - `Import date` / `Export date` appear in the field list (type date).
  - Adding `Import date` as a column shows a grain `<select>` defaulting to **Month**.
  - Add a metric `doc_count`, keep `Import date` (month) as the dimension, Run → grouped-by-month rows (scope to a process whose Statistics table exists, e.g. compass, to avoid the known missing-table 500s).
  - Add a filter on `Import date` `>=` a date → flatpickr mounts; the run payload's WHERE uses the raw date (intercept `/api/reporting/run` body / inspect generated rows).

- [ ] **Step 3: Capture** `var/screenshots/reporting-date-dimension.png` and send via SendUserFile (remote session).

- [ ] **Step 4: Stop the dev server.**

---

## Final verification

- [ ] `.venv/Scripts/python.exe -m pytest tests/unit -q` → all green.
- [ ] `.venv/Scripts/python.exe -m ruff check nx_lib/` → clean.
- [ ] Confirm `git status` shows only intended changes; branch is **committed, not pushed** (remote rule).

## Notes / out of scope

- The scheduled-report runner (`runner.py:84-86`) scopes by `scope.processes` only and ignores `scope.clients` — a pre-existing gap from the process-picker work, **not** addressed here. Flag for a separate fix.
- Teaching the AI surfaces to *emit* `grain` is deferred (date fields already appear in AI grounding as `type:date`).
- A single report uses one grain per date field (alias `[import_date]`); two grains of the same date in one report is unsupported by design.
