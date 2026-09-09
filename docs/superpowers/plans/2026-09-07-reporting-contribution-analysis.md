# Reporting contribution analysis ("Why did it move?") — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Anchor on **function names and quoted snippets**, never line numbers — re-Grep before every edit.

**Goal:** Make the Simple KPI band's Total delta chip a **Why?** button that opens a drawer decomposing the change vs. the prior window by process and the source's categorical columns, ranked by contribution.

**Architecture:** A Flask-free helper `nx_lib/reporting/contribution.py` (dimension pick, join, fold, shares) plus one new endpoint `POST /api/reporting/contribution` in `nx_lib/views/reporting/run.py` that reuses `_prepare_run`/`_execute` and `shifted_definition_for_comparison` for every query, so grants and scope equal the report's own. The UI is a new `static/js/reporting_contribution.js` module rendering into the existing drill slide-over shell (`#rdPanel`), wired from the Simple KPI band and dashboard whole-report cards; rows click through to `ReportingDrill.open`.

**Tech Stack:** Flask + pyodbc raw cursors, vanilla JS (#191 shim pattern, `window.NX`/`window.RS`), CSS in `static/css/reporting.css`, pytest unit + integration (NEXORA_TEST), Playwright e2e with `page.route` stubs (CI-only).

**Spec:** `docs/superpowers/specs/2026-09-07-reporting-contribution-analysis-design.md` — the Decisions table and §1–§6 are authoritative. One deliberate deviation is recorded as D3 below.

## Global Constraints

- No new permission code, no migration, no env key, no deploy exclude (spec §4, §6).
- Every server query goes through `_prepare_run(rd)` + `_execute(engine, sql, params)` from `nx_lib/views/reporting/_shared.py`; no SQL is built outside `query.py`/`table_query.py`.
- Hand-built URLs in JS go through `API_PREFIX` (use `RS.api(...)` / `NX.apiSafe(...)`); no inline `onclick=` (CSP on PROD; `tests/unit/test_no_inline_event_handlers.py` fails the build).
- Translated strings live in the Jinja shim and are read off `window`; the `.js` file has no `url_for()`.
- Delta colouring is **directional only** (`rp-delta--up` / `--down` / `--flat`), never good/bad.
- Templates are cached for the process lifetime: `nx -r` after every template edit before browser checks.
- Never `--no-verify`. If the SQL pre-commit hooks block on unrelated INT drift, use `SQL_SYNC_SKIP=1 git commit ...`.
- Remote session policy: commit, never push, never open a PR.

---

## Context an engineer needs (read first)

- **Branch / worktree:** plan authored in worktree `.claude/worktrees/plan-reporting-contribution-analysis` on `plan/reporting-contribution-analysis` (from `feat/reporting-contribution-analysis` @ `7a1c6b4d`, itself cut from `origin/main` @ `69dc932d`). Execute there. The main checkout has untracked drawio backups and hook-regenerated INT-drift dumps under `sql/NexoraDB/` — never stage them.
- **Worktree has no secrets or venv:** `env/*.env` are gitignored. Before Task 3: `cp ../../../env/INT.env ../../../env/TEST.env env/` (never commit them). Prepend `C:\dev\nexora\.venv\Scripts` to `PATH` for `pytest`/`python`. Run `python scripts/test_db_reset.py` once before the integration tests.
- **In-flight work — sequencing:** worktree `plan-report-layouts` (`plan/report-layouts`, plan `docs/superpowers/plans/2026-09-07-report-layouts-definitions.md`) modifies `nx_lib/views/reporting/run.py`, `static/css/reporting.css`, `static/js/reporting_simple.js`, `static/js/reporting_dashboard.js`, `templates/js/_reporting_simple_js.html`, `templates/reporting.html`, `templates/_reporting_help.html`, `docs/howto/reporting.md`, `docs/howto/reporting-guide.md`, `CHANGELOG.md`. Our edits to those files are **small and append-only** (a new `add_url_rule` at the end of `register_routes`, a new CSS block at the end of the file, one delegated listener, one `<script>`/`include` line) so whichever branch lands second re-anchors on quoted snippets. No shared function bodies are rewritten.
- **How a Simple run works:** `runCurrent` in `static/js/reporting_simple.js` posts `Object.assign({}, def, { compare: true })` to `/api/reporting/run`; the response's `comparison` block feeds `renderKpiBand(dims, rows, comparison, def, columns)` in `static/js/reporting_simple_result.js`, whose `deltaChipHtml(current, prior, priorStart, priorEnd)` renders the `↑ 40%` chip (`data-testid="rp-delta"`). The current definition is `RS.state.current.def`; the source catalog with its `fields` list is `RS.state.sources.find(s => s.id === def.source)`.
- **Dashboard whole-report cards** call `RS.kpiBandHtml(dims, rows, data.comparison || null, def, columns, grandTotals)` inside `renderReportCard(card, body, def, data, gen)` in `static/js/reporting_dashboard.js`; `def` there is the effective definition already POSTed (global filters merged). The card's catalog comes from that module's `ensureCatalog()` → `catalog.sources`.
- **Drill shell:** `templates/reporting.html` owns `#rdBackdrop`, `#rdPanel`, `#rdTitle`, `#rdSubtitle`, `#rdChips`, `#rdBody`, `#rdNote`, `#rdClose`; `window.ReportingDrill` (`templates/js/_reporting_drill_js.html`) exposes `open(opts)`, `close()`, `buildDrillDefinition(def, fields, clicked)`, `I18N`. `open({definition, fields, clicked:[{field, grain, value}], header, isDistinct})` builds an `eq`/`is_null` filter per clicked entry — the clicked field does **not** have to be one of `definition.columns`, so a contribution row can drill on a dimension the report never grouped by.
- **Server side:** `api_run` in `nx_lib/views/reporting/run.py` is the template — `@require_permission("reporting.view")`, `@limiter.limit("120 per minute")`, `_prepare_run(rd)` returning `(columns, sql, params, engine)`, `_execute(engine, sql, params)` returning `list[list]`, `_rows_json_safe`. A grouped run with `columns=[{"field": dim}]` and one metric returns rows shaped `[dim_value, metric_value]`. `shifted_definition_for_comparison(rd)` (`nx_lib/reporting/tokens.py`) returns `(shifted_rd, prior_start, prior_end)` or `None`. `total_definition(definition)` (`nx_lib/reporting/schedule.py`) is the zero-column clone whose single cell is the grand total of the first metric. `_catalog_for_source(source)` and `_get_effective_source(source_id)` and `_metrics_for_source(source_id, locale)` live in `_shared.py`; a catalog entry is `{field, label, type, filterable, sortable, grainable}` with `type` in `string`/`number`/`date`/`datetime`; `_metrics_for_source` returns `{code: {aggregation, base_field, total_mode, anchor, label}}` with `aggregation` in `count`, `count_distinct`, `sum`, `avg`, `min`, `max`.
- **e2e:** `tests/e2e/test_reporting_simple.py::test_delta_chip_renders_vs_prior_period` is the exemplar — `_login`, `_stub_catalogs(page)`, `page.route` registered **before** the click that fires the request, wizard clicks (`rs-new-report` → measure "Stub count" → `rs-measure-next` → `rs-breakdown-next` → time "This month" → `rs-wizard-run`). e2e is CI-only; locally run it with `NEXORA_E2E_PORT` set.
- **Help sync:** any change under `static/js/reporting_*`, `templates/js/_reporting_*`, `nx_lib/views/reporting/` makes the `reporting-help-sync` pre-commit hook nudge for `docs/howto/reporting-guide.md` + `templates/_reporting_help.html` — Task 9 covers both.
- **Migrations needed: NO. i18n needed: YES** (Task 10). **Deploy excludes: none. Env keys: none.**

## Decisions locked in

| # | Decision | Rationale |
|---|---|---|
| D1 | Trigger = the Total delta chip on the Simple KPI band, rendered as a `<button>`; Avg/Peak chips stay spans. | Spec; dashboard cards share the renderer so they inherit it. |
| D2 | Dimension pick: `processname` first if present, then `type == "string"` catalog entries in catalog order, minus `workitem_id`, minus fields with an `eq` filter, cap 3. | Spec §2. |
| D3 | **Header totals come from `total_definition()` clones** (one current, one prior query), not from summing the first dimension's rows. | Deviation from spec §1: a summed `avg`/`count_distinct` column is not the grand total; the zero-column clone is exactly what the KPI band and alert schedules already use, so `currentTotal` always equals the visible Total. Cost: 2 extra cheap queries (8 max per drawer). |
| D4 | Ratio metrics (`avg`, `min`, `max`, `count_distinct`) get `delta` only; `share` is `null` for every row and the UI hides the share column. Also `null` when the total delta is `0`. | Spec §1/§2. |
| D5 | Top 8 rows by `abs(delta)`, remainder folded into `(other)`; `None` dimension value → `(empty)`. `(other)` is not drillable. | Spec §2/§3. |
| D6 | The drawer reuses the drill shell elements verbatim; row click hands over to `ReportingDrill.open`, which repaints the same shell. | No second slide-over, no new markup beyond one CSS block. |
| D7 | A failing dimension query is skipped and listed in `skipped`; only a `PermissionError` from the first `_prepare_run` becomes a 403. | Spec §1: never 500 because one column is unqueryable. |
| D8 | Endpoint guard `reporting.view` + `120 per minute`, same as `api_run`. | Spec §4. |

## Owner actions

- None before execution. After merge, the INT walkthrough screenshot (Task 11) goes to `var/screenshots/contribution_*.png`.

---

# PHASE 1 — Pure helper (`nx_lib/reporting/contribution.py`)

### Task 1: `pick_dimensions` and `single_dimension_definition`

**Files:**
- Create: `nx_lib/reporting/contribution.py`
- Create: `tests/unit/test_reporting_contribution.py`

**Interfaces:**
- Produces: `pick_dimensions(catalog, filters, *, cap=3) -> list[dict]` returning catalog entries (`{field, label, ...}`) in pick order; `single_dimension_definition(rd, field, metric_code) -> dict` (deep copy with one column, one metric, no sort/forecast/compare, `rowLimit = MAX_ROW_LIMIT`).

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for nx_lib.reporting.contribution — contribution analysis maths."""

import pytest

from nx_lib.reporting.contribution import (
    contribution_rows,
    fill_shares,
    is_ratio_metric,
    pick_dimensions,
    single_dimension_definition,
)
from nx_lib.reporting.sources import MAX_ROW_LIMIT


def _f(field, type_="string", label=None):
    return {"field": field, "label": label or field, "type": type_,
            "filterable": True, "sortable": True, "grainable": type_ in ("date", "datetime")}


CATALOG = [
    _f("doctype"),
    _f("import_date", "date"),
    _f("processname", label="Process"),
    _f("pages", "number"),
    _f("status"),
    _f("workitem_id"),
    _f("client"),
]


def test_pick_dimensions_process_first_then_strings_in_catalog_order():
    picked = pick_dimensions(CATALOG, [])
    assert [d["field"] for d in picked] == ["processname", "doctype", "status"]


def test_pick_dimensions_skips_eq_filtered_and_workitem_id():
    filters = [{"field": "doctype", "op": "eq", "value": "Invoice"},
               {"field": "status", "op": "in", "value": ["a", "b"]}]
    picked = pick_dimensions(CATALOG, filters)
    assert [d["field"] for d in picked] == ["processname", "status", "client"]


def test_pick_dimensions_without_processname_and_with_cap():
    cat = [_f("a"), _f("b"), _f("c"), _f("d")]
    assert [d["field"] for d in pick_dimensions(cat, [], cap=2)] == ["a", "b"]
    assert pick_dimensions([_f("n", "number")], []) == []


def test_single_dimension_definition_is_a_clean_deep_copy():
    rd = {"schemaVersion": 1, "source": "docprocessing", "title": "T",
          "columns": [{"field": "import_date", "grain": "month"}],
          "filters": [{"field": "import_date", "op": "between", "value": {"token": "this_month"}}],
          "sort": [{"field": "import_date", "dir": "asc"}],
          "metrics": [{"metric": "doc_count"}, {"metric": "pages_sum"}],
          "forecast": {"enabled": True}, "compare": True, "rowLimit": 50,
          "scope": {"clients": ["a"], "processes": []}}
    out = single_dimension_definition(rd, "doctype", "doc_count")
    assert out["columns"] == [{"field": "doctype"}]
    assert out["metrics"] == [{"metric": "doc_count"}]
    assert out["sort"] == []
    assert "forecast" not in out and "compare" not in out
    assert out["rowLimit"] == MAX_ROW_LIMIT
    assert out["filters"] == rd["filters"] and out["filters"] is not rd["filters"]
    assert out["scope"] == rd["scope"]
    assert rd["columns"][0]["grain"] == "month"          # original untouched
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_reporting_contribution.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nx_lib.reporting.contribution'`

- [ ] **Step 3: Create the module with the two helpers** (`contribution_rows`, `fill_shares`, `is_ratio_metric` are added in Task 2 — add stub names now so the import line resolves):

```python
"""Contribution analysis ("Why did it move?") — Flask-free maths.

Given a Simple definition whose KPI band shows a delta chip, explain the
change vs. the shifted prior window by decomposing the first metric along a
few categorical dimensions. The view layer (nx_lib/views/reporting/run.py,
api_contribution) does the I/O; everything here is pure so the later Eddard
weekly card can call it without HTTP.
"""

import copy

from .sources import MAX_ROW_LIMIT

EMPTY_LABEL = "(empty)"
OTHER_LABEL = "(other)"
RATIO_AGGREGATIONS = {"avg", "min", "max", "count_distinct"}


def pick_dimensions(catalog, filters, *, cap=3):
    """Catalog entries to decompose by: processname first when present, then
    string-typed entries in catalog order; never workitem_id, never a field a
    single-value `eq` filter already pins. At most `cap` entries."""
    pinned = {
        f.get("field") for f in (filters or []) if isinstance(f, dict) and f.get("op") == "eq"
    }
    by_field = {c["field"]: c for c in catalog or []}
    out = []
    if "processname" in by_field and "processname" not in pinned:
        out.append(by_field["processname"])
    for c in catalog or []:
        if len(out) >= cap:
            break
        f = c.get("field")
        if f in ("processname", "workitem_id") or f in pinned:
            continue
        if c.get("type") != "string":
            continue
        out.append(c)
    return out[:cap]


def single_dimension_definition(rd, field, metric_code):
    """Deep copy of `rd` grouped by exactly one column with exactly one metric,
    ready for _prepare_run. Tokens stay intact (the run path resolves them)."""
    out = copy.deepcopy(rd)
    out["columns"] = [{"field": field}]
    out["metrics"] = [{"metric": metric_code}]
    out["sort"] = []
    out["rowLimit"] = MAX_ROW_LIMIT
    out.pop("forecast", None)
    out.pop("compare", None)
    return out


def is_ratio_metric(metric_def):  # Task 2
    raise NotImplementedError


def contribution_rows(current_rows, prior_rows, *, top=8):  # Task 2
    raise NotImplementedError


def fill_shares(dimensions, total_delta, is_ratio):  # Task 2
    raise NotImplementedError
```

- [ ] **Step 4: Run to verify the four tests pass**

Run: `pytest tests/unit/test_reporting_contribution.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/contribution.py tests/unit/test_reporting_contribution.py
git commit -m "feat(reporting): contribution helper — dimension pick and single-dimension clone"
```

### Task 2: `contribution_rows`, `fill_shares`, `is_ratio_metric`

**Files:**
- Modify: `nx_lib/reporting/contribution.py`
- Modify: `tests/unit/test_reporting_contribution.py`

**Interfaces:**
- Produces: `contribution_rows(current_rows, prior_rows, *, top=8) -> list[dict]` where each input row is `[dim_value, metric_value]` and each output row is `{"value": str, "current": float, "prior": float, "delta": float, "share": None}` sorted by `abs(delta)` desc, at most `top + 1` rows (the last being `(other)` when folded); `fill_shares(dimensions, total_delta, is_ratio) -> None` mutating `share` in place; `is_ratio_metric(metric_def) -> bool`.

- [ ] **Step 1: Append the failing tests**

```python
def test_contribution_rows_joins_sorts_and_folds():
    current = [["a", 400], ["b", 50], [None, 12], ["c", 5], ["d", 1]]
    prior = [["a", 250], ["b", 80], [None, 30], ["e", 7]]
    rows = contribution_rows(current, prior, top=2)
    assert [r["value"] for r in rows] == ["a", "b", "(other)"]
    assert rows[0] == {"value": "a", "current": 400, "prior": 250, "delta": 150, "share": None}
    assert rows[1]["delta"] == -30
    other = rows[2]
    # (empty) -18, c +5, d +1, e -7  → current 18, prior 37, delta -19
    assert (other["current"], other["prior"], other["delta"]) == (18, 37, -19)


def test_contribution_rows_no_fold_when_within_top():
    rows = contribution_rows([["a", 1]], [["b", 2]], top=8)
    assert [r["value"] for r in rows] == ["b", "a"]        # |−2| before |+1|
    assert rows[0] == {"value": "b", "current": 0, "prior": 2, "delta": -2, "share": None}


def test_contribution_rows_empty_label_and_decimal_strings():
    from decimal import Decimal
    rows = contribution_rows([[None, Decimal("2.5")]], [], top=8)
    assert rows == [{"value": "(empty)", "current": 2.5, "prior": 0, "delta": 2.5, "share": None}]


def test_fill_shares_sets_fraction_or_null():
    dims = [{"field": "x", "label": "X", "rows": [
        {"value": "a", "current": 4, "prior": 1, "delta": 3, "share": None},
        {"value": "b", "current": 0, "prior": 1, "delta": -1, "share": None},
    ]}]
    fill_shares(dims, 2, False)
    assert dims[0]["rows"][0]["share"] == pytest.approx(1.5)
    assert dims[0]["rows"][1]["share"] == pytest.approx(-0.5)
    fill_shares(dims, 0, False)
    assert all(r["share"] is None for r in dims[0]["rows"])
    fill_shares(dims, 2, True)
    assert all(r["share"] is None for r in dims[0]["rows"])


@pytest.mark.parametrize("agg,expected", [
    ("count", False), ("sum", False), ("avg", True), ("min", True),
    ("max", True), ("count_distinct", True),
])
def test_is_ratio_metric(agg, expected):
    assert is_ratio_metric({"aggregation": agg}) is expected
    assert is_ratio_metric(None) is False
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_reporting_contribution.py -q`
Expected: the new tests FAIL with `NotImplementedError`; the Task 1 tests still pass.

- [ ] **Step 3: Replace the three stubs**

```python
def is_ratio_metric(metric_def):
    """True for aggregations whose per-group values do not sum to the total —
    a 'share of the change' is meaningless for them (avg/min/max/distinct)."""
    agg = (metric_def or {}).get("aggregation")
    return agg in RATIO_AGGREGATIONS


def _num(v):
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _label(v):
    return EMPTY_LABEL if v is None or v == "" else str(v)


def contribution_rows(current_rows, prior_rows, *, top=8):
    """Full outer join of two [value, metric] row lists on value, delta per
    value, sorted by |delta| desc. Keeps `top` rows and folds the rest into
    one '(other)' row. `share` is left None — fill_shares sets it once the
    caller knows the grand totals (D3)."""
    joined = {}
    for v, m in current_rows or []:
        joined.setdefault(_label(v), [0.0, 0.0])[0] += _num(m)
    for v, m in prior_rows or []:
        joined.setdefault(_label(v), [0.0, 0.0])[1] += _num(m)
    rows = [
        {"value": k, "current": c, "prior": p, "delta": c - p, "share": None}
        for k, (c, p) in joined.items()
    ]
    rows.sort(key=lambda r: (-abs(r["delta"]), r["value"]))
    head, tail = rows[:top], rows[top:]
    if tail:
        c = sum(r["current"] for r in tail)
        p = sum(r["prior"] for r in tail)
        head.append({"value": OTHER_LABEL, "current": c, "prior": p, "delta": c - p, "share": None})
    return head


def fill_shares(dimensions, total_delta, is_ratio):
    """share = delta / total_delta, or None for ratio metrics / a zero total."""
    usable = (not is_ratio) and bool(total_delta)
    for d in dimensions:
        for r in d.get("rows", []):
            r["share"] = (r["delta"] / total_delta) if usable else None
```

Note the sort tiebreak on `value` — deterministic output for equal deltas, which the tests rely on.

- [ ] **Step 4: Run green**

Run: `pytest tests/unit/test_reporting_contribution.py -q`
Expected: 14 passed (4 from Task 1, 4 new, 6 parametrized)

- [ ] **Step 5: Commit**

```bash
git add nx_lib/reporting/contribution.py tests/unit/test_reporting_contribution.py
git commit -m "feat(reporting): contribution rows — join, fold, shares, ratio guard"
```

---

# PHASE 2 — Endpoint

### Task 3: `POST /api/reporting/contribution`

**Files:**
- Modify: `nx_lib/views/reporting/run.py`
- Test: `tests/integration/test_reporting_contribution_api.py` (new)

**Interfaces:**
- Consumes: Task 1–2 helpers; `_prepare_run`, `_execute`, `_get_effective_source`, `_catalog_for_source`, `_metrics_for_source` from `._shared`; `shifted_definition_for_comparison`; `total_definition` from `nx_lib.reporting.schedule`.
- Produces: JSON `{priorStart, priorEnd, metric, metricLabel, isRatio, currentTotal, priorTotal, dimensions:[{field,label,rows:[...]}], skipped:[...]}` exactly as spec §1.

- [ ] **Step 1: Write the failing integration tests.** Copy the seeded-table-source idiom from `test_zero_dim_latest_metric_run_constrains_to_latest_bucket` in `tests/integration/test_reporting_routes.py` (admin creates a `table` source over `dbo.Users` via `/api/reporting/admin/sources` + a `count` metric via `/api/reporting/admin/metrics`, deletes both in `finally`).

```python
"""Integration: POST /api/reporting/contribution (contribution analysis)."""

import pytest

SOURCE = {
    "code": "contrib_test_src",
    "kind": "curated",
    "label": "Contrib Test Src",
    "permission": "reporting.source.docprocessing",
    "provider": "table",
    "engine": "nexora",
    "baseObject": "dbo.Users",
    "columns": [
        {"field": "Email", "label": "Email", "type": "string",
         "filterable": True, "sortable": True, "grainable": False},
        {"field": "locale", "label": "Locale", "type": "string",
         "filterable": True, "sortable": True, "grainable": False},
        {"field": "LastLoginAt", "label": "Last Login", "type": "datetime",
         "filterable": True, "sortable": True, "grainable": True},
    ],
    "enabled": True,
    "sortOrder": 18,
}


@pytest.fixture
def contrib_source(admin_client):
    src = admin_client.post("/api/reporting/admin/sources", json=SOURCE).get_json()["id"]
    met = admin_client.post(
        "/api/reporting/admin/metrics",
        json={"code": "contrib_test_count", "sourceId": "contrib_test_src",
              "label": "Users", "aggregation": "count", "enabled": True, "sortOrder": 18},
    ).get_json()["id"]
    yield "contrib_test_src"
    admin_client.delete(f"/api/reporting/admin/metrics/{met}")
    admin_client.delete(f"/api/reporting/admin/sources/{src}")


def _definition(filters):
    return {
        "schemaVersion": 1, "source": "contrib_test_src", "visualization": "table",
        "title": "Contrib", "columns": [], "filters": filters, "sort": [],
        "scope": {}, "rowLimit": 10, "metrics": [{"metric": "contrib_test_count"}],
    }


TOKEN_FILTER = {"field": "LastLoginAt", "op": "between", "value": {"token": "this_year"}}


def test_contribution_invalid_json_400(admin_client):
    resp = admin_client.post("/api/reporting/contribution", data="nope")
    assert resp.status_code == 400


def test_contribution_without_metrics_400(admin_client, contrib_source):
    rd = _definition([TOKEN_FILTER])
    rd["metrics"] = []
    resp = admin_client.post("/api/reporting/contribution", json=rd)
    assert resp.status_code == 400
    assert "measure" in resp.get_json()["error"]


def test_contribution_without_token_window_400(admin_client, contrib_source):
    resp = admin_client.post("/api/reporting/contribution", json=_definition([]))
    assert resp.status_code == 400
    assert "comparison window" in resp.get_json()["error"]


def test_contribution_shape_and_totals_match_run(admin_client, contrib_source):
    rd = _definition([TOKEN_FILTER])
    resp = admin_client.post("/api/reporting/contribution", json=rd)
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert set(body) >= {"priorStart", "priorEnd", "metric", "metricLabel", "isRatio",
                         "currentTotal", "priorTotal", "dimensions", "skipped"}
    assert body["metric"] == "contrib_test_count" and body["isRatio"] is False
    # string columns in catalog order, no processname on a table source
    assert [d["field"] for d in body["dimensions"]] == ["Email", "locale"]
    assert body["dimensions"][0]["label"] == "Email"
    for row in body["dimensions"][0]["rows"]:
        assert set(row) == {"value", "current", "prior", "delta", "share"}
    # D3: header total is the zero-column run's grand total
    run = admin_client.post("/api/reporting/run", json=rd).get_json()
    assert body["currentTotal"] == float(run["rows"][0][0])


def test_contribution_eq_filter_drops_that_dimension(admin_client, contrib_source):
    rd = _definition([TOKEN_FILTER, {"field": "locale", "op": "eq", "value": "de"}])
    body = admin_client.post("/api/reporting/contribution", json=rd).get_json()
    assert [d["field"] for d in body["dimensions"]] == ["Email"]


def test_contribution_without_permission_403(user_client, contrib_source):
    resp = user_client.post("/api/reporting/contribution", json=_definition([TOKEN_FILTER]))
    assert resp.status_code in (403, 400)   # user@test.local lacks the source perm
```

The `admin_client` / `user_client` fixtures come from `tests/conftest.py` (`def admin_client(login)` / `def user_client(login)`, same as `test_reporting_routes.py` uses). If `user@test.local` cannot even reach `reporting.view`, the last test's 403 comes from `require_permission` — both are correct; keep the tuple.

- [ ] **Step 2: Run to verify failure**

Run: `python scripts/test_db_reset.py && pytest tests/integration/test_reporting_contribution_api.py -q`
Expected: FAIL — 404 on every POST (route not registered).

- [ ] **Step 3: Add the imports** at the top of `nx_lib/views/reporting/run.py`, after `from ...reporting.catalog import fetch_docprocessing_catalog`:

```python
from ...reporting.contribution import (
    contribution_rows,
    fill_shares,
    is_ratio_metric,
    pick_dimensions,
    single_dimension_definition,
)
from ...reporting.schedule import total_definition
```

and extend the `from ._shared import (` block with `_catalog_for_source,` and `_metrics_for_source` is already there; add `_catalog_for_source` in alphabetical position (after `_authorize_sql_target,`).

- [ ] **Step 4: Add the view** directly after the `api_run` function body (before `def _sandbox_error_message`):

```python
def _grand_total(rd):
    """Single cell of the zero-column clone (the KPI band's own Total)."""
    clone = total_definition(rd)
    columns, sql, params, engine = _prepare_run(clone)
    rows = _execute(engine, sql, params)
    cell = rows[0][0] if rows and rows[0] else 0
    try:
        return float(cell) if cell is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


@require_permission("reporting.view")
@limiter.limit("120 per minute")
def api_contribution():
    """Decompose the first metric's change vs. the shifted prior window by a
    few categorical dimensions (spec 2026-09-07-reporting-contribution-analysis).
    Every query goes through _prepare_run, so grants/scope equal the report's."""
    rd = request.get_json(silent=True)
    if not isinstance(rd, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    metrics = rd.get("metrics") or []
    if not metrics or not isinstance(metrics[0], dict) or not metrics[0].get("metric"):
        return jsonify({"error": _("This report has no measure to explain.")}), 400
    shifted = shifted_definition_for_comparison(rd)
    if shifted is None:
        return jsonify(
            {"error": _("No comparison window — the report needs exactly one relative-date filter.")}
        ), 400
    shifted_rd, prior_start, prior_end = shifted
    source = _get_effective_source(rd.get("source"))
    if source is None or source.get("kind") != "curated":
        return jsonify({"error": _("This report definition is invalid or outdated.")}), 400
    if not has_permission(source["permission"]):
        return jsonify({"error": _("Not authorized for this source")}), 403
    metric_code = metrics[0]["metric"]
    try:
        catalog, _fields, _filterable, _sortable = _catalog_for_source(source)
        source_metrics = _metrics_for_source(source["id"], get_locale())
        current_total = _grand_total(rd)
        prior_total = _grand_total(shifted_rd)
    except PermissionError:
        return jsonify({"error": _("Not authorized for this source")}), 403
    except (ReportDefinitionError, QueryBuildError, TableQueryError, MetricResolveError) as e:
        return jsonify(
            {"error": _("This report definition is invalid or outdated."), "detail": str(e)}
        ), 400
    except Exception as e:
        current_app.logger.error(f"/api/reporting/contribution prepare error: {e}")
        return jsonify({"error": _("Could not build report")}), 500

    metric_def = source_metrics.get(metric_code) or {}
    is_ratio = is_ratio_metric(metric_def)
    dimensions, skipped = [], []
    for dim in pick_dimensions(catalog, rd.get("filters") or []):
        field = dim["field"]
        try:
            c_cols, c_sql, c_params, c_engine = _prepare_run(
                single_dimension_definition(rd, field, metric_code)
            )
            p_cols, p_sql, p_params, p_engine = _prepare_run(
                single_dimension_definition(shifted_rd, field, metric_code)
            )
            c_rows = _execute(c_engine, c_sql, c_params)
            p_rows = _execute(p_engine, p_sql, p_params)
        except Exception as e:  # one unqueryable column must not sink the drawer
            current_app.logger.warning(f"/api/reporting/contribution skipped {field}: {e}")
            skipped.append(field)
            continue
        dimensions.append(
            {
                "field": field,
                "label": dim.get("label") or field,
                "rows": contribution_rows(c_rows, p_rows, top=8),
            }
        )
    fill_shares(dimensions, current_total - prior_total, is_ratio)
    return jsonify(
        {
            "priorStart": prior_start.isoformat(),
            "priorEnd": prior_end.isoformat(),
            "metric": metric_code,
            "metricLabel": metric_def.get("label") or metric_code,
            "isRatio": is_ratio,
            "currentTotal": current_total,
            "priorTotal": prior_total,
            "dimensions": dimensions,
            "skipped": skipped,
        }
    )
```

- [ ] **Step 5: Register the route** — append inside `register_routes(app)` in the same file, after the existing `"/api/reporting/sql/ack"` rule (last statement of the function):

```python
    app.add_url_rule(
        "/api/reporting/contribution",
        endpoint="reporting_contribution",
        view_func=api_contribution,
        methods=["POST"],
    )
```

- [ ] **Step 6: Run green**

Run: `pytest tests/integration/test_reporting_contribution_api.py tests/unit/test_reporting_contribution.py -q`
Expected: all passed. If `test_contribution_shape_and_totals_match_run` fails on `currentTotal` because `run["rows"][0][0]` is an `int`, keep the `float(...)` on the test side — the endpoint always returns a float (D3).

- [ ] **Step 7: Run the neighbouring suites to prove nothing regressed**

Run: `pytest tests/integration/test_reporting_routes.py tests/unit/test_reporting_shared_exports.py -q`
Expected: passed (the `_shared` export test guards the import surface you just touched).

- [ ] **Step 8: Commit**

```bash
git add nx_lib/views/reporting/run.py tests/integration/test_reporting_contribution_api.py
git commit -m "feat(reporting): POST /api/reporting/contribution explains a delta by dimension"
```

---

# PHASE 3 — UI

### Task 4: The Total chip becomes a button

**Files:**
- Modify: `static/js/reporting_simple_result.js`
- Modify: `templates/js/_reporting_simple_js.html`
- Modify: `static/css/reporting.css`

**Interfaces:**
- Produces: a `<button type="button" class="rp-delta rp-delta--<dir> rp-delta--why" data-testid="rp-delta" data-why="1">` on the Total tile only; `RS.I18N.whyLabel` string.

- [ ] **Step 1: Add the string to the shim.** In `templates/js/_reporting_simple_js.html`, inside the `window.NX_I18N_REPORTING_SIMPLE = {` object, after the line `deltaVs: {{ _("vs")|tojson }},` add:

```js
    whyLabel: {{ _("Why did this change?")|tojson }},
```

- [ ] **Step 2: Extend `deltaChipHtml`.** In `static/js/reporting_simple_result.js` change the signature `function deltaChipHtml(current, prior, priorStart, priorEnd) {` to `function deltaChipHtml(current, prior, priorStart, priorEnd, asButton) {` and replace its `return '<span class="rp-delta ...` statement with:

```js
    var body = arrow + ' ' + Math.round(d.pct) + '%';
    if (!asButton) {
      return '<span class="rp-delta rp-delta--' + d.dir + '" data-testid="rp-delta"' +
        ' title="' + RS.esc(title) + '" aria-label="' + RS.esc(title) + '">' + body + '</span>';
    }
    return '<button type="button" class="rp-delta rp-delta--' + d.dir + ' rp-delta--why"' +
      ' data-testid="rp-delta" data-why="1"' +
      ' title="' + RS.esc(title + ' · ' + RS.I18N.whyLabel) + '"' +
      ' aria-label="' + RS.esc(RS.I18N.whyLabel + ' ' + title) + '">' + body + '</button>';
```

Then change the one Total call `totalDelta = deltaChipHtml(kpi.total, priorKpi.total, comparison.priorStart, comparison.priorEnd);` to pass `true` as a fifth argument. Avg and Peak calls stay unchanged.

- [ ] **Step 3: CSS.** Append at the end of `static/css/reporting.css`:

```css
/* ---- Contribution analysis ("Why did it move?") — the Total delta chip is
   a button; the drawer body reuses the drill shell (#rdPanel). ---- */
.rp-delta--why {
  cursor: pointer;
  border: 1px solid currentColor;
  border-radius: 999px;
  padding: 0 .45rem;
  background: transparent;
  font: inherit;
  font-size: .72rem;
  font-weight: 700;
  line-height: 1.5;
}
.rp-delta--why:hover,
.rp-delta--why:focus-visible { background: color-mix(in srgb, currentColor 12%, transparent); outline: none; }
```

- [ ] **Step 4: Verify the existing e2e assertions still hold** — `tests/e2e/test_reporting_simple.py::test_delta_chip_renders_vs_prior_period` checks `rp-delta--up`, text `↑ 40%` and the `title` attribute `vs 2026-05-01 – 2026-05-31`. The title now carries a suffix, so change that assertion to:

```python
    expect(chip).to_have_attribute("title", re.compile(r"^vs 2026-05-01 – 2026-05-31"))  # noqa: RUF001
```

Run: `NEXORA_E2E_PORT=5177 pytest tests/e2e/test_reporting_simple.py -k delta_chip -q` (needs a browser; on CI this runs automatically — if no local browser, skip and rely on CI, say so in the commit body).

- [ ] **Step 5: Commit**

```bash
git add static/js/reporting_simple_result.js templates/js/_reporting_simple_js.html static/css/reporting.css tests/e2e/test_reporting_simple.py
git commit -m "feat(reporting): Total delta chip is a Why? button"
```

### Task 5: The contribution drawer module

**Files:**
- Create: `static/js/reporting_contribution.js`
- Create: `templates/js/_reporting_contribution_js.html`
- Modify: `templates/reporting.html`
- Modify: `static/css/reporting.css`

**Interfaces:**
- Consumes: `window.ReportingDrill` (`open`, `close`, `I18N.nullLabel`), `window.NX` (`el`, `esc`, `apiSafe`), `window.RS.fmtNumber`.
- Produces: `window.ReportingContribution = { open(definition, fields, opts) }` where `opts = {header}`; posts `definition` to `api/reporting/contribution`, renders tabs + bars into `#rdBody`.

- [ ] **Step 1: Create the shim** `templates/js/_reporting_contribution_js.html`:

```html
<script nonce="{{ csp_nonce() }}">
  // Jinja-rendered strings for static/js/reporting_contribution.js (#191).
  window.NX_I18N_REPORTING_CONTRIBUTION = {
    title: {{ _("Why did it change?")|tojson }},
    subtitle: {{ _("Contribution to the change vs. the prior period")|tojson }},
    prior: {{ _("prior")|tojson }},
    current: {{ _("current")|tojson }},
    change: {{ _("change")|tojson }},
    shareOfChange: {{ _("share of change")|tojson }},
    other: {{ _("(other)")|tojson }},
    noDimensions: {{ _("This source has no columns to break the change down by.")|tojson }},
    notShown: {{ _("Not shown: {fields}")|tojson }},
    loading: {{ _("Working out what changed…")|tojson }},
    loadError: {{ _("Could not explain this change.")|tojson }},
    drillHint: {{ _("Click a row to see the documents behind it.")|tojson }}
  };
</script>
<script src="{{ static_v('js/reporting_contribution.js') }}"></script>
```

- [ ] **Step 2: Include it** in `templates/reporting.html` on the line directly after `{% include "js/_reporting_drill_js.html" %}`:

```jinja
  {% include "js/_reporting_contribution_js.html" %}
```

(ReportingDrill must exist first — same ordering rule the comment above that include already states.)

- [ ] **Step 3: Write the module** `static/js/reporting_contribution.js`:

```js
/* Contribution analysis drawer ("Why did it move?"). Reuses the drill shell
   (#rdPanel etc., owned by templates/reporting.html) and hands row clicks to
   ReportingDrill.open. Behaviour only — strings come from the shim
   templates/js/_reporting_contribution_js.html (#191). */
window.ReportingContribution = (function () {
  'use strict';
  var I18N = window.NX_I18N_REPORTING_CONTRIBUTION || {};
  var el = window.NX.el, esc = window.NX.esc;
  var fmt = function (n) { return (window.RS && RS.fmtNumber) ? RS.fmtNumber(n) : String(n); };
  var current = null;      // {definition, fields, data} of the open drawer

  function pct(v) { return (v > 0 ? '+' : '') + Math.round(v * 100) + '%'; }
  function dir(delta) { return delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat'; }
  function arrow(delta) { return delta > 0 ? '↑' : delta < 0 ? '↓' : '—'; }

  function headerHtml(d) {
    var delta = d.currentTotal - d.priorTotal;
    var rel = d.priorTotal ? ' (' + pct(delta / d.priorTotal) + ')' : '';
    return '<p class="reporting-contrib-head" data-testid="contrib-head">' +
      esc(d.metricLabel) + ' · ' + esc(fmt(d.priorTotal)) + ' → ' + esc(fmt(d.currentTotal)) +
      ' <span class="rp-delta rp-delta--' + dir(delta) + '">' + arrow(delta) + ' ' +
      esc(fmt(Math.abs(delta))) + esc(rel) + '</span>' +
      ' · ' + esc(I18N.prior) + ' ' + esc(d.priorStart) + ' – ' + esc(d.priorEnd) + '</p>';
  }

  function tabHtml(dim, i, active) {
    return '<button type="button" role="tab" class="reporting-contrib-tab' +
      (active ? ' is-active' : '') + '" data-tab="' + i + '"' +
      ' aria-selected="' + (active ? 'true' : 'false') + '" data-testid="contrib-tab">' +
      esc(dim.label) + '</button>';
  }

  function rowsHtml(dim, i, active, isRatio) {
    var max = 0;
    dim.rows.forEach(function (r) { max = Math.max(max, Math.abs(r.delta)); });
    return '<div class="reporting-contrib-rows" data-panel="' + i + '"' + (active ? '' : ' hidden') +
      ' data-testid="contrib-rows">' +
      dim.rows.map(function (r, ri) {
        var other = r.value === '(other)';
        var w = max ? Math.round(Math.abs(r.delta) / max * 100) : 0;
        var label = r.value === '(empty)' ? ReportingDrill.I18N.nullLabel
          : other ? I18N.other : r.value;
        return '<div class="reporting-contrib-row' + (other ? ' is-other' : '') + '"' +
          (other ? '' : ' tabindex="0" data-row="' + ri + '"') + ' data-testid="contrib-row">' +
          '<span class="reporting-contrib-label" title="' + esc(label) + '">' + esc(label) + '</span>' +
          '<span class="reporting-contrib-bar rp-delta--' + dir(r.delta) + '">' +
            (other ? '' : '<i style="width:' + w + '%"></i>') + '</span>' +
          '<span class="reporting-contrib-nums">' +
            esc(fmt(r.prior)) + ' → ' + esc(fmt(r.current)) +
            ' <b class="rp-delta rp-delta--' + dir(r.delta) + '">' + arrow(r.delta) + ' ' +
            esc(fmt(Math.abs(r.delta))) + '</b>' +
            (!isRatio && r.share != null ? ' <small>' + esc(pct(r.share)) + '</small>' : '') +
          '</span></div>';
      }).join('') + '</div>';
  }

  function render(d) {
    var body = el('rdBody');
    if (!d.dimensions.length) {
      body.innerHTML = headerHtml(d) + '<p class="reporting-drill-note">' + esc(I18N.noDimensions) + '</p>';
      return;
    }
    body.innerHTML = headerHtml(d) +
      '<div class="reporting-contrib-tabs" role="tablist">' +
        d.dimensions.map(function (dim, i) { return tabHtml(dim, i, i === 0); }).join('') +
      '</div>' +
      d.dimensions.map(function (dim, i) { return rowsHtml(dim, i, i === 0, d.isRatio); }).join('');
    var note = [I18N.drillHint];
    if (d.skipped && d.skipped.length) note.push(I18N.notShown.replace('{fields}', d.skipped.join(', ')));
    el('rdNote').textContent = note.join(' ');
  }

  function onBodyClick(e) {
    if (!current) return;
    var tab = e.target.closest('[data-tab]');
    if (tab) {
      var idx = tab.getAttribute('data-tab');
      el('rdBody').querySelectorAll('[data-tab]').forEach(function (t) {
        var on = t.getAttribute('data-tab') === idx;
        t.classList.toggle('is-active', on);
        t.setAttribute('aria-selected', on ? 'true' : 'false');
      });
      el('rdBody').querySelectorAll('[data-panel]').forEach(function (p) {
        p.hidden = p.getAttribute('data-panel') !== idx;
      });
      return;
    }
    var row = e.target.closest('[data-row]');
    if (!row) return;
    drill(row);
  }

  function onBodyKey(e) {
    if (e.key !== 'Enter') return;
    var row = e.target.closest('[data-row]');
    if (row) drill(row);
  }

  function drill(rowEl) {
    var panel = rowEl.closest('[data-panel]');
    var dim = current.data.dimensions[Number(panel.getAttribute('data-panel'))];
    var r = dim.rows[Number(rowEl.getAttribute('data-row'))];
    var value = r.value === '(empty)' ? null : r.value;
    var def = current.definition, fields = current.fields;
    current = null;                          // the drill now owns the shell
    ReportingDrill.open({
      definition: def, fields: fields,
      clicked: [{ field: dim.field, grain: null, value: value }],
      header: dim.label + ' = ' + (value === null ? ReportingDrill.I18N.nullLabel : String(value).slice(0, 60))
    });
  }

  /* definition: the Simple definition whose KPI band showed the chip (tokens
     intact). fields: that source's catalog field list. opts.header: title. */
  function open(definition, fields, opts) {
    opts = opts || {};
    current = { definition: definition, fields: fields, data: null };
    var token = current;
    el('rdTitle').textContent = opts.header || I18N.title;
    el('rdSubtitle').textContent = I18N.subtitle;
    el('rdChips').innerHTML = '';
    el('rdNote').textContent = '';
    el('rdBody').innerHTML =
      '<div class="reporting-ai-loading"><span class="reporting-ai-dots" aria-hidden="true">' +
      '<i></i><i></i><i></i></span><span role="status">' + esc(I18N.loading) + '</span></div>';
    el('rdPanel').hidden = false;
    el('rdBackdrop').hidden = false;
    // NX.apiSafe resolves a leading-slash URL through API_PREFIX itself and
    // sets Content-Type + X-CSRFToken (see resolveUrl in nx_core.js).
    window.NX.apiSafe('/api/reporting/contribution', {
      method: 'POST', body: JSON.stringify(definition)
    }).then(function (r) {
      if (current !== token) return;
      if (!r.ok) {
        el('rdBody').innerHTML = '<p class="reporting-drill-note" data-testid="contrib-error">' +
          esc((r.data && r.data.error) || I18N.loadError) + '</p>';
        return;
      }
      current.data = r.data;
      render(r.data);
    });
  }

  el('rdBody').addEventListener('click', onBodyClick);
  el('rdBody').addEventListener('keydown', onBodyKey);
  el('rdClose').addEventListener('click', function () { current = null; });

  return { open: open };
})();
```

`window.NX.apiSafe(url, opts)` (in `static/js/nx_core.js`) merges `{ headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() } }` and runs `resolveUrl`, which turns `/api/...` into `window.API_PREFIX + 'api/...'` — the same idiom `RS.api('/api/reporting/run', …)` uses in `reporting_simple.js`. Never prepend `API_PREFIX` yourself or PROD double-prefixes.

- [ ] **Step 4: Drawer CSS.** Append at the end of `static/css/reporting.css` (after the Task 4 block):

```css
.reporting-contrib-head { margin: 0 0 .75rem; font-size: .9rem; }
.reporting-contrib-tabs { display: flex; gap: .25rem; margin-bottom: .5rem; flex-wrap: wrap; }
.reporting-contrib-tab {
  font: inherit; font-size: .8rem; padding: .25rem .6rem; border-radius: 999px;
  border: 1px solid var(--nx-border); background: transparent; cursor: pointer;
}
.reporting-contrib-tab.is-active { background: var(--nx-accent); color: #fff; border-color: var(--nx-accent); }
.reporting-contrib-row {
  display: grid; grid-template-columns: minmax(6rem, 1fr) 2fr auto; gap: .5rem;
  align-items: center; padding: .35rem .25rem; border-bottom: 1px solid var(--nx-border);
}
.reporting-contrib-row[tabindex]:hover,
.reporting-contrib-row[tabindex]:focus-visible { background: var(--nx-accent-tint); cursor: pointer; outline: none; }
.reporting-contrib-row.is-other { opacity: .7; }
.reporting-contrib-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.reporting-contrib-bar { height: .6rem; background: color-mix(in srgb, currentColor 12%, transparent); border-radius: 999px; overflow: hidden; }
.reporting-contrib-bar i { display: block; height: 100%; background: currentColor; border-radius: 999px; }
.reporting-contrib-nums { font-variant-numeric: tabular-nums; font-size: .8rem; white-space: nowrap; }
.reporting-contrib-nums small { color: var(--nx-text-meta); }
```

`--nx-accent`, `--nx-accent-tint`, `--nx-border` and `--nx-text-meta` are the tokens `reporting.css` already uses (`.reporting-drill-chip--indigo`, `.rp-delta--flat`); `color-mix(` is already used seven times in the file.

- [ ] **Step 5: Manual smoke** — `nx -r`, open `/reporting?tab=simple`, run any wizard report with a time preset, confirm the page loads with no console error (`ReportingContribution` defined). Nothing opens yet; wiring is Task 6.

- [ ] **Step 6: Commit**

```bash
git add static/js/reporting_contribution.js templates/js/_reporting_contribution_js.html templates/reporting.html static/css/reporting.css
git commit -m "feat(reporting): contribution drawer module renders tabs and signed bars"
```

### Task 6: Wire the button on the Simple band and dashboard cards

**Files:**
- Modify: `static/js/reporting_simple_result.js`
- Modify: `static/js/reporting_dashboard.js`

- [ ] **Step 1: Simple band.** In `static/js/reporting_simple_result.js`, directly after the line `RS.renderKpiBand = renderKpiBand;` add:

```js
  // "Why?" — the Total delta chip opens the contribution drawer with the
  // definition that produced this band (tokens intact) and its catalog.
  RS.el('rsKpiBand').addEventListener('click', function (e) {
    var btn = e.target.closest('[data-why]');
    if (!btn || !window.ReportingContribution) return;
    var cur = RS.state && RS.state.current;
    if (!cur || !cur.def) return;
    var src = (RS.state.sources || []).find(function (s) { return s.id === cur.def.source; });
    ReportingContribution.open(cur.def, (src && src.fields) || [],
      { header: cur.name || cur.def.title || '' });
  });
```

**Load order trap:** `reporting_simple_result.js` loads *before* `reporting_simple.js` (which sets `RS.el`), and the listener above runs at module-load time. Only `reporting_simple_wizard.js` carries the `RS.el = RS.el || window.NX.el;` fallback today, so add the same line to `reporting_simple_result.js` directly after its `window.RS = window.RS || {};` line, and also guard `RS.state`: use `var cur = RS.state && RS.state.current;` in the listener (the `renderKpiBand` calls inside the file are fine — they run after `reporting_simple.js` has initialised `RS`).

- [ ] **Step 2: Dashboard cards.** In `static/js/reporting_dashboard.js`, inside `renderReportCard(card, body, def, data, gen)`, directly after the block that ends `kpis.hidden = false;` … `});` `}` (the `if (kpiHtml) {` block), add:

```js
    var kpiHost = q('.rdb-report-kpis');
    if (kpiHost && !kpiHost._whyWired) {
      kpiHost._whyWired = true;
      kpiHost.addEventListener('click', function (e) {
        if (!e.target.closest('[data-why]') || !window.ReportingContribution) return;
        var src = catalog && catalog.sources.find(function (s) { return s.id === def.source; });
        ReportingContribution.open(def, (src && src.fields) || [], { header: card.title || '' });
      });
    }
```

`q` is the card-scoped query helper already used two lines above (`var kpis = q('.rdb-report-kpis');`); `catalog` is this module's lazily-fetched source catalog (populated by `ensureCatalog()`, which `renderReportCard` already awaited). The `_whyWired` flag stops re-renders stacking listeners.

- [ ] **Step 3: Manual verification on INT** — `nx -r`, `/reporting?tab=simple`, wizard: measure → no breakdown → "This month" → Run. Click the `↑/↓` chip on the Total tile: the drawer shows the header line, tabs (Process first), bars. Click a row: the drill drawer replaces it with document rows. Then `/reporting?tab=dashboard`, a whole-report card with a time preset: same chip, same drawer. Save `var/screenshots/contribution_simple.png` and `var/screenshots/contribution_dashboard.png` (Playwright via `bin/nx.ps1 -u -b --loginas:ben.streich`, or the Chrome MCP).

- [ ] **Step 4: Commit**

```bash
git add static/js/reporting_simple_result.js static/js/reporting_dashboard.js
git commit -m "feat(reporting): Why? chip opens the contribution drawer on Simple and dashboard cards"
```

### Task 7: Playwright e2e

**Files:**
- Create: `tests/e2e/test_reporting_contribution.py`

- [ ] **Step 1: Write the test** (stubs registered before the request-firing click; wizard clicks copied from `test_delta_chip_renders_vs_prior_period`; `_stub_catalogs` is module-level in `tests/e2e/test_reporting_simple.py` — import it):

```python
"""e2e: the contribution-analysis drawer behind the Total delta chip."""

import json

from playwright.sync_api import expect

from tests.e2e.test_reporting_simple import _login, _stub_catalogs

RUN = {
    "columns": [{"field": "stub_count", "header": "Stub count"}],
    "rows": [[42]], "truncated": False, "rowCount": 1, "sql": None, "params": [],
    "resolvedDates": [],
    "comparison": {"columns": [{"field": "stub_count", "header": "Stub count"}],
                   "rows": [[30]], "priorStart": "2026-05-01", "priorEnd": "2026-05-31"},
}

CONTRIB = {
    "priorStart": "2026-05-01", "priorEnd": "2026-05-31",
    "metric": "stub_count", "metricLabel": "Stub count", "isRatio": False,
    "currentTotal": 42, "priorTotal": 30,
    "dimensions": [
        {"field": "processname", "label": "Process", "rows": [
            {"value": "acme.inv", "current": 30, "prior": 20, "delta": 10, "share": 0.83},
            {"value": "(empty)", "current": 2, "prior": 0, "delta": 2, "share": 0.17},
            {"value": "(other)", "current": 10, "prior": 10, "delta": 0, "share": 0.0},
        ]},
        {"field": "doctype", "label": "Document type", "rows": [
            {"value": "Invoice", "current": 42, "prior": 30, "delta": 12, "share": 1.0},
        ]},
    ],
    "skipped": ["status"],
}


def _run_with_preset(page):
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Stub count").click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-time-list").get_by_text("This month", exact=True).click()
    page.get_by_test_id("rs-wizard-run").click()
    expect(page.get_by_test_id("rs-result")).to_be_visible()


def test_why_chip_opens_contribution_drawer_and_drills(nexora_server, page):
    _login(page, nexora_server)
    _stub_catalogs(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    posted = []

    def _contrib(route):
        posted.append(route.request.post_data_json)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(CONTRIB))

    runs = []

    def _run(route):
        runs.append(route.request.post_data_json)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(RUN))

    page.route("**/api/reporting/contribution", _contrib)
    page.route("**/api/reporting/run", _run)
    _run_with_preset(page)

    chip = page.get_by_test_id("rs-kpi-total").get_by_test_id("rp-delta")
    expect(chip).to_have_attribute("data-why", "1")
    chip.click()

    expect(page.get_by_test_id("contrib-head")).to_contain_text("Stub count")
    expect(page.get_by_test_id("contrib-tab")).to_have_count(2)
    rows = page.get_by_test_id("contrib-rows").first.get_by_test_id("contrib-row")
    expect(rows).to_have_count(3)
    expect(rows.first).to_contain_text("acme.inv")
    expect(rows.first).to_contain_text("+83%")
    expect(page.locator("#rdNote")).to_contain_text("status")
    # The posted body is the Simple definition with its token filter intact.
    assert posted and posted[0]["metrics"][0]["metric"] == "stub_count"
    assert any("token" in json.dumps(f) for f in posted[0]["filters"])

    # Second tab swaps the panel.
    page.get_by_test_id("contrib-tab").nth(1).click()
    expect(page.get_by_test_id("contrib-rows").nth(1)).to_be_visible()
    expect(page.get_by_test_id("contrib-rows").first).to_be_hidden()

    # Row click hands over to the drill drawer: one more /run POST with an eq
    # filter on the clicked dimension.
    before = len(runs)
    page.get_by_test_id("contrib-rows").nth(1).get_by_test_id("contrib-row").first.click()
    expect(page.locator("#rdTitle")).to_contain_text("Document type = Invoice")
    expect(page.locator("#rdChips")).to_contain_text("Invoice")   # drill repainted the shell
    assert len(runs) > before
    assert {"field": "doctype", "op": "eq", "value": "Invoice"} in runs[-1]["filters"]


def test_why_chip_shows_server_error(nexora_server, page):
    _login(page, nexora_server)
    _stub_catalogs(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.route("**/api/reporting/contribution", lambda r: r.fulfill(
        status=400, content_type="application/json",
        body=json.dumps({"error": "No comparison window — the report needs exactly one relative-date filter."})))
    page.route("**/api/reporting/run", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(RUN)))
    _run_with_preset(page)
    page.get_by_test_id("rs-kpi-total").get_by_test_id("rp-delta").click()
    expect(page.get_by_test_id("contrib-error")).to_contain_text("No comparison window")
```

`_stub_catalogs` serves `WIZ_STUB_SOURCES`, whose only source `stub_src` has the fields `import_date` (date) and `doctype` (string, filterable) — that is why the drill click above targets the **doctype** tab's row, not the process one (`processname` is not in the stub, and `buildDrillDefinition` returns `null` for an unknown field, which would toast instead of opening).

- [ ] **Step 2: Run it**

Run: `NEXORA_E2E_PORT=5177 pytest tests/e2e/test_reporting_contribution.py -q`
Expected: 2 passed (if no local browser, push to CI and confirm there; say so in the commit body).

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_reporting_contribution.py
git commit -m "test(e2e): contribution drawer opens from the Why? chip and drills through"
```

---

# PHASE 4 — Chores

### Task 8: Unit guard for the JS/template surface

**Files:**
- Test run only.

- [ ] **Step 1: Run the lint-style unit suites that watch templates and JS**

Run: `pytest tests/unit/test_no_inline_event_handlers.py tests/unit/test_template_url_prefix.py tests/unit/test_reporting_i18n_lint.py tests/unit/test_reporting_shared_exports.py -q`
Expected: passed. A failure in `test_template_url_prefix.py` means a URL bypassed `API_PREFIX` — the module uses `window.API_PREFIX + 'api/reporting/contribution'`, which is the sanctioned idiom.

### Task 9: Docs, help panel, changelog

**Files:**
- Modify: `docs/howto/reporting.md`
- Modify: `docs/howto/reporting-guide.md`
- Modify: `templates/_reporting_help.html`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: `docs/howto/reporting.md`** — after the `### Drill-through` section (it ends with the paragraph naming `templates/js/_reporting_drill_js.html` … `static/css/reporting.css`) and before `### Export (Excel / CSV, and what you see)`, insert:

```markdown
### Contribution analysis ("Why did it move?")

When the Simple KPI band shows a **Total** delta chip (see *Comparison & delta
chips*), the chip is a button. Clicking it POSTs the current definition
(tokens intact) to `POST /api/reporting/contribution` and opens the drill
slide-over with one tab per dimension, each listing the values ranked by
their contribution to the change vs. the same shifted prior window the chip
used. Dashboard whole-report cards get the same button because they render
the Simple KPI band.

- **Dimensions** are picked automatically (`pick_dimensions` in
  `nx_lib/reporting/contribution.py`): `processname` first when the source
  has it, then string-typed catalog columns in catalog order, never
  `workitem_id`, never a field an `eq` filter already pins; at most three.
- **Rows** are the first metric grouped by that one column, run once for the
  current window and once for the prior one through the ordinary
  `_prepare_run` path (same grants, source permission and process scope as
  the report), joined on value, sorted by `|delta|`, top 8 plus `(other)`.
  `share` is `delta / (currentTotal − priorTotal)`; it is `null` for ratio
  metrics (`avg`, `min`, `max`, `count_distinct`) and when the total did not
  change. Header totals come from the zero-column clone (`total_definition`),
  so they always equal the band's Total.
- A dimension whose query fails is dropped and listed under `skipped`
  (footer note "Not shown: …"); the endpoint never 500s because one column
  is unqueryable. 400 without metrics or without exactly one relative-date
  token filter; 403 without the source permission.
- Clicking a row opens the normal drill-through for that value on the
  current window (`eq`, or `is_null` for "(empty)"); `(other)` is not
  clickable.

Code: `nx_lib/reporting/contribution.py` (pure), `api_contribution` in
`nx_lib/views/reporting/run.py`, `static/js/reporting_contribution.js` +
shim `templates/js/_reporting_contribution_js.html`, wired in
`static/js/reporting_simple_result.js` and `static/js/reporting_dashboard.js`.
```

- [ ] **Step 2: `docs/howto/reporting-guide.md`** — after the `### Click a bar to see the documents behind it` section's bullet list, add a sibling section:

```markdown
### Click the arrow on the total to see what drove the change

When a report with a time preset shows a small **↑ / ↓ percentage** next to its
total, that chip is a button. Click it and a panel explains the change: one
tab per breakdown (process first, then the source's other categories), each
listing which values moved the number most, with the previous and current
figure, the change, and its share of the total change.

- Click a row to jump to the documents behind that value.
- "(other)" gathers everything outside the top eight.
- Averages and distinct counts show the change but no share — a share of an
  average has no meaning.
```

Also add one bullet to the `## Tips — getting the best results` list next to the existing "Click a chart bar or a table row…" line:

```markdown
- Click the ↑/↓ chip on the total to see which processes or categories drove
  the change since the previous period.
```

- [ ] **Step 3: `templates/_reporting_help.html`** — directly after the `<li>{{ _("Click a chart bar or a table row to open the documents behind that number; …") }}</li>` line add:

```html
        <li>{{ _("Click the ↑/↓ chip on the total to see which processes or categories drove the change since the previous period.") }}</li>
```

- [ ] **Step 4: `CHANGELOG.md`** — under `## [Unreleased]`, add an `### Added` heading if none exists (place it before `### Changed`) with:

```markdown
- **Reporting explains a change ("Why did it move?").** The Total delta chip on
  the Simple KPI band (and on dashboard whole-report cards) is now a button.
  It opens a drawer decomposing the change vs. the prior window by process and
  the source's categorical columns, ranked by contribution, with click-through
  to the documents. New `POST /api/reporting/contribution`; no new permission.
```

- [ ] **Step 5: Run the help-sync and guide tests**

Run: `pytest tests/unit/test_reporting_help_sync.py tests/unit/test_reporting_guide.py -q`
Expected: passed.

- [ ] **Step 6: Commit**

```bash
git add docs/howto/reporting.md docs/howto/reporting-guide.md templates/_reporting_help.html CHANGELOG.md
git commit -m "docs(reporting): contribution analysis — howto, user guide, tips panel, changelog"
```

### Task 10: i18n cycle (de/fr/it)

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` + `.mo`

- [ ] **Step 1: Run the `nx-i18n` skill** (`/nx-i18n`). Fallback commands from `docs/howto/babel.md`:

```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
# translate every new msgid in de/fr/it (no fuzzy left), then
pybabel compile -d translations
```

New msgids: `Why did this change?`, `Why did it change?`, `Contribution to the change vs. the prior period`, `prior`, `current`, `change`, `share of change`, `(other)`, `This source has no columns to break the change down by.`, `Not shown: {fields}`, `Working out what changed…`, `Could not explain this change.`, `Click a row to see the documents behind it.`, `This report has no measure to explain.`, `No comparison window — the report needs exactly one relative-date filter.`, and the tips-panel sentence. After `pybabel update`, diff-sweep the `.po` files for mangled lines (memory: pybabel silently mangles malformed msgstr).

- [ ] **Step 2: Verify**

Run: `pytest tests/unit/test_translations.py -q`
Expected: passed — `.pot` in sync, every msgid translated, none fuzzy.

- [ ] **Step 3: Commit**

```bash
git add messages.pot translations
git commit -m "i18n(reporting): contribution analysis strings (de/fr/it)"
```

### Task 11: Full verification and handoff

- [ ] **Step 1: Fast-tier suite**

Run: `python scripts/test_db_reset.py && pytest tests/unit tests/integration -q`
Expected: passed.

- [ ] **Step 2: INT walkthrough** — restart (`nx -r`), repeat Task 6 Step 3 on a real docprocessing report (e.g. "Documents · This month"), confirm Process tab totals reconcile with the chip (sum of `current` over an un-folded dimension equals the band Total for a `count` metric), take `var/screenshots/contribution_simple.png` and `contribution_dashboard.png`. In a remote session send both with `SendUserFile`.

- [ ] **Step 3: Handoff** — run `/handoff-session-state` (writes the handoff, commits, no push).

---

## Gotchas & notes

- **Token filters must survive to the server.** The Simple pane's `def` (== `RS.state.current.def`) keeps the `{token}` filter; never post the resolved or `compare`-augmented copy. The endpoint calls `shifted_definition_for_comparison(rd)` itself and returns 400 if it finds zero or two token filters.
- **Grouped result row shape** is `[dim_value, metric_value]` because `_prepare_run` returns `rd_columns + metric_result_columns(...)` — one dimension column then the metric. `contribution_rows` relies on that order.
- **`_prepare_run` on the `docprocessing` provider** can raise `ReportDefinitionError` for anchored measures (`imported`/`exported`/`backlog`) combined with `import_date`/`export_date` columns — a single-dimension clone never adds a date column, so an anchored report explains fine; its token filter is on `activity_date`, which the clone keeps.
- **Ratio metrics on the dashboard**: a whole-report card with an `avg` metric shows the chip only when `seriesIsHeadline` holds (see `kpiBandHtml`); the drawer then shows deltas without shares (D4).
- **Drill shell ownership**: after a row click `ReportingContribution` sets `current = null` so its click handlers ignore the drill's DOM; `ReportingDrill.open` repaints `#rdBody`/`#rdChips`/`#rdNote`. Closing via `#rdClose` clears both modules' state.
- **In-flight layouts branch** rewrites parts of `runCurrent`/`renderKpiBand` callers; our listener hangs off `#rsKpiBand` and the `[data-why]` attribute, not off those functions, so it survives a re-render of the band.
- **e2e locally** needs a free port (`NEXORA_E2E_PORT`) and a Playwright browser; an orphan TEST `nx_main` makes every e2e fail with "port in use" — kill it first.
- **Token filter on a `datetime` column (Task 3 tests):** `test_zero_dim_latest_metric_run_constrains_to_latest_bucket` already registers `LastLoginAt` as `"type": "datetime"` with `grainable: True`; if `validate_report_definition` nevertheless rejects the `between` token on it, change the test source's column type to `"date"` — the endpoint code does not change.
- **Never stage** `sql/NexoraDB/**` dumps or `env/*.env` from the worktree.
