# Codebase beautification, Phase 0+1 — dead code, perf freebies, modularity foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Single-session planning run distilled from a **five-agent audit run against `v3.2.4.1` HEAD (`0da9f522`) on 2026-08-31** (views structure, dead code, frontend JS, lint/typing, performance — measured, not guessed); every deletion target and symbol re-verified by Grep/Test-Path in the planning session. Anchor on quoted snippets + symbol names, never line numbers; re-Grep before editing. Plan file: `docs/superpowers/plans/2026-08-31-beautify-phase-0-1.md`.

**Goal:** Make the codebase smaller, faster, and modular enough that the next white-label customer is a descriptor, not a fork. Phase 0 deletes everything provably dead and lands the measured zero-risk perf wins (~−2,000 lines, 1 DB query off every page render, static assets cacheable). Phase 1 builds the modularity foundation: one shared JS core (kills 37 `API_PREFIX` copies + ~60 duplicated helpers), `views/generali/` and `views/admin/` become packages, and generali's 8 copy-pasted CRUD families collapse into one descriptor-driven factory — the tenant-module pattern every future customer page follows.

**Architecture:** No Blueprints — every view package keeps `register_routes(app)` fanning out to submodule `register_routes(app)` calls; `nx_lib/__init__.py` and every `url_for()` endpoint name stay untouched. JS consolidation is additive-first: `nx_core.js` defines the shared surface, then copies are removed file-by-file. Package splits use re-exporting `__init__.py` so existing imports and test patch targets keep working.

**Tech Stack:** Flask + Jinja2, vanilla JS (no bundler — script order in `{% include %}` is authoritative), ruff 0.7.4 + mypy 1.13.0, pytest. **Migrations needed: NO.**

---

## Context an engineer needs (read first)

- **Branch:** cut from `v3.2.4.1` (or the current release branch at execution time — check `git branch --show-current`). Parallel sessions are normal — work in your own worktree (`git worktree add .claude/worktrees/beautify -b feat/beautify-phase-0-1 v3.2.4.1`), stage by pathspec, commit per task. **No `git push`, no PR** — the owner reviews and pushes.
- **Copy the gitignored env files into the worktree first**: `Copy-Item C:\dev\nexora\env\*.env <worktree>\env\` — pre-commit runs `scripts/db-migrate.py --env INT` and tests need `env/TEST.env`.
- **Python for tests:** `.venv\Scripts\python.exe -m pytest …`. The dev server (`bin/nx.ps1 -u`) runs global Python313.
- **Sequencing vs in-flight work (owner-decided 2026-08-31): this plan runs BEFORE the Generali DB restructure (#220).** `docs/superpowers/plans/2026-08-27-generali-db-restructure.md` quotes anchors inside `nx_lib/views/generali.py` as one file; after Task 13/14 those anchors live in `nx_lib/views/generali/` submodules. #220's own rules require re-Grepping anchors before editing — its executor must do so. Do not "fix" #220's plan file here.
- **Jinja templates are cached for the process lifetime** — restart the dev server (`bin/nx.ps1 -r` or `-u`) before any browser verification.
- **CSP is PROD-only** — no inline `on<event>=` handlers (lint test enforces); behaviour in JS files/partials with `addEventListener`.
- **Hand-built URLs in JS must normalize through `API_PREFIX`** (`tests/unit/test_template_url_prefix.py` enforces; that test also bans Jinja syntax inside `static/js/*.js`).
- **gitlint:** conventional-commit subject ≤72 chars, imperative, no trailing period; non-empty body wrapped ≤100 chars/line; `git commit -F -` with a here-doc; end with the executing model's `Co-Authored-By:` trailer.
- **Pre-push gate is fast-tier only** (v3.2.4.1); still run `python scripts/test_db_reset.py` before the integration suite, and prepend `.venv\Scripts` to PATH for the gate.
- **If the SQL pre-commit hooks block on unrelated drift** (INT unreachable / stale dumps on an older base): `SQL_SYNC_SKIP=1 git commit …` — never `--no-verify`.
- **i18n: one task needs it.** Task 4 deletes a commented-out Jinja block that still carries live `{{ _() }}` strings — run the `/nx-i18n` cycle in that task or `test_translations.py` fails on the orphaned msgids. No other task adds or removes user-visible strings.
- **Verification loop:** each task ends with its named tests green. JS-touching tasks additionally get a browser pass (`bin/nx.ps1 -u -b --loginas:ben.streich`, screenshots to `var/screenshots/`).

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | `tools/autopilot/` is deleted, including its `bin/nx.ps1` driver plumbing. | Owner-approved 2026-08-31. Dormant since 2026-06-15; recoverable from git history. |
| D2 | The `/jdvance` easter egg and the Anthropic provider path in `nx_lib/reporting/ai.py` are **kept** — closed as deliberate, not findings. | Owner's call (easter egg); provider-agnosticism is a documented design decision (`docs/design/reporting-ai-assistant.md`). |
| D3 | View packages keep `register_routes(app)` + `add_url_rule` — **no Blueprints**, no endpoint renames. | `nx_lib/__init__.py` documents this as deliberate; `url_for()` everywhere depends on it. |
| D4 | Package `__init__.py` re-exports every public symbol and every test-patched private symbol under its old path. | `api_external.py` imports 10 symbols from `workitems`; generali tests call `gv.<fn>` directly; keeps blast radius zero. |
| D5 | `nx_core.js` lands additive-first; copies removed in separate, per-family commits. | A big-bang removal across ~40 files is unreviewable and unbisectable. |
| D6 | The divergent `esc()` in `templates/js/_reporting_drill_js.html` (textContent/innerHTML round-trip) is **replaced** by the shared one. | It under-escapes `"` and `'` — unsafe in attribute context. This is a behaviour fix, noted in the commit message. |
| D7 | `SEND_FILE_MAX_AGE_DEFAULT` goes long (365 days) only in the same task that routes **all** template asset references through `static_v()`, plus a lint test locking the rule. | `static_v()`'s own docstring names this follow-through; long cache without busting = stale-asset bugs. |
| D8 | generali split lands as **mechanical move first (Task 13), factory second (Task 14)** — two reviewable steps, not one rewrite. | The factory changes function bodies; the move must be diff-verifiable as pure relocation. |
| D9 | mypy ratchet in this plan is `warn_return_any = true` only. `check_untyped_defs` and `disallow_untyped_defs` are Phase 3. | 7 fixes vs 69/748 — the big knobs come after the splits rewrite the worst files anyway. |

## Owner actions (not for the executor)

- **⚠ Revoke the GitHub PAT exposed in the 2026-06-15 autopilot transcript** (memory: `project_autopilot_recovery_layer`). Deleting `tools/autopilot/` (Task 2) does **not** revoke the token — it must be revoked at github.com/settings/tokens. Overdue since June.
- When executing #220 later, expect its `generali.py` anchors to have moved into `nx_lib/views/generali/` — its re-Grep rule covers this.
- Phase 2/3 follow-on (below) needs a green-light when this plan lands.

---

# PHASE 0 — zero-risk deletions and measured perf freebies

### Task 1: Delete dead files

- [ ] `git rm -r templates/js/archive templates/admin/archive static/css/archive` (tour partial + CSS, archived admin page referencing a CSS file that no longer exists — all zero-reference, Grep-verified).
- [ ] `git rm static/images/1019-icon.png static/images/nexora-logo.png scripts/export-help/csvToStructuredExport.ps1` (orphan avatar, orphan logo variant, unreferenced script).
- [ ] Re-verify before each rm: `grep -rn "<basename>" templates nx_lib static --include="*.html" --include="*.py" --include="*.js"` returns nothing (excluding the file itself).
- [ ] Run: `.venv\Scripts\python.exe -m pytest tests/unit -x -q` — green.
- [ ] Commit: `chore: delete archived templates, orphan images and dead export script` (body lists each path + "zero references, verified by grep").

### Task 2: Delete tools/autopilot and its nx.ps1 plumbing

- [ ] `git rm -r tools/autopilot`.
- [ ] In `bin/nx.ps1`: remove the autopilot driver surface — every param/function/block matching `invoke-workflow|kill-workflow|workflow-logs|--queue|autopilot` (~180 lines; 13 flag references Grep-confirmed). Keep everything else byte-identical.
- [ ] Check `.github/workflows/deploy.yml` robocopy excludes: if `tools` (or an autopilot-specific entry) is in `/XD`, leave it; if autopilot had its own entry, remove it.
- [ ] Grep repo-wide for `autopilot` — remaining hits should only be docs/memory/changelog history; clean any live references (e.g. `docs/howto/nx.md` flag docs).
- [ ] Verify: `powershell -File bin/nx.ps1 --doctor` still runs; `bin/nx.ps1 -u`, hit `http://127.0.0.1:8000/login`, stop server.
- [ ] Update `CHANGELOG.md` [Unreleased] (Removed) + `docs/howto/nx.md` if it documents the removed flags.
- [ ] Commit: `chore(nx): remove the dormant autopilot orchestrator and its CLI plumbing`.

### Task 3: Delete dead Python

Symbols (all Grep-verified zero non-test callers):

| Symbol | File |
|---|---|
| `def ping_db(engine, label, timeout_s=2.0):` | `nx_lib/db.py` (callers use `ping_dbs_parallel`) |
| `def _empty_paginated_response(extra=None):` | `nx_lib/views/generali.py` |
| `def get_source(source_id):` + `def list_accessible_sources(permissions):` | `nx_lib/reporting/sources.py` |
| `def get_params_from_process_list(process_list):` + `def build_stat_query(proc):` | `nx_lib/process_helpers.py` |
| `BEXIO_PAT = os.environ.get("BEXIO_PAT")` | `nx_lib/config.py` |
| `{% macro label(...) %}` + `{% macro stat_card(...) %}` | `templates/_ui.html` |

- [ ] For each: re-Grep callers (`grep -rn "<name>" nx_lib tests templates scripts`), delete the definition, delete any now-dead tests that only exercised it.
- [ ] Remove `BEXIO_PAT` from `env/*.env.example` if present.
- [ ] Run: `.venv\Scripts\python.exe -m pytest tests/unit tests/integration -x -q` — green. `ruff check .` — clean.
- [ ] Commit: `chore: delete dead functions, config key and template macros` (body names each symbol).

### Task 4: Delete dead JS, commented block, stray DOCTYPE wrappers

- [ ] `templates/js/_workitems_overview_js.html`: delete the four uncalled functions — `function cancelAllAnimations()`, `function closeAllDetails()`, `function getCurrentFilterOrSearch()`, `async function fetchFieldConfig()` (re-Grep each name repo-wide first).
- [ ] `templates/js/_generali_reporting_js.html`: delete the commented-out "details modal (disabled)" block (~30 lines; contains dead `{{ _() }}` calls Babel still extracts).
- [ ] Strip the `<!DOCTYPE html>…</head><body>` / `</body></html>` wrappers from the 8 included partials that carry them: `_workitems_overview_js.html`, `_hero_js.html`, `admin/_clients_js.html`, `admin/_organizations_js.html`, `admin/_permission_matrix_js.html`, `admin/_processes_js.html`, `admin/_user_management_js.html` (8th was the deleted tour file). Verify nothing greps for `</body>` in tests.
- [ ] Run `/nx-i18n` cycle (the deleted block drops msgids; `test_translations.py` must stay green).
- [ ] Browser pass: workitems overview + generali reporting pages render and filter correctly.
- [ ] Commit: `chore(js): delete uncalled functions, dead commented block and stray document wrappers`.

### Task 5: Long-lived static asset caching

- [ ] In `nx_lib/__init__.py`, find `def static_v(filename):` — its docstring documents this task ("once the CSS/image tags use static_v() too, SEND_FILE_MAX_AGE_DEFAULT can go long").
- [ ] Sweep every template: replace `url_for('static', filename=…)` asset references with `static_v('…')` (Grep `url_for('static'` and `url_for("static"` across `templates/`).
- [ ] Set `app.config["SEND_FILE_MAX_AGE_DEFAULT"] = timedelta(days=365)` next to the `static_v` definition.
- [ ] Add a unit lint test beside `test_template_url_prefix.py`: no `url_for('static'` in `templates/**` (allowlist: none expected; `static_v` is the only sanctioned path).
- [ ] Verify with the dev server: `curl -sI http://127.0.0.1:8000/static/js/reporting_simple.js` (via a page that links it) shows `Cache-Control: public, max-age=31536000` and the HTML references carry `?v=<mtime>`.
- [ ] Do **not** suffix the ETag (compression rule — breaks `If-None-Match`).
- [ ] `CHANGELOG.md` [Unreleased] (Performance).
- [ ] Commit: `perf(static): cache assets for a year behind static_v() busting`.

### Task 6: What's-New read through the user cache

- [ ] `nx_lib/whats_new.py`: `def load_seen_version(userid):` runs an uncached SELECT per HTML render (called by `_inject_whats_new` in `nx_lib/hooks.py`). Route it through the 30s TTL idiom in `nx_lib/user_cache.py` (same pattern permissions/ui_prefs use).
- [ ] `def mark_seen(userid):` invalidates that cache entry after its UPDATE.
- [ ] Test: unit test asserting a second call within TTL does not hit the engine (mock `raw_connection`), and `mark_seen` busts it.
- [ ] Run whats-new tests + `tests/unit/test_hooks*.py` if present — green.
- [ ] Commit: `perf(whats-new): read seen-version through the user TTL cache`.

### Task 7: Cache the reporting source/metric registry

- [ ] `nx_lib/views/reporting.py`: `def _load_db_sources():` and `def _load_db_metrics():` hit the DB on every call (~8× per report run). Wrap both in the house 60s TTL pattern — mirror `nx_lib/mapping_config.py` (success-only caching, load error returns fresh next call, `invalidate_…()` hook).
- [ ] Call the invalidator from every registry admin CRUD route (Grep the callers that INSERT/UPDATE/DELETE `ReportingSources`/`ReportingMetrics` in `views/reporting.py`).
- [ ] Test: unit test for TTL hit/miss + invalidation (mock the engine, model on `tests/unit/test_mapping_config.py`).
- [ ] Run `tests/integration/test_reporting_*.py` — green.
- [ ] Commit: `perf(reporting): cache the source/metric registry for 60s with admin invalidation`.

### Task 8: Lint/typing ratchet + CI coverage

- [ ] `pyproject.toml` `[tool.ruff.lint]`: `select = ["E","F","W","I","N","UP","B","SIM","RUF","RET","C4","PIE"]`.
- [ ] `ruff check . --fix` (15 safe fixes), then `--unsafe-fixes --diff` → review → apply the mechanical remainder (~9); hand-fix what's left. `ruff check .` clean.
- [ ] `[tool.mypy]`: add `warn_return_any = true`; fix the 7 errors (3 files).
- [ ] `.github/workflows/deploy.yml`: add `scripts` to both ruff steps' paths; add a mypy step (`python -m mypy nx_lib nx_main.py`) beside them.
- [ ] Full fast-tier gate green.
- [ ] Commit: `ci(lint): enable RET/C4/PIE, warn_return_any, and cover scripts in CI`.

# PHASE 1 — modularity foundation

### Task 9: Create static/js/nx_core.js (additive only)

- [ ] New file `static/js/nx_core.js` defining `window.NX` + back-compat globals: `window.API_PREFIX` (the canonical idiom), `NX.esc` (full attr-safe escaper), `NX.el`, `NX.api` (throwing flavour), `NX.apiSafe` (`{ok,status,data}` flavour — both exist in the wild), `NX.toast` (absorbs `showNotification`), `NX.formatDate`/`NX.formatDateTime` (via `Intl.DateTimeFormat`; keep a seconds-precision option — `_generali_import_status_js.html` shows seconds), `NX.formatHours`.
- [ ] No Jinja syntax in the file (lint enforces). No behaviour change anywhere — nothing consumes it yet.
- [ ] Load it first in `templates/_header.html` via `static_v('js/nx_core.js')`, before any other script include.
- [ ] Browser smoke: any page; `window.NX` and `window.API_PREFIX` defined in console.
- [ ] Commit: `feat(js): add nx_core.js shared helper surface (additive)`.

### Task 10: Remove API_PREFIX copies

- [ ] Grep `const API_PREFIX` across `templates/js/**` and `static/js/**` (37 copies) — delete each local declaration; code now reads the global. `_workitem_detail_panel_js.html` already reads `window.API_PREFIX` — leave it.
- [ ] Batch by directory (reporting / workitems / generali / admin), one commit per batch, browser-smoke each batch's main page.
- [ ] `tests/unit/test_template_url_prefix.py` green after each batch.
- [ ] Commits: `refactor(js): use shared API_PREFIX in <area> scripts`.

### Task 11: Deduplicate esc/el/api/toast in the reporting family

- [ ] Replace local `esc`/`el`/`api`/`toast` copies in `reporting_simple.js`, `reporting_dashboard.js`, `reporting_schema.js`, `_reporting_scheduled_js.html`, `_reporting_tabs_js.html`, `_reporting_sqlformat_js.html`, `_reporting_js.html`, `_reporting_metrics_js.html`, `_reporting_sources_js.html`, `_reporting_drill_js.html` with the `NX.*` equivalents (match throwing vs non-throwing `api` flavour per file — misassigning changes error handling).
- [ ] `_reporting_drill_js.html`'s divergent `esc` is replaced by `NX.esc` — **behaviour fix** (D6), note in commit body.
- [ ] Run reporting e2e (`tests/e2e/test_reporting_simple.py` — stub `/api/reporting/run` per the known chips race) + browser pass on Simple, Advanced, dashboard.
- [ ] Commit: `refactor(js): reporting family uses nx_core helpers` (body notes the esc hardening).

### Task 12: Deduplicate the generali/admin formatters and notifiers

- [ ] Replace `formatDate`/`formatDateTime`/`formatHours` copies across the 6 generali partials and `showNotification`/`escapeHtml` copies across `templates/js/admin/*` + `_workitems_overview_js.html` with `NX.*`.
- [ ] Reconcile the one divergence: import-status keeps seconds precision via the `NX.formatDateTime` option.
- [ ] Browser pass: one generali page, one admin page, workitems overview.
- [ ] Commit: `refactor(js): generali and admin partials use nx_core helpers`.

### Task 13: Split views/generali.py into a package (mechanical move)

- [ ] Create `nx_lib/views/generali/` with: `_scope.py` (the four shared helpers: `_generali_orgs_for_userids`, `_generali_userids_in_org`, `_generali_scope_where`, plus `_empty_paginated_response` already deleted in Task 3), `documents.py` (Evaluation/Documents), `reporting.py`, `attendance.py` (Additional Services), `baseservices.py`, `projectmanagement.py`, `pdqm.py`, `importstatus.py`.
- [ ] Each submodule gets its own `register_routes(app)`; package `__init__.py` re-exports **every** function name (`from .reporting import *`-style explicit lists — generali tests do `import nx_lib.views.generali as gv; gv.<fn>(…)`) and defines `register_routes(app)` fanning out to submodules **in the original registration order**.
- [ ] `nx_lib/__init__.py` unchanged (imports `generali` from `.views` — a package satisfies it).
- [ ] Move is diff-verifiable: no body edits, only relocation + import fixing.
- [ ] Run all generali tests + `pytest tests/unit -q` — green with **zero test edits**.
- [ ] Browser smoke: each generali page loads.
- [ ] Commit: `refactor(views): split generali.py into a views/generali package`.

### Task 14: Collapse the generali CRUD clones into a descriptor factory

- [ ] The 8 endpoint families (`api_list` ×6, `monthreport` ×5, `api_add`/`api_edit`/`api_delete` ×5, `api_filter_users` ×5, `api_organizations` ×5, `api_org_users` ×4 — 1,674 measured redundant lines) become: one descriptor dict per table (`{table, perm_prefix, columns, user_column, categories…}`) + `register_crud(app, desc)` in a new `nx_lib/views/generali/_crud.py`.
- [ ] **Test-first:** the existing per-family tests are the spec — they keep passing unmodified. Bind each generated view under its original function name in the owning submodule and re-export from `__init__` (D4), so `gv.<fn>` and endpoint names are unchanged.
- [ ] Migrate one family (baseservices) first, prove tests green, then the rest one commit per table.
- [ ] Keep genuine per-table divergence in the descriptor (validators, category sets) — do not force-uniform what differs.
- [ ] Commits: `refactor(generali): drive <table> CRUD from the shared descriptor factory`.

### Task 15: Parameterize the generali CRUD JS

- [ ] New `static/js/generali_crud.js`: the shared `loadRecords`/`canEditRecord`/`canDeleteRecord`/`exportToExcel`/`getAddMinDate`/pagination logic, parameterized by a per-page descriptor object the shim partial sets on `window` (Jinja data + translated strings stay in the shim — #191 convention; `babel.cfg` only extracts from templates).
- [ ] Convert the 4 clone partials (`_generali_base_services_js.html`, `_generali_additional_services_js.html`, `_generali_project_management_js.html`, `_generali_pdqm_js.html`, ~2,258 lines → ~4 thin shims + one JS file); one commit per page, browser pass each.
- [ ] Reporting/import-status partials are not clones — leave them.
- [ ] Commits: `refactor(js): <page> uses the shared generali_crud module`.

### Task 16: Split views/admin.py into a package

- [ ] Create `nx_lib/views/admin/`: `overview.py`, `organizations.py` (incl. branding), `clients.py`, `processes.py`, `system.py` (status + dev restart + maintenance), `logs.py`, `users.py` (sessions & users), `permissions.py` (access control). The file's own `# ---- section ----` banners are the split lines; helpers are cluster-local (audit-verified).
- [ ] Re-exporting `__init__.py` + fan-out `register_routes(app)` in original order (D3/D4).
- [ ] Retarget the 5 patch strings in `tests/integration/test_admin_routes.py`: `PATHS`, `engine_nexora_db`, `invalidate_branding`, `invalidate_mapping_config` → the owning submodule; `has_permission` (~10 patches) → each submodule re-imports it, tests patch the submodule that owns the route under test.
- [ ] Full admin test file green; browser smoke on `/admin`, `/admin/organizations`, `/admin/processes`, `/admin/access-control`.
- [ ] Commit: `refactor(views): split admin.py into a views/admin package`.

### Task 17: Docs, changelog, wrap-up

- [ ] `CHANGELOG.md` [Unreleased]: consolidated Changed/Removed/Performance entries.
- [ ] `CLAUDE.md`: routing convention line now mentions view *packages*; `docs/howto/nx.md` autopilot flags gone (if not done in Task 2); fix any doc that references `nx_lib/views/generali.py`/`admin.py` as files.
- [ ] Full gate: fast tier + `scripts/test_db_reset.py` + integration suite green.
- [ ] Commit: `docs: sync changelog and structure docs for beautification phase 0+1`.

---

## Follow-on (Phase 2/3 — needs owner green-light, planned separately)

1. **reporting.py split** — lift the 810-line AI cluster first; `nx_lib/reporting/runner.py` back-imports 12 symbols (`from ..views import reporting as rv`) that must stay reachable; ~30 test patch strings.
2. **workitems logic extraction** — pure sibling package (the `nx_lib/reporting/` precedent), not a route split; `api_external.py` imports 10 symbols.
3. **Shim-ification** — `_workitems_overview_js.html` (−1,650) then `_reporting_js.html` (−1,900; **must widen `test_reporting_i18n_lint.py` to `static/js/` in the same commit**), then the `reporting_simple.js` 5-file split (`window.RS` namespace; zero-fill cluster is the pilot).
4. **Perf mediums** — `COUNT(*) OVER()` in the workitems paging CTE (biggest lever on the measured 638ms), batch the prepared-docs per-PID N+1, NexoraDB pool ≥ 32 waitress threads + ODBC login timeout, skip unchanged session writes, bound the reporting health probe.
5. **Typing ratchet** — `check_untyped_defs = true` (69), then per-module `disallow_untyped_defs` via overrides.
6. **conn/cursor `contextlib.closing`** — opportunistic as files get touched, never a standalone sweep.

## Gotchas & notes

- **Monkeypatch targets are the #1 split hazard**: `monkeypatch.setattr("nx_lib.views.X.name", …)` rebinds the package attribute; a submodule's own binding wins silently. D4's re-export rule + per-submodule patching (Task 16) is the mitigation — after any split, deliberately break one patched function to prove its test still fails (no vacuous passes).
- **Deleting files on a branch older than current dumps** can trip `sql-sync-check` on unrelated drift — that's the stale-dump trap, not your change (`SQL_SYNC_SKIP=1` pathspec commit).
- **Chart pages after Task 11**: `reporting_simple.js` and `reporting_dashboard.js` byte-share their `api` copy — both use the non-throwing flavour; keep `NX.apiSafe` there or error paths change.
- **`nx_core.js` must load before every consumer** — it's a plain script tag ordered in `_header.html`; anything loaded above the header include cannot use it.
- **Do not touch** `# ponytail:`-marked modules (`compression.py`, `user_cache.py`, `extensions.client_ip`, `version.py`) — deliberate shortcuts, audited and closed.
