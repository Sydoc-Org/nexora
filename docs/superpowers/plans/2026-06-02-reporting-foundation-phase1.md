# Reporting Foundation — Phase 1 (Curated Table Engine) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working internal `/reporting` page — a PowerBI-style table report builder over the curated **Document Processing** source, with filters, combine-clients/processes, custom headers, save/load, and Excel export — behind new `reporting.*` permissions.

**Architecture:** A new pure-Python engine package `nx_lib/reporting/` (schema validation, field catalog, source registry, parameterized table-query builder, xlsx exporter) is driven by a thin Flask view module `nx_lib/views/reporting.py`. The curated source reuses the existing `FieldMetadata` / `SearchConfig` / `Search_Field_Labels` / `Statconfig` tables and queries `engine_statistics_db`; saved reports live in a new `Reports` table in NexoraDB. The engine's core functions are dependency-injected (configs/column-maps passed in) so they unit-test with no database.

**Tech Stack:** Python 3.13, Flask, SQLAlchemy + pyodbc, Jinja2, vanilla JS + Tailwind/Chart.js/flatpickr (CDN), openpyxl (new), pytest, SQL Server migrations via `sql/_migrations/NexoraDB/`.

**Spec:** `docs/superpowers/specs/2026-06-02-reporting-foundation-design.md`. Phase 2 (live read-only SQL sandbox) is a separate plan.

**Scope note (Phase 1 only):** The live-SQL source, the `engine_*_ro` read-only engines, and `reporting.sql.run` are **out of scope here** — they are Phase 2. The Layout-A UI renders a `Table | SQL` toggle but the SQL tab is disabled with a "coming soon" state in Phase 1.

---

## File Structure

**Create:**
- `nx_lib/reporting/__init__.py` — package exports.
- `nx_lib/reporting/schema.py` — report-definition (v1) validation. Pure.
- `nx_lib/reporting/catalog.py` — field-catalog row→dict mapping (pure) + DB fetch for docprocessing.
- `nx_lib/reporting/sources.py` — built-in source registry + per-user access filtering. Pure.
- `nx_lib/reporting/query.py` — parameterized table-query builder. Pure.
- `nx_lib/reporting/export.py` — rows → `.xlsx` bytes (openpyxl).
- `nx_lib/views/reporting.py` — routes.
- `templates/reporting.html` — page (Layout A).
- `templates/js/_reporting_js.html` — page JS partial.
- `static/css/reporting.css` — page styles.
- `sql/_migrations/NexoraDB/0004_create_reports_table.sql`
- `sql/_migrations/NexoraDB/0005_seed_reporting_permissions.sql`
- `docs/howto/reporting.md`
- `tests/unit/test_reporting_schema.py`
- `tests/unit/test_reporting_catalog.py`
- `tests/unit/test_reporting_sources.py`
- `tests/unit/test_reporting_query.py`
- `tests/unit/test_reporting_export.py`
- `tests/integration/test_reporting_routes.py`
- `tests/e2e/test_reporting.py`

**Modify:**
- `pyproject.toml` — add `openpyxl` dependency; regenerate `requirements.txt`.
- `nx_lib/__init__.py:66-75` — register reporting routes.
- `nx_lib/security.py:111-150` — `startpage_redirect_to` + `page_visibility` gain reporting entries.
- `templates/_header.html:77-92` — add Reporting nav item.
- `CHANGELOG.md` — `[Unreleased]` entries.
- `CLAUDE.md` — new module / perms / dependency.

---

## Task 1: Reporting package + report-definition schema validation

**Files:**
- Create: `nx_lib/reporting/__init__.py`
- Create: `nx_lib/reporting/schema.py`
- Test: `tests/unit/test_reporting_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_reporting_schema.py
"""Unit tests for nx_lib.reporting.schema — report-definition (v1) validation."""

import pytest

from nx_lib.reporting.schema import (
    REPORT_SCHEMA_VERSION,
    ReportDefinitionError,
    validate_report_definition,
)

CATALOG_FIELDS = {"date", "client", "doctype", "status", "pages"}
FILTERABLE = {"date", "client", "doctype", "status", "pages"}
SORTABLE = {"date", "doctype", "pages"}


def _valid_def():
    return {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "source": "docprocessing",
        "visualization": "table",
        "title": "My report",
        "subtitle": None,
        "columns": [
            {"field": "date", "header": "Date", "agg": None},
            {"field": "doctype", "header": "Type", "agg": None},
        ],
        "groupBy": [],
        "filters": [{"field": "status", "op": "eq", "value": "Done"}],
        "sort": [{"field": "date", "dir": "desc"}],
        "scope": {"clients": ["acme"], "processes": ["acme.invoices"]},
        "rowLimit": 5000,
        "sql": None,
        "sqlTarget": None,
    }


def test_valid_definition_passes():
    validate_report_definition(
        _valid_def(), CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000
    )


def test_wrong_schema_version_rejected():
    d = _valid_def()
    d["schemaVersion"] = 99
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_unknown_column_field_rejected():
    d = _valid_def()
    d["columns"].append({"field": "evil; DROP TABLE", "header": "x", "agg": None})
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_table_requires_at_least_one_column():
    d = _valid_def()
    d["columns"] = []
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_unknown_filter_op_rejected():
    d = _valid_def()
    d["filters"] = [{"field": "status", "op": "regex", "value": "x"}]
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_filter_on_non_filterable_field_rejected():
    d = _valid_def()
    d["filters"] = [{"field": "client", "op": "eq", "value": "x"}]
    # client is filterable here, so flip it: make a field filterable-excluded
    d["filters"] = [{"field": "date", "op": "eq", "value": "x"}]
    non_filterable = CATALOG_FIELDS  # all filterable in fixture
    # craft a catalog where 'date' is not filterable
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(
            d, CATALOG_FIELDS, FILTERABLE - {"date"}, SORTABLE, max_row_limit=50000
        )


def test_sort_on_non_sortable_field_rejected():
    d = _valid_def()
    d["sort"] = [{"field": "client", "dir": "asc"}]  # client not in SORTABLE
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_row_limit_capped_and_typed():
    d = _valid_def()
    d["rowLimit"] = 9_999_999
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_is_null_op_allows_missing_value():
    d = _valid_def()
    d["filters"] = [{"field": "status", "op": "is_null"}]
    validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_reporting_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nx_lib.reporting'`.

- [ ] **Step 3: Write minimal implementation**

```python
# nx_lib/reporting/__init__.py
"""Self-service reporting engine (curated table sources).

Pure-Python building blocks (schema, catalog mapping, source registry, query
builder, exporter) live here so they unit-test without a database. The Flask
view layer in nx_lib/views/reporting.py wires them to real engines.
"""
```

```python
# nx_lib/reporting/schema.py
"""Validation for the v1 report-definition JSON shape.

A report definition is the saved/sent description of a report:
source, visualization, columns (+ custom headers), filters, sort, scope,
and a row limit. Validation is whitelist-based: every field/op/dir must
already exist in the source's catalog, so nothing user-supplied can reach
SQL unchecked.
"""

REPORT_SCHEMA_VERSION = 1

SUPPORTED_VISUALIZATIONS = {"table"}

# op -> whether it requires a `value` key
FILTER_OPS = {
    "eq": True,
    "ne": True,
    "in": True,
    "not_in": True,
    "gt": True,
    "gte": True,
    "lt": True,
    "lte": True,
    "between": True,
    "contains": True,
    "starts_with": True,
    "is_null": False,
    "is_not_null": False,
}

SORT_DIRS = {"asc", "desc"}


class ReportDefinitionError(ValueError):
    """Raised when a report definition does not match the v1 schema."""


def validate_report_definition(
    rd, catalog_fields, filterable_fields, sortable_fields, *, max_row_limit
):
    """Validate `rd` (a dict) against the v1 schema. Raises ReportDefinitionError.

    `catalog_fields`, `filterable_fields`, `sortable_fields` are sets of the
    field keys the chosen source exposes. `max_row_limit` is the server cap.
    """
    if not isinstance(rd, dict):
        raise ReportDefinitionError("definition must be an object")
    if rd.get("schemaVersion") != REPORT_SCHEMA_VERSION:
        raise ReportDefinitionError(f"schemaVersion must be {REPORT_SCHEMA_VERSION}")
    if rd.get("visualization") not in SUPPORTED_VISUALIZATIONS:
        raise ReportDefinitionError("visualization must be 'table'")
    if not isinstance(rd.get("source"), str) or not rd["source"]:
        raise ReportDefinitionError("source is required")

    title = rd.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ReportDefinitionError("title is required")
    subtitle = rd.get("subtitle")
    if subtitle is not None and not isinstance(subtitle, str):
        raise ReportDefinitionError("subtitle must be a string or null")

    columns = rd.get("columns")
    if not isinstance(columns, list) or not columns:
        raise ReportDefinitionError("at least one column is required")
    for c in columns:
        if not isinstance(c, dict) or c.get("field") not in catalog_fields:
            raise ReportDefinitionError(f"unknown column field: {c.get('field')!r}")
        header = c.get("header")
        if header is not None and not isinstance(header, str):
            raise ReportDefinitionError("column header must be a string or null")

    for f in rd.get("filters") or []:
        if not isinstance(f, dict):
            raise ReportDefinitionError("filter must be an object")
        if f.get("field") not in filterable_fields:
            raise ReportDefinitionError(f"field not filterable: {f.get('field')!r}")
        op = f.get("op")
        if op not in FILTER_OPS:
            raise ReportDefinitionError(f"unknown filter op: {op!r}")
        if FILTER_OPS[op] and "value" not in f:
            raise ReportDefinitionError(f"filter op {op!r} requires a value")

    for s in rd.get("sort") or []:
        if not isinstance(s, dict) or s.get("field") not in sortable_fields:
            raise ReportDefinitionError(f"field not sortable: {s.get('field')!r}")
        if s.get("dir") not in SORT_DIRS:
            raise ReportDefinitionError("sort dir must be 'asc' or 'desc'")

    scope = rd.get("scope") or {}
    if not isinstance(scope, dict):
        raise ReportDefinitionError("scope must be an object")
    for key in ("clients", "processes"):
        val = scope.get(key, [])
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            raise ReportDefinitionError(f"scope.{key} must be a list of strings")

    row_limit = rd.get("rowLimit")
    if not isinstance(row_limit, int) or row_limit < 1 or row_limit > max_row_limit:
        raise ReportDefinitionError(f"rowLimit must be an int in [1, {max_row_limit}]")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_reporting_schema.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Lint + commit**

```bash
ruff check nx_lib/reporting tests/unit/test_reporting_schema.py
ruff format nx_lib/reporting tests/unit/test_reporting_schema.py
git add nx_lib/reporting/__init__.py nx_lib/reporting/schema.py tests/unit/test_reporting_schema.py
git commit -m "feat(reporting): add report-definition v1 schema validation"
```
> Note: committing runs the `sql-migrate-int` pre-commit hook (auto-applies pending INT migrations). Ensure that is acceptable, or set `SQL_SYNC_SKIP=1` only if explicitly cleared by the owner. Never use `--no-verify`.

---

## Task 2: Field catalog mapping (docprocessing)

**Files:**
- Create: `nx_lib/reporting/catalog.py`
- Test: `tests/unit/test_reporting_catalog.py`

The DB query mirrors `dashboard.py::dashboard_field_metadata` (FieldMetadata + Search_Field_Labels + SearchConfig availability), but the row→catalog mapping is extracted as a **pure** function so it unit-tests without a DB.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_reporting_catalog.py
"""Unit tests for nx_lib.reporting.catalog — pure row→catalog mapping."""

from nx_lib.reporting.catalog import build_catalog


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_build_catalog_merges_meta_labels_and_availability():
    meta_rows = [
        _Row(FieldKey="doctype", DataType="string", Aggregable=0, Sortable=1),
        _Row(FieldKey="pages", DataType="number", Aggregable=1, Sortable=1),
    ]
    label_rows = [
        _Row(FieldKey="doctype", EnglishLabel="Doc type", GermanLabel="Belegart",
             FrenchLabel=None, ItalianLabel=None),
    ]
    availability = {"doctype": ["acme.invoices"], "pages": ["acme.invoices"]}

    cat = build_catalog(meta_rows, label_rows, availability, lang_col="GermanLabel")
    by_key = {f["field"]: f for f in cat}

    assert by_key["doctype"]["label"] == "Belegart"
    assert by_key["doctype"]["type"] == "string"
    assert by_key["doctype"]["sortable"] is True
    assert by_key["doctype"]["aggregable"] is False
    assert by_key["doctype"]["filterable"] is True
    assert by_key["pages"]["label"] == "Pages"  # no label row → titleized key
    assert by_key["pages"]["processes"] == ["acme.invoices"]


def test_build_catalog_excludes_fields_without_availability():
    meta_rows = [_Row(FieldKey="ghost", DataType="string", Aggregable=0, Sortable=0)]
    cat = build_catalog(meta_rows, [], {}, lang_col="EnglishLabel")
    assert cat == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_reporting_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError` / `ImportError: build_catalog`.

- [ ] **Step 3: Write minimal implementation**

```python
# nx_lib/reporting/catalog.py
"""Field catalog for curated reporting sources.

`build_catalog` is the pure merge of FieldMetadata rows, localized label rows,
and a per-field availability map (which processes expose the field). The DB
fetch (`fetch_docprocessing_catalog`) is a thin wrapper that mirrors
dashboard.dashboard_field_metadata and feeds build_catalog.
"""

from ..db import engine_nexora_db

_LANG_COLS = {"de": "GermanLabel", "fr": "FrenchLabel", "it": "ItalianLabel"}


def build_catalog(meta_rows, label_rows, availability, *, lang_col):
    """Merge metadata + labels + availability into a sorted list of field dicts.

    Each entry: {field, label, type, aggregable, sortable, filterable, processes}.
    A field is only included if it appears in `availability` (i.e. at least one
    permitted process exposes it). Filterable = appears in availability (every
    exposed field can be filtered in phase 1).
    """
    labels = {}
    for r in label_rows:
        labels[r.FieldKey] = getattr(r, lang_col, None) or r.EnglishLabel

    out = []
    for r in meta_rows:
        fk = r.FieldKey
        if fk not in availability:
            continue
        out.append(
            {
                "field": fk,
                "label": labels.get(fk) or fk.replace("_", " ").title(),
                "type": r.DataType,
                "aggregable": bool(r.Aggregable),
                "sortable": bool(r.Sortable),
                "filterable": True,
                "processes": sorted(availability[fk]),
            }
        )
    out.sort(key=lambda e: e["label"])
    return out


def lang_col_for(locale_str):
    """Return the FieldMetadata label column name for a locale string."""
    return _LANG_COLS.get(locale_str, "EnglishLabel")


def fetch_docprocessing_catalog(allowed_processes, locale_str):
    """Load the docprocessing field catalog for the given allowed processes.

    Returns build_catalog(...) output. Mirrors the dashboard field_metadata
    query: FieldMetadata (+ Search_Field_Labels) joined to per-process
    SearchConfig.col_* availability. `processname`/`status` are always available
    for any allowed process.
    """
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT FieldKey, DataType, Aggregable, Sortable FROM FieldMetadata")
        meta_rows = cur.fetchall()
        cur.execute(
            "SELECT FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel "
            "FROM Search_Field_Labels"
        )
        label_rows = cur.fetchall()

        cur.execute("SELECT TOP 0 * FROM SearchConfig")
        cols = [c[0] for c in cur.description if c[0].startswith("col_")]
        select_cols = ", ".join(cols)
        cur.execute(f"SELECT ProcessName, {select_cols} FROM SearchConfig")
        availability = {}
        allowed = set(allowed_processes)
        for row in cur.fetchall():
            if row.ProcessName not in allowed:
                continue
            for i, col in enumerate(cols):
                if row[i + 1]:
                    availability.setdefault(col[len("col_"):], []).append(row.ProcessName)
        for fk in ("processname", "status"):
            availability[fk] = list(allowed_processes)

        return build_catalog(meta_rows, label_rows, availability, lang_col=lang_col_for(locale_str))
    finally:
        conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_reporting_catalog.py -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
ruff check nx_lib/reporting/catalog.py tests/unit/test_reporting_catalog.py
ruff format nx_lib/reporting/catalog.py tests/unit/test_reporting_catalog.py
git add nx_lib/reporting/catalog.py tests/unit/test_reporting_catalog.py
git commit -m "feat(reporting): add field catalog mapping for docprocessing"
```

---

## Task 3: Source registry + per-user access

**Files:**
- Create: `nx_lib/reporting/sources.py`
- Test: `tests/unit/test_reporting_sources.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_reporting_sources.py
"""Unit tests for nx_lib.reporting.sources — built-in registry + access filter."""

from nx_lib.reporting.sources import (
    DEFAULT_ROW_LIMIT,
    MAX_ROW_LIMIT,
    get_source,
    list_accessible_sources,
)


def test_docprocessing_source_is_registered():
    src = get_source("docprocessing")
    assert src is not None
    assert src["id"] == "docprocessing"
    assert src["kind"] == "curated"
    assert src["permission"] == "reporting.source.docprocessing"


def test_get_unknown_source_returns_none():
    assert get_source("nope") is None


def test_list_accessible_filters_by_permission():
    perms = {"reporting.view", "reporting.source.docprocessing"}
    ids = [s["id"] for s in list_accessible_sources(perms)]
    assert "docprocessing" in ids


def test_list_accessible_excludes_without_permission():
    perms = {"reporting.view"}
    assert list_accessible_sources(perms) == []


def test_row_limit_constants_sane():
    assert 0 < DEFAULT_ROW_LIMIT <= MAX_ROW_LIMIT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_reporting_sources.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# nx_lib/reporting/sources.py
"""Registry of reporting data sources.

Phase 1 ships one curated source: `docprocessing` (Document Processing stats).
Sources are code-defined for now; a DB-backed registry can replace this later.
Each source: {id, kind, label, permission, engine}. `engine` is a key resolved
to a real SQLAlchemy engine in the view layer (keeps this module DB-free for
unit tests).
"""

DEFAULT_ROW_LIMIT = 5000
MAX_ROW_LIMIT = 50000

_SOURCES = {
    "docprocessing": {
        "id": "docprocessing",
        "kind": "curated",
        "label": "Document Processing",
        "permission": "reporting.source.docprocessing",
        "engine": "statistics",
    },
}


def get_source(source_id):
    """Return the source descriptor dict, or None if unknown."""
    return _SOURCES.get(source_id)


def list_accessible_sources(permissions):
    """Return source descriptors the holder of `permissions` (a set) may use."""
    return [s for s in _SOURCES.values() if s["permission"] in permissions]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_reporting_sources.py -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
ruff check nx_lib/reporting/sources.py tests/unit/test_reporting_sources.py
ruff format nx_lib/reporting/sources.py tests/unit/test_reporting_sources.py
git add nx_lib/reporting/sources.py tests/unit/test_reporting_sources.py
git commit -m "feat(reporting): add data-source registry with per-user access"
```

---

## Task 4: Parameterized table-query builder

**Files:**
- Create: `nx_lib/reporting/query.py`
- Test: `tests/unit/test_reporting_query.py`

This is the crux. `build_table_query` is **pure**: it takes the validated report
definition plus injected per-process configs and column maps, and returns
`(sql, params)`. It UNION-ALLs one subquery per in-scope process (mirroring the
dashboard's multi-process union), projects the requested columns (NULL where a
process lacks a field), applies filters/date-scope/`additionalCondition`, then
sorts and caps at the outer level. Column names come only from the injected
maps — never from the client.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_reporting_query.py
"""Unit tests for nx_lib.reporting.query.build_table_query (pure)."""

import pytest

from nx_lib.reporting.query import QueryBuildError, build_table_query

# Two processes; 'pages' only mapped in proc A.
PROCESS_CONFIGS = [
    {"process": "acme.inv", "table": "dbo.StatA", "export_col": "ExportDate",
     "import_col": "ImportDate", "condition": ""},
    {"process": "acme.hr", "table": "dbo.StatB", "export_col": "ExpD",
     "import_col": "ImpD", "condition": "AND IsValid = 1"},
]
FIELD_COL_MAPS = {
    "acme.inv": {"doctype": "DocType", "status": "Status", "pages": "PageCount"},
    "acme.hr": {"doctype": "DType", "status": "Stat"},
}
CATALOG = {"doctype", "status", "pages", "date"}


def _rd(**over):
    base = {
        "schemaVersion": 1, "source": "docprocessing", "visualization": "table",
        "title": "t", "subtitle": None,
        "columns": [{"field": "doctype", "header": "Type", "agg": None},
                    {"field": "pages", "header": "Pages", "agg": None}],
        "groupBy": [], "filters": [], "sort": [{"field": "doctype", "dir": "asc"}],
        "scope": {"clients": [], "processes": ["acme.inv", "acme.hr"]},
        "rowLimit": 100, "sql": None, "sqlTarget": None,
    }
    base.update(over)
    return base


def test_builds_union_over_processes_with_top_and_order():
    sql, params = build_table_query(_rd(), PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "UNION ALL" in sql
    assert sql.strip().upper().startswith("SELECT TOP (100)")
    assert "ORDER BY" in sql
    # 'pages' missing in acme.hr → projected as NULL there
    assert "NULL AS [pages]" in sql


def test_unknown_column_raises():
    with pytest.raises(QueryBuildError):
        build_table_query(_rd(columns=[{"field": "evil", "header": "x", "agg": None}]),
                          PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)


def test_eq_filter_is_parameterized():
    rd = _rd(filters=[{"field": "status", "op": "eq", "value": "Done"}])
    sql, params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "= ?" in sql
    assert "Done" in params


def test_in_filter_expands_placeholders():
    rd = _rd(filters=[{"field": "status", "op": "in", "value": ["A", "B"]}])
    sql, params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "IN (?, ?)" in sql
    assert params.count("A") + params.count("B") >= 2


def test_filter_field_unmapped_in_process_excludes_that_process():
    # filter on 'pages' which acme.hr lacks → only acme.inv subquery remains
    rd = _rd(filters=[{"field": "pages", "op": "gt", "value": 3}])
    sql, _params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "dbo.StatA" in sql
    assert "dbo.StatB" not in sql


def test_additional_condition_is_appended():
    sql, _params = build_table_query(_rd(), PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "IsValid = 1" in sql


def test_empty_process_scope_raises():
    with pytest.raises(QueryBuildError):
        build_table_query(_rd(scope={"clients": [], "processes": []}),
                          [], FIELD_COL_MAPS, row_cap=100)


def test_row_cap_overrides_definition_limit():
    sql, _ = build_table_query(_rd(rowLimit=999), PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=50)
    assert "SELECT TOP (50)" in sql
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_reporting_query.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# nx_lib/reporting/query.py
"""Translate a validated report definition into a parameterized SQL query.

build_table_query is pure: it receives the report definition and injected
per-process configs + column maps (so it is DB-free and unit-testable), and
returns (sql, params) for the statistics engine. Every column/table name comes
from the injected maps/configs; only filter *values* become ? parameters.
"""

_OP_SQL = {
    "eq": "= ?",
    "ne": "<> ?",
    "gt": "> ?",
    "gte": ">= ?",
    "lt": "< ?",
    "lte": "<= ?",
    "contains": "LIKE ?",
    "starts_with": "LIKE ?",
    "is_null": "IS NULL",
    "is_not_null": "IS NOT NULL",
}


class QueryBuildError(ValueError):
    """Raised when a report definition cannot be turned into SQL."""


def _filter_clause(col, op, value, params):
    """Append a single filter clause for `col`. Returns the SQL fragment."""
    if op in ("is_null", "is_not_null"):
        return f"{col} {_OP_SQL[op]}"
    if op == "in" or op == "not_in":
        values = value if isinstance(value, list) else [value]
        if not values:
            # empty IN — make it match nothing / everything safely
            return "1 = 0" if op == "in" else "1 = 1"
        placeholders = ", ".join(["?"] * len(values))
        params.extend(values)
        keyword = "IN" if op == "in" else "NOT IN"
        return f"{col} {keyword} ({placeholders})"
    if op == "between":
        if not isinstance(value, list) or len(value) != 2:
            raise QueryBuildError("between requires a 2-element list")
        params.extend(value)
        return f"{col} BETWEEN ? AND ?"
    if op == "contains":
        params.append(f"%{value}%")
        return f"{col} LIKE ?"
    if op == "starts_with":
        params.append(f"{value}%")
        return f"{col} LIKE ?"
    # simple binary ops
    params.append(value)
    return f"{col} {_OP_SQL[op]}"


def build_table_query(rd, process_configs, field_col_maps, *, row_cap):
    """Build (sql, params) for a table report.

    process_configs: [{process, table, export_col, import_col, condition}] already
      filtered to the effective (permitted ∩ requested) process scope.
    field_col_maps: {process: {field_key: actual_column_name}}.
    row_cap: server-enforced TOP cap (min of definition rowLimit and server max).
    """
    if not process_configs:
        raise QueryBuildError("no processes in scope")

    columns = [c["field"] for c in rd["columns"]]
    filters = rd.get("filters") or []
    sort = rd.get("sort") or []
    cap = min(int(rd.get("rowLimit", row_cap)), int(row_cap))

    sub_queries = []
    params = []
    for cfg in process_configs:
        colmap = field_col_maps.get(cfg["process"], {})

        # A filter referencing a field this process doesn't expose can never
        # match here — drop the whole subquery for correctness.
        if any(f["field"] not in colmap and f["field"] != "processname" for f in filters):
            continue

        select_exprs = []
        for field in columns:
            if field == "processname":
                select_exprs.append("? AS [processname]")
                params.append(cfg["process"])
            else:
                actual = colmap.get(field)
                if actual:
                    select_exprs.append(f"{actual} AS [{field}]")
                else:
                    select_exprs.append(f"NULL AS [{field}]")

        where = ["1 = 1"]
        for f in filters:
            col = colmap.get(f["field"])
            if not col:
                continue
            where.append(_filter_clause(col, f["op"], f.get("value"), params))
        cond = f" {cfg['condition']}" if cfg.get("condition") else ""
        sub_queries.append(
            f"SELECT {', '.join(select_exprs)} FROM [{cfg['table']}] "
            f"WHERE {' AND '.join(where)}{cond}"
        )

    if not sub_queries:
        raise QueryBuildError("no subqueries produced for the requested scope/filters")

    inner = " UNION ALL ".join(sub_queries)
    out_cols = ", ".join(f"[{c}]" for c in columns)
    sql = f"SELECT TOP ({cap}) {out_cols} FROM ({inner}) t"
    if sort:
        order = ", ".join(f"[{s['field']}] {s['dir'].upper()}" for s in sort)
        sql += f" ORDER BY {order}"
    return sql, params
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_reporting_query.py -v`
Expected: PASS (all 8 tests).

- [ ] **Step 5: Lint + commit**

```bash
ruff check nx_lib/reporting/query.py tests/unit/test_reporting_query.py
ruff format nx_lib/reporting/query.py tests/unit/test_reporting_query.py
git add nx_lib/reporting/query.py tests/unit/test_reporting_query.py
git commit -m "feat(reporting): add parameterized table-query builder"
```

---

## Task 5: Excel exporter (+ openpyxl dependency)

**Files:**
- Modify: `pyproject.toml:11-31` (add dependency), regenerate `requirements.txt`
- Create: `nx_lib/reporting/export.py`
- Test: `tests/unit/test_reporting_export.py`

- [ ] **Step 1: Add the dependency and regenerate requirements**

Edit `pyproject.toml` — add to `[project.dependencies]` (after `prompt_toolkit`):
```toml
    "openpyxl==3.1.5",
```
Then regenerate the IIS requirements file (do NOT hand-edit requirements.txt):
```bash
uv lock
uv export --format requirements-txt --no-hashes --no-dev -o requirements.txt
uv pip install openpyxl==3.1.5
```
Expected: `requirements.txt` now lists `openpyxl==3.1.5` and `et-xmlfile` (its dep).

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_reporting_export.py
"""Unit tests for nx_lib.reporting.export — rows → xlsx bytes."""

import io

from openpyxl import load_workbook

from nx_lib.reporting.export import rows_to_xlsx


def test_rows_to_xlsx_uses_custom_headers_and_title():
    columns = [{"field": "doctype", "header": "Document type"},
               {"field": "pages", "header": "Pages"}]
    rows = [["Invoice", 3], ["Letter", 1]]
    data = rows_to_xlsx(columns, rows, title="Q1 report")
    wb = load_workbook(io.BytesIO(data))
    ws = wb.active
    assert ws["A1"].value == "Document type"
    assert ws["B1"].value == "Pages"
    assert ws["A2"].value == "Invoice"
    assert ws["B3"].value == 1


def test_rows_to_xlsx_falls_back_to_field_when_no_header():
    columns = [{"field": "doctype", "header": None}]
    data = rows_to_xlsx(columns, [["x"]], title="t")
    ws = load_workbook(io.BytesIO(data)).active
    assert ws["A1"].value == "doctype"


def test_rows_to_xlsx_returns_bytes():
    data = rows_to_xlsx([{"field": "a", "header": "A"}], [], title="t")
    assert isinstance(data, (bytes, bytearray)) and len(data) > 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_reporting_export.py -v`
Expected: FAIL — `ImportError: rows_to_xlsx`.

- [ ] **Step 4: Write minimal implementation**

```python
# nx_lib/reporting/export.py
"""Export report rows to an .xlsx workbook (openpyxl)."""

import io

from openpyxl import Workbook


def rows_to_xlsx(columns, rows, *, title):
    """Return .xlsx bytes for `rows` with a header row from `columns`.

    columns: [{field, header}] — header falls back to field when None/empty.
    rows: iterable of row sequences aligned to columns.
    title: used as the worksheet title (truncated to Excel's 31-char limit).
    """
    wb = Workbook()
    ws = wb.active
    ws.title = (title or "Report")[:31]
    ws.append([(c.get("header") or c["field"]) for c in columns])
    for row in rows:
        ws.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_reporting_export.py -v`
Expected: PASS.

- [ ] **Step 6: Lint + commit**

```bash
ruff check nx_lib/reporting/export.py tests/unit/test_reporting_export.py
ruff format nx_lib/reporting/export.py tests/unit/test_reporting_export.py
git add pyproject.toml uv.lock requirements.txt nx_lib/reporting/export.py tests/unit/test_reporting_export.py
git commit -m "feat(reporting): add xlsx exporter and openpyxl dependency"
```

---

## Task 6: Database migrations — Reports table + reporting permissions

**Files:**
- Create: `sql/_migrations/NexoraDB/0004_create_reports_table.sql`
- Create: `sql/_migrations/NexoraDB/0005_seed_reporting_permissions.sql`

Both idempotent so the pre-commit hook can re-apply safely.

- [ ] **Step 1: Write the Reports table migration**

```sql
-- 0004_create_reports_table.sql
-- Per-user saved report definitions for the Reporting page. DefinitionJSON holds
-- the v1 report definition validated by nx_lib.reporting.schema. Sharing is
-- deferred; OwnerUserID scopes visibility for now.
IF OBJECT_ID(N'dbo.Reports', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Reports (
        ReportID        INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Reports PRIMARY KEY,
        OwnerUserID     INT NOT NULL,
        Name            NVARCHAR(200) NOT NULL,
        DefinitionJSON  NVARCHAR(MAX) NOT NULL,
        CreatedAt       DATETIME2 NOT NULL CONSTRAINT DF_Reports_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt       DATETIME2 NOT NULL CONSTRAINT DF_Reports_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_Reports_Users FOREIGN KEY (OwnerUserID) REFERENCES dbo.Users(userID)
    );
    CREATE INDEX IX_Reports_Owner ON dbo.Reports(OwnerUserID);
END;
GO
```

- [ ] **Step 2: Write the permissions seed migration**

```sql
-- 0005_seed_reporting_permissions.sql
-- Adds reporting.* permission codes and grants them to whichever access profiles
-- already grant admin.view (Effect 'A'). Also mirrors each existing
-- dashboard.filter.process.<client>.<process> grant into a separate
-- reporting.scope.process.<client>.<process> permission, so users who can see a
-- process on the dashboard can include it in reports. Idempotent throughout.

-- 1) base reporting permission codes
INSERT INTO dbo.Permission (Code, Description)
SELECT v.Code, v.Descr
FROM (VALUES
    ('reporting.view',                  'Access the Reporting page'),
    ('reporting.source.docprocessing',  'Reporting: use the Document Processing source'),
    ('reporting.export',                'Reporting: export reports to Excel')
) AS v(Code, Descr)
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = v.Code);
GO

-- 2) scope perms mirrored from dashboard.filter.process.*
INSERT INTO dbo.Permission (Code, Description)
SELECT REPLACE(p.Code, 'dashboard.filter.process.', 'reporting.scope.process.'),
       CONCAT('Reporting scope: ', REPLACE(p.Code, 'dashboard.filter.process.', ''))
FROM dbo.Permission p
WHERE p.Code LIKE 'dashboard.filter.process.%'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.Permission p2
        WHERE p2.Code = REPLACE(p.Code, 'dashboard.filter.process.', 'reporting.scope.process.')
  );
GO

-- 3) grant base reporting perms to every profile that grants admin.view ('A')
INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code IN ('reporting.view', 'reporting.source.docprocessing', 'reporting.export')
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO

-- 4) grant each reporting.scope.process.* to the same profiles that grant the
--    matching dashboard.filter.process.* ('A')
INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, rp.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission dp ON dp.PermissionID = ap.PermissionID
                       AND dp.Code LIKE 'dashboard.filter.process.%' AND ap.Effect = 'A'
JOIN dbo.Permission rp ON rp.Code = REPLACE(dp.Code, 'dashboard.filter.process.', 'reporting.scope.process.')
WHERE NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = rp.PermissionID
);
GO
```

- [ ] **Step 3: Apply to INT and verify**

Run:
```bash
python scripts/db-migrate.py --env INT
```
Expected: reports `0004_create_reports_table.sql` and `0005_seed_reporting_permissions.sql` applied (or "already applied"). Then verify:
```bash
python sql/sync-from-db.py --check
```
Expected: per-object dumps still match INT (new `dbo.Reports` table + `Permission` rows generated). If `sync-from-db.py` reports the new table, re-run it without `--check` to refresh dumps and stage them.

- [ ] **Step 4: Commit**

```bash
git add sql/_migrations/NexoraDB/0004_create_reports_table.sql \
        sql/_migrations/NexoraDB/0005_seed_reporting_permissions.sql \
        sql/NexoraDB
git commit -m "feat(reporting): add Reports table and reporting.* permissions migrations"
```

---

## Task 7: View module — routes (page + APIs)

**Files:**
- Create: `nx_lib/views/reporting.py`
- Modify: `nx_lib/__init__.py:66-75`
- Test: `tests/integration/test_reporting_routes.py`

The view wires the engine to real engines/session. It resolves the caller's
allowed processes from `reporting.scope.process.*` perms (separate scope, per
spec), loads `Statconfig` + `SearchConfig` maps (reusing the dashboard's column
resolution), then validates → builds → runs → returns. Saved-report CRUD uses
the `Reports` table.

- [ ] **Step 1: Write the failing integration test**

```python
# tests/integration/test_reporting_routes.py
"""Integration tests for nx_lib.views.reporting.

Seed test users have no reporting.* perms, so guarded routes return 403 (authed)
or redirect (anon). Endpoints whose first DB hit needs tables absent from the
TEST schema are asserted as (200, 500) to stay forward-compatible, mirroring the
dashboard route tests.
"""


def test_reporting_anonymous_redirects_to_login(client):
    resp = client.get("/reporting", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_reporting_without_perm_returns_403(user_client):
    resp = user_client.get("/reporting")
    assert resp.status_code == 403


def test_sources_without_perm_returns_403(user_client):
    resp = user_client.get("/api/reporting/sources")
    assert resp.status_code == 403


def test_run_invalid_json_returns_400_or_403(user_client):
    # no perm → 403 before body parsing
    resp = user_client.post("/api/reporting/run", data="not-json")
    assert resp.status_code in (400, 403)


def test_run_anonymous_redirects(client):
    resp = client.post("/api/reporting/run", json={}, follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_reports_list_without_perm_403(user_client):
    resp = user_client.get("/api/reporting/reports")
    assert resp.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/integration/test_reporting_routes.py -v`
Expected: FAIL — 404 for all routes (not registered yet).

- [ ] **Step 3: Write the view module**

```python
# nx_lib/views/reporting.py
"""Self-service Reporting page (curated table sources) — Phase 1.

Routes:
  GET  /reporting                     builder page
  GET  /api/reporting/sources         sources + field catalog the caller may use
  POST /api/reporting/run             run a curated report definition -> rows
  POST /api/reporting/export          report definition -> .xlsx download
  GET  /api/reporting/reports         list the caller's saved reports
  POST /api/reporting/reports         create a saved report
  GET  /api/reporting/reports/<id>    load one
  PUT  /api/reporting/reports/<id>    update
  DELETE /api/reporting/reports/<id>  delete
"""

import json

from flask import Response, current_app, jsonify, redirect, render_template, request, session, url_for
from flask_babel import gettext as _

from ..db import engine_nexora_db, engine_statistics_db
from ..extensions import limiter
from ..i18n import get_locale
from ..reporting.catalog import fetch_docprocessing_catalog
from ..reporting.export import rows_to_xlsx
from ..reporting.query import QueryBuildError, build_table_query
from ..reporting.schema import ReportDefinitionError, validate_report_definition
from ..reporting.sources import DEFAULT_ROW_LIMIT, MAX_ROW_LIMIT, get_source, list_accessible_sources
from ..security import has_permission, page_visibility, require_permission

_SCOPE_PREFIX = "reporting.scope.process."


def _allowed_processes():
    """Processes the caller may include, from reporting.scope.process.* perms.

    Code shape: reporting.scope.process.<client>.<process> -> '<client>.<process>'.
    """
    perms = session.get("permissions", [])
    return sorted(
        {
            ".".join(p[len(_SCOPE_PREFIX):].rsplit(".", 1))
            for p in perms
            if p.startswith(_SCOPE_PREFIX)
        }
    )


def _load_process_configs(target_processes):
    """Load Statconfig rows for the target processes as plain dicts."""
    if not target_processes:
        return []
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        ph = ",".join(["?"] * len(target_processes))
        cur.execute(
            f"SELECT ProcessName, TableName, ExportColumn, ImportColumn, additionalCondition "
            f"FROM Statconfig WHERE ProcessName IN ({ph})",
            target_processes,
        )
        return [
            {
                "process": r.ProcessName,
                "table": r.TableName,
                "export_col": r.ExportColumn,
                "import_col": r.ImportColumn,
                "condition": r.additionalCondition or "",
            }
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def _load_field_col_maps(target_processes):
    """Load per-process {field_key: actual_column} maps from SearchConfig."""
    maps = {}
    if not target_processes:
        return maps
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT TOP 0 * FROM SearchConfig")
        cols = [c[0] for c in cur.description if c[0].startswith("col_")]
        select_cols = ", ".join(cols)
        ph = ",".join(["?"] * len(target_processes))
        cur.execute(
            f"SELECT ProcessName, {select_cols} FROM SearchConfig WHERE ProcessName IN ({ph})",
            target_processes,
        )
        for row in cur.fetchall():
            m = {}
            for i, col in enumerate(cols):
                val = row[i + 1]
                if val:
                    m[col[len("col_"):]] = val
            maps[row.ProcessName] = m
        return maps
    finally:
        conn.close()


def _effective_scope(rd, allowed):
    """Intersection of requested scope.processes and the caller's allowed set."""
    requested = (rd.get("scope") or {}).get("processes") or []
    allowed_set = set(allowed)
    if not requested:
        return list(allowed)
    return [p for p in requested if p in allowed_set]


def _prepare_run(rd):
    """Validate + build a query for a curated report. Returns (columns, sql, params).

    Raises ReportDefinitionError / QueryBuildError on bad input.
    """
    source = get_source(rd.get("source"))
    if source is None or source["kind"] != "curated":
        raise ReportDefinitionError("unknown or unsupported source")
    if not has_permission(source["permission"]):
        raise PermissionError(source["permission"])

    allowed = _allowed_processes()
    catalog = fetch_docprocessing_catalog(allowed, str(get_locale()))
    catalog_fields = {f["field"] for f in catalog}
    filterable = {f["field"] for f in catalog if f["filterable"]}
    sortable = {f["field"] for f in catalog if f["sortable"]}

    validate_report_definition(
        rd, catalog_fields, filterable, sortable, max_row_limit=MAX_ROW_LIMIT
    )

    scope = _effective_scope(rd, allowed)
    configs = _load_process_configs(scope)
    col_maps = _load_field_col_maps(scope)
    sql, params = build_table_query(rd, configs, col_maps, row_cap=rd.get("rowLimit", DEFAULT_ROW_LIMIT))
    columns = rd["columns"]
    return columns, sql, params


def _execute(sql, params):
    conn = engine_statistics_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = [list(r) for r in cur.fetchall()]
        return rows
    finally:
        conn.close()


@require_permission("reporting.view")
def reporting():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template(
        "reporting.html",
        logged_in_user=session.get("username", "Unknown"),
        userid=session.get("userid", "Unknown"),
        fullname=session.get("fullname"),
        pageV=page_visibility(),
    )


@require_permission("reporting.view")
def api_sources():
    perms = set(session.get("permissions", []))
    sources = list_accessible_sources(perms)
    out = []
    for s in sources:
        entry = {"id": s["id"], "label": s["label"], "kind": s["kind"]}
        if s["id"] == "docprocessing":
            entry["fields"] = fetch_docprocessing_catalog(_allowed_processes(), str(get_locale()))
            entry["processes"] = _allowed_processes()
        out.append(entry)
    return jsonify(out)


@require_permission("reporting.view")
@limiter.limit("120 per minute")
def api_run():
    rd = request.get_json(silent=True)
    if not isinstance(rd, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    try:
        columns, sql, params = _prepare_run(rd)
    except PermissionError:
        return jsonify({"error": _("Not authorized for this source")}), 403
    except (ReportDefinitionError, QueryBuildError) as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"/api/reporting/run prepare error: {e}")
        return jsonify({"error": _("Could not build report")}), 500
    try:
        rows = _execute(sql, params)
    except Exception as e:
        current_app.logger.error(f"/api/reporting/run exec error: {e}")
        return jsonify({"error": _("Could not run report")}), 500
    return jsonify(
        {
            "columns": [{"field": c["field"], "header": c.get("header") or c["field"]} for c in columns],
            "rows": rows,
            "rowCount": len(rows),
            "truncated": len(rows) >= min(int(rd.get("rowLimit", DEFAULT_ROW_LIMIT)), MAX_ROW_LIMIT),
        }
    )


@require_permission("reporting.export")
@limiter.limit("30 per minute")
def api_export():
    rd = request.get_json(silent=True)
    if not isinstance(rd, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    try:
        columns, sql, params = _prepare_run(rd)
        rows = _execute(sql, params)
    except PermissionError:
        return jsonify({"error": _("Not authorized for this source")}), 403
    except (ReportDefinitionError, QueryBuildError) as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"/api/reporting/export error: {e}")
        return jsonify({"error": _("Could not export report")}), 500
    data = rows_to_xlsx(columns, rows, title=rd.get("title") or "Report")
    filename = (rd.get("title") or "report").strip().replace('"', "") + ".xlsx"
    return Response(
        data,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@require_permission("reporting.view")
def api_reports_list():
    userid = session.get("userid")
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT ReportID, Name, UpdatedAt FROM Reports WHERE OwnerUserID = ? ORDER BY UpdatedAt DESC",
            (userid,),
        )
        return jsonify(
            [{"id": r.ReportID, "name": r.Name, "updatedAt": str(r.UpdatedAt)} for r in cur.fetchall()]
        )
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports list error: {e}")
        return jsonify({"error": _("Could not list reports")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
def api_reports_get(report_id):
    userid = session.get("userid")
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT Name, DefinitionJSON FROM Reports WHERE ReportID = ? AND OwnerUserID = ?",
            (report_id, userid),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": _("Not found")}), 404
        return jsonify({"id": report_id, "name": row.Name, "definition": json.loads(row.DefinitionJSON)})
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports get error: {e}")
        return jsonify({"error": _("Could not load report")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
@limiter.limit("60 per minute")
def api_reports_create():
    userid = session.get("userid")
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    rd = payload.get("definition")
    if not name or not isinstance(rd, dict):
        return jsonify({"error": _("name and definition are required")}), 400
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO Reports (OwnerUserID, Name, DefinitionJSON) OUTPUT INSERTED.ReportID VALUES (?, ?, ?)",
            (userid, name, json.dumps(rd, ensure_ascii=False)),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({"id": new_id, "ok": True})
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports create error: {e}")
        return jsonify({"error": _("Could not save report")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
@limiter.limit("60 per minute")
def api_reports_update(report_id):
    userid = session.get("userid")
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    rd = payload.get("definition")
    if not name or not isinstance(rd, dict):
        return jsonify({"error": _("name and definition are required")}), 400
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE Reports SET Name = ?, DefinitionJSON = ?, UpdatedAt = SYSUTCDATETIME() "
            "WHERE ReportID = ? AND OwnerUserID = ?",
            (name, json.dumps(rd, ensure_ascii=False), report_id, userid),
        )
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports update error: {e}")
        return jsonify({"error": _("Could not update report")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
def api_reports_delete(report_id):
    userid = session.get("userid")
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM Reports WHERE ReportID = ? AND OwnerUserID = ?", (report_id, userid))
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports delete error: {e}")
        return jsonify({"error": _("Could not delete report")}), 500
    finally:
        conn.close()


def register_routes(app):
    app.add_url_rule("/reporting", endpoint="reporting", view_func=reporting)
    app.add_url_rule("/api/reporting/sources", endpoint="reporting_sources", view_func=api_sources)
    app.add_url_rule("/api/reporting/run", endpoint="reporting_run", view_func=api_run, methods=["POST"])
    app.add_url_rule("/api/reporting/export", endpoint="reporting_export", view_func=api_export, methods=["POST"])
    app.add_url_rule("/api/reporting/reports", endpoint="reporting_reports_list", view_func=api_reports_list)
    app.add_url_rule("/api/reporting/reports", endpoint="reporting_reports_create", view_func=api_reports_create, methods=["POST"])
    app.add_url_rule("/api/reporting/reports/<int:report_id>", endpoint="reporting_reports_get", view_func=api_reports_get)
    app.add_url_rule("/api/reporting/reports/<int:report_id>", endpoint="reporting_reports_update", view_func=api_reports_update, methods=["PUT"])
    app.add_url_rule("/api/reporting/reports/<int:report_id>", endpoint="reporting_reports_delete", view_func=api_reports_delete, methods=["DELETE"])
```

- [ ] **Step 4: Register the module**

Edit `nx_lib/__init__.py` — add the import alongside the other view imports and a `reporting.register_routes(app)` line next to `dashboard.register_routes(app)` (around line 70). Match the existing import style (the views are imported as a group near the top of `create_app`; add `reporting` to that group, then call `reporting.register_routes(app)`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/integration/test_reporting_routes.py -v`
Expected: PASS (403/302 as asserted).

- [ ] **Step 6: Lint + commit**

```bash
ruff check nx_lib/views/reporting.py nx_lib/__init__.py tests/integration/test_reporting_routes.py
ruff format nx_lib/views/reporting.py
git add nx_lib/views/reporting.py nx_lib/__init__.py tests/integration/test_reporting_routes.py
git commit -m "feat(reporting): add reporting view module and routes"
```

---

## Task 8: Security wiring — page visibility + nav

**Files:**
- Modify: `nx_lib/security.py:111-150`
- Modify: `templates/_header.html:77-92`
- Test: `tests/unit/test_security.py` (add a case)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_security.py`:
```python
def test_page_visibility_includes_reporting(app):
    from nx_lib.security import page_visibility

    with app.test_request_context():
        from flask import session

        session["permissions"] = ["reporting.view"]
        pv = page_visibility()
        assert pv["reportingPagePerm"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_security.py::test_page_visibility_includes_reporting -v`
Expected: FAIL — `KeyError: 'reportingPagePerm'`.

- [ ] **Step 3: Implement**

In `nx_lib/security.py`, add to the `page_visibility()` dict (after `dashboardPagePerm`):
```python
        "reportingPagePerm": has_permission("reporting.view"),
```
And in `startpage_redirect_to`'s `perm_to_function` map, add after `"dashboardPagePerm": "dashboard",`:
```python
        "reportingPagePerm": "reporting",
```

- [ ] **Step 4: Add the nav item**

In `templates/_header.html`, add to the `nav_items` list (after the dashboard entry, ~line 79):
```jinja
                {'perm': pageV.reportingPagePerm, 'url': url_for('reporting'),        'icon': 'fa-chart-column',        'label': _('Reporting'),              'active': active_page == 'reporting'},
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_security.py::test_page_visibility_includes_reporting -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add nx_lib/security.py templates/_header.html tests/unit/test_security.py
git commit -m "feat(reporting): wire reporting into nav and page visibility"
```

---

## Task 9: Frontend — Reporting page (Layout A)

**Files:**
- Create: `templates/reporting.html`
- Create: `templates/js/_reporting_js.html`
- Create: `static/css/reporting.css`
- Test: `tests/e2e/test_reporting.py`

Layout A: left **Field panel** (source select + searchable field list), center
**Results** (toolbar with Table|SQL toggle [SQL disabled in Phase 1], title input,
Save, Export, results table), right **Config wells** (Columns, Filters, Sort,
Format/Headers). Vanilla JS, follows the dashboard template/JS-partial pattern.

- [ ] **Step 1: Write the page template**

Create `templates/reporting.html` modeled on `templates/dashboard.html` (same
`<head>` CDN includes: Chart.js, flatpickr, Inter, FontAwesome; add
`static/css/reporting.css`). Body:
```jinja
<!DOCTYPE html>
<html lang="{{ get_locale }}">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{{ _("Reporting - nexora") }}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css">
  <script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css" />
  <link rel="stylesheet" href="{{ url_for('static',filename='css/reporting.css') }}">
  <link rel="icon" type="image/x-icon" href="{{ url_for('static',filename='images/favicon.ico') }}">
</head>
<body class="bg-gray-50 text-gray-800">
  {% set active_page = 'reporting' %} {% include '_header.html' %}
  <main class="reporting-main" data-testid="reporting-page">
    <aside class="reporting-fields" data-testid="reporting-field-panel">
      <label class="reporting-label">{{ _("Source") }}</label>
      <select id="rpSource" data-testid="reporting-source-select"></select>
      <input id="rpFieldSearch" class="reporting-input" placeholder="{{ _('Search fields…') }}" data-testid="reporting-field-search">
      <ul id="rpFieldList" class="reporting-field-list"></ul>
    </aside>

    <section class="reporting-results">
      <div class="reporting-toolbar">
        <div class="reporting-mode-toggle">
          <button id="rpModeTable" class="active" data-testid="reporting-mode-table">{{ _("Table") }}</button>
          <button id="rpModeSql" disabled title="{{ _('Coming soon') }}" data-testid="reporting-mode-sql">{{ _("SQL") }}</button>
        </div>
        <input id="rpTitle" class="reporting-title-input" placeholder="{{ _('Untitled report') }}" data-testid="reporting-title">
        <span style="flex:1"></span>
        <button id="rpRun" class="reporting-btn" data-testid="reporting-run">{{ _("Run") }}</button>
        <button id="rpSave" class="reporting-btn" data-testid="reporting-save">{{ _("Save") }}</button>
        <button id="rpExport" class="reporting-btn" data-testid="reporting-export">{{ _("Export") }}</button>
      </div>
      <div id="rpResults" class="reporting-table-wrap" data-testid="reporting-results"></div>
    </section>

    <aside class="reporting-wells" data-testid="reporting-wells">
      <div class="reporting-well"><h4>{{ _("Columns") }}</h4><ul id="rpWellColumns"></ul></div>
      <div class="reporting-well"><h4>{{ _("Filters") }}</h4><div id="rpWellFilters"></div>
        <button id="rpAddFilter" class="reporting-link">+ {{ _("Add filter") }}</button></div>
      <div class="reporting-well"><h4>{{ _("Sort") }}</h4><div id="rpWellSort"></div></div>
      <div class="reporting-well"><h4>{{ _("Format") }}</h4>
        <input id="rpSubtitle" class="reporting-input" placeholder="{{ _('Subtitle') }}"></div>
    </aside>
  </main>
  {% include 'js/_reporting_js.html' %}
</body>
</html>
```

- [ ] **Step 2: Write the JS partial**

Create `templates/js/_reporting_js.html` — a `<script>` implementing the state +
fetch wiring. Required behaviors (write them out fully):
```html
<script>
(function () {
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const state = { source: null, fields: [], columns: [], filters: [], sort: [], processes: [] };

  async function api(url, opts = {}) {
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      ...opts,
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.statusText);
    return res;
  }

  function buildDefinition() {
    return {
      schemaVersion: 1, source: state.source, visualization: 'table',
      title: document.getElementById('rpTitle').value || 'Untitled report',
      subtitle: document.getElementById('rpSubtitle').value || null,
      columns: state.columns.map(c => ({ field: c.field, header: c.header || c.label, agg: null })),
      groupBy: [], filters: state.filters, sort: state.sort,
      scope: { clients: [], processes: state.processes },
      rowLimit: 5000, sql: null, sqlTarget: null,
    };
  }

  function renderFields() {
    const q = document.getElementById('rpFieldSearch').value.toLowerCase();
    const ul = document.getElementById('rpFieldList');
    ul.innerHTML = '';
    state.fields.filter(f => f.label.toLowerCase().includes(q)).forEach(f => {
      const li = document.createElement('li');
      li.textContent = f.label;
      li.onclick = () => { if (!state.columns.find(c => c.field === f.field)) { state.columns.push({ ...f, header: f.label }); renderWells(); } };
      ul.appendChild(li);
    });
  }

  function renderWells() {
    const cols = document.getElementById('rpWellColumns');
    cols.innerHTML = '';
    state.columns.forEach((c, i) => {
      const li = document.createElement('li');
      const inp = document.createElement('input');           // custom header editor
      inp.value = c.header; inp.oninput = e => { c.header = e.target.value; };
      const rm = document.createElement('button'); rm.textContent = '×';
      rm.onclick = () => { state.columns.splice(i, 1); renderWells(); };
      li.appendChild(inp); li.appendChild(rm); cols.appendChild(li);
    });
  }

  function renderResults(data) {
    const wrap = document.getElementById('rpResults');
    if (!data.rows.length) { wrap.innerHTML = '<p class="reporting-empty">No rows.</p>'; return; }
    const head = '<tr>' + data.columns.map(c => `<th>${c.header}</th>`).join('') + '</tr>';
    const body = data.rows.map(r => '<tr>' + r.map(v => `<td>${v == null ? '' : v}</td>`).join('') + '</tr>').join('');
    wrap.innerHTML = `<table class="reporting-table"><thead>${head}</thead><tbody>${body}</tbody></table>`;
  }

  async function loadSources() {
    const sources = await (await api('/api/reporting/sources')).json();
    const sel = document.getElementById('rpSource');
    sel.innerHTML = sources.map(s => `<option value="${s.id}">${s.label}</option>`).join('');
    function pick() {
      const s = sources.find(x => x.id === sel.value);
      state.source = s.id; state.fields = s.fields || []; state.processes = s.processes || [];
      state.columns = []; renderFields(); renderWells();
    }
    sel.onchange = pick; if (sources.length) pick();
  }

  async function run() {
    try { renderResults(await (await api('/api/reporting/run', { method: 'POST', body: JSON.stringify(buildDefinition()) })).json()); }
    catch (e) { document.getElementById('rpResults').innerHTML = `<p class="reporting-error">${e.message}</p>`; }
  }

  async function save() {
    const name = prompt('{{ _("Report name") }}', document.getElementById('rpTitle').value || 'Report');
    if (!name) return;
    await api('/api/reporting/reports', { method: 'POST', body: JSON.stringify({ name, definition: buildDefinition() }) });
    alert('{{ _("Saved") }}');
  }

  async function exportXlsx() {
    const res = await api('/api/reporting/export', { method: 'POST', body: JSON.stringify(buildDefinition()) });
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = (document.getElementById('rpTitle').value || 'report') + '.xlsx';
    a.click(); URL.revokeObjectURL(a.href);
  }

  function addFilter() {
    if (!state.fields.length) return;
    state.filters.push({ field: state.fields[0].field, op: 'eq', value: '' });
    renderFilters();
  }
  function renderFilters() {
    const box = document.getElementById('rpWellFilters');
    box.innerHTML = '';
    state.filters.forEach((f, i) => {
      const row = document.createElement('div'); row.className = 'reporting-filter-row';
      const fld = document.createElement('select');
      fld.innerHTML = state.fields.filter(x => x.filterable).map(x => `<option value="${x.field}">${x.label}</option>`).join('');
      fld.value = f.field; fld.onchange = e => { f.field = e.target.value; };
      const op = document.createElement('select');
      op.innerHTML = ['eq','ne','contains','starts_with','gt','gte','lt','lte','is_null','is_not_null']
        .map(o => `<option value="${o}">${o}</option>`).join('');
      op.value = f.op; op.onchange = e => { f.op = e.target.value; };
      const val = document.createElement('input'); val.value = f.value ?? '';
      val.oninput = e => { f.value = e.target.value; };
      const rm = document.createElement('button'); rm.textContent = '×';
      rm.onclick = () => { state.filters.splice(i, 1); renderFilters(); };
      row.append(fld, op, val, rm); box.appendChild(row);
    });
  }

  document.getElementById('rpFieldSearch').addEventListener('input', renderFields);
  document.getElementById('rpRun').addEventListener('click', run);
  document.getElementById('rpSave').addEventListener('click', save);
  document.getElementById('rpExport').addEventListener('click', exportXlsx);
  document.getElementById('rpAddFilter').addEventListener('click', addFilter);
  loadSources();
})();
</script>
```

- [ ] **Step 3: Write the CSS**

Create `static/css/reporting.css` implementing the three-column grid:
```css
.reporting-main { display: grid; grid-template-columns: 260px 1fr 300px; gap: 16px; padding: 20px; }
.reporting-fields, .reporting-wells { background:#fff; border:1px solid #eef; border-radius:14px; padding:14px; }
.reporting-results { background:#fff; border:1px solid #eef; border-radius:14px; padding:14px; min-height:60vh; }
.reporting-toolbar { display:flex; align-items:center; gap:8px; margin-bottom:12px; }
.reporting-mode-toggle button { padding:4px 10px; border-radius:8px; border:1px solid #ddd; }
.reporting-mode-toggle button.active { background:#4338ca; color:#fff; }
.reporting-mode-toggle button[disabled] { opacity:.5; cursor:not-allowed; }
.reporting-btn { padding:6px 12px; border-radius:8px; background:#4338ca; color:#fff; }
.reporting-input, .reporting-title-input, #rpSource { width:100%; padding:6px 8px; border:1px solid #ddd; border-radius:8px; margin:6px 0; }
.reporting-field-list { list-style:none; padding:0; max-height:60vh; overflow:auto; }
.reporting-field-list li { padding:6px 8px; border-radius:8px; cursor:pointer; }
.reporting-field-list li:hover { background:#eef2ff; }
.reporting-well { margin-bottom:16px; }
.reporting-well h4 { font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:#888; margin-bottom:6px; }
.reporting-filter-row { display:flex; gap:4px; margin-bottom:6px; }
.reporting-table { width:100%; border-collapse:collapse; font-size:13px; }
.reporting-table th, .reporting-table td { border:1px solid #eee; padding:6px 8px; text-align:left; }
.reporting-empty, .reporting-error { color:#888; padding:20px; }
.reporting-error { color:#c0392b; }
@media (max-width: 1100px){ .reporting-main{ grid-template-columns:1fr; } }
```

- [ ] **Step 4: Write the e2e smoke test**

```python
# tests/e2e/test_reporting.py
"""End-to-end smoke for the Reporting page. Requires a user with reporting.view.

Run locally with the dev server started via `nx -u -b --loginas:<user>`.
"""

import pytest

pytestmark = pytest.mark.flaky_e2e


def test_reporting_page_loads(page, base_url, reporting_user_login):
    page.goto(f"{base_url}/reporting")
    page.wait_for_selector('[data-testid="reporting-page"]')
    assert page.locator('[data-testid="reporting-source-select"]').count() == 1
    page.screenshot(path="var/screenshots/reporting_page.png")
```
> Note: `reporting_user_login` mirrors the existing e2e login fixtures in
> `tests/e2e/conftest.py`. If no seed user has `reporting.view` in TEST, add the
> grant to `sql/test/seed.sql` (grant `reporting.view`, `reporting.source.docprocessing`,
> `reporting.export` to the admin test access profile) in this step and reseed.

- [ ] **Step 5: Verify the page renders (manual + test)**

Run the unit/integration suite (fast) to ensure nothing regressed:
```bash
python -m pytest tests/unit/test_reporting_query.py tests/integration/test_reporting_routes.py -v
```
Then drive the page once with Playwright via `nx -u -b --loginas:<reporting-capable user>` and confirm sources load and a Run returns rows. Screenshot to `var/screenshots/`.

- [ ] **Step 6: Commit**

```bash
git add templates/reporting.html templates/js/_reporting_js.html static/css/reporting.css tests/e2e/test_reporting.py
git commit -m "feat(reporting): add Layout A report-builder page (table viz)"
```

---

## Task 10: Docs, changelog, deploy check

**Files:**
- Modify: `CHANGELOG.md`
- Create: `docs/howto/reporting.md`
- Modify: `CLAUDE.md`
- Check: `.github/workflows/deploy.yml`

- [ ] **Step 1: Changelog**

Add under `## [Unreleased]` → `### Added` in `CHANGELOG.md`:
```markdown
- **Reporting page** (`/reporting`): internal self-service report builder (PowerBI replacement, phase 1). Curated **Document Processing** source, table visualization with field picker, filters, combine clients/processes, custom column headers, save/load reports, and Excel export. New `reporting.*` permissions; new `Reports` table; new `openpyxl` dependency.
```

- [ ] **Step 2: How-to doc**

Create `docs/howto/reporting.md` covering: what the page does; the `reporting.*`
permissions and how scope perms mirror `dashboard.filter.process.*`; how to add a
new curated source (register in `nx_lib/reporting/sources.py` + ensure
FieldMetadata/SearchConfig coverage); the report-definition v1 shape; and a note
that the live-SQL source is Phase 2.

- [ ] **Step 3: CLAUDE.md**

In `CLAUDE.md` "Routing" bullet, add `reporting` to the list of route modules.
In "Permissions", note the `reporting.*` family. Add `openpyxl` mention where
dependencies/feature stack are described if applicable.

- [ ] **Step 4: Deploy excludes check**

Confirm no new **top-level** file/dir was added that the running app doesn't need
(all new runtime code is under `nx_lib/`, `templates/`, `static/` — already
mirrored; `docs/`, `sql/`, `tests/` already excluded). No `deploy.yml` change
expected. If anything new sits at top level, add `/XF`/`/XD` entries.

- [ ] **Step 5: Extract translations**

```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
pybabel compile -d translations
```
Then translate new strings in `translations/<de|fr|it>/LC_MESSAGES/messages.po` and recompile.

- [ ] **Step 6: Final full test run + commit**

```bash
python -m pytest tests/unit tests/integration -q
git add CHANGELOG.md docs/howto/reporting.md CLAUDE.md messages.pot translations
git commit -m "docs(reporting): changelog, how-to, CLAUDE.md, translations"
```

---

## Self-Review

**Spec coverage:**
- Data-source registry + field catalog → Tasks 2, 3 ✓
- Query engine (parameterized, whitelisted, combine clients/processes, scope intersection) → Tasks 1, 4, 7 ✓
- Table visualization + filters + sort + custom headers/title → Tasks 4, 9 ✓
- Save & name reports (CRUD) → Tasks 6, 7 ✓
- Excel export → Task 5, 7 ✓
- `reporting.*` separate scope permissions → Tasks 6, 8 ✓
- Document Processing live first → Tasks 2, 7 ✓
- Page + nav + page_visibility + startpage_redirect_to → Tasks 7, 8 ✓
- Migrations (Reports + perms) → Task 6 ✓
- Tests (unit + integration + e2e) → every task ✓
- Docs/changelog/deploy → Task 10 ✓
- **Deferred (Phase 2, correctly absent):** live-SQL sandbox, `engine_*_ro`, `reporting.sql.run`, SQL tab enabled.

**Placeholder scan:** No "TBD/handle errors/etc." — each step has real code or exact commands. The two genuinely environment-dependent items (e2e login fixture name; whether a TEST seed grant is needed) are called out with the exact action to take, not left vague.

**Type consistency:** `build_table_query(rd, process_configs, field_col_maps, *, row_cap)` used consistently (Tasks 4, 7). `validate_report_definition(rd, catalog_fields, filterable_fields, sortable_fields, *, max_row_limit)` consistent (Tasks 1, 7). `rows_to_xlsx(columns, rows, *, title)` consistent (Tasks 5, 7). Catalog dict keys (`field/label/type/aggregable/sortable/filterable/processes`) consistent (Tasks 2, 7, 9). Source descriptor keys (`id/kind/label/permission/engine`) consistent (Tasks 3, 7).

## Phase 2 (separate plan, not built here)
Live read-only SQL source: `engine_*_ro` engines + `DB_REPORTING_RO_*` env vars (Statistics + Octopus, `db_datareader`), `nx_lib/reporting/sandbox.py` (single-SELECT, blocklist, TOP cap, timeout, audit log), `/api/reporting/sql/run`, `reporting.sql.run` permission, and enabling the SQL tab in the builder.
