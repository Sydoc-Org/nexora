# Reporting Relative-Date Tokens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Date filters in report definitions can carry a relative-date token (`{"token": "last_month"}`) that resolves to absolute dates at every run, so saved/scheduled/AI-built reports never go stale.

**Architecture:** A standalone `nx_lib/reporting/tokens.py` owns the frozen vocabulary, validation, and resolution. The schema validator accepts token values (new `date_fields` parameter); resolution to internal half-open `gte`/`lt` pairs happens after validation at the two execution choke points (`_prepare_run` in the views, `execute_definition` in the runner — the scheduler rides the runner unchanged). The Simple wizard presets and a new Advanced preset select emit tokens; AI prompts teach the syntax; `api_run` returns `resolvedDates` so the UI shows what actually ran.

**Tech Stack:** Flask, pytest (unit + integration + Playwright e2e), Jinja2 JS partials, Flask-Babel.

**Spec:** `docs/superpowers/specs/2026-06-10-reporting-relative-date-tokens-design.md`

---

## Repo conventions that apply to every task

- Run `gitnexus_impact({target: "<symbol>", direction: "upstream"})` before editing each named function, and `gitnexus_detect_changes()` before each commit (project CLAUDE.md rules).
- The `sql-migrate-int` pre-commit hook currently always fails on Windows (INT CRLF checksum drift). Commit with `SQL_SYNC_SKIP=1 git commit ...`.
- Test runner: `.venv\Scripts\python.exe -m pytest <path> -v` from `C:\dev\nexora`.
- Jinja templates are cached for the process lifetime — restart the dev server after template edits before browser-verifying.
- e2e prep when running the e2e files: `python scripts/test_db_reset.py` first (stale NEXORA_TEST state fails order-dependent tests).

---

### Task 1: The tokens module

**Files:**
- Create: `nx_lib/reporting/tokens.py`
- Create: `tests/unit/test_reporting_tokens.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_reporting_tokens.py`:

```python
"""Unit tests for nx_lib.reporting.tokens — relative-date token resolution."""

import datetime

import pytest

from nx_lib.reporting.tokens import (
    RELATIVE_DATE_TOKENS,
    date_fields_from_catalog,
    resolve_definition_tokens,
    resolve_token,
    validate_token_value,
)

# A Wednesday. ISO week = Mon 2026-06-08 .. Sun 2026-06-14.
TODAY = datetime.date(2026, 6, 10)


def _d(s):
    return datetime.date.fromisoformat(s)


@pytest.mark.parametrize(
    ("token", "start", "end"),
    [
        ("today", "2026-06-10", "2026-06-10"),
        ("yesterday", "2026-06-09", "2026-06-09"),
        ("this_week", "2026-06-08", "2026-06-14"),
        ("last_week", "2026-06-01", "2026-06-07"),
        ("this_month", "2026-06-01", "2026-06-30"),
        ("last_month", "2026-05-01", "2026-05-31"),
        ("this_year", "2026-01-01", "2026-12-31"),
        ("last_year", "2025-01-01", "2025-12-31"),
        # 1st of month-2 .. last day of current month (wizard preset semantics)
        ("last_3_months", "2026-04-01", "2026-06-30"),
    ],
)
def test_fixed_token_resolution(token, start, end):
    assert resolve_token({"token": token}, TODAY) == (_d(start), _d(end))


def test_last_n_days_is_a_rolling_inclusive_window():
    assert resolve_token({"token": "last_n_days", "n": 1}, TODAY) == (TODAY, TODAY)
    assert resolve_token({"token": "last_n_days", "n": 30}, TODAY) == (
        _d("2026-05-12"),
        TODAY,
    )


def test_month_edges_resolve_correctly():
    # Jan: last_month crosses the year boundary.
    assert resolve_token({"token": "last_month"}, _d("2026-01-15")) == (
        _d("2025-12-01"),
        _d("2025-12-31"),
    )
    # March in a leap year: last_month is a 29-day February.
    assert resolve_token({"token": "last_month"}, _d("2028-03-31")) == (
        _d("2028-02-01"),
        _d("2028-02-29"),
    )
    # Week range never depends on DATEFIRST: Monday anchor from a Sunday.
    assert resolve_token({"token": "this_week"}, _d("2026-06-14")) == (
        _d("2026-06-08"),
        _d("2026-06-14"),
    )


def test_validate_token_value_matrix():
    assert validate_token_value({"token": "last_month"}) is None
    assert validate_token_value({"token": "last_n_days", "n": 30}) is None
    assert "unknown" in validate_token_value({"token": "last_fortnight"})
    assert validate_token_value("last_month") is not None          # not an object
    assert validate_token_value({"token": "last_n_days"}) is not None        # n missing
    assert validate_token_value({"token": "last_n_days", "n": 0}) is not None
    assert validate_token_value({"token": "last_n_days", "n": 367}) is not None
    assert validate_token_value({"token": "last_n_days", "n": "30"}) is not None
    assert validate_token_value({"token": "last_n_days", "n": True}) is not None
    assert validate_token_value({"token": "last_month", "n": 3}) is not None  # stray n
    assert validate_token_value({"token": "last_month", "x": 1}) is not None  # stray key


def test_unknown_token_error_lists_vocabulary():
    msg = validate_token_value({"token": "nope"})
    assert "last_month" in msg and "last_n_days" in msg


def test_resolve_definition_tokens_expands_to_half_open_pair():
    rd = {
        "filters": [
            {"field": "import_date", "op": "between", "value": {"token": "last_month"}},
            {"field": "doctype", "op": "eq", "value": "Invoice"},
        ]
    }
    out = resolve_definition_tokens(rd, TODAY)
    assert out is not rd  # copy when tokens present
    assert out["filters"] == [
        {"field": "import_date", "op": "gte", "value": "2026-05-01"},
        {"field": "import_date", "op": "lt", "value": "2026-06-01"},  # end + 1 day
        {"field": "doctype", "op": "eq", "value": "Invoice"},
    ]
    # The input definition is untouched (the stored JSON keeps its token).
    assert rd["filters"][0]["value"] == {"token": "last_month"}


def test_resolve_definition_tokens_is_identity_without_tokens():
    rd = {"filters": [{"field": "doctype", "op": "eq", "value": "Invoice"}]}
    assert resolve_definition_tokens(rd, TODAY) is rd
    rd_no_filters = {"columns": []}
    assert resolve_definition_tokens(rd_no_filters, TODAY) is rd_no_filters


def test_resolve_definition_tokens_raises_on_bad_token():
    rd = {"filters": [{"field": "d", "op": "between", "value": {"token": "nope"}}]}
    with pytest.raises(ValueError):
        resolve_definition_tokens(rd, TODAY)


def test_date_fields_from_catalog():
    catalog = [
        {"field": "import_date", "type": "string", "grainable": True},  # docprocessing
        {"field": "created", "type": "date"},                           # table source
        {"field": "modified", "type": "DATETIME"},                      # case-insensitive
        {"field": "doctype", "type": "string"},
    ]
    assert date_fields_from_catalog(catalog) == {"import_date", "created", "modified"}
    assert date_fields_from_catalog(None) == set()


def test_registry_is_the_documented_vocabulary():
    assert set(RELATIVE_DATE_TOKENS) == {
        "today", "yesterday", "this_week", "last_week", "this_month",
        "last_month", "this_year", "last_year", "last_3_months", "last_n_days",
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_tokens.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nx_lib.reporting.tokens'`

- [ ] **Step 3: Implement the module**

Create `nx_lib/reporting/tokens.py`:

```python
"""Relative-date tokens for report definitions.

A date filter's `value` may be {"token": "<name>"} (plus {"n": <int>} for
last_n_days) instead of literal dates. Tokens are validated at save/AI time
(schema.validate_report_definition) and resolved to absolute dates at RUN time
(views._prepare_run / runner.execute_definition), so saved and scheduled
reports never go stale.

Standalone on purpose: stdlib-only imports, so schema.py can import from here
without a cycle. Resolution uses datetime.date.today() (server-local) —
consistent with the AI prompt grounding; users have no stored timezone.
"This"-period tokens cover the FULL calendar period (future days simply match
no data), mirroring the Simple wizard's historical presetRange() semantics.
"""

import calendar
import datetime


def _day(d):
    return d, d


def _month_range(y, m):
    return datetime.date(y, m, 1), datetime.date(y, m, calendar.monthrange(y, m)[1])


def _month_start(d, delta):
    """First day of the month `delta` months from d's month."""
    total = d.year * 12 + (d.month - 1) + delta
    return datetime.date(total // 12, total % 12 + 1, 1)


def _week_of(d):
    start = d - datetime.timedelta(days=d.weekday())  # ISO Monday
    return start, start + datetime.timedelta(days=6)


# Frozen vocabulary: name -> resolver(today) -> (start_date, end_date), inclusive.
# last_n_days is parameterized and handled explicitly in resolve_token.
RELATIVE_DATE_TOKENS = {
    "today": _day,
    "yesterday": lambda t: _day(t - datetime.timedelta(days=1)),
    "this_week": _week_of,
    "last_week": lambda t: _week_of(t - datetime.timedelta(days=7)),
    "this_month": lambda t: _month_range(t.year, t.month),
    "last_month": lambda t: _month_range(_month_start(t, -1).year, _month_start(t, -1).month),
    "this_year": lambda t: (datetime.date(t.year, 1, 1), datetime.date(t.year, 12, 31)),
    "last_year": lambda t: (datetime.date(t.year - 1, 1, 1), datetime.date(t.year - 1, 12, 31)),
    "last_3_months": lambda t: (_month_start(t, -2), _month_range(t.year, t.month)[1]),
    "last_n_days": None,
}

_N_MIN, _N_MAX = 1, 366


def validate_token_value(value):
    """Error message if `value` is not a well-formed token object, else None."""
    if not isinstance(value, dict):
        return "relative-date value must be an object like {\"token\": \"last_month\"}"
    token = value.get("token")
    if token not in RELATIVE_DATE_TOKENS:
        allowed = ", ".join(sorted(RELATIVE_DATE_TOKENS))
        return f"unknown relative-date token: {token!r} (allowed: {allowed})"
    extra = set(value) - {"token", "n"}
    if extra:
        return f"unexpected keys in relative-date value: {sorted(extra)}"
    n = value.get("n")
    if token == "last_n_days":
        if isinstance(n, bool) or not isinstance(n, int) or not _N_MIN <= n <= _N_MAX:
            return f"last_n_days requires an integer n in [{_N_MIN}, {_N_MAX}]"
    elif n is not None:
        return f"token {token!r} takes no 'n'"
    return None


def resolve_token(value, today=None):
    """Inclusive (start_date, end_date) for one token value.

    Raises ValueError on a malformed value (callers normally validate first;
    this is the safety net for stale saved JSON).
    """
    err = validate_token_value(value)
    if err:
        raise ValueError(err)
    today = today or datetime.date.today()
    if value["token"] == "last_n_days":
        return today - datetime.timedelta(days=value["n"] - 1), today
    return RELATIVE_DATE_TOKENS[value["token"]](today)


def resolve_definition_tokens(rd, today=None):
    """Replace token-valued filters with absolute half-open date pairs.

    Returns `rd` unchanged (same object identity) when no filter carries a
    token; otherwise returns a shallow copy whose token filters each become two
    literal clauses: field >= start AND field < end+1day. Half-open beats a
    resolved `between` because a datetime column would silently lose the end
    day's intraday rows. The op on a token filter is ignored (the validator
    only admits tokens with op 'between'). Raises ValueError on a bad token.
    """
    filters = (rd or {}).get("filters") or []
    if not any(isinstance(f, dict) and isinstance(f.get("value"), dict) for f in filters):
        return rd
    new_filters = []
    for f in filters:
        if not (isinstance(f, dict) and isinstance(f.get("value"), dict)):
            new_filters.append(f)
            continue
        start, end = resolve_token(f["value"], today)
        end_excl = end + datetime.timedelta(days=1)
        new_filters.append({"field": f["field"], "op": "gte", "value": start.isoformat()})
        new_filters.append({"field": f["field"], "op": "lt", "value": end_excl.isoformat()})
    out = dict(rd)
    out["filters"] = new_filters
    return out


def date_fields_from_catalog(catalog):
    """Field keys that may carry a relative-date token: grainable (the
    docprocessing date fields) or date/datetime-typed (table sources)."""
    return {
        f["field"]
        for f in catalog or []
        if f.get("grainable") or str(f.get("type", "")).lower() in ("date", "datetime")
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_tokens.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/tokens.py tests/unit/test_reporting_tokens.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): relative-date token module"
```

---

### Task 2: Validator accepts tokens; coercion normalizes them

**Files:**
- Modify: `nx_lib/reporting/schema.py:46-124` (`validate_report_definition`), `:232-239` (filters loop in `coerce_definition`), module imports
- Test: `tests/unit/test_reporting_schema.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_reporting_schema.py` (uses the existing `_valid_def` / `CATALOG_FIELDS` / `FILTERABLE` / `SORTABLE` constants at the top of the file):

```python
DATE_FIELDS = {"date"}


def _token_def(value, field="date", op="between"):
    d = _valid_def()
    d["filters"] = [{"field": field, "op": op, "value": value}]
    return d


def test_token_filter_accepted_on_date_field():
    validate_report_definition(
        _token_def({"token": "last_month"}),
        CATALOG_FIELDS, FILTERABLE, SORTABLE,
        max_row_limit=50000, date_fields=DATE_FIELDS,
    )
    validate_report_definition(
        _token_def({"token": "last_n_days", "n": 30}),
        CATALOG_FIELDS, FILTERABLE, SORTABLE,
        max_row_limit=50000, date_fields=DATE_FIELDS,
    )


def test_token_filter_rejected_on_non_date_field():
    with pytest.raises(ReportDefinitionError, match="relative dates"):
        validate_report_definition(
            _token_def({"token": "last_month"}, field="status"),
            CATALOG_FIELDS, FILTERABLE, SORTABLE,
            max_row_limit=50000, date_fields=DATE_FIELDS,
        )


def test_token_filter_rejected_without_date_fields_param():
    # Default date_fields is empty: callers must opt fields in explicitly.
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(
            _token_def({"token": "last_month"}),
            CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000,
        )


def test_token_filter_rejected_with_non_between_op():
    with pytest.raises(ReportDefinitionError, match="between"):
        validate_report_definition(
            _token_def({"token": "last_month"}, op="eq"),
            CATALOG_FIELDS, FILTERABLE, SORTABLE,
            max_row_limit=50000, date_fields=DATE_FIELDS,
        )


def test_unknown_token_rejected_with_vocabulary_in_message():
    with pytest.raises(ReportDefinitionError, match="last_fortnight"):
        validate_report_definition(
            _token_def({"token": "last_fortnight"}),
            CATALOG_FIELDS, FILTERABLE, SORTABLE,
            max_row_limit=50000, date_fields=DATE_FIELDS,
        )


def test_coerce_normalizes_token_case_and_numeric_n():
    catalog = [{"field": "date", "label": "Date"}]
    rd = {
        "filters": [
            {"field": "date", "op": "between", "value": {"token": "Last_Month"}},
            {"field": "date", "op": "between", "value": {"token": "last_n_days", "n": "30"}},
        ]
    }
    coerce_definition(rd, catalog)
    assert rd["filters"][0]["value"]["token"] == "last_month"
    assert rd["filters"][1]["value"]["n"] == 30
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_schema.py -v -k "token or coerce_normalizes"`
Expected: FAIL — `TypeError: validate_report_definition() got an unexpected keyword argument 'date_fields'` (and the coerce test fails on the un-normalized token).

- [ ] **Step 3: Implement the validator branch**

In `nx_lib/reporting/schema.py`, add the import at the top of the module (after the docstring, before `REPORT_SCHEMA_VERSION`):

```python
from .tokens import RELATIVE_DATE_TOKENS, validate_token_value
```

Add the keyword parameter to `validate_report_definition` (line 46-55) — the signature becomes:

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
    date_fields=frozenset(),
):
```

In the filter loop, replace the value-checking block (lines 117-124):

```python
        if FILTER_OPS[op]:
            value = f.get("value")
            if value is None:
                raise ReportDefinitionError(f"filter op {op!r} requires a value")
            if op == "between" and (not isinstance(value, list) or len(value) != 2):
                raise ReportDefinitionError("between value must be a 2-element list")
            if op in ("in", "not_in") and not isinstance(value, list):
                raise ReportDefinitionError(f"filter op {op!r} value must be a list")
```

with:

```python
        if FILTER_OPS[op]:
            value = f.get("value")
            if value is None:
                raise ReportDefinitionError(f"filter op {op!r} requires a value")
            if isinstance(value, dict):
                # Relative-date token: resolved to absolute dates at run time
                # (nx_lib.reporting.tokens). Only date fields, only 'between'.
                if op != "between":
                    raise ReportDefinitionError(
                        f"a relative-date value requires op 'between', got {op!r}"
                    )
                if f.get("field") not in date_fields:
                    raise ReportDefinitionError(
                        f"field does not accept relative dates: {f.get('field')!r}"
                    )
                err = validate_token_value(value)
                if err:
                    raise ReportDefinitionError(err)
                continue
            if op == "between" and (not isinstance(value, list) or len(value) != 2):
                raise ReportDefinitionError("between value must be a 2-element list")
            if op in ("in", "not_in") and not isinstance(value, list):
                raise ReportDefinitionError(f"filter op {op!r} value must be a list")
```

In `coerce_definition`, extend the filters loop (lines 232-239) — after the `op` normalization, add:

```python
            value = spec.get("value")
            if isinstance(value, dict) and isinstance(value.get("token"), str):
                tok = value["token"].strip().lower()
                if tok in RELATIVE_DATE_TOKENS:
                    value["token"] = tok
                n = value.get("n")
                if isinstance(n, str) and n.strip().isdigit():
                    value["n"] = int(n.strip())
```

- [ ] **Step 4: Run the full schema test file**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_schema.py -v`
Expected: ALL PASS (pre-existing tests don't pass `date_fields`, so the default `frozenset()` keeps them green).

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/schema.py tests/unit/test_reporting_schema.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): validate relative-date tokens in definitions"
```

---

### Task 3: Query builders reject unresolved tokens (defense in depth)

**Files:**
- Modify: `nx_lib/reporting/query.py:123-127` (`_filter_clause`), `nx_lib/reporting/table_query.py:63-73` (`_build_conditions`)
- Test: `tests/unit/test_reporting_query.py`, `tests/unit/test_reporting_table_query.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_reporting_query.py`:

```python
def test_filter_clause_rejects_unresolved_token_value():
    from nx_lib.reporting.query import QueryBuildError, _filter_clause

    with pytest.raises(QueryBuildError, match="unresolved"):
        _filter_clause("[d]", "between", {"token": "last_month"}, [])
```

Append to `tests/unit/test_reporting_table_query.py`:

```python
def test_build_conditions_rejects_unresolved_token_value():
    from nx_lib.reporting.table_query import TableQueryError, _build_conditions

    rd = {"filters": [{"field": "d", "op": "between", "value": {"token": "last_month"}}]}
    with pytest.raises(TableQueryError, match="unresolved"):
        _build_conditions(rd, {"d": {"field": "d"}})
```

(Both files already import `pytest`; if not at the top of either file, add `import pytest`.)

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_query.py tests\unit\test_reporting_table_query.py -v -k unresolved`
Expected: FAIL — both currently treat the dict as a literal (the query one raises the wrong error: "between requires a 2-element list" is NOT raised because a dict isn't a list... it is raised, but without "unresolved" in the message; the match fails either way).

- [ ] **Step 3: Implement the guards**

In `nx_lib/reporting/query.py` `_filter_clause` (line 123), add right after the `if op not in _OP_SQL and op not in _SPECIAL_OPS:` check:

```python
    if isinstance(value, dict):
        # A relative-date token reached the SQL layer: resolve_definition_tokens
        # (nx_lib.reporting.tokens) must run before query building.
        raise QueryBuildError(f"unresolved relative-date value for {col}")
```

In `nx_lib/reporting/table_query.py` `_build_conditions`, after `op, val = f.get("op"), f.get("value")` (line 72), add:

```python
        if isinstance(val, dict):
            raise TableQueryError(f"unresolved relative-date value for {field!r}")
```

- [ ] **Step 4: Run both files to verify everything passes**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_query.py tests\unit\test_reporting_table_query.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/query.py nx_lib/reporting/table_query.py tests/unit/test_reporting_query.py tests/unit/test_reporting_table_query.py
SQL_SYNC_SKIP=1 git commit -m "fix(reporting): query builders reject unresolved token values"
```

---

### Task 4: Resolution at the execution choke points + `resolvedDates` metadata

**Files:**
- Modify: `nx_lib/views/reporting.py` — imports (~line 70), `_validate_definition_for_user` (431-439), `_prepare_run` (713-800), `api_run` (913-941); two new helpers
- Modify: `nx_lib/reporting/runner.py` — imports (14-23), `execute_definition` (89-97 and 125-132)
- Test: `tests/unit/test_reporting_runner.py`, `tests/unit/test_reporting_tokens.py`

- [ ] **Step 1: Write the failing runner test**

Append to `tests/unit/test_reporting_runner.py` (reuses the module's `FAKE_CATALOG`, `OWNER_PERMS`, `_definition`, `_patch_view_internals`; add `import datetime` to the file imports):

```python
def test_scheduled_definition_with_relative_token_resolves_at_run_time(monkeypatch):
    from nx_lib.reporting.tokens import resolve_token

    captured = {}
    _patch_view_internals(monkeypatch, captured)
    date_catalog = FAKE_CATALOG + [
        {
            "field": "import_date",
            "label": "Import date",
            "type": "string",
            "grainable": True,
            "filterable": True,
            "sortable": True,
            "aggregable": False,
            "processes": ["acme.inv"],
        }
    ]
    monkeypatch.setattr(
        runner_mod, "fetch_docprocessing_catalog", lambda allowed, loc: date_catalog
    )
    from nx_lib.views import reporting as rv

    monkeypatch.setattr(
        rv,
        "_load_process_configs",
        lambda scope: [
            {
                "process": "acme.inv",
                "table": "dbo.StatA",
                "export_col": None,
                "import_col": "ImportDate",
                "condition": "",
                "workitem_col": "WorkItem",
            }
        ],
    )

    definition = _definition(
        filters=[{"field": "import_date", "op": "between", "value": {"token": "last_month"}}]
    )
    runner_mod.execute_definition(definition, OWNER_PERMS, 1, "tester", "en")

    start, end = resolve_token({"token": "last_month"})
    end_excl = end + datetime.timedelta(days=1)
    assert ">= ?" in captured["sql"] and "< ?" in captured["sql"]
    assert "BETWEEN" not in captured["sql"]
    assert captured["params"] == [start.isoformat(), end_excl.isoformat()]
    # The caller's saved definition object still carries the token.
    assert definition["filters"][0]["value"] == {"token": "last_month"}
```

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_runner.py -v -k relative_token`
Expected: FAIL — `ReportDefinitionError: field does not accept relative dates: 'import_date'` (the runner doesn't pass `date_fields` yet).

- [ ] **Step 2: Wire the runner**

In `nx_lib/reporting/runner.py`, extend the schema import block (lines 16-20):

```python
from .schema import (
    ReportDefinitionError,
    validate_report_definition,
    validate_sql_definition,
)
from .tokens import date_fields_from_catalog, resolve_definition_tokens
```

In the **docprocessing branch** of `execute_definition`, add `date_fields` to the validator call (after `grainable_fields=grainable,` at line 96):

```python
            grainable_fields=grainable,
            date_fields=date_fields_from_catalog(catalog),
```

and immediately after that `validate_report_definition(...)` call, add:

```python
        try:
            definition = resolve_definition_tokens(definition)
        except ValueError as e:
            raise ReportDefinitionError(str(e))
```

In the **table branch**, add to its validator call (after `metric_codes=set(source_metrics),` at line 131):

```python
            metric_codes=set(source_metrics),
            date_fields=date_fields_from_catalog(catalog),
```

and the same `resolve_definition_tokens` try/except right after it.

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_runner.py -v`
Expected: ALL PASS

- [ ] **Step 3: Write the failing views-glue tests**

Append to `tests/unit/test_reporting_tokens.py`:

```python
def test_resolved_dates_meta_lists_token_filters_only():
    from nx_lib.views import reporting as rv

    rd = {
        "filters": [
            {"field": "import_date", "op": "between", "value": {"token": "last_month"}},
            {"field": "import_date", "op": "between", "value": {"token": "last_n_days", "n": 7}},
            {"field": "doctype", "op": "eq", "value": "Invoice"},
        ]
    }
    meta = rv._resolved_dates_meta(rd)
    assert [m["token"] for m in meta] == ["last_month", "last_n_days"]
    assert meta[0]["field"] == "import_date"
    assert meta[1]["n"] == 7
    start, end = resolve_token({"token": "last_month"})
    assert meta[0]["start"] == start.isoformat()
    assert meta[0]["end"] == end.isoformat()
    assert rv._resolved_dates_meta({"filters": []}) == []
```

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_tokens.py -v -k resolved_dates_meta`
Expected: FAIL — `AttributeError: module ... has no attribute '_resolved_dates_meta'`

- [ ] **Step 4: Wire the views**

In `nx_lib/views/reporting.py`, add after the `..reporting.sources` import block (~line 75):

```python
from ..reporting.tokens import (
    date_fields_from_catalog,
    resolve_definition_tokens,
    resolve_token,
)
```

Add two helpers directly above `_prepare_run` (line 713):

```python
def _resolve_definition_tokens_or_error(rd):
    """Token -> absolute dates at run time. A malformed token cannot pass the
    validator, but saved JSON is not immutable — surface it as a definition
    error (HTTP 400), never a 500."""
    try:
        return resolve_definition_tokens(rd)
    except ValueError as e:
        raise ReportDefinitionError(str(e))


def _resolved_dates_meta(rd):
    """[{field, token, n?, start, end}] for each token filter (inclusive display
    range) — the run response's transparency metadata."""
    out = []
    for f in rd.get("filters") or []:
        value = f.get("value")
        if not isinstance(value, dict):
            continue
        try:
            start, end = resolve_token(value)
        except ValueError:
            continue
        item = {
            "field": f.get("field"),
            "token": value.get("token"),
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        if value.get("n") is not None:
            item["n"] = value["n"]
        out.append(item)
    return out
```

In `_prepare_run`'s **docprocessing branch**, extend the validator call (line 744) and resolve right after it:

```python
            grainable_fields=grainable,
            date_fields=date_fields_from_catalog(catalog),
        )
        rd = _resolve_definition_tokens_or_error(rd)
```

In `_prepare_run`'s **table branch**, extend its validator call (line 777) and resolve right after it:

```python
            metric_codes=set(source_metrics),
            date_fields=date_fields_from_catalog(catalog),
        )
        rd = _resolve_definition_tokens_or_error(rd)
```

In `_validate_definition_for_user`, extend its validator call (after `grainable_fields=grainable,` at line 438):

```python
            grainable_fields=grainable,
            date_fields=date_fields_from_catalog(catalog),
```

In `api_run`, build the response through a variable so the metadata is conditional — replace the closing `return jsonify({...})` (lines 931-941) with:

```python
    payload = {
        "columns": [
            {"field": c["field"], "header": c.get("header") or c["field"]} for c in columns
        ],
        "rows": _rows_json_safe(rows),
        "rowCount": len(rows),
        "truncated": len(rows)
        >= min(int(rd.get("rowLimit", DEFAULT_ROW_LIMIT)), MAX_ROW_LIMIT),
    }
    resolved_dates = _resolved_dates_meta(rd)
    if resolved_dates:
        payload["resolvedDates"] = resolved_dates
    return jsonify(payload)
```

(`rd` here is the request body — `_prepare_run` resolves its own reference, the caller's dict still has the tokens, so `_resolved_dates_meta(rd)` sees them.)

- [ ] **Step 5: Run the unit + integration suites**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_tokens.py tests\unit\test_reporting_runner.py tests\integration\test_reporting_routes.py tests\integration\test_reporting_ai_routes.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add nx_lib/views/reporting.py nx_lib/reporting/runner.py tests/unit/test_reporting_runner.py tests/unit/test_reporting_tokens.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): resolve relative-date tokens at run time"
```

---

### Task 5: Teach the AI surfaces the token syntax

**Files:**
- Modify: `nx_lib/reporting/ai.py:195-234` (`_SYSTEM_DEF`), `:264-282` (`_definition_user_prompt`), `:405-422` (`_AGENT_SYSTEM`)
- Test: `tests/unit/test_reporting_ai_definition.py`, `tests/unit/test_reporting_ai_agentic.py`

- [ ] **Step 1: Write the failing prompt-content tests**

Append to `tests/unit/test_reporting_ai_definition.py`:

```python
def test_system_def_teaches_relative_date_tokens():
    s = ai._SYSTEM_DEF
    assert '{"token": "last_month"}' in s
    assert "last_n_days" in s
    assert "resolved against the CURRENT date" in s
```

Append to `tests/unit/test_reporting_ai_agentic.py`:

```python
def test_agent_system_prompt_teaches_relative_date_tokens():
    s = ai._AGENT_SYSTEM
    assert '"token"' in s
    assert "last_n_days" in s
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py tests\unit\test_reporting_ai_agentic.py -v -k relative_date_tokens`
Expected: FAIL (×2)

- [ ] **Step 3: Extend the prompts**

In `nx_lib/reporting/ai.py`, append to the `_SYSTEM_DEF` string (after the "guessing one." sentence, keeping the implicit-concatenation style):

```python
    ' For RELATIVE time ranges ("last month", "this year", "letzte Woche"),'
    " set the date filter value to a relative-date token object instead of"
    ' literal dates: {"field": "<date key>", "op": "between", "value":'
    ' {"token": "last_month"}}. Valid tokens: today, yesterday, this_week,'
    " last_week, this_month, last_month, this_year, last_year, last_3_months,"
    ' and {"token": "last_n_days", "n": <1-366>}. Token values are resolved'
    " against the CURRENT date on every run, so a saved report stays fresh."
    " Only grainable/date-typed fields accept tokens. For EXPLICIT dates"
    ' ("May 2026", "2026-01-01 to 2026-03-31") keep literal ISO dates.'
```

Append to the `_AGENT_SYSTEM` string (after "include all matches, or none rather than a guess."):

```python
    " For relative time ranges set the date filter value to a token object,"
    ' e.g. {"op": "between", "value": {"token": "last_month"}} (tokens: today,'
    " yesterday, this_week, last_week, this_month, last_month, this_year,"
    ' last_year, last_3_months, last_n_days with "n") — these resolve at run'
    " time; keep literal ISO dates for explicit dates."
```

In `_definition_user_prompt` (line 264), update the date line so it no longer contradicts the token instruction — replace:

```python
        base += (
            f"Today's date is {today}. Resolve relative time expressions "
            '("last month", "this year", "yesterday") against this date, '
            "never against your training data.\n\n"
        )
```

with:

```python
        base += (
            f"Today's date is {today}. For relative time expressions "
            '("last month", "this year", "yesterday") emit a relative-date '
            "token as instructed; resolve explicit dates against this date, "
            "never against your training data.\n\n"
        )
```

- [ ] **Step 4: Run both AI test files**

Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_reporting_ai_definition.py tests\unit\test_reporting_ai_agentic.py -v`
Expected: ALL PASS (the existing `test_ask_definition_includes_today_in_prompt` asserts only the `Today's date is ...` prefix and ordering — both survive the reworded line).

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/ai.py tests/unit/test_reporting_ai_definition.py tests/unit/test_reporting_ai_agentic.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): teach AI prompts relative-date tokens"
```

---

### Task 6: Simple wizard emits tokens; result view shows the resolved range

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` — I18N block (11-46), new helpers above `aiSummaryLine` (~247), `aiSummaryLine` (247-260), `runCurrent` (267-330), `presetRange`/`renderTimeStep` (532-602)
- Test: `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Add the I18N strings and token helpers**

In the `I18N` object (`_reporting_simple_js.html:11-46`), append after `aiNoFilters` (add a trailing comma to it):

```js
    aiNoFilters: {{ _("no filters")|tojson }},
    tokenToday: {{ _("Today")|tojson }},
    tokenYesterday: {{ _("Yesterday")|tojson }},
    thisWeek: {{ _("This week")|tojson }},
    lastWeek: {{ _("Last week")|tojson }},
    lastNDays: {{ _("Last {n} days")|tojson }}
```

Directly above `aiSummaryLine` (~line 247), add:

```js
  // Relative-date tokens (nx_lib/reporting/tokens.py) — humanized labels for
  // chips/summary lines. A token value is {token: '<name>'[, n: <int>]}.
  var TOKEN_LABELS = {
    today: I18N.tokenToday, yesterday: I18N.tokenYesterday,
    this_week: I18N.thisWeek, last_week: I18N.lastWeek,
    this_month: I18N.thisMonth, last_month: I18N.lastMonth,
    last_3_months: I18N.last3Months, this_year: I18N.thisYear,
    last_year: I18N.lastYear, last_n_days: I18N.lastNDays
  };
  function isTokenValue(v) {
    return !!v && typeof v === 'object' && !Array.isArray(v) && typeof v.token === 'string';
  }
  function tokenLabel(v) {
    var lbl = TOKEN_LABELS[v.token] || v.token;
    return v.token === 'last_n_days' ? lbl.replace('{n}', v.n) : lbl;
  }
```

- [ ] **Step 2: Wizard presets emit tokens**

In `renderTimeStep` (~line 596), replace the preset branch:

```js
        } else {
          var r = presetRange(p[0]);
          state.wiz.range = r ? [isoDate(r[0]), isoDate(r[1])] : null;
        }
```

with:

```js
        } else {
          // Preset = relative-date token: the saved definition stays fresh
          // (resolved server-side on every run). all_time = no filter.
          state.wiz.range = p[0] === 'all_time' ? null : { token: p[0] };
        }
```

Delete the now-unused `presetRange` function (lines 532-540). (`isoDate` stays — the custom flatpickr branch uses it.) `wizardDefinition` (line 624-626) needs **no change**: `value: w.range` now carries either the absolute pair or the token object, and the server validates both.

- [ ] **Step 3: Humanize tokens in the summary line and show the resolved range**

In `aiSummaryLine` (line 251-255), replace the value formatting:

```js
    var fs = (def.filters || []).map(function (f) {
      var v = Array.isArray(f.value) ? f.value.join(' → ')
            : (f.value === null || f.value === undefined ? '' : String(f.value));
      return f.field + ' ' + f.op + (v !== '' ? ' ' + v : '');
    });
```

with:

```js
    var fs = (def.filters || []).map(function (f) {
      var v = isTokenValue(f.value) ? tokenLabel(f.value)
            : Array.isArray(f.value) ? f.value.join(' → ')
            : (f.value === null || f.value === undefined ? '' : String(f.value));
      return f.field + ' ' + f.op + (v !== '' ? ' ' + v : '');
    });
```

In `runCurrent`, directly after `var columns = res.data.columns || [], rows = res.data.rows || [];` (line 308), insert:

```js
    // What the tokens resolved to on THIS run — appended to the transparency
    // line (and shown alone for wizard-built reports), so "Last month" and the
    // concrete dates are both visible, even over an empty result.
    var rdates = res.data.resolvedDates || [];
    if (rdates.length) {
      var resolvedTxt = rdates.map(function (d) {
        return tokenLabel(d) + ' (' + d.start + ' → ' + d.end + ')';
      }).join(' · ');
      var msg = el('rsMsg');
      msg.textContent = msg.hidden || !msg.textContent
        ? resolvedTxt : msg.textContent + ' — ' + resolvedTxt;
      msg.hidden = false;
    }
```

(`tokenLabel(d)` works on the metadata items too — they carry `token` and `n`.)

- [ ] **Step 4: e2e — token round-trips through save/open and shows the resolved range**

Append to `tests/e2e/test_reporting_simple.py`. Deterministic setup: seed a **table source with a date-typed column** by mirroring the admin-seeding `page.evaluate` block of `test_wizard_category_breakdown_to_result_cards` (same file, line 74+ — copy its source/metric seeding verbatim) and extend the seeded source's `columns` array with a date column, e.g. `{field: 'created', label: 'Created', type: 'date', filterable: true, sortable: true}` on a base object whose TEST-db view has such a column (reuse whatever base object that test seeds). Then save a report whose filter is a token on that column (in-page-fetch pattern as in `test_library_groups_and_hides_sql_kind`, line 39-54):

```python
def test_saved_token_report_shows_resolved_range(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    # 1) Seed source (copy from test_wizard_category_breakdown_to_result_cards,
    #    + date column as described above). 2) Save the token report:
    page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          await fetch('/api/reporting/reports', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify({name: 'e2e token report', definition: {
              schemaVersion: 1, source: '<seeded source id>', visualization: 'table',
              title: 'e2e token report',
              columns: [{field: '<a string column of the seeded source>'}],
              filters: [{field: 'created', op: 'between',
                         value: {token: 'last_month'}}],
              sort: [], scope: {clients: [], processes: []}, rowLimit: 100}})
          });
        }"""
    )
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-group-mine").get_by_text("e2e token report").click()
    # The resolved-range line renders even over an empty result (the TEST db
    # may have no matching rows) — that is exactly the point.
    expect(page.get_by_test_id("rs-msg")).to_be_visible()
    expect(page.get_by_test_id("rs-msg")).to_contain_text("Last month")
    expect(page.get_by_test_id("rs-msg")).to_contain_text("→")
```

(`<seeded source id>` / column placeholders: take them 1:1 from the mirrored seeding block — they are existing values in the neighboring test, not new design. If TEST's seeded base object has no date column at all, add one to the seeding view via the wizard test's seeding SQL, or fall back to `source: 'docprocessing'` with the token on `import_date` — that variant only works when TEST has Statconfig rows.)

Run:

```powershell
python scripts/test_db_reset.py
.venv\Scripts\python.exe -m pytest tests\e2e\test_reporting_simple.py -v
```

Expected: ALL PASS

- [ ] **Step 5: Browser-verify the wizard path** (template cache: restart the server first)

```powershell
.\bin\nx.ps1 -u -b --loginas:ben.streich
```

Open `/reporting` → New report → any measure → Over time → pick "Last month" → Show result. Verify the result renders and `rsMsg` shows `Last month (YYYY-MM-01 → YYYY-MM-31)`. Save it, reopen from the library, verify the same. Screenshot to `var/screenshots/2026-06-10-token-wizard.png`; **if this is a remote session, send it via SendUserFile.**

- [ ] **Step 6: Commit**

```bash
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): simple wizard emits relative-date tokens + resolved-range line"
```

---

### Task 7: Advanced Filters well — relative-date presets

**Files:**
- Modify: `templates/js/_reporting_js.html` — new constant near the top of the IIFE (~line 16), `renderFilters` (623-681)
- Test: `tests/e2e/test_reporting.py`

- [ ] **Step 1: Add the preset constant**

In `templates/js/_reporting_js.html`, after the `state` declaration (line 16), add:

```js
  // Relative-date presets for date-typed filter fields. Value shape
  // {token: '<name>'[, n]} matches nx_lib/reporting/tokens.py; resolved
  // server-side on every run.
  var DATE_TOKEN_PRESETS = [
    ['today', {{ _("Today")|tojson }}],
    ['yesterday', {{ _("Yesterday")|tojson }}],
    ['this_week', {{ _("This week")|tojson }}],
    ['last_week', {{ _("Last week")|tojson }}],
    ['this_month', {{ _("This month")|tojson }}],
    ['last_month', {{ _("Last month")|tojson }}],
    ['last_3_months', {{ _("Last 3 months")|tojson }}],
    ['this_year', {{ _("This year")|tojson }}],
    ['last_year', {{ _("Last year")|tojson }}],
    ['last_n_days', {{ _("Last N days")|tojson }}]
  ];
  var CUSTOM_DATES_LABEL = {{ _("Custom dates…")|tojson }};
```

- [ ] **Step 2: Rework `renderFilters`**

Replace the body of the per-filter loop in `renderFilters` (lines 626-680) with the version below. Changes: the field-meta lookup moves up; date fields get a preset `<select>` before the op; an active token hides the op select and the value input; `renderFilters`'s full re-render makes saved-definition hydration automatic (a token value pre-selects its preset).

```js
    state.filters.forEach(function (f, i) {
      var row = document.createElement('div');
      row.className = 'reporting-filter-row';

      var fld = document.createElement('select');
      state.fields.filter(function (x) {
        return x.filterable && isFieldAvailable(x);
      }).forEach(function (x) {
        var opt = document.createElement('option');
        opt.value = x.field;
        opt.textContent = x.label;
        fld.appendChild(opt);
      });
      fld.value = f.field;
      // Re-render when field changes so flatpickr/presets initialize correctly.
      fld.onchange = function (e) { f.field = e.target.value; f.op = 'eq'; f.value = ''; renderFilters(); };

      var fieldMeta = state.fields.find(function (x) { return x.field === f.field; });
      var isDateField = !!(fieldMeta && (/date/i.test(fieldMeta.type) || fieldMeta.grainable));
      var tokenActive = isDateField && f.value && typeof f.value === 'object'
        && !Array.isArray(f.value) && typeof f.value.token === 'string';

      var preset = null, nInput = null;
      if (isDateField) {
        preset = document.createElement('select');
        var co = document.createElement('option');
        co.value = '';
        co.textContent = CUSTOM_DATES_LABEL;
        preset.appendChild(co);
        DATE_TOKEN_PRESETS.forEach(function (t) {
          var o = document.createElement('option');
          o.value = t[0];
          o.textContent = t[1];
          preset.appendChild(o);
        });
        nInput = document.createElement('input');
        nInput.type = 'number';
        nInput.min = '1';
        nInput.max = '366';
        nInput.hidden = true;
        if (tokenActive) {
          preset.value = f.value.token;
          if (f.value.token === 'last_n_days') {
            nInput.hidden = false;
            nInput.value = f.value.n || 30;
          }
        }
        preset.onchange = function () {
          if (!preset.value) { f.op = 'eq'; f.value = ''; renderFilters(); return; }
          f.op = 'between';   // a token IS a range; the server only admits between
          f.value = preset.value === 'last_n_days'
            ? { token: 'last_n_days', n: parseInt(nInput.value, 10) || 30 }
            : { token: preset.value };
          renderFilters();
        };
        nInput.oninput = function () {
          if (f.value && f.value.token === 'last_n_days') {
            f.value.n = Math.max(1, Math.min(366, parseInt(nInput.value, 10) || 30));
          }
        };
      }

      var op = document.createElement('select');
      ['eq', 'ne', 'contains', 'starts_with', 'gt', 'gte', 'lt', 'lte',
        'is_null', 'is_not_null'].forEach(function (o) {
        var opt = document.createElement('option');
        opt.value = o;
        opt.textContent = o;
        op.appendChild(opt);
      });
      op.value = tokenActive ? 'eq' : f.op;  // display only; hidden when token active
      op.onchange = function (e) { f.op = e.target.value; };
      op.hidden = tokenActive;

      var val = document.createElement('input');
      val.value = (!tokenActive && f.value != null) ? f.value : '';
      val.oninput = function (e) { f.value = e.target.value; };
      val.hidden = tokenActive;

      // Initialize flatpickr for date/datetime fields if the library is present.
      if (!tokenActive && fieldMeta && /date/i.test(fieldMeta.type)
          && typeof flatpickr === 'function') {
        var fpOpts = { allowInput: true, onChange: function (d, s) { f.value = s; } };
        if (/time|datetime/i.test(fieldMeta.type)) {
          fpOpts.enableTime = true;
          fpOpts.dateFormat = 'Y-m-d H:i';
        } else {
          fpOpts.dateFormat = 'Y-m-d';
        }
        flatpickr(val, fpOpts);
      }

      var rm = document.createElement('button');
      rm.textContent = '×';
      rm.onclick = function () { state.filters.splice(i, 1); renderFilters(); };

      row.appendChild(fld);
      if (preset) row.appendChild(preset);
      row.appendChild(op);
      row.appendChild(val);
      if (nInput) row.appendChild(nInput);
      row.appendChild(rm);
      box.appendChild(row);
    });
```

(Note the deliberate behavior change in `fld.onchange`: switching fields now also resets `f.op` to `'eq'` — previously a token-shaped op/value could survive a switch to a non-date field and 400 on run.)

- [ ] **Step 3: e2e — preset round-trips through save/load**

Append to `tests/e2e/test_reporting.py` (same `_login`/fixture style as the file's existing tests; check its top for the exact login helper name and reuse it):

```python
def test_advanced_date_filter_token_preset_round_trips(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    # Save a definition with a token filter via the API, load it into the
    # builder, and assert the preset select hydrates to "Last month".
    rid = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const res = await fetch('/api/reporting/reports', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify({name: 'e2e adv token', definition: {
              schemaVersion: 1, source: 'docprocessing', visualization: 'table',
              title: 'e2e adv token',
              columns: [{field: 'processname'}],
              filters: [{field: 'import_date', op: 'between',
                         value: {token: 'last_month'}}],
              sort: [], scope: {clients: [], processes: []}, rowLimit: 100}})
          });
          return (await res.json()).id;
        }"""
    )
    page.reload()
    # Load the saved report through the UI (saved-reports menu), then check
    # the filter row: preset select shows last_month, op and value are hidden.
    page.get_by_test_id("rp-load-report").click()
    page.get_by_text("e2e adv token").click()
    row = page.locator(".reporting-filter-row").first
    expect(row.locator("select").nth(1)).to_have_value("last_month")
```

(If the saved-reports menu's test ids differ, mirror how the file's existing load test opens a report — the assertion on the filter row is the contract being added.)

Run:

```powershell
python scripts/test_db_reset.py
.venv\Scripts\python.exe -m pytest tests\e2e\test_reporting.py -v
```

Expected: ALL PASS

- [ ] **Step 4: Browser-verify** (restart server first): add a filter on `import_date` in Advanced, pick "Last month", Run — result loads, no 400; save, reload, reopen — preset still selected. Screenshot to `var/screenshots/2026-06-10-token-advanced.png`; **send via SendUserFile if remote.**

- [ ] **Step 5: Commit**

```bash
git add templates/js/_reporting_js.html tests/e2e/test_reporting.py
SQL_SYNC_SKIP=1 git commit -m "feat(reporting): advanced filter presets for relative dates"
```

---

### Task 8: i18n, changelog, docs

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`)
- Modify: `CHANGELOG.md`, `docs/howto/reporting.md`, `docs/design/reporting-ai-assistant.md`

- [ ] **Step 1: Run the Babel cycle** (or invoke the `/nx-i18n` skill, which does the same)

```powershell
.venv\Scripts\pybabel.exe extract -F babel.cfg -o messages.pot .
.venv\Scripts\pybabel.exe update -i messages.pot -d translations
```

- [ ] **Step 2: Translate the new msgids in each `.po`** (some may already exist from other pages — `pybabel update` reuses them; fill only what is new/fuzzy and clear fuzzy markers)

| msgid | de | fr | it |
|---|---|---|---|
| `Today` | `Heute` | `Aujourd'hui` | `Oggi` |
| `Yesterday` | `Gestern` | `Hier` | `Ieri` |
| `This week` | `Diese Woche` | `Cette semaine` | `Questa settimana` |
| `Last week` | `Letzte Woche` | `Semaine dernière` | `Settimana scorsa` |
| `Last {n} days` | `Letzte {n} Tage` | `{n} derniers jours` | `Ultimi {n} giorni` |
| `Last N days` | `Letzte N Tage` | `N derniers jours` | `Ultimi N giorni` |
| `Custom dates…` | `Benutzerdefinierte Daten…` | `Dates personnalisées…` | `Date personalizzate…` |

- [ ] **Step 3: Compile and verify translations are green**

```powershell
.venv\Scripts\pybabel.exe compile -d translations
.venv\Scripts\python.exe -m pytest tests -v -k translations
```

Expected: PASS

- [ ] **Step 4: Changelog** — under `[Unreleased]` in `CHANGELOG.md`:

```markdown
### Added
- Reporting date filters can carry relative-date tokens (`{"token": "last_month"}`, incl. `last_n_days`) that resolve at every run, so saved and scheduled reports never go stale. Wizard presets and a new Advanced preset dropdown emit them; the AI drafts them for relative questions; results show the concrete resolved range.
```

- [ ] **Step 5: Docs**

- `docs/howto/reporting.md`: in the definitions/filters section, document the token value shape, the vocabulary table, full-period semantics, run-time resolution (server-local date), and that the run response carries `resolvedDates`.
- `docs/design/reporting-ai-assistant.md`: note that Surface A/C prompts teach token emission for relative phrasing (egress unchanged — tokens are schema, not data).

- [ ] **Step 6: Full verification run and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests\unit tests\integration -q
```

Expected: ALL PASS.

```bash
git add messages.pot translations CHANGELOG.md docs/howto/reporting.md docs/design/reporting-ai-assistant.md
SQL_SYNC_SKIP=1 git commit -m "docs(reporting): i18n + docs for relative-date tokens"
```
