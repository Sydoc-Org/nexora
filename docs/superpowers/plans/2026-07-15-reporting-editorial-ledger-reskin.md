# Reporting "Editorial Ledger" Reskin — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Executor model: Sonnet (substitute the real executing model in commit trailers). Single-session planning run; **every file path, symbol, and quoted snippet was Grep-verified against the worktree at `plan/reporting-editorial-ledger-reskin` (based on feature/2.5.64 `00c7525`) on 2026-07-15** — trust the anchors, re-Grep before editing since line numbers drift (this plan quotes code, never line numbers).

**Spec:** `docs/superpowers/specs/2026-07-15-reporting-editorial-ledger-design.md` (owner-approved, binding — its "Locked identity" and "Hard constraints" sections govern every task below).

**Goal:** The Reporting page gets its own data-workspace identity — **"Editorial Ledger" on a cool neutral canvas**: serif masthead + white masthead band on `#fcfcfc`, hairline dividers instead of card chrome, a 2px ink rule over the chart block, all-mono data typography, ink-navy `#312e81` single-series charts with a `#4f46e5` peak accent, and three new elements: a client-computed **KPI stat band**, a **timing badge** ("N rows · M ms"), and a **persistent query footer** peeking the existing `sqlDisplay`.

**Architecture:** Pure front-end. All new CSS **appended** to `static/css/reporting.css` (unlayered, append-wins) under a `.reporting-ledger-*` namespace plus local custom properties (`--rl-*`) with `html.dark` overrides; `static/css/nexora-ui.css` untouched. Template edits are additive (new elements, new classes on existing tags) — **no `id`/`name`/`data-testid`/`.reporting-*` class is renamed or removed**. The three new elements are wired per-pane in the two JS partials (house per-pane duplication, same as the `OP_LABELS` precedent), reusing the run responses both panes already hold (`rows`, `sqlDisplay`); no backend change of any kind.

**Tech Stack:** Jinja2 templates + JS partials (`templates/js/_reporting_*.html`), `static/css/reporting.css`, Chart.js via `templates/js/_reporting_viz_js.html` (Advanced) and the inline chart build in `templates/js/_reporting_simple_js.html` (Simple), pytest + Playwright e2e (network-stub pattern), pybabel de/fr/it.

---

## Context an engineer needs (read first)

- **Where you work:** the worktree `C:\dev\nexora\.claude\worktrees\plan-reporting-editorial-ledger-reskin` on branch `plan/reporting-editorial-ledger-reskin` (already created, based on `feature/2.5.64` @ `00c7525`). Commit per task. **Do NOT `git push`, do NOT open a PR** — owner reviews and pushes (pre-push gate runs the full suite incl. e2e).
- **Python for tests:** the worktree has no `.venv`. Run everything with `C:\dev\nexora\.venv\Scripts\python -m pytest …` from the worktree root.
- **FIRST-COMMIT BLOCKER:** worktree `env/` has only `*.env.example`. Before the first commit: `Copy-Item C:\dev\nexora\env\INT.env env\INT.env` and `Copy-Item C:\dev\nexora\env\TEST.env env\TEST.env` (gitignored). If INT is unreachable, `$env:SQL_SYNC_SKIP="1"` for that commit — **never** `--no-verify`. Expect the recurring `sql/` drift from parallel sessions: `git restore sql/` first, then `SQL_SYNC_SKIP=1` if it recurs; never commit `sql/` files from this plan.
- **Anchor on quoted snippets + function names, NEVER line numbers.** Re-Grep every anchor before editing.
- **Reporting-metrics plan merged in (2026-07-15, before Task 1 started):** the parallel "page_count metric + process-coverage marking" plan shipped and was merged into `feature/2.5.64`, then merged into this branch (see the `chore(reporting): merge reporting-metrics into ledger-reskin branch` commit). It touched `templates/js/_reporting_metrics_js.html`, `templates/reporting_metrics.html` (admin pages, out of scope for this plan either way) plus `templates/js/_reporting_simple_js.html` — it added the `.reporting-simple-chip-cov` "n/m" coverage badge (`renderMeasureStep()`/`renderBreakdownStep()`) and the `page_count` metric. Task 7 now includes restyling that badge; Task 5's KPI band needs no special-case (metric-agnostic — `page_count` just works as another numeric column). The dormant 2026-06-12 AI-clarifications plan touches the same JS partials; it is NOT executed — do not assume its chips exist.
- **The visual contract (binding, from the spec):** never rename a `.reporting-*` class; preserve every `id`/`name`/`data-testid` (11 e2e files select by them); `.reporting-admin*` rules shared with admin pages — don't touch; append to `static/css/reporting.css` in place (no new stylesheet — a new one would need a deploy.yml exclude); don't edit `static/css/nexora-ui.css`; `.nx-rise*` fill-mode stays `backwards`; pie slice borders stay `#fff` (PNG export); light `.sql-*` token colors stay byte-identical.
- **i18n:** every new user-facing string via gettext — page markup `{{ _("…") }}`; JS-visible strings through each file's existing convention (`I18N` object with `|tojson` in Simple; flat `var I18N_* = {{ _("…")|tojson }};` in Advanced). `tests/unit/test_reporting_i18n_lint.py` fails hardcoded ≥2-word English in reporting templates — it is the tripwire, not a formality. `tests/unit/test_translations.py` is expected RED between the first new msgid and Task 10's single late pybabel cycle; use `--deselect tests/unit/test_translations.py` for the fast tier in between.
- **e2e:** TEST env has no Statistics DB — use the established stubs in `tests/e2e/test_reporting_simple.py`: `_stub_catalogs(page)`, `_stub_run_ok(page, capture=…)`, routes registered **before** `page.goto`. e2e locale is English (assert msgids). Before any e2e tier: `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py`.
- **Jinja template cache is process-lifetime** — restart the dev server before ANY manual browser check.
- **Migrations needed: NO. Permissions: none new. deploy.yml: no change** (only already-deployed dirs touched). No new dependencies, no font assets (system serif stack).
- **gitlint:** conventional-commit title ≤72 chars, imperative, no trailing period; allowed types `feat,fix,chore,refactor,docs,test,ci,perf,style,build,revert`; non-empty body wrapped ≤100 chars. Commit via `git commit -F - <<'EOF' … EOF`. If ruff-format rewrites a file on first attempt: `git add -u`, recommit.
- **Remote-session rules:** screenshots to `var/screenshots/`, `SendUserFile` them proactively; stop at `git commit`.

---

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| L1 (owner) | Editorial Ledger identity on cool neutral canvas — B layout + C background from the visual brainstorm. | Locked in spec via 3 mockup rounds. |
| L2 (owner) | All three new elements in scope: KPI band, timing badge, query footer. | Owner multi-selected all three. |
| L3 (owner) | Dark mode = minimal adaptation: `html.dark` overrides for new/changed elements only; no designed ink edition. | Owner choice. |
| L4 (owner) | Serif = system stack (`Georgia, 'Charter', 'Times New Roman', serif`), masthead + section titles only. | Zero assets, zero CSP change. |
| L5 | Canvas scoping via one additive class on the reporting page `<body>` (`class="nx-app reporting-ledger"`); every new CSS rule keys off `.reporting-ledger` or `.reporting-ledger-*`. | Scopes the deviation to this page without touching nexora-ui.css or other pages; body-class is the cheapest correct scope. |
| L6 | New CSS uses local custom props `--rl-canvas:#fcfcfc; --rl-band:#fff; --rl-hairline:#e4e4e7; --rl-ink:#18181b; --rl-navy:#312e81` declared on `body.reporting-ledger`, redefined under `html.dark body.reporting-ledger`. Existing `--nx-*` tokens used where they already fit (e.g. `--nx-text-meta`). | One place to tune both modes (L3); append-wins layer stays readable. |
| L7 | KPI band computes client-side from the current result only: total of the **first numeric column after the dimension columns**, bucket count = `rows.length`, avg = total/buckets. **No vs-prior delta** (needs a second query — deferred, spec "Deferred"). Band hidden for zero-row results and for results with no numeric column. | Spec v1 scope; no backend work. |
| L8 | Timing badge: elapsed measured client-side around the existing `api('/api/reporting/run', …)` calls (`performance.now()` bracket), rows from the response; rendered into one always-present masthead element `#reportingTiming` shared by both panes, `hidden` until the first successful run, updated on every run. | The run response has no server elapsed field; client-measured is honest ("round trip") and needs no API change. One element because the masthead is shared chrome. |
| L9 | Query footer = one always-rendered element per pane (`#rsSqlPeek`, `#rpSqlPeek`) under the results area showing the first line of `sqlDisplay`, `hidden` when absent; click triggers the existing show-query toggle handlers (same code path as `rsShowSql`/`rpShowSql`). Falls back to hidden when `sqlDisplay` is null (inliner degrade path). | Reuses yesterday's WS1 plumbing (`state.current.sqlDisplay` / `state._lastSqlDisplay`) — no new SQL machinery. |
| L10 | Chart identity change applies to **single-series bar/line only**, in both chart paths (`mountChart` in `_reporting_viz_js.html`, and the Simple chart build around `state.chart = new Chart(el('rsChartCanvas'), …)`): bars `#312e81` with the max-value bar `#4f46e5`; line border `#312e81`, fill `rgba(49,46,129,.12)`. Multi-series/pie/doughnut/stacked untouched. | Spec. Peak accent = map over data to find max index. |
| L11 | Numeric table cells get a `reporting-ledger-num` class added at render time (both panes' table HTML builders already know which cells they ran through `fmtNumber`); CSS right-aligns + mono + tabular-nums. | Cheaper and more precise than CSS `:has()` heuristics. |
| L12 | Per-pane duplication of the tiny KPI/timing helpers (house pattern, like `OP_LABELS`); the shared `ReportingSqlFormat` seam is NOT extended — nothing here is format logic. | Two small IIFEs, no new global seam to e2e-pin. |
| L13 | The Beta badge stays (its removal is a still-open owner action from the 2026-07-14 plan, not this plan's call). | Don't fold unrelated owner decisions into a reskin. |

---

# PHASE 1 — Canvas & typography (CSS + masthead)

### Task 1: Ledger canvas, masthead band, serif title

**Files:** Modify `templates/reporting.html`, append to `static/css/reporting.css`.

- [ ] Re-Grep the body tag in `templates/reporting.html`: `<body class="nx-app">` → change to `<body class="nx-app reporting-ledger">` (this page only; verify no other template contains `reporting-ledger`).
- [ ] Append a new final section to `static/css/reporting.css` headed `/* ============ Editorial Ledger (2026-07-15 reskin) ============ */`: declare the `--rl-*` props on `body.reporting-ledger` and the `html.dark body.reporting-ledger` overrides (L6; dark values: pick from existing `html.dark` values in this file so nothing reads broken — L3).
- [ ] Canvas + masthead rules: `body.reporting-ledger { background: var(--rl-canvas); }`; `.reporting-ledger .reporting-page-head` gets `background: var(--rl-band); border-bottom: 1px solid var(--rl-hairline);` (anchor: existing rule `.reporting-page-head { padding: 20px 24px 0; margin-bottom: 0; }` — append, don't edit); serif title `.reporting-ledger .nx-title { font-family: Georgia, 'Charter', 'Times New Roman', serif; }`.
- [ ] Run the reporting e2e chrome suite as regression net: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -q -k "chrome or tab"` (fallback: whole file). Green = selectors intact.
- [ ] Restart dev server, visual spot-check both tabs light+dark, screenshot to `var/screenshots/ledger-task1.png`.
- [ ] Commit:

```
style(reporting): editorial-ledger canvas, masthead band and serif title

Scope the new identity with a body.reporting-ledger class on the
reporting page only; declare the --rl-* custom-property palette with
html.dark overrides and restyle the masthead as a white band with a
hairline rule and system-serif page title. No selector renamed.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

### Task 2: Data typography — mono numerals, hairline tables, captions

**Files:** Modify `templates/js/_reporting_simple_js.html`, `templates/js/_reporting_js.html`, append `static/css/reporting.css`.

- [ ] In the Simple table builder (anchor: the function that ends `el('rsTableWrap').innerHTML = html;`), add `class="reporting-ledger-num"` to every `<td>`/`<th>` whose value went through `fmtNumber` (anchor: `function fmtNumber(v) {` … `// App locale (html lang attr), not browser locale`). Same in the Advanced grid builder (anchor: `var wrap = document.getElementById('rpResults');` inside its render function — Grep for the cell-emitting loop; Advanced may format numbers inline rather than via a named helper — key off the same numeric check it already uses).
- [ ] Append CSS: `.reporting-ledger-num { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; text-align: right; }`; hairline table rules scoped `.reporting-ledger .reporting-table-wrap` (anchor: existing `.reporting-table-wrap {`): 1px `var(--rl-hairline)` row rules, header row in muted uppercase tracked caps, remove zebra/heavy borders if present; caption utility `.reporting-ledger-caption { font-size:.68rem; letter-spacing:.1em; text-transform:uppercase; color: var(--nx-text-meta); }`.
- [ ] e2e regression: `…python -m pytest tests/e2e/test_reporting_simple.py tests/e2e/test_reporting_save.py -q`.
- [ ] Restart server, spot-check a run result table both tabs, screenshot `var/screenshots/ledger-task2.png`.
- [ ] Commit:

```
style(reporting): mono tabular numerals and hairline table rules

Tag numeric cells reporting-ledger-num at render time in both panes
and restyle result tables with hairline rules, uppercase tracked
headers and right-aligned tabular-nums mono figures, scoped to the
ledger body class.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

# PHASE 2 — Chart identity

### Task 3: Ink-navy single-series charts with peak accent

**Files:** Modify `templates/js/_reporting_viz_js.html`, `templates/js/_reporting_simple_js.html`.

- [ ] Advanced path — anchor in `mountChart` (`templates/js/_reporting_viz_js.html`):

```js
backgroundColor: single ? (type === 'line' ? 'rgba(67,56,202,.15)' : PALETTE[0]) : colors,
borderColor: single ? PALETTE[0] : '#fff',
```

  Replace the single-series arm: bars → per-point array `data.map((v,i) => i === maxIdx ? '#4f46e5' : '#312e81')` (compute `maxIdx` once above); line → `borderColor:'#312e81'`, `backgroundColor:'rgba(49,46,129,.12)'`. Multi-series (`colors`) and pie `'#fff'` borders untouched (L10).
- [ ] Simple path — anchor `state.chart = new Chart(el('rsChartCanvas'), {` and `var SIMPLE_PALETTE = [`: apply the same single-series recolor where `d.datasets.length === 1` and type is bar/line; stacked/pie/doughnut untouched.
- [ ] Both panes still pass their chart e2e: `…python -m pytest tests/e2e -q -k "chart"`.
- [ ] Restart server, run a single-series and a multi-series report, confirm navy+peak vs unchanged palette, screenshot `var/screenshots/ledger-task3.png`.
- [ ] Commit:

```
feat(reporting): ink-navy single-series charts with indigo peak accent

Single-series bars render #312e81 with the max bucket accented in
brand indigo; single-series lines go ink-navy with a soft navy fill.
Multi-series palettes, stacked charts and white pie borders are
unchanged in both chart paths.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

# PHASE 3 — New elements (TDD)

### Task 4: Timing badge in the masthead

**Files:** Modify `templates/reporting.html`, `templates/js/_reporting_simple_js.html`, `templates/js/_reporting_js.html`; test `tests/e2e/test_reporting_simple.py` (append).

- [ ] **Failing e2e first** (pattern: existing `_stub_run_ok` tests): stub catalogs + run, execute a Simple wizard run, assert `page.get_by_test_id("reporting-timing")` becomes visible and its text matches `r"\d+ rows · \d+ ms"` (English msgid form). Run it — RED (element doesn't exist).
- [ ] Markup: in `templates/reporting.html` masthead (anchor: `<p class="nx-subtitle">{{ _("Build, explore, and share reports across your data sources") }}</p>`), add inside `.nx-page-head__main` a right-aligned `<span id="reportingTiming" class="reporting-ledger-timing" hidden data-testid="reporting-timing"></span>`. NOT inside `.nx-page-head__actions` (that block is permission-gated).
- [ ] Simple pane: in `async function runCurrent()` bracket the `await api('/api/reporting/run', …)` call(s) with `performance.now()`; on success set the badge text via a new I18N entry `timingBadge: {{ _("{rows} rows · {ms} ms")|tojson }}` (add to the existing `var I18N = {` object) with `.replace()` substitution, unhide. Advanced pane: same around its `return api('/api/reporting/run', …)` success path, new flat const `var I18N_TIMING = {{ _("{rows} rows · {ms} ms")|tojson }};` beside `var I18N_RUNNING = …`.
- [ ] CSS: `.reporting-ledger-timing { margin-left:auto; font-family: ui-monospace, …; font-size:.75rem; color: var(--nx-text-meta); }` + masthead flex alignment if needed.
- [ ] e2e GREEN; fast tier: `…python -m pytest tests --ignore=tests/e2e -q --deselect tests/unit/test_translations.py`.
- [ ] Commit:

```
feat(reporting): timing badge with row count and elapsed run time

Both panes measure the run round-trip with performance.now() and
render "N rows · M ms" into a shared masthead badge, hidden until the
first successful run. Localized via each pane's I18N convention.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

### Task 5: KPI stat band above results

**Files:** Modify `templates/_reporting_simple.html`, `templates/reporting.html`, both JS partials; append CSS; test `tests/e2e/test_reporting_simple.py` (append).

- [ ] **Failing e2e first:** with `_stub_run_ok` returning known rows, assert `page.get_by_test_id("rs-kpi-band")` shows the expected total/buckets/avg figures. RED.
- [ ] Markup: Simple — inside `<div id="rsResult" …>` before the chart card (anchor: `<h3 id="rsResultTitle" class="reporting-simple-rtitle" …>`), add `<div id="rsKpiBand" class="reporting-ledger-kpis" hidden data-testid="rs-kpi-band"></div>`. Advanced — immediately above `<div id="rpResults" class="reporting-table-wrap" data-testid="reporting-results">`, add `<div id="rpKpiBand" class="reporting-ledger-kpis" hidden data-testid="reporting-kpi-band"></div>`.
- [ ] JS per pane (L7, L12): tiny helper computing `{total, buckets, avg}` from the result rows — first numeric column after the dimensions (Simple knows its measure columns from the wizard def; Advanced: first column whose values are all finite numbers, skipping the group-by columns it already tracks); hide the band on zero rows / no numeric column. Values through the pane's existing `fmtNumber` (Simple) / equivalent formatting (Advanced). Labels via gettext (`Total`, `Buckets`, `Avg per bucket` — through I18N conventions; the i18n lint guard enforces this). Uppercase caption styling comes from `.reporting-ledger-caption` (Task 2). No `page_count`-specific casing needed — the helper is metric-agnostic; sanity-check it once against a `page_count` run if `SearchConfig` has a mapped process on the test DB, otherwise any sum/avg measure proves the same code path.
- [ ] CSS: `.reporting-ledger-kpis` flex row, gap, big mono numerals (`font-size:1.6rem`), captions above, hairline-free.
- [ ] e2e GREEN; both panes' suites: `…python -m pytest tests/e2e/test_reporting_simple.py -q`.
- [ ] Commit:

```
feat(reporting): client-computed KPI stat band above results

Both panes derive total, bucket count and average per bucket from the
rows already returned and render them as big mono figures with
uppercase tracked captions. Hidden for zero-row or non-numeric
results; no vs-prior delta (would need a second query — deferred).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

### Task 6: Persistent query footer

**Files:** Modify `templates/_reporting_simple.html`, `templates/reporting.html`, both JS partials; append CSS; test `tests/e2e/test_reporting_simple.py` (append).

- [ ] **Failing e2e first:** after a stubbed run whose response includes `sqlDisplay`, assert `page.get_by_test_id("rs-sql-peek")` is visible showing the SQL's first line; click it; assert `rsSqlView` (`data-testid="rs-sql-view"`) becomes visible. RED.
- [ ] Markup: Simple — after `<div id="rsTableWrap" class="reporting-table-wrap reporting-simple-table" hidden data-testid="rs-table"></div>`, add `<button type="button" id="rsSqlPeek" class="reporting-ledger-sqlpeek" hidden data-testid="rs-sql-peek"></button>`. Advanced — after `<div id="rpChart" class="reporting-viz" hidden data-testid="reporting-chart"></div>`, add the twin `#rpSqlPeek` (`data-testid="reporting-sql-peek"`).
- [ ] JS: on successful run, if `sqlDisplay` present (Simple anchor: `state.current.sqlDisplay = res.data.sqlDisplay || null;`; Advanced anchor: `state._lastSqlDisplay = data.sqlDisplay || null;`) set peek text to the first line + `…`, unhide; else hide (L9 degrade path). Click handler invokes the existing show-query reveal (same function the `rsShowSql`/`rpShowSql` buttons call — re-Grep their listeners and reuse, do not duplicate the panel-fill logic).
- [ ] CSS: full-width hairline-top bar, mono, muted, `text-align:left`, cursor pointer, `background: var(--rl-band)`; visible focus outline (a11y — it's a button).
- [ ] e2e GREEN; run the show-query e2e neighbors too: `…python -m pytest tests/e2e -q -k "sql"`.
- [ ] Commit:

```
feat(reporting): persistent query footer peeking the inlined SQL

One-line sqlDisplay peek under the results on both panes; clicking it
opens the existing show-query panel via the same reveal path as the
Show-query button. Hidden whenever sqlDisplay is absent (inliner
degrade), so the WS1 fallback contract is preserved.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

# PHASE 4 — Surface sweep

### Task 7: Simple library + wizard ledger treatment

**Files:** Append CSS; at most additive classes in `templates/_reporting_simple.html` / `renderLibrary` (anchor: `function renderLibrary() {` in `templates/js/_reporting_simple_js.html`).

- [ ] Library tiles: scoped rules restyle the existing tile markup — hairline separation, serif report names, mono metadata line; kill drop shadows/heavy borders under `.reporting-ledger`. If a class is needed on tile internals, add it in `renderLibrary` additively.
- [ ] Wizard: step labels get `.reporting-ledger-caption` treatment via scoped CSS on the existing step-header selectors (re-Grep `reporting-simple-step` / the wizard's heading classes in `_reporting_simple.html` — style what exists, add no wrapper markup).
- [ ] Process-coverage badges (merged in from the parallel reporting-metrics plan, not present when this plan was first drafted): scoped override `.reporting-ledger .reporting-simple-chip-cov` (anchor: base rule in `static/css/reporting.css`, "Process-coverage badge on wizard chips\measure cards" — append, don't edit) — swap the pill's `--nx-accent-tint`/`--nx-accent` for mono ink-navy on a hairline pill (`border: 1px solid var(--rl-hairline); background: transparent; color: var(--rl-navy); font-family: ui-monospace, …;`) so the "n/m" badge on measure cards and breakdown chips reads as ledger typography, not a stock accent chip. No JS/markup change — `renderMeasureStep()`/`renderBreakdownStep()` already emit the class.
- [ ] 2px ink rule over the chart block: `.reporting-ledger .reporting-simple-chartcard { border-top: 2px solid var(--rl-ink); }` + Advanced twin on `.reporting-ledger .reporting-viz`.
- [ ] e2e: `…python -m pytest tests/e2e/test_reporting_simple.py -q -k "coverage or chip or cov"` (regression net for the badge markup) then the full file. Screenshot `var/screenshots/ledger-task7.png` showing a partial-coverage badge on both a measure card and a breakdown chip.
- [ ] Commit:

```
style(reporting): ledger treatment for library, wizard and chart rule

Library tiles flatten to hairline-separated ledger rows with serif
names and mono metadata; wizard step labels take the uppercase
tracked caption style; process-coverage n/m badges go mono ink-navy
on a hairline pill instead of the stock accent chip; the chart block
gets the signature 2px ink top rule on both panes.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

### Task 8: Advanced builder, drill drawer and AI surfaces alignment

**Files:** Append CSS only (surgical; no restructure of `_reporting_drill_js.html` beyond styling hooks that already exist).

- [ ] Advanced builder: chip-like selects/inputs (`.reporting-ledger .reporting-input`, the toolbar selects), mono values, hairline panel separation replacing card shadows (anchor selectors exist in the css sections `/* --- Toolbar: structured, wraps as groups, one primary action --- */` and `/* Inputs / selects / textareas */` — append overrides, never edit those layers).
- [ ] Drill drawer + AI panels: canvas/typography alignment only — background `var(--rl-band)`, hairlines, mono metadata; the drill loader and AI chrome keep their existing structure and testids.
- [ ] Full e2e reporting sweep: `…python -m pytest tests/e2e -q -k "reporting"`. Screenshot `var/screenshots/ledger-task8.png`.
- [ ] Commit:

```
style(reporting): ledger alignment for builder, drill and AI chrome

Advanced builder controls read as chips with mono values; drill
drawer and AI surfaces adopt the ledger canvas, hairlines and mono
metadata without structural or selector changes.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

### Task 9: Dark-mode pass for everything new

**Files:** Append CSS.

- [ ] Audit every rule added in Tasks 1–8 against `html.dark`: `--rl-*` dark values (already declared in Task 1) actually reached — spot-fix any hardcoded light value that leaked; chart navy needs no dark variant per L3 unless illegible on the dark canvas — if it is, lift the dark single-series color to `#818cf8`-family via a JS `document.documentElement.classList.contains('dark')` check ONLY if visibly broken (minimal adaptation, L3).
- [ ] Restart server, dark-mode walkthrough of both tabs + drill + AI, screenshots `var/screenshots/ledger-task9-dark-*.png`.
- [ ] Commit:

```
style(reporting): dark-mode adaptation for the ledger reskin

html.dark values for the --rl-* palette verified across masthead,
tables, KPI band, timing badge, query footer, library and builder;
spot fixes where a light value leaked through.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

# PHASE 5 — Chores & gate

### Task 10: i18n cycle (ONCE, late)

- [ ] `pybabel extract -F babel.cfg -o messages.pot .` → `pybabel update -i messages.pot -d translations` → hand-translate the new msgids in de/fr/it (`{rows} rows · {ms} ms`, `Total`, `Buckets`, `Avg per bucket`, any Task 7/8 strings — remove every `#, fuzzy`) → `pybabel compile -d translations`.
- [ ] `…python -m pytest tests/unit/test_translations.py tests/unit/test_reporting_i18n_lint.py -q` — 7+ passed, lint green.
- [ ] Commit:

```
chore(i18n): extract and translate editorial-ledger reskin strings

pybabel extract/update, hand-translated de/fr/it for the timing
badge, KPI captions and ledger strings, zero fuzzy entries, compiled
catalogs committed.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

### Task 11: Changelog + docs

- [ ] `CHANGELOG.md` under `## [Unreleased]` (anchor: `Work toward 2.5.64.`): Added — KPI band, timing badge, query footer; Changed — reporting page Editorial Ledger identity, single-series chart colors.
- [ ] `docs/howto/reporting.md`: short "Editorial Ledger" paragraph in the UI section + the three new elements; link the spec.
- [ ] Commit:

```
docs(reporting): changelog and howto for the editorial-ledger reskin

Record the new identity, KPI band, timing badge and query footer in
the changelog and the reporting howto; link the design spec.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

### Task 12: Full gate + live verification

- [ ] `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py`
- [ ] `…python -m pytest tests --ignore=tests/e2e -q` — all green.
- [ ] `…python -m pytest tests/e2e -q` — all green.
- [ ] Restart dev server; live INT pass (Playwright script or Chrome MCP, login pattern from the 2026-07-14 execution: `/dev/login/ben.streich` fallback if the extension is absent): both tabs light+dark, run a real report, KPI band + timing + footer + charts + drill spot-check. Screenshots `var/screenshots/ledger-final-*.png`, `SendUserFile` them.
- [ ] Fix-forward anything found (each fix its own conventional commit), re-run the affected tier.
- [ ] Hand back for owner review + merge of `plan/reporting-editorial-ledger-reskin` into `feature/2.5.64` (owner pushes; pre-push gate runs everything again).

---

## Gotchas & notes

- **Append-wins discipline:** all new CSS goes in ONE new final section of `reporting.css`. If an existing rule fights you, append a more specific `.reporting-ledger …` override — never edit the historical layers above (four of them, plus yesterday's polish section).
- **`.nx-card` flattening:** Tasks 2/7/8 visually flatten `nx-card` surfaces via scoped overrides — do NOT remove the `nx-card` classes from markup (e2e and shared CSS depend on them).
- **Advanced pane number formatting:** Advanced may not have a named `fmtNumber` — Task 2/5 key off whatever numeric formatting its grid builder already does (re-Grep at execution). If it truly formats nothing, format KPI values with the same `Intl.NumberFormat(document.documentElement.lang || undefined)` idiom Simple uses.
- **Timing badge honesty:** client-measured elapsed is round-trip (network included). The label says what it is; do not present it as server execution time in docs.
- **`_stub_run_ok` response shape:** extend the stub's payload with `sqlDisplay` where Task 6's test needs it — check how the 2026-07-14 show-query e2e stubbed it first (`test_show_query_reveals_sql` seeds a real `dbo.Users` source instead; for the peek test the stub route is enough).
- **Parallel-session drift:** `tests/unit/test_reporting_query.py` and the metrics surfaces are being edited in the main tree in parallel. If a rebase/merge of `feature/2.5.64` happens mid-execution, re-Grep every anchor in the affected partials before continuing.
- **Screenshots are part of done** (remote session): every visual task leaves a `var/screenshots/ledger-*.png` and the final pass sends them via `SendUserFile`.
