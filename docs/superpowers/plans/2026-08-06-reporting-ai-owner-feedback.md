# Reporting AI Owner-Testing Feedback (#178) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Single-session planning run (recon → draft → self-red-team); **every file path, symbol, and quoted snippet below was Grep/Read-verified against `v3.1` HEAD (`4856eed`) on 2026-08-06** — trust the anchors, but re-Grep before editing (this plan quotes code, never line numbers). Plan file: `docs/superpowers/plans/2026-08-06-reporting-ai-owner-feedback.md`. GitHub issue: **#178** (label `inprogress` already set).

**Goal:** Close the ten owner-testing gripes from issue #178 across four surfaces: the AI chat agent (visible "building the report" progress, artifact-carrying follow-up context, fewer T-SQL retry loops, AI reports opening in the Simple tab), the Simple pane (hero hidden while a report is open, a granularity chip, wizard granularity + process scoping for table sources), semantics (backlog "Gesamt" = latest snapshot, forecast fitted on real history), and dashboards (a card that takes over a saved report 1:1).

**Architecture:** Every fix is a bolt-on to an existing seam — no new pages, no new permissions. The agent's NDJSON progress stream and the `history` param already exist; the chat partial upgrades its ticker into a live step list and enriches the history it already threads. Backlog totals ride a new `TotalMode` column on `dbo.ReportingMetrics` (migration `0056`) consumed at the one place zero-dim aggregates are built (`build_generic_query`) plus the client KPI band. Forecast lookback reuses the `shifted_definition_for_comparison` pattern (a second `_prepare_run/_execute` on a widened copy of the definition). The wizard's process step for table sources rides one new tiny endpoint (`/api/reporting/field_values`, `SELECT DISTINCT TOP`) serialized into a plain `in` filter. The dashboard gains one new card type `'report'` that runs the adopted definition verbatim.

**Tech Stack:** Flask + pyodbc (existing engines), sqlglot sandbox (untouched), Chart.js 4, Jinja JS partials, pytest unit/integration (`unittest.mock.patch` on `_prepare_run`/`_execute`), Playwright e2e with route stubs, Flask-Babel de/fr/it.

---

## Context an engineer needs (read first)

- **Branch/worktree:** this plan was authored in worktree `.claude/worktrees/plan-reporting-ai-owner-feedback` (branch `plan/reporting-ai-owner-feedback`, cut from `v3.1` @ `4856eed`). Execute there. **Commit per task. Do NOT `git push`, do NOT open a PR** — the owner reviews, merges the worktree branch back into `v3.1`, and pushes.
- **Parallel sessions are normal** on this repo. The main checkout has uncommitted foreign work (`static/css/reporting.css` among others) — never touch the main checkout; all CSS additions in this plan are **appends at the end of the file** to keep the eventual merge trivial.
- **Python for tests:** `C:\dev\nexora\.venv\Scripts\python -m pytest …`. No new runtime deps anywhere in this plan.
- **Anchor on quoted snippets + function names, NEVER line numbers.** Re-`Grep` a snippet if it has moved.
- **TDD is the house rule.** Backend tasks are strict RED→GREEN. Frontend tasks write the failing Playwright e2e first where the behavior is stubbable; pure-presentation steps (CSS, ticker layout) get their assertions folded into the same task's e2e.
- **TEST env has NO Statistics DB** — nothing that queries `StatisticsDB` can execute in e2e. Backend integration tests patch `nx_lib.views.reporting._prepare_run` / `_execute` (copy the pattern of `test_run_compare_true_with_token_filter_returns_comparison` in `tests/integration/test_reporting_routes.py`); e2e stubs `**/api/reporting/run` (see `_stub_run_ok` in `tests/e2e/test_reporting_simple.py`) and must also stub the new `**/api/reporting/field_values`.
- **Before running any e2e tier:** `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py` (stale NEXORA_TEST state fails order-dependent e2e tests).
- **Jinja template cache is process-lifetime** — restart the dev server (`nx -r`) before ANY manual browser check. For UI tasks, verify in the real app (`nx -u -b --no-conflict --loginas:ben.streich`, own port, kill the browser when done) and save screenshots to `var/screenshots/`, sending them to the owner as you go.
- **e2e locale is English** — assert English strings.
- **Migrations needed: YES — one:** `sql/_migrations/NexoraDB/0056_reporting_metrics_total_mode.sql` (Task 8). The pre-commit hook auto-applies it to INT on commit; if INT is unreachable use `SQL_SYNC_SKIP=1 git commit …`, never `--no-verify`. No new permission; no `deploy.yml` change (only `nx_lib/`, `templates/`, `static/`, `sql/`, `tests/`, `translations/`, `docs/` are touched).
- **i18n: ONE late pybabel cycle (Task 16).** New msgids land in Tasks 1–14; `tests/unit/test_translations.py` is expected RED in between — `--deselect tests/unit/test_translations.py` for the fast tier until Task 16. `tests/unit/test_reporting_i18n_lint.py` lints the reporting partials — every new UI string must be `{{ _('…') }}`-wrapped from the start.
- **PROD URL prefix:** the Simple pane's `api()` helper and the chat partial's `API_PREFIX` idiom already normalize; never hand-build a root-relative URL.
- **Visual contract:** never rename a `.reporting-*`/`.rp-*`/`.rdb-*` class; preserve every `data-testid`/`id`; `.nx-rise*` animations use fill-mode `backwards`, never `both`.
- **gitlint:** conventional-commit title ≤72 chars, imperative, no trailing period; non-empty body wrapped ≤100 chars; commit via Bash `git commit -F - <<'EOF' … EOF`. If `ruff-format` rewrites a file the first attempt fails — `git add -u` and recommit.
- **Commit trailer names the EXECUTING model** — the blocks below say `Claude Fable 5`; substitute the real executor if different.

---

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **A1 progress = live step list, same endpoint.** The NDJSON stream (`body.get("stream")` branch of `api_ai_agent`) and `ask_agentic_iter`'s `thinking`/`note`/`tool` events already exist; the chat partial's one-line ticker becomes a "Building your report…" card that appends one row per tool event. No backend change. | The backend was built for exactly this; the gripe is presentation. |
| D2 | **A3 context carry = client-side artifact suffix + bigger server cap.** After each turn the client appends the returned `sql`/`definition` (truncated) to the assistant history entry it already pushes; the server's history char cap rises 4000→12000. Plus one `_AGENT_SYSTEM` sentence: presentation-only follow-ups stay on the prior answer's source/data. | Nothing persists server-side between agent calls — the client-held history is the only carrier. The "Als Diagramm anzeigen" failure happened because the prior answer's SQL never reached the model. |
| D3 | **A2 = prompt discipline + error-hint map, NO server-side compile check.** `validate_select` stays pure. New `humanize_sql_error` hints for SQL Server errors 156 (UNION syntax), 205 (branch column counts), 209 (ambiguous column); new T-SQL discipline sentences in the agent system prompt. | A compile check at validate time saves zero loop turns (validate+run fail in the same feedback round-trip) and would drag engine bindings into a pure module. The agent already self-repairs; the goal is fewer retries and better teaching hints. |
| D4 | **A4 = retarget the chat's "Open in builder" to the Simple result view** via a new `window.ReportingSimple.openDefinition(def, name)` (mirrors `openReport` minus the report id). Advanced stays reachable through the result bar's existing "Open in Advanced". A `chartHint.type` on the definition maps to `def.chartType` before opening. | Saved+reopened AI reports already land in Simple — the classification is fine; only the chat's open path hardcodes `ReportingTabs.show("advanced")`. |
| D5 | **A5 "Live SQL geht nicht" is repro-first (Task 15), not speculatively fixed.** One-sentence gripe, no screenshot; candidate suspects are listed in the task. | Fixing a guess wastes more than a 20-minute browser repro. |
| D6 | **B6 = `setView` hides `#rsHero` outside the library view.** | `setView` already hides `rsLibrary`/`rsNewReport`/`rsNewDashboard`/`rsAiBar`; the hero was simply missed. |
| D7 | **B7 = a "Granularity" chip in the result chips row** for any definition with a date-grained (or grainable) column; editor = the same 5-grain select the wizard uses; apply mutates `col.grain` + `runCurrent()`. | The "Too many data points" dead-end (`noChartTooManyPoints`, >50 buckets) is fixable in-place once grain is a chip like Prozesse/date already are. |
| D8 | **B8 grain = always-visible, gated-enabled.** The wizard's `rsGrainWrap` shows whenever the source has a grainable field; the select is `disabled` (with a tooltip) until a date breakdown is picked. | Owner couldn't find granularity at all; hiding the control entirely is the confusion. |
| D9 | **B8 processes = field-scope step for table sources.** A table source with no `processes` but with a filterable string field matching `/process/i` (backlog_history's `ProcessName`) gets the scope step, backed by new `POST /api/reporting/field_values` (`SELECT DISTINCT TOP (100)`, source-permission-gated, table provider only); picks serialize to a `{field, op:'in', value:[…]}` filter (omitted when all values picked). `wizardStateFromDefinition` learns to map that filter back. | "Prozesse" must not silently skip for the backlog source. A filter is the honest representation — table sources have no scope registry. |
| D10 | **C10 = `TotalMode` on the metric registry, enforced server-side for zero-dim runs + client-side in the KPI band.** Migration `0056` adds `TotalMode NVARCHAR(16) DEFAULT 'sum'` (check `sum|latest`), backfills `backlog_total→latest`. Server: a zero-column aggregate whose metrics are all `latest` over a source with exactly ONE grainable field constrains to `[f] = (SELECT MAX([f]) …same WHERE…)` — this fixes the Simple stat-card clone, wizard "just the total" reports, exports and scheduled totals in one spot. Client: the orange GESAMT band card sums only the latest bucket (label "· latest snapshot"), applied to current AND prior-period rows. | Summing 30-minute snapshots over days is meaningless for a point-in-time series; the owner explicitly asked for "Gesamt zum letzten Zeitpunkt". Registry-driven so future snapshot metrics get it for free; admin CRUD UI intentionally untouched (TotalMode set by migration only, v1). |
| D11 | **C9 = grain-dependent history widening for the forecast fit.** New `widened_definition_for_forecast(rd)` in `tokens.py` (token-filter definitions only, mirroring `shifted_definition_for_comparison`'s ceiling): extends the resolved window's start by {day:56, week:182, month:730, quarter:1460, year:2190} days. `api_run`'s forecast branch runs the widened copy and fits on those rows; any failure falls back to the visible rows (current behavior). The response block shape is unchanged — the visible chart stays the same, predictions get real history (weekday seasonality needs ≥14 daily buckets; a 6-day month never had a chance). | Owner: "Es muss historische Daten haben." |
| D12 | **D11 (dashboard) = new card type `'report'`.** Add-tile pill "Report", span 12, `cardRunDef` leaves the definition **unmodified** (filters, grain, sort intact; global-filter merge still applies), body renders a headline total + the definition's chart (`def.chartType||'line'` via the existing `renderLine`/`renderBar`/`renderDonut`) — the closest 1:1 to the Simple result a card can be. Forecast/caption/drill inside cards stay out (v1). | `adoptReport` already copies the definition verbatim; only the card types forced a lossy presentation. |
| D13 | **Chat "Open in builder" label becomes "Open report"** (msgid change, retranslated in Task 16). | It no longer opens the Advanced builder. |

---

## Owner actions (not for the executor)

1. **Review + merge** `plan/reporting-ai-owner-feedback` into `v3.1`, push, then close #178 with the fix SHA. Note: `static/css/reporting.css` has uncommitted foreign edits in the main checkout — this branch only appends at file end; merge should be clean, but eyeball it.
2. **PROD migration `0056`** rides the normal deploy; no env keys touched (no `env-sync` needed for this plan).
3. **Deliberately deferred** (say the word if wanted): server-side SQL compile check in `validate_sql`; forecast lookback for literal (non-token) date ranges; `TotalMode` in the admin metrics editor UI; latest-mode awareness inside dashboard report cards; forecast/caption/drill inside dashboard cards.

---

# PHASE 1 — Simple pane quick wins

### Task 1: Hide the hero outside the library view (B6)

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (`setView`)
- Test: `tests/e2e/test_reporting_simple.py` (append)

**Interfaces:** none new — `setView(view)` gains one line.

- [ ] **Step 1 — Failing e2e.** Append to `tests/e2e/test_reporting_simple.py` (reuse the module's `_login`; no run stub needed — the wizard view switch is enough):

```python
def test_hero_hidden_outside_library_view(nexora_server, page):
    """#178 B6: the 'Build a report in seconds' hero must vanish when a
    wizard/result is open and come back in the library."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    expect(page.get_by_test_id("rs-hero")).to_be_visible()
    page.get_by_test_id("rs-new-report").click()
    expect(page.get_by_test_id("rs-hero")).to_be_hidden()
    page.get_by_test_id("rs-wizard-backlib").first.click()
    expect(page.get_by_test_id("rs-hero")).to_be_visible()
```

- [ ] **Step 2 — RED:** `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py; C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -k hero_hidden -q`
- [ ] **Step 3 — Implement.** In `setView` (anchor `el('rsLibrary').hidden = view !== 'library';  // #rsSearch nests under it now`), add directly after that line:

```js
    el('rsHero').hidden = view !== 'library';
```

- [ ] **Step 4 — GREEN** (same command), restart `nx -r`, screenshot the result view without hero → `var/screenshots/178-hero-hidden.png`, send it.
- [ ] **Step 5 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
fix(reporting): hide the Simple hero outside the library view

The Build-a-report hero stayed visible above open results and the
wizard, stealing focus from the report (#178). setView now toggles it
with the same rule as the library grid.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 2: Granularity chip in the result chips row (B7)

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (`renderAiChips`, new `grainChipEditor`, I18N map)
- Test: `tests/e2e/test_reporting_simple.py` (append)

**Interfaces:**
- Produces: a `data-testid="rs-chip-grain"` editor with `data-testid="rs-chip-grain-apply"`; applying writes `col.grain` and re-runs. Task 3 and Task 13 do not depend on it, but the chip must keep working for definitions they produce.

- [ ] **Step 1 — Failing e2e.** Append (copy the module's `_stub_run_ok`-style run stub that captures posted bodies — Grep `def _stub_run_ok` and the neighbouring capture idiom in the same file, reuse verbatim; the stubbed rows shape does not matter for this test):

```python
def test_granularity_chip_changes_grain_and_reruns(nexora_server, page):
    """#178 B7: a date-grained definition shows a Granularity chip; picking a
    different grain re-POSTs the definition with the new grain."""
    posted = []
    _stub_run_ok(page, capture=posted)   # exact helper/kwargs: copy from neighbours
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    # Open a grained definition through the exposed test seam (Task 4 adds
    # window.ReportingSimple.openDefinition; if Task 4 is not merged yet,
    # drive the wizard like the neighbouring wizard tests instead).
    page.evaluate("""() => window.ReportingSimple.openDefinition({
      schemaVersion: 1, visualization: 'table', source: 'docprocessing',
      title: 'per month', columns: [{field: 'export_date', grain: 'month'}],
      metrics: [{metric: 'doc_count'}], filters: [], sort: [],
      scope: {clients: [], processes: []}, rowLimit: 5000}, 'per month')""")
    chip = page.get_by_test_id("rs-chip").filter(has_text="Granularity")
    expect(chip).to_be_visible()
    chip.click()
    page.get_by_test_id("rs-chip-grain").locator("select").select_option("week")
    page.get_by_test_id("rs-chip-grain-apply").click()
    expect.poll(lambda: any(
        (b.get("columns") or [{}])[0].get("grain") == "week" for b in posted
    )).to_be(True)
```

> If Task 4 hasn't landed when this runs, replace the `page.evaluate` with the neighbouring wizard click sequence (Grep the wizard e2e in the same file) — the chip logic is identical either way. Execute Task 4 before this one if that is simpler.

- [ ] **Step 2 — RED:** `…pytest tests/e2e/test_reporting_simple.py -k granularity_chip -q`
- [ ] **Step 3 — I18N keys.** In the `var I18N = {` map of `_reporting_simple_js.html` (anchor: `chipApply:`), add:

```js
    granularity: {{ _("Granularity")|tojson }},
    grainDay: {{ _("Day")|tojson }},
    grainWeek: {{ _("Week")|tojson }},
    grainMonth: {{ _("Month")|tojson }},
    grainQuarter: {{ _("Quarter")|tojson }},
    grainYear: {{ _("Year")|tojson }},
```

(All six msgids already exist in `templates/_reporting_simple.html` — no new translations.)

- [ ] **Step 4 — Chip + editor.** In `renderAiChips`, after the process chip append (anchor: `function (chipEl) { processChipEditor(cur, chipEl); },` and its closing `));`), add:

```js
    var grainedCol = (def.columns || []).find(function (c) { return c.grain; });
    if (!grainedCol) {
      grainedCol = (def.columns || []).find(function (c) {
        var m = fieldMetaFor(def, c.field);
        return m && m.grainable;
      }) || null;
    }
    if (grainedCol) {
      var GRAIN_LABELS = { day: I18N.grainDay, week: I18N.grainWeek, month: I18N.grainMonth,
                           quarter: I18N.grainQuarter, year: I18N.grainYear };
      wrap.appendChild(chip(
        I18N.granularity + ': ' + (GRAIN_LABELS[grainedCol.grain] || I18N.grainDay),
        function (chipEl) { grainChipEditor(cur, grainedCol, chipEl); },
        null
      ));
    }
```

Then add beside `processChipEditor`:

```js
  function grainChipEditor(cur, col, chipEl) {
    var box = document.createElement('span');
    box.className = 'rs-chip rs-chip-editor';
    box.setAttribute('data-testid', 'rs-chip-grain');
    var sel = document.createElement('select');
    sel.className = 'reporting-input';
    [['day', I18N.grainDay], ['week', I18N.grainWeek], ['month', I18N.grainMonth],
     ['quarter', I18N.grainQuarter], ['year', I18N.grainYear]].forEach(function (g) {
      var o = document.createElement('option');
      o.value = g[0]; o.textContent = g[1];
      sel.appendChild(o);
    });
    if (col.grain) sel.value = col.grain;
    var ok = document.createElement('button');
    ok.className = 'reporting-btn';
    ok.setAttribute('data-testid', 'rs-chip-grain-apply');
    ok.textContent = I18N.chipApply;
    ok.addEventListener('click', function () {
      col.grain = sel.value;
      runCurrent();
    });
    box.appendChild(sel);
    box.appendChild(ok);
    chipEl.replaceWith(box);
  }
```

- [ ] **Step 5 — GREEN**, restart, screenshot the chip open next to the "Too many data points" note if reproducible (`var/screenshots/178-grain-chip.png`), send.
- [ ] **Step 6 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
feat(reporting): granularity chip on Simple results

Date-grained results get a Granularity chip beside the filter and
process chips; picking day/week/month/quarter/year mutates the date
column's grain and re-runs — the in-place fix for the too-many-data-
points dead end (#178).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 3: Wizard — grain always visible, disabled until a date pick (B8, grain half)

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (`renderBreakdownStep`/`refreshChips`)
- Test: `tests/e2e/test_reporting_simple.py` (append)

- [ ] **Step 1 — Failing e2e.** Drive the wizard like the neighbouring wizard tests (Grep their catalog stubs + click sequence in `tests/e2e/test_reporting_simple.py`, copy verbatim) to the breakdown step, then:

```python
def test_wizard_grain_visible_before_date_pick(nexora_server, page):
    """#178 B8: the Granularity select is visible (disabled) as soon as the
    breakdown step opens for a source with date fields, enabled once a date
    breakdown is picked."""
    # …stubs + clicks to reach the breakdown step: copy from the neighbouring
    # wizard e2e in this file …
    grain_wrap = page.locator("#rsGrainWrap")
    expect(grain_wrap).to_be_visible()
    expect(page.locator("#rsGrain")).to_be_disabled()
    page.locator('[data-bd-kind="date"]').first.click()
    expect(page.locator("#rsGrain")).to_be_enabled()
```

- [ ] **Step 2 — RED:** `…pytest tests/e2e/test_reporting_simple.py -k grain_visible -q`
- [ ] **Step 3 — Implement.** In `renderBreakdownStep`, first line after `var allProcs = w.source.processes || [];`, add:

```js
    var sourceHasDates = (w.source.fields || []).some(function (f) { return f.grainable; });
```

In the nested `refreshChips`, replace the anchor line

```js
      el('rsGrainWrap').hidden = !hasDate;
```

with:

```js
      el('rsGrainWrap').hidden = !sourceHasDates;
      el('rsGrain').disabled = !hasDate;
      el('rsGrainWrap').title = hasDate ? '' : I18N.grainNeedsDate;
```

and add to the I18N map:

```js
    grainNeedsDate: {{ _("Pick a time breakdown first to choose its granularity.")|tojson }},
```

- [ ] **Step 4 — GREEN.** Also rerun the whole file's wizard tests (an older test may assert `rsGrainWrap` hidden — if one does, update its expectation to `disabled`): `…pytest tests/e2e/test_reporting_simple.py -q`
- [ ] **Step 5 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
fix(reporting): wizard granularity select is discoverable

The Granularity select only existed after picking a date breakdown, so
it read as missing (#178). It now shows (disabled, with a hint) whenever
the source has date fields and enables on the first date pick.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 2 — AI chat agent

### Task 4: AI reports open in the Simple tab (A4)

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (new `openDefinition` + `window.ReportingSimple` export)
- Modify: `templates/js/_reporting_ai_js.html` (`wireTurnActions` open handler, `I18N.openBuilder` label)
- Test: `tests/e2e/test_reporting_agent.py` (adjust/append)

**Interfaces:**
- Produces: `window.ReportingSimple.openDefinition(def, name)` — awaits catalogs, sets `state.current = {def, name, reportId: null, owned: true, canEdit: true, fromWizard: false, origin: 'ai'}`, calls `runCurrent()`. Tasks 2 and 15 use it as a test seam.

- [ ] **Step 1 — Failing e2e.** Grep `rp-chat-open-builder` in `tests/e2e/test_reporting_agent.py`. If an existing test asserts the Advanced pane opens, repoint it; otherwise append (copying that file's agent-response stub verbatim — it stubs `**/api/reporting/ai/agent` with a JSON body containing `definition`):

```python
def test_agent_definition_opens_in_simple_result(nexora_server, page):
    """#178 A4: 'Open report' on an agent answer with a definition lands in
    the Simple result view, not the Advanced builder."""
    # …stub the agent endpoint with a definition-bearing answer and stub
    #  **/api/reporting/run (copy this file's existing stubs verbatim)…
    page.get_by_test_id("rp-chat-open-builder").click()
    expect(page.get_by_test_id("rs-result")).to_be_visible()
    expect(page.get_by_test_id("rs-chips")).to_be_visible()
```

- [ ] **Step 2 — RED:** `…pytest tests/e2e/test_reporting_agent.py -k opens_in_simple -q`
- [ ] **Step 3 — Simple side.** In `_reporting_simple_js.html`, directly after `async function openReport(r) { … }` (anchor: its closing `runCurrent();\n  }`), add:

```js
  // #178 A4: open a raw definition (from the AI chat) straight into the
  // Simple result view — openReport minus the saved-report id.
  async function openDefinition(def, name) {
    await loadSourcesCatalog();
    if (!state.metricsBySource) await loadMetricsCatalog();
    state.current = {
      def: def, name: name || def.title || '', reportId: null,
      owned: true, canEdit: true, fromWizard: false, origin: 'ai'
    };
    runCurrent();
  }
```

At the bottom of the partial, directly before the `document.addEventListener('rp:tabshown', …)` block, add:

```js
  window.ReportingSimple = { openDefinition: openDefinition };
```

- [ ] **Step 4 — Chat side.** In `_reporting_ai_js.html`, replace the open handler body (anchor `if (openBtn) openBtn.addEventListener("click", function () {` through its closing `});`):

```js
    if (openBtn) openBtn.addEventListener("click", function () {
      if (!d.definition) return;
      var def = d.definition;
      if (def.chartHint && def.chartHint.type && !def.chartType) def.chartType = def.chartHint.type;
      if (window.ReportingSimple && window.ReportingSimple.openDefinition) {
        if (window.ReportingTabs) window.ReportingTabs.show("simple");
        window.ReportingSimple.openDefinition(def, def.title || I18N.reportTitle);
      } else if (window.Reporting && window.Reporting.applyDefinition) {
        window.Reporting.applyDefinition(def, def.title || I18N.reportTitle, null);
        if (window.ReportingTabs) window.ReportingTabs.show("advanced");
      }
      closePanel();
    });
```

Change the label (anchor `openBuilder: {{ _("Open in builder")|tojson }},`):

```js
    openBuilder: {{ _("Open report")|tojson }},
```

- [ ] **Step 5 — GREEN** (whole agent e2e file), restart, manually ask the chat for a report, click Open report, screenshot Simple result → `var/screenshots/178-ai-opens-simple.png`, send.
- [ ] **Step 6 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html templates/js/_reporting_ai_js.html tests/e2e/test_reporting_agent.py
git commit -F - <<'EOF'
feat(reporting): AI-built reports open in the Simple tab

The chat's open action routed every definition into the Advanced
builder; saved+reopened copies already landed in Simple (#178). New
ReportingSimple.openDefinition() seam opens the definition straight into
the Simple result view (chartHint mapped to chartType); Advanced stays
reachable via the result bar.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 5: Live "building your report" step list (A1)

**Files:**
- Modify: `templates/js/_reporting_ai_js.html` (ticker rework)
- Modify: `static/css/reporting.css` (append at END of file)
- Test: `tests/e2e/test_reporting_agent.py` (append/adjust)

**Interfaces:** the ticker container keeps `data-testid="rp-chat-ticker"`; new inner `data-testid="rp-build-steps"` list.

- [ ] **Step 1 — Failing e2e.** Grep this file for an existing NDJSON-stream stub (search `x-ndjson` in `tests/e2e/test_reporting_agent.py`); if present copy it, else fulfill the agent route with `content_type="application/x-ndjson"` and a body of newline-joined JSON events ending in a `done` line:

```python
def test_agent_stream_renders_build_steps(nexora_server, page):
    """#178 A1: streamed tool events appear as build-step rows while the
    agent works."""
    events = [
        {"phase": "thinking", "turn": 1},
        {"phase": "tool", "name": "build_definition"},
        {"phase": "tool", "name": "validate_sql"},
        {"phase": "tool", "name": "run_sql"},
        {"done": True, "answer": "Done.", "definition": None, "sql": None,
         "toolTrace": [], "turns": 2, "stoppedReason": "final",
         "explainData": False, "continueAttempt": 0, "canContinue": False},
    ]
    body = "\n".join(json.dumps(e) for e in events) + "\n"
    page.route("**/api/reporting/ai/agent", lambda r: r.fulfill(
        status=200, content_type="application/x-ndjson", body=body))
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    # open the chat + send: copy the open/send idiom from this file's tests
    page.get_by_test_id("rp-chat-msg-ai").wait_for()
    # The final bubble replaced the ticker; assert the trace survived so the
    # steps were really rendered live (ticker rows are transient) — the
    # steps list testid is asserted via a route that never sends `done`:
```

> Playwright fulfills the whole body at once, so the transient ticker may
> resolve before an assertion can see it. Add a SECOND test whose stub sends
> the events but **no** `done` line via a streaming response if the harness
> supports it — otherwise assert post-hoc: after `done`, the answer bubble
> exists and no ticker remains (`expect(page.get_by_test_id("rp-chat-ticker")).to_have_count(0)`).
> Keep whichever assertion the harness makes reliable; the row-building logic
> is additionally covered by manual verification in Step 4.

- [ ] **Step 2 — RED**, then **Implement.** In `_reporting_ai_js.html`:

(a) beside `var tickerEl = null; var tickerTextEl = null;` add `var tickerStepsEl = null;`, and add to the label block (anchor `var STEP_START =`):

```js
  var BUILD_TITLE = {{ _("Building your report…")|tojson }};
```

(b) replace `startTicker` and `setTicker` (keep `stopTicker` as-is, but null out `tickerStepsEl` in it too):

```js
  function startTicker() {
    tickerEl = document.createElement("div");
    tickerEl.className = "rp-chat-ticker rp-chat-build";
    tickerEl.setAttribute("role", "status");
    tickerEl.setAttribute("data-testid", "rp-chat-ticker");
    tickerEl.innerHTML = '<div class="rp-build-title"><i></i><i></i><i></i><span></span></div>' +
      '<ol class="rp-build-steps" data-testid="rp-build-steps"></ol>';
    tickerTextEl = tickerEl.querySelector(".rp-build-title span");
    tickerStepsEl = tickerEl.querySelector(".rp-build-steps");
    tickerTextEl.textContent = STEP_START;
    thread.appendChild(tickerEl);
    thread.scrollTop = thread.scrollHeight;
  }

  // A progress event either updates the title (thinking/note) or appends a
  // build-step row (tool). The previous running row flips to done — the
  // stream carries no per-tool completion event, so "the next thing started"
  // is the completion signal.
  function tickerEvent(ev) {
    if (!tickerEl) return;
    if (ev.phase === "tool") {
      tickerTextEl.textContent = BUILD_TITLE;
      var prev = tickerStepsEl.querySelector(".is-running");
      if (prev) { prev.classList.remove("is-running"); prev.classList.add("is-done"); }
      var li = document.createElement("li");
      li.className = "rp-build-step is-running";
      li.textContent = STEP_LABELS[ev.name] || STEP_WORKING;
      tickerStepsEl.appendChild(li);
    } else {
      tickerTextEl.textContent = stepLabel(ev);
    }
    thread.scrollTop = thread.scrollHeight;
  }
```

(c) in `send()`'s NDJSON reader, replace `setTicker(stepLabel(ev));` with `tickerEvent(ev);`.

- [ ] **Step 3 — CSS.** Append at the END of `static/css/reporting.css`:

```css
/* #178 A1 — live build-step list inside the chat ticker */
.rp-chat-build { display: block; }
.rp-chat-build .rp-build-title { display: flex; align-items: center; gap: 4px; }
.rp-build-steps { margin: 6px 0 0; padding: 0 0 0 2px; list-style: none;
  display: flex; flex-direction: column; gap: 3px; }
.rp-build-step { font-size: 12px; color: var(--nx-text-soft, #6b7280);
  display: flex; align-items: center; gap: 6px; }
.rp-build-step::before { content: ""; width: 10px; height: 10px; flex: 0 0 10px;
  border-radius: 50%; border: 2px solid currentColor; opacity: .45; }
.rp-build-step.is-running::before { border-top-color: transparent;
  animation: rp-build-spin .7s linear infinite; opacity: .9; }
.rp-build-step.is-done { opacity: .75; }
.rp-build-step.is-done::before { content: "✓"; border: 0; width: auto; height: auto;
  font-size: 11px; line-height: 1; opacity: 1; color: var(--nx-accent, #4f46e5); }
@keyframes rp-build-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .rp-build-step.is-running::before { animation: none; }
}
```

- [ ] **Step 4 — GREEN + real check.** Run the agent e2e file; then `nx -r`, ask the live chat a slow question, watch the step rows build, screenshot mid-flight → `var/screenshots/178-build-steps.png`, send.
- [ ] **Step 5 — Commit:**

```bash
git add templates/js/_reporting_ai_js.html static/css/reporting.css tests/e2e/test_reporting_agent.py
git commit -F - <<'EOF'
feat(reporting): chat shows a live report-building step list

The one-line ticker becomes a "Building your report…" card that appends
a row per streamed tool event (spinner on the running step, check on
completed ones), so long agent runs read as work, not silence (#178).
Same NDJSON stream, no backend change.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 6: Follow-ups carry the prior answer's artifacts (A3)

**Files:**
- Modify: `templates/js/_reporting_ai_js.html` (history push)
- Modify: `nx_lib/views/reporting.py` (history char cap)
- Modify: `nx_lib/reporting/ai.py` (`_AGENT_SYSTEM` sentence)
- Test: `tests/integration/test_reporting_ai_routes.py` (append/adjust), `tests/unit/test_reporting_ai_agentic.py` (only if a cap constant is asserted there — Grep `4000`)

**Interfaces:** history entries stay `{role, content}` strings — the artifacts ride INSIDE the assistant content, so the server-side validation shape is untouched.

- [ ] **Step 1 — Failing integration test.** Grep `history` in `tests/integration/test_reporting_ai_routes.py` for the existing threading/cap tests and copy their transport/patch idiom, then append:

```python
def test_agent_history_keeps_long_artifact_context(admin_client):
    """#178 A3: an 11KB two-entry history must reach the loop intact (the old
    4000-char cap silently dropped the artifact-bearing assistant turn)."""
    big_sql = "SELECT " + ("x" * 5000)
    history = [
        {"role": "user", "content": "wie viele dokumente diesen monat"},
        {"role": "assistant", "content": "Antwort…\n[sql from this answer]\n" + big_sql},
    ]
    seen = {}
    def fake_step(messages):
        seen["messages"] = messages
        return AssistantTurn(text="ok")
    # patch make_agent_step to return fake_step — copy the neighbouring
    # agent-route test's patching of nx_lib.views.reporting.make_agent_step
    ...
    assert any("[sql from this answer]" in m.get("content", "")
               for m in seen["messages"] if m["role"] == "assistant")
```

- [ ] **Step 2 — RED:** `…pytest tests/integration/test_reporting_ai_routes.py -k artifact_context -q`
- [ ] **Step 3 — Server cap.** In `api_ai_agent` (anchor `while history and sum(len(h["content"]) for h in history) > 4000:`) change `4000` → `12000`. If a test asserts the old cap, update it.
- [ ] **Step 4 — Client history.** In `_reporting_ai_js.html` `send()` success handler, replace the two `chat.history.push(…)` lines (anchor `chat.history.push({ role: "user", content: text });`):

```js
      chat.history.push({ role: "user", content: text });
      // #178 A3: thread the produced artifacts back with the answer so a
      // follow-up ("show it as a chart") keeps the same source and data.
      var mem = res.data.answer || "";
      if (res.data.sql) {
        mem += "\n[sql from this answer]\n" + String(res.data.sql).slice(0, 1500);
      }
      if (res.data.definition) {
        try {
          mem += "\n[report definition from this answer]\n" +
            JSON.stringify(res.data.definition).slice(0, 1200);
        } catch (e) { /* non-serializable definition: skip the suffix */ }
      }
      chat.history.push({ role: "assistant", content: mem });
```

- [ ] **Step 5 — Prompt rule.** In `nx_lib/reporting/ai.py`, append to `_AGENT_SYSTEM` (anchor: the closing of the "Never present a query you did not execute" sentence, `" instructions to run it."` — add a new string literal after it):

```python
    " When a follow-up only changes HOW the previous answer is presented"
    " (as a chart, as a table, a different breakdown of the SAME data), stay"
    " on the same source and data as that answer — reuse the"
    " [sql from this answer] / [report definition from this answer] context"
    " carried in the conversation. Switching to a different source for a"
    " presentation-only follow-up is wrong."
```

- [ ] **Step 6 — GREEN** (integration file + `tests/unit/test_reporting_ai_agentic.py -q`).
- [ ] **Step 7 — Commit:**

```bash
git add templates/js/_reporting_ai_js.html nx_lib/views/reporting.py nx_lib/reporting/ai.py tests/integration/test_reporting_ai_routes.py
git commit -F - <<'EOF'
fix(reporting): agent follow-ups keep the prior answer's artifacts

"Als Diagramm anzeigen" switched sources because the threaded history
carried only prose — the executed SQL/definition never reached the next
loop (#178). The client now appends truncated artifact context to each
assistant history entry, the server history cap rises 4000->12000 chars,
and the system prompt pins presentation-only follow-ups to the prior
answer's source.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 7: Fewer T-SQL retry loops — hints + prompt discipline (A2)

**Files:**
- Modify: `nx_lib/reporting/sandbox.py` (`_SQL_ERROR_HINTS`)
- Modify: `nx_lib/reporting/ai.py` (`_AGENT_EXPLAIN_SUFFIX`)
- Test: `tests/unit/test_reporting_sandbox.py` (append)

- [ ] **Step 1 — Failing unit tests.** Grep `1033` in `tests/unit/test_reporting_sandbox.py` for the existing humanize test shape, copy it, append cases:

```python
def test_humanize_appends_union_order_by_hint():
    msg = ("('42000', \"[42000] [Microsoft][ODBC SQL Server Driver][SQL Server]"
           "Incorrect syntax near the keyword 'UNION'. (156) (SQLExecDirectW)\")")
    out = humanize_sql_error(msg)
    assert "Incorrect syntax near the keyword 'UNION'." in out
    assert "Hint:" in out and "last branch" in out


def test_humanize_appends_ambiguous_column_hint():
    msg = ("('42000', \"[42000] [Microsoft][ODBC SQL Server Driver][SQL Server]"
           "Ambiguous column name 'd'. (209) (SQLExecDirectW)\")")
    out = humanize_sql_error(msg)
    assert "Ambiguous column name 'd'." in out
    assert "Hint:" in out and "alias" in out
```

- [ ] **Step 2 — RED:** `…pytest tests/unit/test_reporting_sandbox.py -k humanize -q`
- [ ] **Step 3 — Hints.** In `sandbox.py`, extend `_SQL_ERROR_HINTS` (anchor `"1033": (`):

```python
    "156": (
        "In a set operation (UNION/EXCEPT/INTERSECT) ORDER BY may only follow "
        "the last branch, and each branch must be a complete SELECT — remove "
        "ORDER BY/extra clauses from inner branches or wrap the whole set "
        "operation in an outer SELECT and order there."
    ),
    "205": (
        "All branches of a set operation must project the same number of "
        "columns in the same order."
    ),
    "209": (
        "The column exists in more than one table/branch — qualify it with "
        "its table or CTE alias (e.g. e.d instead of d) everywhere, "
        "including GROUP BY and ORDER BY."
    ),
```

- [ ] **Step 4 — Prompt.** In `ai.py`, append to `_AGENT_EXPLAIN_SUFFIX` (after the final sentence `" build_definition, and state the coverage either way."`):

```python
    " T-SQL discipline for drafted SQL: alias every table and derived table;"
    " qualify every column that appears in more than one table, CTE or UNION"
    " branch; give every computed column an explicit alias; in a set"
    " operation put ORDER BY only after the LAST branch (never inside inner"
    " branches or a derived table without TOP)."
```

- [ ] **Step 5 — GREEN** (`tests/unit/test_reporting_sandbox.py -q` and `tests/unit/test_reporting_ai_agentic.py -q`).
- [ ] **Step 6 — Commit:**

```bash
git add nx_lib/reporting/sandbox.py nx_lib/reporting/ai.py tests/unit/test_reporting_sandbox.py
git commit -F - <<'EOF'
fix(reporting): teach the agent out of its T-SQL retry loops

Owner testing showed validate_sql passing what run_sql then rejected
(UNION shape, ambiguous aliases), burning turns on self-repair (#178).
humanize_sql_error gains hints for SQL Server errors 156/205/209 and the
agent system prompt gains explicit set-operation and aliasing rules.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 3 — Backlog "Gesamt" = latest snapshot (C10)

### Task 8: Migration 0056 + registry plumbing (`TotalMode`)

**Files:**
- Create: `sql/_migrations/NexoraDB/0056_reporting_metrics_total_mode.sql`
- Modify: `nx_lib/views/reporting.py` (`_load_db_metrics`, `_metrics_for_source`, `api_metrics`)
- Test: `tests/integration/test_reporting_metrics_routes.py` (append/adjust)

**Interfaces:**
- Produces: `_load_db_metrics()` entries gain `"total_mode"`; `_metrics_for_source()` entries gain `"total_mode"`; `/api/reporting/metrics` items gain `"totalMode"`. Tasks 9–10 consume these exact keys.

- [ ] **Step 1 — Migration.** Create `sql/_migrations/NexoraDB/0056_reporting_metrics_total_mode.sql`:

```sql
-- 0056_reporting_metrics_total_mode.sql
-- #178: how a metric's zero-dimension "grand total" is computed.
--   'sum'    = aggregate over all matching rows (default, unchanged)
--   'latest' = aggregate only the rows of the latest date bucket — for
--              point-in-time snapshot series (backlog), where summing
--              snapshots across time is meaningless.
-- Idempotent.
IF COL_LENGTH('dbo.ReportingMetrics', 'TotalMode') IS NULL
BEGIN
    ALTER TABLE dbo.ReportingMetrics
        ADD TotalMode NVARCHAR(16) NOT NULL
            CONSTRAINT DF_ReportingMetrics_TotalMode DEFAULT 'sum'
            CONSTRAINT CK_ReportingMetrics_TotalMode CHECK (TotalMode IN ('sum', 'latest'));
END
GO
UPDATE dbo.ReportingMetrics SET TotalMode = 'latest' WHERE Code = 'backlog_total';
GO
```

- [ ] **Step 2 — Failing integration test.** In `tests/integration/test_reporting_metrics_routes.py`, Grep the existing `/api/reporting/metrics` payload test, copy its client/DB seeding idiom, and assert the new key:

```python
def test_metrics_payload_carries_total_mode(admin_client):
    resp = admin_client.get("/api/reporting/metrics")
    assert resp.status_code == 200
    items = [m for grp in resp.get_json().values() for m in grp]
    assert items and all("totalMode" in m for m in items)
```

- [ ] **Step 3 — RED** (the TEST db gets `0056` applied by `scripts/test_db_reset.py` / the migration runner — if the integration harness migrates on setup, RED comes from the missing payload key, which is the point): `…pytest tests/integration/test_reporting_metrics_routes.py -k total_mode -q`
- [ ] **Step 4 — Plumbing.** In `nx_lib/views/reporting.py`:

(a) `_load_db_metrics` SELECT (anchor `"Aggregation, BaseField, Description, Format, Enabled, SortOrder "`) — add `TotalMode` to the list: `"Aggregation, BaseField, Description, Format, Enabled, SortOrder, TotalMode "`, and to the row dict (anchor `"sort_order": r.SortOrder,`):

```python
                "total_mode": (getattr(r, "TotalMode", None) or "sum"),
```

(b) `_metrics_for_source` (anchor `code: {"aggregation": m["aggregation"], "base_field": m["base_field"]}`):

```python
        code: {
            "aggregation": m["aggregation"],
            "base_field": m["base_field"],
            "total_mode": m.get("total_mode", "sum"),
        }
```

(c) `api_metrics` item dict (anchor `"format": m["format"],`):

```python
                "totalMode": m.get("total_mode", "sum"),
```

- [ ] **Step 5 — Commit** (the pre-commit hook auto-applies 0056 to INT and re-dumps DDL — expect `sql/NexoraDB/...` regenerated files staged by the hook; include them):

```bash
git add sql/_migrations/NexoraDB/0056_reporting_metrics_total_mode.sql nx_lib/views/reporting.py tests/integration/test_reporting_metrics_routes.py
git commit -F - <<'EOF'
feat(reporting): TotalMode on the metrics registry (migration 0056)

Point-in-time metrics (backlog) must not sum snapshots across time for
their grand total (#178). dbo.ReportingMetrics gains TotalMode
('sum'|'latest', default sum; backlog_total backfilled to latest), read
into the registry loaders and exposed as totalMode on
/api/reporting/metrics.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 9: Server — zero-dim totals of `latest` metrics aggregate the latest bucket

**Files:**
- Modify: `nx_lib/reporting/table_query.py` (`build_generic_query` gains `latest_of`)
- Modify: `nx_lib/views/reporting.py` (`_prepare_run` table branch computes `latest_of`)
- Test: `tests/unit/test_reporting_table_query.py` (append)

**Interfaces:**
- Produces: `build_generic_query(rd, base_object, columns, *, row_cap, resolved_metrics=None, latest_of=None)` — when `latest_of` is a field key and `resolved_metrics` is non-empty, the aggregate's FROM body gains `AND|WHERE [f] = (SELECT MAX([f]) FROM <base> <same WHERE>)` with the filter params duplicated for the subquery.

- [ ] **Step 1 — Failing unit tests.** Append to `tests/unit/test_reporting_table_query.py` (copy the module's existing catalog/`rd` fixtures — Grep `build_generic_query(` there for the call shape):

```python
def test_zero_dim_latest_of_constrains_to_max_bucket():
    rd = {"columns": [], "filters": [{"field": "SnapshotAt", "op": "between",
                                      "value": ["2026-08-01", "2026-08-31"]}],
          "sort": []}
    cols = [
        {"field": "SnapshotAt", "type": "datetime", "filterable": True,
         "sortable": True, "grainable": True},
        {"field": "BacklogCount", "type": "number", "filterable": True, "sortable": True},
    ]
    metrics = [{"code": "backlog_total", "aggregation": "sum", "base_field": "BacklogCount"}]
    sql, params = build_generic_query(
        rd, "dbo.BacklogHistory", cols, row_cap=5000,
        resolved_metrics=metrics, latest_of="SnapshotAt")
    assert "[SnapshotAt] = (SELECT MAX([SnapshotAt]) FROM [dbo].[BacklogHistory]" in sql
    # filter params appear twice: outer WHERE + the MAX() subquery's WHERE
    assert params == ["2026-08-01", "2026-08-31", "2026-08-01", "2026-08-31"]


def test_latest_of_ignored_with_dimensions():
    rd = {"columns": [{"field": "SnapshotAt", "grain": "day"}], "filters": [], "sort": []}
    cols = [
        {"field": "SnapshotAt", "type": "datetime", "filterable": True,
         "sortable": True, "grainable": True},
        {"field": "BacklogCount", "type": "number", "filterable": True, "sortable": True},
    ]
    metrics = [{"code": "backlog_total", "aggregation": "sum", "base_field": "BacklogCount"}]
    sql, _ = build_generic_query(
        rd, "dbo.BacklogHistory", cols, row_cap=5000,
        resolved_metrics=metrics, latest_of="SnapshotAt")
    assert "SELECT MAX(" not in sql
```

> Check `_quote_object("dbo.BacklogHistory")`'s exact output first (Grep `def _quote_object` — it splits on `.` and brackets each part) and match the assertion string to it.

- [ ] **Step 2 — RED:** `…pytest tests/unit/test_reporting_table_query.py -k latest -q`
- [ ] **Step 3 — Implement.** In `table_query.py`, change the signature (anchor `def build_generic_query(rd, base_object, columns, *, row_cap, resolved_metrics=None):`) to add `latest_of=None`, and in the metrics branch replace (anchor):

```python
    if resolved_metrics:
        # Zero-dimension grand totals: empty dim_fields is valid here and
        # yields a global aggregate with no GROUP BY.
        where = (" WHERE " + " AND ".join(conds)) if conds else ""
        inner_from = f"{_quote_object(base_object)}{where}"
```

with:

```python
    if resolved_metrics:
        # Zero-dimension grand totals: empty dim_fields is valid here and
        # yields a global aggregate with no GROUP BY.
        where = (" WHERE " + " AND ".join(conds)) if conds else ""
        inner_from = f"{_quote_object(base_object)}{where}"
        # #178: a 'latest' total aggregates only the newest bucket of the
        # snapshot date field — summing point-in-time snapshots across time
        # is meaningless. Caller passes latest_of only for zero-dim runs.
        if latest_of and not dim_fields:
            if latest_of not in by_field:
                raise TableQueryError(f"unknown latest_of field: {latest_of!r}")
            col = _quote_ident(latest_of)
            sub = f"(SELECT MAX({col}) FROM {_quote_object(base_object)}{where})"
            glue = " AND " if conds else " WHERE "
            inner_from = f"{inner_from}{glue}{col} = {sub}"
            params = params + params  # outer WHERE params, then the subquery's
```

- [ ] **Step 4 — Wire `_prepare_run`.** In the `provider == "table"` branch of `_prepare_run` (anchor `sql, params = build_generic_query(`), insert before that call:

```python
        latest_of = None
        if resolved and not (rd.get("columns") or []):
            modes = {
                (source_metrics.get(m["code"]) or {}).get("total_mode", "sum")
                for m in resolved
            }
            date_candidates = [f["field"] for f in catalog if f.get("grainable")]
            if modes == {"latest"} and len(date_candidates) == 1:
                latest_of = date_candidates[0]
```

and pass `latest_of=latest_of` into `build_generic_query`.

- [ ] **Step 5 — GREEN** (`tests/unit/test_reporting_table_query.py -q` + `tests/integration/test_reporting_routes.py -q` — the run route must still pass untouched).
- [ ] **Step 6 — Live check** (real INT data): `nx -r`, open the Simple backlog report, confirm the stat-card "Gesamt" now shows the latest snapshot total, screenshot → `var/screenshots/178-backlog-total-server.png`, send.
- [ ] **Step 7 — Commit:**

```bash
git add nx_lib/reporting/table_query.py nx_lib/views/reporting.py tests/unit/test_reporting_table_query.py
git commit -F - <<'EOF'
feat(reporting): latest-bucket grand totals for snapshot metrics

A zero-dimension aggregate whose metrics are all TotalMode='latest'
(over a table source with exactly one date field) now constrains to the
newest bucket via a MAX() subquery sharing the run's own filters (#178).
Fixes the Simple stat-card clone, wizard just-the-total reports, exports
and scheduled totals in one spot; dimensioned runs are untouched.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 10: Client — GESAMT band card shows the latest snapshot

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (`renderKpiBand` + helper, I18N)
- Test: `tests/e2e/test_reporting_simple.py` (append)

- [ ] **Step 1 — Failing e2e.** Stub `**/api/reporting/metrics` so `backlog_total` carries `totalMode: 'latest'` and stub the run with a two-bucket series (copy the module's metrics/run stub idioms verbatim), open via `window.ReportingSimple.openDefinition` a `backlog_history` definition with `columns: [{field:'SnapshotAt', grain:'day'}]`, `metrics: [{metric:'backlog_total'}]`, rows e.g. `[["2026-08-05", 27122], ["2026-08-06", 9755]]`, then:

```python
    total = page.get_by_test_id("rs-kpi-total")
    expect(total).to_contain_text("9")        # 9,755 — latest bucket only
    expect(total).not_to_contain_text("36")   # never 36,877 (the sum)
```

- [ ] **Step 2 — RED:** `…pytest tests/e2e/test_reporting_simple.py -k latest_snapshot -q`
- [ ] **Step 3 — Implement.** In `_reporting_simple_js.html`:

(a) I18N (anchor `kpiTotal:` — Grep it):

```js
    kpiLatestSuffix: {{ _("latest snapshot")|tojson }},
```

(b) beside `metricAggFor` add:

```js
  function metricTotalModeFor(def) {
    var m = (def.metrics && def.metrics[0]) || null;
    if (!m) return 'sum';
    var list = (state.metricsBySource || {})[def.source] || [];
    var hit = list.find(function (x) { return x.code === m.metric; });
    return (hit && hit.totalMode) || 'sum';
  }

  // #178 C10: for a latest-mode metric the band total is the newest date
  // bucket's sum, not the sum over all buckets. Returns the bucket label it
  // used, or null when not applicable (no date dim / not latest mode).
  function applyLatestTotal(def, kpi, rows) {
    if (!kpi || metricTotalModeFor(def) !== 'latest') return null;
    var cols = def.columns || [];
    var dateIdx = -1;
    for (var i = 0; i < cols.length; i++) {
      var m = fieldMetaFor(def, cols[i].field);
      if (cols[i].grain || (m && m.grainable)) { dateIdx = i; break; }
    }
    if (dateIdx === -1) return null;
    var maxKey = null;
    rows.forEach(function (r) {
      var k = String(r[dateIdx]);
      if (maxKey === null || k > maxKey) maxKey = k;
    });
    if (maxKey === null) return null;
    var t = 0;
    rows.forEach(function (r) {
      if (String(r[dateIdx]) === maxKey) t += Number(r[kpi.idx]) || 0;
    });
    kpi.total = t;
    return maxKey;
  }
```

(c) in `renderKpiBand`, after `var kpi = computeKpiBand(dims, rows);` + null-guard, and after `var priorKpi = priorRows ? computeKpiBand(dims, priorRows) : null;`, add:

```js
    var latestKey = applyLatestTotal(def, kpi, rows);
    if (priorKpi) applyLatestTotal(def, priorKpi, priorRows);
```

and in the total-card HTML (anchor `'<span class="reporting-ledger-caption">' + esc(I18N.kpiTotal) + '</span>'`), change the caption expression to:

```js
        '<span class="reporting-ledger-caption">' + esc(I18N.kpiTotal) +
          (latestKey ? ' · ' + esc(I18N.kpiLatestSuffix) + ' ' + esc(String(latestKey).slice(0, 16)) : '') + '</span>' +
```

- [ ] **Step 4 — GREEN**, then live check against real INT backlog data (band total ≈ the last time bucket, matching screenshot 11's expectation), screenshot → `var/screenshots/178-backlog-total-band.png`, send.
- [ ] **Step 5 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
fix(reporting): KPI band total honours latest-mode metrics

The orange GESAMT card summed every snapshot bucket for backlog reports
(42,897 across three days) instead of the newest bucket's value (#178).
Latest-mode metrics (totalMode from /api/reporting/metrics) now total
the max date bucket for both current and prior-period rows, with a
"latest snapshot" caption suffix.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 4 — Forecast fits on real history (C9)

### Task 11: Grain-dependent lookback for the forecast fit

**Files:**
- Modify: `nx_lib/reporting/tokens.py` (new `widened_definition_for_forecast`)
- Modify: `nx_lib/views/reporting.py` (`api_run` forecast branch)
- Test: `tests/unit/test_reporting_tokens.py`, `tests/integration/test_reporting_routes.py` (append)

**Interfaces:**
- Produces: `widened_definition_for_forecast(rd, today=None)` → widened rd (its single token date filter replaced by a literal `between` reaching `_FORECAST_LOOKBACK_DAYS[grain]` days further back, `compare` key stripped) or `None` (no single-date-dim grain, no/ambiguous token filter, unmapped grain).

- [ ] **Step 1 — Failing unit tests.** Append to `tests/unit/test_reporting_tokens.py` (Grep its imports/`today=` idiom first):

```python
def test_widened_definition_extends_day_grain_window():
    rd = {
        "columns": [{"field": "import_date", "grain": "day"}],
        "metrics": [{"metric": "doc_count"}],
        "filters": [{"field": "import_date", "op": "between",
                     "value": {"token": "this_month"}}],
        "compare": True,
    }
    today = datetime.date(2026, 8, 6)
    out = widened_definition_for_forecast(rd, today=today)
    assert out is not None and "compare" not in out
    f = out["filters"][0]
    assert f["op"] == "between"
    # this_month resolves to [2026-08-01, 2026-08-31]; day lookback = 56 days
    assert f["value"] == ["2026-06-06", "2026-08-31"]
    # original untouched
    assert rd["filters"][0]["value"] == {"token": "this_month"}


def test_widened_definition_requires_single_grained_dim_and_token():
    base = {"columns": [{"field": "import_date", "grain": "day"}],
            "filters": [{"field": "import_date", "op": "between",
                         "value": {"token": "this_month"}}]}
    no_grain = {**base, "columns": [{"field": "import_date"}]}
    assert widened_definition_for_forecast(no_grain) is None
    literal = {**base, "filters": [{"field": "import_date", "op": "between",
                                    "value": ["2026-08-01", "2026-08-31"]}]}
    assert widened_definition_for_forecast(literal) is None
    two_dims = {**base, "columns": base["columns"] + [{"field": "process"}]}
    assert widened_definition_for_forecast(two_dims) is None
```

- [ ] **Step 2 — RED:** `…pytest tests/unit/test_reporting_tokens.py -k widened -q`
- [ ] **Step 3 — Implement.** Append to `tokens.py` after `shifted_definition_for_comparison`:

```python
# #178: how far back the forecast fit may reach beyond the visible window,
# per grain — enough buckets for the seasonal fit (day needs >= 2 weekday
# cycles; see forecast._SEASON_PERIODS) without scanning unbounded history.
_FORECAST_LOOKBACK_DAYS = {"day": 56, "week": 182, "month": 730, "quarter": 1460, "year": 2190}


def widened_definition_for_forecast(rd, today=None):
    """Same definition with its single relative-date window extended
    backwards by a grain-dependent lookback, so the forecast fit sees real
    history (weekend dips need weeks of daily buckets, not six days).

    Applies only to the forecastable shape: exactly one column WITH a grain,
    and exactly one token date filter (mirrors
    shifted_definition_for_comparison's token-only ceiling). Returns the
    widened copy (compare stripped — the caller only fits on it) or None.
    """
    cols = (rd or {}).get("columns") or []
    grain = cols[0].get("grain") if len(cols) == 1 and isinstance(cols[0], dict) else None
    lookback = _FORECAST_LOOKBACK_DAYS.get(grain)
    if lookback is None:
        return None
    filters = rd.get("filters") or []
    token_filters = [
        f
        for f in filters
        if isinstance(f, dict) and isinstance(f.get("value"), dict) and "token" in f["value"]
    ]
    if len(token_filters) != 1:
        return None
    f = token_filters[0]
    start, end = resolve_token(f["value"], today)
    new_filters = [x for x in filters if x is not f]
    new_filters.append(
        {
            "field": f["field"],
            "op": "between",
            "value": [
                (start - datetime.timedelta(days=lookback)).isoformat(),
                end.isoformat(),
            ],
        }
    )
    out = dict(rd)
    out["filters"] = new_filters
    out.pop("compare", None)
    return out
```

- [ ] **Step 4 — Wire `api_run`.** Import it next to `shifted_definition_for_comparison` (Grep the `from ..reporting.tokens import` line), then replace the forecast branch (anchor `payload["forecast"] = compute_forecast(rd, columns, rows)`):

```python
    fc_req = rd.get("forecast")
    if isinstance(fc_req, dict) and fc_req.get("enabled"):
        try:
            fit_columns, fit_rows = columns, rows
            widened = widened_definition_for_forecast(rd)
            if widened is not None:
                # Fit on real history: rerun the widened window purely for the
                # fit. Any failure falls back to the visible rows (#178).
                try:
                    w_columns, w_sql, w_params, w_engine = _prepare_run(widened)
                    fit_columns, fit_rows = w_columns, _execute(w_engine, w_sql, w_params)
                except Exception as e:
                    current_app.logger.warning(
                        f"/api/reporting/run forecast lookback skipped: {e}"
                    )
            payload["forecast"] = compute_forecast(rd, fit_columns, fit_rows)
        except Exception as e:  # a forecast must never take down the run
            current_app.logger.warning(f"/api/reporting/run forecast skipped: {e}")
```

- [ ] **Step 5 — Failing→green integration test.** Append to `tests/integration/test_reporting_routes.py` (copy the `_FC_DEF`/patch idiom already there from the forecast feature — Grep `_FC_DEF`): a def with a `{"token": "this_month"}` filter, `patch("nx_lib.views.reporting._prepare_run")` with `side_effect` for [visible, widened] and `_execute` `side_effect=[visible_rows(6), widened_rows(60)]`; assert `_prepare_run` was called twice and the second call's definition had a literal widened `between`, and the response carries a forecast with `method == "trend_seasonal"` (60 daily buckets with a weekend dip → seasonal kicks in, which the visible 6 rows alone could never produce).
- [ ] **Step 6 — GREEN** (tokens + routes files), then live check on INT: import-documents day-grain report, forecast on, weekend dips now visible in the dashed line; screenshot → `var/screenshots/178-forecast-lookback.png`, send.
- [ ] **Step 7 — Commit:**

```bash
git add nx_lib/reporting/tokens.py nx_lib/views/reporting.py tests/unit/test_reporting_tokens.py tests/integration/test_reporting_routes.py
git commit -F - <<'EOF'
feat(reporting): forecast fits on widened history, not the window

A this-month day-grain report fed the fit six buckets, so weekends were
invisible and the band exploded (#178). The forecast branch now reruns
the definition with its token window extended back by a grain-dependent
lookback (day 56d, week 182d, month 730d, quarter 4y, year 6y) and fits
on that; the visible window and response shape are unchanged, and any
lookback failure falls back to the old fit.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 5 — Wizard process scoping for table sources (B8, processes half)

### Task 12: `POST /api/reporting/field_values` (distinct values, table provider)

**Files:**
- Modify: `nx_lib/reporting/table_query.py` (new `build_distinct_query`)
- Modify: `nx_lib/views/reporting.py` (new `api_field_values` + route registration)
- Test: `tests/unit/test_reporting_table_query.py`, `tests/integration/test_reporting_routes.py` (append)

**Interfaces:**
- Produces: `build_distinct_query(field, base_object, columns, *, cap=100)` → SQL string (no params). Endpoint: `POST /api/reporting/field_values` body `{"source": id, "field": key}` → `{"values": [...]}`; 400 unknown source/field/non-table provider, 403 missing source permission, 503 unconfigured engine. Task 13 consumes it.

- [ ] **Step 1 — Failing unit test:**

```python
def test_build_distinct_query_shape():
    cols = [{"field": "ProcessName", "type": "string", "filterable": True, "sortable": True}]
    sql = build_distinct_query("ProcessName", "dbo.BacklogHistory", cols)
    assert sql == ("SELECT DISTINCT TOP (100) [ProcessName] FROM [dbo].[BacklogHistory] "
                   "WHERE [ProcessName] IS NOT NULL ORDER BY [ProcessName]")


def test_build_distinct_query_rejects_unknown_or_unfilterable():
    cols = [{"field": "ProcessName", "type": "string", "filterable": False}]
    with pytest.raises(TableQueryError):
        build_distinct_query("ProcessName", "dbo.BacklogHistory", cols)
    with pytest.raises(TableQueryError):
        build_distinct_query("Nope", "dbo.BacklogHistory", cols)
```

(Adjust the exact bracket form to `_quote_object`'s real output, as in Task 9.)

- [ ] **Step 2 — RED**, then implement in `table_query.py` (after `_build_conditions`):

```python
def build_distinct_query(field, base_object, columns, *, cap=100):
    """SELECT DISTINCT TOP (cap) values of one whitelisted, filterable
    column — feeds the wizard's field-scope step (#178). No params: field
    and object are identifier-validated/quoted, cap is int-coerced."""
    by_field = {c["field"]: c for c in columns}
    meta = by_field.get(field)
    if meta is None or not meta.get("filterable"):
        raise TableQueryError(f"unknown or unfilterable field: {field!r}")
    col = _quote_ident(field)
    return (
        f"SELECT DISTINCT TOP ({int(cap)}) {col} FROM {_quote_object(base_object)} "
        f"WHERE {col} IS NOT NULL ORDER BY {col}"
    )
```

- [ ] **Step 3 — Failing integration test.** Copy the run-route patch idiom (`admin_client`, `patch("nx_lib.views.reporting._execute")`); POST `{"source": "backlog_history", "field": "ProcessName"}` with `_execute` returning `[["01_EasyTax"], ["03_Invoice_New"]]` → expect `{"values": ["01_EasyTax", "03_Invoice_New"]}`; plus a 400 case for `field: "Nope"`. (If the TEST NexoraDB lacks the `backlog_history` source row/permission, Grep how the existing source-dependent integration tests seed `ReportingSources` and copy that.)
- [ ] **Step 4 — Implement the route.** In `nx_lib/views/reporting.py`, next to `api_metrics`:

```python
@require_permission("reporting.view")
@limiter.limit("30 per minute")
def api_field_values():
    """Distinct values of one whitelisted field of a table source (#178) —
    powers the wizard's process-scope step for sources without a process
    registry. Source-permission-gated; table provider only."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    source = _get_effective_source((body.get("source") or "").strip())
    if (
        source is None
        or source.get("kind") != "curated"
        or (source.get("provider") or "docprocessing") != "table"
    ):
        return jsonify({"error": _("Unknown or unsupported source")}), 400
    if not has_permission(source["permission"]):
        return jsonify({"error": _("Not authorized for this source")}), 403
    engine = _CURATED_ENGINES.get(source.get("engine"))
    if engine is None:
        return jsonify({"error": _("Source engine is not configured")}), 503
    catalog, _fields, _filterable, _sortable = _catalog_for_source(source)
    try:
        sql = build_distinct_query((body.get("field") or "").strip(), source.get("baseObject"), catalog)
        rows = _execute(engine, sql, [])
    except TableQueryError as e:
        return jsonify({"error": _("This request is invalid."), "detail": str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"/api/reporting/field_values exec error: {e}")
        return jsonify({"error": _("Could not load values")}), 500
    return jsonify({"values": [r[0] for r in rows]})
```

> Route registration: Grep how `api_metrics` is registered (`add_url_rule` or blueprint decorator table — follow the same mechanism, path `/api/reporting/field_values`, `methods=["POST"]`). `_catalog_for_source` returns a 4-tuple — confirm its exact unpack shape at the `provider == "table"` branch of `_prepare_run` and mirror it.

- [ ] **Step 5 — GREEN** (unit + integration files), **Step 6 — Commit:**

```bash
git add nx_lib/reporting/table_query.py nx_lib/views/reporting.py tests/unit/test_reporting_table_query.py tests/integration/test_reporting_routes.py
git commit -F - <<'EOF'
feat(reporting): field-values endpoint for table sources

POST /api/reporting/field_values returns the distinct values (TOP 100)
of one whitelisted filterable column of a table source, gated by the
source permission (#178). Feeds the wizard's process-scope step for
sources without a process registry, e.g. backlog_history.ProcessName.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 13: Wizard scope step for process-like fields (B8, processes half)

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (`startWizard` state, `renderScopeStep`, `wizardDefinition`, `wizardStateFromDefinition`, `wizSummaries`)
- Test: `tests/e2e/test_reporting_simple.py` (append)

**Interfaces:** `state.wiz.fieldScope = {field, label, values: [...], picked: [...]}` or `null`.

- [ ] **Step 1 — Failing e2e.** Stub `**/api/reporting/field_values` with `{"values": ["01_EasyTax", "02_Invoice", "03_Invoice_New"]}`, stub metrics/sources so the backlog measure exists (copy the neighbouring wizard stubs), start the wizard, pick the Backlog measure, Continue:

```python
    expect(page.locator("#rsStepScope")).to_be_visible()
    boxes = page.locator("#rsScopeList input[type=checkbox]")
    expect(boxes).to_have_count(3)
    boxes.nth(0).uncheck()
    # …Continue through breakdown/time to Show result with a run stub that
    # captures the POSTed body (copy neighbours)…
    # the definition must carry the in-filter for the two remaining values
    assert any(
        any(f.get("op") == "in" and f.get("field") == "ProcessName"
            and sorted(f.get("value") or []) == ["02_Invoice", "03_Invoice_New"]
            for f in (b.get("filters") or []))
        for b in posted
    )
```

- [ ] **Step 2 — RED:** `…pytest tests/e2e/test_reporting_simple.py -k field_scope -q`
- [ ] **Step 3 — Implement.** In `_reporting_simple_js.html`:

(a) `startWizard` state line (anchor `state.wiz = { measures: [], source: null, breakdowns: [],`): add `fieldScope: null,` to the object.

(b) new helper beside `renderScopeStep`:

```js
  // #178 B8: a table source without a process registry still gets a
  // process step when it carries a filterable string field named like one
  // (backlog_history.ProcessName). Selection serializes to a plain
  // in-filter, not scope.processes.
  function processFieldFor(src) {
    if ((src.processes || []).length) return null;
    return (src.fields || []).find(function (f) {
      return f.type === 'string' && f.filterable &&
        /process/i.test(f.field + ' ' + (f.label || ''));
    }) || null;
  }
```

(c) `renderScopeStep`: replace the skip line (anchor `if (!procs.length) { step.hidden = true; renderBreakdownStep(); return; }`):

```js
    var pf = processFieldFor(w.source);
    if (!procs.length && !pf) { step.hidden = true; renderBreakdownStep(); return; }
    if (!procs.length && pf) { renderFieldScopeStep(step, pf); return; }
```

and add the new renderer after `renderScopeStep`:

```js
  async function renderFieldScopeStep(step, pf) {
    var w = state.wiz;
    step.hidden = false;
    el('rsStepBreakdown').hidden = true;
    el('rsStepTime').hidden = true;
    el('rsWizardRun').hidden = true;
    var box = el('rsScopeList');
    box.innerHTML = '<p class="reporting-simple-hint">' + esc(I18N.loadingValues) + '</p>';
    renderWizardRail();
    var res = await api('/api/reporting/field_values', {
      method: 'POST',
      body: JSON.stringify({ source: w.source.id, field: pf.field })
    });
    if (state.view !== 'wizard' || el('rsStepScope').hidden) return;
    var values = (res.ok && res.data && res.data.values) || [];
    if (!values.length) {  // endpoint down or empty column: skip the step
      w.fieldScope = null;
      step.hidden = true;
      renderBreakdownStep();
      return;
    }
    var prior = (w.fieldScope && w.fieldScope.picked) || [];
    w.fieldScope = { field: pf.field, label: pf.label || pf.field,
                     values: values, picked: prior.length ? prior : values.slice() };
    box.innerHTML = '';
    values.forEach(function (p) {
      var lbl = document.createElement('label');
      var cb = document.createElement('input');
      cb.type = 'checkbox'; cb.value = p;
      cb.checked = w.fieldScope.picked.indexOf(p) !== -1;
      cb.addEventListener('change', function () {
        w.fieldScope.picked = Array.prototype.map.call(
          box.querySelectorAll('input:checked'), function (c) { return c.value; });
      });
      lbl.appendChild(cb);
      lbl.appendChild(document.createTextNode(' ' + p));
      box.appendChild(lbl);
    });
    renderWizardRail();
  }
```

with the I18N addition `loadingValues: {{ _("Loading values…")|tojson }},`.

(d) `wizardDefinition`: after the range-filter push (anchor `filters.push({ field: w.dateField, op: 'between', value: w.range });` and its closing `}`), add:

```js
    if (w.fieldScope && w.fieldScope.picked.length &&
        w.fieldScope.picked.length < w.fieldScope.values.length) {
      filters.push({ field: w.fieldScope.field, op: 'in', value: w.fieldScope.picked.slice() });
    }
```

(e) `wizardStateFromDefinition`: the `if (filters.length > 1) return null;` gate must tolerate exactly one extra `in`-filter on a string field. Replace that gate with:

```js
    var fieldScopeFilter = null;
    var rest = [];
    filters.forEach(function (ft) {
      var meta = (src.fields || []).find(function (x) { return x.field === ft.field; });
      if (!fieldScopeFilter && ft.op === 'in' && meta && meta.type === 'string') {
        fieldScopeFilter = ft;
      } else {
        rest.push(ft);
      }
    });
    filters = rest;
    if (filters.length > 1) return null;
```

and where the returned `wiz` object is assembled (Grep `return { wiz:` / the function's tail — it builds `{measures, source, breakdowns, scopeProcs, range, dateField}`), include:

```js
      fieldScope: fieldScopeFilter
        ? { field: fieldScopeFilter.field, label: fieldScopeFilter.field,
            values: fieldScopeFilter.value.slice(), picked: fieldScopeFilter.value.slice() }
        : null,
```

(f) `wizSummaries` rail line (anchor `var allProcs = (w.source && w.source.processes) || [];`): after the existing `out[1]` block, add:

```js
    if (!allProcs.length && w.fieldScope) {
      var n = w.fieldScope.picked.length, m = w.fieldScope.values.length;
      out[1] = n === m ? I18N.allProcesses
        : I18N.wizScopeCount.replace('{n}', n).replace('{m}', m);
    }
```

- [ ] **Step 4 — GREEN** (whole `test_reporting_simple.py`), live check on INT with the real backlog source (values come from StatisticsDB), screenshot the scope step → `var/screenshots/178-wizard-process-scope.png`, send.
- [ ] **Step 5 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
feat(reporting): wizard process step for table sources

The backlog source skipped the Prozesse step because table sources have
no process registry (#178). Sources with a filterable process-like
string field now get the step backed by /api/reporting/field_values;
the selection serializes to a plain in-filter (editable later as a
chip), and Adjust-in-wizard maps it back.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 6 — Dashboard "report" card (D11)

### Task 14: Card type `report` renders the adopted definition 1:1

**Files:**
- Modify: `templates/js/_reporting_dashboard_js.html` (`DEFAULT_SPAN`, `addTileHtml`, `renderCardContent`, new `renderReportCard`, `loadingBodyHtml`)
- Modify: `static/css/reporting.css` (append at END)
- Test: `tests/e2e/test_reporting_dashboard.py` (append)

**Interfaces:** card shape unchanged (`{id, type: 'report', span, title, definition, filterOverrides}`); `cardRunDef` already leaves non-KPI definitions untouched, so the run POSTs the adopted definition verbatim (plus merged global filters).

- [ ] **Step 1 — Failing e2e.** Copy the dashboard e2e's builder-open + run-stub idiom (Grep `rdb-add-tile` / `openNew` usage in `tests/e2e/test_reporting_dashboard.py`):

```python
def test_report_card_runs_definition_unmodified(nexora_server, page):
    """#178 D11: a report card POSTs the adopted definition as-is (grain,
    filters, sort intact) and renders total + chart."""
    posted = []
    # …run stub capturing bodies; reports-list + report-GET stubs so the
    #  picker offers one saved grained report (copy neighbours)…
    # add a report card, adopt the saved report
    page.get_by_test_id("rdb-add-report").click()
    page.get_by_test_id("rdb-card-configure").click()
    page.get_by_test_id("rdb-report-pick").first.click()
    body = page.get_by_test_id("rdb-report-total")
    expect(body).to_be_visible()
    grained = [b for b in posted
               if (b.get("columns") or [{}])[0].get("grain") == "month"]
    assert grained, "definition lost its grain on the way to /run"
```

- [ ] **Step 2 — RED:** `…pytest tests/e2e/test_reporting_dashboard.py -k report_card -q`
- [ ] **Step 3 — Implement.** In `_reporting_dashboard_js.html`:

(a) Grep `DEFAULT_SPAN` — add `report: 12` to the map.

(b) `addTileHtml` pills (anchor `data-testid="rdb-add-donut" data-add-type="donut"` line) — add after it:

```js
        '<button type="button" class="rdb-add-pill" data-testid="rdb-add-report" data-add-type="report">' +
          '<i class="fas fa-window-maximize" aria-hidden="true"></i>' + esc(I18N.pillReport) + '</button>' +
```

with I18N addition `pillReport: {{ _("Report")|tojson }},` (anchor `pillDonut:` — Grep the exact key names used there and match).

(c) `renderCardContent` (anchor `if (card.type === 'table') return renderTable(card, body, columns, rows);`) — add before the fallback:

```js
    if (card.type === 'report') return renderReportCard(card, body, columns, rows);
```

(d) new renderer beside `renderTable`:

```js
  // #178 D11: the closest 1:1 of the Simple result a card can be — headline
  // total over the grouped rows + the definition's own chart type, with the
  // definition (grain, filters, sort) POSTed verbatim by cardRunDef.
  function renderReportCard(card, body, columns, rows) {
    destroyCardChart(card.id);
    var idx = dimValIdx(columns);
    var total = rows.reduce(function (a, r) { return a + (toNum(r[idx.val]) || 0); }, 0);
    var head = '<div class="rdb-report-total" data-testid="rdb-report-total">' +
      '<span class="rdb-report-total-value">' + esc(fmtNum(total)) + '</span>' +
      '<span class="rdb-report-total-label">' + esc(I18N.total) + '</span></div>';
    var chartHost = document.createElement('div');
    body.innerHTML = head;
    body.appendChild(chartHost);
    chartHost.className = 'rdb-report-chart';
    var t = (card.definition && card.definition.chartType) || 'line';
    if (t === 'pie' || t === 'doughnut') return renderDonut(card, chartHost, columns, rows);
    if (t === 'bar' || t === 'stacked') return renderBar(card, chartHost, columns, rows);
    return renderLine(card, chartHost, columns, rows);
  }
```

> `renderLine`/`renderBar`/`renderDonut` write `body.innerHTML` themselves — passing `chartHost` (a child div) keeps the total strip alive. Verify each of the three sets `innerHTML` on the passed element only (Grep their bodies) — they do (`body.innerHTML = …` + `body.querySelector('canvas')`).

(e) `loadingBodyHtml`: the default chart skeleton already covers `'report'` — no change (verify the `return` fallback comment).

- [ ] **Step 4 — CSS.** Append at END of `static/css/reporting.css`:

```css
/* #178 D11 — dashboard report card */
.rdb-report-total { display: flex; align-items: baseline; gap: 8px; margin: 2px 0 8px; }
.rdb-report-total-value { font-size: 24px; font-weight: 700; }
.rdb-report-total-label { font-size: 11.5px; color: var(--nx-text-soft, #6b7280);
  text-transform: uppercase; letter-spacing: .04em; }
.rdb-report-chart { min-height: 180px; position: relative; }
```

- [ ] **Step 5 — GREEN** (whole dashboard e2e file), live check: build a dashboard, add a Report card from the saved backlog report, confirm filters/grain arrive intact; screenshot → `var/screenshots/178-dashboard-report-card.png`, send.
- [ ] **Step 6 — Commit:**

```bash
git add templates/js/_reporting_dashboard_js.html static/css/reporting.css tests/e2e/test_reporting_dashboard.py
git commit -F - <<'EOF'
feat(reporting): dashboard report card adopts a saved report 1:1

New card type 'report' (span 12): the adopted definition is POSTed
verbatim — grain, filters and sort intact — and rendered as a headline
total plus the definition's own chart type, instead of being squeezed
into a kpi/line/table shape (#178).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 7 — "Live SQL geht nicht" (A5, repro-first)

### Task 15: Reproduce, diagnose, fix the smallest real bug

The gripe is one sentence with no screenshot. Suspects, in likelihood order:

1. **Simple result "Show query"** (`rsShowSql` in the ⋯ menu / `rsSqlPeek`) on an AI-opened definition — `state.current.sql` comes from the run payload; check it renders.
2. **Advanced "SQL anzeigen"** on an AI-adopted definition (the owner was in Advanced when noting it).
3. **The SQL sandbox pane** (`Live SQL — read-only` ack modal in `templates/reporting.html`, `api_sql_run`) — a 409 `needAck` loop or a 503 unconfigured-target on the owner's box.

- [ ] **Step 1 — Reproduce.** `nx -r`, then `nx -u -b --no-conflict --loginas:ben.streich`; recreate the owner's exact flow: ask the chat for "importierte Dokumente diesen Monat", open the report, try every SQL affordance above in both tabs; also open the Advanced SQL editor and run a trivial `SELECT TOP (5) …` against the statistics target. Capture the failing network call (status + body) and console errors.
- [ ] **Step 2 — Fix the smallest real bug** found, with a regression test in the matching layer (e2e for a UI wiring bug, integration for a route bug). If NOTHING reproduces, write the findings (what was tried, what worked) into a draft comment for issue #178 at `var/screenshots/178-live-sql-findings.md` and skip the fix — do not invent one.
- [ ] **Step 3 — Screenshot** the working (or still-broken-with-evidence) state → `var/screenshots/178-live-sql.png`, send.
- [ ] **Step 4 — Commit** (adapt the message to the actual fix; if nothing reproduced, commit only the findings note **outside** `var/` — put it in the issue comment instead and commit nothing).

---

# PHASE 8 — Chores

### Task 16: i18n cycle, changelog, docs, full verification

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`)
- Modify: `CHANGELOG.md` (`[Unreleased]`)
- Modify: `docs/howto/reporting.md`, `docs/design/reporting-ai-assistant.md`

- [ ] **Step 1 — pybabel cycle** (from repo root of the worktree):

```
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
# translate every new msgid in de/fr/it (Grep for ", fuzzy" and empty msgstr) — new strings:
#   "Open report", "Building your report…", "latest snapshot",
#   "Pick a time breakdown first to choose its granularity.", "Loading values…",
#   "Report" (dashboard pill), plus any task-added strings
pybabel compile -d translations
```

**pybabel trap:** `pybabel update` silently mangles malformed msgstr lines — diff-sweep the three `.po` files for unrelated content changes before committing (known past incident: dropped "T" from "T-SQL").

- [ ] **Step 2 — Changelog.** Under `[Unreleased]` in `CHANGELOG.md`:

```markdown
### Added
- Reporting: live "building your report" step list in the AI chat while the agent works (#178).
- Reporting: granularity chip on Simple results; wizard granularity always discoverable (#178).
- Reporting: wizard process step for table sources via new `POST /api/reporting/field_values` (#178).
- Reporting: `TotalMode` on the metrics registry (migration 0056) — snapshot metrics (backlog) total the latest bucket instead of summing snapshots (#178).
- Reporting: dashboard card type "Report" that adopts a saved report 1:1 (#178).

### Changed
- Reporting: AI-built reports open directly in the Simple tab; chat follow-ups carry the prior answer's SQL/definition context (#178).
- Reporting: forecasts fit on a widened history window (grain-dependent lookback), so day-grain forecasts learn weekday seasonality (#178).

### Fixed
- Reporting: the Simple hero no longer overlays open reports (#178).
- Reporting: clearer self-repair hints for AI SQL errors 156/205/209 (#178).
```

- [ ] **Step 3 — Docs.** In `docs/howto/reporting.md`: document the granularity chip, the wizard field-scope step + `field_values` endpoint, `TotalMode`, and the dashboard report card. In `docs/design/reporting-ai-assistant.md`: document the artifact-carrying history (`[sql from this answer]` convention, 12000-char cap) and the build-step ticker. Fix any drifted references you touch.
- [ ] **Step 4 — Full verification:**

```
C:\dev\nexora\.venv\Scripts\python -m ruff check . ; C:\dev\nexora\.venv\Scripts\python -m ruff format --check .
C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit tests/integration -q
C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py
C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e -q -k "reporting"
```

All green (translations test included now).

- [ ] **Step 5 — Commit:**

```bash
git add messages.pot translations CHANGELOG.md docs/howto/reporting.md docs/design/reporting-ai-assistant.md
git commit -F - <<'EOF'
docs(reporting): i18n, changelog and docs for the #178 batch

de/fr/it translations for the new reporting strings, changelog entries
under Unreleased, and reporting/AI-assistant doc updates (granularity
chip, field-values endpoint, TotalMode, report card, artifact-carrying
chat history).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

## Gotchas & notes

- **Execute in the worktree** `.claude/worktrees/plan-reporting-ai-owner-feedback`. The `nx` CLI serves the MAIN checkout (`C:\dev\nexora`), which has foreign uncommitted work — never touch it. For the mid-task live checks, run Flask directly from the worktree instead: `$env:ENVIRONMENT='INT'; C:\dev\nexora\.venv\Scripts\python nx_main.py` from the worktree root (pick a free port via `NEXORA_E2E_PORT`/Flask args if 5000 is taken), and drive it with your own Playwright browser. The e2e suite starts its own server from whatever working copy you invoke pytest in — invoke it from the worktree.
- **`static/css/reporting.css` is edited (uncommitted) in the main checkout by another session.** All CSS in this plan appends at file END in the worktree copy; the merge back into `v3.1` should auto-resolve. Never open the main checkout's copy.
- **Anthropic prompt strings in `ai.py` are English by design** (model-facing) — never gettext them (`humanize_sql_error` docstring says the same for hints).
- **`tools/reporting_ai_eval/prompts.json`** is being tuned in a parallel session (modified in the main checkout) — this plan deliberately does not touch the eval tool.
- **Task ordering:** Task 4 before Task 2 makes the e2e seam (`openDefinition`) available; otherwise Task 2 falls back to wizard-driving. Tasks 8→9→10 are strictly ordered. Task 12 before 13. Everything else is independent.
- **Migration 0056 + pre-commit:** the hook applies it to INT during the Task 8 commit and re-dumps per-object DDL — `git add` the regenerated `sql/NexoraDB/**` files the hook touches into the same commit. Offline: `SQL_SYNC_SKIP=1`.
- **Worktrees have no `env/*.env`** (gitignored, main checkout only) — the SQL pre-commit hooks fail with "Missing DB_SERVER_PRD / DB_UID / DB_PWD in env". Before Task 8's commit, copy the real file in once: `Copy-Item C:\dev\nexora\env\INT.env .\env\INT.env` (it stays gitignored). For docs/JS-only commits, `SQL_SYNC_SKIP=1` is fine. Same story for live checks: the worktree Flask server needs that copied `env/INT.env`.
- **The forecast lookback multiplies query cost** for forecast-enabled runs (one extra aggregate over ≤2 years). Acceptable: forecast is opt-in per definition. If INT feels slow, the lookback map is the single knob.
- **`_reporting_anim_js.html` exists** (result-row entrance animation) — Task 5's build steps are chat-side only; don't confuse the two.
- **`processChipEditor` only handles registry processes** — after Task 13, a field-scope pick shows up as a normal filter chip (editable via `filterChipEditor`), which is intended.
- **wizardStateFromDefinition round-trip:** Task 13(e) keeps `values` = the filter's own values when reopening a saved def (the full TOP-100 list isn't known then); `renderFieldScopeStep` re-fetches and unions `picked` into the fresh list — verify `prior.length ? prior : values.slice()` picks up the mapped picks.
- **e2e stubs must cover `**/api/reporting/field_values`** in any test that walks the wizard past the measure step for a table source, or the step will fall through (empty values → skip) — which is also the graceful-degrade behavior in production when StatisticsDB is down.
- **After every template/partial edit: `nx -r`** before browser verification — Jinja caches for the process lifetime.
- **Remote-session rule:** screenshots of every visible change go to the owner via SendUserFile as the tasks complete, from `var/screenshots/` (gitignored — never commit them).
