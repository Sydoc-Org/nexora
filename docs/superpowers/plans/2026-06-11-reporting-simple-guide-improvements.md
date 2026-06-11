# Reporting Simple Guide (Wizard) Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the Simple tab's guided wizard: curated breakdown dimensions, explained/ switchable charts, a prominent process-scope control, wizard re-entry for saved reports, sane Back/Exit navigation, and a proper Save-as dialog in Advanced.

**Architecture:** All changes are client-side template/JS edits in the Simple pane (`templates/js/_reporting_simple_js.html` + `templates/_reporting_simple.html`), the Advanced builder (`templates/js/_reporting_js.html` + `templates/reporting.html`), and `static/css/reporting.css`. **No backend or migration changes** — the run validator already ignores unknown definition keys (verified: `nx_lib/reporting/schema.py` reads only known keys), so the chart-type preference rides inside the saved definition JSON. The wizard's definition emitter (`wizardDefinition()`) is invertible, so saved-report re-entry uses a pure client-side reverse-mapper — no schema change, works for pre-existing saved reports.

**Tech Stack:** Jinja2 templates, vanilla JS (ES5-style IIFE, the file's existing idiom), Chart.js 4.5.1, Flask-Babel i18n, Playwright e2e (pytest).

---

## Context an engineer needs (read first)

- **Branch:** work directly on `feature/2.5.63` (current feature branch; status clean at plan time).
- **The Simple pane is a self-contained IIFE** in `templates/js/_reporting_simple_js.html`. It owns a private Chart.js instance (`state.chart`) and must never call `window.ReportingViz` (that is the Advanced pane's singleton).
- **Wizard state shape** (`state.wiz`, set in `startWizard()` line 661-662):
  `{ measure, source, breakdown: {kind:'date'|'category', field} | {kind:'none'}, scopeProcs: [], range: null | {token:'...'} | ['YYYY-MM-DD','YYYY-MM-DD'], dateField, _fp }`.
  Grain is NOT in `state.wiz` — `wizardDefinition()` reads `el('rsGrain').value` live from the DOM.
- **Jinja template cache:** nexora caches templates for the process lifetime. Restart the dev server (`nx -u`) after every template edit before browser-verifying.
- **E2E constraint:** the TEST env has **no Statistics DB**, so the `docprocessing` source can never be *run* in e2e. All wizard e2e tests use admin-seeded `table`-provider sources (see `tests/e2e/test_reporting_simple.py:63-128` for the seeding pattern). Anything docprocessing-only (Tasks 2 and 5) is verified in the browser on INT instead.
- **Pre-commit hook** runs `db-migrate --env INT` + sync check. If it fails on a checksum/CRLF complaint unrelated to your change, use the documented escape hatch: `SQL_SYNC_SKIP=1 git commit ...`.
- **i18n:** every new `{{ _("...") }}` string must go through the pybabel cycle (Task 9) or `tests/unit/test_translations.py` fails. Tasks 2-8 only *add* strings; Task 9 runs the cycle once for all of them.
- **Line references** below were verified on 2026-06-11 against `feature/2.5.63` HEAD `f308078`. If lines have drifted, anchor on the quoted code, not the numbers.

### Decisions locked in (and why)

| # | User ask | Decision |
|---|----------|----------|
| 1 | Two identical metrics | **Already fixed** — migration `0021` set `Enabled=0` on `workitem_count`; live-verified on INT (`dbo.ReportingMetrics`: only `doc_count` enabled). `_load_db_metrics()` filters `Enabled=1`. Task 1 is browser-verification only. Keep disabled-not-deleted (reversible; admin UI shows it as ✗). |
| 2 | Breakdown bloat / missing dims | Client-side curation in `renderBreakdownStep()`, gated on `source.id === 'docprocessing'` — zero backend risk, table-source e2e untouched, Advanced/AI unaffected. All 7 requested fields verified to exist in the live catalog: `docsource`, `doctype`, `forwarding`, `ownernr`, `propertynr`, `registered`, `tenancynr`. Hide: `processname`, `bankpk`, `crdno`, `docbarcode`, `docdate`, plus `workitem_id` (grouping by a unique id is never a sensible wizard breakdown). Keep the 12-item cap. |
| 3 | Explain missing graph | Three no-chart cases get explanations: total-only (note appended to `#rsMsg`), too-many-points date series (note in chart card), Chart.js CDN failure (note in chart card). Category breakdowns >50 rows now chart the first 50 **with a note** instead of hiding (wizard category defs sort by metric desc, so first 50 = top 50). |
| 4 | Change-graph button | Bar/Line/Pie/Doughnut switcher inside the chart card. Choice persists as `def.chartType` (validator ignores unknown keys — verified; survives Simple save/load; silently dropped if re-saved through Advanced, documented caveat). "More graphs" (multiple simultaneous charts) is out of scope — YAGNI. |
| 5 | Scope control too small | Restyle the existing `<details>` into a bordered card-row with icon + live selection badge ("All processes" / "3 / 12"). Keeps the existing msgid (no i18n churn for the summary). |
| 6 | Saved reports adjustable | Filter/process chips + refine bar **already show** for library-opened reports (Task 14, commit `7aaecda`). Only "Adjust in wizard" is gated to in-session wizard runs. Fix: a pure `def → state.wiz` reverse-mapper; button appears for any wizard-shaped definition (incl. pre-existing saved reports and simple AI-built ones). No persistence, no schema change. |
| 7 | Back → adjustment + exit | Result-view **Back** re-enters the wizard with preserved choices whenever the definition is wizard-shaped (else falls back to library). New ✕ buttons on both the result bar and the wizard exit straight to the library. Wizard's own "← Back" keeps exiting to library. |
| 8 | Save-as browser prompt | Replace `window.prompt` in Advanced `doSave()` (and `renameSelectedReport()`, same smell) with a `.reporting-modal` name dialog declared in initial page markup (required for the Motion spring-in animation — the anim observer only registers modals present at load). Reuses existing msgids "Report name" / "New name" / "Save" / "Cancel" — zero new i18n. |

---

### Task 1: Verify the metric dedupe is live (no code expected)

**Files:** none (verification only).

- [ ] **Step 1: Confirm DB state**

```powershell
python scripts/db-migrate.py --env INT --dry-run
```
Expected: `[NexoraDB] up-to-date` (0021 applied).

- [ ] **Step 2: Browser-verify the wizard measure step**

```powershell
nx -u -b --loginas:admin
```
Navigate to `/reporting?tab=simple` → **New report**. Step 1 must list **only "Document count"** — no "Workitem count (distinct)".
Screenshot to `var/screenshots/simple-guide-01-single-metric.png`.

- [ ] **Step 3: If two metrics still appear** (not expected — `_load_db_metrics()` at `nx_lib/views/reporting.py:182-216` reads `Enabled=1` only and the row is live-verified disabled): restart the dev server first (stale process), then re-check. Only if it persists, debug `/api/reporting/metrics` output.

- [ ] **Step 4: No commit** (nothing changed). Report the finding in the task summary.

---

### Task 2: Curate the docprocessing breakdown dimensions

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (constants near line 59; `renderBreakdownStep()` lines 706-720)

- [ ] **Step 1: Add the curation constants** right after the `I18N` map closes (after line 58):

```js
  // Wizard category-dimension curation (docprocessing only). Preferred
  // business dimensions first, noise hidden; table sources are untouched.
  var DOCPROC_DIM_ORDER = ['docsource', 'doctype', 'forwarding', 'ownernr',
                           'propertynr', 'registered', 'tenancynr'];
  var DOCPROC_DIM_HIDE = { processname: 1, bankpk: 1, crdno: 1, docbarcode: 1,
                           docdate: 1, workitem_id: 1 };
```

- [ ] **Step 2: Apply them in `renderBreakdownStep()`.** Replace lines 706-708:

```js
    var catFields = fields.filter(function (f) {
      return f.type === 'string' && f.filterable && f.field !== 'processname';
    });
```

with:

```js
    var catFields = fields.filter(function (f) {
      return f.type === 'string' && f.filterable && f.field !== 'processname';
    });
    if (state.wiz.source.id === 'docprocessing') {
      catFields = catFields.filter(function (f) { return !DOCPROC_DIM_HIDE[f.field]; });
      catFields.sort(function (a, b) {
        var ia = DOCPROC_DIM_ORDER.indexOf(a.field), ib = DOCPROC_DIM_ORDER.indexOf(b.field);
        if (ia === -1) ia = DOCPROC_DIM_ORDER.length;
        if (ib === -1) ib = DOCPROC_DIM_ORDER.length;
        return (ia - ib) || a.label.localeCompare(b.label);
      });
    }
```

- [ ] **Step 3: Delete the processname-first special case.** Remove lines 717-719:

```js
    // processname first (the natural docprocessing category), then the rest.
    var procField = fields.find(function (f) { return f.field === 'processname'; });
    if (procField) catFields.unshift(procField);
```

(The `slice(0, 12)` on line 720 stays.)

- [ ] **Step 4: Guard against regressions in the table-source wizard e2e**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_simple.py -v
```
Expected: PASS (table sources hit the `else`-less generic path — behavior unchanged).

- [ ] **Step 5: Browser-verify on INT** (docprocessing isn't e2e-testable): restart `nx -u -b --loginas:admin`, open wizard, pick Document count. Step 2 must show, in order: *Over time* options, then **Document Source, Document Type, Forwarding, Owner no., Property No., Registered, Tenancy no.**, then remaining fields alphabetically — and none of Processname / Bank PK / Creditor no. / Document Barcode / Document Date / Workitem ID. Screenshot → `var/screenshots/simple-guide-02-curated-dims.png`.

- [ ] **Step 6: Commit**

```powershell
git add templates/js/_reporting_simple_js.html
git commit -m "feat(reporting): curate wizard breakdown dimensions for docprocessing"
```

---

### Task 3: Explain why no chart is shown (and chart top-50 categories)

**Files:**
- Modify: `templates/_reporting_simple.html:109-111` (chart card)
- Modify: `templates/js/_reporting_simple_js.html` (I18N map line 57; `mountChart()` 226-256; `runCurrent()` 537-541; `showResultError()` 174-188)

- [ ] **Step 1: Add the note element to the chart card.** Replace lines 109-111 of `templates/_reporting_simple.html`:

```html
      <div class="nx-card nx-card--pad reporting-simple-chartcard" id="rsChartCard" hidden data-testid="rs-chart-card">
        <p id="rsChartNote" class="reporting-simple-chartnote" hidden data-testid="rs-chart-note"></p>
        <canvas id="rsChartCanvas"></canvas>
      </div>
```

- [ ] **Step 2: Add I18N strings.** In the `I18N` map, after `allProcesses` (line 57 — add a trailing comma to it):

```js
    allProcesses: {{ _("All processes")|tojson }},
    noChartTotalOnly: {{ _("No chart — this report is a single total. Adjust it in the wizard and pick a breakdown to get one.")|tojson }},
    chartFirst50: {{ _("Chart shows the first 50 of {n} rows.")|tojson }},
    noChartTooManyPoints: {{ _("Too many data points to chart — choose a coarser granularity or a shorter time range.")|tojson }},
    noChartLib: {{ _("The chart could not be drawn (chart library failed to load).")|tojson }}
```

- [ ] **Step 3: Rework `mountChart()` branching.** Replace lines 226-231:

```js
  function mountChart(def, columns, rows) {
    destroyChart();
    var dims = (def.columns || []).length;
    if (!dims || !rows.length || rows.length > 50 || !window.Chart) {
      el('rsChartCard').hidden = true; return;
    }
```

with:

```js
  function chartCardNote(msg) {
    el('rsChartCanvas').hidden = true;
    el('rsChartNote').textContent = msg;
    el('rsChartNote').hidden = false;
    el('rsChartCard').hidden = false;
  }

  function mountChart(def, columns, rows) {
    destroyChart();
    el('rsChartNote').hidden = true;
    el('rsChartCanvas').hidden = false;
    var dims = (def.columns || []).length;
    if (!dims || !rows.length) { el('rsChartCard').hidden = true; return; }
    if (!window.Chart) { chartCardNote(I18N.noChartLib); return; }
    var firstCol = def.columns[0];
    var isDate = !!firstCol.grain || /date/.test(firstCol.field);
    if (rows.length > 50) {
      if (isDate) { chartCardNote(I18N.noChartTooManyPoints); return; }
      el('rsChartNote').textContent = I18N.chartFirst50.replace('{n}', String(rows.length));
      el('rsChartNote').hidden = false;
      rows = rows.slice(0, 50);
    }
```

and **delete** the now-duplicate `firstCol`/`isDate` declarations on the original lines 232-233 (they moved up).

- [ ] **Step 4: Explain the total-only case.** In `runCurrent()`, replace lines 537-541:

```js
    if (hasMetrics && !dims && rows.length) {
      el('rsStatLabel').textContent = metricLabelFor(def);
      el('rsStatValue').textContent = fmtNumber(rows[0][0]);
      el('rsStatCard').hidden = false;
    }
```

with:

```js
    if (hasMetrics && !dims && rows.length) {
      el('rsStatLabel').textContent = metricLabelFor(def);
      el('rsStatValue').textContent = fmtNumber(rows[0][0]);
      el('rsStatCard').hidden = false;
      var totMsg = el('rsMsg');
      totMsg.textContent = (!totMsg.hidden && totMsg.textContent)
        ? totMsg.textContent + ' — ' + I18N.noChartTotalOnly : I18N.noChartTotalOnly;
      totMsg.hidden = false;
    }
```

- [ ] **Step 5: Reset the note on error views.** In `showResultError()` after line 185 (`el('rsChartCard').hidden = true;`) add:

```js
    el('rsChartNote').hidden = true;
```

- [ ] **Step 6: Add CSS** at the end of the Simple section of `static/css/reporting.css` (after line 998):

```css
.reporting-simple-chartnote { font-size: 13px; color: #6b7280; margin: 0 0 8px; }
```

- [ ] **Step 7: Write the e2e test** (zero-dim total note; table-source pattern). In `tests/e2e/test_reporting_simple.py`, copy the seeding fixture used by `test_adjust_wizard_button_round_trip` (lines 426-488) and add:

```python
def test_total_only_result_explains_missing_chart(page, seeded_simple_source):
    """A 'None — just the total' wizard run shows the number card plus a
    note explaining why there is no chart."""
    page.goto(f"{BASE_URL}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_role("button").first.click()
    page.get_by_test_id("rs-breakdown-list").get_by_role(
        "button", name=re.compile("just the total", re.I)).click()
    page.get_by_test_id("rs-wizard-run").click()
    expect(page.get_by_test_id("rs-stat-card")).to_be_visible()
    expect(page.get_by_test_id("rs-msg")).to_contain_text("single total")
    expect(page.get_by_test_id("rs-chart-card")).to_be_hidden()
```

(Adapt fixture/selector names to the file's existing helpers — the seeded source + metric setup at lines 63-128 is the canonical pattern.)

- [ ] **Step 8: Run the test, verify it fails** (before template restart it sees stale HTML — restart the server first):

```powershell
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_simple.py::test_total_only_result_explains_missing_chart -v
```
Expected: PASS after implementation (steps 1-6 already done — if it fails, debug). If you prefer strict TDD, write Step 7 before Steps 1-6 and watch it fail on the missing `rs-msg` text.

- [ ] **Step 9: Commit**

```powershell
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html static/css/reporting.css tests/e2e/test_reporting_simple.py
git commit -m "feat(reporting): explain absent charts and plot top-50 categories in Simple results"
```

---

### Task 4: Chart-type switcher on the Simple result chart

**Files:**
- Modify: `templates/_reporting_simple.html` (chart card from Task 3)
- Modify: `templates/js/_reporting_simple_js.html` (`mountChart()`; new `renderChart()`; switcher wiring)
- Modify: `static/css/reporting.css`
- Test: `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Add the switcher markup.** In the chart card (Task 3 version), insert the toolbar before `#rsChartNote`:

```html
      <div class="nx-card nx-card--pad reporting-simple-chartcard" id="rsChartCard" hidden data-testid="rs-chart-card">
        <div class="reporting-simple-charttools" id="rsChartTools" hidden data-testid="rs-chart-tools">
          <button type="button" class="reporting-chartbtn" data-type="bar" title="{{ _('Bar chart') }}" aria-label="{{ _('Bar chart') }}" data-testid="rs-chart-bar"><i class="fas fa-chart-column" aria-hidden="true"></i></button>
          <button type="button" class="reporting-chartbtn" data-type="line" title="{{ _('Line chart') }}" aria-label="{{ _('Line chart') }}" data-testid="rs-chart-line"><i class="fas fa-chart-line" aria-hidden="true"></i></button>
          <button type="button" class="reporting-chartbtn" data-type="pie" title="{{ _('Pie chart') }}" aria-label="{{ _('Pie chart') }}" data-testid="rs-chart-pie"><i class="fas fa-chart-pie" aria-hidden="true"></i></button>
          <button type="button" class="reporting-chartbtn" data-type="doughnut" title="{{ _('Doughnut chart') }}" aria-label="{{ _('Doughnut chart') }}" data-testid="rs-chart-doughnut"><i class="fas fa-circle-notch" aria-hidden="true"></i></button>
        </div>
        <p id="rsChartNote" class="reporting-simple-chartnote" hidden data-testid="rs-chart-note"></p>
        <canvas id="rsChartCanvas"></canvas>
      </div>
```

- [ ] **Step 2: Split `mountChart()` into data-prep + `renderChart(type)`.** Add `chartData: null` to the `state` object (line 60-69), then replace the body of `mountChart()` from `var metricIdx = ...` (line 234) through the `new Chart(...)` block (line 250-255) with:

```js
    var metricIdx = columns.length - (def.metrics || []).length;
    var labels = rows.map(function (r) {
      var v = String(r[0] == null ? '' : r[0]);
      return isDate ? v.slice(0, 10) : v;
    });
    var datasets = (def.metrics || []).map(function (m, i) {
      var col = columns[metricIdx + i];
      return {
        label: col ? (col.header || m.metric) : m.metric,
        data: rows.map(function (r) { return Number(r[metricIdx + i]); }),
        borderColor: '#4f46e5', backgroundColor: 'rgba(79,70,229,.45)', tension: .25
      };
    });
    state.chartData = { labels: labels, datasets: datasets };
    el('rsChartCard').hidden = false;
    el('rsChartTools').hidden = false;
    renderChart(def.chartType || (isDate ? 'line' : 'bar'));
  }

  // Mirrors ReportingViz's palette so Simple pies match Advanced ones.
  var SIMPLE_PALETTE = [
    '#4338ca', '#2563eb', '#0891b2', '#059669', '#65a30d', '#ca8a04',
    '#dc2626', '#db2777', '#7c3aed', '#0d9488', '#ea580c', '#4f46e5'
  ];

  function renderChart(type) {
    var d = state.chartData;
    if (!d) return;
    destroyChart();
    var circular = type === 'pie' || type === 'doughnut';
    var datasets = d.datasets.map(function (ds) {
      var out = Object.assign({}, ds);
      if (circular) {
        out.backgroundColor = d.labels.map(function (_, i) {
          return SIMPLE_PALETTE[i % SIMPLE_PALETTE.length];
        });
        out.borderColor = '#fff';
      }
      return out;
    });
    state.chart = new Chart(el('rsChartCanvas'), {
      type: type,
      data: { labels: d.labels, datasets: datasets },
      options: { responsive: true, maintainAspectRatio: false,
                 plugins: { legend: { display: circular || d.datasets.length > 1 } } }
    });
    Array.prototype.forEach.call(
      el('rsChartTools').querySelectorAll('button'), function (b) {
        b.classList.toggle('is-selected', b.dataset.type === type);
        b.setAttribute('aria-pressed', b.dataset.type === type ? 'true' : 'false');
      });
  }
```

Also: in the Task 3 version of `mountChart()`, the early-return branches must hide the tools — add `el('rsChartTools').hidden = true;` next to the `el('rsChartNote').hidden = true;` reset at the top, and `chartCardNote()` already hides the canvas; add `el('rsChartTools').hidden = true;` inside `chartCardNote()` too.

- [ ] **Step 3: Wire the switcher + persist the choice.** Near the other listeners (after the `rsTableToggle` listener, line 560-564):

```js
  el('rsChartTools').addEventListener('click', function (e) {
    var btn = e.target.closest('button[data-type]');
    if (!btn || !state.chartData) return;
    if (state.current && state.current.def) state.current.def.chartType = btn.dataset.type;
    renderChart(btn.dataset.type);
  });
```

The choice lands in `state.current.def.chartType`, so **Save** (`rsSave`, posts `state.current.def`) persists it and a later library open renders the saved type via `def.chartType ||` in `mountChart`. (Caveat, by design: re-saving the report through Advanced rebuilds the definition and drops the key.)

- [ ] **Step 4: Reset stale data.** In `destroyChart()` do NOT clear `state.chartData` (renderChart needs it); instead clear it at the top of `mountChart()` (`state.chartData = null;` before the early returns) and in `showResultError()` add `el('rsChartTools').hidden = true;`.

- [ ] **Step 5: Add CSS** (after the Task 3 rule):

```css
.reporting-simple-charttools { position: absolute; top: 10px; right: 10px; display: flex; gap: 4px; z-index: 1; }
.reporting-chartbtn { border: 1px solid #e5e7eb; background: #fff; border-radius: 6px; padding: 4px 8px; font-size: 12px; color: #6b7280; cursor: pointer; }
.reporting-chartbtn.is-selected { border-color: #4f46e5; color: #4f46e5; background: #eef2ff; }
```

- [ ] **Step 6: Write the e2e test** (table-source category breakdown renders a chart; switching to pie keeps it alive and marks the button selected):

```python
def test_chart_type_switcher(page, seeded_simple_source):
    """The result chart card offers bar/line/pie/doughnut switching."""
    page.goto(f"{BASE_URL}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_role("button").first.click()
    # pick the first category breakdown (not 'just the total')
    page.get_by_test_id("rs-breakdown-list").get_by_role("button").first.click()
    page.get_by_test_id("rs-wizard-run").click()
    expect(page.get_by_test_id("rs-chart-card")).to_be_visible()
    expect(page.get_by_test_id("rs-chart-tools")).to_be_visible()
    page.get_by_test_id("rs-chart-pie").click()
    expect(page.get_by_test_id("rs-chart-pie")).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#rsChartCanvas")).to_be_visible()
```

- [ ] **Step 7: Run it**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_simple.py::test_chart_type_switcher -v
```
Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html static/css/reporting.css tests/e2e/test_reporting_simple.py
git commit -m "feat(reporting): chart-type switcher (bar/line/pie/doughnut) on Simple results"
```

---

### Task 5: Make "Limit to specific processes" prominent

**Files:**
- Modify: `templates/_reporting_simple.html:51-54`
- Modify: `templates/js/_reporting_simple_js.html` (`renderBreakdownStep()` scope block, lines 736-757)
- Modify: `static/css/reporting.css:987-988`

- [ ] **Step 1: Upgrade the markup.** Replace lines 51-54 of `templates/_reporting_simple.html`:

```html
      <details id="rsScopeWrap" class="reporting-simple-scope" hidden>
        <summary data-testid="rs-scope-summary">
          <i class="fas fa-filter" aria-hidden="true"></i>
          <span>{{ _("Limit to specific processes") }}</span>
          <span id="rsScopeBadge" class="reporting-simple-scope-badge" data-testid="rs-scope-badge"></span>
        </summary>
        <div id="rsScopeList" data-testid="rs-scope-list"></div>
      </details>
```

(The summary msgid is unchanged — no i18n churn.)

- [ ] **Step 2: Maintain the badge.** In `renderBreakdownStep()`, inside the `if (procs.length) { ... }` block (lines 739-757), add a helper and call it from the change handler and after initial population:

```js
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
        });
        lbl.appendChild(cb);
        lbl.appendChild(document.createTextNode(' ' + p));
        box.appendChild(lbl);
      });
      if (!prior.length) state.wiz.scopeProcs = procs.slice();
      updateScopeBadge();
    }
```

(`I18N.allProcesses` already exists — line 57.)

- [ ] **Step 3: Restyle.** Replace `static/css/reporting.css:987-988`:

```css
.reporting-simple-scope { margin-top: 10px; font-size: 13px; }
.reporting-simple-scope label { display: block; padding: 2px 0; }
```

with:

```css
.reporting-simple-scope { margin-top: 14px; font-size: 14px; border: 1px solid #d1d5db; border-radius: 8px; background: #fff; max-width: 520px; }
.reporting-simple-scope summary { cursor: pointer; font-weight: 600; padding: 10px 12px; display: flex; align-items: center; gap: 8px; list-style-position: inside; }
.reporting-simple-scope-badge { margin-left: auto; font-weight: 500; font-size: 12px; background: #eef2ff; color: #4338ca; border-radius: 999px; padding: 2px 10px; }
.reporting-simple-scope > div { padding: 0 12px 10px; max-height: 220px; overflow: auto; }
.reporting-simple-scope label { display: block; padding: 3px 0; }
```

- [ ] **Step 4: Verify.** Processes exist only on docprocessing, which e2e can't run — verify in the browser on INT: restart server, wizard → Document count → step 2 shows the bordered scope row with the "All processes" badge; tick off one process → badge flips to "n-1 / n". Screenshots → `var/screenshots/simple-guide-05-scope-closed.png` and `...-scope-open.png`. Also re-run the existing e2e to prove no table-source regression:

```powershell
python -m pytest tests/e2e/test_reporting_simple.py -v
```

- [ ] **Step 5: Commit**

```powershell
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html static/css/reporting.css
git commit -m "feat(reporting): make wizard process-scope control prominent with selection badge"
```

---

### Task 6: "Adjust in wizard" for saved (and AI) reports — definition reverse-mapper

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (`openReport()` 156-166; `runCurrent()` gate 494-495; new `wizardStateFromDefinition()` + `adjustInWizard()` near `reopenWizard()` 873-881; listener line 595)
- Test: `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Write the reverse-mapper** — the exact inverse of `wizardDefinition()` (lines 840-871). Insert before `reopenWizard()`:

```js
  // Wizard presets that renderTimeStep offers; other tokens (e.g. last_n_days,
  // this_week) can't be represented in the wizard UI, so such defs don't map.
  var WIZ_TOKENS = ['this_month', 'last_month', 'last_quarter',
                    'last_3_months', 'this_year', 'last_year'];

  // Inverse of wizardDefinition(): returns a state.wiz candidate (+grain) for
  // wizard-shaped definitions, or null when the def can't be represented in
  // the wizard (multiple columns/filters/metrics, exotic ops, client scope).
  function wizardStateFromDefinition(def) {
    if (!def || !Array.isArray(def.metrics) || def.metrics.length !== 1) return null;
    var src = (state.sources || []).find(function (s) { return s.id === def.source; });
    var mlist = (state.metricsBySource || {})[def.source] || [];
    var m = mlist.find(function (x) { return x.code === def.metrics[0].metric; });
    if (!src || !m) return null;
    var cols = def.columns || [];
    if (cols.length > 1) return null;
    var breakdown = { kind: 'none' }, grain = null;
    if (cols.length === 1) {
      var f = (src.fields || []).find(function (x) { return x.field === cols[0].field; });
      if (!f) return null;
      if (cols[0].grain) {
        if (!f.grainable) return null;
        breakdown = { kind: 'date', field: f };
        grain = cols[0].grain;
      } else {
        breakdown = { kind: 'category', field: f };
      }
    }
    var filters = def.filters || [];
    if (filters.length > 1) return null;
    var range = null, dateField = null;
    if (filters.length === 1) {
      var ft = filters[0];
      if (ft.op !== 'between') return null;
      var df = (src.fields || []).find(function (x) {
        return x.field === ft.field && x.grainable;
      });
      if (!df) return null;
      dateField = ft.field;
      if (ft.value && ft.value.token) {
        if (WIZ_TOKENS.indexOf(ft.value.token) === -1) return null;
        range = { token: ft.value.token };
      } else if (Array.isArray(ft.value) && ft.value.length === 2) {
        range = ft.value.slice();
      } else { return null; }
    }
    var scope = def.scope || {};
    if ((scope.clients || []).length) return null;
    return { wiz: { measure: m, source: src, breakdown: breakdown,
                    scopeProcs: (scope.processes || []).slice(),
                    range: range, dateField: dateField, _fp: null },
             grain: grain };
  }

  function adjustInWizard() {
    var cur = state.current;
    if (!cur) return;
    if (cur.builtBy === 'wizard' && state.wiz && state.wiz.measure) {
      reopenWizard(); return;
    }
    var mapped = wizardStateFromDefinition(cur.def);
    if (!mapped) return;
    state.wiz = mapped.wiz;
    if (mapped.grain) el('rsGrain').value = mapped.grain;
    reopenWizard();
  }
```

Note: a custom `[from, to]` range restores as "Custom" highlighted (`Array.isArray(state.wiz.range)` — renderTimeStep line 829), but the flatpickr display starts empty (`_fp: null`); the range value itself is preserved in state and re-emitted on run. Acceptable; do NOT try to pre-fill flatpickr in this task.

- [ ] **Step 2: Preload catalogs on library open** so the gate can map synchronously. In `openReport()` (lines 156-166), before the `state.current =` assignment add:

```js
    await loadSourcesCatalog();
    if (!state.metricsBySource) await loadMetricsCatalog();
```

- [ ] **Step 3: Widen the button gate.** Replace `runCurrent()` lines 494-495:

```js
    var adjustBtn = el('rsAdjustWizard');
    if (adjustBtn) adjustBtn.hidden = cur.builtBy !== 'wizard';
```

with:

```js
    var adjustBtn = el('rsAdjustWizard');
    if (adjustBtn) {
      adjustBtn.hidden = cur.builtBy !== 'wizard' && !wizardStateFromDefinition(cur.def);
    }
```

- [ ] **Step 4: Rewire the button.** Replace line 595:

```js
  el('rsAdjustWizard').addEventListener('click', reopenWizard);
```

with:

```js
  el('rsAdjustWizard').addEventListener('click', adjustInWizard);
```

- [ ] **Step 5: Write the e2e test** — save a wizard-built report, reload the page (fresh state), open it from the library, adjust in wizard:

```python
def test_saved_report_adjust_in_wizard(page, seeded_simple_source):
    """A wizard-shaped SAVED report re-enters the wizard with choices restored,
    even in a fresh session (no in-memory wizard state)."""
    # build + save via the wizard
    page.goto(f"{BASE_URL}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_role("button").first.click()
    page.get_by_test_id("rs-breakdown-list").get_by_role("button").first.click()
    page.get_by_test_id("rs-wizard-run").click()
    page.get_by_test_id("rs-save").click()
    page.get_by_test_id("rs-save-name").fill("adjust-saved-e2e")
    page.get_by_test_id("rs-save").click()
    # fresh page load wipes state.wiz
    page.goto(f"{BASE_URL}/reporting?tab=simple")
    page.get_by_test_id("rs-group-mine").get_by_text("adjust-saved-e2e").click()
    adjust = page.get_by_test_id("rs-adjust-wizard")
    expect(adjust).to_be_visible()
    adjust.click()
    expect(page.get_by_test_id("rs-wizard")).to_be_visible()
    # the previously chosen measure + breakdown render pre-selected
    expect(page.get_by_test_id("rs-measure-list").locator(".is-selected")).to_have_count(1)
    expect(page.get_by_test_id("rs-breakdown-list").locator(".is-selected")).to_have_count(1)
```

(Reuse the file's existing save/cleanup helpers; delete the report in a finally/fixture teardown like the neighbouring tests do.)

- [ ] **Step 6: Run it + the whole Simple suite**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_simple.py -v
```
Expected: all PASS (incl. the existing `test_adjust_wizard_button_round_trip`).

- [ ] **Step 7: Commit**

```powershell
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -m "feat(reporting): Adjust-in-wizard for saved and AI reports via definition reverse-mapping"
```

---

### Task 7: Result Back returns to the wizard; explicit exit buttons

**Files:**
- Modify: `templates/_reporting_simple.html` (result bar line 71; wizard header line 35)
- Modify: `templates/js/_reporting_simple_js.html` (rsBack handler ~line 975; new listeners near 883-884)
- Test: `tests/e2e/test_reporting_simple.py`

Depends on Task 6 (`adjustInWizard`, `wizardStateFromDefinition`).

- [ ] **Step 1: Add the exit buttons.** Wizard header — replace line 35:

```html
    <button id="rsWizardBack" class="reporting-link" data-testid="rs-wizard-back">&larr; {{ _("Back") }}</button>
```

with:

```html
    <div class="reporting-simple-wizbar">
      <button id="rsWizardBack" class="reporting-link" data-testid="rs-wizard-back">&larr; {{ _("Back") }}</button>
      <button id="rsWizardClose" class="reporting-link reporting-simple-close" data-testid="rs-wizard-close"
              title="{{ _('Back to library') }}" aria-label="{{ _('Back to library') }}">&times;</button>
    </div>
```

Result bar — after the `rsExport` button (inside `.reporting-simple-ractions`, line 80-82), add:

```html
        <button id="rsExit" class="reporting-link reporting-simple-close" data-testid="rs-exit"
                title="{{ _('Back to library') }}" aria-label="{{ _('Back to library') }}">&times;</button>
```

- [ ] **Step 2: CSS** (append to the Simple section of `static/css/reporting.css`):

```css
.reporting-simple-wizbar { display: flex; justify-content: space-between; align-items: center; }
.reporting-simple-close { font-size: 20px; line-height: 1; padding: 2px 8px; }
```

- [ ] **Step 3: Retarget Back; wire the exits.** Replace the `rsBack` handler (the line reading `el('rsBack').addEventListener('click', function () { setView('library'); loadLibrary(); });`, ~line 975):

```js
  function exitToLibrary() { setView('library'); loadLibrary(); }

  // Back on a result returns to the wizard ADJUSTMENT whenever the definition
  // is wizard-shaped; the X is the explicit way out to the library.
  el('rsBack').addEventListener('click', function () {
    var cur = state.current;
    var adjustable = cur && (
      (cur.builtBy === 'wizard' && state.wiz && state.wiz.measure)
      || wizardStateFromDefinition(cur.def));
    if (adjustable) { adjustInWizard(); return; }
    exitToLibrary();
  });
  el('rsExit').addEventListener('click', exitToLibrary);
  el('rsWizardClose').addEventListener('click', exitToLibrary);
```

(Leave the `rsWizardBack` handler on line 884 unchanged — on the wizard screen, ← Back still exits to the library.)

- [ ] **Step 4: Write the e2e test**

```python
def test_result_back_returns_to_wizard(page, seeded_simple_source):
    """Back on a wizard-built result re-enters the wizard; X exits to library."""
    page.goto(f"{BASE_URL}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_role("button").first.click()
    page.get_by_test_id("rs-breakdown-list").get_by_role("button").first.click()
    page.get_by_test_id("rs-wizard-run").click()
    expect(page.get_by_test_id("rs-result")).to_be_visible()
    page.get_by_test_id("rs-back").click()
    expect(page.get_by_test_id("rs-wizard")).to_be_visible()   # wizard, not library
    page.get_by_test_id("rs-wizard-close").click()
    expect(page.get_by_test_id("rs-library")).to_be_visible()
```

- [ ] **Step 5: Run it + check for broken assumptions in older tests** (any test that clicked `rs-back` expecting the library now lands in the wizard — fix those tests to use `rs-exit`):

```powershell
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_simple.py -v
```

- [ ] **Step 6: Commit**

```powershell
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html static/css/reporting.css tests/e2e/test_reporting_simple.py
git commit -m "feat(reporting): result Back re-enters wizard; explicit exit-to-library buttons"
```

---

### Task 8: Advanced "Save as" / "Rename" — name modal instead of window.prompt

**Files:**
- Modify: `templates/reporting.html` (modal markup after `#rpSqlAck`, lines 225-234)
- Modify: `templates/js/_reporting_js.html` (`doSave()` 491-526; `renameSelectedReport()` ~1014-1030)
- Test: `tests/e2e/test_reporting_save.py`

- [ ] **Step 1: Add the modal to the initial page markup** (REQUIRED in the template, not injected — the Motion anim observer registers `.reporting-modal` elements once at load). After the `#rpSqlAck` modal block in `templates/reporting.html`:

```html
  <div id="rpNameModal" class="reporting-modal" hidden data-testid="reporting-name-modal">
    <div class="reporting-modal-box">
      <h3 id="rpNameModalTitle"></h3>
      <input id="rpNameModalInput" class="reporting-input" data-testid="reporting-name-input">
      <div class="reporting-modal-actions">
        <button id="rpNameModalCancel" class="reporting-btn" data-testid="reporting-name-cancel">{{ _("Cancel") }}</button>
        <button id="rpNameModalOk" class="reporting-btn reporting-btn-primary" data-testid="reporting-name-ok">{{ _("Save") }}</button>
      </div>
    </div>
  </div>
```

(All four msgids already exist — zero new i18n in this task.)

- [ ] **Step 2: Add the `promptName()` helper** in `templates/js/_reporting_js.html`, next to the `ackThen` modal helper (~line 449). Match the file's existing element-access idiom (it has its own helpers; if none fits, `document.getElementById` directly):

```js
  // Modal replacement for window.prompt: resolves the trimmed name, or null
  // on cancel/empty.
  function promptName(title, initial) {
    return new Promise(function (resolve) {
      var modal = document.getElementById('rpNameModal');
      var input = document.getElementById('rpNameModalInput');
      var ok = document.getElementById('rpNameModalOk');
      var cancel = document.getElementById('rpNameModalCancel');
      document.getElementById('rpNameModalTitle').textContent = title;
      input.value = initial || '';
      modal.hidden = false;
      input.focus();
      input.select();
      function done(v) {
        modal.hidden = true;
        ok.onclick = cancel.onclick = input.onkeydown = null;
        resolve(v);
      }
      ok.onclick = function () { done(input.value.trim() || null); };
      cancel.onclick = function () { done(null); };
      input.onkeydown = function (e) {
        if (e.key === 'Enter') ok.click();
        if (e.key === 'Escape') cancel.click();
      };
    });
  }
```

- [ ] **Step 3: Use it in `doSave()`.** Replace the create/copy branch (lines 495-511):

```js
    if (asNew || !canOverwrite) {
      var name = window.prompt('{{ _("Report name") }}', reportTitle());
      if (!name) return;
      api('/api/reporting/reports', {
        method: 'POST',
        body: JSON.stringify({ name: name, definition: def }),
      }).then(function (res) { return res.json(); })
```

with:

```js
    if (asNew || !canOverwrite) {
      promptName('{{ _("Report name") }}', reportTitle()).then(function (name) {
        if (!name) return;
        api('/api/reporting/reports', {
          method: 'POST',
          body: JSON.stringify({ name: name, definition: def }),
        }).then(function (res) { return res.json(); })
```

…and keep the rest of the chain identical, closing the new `promptName(...).then(function (name) { ... })` wrapper before the branch's `return;`. (Indentation shifts by one level inside the wrapper; the `.then(...)`/`.catch(...)` bodies are unchanged.)

- [ ] **Step 4: Use it in `renameSelectedReport()`.** Replace the `window.prompt` line (~1019):

```js
    var name = window.prompt('{{ _("New name") }}', current);
    if (!name || name === current) return;
```

with:

```js
    promptName('{{ _("New name") }}', current).then(function (name) {
      if (!name || name === current) return;
```

and close the wrapper around the rest of the function body.

- [ ] **Step 5: Write the e2e test** — the create path was deliberately untestable with `window.prompt` (see `tests/e2e/test_reporting_load.py:28`); the modal finally makes it drivable. Append to `tests/e2e/test_reporting_save.py`:

```python
def test_save_as_uses_name_modal(page, logged_in):
    """Save as opens the custom name modal (no browser prompt) and creates
    a new report under that name."""
    page.goto(f"{BASE_URL}/reporting?tab=advanced")
    # minimal definition: add first field as a column (existing helper pattern)
    _add_first_column(page)
    page.get_by_test_id("reporting-save-as").click()
    modal = page.get_by_test_id("reporting-name-modal")
    expect(modal).to_be_visible()
    page.get_by_test_id("reporting-name-input").fill("modal-save-e2e")
    page.get_by_test_id("reporting-name-ok").click()
    expect(modal).to_be_hidden()
    # the new report appears in the Saved reports dropdown
    expect(page.locator("#rpSavedReports")).to_contain_text("modal-save-e2e")
```

(Adapt `_add_first_column`, the Save-as button test id, and the dropdown locator to the file's existing helpers/ids — `test_reporting_save.py:1-71` shows the established setup; add cleanup of the created report like its neighbours.)

- [ ] **Step 6: Run the save e2e file**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_save.py -v
```
Expected: all PASS (the existing PUT-path test still passes — its `page.on("dialog")` only ever auto-accepted the alert, which remains).

- [ ] **Step 7: Commit**

```powershell
git add templates/reporting.html templates/js/_reporting_js.html tests/e2e/test_reporting_save.py
git commit -m "feat(reporting): replace window.prompt with name modal for Save as and Rename"
```

---

### Task 9: i18n — translate the new strings (de/fr/it)

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`)

New msgids introduced by Tasks 3, 4, 7 (Task 8 reuses existing ones; Tasks 2, 5, 6 add none):

| msgid | de | fr | it |
|---|---|---|---|
| `No chart — this report is a single total. Adjust it in the wizard and pick a breakdown to get one.` | `Kein Diagramm — dieser Bericht ist eine einzelne Summe. Passen Sie ihn im Assistenten an und wählen Sie eine Aufschlüsselung.` | `Pas de graphique — ce rapport est un total unique. Ajustez-le dans l'assistant et choisissez une ventilation.` | `Nessun grafico — questo report è un totale unico. Modificalo nella procedura guidata e scegli una suddivisione.` |
| `Chart shows the first 50 of {n} rows.` | `Das Diagramm zeigt die ersten 50 von {n} Zeilen.` | `Le graphique montre les 50 premières lignes sur {n}.` | `Il grafico mostra le prime 50 righe su {n}.` |
| `Too many data points to chart — choose a coarser granularity or a shorter time range.` | `Zu viele Datenpunkte für ein Diagramm — wählen Sie eine gröbere Granularität oder einen kürzeren Zeitraum.` | `Trop de points de données pour un graphique — choisissez une granularité plus grossière ou une période plus courte.` | `Troppi punti dati per un grafico — scegli una granularità più ampia o un intervallo più breve.` |
| `The chart could not be drawn (chart library failed to load).` | `Das Diagramm konnte nicht gezeichnet werden (Diagrammbibliothek nicht geladen).` | `Le graphique n'a pas pu être tracé (échec du chargement de la bibliothèque).` | `Impossibile disegnare il grafico (libreria non caricata).` |
| `Bar chart` | `Balkendiagramm` | `Graphique à barres` | `Grafico a barre` |
| `Line chart` | `Liniendiagramm` | `Graphique linéaire` | `Grafico a linee` |
| `Pie chart` | `Kreisdiagramm` | `Graphique circulaire` | `Grafico a torta` |
| `Doughnut chart` | `Ringdiagramm` | `Graphique en anneau` | `Grafico ad anello` |
| `Back to library` | `Zurück zur Bibliothek` | `Retour à la bibliothèque` | `Torna alla libreria` |

- [ ] **Step 1: Extract + update**

```powershell
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
```

- [ ] **Step 2: Fill in the translations** above in `translations/de/LC_MESSAGES/messages.po`, `.../fr/...`, `.../it/...` (find each msgid, set msgstr, remove any `#, fuzzy` marker on those entries).

- [ ] **Step 3: Compile + test**

```powershell
pybabel compile -d translations
python -m pytest tests/unit/test_translations.py -v
```
Expected: PASS (pot in sync, no missing/fuzzy entries).

- [ ] **Step 4: Commit**

```powershell
git add messages.pot translations
git commit -m "chore(i18n): translate new Simple-wizard chart/navigation strings (de/fr/it)"
```

---

### Task 10: Docs + changelog

**Files:**
- Modify: `docs/howto/reporting.md` (Simple-tab section lines 8-53; Save & load section ~144-152)
- Modify: `CHANGELOG.md` (`[Unreleased]`, line 7)

- [ ] **Step 1: Update `docs/howto/reporting.md`** Simple-tab bullets (lines 22-44):
  - In the wizard bullet: after the *measure* sentence, add: `The category list is curated for the Document Processing source — preferred business dimensions (Document Source, Document Type, Forwarding, Owner no., Property No., Registered, Tenancy no.) come first and technical noise (process name, Bank PK, creditor no., barcode, document date) is hidden; other sources list their catalog fields unfiltered. The "Limit to specific processes" control is a prominent bordered row with a live selection badge.`
  - In the result-view bullet: replace `a **chart card** (line for date breakdowns, bar for categories; ≤50 categories)` with `a **chart card** (line for date breakdowns, bar for categories by default, with a bar/line/pie/doughnut switcher; the chosen type is saved with the report). Category breakdowns beyond 50 rows chart the top 50 with a note; when no chart is possible the result explains why (single total, too many date points, chart library unavailable).`
  - Replace the "Adjust in wizard" sentence (lines 39-44 tail): `Any result whose definition is wizard-shaped — including saved library reports and simple AI-built ones — shows an **"Adjust in wizard"** button that re-opens the walkthrough with the previous measure, breakdown, time and process choices pre-selected. **Back** on such a result returns to the wizard adjustment; the **✕** button (on both the result bar and the wizard) exits to the library.`
- [ ] **Step 2: Update the Save & load / Save-vs-Save-as paragraphs** (~lines 144-152 and 180-184): change `prompts for a name` wording to `opens a name dialog` (the browser prompt is gone).
- [ ] **Step 3: CHANGELOG.** Under `[Unreleased]`:

```markdown
### Added
- Reporting Simple wizard: chart-type switcher (bar/line/pie/doughnut) on results; the chosen type is saved with the report.
- Reporting Simple wizard: "Adjust in wizard" now also works for saved library reports and simple AI-built results (definition reverse-mapping).
- Reporting Simple results: explanation notes whenever no chart can be drawn (single total, too many date points, chart library unavailable); category breakdowns >50 rows chart the top 50 with a note.
- Reporting Simple: explicit exit (✕) buttons on the wizard and result views.

### Changed
- Reporting Simple wizard: curated "Break down by" list for Document Processing — Document Source, Document Type, Forwarding, Owner no., Property No., Registered and Tenancy no. first; process name, Bank PK, creditor no., barcode, document date and workitem id hidden.
- Reporting Simple wizard: "Limit to specific processes" is a prominent bordered control with a live selection badge.
- Reporting Simple: Back on a wizard-shaped result returns to the wizard adjustment instead of the library.
- Reporting Advanced: "Save as" and "Rename" use an in-page name dialog instead of the browser prompt.
```

- [ ] **Step 4: Commit**

```powershell
git add docs/howto/reporting.md CHANGELOG.md
git commit -m "docs(reporting): document Simple-wizard curation, chart switcher, navigation and save dialog"
```

---

### Task 11: Full verification + browser walkthrough

- [ ] **Step 1: Full test suite**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/ -v
```
Expected: all green (pre-push runs this anyway, incl. e2e).

- [ ] **Step 2: Browser walkthrough on INT with screenshots** (restart first — template cache):

```powershell
nx -u -b --loginas:admin
```

Capture to `var/screenshots/` (and send them to the user if this is a remote session):
1. Wizard step 1 — single "Document count" metric (`simple-guide-01-single-metric.png`)
2. Wizard step 2 — curated dims, Document Source first (`simple-guide-02-curated-dims.png`)
3. Scope control closed + badge, and open (`simple-guide-05-scope-*.png`)
4. Result with chart switcher; same result as pie (`simple-guide-04-chart-*.png`)
5. Total-only result with explanation note (`simple-guide-03-total-note.png`)
6. Saved library report showing "Adjust in wizard"; wizard re-entered with selections (`simple-guide-06-adjust-saved-*.png`)
7. Advanced Save-as name modal (`simple-guide-08-saveas-modal.png`)

- [ ] **Step 3: Confirm clean working tree, summarize commits**

```powershell
git status
git log --oneline -12
```

Do not push and do not open a PR if this is a remote session (owner reviews locally first).

---

## Self-review (done at plan time)

- **Spec coverage:** all 9 user asks map to tasks — duplicate metrics → T1 (already shipped; verify), breakdown bloat/additions → T2, no-graph explanation → T3, change-graph button → T4 ("adding more graphs" deliberately out of scope), scope prominence → T5, saved-reports adjustable → T6 (chips already shipped in Task 14), wizard Back/exit → T7, Save-as textbox → T8; i18n/docs/verification → T9-T11.
- **Type consistency:** `wizardStateFromDefinition` returns `{wiz, grain}`; both `adjustInWizard` (T6) and the `rsBack` handler (T7) treat its truthiness only — consistent. `state.chartData = {labels, datasets}` written by `mountChart` (T4 Step 2) and read by `renderChart` — consistent. `chartCardNote` defined in T3, extended (hide tools) in T4.
- **Known caveats accepted:** `def.chartType` dropped on Advanced re-save (documented); custom date range re-entry shows an empty flatpickr display while preserving the range in state; tokens outside the wizard's preset set make a def non-mappable (button hidden — chips still cover it).
