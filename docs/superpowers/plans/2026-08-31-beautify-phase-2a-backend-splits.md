# Beautification Phase 2a — reporting/workitems backend splits — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Distilled from the five-agent audit of 2026-08-31 (`v3.2.4.1` HEAD `0da9f522`); key anchors re-verified in the planning session. Anchor on quoted snippets + symbol names, never line numbers; re-Grep before editing — **Phase 0+1 will have moved code by execution time.**

**Prerequisite:** `docs/superpowers/plans/2026-08-31-beautify-phase-0-1.md` executed and merged. Shared context (worktree rules, env copies, gitlint, SQL_SYNC_SKIP, test commands) lives in that plan's "Context an engineer needs" — read it first; it all applies here. **Migrations needed: NO.**

**Goal:** The last two monster view files become navigable: `nx_lib/views/reporting.py` (~3.7k lines, 40 rules) becomes a package split by feature cluster; `nx_lib/views/workitems.py` (~2.5k lines, only 16 rules) gets its non-route logic extracted into a pure sibling package following the `nx_lib/reporting/` precedent.

**Architecture:** Same registration model as Phase 1 — no Blueprints, package `__init__.py` re-exports everything and fans `register_routes(app)` out to submodules in original order; `nx_lib/__init__.py` untouched, endpoint names untouched.

---

## Context specific to this plan

- **`nx_lib/reporting/runner.py` back-imports the view module** — `from ..views import reporting as rv` (two sites) — and reads 12 attributes off it including `metric_result_columns`, `_SQL_TARGETS`, `_run_sql`, `_execute`, `_effective_scope`, and the **re-exported** `engine_statistics_db`. Every one must stay reachable as `nx_lib.views.reporting.<name>` via the package `__init__` — add an explicit re-export list and a unit test asserting all 12 resolve.
- **~30 monkeypatch strings** in `tests/integration/test_reporting_*.py` target `nx_lib.views.reporting.<name>`. Patching a package attribute does NOT rebind a submodule's own binding — retarget each patch string to the owning submodule as its cluster moves. After each move, deliberately break one patched function to prove the test still fails (no vacuous passes).
- **`api_external.py` imports 10 symbols from `.workitems`** (`DOCFIELD_OPS, WORKITEM_STAGES, _get_workitems_data, _load_media_info, …`) and `dashboard.py` imports 2 (`sensitive_blocked_tokens, strip_sensitive_fields`). Update both importers to the new package; keep re-exports in `views/workitems` for tests.

## Decisions locked in

| # | Decision | Rationale |
|---|---|---|
| D1 | reporting.py becomes `views/reporting/` split by cluster; the ~700-line shared core (`_effective_sources`, `_metrics_for_source`, `_prepare_run`, `_execute`, `_run_sql`, SQL-target constants) goes to `_shared.py`. | The core spans five clusters (audit-measured); everything else is cleanly cluster-local. |
| D2 | AI cluster (~810 lines, 4 routes) moves FIRST as its own commit — it is the largest and most self-contained slice (`_audit_ai`'s 16 call sites are all internal). | Proves the pattern at lowest risk before the entangled clusters move. |
| D3 | workitems is a **logic extraction**, not a route split: helpers move to a new pure package `nx_lib/workitems/`; `views/workitems.py` stays one file of routes (~1.1k lines after). | Only 16 routes; the bulk is `_get_workitems_data` (395 lines) + five interlocking helper blocks. Splitting routes would relocate the tangle, not resolve it (audit verdict). |
| D4 | `nx_lib/workitems/` modules must stay Flask-free (import no `request`/`session`) — scope/permission inputs are passed in as arguments. | The `nx_lib/reporting/` precedent: "pure-Python building blocks … unit-test without a database". |

# PHASE A — views/reporting package

### Task 1: Convert to package, lift the AI cluster

- [ ] `git mv nx_lib/views/reporting.py nx_lib/views/reporting/__init__.py` — commit this rename alone (zero behavior, clean diff history).
- [ ] Create `nx_lib/views/reporting/ai.py`: move the AI cluster — `_ai_config`, `_ai_schema_text`, `_ai_catalog_text`, `_validate_definition_for_user`, `_normalize_definition`, `_audit_ai`, `_ai_daily_limit`, `_ai_asks_today` + the 4 AI routes (`ask`/`build`/`agent`/`caption`) and their `register_routes` lines.
- [ ] `__init__.py` re-exports every moved name; retarget the AI-related patch strings (`_ai_config`, `_ai_schema_text`, `_ai_catalog_text`, `_ai_daily_limit`, `_ai_asks_today`, `_audit_ai`, `ai_ask`, `ai_ask_definition`, `ai_caption`, `ask_agentic`, …) to `nx_lib.views.reporting.ai.<name>`.
- [ ] Vacuous-pass probe + `tests/integration/test_reporting_ai*.py` green.
- [ ] Commits: `refactor(views): make reporting a package` / `refactor(reporting): move the AI cluster to views/reporting/ai.py`.

### Task 2: Extract the shared core

- [ ] Create `_shared.py`: SQL-target constants (`_SCOPE_PREFIX`, `_SQL_TARGETS`, `_SQL_TARGET_PERMISSION`, `_CURATED_ENGINES`), source/metric registry (`_load_db_sources`, `_effective_sources`, `_get_effective_source`, `_load_db_metrics`, `_metrics_for_source`, `metric_result_columns`, `_accessible_metrics`), run pipeline (`_allowed_processes`, `_load_process_configs`, `_load_field_col_maps`, `_effective_scope`, `_prepare_run`, `_execute`, `_run_sql`, `_json_safe`), auth/audit (`_authorize_sql_target`, `_has_acked`, `_audit_sql`).
- [ ] Add unit test: the 12 `runner.py`-consumed attributes resolve on `nx_lib.views.reporting` (import-and-assert loop).
- [ ] Retarget core patch strings; vacuous-pass probe; reporting integration suite green.
- [ ] Commit: `refactor(reporting): extract the shared run/registry core to _shared.py`.

### Task 3: Split the remaining clusters

One submodule per commit, each: move cluster + its `register_routes` lines, re-export, retarget patches, targeted tests green.

- [ ] `pages.py` (guide + builder), `run.py` (sources/run + SQL sandbox routes), `export.py`, `reports.py` (CRUD + shares + `_preview_*`), `schedules.py`, `admin_registry.py` (sources+metrics admin + validators), `health.py` (`api_sources_health`, schema), `catalog.py` (field values / metrics API).
- [ ] `__init__.py` ends as: imports, re-export list, fan-out `register_routes` in original order (~250 lines).
- [ ] Full `tests/integration/test_reporting_*.py` + e2e reporting green; browser smoke Simple/Advanced/admin registry.
- [ ] Commits: `refactor(reporting): move <cluster> to views/reporting/<file>.py`.

# PHASE B — workitems logic extraction

### Task 4: Create nx_lib/workitems/ pure package

One commit per module; Flask-free (D4):

- [ ] `fields.py` — field config (`_build_field_config`, `_LABEL_LANGS`) + docfield DSL (`DOCFIELD_OPS`, `_docfield_predicate`, `_docfield_pairs_normalized`, `_docfield_ids_cache_key`).
- [ ] `sensitivity.py` — `get_valid_search_columns`, `strip_sensitive_fields`, `sensitive_blocked_keys/tokens`, `strip_sensitive_from_detail`.
- [ ] `query.py` — `_get_workitems_data` (395 lines), `_docfield_values_all_fields`, MS02 helpers, `_session_scope`-style scope helpers refactored to take explicit args (session reads stay in the view).
- [ ] `media.py` — `_load_media_info`.
- [ ] Commits: `refactor(workitems): extract <module> into nx_lib/workitems`.

### Task 5: Rewire consumers

- [ ] `views/workitems.py` imports from `nx_lib.workitems.*`; keeps re-exports of the old names (tests + `_may_view_workitem` patch target).
- [ ] `api_external.py` (10 symbols) and `dashboard.py` (2 symbols) import from the new package directly.
- [ ] Full workitems + api_external + dashboard integration suites green; browser smoke overview/detail/export; `/api/v1` test-env twin endpoints exercised.
- [ ] Commit: `refactor(workitems): route consumers through the extracted package`.

### Task 6: Docs & wrap-up

- [ ] `CHANGELOG.md` [Unreleased]; `CLAUDE.md` routing/workitems lines; `docs/design/architecture-conventions.md` if it names the old shapes. Full fast-tier + integration gate green.
- [ ] Commit: `docs: sync structure docs for phase 2a`.

## Gotchas & notes

- The monkeypatch/vacuous-pass discipline from the Phase 0+1 plan applies to **every** move here.
- `runner.py`'s lazy back-import exists "to avoid a heavy import at module load and any import cycle" — do not convert it to a top-level import.
- `_stamp_in_register` and friends: `_get_workitems_data` touches nearly every helper block — move it LAST within Task 4 `query.py`, after its dependencies already live in the package.
- Scheduled reports run through `ops/run_scheduled_reports.py` → `runner.py` — after Task 2, run one scheduled-report smoke (`python ops/run_scheduled_reports.py --dry-run` if available, else its tests).
