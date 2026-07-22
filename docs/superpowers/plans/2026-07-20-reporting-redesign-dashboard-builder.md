# Reporting Redesign ("Indigo Studio") + Dashboard Builder — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Single-session planning run (recon → draft → self-red-team); **every file path, symbol, and quoted snippet below was Grep/Read-verified against `feature/2.5.64` HEAD (`ba2e499`) on 2026-07-20** — trust the anchors, but re-Grep before editing (this plan quotes code, never line numbers).

**Spec:** `docs/superpowers/specs/2026-07-20-reporting-redesign-handoff.md` (the design handoff README — colors, type scale, per-screen specs; committed with this plan) + `docs/superpowers/specs/2026-07-20-reporting-dashboard-prototype.dc.html` (the working dashboard prototype — **its logic class is the literal spec for the dashboard JS state model and handlers**). The full static mock canvas stays outside the repo at `C:\Users\bes\Downloads\Reporting page redesign\design_handoff_reporting_redesign\Reporting Redesign.dc.html` (sections `2a` landing, `1d` wizard, `2b` dashboard edit-mode, `3a` drill drawer, `3b` Advanced skin, `3c` dark mode, `1e` result view — `1a/1b/1c/1f` are superseded, ignore). **The spec is the contract; this plan is the route. Fidelity is HIGH — colors, type, spacing, radii and interactions in the spec are final.**

**Goal:** Rebuild the Reporting page's presentation into the "Indigo Studio" design — landing with hero + AI command bar + live-preview report cards, a progress-rail wizard, a refined result view, a restyled drill drawer, an Advanced-builder reskin, dark mode — and add a new **multi-card dashboard** saved-report kind (`kind:'dashboard'`) with global filters, per-card overrides, drag-to-rearrange, add/duplicate/remove and Edit/Done, all built on the existing reporting REST endpoints.

**Architecture:** Zero backend changes. A saved report's `kind` already lives inside `DefinitionJSON` (`api_reports_list` selects `JSON_VALUE(r.DefinitionJSON, '$.kind') AS Kind`; create/update don't validate it) — a dashboard is just a saved report whose definition is `{kind:'dashboard', title, globalFilters, cards}`, persisted through the existing `/api/reporting/reports` CRUD and executed card-by-card through the existing `POST /api/reporting/run`. All work is in `templates/reporting.html`, `templates/_reporting_simple.html`, the `templates/js/_reporting_*_js.html` partials, one **new** partial `templates/js/_reporting_dashboard_js.html`, and `static/css/reporting.css` (+ additive tokens in `static/css/nexora-ui.css`). The Editorial Ledger skin (serif/mono) is retired in place — **class names and every id/data-testid survive; only the CSS underneath changes.**

**Tech Stack:** Jinja2 partials, vanilla-JS IIFE modules (`API_PREFIX` idiom), Chart.js 4.5.1 (CDN, already loaded), Font Awesome 6.4.2, Inter (already loaded), HTML5 drag-and-drop, Playwright e2e (network-stub pattern), Flask-Babel de/fr/it.

---

## Context an engineer needs (read first)

- **Branch:** work directly on `feature/2.5.64` (no worktree — branch was clean at planning time). **Commit per task. Do NOT `git push`, do NOT open a PR** — the owner reviews and pushes (the pre-push gate runs the FULL suite incl. Playwright e2e).
- **Read the spec first.** `docs/superpowers/specs/2026-07-20-reporting-redesign-handoff.md` carries the token table, type scale and per-screen pixel specs this plan references as "spec §Landing", "spec §Wizard" etc. Where a CSS block below says "values per spec", the spec's number wins over your taste.
- **Python for tests:** `C:\dev\nexora\.venv\Scripts\python -m pytest …`. The dev server (`nx -u`) runs global Python — the `.venv` is test-only.
- **Anchor on quoted snippets + function names, NEVER line numbers.** Re-`Grep` a snippet if it has moved.
- **TDD where behavior changes.** New behavior (dashboard module, library routing, preview cache, menu regroup) gets a failing Playwright e2e first. Pure-CSS restyles instead end with: the existing reporting e2e subset still green + a screenshot check.
- **TEST env has NO Statistics DB** — reporting runs can never execute for real in e2e. Stub `**/api/reporting/run` (and friends) **before** `page.goto` — copy the `_stub_run_ok(page)` helper pattern in `tests/e2e/test_reporting_simple.py`. Never let a Simple-pane AI flow hit the real run endpoint (`showResultError` tears down chips/refine mid-test).
- **Before running any e2e tier:** `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py`.
- **Jinja template cache is process-lifetime** — restart the dev server (`nx -r`) before ANY manual browser check.
- **e2e locale is English** — assert English strings.
- **Migrations needed: NO.** No SQL, no new permission codes, no `page_visibility()` change, no `deploy.yml` change. (`kind:'dashboard'` lives in `DefinitionJSON`; dashboards inherit the existing reports access model: owner / `Visibility='shared'` / `ReportShares` row.)
- **i18n: ONE late pybabel cycle (Task 17).** New msgids land in Tasks 3, 5, 7, 9, 11–15; `tests/unit/test_translations.py` is expected RED in between — use `--deselect tests/unit/test_translations.py` for the fast tier until Task 17.
- **PROD URL prefix:** every hand-built URL goes through the `API_PREFIX` idiom. The Simple pane's `api(url, opts)` helper already normalizes; the new dashboard partial must open with the same two lines every other `_reporting_*_js.html` module uses.
- **Visual contract:** never rename a `.reporting-*` class; preserve every `data-testid`/`id` (the e2e suite — 61 tests in `test_reporting_simple.py` alone — keys on them); `.nx-rise*` animations use fill-mode `backwards`, **never** `both` (stacking-context trap: `both` holds an identity transform that buries overflowing popovers).
- **The 61-test Simple suite is the redesign's safety net.** After every task run the fast tier below; presentational assertions that legitimately changed (moved element, new wrapper) may be updated — **flow assertions (click step → next step) may not.**
- **Fast tier per task:** `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py tests/e2e/test_reporting.py -q --deselect tests/unit/test_translations.py` (plus the task's own new tests).
- **gitlint:** conventional-commit title ≤72 chars, imperative, no trailing period; non-empty body wrapped ≤100 chars; commit via Bash `git commit -F - <<'EOF' … EOF`. If `ruff-format` rewrites a file the first attempt fails — `git add -u` and recommit. If INT is unreachable: `SQL_SYNC_SKIP=1`, never `--no-verify`.
- **Commit trailer names the EXECUTING model** — the blocks below say `Claude Fable 5`; substitute the real executor if different.
- **Two stray untracked files** (`package.json`, `package-lock.json` at repo root) may exist from earlier sessions — never `git add` them.

---

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Supersede the pin-to-dashboard plan** (`2026-07-15-reporting-pin-to-dashboard.md`, never executed — `dbo.ReportingPins` does not exist and its migration number `0040` has since been taken). No Pin button in the redesigned result header. Task 17 stamps the old plan SUPERSEDED. | Owner call (2026-07-20). The dashboard builder covers "my saved reports as live cards" better; the add-card tile's "drop a saved report here" is the successor affordance. |
| D2 | **A dashboard is a saved report with `definition = {kind:'dashboard', schemaVersion:1, title, globalFilters:[{field,op,value}], cards:[…]}`; card = `{id, type:'kpi'\|'line'\|'bar'\|'donut'\|'table', span, title, definition, filterOverrides:[…]}`. No migration, no new endpoints.** | `dbo.Reports` has no Kind column; `$.kind` is already the client-written discriminator (`"sql"` vs default `"table"`). Create/update endpoints `json.dumps` whatever definition they get (`len(definition_json) > 64_000` cap — ~10–15 embedded card defs fit comfortably). |
| D3 | **Dashboards render as a fourth Simple-pane view** (`state.view: library\|wizard\|result\|dashboard`), implemented in a new partial `templates/js/_reporting_dashboard_js.html` exposing `window.ReportingDashboard = {openNew, open, close}`. No new route. | Reuses the pane's view switching, toast, catalog and the shared drill drawer. Deep-linking stays the existing `?tab=` mechanism. |
| D4 | **Per-card effective filters = card.definition.filters + globalFilters + filterOverrides, where an override replaces any global filter on the same field.** Merge is client-side, then one `POST /api/reporting/run` per card. | Matches the prototype's semantics ("apply to every card · a card can override them"). The run endpoint re-enforces source permissions and row scope per call — no new security surface. |
| D5 | **Library previews are rendered from the saved definition + a localStorage result cache — never by running reports on landing load.** Cache `nx.reporting.preview.<id>` = `{t: chartTypeOrTotal, v: number[] \| total, ts}`, written every time a report's run succeeds (Simple result path). Cards without a cache entry render a deterministic decorative curve seeded from the report id; total-kind cards without cache show the metric label instead of a fake number. | "Live thumbnails" without N runs per landing (rate limit is 60/min; Statistics DB load). Previews become real organically. Inline SVG only — spec explicitly forbids per-card Chart.js instances. |
| D6 | **Result-header regroup: `rsOpenAdvanced` and `rsShowSql` move into a new `⋯` overflow menu (`#rsMoreMenu`); `rsSave` becomes the gradient primary; Export becomes `Export ▾` (existing `rsExportFormat` select + `rsExport` restyled as one visual unit).** Affected e2e tests are updated to open the menu first — ids/testids unchanged. | Spec §Result is explicit about the header. Keeping the ids means the handful of `rs-open-advanced` / `rs-show-sql` e2e clicks just gain one `rs-more` click before them. `rs-error-open-advanced` (error-state escape hatch) stays a visible inline button — untouched. |
| D7 | **Wizard: presentation only.** The four steps (`rsStepMeasure/Scope/Breakdown/Time`), their renderers (`renderMeasureStep` …), ids, testids and the step *order* are untouched; the wizard already shows one step at a time. New: header bar with "Step N of 4", left progress rail + preview box (new elements, JS-rendered from existing `wiz` state), step-card chrome, coverage progress-bar chips. | The 61-test suite drives the wizard through `rs-measure-next` → `rs-scope-next` → … — flow must stay byte-compatible. |
| D8 | **KPI trend on dashboard cards: computed only when the card's effective filters contain exactly one date-range filter; a second `/api/reporting/run` with the range shifted back one period yields "vs previous period". Otherwise the trend line is hidden.** | Honest numbers or nothing. Two runs per KPI card is bounded (KPIs are span-3 cards; typical dashboards have ≤4). |
| D9 | **Dashboard Export v1 = per-card:** the header Export button opens a small menu listing the cards; picking one POSTs that card's *effective* definition to the existing `/api/reporting/export` (xlsx). Whole-workbook export deferred. | `/api/reporting/export` already turns a definition into a download — zero new backend. Gated by `has_permission('reporting.export')` like every other export control. |
| D10 | **Drag & drop = plain HTML5 DnD exactly as the prototype implements it** (dragstart → `opacity:.35`; dragover target → indigo ring; drop → splice source before target; dragend clears). The mock-`2b` dashed drop-slot + tilted drag image is **skipped** (spec marks it nice-to-have). | Prototype logic is the spec; the fancy drag image needs a custom drag-image canvas — YAGNI. |
| D11 | **Global-filter chip editor v1 = popover with three controls (field select from the run catalog, op select, value input/select), self-contained in the dashboard partial.** The prototype's value-cycling is a stand-in, not the spec. | The Simple pane's chip editor is welded into its IIFE; extracting it is a refactor this plan doesn't need. Same filter model (`{field, op, value}`) as everywhere else. |
| D12 | **Ledger retirement = rewrite the `body.reporting-ledger` CSS section in place.** Class names (`.reporting-ledger-kpis`, `.reporting-ledger-num`, …) survive — templates/JS keep working — but every `Georgia`/serif and `ui-monospace` font treatment inside that section is replaced per the spec ("Everything is Inter now"). The two mono faces **outside** the ledger section (`.reporting-sql-live` area + `#rsSqlText`/show-query panels) stay mono — SQL is code. | Cheapest faithful retirement; zero markup churn. |
| D13 | **`Chart.defaults.font.family` is set once on the Reporting page** via a two-line inline script in `templates/reporting.html` right after the Chart.js CDN tag (plus `Chart.defaults.color = '#9ca3af'`). Existing inline per-chart configs already pass explicit colors and win where set. | Spec mandate. Today no defaults are set on `/reporting` (only `_dashboard_js.html` sets them, on a different page). |
| D14 | **New tokens are additive** in `static/css/nexora-ui.css`: `--nx-violet-tint: #f5f3ff`, `--nx-violet-border: #ddd6fe`, `--nx-radius-lg: 12px`, `--nx-radius-hero: 16px`, `--nx-card-hover-border: #c7d2fe`, `--nx-card-hover-shadow: 0 8px 24px -8px rgba(79,70,229,.18)` + `html.dark` overrides (`--nx-violet-tint: rgba(167,139,250,.12)`, `--nx-violet-border: #4c1d95`, hover border `#4c4a8f`, hover shadow `0 8px 24px -8px rgba(0,0,0,.5)`). Nothing existing is edited. | nexora-ui.css is app-wide; additive-only keeps every other page byte-identical. |
| D15 | **The masthead segmented control**: the existing `.nx-tabs.reporting-tabs` div (ids `rpTabSimple`/`rpTabAdvanced`, roles, ARIA) moves inside `.nx-page-head` next to the Sources button and is restyled as the spec's segmented track. Ids, roles, `aria-controls`, testids unchanged. | Spec §Landing ("Tabs move into the masthead"). Pure relocation + CSS. |
| D16 | **`ai_enabled` false ⇒ the hero renders without the AI command bar and suggestion chips** (guided-builder + New-dashboard buttons center-stage); the existing `{% if ai_enabled %}` guard pattern in `_reporting_simple.html` is kept. | The AI bar reuses `#rsAiPrompt`/`#rsAiAsk` which only exist when `ai_enabled`. |
| D17 | **Dashboards are excluded from the Advanced saved-reports `<select>`** (same treatment as the existing ` (SQL)` suffix path: filter them out entirely — Advanced cannot edit a dashboard) and from the Simple library's plain-report click path (they route to `ReportingDashboard.open`). | Advanced's definition model can't represent a dashboard; loading one would corrupt it on save. |

---

## Owner actions (not for the executor)

1. **Review + push `feature/2.5.64`** when the plan completes (pre-push gate runs the FULL suite; run `scripts/test_db_reset.py` first).
2. **Pin-to-dashboard plan** is superseded (D1) — if you still want report tiles on the `/dashboard` landing page later, that's a fresh (much smaller) plan on top of the dashboard builder.
3. **Whole-workbook dashboard export** (one XLSX, sheet per card) deferred (D9) — say the word if wanted.
4. **Custom drag image** (tilted card + dashed drop slot, mock `2b`) skipped (D10) — cosmetic upgrade path noted in `reporting.css` comments.
5. The **`Reporting Redesign.dc.html` mock stays in your Downloads folder** — keep it until execution finishes (pixel reference for sections the README summarizes).

---

# PHASE 1 — Foundation & ledger retirement

### Task 1: Tokens, Chart defaults, masthead segmented tabs

**Files:**
- Modify: `static/css/nexora-ui.css` (append tokens — additive only)
- Modify: `templates/reporting.html` (Chart defaults script; move tabs div into page head)
- Modify: `static/css/reporting.css` (segmented-control styles for `.reporting-tabs`)

**Interfaces:**
- Produces: the D14 token set (`--nx-violet-tint`, `--nx-violet-border`, `--nx-radius-lg`, `--nx-radius-hero`, `--nx-card-hover-border`, `--nx-card-hover-shadow`) — every later task's CSS uses these instead of raw hex where a token exists.

- [ ] **Step 1 — Append tokens.** In `static/css/nexora-ui.css`, find the end of the `:root {` block (anchor: the last custom property before its closing `}`) and append inside it:

```css
  /* Indigo Studio (2026-07-20 reporting redesign) */
  --nx-violet-tint: #f5f3ff;
  --nx-violet-border: #ddd6fe;
  --nx-radius-lg: 12px;
  --nx-radius-hero: 16px;
  --nx-card-hover-border: #c7d2fe;
  --nx-card-hover-shadow: 0 8px 24px -8px rgba(79, 70, 229, .18);
```

and inside the `html.dark {` override block append:

```css
  --nx-violet-tint: rgba(167, 139, 250, .12);
  --nx-violet-border: #4c1d95;
  --nx-card-hover-border: #4c4a8f;
  --nx-card-hover-shadow: 0 8px 24px -8px rgba(0, 0, 0, .5);
```

- [ ] **Step 2 — Chart defaults.** In `templates/reporting.html`, directly after the line `<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1" integrity="sha384-jb8JQMbMoBUzgWatfe6COACi2ljcDdZQ2OxczGA3bGNeWe+6DChMTBJemed7ZnvJ" crossorigin="anonymous"></script>` add:

```html
  <script>
    if (window.Chart) { Chart.defaults.font.family = "'Inter', sans-serif"; Chart.defaults.color = '#9ca3af'; }
  </script>
```

- [ ] **Step 3 — Move the tabs into the masthead.** In `templates/reporting.html`, cut the whole `<div class="nx-tabs reporting-tabs" role="tablist" …>…</div>` block (anchor: `data-testid="reporting-tabs"`) and paste it inside `.nx-page-head` as a sibling *before* the `{% if has_permission('reporting.admin.sources') %}` actions block, wrapped so head layout holds:

```html
    <div class="nx-page-head__actions reporting-head-actions">
      <div class="nx-tabs reporting-tabs" role="tablist" aria-label="{{ _('Reporting view') }}" data-testid="reporting-tabs">
        …unchanged tab buttons…
      </div>
      {% if has_permission('reporting.admin.sources') %}
      <a href="{{ url_for('reporting_sources_admin') }}" …unchanged Sources link…</a>
      {% endif %}
    </div>
```

(The old standalone actions div collapses into this one — one wrapper, tabs + Sources side by side, `gap:10px`.)

- [ ] **Step 4 — Segmented-control CSS.** In `static/css/reporting.css`, find the existing `.reporting-tabs` rules (anchor: the Simple/Advanced tabs section near the comment mentioning tabs) and replace with the spec's segmented track (spec §Landing "Tabs"):

```css
/* Masthead segmented control (Indigo Studio) */
.reporting-head-actions { display: flex; align-items: center; gap: 10px; }
.reporting-tabs { display: flex; gap: 2px; padding: 3px; background: var(--nx-divider); border: 1px solid var(--nx-border); border-radius: 8px; margin: 0; }
.reporting-tabs .nx-tab { border: none; background: transparent; border-radius: 6px; padding: 6px 14px; font: 500 12.5px var(--nx-font); color: var(--nx-text-sec); cursor: pointer; }
.reporting-tabs .nx-tab:hover { color: var(--nx-text); }
.reporting-tabs .nx-tab[aria-selected="true"] { background: var(--nx-card); color: var(--nx-accent); font-weight: 600; box-shadow: 0 1px 2px rgba(16, 24, 40, .06); }
```

(If the existing `.nx-tab` base styles set underlines/borders that bleed through, neutralize them here at `.reporting-tabs .nx-tab` specificity — do NOT edit `nexora-ui.css`'s `.nx-tab`.)

- [ ] **Step 5 — Verify.** Restart dev server (`nx -r`), then:

Run: `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py` then the fast tier.
Expected: green (tab ids/roles unchanged — the tab-switching tests must pass untouched).

- [ ] **Step 6 — Commit:**

```bash
git add static/css/nexora-ui.css static/css/reporting.css templates/reporting.html
git commit -F - <<'EOF'
feat(reporting): studio tokens, Chart.js Inter defaults, masthead tabs

Additive Indigo-Studio tokens in nexora-ui.css (violet tints, lg/hero
radii, card-hover treatment, dark twins), Chart.defaults font/color on
the reporting page, and the Simple/Advanced tab list relocated into the
page head restyled as a segmented control (ids, roles and ARIA intact).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 2: Retire the Editorial Ledger typography

**Files:**
- Modify: `static/css/reporting.css` (the `============ Editorial Ledger (2026-07-15 reskin) ============` section — rewrite in place)

**Interfaces:**
- Produces: same class names, Studio look — `.reporting-ledger-kpis/-kpi-value/-num/-timing/-sqlpeek`, `.rs-card-name/-meta` etc. all keep working. Every later task assumes ledger flatness is gone (cards get `--nx-radius-lg` + token borders).

- [ ] **Step 1 — Inventory before touching.** Grep every `reporting-ledger-` class actually referenced outside the CSS: `git grep -n "reporting-ledger" -- templates/`. Anything referenced must keep a rule; anything CSS-only may be deleted with its rule.

- [ ] **Step 2 — Rewrite the section.** In `static/css/reporting.css`, inside the section starting at the comment `============ Editorial Ledger` (runs to end of file):
  - Delete every `font-family` declaration naming `Georgia`, `'Charter'`, `'Times New Roman'`, `serif` (anchors: `.reporting-ledger .nx-title`, `.rs-card-name`) — they fall back to the page's Inter.
  - Replace every `font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace` inside this section (anchors: `.reporting-ledger-num`, `-timing`, `-kpi-value`, `-sqlpeek`, `.rs-card-meta`, the coverage chip) with `font-variant-numeric: tabular-nums;` (keep any existing size/weight lines). **Exception:** `.reporting-ledger-sqlpeek` keeps a mono face for its SQL snippet — restyle it per spec §Result's query-peek footer instead: `background: #fcfcfd; border-top: 1px solid var(--nx-divider); font: 11px var(--nx-mono); color: var(--nx-text-meta);` hover `color: var(--nx-accent)`.
  - Replace the ledger's flattened-card rules (hairline tables, shadow removal on Advanced panels, 2px ink rules over charts, hairline library rows) with nothing — later tasks restyle those surfaces; deleting here must not leave the page broken, so where a deleted rule styled a still-visible element, leave a minimal token rule (`border: 1px solid var(--nx-border); border-radius: var(--nx-radius-lg); background: var(--nx-card);`).
  - Keep the `--rl-*` custom-property block and its `html.dark` remap **only if** any surviving rule still consumes an `--rl-*` var (Grep `var(--rl-` after the rewrite); otherwise delete both blocks.
- [ ] **Step 3 — Verify.** Restart server; fast tier + eyeball `/reporting` (no serif anywhere — the page title, library cards, KPI values are all Inter).
- [ ] **Step 4 — Screenshot** to `var/screenshots/redesign-task2-ledger-retired.png` (drive Playwright yourself via `nx -u -b --loginas:ben.streich`).
- [ ] **Step 5 — Commit:**

```bash
git add static/css/reporting.css
git commit -F - <<'EOF'
feat(reporting): retire Editorial Ledger serif/mono skin

The body.reporting-ledger section is rewritten in place: Georgia/serif
titles and ui-monospace numerals become Inter + tabular-nums, ledger
flatness gives way to token cards. Class names, ids and testids are
untouched; SQL text panels keep their mono face.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 2 — Landing ("Indigo Studio")

### Task 3: Hero card, AI command bar, action buttons

**Files:**
- Modify: `templates/_reporting_simple.html` (restructure the top block)
- Modify: `static/css/reporting.css` (hero styles)
- Test: `tests/e2e/test_reporting_simple.py` (append)

**Interfaces:**
- Produces: `#rsHero` (hero card), `#rsNewDashboard` (`data-testid="rs-new-dashboard"`, **`hidden` until Task 11 wires it**), three suggestion-chip buttons `.rs-suggestion` (`data-testid="rs-suggestion"`), relocated `#rsAiBar` inside the hero. `#rsNewReport`, `#rsAiPrompt`, `#rsAiAsk`, `#rsSearch` keep ids/testids.

- [ ] **Step 1 — Failing e2e.** Append to `tests/e2e/test_reporting_simple.py` (reuse the module's login + stub helpers exactly as neighbouring tests do):

```python
def test_landing_hero_suggestion_fills_prompt(nexora_server, page):
    # same catalog/library stubs as the existing library tests
    _stub_catalog(page)  # ← use the module's real helper names at execution time
    _login(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    hero = page.get_by_test_id("rs-hero")
    expect(hero).to_be_visible()
    expect(hero.get_by_test_id("rs-ai-prompt")).to_be_visible()
    chip = page.get_by_test_id("rs-suggestion").first
    chip_text = chip.inner_text()
    chip.click()
    expect(page.get_by_test_id("rs-ai-prompt")).to_have_value(chip_text)
```

> The helper names above (`_stub_catalog`, `_login`) are placeholders for the module's real fixtures — Grep the top of `test_reporting_simple.py` and copy the exact setup the existing landing/library tests use. Do not invent new stub payloads.

- [ ] **Step 2 — Run, expect RED** (`rs-hero` not found):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -k "hero_suggestion" -q`

- [ ] **Step 3 — Restructure the template.** In `templates/_reporting_simple.html`, replace the current `.reporting-simple-top` block (anchor: `<div class="reporting-simple-top">` through its closing `</div>` before `<div id="rsLibrary"`) with:

```html
  <div id="rsHero" class="reporting-hero nx-rise" data-testid="rs-hero">
    <h2 class="reporting-hero__title">{{ _("Build a report in seconds") }}</h2>
    <p class="reporting-hero__sub">{{ _("Ask in plain language, or step through the guided builder.") }}</p>
    {% if ai_enabled %}
    <div class="reporting-hero__aiwrap">
      <div class="reporting-simple-aibar" id="rsAiBar" data-testid="rs-ai-bar">
        <i class="fas fa-wand-magic-sparkles reporting-hero__wand" aria-hidden="true"></i>
        <input id="rsAiPrompt" class="reporting-hero__aiinput"
               placeholder="{{ _('Ask AI — e.g. “documents per month this year”') }}"
               data-testid="rs-ai-prompt">
        <button id="rsAiAsk" class="reporting-hero__aibtn" data-testid="rs-ai-ask">{{ _("Ask AI") }}</button>
      </div>
    </div>
    <div class="reporting-hero__chips">
      <button type="button" class="rs-suggestion" data-testid="rs-suggestion">{{ _("documents per month this year") }}</button>
      <button type="button" class="rs-suggestion" data-testid="rs-suggestion">{{ _("invoices by process, last 3 months") }}</button>
      <button type="button" class="rs-suggestion" data-testid="rs-suggestion">{{ _("pages processed per week") }}</button>
    </div>
    <p class="reporting-simple-hint" id="rsAiGone" hidden data-testid="rs-ai-gone">{{ _("The AI assistant is unavailable right now — you can still build reports with “New report”.") }}</p>
    {% endif %}
    <div class="reporting-hero__actions">
      <button id="rsNewReport" class="nx-btn nx-btn--secondary" data-testid="rs-new-report">
        <i class="fas fa-plus" aria-hidden="true"></i>{{ _("New report — guided builder") }}</button>
      <button id="rsNewDashboard" class="nx-btn nx-btn--secondary reporting-hero__dashbtn" hidden data-testid="rs-new-dashboard">
        <i class="fas fa-table-cells-large" aria-hidden="true"></i>{{ _("New dashboard") }}</button>
    </div>
  </div>
```

`#rsSearch` moves out of this block — Task 4 re-homes it in the My-reports header. Until Task 4 lands, park it directly under the hero unchanged (keep id/testid — the suite's search tests must stay green):

```html
  <input id="rsSearch" class="reporting-input reporting-simple-search"
         placeholder="{{ _('Search reports…') }}" data-testid="rs-search">
```

- [ ] **Step 4 — Wire the suggestion chips.** In `templates/js/_reporting_simple_js.html`, near the existing `rsAiAsk` click wiring (anchor: Grep `rsAiAsk` in the file), add:

```js
  document.querySelectorAll('.rs-suggestion').forEach(function (b) {
    b.addEventListener('click', function () {
      var p = el('rsAiPrompt'); if (!p) return;
      p.value = b.textContent.trim(); p.focus();
    });
  });
```

- [ ] **Step 5 — Hero CSS.** Append to `static/css/reporting.css` (values: spec §Landing "Hero card" — radial-gradient bg, 16px radius, `#e0e7ff` border, gradient-framed AI bar `max-width:660px` with `1.5px` gradient padding + `0 12px 32px -12px rgba(79,70,229,.4)` shadow, gradient Ask-AI button `border-radius:9px; padding:11px 20px`, chip pills `border:1px solid #e0e7ff; color:#4f46e5; hover bg #eef2ff`):

```css
/* ---- Landing hero (spec §Landing) ---- */
.reporting-hero { border-radius: var(--nx-radius-hero); border: 1px solid #e0e7ff; background: radial-gradient(1200px 320px at 50% -80px, var(--nx-accent-tint) 0%, var(--nx-card) 70%); padding: 44px 48px 36px; text-align: center; }
.reporting-hero__title { margin: 0 0 8px; font: 600 28px var(--nx-font); letter-spacing: -.6px; color: var(--nx-text); }
.reporting-hero__sub { margin: 0 0 24px; font-size: 14px; color: var(--nx-text-sec); }
.reporting-hero__aiwrap { max-width: 660px; margin: 0 auto; border-radius: 14px; background: var(--nx-brand-grad); padding: 1.5px; box-shadow: 0 12px 32px -12px rgba(79, 70, 229, .4); }
.reporting-hero__aiwrap .reporting-simple-aibar { display: flex; align-items: center; border-radius: 12.5px; background: var(--nx-card); padding: 5px 5px 5px 18px; }
.reporting-hero__wand { color: var(--nx-violet); font-size: 15px; }
.reporting-hero__aiinput { flex: 1; border: none; outline: none; background: transparent; padding: 11px 14px; font: 13.5px var(--nx-font); color: var(--nx-text); }
.reporting-hero__aibtn { border: none; border-radius: 9px; background: var(--nx-brand-grad); color: #fff; font: 600 13px var(--nx-font); padding: 11px 20px; cursor: pointer; }
.reporting-hero__aibtn:hover { filter: brightness(1.08); }
.reporting-hero__chips { display: flex; justify-content: center; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
.rs-suggestion { border: 1px solid #e0e7ff; border-radius: 999px; background: var(--nx-card); color: var(--nx-accent); font: 500 12px var(--nx-font); padding: 6px 14px; cursor: pointer; }
.rs-suggestion:hover { background: var(--nx-accent-tint); }
.reporting-hero__actions { margin-top: 24px; display: flex; justify-content: center; gap: 10px; }
```

- [ ] **Step 6 — Run, expect GREEN** (new test + fast tier). Restart server first.
- [ ] **Step 7 — Screenshot** → `var/screenshots/redesign-task3-hero.png`.
- [ ] **Step 8 — Commit:**

```bash
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html static/css/reporting.css tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
feat(reporting): landing hero with AI command bar and suggestions

Hero card per the Indigo Studio spec: gradient-framed AI command bar
(reusing rsAiPrompt/rsAiAsk), three suggestion chips that fill the
prompt, guided-builder button, and a hidden New-dashboard button that
the dashboard phase unhides. Search keeps its id, parked until the
My-reports header lands.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 4: Report cards with preview thumbnails + group headers

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (`card()`, `renderLibrary()`, run-success cache write)
- Modify: `templates/_reporting_simple.html` (library group headers with count pills + search re-home)
- Modify: `static/css/reporting.css` (card grid, preview band, empty groups)
- Test: `tests/e2e/test_reporting_simple.py` (append)

**Interfaces:**
- Consumes: D5 cache contract `nx.reporting.preview.<id>` = `{t:'line'|'bar'|'donut'|'total', v:number[]|number, ts}`.
- Produces: `card(r)` renders `.rs-card` with `.rs-card-preview` band + `.rs-card-body`; count pills `#rsCountMine` etc.; empty-group placeholders `.rs-group-empty`. Existing testids `rs-card` (Grep the current `card()` for the exact testid it stamps — reuse), `rs-group-shared/-mine/-direct` unchanged.

- [ ] **Step 1 — Failing e2e:**

```python
def test_library_card_shows_preview_band_and_type_badge(nexora_server, page):
    # library stub must include one saved report with kind 'table' and a
    # definition whose first column has a grain (⇒ line badge). Copy the
    # module's library stub and extend the report entry accordingly.
    ...
    page.goto(f"{nexora_server}/reporting?tab=simple")
    card = page.get_by_test_id("rs-card").first
    expect(card.locator(".rs-card-preview")).to_be_visible()
    expect(card.locator(".rs-card-badge")).to_contain_text("LINE")
```

- [ ] **Step 2 — Run, expect RED.**
- [ ] **Step 3 — Group headers + search re-home.** In `templates/_reporting_simple.html`, restructure `#rsLibrary` (ids for the three grids unchanged):

```html
  <div id="rsLibrary" data-testid="rs-library">
    <div class="rs-group-head">
      <h3 class="reporting-simple-h">{{ _("My reports") }}</h3>
      <span class="rs-count-pill" id="rsCountMine"></span>
      <span class="rs-group-spacer"></span>
      <span class="rs-search-wrap"><i class="fas fa-magnifying-glass" aria-hidden="true"></i>
        <input id="rsSearch" class="reporting-input reporting-simple-search"
               placeholder="{{ _('Search reports…') }}" data-testid="rs-search"></span>
    </div>
    <div id="rsGroupMine" class="reporting-simple-grid" data-testid="rs-group-mine"></div>
    <div class="rs-group-head"><h3 class="reporting-simple-h">{{ _("Library") }}</h3><span class="rs-count-pill" id="rsCountShared"></span></div>
    <div id="rsGroupShared" class="reporting-simple-grid" data-testid="rs-group-shared"></div>
    <div class="rs-group-head"><h3 class="reporting-simple-h">{{ _("Shared with me") }}</h3><span class="rs-count-pill" id="rsCountDirect"></span></div>
    <div id="rsGroupDirect" class="reporting-simple-grid" data-testid="rs-group-direct"></div>
  </div>
```

(Delete the parked `#rsSearch` from Task 3. Note the spec puts *My reports* first; today the template renders Library/shared first — reorder as shown. If an e2e test asserts group ORDER, update it — that's presentational.)

- [ ] **Step 4 — Card renderer.** In `templates/js/_reporting_simple_js.html`, rewrite `card(r)` (anchor: `function card(r) {`) to emit the two-band card. Preserve whatever click handler + testid the current implementation stamps. Shape:

```js
  function previewCacheGet(id) {
    try { return JSON.parse(localStorage.getItem('nx.reporting.preview.' + id) || 'null'); }
    catch (e) { return null; }
  }
  function previewKindOf(r) {
    // derive the badge/thumbnail type from the saved definition summary the
    // list endpoint returns (r.kind, r.definition summary fields if present):
    // dashboard → 'dash'; zero-dimension → 'total'; first col grained/date →
    // 'line'; visualization pie/doughnut → 'donut'; else 'bar'.
    …
  }
  function sparkPath(vals, w, h) {  // shared by line preview; pure, 6 lines
    var max = Math.max.apply(null, vals) || 1;
    return vals.map(function (v, i) {
      return (i / (vals.length - 1) * w).toFixed(1) + ',' + (h - 4 - (v / max) * (h - 10)).toFixed(1);
    }).join(' ');
  }
  function seededVals(id, n) {      // deterministic decorative fallback (D5)
    var vals = [], x = (id * 2654435761) % 977;
    for (var i = 0; i < n; i++) { x = (x * 48271) % 2147483647; vals.push(40 + (x % 60)); }
    return vals;
  }
```

`card(r)` then builds: preview band (inline `<svg>` per type — line: polyline + 12%-opacity area polygon + end dot, stroke `#4f46e5` width 2; bar: 8 `rect rx=2.5` in `#a5b4fc` with the max bar `#7c3aed`; donut: two stroked circles per spec; total: cached total `toLocaleString()` in 30px `#4f46e5`, else the first metric's label), type badge top-right (`.rs-card-badge`, uppercase, violet icon), body (name `.rs-card-name` 2-line clamp, avatar circle with owner initials, `owner · rel-time` line — reuse the existing relative-time formatting if the current `card()` has one, else `r.updatedAt` date). Real values from `previewCacheGet(r.id)` when present (`t` matches), else `seededVals`.

- [ ] **Step 5 — Cache writer.** In the Simple run-success path (anchor: the function that receives the successful `/api/reporting/run` response and calls `renderChart` / `renderKpiBand`), after the result is rendered and **only when `state.current.reportId` is set**, write the cache: first-metric series (capped 16 points) for dimensioned results as `t:'line'|'bar'` (match the rendered chart type), `{t:'total', v: grandTotal}` for zero-dimension. Wrap in `try{}catch(e){}` — quota errors must never break a run.
- [ ] **Step 6 — Count pills + empty groups.** In `renderLibrary()` (anchor: `function renderLibrary() {`): set each `#rsCount*` pill to the group's card count; when a group is empty render `<div class="rs-group-empty">` with the spec's two lines (bold name + `#9ca3af` explanation: Library → "Reports shared with everyone will appear here.", Shared with me → "Reports shared directly with you will appear here.", My reports → "Reports you save will appear here.") — i18n-wrapped via the partial's existing I18N pattern (Grep `I18N` in the file; template-side strings need `{{ _(…)|tojson }}` entries).
- [ ] **Step 7 — CSS.** Append per spec §Landing: grid `repeat(auto-fill, minmax(240px, 1fr)); gap:14px`; `.rs-card` 12px radius, hover `border-color: var(--nx-card-hover-border); box-shadow: var(--nx-card-hover-shadow); transform: translateY(-2px);` (transition 150ms `cubic-bezier(.4,0,.2,1)`; hover lift only in view contexts); `.rs-card-preview` band (`padding:14px 14px 0; background:linear-gradient(180deg,#fafaff,var(--nx-card)); border-bottom:1px solid var(--nx-divider); height:78px`); badge pill; body typography per spec's type scale; `.rs-group-head` row; `.rs-count-pill`; `.rs-group-empty` dashed placeholder; `.rs-search-wrap` icon-inside input (width 200px).
- [ ] **Step 8 — Run, expect GREEN** (new test + fast tier; search + open-report tests must still pass).
- [ ] **Step 9 — Screenshot** → `var/screenshots/redesign-task4-cards.png`.
- [ ] **Step 10 — Commit:**

```bash
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html static/css/reporting.css tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
feat(reporting): library report cards with preview thumbnails

Two-band cards per spec: inline-SVG preview (line/bar/donut/total) fed
by a localStorage last-run cache, decorative seeded fallback, type
badge, owner avatar + relative time. Group headers gain count pills and
dashed empty states; search moves into the My-reports header row.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 3 — Wizard (progress rail)

### Task 5: Two-column layout, progress rail, wizard header

**Files:**
- Modify: `templates/_reporting_simple.html` (wizard wrapper: header bar + rail + step-card column)
- Modify: `templates/js/_reporting_simple_js.html` (rail renderer + step counter, called from the existing step transitions)
- Modify: `static/css/reporting.css`
- Test: `tests/e2e/test_reporting_simple.py` (append)

**Interfaces:**
- Produces: `#rsWizardRail` (`data-testid="rs-wizard-rail"`), `#rsWizardStepNo` ("Step N of 4"), `#rsWizardPreview` (running-sentence box), `renderWizardRail()` — Task 6 restyles chips inside the untouched step containers.
- Consumes: existing `wiz` state + step renderers (`renderMeasureStep`, `renderScopeStep`, `renderBreakdownStep`, `renderTimeStep`) — **not modified here.**

- [ ] **Step 1 — Failing e2e:**

```python
def test_wizard_rail_tracks_progress(nexora_server, page):
    # existing wizard-entry stubs from neighbouring tests
    ...
    page.get_by_test_id("rs-new-report").click()
    rail = page.get_by_test_id("rs-wizard-rail")
    expect(rail).to_be_visible()
    expect(page.locator("#rsWizardStepNo")).to_have_text("Step 1 of 4")
    # advance one step (pick a measure the way existing tests do), then:
    expect(page.locator("#rsWizardStepNo")).to_have_text("Step 2 of 4")
    expect(rail).to_contain_text("Document count")  # chosen-value summary
```

(Adapt the measure-picking lines from the module's existing wizard tests — same stub catalog, same click sequence.)

- [ ] **Step 2 — Run, expect RED.**
- [ ] **Step 3 — Template.** In `templates/_reporting_simple.html`, wrap the existing wizard internals. The four `.reporting-simple-step` divs move **unchanged** into the right column:

```html
  <div id="rsWizard" class="reporting-simple-wizard" hidden data-testid="rs-wizard">
    <div class="rs-wizard-head">
      <button id="rsWizardClose2" class="nx-btn nx-btn--secondary rs-wizard-backlib" data-testid="rs-wizard-backlib">
        <i class="fas fa-arrow-left" aria-hidden="true"></i>{{ _("Library") }}</button>
      <h2 class="rs-wizard-title">{{ _("New report") }}</h2>
      <span class="rs-wizard-spacer"></span>
      <span id="rsWizardStepNo" class="rs-wizard-stepno"></span>
      <button id="rsWizardClose" class="reporting-link reporting-simple-close" data-testid="rs-wizard-close"
              title="{{ _('Back to library') }}" aria-label="{{ _('Back to library') }}">&times;</button>
    </div>
    <div class="rs-wizard-grid">
      <div id="rsWizardRail" class="rs-wizard-rail" data-testid="rs-wizard-rail"></div>
      <div class="rs-wizard-stepcard">
        <div class="reporting-simple-wizbar">
          <button id="rsWizardBack" class="reporting-link" data-testid="rs-wizard-back">&larr; {{ _("Back") }}</button>
        </div>
        …the four unchanged .reporting-simple-step divs…
      </div>
    </div>
  </div>
```

(`rsWizardClose2` is a second close affordance; the original `rsWizardClose` keeps its id/testid so existing close tests pass. Wire `rsWizardClose2` to the same handler.)

- [ ] **Step 4 — Rail renderer.** In `templates/js/_reporting_simple_js.html` add `renderWizardRail()` and call it from every point that switches the visible step (anchor: Grep how steps are shown/hidden — the function(s) toggling `rsStepMeasure/Scope/Breakdown/Time` `hidden`; add the call at each). The renderer:

```js
  var WIZ_STEPS = [
    { id: 'rsStepMeasure',   label: I18N.wizMeasure },   // "Measure"
    { id: 'rsStepScope',     label: I18N.wizScope },     // "Processes"
    { id: 'rsStepBreakdown', label: I18N.wizBreakdown }, // "Breakdown"
    { id: 'rsStepTime',      label: I18N.wizTime }       // "Time range"
  ];
  function wizStepIndex() { /* first WIZ_STEPS entry whose el is not hidden */ }
  function wizSummaries() {
    // one short line per step from existing wiz state: chosen measure labels,
    // "N of M selected" for scope, breakdown field names + grain, time label.
    // Reuse the exact state fields the step renderers read (Grep `state.wiz`).
  }
  function renderWizardRail() {
    var idx = wizStepIndex();
    el('rsWizardStepNo').textContent = I18N.stepNof4.replace('{n}', idx + 1);
    // per step: 28px circle (done ✓ / active number on brand-grad / upcoming
    // number), 2px connector, title, summary line — spec §Wizard values.
    // Below: #rsWizardPreview box with the running sentence
    // (summaries joined with ' · ').
  }
```

Rail markup is built with DOM/innerHTML in the partial's existing style; classes `rs-rail-step`, `rs-rail-dot`, `rs-rail-line`, `rs-rail-title`, `rs-rail-sum`, states via `.is-done`/`.is-active`. All user-visible strings go through the partial's I18N map (add `wizMeasure`, `wizScope`, `wizBreakdown`, `wizTime`, `stepNof4` = `{{ _("Step {n} of 4")|tojson }}`, `wizPreviewTitle`).

- [ ] **Step 5 — CSS** per spec §Wizard: `.rs-wizard-grid { display:grid; grid-template-columns:280px 1fr; gap:40px; max-width:1120px; margin:0 auto; align-items:start; }`; header bar (white band, border-bottom, 16px 40px padding); dot states (done `#eef2ff` bg + `#4338ca` ✓ + `#c7d2fe` border; active brand-grad + white; upcoming white + `#e5e7eb` border + `#9ca3af`); connectors (`#c7d2fe` done / `#e5e7eb` upcoming); `.rs-wizard-stepcard { background:var(--nx-card); border:1px solid var(--nx-border); border-radius:14px; padding:28px 32px; }`; preview box (`#eef2ff` bg, `#e0e7ff` border, 10px radius); step transition 200ms fade/slide on `.reporting-simple-step` (respecting reduced motion — reuse the `.nx-rise` media-query guard pattern).
- [ ] **Step 6 — Run, expect GREEN** (new test + the full wizard flow subset: `-k "wizard"` + fast tier).
- [ ] **Step 7 — Screenshot** → `var/screenshots/redesign-task5-wizard-rail.png`.
- [ ] **Step 8 — Commit:**

```bash
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html static/css/reporting.css tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
feat(reporting): wizard progress rail and studio step layout

Two-column wizard per spec: header bar with step counter, left rail
with per-step status dots, chosen-value summaries and a running
preview sentence, step content in a 14px-radius card. Step ids,
renderers and the click flow are untouched.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 6: Step chips, coverage bars, footer polish

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (coverage chip markup, "n of m picked" counter)
- Modify: `templates/_reporting_simple.html` (group labels in the breakdown step, footer row)
- Modify: `static/css/reporting.css`

**Interfaces:**
- Consumes: Task 5's step-card chrome. The coverage tooltip text/logic (Grep `coverage` in the partial — the sort + tooltip listing providing processes) is kept verbatim.

- [ ] **Step 1 — Chip restyle CSS**: `.reporting-simple-choices` buttons become 999px pills (`padding:8px 16px; 13px`); selected state `1.5px solid var(--nx-accent); background:var(--nx-accent-tint); color:#4338ca; font-weight:600;` with a leading ✓ (`::before` content or an `<i>` the renderer adds — match how selection is currently marked, Grep the selected-class name in the step renderers and key the CSS on it).
- [ ] **Step 2 — Breakdown grouping.** In the breakdown step, render the uppercase 10.5px group labels ("Time", "Document fields", "Or") — the renderer already distinguishes date vs category vs none breakdown kinds (anchor: `kind:'date'|'category'|'none'` handling in `renderBreakdownStep`); emit a label row before each group. The "None — just the total" choice becomes the dashed pill per spec.
- [ ] **Step 3 — Coverage bar chips.** Where the current coverage badge renders `n/5` (anchor: the coverage-chip markup in the breakdown/measure renderers — Grep `coverage` class name), replace the pill with the in-chip 26×4px progress bar + `n/m` in matching color (fill `var(--nx-accent)` ≥80%, `#b45309` partial, `#94a3b8` ≤33%). Keep the existing tooltip attribute untouched.
- [ ] **Step 4 — Footer.** Move each step's Continue button into a footer row inside the step card (`border-top:1px solid var(--nx-divider); padding-top:20px; margin-top:30px`): Back (ghost, the existing `rsWizardBack`) · spacer · picked-counter span (`#rsPickedCount` — breakdown step only: "{n} of 3 picked") · Continue (existing `rs*Next` buttons restyled gradient with a trailing →). **Do not change button ids or their handlers** — this is DOM placement (template) + CSS only; the picked-counter updates inside the breakdown renderer.
- [ ] **Step 5 — Verify**: full wizard e2e subset green; screenshot → `var/screenshots/redesign-task6-wizard-chips.png`.
- [ ] **Step 6 — Commit:**

```bash
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html static/css/reporting.css
git commit -F - <<'EOF'
feat(reporting): wizard chip pills, coverage bars, step footer

Choice chips become studio pills with a check on selection, breakdown
choices group under uppercase labels, the n/5 coverage pill becomes an
in-chip progress bar with thresholds, and each step gains the
Back / picked-counter / gradient-Continue footer. Ids and handlers
unchanged.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 4 — Result view

### Task 7: Result header regroup (+ ⋯ menu)

**Files:**
- Modify: `templates/_reporting_simple.html` (result bar restructure)
- Modify: `templates/js/_reporting_simple_js.html` (menu toggle, meta line, inline title edit)
- Modify: `static/css/reporting.css`
- Test: `tests/e2e/test_reporting_simple.py` (append + update affected tests)

**Interfaces:**
- Produces: `#rsResultMeta` ("2 rows · 765 ms · run just now"), `#rsMore` (`data-testid="rs-more"`) opening `#rsMoreMenu` (contains the **unchanged** `rsOpenAdvanced` + `rsShowSql` buttons), `rsSave` restyled primary, Export group. `#rsBack` becomes the bordered "← Library"-style button.
- Consumes: run timing values (Grep where `#reportingTiming` is set — same numbers feed `#rsResultMeta`).

- [ ] **Step 1 — Failing e2e:**

```python
def test_result_more_menu_holds_advanced_and_sql(nexora_server, page):
    # open a saved report exactly like the existing openReport tests
    ...
    expect(page.get_by_test_id("rs-open-advanced")).to_be_hidden()
    page.get_by_test_id("rs-more").click()
    expect(page.get_by_test_id("rs-open-advanced")).to_be_visible()
```

- [ ] **Step 2 — Run, expect RED.** Also list the tests to update: `git grep -n "rs-open-advanced\|rs-show-sql" -- tests/e2e/` — every hit that clicks either control inside the *result* view gains a `page.get_by_test_id("rs-more").click()` line first (the error-state `rs-error-open-advanced` hits are NOT touched).
- [ ] **Step 3 — Template.** Restructure `.reporting-simple-resultbar`: back button + title-block (`rsResultTitle` with pencil icon; clicking swaps in the existing `rsSaveName` input for inline rename; `#rsResultMeta` under the title) + spacer + `rsAdjustWizard` ("Adjust") + export group (`rsExportFormat`+`rsExport` in one `.rs-export-group`, perm-gated as today) + `rsSave` (now `nx-btn--primary`) + `#rsMore` (⋯) + `#rsMoreMenu` (absolutely-positioned card holding `rsOpenAdvanced` and `rsShowSql` as menu rows) + `rsExit` (×). **Every existing id/testid stays in the DOM.**
- [ ] **Step 4 — JS.** Menu open/close (click toggles, outside-click + Escape close); populate `#rsResultMeta` where the run success handler currently updates `#reportingTiming` (same rowCount/ms values + `I18N.runJustNow`); pencil click focuses the rename input (reuse the existing rename/save-name flow — Grep `rsSaveName` handlers; do not build a second rename path).
- [ ] **Step 5 — CSS** per spec §Result header + mock `1e`: header as white band; `.rs-export-group` as one bordered control; primary Save gradient with `0 2px 8px -2px rgba(79,70,229,.45)`; `.rs-more-menu` card (`border-radius:10px; box-shadow; min-width:180px`).
- [ ] **Step 6 — Run**: new test + updated tests + fast tier → GREEN.
- [ ] **Step 7 — Commit:**

```bash
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html static/css/reporting.css tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
feat(reporting): studio result header with overflow menu

Result bar per spec: bordered back button, inline-editable title with
rows/ms/recency meta line, Adjust, unified Export group, gradient Save
and a new overflow menu that now hosts Open-in-Advanced and Show-query
(ids unchanged; affected e2e tests open the menu first).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 8: Result body — KPI rail, chart card, table card, query peek

**Files:**
- Modify: `templates/_reporting_simple.html` (body regroup: left rail + right chart column, table card wrapper)
- Modify: `templates/js/_reporting_simple_js.html` (`renderKpiBand` gains Peak; layout classes)
- Modify: `static/css/reporting.css`

**Interfaces:**
- Consumes: existing `renderKpiBand` (ids `rs-kpi-total/-buckets/-avg` — Grep the exact ids it writes), `rsChartTools`, `rsTableWrap`, `rsSqlPeek`, `rsDrillHint`.
- Produces: `.rs-result-grid` (250px + 1fr), gradient total card, secondary stats card with new Peak row (`#rsKpiPeak`), chart-type segmented control, table card head ("Table · N rows" + drill hint) with the query-peek footer inside the card.

- [ ] **Step 1 — Template regroup:** wrap `rsStatCard`/`rsKpiBand` into a left column and `rsChartCard` into the right of a new `.rs-result-grid`; `rsTableToggle`, `rsTableWrap`, `rsSqlPeek`, `rsDrillHint` regroup into a `.rs-table-card` below (head row: "Table" + row count + drill hint right-aligned; `rsSqlPeek` becomes the card's footer button). No id changes.
- [ ] **Step 2 — KPI restyle + Peak.** `renderKpiBand` additionally computes Peak (max metric bucket: label + value) and renders the three secondary rows (Buckets / Avg per bucket / Peak) into the stacked card; the primary total renders into the gradient card (`background:var(--nx-brand-grad); color:#fff; border-radius:14px; box-shadow:0 12px 28px -10px rgba(79,70,229,.5);` value 38px/-1.5px). Zero-dimension runs keep using `rsStatCard` as today.
- [ ] **Step 3 — Chart segmented control:** restyle `#rsChartTools` as the segmented track (reuse Task 1's pattern at `.reporting-simple-charttools` specificity); active type gets the white segment. The PNG-download button stays right-aligned outside the track.
- [ ] **Step 4 — CSS** for `.rs-result-grid`, cards at 14px radius, table card head, query-peek footer (Task 2 already restyled `.reporting-ledger-sqlpeek` — ensure it sits flush as card footer: full-width, `border-top`, left-aligned, ellipsis).
- [ ] **Step 5 — Verify:** fast tier green (KPI band tests key on `rs-kpi-*` testids — extend, don't rename); screenshots light mode → `var/screenshots/redesign-task8-result.png`.
- [ ] **Step 6 — Commit:**

```bash
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html static/css/reporting.css
git commit -F - <<'EOF'
feat(reporting): studio result body with KPI rail and table card

Result body per spec: gradient total card + stacked Buckets/Avg/Peak
stats on the left rail, chart card with a segmented type switcher,
table card with head row, drill hint and the query-peek footer.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 5 — Drill-through drawer

### Task 9: Drawer restyle + context chips

**Files:**
- Modify: `templates/reporting.html` (drawer head: icon chip; context chip row container `#rdChips`)
- Modify: `templates/js/_reporting_drill_js.html` (populate `#rdChips` from the drill definition)
- Modify: `static/css/reporting.css`
- Test: `tests/e2e/` (append to the file that exercises the drill drawer — Grep `reporting-drill-panel` under `tests/e2e/`)

**Interfaces:**
- Consumes: `ReportingDrill.open(opts)` / `buildDrillDefinition` (filters array on the built definition).
- Produces: `#rdChips` (`data-testid="reporting-drill-chips"`) — indigo chips for definition filters, violet chips for the clicked-cell filters; Task 15 reuses this exact surface for dashboard-card drills.

- [ ] **Step 1 — Failing e2e:** drill open (copy an existing drill test's stub + click path), then `expect(page.get_by_test_id("reporting-drill-chips")).to_be_visible()` and chip count ≥1.
- [ ] **Step 2 — Template:** in the drawer head add the 36px icon chip (`fa-magnifying-glass-chart` on `--nx-accent-tint`); after the head insert `<div id="rdChips" class="reporting-drill-chips" data-testid="reporting-drill-chips"></div>`; the footer note + CSV/XLSX buttons stay (ids `rdNote`, `rdExportCsv`, `rdExportXlsx`).
- [ ] **Step 3 — JS:** where the drawer fills `#rdTitle`/`#rdSubtitle` (anchor: Grep `rdSubtitle` in `_reporting_drill_js.html`), also render chips: one indigo chip per pre-existing definition filter (`field · value`), one violet chip per clicked-derived filter (the `clicked` array). Icons: `fa-calendar` for date/grain fields, `fa-filter` otherwise. Add an info callout div (`.reporting-drill-callout`, eye icon, spec §Drill text) above the footer when the workitem-preview modal is available (Grep the flag/perm the drill module already checks before wiring workitem links).
- [ ] **Step 4 — CSS** per spec §Drill: width 640px, backdrop `rgba(15,23,42,.28)`, shadow `-24px 0 64px -24px rgba(15,23,42,.35)`, slide-in 250ms, chip styles (indigo `--nx-accent-tint`/`#e0e7ff`/`#4338ca`; violet `--nx-violet-tint`/`--nx-violet-border`/`--nx-violet`), uppercase 10px table header, workitem-id links indigo underlined, type as indigo-tint pill, callout card.
- [ ] **Step 5 — Verify:** new + existing drill tests green; screenshot with open drawer → `var/screenshots/redesign-task9-drill.png`.
- [ ] **Step 6 — Commit:**

```bash
git add templates/reporting.html templates/js/_reporting_drill_js.html static/css/reporting.css tests/e2e
git commit -F - <<'EOF'
feat(reporting): studio drill drawer with filter context chips

640px drawer per spec: icon-chip header, indigo/violet context chips
built from the drill definition and clicked cell, info callout, styled
document table. Export buttons and ids unchanged.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 6 — Advanced builder skin

### Task 10: Advanced reskin (CSS + field-type icons)

**Files:**
- Modify: `static/css/reporting.css` (Advanced chrome)
- Modify: `templates/js/_reporting_js.html` (field-row icon + hover "+"; wells chip classes if missing)

**Interfaces:**
- Consumes: the Advanced grid (260/1fr/300), field-list renderer (Grep the function that renders source fields into the left panel), wells renderers (metrics/columns/filters/sort).

- [ ] **Step 1 — Panels + toggles CSS:** panels → `border-radius:var(--nx-radius-lg)`, token borders/cards (Task 2 removed ledger flatness — fill the gap here); mode toggle (Table/SQL/Ask-AI) and view toggle (Grid/Chart/Pivot) restyled as segmented tracks (same classes as Task 1's pattern — key on their existing container class names, Grep them); Run keeps the gradient; layout grid untouched.
- [ ] **Step 2 — Field rows:** in the field-list renderer add a leading type icon `<i>` (`#a5b4fc`): `fa-calendar` for date-typed fields, `fa-hashtag` numeric, `fa-font` text (field type is in the catalog rows the renderer consumes — Grep the field descriptor's type property); CSS adds the trailing `+` affordance on row hover (`.fa-plus` via `::after` or a hidden `<i>` shown on hover) + `--nx-accent-tint` hover bg.
- [ ] **Step 3 — Wells:** metric entries as indigo chips, filter entries as violet chips, column entries as draggable rows with `fa-grip-vertical` grips (grip icon is display-only if no reorder exists today — do not add reorder behavior), dashed "+ Add …" buttons per spec §Advanced.
- [ ] **Step 4 — Verify:** Advanced e2e files green (`test_reporting.py`, `test_reporting_viz.py`, `test_reporting_sql.py`, `test_reporting_save.py`, `test_reporting_agent.py`); screenshot → `var/screenshots/redesign-task10-advanced.png`.
- [ ] **Step 5 — Commit:**

```bash
git add static/css/reporting.css templates/js/_reporting_js.html
git commit -F - <<'EOF'
feat(reporting): advanced builder studio skin

Panels on studio tokens, segmented mode and view toggles, field rows
with type icons and hover add affordance, wells as indigo/violet chips
with dashed add buttons. Layout grid and all behavior unchanged.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 7 — Dashboard builder

### Task 11: Dashboard module skeleton — open/save/close + library routing

**Files:**
- Create: `templates/js/_reporting_dashboard_js.html`
- Modify: `templates/_reporting_simple.html` (`#rsDashboard` view container + include the new partial at the bottom, after the simple JS include)
- Modify: `templates/js/_reporting_simple_js.html` (`setView('dashboard')`, library routing, unhide + wire `#rsNewDashboard`)
- Modify: `templates/js/_reporting_js.html` (exclude dashboards from the saved-reports `<select>`)
- Modify: `static/css/reporting.css` (dashboard shell + header)
- Test: `tests/e2e/test_reporting_dashboard.py` (**new file**)

**Interfaces:**
- Produces: `window.ReportingDashboard = { openNew: function(), open: function(report), close: function() }` (report = the `GET /api/reporting/reports/<id>` payload). Definition contract (D2) — **Tasks 12–15 build on these exact property names:** `{kind:'dashboard', schemaVersion:1, title, globalFilters:[{field,op,value}], cards:[{id, type, span, title, definition, filterOverrides}]}`. Module state: `{editing, dirty, reportId, canEdit, dragId, overId, seq, def}`.
- Produces DOM: `#rsDashboard` (`data-testid="rs-dashboard"`), header (`#rdbBack`, `#rdbTitle` + pencil, `#rdbMeta`, `#rdbEditingPill`, `#rdbAddCard`, `#rdbExport`, `#rdbEditToggle` — testids `rdb-back`, `rdb-title`, `rdb-add-card`, `rdb-export`, `rdb-edit-toggle`), `#rdbFilterBar`, `#rdbGrid`.
- Consumes: Simple pane's `setView`, `api()` (the dashboard partial defines its own identical `api()` — modules are self-contained IIFEs), toast helper (Grep the Simple partial's toast call and reuse the same global if one exists, else the `reporting-toast` element pattern).

- [ ] **Step 1 — Failing e2e** (new file `tests/e2e/test_reporting_dashboard.py`; copy the login/stub scaffolding style from `test_reporting_simple.py`):

```python
def test_new_dashboard_opens_builder_and_saves(nexora_server, page):
    # stubs: catalog + empty library; POST /api/reporting/reports captures body
    saved = {}
    def capture_save(route):
        if route.request.method == "POST":
            saved.update(route.request.post_data_json)
            route.fulfill(json={"id": 42})
        else:
            route.fulfill(json=[])
    page.route("**/api/reporting/reports", capture_save)
    ...
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-dashboard").click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    expect(page.get_by_test_id("rdb-edit-toggle")).to_have_text("Done")  # new dashboards open editing
    page.get_by_test_id("rdb-edit-toggle").click()                       # Done → autosave (D2)
    assert saved["definition"]["kind"] == "dashboard"

def test_dashboard_report_in_library_routes_to_builder(nexora_server, page):
    # library stub returns one report with kind='dashboard'
    ...
    page.get_by_test_id("rs-card").first.click()
    expect(page.get_by_test_id("rs-dashboard")).to_be_visible()
    expect(page.get_by_test_id("rs-result")).to_be_hidden()
```

- [ ] **Step 2 — Run, expect RED.**
- [ ] **Step 3 — View container.** In `templates/_reporting_simple.html`, after the `#rsResult` div's closing tag add:

```html
  <div id="rsDashboard" class="reporting-dashboard" hidden data-testid="rs-dashboard"></div>
```

and at the file bottom, after `{% include 'js/_reporting_simple_js.html' %}`:

```html
{% include 'js/_reporting_dashboard_js.html' %}
```

- [ ] **Step 4 — The module.** Create `templates/js/_reporting_dashboard_js.html` — IIFE with the standard prologue (`API_PREFIX` + `api()` copied from the drill partial's opening lines), private `state`, and the header/filterbar/grid render skeleton. **The prototype's logic class is the spec** — port its state model and handlers 1:1 into module functions (`setCards(fn)`, `toggleEditing`, `addCard(type)`, per-card `remove/duplicate/removeFilter`, `onDragStart/Over/Drop/End`, `addFilter`, filter `cycle` replaced by Task 13's popover). Core skeleton:

```html
{# Dashboard builder (kind:'dashboard' saved reports). State model + handlers
   ported from docs/superpowers/specs/2026-07-20-reporting-dashboard-prototype.dc.html #}
<script>
(function () {
  'use strict';
  const API_PREFIX = window.location.href.includes("nexora") ? "/nexora/" : "/";
  /* api() — copy the drill partial's helper verbatim (CSRF + prefix) */

  var I18N = {
    editing: {{ _("Editing")|tojson }}, edit: {{ _("Edit")|tojson }}, done: {{ _("Done")|tojson }},
    addCard: {{ _("Add card")|tojson }}, export_: {{ _("Export")|tojson }},
    untitled: {{ _("Untitled dashboard")|tojson }},
    cardsMeta: {{ _("{n} cards · drag to rearrange · hover a card for controls")|tojson }},
    globalFilters: {{ _("Global filters")|tojson }}, addFilter: {{ _("Add filter")|tojson }},
    filterHint: {{ _("apply to every card · a card can override them")|tojson }},
    inherits: {{ _("inherits global filters")|tojson }},
    newChart: {{ _("New chart")|tojson }}, newKpi: {{ _("New KPI")|tojson }},
    newTable: {{ _("New table")|tojson }}, newDonut: {{ _("New donut")|tojson }},
    addACard: {{ _("Add a card")|tojson }}, dropHint: {{ _("or drop a saved report here")|tojson }},
    couldNotLoad: {{ _("Could not load this card.")|tojson }},
    saved: {{ _("Dashboard saved")|tojson }}, saveFailed: {{ _("Could not save the dashboard")|tojson }}
  };

  var state = { editing: false, dirty: false, reportId: null, canEdit: true,
                dragId: null, overId: null, seq: 100, def: null };

  function blankDef() {
    return { kind: 'dashboard', schemaVersion: 1, title: I18N.untitled,
             globalFilters: [], cards: [] };
  }
  var DEFAULT_SPAN = { kpi: 3, line: 8, donut: 4, bar: 6, table: 6 };

  function openNew() { state.def = blankDef(); state.reportId = null;
                       state.canEdit = true; state.editing = true; show(); }
  function open(report) {
    state.def = report.definition; state.reportId = report.id;
    state.canEdit = !!report.canEdit; state.editing = false; show();
  }
  function close() { /* hide #rsDashboard; caller switches view */ }
  async function save() {
    var body = { name: state.def.title, definition: state.def };
    var res = state.reportId
      ? await api('/api/reporting/reports/' + state.reportId, { method: 'PUT', body: body })
      : await api('/api/reporting/reports', { method: 'POST', body: body });
    /* on success: reportId = res.data.id when created; toast I18N.saved;
       state.dirty = false. On failure: toast I18N.saveFailed, stay editing. */
  }
  function toggleEditing() {
    if (state.editing && state.dirty) save();
    state.editing = !state.editing; render();
  }
  function render() { renderHeader(); renderFilterBar(); renderGrid(); }
  /* renderHeader/renderFilterBar/renderGrid: DOM per spec §Dashboard; grid
     items delegated to Task 12's renderCard(card). Until Task 12 lands,
     renderGrid draws card shells with title only. */

  window.ReportingDashboard = { openNew: openNew, open: open, close: close };
}());
</script>
```

(Adapt `api()` body-passing to the helper's real signature at execution time — Grep how the Simple partial POSTs JSON.)

- [ ] **Step 5 — Simple-pane wiring.** In `templates/js/_reporting_simple_js.html`:
  - `setView` (anchor: `function setView(view) {`) learns `'dashboard'`: shows `#rsDashboard`, hides library/wizard/result (and vice versa — the three existing branches each hide `#rsDashboard`).
  - Library routing: in the card click path / `openReport` entry (anchor: `function card(r)` click handler → `openReport`), branch first: `if (r.kind === 'dashboard') { openDashboard(r); return; }` where `openDashboard` fetches `GET /api/reporting/reports/<id>` and calls `setView('dashboard'); window.ReportingDashboard.open(payload)`.
  - `#rsNewDashboard`: remove `hidden` in the template; click → `setView('dashboard'); window.ReportingDashboard.openNew()`.
  - Dashboard close → `setView('library'); loadLibrary()` (pass a callback or dispatch a custom event `rs:dashboard-closed` the Simple partial listens for — pick the event: no cross-module function coupling).
  - The library card badge for `kind==='dashboard'` reads "DASHBOARD" with `fa-table-cells-large` (Task 4's `previewKindOf` gains the branch; preview band renders a 2×2 mini-grid glyph instead of a spark).
- [ ] **Step 6 — Advanced exclusion.** In `templates/js/_reporting_js.html`, where the saved-reports `<select>` is filled (anchor: the ` (SQL)` suffix logic), filter out `r.kind === 'dashboard'` entries entirely.
- [ ] **Step 7 — Shell CSS:** `.reporting-dashboard` (max-width 1240px, centered), header band per spec §Dashboard (back button, editable title + pencil, meta line, Editing pill `#eef2ff`/`#c7d2fe`/`#4338ca` + 7px dot, indigo-tint Add-card button, secondary Export, gradient Done/Edit), `#rdbGrid { display:grid; grid-template-columns:repeat(12,1fr); gap:14px; }`.
- [ ] **Step 8 — Run, expect GREEN** (both new tests + fast tier).
- [ ] **Step 9 — Commit:**

```bash
git add templates/js/_reporting_dashboard_js.html templates/_reporting_simple.html templates/js/_reporting_simple_js.html templates/js/_reporting_js.html static/css/reporting.css tests/e2e/test_reporting_dashboard.py
git commit -F - <<'EOF'
feat(reporting): dashboard builder skeleton as kind-dashboard reports

New _reporting_dashboard_js partial (state model ported from the design
prototype) rendering into a fourth Simple-pane view. Dashboards persist
through the existing reports CRUD with kind:'dashboard' definitions —
no backend change. Library cards route dashboards to the builder, the
hero's New-dashboard button goes live, Advanced excludes dashboards
from its saved-reports select.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 12: Card rendering + per-card runs

**Files:**
- Modify: `templates/js/_reporting_dashboard_js.html`
- Modify: `static/css/reporting.css`
- Test: `tests/e2e/test_reporting_dashboard.py` (append)

**Interfaces:**
- Produces: `renderCard(card)` → card DOM (`data-testid="rdb-card"`, `data-card-id`); `effectiveFilters(card)` (D4 merge — Task 13/15 reuse it); `runCard(card, el)` (one `POST /api/reporting/run`, renders by `card.type`).
- Consumes: Task 11 skeleton; Chart.js configs per spec §Dashboard "Cards" (line: `#4f46e5` w2.5 tension .4 no points, 20%→0 gradient fill, y-grid `--nx-divider` only, 10.5px `#9ca3af` ticks; bar: palette `#4f46e5 #6366f1 #7c3aed #8b5cf6 #a5b4fc`, `borderRadius:5`, `barThickness:26`; donut: `cutout:'68%'`, palette + 2px white borders, HTML center overlay total, right/bottom legend 9px swatches; KPI: uppercase 10.5px label, 30px value; table: 2-col grid rows).

- [ ] **Step 1 — Failing e2e:** dashboard report stub with one KPI + one line card; stub `**/api/reporting/run` with distinct payloads (match on `route.request.post_data_json["metrics"]` or card marker); assert the KPI value renders and a `canvas` exists in the line card.
- [ ] **Step 2 — Run, expect RED.**
- [ ] **Step 3 — Implement.** `effectiveFilters(card)`: card.definition.filters ⊕ globalFilters ⊕ filterOverrides (override wins per field — D4). `runCard`: clone `card.definition`, set merged filters, `POST /api/reporting/run`; per-type renderers translate `{columns, rows}` → the Chart.js/DOM shapes above (first column = labels, first metric = values; donut/table cap at 8 rows + "Other" roll-up for donuts). Loading shimmer while pending; `I18N.couldNotLoad` error body on failure (card stays manageable in edit mode). Destroy chart instances before re-render (keep a `charts` map by card id — same destroy-before-recreate discipline as `ReportingViz`).
- [ ] **Step 4 — CSS:** card chrome per spec (12px radius, `padding:14px 18px`, hover border in view mode), KPI/donut-overlay/table styles, `grid-column: span N` per card with responsive collapse (`@media (max-width: 900px)` → all cards span 12).
- [ ] **Step 5 — GREEN + fast tier.** Screenshot with a stub dashboard → `var/screenshots/redesign-task12-cards.png`.
- [ ] **Step 6 — Commit:**

```bash
git add templates/js/_reporting_dashboard_js.html static/css/reporting.css tests/e2e/test_reporting_dashboard.py
git commit -F - <<'EOF'
feat(reporting): dashboard card renderers with per-card runs

KPI, line, bar, donut and table cards render from one /api/reporting/run
per card using merged global+override filters; spec chart styling,
loading and per-card error states, destroy-before-recreate charts.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 13: Global filter bar + per-card overrides

**Files:**
- Modify: `templates/js/_reporting_dashboard_js.html`
- Modify: `static/css/reporting.css`
- Test: `tests/e2e/test_reporting_dashboard.py` (append)

**Interfaces:**
- Produces: filter bar chips (indigo, `data-testid="rdb-gfilter"`), dashed add-filter chip (`rdb-add-filter`), popover editor (`#rdbFilterPop`: field/op/value from the catalog the Simple pane already loads — the dashboard module fetches `GET /api/reporting/sources` + metrics itself, same endpoints), per-card violet override chip (`rdb-card-filter`) with × removal. Removing/adding/editing any filter re-runs affected cards only.

- [ ] **Step 1 — Failing e2e:** add a global filter via popover (stubbed catalog), assert a `rdb-gfilter` chip appears and the run stub was re-hit; remove a card's override chip, assert re-run.
- [ ] **Step 2 — Run, expect RED.**
- [ ] **Step 3 — Implement** per prototype handlers (`addFilter`, chip `remove`; `cycle` becomes "open popover pre-filled"). Popover: positioned under the chip, field `<select>` (filterable fields of the card sources' shared catalog), op `<select>` (reuse the op set the Simple chips use — Grep the Simple partial's chip op list and mirror it), value input (text/date by field type), Apply/Cancel. On apply: update `state.def.globalFilters`, `state.dirty = true`, re-run affected cards (`effectiveFilters` changed ⇒ compare serialized). Per-card chip: shows `filterOverrides` summary, × clears overrides (`state.dirty = true`, re-run that card); "inherits global filters" note when none (KPI cards: note hidden per prototype `showInherit`).
- [ ] **Step 4 — CSS:** bar as white 12px-radius card, uppercase label + violet funnel, vertical divider, chips per spec; popover card (radius 10, shadow, z-index above cards — remember the `.nx-rise` fill-mode trap: the popover must not be buried by an animated ancestor; keep `backwards`).
- [ ] **Step 5 — GREEN + fast tier; commit:**

```bash
git add templates/js/_reporting_dashboard_js.html static/css/reporting.css tests/e2e/test_reporting_dashboard.py
git commit -F - <<'EOF'
feat(reporting): dashboard global filters and per-card overrides

Global filter bar with indigo chips and a field/op/value popover
editor; violet per-card override chips with removal; edits mark the
definition dirty and re-run only the affected cards.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 14: Edit mode — DnD reorder, add/duplicate/remove, add-card tile

**Files:**
- Modify: `templates/js/_reporting_dashboard_js.html`
- Modify: `static/css/reporting.css`
- Test: `tests/e2e/test_reporting_dashboard.py` (append)

**Interfaces:**
- Produces: edit-mode chrome (grips, hover control cluster `rdb-card-dup`/`rdb-card-remove`, draggable cards), add-card tile (`rdb-add-tile` + type pills), reorder persisted in `state.def.cards` order.
- Consumes: prototype handlers verbatim (D10).

- [ ] **Step 1 — Failing e2e:** in edit mode, `page.locator('[data-card-id="k1"]').drag_to(page.locator('[data-card-id="c1"]'))` then Done → captured PUT body's card order changed; duplicate → card count +1; remove → −1; add-card tile "KPI" pill → a new KPI card shell appears.
- [ ] **Step 2 — Run, expect RED.** (If Playwright's `drag_to` doesn't fire HTML5 DnD reliably, dispatch `dragstart/dragover/drop` events via `page.evaluate` — note it in the test.)
- [ ] **Step 3 — Implement** exactly per the prototype: dragstart sets `state.dragId` + `.35` opacity; dragover sets `overId` (indigo border + `0 0 0 3px rgba(79,70,229,.15)` ring on target); drop splices source before target; dragend clears. Control cluster at `top:-11px; right:10px` (22px white squares, clone + red xmark) on card hover in edit mode. Add-card tile as last grid item (span 6, 2px dashed, plus circle, four type pills, drop hint). New cards get `DEFAULT_SPAN[type]`, a fresh `'n' + state.seq++` id, and an **empty definition placeholder** `{source: null, metrics: [], columns: [], filters: []}` rendering as a "configure this card" body — v1 card configuration = pick a saved report: clicking the placeholder opens a simple list of the user's saved non-SQL reports (from the already-loaded library data via a `GET /api/reporting/reports` call) and adopting one copies its definition into the card (`card.definition = report.definition`, title = report name). All mutations set `state.dirty`.
- [ ] **Step 4 — "Drop a saved report here":** library cards are NOT draggable across views (they live in another DOM state) — the tile hint text stays (spec), the affordance is the click-to-pick list above. (Deviation noted in Gotchas.)
- [ ] **Step 5 — GREEN + fast tier; screenshot edit mode → `var/screenshots/redesign-task14-edit.png`; commit:**

```bash
git add templates/js/_reporting_dashboard_js.html static/css/reporting.css tests/e2e/test_reporting_dashboard.py
git commit -F - <<'EOF'
feat(reporting): dashboard edit mode with drag reorder and card CRUD

HTML5 drag-to-rearrange per the prototype handlers, hover control
cluster (duplicate/remove), add-card tile with type pills; new cards
adopt a saved report's definition via a picker. Done autosaves the
reordered definition.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 15: KPI trends, card drill-through, Export

**Files:**
- Modify: `templates/js/_reporting_dashboard_js.html`
- Test: `tests/e2e/test_reporting_dashboard.py` (append)

**Interfaces:**
- Consumes: `ReportingDrill.open(opts)` (Task 9's chips), `effectiveFilters`, `/api/reporting/export` (definition → download), D8/D9.

- [ ] **Step 1 — Failing e2e:** clicking a line-card point opens `reporting-drill-panel` (stub the drill run); Export menu lists card titles; picking one hits a stubbed `**/api/reporting/export`.
- [ ] **Step 2 — Run, expect RED.**
- [ ] **Step 3 — KPI trend (D8):** when a KPI card's effective filters hold exactly one date-range filter, clone the def with the range shifted back one equal period, second run, render `+x.y% vs previous period` (`--nx-success` + `fa-arrow-trend-up` / `--nx-danger` + down); otherwise no trend line. Period shift helper is pure — mirror how the Simple pane parses its relative date tokens (Grep the token names in the Simple partial; if the filter value is a token like `this_year`, map to `last_year` where a sibling token exists, else shift literal dates).
- [ ] **Step 4 — Drill:** chart-element / table-row clicks build `clicked` the same way the Simple pane does for its charts (Grep the Simple pane's chart `onClick` → `ReportingDrill.open` call and mirror: definition = card def with merged filters, fields = catalog, clicked = [{field, grain, value}], header = card title).
- [ ] **Step 5 — Export (D9):** `#rdbExport` opens a menu of card titles; picking one POSTs the card's effective definition to `/api/reporting/export` and downloads (mirror the Simple pane's export fetch → blob → anchor-click code; xlsx only v1). Button perm-gated: render only when the page exposes export permission (Grep how `_reporting_simple.html` gates `#rsExport` — `has_permission('reporting.export')` — and mirror the Jinja guard around the button markup in the dashboard header, which lives in `_reporting_simple.html`'s `#rsDashboard`... the header is JS-rendered, so gate via a Jinja-set flag: add `data-can-export="{{ 1 if has_permission('reporting.export') else 0 }}"` on `#rsDashboard` and read it in the module).
- [ ] **Step 6 — GREEN + full dashboard file + fast tier; commit:**

```bash
git add templates/js/_reporting_dashboard_js.html templates/_reporting_simple.html tests/e2e/test_reporting_dashboard.py
git commit -F - <<'EOF'
feat(reporting): dashboard KPI trends, drill-through and export

KPI cards compare against the previous period when a single date-range
filter applies; chart and table clicks open the shared drill drawer
with merged filter context; header Export downloads any card via the
existing export endpoint, permission-gated.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 8 — Dark mode + chores

### Task 16: Dark-mode pass

**Files:**
- Modify: `static/css/reporting.css` (one `html.dark` section for the redesign)
- Modify: `templates/js/_reporting_dashboard_js.html` (dark-aware chart grid/tick colors)

- [ ] **Step 1 — Sweep every hex introduced by Tasks 1–15** (`git diff main -- static/css/reporting.css | grep -i "#[0-9a-f]"`): anything not already a token gets an `html.dark` override per spec §Dark (mock `3c`): page `#0f172a`, cards `#1e293b`, borders `#334155`, text `#e2e8f0`, indigo accents → `#818cf8`, violet → `#a78bfa`, indigo chips `#312e81` bg + `#c7d2fe` text, hero radial → `rgba(49,46,129,.55) → #1e293b`, gradient buttons → `linear-gradient(135deg,#818cf8,#a78bfa)` with dark text per mock. Chart tick/grid colors: the JS reads a `isDark = document.documentElement.classList.contains('dark')` flag where charts are built (dashboard module + any hardcoded `#f3f4f6` grid in new configs) — grid `#273449`, ticks `#64748b` when dark.
- [ ] **Step 2 — Verify** in-browser both modes (toggle the app's dark switch — Grep how other pages toggle `html.dark`); screenshots → `var/screenshots/redesign-task16-dark-{landing,dashboard,result}.png`.
- [ ] **Step 3 — Fast tier green; commit:**

```bash
git add static/css/reporting.css templates/js/_reporting_dashboard_js.html
git commit -F - <<'EOF'
style(reporting): dark-mode pass over the studio redesign

html.dark overrides for every non-token color the redesign introduced
(hero, cards, chips, gradients, dashboard) and dark-aware chart grid
and tick colors, per the spec's dark mock.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 17: i18n, changelog, docs, supersede stamp, full verify

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`)
- Modify: `CHANGELOG.md`, `docs/howto/reporting.md`, `docs/superpowers/plans/2026-07-15-reporting-pin-to-dashboard.md` (supersede stamp)

- [ ] **Step 1 — Babel cycle** (repo root):

```powershell
.\.venv\Scripts\pybabel.exe extract -F babel.cfg -o messages.pot .
.\.venv\Scripts\pybabel.exe update -i messages.pot -d translations
```

Translate every new msgid non-fuzzy in de/fr/it (hero strings, suggestions, wizard rail labels, dashboard I18N block, drill callout, empty-group lines, …). **Trap:** `pybabel update` silently mangles malformed msgstr lines — diff-sweep existing msgstr content after the update (`git diff translations/ | grep '^-msgstr'` must show nothing unexpected). Then `.\.venv\Scripts\pybabel.exe compile -d translations`.

- [ ] **Step 2 — Changelog** under `## [Unreleased]`:

```markdown
### Added
- Reporting: multi-card dashboards — a new `kind:'dashboard'` saved-report type
  built in the Simple pane: KPI / line / bar / donut / table cards over the
  existing run endpoint, global filters with per-card overrides, drag-to-
  rearrange, add/duplicate/remove, Edit/Done with autosave, per-card export
  and drill-through. No schema change.

### Changed
- Reporting: full "Indigo Studio" redesign — landing hero with AI command bar
  and live-preview report cards, progress-rail wizard, refined result view
  with overflow menu, restyled drill drawer and Advanced builder, dark mode.
  The Editorial Ledger serif/mono skin is retired; all ids and testids kept.
```

- [ ] **Step 3 — Docs.** `docs/howto/reporting.md`: update the Simple-tab description (hero, cards, wizard rail), add a **Dashboards** section (what a dashboard is, D2 definition shape, access model = the normal reports sharing model, per-card runs, export). Stamp the pin plan: prepend to `docs/superpowers/plans/2026-07-15-reporting-pin-to-dashboard.md` line 2: `> **SUPERSEDED (2026-07-20):** replaced by docs/superpowers/plans/2026-07-20-reporting-redesign-dashboard-builder.md (owner decision — dashboard builder covers the need).`
- [ ] **Step 4 — Full verify:**

```powershell
.\.venv\Scripts\python scripts\test_db_reset.py
.\.venv\Scripts\python -m pytest tests --ignore=tests/e2e -q
.\.venv\Scripts\python -m pytest tests/e2e -q -k "reporting"
```

Expected: all green including `test_translations.py`.

- [ ] **Step 5 — Live pass.** `nx -r`, login as ben.streich, walk: landing → suggestion chip → wizard end-to-end → save → reopen from card (preview now real) → new dashboard → add cards from saved reports → filters → drag → Done → reopen → drill → export. Screenshots of each surface → `var/screenshots/redesign-final-*.png`. Send them to the owner.
- [ ] **Step 6 — Commit:**

```bash
git add messages.pot translations CHANGELOG.md docs/howto/reporting.md docs/superpowers/plans/2026-07-15-reporting-pin-to-dashboard.md
git commit -F - <<'EOF'
docs(reporting): redesign changelog, howto, i18n and supersede stamp

Changelog entries for the Indigo Studio redesign and the dashboard
builder, a Dashboards section in docs/howto/reporting.md, the pybabel
cycle for all new strings (de/fr/it, non-fuzzy, msgstr diff-swept),
and the pin-to-dashboard plan stamped superseded.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

## Gotchas & notes

- **The 64 000-char `DefinitionJSON` cap** (anchor: `if len(definition_json) > 64_000:` in `api_reports_create`, same check in update) bounds dashboard size at roughly 10–15 cards with embedded definitions — plenty for v1. If a save 400s on size, the toast shows the server error; no client-side pre-check in v1 (ponytail: add one only if someone actually hits it).
- **Concurrent dashboard edits** last-write-wins, like every other saved report. Acceptable v1.
- **`renderLibrary` group order changes** (My reports first) — if an e2e test asserts Library-first order, updating it is legitimate (presentational).
- **The dashboard header lives inside JS-rendered DOM** — Jinja perm gates can't wrap it directly; permission flags ride on `#rsDashboard` data attributes (Task 15's `data-can-export` pattern; `canEdit` comes from the report payload).
- **"Drop a saved report here"** is v1-approximated by the click-to-pick list (Task 14 Step 4) — real cross-view HTML5 drag of a library card is an upgrade path, not spec-mandatory (the prototype doesn't implement it either).
- **Chart instance leaks:** every dashboard re-render must destroy Chart instances first (`charts` map) — same discipline as `ReportingViz.destroyChart`; forgetting this makes DnD reorder leak canvases.
- **`.nx-rise` fill-mode `backwards` only** — the dashboard grid and filter popover must never sit inside an ancestor with `animation-fill-mode: both` (stacking-context trap that has bitten twice).
- **`prefers-reduced-motion`** is globally handled for `.nx-rise*`; new transitions (drawer slide, step fade, card hover lift) must sit behind the same media-query guard pattern used in `nexora-ui.css`.
- **The e2e suite is the contract:** 61 tests key on `rs-*` testids. Any test change in this plan is presentational-only (menu-open step, group order); if a *flow* test goes red, the implementation is wrong — fix the code, not the test.
- **Suggestion chips are static i18n strings** (D16 area) — they only prefill the prompt; no backend registry of suggestions (YAGNI).
- **Preview cache staleness:** `nx.reporting.preview.<id>` is refreshed on every successful run and keyed by report id — a definition edit without a re-run shows the previous shape until the next run. Acceptable (thumbnails are a hint, and `ts` allows a future TTL).
- **Dark-mode chart colors** are read at chart-build time (Task 16) — toggling dark mode with a dashboard open re-themes on next render, not live. Acceptable v1.
