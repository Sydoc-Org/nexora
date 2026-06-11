# Reporting: Drill-Through to Underlying Rows — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Click a chart element or aggregate-table row on either reporting tab and a slide-over drawer shows the raw document rows behind that number, with workitem deep-links and CSV/XLSX export.

**Architecture:** A pure client-side definition transform (`ReportingDrill.buildDrillDefinition`) turns the clicked group into `eq`/`gte`+`lt`/`is_null` filters on a metric-less copy of the definition and re-POSTs it through the existing `/api/reporting/run` — validator, grants, row scope, and caps apply unchanged. One small backend fix makes `is_null` on a field a process doesn't expose trivially true (symmetric with `NULL AS [field]` projection), so "(null)" groups drill correctly. Spec: `docs/superpowers/specs/2026-06-11-reporting-drill-through-design.md`.

**Tech Stack:** Flask, Jinja2 + vanilla ES5 IIFE, Chart.js 4.5.1, pytest + Playwright, Flask-Babel.

---

## Context an engineer needs (read first)

- **Branch:** `feature/2.5.63`.
- **SEQUENCING — do not skip:** Task 1 (backend) may start immediately. **Tasks 2–8 are
  blocked until the `feat/rich-export` worktree is merged** into `feature/2.5.63` — it
  rewrites `mountChart()`/result panels in `templates/js/_reporting_simple_js.html`,
  `templates/js/_reporting_js.html`, `templates/js/_reporting_viz_js.html`,
  `templates/reporting.html` and `static/css/reporting.css`, and introduces the
  multi-series chart shape (`state.chartData.multiSeries`) that drill clicks must
  interpret. Verify before starting Task 2: `git log --oneline -20` shows the rich-export
  merge (commits like "multi-series charts", "Show query panel"), and `git worktree list`
  no longer shows `.claude/worktrees/rich-export` (or its branch is merged).
- **Anchor on quoted code and function names, not line numbers** — the rich-export merge
  shifts every line in the frontend files.
- **Jinja template cache:** nexora caches templates for the process lifetime. Restart the
  dev server (`nx -u`) after every template edit before browser-verifying.
- **E2E constraint:** the TEST env has **no Statistics DB** — e2e must use admin-seeded
  `table`-provider sources. Reuse the seeding + wizard-walk pattern from
  `tests/e2e/test_reporting_simple.py::test_wizard_category_breakdown_to_result_cards`.
- **Pre-commit hook** auto-runs `db-migrate --env INT` + sync check; on the known
  CRLF-checksum complaint use the documented escape hatch `SQL_SYNC_SKIP=1 git commit ...`.
- **i18n:** every new `{{ _("...") }}` string must go through the pybabel cycle (Task 7)
  or `tests/unit/test_translations.py` fails.
- **No migrations, no new permissions, no new dependencies** anywhere in this plan.
- Key verified facts: `FILTER_OPS` in `nx_lib/reporting/schema.py` already contains
  `eq/gte/lt/is_null/is_not_null`; both query builders emit SQL for them. The metric-less
  raw-row path exists in `build_table_query` (`SELECT TOP (cap) ... FROM (union) t`).
  Grain SQL truncates dates to bucket starts (month → `2026-04-01`, week → Monday).
  The run endpoint is `POST /api/reporting/run`; export is `POST /api/reporting/export`.
  The Simple pane caches `/api/reporting/sources` in `state.sources`; each source carries
  `fields` (`{field, label, grainable, filterable, ...}`). The workitems page accepts
  `/workitems?search=<workitem-id>`. CSRF: POSTs need the `X-CSRFToken` header from
  `document.querySelector('meta[name="csrf-token"]').content`.

### Decisions locked in (owner, 2026-06-11)

| # | Question | Decision |
|---|----------|----------|
| 1 | Click targets | Chart elements + aggregate-table rows, both tabs. Not the big-number card, not pivot cells. |
| 2 | Detail columns | Fixed smart set (`workitem_id`, `processname`, `import_date`, `export_date` + breakdown fields, intersected with the catalog); generic table sources top up to ~6 leading catalog columns. |
| 3 | Panel UX | Slide-over drawer from the right (~45%, min 420px), Esc/✕/backdrop close, content replaced on next click. |
| 4 | Approach | Client transform through existing run endpoint + `is_null` projection/filter symmetry fix. |

---

# PHASE 1 — Backend (safe immediately)

### Task 1: `is_null` symmetry — keep subqueries for processes lacking the filtered field

Today `build_table_query` projects a field a process doesn't expose as `NULL AS [field]`
(its rows land in the "(null)" aggregate group) but **drops the whole process subquery**
when any filter references such a field. For `is_null` that is wrong — the filter is
trivially true for those rows. Every other op keeps the drop (they can never match).

**Files:**
- Modify: `nx_lib/reporting/query.py` (`build_table_query`)
- Test: `tests/unit/test_reporting_query.py`

- [ ] **Step 1: Write the failing tests.** The file's fixtures already model the exact
  situation: `PROCESS_CONFIGS` has two processes and `FIELD_COL_MAPS` maps `pages` only
  for `acme.inv`. Append:

```python
def test_is_null_filter_keeps_process_lacking_the_field():
    """is_null on a field a process doesn't expose is trivially true there:
    the subquery is kept (projection emits NULL for it) and carries no clause."""
    rd = _rd(filters=[{"field": "pages", "op": "is_null"}],
             columns=[{"field": "doctype", "header": None, "agg": None}],
             sort=[])
    sql, params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "dbo].[StatA" in sql or "[dbo].[StatA]" in sql   # process with the column
    assert "dbo].[StatB" in sql or "[dbo].[StatB]" in sql   # process lacking it — kept
    assert sql.count("IS NULL") == 1                        # clause only where mapped


def test_is_not_null_filter_still_drops_process_lacking_the_field():
    """is_not_null can never match rows that project the field as NULL."""
    rd = _rd(filters=[{"field": "pages", "op": "is_not_null"}],
             columns=[{"field": "doctype", "header": None, "agg": None}],
             sort=[])
    sql, params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "StatB" not in sql


def test_eq_filter_still_drops_process_lacking_the_field():
    """Existing drop behavior for value-ops is unchanged."""
    rd = _rd(filters=[{"field": "pages", "op": "eq", "value": 3}],
             columns=[{"field": "doctype", "header": None, "agg": None}],
             sort=[])
    sql, params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "StatB" not in sql
```

  (Adapt the `columns`/`sort` keys to whatever the neighbouring tests pass — e.g.
  `test_filter_field_unmapped_in_process_excludes_that_process` is the existing test
  pinning today's drop behavior for value-ops; leave it green.)

- [ ] **Step 2: Run them, watch the first one fail**

```powershell
python -m pytest tests/unit/test_reporting_query.py -v -k "lacking_the_field"
```
Expected: `test_is_null_filter_keeps_process_lacking_the_field` FAILS (StatB missing);
the other two PASS (they pin current behavior).

- [ ] **Step 3: Implement.** In `nx_lib/reporting/query.py`, inside `build_table_query`,
  find:

```python
        # A filter referencing a field this process doesn't expose can never
        # match here — drop the whole subquery for correctness.
        if any(f["field"] not in filt_resolved for f in col_filters):
            continue
```

  and replace with:

```python
        # A filter referencing a field this process doesn't expose can never
        # match here — drop the whole subquery. Exception: is_null is trivially
        # TRUE for such a process (the projection emits NULL for that field),
        # so it keeps the subquery and simply emits no clause.
        if any(
            f["field"] not in filt_resolved and f["op"] != "is_null"
            for f in col_filters
        ):
            continue
```

  The WHERE loop below already skips unresolved fields (`if not col: continue`), so the
  kept subquery emits no clause for the `is_null` filter — no further change needed.

- [ ] **Step 4: Run the full file**

```powershell
python -m pytest tests/unit/test_reporting_query.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add nx_lib/reporting/query.py tests/unit/test_reporting_query.py
git commit -m "fix(reporting): is_null filter keeps processes lacking the field (matches NULL projection)"
```

---

# PHASE 2 — Frontend (BLOCKED until feat/rich-export is merged — see Context)

### Task 2: `ReportingDrill` partial — pure transform + drawer markup/CSS

**Files:**
- Create: `templates/js/_reporting_drill_js.html`
- Modify: `templates/reporting.html` (drawer markup + include the partial)
- Modify: `static/css/reporting.css`

- [ ] **Step 1: Create `templates/js/_reporting_drill_js.html`** with the shared module.
  ES5 IIFE like the other partials; exposed globally so both tabs and `page.evaluate`
  tests reach it:

```html
<script>
/* Drill-through: click an aggregate number, see the rows behind it.
   Shared by the Simple and Advanced panes. */
window.ReportingDrill = (function () {
  'use strict';
  var csrf = document.querySelector('meta[name="csrf-token"]').content;
  var I18N = {
    title: {{ _("Rows behind this number")|tojson }},
    distinctNote: {{ _("Rows contributing to this number — the distinct count may be smaller.")|tojson }},
    truncatedNote: {{ _("Showing the first {n} rows — export to get all.")|tojson }},
    nullLabel: {{ _("(empty)")|tojson }},
    loadError: {{ _("Could not load the rows behind this number.")|tojson }},
    close: {{ _("Close")|tojson }}
  };

  var SMART_FIELDS = ['workitem_id', 'processname', 'import_date', 'export_date'];

  function addGrainUpper(startStr, grain) {
    var s = String(startStr).slice(0, 10);
    var p = s.split('-');
    if (p.length !== 3) return null;
    var d = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2]));
    if (isNaN(d.getTime())) return null;
    if (grain === 'day') d.setUTCDate(d.getUTCDate() + 1);
    else if (grain === 'week') d.setUTCDate(d.getUTCDate() + 7);
    else if (grain === 'month') d.setUTCMonth(d.getUTCMonth() + 1);
    else if (grain === 'quarter') d.setUTCMonth(d.getUTCMonth() + 3);
    else if (grain === 'year') d.setUTCFullYear(d.getUTCFullYear() + 1);
    else return null;
    return d.toISOString().slice(0, 10);
  }

  /* def: the definition that produced the current aggregate result.
     fields: the source catalog's field list ({field,label,grainable,filterable}).
     clicked: [{field, grain?, value}] — one entry per definition column, in order.
     Returns a raw-row drill definition, or null when drilling is not possible. */
  function buildDrillDefinition(def, fields, clicked) {
    if (!def || !def.source || !clicked || !clicked.length) return null;
    var byField = {};
    (fields || []).forEach(function (f) { byField[f.field] = f; });
    for (var i = 0; i < clicked.length; i++) {
      var cf = byField[clicked[i].field];
      if (!cf || cf.filterable === false) return null;
    }
    var filters = (def.filters || []).map(function (x) {
      return JSON.parse(JSON.stringify(x));
    });
    clicked.forEach(function (c) {
      if (c.grain) {
        var upper = addGrainUpper(c.value, c.grain);
        if (!upper) return;
        filters.push({ field: c.field, op: 'gte', value: String(c.value).slice(0, 10) });
        filters.push({ field: c.field, op: 'lt', value: upper });
      } else if (c.value === null || c.value === undefined || c.value === '') {
        filters.push({ field: c.field, op: 'is_null' });
      } else {
        filters.push({ field: c.field, op: 'eq', value: c.value });
      }
    });
    var cols = [];
    SMART_FIELDS.concat(clicked.map(function (c) { return c.field; }))
      .forEach(function (fd) {
        if (byField[fd] && cols.indexOf(fd) === -1 && cols.length < 8) cols.push(fd);
      });
    var hasSmart = SMART_FIELDS.some(function (fd) { return !!byField[fd]; });
    if (!hasSmart) {           // generic table source: top up with leading columns
      for (var j = 0; j < (fields || []).length && cols.length < 6; j++) {
        if (cols.indexOf(fields[j].field) === -1) cols.push(fields[j].field);
      }
    }
    if (!cols.length) return null;
    var sortField = cols.indexOf('export_date') !== -1 ? 'export_date' : cols[0];
    var dd = {
      schemaVersion: 1,
      source: def.source,
      title: def.title || 'drill',
      visualization: 'table',
      columns: cols.map(function (fd) { return { field: fd }; }),
      filters: filters,
      sort: [{ field: sortField, dir: sortField === 'export_date' ? 'desc' : 'asc' }],
      rowLimit: 100
    };
    if (def.scope) dd.scope = JSON.parse(JSON.stringify(def.scope));
    return dd;
  }

  // ---- drawer rendering (open/close/fetch) is added in Task 3 ----

  return {
    buildDrillDefinition: buildDrillDefinition,
    addGrainUpper: addGrainUpper,
    I18N: I18N
  };
})();
</script>
```

- [ ] **Step 2: Drawer markup.** In `templates/reporting.html`, before the closing
  scripts (next to where other shared modals/partials sit — both tabs live on this page),
  add:

```html
  <div id="rdBackdrop" class="reporting-drill-backdrop" hidden></div>
  <aside id="rdPanel" class="reporting-drill-panel" hidden role="dialog"
         aria-labelledby="rdTitle" data-testid="reporting-drill-panel">
    <div class="reporting-drill-head">
      <div>
        <h3 id="rdTitle"></h3>
        <p id="rdSubtitle" class="reporting-drill-subtitle"></p>
      </div>
      <button type="button" id="rdClose" class="reporting-link"
              aria-label="{{ _('Close') }}" data-testid="reporting-drill-close">&#10005;</button>
    </div>
    <div id="rdBody" class="reporting-drill-body"></div>
    <div class="reporting-drill-foot">
      <p id="rdNote" class="reporting-drill-note"></p>
      {% if has_permission('reporting.export') %}
      <span>
        <button type="button" id="rdExportCsv" class="reporting-link"
                data-testid="reporting-drill-export-csv">CSV</button>
        <button type="button" id="rdExportXlsx" class="reporting-link"
                data-testid="reporting-drill-export-xlsx">XLSX</button>
      </span>
      {% endif %}
    </div>
  </aside>
```

  and include the new partial next to the other `templates/js/_reporting_*` includes:

```jinja
  {% include "js/_reporting_drill_js.html" %}
```

  (Match the exact include syntax of the neighbouring partial includes in the file —
  include it **before** `_reporting_simple_js.html` / `_reporting_js.html` so
  `ReportingDrill` exists when they wire click handlers.)

- [ ] **Step 3: CSS.** Append to `static/css/reporting.css`:

```css
.reporting-drill-backdrop { position: fixed; inset: 0; background: rgba(17, 24, 39, .35); z-index: 60; }
.reporting-drill-panel { position: fixed; top: 0; right: 0; bottom: 0; width: 45vw; min-width: 420px; max-width: 720px; background: #fff; box-shadow: -8px 0 24px rgba(0, 0, 0, .15); z-index: 61; display: flex; flex-direction: column; }
.reporting-drill-head { display: flex; justify-content: space-between; align-items: flex-start; padding: 16px; border-bottom: 1px solid #e5e7eb; }
.reporting-drill-head h3 { margin: 0; font-size: 15px; }
.reporting-drill-subtitle { margin: 4px 0 0; font-size: 12px; color: #6b7280; }
.reporting-drill-body { flex: 1; overflow: auto; padding: 0 16px; }
.reporting-drill-body table { width: 100%; border-collapse: collapse; font-size: 12px; }
.reporting-drill-body th, .reporting-drill-body td { padding: 6px 8px; border-bottom: 1px solid #f3f4f6; text-align: left; white-space: nowrap; }
.reporting-drill-foot { display: flex; justify-content: space-between; align-items: center; padding: 10px 16px; border-top: 1px solid #e5e7eb; }
.reporting-drill-note { margin: 0; font-size: 12px; color: #6b7280; }
.reporting-drill-null { color: #9ca3af; font-style: italic; }
.reporting-drill-clickable tbody tr { cursor: pointer; }
.reporting-drill-clickable tbody tr:hover { background: #f5f7ff; }
@media (max-width: 900px) { .reporting-drill-panel { width: 100vw; min-width: 0; } }
```

- [ ] **Step 4: Restart server, smoke-check** — `nx -u`, open `/reporting`, confirm the
  page still renders (drawer is `hidden`) and `window.ReportingDrill` exists in DevTools.

- [ ] **Step 5: Commit**

```powershell
git add templates/js/_reporting_drill_js.html templates/reporting.html static/css/reporting.css
git commit -m "feat(reporting): ReportingDrill module — drill definition transform and drawer shell"
```

---

### Task 3: Drawer behavior — open, fetch, render, export

**Files:**
- Modify: `templates/js/_reporting_drill_js.html`

- [ ] **Step 1: Add the drawer logic** inside the IIFE (above the `return`), and extend
  the return object:

```js
  function el(id) { return document.getElementById(id); }
  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  var current = null;   // {definition} of the open drill, for export

  function close() {
    el('rdPanel').hidden = true;
    el('rdBackdrop').hidden = true;
    current = null;
  }

  function renderRows(columns, rows, truncated, isDistinct) {
    var head = '<tr>' + columns.map(function (c) {
      return '<th>' + esc(c.header || c.field) + '</th>';
    }).join('') + '</tr>';
    var wiIdx = -1;
    columns.forEach(function (c, i) { if (c.field === 'workitem_id') wiIdx = i; });
    var body = rows.map(function (r) {
      return '<tr>' + r.map(function (v, i) {
        var cell = v == null ? '<span class="reporting-drill-null">' + esc(I18N.nullLabel) + '</span>'
                             : esc(String(v).slice(0, 200));
        if (i === wiIdx && v != null) {
          cell = '<a href="/workitems?search=' + encodeURIComponent(String(v)) +
                 '" target="_blank" rel="noopener">' + esc(String(v)) + '</a>';
        }
        return '<td>' + cell + '</td>';
      }).join('') + '</tr>';
    }).join('');
    el('rdBody').innerHTML = '<table><thead>' + head + '</thead><tbody>' + body + '</tbody></table>';
    var notes = [];
    if (isDistinct) notes.push(I18N.distinctNote);
    if (truncated) notes.push(I18N.truncatedNote.replace('{n}', String(rows.length)));
    el('rdNote').textContent = notes.join(' ');
  }

  /* opts: {definition, fields, clicked, header, isDistinct} */
  function open(opts) {
    var dd = buildDrillDefinition(opts.definition, opts.fields, opts.clicked);
    if (!dd) return;
    current = { definition: dd };
    el('rdTitle').textContent = opts.header || I18N.title;
    el('rdSubtitle').textContent = I18N.title;
    el('rdBody').innerHTML = '<p class="reporting-drill-note">…</p>';
    el('rdNote').textContent = '';
    el('rdPanel').hidden = false;
    el('rdBackdrop').hidden = false;
    fetch('/api/reporting/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify(dd)
    }).then(function (res) {
      return res.json().then(function (data) { return { ok: res.ok, data: data }; });
    }).then(function (r) {
      if (!current) return;                       // closed while loading
      if (!r.ok) {
        el('rdBody').innerHTML = '<p class="reporting-drill-note">' +
          esc((r.data && r.data.error) || I18N.loadError) + '</p>';
        return;
      }
      renderRows(r.data.columns || [], r.data.rows || [], !!r.data.truncated,
                 !!opts.isDistinct);
    }).catch(function () {
      if (current) {
        el('rdBody').innerHTML = '<p class="reporting-drill-note">' + esc(I18N.loadError) + '</p>';
      }
    });
  }

  function exportDrill(format) {
    if (!current) return;
    // Mirror the host tab's export call: same endpoint/body shape as the
    // existing export button listener (search for "/api/reporting/export" in
    // _reporting_simple_js.html and reuse its body + download handling),
    // swapping in current.definition and the chosen format.
  }

  function wire() {
    el('rdClose').addEventListener('click', close);
    el('rdBackdrop').addEventListener('click', close);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !el('rdPanel').hidden) close();
    });
    if (el('rdExportCsv')) {
      el('rdExportCsv').addEventListener('click', function () { exportDrill('csv'); });
      el('rdExportXlsx').addEventListener('click', function () { exportDrill('xlsx'); });
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
```

  Extend the return object to:

```js
  return {
    buildDrillDefinition: buildDrillDefinition,
    addGrainUpper: addGrainUpper,
    open: open,
    close: close,
    I18N: I18N
  };
```

- [ ] **Step 2: Implement `exportDrill` for real.** Open
  `templates/js/_reporting_simple_js.html`, find the `rsExport` click listener (it POSTs
  to `/api/reporting/export` and triggers a download via a blob anchor). Copy that exact
  fetch/download body into `exportDrill`, replacing the definition with
  `current.definition` and the format with the `format` argument. Keep the blob/anchor
  download idiom identical.

- [ ] **Step 3: Restart server, manual smoke-check** in DevTools on `/reporting`:

```js
ReportingDrill.open({
  definition: {source: '<a seeded source id>', columns: [{field: '<a field>'}], filters: []},
  fields: [{field: '<a field>', filterable: true}],
  clicked: [{field: '<a field>', value: '<a real value>'}]
});
```
Expected: drawer slides in, rows render (or a clean error message if the value matches
nothing). Esc closes.

- [ ] **Step 4: Commit**

```powershell
git add templates/js/_reporting_drill_js.html
git commit -m "feat(reporting): drill drawer — fetch, render, workitem links, export"
```

---

### Task 4: Wire the Simple pane (chart clicks + table rows)

**Files:**
- Modify: `templates/js/_reporting_simple_js.html`
- Modify: `templates/_reporting_simple.html` (hint line)

The exact function bodies depend on the rich-export merge; anchor on these names:
`mountChart()` builds `state.chartData` (`labels`, `datasets`, `multiSeries`),
`renderChart(type)` creates the Chart.js instance, `renderTable()` renders the result
table, `state.current.def` holds the definition that produced the result, and
`state.current.data` (or the equivalent — search for where the run response is stashed)
holds `columns`/`rows`.

- [ ] **Step 1: Stash raw click values when building chart data.** In `mountChart()`,
  wherever `state.chartData` is assembled, also stash the **raw row values** (labels are
  display strings — `''` may mean NULL):
  - single-dim branch: `state.chartData.rawX = <array of raw first-dim values, same order as labels>;`
  - multi-series branch: `state.chartData.rawX = xOrder;` and
    `state.chartData.rawSeries = series;` (the pivot's x and series key arrays — note
    the pivot stringifies, so `''` represents NULL).

- [ ] **Step 2: Helper to build `clicked` and open the drawer.** Add next to the chart
  code:

```js
  function drillFromChart(index, datasetIndex) {
    var cur = state.current;
    if (!cur || !cur.def) return;
    var dims = (cur.def.columns || []);
    if (!dims.length) return;
    var cd = state.chartData || {};
    var clicked = [{
      field: dims[0].field, grain: dims[0].grain || null,
      value: (cd.rawX || cd.labels || [])[index]
    }];
    if (cd.multiSeries && dims.length > 1) {
      clicked.push({
        field: dims[1].field, grain: null,
        value: (cd.rawSeries || [])[datasetIndex]
      });
    }
    openDrill(clicked);
  }

  function openDrill(clicked) {
    var cur = state.current;
    var src = (state.sources || []).find(function (s) { return s.id === cur.def.source; });
    if (!src) return;
    // header: "Label = value · Label = value"
    var header = clicked.map(function (c) {
      var f = (src.fields || []).find(function (x) { return x.field === c.field; });
      var v = (c.value === null || c.value === undefined || c.value === '')
        ? ReportingDrill.I18N.nullLabel : String(c.value).slice(0, 60);
      return ((f && f.label) || c.field) + ' = ' + v;
    }).join(' · ');
    var isDistinct = /distinct/i.test(String(cur.metricAgg || ''));
    ReportingDrill.open({
      definition: cur.def, fields: src.fields || [],
      clicked: clicked, header: header, isDistinct: isDistinct
    });
  }
```

  For `isDistinct`: the metric's aggregation is known where the measure was chosen
  (the wizard's metric list from `/api/reporting/metrics` carries `aggregation`) — stash
  it on `state.current` when the run fires (e.g. `state.current.metricAgg = m.aggregation`)
  and test `/distinct/`. Adapt to the file's actual metric bookkeeping.

- [ ] **Step 3: Chart `onClick`/`onHover`.** In `renderChart(type)`, extend the Chart.js
  `options` literal:

```js
      onClick: function (evt) {
        var els = this.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, false);
        if (els.length) drillFromChart(els[0].index, els[0].datasetIndex);
      },
      onHover: function (evt, els) {
        evt.native.target.style.cursor = els.length ? 'pointer' : 'default';
      }
```

  Drill must only engage for aggregate results: guard `drillFromChart` with
  `if (!(cur.def.metrics || []).length) return;`.

- [ ] **Step 4: Table rows.** In `renderTable()`, when the producing definition has at
  least one metric **and** at least one dimension and
  `ReportingDrill.buildDrillDefinition(cur.def, src.fields, clickedFor(firstRowValues))`
  returns non-null (probe once with the first row to decide the affordance), add the
  `reporting-drill-clickable` class to the table and per-row:

```js
      tr.tabIndex = 0;
      tr.addEventListener('click', function () { openDrill(clickedFor(rowValues)); });
      tr.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') openDrill(clickedFor(rowValues));
      });
```

  where `clickedFor(rowValues)` maps the definition's columns (dimensions come first in
  the result columns) to `{field, grain, value}` from the row's leading cells:

```js
  function clickedFor(rowValues) {
    return (state.current.def.columns || []).map(function (c, i) {
      return { field: c.field, grain: c.grain || null, value: rowValues[i] };
    });
  }
```

- [ ] **Step 5: Hint line.** In `templates/_reporting_simple.html`, under the result
  table card, add:

```html
      <p class="reporting-simple-hint" id="rsDrillHint" hidden>{{ _("Click a row or chart element to see the documents behind it.") }}</p>
```

  Show it (`hidden = false`) from `renderTable()` exactly when rows are drillable.

- [ ] **Step 6: Restart + browser-verify on INT** (`nx -u -b --loginas:<admin user>`):
  run a wizard report with one breakdown, click a bar and a table row, drawer shows rows.
  Screenshot to `var/screenshots/`.

- [ ] **Step 7: Commit**

```powershell
git add templates/js/_reporting_simple_js.html templates/_reporting_simple.html
git commit -m "feat(reporting): drill-through from Simple charts and result rows"
```

---

### Task 5: Wire the Advanced pane (chart + grid rows)

**Files:**
- Modify: `templates/js/_reporting_js.html`
- Modify: `templates/js/_reporting_viz_js.html` (only if the chart instance/options are created there)

- [ ] **Step 1: Locate the Advanced state.** In `templates/js/_reporting_js.html`, find
  where the run response is stashed (search for `lastResult` / where `renderResults` or
  the grid renderer consumes `columns`/`rows`) and where the current definition is held
  (the builder state that was POSTed). Advanced drills only for definitions with
  `metrics.length >= 1` and `columns.length >= 1` and `kind !== 'sql'` (SQL-sandbox
  results carry no definition to transform — no drill there).

- [ ] **Step 2: Reuse the same two helpers.** Port `drillFromChart`/`openDrill`/
  `clickedFor` from Task 4 with the Advanced equivalents: source fields come from the
  Advanced pane's source/catalog cache (search for where the builder lists fields), and
  the chart's raw x/series arrays mirror whatever the Advanced chart mount builds (in
  `_reporting_viz_js.html` after rich-export). If the viz module owns the Chart.js
  `options`, add the same `onClick`/`onHover` there, parameterized with a callback the
  Advanced pane passes in (keep the viz module tab-agnostic: it should accept an
  `onElementClick(index, datasetIndex)` option rather than reference Advanced state).

- [ ] **Step 3: Grid rows.** Same pattern as Task 4 Step 4 on the Advanced grid renderer
  (aggregate results only).

- [ ] **Step 4: Restart + browser-verify on INT**: Advanced aggregate report (metrics +
  dimension), click chart element and grid row, drawer works; verify a SQL-sandbox run
  shows **no** drill affordance. Screenshot to `var/screenshots/`.

- [ ] **Step 5: Commit**

```powershell
git add templates/js/_reporting_js.html templates/js/_reporting_viz_js.html
git commit -m "feat(reporting): drill-through from Advanced charts and grid rows"
```

---

### Task 6: E2E tests

**Files:**
- Test: `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Transform tests via `page.evaluate`** (pins the pure function without
  chart pixel-clicks). Append:

```python
def test_drill_transform_category_eq(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    dd = page.evaluate("""() => ReportingDrill.buildDrillDefinition(
        {source: 's1', columns: [{field: 'doctype'}],
         filters: [{field: 'status', op: 'eq', value: 'ok'}]},
        [{field: 'doctype', filterable: true}, {field: 'status', filterable: true}],
        [{field: 'doctype', value: 'invoice'}])""")
    assert dd["rowLimit"] == 100
    assert {"field": "doctype", "op": "eq", "value": "invoice"} in dd["filters"]
    assert {"field": "status", "op": "eq", "value": "ok"} in dd["filters"]
    assert "metrics" not in dd or not dd["metrics"]


def test_drill_transform_month_grain_bounds(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    dd = page.evaluate("""() => ReportingDrill.buildDrillDefinition(
        {source: 's1', columns: [{field: 'exportdate', grain: 'month'}], filters: []},
        [{field: 'exportdate', filterable: true, grainable: true}],
        [{field: 'exportdate', grain: 'month', value: '2026-04-01'}])""")
    assert {"field": "exportdate", "op": "gte", "value": "2026-04-01"} in dd["filters"]
    assert {"field": "exportdate", "op": "lt", "value": "2026-05-01"} in dd["filters"]


def test_drill_transform_null_group_uses_is_null(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    dd = page.evaluate("""() => ReportingDrill.buildDrillDefinition(
        {source: 's1', columns: [{field: 'doctype'}], filters: []},
        [{field: 'doctype', filterable: true}],
        [{field: 'doctype', value: null}])""")
    assert {"field": "doctype", "op": "is_null"} in dd["filters"]


def test_drill_transform_unfilterable_dim_returns_null(nexora_server, page):
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    dd = page.evaluate("""() => ReportingDrill.buildDrillDefinition(
        {source: 's1', columns: [{field: 'doctype'}], filters: []},
        [{field: 'doctype', filterable: false}],
        [{field: 'doctype', value: 'x'}])""")
    assert dd is None
```

- [ ] **Step 2: Drawer e2e through the wizard.** Reuse the seeding + wizard walk from
  `test_wizard_category_breakdown_to_result_cards` (same fixtures, same clicks — include
  the breakdown **Continue** step the rich-export work added), then:

```python
def test_drill_row_opens_panel(nexora_server, page):
    """Clicking an aggregate result row opens the drill drawer with rows."""
    # ... seeded source + wizard walk to a 1-breakdown result, as in
    # test_wizard_category_breakdown_to_result_cards ...
    page.locator("#rsTable tbody tr").first.click()
    panel = page.get_by_test_id("reporting-drill-panel")
    expect(panel).to_be_visible()
    expect(panel.locator("tbody tr").first).to_be_visible()
    page.keyboard.press("Escape")
    expect(panel).to_be_hidden()
```

  (Adapt the result-table locator to the Simple table's real id; the seeded table source
  must expose at least one drillable string field.)

- [ ] **Step 3: Reset + run**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_simple.py -v
```
Expected: all PASS (new tests plus no regressions).

- [ ] **Step 4: Commit**

```powershell
git add tests/e2e/test_reporting_simple.py
git commit -m "test(reporting): drill-through transform and drawer e2e coverage"
```

---

### Task 7: i18n cycle

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`)

- [ ] **Step 1: Extract + update**

```powershell
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
```

- [ ] **Step 2: Translate every new msgid** in de/fr/it (the drill strings from Tasks 2–4:
  "Rows behind this number", the distinct/truncated notes, "(empty)", "Close", the load
  error, the hint line). No fuzzy entries.

- [ ] **Step 3: Compile + verify**

```powershell
pybabel compile -d translations
python -m pytest tests/unit/test_translations.py -v
```
Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add messages.pot translations
git commit -m "chore(i18n): translate reporting drill-through strings (de/fr/it)"
```

---

### Task 8: Docs, changelog, full verification

**Files:**
- Modify: `docs/howto/reporting.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Document.** Add a "Drill-through" subsection to `docs/howto/reporting.md`
  (where the result views are described): what is clickable, the smart-set columns, the
  100-row display cap vs full export, the distinct-count caveat, and that drill rows obey
  the same grants/scope as any report.

- [ ] **Step 2: Changelog.** Under `[Unreleased]` → Added:

```markdown
- Reporting: drill-through — click a chart element or aggregate row to see the underlying
  document rows in a slide-over panel, with workitem links and CSV/XLSX export.
- Reporting: `is_null` filters now match rows from processes that don't expose the field
  (consistent with how those rows are projected into "(null)" groups).
```

- [ ] **Step 3: Full test suite + browser pass**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/unit tests/integration -v
python -m pytest tests/e2e -v
```
Expected: all PASS. Then on INT (`nx -u -b --loginas:<admin user>`): docprocessing
"doc count by docsource per month" → click a month bar → rows match the period; click a
"(null)" group if one exists → rows appear (validates Task 1 end-to-end); a
`workitem_id` link opens the workitem. Screenshots to `var/screenshots/`.

- [ ] **Step 4: Commit**

```powershell
git add docs/howto/reporting.md CHANGELOG.md
git commit -m "docs(reporting): drill-through feature docs and changelog"
```
