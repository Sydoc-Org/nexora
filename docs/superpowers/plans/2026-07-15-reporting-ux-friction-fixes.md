# Reporting UX Friction Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Single-session planning run (recon → draft → self-red-team); **every file path, symbol, and quoted snippet below was Grep/Read-verified against `feature/2.5.64` HEAD (`625147e`) on 2026-07-15** — trust the anchors, but re-Grep before editing (this plan quotes code, never line numbers).

**Spec:** `docs/superpowers/specs/2026-07-15-reporting-ux-friction-design.md` (committed `625147e`). The spec is the contract; this plan is the route.

**Goal:** Six UX fixes on the reporting page so the everyday Simple-tab path stops dead-ending: real error reasons with a working escape hatch, an explanatory zero-row state, Back that returns where you came from, a wizard that shows the range it will run, drill-drawer rows that open the workitem detail panel in place, and an agent surface whose failures teach and offer a retry.

**Architecture:** Pure frontend behavior changes in the Simple pane partial (`templates/js/_reporting_simple_js.html`), the shared drill drawer (`templates/js/_reporting_drill_js.html`), and the AI surface partial (`templates/js/_reporting_ai_js.html`) — plus one small server-side pure helper (`humanize_sql_error` in `nx_lib/reporting/sandbox.py`) wired into the AI toolbox error choke point (`nx_lib/reporting/ai_tools.py`) and one line added to the agent system prompt (`nx_lib/reporting/ai.py`). The drill-drawer workitem panel reuses the shared `NexoraWorkitemDetail` renderer exactly the way the Prepared Documents preview modal does. No new endpoints, no schema change.

**Tech Stack:** Vanilla-JS Jinja partials, flatpickr (already loaded), pytest unit/integration, Playwright e2e (network-stub pattern), Flask-Babel de/fr/it.

---

## Context an engineer needs (read first)

- **Branch:** work directly on `feature/2.5.64` (no worktree). **Commit per task. Do NOT `git push`, do NOT open a PR** — push was authorized for the session owner-level flow; the orchestrating session handles it after review, not task executors.
- **Two stray untracked files** (`package.json`, `package-lock.json` at repo root) predate this plan — never `git add` them.
- **Python for tests:** `C:\dev\nexora\.venv\Scripts\python -m pytest …`. The dev server (`nx -u`) runs global Python — the `.venv` is test-only.
- **Anchor on quoted snippets + function names, NEVER line numbers.** Re-`Grep` a snippet if it has moved.
- **TDD:** backend tasks strict RED→GREEN. Frontend tasks write the failing Playwright e2e first where the behavior is stubbable; pure-display details are covered by the e2e assertions listed per task.
- **TEST env has NO Statistics DB** — reporting runs can never execute for real in e2e. Use the established network-stub helpers in `tests/e2e/test_reporting_simple.py` (`_stub_run_ok(page)` and `page.route("**/api/reporting/run", …)` **before** `page.goto`). The known race: never let a Simple-pane AI flow hit the real `/api/reporting/run` — `showResultError` tears down chips/refine mid-test.
- **Before running any e2e tier:** `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py`.
- **Jinja template cache is process-lifetime** — restart the dev server (`nx -r`) before ANY manual browser check.
- **e2e locale is English** — assert English strings.
- **Migrations needed: NO.** No SQL, no permission codes, no `page_visibility()` change, no `deploy.yml` change.
- **i18n: ONE late pybabel cycle (Task 8).** New msgids land in Tasks 1, 2, 5, 7; `tests/unit/test_translations.py` is expected RED in between — use `--deselect tests/unit/test_translations.py` for the fast tier until Task 8.
- **PROD URL prefix:** any hand-built URL goes through the `API_PREFIX` idiom (`_reporting_drill_js.html` already opens with `var API_PREFIX = window.location.href.includes("nexora") ? "/nexora/" : "/";`).
- **Visual contract (2026-07-14 flagship polish):** never rename a `.reporting-*` class; preserve every `data-testid`/`id`; `.nx-rise*` animations use fill-mode `backwards`, never `both`.
- **gitlint:** conventional-commit title ≤72 chars, imperative, no trailing period; non-empty body wrapped ≤100 chars; commit via Bash `git commit -F - <<'EOF' … EOF`. If `ruff-format` rewrites a file the first attempt fails — `git add -u` and recommit. If INT is unreachable: `SQL_SYNC_SKIP=1`, never `--no-verify`.
- **Commit trailer names the EXECUTING model** — the blocks below say `Claude Fable 5`; substitute the real executor if different.

---

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **400s in the Simple pane show `error — detail`; the canned "outdated" line is only the no-detail fallback.** | The server already returns `{"error": …, "detail": str(e)}` from `/api/reporting/run` (`nx_lib/views/reporting.py`, the `except (ReportDefinitionError, QueryBuildError, TableQueryError, MetricResolveError)` block). `friendlyRunError` discards it today. |
| D2 | **Error state keeps the report title and renders an inline "Open in Advanced" button; Save/Export/Show-query stay hidden (already are) and the header Save/Export buttons get disabled while no successful result is loaded.** | `showResultError` already hides the in-body controls; the header `rsSave`/`rsExport`/`rsOpenAdvanced` stay live. Open-in-Advanced is the escape hatch, so it stays ENABLED; Save/Export on a failed run are traps. |
| D3 | **Zero rows always shows the `noData` empty state + a hint line, even when the grand-total stat card rendered.** | Today `if (!rows.length && el('rsStatCard').hidden)` skips the empty state whenever the zero-total stat card is visible — exactly the confusing case. |
| D4 | **Back-origin tracking: `state.current.origin ∈ {'library','wizard','ask'}`; `rsBack` returns there. Wizard adjustment stays on the explicit "Adjust in wizard" button.** | Today `rsBack` prefers the wizard whenever the definition is wizard-shaped, even for library-opened reports. `×` (`rsExit`) stays the always-library exit. |
| D5 | **Wizard restore seeds the flatpickr with the literal range (`defaultDate`), so display always equals what runs.** | `wizardStateFromDefinition` maps `range = ft.value.slice()` but `renderTimeStep` never writes it into `el('rsTimeRange')` — hidden state. |
| D6 | **Drill-drawer workitem click opens the shared `NexoraWorkitemDetail` panel in a modal over the drawer; the `<a href>` to `/workitems?search=<id>` is kept for middle-click/new-tab.** | Owner picked inline panel over page-jump. Precedent: `templates/js/_prepared_documents_js.html` `openPreview()` + `templates/prepared_documents.html` modal shell + `__pdocPreviewPerms`. |
| D7 | **`humanize_sql_error(msg)` lives in `nx_lib/reporting/sandbox.py` as a pure function; wired in `ai_tools.AiToolbox._call`'s generic `except` and into the `/api/reporting/sql/run` generic-500 `detail`.** | One choke point covers every tool error the model and the trace see; the SQL editor's bare "Could not run query" gets the same readable detail. English only — the text also feeds the model. |
| D8 | **First teaching mapping: SQL Server error 1033 → "ORDER BY inside a derived table needs TOP or OFFSET — or move ORDER BY to the outer SELECT."** | The exact failure observed in the live audit; same philosophy as the `tsql_limit` gate from `b2f9f39`. More mappings can accrete later. |
| D9 | **Agent retry: a "Try again" button appears when `stoppedReason !== 'final'` or the response carried no artifacts (`agentInvalid` case); it resends the SAME question text.** | `stoppedReason` is already in the response JSON. No server change. |
| D10 | **Prompt line added to `_AGENT_SYSTEM`: after a failed `run_sql`, never resubmit the identical SQL — change the query first.** | The audited agent burned two turns resubmitting byte-identical broken SQL. |
| D11 | **Opportunistic: the masthead timing badge (`#reportingTiming`) hides when leaving the result view (`setView` to non-result) and on `showResultError`.** | Stale "2 rows · 1707 ms" over a library list / error state misinforms. |
| D12 | **No metric back-compat aliasing for `workitem_count`; no auto-fix of broken definitions.** | Spec non-goal — disabled means disabled; the UI now says why. |

---

## Owner actions (not for the executor)

1. **Review + push `feature/2.5.64`** when the plan completes (pre-push gate runs the FULL suite; run `scripts/test_db_reset.py` first).
2. The broken saved report "Docs and workitems per process per month 2026" references the disabled `workitem_count` metric — after Task 1 ships, open it, read the real reason, and fix or delete it via Advanced.
3. Say the word if the drill-panel modal should also expose comments/audit write actions — v1 is strictly read-only.

---

# PHASE 1 — Simple pane: honest error + empty states

### Task 1: 400 detail passthrough + actionable error state

**Files:**
- Modify: `templates/js/_reporting_simple_js.html`
- Test: `tests/e2e/test_reporting_simple.py`

**Interfaces:**
- Produces: `friendlyRunError(status, data)` returns `data.error + ' — ' + data.detail` when both exist; `showResultError(msg, opts)` gains an optional `{openAdvanced: true, title: str}` second argument; new i18n key `openInAdvanced` reuse (button label already exists in the header — reuse `I18N` only if a new string is actually needed).

- [ ] **Step 1 — Write the failing e2e.** In `tests/e2e/test_reporting_simple.py`, add `test_library_report_run_400_shows_detail_and_advanced_action` following the file's stub idiom: stub `**/api/reporting/reports` + `**/api/reporting/reports/*` to return a saved report whose definition is arbitrary, stub `**/api/reporting/run` to return status 400 with body `{"error": "This report definition is invalid or outdated.", "detail": "unknown metric: 'workitem_count'"}` (register routes **before** `page.goto`). Open the library card, assert:
  - the error text contains `unknown metric: 'workitem_count'`
  - the result header still shows the report name
  - a visible button/link inside the error region with `data-testid="rs-error-open-advanced"`
  - the header `rsSave` and `rsExport` buttons are disabled (`to_be_disabled()`)
- [ ] **Step 2 — Run it, confirm RED:** `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -k "400_shows_detail" -q` (reset TEST DB first if this is the session's first e2e).
- [ ] **Step 3 — Implement.** In `templates/js/_reporting_simple_js.html`:
  - `friendlyRunError`: replace the `if (status === 400) return I18N.outdated;` line with logic that prefers `data.error` and appends `' — ' + data.detail` when present; keep `I18N.outdated` as the 400-without-detail fallback.
  - `showResultError(msg)` → `showResultError(msg, opts)`: keep every current hide; when `opts && opts.title` set `rsResultTitle.textContent` to it instead of `''`; when `opts && opts.openAdvanced`, render below `rsError` a button `data-testid="rs-error-open-advanced"` (label: reuse the existing header button's string `Open in Advanced` — check `templates/_reporting_simple.html` for the exact msgid before adding a new one) that calls the same handler as `el('rsOpenAdvanced')`.
  - `runCurrent()` error branch `if (!res.ok) { showResultError(friendlyRunError(res.status, res.data)); return; }`: pass `{title: cur.name || cur.def.title || '', openAdvanced: true}`.
  - Add a `setHeaderActionsEnabled(enabled)` helper toggling `disabled` on `rsSave` and `rsExport` (if present — `EXPORT_ALLOWED` guard exists); call `setHeaderActionsEnabled(false)` in `showResultError` and at the top of `runCurrent`, `setHeaderActionsEnabled(true)` after a successful run.
- [ ] **Step 4 — Run the e2e GREEN**, plus the whole file: `… -m pytest tests/e2e/test_reporting_simple.py -q` (expect all green; the suite passed 56 tests on 2026-07-15).
- [ ] **Step 5 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
fix(reporting): surface run-error detail and escape hatch in Simple

A 400 from /api/reporting/run now shows the server's error + detail
(e.g. "unknown metric") instead of a canned line, keeps the report
title, renders an Open-in-Advanced action in the error state, and
disables Save/Export while no successful result is loaded.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 2: zero-row empty state with hint

**Files:**
- Modify: `templates/js/_reporting_simple_js.html`
- Test: `tests/e2e/test_reporting_simple.py`

**Interfaces:**
- Produces: new i18n msgid `Widen the time range or remove a filter.` (key `noDataHint` in the `I18N` map).

- [ ] **Step 1 — Write the failing e2e** `test_zero_rows_shows_empty_state_hint`: stub `**/api/reporting/run` to return `{"columns": [{"field":"import_date","header":"Import date"},{"field":"doc_count","header":"doc_count"}], "rows": [], "rowCount": 0, "sql": null}` for BOTH calls (grand-total and breakdown — `_stub_run_ok`'s shape shows how the helper builds responses; a custom `page.route` returning rows `[]` and for the zero-column total-def call rows `[[0]]` is fine). Drive any definition through (simplest: reuse the wizard flow an existing test uses, or open a stubbed saved report). Assert the empty-state title `No data for this report` AND the hint `Widen the time range or remove a filter.` are visible, and that no bare `<table>` with only a header row rendered.
- [ ] **Step 2 — RED run** (`-k zero_rows_shows_empty`).
- [ ] **Step 3 — Implement.** In `runCurrent()`, the block anchored on `if (!rows.length && el('rsStatCard').hidden) {`:
  - drop the `&& el('rsStatCard').hidden` condition (zero rows always shows the empty state; the zero stat card may stay visible above it),
  - append inside the `.nx-empty` markup a `<p class="nx-empty__hint">` with new `I18N.noDataHint` = `{{ _("Widen the time range or remove a filter.")|tojson }}`.
- [ ] **Step 4 — GREEN run**, then full file. (Beware `tests/e2e/test_reporting_simple.py` tests that assert the CURRENT no-data behavior — if one asserts the stat card and empty state are mutually exclusive, update it deliberately and say so in the commit body.)
- [ ] **Step 5 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
fix(reporting): explain zero-row results in the Simple pane

A successful run with no rows now always renders the no-data empty
state with a "widen the range or remove a filter" hint, instead of a
bare header-only grid when the zero grand-total stat card is visible.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

# PHASE 2 — Simple pane: navigation honesty

### Task 3: Back returns to its origin

**Files:**
- Modify: `templates/js/_reporting_simple_js.html`
- Test: `tests/e2e/test_reporting_simple.py`

**Interfaces:**
- Produces: `state.current.origin` (`'library' | 'wizard' | 'ask'`) set at every `state.current = {…}` assignment site. Task 4 does not depend on it; nothing else reads it.

- [ ] **Step 1 — Write the failing e2e** `test_back_from_library_report_returns_to_library`: stub reports list/get + `_stub_run_ok(page)`, open a library card, wait for the result view, click `rsBack` (`data-testid="rs-back"`), assert the library group `rs-group-mine` is visible and the wizard (`rsWizard`) is NOT. Add a companion assertion inside an existing wizard-flow test (or a new `test_back_from_wizard_result_returns_to_wizard`): build via wizard → result → `rsBack` → wizard step markup visible (existing behavior, now explicit).
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** In `templates/js/_reporting_simple_js.html`:
  - `openReport(r)`: add `origin: 'library'` to the `state.current = {…}` literal.
  - the `rsWizardRun` click handler (`builtBy: 'wizard'` literal): add `origin: 'wizard'`.
  - the Ask-AI result assignment (anchored on `aiQuestion: q` in the `state.current = {…}` literal near `runCurrent();` at the end of the ask flow): add `origin: 'ask'`. Also the Refine flow if it builds a fresh `state.current` (Grep `aiQuestion` for all assignment sites and stamp each).
  - `adjustInWizard()` reopening: when the user re-runs from the wizard the `rsWizardRun` handler already stamps `'wizard'` — no change.
  - Replace the `el('rsBack').addEventListener('click', …)` body (anchored on the comment `// Back on a result returns to the wizard ADJUSTMENT whenever the definition`): `origin === 'wizard'` → keep today's adjust-in-wizard path; anything else → `exitToLibrary()`. Update the comment to describe origin-based behavior.
- [ ] **Step 4 — GREEN run**, full file.
- [ ] **Step 5 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
fix(reporting): Back returns to where the report was opened from

Result views track their origin (library, wizard, ask); the Back
control returns there instead of always preferring the wizard for any
wizard-shaped definition. Adjust-in-wizard stays the explicit entry.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 4: wizard shows the restored custom range

**Files:**
- Modify: `templates/js/_reporting_simple_js.html`
- Test: `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1 — Write the failing e2e** `test_adjust_in_wizard_prefills_custom_range`: stub a saved report whose definition has `"filters": [{"field": "import_date", "op": "between", "value": ["2026-01-01", "2026-03-31"]}]` (plus one metric, ≤3 columns so `wizardStateFromDefinition` maps it), `_stub_run_ok(page)`, open it, click `rs-adjust-wizard` (Grep the template for the exact `data-testid` on `rsAdjustWizard`), assert the visible custom-range input `rsTimeRange` has a non-empty value containing `2026-01-01`.
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** In `renderTimeStep()` (anchored on `el('rsTimeCustom').hidden = !Array.isArray(state.wiz.range);`): when `Array.isArray(state.wiz.range)`, eagerly create the flatpickr if missing and seed it —

```js
if (Array.isArray(state.wiz.range) && window.flatpickr) {
  if (!state.wiz._fp) {
    state.wiz._fp = flatpickr(el('rsTimeRange'), {
      mode: 'range', dateFormat: 'Y-m-d',
      onChange: function (picked) {
        if (picked.length === 2) {
          state.wiz.range = [isoDate(picked[0]), isoDate(picked[1])];
        }
      }
    });
  }
  state.wiz._fp.setDate(state.wiz.range, false);   // display = state, no event
}
```

  Keep the lazy-create branch inside the Custom `choiceBtn` handler as-is (dedupe: extract a tiny `ensureRangePicker()` used by both sites so the flatpickr options exist once).
- [ ] **Step 4 — GREEN run**, full file. Also restart the dev server and manually verify once in the browser (`nx -r -b --loginas:ben.streich`, open "Compass imports Q1 2026" → Adjust in wizard → range visible).
- [ ] **Step 5 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
fix(reporting): wizard shows the restored custom date range

Adjust-in-wizard on a definition with a literal between range now
seeds the flatpickr, so the picker displays exactly the range Show
result will run — no more hidden-but-applied filter.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

# PHASE 3 — Drill drawer: inline workitem detail

### Task 5: workitem detail panel modal from the drill drawer

**Files:**
- Modify: `templates/reporting.html` (include the shared panel partial + perms bootstrap + modal shell)
- Modify: `nx_lib/views/reporting.py` (`reporting()` view: pass the three `details_*_perm` flags)
- Modify: `templates/js/_reporting_drill_js.html` (click interception + panel open)
- Modify: `static/css/` only if link affordance needs it (prefer an existing utility class)
- Test: `tests/e2e/test_reporting_simple.py`

**Interfaces:**
- Consumes: `window.NexoraWorkitemDetail.render(wid, containerEl, {readOnly, perms, …})` and `attachLightbox(cfg)` from `templates/js/_workitem_detail_panel_js.html` (already exported globals).
- Produces: `window.__rpDrillPerms` (same shape as `window.__pdocPreviewPerms` in `templates/prepared_documents.html`), modal ids `rdWiModal`, `rdWiBody`, `rdWiClose`, lightbox ids `rdWiLightbox`, `rdWiImage`, `rdWiHlLayer`, `rdWiHlToggle`, `rdWiHlToggleLabel`, `rdWiReviewPanel`, `rdWiReviewPanelBody`.

- [ ] **Step 1 — Write the failing e2e** `test_drill_row_opens_workitem_panel`: stub the run endpoints so a drill returns a row with a `workitem_id` column (see how drill fires: `ReportingDrill.open` POSTs the drill definition to `**/api/reporting/run` — the SAME route stub can key on `body.rowLimit === 100` + `visualization === 'table'` to serve the drill response), stub `**/get_extensions_urls_fields*` (or whatever endpoint `NexoraWorkitemDetail.render` fetches — Grep `_workitem_detail_panel_js.html` for its fetch URL and stub it minimally). Click a drillable table row, then click the workitem link in the drawer, assert `#rdWiModal` becomes visible and `#rdWiBody` is non-empty. Assert the link did NOT navigate (page URL unchanged).
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Backend flags.** In `nx_lib/views/reporting.py` `reporting()` (anchored on `ai_explain_enabled=has_permission("reporting.ai.explain_data")`): add `details_images_perm=has_permission("workitems.details.view.images")`, `details_audit_perm=has_permission("workitems.details.view.audit")`, `details_fields_perm=has_permission("workitems.details.view.fields")` (verify the exact codes by Grep in `nx_lib/views/workitems.py` — the `details_images_perm = has_permission(` block).
- [ ] **Step 4 — Template.** In `templates/reporting.html`, after the `{% include "js/_reporting_drill_js.html" %}` line: add the perms bootstrap `<script>` (copy the `window.__pdocPreviewPerms` block from `templates/prepared_documents.html`, rename to `__rpDrillPerms`, include the `srcConfClass`/`srcConfPct`/`fieldConfig`/`mentionableUsers` fallbacks it needs), the modal + lightbox shells (copy `#pdocPreviewModal` / `#pdocPreviewLightbox` markup, rename ids to the `rdWi*` set), and `{% include 'js/_workitem_detail_panel_js.html' %}` — all gated `{% if details_images_perm or details_fields_perm %}` like prepared_documents gates its include.
- [ ] **Step 5 — Drawer JS.** In `templates/js/_reporting_drill_js.html` `renderRows` (anchored on `cell = '<a href="' + API_PREFIX + 'workitems?search='`): add `class="reporting-drill-wi-link" data-wid="' + esc(String(v)) + '"` to the anchor. In `wire()`, delegate: click on `.reporting-drill-wi-link` without modifier keys → `preventDefault()` + `openWorkitemPanel(wid)`; with Ctrl/Cmd/middle-click the native anchor wins. `openWorkitemPanel` mirrors `openPreview` in `_prepared_documents_js.html`: lazy `attachLightbox({modal:'rdWiLightbox', …})`, clear `rdWiBody`, `NexoraWorkitemDetail.render(wid, body, {readOnly: true, perms: window.__rpDrillPerms || {}})`, unhide `rdWiModal`; close on `rdWiClose`, backdrop click, and Escape (yield to the lightbox's own Escape first — copy the `lbOpen` guard from `_prepared_documents_js.html`). Guard everything on `window.NexoraWorkitemDetail` existing (perm-gated include) — without it the anchor behaves as today.
- [ ] **Step 6 — Link affordance.** Ensure `.reporting-drill-wi-link` renders as a link (underline/color). Check `static/css/` for an existing drawer stylesheet (Grep `reporting-drill-null` for where drawer styles live) and add one rule there.
- [ ] **Step 7 — GREEN run**, full e2e file. Restart dev server, manual check: Simple → Ask AI result → drill a bucket → click a workitem id → panel renders in place (screenshot to `var/screenshots/`).
- [ ] **Step 8 — Commit:**

```bash
git add templates/reporting.html nx_lib/views/reporting.py templates/js/_reporting_drill_js.html tests/e2e/test_reporting_simple.py
# plus the css file touched in Step 6
git commit -F - <<'EOF'
feat(reporting): open workitem detail panel from the drill drawer

Drill-drawer workitem ids open the shared NexoraWorkitemDetail panel
in a modal over the drawer (read-only, perm-gated like the Prepared
Documents preview); plain link to /workitems kept for new-tab clicks.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

# PHASE 4 — Agent surface: errors that teach + retry

### Task 6: humanize SQL tool errors server-side

**Files:**
- Modify: `nx_lib/reporting/sandbox.py` (new pure function `humanize_sql_error`)
- Modify: `nx_lib/reporting/ai_tools.py` (use it in `AiToolbox._call`'s generic `except`)
- Modify: `nx_lib/views/reporting.py` (SQL run generic-500 gains a humanized `detail`)
- Modify: `nx_lib/reporting/ai.py` (`_AGENT_SYSTEM` one-line addition, D10)
- Test: `tests/unit/test_reporting_sandbox.py` (exists — follow its conventions), `tests/integration/test_reporting_ai_routes.py`

**Interfaces:**
- Produces: `humanize_sql_error(msg: str) -> str` — strips the pyodbc tuple wrapper (`('42000', "[42000] [Microsoft][ODBC SQL Server Driver][SQL Server]…`) and `[Microsoft][ODBC …][SQL Server]` prefixes, trims the trailing `(1033) (SQLExecDirectW)` noise into a readable sentence, and appends a teaching hint for known error codes. Mapping v1: code `1033` → `Hint: ORDER BY inside a derived table needs TOP or OFFSET — or move ORDER BY to the outer SELECT.` Unknown messages pass through unchanged. English only (feeds the model).

- [ ] **Step 1 — Write the failing unit tests** (RED): parametrize over (a) the exact live-audit string `('42000', '[42000] [Microsoft][ODBC SQL Server Driver][SQL Server]The ORDER BY clause is invalid in views, inline functions, derived tables, subqueries, and common table expressions, unless TOP, OFFSET or FOR XML is also specified. (1033) (SQLExecDirectW)')` → asserts the result contains `ORDER BY clause is invalid` AND the `Hint:` line AND no `SQLExecDirectW`/`[Microsoft]` noise; (b) an incorrect-syntax string with code `102` → cleaned, no hint; (c) a non-ODBC message `unknown metric: 'x'` → returned verbatim.
- [ ] **Step 2 — Implement `humanize_sql_error` in `nx_lib/reporting/sandbox.py`** (module-level, near `SqlSandboxError`; regex-based, no new deps). GREEN.
- [ ] **Step 3 — Wire the toolbox choke point.** In `nx_lib/reporting/ai_tools.py`, the generic handler anchored on `return {"ok": False, "error": str(e) or e.__class__.__name__}`: pass through `humanize_sql_error(...)` (import from `.sandbox`). Extend an existing agent-loop test in `tests/integration/test_reporting_ai_routes.py` (or add one): a `run_sql` stub raising an exception with the ODBC tuple text yields a tool-trace error WITHOUT `SQLExecDirectW` and WITH the hint — RED first, then GREEN.
- [ ] **Step 4 — SQL route detail.** In `nx_lib/views/reporting.py`, the handler anchored on `return jsonify({"error": _("Could not run query")}), 500`: add `"detail": humanize_sql_error(str(e))` to the body (import already available via the sandbox imports at the top — check). Quick integration assert in the SQL-run tests if one covers the 500 path; add a minimal one if not.
- [ ] **Step 5 — Prompt line.** In `nx_lib/reporting/ai.py` `_AGENT_SYSTEM` (anchored on the string `"— never invent fields, tables, or sources.`): append one sentence — `After a failed run_sql, never resubmit the identical SQL; change the query before retrying.`
- [ ] **Step 6 — Full relevant tier:** `… -m pytest tests -k "sandbox or ai_tools or reporting_ai" -q` green; then `… -m pytest tests --ignore=tests/e2e --deselect tests/unit/test_translations.py -q`.
- [ ] **Step 7 — Commit:**

```bash
git add nx_lib/reporting/sandbox.py nx_lib/reporting/ai_tools.py nx_lib/views/reporting.py nx_lib/reporting/ai.py tests/
git commit -F - <<'EOF'
fix(reporting): humanize SQL errors for the agent and SQL editor

New sandbox.humanize_sql_error strips pyodbc/ODBC driver noise and
appends a teaching hint for known SQL Server errors (1033: ORDER BY
in derived tables needs TOP/OFFSET). Wired into the AI toolbox error
choke point and the SQL run 500 detail. Agent prompt now forbids
resubmitting identical failed SQL.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

### Task 7: agent "Try again" affordance

**Files:**
- Modify: `templates/js/_reporting_ai_js.html`
- Modify: `templates/reporting.html` — the AI-surface markup lives here (verified: `id="rpAiOpenBuilder"` with `data-testid="reporting-ai-open-builder"`, and `_reporting_ai_js.html` reads `rpAiAgentInvalid`); put the retry button beside the agent action buttons
- Test: Create `tests/e2e/test_reporting_agent.py` — **no e2e covers the agent surface yet** (verified: no `ai/agent` match under `tests/e2e/`); follow `tests/e2e/test_reporting_simple.py` fixtures/stub conventions and stub `**/api/reporting/ai/agent` before `page.goto`

**Interfaces:**
- Consumes: `stoppedReason` from the agent response JSON (already returned by `nx_lib/views/reporting.py`); `askAgent(question)` in `_reporting_ai_js.html`.
- Produces: button `data-testid="reporting-ai-retry"`, new msgid `Try again`.

- [ ] **Step 1 — Write the failing e2e:** stub `**/api/reporting/ai/agent` returning `{"answer": "I could not…", "toolTrace": [{"name": "run_sql", "result": {"ok": false, "error": "boom"}}], "turns": 10, "stoppedReason": "max_turns", "definition": null, "sql": null}`; ask a question in Agent mode; assert the `reporting-ai-retry` button is visible; re-stub with a success payload (`stoppedReason: "final"`, a definition artifact), click retry, assert the button hides and the thread shows TWO turns with the SAME question text.
- [ ] **Step 2 — RED run.**
- [ ] **Step 3 — Implement.** In `templates/js/_reporting_ai_js.html` `askAgent`'s success handler (anchored on `if (agentInvalid)`): keep the last question in a `lastAgentQuestion` var (set where `agentThread.push({ q: question, …})` runs); show the retry button when `d.stoppedReason !== 'final' || !(lastAgentDef || lastAgentSql)`; hide it otherwise and on mode switches (the same place `errorEl.hidden = true` resets on switch). Button click → `askAgent(lastAgentQuestion)`. Markup: in `templates/reporting.html`, add the button beside `id="rpAiOpenBuilder"` (`data-testid="reporting-ai-open-builder"`), label `{{ _("Try again") }}`, `hidden` by default.
- [ ] **Step 4 — GREEN run** + that e2e file fully.
- [ ] **Step 5 — Commit:**

```bash
git add templates/js/_reporting_ai_js.html templates/reporting.html tests/e2e/test_reporting_agent.py
git commit -F - <<'EOF'
feat(reporting): retry affordance on failed agent runs

An agent response that hit the turn cap or produced no artifacts now
shows a Try again button that resends the same question, instead of
leaving only apologetic prose.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

# PHASE 5 — Polish + chores

### Task 8: timing-badge reset, i18n cycle, changelog, docs

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (badge reset)
- Modify: `CHANGELOG.md`, `docs/howto/reporting.md`
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`)

- [ ] **Step 1 — Badge reset.** In `setView(view)` (anchored on `if (view !== 'result') destroyChart();`): also hide `#reportingTiming` when `view !== 'result'`. In `showResultError`, hide it too. Quick e2e assertion added to the Task 1 test (badge hidden in the error state) — RED→GREEN it here if not folded in earlier.
- [ ] **Step 2 — i18n cycle** (all new msgids from Tasks 1, 2, 5, 7):

```powershell
.\.venv\Scripts\pybabel extract -F babel.cfg -o messages.pot .
.\.venv\Scripts\pybabel update -i messages.pot -d translations
# translate every new msgid in de/fr/it .po files (non-fuzzy)
.\.venv\Scripts\pybabel compile -d translations
```

- [ ] **Step 3 — Verify translations test green:** `… -m pytest tests/unit/test_translations.py -q`.
- [ ] **Step 4 — Changelog + docs.** `CHANGELOG.md` under `[Unreleased]`: Fixed — run-error detail, zero-row hint, back-origin, wizard range display, timing-badge reset; Added — drill-drawer workitem panel, agent retry, humanized SQL errors. `docs/howto/reporting.md`: short paragraphs where the affected surfaces are documented (drill-through section gains the inline panel; agent section gains retry + teaching errors).
- [ ] **Step 5 — Full fast tier green:** `… -m pytest tests --ignore=tests/e2e -q` and the two touched e2e files.
- [ ] **Step 6 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html CHANGELOG.md docs/howto/reporting.md messages.pot translations/
git commit -F - <<'EOF'
docs(reporting): changelog, docs and i18n for the UX friction pass

Timing badge now hides outside result views; extract/update/compile
cycle for the new Simple-pane, drill-panel and agent-retry strings
(de/fr/it); changelog and reporting howto updated.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
```

---

## Gotchas & notes

- **The Simple e2e stub race (memory `project_reporting_aiflow_e2e_race`):** always stub `**/api/reporting/run` BEFORE any Simple-pane interaction that triggers `runCurrent()` — an unstubbed run 500s in TEST and `showResultError` tears down the surface mid-test.
- **`runCurrent()` fires TWO runs for metric+dims definitions** (zero-column grand-total clone first). Route stubs must handle both bodies; key on `body.columns.length === 0` for the total call.
- **`wizardStateFromDefinition` maps only wizard-shaped defs** (1 metric, ≤3 columns, ≤1 between-filter, no client scope, WIZ_TOKENS only). Task 4's test definition must satisfy it or `rsAdjustWizard` stays hidden.
- **`_workitem_detail_panel_js.html` fetch targets:** Grep its `fetch(` calls before writing the Task 5 e2e stubs — it hits the workitems detail endpoints (`get_extensions_urls_fields`-backed route) which don't exist in TEST with real data.
- **The drill drawer is shared** by Simple and Advanced panes — Task 5's modal works for both automatically (the include lives on `reporting.html`, not inside a pane).
- **`humanize_sql_error` feeds the MODEL as well as the trace UI** — keep it English, deterministic, and short; do not gettext it.
- **Do not rename `outdated` in the `I18N` map** — it stays as the no-detail 400 fallback; other tests may reference its string.
- **Template cache:** restart `nx -r` before every manual browser verification; e2e restarts are handled by the suite fixtures.
- **After the last task:** run `scripts/test_db_reset.py` then the full e2e tier once locally if time allows — the owner's pre-push gate runs it anyway.
