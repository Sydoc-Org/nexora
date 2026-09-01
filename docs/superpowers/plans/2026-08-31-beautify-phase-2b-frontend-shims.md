# Beautification Phase 2b — shim-ification and the reporting_simple split — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Distilled from the 2026-08-31 five-agent audit (frontend agent measured every file); anchors are symbol/function names — re-Grep before editing, **Phase 1's nx_core.js work will have edited these files.**

**Prerequisite:** Phase 0+1 executed (nx_core.js exists and is loaded from `_header.html`; generali CRUD partials already converted by its Task 15). Shared context: the Phase 0+1 plan's "Context an engineer needs". **Migrations needed: NO.**

**Goal:** Enforce the #191 shim convention across the big partials (~5,500 movable lines out of templates) and break the 4k-line `static/js/reporting_simple.js` monolith into 5 ordered files. No bundler exists and none is added — script order via `{% include %}` + `static_v()` tags is the module system.

**Architecture:** Each converted page keeps a thin inline shim (`<script nonce>`) holding ONLY Jinja-rendered data and translated strings on `window`; behaviour moves to `static/js/<name>.js`. `reporting_simple.js` converts its closure to a `window.RS` namespace so clusters can live in separate files.

---

## Decisions locked in

| # | Decision | Rationale |
|---|---|---|
| D1 | **Widen the i18n lint BEFORE any move**: `tests/unit/test_reporting_i18n_lint.py` scans `templates/js/_reporting*.html` only — extend it to `static/js/reporting*.js` first, or moving code silently removes it from the hardcoded-English guard. | Audit-flagged; the guard must never gap. |
| D2 | Translated strings stay in shims (`babel.cfg` extracts from `templates/**.html` only); `.js` reads them off `window.NX_I18N_*` maps. | House convention, already proven by `_reporting_simple_js.html`. |
| D3 | The Simple↔Advanced duplicated functions (`fireCaption`, `computeKpiBand`, drill trio, …) stay duplicated. | The authors chose it deliberately (documented in-code); the two sides hold different state shapes. Explicitly out of scope. |
| D4 | `window.RS` namespace: file 1 declares `window.RS = window.RS || {}`; later files read/write `RS.state`, `RS.el`, `RS.esc`, `RS.api`, `RS.I18N`. Load order in `_reporting_simple_js.html` is authoritative. | No bundler; plain ordered scripts. |

# PHASE A — guards first

### Task 1: Widen the i18n lint

- [ ] Extend `test_reporting_i18n_lint.py` to scan `static/js/reporting*.js` (and the files this plan creates) with the same hardcoded-English rules.
- [ ] Run it — must stay green pre-move. Commit: `test(i18n): extend the reporting hardcoded-string lint to static/js`.

# PHASE B — shim-ification (one page per task, biggest first)

Per page, the recipe: create `static/js/<name>.js` with the behaviour; shrink the partial to a data/i18n shim; load via `static_v()` after `nx_core.js`; verify zero `{{ }}` in the .js (`test_no_jinja_syntax_in_static_js` enforces); browser pass + targeted tests; commit `refactor(js): shim-ify <page> per #191`.

- [ ] Task 2: `templates/js/_workitems_overview_js.html` → `static/js/workitems_overview.js` (~1,650 movable, only ~34 Jinja lines — cheapest big win). Gate: workitems integration tests + overview browser pass (filters, pagination, detail panel opening).
- [ ] Task 3: `templates/js/_reporting_js.html` (Advanced tab) → `static/js/reporting_advanced.js` (~1,900 movable; build the `NX_I18N_REPORTING_ADVANCED` map for its ~72 scattered `_()` calls, several mid-expression). Gate: reporting e2e + Advanced-tab browser pass.
- [ ] Task 4: `templates/js/_workitem_detail_panel_js.html` → `static/js/workitem_detail_panel.js` (~780; shared renderer — verify BOTH including pages: workitems + dashboard).
- [ ] Task 5: `templates/js/_reporting_viz_js.html` → `static/js/reporting_viz.js` (~740) and `templates/js/_generali_reporting_js.html` → `static/js/generali_reporting.js` (~860).
- [ ] Task 6: `templates/js/admin/_access_control_js.html` → `static/js/admin_access_control.js` (~1,150). Gate: access-control browser pass (grant/revoke round-trip on a test user).

# PHASE C — reporting_simple.js split

### Task 7: RS namespace + chart pilot

- [ ] Convert the single IIFE's shared closure surface to `window.RS` (D4) in place — no file moves yet; run reporting e2e to prove equivalence.
- [ ] Extract the chart trio into `static/js/reporting_simple_chart.js`: zero-fill cluster (pure, zero `state.` refs — the pilot), chart config/`renderChart`, `buildChartData`/`mountChart`.
- [ ] Update `_reporting_simple_js.html` script order: i18n shim → nx_core → chart → core.
- [ ] Commits: `refactor(js): introduce the RS namespace in reporting_simple` / `refactor(js): extract reporting_simple_chart.js`.

### Task 8: Library, result, wizard

- [ ] `reporting_simple_library.js` (card grid, preview SVGs, load/open — ~440).
- [ ] `reporting_simple_result.js` (KPI band, anomalies, drill, table — ~750).
- [ ] `reporting_simple_wizard.js` (chip editors + 4-step wizard — ~1,240; heaviest `state` coupling, do last).
- [ ] Core file retains state/`runCurrent`/save/init + the `window.ReportingSimple = {` export (consumed by `_reporting_ai_js.html` and `_reporting_tabs_js.html` — keep every exported name).
- [ ] Full reporting e2e + browser pass: build a report through the wizard, run, edit chips, save, reload.
- [ ] Commits: one per extracted file.

### Task 9: Docs & wrap-up

- [ ] `CHANGELOG.md`; CLAUDE.md's #191 line updated (the "three biggest partials are shims" count is now wrong in the good direction). Full gate green.
- [ ] Commit: `docs: sync docs for phase 2b shim-ification`.

## Gotchas & notes

- **Restart the dev server before every browser verification** — Jinja caches templates per process.
- Scripts have no `url_for()` — URLs via `window.API_PREFIX` (nx_core). The prefix lint (`test_template_url_prefix.py`) fails hard on violations.
- The reporting AI-flow e2e race: stub `/api/reporting/run` or chips vanish mid-test (known, memory-documented).
- `_reporting_simple_js.html`'s i18n shim must stay the FIRST script so `window.NX_I18N_REPORTING_SIMPLE` exists before any RS file runs.
- CSP: new `static/js/*.js` files are covered by `script-src 'self'` — no CSP change; inline shims keep their `nonce`.
