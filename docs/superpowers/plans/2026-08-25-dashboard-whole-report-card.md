# Reporting Dashboard: "Whole report" card — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Single-session planning run (recon → draft → self-red-team); **every file path, symbol, and quoted snippet below was Grep/Read-verified against the `v3.2.3.1` tip `48a08364` on 2026-08-25** (the plan worktree was cut one commit earlier at `33b42f4c` — see Owner action 1) — trust the anchors, but re-Grep before editing (this plan quotes code, never line numbers). Plan file: `docs/superpowers/plans/2026-08-25-dashboard-whole-report-card.md`. Written for a **Sonnet executor**: every edit is spelled out; where a large function body is *moved*, the boundaries and every in-body replacement are enumerated.

**Goal:** In the editable dashboard on the Reporting page (Simple tab → *New dashboard* / a saved dashboard → *Edit*), the "Report" tile becomes a **"Whole report"** tile that imports a saved report *as it looks on the Simple tab* — stat card with per-metric grand totals, the KPI band (Total / Buckets / Avg / Peak with prior-period chips), the chart with its saved chart type, colours, right axis and forecast, and the full table behind a *Show table* toggle — instead of today's lossy "one number + one line" rendering.

**Architecture:** Zero backend changes. The Simple pane (`templates/js/_reporting_simple_js.html`) already renders exactly this result view, but its renderers write straight into fixed `#rs*` elements. Phase 1 splits four of them into **pure, DOM-free builders** (`kpiBandHtml`, `buildChartData`, `chartConfigFor`, `tableHtml`, plus the tiny `statCardHtml`/`ensureCatalogs`) and exposes them on the existing `window.ReportingSimple` object; the Simple pane keeps calling them through thin DOM wrappers, so its behaviour is unchanged (the 86-test Simple e2e suite is the safety net). Phase 2 rewrites the dashboard partial's `renderReportCard` to call those builders inside the card — one `/api/reporting/run` for the breakdown (with `compare: true`, like Simple) plus one zero-column clone run for the grand totals (again like Simple). Global filters still merge in through the existing `effectiveFilters`/`cardRunDef` path.

**Tech Stack:** Jinja JS partials (vanilla IIFEs), Chart.js 4 (CDN), Playwright e2e (network-stub pattern), Flask-Babel de/fr/it. No Python changes, no migration, no new permission.

**Spec:** none authored for this feature. Lineage: `docs/superpowers/plans/2026-07-20-reporting-redesign-dashboard-builder.md` (the dashboard builder, D2/D14 card model) and `docs/superpowers/plans/2026-08-06-reporting-ai-owner-feedback.md` (D12 — the first, lossy `'report'` card type this plan replaces). **BEFORE screenshots** (STAGING, 2026-08-25): `var/screenshots/_forclaudedesign/04c-current-report-card-BEFORE.png` (today's Report card: one series, wrong total) vs `03-result-view.png` (the same report on the Simple tab — the target).

---

## Context an engineer needs (read first)

- **Branch/worktree:** this plan was authored in worktree `.claude/worktrees/plan-dashboard-whole-report-card` (branch `plan/dashboard-whole-report-card`, cut from `v3.2.3.1` @ `33b42f4c`). Execute there. **Commit per task. Do NOT `git push`, do NOT open a PR** — the owner reviews, merges the worktree branch back into `v3.2.3.1`, and pushes.
- **SEQUENCING — one commit behind, fast-forward first.** While this plan was being written, the owner's session committed `48a08364 fix(reporting): stop at today, treat backlog as a level, ground the AI` on `v3.2.3.1` (null-not-zero buckets, backlog as a level, migration `0070_backlog_metric_total_mode_latest.sql`, new Simple helpers `metricTotalModes` / `noteDataQuality` / `appendChartNote` / `currentBucketStart`, `xCap`). It edits **the same functions Phase 1 extracts** (`computeKpiBand`, `mountChart`, `renderChart`, `zeroFillDateBuckets`). **Every anchor below is verified against `48a08364`**, so before Task 1 the worktree must sit on it: `git merge --ff-only v3.2.3.1` inside the worktree (a modifying git op — the owner runs it or says "go ahead" for this turn; Owner action 1). Then re-Grep the Task 1–4 anchors once; the extraction steps are written as *boundary moves + enumerated replacements* and already account for those helpers.
- **Parallel sessions are normal** on this repo. Never touch the main checkout (`C:\dev\nexora`) or the peer worktree `C:\dev\nexora-c0`; never stash/revert foreign changes.
- **Python for tests:** `C:\dev\nexora\.venv\Scripts\python -m pytest …` run **from the worktree root** (the e2e `nexora_server` fixture launches the worktree's `nx_main.py`). No new runtime deps anywhere in this plan.
- **Anchor on quoted snippets + function names, NEVER line numbers.** Re-`Grep` a snippet if it has moved.
- **TDD is the house rule.** Phase 1 tasks are behaviour-preserving refactors: each adds one name to the `test_reporting_simple_exposes_result_builders` e2e (RED → GREEN) and re-runs the affected slice of the existing Simple suite. Phase 2 tasks write the failing dashboard e2e first.
- **TEST env has NO Statistics DB** — reporting runs can never execute for real in e2e. Stub `**/api/reporting/run` (and `**/api/reporting/reports*`, `**/api/reporting/sources`, `**/api/reporting/metrics`) **before** `page.goto` — copy the neighbouring tests in `tests/e2e/test_reporting_dashboard.py`.
- **Before running any e2e tier:** `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py`. Use your **own e2e port** so a stale TEST server from another session can't collide: `$env:NEXORA_E2E_PORT = "8791"` (any free port) in the shell you run pytest from.
- **e2e locale is English** — assert English strings ("Show table", "Hide table").
- **Jinja template cache is process-lifetime** — restart the dev server before ANY manual browser check: `& C:\dev\nexora\bin\nx.ps1 -u --env:staging --no-conflict` starts your own STAGING instance on the first free port ≥ 8001 (STAGING has real multi-metric reports + `BacklogHistory` snapshots; the owner said "not INT" for reporting checks). Login: `http://localhost:<port>/dev/login/ben.streich`. STAGING locale is **de** (labels: *Neues Dashboard*, *Bearbeiten*, *Fertig*, *Karte hinzufügen*). Drive Playwright yourself (own browser, never the user's Chrome); save shots to `var/screenshots/` and send them. Kill the browser and stop your instance (`& C:\dev\nexora\bin\nx.ps1 -d --port:<port>`) when done.
- **Migrations needed: NO.** No SQL, no new permission code, no `page_visibility()` change, no `deploy.yml` change (only `templates/`, `static/`, `tests/`, `translations/`, `docs/`, `CHANGELOG.md` are touched).
- **i18n: ONE late pybabel cycle (Task 9).** New msgids land in Task 8 only ("Whole report" + one help tip); `tests/unit/test_translations.py` is expected RED between Task 8 and Task 9 — `--deselect tests/unit/test_translations.py` until then. `tests/unit/test_reporting_i18n_lint.py` lints the reporting partials — every new UI string must be `{{ _('…') }}`-wrapped from the start (the two new dashboard I18N keys reuse existing msgids).
- **Pre-commit hooks:** the SQL hooks run on every commit; if INT is unreachable use `SQL_SYNC_SKIP=1 git commit …`, never `--no-verify`. `mixed-line-ending` may rewrite `.po` files on the first attempt → `git add translations/` and commit again. `reporting-help-sync` prints a reminder when the JS partials change without `docs/howto/reporting-guide.md` + `templates/_reporting_help.html` — Task 8 updates both.
- **PROD URL prefix:** the dashboard partial's `api()` helper already normalizes through `API_PREFIX`; never hand-build a root-relative URL.
- **Visual contract:** never rename a `.reporting-*`/`.rs-*`/`.rdb-*` class; preserve every existing `data-testid`/`id` (the one deliberate removal — `rdb-report-total` — is covered by the test rewrite in Task 6); `.nx-rise*` animations use fill-mode `backwards`, never `both`.
- **gitlint:** conventional-commit title ≤72 chars, imperative, no trailing period; non-empty body wrapped ≤100 chars; commit via Bash `git commit -F - <<'EOF' … EOF`. **Commit trailer names the EXECUTING model** — the blocks below say `Claude Sonnet 5`; substitute the real executor if different.

---

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Upgrade the existing `'report'` card type; do not add a sixth type.** The add-tile pill keeps `data-add-type="report"` and `data-testid="rdb-add-report"`; its label becomes **"Whole report"**. Saved dashboards with `type:'report'` cards upgrade automatically. | The pill already *means* "the whole report" (#178 D12); only its rendering was lossy. No schema change for saved dashboards. |
| D2 | **Render through the Simple pane's own builders, exposed on `window.ReportingSimple`.** Four renderers are split into pure builder + thin DOM wrapper. The dashboard never reaches into Simple's DOM or state; it only calls functions that take data in and return HTML / Chart.js config. | The only way "as on the Simple tab" stays true over time — a second copy of the forecast/colour/axis logic in the dashboard partial would drift (today's card is exactly that drift). Load order is fine: `_reporting_simple.html` includes the Simple partial before the dashboard partial, and the card calls happen at run time anyway. |
| D3 | **`chartConfigFor(d, type, def, opts)` takes the definition, not a style object.** Style = `def.style`; the date grain comes from `def.columns[0].grain`. `opts.onDrill(index, datasetIndex)` replaces the Simple-internal `drillFromChart`; `this.data.datasets` replaces `state.chart.data.datasets` inside the click handler (Chart.js binds `this` to the chart). | The in-flight partial-bucket work reads the grain inside `renderChart`; passing `def` keeps the builder pure for both callers. |
| D4 | **Two runs per whole-report card, same as Simple:** the breakdown run POSTs the effective definition **plus `compare: true`** (delta chips), then a zero-column clone (`columns: []`, `sort: []`, no `forecast`, no `compare`) feeds the stat card. `compare` rides on a *copy* of the body only — `cardRunDef`'s return value is also what Export uses. | Grand totals must be aggregation-correct (avg/count_distinct); summing grouped rows is what produced today's wrong "5,889". |
| D5 | **Testids from the Simple builders get an `rdb-` prefix inside cards** (`rs-kpi-total` → `rdb-rs-kpi-total`, `rs-forecast-row` → `rdb-rs-forecast-row`) via a one-line `prefixTestIds(root)` pass. | A closed dashboard stays mounted (hidden) under `#rsDashboard`; duplicate testids would trip Playwright strict mode in the Simple suite. |
| D6 | **Read-only card.** No chart-type switcher, forecast toggle, colour popover or AI caption inside the card — the card renders the *saved* state; edit the report itself to change it. Drill-through (chart click + table row) **is** in scope: it's part of "the whole report" and the plumbing (`openCardDrill`, `clickedFor`, `handleCardTableRowClick`) exists. | YAGNI; controls inside a 12-span card would duplicate the Simple toolbar and its state machine. |
| D7 | **Table collapsed behind *Show table* when a chart rendered; shown directly otherwise** — the exact rule Simple applies (`rsTableToggle`). Count-up animation is skipped on cards (final numbers written directly). | Same reading experience as the Simple tab, no animation storms on multi-card dashboards. |
| D8 | **CSS is additive:** new `.rdb-report*` rules appended to `static/css/reporting.css`; the three dead `.rdb-report-total*` rules are deleted in the same block. Simple's KPI/stat/table classes are already global (not scoped under `#rsResult`) and reused as-is. | Keeps the eventual merge with the owner's branch trivial. |
| D9 | **Span stays 12** (`DEFAULT_SPAN.report`), chart area 320px tall (Simple's canvas `max-height: 320px`), table capped at 420px with its own scrollbar. | A whole report needs the row; a 190px card body (today) cannot carry it. |

---

## Owner actions (not for the executor)

1. **Before `/execute-plan`:** fast-forward the plan worktree onto the tip that already carries the audit fixes: `git -C .claude\worktrees\plan-dashboard-whole-report-card merge --ff-only v3.2.3.1` (moves `plan/dashboard-whole-report-card` from `33b42f4c` to `48a08364`; the plan commit lands on top). Or tell the executor "fast-forward onto v3.2.3.1" — a merge needs your per-turn OK under the git policy.
2. **After execution:** review + merge `plan/dashboard-whole-report-card` into `v3.2.3.1`, push, delete the worktree + branch. No env keys, no migration → no `env-sync`, no PROD SQL.
3. **Deliberately deferred** (say the word if wanted): live controls inside the card (chart type / forecast / colours), AI caption per card, whole-dashboard XLSX export, latest-snapshot awareness in the *other* card types (KPI/line/bar/table still sum).

---

# PHASE 1 — Simple pane: extract pure result builders (behaviour-preserving)

All Phase 1 edits are in `templates/js/_reporting_simple_js.html`. After each task the affected slice of `tests/e2e/test_reporting_simple.py` must still be green. Run the fast tier from the worktree root:

```powershell
$env:NEXORA_E2E_PORT = "8791"
C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py
C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -k "<slice>" -q
```

### Task 1: `kpiBandHtml` + `statCardHtml` + `ensureCatalogs`, exposed on `window.ReportingSimple`

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (`renderKpiBand`, `fillStatCard`, `window.ReportingSimple = …`)
- Test: `tests/e2e/test_reporting_simple.py` (append)

**Interfaces (Produces — Phase 2 relies on these exact names):**
- `window.ReportingSimple.kpiBandHtml(dims:number, rows:any[][], comparison:object|null, def:object) → string` ('' when no numeric metric column)
- `window.ReportingSimple.statCardHtml(def:object, rowVals:any[], withIds:boolean) → string`
- `window.ReportingSimple.ensureCatalogs() → Promise<void>` (warms `state.sources` + `state.metricsBySource`)
- `window.ReportingSimple.fmtNumber(v) → string`, `window.ReportingSimple.zeroFillDateBuckets(def, rows, resolvedDates) → any[][]` (existing functions, just exposed)

- [ ] **Step 1 — Failing e2e.** Append to `tests/e2e/test_reporting_simple.py` (Grep `def _login` in that file first and call it the way its neighbours do — the module's helper takes `(page, base)`):

```python
def test_reporting_simple_exposes_result_builders(nexora_server, page):
    """Whole-report dashboard cards draw through the Simple pane's own result
    builders; they must be reachable (and pure functions) on
    window.ReportingSimple. Each Phase-1 task of the whole-report-card plan
    adds its builder to this list."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    expect(page.get_by_test_id("rs-hero")).to_be_visible()
    names = ["ensureCatalogs", "fmtNumber", "zeroFillDateBuckets", "kpiBandHtml", "statCardHtml"]
    kinds = page.evaluate(
        "(names) => names.map(k => typeof window.ReportingSimple[k])", names
    )
    assert kinds == ["function"] * len(names), dict(zip(names, kinds))
```

- [ ] **Step 2 — RED:** `…pytest tests/e2e/test_reporting_simple.py -k exposes_result_builders -q` → fails (`undefined` for every name).

- [ ] **Step 3 — Split `renderKpiBand`.** Find `function renderKpiBand(dims, rows, comparison, def) {`. Its body today is: `var band = el('rsKpiBand');` → `var kpi = computeKpiBand(dims, rows);` → `if (!kpi) { band.hidden = true; band.innerHTML = ''; return; }` → (prior-period / latest-total / delta / sparkline computations) → `band.innerHTML =` `'<div class="rs-kpi-total-card" …` … `'</div>';` → `band.hidden = false;` → the `animateValue` loop. Rewrite it as **two** functions: everything from `var kpi = computeKpiBand(dims, rows);` down to the closing `'</div>';` of the big string moves into the new builder **unchanged**, except for the two marked lines:

```js
  // Pure HTML builder for the KPI band (Total / Buckets / Avg / Peak, prior-
  // period delta chips, sparkline). Returns '' when the rows carry no numeric
  // metric column. DOM-free -- shared with the dashboard's whole-report card
  // via window.ReportingSimple, so it must never touch #rs* elements.
  function kpiBandHtml(dims, rows, comparison, def) {
    var kpi = computeKpiBand(dims, rows);
    if (!kpi) return '';                                   // <-- was: band.hidden = true; band.innerHTML = ''; return;
    // ... the existing computations, verbatim (priorRows, priorKpi, latestKey,
    //     totalDelta/avgDelta/peakDelta, sparkHtml) ...
    return                                                  // <-- was: band.innerHTML =
      '<div class="rs-kpi-total-card" data-testid="rs-kpi-total">' +
      // ... the existing string, verbatim, down to its closing '</div>';
  }

  function renderKpiBand(dims, rows, comparison, def) {
    var band = el('rsKpiBand');
    var html = kpiBandHtml(dims, rows, comparison, def);
    if (!html) { band.hidden = true; band.innerHTML = ''; return; }
    band.innerHTML = html;
    band.hidden = false;
    Array.prototype.forEach.call(band.querySelectorAll('[data-count-target]'), function (span) {
      animateValue(span, Number(span.getAttribute('data-count-target')), fmtNumber);
    });
  }
```

- [ ] **Step 4 — Split `fillStatCard`.** Find `function fillStatCard(def, rowVals) {` (body: `var labels = metricLabelsFor(def);` → `el('rsStatBody').innerHTML = labels.map(function (lb, i) {` … `}).join('');` → `el('rsStatCard').hidden = false;`). Replace the whole function with:

```js
  // Pure: one label/value pair per metric. withIds keeps the rsStatLabel/
  // rsStatValue ids on the first pair (the Simple pane's tests target them);
  // the dashboard's whole-report card passes false so ids never duplicate.
  function statCardHtml(def, rowVals, withIds) {
    var labels = metricLabelsFor(def);
    return labels.map(function (lb, i) {
      var idL = (withIds && i === 0) ? ' id="rsStatLabel"' : '';
      var idV = (withIds && i === 0) ? ' id="rsStatValue"' : '';
      return '<p class="nx-stat__label"' + idL + '>' + esc(lb) + '</p>' +
             '<div class="nx-stat__value"' + idV + '>' + fmtNumber(rowVals[i]) + '</div>';
    }).join('');
  }

  function fillStatCard(def, rowVals) {
    el('rsStatBody').innerHTML = statCardHtml(def, rowVals, true);
    el('rsStatCard').hidden = false;
  }
```

- [ ] **Step 5 — `ensureCatalogs`.** Directly after the function `async function loadSourcesCatalog() {` … `}` add:

```js
  // Warms the two catalogs the shared builders read through state
  // (metricLabelsFor, applyLatestTotal, fieldMetaFor). Idempotent -- both
  // loaders short-circuit once filled. Exposed for the dashboard's
  // whole-report card, which renders while the Simple result view is idle.
  async function ensureCatalogs() {
    await loadSourcesCatalog();
    if (!state.metricsBySource) await loadMetricsCatalog();
  }
```

- [ ] **Step 6 — Expose.** Replace the line `window.ReportingSimple = { openDefinition: openDefinition };` with:

```js
  // Result builders shared with the dashboard's whole-report card
  // (_reporting_dashboard_js.html renderReportCard). Everything here is
  // DOM-free except ensureCatalogs (network); none of it touches the Simple
  // pane's own elements, so a card can call them while #rsResult is hidden.
  window.ReportingSimple = {
    openDefinition: openDefinition,
    ensureCatalogs: ensureCatalogs,
    fmtNumber: fmtNumber,
    zeroFillDateBuckets: zeroFillDateBuckets,
    kpiBandHtml: kpiBandHtml,
    statCardHtml: statCardHtml
  };
```

- [ ] **Step 7 — GREEN + regression slice:** `…pytest tests/e2e/test_reporting_simple.py -k "exposes_result_builders or kpi_band or total_only or latest_snapshot" -q` → all pass.

- [ ] **Step 8 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
refactor(reporting): extract KPI-band and stat-card HTML builders

renderKpiBand and fillStatCard split into pure builders (kpiBandHtml,
statCardHtml) plus thin DOM wrappers, and window.ReportingSimple now
exposes them together with ensureCatalogs, fmtNumber and
zeroFillDateBuckets. First step of the dashboard whole-report card, which
renders through the Simple pane's own builders. No behaviour change.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

### Task 2: `buildChartData` (split `mountChart`)

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (`mountChart`)
- Test: `tests/e2e/test_reporting_simple.py` (edit the list in `test_reporting_simple_exposes_result_builders`)

**Interfaces (Produces):**
- `window.ReportingSimple.buildChartData(def, columns, rows, forecast|null) → { data: object|null, note: string|null }` — `data` is the chart-data block (`{labels, rawX, datasets, multiSeries, forecast?, forecastStart?, rawSeries?, type}`); `data: null` means "no chart" and `note` says why; `note` with `data` is a non-blocking disclosure to show under the chart.

- [ ] **Step 1 — RED:** in the e2e from Task 1 change the list to `names = ["ensureCatalogs", "fmtNumber", "zeroFillDateBuckets", "kpiBandHtml", "statCardHtml", "buildChartData"]`; run `-k exposes_result_builders` → fails on `buildChartData`.

- [ ] **Step 2 — Move the body.** Find `function mountChart(def, columns, rows, forecast) {`. Its head is DOM work (`destroyChart();` … `if (!window.Chart) { chartCardNote(I18N.noChartLib); return false; }`), then `var firstCol = def.columns[0];` starts the pure part, which ends with the second `renderChart(state.chartData.type);` + `return true;` + the function's closing `}`. Create the new function **directly above** `mountChart`, moving everything from `var firstCol = def.columns[0];` to the end of `mountChart`'s body into it:

```js
  // Pure: turns a run result into the chart-data block renderChart /
  // chartConfigFor draw. Returns {data, note}: data null = no chart and
  // note says why (too many points); note alongside data = a non-blocking
  // disclosure (first-50 cut, series cap, data-quality notes). DOM-free --
  // shared with the dashboard's whole-report card via window.ReportingSimple.
  function buildChartData(def, columns, rows, forecast) {
    var note = null;
    function addNote(txt) { note = note ? note + ' — ' + txt : txt; }
    var dims = (def.columns || []).length;
    if (!dims || !rows.length) return { data: null, note: null };
    var firstCol = def.columns[0];
    // ... moved body, with the replacements listed in Step 3 ...
  }
```

- [ ] **Step 3 — Apply these replacements inside the moved body** (Grep each; apply to *every* occurrence):

| Was (inside the moved body) | Becomes |
|---|---|
| `chartCardNote(I18N.noChartTooManyPoints); return false;` (two places: the single-dim `if (isDate) { … }` guard and the `if (xOrder.length > xCap) { … }` guard) | `return { data: null, note: I18N.noChartTooManyPoints };` |
| the pair `el('rsChartNote').textContent = I18N.chartFirst50.replace('{n}', String(rows.length));` + `el('rsChartNote').hidden = false;` | `addNote(I18N.chartFirst50.replace('{n}', String(rows.length)));` |
| the pair `el('rsChartNote').textContent = I18N.chartSeriesCapped` `.replace(...)…;` + `el('rsChartNote').hidden = false;` | `addNote(I18N.chartSeriesCapped.replace('{shown}', String(series.length)).replace('{n}', String(allSeries.length)));` |
| `noteDataQuality(def, rows, isDate);` (two places — end of the `dims >= 2` branch and before the single-dim `state.chartData = {`) | `noteDataQuality(def, rows, isDate).forEach(addNote);` — **and** change `function noteDataQuality(def, rows, isDate) {` (defined right below `mountChart`) to collect into an array and `return` it instead of calling `appendChartNote`: `var out = [];` at the top, `out.push(I18N.partialBucketNote)` / `out.push(I18N.gapNote)` where it currently calls `appendChartNote(...)`, `return out;` at the end (early `return;` becomes `return out;`). `appendChartNote` itself stays — `syncForecastCtl` still uses it. |
| any other `appendChartNote(X);` that turns out to be inside the moved body | `addNote(X);` |
| the block `state.chartData = { … };` + `el('rsChartCard').hidden = false;` + `el('rsChartTools').hidden = false;` + `renderChart(state.chartData.type);` + `return true;` (two places: end of the `dims >= 2` branch, and the end of the function) | `return { data: { … }, note: note };` — the object literal is the former `state.chartData` value, verbatim |

After this, `buildChartData` must contain **no** `el(`, `state.`, `chartCardNote`, `renderChart` or `appendChartNote` reference — Grep the function body to confirm.

- [ ] **Step 4 — Rewrite `mountChart` as the DOM wrapper:**

```js
  function mountChart(def, columns, rows, forecast) {
    destroyChart();
    state.chartData = null;
    el('rsChartNote').hidden = true;
    el('rsChartTools').hidden = true;
    toggleStylePop(false);
    el('rsChartCanvas').hidden = false;
    var dims = (def.columns || []).length;
    if (!dims || !rows.length) { el('rsChartCard').hidden = true; return false; }
    if (!window.Chart) { chartCardNote(I18N.noChartLib); return false; }
    var built = buildChartData(def, columns, rows, forecast);
    if (!built.data) { chartCardNote(built.note || I18N.noChartTooManyPoints); return false; }
    if (built.note) {
      el('rsChartNote').textContent = built.note;
      el('rsChartNote').hidden = false;
    }
    state.chartData = built.data;
    el('rsChartCard').hidden = false;
    el('rsChartTools').hidden = false;
    renderChart(state.chartData.type);
    return true;
  }
```

- [ ] **Step 5 — Expose:** add `buildChartData: buildChartData,` after the `statCardHtml: statCardHtml` line in `window.ReportingSimple = {` (mind the comma on the previous line).

- [ ] **Step 6 — GREEN + regression slice:** `…pytest tests/e2e/test_reporting_simple.py -k "exposes_result_builders or chart or forecast or breakdown or series" -q` → all pass. Restart the dev server, open any grained report on the Simple tab, confirm the chart + notes look unchanged.

- [ ] **Step 7 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
refactor(reporting): split mountChart into pure buildChartData + wrapper

The pivot/label/forecast-bucket logic moves into buildChartData, which
returns {data, note} and never touches the DOM; mountChart keeps the
#rsChart* side effects. Exposed on window.ReportingSimple for the
dashboard whole-report card. No behaviour change.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

### Task 3: `chartConfigFor` (split `renderChart`)

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (`renderChart`)
- Test: `tests/e2e/test_reporting_simple.py` (edit the names list)

**Interfaces (Produces):**
- `window.ReportingSimple.chartConfigFor(d:chartData, type:string, def:object, opts:{onDrill?:function(index, datasetIndex)}) → { type: string, multi: boolean, circular: boolean, config: ChartJsConfig }` — `type` is the *resolved* type (multi-series pie/doughnut fall back to bar); `config` goes straight into `new Chart(canvas, config)`.

- [ ] **Step 1 — RED:** add `"chartConfigFor"` to the names list; run `-k exposes_result_builders` → fails.

- [ ] **Step 2 — Move the body.** Find `function renderChart(type) {`. Head: `var d = state.chartData;` / `if (!d) return;` / `destroyChart();`. The pure part starts at `var multi = !!(d && d.multiSeries);` and ends with the `});` that closes `state.chart = new Chart(el('rsChartCanvas'), {`. After that comes the DOM tail (`el('rsChartTools').querySelector('[data-type="pie"]').hidden = multi;` … the `is-selected` toggle loop). Create the new function **directly above** `renderChart`, moving the pure part into it:

```js
  // Pure: the Chart.js config for a chart-data block. `def` supplies the
  // saved style (colours / right-axis picks) and the date grain; opts.onDrill
  // (index, datasetIndex) receives clicks on real (non-forecast) elements.
  // Reads only the dark-mode class and --nx-border from the document.
  // Returns {type, multi, circular, config}. Shared with the dashboard's
  // whole-report card via window.ReportingSimple.
  function chartConfigFor(d, type, def, opts) {
    var style = (def && def.style) || {};
    var onDrill = (opts && opts.onDrill) || function () {};
    var multi = !!(d && d.multiSeries);
    // ... moved body, with the replacements listed in Step 3 ...
    return { type: type, multi: multi, circular: circular, config: config };
  }
```

- [ ] **Step 3 — Apply these replacements inside the moved body:**

| Was | Becomes |
|---|---|
| `state.chartType = type;` | *(delete — `renderChart` sets it from the return value)* |
| `var style = styleOf();` | *(delete — `style` is now the first line of the builder)* |
| `state.chart = new Chart(el('rsChartCanvas'), {` | `var config = {` |
| the matching closing `});` (the one right before the `el('rsChartTools')…hidden = multi;` tail) | `};` |
| `var dsHit = (state.chart.data.datasets || [])[els[0].datasetIndex] || {};` | `var dsHit = (this.data.datasets || [])[els[0].datasetIndex] || {};` |
| `drillFromChart(els[0].index, els[0].datasetIndex);` | `onDrill(els[0].index, els[0].datasetIndex);` |
| the two-line statement starting `var grain0 = (state.current && state.current.def && (state.current.def.columns || [])[0])` and ending `? state.current.def.columns[0].grain : null;` (partial-bucket fade) | `var grain0 = (def && (def.columns || [])[0]) ? def.columns[0].grain : null;` |

After this, `chartConfigFor` must contain **no** `state.`, `el(`, `styleOf`, `drillFromChart` or `forecastEligible` reference — Grep the function body to confirm (`gridColor()`, `hexAlpha`, `seriesKey`, `rightAxisKeys`, `fmtChartTooltip`, `NX_PALETTE`, `I18N.forecastLabel` are fine — they are module-level helpers/constants that don't touch Simple's DOM).

- [ ] **Step 4 — Rewrite `renderChart` as the DOM wrapper** (its tail — everything from `el('rsChartTools').querySelector('[data-type="pie"]').hidden = multi;` to the end — stays **verbatim**):

```js
  function renderChart(type) {
    var d = state.chartData;
    if (!d) return;
    destroyChart();
    var built = chartConfigFor(d, type, (state.current && state.current.def) || {}, { onDrill: drillFromChart });
    type = built.type;
    state.chartType = type;
    var multi = built.multi, circular = built.circular;
    state.chart = new Chart(el('rsChartCanvas'), built.config);
    el('rsChartTools').querySelector('[data-type="pie"]').hidden = multi;
    // ... existing tail, verbatim ...
  }
```

- [ ] **Step 5 — Expose:** add `chartConfigFor: chartConfigFor,` after `buildChartData: buildChartData,` in `window.ReportingSimple = {`.

- [ ] **Step 6 — GREEN + regression slice:** `…pytest tests/e2e/test_reporting_simple.py -k "exposes_result_builders or chart or forecast or drill or series or colors" -q` → all pass. Restart the dev server, open a multi-measure report (STAGING: *DEMO* — imports/exports/backlog with the backlog on the right axis and a forecast), confirm colours, right axis, forecast tail, legend and a chart-click drill all still work; screenshot to `var/screenshots/whole-report-01-simple-unchanged.png`.

- [ ] **Step 7 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
refactor(reporting): split renderChart into pure chartConfigFor + wrapper

chartConfigFor(d, type, def, opts) builds the Chart.js config (saved
colours, right axis, forecast tail/band, legend/tooltip/drill hooks)
without touching the Simple pane's DOM or state; renderChart mounts the
result and keeps the toolbar side effects. Exposed on
window.ReportingSimple for the dashboard whole-report card. No behaviour
change.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

### Task 4: `tableHtml` (split `renderTable`)

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (`renderTable`)
- Test: `tests/e2e/test_reporting_simple.py` (edit the names list)

**Interfaces (Produces):**
- `window.ReportingSimple.tableHtml(columns, rows, forecast|null, drillable:boolean) → string` — the full `<table class="reporting-table …">` markup incl. forecast rows (`data-testid="rs-forecast-row"`); `drillable` only toggles the `reporting-drill-clickable` class — the **caller** binds row handlers.

- [ ] **Step 1 — RED:** add `"tableHtml"` to the names list; run `-k exposes_result_builders` → fails.

- [ ] **Step 2 — Split.** Find `function renderTable(columns, rows, forecast) {`. Its body computes `drillable` (reads `state.current`, `state.sources`, `ReportingDrill.buildDrillDefinition`, `clickedFor`), then builds `var html = '<table class="reporting-table' + (drillable ? ' reporting-drill-clickable' : '') +` … down to `html += '</tbody></table>';`, then writes `el('rsTableWrap').innerHTML = html;`, binds row clicks, and sets `el('rsDrillHint').hidden = !drillable;`. Create `tableHtml` **directly above** `renderTable` by moving everything from `var html = '<table class="reporting-table'` through `html += '</tbody></table>';` into it (verbatim) and returning `html`:

```js
  // Pure HTML builder for the result grid (data bars + forecast rows).
  // `drillable` only adds the clickable class -- the caller binds the row
  // handlers. Shared with the dashboard's whole-report card.
  function tableHtml(columns, rows, forecast, drillable) {
    var html = '<table class="reporting-table' + (drillable ? ' reporting-drill-clickable' : '') +
      '"><thead><tr>';
    // ... moved body, verbatim ...
    html += '</tbody></table>';
    return html;
  }
```

and in `renderTable` replace the moved block + `el('rsTableWrap').innerHTML = html;` with the single line:

```js
    el('rsTableWrap').innerHTML = tableHtml(columns, rows, forecast, drillable);
```

(the `drillable` computation above it and the `if (drillable) { … }` binding + `el('rsDrillHint').hidden = !drillable;` below it stay verbatim.)

- [ ] **Step 3 — Expose:** add `tableHtml: tableHtml` after `chartConfigFor: chartConfigFor,` in `window.ReportingSimple = {` (last entry — no trailing comma).

- [ ] **Step 4 — GREEN + regression slice:** `…pytest tests/e2e/test_reporting_simple.py -k "exposes_result_builders or drill_row or forecast_trims or forecast_toggle or table" -q` → all pass.

- [ ] **Step 5 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
refactor(reporting): extract tableHtml from renderTable

The grid markup (data bars, forecast rows) is built by a pure tableHtml;
renderTable keeps the drillable probe, the #rsTableWrap write and the row
handlers. Exposed on window.ReportingSimple for the dashboard
whole-report card. No behaviour change.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

### Task 5: Phase 1 gate — full Simple suite + lints

**Files:** none modified.

- [ ] **Step 1:** `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py`
- [ ] **Step 2:** `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py tests/e2e/test_reporting_dashboard.py tests/e2e/test_reporting_viz.py -q` → all green (dashboard suite still green: `renderReportCard` is untouched so far).
- [ ] **Step 3:** `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_i18n_lint.py tests/unit/test_no_inline_event_handlers.py tests/unit/test_template_url_prefix.py tests/unit/test_translations.py -q` → green (no new msgids yet).
- [ ] **Step 4:** If anything failed, fix it in the task that introduced it (amend nothing — add a `fix(reporting): …` commit). Nothing to commit otherwise.

---

# PHASE 2 — Dashboard: the whole-report card

All Phase 2 JS edits are in `templates/js/_reporting_dashboard_js.html`; CSS appends go to the end of `static/css/reporting.css`.

### Task 6: Render the whole report inside the card (stat card, KPI band, chart, table)

**Files:**
- Modify: `templates/js/_reporting_dashboard_js.html` (`I18N`, `runCard`, `renderCardContent`, `renderReportCard`, new `prefixTestIds`, `reportCardDrillable`, `reportCardChartDrill`)
- Modify: `static/css/reporting.css` (replace the `#178 D11` block; append)
- Test: `tests/e2e/test_reporting_dashboard.py` (rewrite `test_report_card_runs_definition_unmodified`; add `test_whole_report_card_keeps_saved_colours_axis_forecast_and_table`)

**Interfaces:**
- Consumes (Phase 1): `window.ReportingSimple.{ensureCatalogs, fmtNumber, zeroFillDateBuckets, kpiBandHtml, statCardHtml, buildChartData, chartConfigFor, tableHtml}`; dashboard-internal `cardRunDef`, `effectiveFilters`, `runGen`, `charts`, `cardRunData`, `destroyCardChart`, `ensureCatalog`, `catalog`, `dimValIdx`, `clickedFor`, `openCardDrill`, `findCardById`, `esc`, `api`.
- Produces (Task 7 relies on): card markup with `.rdb-report-table-toggle` (`data-testid="rdb-report-table-toggle"`), `.rdb-report-table` (`data-testid="rdb-report-table"`, a `hidden` wrapper around the Simple `<table>`), `.rdb-report-chartcard canvas`; `cardRunData[card.id].rows` = the zero-filled, forecast-trimmed rows the table draws; `I18N.showTable` / `I18N.hideTable`.

- [ ] **Step 1 — Failing e2e (rewrite the existing report-card test).** In `tests/e2e/test_reporting_dashboard.py` find `def test_report_card_runs_definition_unmodified(nexora_server, page):`. Keep its `reports_list`, `adopted_definition`, `handle_reports` and the `**/api/reporting/reports/601` stub exactly as they are. Add `_stub_gfilter_catalog(page)` right after `_login(page, nexora_server)`. Replace its `fulfill_run` + everything from `page.goto(` to the end of the test with:

```python
    posted = []

    def fulfill_run(route):
        body = route.request.post_data_json or {}
        posted.append(body)
        if not body.get("columns"):
            # the zero-column grand-total clone the whole-report card fires
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"columns": [{"field": "id", "header": "Count"}], "rows": [[12]], "rowCount": 1}
                ),
            )
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "columns": [
                        {"field": "createdDate", "header": "Month"},
                        {"field": "id", "header": "Count"},
                    ],
                    "rows": [["2026-01-01", 5], ["2026-02-01", 7]],
                    "rowCount": 2,
                }
            ),
        )

    page.route("**/api/reporting/run", fulfill_run)

    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-dashboard").click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()

    page.get_by_test_id("rdb-add-report").click()
    expect(page.get_by_test_id("rdb-card")).to_have_count(1)
    expect(page.locator('[data-testid="rdb-card"][data-type="report"]')).to_have_count(1)

    page.get_by_test_id("rdb-card-configure").click()
    picker = page.get_by_test_id("rdb-report-picker")
    expect(picker).to_be_visible()
    page.get_by_test_id("rdb-report-pick").first.click()

    # The whole report: KPI band (Simple's own markup, rdb- prefixed testids),
    # chart canvas, grand-total stat card, table collapsed behind its toggle.
    expect(page.get_by_test_id("rdb-report-kpis")).to_be_visible()
    expect(page.get_by_test_id("rdb-rs-kpi-total")).to_contain_text("12")
    expect(page.locator('[data-testid="rdb-report-chartcard"] canvas')).to_be_visible()
    expect(page.get_by_test_id("rdb-report-stat")).to_contain_text("12")
    expect(page.get_by_test_id("rdb-report-table")).to_be_hidden()
    expect(page.get_by_test_id("rdb-report-table-toggle")).to_have_text("Show table")

    grained = [b for b in posted if (b.get("columns") or [{}])[0].get("grain") == "month"]
    assert grained, "definition lost its grain on the way to /run"
    assert grained[0]["filters"] == adopted_definition["filters"]
    assert grained[0]["sort"] == adopted_definition["sort"]
    assert grained[0].get("compare") is True, "whole-report run must ask for the prior period"
    totals = [b for b in posted if not b.get("columns")]
    assert totals and totals[0]["filters"] == adopted_definition["filters"]
    assert "compare" not in totals[0] and "forecast" not in totals[0]
```

Update the test's docstring to: `"""Whole-report card: POSTs the adopted definition as-is (grain, filters, sort intact, plus compare: true), fires the zero-column grand-total clone, and renders KPI band + chart + stat card + collapsed table."""`

- [ ] **Step 2 — Failing e2e (new).** Append to the same file:

```python
def test_whole_report_card_keeps_saved_colours_axis_forecast_and_table(nexora_server, page):
    """The card draws through the Simple pane's own builders: saved series
    colours and right-axis picks reach the Chart.js datasets, the forecast
    tail is drawn per series, and Show table reveals the full grid with its
    forecast rows."""
    _login(page, nexora_server)
    _stub_gfilter_catalog(page)
    definition = {
        "source": "workitems",
        "metrics": [{"metric": "id_count"}, {"metric": "backlog_total"}],
        "columns": [{"field": "createdDate", "grain": "month"}],
        "filters": [],
        "sort": [],
        "chartType": "line",
        "style": {
            "colors": {"id_count": "#00aa00", "backlog_total": "#ff0000"},
            "rightAxis": ["backlog_total"],
        },
        "forecast": {"enabled": True, "horizon": 2},
    }
    dash = {
        "kind": "dashboard",
        "schemaVersion": 1,
        "title": "e2e whole report",
        "globalFilters": [],
        "cards": [
            {"id": "r1", "type": "report", "span": 12, "title": "Imports vs backlog",
             "definition": definition, "filterOverrides": []}
        ],
    }
    _stub_dashboard_report(page, "e2e-dash-whole", dash)

    def fulfill_run(route):
        body = route.request.post_data_json or {}
        if not body.get("columns"):
            route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({
                    "columns": [{"field": "id_count", "header": "Count"},
                                {"field": "backlog_total", "header": "Backlog"}],
                    "rows": [[12, 90]], "rowCount": 1,
                }),
            )
            return
        route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({
                "columns": [{"field": "createdDate", "header": "Month"},
                            {"field": "id_count", "header": "Count"},
                            {"field": "backlog_total", "header": "Backlog"}],
                "rows": [["2026-01-01", 5, 100], ["2026-02-01", 7, 90]],
                "rowCount": 2,
                "forecast": {
                    "anchor": "2026-02-01",
                    "buckets": ["2026-03-01", "2026-04-01"],
                    "series": [
                        {"field": "id_count", "values": [8, 9], "upper": [10, 11], "lower": [6, 7]},
                        {"field": "backlog_total", "values": [80, 70], "upper": [90, 80], "lower": [70, 60]},
                    ],
                },
            }),
        )

    page.route("**/api/reporting/run", fulfill_run)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").filter(has_text="e2e whole report").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()

    canvas = page.locator('[data-testid="rdb-report-chartcard"] canvas')
    expect(canvas).to_be_visible()
    page.wait_for_function(
        "() => { const c = document.querySelector('[data-testid=\"rdb-report-chartcard\"] canvas');"
        " return !!(c && window.Chart && Chart.getChart(c)); }"
    )
    datasets = page.evaluate(
        "() => { const c = document.querySelector('[data-testid=\"rdb-report-chartcard\"] canvas');"
        " return Chart.getChart(c).data.datasets.map(d => [d.borderColor, d.yAxisID || 'y', !!d._forecast]); }"
    )
    real = [d for d in datasets if not d[2]]
    assert [d[0] for d in real] == ["#00aa00", "#ff0000"], datasets
    assert [d[1] for d in real] == ["y", "y2"], datasets
    assert sum(1 for d in datasets if d[2]) == 2, datasets  # one forecast tail per series

    expect(page.get_by_test_id("rdb-rs-kpi-total")).to_contain_text("12")
    expect(page.get_by_test_id("rdb-report-stat")).to_contain_text("12")
    expect(page.get_by_test_id("rdb-report-stat")).to_contain_text("90")

    expect(page.get_by_test_id("rdb-report-table")).to_be_hidden()
    page.get_by_test_id("rdb-report-table-toggle").click()
    expect(page.get_by_test_id("rdb-report-table")).to_be_visible()
    expect(page.get_by_test_id("rdb-report-table-toggle")).to_have_text("Hide table")
    expect(page.get_by_test_id("rdb-rs-forecast-row")).to_have_count(2)
```

> `_stub_dashboard_report(page, report_id, definition)` already exists in this file (it stubs the list + GET-by-id so the library shows one dashboard card). `_stub_gfilter_catalog` stubs `/api/reporting/sources` + `/api/reporting/metrics` with the `workitems` source and an `id_count` metric — `backlog_total` simply falls back to its code as label, which is fine here.

- [ ] **Step 3 — RED:** `…pytest tests/e2e/test_reporting_dashboard.py -k "report_card or whole_report" -q` → both fail (no `rdb-report-kpis`, toggle etc.).

- [ ] **Step 4 — I18N keys.** In the `var I18N = {` map find the **last** entry `chartSeriesCapped: {{ _("Showing the {shown} largest of {n} series.")|tojson }}` — add a trailing comma to it and append (both msgids already exist in the Simple partial → no new translations):

```js
    // Whole-report card table toggle -- same msgids as the Simple pane's
    // #rsTableToggle so the two surfaces read identically.
    showTable: {{ _("Show table")|tojson }},
    hideTable: {{ _("Hide table")|tojson }}
```

- [ ] **Step 5 — `runCard`: post `compare: true` for report cards and branch to the new renderer.** In `async function runCard(card, cardEl) {` replace

```js
    var def = cardRunDef(card, effectiveFilters(card));
    var res = await api('/api/reporting/run', { method: 'POST', body: JSON.stringify(def) });
```

with

```js
    var def = cardRunDef(card, effectiveFilters(card));
    // Whole-report cards mirror the Simple result run: compare: true rides on
    // a COPY of the body (cardRunDef's value also feeds Export) so the KPI
    // band gets its prior-period delta chips.
    var posted = card.type === 'report' ? Object.assign({}, def, { compare: true }) : def;
    var res = await api('/api/reporting/run', { method: 'POST', body: JSON.stringify(posted) });
```

and replace

```js
    body.className = 'rdb-card-body';
    cardRunData[card.id] = { columns: res.data.columns, rows: res.data.rows };
    renderCardContent(card, body, res.data.columns, res.data.rows);
```

with

```js
    body.className = 'rdb-card-body';
    if (card.type === 'report') { renderReportCard(card, body, def, res.data, gen); return; }
    cardRunData[card.id] = { columns: res.data.columns, rows: res.data.rows };
    renderCardContent(card, body, res.data.columns, res.data.rows);
```

In `function renderCardContent(card, body, columns, rows) {` **delete** the line `if (card.type === 'report') return renderReportCard(card, body, columns, rows);`.

- [ ] **Step 6 — Replace `renderReportCard`.** Delete the whole existing `function renderReportCard(card, body, columns, rows) { … }` (and its `// #178 D11: …` comment block) and put this in its place:

```js
  // Whole-report card: the saved report as the Simple tab shows it -- stat
  // card (per-metric grand totals), KPI band, the chart with its saved
  // colours / right axis / forecast, and the full table behind a toggle.
  // Everything is drawn by the Simple pane's own builders
  // (window.ReportingSimple), so the two surfaces cannot drift apart. `def`
  // is the effective definition that was POSTed (global filters merged).
  async function renderReportCard(card, body, def, data, gen) {
    destroyCardChart(card.id);
    var RS = window.ReportingSimple;
    await RS.ensureCatalogs();   // metric labels / latest-mode totals
    await ensureCatalog();       // this module's own source catalog (drill probe)
    if (runGen[card.id] !== gen) return;
    var hasMetrics = Array.isArray(def.metrics) && def.metrics.length > 0;
    var dims = (def.columns || []).length;
    var columns = data.columns || [];
    var rows = RS.zeroFillDateBuckets(def, data.rows || [], data.resolvedDates || []);
    var fc = data.forecast || null;
    // Same trailing trim as the Simple pane's runCurrent: zero-fill pads to
    // the filter range, but the forecast starts at the last REAL bucket.
    if (fc && !fc.unavailable && fc.anchor) {
      rows = rows.filter(function (r) {
        return String(r[0] == null ? '' : r[0]).slice(0, 10) <= fc.anchor;
      });
    }
    cardRunData[card.id] = { columns: columns, rows: rows };
    body.innerHTML =
      '<div class="rdb-report" data-testid="rdb-report">' +
        '<div class="rdb-report-side">' +
          '<div class="nx-card nx-card--pad nx-stat rdb-report-stat" data-testid="rdb-report-stat" hidden></div>' +
          '<div class="reporting-ledger-kpis rdb-report-kpis" data-testid="rdb-report-kpis" hidden></div>' +
        '</div>' +
        '<div class="nx-card nx-card--pad rdb-report-chartcard" data-testid="rdb-report-chartcard">' +
          '<p class="reporting-simple-chartnote rdb-report-note" data-testid="rdb-report-note" hidden></p>' +
          '<div class="rdb-report-chart"><canvas></canvas></div>' +
        '</div>' +
      '</div>' +
      '<div class="rdb-report-tablebar">' +
        '<button type="button" class="reporting-link rdb-report-table-toggle" ' +
          'data-testid="rdb-report-table-toggle">' + esc(I18N.showTable) + '</button>' +
      '</div>' +
      '<div class="reporting-table-wrap rdb-report-table" data-testid="rdb-report-table" hidden></div>';
    var q = function (sel) { return body.querySelector(sel); };

    // KPI band (Total / Buckets / Avg / Peak + prior-period chips). Cards
    // skip the count-up animation and write the final numbers.
    var kpiHtml = (hasMetrics && dims) ? RS.kpiBandHtml(dims, rows, data.comparison || null, def) : '';
    if (kpiHtml) {
      var kpis = q('.rdb-report-kpis');
      kpis.innerHTML = kpiHtml;
      kpis.hidden = false;
      Array.prototype.forEach.call(kpis.querySelectorAll('[data-count-target]'), function (span) {
        span.textContent = RS.fmtNumber(Number(span.getAttribute('data-count-target')));
      });
    }

    // Chart -- identical config to the Simple result view (saved colours,
    // right axis, forecast tail/band), on the card's own canvas.
    var charted = false;
    if (hasMetrics && dims && rows.length && typeof Chart !== 'undefined') {
      var built = RS.buildChartData(def, columns, rows, fc);
      if (built.note) { q('.rdb-report-note').textContent = built.note; q('.rdb-report-note').hidden = false; }
      if (built.data) {
        var cfg = RS.chartConfigFor(built.data, built.data.type, def, {
          onDrill: function (index, datasetIndex) { reportCardChartDrill(card, built.data, index, datasetIndex); }
        });
        charts[card.id] = new Chart(q('.rdb-report-chart canvas'), cfg.config);
        charted = true;
      } else {
        q('.rdb-report-chart').hidden = true;
      }
    } else {
      q('.rdb-report-chartcard').hidden = true;
    }

    // Table -- full rows (+ forecast rows). Collapsed behind the toggle only
    // when a chart carries the result, exactly like the Simple pane.
    var drillable = !!(hasMetrics && dims && rows.length && reportCardDrillable(card, def, columns, rows));
    q('.rdb-report-table').innerHTML = RS.tableHtml(columns, rows, fc, drillable);
    if (!charted) { q('.rdb-report-table').hidden = false; q('.rdb-report-tablebar').hidden = true; }
    prefixTestIds(body);

    // Stat card: per-metric grand totals via a zero-column clone -- correct
    // for every aggregation (avg / count_distinct), unlike summing the
    // grouped rows. Same clone the Simple pane's runCurrent fires.
    if (hasMetrics && dims) {
      var totalDef = JSON.parse(JSON.stringify(def));
      totalDef.columns = []; totalDef.sort = [];
      delete totalDef.forecast; delete totalDef.compare;
      var t = await api('/api/reporting/run', { method: 'POST', body: JSON.stringify(totalDef) });
      if (runGen[card.id] !== gen) return;
      var stat = q('.rdb-report-stat');
      if (stat && t.ok && t.data && Array.isArray(t.data.rows) && t.data.rows.length) {
        stat.innerHTML = RS.statCardHtml(def, t.data.rows[0], false);
        stat.hidden = false;
      }
    }
  }

  // The Simple builders stamp their own data-testids (rs-kpi-total,
  // rs-forecast-row, ...). Inside a card those would collide with the
  // (hidden but still mounted) Simple result view under Playwright's strict
  // mode, so they get an rdb- prefix: rs-kpi-total -> rdb-rs-kpi-total.
  function prefixTestIds(root) {
    Array.prototype.forEach.call(root.querySelectorAll('[data-testid^="rs-"]'), function (n) {
      n.setAttribute('data-testid', 'rdb-' + n.getAttribute('data-testid'));
    });
  }

  // Mirrors the Simple pane's renderTable probe: drillable only when the
  // leading columns resolve to a valid drill definition for the first row.
  function reportCardDrillable(card, def, columns, rows) {
    if (!window.ReportingDrill || !catalog.sources) return false;
    var src = catalog.sources.find(function (s) { return s.id === def.source; });
    if (!src) return false;
    var idx = dimValIdx(columns, card);
    var clicked = clickedFor(card, idx, idx.dims.map(function (d) { return rows[0][d]; }));
    return !!(clicked.length && ReportingDrill.buildDrillDefinition(def, src.fields || [], clicked));
  }

  // Chart click -> drill, mirroring the Simple pane's drillFromChart: the x
  // value comes from rawX; on a pivoted (multi-series) chart the clicked
  // series' raw per-dim values feed the remaining breakdowns.
  function reportCardChartDrill(card, d, index, datasetIndex) {
    var cols = (card.definition && card.definition.columns) || [];
    if (!cols.length) return;
    var clicked = [{ field: cols[0].field, grain: cols[0].grain || null,
                     value: (d.rawX || d.labels || [])[index] }];
    if (d.multiSeries && cols.length > 1) {
      var parts = (d.rawSeries || [])[datasetIndex] || [];
      for (var i = 1; i < cols.length; i++) {
        clicked.push({ field: cols[i].field, grain: cols[i].grain || null, value: parts[i - 1] });
      }
    }
    openCardDrill(card, clicked);
  }
```

> Grep `var catalog = ` in this partial to confirm the module-level catalog object (`catalog.sources` is what `openCardDrill` already reads) — do not introduce a second one.

- [ ] **Step 7 — CSS.** In `static/css/reporting.css` find the block starting with the comment `/* #178 D11 -- dashboard report card */` (four rules: `.rdb-report-total`, `.rdb-report-total-value`, `.rdb-report-total-label`, `.rdb-report-chart { min-height: 180px; position: relative; }`) and **replace the whole block** with:

```css
/* Whole-report dashboard card -- the Simple result view's own building
   blocks (stat card / KPI band / chart / table) laid out inside one
   span-12 card. Mirrors .rs-result-grid (250px rail + chart). */
.rdb-report { display: grid; grid-template-columns: 250px 1fr; gap: 14px; align-items: start; }
.rdb-report:has(.rdb-report-chartcard[hidden]) { grid-template-columns: 250px; }
.rdb-report-side { display: flex; flex-direction: column; gap: 10px; }
.rdb-report-stat { border-radius: calc(var(--nx-radius-scale, 1) * 14px); }
.rdb-report-kpis { display: flex; flex-direction: column; gap: 10px; padding: 0; }
.rdb-report-chartcard { min-height: 260px; border-radius: calc(var(--nx-radius-scale, 1) * 14px); }
.rdb-report-chart { position: relative; height: 320px; }
.rdb-report-note { margin: 0 0 6px; }
.rdb-report-tablebar { display: flex; justify-content: flex-end; margin-top: 10px; }
.rdb-report-table.reporting-table-wrap { min-height: 0; max-height: 420px; overflow: auto; margin-top: 8px; }
@media (max-width: 900px) { .rdb-report { grid-template-columns: 1fr; } }
```

- [ ] **Step 8 — GREEN:** `…pytest tests/e2e/test_reporting_dashboard.py -k "report_card or whole_report" -q` → both pass. Then the full dashboard file: `…pytest tests/e2e/test_reporting_dashboard.py -q`.

- [ ] **Step 9 — Real-app check.** Restart your STAGING instance (`& C:\dev\nexora\bin\nx.ps1 -r --port:<port>`), open `/reporting?tab=simple` → *Neues Dashboard* → *Karte hinzufügen* → the report pill → configure → pick *DEMO*. Confirm: three totals in the stat card, KPI band with chips, chart with backlog on the right axis + forecast, *Tabelle anzeigen* toggle. Screenshot → `var/screenshots/whole-report-02-card.png`, send it. Compare against `var/screenshots/_forclaudedesign/03-result-view.png`.

- [ ] **Step 10 — Commit:**

```bash
git add templates/js/_reporting_dashboard_js.html static/css/reporting.css tests/e2e/test_reporting_dashboard.py
git commit -F - <<'EOF'
feat(reporting): dashboard report card renders the whole report

The 'report' card type now draws the saved report as the Simple tab
does -- per-metric grand totals, the KPI band with prior-period chips,
the chart with its saved colours, right axis and forecast, and the full
table behind a Show-table toggle -- through the Simple pane's own
builders on window.ReportingSimple. Two runs per card like Simple
(breakdown with compare: true, zero-column clone for the totals);
global filters still merge in through cardRunDef.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

### Task 7: Table toggle + row drill-through inside the card

**Files:**
- Modify: `templates/js/_reporting_dashboard_js.html` (`ensureShell` delegated click handler)
- Test: `tests/e2e/test_reporting_dashboard.py` (append)

**Interfaces:**
- Consumes (Task 6): `.rdb-report-table-toggle`, `.rdb-report-table`, `cardRunData[card.id].rows`, `I18N.showTable/hideTable`; existing `handleCardTableRowClick(card, rowIndex)`, `findCardById`.

- [ ] **Step 1 — Failing e2e.** Append. The drill drawer has no endpoint of its own: `ReportingDrill.open` POSTs the drill definition to `**/api/reporting/run` with `rowLimit: 100` (see `test_table_card_row_click_opens_drill_panel` in this file) — the run stub below branches on that:

```python
def test_whole_report_card_table_toggle_and_row_drill(nexora_server, page):
    """Show table toggles the full grid; clicking a data row drills through
    (same handler as the table card), forecast rows are inert."""
    _login(page, nexora_server)
    _stub_gfilter_catalog(page)
    definition = {
        "source": "workitems",
        "metrics": [{"metric": "id_count"}],
        "columns": [{"field": "status"}],
        "filters": [],
        "sort": [],
        "chartType": "bar",
    }
    dash = {
        "kind": "dashboard", "schemaVersion": 1, "title": "e2e whole report drill",
        "globalFilters": [],
        "cards": [{"id": "r1", "type": "report", "span": 12, "title": "By status",
                   "definition": definition, "filterOverrides": []}],
    }
    _stub_dashboard_report(page, "e2e-dash-whole-drill", dash)

    def fulfill_run(route):
        body = route.request.post_data_json or {}
        if body.get("rowLimit") == 100:
            # the drill drawer's own run (raw rows behind the clicked bucket)
            payload = {"columns": [{"field": "status", "header": "Status"}],
                       "rows": [["closed"]], "rowCount": 1, "truncated": False}
        elif not body.get("columns"):
            payload = {"columns": [{"field": "id_count", "header": "Count"}],
                       "rows": [[9]], "rowCount": 1}
        else:
            payload = {"columns": [{"field": "status", "header": "Status"},
                                   {"field": "id_count", "header": "Count"}],
                       "rows": [["open", 4], ["closed", 5]], "rowCount": 2}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("**/api/reporting/run", fulfill_run)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-card").filter(has_text="e2e whole report drill").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    expect(page.locator('[data-testid="rdb-report-chartcard"] canvas')).to_be_visible()

    toggle = page.get_by_test_id("rdb-report-table-toggle")
    table = page.get_by_test_id("rdb-report-table")
    expect(table).to_be_hidden()
    toggle.click()
    expect(table).to_be_visible()
    expect(toggle).to_have_text("Hide table")
    expect(table.locator("tbody tr")).to_have_count(2)
    expect(table.locator("table")).to_have_class(re.compile(r"reporting-drill-clickable"))

    table.locator("tbody tr").nth(1).click()
    expect(page.get_by_test_id("reporting-drill-panel")).to_be_visible()
    expect(page.locator("#rdTitle")).to_have_text("By status")

    toggle.click()
    expect(table).to_be_hidden()
    expect(toggle).to_have_text("Show table")
```

Add `import re` at the top of the file if it is not there yet.

- [ ] **Step 2 — RED:** `…pytest tests/e2e/test_reporting_dashboard.py -k table_toggle_and_row_drill -q` → fails (toggle does nothing).

- [ ] **Step 3 — Delegated handlers.** In `ensureShell`, inside the grid `click` listener, find the comment `// Table-card row drill-through (Task 15): …` and the line `var tableHit = e.target.closest && e.target.closest('.rdb-table-k, .rdb-table-v');`. Insert **before** that comment:

```js
      // Whole-report card: table toggle + row drill. The rows are the Simple
      // pane's own <table>, so a row's index is its position among the
      // non-forecast body rows -- cardRunData holds exactly those rows.
      var rtToggle = e.target.closest && e.target.closest('.rdb-report-table-toggle');
      if (rtToggle) {
        var rtCardEl = rtToggle.closest('[data-card-id]');
        var rtWrap = rtCardEl && rtCardEl.querySelector('.rdb-report-table');
        if (rtWrap) {
          rtWrap.hidden = !rtWrap.hidden;
          rtToggle.textContent = rtWrap.hidden ? I18N.showTable : I18N.hideTable;
        }
        return;
      }
      var rtRow = e.target.closest && e.target.closest('.rdb-report-table tbody tr');
      if (rtRow) {
        if (rtRow.classList.contains('is-forecast') || !rtRow.closest('.reporting-drill-clickable')) return;
        var rtRows = Array.prototype.filter.call(rtRow.parentNode.children, function (tr) {
          return !tr.classList.contains('is-forecast');
        });
        var rtCard = findCardById(rtRow.closest('[data-card-id]').getAttribute('data-card-id'));
        if (rtCard) handleCardTableRowClick(rtCard, rtRows.indexOf(rtRow));
        return;
      }
```

- [ ] **Step 4 — GREEN:** `…pytest tests/e2e/test_reporting_dashboard.py -k "whole_report or report_card" -q` → pass. Restart the STAGING instance, open the dashboard from Task 6 Step 9, toggle the table, click a row → drawer opens; screenshot `var/screenshots/whole-report-03-table-drill.png`, send it.

- [ ] **Step 5 — Commit:**

```bash
git add templates/js/_reporting_dashboard_js.html tests/e2e/test_reporting_dashboard.py
git commit -F - <<'EOF'
feat(reporting): table toggle and row drill on whole-report cards

Show/Hide table flips the card's full grid (same msgids as the Simple
pane), and a click on a data row drills through via the existing
handleCardTableRowClick; forecast rows stay inert.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

### Task 8: "Whole report" pill, loading skeleton, docs + changelog

**Files:**
- Modify: `templates/js/_reporting_dashboard_js.html` (`I18N.pillReport`, `loadingBodyHtml`)
- Modify: `templates/_reporting_help.html`, `docs/howto/reporting-guide.md`, `CHANGELOG.md`
- Test: `tests/e2e/test_reporting_dashboard.py` (one assertion)

- [ ] **Step 1 — Failing e2e.** In `test_report_card_runs_definition_unmodified` add right after `page.get_by_test_id("rs-new-dashboard").click()` / the `rs-dashboard` visibility check:

```python
    expect(page.get_by_test_id("rdb-add-report")).to_have_text("Whole report")
```

- [ ] **Step 2 — RED:** `-k report_card_runs` → fails ("Report").

- [ ] **Step 3 — Pill label.** In the `I18N` map replace `pillReport: {{ _("Report")|tojson }},` with `pillReport: {{ _("Whole report")|tojson }},`.

- [ ] **Step 4 — Loading skeleton.** In `function loadingBodyHtml(type) {` insert before `return '<div class="rdb-skeleton rdb-skeleton--chart"></div>';  // line/bar`:

```js
    if (type === 'report') {
      return '<div class="rdb-skeleton rdb-skeleton--kpi"></div>' +
        '<div class="rdb-skeleton rdb-skeleton--chart"></div>';
    }
```

- [ ] **Step 5 — In-app tips.** In `templates/_reporting_help.html`, in the `<h4>{{ _("Saving and sharing") }}</h4>` list, after the `<li>` that starts with `{{ _("Delete a report you own:` add:

```html
        <li>{{ _("On a dashboard, the “Whole report” tile shows a saved report exactly as the Simple tab does — totals, chart with its colours, axes and forecast, and the table behind “Show table”. The other tiles show one piece each; change colours or the chart type in the report itself.") }}</li>
```

- [ ] **Step 6 — End-user guide.** In `docs/howto/reporting-guide.md`, section `## Dashboards`, change the sentence ending `or **table**.` to end `or **table** — or a **Whole report** tile.` and add this bullet before the closing line `A dashboard saves, shares and deletes exactly like any other report.`:

```markdown
- **Whole report** imports a saved report exactly as the Simple tab shows it:
  the per-measure totals, the KPI band, the chart with its saved colours,
  right axis and forecast, and the full table behind **Show table** (rows drill
  through like everywhere else). Global filters still apply. The tile is
  read-only — change colours, chart type or forecast in the report itself.
```

- [ ] **Step 7 — Changelog.** In `CHANGELOG.md` under `## [Unreleased]` → `### Changed` (the first `### Changed` after `[Unreleased]`) add:

```markdown
- **Dashboard "Whole report" tile.** The Report tile on a reporting dashboard
  now renders the saved report as the Simple tab does — per-measure totals,
  KPI band with prior-period chips, the chart with its saved colours, right
  axis and forecast, and the full table behind *Show table* with row
  drill-through — instead of a single total and one line. It draws through
  the Simple pane's own builders (`window.ReportingSimple`), so the two
  surfaces can no longer drift apart. Existing dashboards upgrade in place.
```

- [ ] **Step 8 — GREEN:** `-k report_card_runs` → pass; `…pytest tests/unit/test_reporting_i18n_lint.py tests/unit/test_no_inline_event_handlers.py tests/unit/test_template_url_prefix.py -q` → pass. (`test_translations.py` is RED until Task 9 — expected.)

- [ ] **Step 9 — Commit:**

```bash
git add templates/js/_reporting_dashboard_js.html templates/_reporting_help.html docs/howto/reporting-guide.md CHANGELOG.md tests/e2e/test_reporting_dashboard.py
git commit -F - <<'EOF'
feat(reporting): name the dashboard tile "Whole report" and document it

The add-card pill reads Whole report, the card gets a KPI+chart loading
skeleton, and the guide, the in-app tips and the changelog describe what
the tile shows and that it is read-only.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

### Task 9: i18n cycle + final gates

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` + `.mo`

- [ ] **Step 1 — Extract + update** (from the worktree root; the venv has pybabel):

```powershell
C:\dev\nexora\.venv\Scripts\pybabel extract -F babel.cfg -o messages.pot .
C:\dev\nexora\.venv\Scripts\pybabel update -i messages.pot -d translations
git diff --stat translations/
```

Only the two new msgids may appear as untranslated; if `git diff translations/` shows an **existing** `msgstr` being changed/emptied, pybabel mangled a malformed line — restore that entry by hand (known trap).

- [ ] **Step 2 — Fill the two msgids** in each `translations/<lang>/LC_MESSAGES/messages.po` (search for `msgid "Whole report"` and the tip's msgid; remove any `#, fuzzy` flag):

| msgid | de | fr | it |
|---|---|---|---|
| `Whole report` | `Ganzer Bericht` | `Rapport complet` | `Report completo` |
| `On a dashboard, the “Whole report” tile shows a saved report exactly as the Simple tab does — totals, chart with its colours, axes and forecast, and the table behind “Show table”. The other tiles show one piece each; change colours or the chart type in the report itself.` | `Auf einem Dashboard zeigt die Kachel „Ganzer Bericht“ einen gespeicherten Bericht genau wie der Tab „Einfach“ — Summen, Diagramm mit seinen Farben, Achsen und Prognose sowie die Tabelle hinter „Tabelle anzeigen“. Die anderen Kacheln zeigen je einen Ausschnitt; Farben oder Diagrammtyp ändern Sie im Bericht selbst.` | `Sur un tableau de bord, la tuile « Rapport complet » affiche un rapport enregistré exactement comme l’onglet Simple — totaux, graphique avec ses couleurs, axes et prévision, et le tableau derrière « Afficher le tableau ». Les autres tuiles montrent un seul élément ; modifiez les couleurs ou le type de graphique dans le rapport lui-même.` | `In una dashboard il riquadro «Report completo» mostra un report salvato esattamente come la scheda Semplice — totali, grafico con i suoi colori, assi e previsione, e la tabella dietro «Mostra tabella». Gli altri riquadri mostrano un solo elemento; colori o tipo di grafico si cambiano nel report stesso.` |

(Check how the existing `.po` files translate "Show table"/"Simple" for de/fr/it and align the quoted words in the tip if they differ.)

- [ ] **Step 3 — Compile:** `C:\dev\nexora\.venv\Scripts\pybabel compile -d translations`

- [ ] **Step 4 — Gates:**

```powershell
C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_translations.py tests/unit/test_reporting_i18n_lint.py tests/unit/test_no_inline_event_handlers.py tests/unit/test_template_url_prefix.py -q
C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py
C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py tests/e2e/test_reporting_dashboard.py tests/e2e/test_reporting_viz.py -q
```

All green. Restart the STAGING instance once more; screenshot the finished card in light **and** dark mode (`document.documentElement.classList.add('dark')` in the console is enough — never persist a theme pref for `ben.streich`) → `var/screenshots/whole-report-04-final-light.png`, `…-05-final-dark.png`; send them. Stop your instance and close the browser.

- [ ] **Step 5 — Commit** (if `mixed-line-ending` rewrites the `.po` files, `git add translations/` and run the commit again):

```bash
git add messages.pot translations/
git commit -F - <<'EOF'
chore(i18n): translate the dashboard Whole-report tile and its tip

pybabel extract/update/compile for the two new reporting msgids
(de/fr/it), no existing msgstr touched.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

## Gotchas & notes

- **Load order / availability:** `templates/_reporting_simple.html` includes `js/_reporting_simple_js.html` *then* `js/_reporting_dashboard_js.html`; `window.ReportingSimple` is assigned at the end of the Simple IIFE, and the dashboard only reads it inside `renderReportCard` (run time). If a card ever renders before the Simple partial ran, `RS` is `undefined` — guard is unnecessary today, don't add one speculatively.
- **`this` inside the Chart.js `onClick`:** Chart.js 4 invokes `options.onClick` with `this` bound to the chart instance (the existing code already relies on it via `this.getElementsAtEventForMode`). `this.data.datasets` is therefore correct in both the Simple canvas and the card canvas — never reintroduce `state.chart` there.
- **`compare: true` doubles the server work** for a whole-report card (a prior-period run). It's what Simple does per result; a dashboard with many whole-report cards gets slow on STAGING (10–30 s per run there). Acceptable for v1 — note it in the PR body.
- **Grand-total clone must drop `forecast` and `compare`** (`delete totalDef.forecast; delete totalDef.compare;`) — the Simple pane does the same; forgetting `compare` wastes a query, forgetting `forecast` returns a forecast block nobody reads.
- **Zero-fill + forecast trim order matters:** fill first (pads to the filter range), then trim back to `forecast.anchor`, then hand *those* rows to KPI band, chart and table — and store them in `cardRunData` so the table-row drill index matches what's drawn.
- **Testid prefixing runs before the stat card is filled** (`statCardHtml` has no testids, so that's fine) and only touches `data-testid^="rs-"`; the card's own `rdb-*` testids are untouched.
- **Audit-fix helpers (`noteDataQuality`, `appendChartNote`, `metricTotalModes`, partial-bucket fade, `xCap`)** landed in `48a08364`; Tasks 2–3 fold them into the pure builders. If the worktree was **not** fast-forwarded (Owner action 1) you won't find them — stop and ask for the fast-forward rather than extracting the stale bodies.
- **Drill drawer plumbing:** `ReportingDrill.open` re-POSTs `/api/reporting/run` with `rowLimit: 100`; there is no separate drill endpoint. Every e2e run stub that can reach a drill must branch on `rowLimit`.
- **Do not rename** `rdb-add-report`, `data-add-type="report"`, `DEFAULT_SPAN.report` — saved dashboards persist `type:'report'`.
- **`.rdb-report:has(...)`** needs `:has()` support (Chromium/Edge ≥105, Firefox ≥121) — same dependency `.rs-result-grid:has(#rsChartCard[hidden])` already takes.
- **Dark mode:** `chartConfigFor` reads `document.documentElement.classList.contains('dark')` at build time; cards re-render on every `render()`, and a theme switch reloads the page's `html.dark` class before paint, so no listener is needed.
- **Peer sessions:** `C:\dev\nexora-c0` (branch `v3.2.3.2`) is another session's worktree — never touch it; run `ListAgents`-style checks if something in your worktree changes under you.
