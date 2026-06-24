# Reporting Semantic Layer — Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add canonical, reusable **metrics** (named server-side aggregations) to the reporting engine so the builder and the AI produce the same, blessed numbers.

**Architecture:** Approach A from the spec — extend the existing report definition with an optional `metrics` list. When present, the existing `columns` become the GROUP BY dimensions, and a new pure `nx_lib/reporting/semantic.py` resolves canonical metric codes into `AGG(col) AS [code]` expressions; both existing query builders gain an aggregate branch that reuses their current whitelist + parameterized-value security boundary. Metrics live in a new DB table `dbo.ReportingMetrics`, curated through a `/reporting/metrics` admin page. Empty/absent `metrics` → today's row-projection path, unchanged.

**Tech Stack:** Python 3 / Flask, SQLAlchemy + pyodbc, SQL Server (T-SQL), Jinja2, Flask-Babel, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-06-08-reporting-semantic-layer-design.md`

**Conventions for every task below:**
- Tests run with the project venv: `\.venv\Scripts\python.exe -m pytest <path> -v` (PowerShell) — the repo's `pyproject.toml` injects coverage flags automatically; do not add `-p no:cov`.
- Commits on `feature/2.5.63`. The pre-commit hook runs `db-migrate --env INT` + `sync-from-db --check`; on this Windows box use `SQL_SYNC_SKIP=1 git commit ...` (known INT CRLF-checksum drift; not a real SQL error). Never `--no-verify`.
- One scope decision carried from the spec: **per-metric locked filters (`FilterJson`) are stored in the table but NOT applied by the engine or exposed in the admin form in Slice 1** — they move to Slice 3. Report-level `filters` still apply pre-aggregation (already works). This keeps Slice 1's engine change minimal.

---

### Task 1: Migration `0017` — `dbo.ReportingMetrics` + permission + seeds

**Files:**
- Create: `sql/_migrations/NexoraDB/0017_create_reporting_metrics.sql`

- [ ] **Step 1: Write the migration**

```sql
-- 0017_create_reporting_metrics.sql
-- Reporting semantic layer (Slice 1): canonical metrics. A metric is a named
-- server-side aggregation (Aggregation over BaseField) bound to a registered
-- source (ReportingSources.Code or a code-default source id). Used in a report
-- definition's `metrics` list; the existing `columns` become the GROUP BY.
-- Curated via the /reporting/metrics admin page, gated reporting.semantic.admin.
-- FilterJson is reserved for a later slice (stored, not yet applied).

IF OBJECT_ID(N'dbo.ReportingMetrics', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportingMetrics (
        MetricID     INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ReportingMetrics PRIMARY KEY,
        Code         NVARCHAR(64) NOT NULL CONSTRAINT UQ_ReportingMetrics_Code UNIQUE,
        SourceId     NVARCHAR(64) NOT NULL,             -- ReportingSources.Code / code-default id
        Label        NVARCHAR(120) NOT NULL,
        Aggregation  NVARCHAR(16) NOT NULL,             -- count|count_distinct|sum|avg|min|max
        BaseField    NVARCHAR(128) NULL,                -- source column key; NULL only for count
        FilterJson   NVARCHAR(MAX) NULL,                -- reserved (Slice 3); not yet applied
        Description  NVARCHAR(512) NULL,
        Format       NVARCHAR(16) NULL,                 -- int|decimal|percent (display hint)
        Enabled      BIT NOT NULL CONSTRAINT DF_ReportingMetrics_Enabled DEFAULT 1,
        SortOrder    INT NOT NULL CONSTRAINT DF_ReportingMetrics_SortOrder DEFAULT 100,
        CreatedAt    DATETIME2 NOT NULL CONSTRAINT DF_ReportingMetrics_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt    DATETIME2 NOT NULL CONSTRAINT DF_ReportingMetrics_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_ReportingMetrics_Aggregation
            CHECK (Aggregation IN ('count','count_distinct','sum','avg','min','max'))
    );
END;
GO

-- Admin permission for the metrics-registry UI/endpoints, granted to every
-- profile that already grants admin.view ('A'). Idempotent.
INSERT INTO dbo.Permission (Code, Description)
SELECT 'reporting.semantic.admin', 'Reporting: manage the canonical metrics registry'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'reporting.semantic.admin');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'reporting.semantic.admin'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO

-- Worked example over the docprocessing source (always present). Idempotent.
INSERT INTO dbo.ReportingMetrics (Code, SourceId, Label, Aggregation, BaseField, Description, Format, SortOrder)
SELECT 'doc_count', 'docprocessing', 'Document count', 'count', NULL,
       'Number of documents (rows) in scope', 'int', 10
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics WHERE Code = 'doc_count');
GO
```

- [ ] **Step 2: Apply to INT + confirm**

Run: `\.venv\Scripts\python.exe scripts\db-migrate.py --env INT --db NexoraDB`
Expected: applies `0017`, records it in `dbo.SchemaMigrations`, no drift error. (If it reports prior-file checksum drift, that's the known INT CRLF issue on files 0001–0003 — re-bless per `docs/howto/db-migrations.md`; do not edit applied migrations.)

- [ ] **Step 3: Verify the per-object dump regenerated**

Run: `\.venv\Scripts\python.exe sql\sync-from-db.py` then `git status --short sql/NexoraDB/`
Expected: a new `sql/NexoraDB/Tables/dbo.ReportingMetrics.sql` appears.

- [ ] **Step 4: Commit**

```bash
git add sql/_migrations/NexoraDB/0017_create_reporting_metrics.sql sql/NexoraDB/
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): ReportingMetrics table + reporting.semantic.admin (Slice 1)"
```

---

### Task 2: `semantic.py` — `resolve_metrics`

**Files:**
- Create: `nx_lib/reporting/semantic.py`
- Test: `tests/unit/test_reporting_semantic.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_reporting_semantic.py
"""Unit tests for nx_lib.reporting.semantic (pure: resolver + aggregate SQL)."""

import pytest

from nx_lib.reporting.semantic import (
    MetricResolveError,
    resolve_metrics,
)

REGISTRY = {
    "doc_count": {"aggregation": "count", "base_field": None},
    "pages_sum": {"aggregation": "sum", "base_field": "pages"},
    "type_distinct": {"aggregation": "count_distinct", "base_field": "doctype"},
}
CATALOG = {"doctype", "status", "pages"}


def test_resolve_count_ignores_base_field():
    out = resolve_metrics([{"metric": "doc_count"}], REGISTRY, CATALOG)
    assert out == [{"code": "doc_count", "aggregation": "count", "base_field": None}]


def test_resolve_sum_requires_base_field_in_catalog():
    out = resolve_metrics([{"metric": "pages_sum"}], REGISTRY, CATALOG)
    assert out == [{"code": "pages_sum", "aggregation": "sum", "base_field": "pages"}]


def test_resolve_unknown_metric_raises():
    with pytest.raises(MetricResolveError):
        resolve_metrics([{"metric": "nope"}], REGISTRY, CATALOG)


def test_resolve_base_field_not_in_catalog_raises():
    reg = {"bad": {"aggregation": "sum", "base_field": "secret_col"}}
    with pytest.raises(MetricResolveError):
        resolve_metrics([{"metric": "bad"}], reg, CATALOG)


def test_resolve_duplicate_metric_raises():
    with pytest.raises(MetricResolveError):
        resolve_metrics([{"metric": "doc_count"}, {"metric": "doc_count"}], REGISTRY, CATALOG)


def test_resolve_unsafe_code_raises():
    reg = {"a]b": {"aggregation": "count", "base_field": None}}
    with pytest.raises(MetricResolveError):
        resolve_metrics([{"metric": "a]b"}], reg, CATALOG)
```

- [ ] **Step 2: Run to verify it fails**

Run: `\.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_semantic.py -v`
Expected: FAIL — `ModuleNotFoundError: nx_lib.reporting.semantic`.

- [ ] **Step 3: Write `semantic.py` (resolver only)**

```python
# nx_lib/reporting/semantic.py
"""Resolve canonical metrics into concrete aggregation specs and GROUP BY SQL.

Pure + DB-free: the metric registry rows and the source's whitelisted catalog
are injected, so this is unit-testable without a DB. Security: the aggregated
column and the metric alias are whitelist/identifier-validated; the aggregation
function comes from a fixed enum. This is the same boundary the row builders
(query.py / table_query.py) enforce — only filter *values* are ever parameters.
"""

import re

AGGREGATIONS = {"count", "count_distinct", "sum", "avg", "min", "max"}
_CODE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class MetricResolveError(ValueError):
    """Raised when a report's metrics cannot be resolved safely."""


def resolve_metrics(metric_refs, metric_registry, catalog_fields):
    """Resolve `metric_refs` (rd['metrics'] = [{'metric': code}, ...]).

    metric_registry: {code: {'aggregation', 'base_field'}}.
    catalog_fields: set of the source's whitelisted column keys.
    Returns [{'code', 'aggregation', 'base_field'}] preserving order.
    Raises MetricResolveError on unknown/duplicate/unsafe/whitelist-miss.
    """
    out = []
    seen = set()
    for ref in metric_refs or []:
        if not isinstance(ref, dict):
            raise MetricResolveError("metric ref must be an object")
        code = ref.get("metric")
        if not isinstance(code, str) or not _CODE.match(code):
            raise MetricResolveError(f"unsafe metric code: {code!r}")
        if code in seen:
            raise MetricResolveError(f"duplicate metric: {code!r}")
        spec = metric_registry.get(code)
        if spec is None:
            raise MetricResolveError(f"unknown metric: {code!r}")
        agg = spec.get("aggregation")
        if agg not in AGGREGATIONS:
            raise MetricResolveError(f"unsupported aggregation: {agg!r}")
        base = spec.get("base_field")
        if agg == "count":
            base = None
        elif base not in catalog_fields:
            raise MetricResolveError(f"metric base field not in catalog: {base!r}")
        seen.add(code)
        out.append({"code": code, "aggregation": agg, "base_field": base})
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `\.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_semantic.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/semantic.py tests/unit/test_reporting_semantic.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): semantic.resolve_metrics (Slice 1)"
```

---

### Task 3: `semantic.py` — `metric_select_expr` + `build_aggregate_sql`

**Files:**
- Modify: `nx_lib/reporting/semantic.py`
- Test: `tests/unit/test_reporting_semantic.py`

- [ ] **Step 1: Append failing tests**

```python
from nx_lib.reporting.semantic import build_aggregate_sql, metric_select_expr


def _bracket(field):
    return f"[{field}]"


def test_metric_select_expr_count_is_count_star():
    r = {"code": "doc_count", "aggregation": "count", "base_field": None}
    assert metric_select_expr(r, _bracket) == "COUNT(*) AS [doc_count]"


def test_metric_select_expr_sum_and_distinct():
    assert (
        metric_select_expr({"code": "pages_sum", "aggregation": "sum", "base_field": "pages"}, _bracket)
        == "SUM([pages]) AS [pages_sum]"
    )
    assert (
        metric_select_expr(
            {"code": "t_d", "aggregation": "count_distinct", "base_field": "doctype"}, _bracket
        )
        == "COUNT(DISTINCT [doctype]) AS [t_d]"
    )


def test_build_aggregate_sql_groups_by_dims_and_orders_by_metric():
    resolved = [{"code": "doc_count", "aggregation": "count", "base_field": None}]
    sql = build_aggregate_sql(
        inner_from="[Db].[dbo].[T]",
        dim_fields=["status"],
        resolved_metrics=resolved,
        sort=[{"field": "doc_count", "dir": "desc"}],
        cap=100,
    )
    assert sql == (
        "SELECT TOP (100) [status], COUNT(*) AS [doc_count] "
        "FROM [Db].[dbo].[T] GROUP BY [status] ORDER BY [doc_count] DESC"
    )


def test_build_aggregate_sql_rejects_sort_field_not_projected():
    with pytest.raises(MetricResolveError):
        build_aggregate_sql(
            inner_from="[T]",
            dim_fields=["status"],
            resolved_metrics=[{"code": "doc_count", "aggregation": "count", "base_field": None}],
            sort=[{"field": "ghost", "dir": "asc"}],
            cap=10,
        )
```

- [ ] **Step 2: Run to verify it fails**

Run: `\.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_semantic.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_aggregate_sql'`.

- [ ] **Step 3: Append to `semantic.py`**

```python
_AGG_SQL = {
    "count_distinct": "COUNT(DISTINCT {})",
    "sum": "SUM({})",
    "avg": "AVG({})",
    "min": "MIN({})",
    "max": "MAX({})",
}
_SORT_DIRS = {"asc": "ASC", "desc": "DESC"}


def metric_select_expr(resolved, col_for_field):
    """Build 'AGG(col) AS [code]'. `col_for_field(field)` returns a safe, already
    bracket-quoted column reference, keeping this provider-agnostic."""
    code = resolved["code"]
    agg = resolved["aggregation"]
    if agg == "count":
        return f"COUNT(*) AS [{code}]"
    return f"{_AGG_SQL[agg].format(col_for_field(resolved['base_field']))} AS [{code}]"


def build_aggregate_sql(*, inner_from, dim_fields, resolved_metrics, sort, cap):
    """Assemble `SELECT TOP(cap) <dims>, <agg exprs> FROM <inner_from>
    GROUP BY <dims> [ORDER BY ...]`.

    `inner_from` is an already-safe FROM body (a bracket-quoted object, or a
    `(<union>) t` subquery). `dim_fields` are whitelisted field keys projected as
    `[field]`; the same alias names back the aggregate columns, so a `col_for_field`
    of `[field]` works for both providers. Sort may target a dim or a metric code;
    anything else raises (defence in depth — the validator should have caught it).
    """
    def bracket(field):
        return f"[{field}]"

    dim_select = ", ".join(bracket(d) for d in dim_fields)
    metric_exprs = ", ".join(metric_select_expr(m, bracket) for m in resolved_metrics)
    select_list = ", ".join(p for p in (dim_select, metric_exprs) if p)
    group_by = ", ".join(bracket(d) for d in dim_fields)
    sql = f"SELECT TOP ({int(cap)}) {select_list} FROM {inner_from} GROUP BY {group_by}"

    projected = set(dim_fields) | {m["code"] for m in resolved_metrics}
    order_parts = []
    for s in sort or []:
        field = s.get("field")
        if field not in projected:
            raise MetricResolveError(f"sort field not projected: {field!r}")
        direction = _SORT_DIRS.get(str(s.get("dir")).lower())
        if direction is None:
            raise MetricResolveError(f"invalid sort dir: {s.get('dir')!r}")
        order_parts.append(f"[{field}] {direction}")
    if order_parts:
        sql += " ORDER BY " + ", ".join(order_parts)
    return sql
```

- [ ] **Step 4: Run to verify it passes**

Run: `\.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_semantic.py -v`
Expected: PASS (10 tests total).

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/semantic.py tests/unit/test_reporting_semantic.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): semantic aggregate-SQL helpers (Slice 1)"
```

---

### Task 4: `schema.py` — validate `metrics`

**Files:**
- Modify: `nx_lib/reporting/schema.py:42-121` (the `validate_report_definition` signature + a new block)
- Test: `tests/unit/test_reporting_schema.py`

- [ ] **Step 1: Add failing tests** (append to the existing file; reuse its `_rd()`/field-set helpers — read the top of the file first to match them)

```python
def test_metrics_unknown_code_rejected():
    from nx_lib.reporting.schema import ReportDefinitionError, validate_report_definition
    rd = _valid_rd(metrics=[{"metric": "ghost"}])
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(
            rd, CATALOG_FIELDS, FILTERABLE, SORTABLE,
            max_row_limit=50000, metric_codes={"doc_count"},
        )


def test_metrics_known_code_accepted():
    from nx_lib.reporting.schema import validate_report_definition
    rd = _valid_rd(metrics=[{"metric": "doc_count"}])
    validate_report_definition(
        rd, CATALOG_FIELDS, FILTERABLE, SORTABLE,
        max_row_limit=50000, metric_codes={"doc_count"},
    )  # no raise


def test_metrics_absent_keeps_row_path_valid():
    from nx_lib.reporting.schema import validate_report_definition
    rd = _valid_rd()  # no metrics key
    validate_report_definition(
        rd, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000,
    )  # no raise; metric_codes defaults empty
```

> If `test_reporting_schema.py` lacks `_valid_rd`/`CATALOG_FIELDS` helpers, add module-level ones mirroring the shape in `validate_report_definition` (a dict with `schemaVersion:1, source, visualization:"table", title, columns:[{field}], rowLimit`).

- [ ] **Step 2: Run to verify failure**

Run: `\.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_schema.py -k metrics -v`
Expected: FAIL — `validate_report_definition() got an unexpected keyword argument 'metric_codes'`.

- [ ] **Step 3: Extend `validate_report_definition`**

Change the signature (line 42-44) to add a keyword-only param:

```python
def validate_report_definition(
    rd, catalog_fields, filterable_fields, sortable_fields, *, max_row_limit,
    metric_codes=frozenset(),
):
```

Insert this block immediately **before** the `row_limit` block (after the `sort` loop, ~line 103):

```python
    metrics = rd.get("metrics")
    if metrics is not None:
        if not isinstance(metrics, list):
            raise ReportDefinitionError("metrics must be a list")
        seen_metrics = set()
        for m in metrics:
            if not isinstance(m, dict):
                raise ReportDefinitionError("metric must be an object")
            code = m.get("metric")
            if code not in metric_codes:
                raise ReportDefinitionError(f"unknown metric: {code!r}")
            if code in seen_metrics:
                raise ReportDefinitionError(f"duplicate metric: {code!r}")
            seen_metrics.add(code)
```

Update the module docstring's field list to mention `metrics` (optional).

- [ ] **Step 4: Run to verify pass**

Run: `\.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_schema.py -v`
Expected: PASS (existing + 3 new; existing callers unaffected since `metric_codes` defaults empty and `metrics` absent is a no-op).

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/schema.py tests/unit/test_reporting_schema.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): validate report-definition metrics (Slice 1)"
```

---

### Task 5: `table_query.py` — aggregate branch

**Files:**
- Modify: `nx_lib/reporting/table_query.py:61` (`build_generic_query` gains `resolved_metrics=None`)
- Test: `tests/unit/test_reporting_table_query.py`

- [ ] **Step 1: Add failing test**

```python
def test_generic_aggregate_groups_and_aggregates():
    from nx_lib.reporting.table_query import build_generic_query
    rd = {
        "columns": [{"field": "client"}],
        "filters": [{"field": "client", "op": "eq", "value": "ACME"}],
        "sort": [{"field": "amount_sum", "dir": "desc"}],
    }
    cols = [
        {"field": "client", "type": "string"},
        {"field": "amount", "type": "number"},
    ]
    resolved = [{"code": "amount_sum", "aggregation": "sum", "base_field": "amount"}]
    sql, params = build_generic_query(
        rd, "Db.dbo.Sales", cols, row_cap=100, resolved_metrics=resolved
    )
    assert sql == (
        "SELECT TOP (100) [client], SUM([amount]) AS [amount_sum] "
        "FROM [Db].[dbo].[Sales] WHERE [client] = ? "
        "GROUP BY [client] ORDER BY [amount_sum] DESC"
    )
    assert params == ["ACME"]
```

- [ ] **Step 2: Run to verify failure**

Run: `\.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_table_query.py -k aggregate -v`
Expected: FAIL — `build_generic_query() got an unexpected keyword argument 'resolved_metrics'`.

- [ ] **Step 3: Implement the aggregate branch**

Add the import at the top of `table_query.py`:

```python
from .semantic import build_aggregate_sql
```

Change the signature and add the branch right after the `by_field`/`proj` whitelist block (keep the existing row-projection code as the `else`):

```python
def build_generic_query(rd, base_object, columns, *, row_cap, resolved_metrics=None):
    by_field = {c["field"]: c for c in columns}
    proj = [c.get("field") for c in rd.get("columns", [])]
    select_cols = [_quote_ident(f) for f in proj if f in by_field]
    if not select_cols:
        raise TableQueryError("no valid columns selected")

    # --- WHERE (shared by both the row and aggregate paths) ---
    conds, params = _build_conditions(rd, by_field)  # see Step 3b

    if resolved_metrics:
        dim_fields = [f for f in proj if f in by_field]
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

    # --- existing row-projection path (unchanged) ---
    sql = [f"SELECT TOP ({int(row_cap)}) {', '.join(select_cols)} FROM {_quote_object(base_object)}"]
    if conds:
        sql.append("WHERE " + " AND ".join(conds))
    order = []
    for s in rd.get("sort") or []:
        field = s.get("field")
        if field not in by_field:
            raise TableQueryError(f"unknown sort field: {field!r}")
        order.append(f"{_quote_ident(field)} {'DESC' if s.get('dir') == 'desc' else 'ASC'}")
    if order:
        sql.append("ORDER BY " + ", ".join(order))
    return " ".join(sql), params
```

- [ ] **Step 3b: Extract the WHERE builder** (refactor the existing filter loop into a helper so both paths share it — DRY). Move the current `for f in rd.get("filters")...` body into:

```python
def _build_conditions(rd, by_field):
    """Return (conds, params) for rd['filters'] against the whitelisted catalog.
    Identical semantics to the prior inline loop; values are parameterized."""
    conds, params = [], []
    for f in rd.get("filters") or []:
        field = f.get("field")
        if field not in by_field:
            raise TableQueryError(f"unknown filter field: {field!r}")
        col = _quote_ident(field)
        op, val = f.get("op"), f.get("value")
        if op in _OP_SYMBOLS:
            conds.append(f"{col} {_OP_SYMBOLS[op]} ?"); params.append(val)
        elif op == "contains":
            conds.append(f"{col} LIKE ?"); params.append(f"%{_like_escape(val)}%")
        elif op == "starts_with":
            conds.append(f"{col} LIKE ?"); params.append(f"{_like_escape(val)}%")
        elif op in ("in", "not_in"):
            vals = val if isinstance(val, list) else [val]
            if not vals:
                conds.append("1=0" if op == "in" else "1=1")
            else:
                placeholders = ",".join(["?"] * len(vals))
                conds.append(f"{col} {'IN' if op == 'in' else 'NOT IN'} ({placeholders})")
                params.extend(vals)
        elif op == "between":
            if not isinstance(val, list) or len(val) != 2:
                raise TableQueryError("between requires two values")
            conds.append(f"{col} BETWEEN ? AND ?"); params.extend(val)
        elif op == "is_null":
            conds.append(f"{col} IS NULL")
        elif op == "is_not_null":
            conds.append(f"{col} IS NOT NULL")
        else:
            raise TableQueryError(f"unsupported filter op: {op!r}")
    return conds, params
```

- [ ] **Step 4: Run to verify pass (incl. the existing row tests, which must still pass unchanged)**

Run: `\.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_table_query.py -v`
Expected: PASS (existing + new aggregate test).

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/table_query.py tests/unit/test_reporting_table_query.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): aggregate branch for the table provider (Slice 1)"
```

---

### Task 6: `query.py` — docprocessing aggregate (UNION-wrap)

**Files:**
- Modify: `nx_lib/reporting/query.py:106` (`build_table_query` gains `resolved_metrics=None`)
- Test: `tests/unit/test_reporting_query.py`

- [ ] **Step 1: Add failing test** (reuse the file's `PROCESS_CONFIGS`/`FIELD_COL_MAPS`/`_rd`)

```python
def test_docprocessing_aggregate_wraps_union():
    from nx_lib.reporting.query import build_table_query
    rd = _rd(columns=[{"field": "doctype"}], filters=[], sort=[{"field": "doc_count", "dir": "desc"}])
    resolved = [{"code": "doc_count", "aggregation": "count", "base_field": None}]
    sql, params = build_table_query(
        rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100, resolved_metrics=resolved
    )
    assert sql.startswith("SELECT TOP (100) [doctype], COUNT(*) AS [doc_count] FROM (")
    assert sql.rstrip().endswith("GROUP BY [doctype] ORDER BY [doc_count] DESC")
    assert "UNION ALL" in sql


def test_docprocessing_aggregate_projects_base_field_into_union():
    from nx_lib.reporting.query import build_table_query
    rd = _rd(columns=[{"field": "doctype"}], filters=[], sort=[])
    resolved = [{"code": "pages_sum", "aggregation": "sum", "base_field": "pages"}]
    sql, _ = build_table_query(
        rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=50, resolved_metrics=resolved
    )
    # 'pages' is only mapped in acme.inv → projected there, NULL in acme.hr.
    assert "AS [pages]" in sql
    assert "SUM([pages]) AS [pages_sum]" in sql
```

- [ ] **Step 2: Run to verify failure**

Run: `\.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_query.py -k aggregate -v`
Expected: FAIL — unexpected keyword `resolved_metrics`.

- [ ] **Step 3: Implement the aggregate branch**

Add at the top of `query.py`:

```python
from .semantic import build_aggregate_sql
```

Change the signature to `def build_table_query(rd, process_configs, field_col_maps, *, row_cap, resolved_metrics=None):`. The existing function builds `sub_queries`, `params`, and `columns`. After the `sub_queries` loop and the `if not sub_queries: raise` guard (around line 184-186), replace the final assembly with a branch:

```python
    inner = " UNION ALL ".join(sub_queries)

    if resolved_metrics:
        # Group-by dims are the projected `columns`; the metric base fields were
        # added to the projection below (Step 3b) so the outer query can aggregate
        # them by their inner alias.
        sql = build_aggregate_sql(
            inner_from=f"({inner}) t",
            dim_fields=columns,
            resolved_metrics=resolved_metrics,
            sort=sort,
            cap=cap,
        )
        return sql, params

    out_cols = ", ".join(f"[{c}]" for c in columns)
    sql = f"SELECT TOP ({cap}) {out_cols} FROM ({inner}) t"
    # ... existing ORDER BY block stays for the row path ...
    return sql, params
```

- [ ] **Step 3b: Project metric base fields into the union.** The inner subqueries must also project each metric's base field (so the outer GROUP BY can aggregate `[base_field]`). Where `columns` is computed (line 121), add a projection list that includes base fields when aggregating:

```python
    columns = [c["field"] for c in rd["columns"]]
    metric_base_fields = [
        m["base_field"] for m in (resolved_metrics or []) if m.get("base_field")
    ]
    # Fields to project in each subquery: the group-by dims plus any metric base
    # fields (deduped, order-stable). For the row path this is just `columns`.
    projected_fields = list(dict.fromkeys(columns + metric_base_fields))
```

Then in the per-process loop, iterate `projected_fields` instead of `columns` when building `select_exprs` (a base field absent from a process's colmap projects `NULL AS [field]`, which SUM/AVG ignore — correct). Keep the `processname` special-case. The outer `dim_fields=columns` ensures only the dims are grouped; the extra base-field columns are consumed only by the aggregates.

- [ ] **Step 4: Run to verify pass (existing row tests must still pass)**

Run: `\.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_query.py -v`
Expected: PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/query.py tests/unit/test_reporting_query.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): docprocessing aggregate UNION-wrap (Slice 1)"
```

---

### Task 7: Views — load metrics registry + wire `_prepare_run` + admin CRUD

**Files:**
- Modify: `nx_lib/views/reporting.py` (loader near `_load_db_sources:110`; `_prepare_run:568`; admin endpoints near `:1921`; `register_routes:2039`)
- Test: `tests/integration/test_reporting_metrics_routes.py` (new)

- [ ] **Step 1: Add the registry loader + per-source helper** (near `_load_db_sources`)

```python
def _load_db_metrics():
    """Read dbo.ReportingMetrics as {code: {...}} (best-effort; [] on error)."""
    try:
        conn = engine_nexora_db.raw_connection()
    except Exception as e:
        current_app.logger.warning(f"reporting metrics: registry unavailable: {e}")
        return {}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT Code, SourceId, Label, Aggregation, BaseField, Description, "
            "Format, Enabled, SortOrder FROM dbo.ReportingMetrics WHERE Enabled = 1"
        )
        out = {}
        for r in cur.fetchall():
            out[r.Code] = {
                "code": r.Code, "source_id": r.SourceId, "label": r.Label,
                "aggregation": r.Aggregation, "base_field": r.BaseField,
                "description": r.Description, "format": r.Format,
                "sort_order": r.SortOrder,
            }
        return out
    except Exception as e:
        current_app.logger.warning(f"reporting metrics: registry read failed: {e}")
        return {}
    finally:
        conn.close()


def _metrics_for_source(source_id):
    """Enabled metrics bound to `source_id`, as {code: {aggregation, base_field}}."""
    return {
        code: {"aggregation": m["aggregation"], "base_field": m["base_field"]}
        for code, m in _load_db_metrics().items()
        if m["source_id"] == source_id
    }
```

- [ ] **Step 2: Wire `_prepare_run`.** In both provider branches, after computing `catalog_fields`/`filterable`/`sortable`, pass metric codes to the validator and resolve when present. Add the import `from nx_lib.reporting.semantic import resolve_metrics, MetricResolveError` at the top, and in each branch:

```python
        source_metrics = _metrics_for_source(source["id"])
        validate_report_definition(
            rd, catalog_fields, filterable, sortable,
            max_row_limit=MAX_ROW_LIMIT, metric_codes=set(source_metrics),
        )
        resolved = (
            resolve_metrics(rd.get("metrics"), source_metrics, catalog_fields)
            if rd.get("metrics") else None
        )
```

Pass `resolved_metrics=resolved` into `build_table_query(...)` / `build_generic_query(...)`. When `resolved`, the returned column list is the dims + metric codes:

```python
        out_columns = (
            rd["columns"] + [{"field": m["code"]} for m in resolved] if resolved else rd["columns"]
        )
        return out_columns, sql, params, <engine>
```

Wrap `resolve_metrics` so `MetricResolveError` surfaces as a 400 (it subclasses `ValueError`; the run handler already maps `ReportDefinitionError`/`QueryBuildError` to 400 — add `MetricResolveError` to that `except` tuple).

- [ ] **Step 3: Add the metrics-admin page + CRUD endpoints** mirroring the sources admin (`api_admin_sources_*` at `:1930-2036`). Read those four functions and produce `api_admin_metrics_list/create/update/delete` against `dbo.ReportingMetrics`, plus:

```python
def reporting_metrics_admin():
    return render_template(
        "reporting_metrics.html",
        logged_in_user=session.get("username", "Unknown"),
        fullname=session.get("fullname"),
        pageV=page_visibility(),
    )
```

Add a `_validate_metric_payload(p)` helper: require non-empty `code` (matching `^[A-Za-z_][A-Za-z0-9_]*$`), `sourceId`, `label`, `aggregation in semantic.AGGREGATIONS`; require `baseField` non-empty unless `aggregation == "count"`. List endpoint returns `{rows: [...]}` and the available sources (`[{id,label}]` from `_effective_sources()`) so the form can offer a source dropdown; it also returns, per source, its catalog field keys for a base-field dropdown (reuse `_catalog_fields_for_source(source)` — extract the catalog-building already in `_prepare_run` into a small helper to avoid duplication).

- [ ] **Step 4: Register routes** (in `register_routes`, alongside the sources routes):

```python
    app.add_url_rule("/reporting/metrics", endpoint="reporting_metrics_admin",
                     view_func=reporting_metrics_admin)
    app.add_url_rule("/api/reporting/admin/metrics", endpoint="reporting_admin_metrics_list",
                     view_func=api_admin_metrics_list)
    app.add_url_rule("/api/reporting/admin/metrics", endpoint="reporting_admin_metrics_create",
                     view_func=api_admin_metrics_create, methods=["POST"])
    app.add_url_rule("/api/reporting/admin/metrics/<int:metric_id>",
                     endpoint="reporting_admin_metrics_update",
                     view_func=api_admin_metrics_update, methods=["PUT"])
    app.add_url_rule("/api/reporting/admin/metrics/<int:metric_id>",
                     endpoint="reporting_admin_metrics_delete",
                     view_func=api_admin_metrics_delete, methods=["DELETE"])
    # Expose the caller's accessible metrics to the builder JS:
    app.add_url_rule("/api/reporting/metrics", endpoint="reporting_metrics",
                     view_func=api_metrics)
```

Add `api_metrics()` (gated by `reporting.view`): returns the caller's accessible metrics grouped by source id — `{sourceId: [{code,label,aggregation,baseField,format}]}` — filtered to sources whose permission the caller holds (reuse `accessible(...)`). The builder uses it to populate the Metrics well per selected source.

- [ ] **Step 5: Integration tests** (`tests/integration/test_reporting_metrics_routes.py`) — model them on `tests/integration/test_reporting_routes.py` (read it for the app/client/login fixtures + how it stubs the DB). Cover: (a) `/reporting/metrics` renders for a user with `reporting.semantic.admin`, 403 without; (b) metrics CRUD happy path + `_validate_metric_payload` rejection (400); (c) `/api/reporting/run` with `metrics:[{metric:"doc_count"}]` returns aggregated rows (stub `_metrics_for_source` + `_execute`); (d) a run referencing an unknown metric → 400.

- [ ] **Step 6: Run + commit**

Run: `\.venv\Scripts\python.exe -m pytest tests/integration/test_reporting_metrics_routes.py -v`
Expected: PASS.

```bash
git add nx_lib/views/reporting.py tests/integration/test_reporting_metrics_routes.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): metrics registry loader, run wiring, admin CRUD (Slice 1)"
```

---

### Task 8: `ai_schema.py` — inject the metric catalog

**Files:**
- Modify: `nx_lib/reporting/ai_schema.py` (add a `metrics` block to `serialize_schema` / `serialize_sources_catalog`)
- Test: `tests/unit/test_reporting_ai_schema.py`

- [ ] **Step 1: Add failing test**

```python
def test_serialize_metrics_catalog_lists_blessed_metrics():
    from nx_lib.reporting.ai_schema import serialize_metrics_catalog
    metrics = [
        {"code": "doc_count", "label": "Document count", "aggregation": "count",
         "base_field": None, "source_id": "docprocessing"},
        {"code": "pages_sum", "label": "Total pages", "aggregation": "sum",
         "base_field": "pages", "source_id": "docprocessing"},
    ]
    text = serialize_metrics_catalog(metrics)
    assert "METRIC doc_count" in text
    assert "count(*) on docprocessing" in text
    assert "sum(pages) on docprocessing" in text
```

- [ ] **Step 2: Run to verify failure**

Run: `\.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_ai_schema.py -k metrics -v`
Expected: FAIL — no `serialize_metrics_catalog`.

- [ ] **Step 3: Implement**

```python
def serialize_metrics_catalog(metrics):
    """One line per blessed metric: `METRIC <code> "<label>" = <agg>(<col|*>) on <source>`.
    So Surfaces A/C can reference canonical metrics by code and get consistent numbers."""
    lines = []
    for m in metrics or []:
        col = m.get("base_field") or "*"
        label = f' "{m.get("label")}"' if m.get("label") else ""
        lines.append(
            f"METRIC {m.get('code')}{label} = "
            f"{m.get('aggregation')}({col}) on {m.get('source_id')}"
        )
    return "\n".join(lines)
```

Then call it from `serialize_schema` (add a `metrics=None` kwarg; append the block under a `# Canonical metrics` header when non-empty) and have the view layer pass the caller's accessible metrics in. Keep the char-budget/truncation behaviour consistent with the existing blocks.

- [ ] **Step 4: Run + commit**

Run: `\.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_ai_schema.py -v`
Expected: PASS.

```bash
git add nx_lib/reporting/ai_schema.py tests/unit/test_reporting_ai_schema.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): inject metric catalog into AI schema (Slice 1)"
```

---

### Task 9: Builder UI — Metrics well

**Files:**
- Modify: `templates/reporting.html` (add a Metrics well in `.reporting-wells`)
- Modify: `templates/js/_reporting_js.html` (load `/api/reporting/metrics`, render the well, include selected metrics in the definition, label the group-by)

- [ ] **Step 1: Add the Metrics well markup.** In `reporting.html`, inside `<aside class="reporting-wells">`, add as the first well (before Columns):

```html
      <div class="reporting-well"><h4>{{ _("Metrics") }}</h4>
        <ul id="rpWellMetrics" data-testid="reporting-well-metrics"></ul>
        <button id="rpAddMetric" class="reporting-link" data-testid="reporting-add-metric">+ {{ _("Add metric") }}</button>
        <p id="rpMetricHint" class="reporting-ai-hint" hidden>{{ _("With a metric selected, the Columns above become the grouping.") }}</p>
      </div>
```

- [ ] **Step 2: Wire the JS.** In `_reporting_js.html`: (a) on source change, `fetch('/api/reporting/metrics')` and keep the metrics for the active source; (b) render chosen metrics into `#rpWellMetrics` (a small dropdown of available metric codes + a remove button, mirroring the existing Sort/Filter well widgets already in this file); (c) include `metrics: [{metric: code}, ...]` in the definition object built for `/api/reporting/run`, Save, and Export; (d) toggle `#rpMetricHint` visible when ≥1 metric is selected. Read the existing well-rendering helpers in this file (e.g. how Sort rows are added/removed) and follow the same pattern + `data-testid` conventions.

- [ ] **Step 3: Verify in the browser**

Restart the server (template cache): `& "C:\dev\nexora\bin\nx.ps1" -r`. Then drive Playwright logged in (`/dev/login/ben.streich`): open `/reporting`, pick the docprocessing source, add the `doc_count` metric, pick a Column as the group-by, Run, and confirm aggregated rows render. Screenshot to `var/screenshots/reporting_metrics_*.png`.

- [ ] **Step 4: Commit**

```bash
git add templates/reporting.html templates/js/_reporting_js.html
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): Metrics well in the builder (Slice 1)"
```

---

### Task 10: Admin UI — `/reporting/metrics`

**Files:**
- Create: `templates/reporting_metrics.html`
- Create: `templates/js/_reporting_metrics_js.html`

- [ ] **Step 1: Build the page** mirroring `templates/reporting_sources.html` (read it as the proven pattern): `<body class="nx-app">`, the branded `nx-page-head` (icon `fa-calculator`, title `{{ _("Reporting metrics") }}`, a "Back to Reporting" `nx-btn--secondary` action), then a `reporting-admin` main with a "Registered metrics" table (`Code, Source, Label, Aggregation, Base field, Enabled, Order, actions`) and an "Add metric" form (`Code`, `Source` select, `Label`, `Aggregation` select of the six funcs, `Base field` input/select, `Format` select, `Sort order`, `Enabled`). Gate the page via the route's permission; include `{% include 'js/_reporting_metrics_js.html' %}`.

- [ ] **Step 2: Build the JS** mirroring `templates/js/_reporting_sources_js.html`: `GET /api/reporting/admin/metrics` to populate the table + source dropdown; `POST`/`PUT`/`DELETE` for save/edit/delete; CSRF header from the `<meta name="csrf-token">` like the sources JS. Disable the Base-field input when `Aggregation == "count"`.

- [ ] **Step 3: Verify in the browser** — restart, `/reporting/metrics` as an admin, add a metric, see it listed; 403 as a non-admin. Screenshot to `var/screenshots/reporting_metrics_admin.png`.

- [ ] **Step 4: Commit**

```bash
git add templates/reporting_metrics.html templates/js/_reporting_metrics_js.html
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): /reporting/metrics admin page (Slice 1)"
```

---

### Task 11: i18n — extract / translate / compile

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` + `.mo`

- [ ] **Step 1: Extract + update**

```
\.venv\Scripts\python.exe -m babel.messages.frontend extract -F babel.cfg -o messages.pot .
\.venv\Scripts\python.exe -m babel.messages.frontend update -i messages.pot -d translations
```

- [ ] **Step 2: Translate** every new msgid (`Metrics`, `Add metric`, `With a metric selected…`, `Reporting metrics`, `Aggregation`, `Base field`, `Document count`, etc.) in de/fr/it — fill each empty/`fuzzy` `msgstr` (a `.po` is just text; edit the three files).

- [ ] **Step 3: Compile + gate**

```
\.venv\Scripts\python.exe -m babel.messages.frontend compile -d translations
\.venv\Scripts\python.exe -m pytest tests/unit/test_translations.py -v
```
Expected: PASS (pot in sync; de/fr/it fully translated, non-fuzzy).

- [ ] **Step 4: Commit**

```bash
git add messages.pot translations/
SQL_SYNC_SKIP=1 git commit -m "chore(i18n): translate semantic-layer strings (Slice 1)"
```

---

### Task 12: Docs, CHANGELOG, e2e, full-suite gate

**Files:**
- Modify: `CHANGELOG.md` ([Unreleased] → Added), `docs/howto/reporting.md`, `docs/design/reporting-ai-assistant.md` (§12: mark Slice 1 done), `CLAUDE.md` (reporting permission list: add `reporting.semantic.admin`)
- Create: `tests/e2e/test_reporting_metrics.py`

- [ ] **Step 1: e2e test** mirroring `tests/e2e/test_reporting_sources.py`: log in, open `/reporting/metrics`, add a metric; open `/reporting`, add the metric + a group-by column, Run, assert an aggregated grid renders.

- [ ] **Step 2: Docs.** CHANGELOG Added entry (new table/route/permission/`metrics` definition key). `docs/howto/reporting.md`: document metrics + the admin page + the `reporting.semantic.admin` perm. `docs/design/reporting-ai-assistant.md` §12: flip Slice 1 to done. `CLAUDE.md`: add `reporting.semantic.admin` to the reporting permission family sentence. (No `deploy.yml` change — every new file is a runtime path under `nx_lib/`, `templates/`, `sql/`.)

- [ ] **Step 3: Full backend suite + targeted e2e**

Run: `\.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q`
Expected: all green (incl. the unchanged row-path tests — backward-compat proof).
Run the metrics e2e per `docs/howto/nx.md` (needs the dev server + NEXORA_TEST reset: `\.venv\Scripts\python.exe scripts\test_db_reset.py` first).

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md docs/ CLAUDE.md tests/e2e/test_reporting_metrics.py
SQL_SYNC_SKIP=1 git commit -m "docs+test(reporting): semantic layer Slice 1 docs + e2e"
```

---

## Self-Review

**Spec coverage:** table + permission + seed (T1) ✓; `semantic.py` resolver + aggregate SQL (T2-3) ✓; definition `metrics` validation (T4) ✓; aggregate branch for both providers incl. docprocessing UNION-wrap (T5-6) ✓; views loader + run wiring + admin CRUD + builder metrics API (T7) ✓; AI metric catalog (T8) ✓; builder Metrics well (T9) ✓; `/reporting/metrics` admin page (T10) ✓; i18n (T11) ✓; CHANGELOG/docs/e2e + backward-compat gate (T12) ✓. Spec's `FilterJson` is intentionally stored-but-deferred to Slice 3 (noted up top + in spec §9) — no Slice 1 task, by design.

**Type/name consistency:** `resolve_metrics(metric_refs, metric_registry, catalog_fields)` and `build_aggregate_sql(*, inner_from, dim_fields, resolved_metrics, sort, cap)` are used identically in T5/T6/T7. `metric_codes=` kwarg on `validate_report_definition` matches T4/T7. Registry dict shape `{aggregation, base_field}` is the same in `_metrics_for_source` (T7) and `resolve_metrics` (T2). Builder `metrics:[{metric: code}]` matches the validator/resolver shape.

**Placeholder scan:** no TBD/TODO; the UI/CRUD tasks (T7/T9/T10) reference exact existing files to mirror with the concrete deltas, not "similar to Task N".
