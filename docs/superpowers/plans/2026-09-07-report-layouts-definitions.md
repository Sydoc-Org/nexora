# Report layouts ("Report definitions") — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Anchor on **function names and quoted snippets**, never line numbers — re-Grep before every edit.

**Goal:** Let a reporting user author reusable **report definitions** (code name: **layout**) — a bundle of derived measures (current, mean, min/max, range, std dev, percentile) plus a drag-and-drop 12-column tile grid — pick one before building a report, and have that report's result render as the tile grid instead of the fixed KPI band + chart + table.

**Architecture:** A layout is a saved report whose definition has `kind: 'layout'` (the dashboard trick — no migration, no new CRUD endpoint). The Simple pane gets a fifth internal view, the **Report definitions** editor, driven by a new `static/js/reporting_layouts.js` that reuses the dashboard's grid engine, extracted into `static/js/reporting_grid.js`. `/api/reporting/run` loads the referenced layout, computes the derived measures server-side in a new Flask-free `nx_lib/reporting/derived.py`, and echoes `derived` + `layout` in the payload; a shared `static/js/reporting_layout_view.js` renders the tiles in both the Simple and Advanced result views. `/reporting/definitions` is a redirect to `/reporting?tab=definitions`.

**Tech Stack:** Flask + Jinja2, pyodbc raw cursors on `engine_nexora_db` (`dbo.Reports`), Chart.js 4.5.1 (already loaded on `reporting.html`), vanilla JS on `window.NX`, pytest (unit + integration against `NEXORA_TEST`), Playwright e2e (CI-only).

**Spec:** `docs/superpowers/specs/2026-09-07-report-layouts-design.md` — approved 2026-09-07. This plan implements it; the two deviations below (D1, D2) were forced by what the repo actually looks like and stay inside the spec's intent.

## Global Constraints

- **Names.** Code, JSON keys, tests and `docs/howto/reporting.md` say **layout** (`layoutId`, `kind: 'layout'`, `ReportingLayouts`, `derived`). Only user-facing strings say **Report definition** / **Report definitions**. Never introduce a second meaning of "definition" in code — `definition` already is the saved report JSON everywhere.
- **English is the source locale.** Every string enters as `_("…")` in the Jinja shim; `de`/`fr`/`it` come from `/nx-i18n` in Task 15. A `.js` file never contains a user-visible string — it reads `window.NX_I18N_REPORTING_LAYOUTS`.
- Hand-built URLs in JS go through `window.API_PREFIX`; use `window.NX.esc` / `NX.el` / `NX.apiSafe` / `NX.toast`. No inline `onclick=` (`tests/unit/test_no_inline_event_handlers.py`). Every new `static/` asset is referenced via `static_v('…')` (`tests/unit/test_static_v_lint.py`). No Jinja in `static/js/*.js` (`tests/unit/test_template_url_prefix.py::test_no_jinja_syntax_in_static_js`).
- Never un-hide with `style.display`; toggle `el.hidden` (the whole reporting UI does).
- Templates are cached for the process lifetime: `bin/nx.ps1 -r` after every template edit before a browser check.
- **No migrations. No new permission codes** (`reporting.view` gates everything here, exactly like dashboards). **No env keys. No deploy excludes** (every new path is inside `static/`, `templates/`, `nx_lib/`).
- **Commit subjects ≤ 72 chars, conventional type, no trailing period; every commit needs a body** (gitlint `B6`). Use `git commit -F -` with a here-doc. End with the `Co-Authored-By` trailer shown in each task.
- Never `--no-verify`. If the SQL pre-commit hooks block on INT drift from a peer session: `SQL_SYNC_SKIP=1 git commit …`.
- Remote-session policy: commit, never push, never open a PR.
- **Charts v1**: `bar | stacked_bar | line | area | pie | doughnut | gauge` on chart tiles; `sparkline: true` on KPI tiles. Nothing else.
- **Measures v1**: `current | mean | minmax | range | stddev | percentile(q)`. The `OPS` dict is the only place a new op is added later.

---

## Context an engineer needs (read first)

- **Branch / worktree:** planned in `.claude/worktrees/plan-report-layouts` on branch `plan/report-layouts`, cut from `refactor/255-admin-nav-tenancy-labels` @ `49a400c5` (the spec commit). Execute there. Before Task 1 and before any merge back run `git log --oneline HEAD..refactor/255-admin-nav-tenancy-labels`; if non-empty, merge that branch in first — two peer sessions were committing reporting work to it while this plan was written (uncommitted at plan time: `nx_lib/views/reporting/run.py`, `static/js/reporting_simple.js`, `static/js/reporting_advanced.js`, `static/js/reporting_dashboard.js`, `static/css/reporting.css`, `templates/reporting.html`, `templates/js/_reporting_dashboard_js.html`). **Tasks 5–12 touch four of those files** — merge first, re-Grep every anchor.
- **Worktree has no secrets or venv.** `cp ../../../env/INT.env ../../../env/TEST.env env/` before Task 1 (never commit them). Prepend `C:\dev\nexora\.venv\Scripts` to `PATH` for `pytest` / `python`.
- **Run unit tests with `ENVIRONMENT=INT`; integration tests with NO `ENVIRONMENT`:**
  - unit: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" ENVIRONMENT=INT python -m pytest tests/unit/<file> -q`
  - integration: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" python -m pytest tests/integration/<file> -q --no-cov`
  - e2e is CI-only; locally `python -m pytest tests/e2e/<file> -q` needs a free `NEXORA_E2E_PORT` and a fresh `scripts/test_db_reset.py` when the shared `NEXORA_TEST` applock is free.
- **There is no JS unit runner.** `tests/unit/test_reporting_kpi_band.py` and `test_reporting_i18n_lint.py` pin JS behaviour by reading the source with regexes. Node 22 is on the machine, so Task 6 adds one `node -e`-driven test that loads `static/js/reporting_grid.js` into a stub `window` — the first JS behaviour test in the repo; keep it that shape (pure function under test, no DOM library).
- **How saved reports work today.** `dbo.Reports (ReportID, OwnerUserID, Name, DefinitionJSON, Visibility, UpdatedAt)`; CRUD in `nx_lib/views/reporting/reports.py` (`api_reports_list`, `api_reports_get`, `api_reports_create`, `api_reports_update`, `api_reports_delete`). **Nothing validates `definition` on save** — a dashboard is stored as-is and validated only by the client. The list endpoint projects `JSON_VALUE(r.DefinitionJSON, '$.kind') AS Kind`, and every consumer filters on `kind`: `reporting_simple_library.js`'s `loadLibrary` drops `kind !== 'sql'`, `navTo` splits `kind === 'dashboard'`, `_reporting_tabs_js.html` counts dashboards for the rail. A `kind: 'layout'` row therefore needs a filter in each of those places (Task 8) or it shows up as a broken library card.
- **How a run works.** `api_run` in `nx_lib/views/reporting/run.py` calls `_prepare_run(rd)` → `(columns, sql, params, engine)` then `_execute`, builds `payload`, then bolts on `comparison`, `forecast` (`_forecast_for`), `resolvedDates`. Every optional block is wrapped so it can never fail the run. `derived` follows that exact pattern. Integration tests patch `nx_lib.views.reporting.run._prepare_run` / `._execute` (see `test_run_forecast_enabled_returns_block` in `tests/integration/test_reporting_routes.py`).
- **The definition validator** `validate_report_definition` in `nx_lib/reporting/schema.py` is whitelist-based and rejects nothing it does not know about only for `forecast` (checked explicitly). Adding `layoutId` means one explicit check there (Task 3).
- **The dashboard is the precedent for everything UI.** `static/js/reporting_dashboard.js` (~1790 lines, IIFE, `window.ReportingDashboard = {openNew, open, close}`) owns the fourth Simple-pane view `#rsDashboard`, autosaves through `/api/reporting/reports`, and has the grid engine: `renderGrid`, `handleGridDragStart/Over/Drop/DragEnd`, `moveDragged`, `reorderGridDom`, `endDrag`, `handleGridPointerDown`, `handleResizeMove`, `handleResizeEnd`, `cardGeomStyle`, `clampInt`, `GRID_COLS = 12, MAX_ROWS = 6`, CSS `.rdb-grid`, `.rdb-card`, `.rdb-card--dragging`, `.rdb-grid--dragging`, `.rdb-card--resizing`, `.rdb-card-resize` in `static/css/reporting.css`. Its e2e suite `tests/e2e/test_reporting_dashboard.py` (20 tests, incl. `test_edit_mode_drag_reorders_cards_and_persists_on_done` and `test_corner_drag_resizes_card_in_grid_steps_and_persists`) is the regression gate for the grid extraction.
- **The Simple pane's views** are toggled in `setView` in `static/js/reporting_simple.js` (`rsLibrary`, `rsWizard`, `rsResult`, `rsDashboard`; `body.rdb-fullbleed` while the dashboard is open). The Console rail (`templates/js/_reporting_tabs_js.html`, `SCREENS = ['library', 'results', 'dashboards', 'scheduled', 'advanced']`, mirrored in the head script of `templates/reporting.html`) routes screens into the Simple pane via `window.ReportingSimple.navTo(screen)` and follows `rs:viewchanged`.
- **Result rendering** in Simple: `runCurrent` in `reporting_simple.js` posts `cur.def`, then `RS.renderKpiBand(...)`, `RS.mountChart(def, columns, rows, forecast)` (`reporting_simple_chart.js`, whose `buildChartData(def, columns, rows, forecast)` returns `{data: {labels, datasets}, note}`), `RS.renderTable(columns, rows, forecast)` into `#rsTableWrap`. Advanced: `renderResults(data)` in `reporting_advanced.js` → `renderKpiBand`, `ReportingViz.mountChart(document.getElementById('rpChart'), …)`, table into `#rpResults`. The tile view (Task 10) hides those three regions and renders into a new sibling container in each pane.
- **Wizard → definition**: `wizardDefinition()` in `static/js/reporting_simple_wizard.js` returns the v1 object (`schemaVersion: 1, source: w.source.id, visualization: 'table', …`). Advanced: `buildDefinition()` in `reporting_advanced.js`, restored by `applyDefinition(def, name, id)`.
- **Export**: `api_export` in `nx_lib/views/reporting/export.py` → `_serialize_export(columns, rows, title, fmt, chart_png=…, forecast_start=…)` → `rows_to_xlsx` / `rows_to_csv` in `nx_lib/reporting/export.py`. Schedules go through `nx_lib/reporting/runner.py::execute_definition` (no forecast there either) — **schedules are out of scope for `derived` in this plan**; the spec's "for free" claim was wrong for schedules and right for export and captions. Recorded as D5.
- **Docs that must move in the same commits**: `docs/howto/reporting.md` (sections "The Console shell", "Report-definition v1 JSON", new "Report layouts"), `docs/howto/reporting-guide.md` (end-user), `templates/_reporting_help.html` (tips panel — the `reporting-help-sync` hook nags otherwise), `CHANGELOG.md` `[Unreleased] → ### Added`.
- **Migrations needed: NO. i18n needed: YES (Task 15). Deploy excludes: none. Env keys: none.**

## Decisions locked in

| # | Decision | Rationale |
|---|---|---|
| D1 | The editor is a **fifth Simple-pane view** (`#rsLayouts`, screen `definitions`), not a separate template. `/reporting/definitions` is a 302 to `/reporting?tab=definitions`. | The spec asked for an own page; the repo's precedent (dashboards) is a pane inside the Console shell, which already carries Chart.js, the catalogs, the rail and the CSS. A separate template would duplicate ~40 includes and split the Console. The URL the spec named still works. |
| D2 | Layouts are **validated on save** by a small explicit branch in `api_reports_create` / `api_reports_update` (`kind == 'layout'` → `validate_layout_definition`), and **again on run**, where a malformed or foreign layout degrades to Standard with `layoutFallback`. | Today no saved definition is validated server-side. Adding validation only for `kind: 'layout'` keeps dashboards untouched and fulfils the spec's "400 on save". |
| D3 | `derived` works on the **first metric column** (`rd['metrics'][0]['metric']` matched against `columns[i]['field']`), else the first column whose values are all numeric. `current` = the value at the max first-column date when `len(rd['columns']) == 1` and that column has a `grain` or a `/date/` field name, else the sum. | Mirrors `buildChartData`'s `isDate` heuristic so "current" on the KPI tile agrees with the last point on the chart tile. |
| D4 | The grid engine moves to `static/js/reporting_grid.js` as `window.ReportingGrid.attach(gridEl, hooks)`; the dashboard becomes its first consumer with **zero behaviour change**, gated by the existing dashboard e2e. | Spec §3. Copying 150 lines into the layouts module would fork the drag/resize maths the day one of them gets a fix. |
| D5 | `derived` is added to `/api/reporting/run`, `/api/reporting/export` (a **Measures** block under the data) and therefore to the Ask-Eddard context (it posts the run payload). **Scheduled mails do not get it** in this plan. | `runner.py::execute_definition` is a separate pipeline without forecast either; adding layouts there is a follow-up once someone asks. `ponytail:` comment marks the spot. |
| D6 | Tile charts are drawn by `reporting_layout_view.js` **directly with Chart.js** from `(columns, rows)`: first column = labels, every numeric metric column = one dataset. It does not call `RS.mountChart` / `ReportingViz.mountChart`. | Both existing mounters are welded to their pane's DOM (`#rsChartCanvas`, toolbar selects, style popovers). A 60-line standalone builder is smaller than parametrising either. Colours ride `--nx-series-1..5` like the dashboard console. |
| D7 | The layouts editor previews against a **real saved report** chosen from the user's library (`kind` not `sql`/`dashboard`/`layout`), running `/api/reporting/run` with the draft layout inlined as `layout` (not `layoutId`), so an unsaved draft previews without a round trip through save. | Spec §3 "live preview". `api_run` accepts an inline `layout` object **only** when `layoutId` is absent; both are validated by the same function. |
| D8 | Deleting a layout leaves referencing reports alone; their next run gets `layoutFallback: "missing"` and renders Standard with one toast. Sharing a report whose layout the recipient does not own → `layoutFallback: "foreign"`, Standard. | Spec §4/§5. Layouts are private; no cascade. |
| D9 | The picker in the Simple wizard is a select on the **Measure step** footer; in Advanced it sits next to `#rpSavedReports`. Both write `layoutId` (number) or delete the key for Standard. | One control per builder, nothing new to open. |
| D10 | KPI tile sparkline is drawn client-side from `rows` when the report has exactly one dimension and it is a date (same heuristic as D3); otherwise the toggle is ignored silently. | Spec §2 says sparkline data is not computed server-side. |

## Owner actions

- After Task 16 lands, eyeball `var/screenshots/layouts_editor.png`, `layouts_result_tiles.png`, `layouts_picker_wizard.png` (Task 16 produces them, gitignored).
- Decide whether scheduled mails should carry the Measures block (D5) — if yes, open an issue; it is a 20-line change in `nx_lib/reporting/runner.py` plus the mail template.

---

# PHASE 1 — Backend: derived measures + layout schema

### Task 1: `nx_lib/reporting/derived.py` — the six ops

**Files:**
- Create: `nx_lib/reporting/derived.py`
- Test: `tests/unit/test_reporting_derived.py`

**Interfaces:**
- Produces: `compute_derived(layout: dict, rd: dict, columns: list, rows: list) -> dict` mapping `measure id -> {"op": str, "value": float | None, "n": int}` for scalar ops, `{"op": "minmax", "min": float, "max": float, "n": int}` for minmax, or `{"op": str, "unavailable": str}` when it cannot compute. Never raises for data reasons; raises `ValueError` only for a malformed `layout` (callers validate first).
- Produces: `OPS: dict[str, Callable]` and `METRIC_COLUMN_UNAVAILABLE = "no_numeric_column"`.
- Consumes: `nx_lib.reporting.stats._as_numbers`, `_percentile`, `MAX_STATS_ROWS`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_reporting_derived.py
"""Unit tests for nx_lib.reporting.derived — layout measures over a run result.

Pure: no Flask, no DB. Rows are the (columns, rows) shape /api/reporting/run
returns: columns [{field, header}], rows positional.
"""

import math

import pytest

from nx_lib.reporting.derived import compute_derived

COLS = [{"field": "import_date", "header": "Import date"}, {"field": "doc_count", "header": "Docs"}]
ROWS = [["2026-01-01", 10], ["2026-01-02", 20], ["2026-01-03", 30], ["2026-01-04", 40]]
RD = {"columns": [{"field": "import_date", "grain": "day"}], "metrics": [{"metric": "doc_count"}]}


def _layout(*measures):
    return {"kind": "layout", "schemaVersion": 1, "title": "t", "measures": list(measures), "tiles": []}


def test_mean_min_max_range_stddev_percentile_over_metric_column():
    out = compute_derived(
        _layout(
            {"id": "a", "op": "mean"},
            {"id": "b", "op": "minmax"},
            {"id": "c", "op": "range"},
            {"id": "d", "op": "stddev"},
            {"id": "e", "op": "percentile", "q": 0.5},
        ),
        RD, COLS, ROWS,
    )
    assert out["a"] == {"op": "mean", "value": 25.0, "n": 4}
    assert out["b"] == {"op": "minmax", "min": 10.0, "max": 40.0, "n": 4}
    assert out["c"] == {"op": "range", "value": 30.0, "n": 4}
    assert math.isclose(out["d"]["value"], 12.909944, rel_tol=1e-6) and out["d"]["n"] == 4
    assert out["e"] == {"op": "percentile", "value": 25.0, "n": 4, "q": 0.5}


def test_current_is_latest_date_bucket_for_single_date_dimension():
    out = compute_derived(_layout({"id": "cur", "op": "current"}), RD, COLS, ROWS)
    assert out["cur"] == {"op": "current", "value": 40.0, "n": 4}


def test_current_is_sum_when_dimension_is_not_a_date():
    rd = {"columns": [{"field": "doctype"}], "metrics": [{"metric": "doc_count"}]}
    cols = [{"field": "doctype", "header": "Type"}, {"field": "doc_count", "header": "Docs"}]
    out = compute_derived(_layout({"id": "cur", "op": "current"}), rd, cols, ROWS)
    assert out["cur"] == {"op": "current", "value": 100.0, "n": 4}


def test_unknown_metric_falls_back_to_first_numeric_column():
    rd = {"columns": [{"field": "doctype"}], "metrics": []}
    cols = [{"field": "doctype", "header": "Type"}, {"field": "pages", "header": "Pages"}]
    out = compute_derived(_layout({"id": "m", "op": "mean"}), rd, cols, [["A", 2], ["B", 4]])
    assert out["m"]["value"] == 3.0


def test_no_numeric_column_reports_unavailable_per_measure():
    cols = [{"field": "a", "header": "A"}, {"field": "b", "header": "B"}]
    out = compute_derived(_layout({"id": "m", "op": "mean"}), {"columns": [], "metrics": []}, cols, [["x", "y"]])
    assert out["m"] == {"op": "mean", "unavailable": "no_numeric_column"}


def test_empty_rows_reports_unavailable_no_rows():
    out = compute_derived(_layout({"id": "m", "op": "mean"}, {"id": "p", "op": "percentile", "q": 0.9}), RD, COLS, [])
    assert out["m"] == {"op": "mean", "unavailable": "no_rows"}
    assert out["p"] == {"op": "percentile", "unavailable": "no_rows"}


def test_null_and_non_numeric_cells_are_dropped_not_fatal():
    rows = [["2026-01-01", 10], ["2026-01-02", None], ["2026-01-03", "n/a"], ["2026-01-04", 30]]
    out = compute_derived(_layout({"id": "m", "op": "mean"}), RD, COLS, rows)
    assert out["m"] == {"op": "mean", "value": 20.0, "n": 2}


def test_single_row_stddev_is_zero():
    out = compute_derived(_layout({"id": "s", "op": "stddev"}), RD, COLS, ROWS[:1])
    assert out["s"] == {"op": "stddev", "value": 0.0, "n": 1}


def test_too_many_rows_reports_unavailable_rows():
    from nx_lib.reporting.derived import MAX_ROWS

    rows = [["2026-01-01", 1]] * (MAX_ROWS + 1)
    out = compute_derived(_layout({"id": "m", "op": "mean"}), RD, COLS, rows)
    assert out["m"] == {"op": "mean", "unavailable": "too_many_rows"}


def test_unknown_op_raises_value_error():
    with pytest.raises(ValueError):
        compute_derived(_layout({"id": "m", "op": "delta"}), RD, COLS, ROWS)
```

- [ ] **Step 2: Run to verify it fails**

Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" ENVIRONMENT=INT python -m pytest tests/unit/test_reporting_derived.py -q`
Expected: `ModuleNotFoundError: No module named 'nx_lib.reporting.derived'`

- [ ] **Step 3: Implement**

```python
# nx_lib/reporting/derived.py
"""Layout measures: derived statistics over one run result.

A *layout* (a saved report with kind 'layout' — the user-facing "Report
definition") lists measures such as mean / percentile / current value. This
module computes them over the (columns, rows) a report run returned, exactly
like forecast.py post-processes the same rows. Pure stdlib, Flask-free.

Each measure resolves to ``{"op", "value", "n"}`` (``minmax`` → ``min``/``max``)
or ``{"op", "unavailable": reason}``. Data problems never raise — one bad tile
must not take down the run. A malformed layout (unknown op) raises ValueError;
callers validate with schema.validate_layout_definition first.

Adding an op later (delta, growth rate, trend, target gap …) is one entry in
OPS plus a test.
"""

import re
import statistics

from .stats import _percentile

MAX_ROWS = 100_000  # same ceiling as stats.MAX_STATS_ROWS
METRIC_COLUMN_UNAVAILABLE = "no_numeric_column"
_DATE_FIELD = re.compile(r"date", re.I)


def _field(col):
    return col["field"] if isinstance(col, dict) else col


def _is_num(v):
    return isinstance(v, int | float) and not isinstance(v, bool)


def _metric_column_index(rd, columns, rows):
    """Index of the column to measure: the first declared metric, else the
    first column whose non-null cells are all numeric. None when nothing fits."""
    names = [_field(c) for c in columns]
    for m in rd.get("metrics") or []:
        code = m.get("metric") if isinstance(m, dict) else None
        if code in names:
            return names.index(code)
    for i in range(len(names)):
        cells = [r[i] for r in rows if r[i] is not None]
        if cells and all(_is_num(v) for v in cells):
            return i
    return None


def _numbers(rows, idx):
    return [float(r[idx]) for r in rows if _is_num(r[idx])]


def _single_date_dimension(rd):
    cols = rd.get("columns") or []
    if len(cols) != 1 or not isinstance(cols[0], dict):
        return False
    return bool(cols[0].get("grain")) or bool(_DATE_FIELD.search(str(cols[0].get("field", ""))))


def _current(nums, ctx):
    if _single_date_dimension(ctx["rd"]):
        # Latest bucket by the first column's string order (ISO dates sort).
        dated = [(str(r[0]), r[ctx["idx"]]) for r in ctx["rows"] if r[0] is not None and _is_num(r[ctx["idx"]])]
        if dated:
            return float(max(dated)[1])
    return sum(nums)


def _minmax(nums, ctx):
    return {"min": min(nums), "max": max(nums)}


OPS = {
    "current": _current,
    "mean": lambda nums, ctx: statistics.fmean(nums),
    "minmax": _minmax,
    "range": lambda nums, ctx: max(nums) - min(nums),
    "stddev": lambda nums, ctx: statistics.stdev(nums) if len(nums) > 1 else 0.0,
    "percentile": lambda nums, ctx: _percentile(sorted(nums), ctx["measure"].get("q", 0.5)),
}


def compute_derived(layout, rd, columns, rows):
    measures = layout.get("measures") or []
    for m in measures:
        if m.get("op") not in OPS:
            raise ValueError(f"unknown measure op: {m.get('op')!r}")
    out = {}
    if len(rows) > MAX_ROWS:
        return {m["id"]: {"op": m["op"], "unavailable": "too_many_rows"} for m in measures}
    idx = _metric_column_index(rd, columns, rows) if rows else None
    for m in measures:
        if not rows:
            out[m["id"]] = {"op": m["op"], "unavailable": "no_rows"}
            continue
        if idx is None:
            out[m["id"]] = {"op": m["op"], "unavailable": METRIC_COLUMN_UNAVAILABLE}
            continue
        nums = _numbers(rows, idx)
        if not nums:
            out[m["id"]] = {"op": m["op"], "unavailable": METRIC_COLUMN_UNAVAILABLE}
            continue
        res = OPS[m["op"]](nums, {"rd": rd, "rows": rows, "idx": idx, "measure": m})
        entry = {"op": m["op"], "n": len(nums)}
        if isinstance(res, dict):
            entry.update(res)
        else:
            entry["value"] = float(res)
        if m["op"] == "percentile":
            entry["q"] = m.get("q", 0.5)
        out[m["id"]] = entry
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" ENVIRONMENT=INT python -m pytest tests/unit/test_reporting_derived.py -q`
Expected: `10 passed`

- [ ] **Step 5: Lint and commit**

```bash
ruff check nx_lib/reporting/derived.py tests/unit/test_reporting_derived.py && ruff format nx_lib/reporting/derived.py tests/unit/test_reporting_derived.py
git add nx_lib/reporting/derived.py tests/unit/test_reporting_derived.py
git commit -F - <<'EOF'
feat(reporting): derived layout measures over a run result

compute_derived() computes current / mean / minmax / range / stddev /
percentile over the first metric column of a report run, the way forecast.py
post-processes the same rows. Pure stdlib; data problems yield an
"unavailable" entry per measure instead of failing the run. First half of
the report-layouts spec (docs/superpowers/specs/2026-09-07-report-layouts-design.md).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

### Task 2: `validate_layout_definition` in `nx_lib/reporting/schema.py`

**Files:**
- Modify: `nx_lib/reporting/schema.py`
- Test: `tests/unit/test_reporting_schema.py`

**Interfaces:**
- Produces: `validate_layout_definition(layout: dict) -> None`, raises `ReportDefinitionError`. Constants `LAYOUT_OPS = frozenset(OPS)` (imported from `derived`), `LAYOUT_TILE_TYPES = {"kpi", "chart", "table"}`, `LAYOUT_CHARTS = {"bar", "stacked_bar", "line", "area", "pie", "doughnut", "gauge"}`, `LAYOUT_MAX_TILES = 24`, `LAYOUT_MAX_MEASURES = 24`.

- [ ] **Step 1: Write the failing tests** — append to `tests/unit/test_reporting_schema.py`:

```python
from nx_lib.reporting.schema import validate_layout_definition


def _layout(**over):
    base = {
        "kind": "layout",
        "schemaVersion": 1,
        "title": "Ops standard",
        "measures": [{"id": "m1", "op": "current"}, {"id": "m2", "op": "percentile", "q": 0.95}],
        "tiles": [
            {"id": "t1", "type": "kpi", "measure": "m1", "sparkline": True, "span": 3, "rows": 2},
            {"id": "t2", "type": "chart", "chart": "area", "span": 9, "rows": 4},
            {"id": "t3", "type": "table", "span": 12, "rows": 4},
        ],
    }
    base.update(over)
    return base


def test_valid_layout_passes():
    validate_layout_definition(_layout())


@pytest.mark.parametrize(
    "bad, msg",
    [
        ({"kind": "dashboard"}, "kind"),
        ({"schemaVersion": 2}, "schemaVersion"),
        ({"title": ""}, "title"),
        ({"measures": [{"id": "m1", "op": "delta"}]}, "op"),
        ({"measures": [{"id": "m1", "op": "mean"}, {"id": "m1", "op": "mean"}]}, "duplicate"),
        ({"measures": [{"id": "m1", "op": "percentile", "q": 1.5}]}, "q"),
        ({"tiles": [{"id": "t1", "type": "gauge", "span": 3, "rows": 2}]}, "type"),
        ({"tiles": [{"id": "t1", "type": "kpi", "measure": "nope", "span": 3, "rows": 2}]}, "measure"),
        ({"tiles": [{"id": "t1", "type": "chart", "chart": "radar", "span": 3, "rows": 2}]}, "chart"),
        ({"tiles": [{"id": "t1", "type": "table", "span": 13, "rows": 2}]}, "span"),
        ({"tiles": [{"id": "t1", "type": "table", "span": 12, "rows": 0}]}, "rows"),
        ({"tiles": [{"id": "t1", "type": "table", "span": 12, "rows": 1}, {"id": "t1", "type": "table", "span": 12, "rows": 1}]}, "duplicate"),
    ],
)
def test_invalid_layout_rejected(bad, msg):
    with pytest.raises(ReportDefinitionError) as ei:
        validate_layout_definition(_layout(**bad))
    assert msg in str(ei.value)


def test_layout_id_accepted_on_report_definition():
    d = dict(_valid_def(), layoutId=57)
    validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=10000)


@pytest.mark.parametrize("bad", ["57", 0, -1, True, 1.5])
def test_layout_id_must_be_positive_int(bad):
    d = dict(_valid_def(), layoutId=bad)
    with pytest.raises(ReportDefinitionError):
        validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=10000)
```

- [ ] **Step 2: Run to verify it fails**

Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" ENVIRONMENT=INT python -m pytest tests/unit/test_reporting_schema.py -q -k "layout"`
Expected: `ImportError: cannot import name 'validate_layout_definition'`

- [ ] **Step 3: Implement** — in `nx_lib/reporting/schema.py`, after the `GRAINS = {...}` constant add:

```python
# Layouts ("Report definitions" in the UI): a saved report with kind 'layout'
# — derived measures plus a 12-column tile grid a report can render with.
LAYOUT_TILE_TYPES = {"kpi", "chart", "table"}
LAYOUT_CHARTS = {"bar", "stacked_bar", "line", "area", "pie", "doughnut", "gauge"}
LAYOUT_MAX_TILES = 24
LAYOUT_MAX_MEASURES = 24
LAYOUT_GRID_COLS = 12
LAYOUT_MAX_ROWS = 8
```

Inside `validate_report_definition`, directly **before** the block starting `forecast = rd.get("forecast")`, add:

```python
    layout_id = rd.get("layoutId")
    if layout_id is not None and (
        isinstance(layout_id, bool) or not isinstance(layout_id, int) or layout_id < 1
    ):
        raise ReportDefinitionError("layoutId must be a positive integer")
```

After `validate_report_definition` (before `def coerce_definition`) add:

```python
def validate_layout_definition(layout):
    """Validate a kind:'layout' saved definition. Raises ReportDefinitionError.

    Measures reference ops from derived.OPS; tiles reference measures by id.
    Geometry mirrors the dashboard grid (span 1-12, rows 1-8).
    """
    from .derived import OPS  # local import: derived imports stats, never schema

    if not isinstance(layout, dict):
        raise ReportDefinitionError("layout must be an object")
    if layout.get("kind") != "layout":
        raise ReportDefinitionError("kind must be 'layout'")
    sv = layout.get("schemaVersion")
    if isinstance(sv, bool) or sv != REPORT_SCHEMA_VERSION:
        raise ReportDefinitionError(f"schemaVersion must be {REPORT_SCHEMA_VERSION}")
    title = layout.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ReportDefinitionError("title is required")

    measures = layout.get("measures")
    if not isinstance(measures, list) or len(measures) > LAYOUT_MAX_MEASURES:
        raise ReportDefinitionError(f"measures must be a list of at most {LAYOUT_MAX_MEASURES}")
    seen = set()
    for m in measures:
        if not isinstance(m, dict) or not isinstance(m.get("id"), str) or not m["id"]:
            raise ReportDefinitionError("each measure needs a string id")
        if m["id"] in seen:
            raise ReportDefinitionError(f"duplicate measure id: {m['id']!r}")
        seen.add(m["id"])
        if m.get("op") not in OPS:
            raise ReportDefinitionError(f"unknown measure op: {m.get('op')!r}")
        if m["op"] == "percentile":
            q = m.get("q", 0.5)
            if isinstance(q, bool) or not isinstance(q, int | float) or not 0 < q < 1:
                raise ReportDefinitionError("percentile q must be a number in (0, 1)")

    tiles = layout.get("tiles")
    if not isinstance(tiles, list) or len(tiles) > LAYOUT_MAX_TILES:
        raise ReportDefinitionError(f"tiles must be a list of at most {LAYOUT_MAX_TILES}")
    tile_ids = set()
    for t in tiles:
        if not isinstance(t, dict) or not isinstance(t.get("id"), str) or not t["id"]:
            raise ReportDefinitionError("each tile needs a string id")
        if t["id"] in tile_ids:
            raise ReportDefinitionError(f"duplicate tile id: {t['id']!r}")
        tile_ids.add(t["id"])
        if t.get("type") not in LAYOUT_TILE_TYPES:
            raise ReportDefinitionError(f"unknown tile type: {t.get('type')!r}")
        if t["type"] == "kpi" and t.get("measure") not in seen:
            raise ReportDefinitionError(f"kpi tile references unknown measure: {t.get('measure')!r}")
        if t["type"] == "chart" and t.get("chart") not in LAYOUT_CHARTS:
            raise ReportDefinitionError(f"unknown chart type: {t.get('chart')!r}")
        span, rows = t.get("span"), t.get("rows")
        if isinstance(span, bool) or not isinstance(span, int) or not 1 <= span <= LAYOUT_GRID_COLS:
            raise ReportDefinitionError(f"tile span must be an int in [1, {LAYOUT_GRID_COLS}]")
        if isinstance(rows, bool) or not isinstance(rows, int) or not 1 <= rows <= LAYOUT_MAX_ROWS:
            raise ReportDefinitionError(f"tile rows must be an int in [1, {LAYOUT_MAX_ROWS}]")
        if "sparkline" in t and not isinstance(t["sparkline"], bool):
            raise ReportDefinitionError("tile sparkline must be a boolean")
```

- [ ] **Step 4: Run to verify it passes**

Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" ENVIRONMENT=INT python -m pytest tests/unit/test_reporting_schema.py -q`
Expected: all pass (the pre-existing suite plus 19 new).

- [ ] **Step 5: Commit**

```bash
ruff check nx_lib/reporting/schema.py tests/unit/test_reporting_schema.py && ruff format nx_lib/reporting/schema.py tests/unit/test_reporting_schema.py
git add nx_lib/reporting/schema.py tests/unit/test_reporting_schema.py
git commit -F - <<'EOF'
feat(reporting): validate kind:'layout' definitions and layoutId

validate_layout_definition() whitelists measure ops (derived.OPS), tile
types, chart types and the 12x8 grid geometry; validate_report_definition()
accepts an optional positive-int layoutId. No schema change: a layout is a
saved report row like a dashboard.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

### Task 3: Save-time validation for `kind: 'layout'` in `reports.py`

**Files:**
- Modify: `nx_lib/views/reporting/reports.py`
- Test: `tests/integration/test_reporting_routes.py`

**Interfaces:**
- Produces: `POST /api/reporting/reports` and `PUT /api/reporting/reports/<id>` return `400 {"error": "This report definition is invalid.", "detail": "<msg>"}` when `definition.kind == 'layout'` fails `validate_layout_definition`. Every other kind is unchanged.

- [ ] **Step 1: Write the failing tests** — append to `tests/integration/test_reporting_routes.py`:

```python
_LAYOUT_OK = {
    "kind": "layout",
    "schemaVersion": 1,
    "title": "Ops standard",
    "measures": [{"id": "m1", "op": "mean"}],
    "tiles": [{"id": "t1", "type": "kpi", "measure": "m1", "span": 3, "rows": 2}],
}


def test_reports_create_layout_is_validated(admin_client):
    bad = dict(_LAYOUT_OK, measures=[{"id": "m1", "op": "delta"}])
    resp = admin_client.post("/api/reporting/reports", json={"name": "L", "definition": bad})
    assert resp.status_code == 400
    assert "delta" in resp.get_json()["detail"]


def test_reports_create_layout_ok_then_update_is_validated(admin_client):
    resp = admin_client.post("/api/reporting/reports", json={"name": "L", "definition": _LAYOUT_OK})
    assert resp.status_code == 200
    rid = resp.get_json()["id"]
    try:
        bad = dict(_LAYOUT_OK, tiles=[{"id": "t1", "type": "table", "span": 99, "rows": 1}])
        upd = admin_client.put(f"/api/reporting/reports/{rid}", json={"name": "L", "definition": bad})
        assert upd.status_code == 400
        assert "span" in upd.get_json()["detail"]
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid}")
```

- [ ] **Step 2: Run to verify it fails**

Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" python -m pytest tests/integration/test_reporting_routes.py -q --no-cov -k "layout"`
Expected: both FAIL (`400 != 200` / `200 != 400`).

- [ ] **Step 3: Implement** — in `nx_lib/views/reporting/reports.py` add to the imports:

```python
from ...reporting.schema import ReportDefinitionError, validate_layout_definition
```

Add one helper above `api_reports_create`:

```python
def _layout_error(rd):
    """400 body for a malformed kind:'layout' definition, else None. Dashboards
    and report definitions are (still) not validated on save — the run path
    validates them; layouts are validated here because nothing else runs them
    before a report references them."""
    if not isinstance(rd, dict) or rd.get("kind") != "layout":
        return None
    try:
        validate_layout_definition(rd)
    except ReportDefinitionError as e:
        return jsonify({"error": _("This report definition is invalid."), "detail": str(e)}), 400
    return None
```

In **both** `api_reports_create` and `api_reports_update`, directly after the line `definition_json = json.dumps(rd, ensure_ascii=False)` is **preceded** by the `if not name or not isinstance(rd, dict):` check, insert:

```python
    bad = _layout_error(rd)
    if bad:
        return bad
```

- [ ] **Step 4: Run to verify it passes**

Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" python -m pytest tests/integration/test_reporting_routes.py -q --no-cov -k "reports"`
Expected: all `reports` tests pass.

- [ ] **Step 5: Commit**

```bash
ruff check nx_lib/views/reporting/reports.py tests/integration/test_reporting_routes.py
git add nx_lib/views/reporting/reports.py tests/integration/test_reporting_routes.py
git commit -F - <<'EOF'
feat(reporting): reject a malformed layout on save

POST/PUT /api/reporting/reports validate kind:'layout' definitions with
validate_layout_definition and answer 400 + detail. Other kinds keep the
existing save-anything behaviour.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

### Task 4: `/api/reporting/run` resolves the layout and returns `derived` + `layout`

**Files:**
- Modify: `nx_lib/views/reporting/run.py`
- Modify: `nx_lib/views/reporting/_shared.py`
- Test: `tests/integration/test_reporting_routes.py`

**Interfaces:**
- Produces in `_shared.py`: `_load_owned_layout(layout_id, userid) -> dict | None` (the parsed definition when the row exists, is owned by `userid` and has `kind == 'layout'`; else None) and `_layout_block(rd, userid) -> tuple[dict | None, str | None]` returning `(layout, fallback)`: `(layout, None)` when usable, `(None, "missing")` when `layoutId` set but no owned row, `(None, "invalid")` when the stored/inlined layout fails validation, `(None, None)` when neither `layoutId` nor `layout` is present. An inline `rd["layout"]` object is accepted only when `layoutId` is absent (editor preview, D7).
- Produces in the run payload: `layout` (the definition), `derived` (from `compute_derived`) or `layoutFallback: "missing" | "invalid"`.

- [ ] **Step 1: Write the failing tests** — append to `tests/integration/test_reporting_routes.py` (reuse `_FC_COLS`, `_FC_ROWS`, `_FC_DEF` already defined in that file for the forecast tests):

```python
def _create_layout(client, layout=_LAYOUT_OK):
    resp = client.post("/api/reporting/reports", json={"name": "L", "definition": layout})
    assert resp.status_code == 200
    return resp.get_json()["id"]


def test_run_with_owned_layout_returns_layout_and_derived(admin_client):
    rid = _create_layout(admin_client)
    try:
        body = dict(_FC_DEF, layoutId=rid)
        with (
            patch("nx_lib.views.reporting.run._prepare_run", return_value=(_FC_COLS, "SELECT 1", [], None)),
            patch("nx_lib.views.reporting.run._execute", return_value=_FC_ROWS),
        ):
            resp = admin_client.post("/api/reporting/run", json=body)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["layout"]["kind"] == "layout"
        assert data["derived"]["m1"]["op"] == "mean" and "value" in data["derived"]["m1"]
        assert "layoutFallback" not in data
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid}")


def test_run_with_missing_layout_falls_back(admin_client):
    body = dict(_FC_DEF, layoutId=999_999_999)
    with (
        patch("nx_lib.views.reporting.run._prepare_run", return_value=(_FC_COLS, "SELECT 1", [], None)),
        patch("nx_lib.views.reporting.run._execute", return_value=_FC_ROWS),
    ):
        resp = admin_client.post("/api/reporting/run", json=body)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["layoutFallback"] == "missing"
    assert "layout" not in data and "derived" not in data


def test_run_with_foreign_layout_falls_back(admin_client, user_client):
    rid = _create_layout(admin_client)
    try:
        body = dict(_FC_DEF, layoutId=rid)
        with (
            patch("nx_lib.views.reporting.run._prepare_run", return_value=(_FC_COLS, "SELECT 1", [], None)),
            patch("nx_lib.views.reporting.run._execute", return_value=_FC_ROWS),
        ):
            resp = user_client.post("/api/reporting/run", json=body)
        assert resp.status_code == 200
        assert resp.get_json()["layoutFallback"] == "missing"
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid}")


def test_run_with_inline_layout_previews_without_saving(admin_client):
    body = dict(_FC_DEF, layout=_LAYOUT_OK)
    with (
        patch("nx_lib.views.reporting.run._prepare_run", return_value=(_FC_COLS, "SELECT 1", [], None)),
        patch("nx_lib.views.reporting.run._execute", return_value=_FC_ROWS),
    ):
        resp = admin_client.post("/api/reporting/run", json=body)
    assert resp.status_code == 200
    assert resp.get_json()["derived"]["m1"]["op"] == "mean"


def test_run_with_invalid_inline_layout_falls_back_invalid(admin_client):
    body = dict(_FC_DEF, layout=dict(_LAYOUT_OK, measures=[{"id": "m1", "op": "delta"}]))
    with (
        patch("nx_lib.views.reporting.run._prepare_run", return_value=(_FC_COLS, "SELECT 1", [], None)),
        patch("nx_lib.views.reporting.run._execute", return_value=_FC_ROWS),
    ):
        resp = admin_client.post("/api/reporting/run", json=body)
    assert resp.status_code == 200
    assert resp.get_json()["layoutFallback"] == "invalid"
```

Note: `_prepare_run` is patched, so `layoutId` never reaches the validator here; `layoutId` validation is covered in Task 2. Check that `user_client` exists in `tests/conftest.py` (it does: `test_run_invalid_json_returns_400_or_403(user_client)` uses it) and that its user is not `admin@test.local`.

- [ ] **Step 2: Run to verify it fails**

Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" python -m pytest tests/integration/test_reporting_routes.py -q --no-cov -k "layout"`
Expected: the five new tests FAIL with `KeyError: 'layout'` / `'layoutFallback'`.

- [ ] **Step 3: Implement the loader** — in `nx_lib/views/reporting/_shared.py` add to imports `import json` (if absent) and `from ...reporting.schema import ReportDefinitionError, validate_layout_definition` (extend the existing schema import line if one exists), then append:

```python
def _load_owned_layout(layout_id, userid):
    """The parsed kind:'layout' definition `userid` owns under `layout_id`, else None.
    Layouts are private (spec D-ownership): shares and Visibility='shared' do not count."""
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT r.DefinitionJSON FROM dbo.Reports r "
            "WHERE r.ReportID = ? AND r.OwnerUserID = ? "
            "  AND JSON_VALUE(r.DefinitionJSON, '$.kind') = 'layout'",
            (layout_id, userid),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return None


def _layout_block(rd, userid):
    """(layout, fallback) for a run request. `layoutId` wins over an inline
    `layout` (the editor's unsaved-preview path). fallback is 'missing' when the
    id resolves to nothing the caller owns, 'invalid' when the layout fails
    validation, None otherwise."""
    layout_id = rd.get("layoutId")
    if layout_id is not None:
        layout = _load_owned_layout(layout_id, userid)
        if layout is None:
            return None, "missing"
    else:
        layout = rd.get("layout")
        if layout is None:
            return None, None
    try:
        validate_layout_definition(layout)
    except ReportDefinitionError:
        return None, "invalid"
    return layout, None
```

Confirm `engine_nexora_db` is already imported in `_shared.py` (Grep `engine_nexora_db` there; it is used by `_has_acked`).

- [ ] **Step 4: Wire the run** — in `nx_lib/views/reporting/run.py` add `from ...reporting.derived import compute_derived` to the imports and `_layout_block,` to the `from ._shared import (...)` list. In `api_run`, directly **before** the comment `# rd is the original request body (tokens intact)`, insert:

```python
    layout, layout_fallback = _layout_block(rd, session.get("userid"))
    if layout is not None:
        payload["layout"] = layout
        try:
            payload["derived"] = compute_derived(layout, rd, columns, rows)
        except Exception as e:  # a measure must never take down the run
            current_app.logger.warning(f"/api/reporting/run derived skipped: {e}")
    elif layout_fallback:
        payload["layoutFallback"] = layout_fallback
```

Also: `_prepare_run` resolves its own copy of `rd`, but the inline `layout` object rides inside `rd` and must not reach `validate_report_definition` as an unknown key — Grep `_prepare_run` in `_shared.py`; if it copies `rd` with `dict(rd)` and passes it to `validate_report_definition`, the validator ignores unknown keys except `forecast` (it does — no change needed; confirm by reading the function once).

- [ ] **Step 5: Run to verify it passes**

Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" python -m pytest tests/integration/test_reporting_routes.py -q --no-cov -k "run"`
Expected: every `run` test passes, including the five new ones.

- [ ] **Step 6: Commit**

```bash
ruff check nx_lib/views/reporting/run.py nx_lib/views/reporting/_shared.py tests/integration/test_reporting_routes.py
git add nx_lib/views/reporting/run.py nx_lib/views/reporting/_shared.py tests/integration/test_reporting_routes.py
git commit -F - <<'EOF'
feat(reporting): run returns layout + derived measures

/api/reporting/run resolves rd.layoutId to a kind:'layout' report the caller
owns (or accepts an inline layout for the editor preview), validates it, and
echoes `layout` plus `derived` (compute_derived) in the payload. A missing,
foreign or invalid layout degrades to `layoutFallback` so the client renders
Standard — a measure never fails the run.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

### Task 5: Export appends a Measures block

**Files:**
- Modify: `nx_lib/reporting/export.py`
- Modify: `nx_lib/views/reporting/export.py`
- Test: `tests/unit/test_reporting_export.py`, `tests/integration/test_reporting_routes.py`

**Interfaces:**
- Produces: `derived_export_rows(layout, derived, *, header_label) -> list[list]` in `nx_lib/reporting/export.py`: `[[header_label, ""], ["<op label> (id)", value], …]` — one row per measure in layout order, `minmax` as two rows `min`/`max`, unavailable measures as `["…", "—"]`. `rows_to_xlsx` / `rows_to_csv` gain an optional `extra_rows=None` appended after the data with one blank row before it.

- [ ] **Step 1: Write the failing unit tests** — append to `tests/unit/test_reporting_export.py`:

```python
from nx_lib.reporting.export import derived_export_rows


def test_derived_export_rows_lists_measures_in_layout_order():
    layout = {"measures": [{"id": "a", "op": "mean"}, {"id": "b", "op": "minmax"}, {"id": "c", "op": "percentile", "q": 0.9}]}
    derived = {
        "a": {"op": "mean", "value": 2.5, "n": 4},
        "b": {"op": "minmax", "min": 1.0, "max": 4.0, "n": 4},
        "c": {"op": "percentile", "unavailable": "no_rows"},
    }
    rows = derived_export_rows(layout, derived, header_label="Measures")
    assert rows[0] == ["Measures", ""]
    assert rows[1] == ["mean", 2.5]
    assert rows[2] == ["min", 1.0] and rows[3] == ["max", 4.0]
    assert rows[4] == ["percentile 0.9", "—"]


def test_rows_to_csv_appends_extra_rows_after_blank_line():
    columns = [{"field": "a", "header": "A"}]
    text = rows_to_csv(columns, [[1]], extra_rows=[["Measures", ""], ["mean", 1.0]]).decode("utf-8-sig")
    lines = text.splitlines()
    assert lines[0] == "A" and lines[1] == "1"
    assert lines[2] == "" and lines[3].startswith("Measures") and lines[4].startswith("mean")


def test_rows_to_xlsx_appends_extra_rows():
    columns = [{"field": "a", "header": "A"}]
    data = rows_to_xlsx(columns, [[1]], title="T", extra_rows=[["Measures", ""], ["mean", 1.0]])
    ws = load_workbook(io.BytesIO(data)).active
    # header row 4, data row 5, blank 6, block from 7
    assert ws["A7"].value == "Measures" and ws["A7"].font.bold
    assert ws["A8"].value == "mean" and ws["B8"].value == 1.0
```

`rows_to_csv` returns BOM-prefixed UTF-8 bytes (`return ("﻿" + buf.getvalue()).encode("utf-8")`), so `.decode("utf-8-sig")` above is right.

- [ ] **Step 2: Run to verify it fails**

Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" ENVIRONMENT=INT python -m pytest tests/unit/test_reporting_export.py -q -k "derived or extra_rows"`
Expected: `ImportError` / `TypeError: unexpected keyword 'extra_rows'`.

- [ ] **Step 3: Implement** — in `nx_lib/reporting/export.py`:

Add after `_safe_cell`:

```python
def derived_export_rows(layout, derived, *, header_label):
    """Two-column block for a layout's measures: [[header, ''], [label, value], …]."""
    out = [[header_label, ""]]
    for m in layout.get("measures") or []:
        d = derived.get(m["id"]) or {}
        label = m["op"] if m["op"] != "percentile" else f"percentile {m.get('q', 0.5)}"
        if d.get("unavailable") or not d:
            out.append([label, "—"])
        elif m["op"] == "minmax":
            out.append(["min", d.get("min")])
            out.append(["max", d.get("max")])
        else:
            out.append([label, d.get("value")])
    return out
```

In `rows_to_xlsx` add the keyword `extra_rows=None` to the signature and, after the data-rows loop (the `for r_off, row in enumerate(row_list, start=1):` block) and before `ws.freeze_panes = …`, insert:

```python
    if extra_rows:
        start = header_row + len(row_list) + 2  # one blank row after the data
        for i, extra in enumerate(extra_rows):
            for c_off, val in enumerate(extra, start=1):
                cell = ws.cell(row=start + i, column=c_off, value=_safe_cell(val))
                if i == 0:
                    cell.font = header_font
```

In `rows_to_csv` add `extra_rows=None` and, after the data rows are written, write an empty row then each extra row through the same writer (read the function body first; it uses `csv.writer` — call `w.writerow([])` then `w.writerow([_safe_cell(v) for v in extra])` per row).

In `nx_lib/views/reporting/export.py`: import `from ...reporting.derived import compute_derived`, `from ...reporting.export import derived_export_rows` (extend the existing `from ...reporting.export import …` line), and add `_layout_block` to the `._shared` import. In `api_export`, after the forecast block and before the final `return _serialize_export(...)`, insert:

```python
    extra_rows = None
    layout, _fallback = _layout_block(rd, session.get("userid"))
    if layout is not None:
        try:
            derived = compute_derived(layout, rd, columns, rows)
            extra_rows = derived_export_rows(layout, derived, header_label=_("Measures"))
        except Exception as e:
            current_app.logger.warning(f"/api/reporting/export derived skipped: {e}")
```

and pass `extra_rows=extra_rows` into that `_serialize_export(...)` call; thread `extra_rows=None` through `_serialize_export` into both `rows_to_xlsx(...)` and `rows_to_csv(...)` calls (read `_serialize_export` first — it lives in the same views module).

Add one integration test to `tests/integration/test_reporting_routes.py`:

```python
def test_export_csv_appends_measures_block_for_layout(admin_client):
    rid = _create_layout(admin_client)
    try:
        body = dict(_FC_DEF, format="csv", layoutId=rid)
        with (
            patch("nx_lib.views.reporting.export._prepare_run", return_value=(_FC_COLS, "SELECT 1", [], None)),
            patch("nx_lib.views.reporting.export._execute", return_value=_FC_ROWS),
        ):
            resp = admin_client.post("/api/reporting/export", json=body)
        assert resp.status_code == 200
        text = resp.data.decode("utf-8-sig")
        assert "Measures" in text and "\nmean," in text.replace("\r", "")
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid}")
```

- [ ] **Step 4: Run to verify it passes**

Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" ENVIRONMENT=INT python -m pytest tests/unit/test_reporting_export.py -q && PATH="/c/dev/nexora/.venv/Scripts:$PATH" python -m pytest tests/integration/test_reporting_routes.py -q --no-cov -k "export"`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
ruff check nx_lib/reporting/export.py nx_lib/views/reporting/export.py tests/unit/test_reporting_export.py tests/integration/test_reporting_routes.py
git add nx_lib/reporting/export.py nx_lib/views/reporting/export.py tests/unit/test_reporting_export.py tests/integration/test_reporting_routes.py
git commit -F - <<'EOF'
feat(reporting): export carries the layout's Measures block

xlsx/csv exports of a report that references a layout append a two-column
Measures block (one row per derived measure) under the data, so the numbers
on the tiles travel with the file.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

# PHASE 2 — Frontend: grid engine extraction

### Task 6: Extract the grid engine into `static/js/reporting_grid.js`

**Files:**
- Create: `static/js/reporting_grid.js`
- Modify: `static/js/reporting_dashboard.js`
- Modify: `templates/js/_reporting_dashboard_js.html`
- Test: `tests/unit/test_reporting_grid_js.py` (new — Node-driven)

**Interfaces:**
- Produces `window.ReportingGrid`:
  - `attach(gridEl, hooks)` → `{ detach() }`. `hooks = { cols: 12, maxRows: 6, isEditing: () => bool, items: () => array, findItem: (id) => item, findEl: (id) => HTMLElement|null, onReorder: (fromIndex, toIndex) => void, onResize: (item, span, rows) => void, geomStyle: (span, rows) => string, resizeHandleSelector: '[data-testid="rdb-card-resize"]', itemAttr: 'data-card-id', addTileSelector: '[data-testid="rdb-add-tile"]' }`. It wires `dragstart/dragover/drop/dragend` and `pointerdown` on `gridEl`, keeps its own `dragId/overId/resizing` state, and calls the hooks; it never touches the caller's model except through `onReorder`/`onResize`.
  - `clampInt(v, lo, hi, dflt)`, `geomStyle(span, rows)` (the current `cardGeomStyle` body), `moveIndex(list, from, to)` (pure splice helper) — exported for tests and for the layouts module.
- The dashboard keeps the identical DOM, classes, test ids and behaviour.

- [ ] **Step 1: Write the failing Node test** — `tests/unit/test_reporting_grid_js.py`:

```python
"""static/js/reporting_grid.js: the pure helpers the drag/resize engine is
built on, run under Node (the repo has no JS test runner; see
test_reporting_kpi_band.py for the read-the-source alternative)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path("static/js/reporting_grid.js")
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

_HARNESS = """
const fs = require('fs');
global.window = {};
global.document = { addEventListener() {} };
eval(fs.readFileSync(process.argv[1], 'utf8'));
const G = window.ReportingGrid;
const out = {
  clamp: [G.clampInt('7', 1, 12, 6), G.clampInt(0, 1, 12, 6), G.clampInt('x', 1, 12, 6), G.clampInt(13, 1, 12, 6)],
  geom: G.geomStyle(8, 3),
  fwd: G.moveIndex(['a', 'b', 'c', 'd'], 0, 2),
  back: G.moveIndex(['a', 'b', 'c', 'd'], 3, 1),
  same: G.moveIndex(['a', 'b'], 1, 1),
};
process.stdout.write(JSON.stringify(out));
"""


def _run():
    res = subprocess.run([NODE, "-e", _HARNESS, str(SRC)], capture_output=True, text=True, check=True)
    return json.loads(res.stdout)


def test_clamp_int_parses_and_bounds():
    assert _run()["clamp"] == [7, 1, 6, 12]


def test_geom_style_matches_dashboard_css_contract():
    assert _run()["geom"] == "grid-column:span 8;--rdb-cardrows:3"


def test_move_index_forward_lands_after_hovered_and_backward_before():
    out = _run()
    assert out["fwd"] == ["b", "c", "a", "d"]
    assert out["back"] == ["a", "d", "b", "c"]
    assert out["same"] == ["a", "b"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" ENVIRONMENT=INT python -m pytest tests/unit/test_reporting_grid_js.py -q`
Expected: FAIL (`ENOENT` on the missing file).

- [ ] **Step 3: Create `static/js/reporting_grid.js`**

```js
// Shared 12-column tile grid engine: HTML5 drag-to-reorder + Pointer-Events
// corner resize, lifted out of reporting_dashboard.js so the dashboard and the
// report-definitions editor (reporting_layouts.js) share one set of drag maths
// and one CSS contract (.rdb-grid / .rdb-card / --rdb-cardrows in reporting.css).
//
// The engine owns only transient drag state. The caller's model is reached
// through hooks: items(), findItem(id), findEl(id), onReorder(from, to),
// onResize(item, span, rows). Nothing here reads window.NX or i18n.
(function () {
  'use strict';

  function clampInt(v, lo, hi, dflt) {
    var n = parseInt(v, 10);
    if (!isFinite(n)) n = dflt;
    return Math.max(lo, Math.min(hi, n));
  }

  function geomStyle(span, rows) {
    return 'grid-column:span ' + span + ';--rdb-cardrows:' + rows;
  }

  // Splice `from` out and insert at `to` read off the PRE-removal array: a
  // forward drag lands after the hovered item, a backward drag before it.
  function moveIndex(list, from, to) {
    var out = list.slice();
    if (from < 0 || to < 0 || from === to || from >= out.length || to >= out.length) return out;
    out.splice(to, 0, out.splice(from, 1)[0]);
    return out;
  }

  function attach(gridEl, hooks) {
    var cols = hooks.cols || 12, maxRows = hooks.maxRows || 6;
    var itemAttr = hooks.itemAttr || 'data-card-id';
    var handleSel = hooks.resizeHandleSelector || '[data-testid="rdb-card-resize"]';
    var addTileSel = hooks.addTileSelector || '[data-testid="rdb-add-tile"]';
    var dragId = null, overId = null, resizing = null;

    function idOf(target) {
      var el = target && target.closest && target.closest('[' + itemAttr + ']');
      return el ? el.getAttribute(itemAttr) : null;
    }
    function indexOf(id) {
      var list = hooks.items();
      for (var i = 0; i < list.length; i++) if (list[i].id === id) return i;
      return -1;
    }
    function reorderDom() {
      var addTile = gridEl.querySelector(addTileSel);
      hooks.items().forEach(function (it) {
        var node = hooks.findEl(it.id);
        if (node) gridEl.insertBefore(node, addTile || null);
      });
    }
    function endDrag() {
      var dragEl = dragId && hooks.findEl(dragId);
      if (dragEl) dragEl.classList.remove('rdb-card--dragging');
      gridEl.classList.remove('rdb-grid--dragging');
      dragId = null; overId = null;
    }

    function onDragStart(e) {
      if (resizing || (e.target.closest && e.target.closest(handleSel))) { e.preventDefault(); return; }
      var id = idOf(e.target);
      if (!hooks.isEditing() || !id) return;
      dragId = id; overId = null;
      if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
      hooks.findEl(id).classList.add('rdb-card--dragging');
      gridEl.classList.add('rdb-grid--dragging');
    }
    function onDragOver(e) {
      if (!hooks.isEditing() || !dragId) return;
      var id = idOf(e.target);
      if (!id) return;
      e.preventDefault();
      if (id === dragId || id === overId) return;
      overId = id;
      var fi = indexOf(dragId), ti = indexOf(id);
      if (fi < 0 || ti < 0 || fi === ti) return;
      hooks.onReorder(fi, ti);
      reorderDom();
    }
    function onDrop(e) { if (hooks.isEditing() && dragId) { e.preventDefault(); endDrag(); } }
    function onDragEnd() { endDrag(); }

    function pxVar(name, dflt) {
      var n = parseFloat(getComputedStyle(gridEl).getPropertyValue(name));
      return isFinite(n) && n > 0 ? n : dflt;
    }
    function onPointerDown(e) {
      var handle = e.target.closest && e.target.closest(handleSel);
      if (!hooks.isEditing() || !handle) return;
      var id = idOf(handle), item = id && hooks.findItem(id), itemEl = id && hooks.findEl(id);
      if (!item || !itemEl) return;
      e.preventDefault();
      var gap = pxVar('--rdb-gap', 14), gridW = gridEl.getBoundingClientRect().width;
      var span = clampInt(item.span, 1, cols, 6), rows = clampInt(item.rows, 1, maxRows, 2);
      resizing = { item: item, el: itemEl, x: e.clientX, y: e.clientY, span: span, rows: rows,
                   nextSpan: span, nextRows: rows,
                   colStep: (gridW - gap * (cols - 1)) / cols + gap, rowStep: pxVar('--rdb-row', 118) + gap };
      itemEl.classList.add('rdb-card--resizing');
      window.addEventListener('pointermove', onResizeMove);
      window.addEventListener('pointerup', onResizeEnd);
    }
    function onResizeMove(e) {
      if (!resizing) return;
      var span = clampInt(resizing.span + Math.round((e.clientX - resizing.x) / resizing.colStep), 1, cols, resizing.span);
      var rows = clampInt(resizing.rows + Math.round((e.clientY - resizing.y) / resizing.rowStep), 1, maxRows, resizing.rows);
      if (span === resizing.nextSpan && rows === resizing.nextRows) return;
      resizing.nextSpan = span; resizing.nextRows = rows;
      resizing.el.setAttribute('style', (hooks.geomStyle || geomStyle)(span, rows));
    }
    function onResizeEnd() {
      if (!resizing) return;
      var r = resizing; resizing = null;
      window.removeEventListener('pointermove', onResizeMove);
      window.removeEventListener('pointerup', onResizeEnd);
      r.el.classList.remove('rdb-card--resizing');
      if (r.nextSpan === r.span && r.nextRows === r.rows) return;
      hooks.onResize(r.item, r.nextSpan, r.nextRows);
    }

    gridEl.addEventListener('dragstart', onDragStart);
    gridEl.addEventListener('dragover', onDragOver);
    gridEl.addEventListener('drop', onDrop);
    gridEl.addEventListener('dragend', onDragEnd);
    gridEl.addEventListener('pointerdown', onPointerDown);
    return {
      detach: function () {
        gridEl.removeEventListener('dragstart', onDragStart);
        gridEl.removeEventListener('dragover', onDragOver);
        gridEl.removeEventListener('drop', onDrop);
        gridEl.removeEventListener('dragend', onDragEnd);
        gridEl.removeEventListener('pointerdown', onPointerDown);
      },
      isResizing: function () { return !!resizing; }
    };
  }

  window.ReportingGrid = { attach: attach, clampInt: clampInt, geomStyle: geomStyle, moveIndex: moveIndex };
}());
```

- [ ] **Step 4: Run the Node test**

Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" ENVIRONMENT=INT python -m pytest tests/unit/test_reporting_grid_js.py -q`
Expected: `3 passed`

- [ ] **Step 5: Switch the dashboard to the engine** — in `static/js/reporting_dashboard.js`:
  1. Replace the body of `clampInt` with `return window.ReportingGrid.clampInt(v, lo, hi, dflt);` and the body of `cardGeomStyle` with `return window.ReportingGrid.geomStyle(span, rows);`.
  2. Delete `handleGridDragStart`, `handleGridDragOver`, `reorderGridDom`, `moveDragged`, `endDrag`, `handleGridDrop`, `handleGridDragEnd`, `var resizing = null;`, `pxVar`, `handleGridPointerDown`, `handleResizeMove`, `handleResizeEnd`. Keep `cardResizeHandleHtml`.
  3. In `ensureShell`, replace the five `el('rdbGrid').addEventListener('dragstart'|'dragover'|'drop'|'dragend'|'pointerdown', …)` lines (Grep `addEventListener('dragstart', handleGridDragStart)`) with:

```js
    window.ReportingGrid.attach(el('rdbGrid'), {
      cols: GRID_COLS, maxRows: MAX_ROWS,
      isEditing: function () { return state.editing; },
      items: function () { return (state.def && state.def.cards) || []; },
      findItem: findCardById,
      findEl: findCardEl,
      onReorder: function (from, to) {
        state.def.cards = window.ReportingGrid.moveIndex(state.def.cards, from, to);
        state.dirty = true;
      },
      onResize: function (card, span, rows) { card.span = span; card.rows = rows; state.dirty = true; },
      geomStyle: cardGeomStyle
    });
```

  4. Grep for any remaining reference to `state.dragId`, `state.overId`, `resizing` in the file and remove the two `dragId: null, overId: null` initialisers in `state` plus the two reset lines in `openNew` / `open` (Grep `state.dragId = null`).
  5. In `templates/js/_reporting_dashboard_js.html`, directly above the line `<script src="{{ static_v('js/reporting_dashboard.js') }}"></script>` add `<script src="{{ static_v('js/reporting_grid.js') }}"></script>`.

- [ ] **Step 6: Run the lints and the dashboard e2e**

Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" ENVIRONMENT=INT python -m pytest tests/unit/test_template_url_prefix.py tests/unit/test_static_v_lint.py tests/unit/test_no_inline_event_handlers.py -q`
Expected: pass.

Run (needs a free port and a seeded `NEXORA_TEST`): `PATH="/c/dev/nexora/.venv/Scripts:$PATH" NEXORA_E2E_PORT=8791 python -m pytest tests/e2e/test_reporting_dashboard.py -q -k "drag_reorders or corner_drag_resizes or duplicate_button or remove_button"`
Expected: `4 passed`. If the shared TEST DB is locked, run the whole dashboard e2e file in CI after the push and do not proceed to Task 7 until it is green.

- [ ] **Step 7: Commit**

```bash
git add static/js/reporting_grid.js static/js/reporting_dashboard.js templates/js/_reporting_dashboard_js.html tests/unit/test_reporting_grid_js.py
git commit -F - <<'EOF'
refactor(reporting): extract the dashboard grid engine into reporting_grid.js

window.ReportingGrid.attach(gridEl, hooks) owns drag-to-reorder and corner
resize; the dashboard is its first consumer with identical DOM, classes and
test ids. The report-definitions editor reuses it next. Pure helpers
(clampInt, geomStyle, moveIndex) get the repo's first Node-driven JS test.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

# PHASE 3 — Frontend: the editor view

### Task 7: Fifth Simple-pane view + Console screen `definitions` + `/reporting/definitions` redirect

**Files:**
- Modify: `templates/_reporting_simple.html`
- Modify: `templates/reporting.html`
- Modify: `templates/js/_reporting_tabs_js.html`
- Modify: `static/js/reporting_simple.js`
- Modify: `nx_lib/views/reporting/pages.py`
- Test: `tests/integration/test_reporting_routes.py`

**Interfaces:**
- Produces: `<div id="rsLayouts" class="reporting-layouts" hidden data-testid="rs-layouts">` as a sibling of `#rsDashboard`; `setView('layouts')` shows it; `navTo('definitions')` opens it via `window.ReportingLayouts.open()` (Task 8); rail button `#rcNavDefinitions` with `data-screen="definitions"` and count `#rcNavDefinitionsCount`; `SCREENS` includes `'definitions'` in both the head script and the tabs controller; `GET /reporting/definitions` → 302 `/reporting?tab=definitions`.

- [ ] **Step 1: Write the failing integration test** — append to `tests/integration/test_reporting_routes.py`:

```python
def test_reporting_definitions_redirects_into_the_console(admin_client):
    resp = admin_client.get("/reporting/definitions")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/reporting?tab=definitions")


def test_reporting_definitions_requires_reporting_view(client):
    resp = client.get("/reporting/definitions")
    assert resp.status_code in (302, 401, 403)
    assert "tab=definitions" not in (resp.headers.get("Location") or "")
```

- [ ] **Step 2: Run to verify it fails**

Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" python -m pytest tests/integration/test_reporting_routes.py -q --no-cov -k "definitions"`
Expected: first test FAILS with 404.

- [ ] **Step 3: Route** — in `nx_lib/views/reporting/pages.py` add `redirect, url_for` to the `from flask import …` line and, after `def reporting():`'s function, add:

```python
@require_permission("reporting.view")
def reporting_definitions():
    """The report-definitions editor lives inside the Console shell as a
    Simple-pane view (like dashboards); this URL just opens that screen."""
    return redirect(url_for("reporting", tab="definitions"))
```

and in `register_routes` add:

```python
    app.add_url_rule(
        "/reporting/definitions", endpoint="reporting_definitions", view_func=reporting_definitions
    )
```

- [ ] **Step 4: Templates** — in `templates/_reporting_simple.html`, directly after the `#rsDashboard` div add:

```html
  {# Report-definitions editor (kind:'layout' saved reports). Empty by design:
     window.ReportingLayouts (js/_reporting_layouts_js.html) renders into it. #}
  <div id="rsLayouts" class="reporting-layouts" hidden data-testid="rs-layouts"></div>
```

In `templates/reporting.html`:
  - head script: change `var SCREENS = ['library', 'results', 'dashboards', 'scheduled', 'advanced'];` to `var SCREENS = ['library', 'results', 'dashboards', 'definitions', 'scheduled', 'advanced'];`
  - rail: directly after the `#rcNavDashboards` button add:

```html
        <button type="button" id="rcNavDefinitions" class="rc-nav" data-screen="definitions" data-testid="rc-nav-definitions">
          <i class="fas fa-sliders" aria-hidden="true"></i>{{ _("Report definitions") }}<span class="rc-nav-count" id="rcNavDefinitionsCount"></span></button>
```

In `templates/js/_reporting_tabs_js.html`:
  - same `SCREENS` change;
  - in the `rs:viewchanged` listener change the `screen` expression to `var screen = v === 'result' ? 'results' : v === 'dashboard' ? 'dashboards' : v === 'layouts' ? 'definitions' : 'library';`
  - in the `rs:libraryloaded` listener, after `var dash = …` add `var lay = reports.filter(function (r) { return r.kind === 'layout'; }).length;`, change the Library count to `String(reports.length - dash - lay)`, and set `var ld = el('rcNavDefinitionsCount'); if (ld) ld.textContent = String(lay);`

In `static/js/reporting_simple.js`:
  - `setView`: after `RS.el('rsDashboard').hidden = view !== 'dashboard';` add `RS.el('rsLayouts').hidden = view !== 'layouts';` and change the full-bleed toggle to `document.body.classList.toggle('rdb-fullbleed', view === 'dashboard' || view === 'layouts');`
  - `navTo`: after the `if (screen === 'dashboards') {…}` block add:

```js
    if (screen === 'definitions') {
      if (RS.state.view === 'layouts') return;
      setView('layouts');
      if (window.ReportingLayouts) window.ReportingLayouts.open();
    }
```

  - in `navTo`'s `results` branch, change the filter to `x.kind !== 'dashboard' && x.kind !== 'layout'`.

- [ ] **Step 5: Verify**

Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" python -m pytest tests/integration/test_reporting_routes.py -q --no-cov -k "definitions"` → `2 passed`.
Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" ENVIRONMENT=INT python -m pytest tests/unit/test_template_url_prefix.py tests/unit/test_create_app.py -q` → pass (the route inventory test, if it enumerates endpoints, needs `reporting_definitions` added — read the failure).

- [ ] **Step 6: Commit**

```bash
git add nx_lib/views/reporting/pages.py templates/_reporting_simple.html templates/reporting.html templates/js/_reporting_tabs_js.html static/js/reporting_simple.js tests/integration/test_reporting_routes.py
git commit -F - <<'EOF'
feat(reporting): Report definitions screen in the Console rail

Fifth Simple-pane view #rsLayouts, rail entry + count, screen name
'definitions' in both SCREENS lists, and /reporting/definitions redirecting
into it. The editor module lands in the next commit; this one only opens
the door.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

### Task 8: `static/js/reporting_layouts.js` — list, editor, autosave, preview

**Files:**
- Create: `static/js/reporting_layouts.js`
- Create: `templates/js/_reporting_layouts_js.html`
- Modify: `templates/_reporting_simple.html` (include the shim after the dashboard shim)
- Modify: `static/js/reporting_simple_library.js`
- Modify: `static/css/reporting.css`

**Interfaces:**
- Produces `window.ReportingLayouts = { open, openNew, openLayout(report), close }` and `window.NX_I18N_REPORTING_LAYOUTS` (shim). The module lists the user's `kind === 'layout'` reports (from `RS.state.reports`, which `loadLibrary` must stop filtering out — see step 4), and renders an editor: header (title input, **Done/Edit**, **New definition**, **Delete**), left rail with the measure palette and tile palette, a `.rdb-grid` of tiles wired through `ReportingGrid.attach`, and a **Preview with** select of the user's runnable reports.
- Layout object as in the spec. Default new layout: `{kind:'layout', schemaVersion:1, title: I18N.untitled, measures:[{id:'m1',op:'current'}], tiles:[{id:'t1',type:'kpi',measure:'m1',span:3,rows:2},{id:'t2',type:'chart',chart:'bar',span:9,rows:4},{id:'t3',type:'table',span:12,rows:4}]}`.
- Consumes: `window.ReportingGrid` (Task 6), `window.ReportingLayoutView` (Task 9 — until then the tiles render as labelled placeholders; the module must check `window.ReportingLayoutView` exists), `NX.apiSafe`, `/api/reporting/reports` CRUD, `/api/reporting/run` with the inline `layout` for the preview (D7).

- [ ] **Step 1: The i18n shim** — create `templates/js/_reporting_layouts_js.html`:

```html
<script nonce="{{ csp_nonce() }}">
  // Jinja-rendered strings for static/js/reporting_layouts.js (#191).
  window.NX_I18N_REPORTING_LAYOUTS = {
    title: {{ _("Report definitions")|tojson }},
    intro: {{ _("A report definition is a set of measures and a tile layout you pick before building a report. Standard is the built-in one.")|tojson }},
    newDefinition: {{ _("New definition")|tojson }},
    untitled: {{ _("Untitled definition")|tojson }},
    edit: {{ _("Edit")|tojson }},
    done: {{ _("Done")|tojson }},
    delete_: {{ _("Delete")|tojson }},
    confirmDelete: {{ _("Delete this report definition? Reports using it fall back to Standard.")|tojson }},
    saved: {{ _("Definition saved")|tojson }},
    saveFailed: {{ _("Could not save the definition")|tojson }},
    measures: {{ _("Measures")|tojson }},
    tiles: {{ _("Tiles")|tojson }},
    addChart: {{ _("Add chart")|tojson }},
    addTable: {{ _("Add table")|tojson }},
    previewWith: {{ _("Preview with")|tojson }},
    previewNone: {{ _("No saved report to preview with — build one in the Library first.")|tojson }},
    previewFailed: {{ _("Preview could not run — the layout still saves.")|tojson }},
    removeTile: {{ _("Remove tile")|tojson }},
    resizeTile: {{ _("Drag to resize")|tojson }},
    sparkline: {{ _("Sparkline")|tojson }},
    percentileQ: {{ _("Percentile")|tojson }},
    tilesMeta: {{ _("{n} tiles · drag to rearrange · drag a corner to resize")|tojson }},
    op: {
      current: {{ _("Current value")|tojson }},
      mean: {{ _("Mean")|tojson }},
      minmax: {{ _("Min / Max")|tojson }},
      range: {{ _("Range")|tojson }},
      stddev: {{ _("Standard deviation")|tojson }},
      percentile: {{ _("Percentile")|tojson }}
    },
    chart: {
      bar: {{ _("Bar")|tojson }},
      stacked_bar: {{ _("Stacked bar")|tojson }},
      line: {{ _("Line")|tojson }},
      area: {{ _("Area")|tojson }},
      pie: {{ _("Pie")|tojson }},
      doughnut: {{ _("Doughnut")|tojson }},
      gauge: {{ _("Gauge")|tojson }}
    },
    table: {{ _("Table")|tojson }},
    unavailable: {{ _("Not available for this report")|tojson }},
    standard: {{ _("Standard")|tojson }}
  };
</script>
<script src="{{ static_v('js/reporting_grid.js') }}"></script>
<script src="{{ static_v('js/reporting_layout_view.js') }}"></script>
<script src="{{ static_v('js/reporting_layouts.js') }}"></script>
```

In `templates/_reporting_simple.html`, after `{% include 'js/_reporting_dashboard_js.html' %}` add `{% include 'js/_reporting_layouts_js.html' %}`. Remove the `reporting_grid.js` script tag added to `_reporting_dashboard_js.html` in Task 6 **only if** the dashboard shim is included after the layouts shim — it is not (dashboard first), so leave both; `static_v` scripts are idempotent IIFEs and the second load just reassigns `window.ReportingGrid`. Simpler: keep the grid script in the dashboard shim (loads first) and **drop** the grid line from the layouts shim. Do that.

- [ ] **Step 2: Library filters** — in `static/js/reporting_simple_library.js`:
  - `loadLibrary`: `RS.state.reports` keeps every kind except `sql` (unchanged), but the card grouping must skip layouts. Grep the function that buckets reports into `rsGroupMine/rsGroupShared/rsGroupDirect` (it iterates `RS.state.reports`) and add `if (r.kind === 'layout') return;` at the top of its per-report callback.
  - the card click handler (`if (r.kind === 'dashboard') { openDashboard(r); return; }`): add `if (r.kind === 'layout') { RS.setView('layouts'); window.ReportingLayouts.openLayout(r); return; }` — defensive only, layouts no longer render cards.

- [ ] **Step 3: The module** — create `static/js/reporting_layouts.js`:

```js
// Report-definitions editor (a "layout": kind:'layout' saved report).
// Lives in the Simple pane's #rsLayouts view like the dashboard builder.
// Model: { kind:'layout', schemaVersion:1, title, measures:[{id,op,q?}],
//          tiles:[{id,type:'kpi'|'chart'|'table', measure?, chart?, sparkline?, span, rows}] }
// Drag/resize: window.ReportingGrid. Tile rendering: window.ReportingLayoutView.
(function () {
  'use strict';
  var API_PREFIX = window.API_PREFIX;
  var api = window.NX.apiSafe, el = window.NX.el, esc = window.NX.esc, toast = window.NX.toast;
  var I18N = window.NX_I18N_REPORTING_LAYOUTS;
  var OPS = ['current', 'mean', 'minmax', 'range', 'stddev', 'percentile'];
  var CHARTS = ['bar', 'stacked_bar', 'line', 'area', 'pie', 'doughnut', 'gauge'];
  var GRID_COLS = 12, MAX_ROWS = 8;
  var DEFAULT_GEOM = { kpi: [3, 2], chart: [9, 4], table: [12, 4] };

  var state = { editing: false, dirty: false, reportId: null, def: null, seq: 100,
                previewId: null, preview: null, saveTimer: null };
  var built = false, grid = null;

  function RS() { return window.ReportingSimple; }
  function layouts() { return (RS().state.reports || []).filter(function (r) { return r.kind === 'layout' && r.owned; }); }
  function runnable() { return (RS().state.reports || []).filter(function (r) { return r.kind !== 'dashboard' && r.kind !== 'layout' && r.kind !== 'sql'; }); }

  function blankDef() {
    return { kind: 'layout', schemaVersion: 1, title: I18N.untitled,
             measures: [{ id: 'm1', op: 'current' }],
             tiles: [{ id: 't1', type: 'kpi', measure: 'm1', span: 3, rows: 2 },
                     { id: 't2', type: 'chart', chart: 'bar', span: 9, rows: 4 },
                     { id: 't3', type: 'table', span: 12, rows: 4 }] };
  }
  function nextId(prefix) { state.seq += 1; return prefix + state.seq; }
  function markDirty() {
    state.dirty = true;
    clearTimeout(state.saveTimer);
    state.saveTimer = setTimeout(save, 600);   // autosave like the dashboard's Done
    render();
  }

  // ---- persistence (existing /api/reporting/reports CRUD) -----------------
  async function save() {
    if (!state.dirty || !state.def) return;
    var body = JSON.stringify({ name: state.def.title, definition: state.def });
    var res = state.reportId
      ? await api('/api/reporting/reports/' + state.reportId, { method: 'PUT', body: body })
      : await api('/api/reporting/reports', { method: 'POST', body: body });
    if (!res.ok) { toast((res.data && res.data.detail) || I18N.saveFailed, 'error'); return; }
    if (!state.reportId && res.data && res.data.id) state.reportId = String(res.data.id);
    state.dirty = false;
    await RS().loadLibrary({ silent: true });   // refresh RS.state.reports + rail counts
    renderList();
  }
  async function remove() {
    if (!state.reportId || !window.confirm(I18N.confirmDelete)) return;
    var res = await api('/api/reporting/reports/' + state.reportId, { method: 'DELETE' });
    if (!res.ok) { toast(I18N.saveFailed, 'error'); return; }
    state.reportId = null; state.def = null; state.editing = false;
    await RS().loadLibrary({ silent: true });
    render();
  }

  // ---- public entry points ------------------------------------------------
  function open() {
    ensureShell();
    if (!state.def) { var first = layouts()[0]; if (first) { openLayout(first); return; } }
    render();
  }
  function openNew() {
    ensureShell();
    state.reportId = null; state.def = blankDef(); state.editing = true; state.dirty = true;
    state.seq = 100;
    render();
    save();
  }
  async function openLayout(report) {
    ensureShell();
    var res = await api('/api/reporting/reports/' + report.id);
    if (!res.ok || !res.data) { toast(I18N.saveFailed, 'error'); return; }
    state.reportId = String(report.id); state.def = res.data.definition; state.editing = false; state.dirty = false;
    state.seq = 100 + (state.def.tiles || []).length + (state.def.measures || []).length;
    render();
  }
  function close() { state.editing = false; if (el('rsLayouts')) el('rsLayouts').hidden = true; }

  // ---- shell ----------------------------------------------------------------
  function ensureShell() {
    if (built) return;
    built = true;
    el('rsLayouts').innerHTML =
      '<div class="rdb-head rl-head">' +
        '<div class="rdb-titleblock"><div class="rdb-titlerow">' +
          '<h2 class="rdb-title" id="rlTitle" data-testid="rl-title"></h2>' +
          '<input id="rlTitleInput" class="reporting-input rdb-title-input" hidden data-testid="rl-title-input">' +
        '</div><p class="rdb-meta" id="rlMeta"></p></div>' +
        '<span class="rdb-spacer"></span>' +
        '<select id="rlList" class="rc-select" data-testid="rl-list"></select>' +
        '<button type="button" id="rlNew" class="rc-btn" data-testid="rl-new">' + esc(I18N.newDefinition) + '</button>' +
        '<button type="button" id="rlDelete" class="rc-btn" data-testid="rl-delete">' + esc(I18N.delete_) + '</button>' +
        '<button type="button" id="rlEdit" class="rc-btn rc-btn--primary" data-testid="rl-edit"></button>' +
      '</div>' +
      '<div class="rl-body">' +
        '<aside class="rl-rail" id="rlRail" data-testid="rl-rail"></aside>' +
        '<div class="rl-main">' +
          '<div class="rl-previewbar"><label>' + esc(I18N.previewWith) + ' <select id="rlPreview" class="rc-select" data-testid="rl-preview"></select></label></div>' +
          '<div id="rlGrid" class="rdb-grid rl-grid" data-testid="rl-grid"></div>' +
        '</div>' +
      '</div>';
    el('rlNew').addEventListener('click', openNew);
    el('rlDelete').addEventListener('click', remove);
    el('rlEdit').addEventListener('click', function () { state.editing = !state.editing; if (!state.editing) save(); render(); });
    el('rlList').addEventListener('change', function () {
      var r = layouts().find(function (x) { return String(x.id) === el('rlList').value; });
      if (r) openLayout(r);
    });
    el('rlPreview').addEventListener('change', function () { state.previewId = el('rlPreview').value || null; runPreview(); });
    el('rlTitle').addEventListener('click', function () {
      if (!state.editing) return;
      el('rlTitle').hidden = true; el('rlTitleInput').hidden = false;
      el('rlTitleInput').value = state.def.title; el('rlTitleInput').focus();
    });
    el('rlTitleInput').addEventListener('blur', commitTitle);
    el('rlTitleInput').addEventListener('keydown', function (e) { if (e.key === 'Enter') commitTitle(); });
    el('rlRail').addEventListener('click', onRailClick);
    el('rlRail').addEventListener('change', onRailChange);
    el('rlGrid').addEventListener('click', onGridClick);
    el('rlGrid').addEventListener('change', onGridChange);
    grid = window.ReportingGrid.attach(el('rlGrid'), {
      cols: GRID_COLS, maxRows: MAX_ROWS,
      isEditing: function () { return state.editing; },
      items: function () { return (state.def && state.def.tiles) || []; },
      findItem: function (id) { return (state.def.tiles || []).find(function (t) { return t.id === id; }); },
      findEl: function (id) { return el('rlGrid').querySelector('[data-card-id="' + id + '"]'); },
      onReorder: function (from, to) { state.def.tiles = window.ReportingGrid.moveIndex(state.def.tiles, from, to); markDirtyNoRender(); },
      onResize: function (tile, span, rows) { tile.span = span; tile.rows = rows; markDirty(); }
    });
  }
  function markDirtyNoRender() { state.dirty = true; clearTimeout(state.saveTimer); state.saveTimer = setTimeout(save, 600); }
  function commitTitle() {
    var v = el('rlTitleInput').value.trim();
    el('rlTitleInput').hidden = true; el('rlTitle').hidden = false;
    if (v && v !== state.def.title) { state.def.title = v; markDirty(); }
  }

  // ---- rail (palettes) ------------------------------------------------------
  function railHtml() {
    var m = '<h4 class="rl-rail-h">' + esc(I18N.measures) + '</h4>' +
      OPS.map(function (op) {
        return '<button type="button" class="rl-pal" data-add-measure="' + op + '" data-testid="rl-add-measure-' + op + '"' +
          (state.editing ? '' : ' disabled') + '>' + esc(I18N.op[op]) + '</button>';
      }).join('') +
      '<ul class="rl-measures" data-testid="rl-measures">' +
      (state.def.measures || []).map(function (ms) {
        return '<li data-measure-id="' + esc(ms.id) + '">' + esc(I18N.op[ms.op]) +
          (ms.op === 'percentile'
            ? ' <input type="number" class="rl-q" min="0.01" max="0.99" step="0.01" value="' + (ms.q || 0.5) + '" data-q-for="' + esc(ms.id) + '"' + (state.editing ? '' : ' disabled') + '>'
            : '') +
          (state.editing ? ' <button type="button" class="rl-x" data-remove-measure="' + esc(ms.id) + '" aria-label="' + esc(I18N.removeTile) + '">&times;</button>' : '') +
          '</li>';
      }).join('') + '</ul>' +
      '<h4 class="rl-rail-h">' + esc(I18N.tiles) + '</h4>' +
      '<button type="button" class="rl-pal" data-add-tile="chart" data-testid="rl-add-chart"' + (state.editing ? '' : ' disabled') + '>' + esc(I18N.addChart) + '</button>' +
      '<button type="button" class="rl-pal" data-add-tile="table" data-testid="rl-add-table"' + (state.editing ? '' : ' disabled') + '>' + esc(I18N.addTable) + '</button>';
    return m;
  }
  function onRailClick(e) {
    var b = e.target.closest('button'); if (!b || !state.editing) return;
    if (b.dataset.addMeasure) {
      var id = nextId('m');
      var ms = { id: id, op: b.dataset.addMeasure };
      if (ms.op === 'percentile') ms.q = 0.95;
      state.def.measures.push(ms);
      state.def.tiles.push({ id: nextId('t'), type: 'kpi', measure: id, span: DEFAULT_GEOM.kpi[0], rows: DEFAULT_GEOM.kpi[1] });
      markDirty();
    } else if (b.dataset.removeMeasure) {
      state.def.measures = state.def.measures.filter(function (x) { return x.id !== b.dataset.removeMeasure; });
      state.def.tiles = state.def.tiles.filter(function (t) { return t.measure !== b.dataset.removeMeasure; });
      markDirty();
    } else if (b.dataset.addTile) {
      var t = { id: nextId('t'), type: b.dataset.addTile, span: DEFAULT_GEOM[b.dataset.addTile][0], rows: DEFAULT_GEOM[b.dataset.addTile][1] };
      if (t.type === 'chart') t.chart = 'bar';
      state.def.tiles.push(t);
      markDirty();
    }
  }
  function onRailChange(e) {
    var q = e.target.closest('[data-q-for]'); if (!q) return;
    var ms = state.def.measures.find(function (x) { return x.id === q.dataset.qFor; });
    var v = parseFloat(q.value);
    if (ms && v > 0 && v < 1) { ms.q = v; markDirty(); }
  }

  // ---- grid -------------------------------------------------------------------
  function tileShellHtml(t) {
    var head = t.type === 'kpi'
      ? esc(I18N.op[(state.def.measures.find(function (m) { return m.id === t.measure; }) || {}).op] || '')
      : t.type === 'chart' ? esc(I18N.chart[t.chart]) : esc(I18N.table);
    var tools = '';
    if (state.editing) {
      if (t.type === 'chart') {
        tools += '<select class="rc-select rl-chart-type" data-chart-for="' + esc(t.id) + '" data-testid="rl-chart-type">' +
          CHARTS.map(function (c) { return '<option value="' + c + '"' + (c === t.chart ? ' selected' : '') + '>' + esc(I18N.chart[c]) + '</option>'; }).join('') + '</select>';
      }
      if (t.type === 'kpi') {
        tools += '<label class="rl-spark"><input type="checkbox" data-spark-for="' + esc(t.id) + '"' + (t.sparkline ? ' checked' : '') + '> ' + esc(I18N.sparkline) + '</label>';
      }
      tools += '<button type="button" class="rl-x" data-remove-tile="' + esc(t.id) + '" aria-label="' + esc(I18N.removeTile) + '" data-testid="rl-remove-tile">&times;</button>';
    }
    return '<div class="rdb-card rl-tile" data-card-id="' + esc(t.id) + '" data-type="' + t.type + '" draggable="' + (state.editing ? 'true' : 'false') + '" ' +
      'style="' + window.ReportingGrid.geomStyle(t.span, t.rows) + '" data-testid="rl-tile">' +
      '<div class="rdb-card-head"><span class="rdb-card-title">' + head + '</span><span class="rdb-spacer"></span>' + tools + '</div>' +
      '<div class="rdb-card-body" data-tile-body></div>' +
      (state.editing ? '<span class="rdb-card-resize" data-testid="rdb-card-resize" title="' + esc(I18N.resizeTile) + '" aria-hidden="true"></span>' : '') +
      '</div>';
  }
  function onGridClick(e) {
    var b = e.target.closest('[data-remove-tile]'); if (!b || !state.editing) return;
    state.def.tiles = state.def.tiles.filter(function (t) { return t.id !== b.dataset.removeTile; });
    markDirty();
  }
  function onGridChange(e) {
    var sel = e.target.closest('[data-chart-for]');
    if (sel) { var t = state.def.tiles.find(function (x) { return x.id === sel.dataset.chartFor; }); if (t) { t.chart = sel.value; markDirty(); } return; }
    var sp = e.target.closest('[data-spark-for]');
    if (sp) { var k = state.def.tiles.find(function (x) { return x.id === sp.dataset.sparkFor; }); if (k) { k.sparkline = sp.checked; markDirty(); } }
  }

  // ---- preview ----------------------------------------------------------------
  async function runPreview() {
    state.preview = null;
    if (!state.previewId || !state.def) { renderTiles(); return; }
    var rep = await api('/api/reporting/reports/' + state.previewId);
    if (!rep.ok || !rep.data || !rep.data.definition) { renderTiles(); return; }
    var def = Object.assign({}, rep.data.definition, { layout: state.def });
    delete def.layoutId;
    var res = await api('/api/reporting/run', { method: 'POST', body: JSON.stringify(def) });
    if (!res.ok) { toast(I18N.previewFailed, 'error'); renderTiles(); return; }
    state.preview = { def: rep.data.definition, data: res.data };
    renderTiles();
  }
  function renderTiles() {
    var host = el('rlGrid');
    host.classList.toggle('rdb-grid--editing', state.editing);
    host.innerHTML = (state.def.tiles || []).map(tileShellHtml).join('');
    if (!window.ReportingLayoutView) return;
    window.ReportingLayoutView.render(host, {
      layout: state.def,
      def: state.preview ? state.preview.def : null,
      columns: state.preview ? state.preview.data.columns : [],
      rows: state.preview ? state.preview.data.rows : [],
      derived: state.preview ? (state.preview.data.derived || {}) : {},
      i18n: I18N
    });
  }

  // ---- render ----------------------------------------------------------------
  function renderList() {
    var list = layouts();
    el('rlList').innerHTML = list.map(function (r) {
      return '<option value="' + r.id + '"' + (String(r.id) === state.reportId ? ' selected' : '') + '>' + esc(r.name) + '</option>';
    }).join('');
    el('rlList').hidden = !list.length;
    var prev = runnable();
    el('rlPreview').innerHTML = '<option value="">' + esc(prev.length ? '—' : I18N.previewNone) + '</option>' +
      prev.map(function (r) { return '<option value="' + r.id + '"' + (String(r.id) === state.previewId ? ' selected' : '') + '>' + esc(r.name) + '</option>'; }).join('');
  }
  function render() {
    if (!built) return;
    renderList();
    var has = !!state.def;
    el('rlTitle').textContent = has ? state.def.title : I18N.title;
    el('rlMeta').textContent = has ? I18N.tilesMeta.replace('{n}', String(state.def.tiles.length)) : I18N.intro;
    el('rlEdit').textContent = state.editing ? I18N.done : I18N.edit;
    el('rlEdit').hidden = !has; el('rlDelete').hidden = !has || !state.reportId;
    el('rlRail').innerHTML = has ? railHtml() : '';
    if (has) renderTiles(); else el('rlGrid').innerHTML = '';
  }

  window.ReportingLayouts = { open: open, openNew: openNew, openLayout: openLayout, close: close };
}());
```

`RS.loadLibrary()` takes no arguments (`async function loadLibrary()` in `reporting_simple_library.js`) — call it bare; replace both `RS().loadLibrary({ silent: true })` above with `RS().loadLibrary()`.

- [ ] **Step 4: CSS** — append to `static/css/reporting.css` after the `.rdb-card-error` rule:

```css
/* ---- Report definitions editor (reporting_layouts.js) — shares the rdb-* grid ---- */
.reporting-layouts { max-width: none; padding: 4px 0 60px; }
.rl-body { display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 18px; align-items: start; }
.rl-rail { position: sticky; top: 12px; display: flex; flex-direction: column; gap: 6px; }
.rl-rail-h { margin: 8px 0 2px; font: 600 11px var(--nx-font); letter-spacing: .06em; text-transform: uppercase; color: var(--nx-text-meta); }
.rl-pal { text-align: left; padding: 6px 10px; border: 1px solid var(--nx-border); border-radius: 8px; background: var(--nx-card); color: var(--nx-text); cursor: pointer; }
.rl-pal:disabled { opacity: .5; cursor: default; }
.rl-measures { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; }
.rl-measures li { display: flex; align-items: center; gap: 6px; padding: 4px 8px; border-radius: 6px; background: var(--nx-accent-soft); }
.rl-q { width: 64px; }
.rl-x { margin-left: auto; border: 0; background: none; cursor: pointer; color: var(--nx-text-meta); }
.rl-previewbar { display: flex; justify-content: flex-end; margin-bottom: 10px; font-size: 12.5px; color: var(--nx-text-meta); }
.rl-tile .rdb-card-body { display: flex; flex-direction: column; }
.rl-kpi { display: flex; flex-direction: column; gap: 4px; }
.rl-kpi-value { font: 600 26px var(--nx-font); letter-spacing: -.5px; color: var(--nx-text); }
.rl-kpi-sub { font-size: 11px; color: var(--nx-text-meta); }
.rl-kpi-spark { height: 28px; margin-top: 4px; }
.rl-chart { position: relative; flex: 1 1 auto; min-height: 120px; }
.rl-chart canvas { position: absolute; inset: 0; }
.rl-table { overflow: auto; font-size: 12.5px; }
.rl-table table { width: 100%; border-collapse: collapse; }
.rl-table th, .rl-table td { padding: 4px 8px; border-bottom: 1px solid var(--nx-border); text-align: left; white-space: nowrap; }
.rl-placeholder { flex: 1; display: grid; place-items: center; color: var(--nx-text-meta); font-size: 12px; }
```

Also extend the full-bleed rule in `static/css/reporting-console.css`: change `body.reporting-console.rdb-fullbleed .reporting-dashboard { max-width: none; padding: 4px 0 60px; }` to also cover `.reporting-layouts` (comma-separated selector).

- [ ] **Step 5: Lints + smoke**

Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" ENVIRONMENT=INT python -m pytest tests/unit/test_template_url_prefix.py tests/unit/test_static_v_lint.py tests/unit/test_no_inline_event_handlers.py tests/unit/test_reporting_i18n_lint.py -q`
Expected: pass. (`test_reporting_i18n_lint.py` may require every `I18N.x` read in the JS to exist in the shim — read its failure and add any missing key to the shim.)

Restart the dev server (`bin/nx.ps1 -r`), open `http://127.0.0.1:<port>/reporting?tab=definitions` logged in as `ben.streich`, click **New definition**, add a measure, drag a tile, resize it, reload — the layout persists. Tiles show placeholders until Task 9.

- [ ] **Step 6: Commit**

```bash
git add static/js/reporting_layouts.js templates/js/_reporting_layouts_js.html templates/_reporting_simple.html static/js/reporting_simple_library.js static/css/reporting.css static/css/reporting-console.css
git commit -F - <<'EOF'
feat(reporting): report-definitions editor (layouts) in the Simple pane

New window.ReportingLayouts: list / new / edit / delete kind:'layout' saved
reports through the existing reports CRUD, a measure palette (current, mean,
min/max, range, std dev, percentile), chart/table tiles on the shared
ReportingGrid engine with autosave, and a live preview that runs a chosen
saved report with the draft layout inlined. Library cards skip layouts.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

### Task 9: `static/js/reporting_layout_view.js` — the tile renderer (KPI, charts, table)

**Files:**
- Create: `static/js/reporting_layout_view.js`
- Test: `tests/unit/test_reporting_layout_view_js.py` (Node, same harness as Task 6)

**Interfaces:**
- Produces `window.ReportingLayoutView = { render(host, ctx), seriesFor(columns, rows, def), destroy(host) }`. `render` finds `[data-card-id]` tiles inside `host` (already laid out by the caller) and fills each `[data-tile-body]` from `ctx = { layout, def, columns, rows, derived, i18n, onDrill? }`; keeps a `Map` of Chart.js instances per host and destroys them on the next `render`/`destroy`. `seriesFor` is pure: returns `{ labels: string[], datasets: [{ label, data: number[] }] }` using column 0 as labels and every column whose non-null cells are all numeric as a dataset (metric columns, per D6). Exported for the Node test.
- KPI tile: `<div class="rl-kpi"><span class="rl-kpi-value" data-testid="rl-kpi-value">…</span><span class="rl-kpi-sub">…</span>[<canvas class="rl-kpi-spark">]</div>`; value formatted via `window.NX.formatHours`-style? No — use `Intl.NumberFormat(undefined, {maximumFractionDigits: 2})`; minmax renders `min – max`; unavailable renders `—` with the reason in `title`.
- Chart tile: `type` mapping `bar→bar`, `stacked_bar→bar + scales.x/y.stacked`, `line→line`, `area→line + fill:true`, `pie/doughnut` as-is with the first dataset only, `gauge→doughnut` with `circumference:180, rotation:270, cutout:'70%'` and data `[current − min, max − current]` from `derived` when a `current`/`minmax` measure exists else from the first dataset's min/max/last.
- Table tile: plain `<table>` of `columns` headers and up to 200 rows.

- [ ] **Step 1: Write the failing Node test** — `tests/unit/test_reporting_layout_view_js.py`:

```python
"""static/js/reporting_layout_view.js: seriesFor() picks column 0 as labels
and every all-numeric column as a dataset (run under Node, see
test_reporting_grid_js.py)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path("static/js/reporting_layout_view.js")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

_HARNESS = """
const fs = require('fs');
global.window = { NX: {} };
global.document = {};
eval(fs.readFileSync(process.argv[1], 'utf8'));
const V = window.ReportingLayoutView;
const cols = [{field:'import_date'},{field:'doc_count'},{field:'client'},{field:'pages'}];
const rows = [['2026-01-01', 3, 'A', 12], ['2026-01-02', null, 'B', 7], ['2026-01-03', 5, 'A', 'n/a']];
process.stdout.write(JSON.stringify(V.seriesFor(cols, rows, {columns:[{field:'import_date', grain:'day'}]})));
"""


def test_series_for_uses_first_column_as_labels_and_numeric_columns_as_datasets():
    out = json.loads(subprocess.run([NODE, "-e", _HARNESS, str(SRC)], capture_output=True, text=True, check=True).stdout)
    assert out["labels"] == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert [d["label"] for d in out["datasets"]] == ["doc_count"]  # pages has 'n/a' → not numeric
    assert out["datasets"][0]["data"] == [3, None, 5]
```

- [ ] **Step 2: Run to verify it fails** — `… pytest tests/unit/test_reporting_layout_view_js.py -q` → ENOENT.

- [ ] **Step 3: Implement** — `static/js/reporting_layout_view.js`:

```js
// Renders a layout's tiles (KPI / chart / table) into an already-laid-out
// .rdb-grid. Shared by the definitions editor preview and both result views.
// Charts are drawn straight from (columns, rows) with Chart.js: column 0 is
// the x axis, every all-numeric column one dataset (the metric columns).
(function () {
  'use strict';
  var esc = (window.NX && window.NX.esc) || function (s) { return String(s); };
  var charts = new WeakMap();   // host -> [Chart]
  var SERIES = ['--nx-series-1', '--nx-series-2', '--nx-series-3', '--nx-series-4', '--nx-series-5'];

  function isNum(v) { return typeof v === 'number' && isFinite(v); }
  function seriesFor(columns, rows, def) {
    var labels = rows.map(function (r) { return r[0] == null ? '' : String(r[0]).slice(0, 10); });
    var datasets = [];
    for (var i = 1; i < columns.length; i++) {
      var cells = rows.map(function (r) { return r[i]; }).filter(function (v) { return v != null; });
      if (!cells.length || !cells.every(isNum)) continue;
      var col = columns[i];
      datasets.push({ label: col.header || col.field, data: rows.map(function (r) { return isNum(r[i]) ? r[i] : null; }) });
    }
    return { labels: labels, datasets: datasets };
  }
  function cssVar(name, dflt) {
    if (typeof getComputedStyle !== 'function') return dflt;
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || dflt;
  }
  function colour(i) { return cssVar(SERIES[i % SERIES.length], '#4f46e5'); }
  function fmt(v) {
    if (v == null || !isFinite(v)) return '—';
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(v);
  }
  function destroy(host) {
    (charts.get(host) || []).forEach(function (c) { try { c.destroy(); } catch (e) {} });
    charts.set(host, []);
  }
  function keep(host, chart) { var list = charts.get(host) || []; list.push(chart); charts.set(host, list); }

  function kpiHtml(tile, ctx) {
    var d = (ctx.derived || {})[tile.measure] || {};
    var ms = (ctx.layout.measures || []).find(function (m) { return m.id === tile.measure; }) || {};
    var label = (ctx.i18n && ctx.i18n.op && ctx.i18n.op[ms.op]) || ms.op || '';
    var value = d.unavailable ? '—' : (ms.op === 'minmax' ? fmt(d.min) + ' – ' + fmt(d.max) : fmt(d.value));
    var sub = d.unavailable ? (ctx.i18n ? ctx.i18n.unavailable : d.unavailable)
      : (ms.op === 'percentile' ? 'p' + Math.round((ms.q || 0.5) * 100) : (d.n != null ? 'n = ' + d.n : ''));
    return '<div class="rl-kpi" title="' + esc(d.unavailable || '') + '">' +
      '<span class="rl-kpi-label rdb-card-meta">' + esc(label) + '</span>' +
      '<span class="rl-kpi-value" data-testid="rl-kpi-value">' + esc(value) + '</span>' +
      '<span class="rl-kpi-sub">' + esc(sub) + '</span>' +
      (tile.sparkline ? '<canvas class="rl-kpi-spark"></canvas>' : '') + '</div>';
  }
  function singleDateDim(def) {
    var cols = (def && def.columns) || [];
    return cols.length === 1 && (!!cols[0].grain || /date/i.test(cols[0].field || ''));
  }
  function mountSpark(host, canvas, ctx) {
    if (!window.Chart || !singleDateDim(ctx.def)) { canvas.remove(); return; }
    var s = seriesFor(ctx.columns, ctx.rows, ctx.def);
    if (!s.datasets.length) { canvas.remove(); return; }
    keep(host, new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { labels: s.labels, datasets: [{ data: s.datasets[0].data, borderColor: colour(0), borderWidth: 1.5, pointRadius: 0, tension: .3, spanGaps: true }] },
      options: { responsive: true, maintainAspectRatio: false, animation: false,
                 plugins: { legend: { display: false }, tooltip: { enabled: false } },
                 scales: { x: { display: false }, y: { display: false } } }
    }));
  }
  function chartConfig(tile, s, ctx) {
    var t = tile.chart;
    var base = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: s.datasets.length > 1 } } };
    if (t === 'pie' || t === 'doughnut') {
      return { type: t, data: { labels: s.labels, datasets: [{ data: s.datasets[0].data, backgroundColor: s.labels.map(function (_, i) { return colour(i); }) }] }, options: base };
    }
    if (t === 'gauge') {
      var d = ctx.derived || {}, cur = null, lo = null, hi = null;
      Object.keys(d).forEach(function (k) {
        if (d[k].op === 'current' && isNum(d[k].value)) cur = d[k].value;
        if (d[k].op === 'minmax') { lo = d[k].min; hi = d[k].max; }
      });
      var data = s.datasets[0].data.filter(isNum);
      if (cur == null) cur = data.length ? data[data.length - 1] : 0;
      if (lo == null) lo = data.length ? Math.min.apply(null, data) : 0;
      if (hi == null) hi = data.length ? Math.max.apply(null, data) : 1;
      var span = Math.max(hi - lo, 1e-9);
      return { type: 'doughnut',
        data: { labels: [fmt(cur), ''], datasets: [{ data: [cur - lo, Math.max(hi - cur, 0)], backgroundColor: [colour(0), cssVar('--nx-border', '#e5e7eb')], borderWidth: 0 }] },
        options: Object.assign({}, base, { circumference: 180, rotation: 270, cutout: '70%', plugins: { legend: { display: false }, tooltip: { enabled: false } } }) };
    }
    var datasets = s.datasets.map(function (ds, i) {
      return { label: ds.label, data: ds.data, borderColor: colour(i), backgroundColor: colour(i) + (t === 'area' ? '33' : ''),
               fill: t === 'area', tension: .3, spanGaps: true };
    });
    var type = (t === 'line' || t === 'area') ? 'line' : 'bar';
    var scales = { y: { beginAtZero: true, ticks: { maxTicksLimit: 6 } } };
    if (t === 'stacked_bar') { scales.x = { stacked: true }; scales.y.stacked = true; }
    return { type: type, data: { labels: s.labels, datasets: datasets }, options: Object.assign({}, base, { scales: scales }) };
  }
  function tableHtml(ctx) {
    var cols = ctx.columns || [], rows = (ctx.rows || []).slice(0, 200);
    return '<div class="rl-table"><table><thead><tr>' +
      cols.map(function (c) { return '<th>' + esc(c.header || c.field) + '</th>'; }).join('') + '</tr></thead><tbody>' +
      rows.map(function (r) { return '<tr>' + r.map(function (v) { return '<td>' + esc(v == null ? '' : v) + '</td>'; }).join('') + '</tr>'; }).join('') +
      '</tbody></table></div>';
  }

  function render(host, ctx) {
    destroy(host);
    var hasData = ctx.columns && ctx.columns.length && ctx.rows && ctx.rows.length;
    var s = hasData ? seriesFor(ctx.columns, ctx.rows, ctx.def) : { labels: [], datasets: [] };
    (ctx.layout.tiles || []).forEach(function (tile) {
      var card = host.querySelector('[data-card-id="' + tile.id + '"]');
      var body = card && card.querySelector('[data-tile-body]');
      if (!body) return;
      if (!hasData && tile.type !== 'kpi') {
        body.innerHTML = '<div class="rl-placeholder">' + esc(tile.type === 'chart' ? (ctx.i18n.chart[tile.chart] || tile.chart) : ctx.i18n.table) + '</div>';
        return;
      }
      if (tile.type === 'kpi') {
        body.innerHTML = kpiHtml(tile, ctx);
        var spark = body.querySelector('.rl-kpi-spark');
        if (spark && hasData) mountSpark(host, spark, ctx);
        return;
      }
      if (tile.type === 'table') { body.innerHTML = tableHtml(ctx); return; }
      body.innerHTML = '<div class="rl-chart"><canvas></canvas></div>';
      if (!window.Chart || !s.datasets.length) { body.innerHTML = '<div class="rl-placeholder">' + esc(ctx.i18n.unavailable) + '</div>'; return; }
      keep(host, new Chart(body.querySelector('canvas').getContext('2d'), chartConfig(tile, s, ctx)));
    });
  }

  window.ReportingLayoutView = { render: render, seriesFor: seriesFor, destroy: destroy };
}());
```

- [ ] **Step 4: Run the Node test and lints** — `… pytest tests/unit/test_reporting_layout_view_js.py tests/unit/test_template_url_prefix.py tests/unit/test_static_v_lint.py -q` → pass. Reload the editor page (server restart not needed for a `.js` change but `static_v` cache-busts on file mtime — hard-reload), pick a **Preview with** report: KPI shows a number, chart draws, table fills.

- [ ] **Step 5: Commit**

```bash
git add static/js/reporting_layout_view.js tests/unit/test_reporting_layout_view_js.py
git commit -F - <<'EOF'
feat(reporting): layout tile renderer (KPI, 7 chart types, table)

window.ReportingLayoutView.render() fills a layout's tiles from a run
result: KPI tiles from `derived` (optional sparkline), chart tiles drawn
straight from (columns, rows) with Chart.js — bar, stacked bar, line, area,
pie, doughnut, gauge — and a plain table tile. Series colours ride the
--nx-series-* tokens.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

# PHASE 4 — Builder picker + result views

### Task 10: Simple pane — picker in the wizard, tile grid in the result

**Files:**
- Modify: `templates/_reporting_simple.html`
- Modify: `templates/js/_reporting_simple_js.html`
- Modify: `static/js/reporting_simple_wizard.js`
- Modify: `static/js/reporting_simple.js`

**Interfaces:**
- Produces: `<select id="rsLayoutPick" class="rc-select" data-testid="rs-layout-pick">` in the wizard footer (before `#rsPickedCount`) listing `Standard` + the user's layouts; `wizardDefinition()` sets `layoutId: Number(value)` when a layout is picked and omits the key otherwise; `wizardStateFromDefinition(def)` restores the select from `def.layoutId`. `runCurrent` renders `<div id="rsLayoutGrid" class="rdb-grid rl-grid" hidden data-testid="rs-layout-grid">` (new, placed right above `#rsChartCard` in the result markup) via `ReportingLayoutView.render` when `res.data.layout` is present, hiding the KPI band host, `#rsChartCard`, `#rsTableCard`, `#rsTableToggle`; on `res.data.layoutFallback` it toasts `RS.I18N.layoutFallback` once per report id and renders Standard.
- New shim strings in `templates/js/_reporting_simple_js.html`'s `window.NX_I18N_REPORTING_SIMPLE`: `layoutStandard: {{ _("Standard")|tojson }}`, `layoutPick: {{ _("Report definition")|tojson }}`, `layoutFallback: {{ _("This report’s definition is not available anymore — showing the Standard layout.")|tojson }}`.

- [ ] **Step 1: Markup** — in `templates/_reporting_simple.html`:
  - in the wizard footer, directly before `<span id="rsPickedCount" …>` insert:

```html
          <label class="rs-layout-pick" title="{{ _('Report definition') }}">
            <i class="fas fa-sliders" aria-hidden="true"></i>
            <select id="rsLayoutPick" class="rc-select" data-testid="rs-layout-pick"></select>
          </label>
```

  - in the result view, directly before the element `id="rsChartCard"` (Grep it) insert `<div id="rsLayoutGrid" class="rdb-grid rl-grid" hidden data-testid="rs-layout-grid"></div>`.
  - add the three shim strings above to `templates/js/_reporting_simple_js.html`.

- [ ] **Step 2: Wizard** — in `static/js/reporting_simple_wizard.js`:
  - add a helper near `wizardDefinition`:

```js
  // "Report definition" picker: Standard (no layoutId) or one of the user's
  // kind:'layout' saved reports. Rebuilt from RS.state.reports on every open.
  function renderLayoutPick(selectedId) {
    var sel = RS.el('rsLayoutPick');
    if (!sel) return;
    var mine = (RS.state.reports || []).filter(function (r) { return r.kind === 'layout' && r.owned; });
    sel.innerHTML = '<option value="">' + RS.esc(RS.I18N.layoutStandard) + '</option>' +
      mine.map(function (r) {
        return '<option value="' + r.id + '"' + (String(r.id) === String(selectedId || '') ? ' selected' : '') + '>' + RS.esc(r.name) + '</option>';
      }).join('');
    sel.closest('label').hidden = !mine.length;
  }
  RS.renderLayoutPick = renderLayoutPick;
```

  - in `wizardDefinition()`'s returned object add, after building it (assign to `var def = {…}; ` then): `var pick = RS.el('rsLayoutPick'); if (pick && pick.value) def.layoutId = Number(pick.value); return def;`
  - in `startWizard` (the `#rsNewReport` click handler: `RS.el('rsNewReport').addEventListener('click', startWizard);`) call `RS.renderLayoutPick(null)` after the wizard state is reset; in the "adjust in wizard" restore path (`wizardStateFromDefinition` consumer, Grep `RS.wizardStateFromDefinition(cur.def)` in `reporting_simple.js`'s adjust handler) call `RS.renderLayoutPick(cur.def.layoutId)` after the wizard state is applied.

- [ ] **Step 3: Result** — in `static/js/reporting_simple.js`'s `runCurrent`, directly **before** `var charted = (hasMetrics && dims)` insert:

```js
    // Report definition (layout): render the tile grid instead of band+chart+table.
    var lgrid = RS.el('rsLayoutGrid');
    if (res.data.layoutFallback && !fallbackToastFor[cur.reportId || 'new']) {
      fallbackToastFor[cur.reportId || 'new'] = true;
      window.NX.toast(RS.I18N.layoutFallback, 'warning');
    }
    if (res.data.layout && window.ReportingLayoutView) {
      lgrid.hidden = false;
      lgrid.innerHTML = (res.data.layout.tiles || []).map(function (t) {
        return '<div class="rdb-card rl-tile" data-card-id="' + RS.esc(t.id) + '" data-type="' + t.type + '" ' +
          'style="' + window.ReportingGrid.geomStyle(t.span, t.rows) + '" data-testid="rs-layout-tile">' +
          '<div class="rdb-card-body" data-tile-body></div></div>';
      }).join('');
      window.ReportingLayoutView.render(lgrid, { layout: res.data.layout, def: def, columns: columns, rows: rows,
        derived: res.data.derived || {}, i18n: window.NX_I18N_REPORTING_LAYOUTS });
      RS.el('rsKpiBand').hidden = true;   // the band host renderKpiBand writes into
      RS.el('rsChartCard').hidden = true;
      RS.el('rsTableCard').hidden = true;
      RS.el('rsTableToggle').hidden = true;
      RS.state.lastRun = { def: def, columns: columns, rows: rows, hasMetrics: hasMetrics, dims: dims,
                           forecast: null, layout: res.data.layout, derived: res.data.derived || {} };
      writePreviewCache(dims, hasMetrics, rows);
      return;
    }
    lgrid.hidden = true;
    if (window.ReportingLayoutView) window.ReportingLayoutView.destroy(lgrid);
```

  Add `var fallbackToastFor = {};` next to `var runSeq` near the top of the IIFE. In `restoreResult`, when `lr.layout` is set, re-render through `ReportingLayoutView.render` instead of `RS.mountChart` (mirror the block above with `lr.*`).

- [ ] **Step 4: Verify in the browser** — restart (`bin/nx.ps1 -r`), login, Library → New report → the Measure step footer shows the picker once a layout exists → pick it → run → the result shows the tile grid with real numbers. Switch to Results via the rail and back: tiles re-render. Delete the layout in the editor, re-run the report: one warning toast, Standard result.

Run the lints: `… pytest tests/unit/test_template_url_prefix.py tests/unit/test_static_v_lint.py tests/unit/test_reporting_i18n_lint.py tests/unit/test_reporting_kpi_band.py -q`.

- [ ] **Step 5: Commit**

```bash
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html static/js/reporting_simple_wizard.js static/js/reporting_simple.js
git commit -F - <<'EOF'
feat(reporting): pick a report definition in the wizard, render its tiles

The wizard's footer offers Standard or one of the user's layouts and writes
layoutId into the definition; runCurrent renders the run's `layout` tiles
through ReportingLayoutView instead of the KPI band, chart and table, and
falls back to Standard with one toast when the server reports layoutFallback.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

### Task 11: Advanced pane — picker next to Saved reports, tile grid in the result

**Files:**
- Modify: `templates/reporting.html`
- Modify: `templates/js/_reporting_js.html`
- Modify: `static/js/reporting_advanced.js`

**Interfaces:**
- Produces: `<select id="rpLayoutPick" class="rc-select" data-testid="reporting-layout-pick">` directly after `#rpSavedReports`'s wrapper (Grep `id="rpSavedReports"` in `templates/reporting.html`); `buildDefinition()` sets `layoutId` from it; `applyDefinition(def, …)` restores it; `renderResults(data)` renders `#rpLayoutGrid` (new div right above `#rpResults`) via `ReportingLayoutView` when `data.layout` is present and hides `#rpResults`, the chart container (`#rpChart`) and the KPI band host, and toasts on `data.layoutFallback`. Shim strings in `templates/js/_reporting_js.html`'s `I18N`: `layoutStandard`, `layoutFallback` (same English text as Task 10).

- [ ] **Step 1: Markup + shim** as described. `#rpLayoutGrid`: `<div id="rpLayoutGrid" class="rdb-grid rl-grid" hidden data-testid="reporting-layout-grid"></div>`.

- [ ] **Step 2: JS** — in `static/js/reporting_advanced.js`:
  - where the saved-reports dropdown is populated (`var buildable = (reports || []).filter(function (r) { return r.kind !== 'dashboard'; });`), change to `r.kind !== 'dashboard' && r.kind !== 'layout'` and, right after, populate the picker:

```js
      var pick = document.getElementById('rpLayoutPick');
      if (pick) {
        var mine = (reports || []).filter(function (r) { return r.kind === 'layout' && r.owned; });
        pick.innerHTML = '<option value="">' + esc(I18N.layoutStandard) + '</option>' +
          mine.map(function (r) { return '<option value="' + r.id + '">' + esc(r.name) + '</option>'; }).join('');
        pick.hidden = !mine.length;
      }
```

  - `buildDefinition()`: before `return d;` add `var lp = document.getElementById('rpLayoutPick'); if (lp && lp.value) d.layoutId = Number(lp.value);`
  - `applyDefinition()`: after `document.getElementById('rpSubtitle').value = def.subtitle || '';` add `var lp = document.getElementById('rpLayoutPick'); if (lp) lp.value = def.layoutId ? String(def.layoutId) : '';`
  - `renderResults(data)`: after `renderKpiBand(state.lastDef, data.rows || [], data.columns || []);` insert:

```js
    var lgrid = document.getElementById('rpLayoutGrid');
    if (data.layoutFallback) window.NX.toast(I18N.layoutFallback, 'warning');
    if (data.layout && window.ReportingLayoutView && lgrid) {
      lgrid.hidden = false;
      lgrid.innerHTML = (data.layout.tiles || []).map(function (t) {
        return '<div class="rdb-card rl-tile" data-card-id="' + esc(t.id) + '" data-type="' + t.type + '" ' +
          'style="' + window.ReportingGrid.geomStyle(t.span, t.rows) + '" data-testid="reporting-layout-tile">' +
          '<div class="rdb-card-body" data-tile-body></div></div>';
      }).join('');
      window.ReportingLayoutView.render(lgrid, { layout: data.layout, def: state.lastDef, columns: data.columns || [],
        rows: data.rows || [], derived: data.derived || {}, i18n: window.NX_I18N_REPORTING_LAYOUTS });
      document.getElementById('rpResults').hidden = true;
      return;
    }
    if (lgrid) { lgrid.hidden = true; if (window.ReportingLayoutView) window.ReportingLayoutView.destroy(lgrid); }
```

  Read `resetViews(hasData)` first: it toggles `#rpResults` by `state.view`; make sure the early `return` above happens **after** `resetViews` would otherwise un-hide `#rpResults` — if `resetViews` runs later in the function, move the layout block to just after `resetViews(!!(data.rows && data.rows.length));`.
  - `window.ReportingGrid` must be loaded before `reporting_advanced.js`: `_reporting_js.html` is included at the page bottom after the Simple pane, so the dashboard shim (which loads the grid) already ran. Confirm order in `templates/reporting.html` (Grep the includes); if `_reporting_js.html` is included **before** `_reporting_simple.html`, add `<script src="{{ static_v('js/reporting_grid.js') }}"></script>` above the advanced script in `_reporting_js.html`.

- [ ] **Step 3: Verify** — Advanced (`?tab=advanced`): pick a layout, run, tiles render; load a saved report with `layoutId`, the picker shows it. Lints as in Task 10.

- [ ] **Step 4: Commit**

```bash
git add templates/reporting.html templates/js/_reporting_js.html static/js/reporting_advanced.js
git commit -F - <<'EOF'
feat(reporting): Advanced builder picks a report definition and renders tiles

Same contract as the Simple wizard: a Standard/layout select next to Saved
reports writes layoutId, applyDefinition restores it, renderResults draws
the layout's tiles via ReportingLayoutView and toasts on layoutFallback.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

# PHASE 5 — e2e, docs, i18n, verification

### Task 12: Playwright e2e for the editor and the result tiles

**Files:**
- Create: `tests/e2e/test_reporting_layouts.py`

Follow `tests/e2e/test_reporting_dashboard.py`'s stubbing style (`page.route("**/api/reporting/reports", …)`, `_login(page, base)`). Every backend call is stubbed so the test needs no seeded data.

- [ ] **Step 1: Write the tests**

```python
"""e2e: report definitions (layouts) — editor, drag/resize, picker, tiles.

A layout is a kind:'layout' saved report; everything here goes through the
existing /api/reporting/reports CRUD and /api/reporting/run, both stubbed.
"""

import json

from playwright.sync_api import expect

LAYOUT = {
    "kind": "layout", "schemaVersion": 1, "title": "Ops standard",
    "measures": [{"id": "m1", "op": "current"}, {"id": "m2", "op": "mean"}],
    "tiles": [
        {"id": "t1", "type": "kpi", "measure": "m1", "span": 3, "rows": 2},
        {"id": "t2", "type": "kpi", "measure": "m2", "span": 3, "rows": 2},
        {"id": "t3", "type": "chart", "chart": "area", "span": 6, "rows": 3},
        {"id": "t4", "type": "table", "span": 12, "rows": 3},
    ],
}
REPORT = {
    "schemaVersion": 1, "source": "docprocessing", "visualization": "table", "title": "Docs per day",
    "columns": [{"field": "import_date", "grain": "day"}], "metrics": [{"metric": "doc_count"}],
    "filters": [], "sort": [], "scope": {"clients": [], "processes": []}, "rowLimit": 5000,
}
RUN = {
    "columns": [{"field": "import_date", "header": "Import date"}, {"field": "doc_count", "header": "Docs"}],
    "rows": [["2026-01-01", 10], ["2026-01-02", 20], ["2026-01-03", 30]],
    "rowCount": 3, "truncated": False, "sql": "SELECT 1", "sqlPretty": "SELECT 1", "sqlDisplay": "SELECT 1", "params": [],
}


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")


def _stub(page, saved):
    reports = [
        {"id": 7, "name": "Docs per day", "kind": "table", "owned": True, "canEdit": True, "visibility": "private",
         "ownerName": "admin", "sharedCount": 0, "previewKind": "bar", "summary": {}, "updatedAt": "2026-01-01"},
        {"id": 9, "name": "Ops standard", "kind": "layout", "owned": True, "canEdit": True, "visibility": "private",
         "ownerName": "admin", "sharedCount": 0, "previewKind": "bar", "summary": {}, "updatedAt": "2026-01-01"},
    ]

    def reports_route(route):
        if route.request.method == "POST":
            saved["created"] = route.request.post_data_json
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"id": 42, "ok": True}))
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(reports))

    def report_route(route):
        rid = route.request.url.rstrip("/").split("/")[-1].split("?")[0]
        if route.request.method == "PUT":
            saved["updated"] = route.request.post_data_json
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))
            return
        body = {"id": rid, "name": "Ops standard", "definition": LAYOUT, "owned": True, "canEdit": True} if rid == "9" \
            else {"id": rid, "name": "Docs per day", "definition": REPORT, "owned": True, "canEdit": True}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def run_route(route):
        rd = route.request.post_data_json
        payload = dict(RUN)
        layout = rd.get("layout") or (LAYOUT if rd.get("layoutId") == 9 else None)
        if layout:
            payload["layout"] = layout
            payload["derived"] = {m["id"]: {"op": m["op"], "value": 30.0 if m["op"] == "current" else 20.0, "n": 3}
                                  for m in layout["measures"]}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("**/api/reporting/reports", reports_route)
    page.route("**/api/reporting/reports/*", report_route)
    page.route("**/api/reporting/run", run_route)


def test_definitions_screen_lists_layout_and_edits_persist(nexora_server, page):
    _login(page, nexora_server)
    saved = {}
    _stub(page, saved)
    page.goto(f"{nexora_server}/reporting?tab=definitions")
    expect(page.get_by_test_id("rs-layouts")).to_be_visible()
    expect(page.get_by_test_id("rl-title")).to_have_text("Ops standard")
    expect(page.get_by_test_id("rl-tile")).to_have_count(4)
    page.get_by_test_id("rl-edit").click()
    page.get_by_test_id("rl-add-measure-stddev").click()
    expect(page.get_by_test_id("rl-tile")).to_have_count(5)
    page.get_by_test_id("rl-edit").click()  # Done → save
    page.wait_for_function("() => window.__rlSaved || true")
    expect.poll(lambda: "updated" in saved).to_be(True)
    assert any(m["op"] == "stddev" for m in saved["updated"]["definition"]["measures"])


def test_definitions_redirect_route_opens_the_screen(nexora_server, page):
    _login(page, nexora_server)
    _stub(page, {})
    page.goto(f"{nexora_server}/reporting/definitions")
    expect(page).to_have_url(lambda u: "tab=definitions" in u)
    expect(page.get_by_test_id("rl-grid")).to_be_visible()


def test_editor_drag_reorders_and_corner_resize_persists(nexora_server, page):
    _login(page, nexora_server)
    saved = {}
    _stub(page, saved)
    page.goto(f"{nexora_server}/reporting?tab=definitions")
    page.get_by_test_id("rl-edit").click()
    tiles = page.get_by_test_id("rl-tile")
    tiles.nth(0).drag_to(tiles.nth(2))
    handle = tiles.nth(3).get_by_test_id("rdb-card-resize")
    box = handle.bounding_box()
    page.mouse.move(box["x"] + 4, box["y"] + 4)
    page.mouse.down()
    page.mouse.move(box["x"] + 4, box["y"] + 260, steps=6)
    page.mouse.up()
    page.get_by_test_id("rl-edit").click()
    expect.poll(lambda: "updated" in saved).to_be(True)
    ids = [t["id"] for t in saved["updated"]["definition"]["tiles"]]
    assert ids[0] != "t1"
    assert saved["updated"]["definition"]["tiles"][-1]["rows"] > 3


def test_wizard_picker_writes_layout_id_and_result_shows_tiles(nexora_server, page):
    _login(page, nexora_server)
    saved = {}
    _stub(page, saved)
    page.goto(f"{nexora_server}/reporting?tab=library")
    page.get_by_test_id("rs-new-report").click()
    expect(page.get_by_test_id("rs-layout-pick")).to_be_visible()
    page.get_by_test_id("rs-layout-pick").select_option("9")
    # Drive the wizard to Run using the shortest path the Simple e2e uses
    # (see test_wizard_category_breakdown_to_result_cards in test_reporting_simple.py).
    page.get_by_test_id("rs-measure-list").locator("button").first.click()
    page.get_by_test_id("rs-measure-next").click()
    page.get_by_test_id("rs-scope-next").click()
    page.get_by_test_id("rs-breakdown-next").click()
    page.get_by_test_id("rs-wizard-run").click()
    expect(page.get_by_test_id("rs-layout-grid")).to_be_visible()
    expect(page.get_by_test_id("rs-layout-tile")).to_have_count(4)
    expect(page.get_by_test_id("rl-kpi-value").first).to_have_text("30")
```

Adapt the wizard-driving steps to the real test ids in `tests/e2e/test_reporting_simple.py::test_wizard_category_breakdown_to_result_cards` (it stubs `/api/reporting/sources` and `/api/reporting/measures` too — copy its `_stub_*` helpers or import them). Drop the `wait_for_function("__rlSaved…")` line — `expect.poll` on `saved` is the real wait.

- [ ] **Step 2: Run locally if the TEST DB is free**

Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" NEXORA_E2E_PORT=8792 python -m pytest tests/e2e/test_reporting_layouts.py -q`
Expected: `4 passed`. Fix selectors against the rendered DOM, not by loosening the assertions.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_reporting_layouts.py
git commit -F - <<'EOF'
test(reporting): e2e for report definitions and layout tiles

Editor lists the layout, adds a measure and autosaves on Done; the redirect
route opens the screen; drag reorders and corner resize persist; the wizard
picker writes layoutId and the result renders the layout's tiles.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

### Task 13: Docs — `reporting.md`, `reporting-guide.md`, tips panel, changelog

**Files:**
- Modify: `docs/howto/reporting.md`
- Modify: `docs/howto/reporting-guide.md`
- Modify: `templates/_reporting_help.html`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: `docs/howto/reporting.md`**
  - "The Console shell" bullet **Workspace nav**: change `Library`, `Results`, `Dashboards`, `Scheduled` … to include `Report definitions` after Dashboards and note it maps into the Simple pane view `layouts`; `/reporting/definitions` redirects into it.
  - "Report-definition v1 JSON": add `"layoutId": 57` to the example and a paragraph **`layoutId` (optional)** — positive int naming a `kind: 'layout'` saved report the *caller* owns; the run response carries `layout` + `derived`, or `layoutFallback: "missing" | "invalid"`.
  - New section `## Report layouts ("Report definitions")` after Dashboards: the layout JSON from the spec, the six ops with their exact semantics (D3), the tile types and chart types, ownership (private), the editor's preview contract (inline `layout` on `/api/reporting/run`, D7), export's Measures block, D5's schedule caveat, and the file map (`nx_lib/reporting/derived.py`, `schema.validate_layout_definition`, `_shared._layout_block`, `static/js/reporting_grid.js`, `reporting_layout_view.js`, `reporting_layouts.js`).
  - Dashboards section: one line noting the grid engine now lives in `static/js/reporting_grid.js`.
- [ ] **Step 2: `docs/howto/reporting-guide.md`** — new section `## Report definitions` before `## Dashboards`, written for end users: what a definition is, how to create one (Report definitions in the rail → New definition → add measures, add chart/table tiles, drag, resize, Done), the six measures in plain words, how to use it (pick it at the top of the wizard or next to Saved reports in Advanced, before running), that it is private, what happens when you delete one, and that the Excel/CSV export lists the measures underneath. Add `Report definition` and `Measure (definition)` to "Words used on the page".
- [ ] **Step 3: `templates/_reporting_help.html`** — under `<h4>{{ _("Building a report") }}</h4>` add one `<li>`: `{{ _("Pick a Report definition in the wizard footer to see your own measures and tile layout instead of the standard result — create them under Report definitions in the rail.") }}`.
- [ ] **Step 4: `CHANGELOG.md`** under `## [Unreleased]` → `### Added` add:

```markdown
- **Report definitions (layouts).** A new *Report definitions* screen in the reporting rail
  lets a user save named bundles of derived measures — current value, mean, min/max, range,
  standard deviation, percentile — and a drag-and-drop 12-column tile layout (KPI tiles with
  optional sparkline, bar / stacked bar / line / area / pie / doughnut / gauge charts, table).
  Pick one at the top of the wizard or next to Saved reports in Advanced; the report stores
  `layoutId`, `/api/reporting/run` returns `layout` + `derived`, and the result renders as
  that tile grid. Exports append a Measures block. Layouts are private per user; a deleted
  one falls back to Standard. `/reporting/definitions` opens the screen. The dashboard's
  drag/resize engine moved to `static/js/reporting_grid.js` and is shared.
```

- [ ] **Step 5: Verify + commit**

Run: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" ENVIRONMENT=INT python -m pytest tests/unit/test_reporting_guide.py tests/unit/test_reporting_help_sync.py -q` → pass.

```bash
git add docs/howto/reporting.md docs/howto/reporting-guide.md templates/_reporting_help.html CHANGELOG.md
git commit -F - <<'EOF'
docs(reporting): report definitions (layouts) — howto, guide, tips, changelog

Architecture section with the layout JSON, measure semantics, run/export
contract and file map; end-user guide section; tips-panel line; Unreleased
changelog entry.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

### Task 14: Coverage thresholds and the endpoint inventory

**Files:**
- Modify (only if failing): `tests/unit/test_coverage_thresholds.py`, `tests/unit/test_create_app.py`

- [ ] **Step 1:** Run the whole fast tier for reporting: `PATH="/c/dev/nexora/.venv/Scripts:$PATH" ENVIRONMENT=INT python -m pytest tests/unit -q -k "reporting or create_app or coverage or template_url or static_v or inline_event"` and `PATH="/c/dev/nexora/.venv/Scripts:$PATH" python -m pytest tests/integration/test_reporting_routes.py -q --no-cov`.
- [ ] **Step 2:** `tests/unit/test_coverage_thresholds.py` parametrises `test_module_coverage_meets_threshold(module, min_pct)`; add `("nx_lib/reporting/derived.py", 90)` to its table (fully unit-tested). `tests/unit/test_create_app.py` asserts individual endpoints via `app.url_map.iter_rules()`; add a one-line `test_create_app_registers_reporting_definitions_endpoint` in the same style as `test_create_app_registers_login_endpoint`.
- [ ] **Step 3:** Commit only if something changed:

```bash
git add tests/unit/test_coverage_thresholds.py tests/unit/test_create_app.py
git commit -F - <<'EOF'
test(reporting): coverage floor for derived.py, endpoint inventory

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

### Task 15: Translations (`/nx-i18n`)

- [ ] **Step 1:** Run the `/nx-i18n` skill (extract → update → compile). Translate every new msgid in `de`, `fr`, `it` — the shim strings from Tasks 8, 10, 11, the rail label, the tips line. No fuzzy entries.
- [ ] **Step 2:** `PATH="/c/dev/nexora/.venv/Scripts:$PATH" ENVIRONMENT=INT python -m pytest tests/unit/test_translations.py -q` → pass. Diff-sweep the `.po` files for mangled lines (`reference_pybabel_malformed_msgstr_trap`).
- [ ] **Step 3:** Commit:

```bash
git add messages.pot translations
git commit -F - <<'EOF'
i18n(reporting): report definitions strings in de/fr/it

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

### Task 16: Browser verification + screenshots

- [ ] **Step 1:** `bin/nx.ps1 -r` (restart), then drive Playwright (own browser, own port, `--no-conflict`) logged in as `ben.streich`:
  1. `/reporting/definitions` → New definition → add **Percentile** (q 0.95) and **Min / Max**, add an **Area** chart tile, resize the table tile to 12×2, pick a real saved report under **Preview with** → `var/screenshots/layouts_editor.png`.
  2. Library → New report → pick that definition → run → `var/screenshots/layouts_result_tiles.png`; footer picker visible → `var/screenshots/layouts_picker_wizard.png`.
  3. Export the report as CSV and confirm the Measures block is at the bottom.
  4. Delete the definition, re-run the report → one warning toast, Standard result.
- [ ] **Step 2:** Kill the browser. Send the three screenshots with `SendUserFile` if the session is remote.
- [ ] **Step 3:** Run `/handoff-session-state` — no push, no PR.

---

## Gotchas & notes

- **Two peer sessions were editing reporting files on the parent branch while this plan was written.** Merge `refactor/255-admin-nav-tenancy-labels` into `plan/report-layouts` before Task 1 and again before Task 6; re-Grep every anchor in `run.py`, `reporting_simple.js`, `reporting_advanced.js`, `reporting_dashboard.js` after each merge.
- **`_prepare_run` copies `rd`** — the inline `layout` object and `layoutId` ride inside it into `validate_report_definition`. Unknown keys are ignored there; `layoutId` is checked explicitly (Task 2). If a future validator rejects unknown keys, strip `layout` in `_layout_block`'s caller.
- **`kind: 'layout'` rows leak into every list consumer.** Task 7/8 filter them in `navTo`, `loadLibrary`'s grouping, the rail counts and the Advanced saved-reports dropdown. Grep `kind !== 'dashboard'` once more after Task 11 — any remaining site is a place a layout would show as a report.
- **Autosave timing in e2e:** the editor saves 600 ms after the last change and on Done. Tests assert on Done (`rl-edit` click), never on the debounce.
- **`getComputedStyle` in Node:** `reporting_layout_view.js` guards `cssVar` so `seriesFor` can be tested headless. Keep any new DOM access inside `render`, never at module scope.
- **Gauge without measures:** falls back to the first dataset's min/max/last. That is fine for a date series and meaningless for a category breakdown — the docs say so; no guard in code.
- **Chart.js dataset colours** use `--nx-series-1..5`, which the dashboard-console plan introduced. If those tokens are absent on this branch (Grep `--nx-series-1` in `static/css/nexora-ui.css`), fall back is `#4f46e5`; add the tokens rather than hardcoding a palette.
- **Deferred to follow-ups (say so, do not build):** change/target measures, dashboards honouring layouts, shared layouts, schedule mails with the Measures block (D5), a card-title editor for tiles.
