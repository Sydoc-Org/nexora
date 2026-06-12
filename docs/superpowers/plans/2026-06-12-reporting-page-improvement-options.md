# Reporting Page Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Review the current `/reporting` page, present a menu of improvement options that do not duplicate merged or already-planned work, and ship the six selected options: **alert-only schedules** (mail only when a threshold trips), a **schedule enable/disable toggle** (the existing UI-less `PUT` endpoint finally gets a caller), **visible row-limit truncation** in both result views, **"This week"/"This quarter" wizard presets**, a **wizard Back button that steps back** instead of exiting, and a **CSV option on the Simple export bar**.

**Architecture:** Alert-only schedules add two nullable columns to `dbo.ReportSchedules` (migration `0022`, mirrored into `sql/test/schema.sql`); all decidable logic lives as pure helpers in `nx_lib/reporting/schedule.py` (`validate_schedule` extension, `alert_trips`, `total_definition` — the Simple stat-card's zero-column-clone trick reused server-side), so `ops/run_scheduled_reports.py` only grows a thin gate before `send_mail` plus an extracted `_advance()`. All frontend work is additive ES5 inside the existing IIFEs, anchored on quoted code (never line numbers) so it merges cleanly regardless of when the in-flight drill-through plan executes. No new permissions, no new pages, no new dependencies, no refactors. No spec exists for this plan; the options menu below is the decision record.

**Tech Stack:** Flask, Jinja2 + vanilla ES5 IIFE, Chart.js 4.5.1, SQL Server (pyodbc), pytest + Playwright, Flask-Babel.

---

## Context an engineer needs (read first)

- **Branch:** worktree `.claude/worktrees/plan-reporting-page-improvement-options`, branch `plan/reporting-page-improvement-options`, based on `feature/2.5.63` @ `9e8236c`. The rich-export bundle (Show query, ≤3 breakdowns, multi-series/stacked charts, styled XLSX + embedded chart, chart-PNG button, scheduled-mail charts), the simple-guide wizard improvements, and the Simple/Advanced tab split are **already merged beneath us** — nothing here re-does any of it.
- **SEQUENCING — committed drill-through plan** (`docs/superpowers/plans/2026-06-11-reporting-drill-through.md`): Task 1 (`is_null` symmetry) is DONE; Tasks 2–8 are unblocked but **not implemented**. They will edit `templates/reporting.html`, `static/css/reporting.css`, `templates/_reporting_simple.html`, `templates/js/_reporting_simple_js.html`, `templates/js/_reporting_js.html`, `templates/js/_reporting_viz_js.html`, `nx_lib/views/reporting.py`, and the reporting test files. Every edit in THIS plan to those files is additive and sits outside drill-through's hot zones (`mountChart` internals, `renderTable`/`renderResults` row-click wiring, the drill drawer). Drill-through Task 3 Step 2 copies the `rsExport` fetch body — after our Task 9 that body carries a format variable; the copy instruction still works verbatim. **Merge-order rule: whichever plan executes second re-anchors its edits on the quoted snippets, never on line numbers.**
- **SEQUENCING — sibling planning session** on branch `plan/reporting-loading-states-sql-display` (worktree exists, no plan committed yet): run-button loading/disabled states in Simple `runCurrent` / Advanced `run()`, library skeleton/failure states, and SQL-panel display polish are **off-limits here** — they are flagged in the menu, not planned. That is also why **parallelizing the Simple total+breakdown runs is NOT selected**: it rewrites the exact `runCurrent` dispatch seam the sibling session presumably owns. Same merge-order rule applies.
- **Anchor on quoted code and function names, never line numbers** — in-flight merges shift every line in the reporting frontend files. Every snippet below was verified verbatim against the live worktree.
- **Jinja template cache:** nexora caches templates for the process lifetime. Restart the dev server (`nx -u`) after every template edit before browser-verifying. (The pytest e2e fixture starts its own fresh server on port 8765, so e2e is unaffected.)
- **E2E constraints (TEST has no Statistics DB):**
  - Where a real path exists, e2e seeds `table`-provider sources via the admin API in-page over `dbo.Users` (the `test_wizard_category_breakdown_to_result_cards` pattern in `tests/e2e/test_reporting_simple.py`).
  - Where TEST physically cannot provide the precondition, e2e uses `page.route` stubs (the `_stub_ai_build` precedent in the same file): wizard time presets need a `grainable` date field, which no `table`-provider source has (`table_source_catalog` never emits `grainable`); Advanced truncation is stubbed on `/api/reporting/run`.
  - **Stub-timing fact (load-bearing):** the Simple pane fetches `/api/reporting/metrics` in `initOnce()` at the `rp:tabshown` event — i.e. at **page load**, not at first wizard open — and may fetch `/api/reporting/sources` equally early. Catalog stubs must therefore be registered **before `page.goto`**, or the pane caches real data and the stubbed source never appears.
  - Run `python scripts/test_db_reset.py` before e2e (stale `ReportingSqlAck` state breaks order-dependent tests) and kill stale port-8765 servers.
- **Pre-commit:** the known INT `SchemaMigrations` CRLF-checksum drift makes the SQL hooks fail on every commit. Use the documented escape hatch and restore the variable afterwards: `$env:SQL_SYNC_SKIP = "1"; git commit ...; Remove-Item Env:SQL_SYNC_SKIP`. Never `--no-verify`. The ruff-format hook may reformat on the first attempt — `git add -u` and commit again. `.gitlint` caps commit titles at **72 chars**; every commit message below is measured to fit.
- **i18n:** every new user-visible string is wrapped (`{{ _("...") }}` / `|tojson`) and Task 10 runs the pybabel cycle for de/fr/it, or `tests/unit/test_translations.py` fails. Expect that test to be red between the first new msgid and Task 10 — it runs at the pre-**push** gate, not per-commit.
- **Migrations needed: YES** — one: `sql/_migrations/NexoraDB/0022_report_schedule_alerts.sql` (next free number after `0021_disable_workitem_count_metric.sql`; GeneraliDB untouched), mirrored into `sql/test/schema.sql`. Because commits run with `SQL_SYNC_SKIP=1`, the auto-apply-to-INT convention is suspended — Task 1 applies it manually. **New permissions: NO. New dependencies: NO. Deploy-exclude changes: NO** — everything lands inside `nx_lib/`, `templates/`, `static/`, `ops/`, `sql/`, `tests/`; `ops/` ships to the server, which the scheduler change needs.
- **Key verified facts:** `PUT /api/reporting/reports/<id>/schedules/<sid>` (`api_reports_schedules_update`) exists, is registered, validates — and **no UI calls it**. `api_run` returns `rowCount` (= rows returned) and `truncated` (`len(rows) >= min(rowLimit, MAX_ROW_LIMIT)`) — **no template reads either**. `tokens.py` resolves `this_week` (`_week_of`) and `this_quarter`, and `I18N.thisWeek`/`I18N.thisQuarter` labels already exist translated in `_reporting_simple_js.html` — only `renderTimeStep`'s preset array and `WIZ_TOKENS` omit them. `rsWizardBack`'s entire handler is `setView('library')`. `rsExport` hardcodes `{ format: 'xlsx' }`. The runner integration test (`test_runner_dry_run_processes_due_table_report` in `tests/integration/test_reporting_routes.py`) already imports `ops.run_scheduled_reports` inside the TEST app — the alert-gate test reuses that exact pattern (`send_mail` is imported into the module namespace, so `patch("ops.run_scheduled_reports.send_mail")` works; `patch` and `datetime` are already module-level imports in that test file).

## Current state review

**What /reporting does today.** The page (permission `reporting.view`) renders a Simple/Advanced tab strip (initial tab: `?tab=` > localStorage > `simple`). The **Simple tab** is a report library in three groups (shared / mine / shared-with-me, sql-kind filtered out) plus a 3-step wizard: measure (metric-registry rows per source), up to three breakdowns (one date with day–year grain, curated category dims, optional process scope), and a time-range step (presets + flatpickr custom range, date-field select). Running builds a v1 definition and shows a result view: grand-total stat card (computed via a zero-column clone run), a private multi-series Chart.js chart with type switcher and PNG download, a collapsible XSS-escaped table, a Show-query panel (echoed SQL + params + copy), click-to-edit definition chips, and resolved relative-date labels on the message line. Save / Adjust-in-wizard / Open-in-Advanced / Export(xlsx) round out the bar; an Ask-AI bar with refine drafts definitions through `/api/reporting/ai/build`. The **Advanced tab** is a 3-column builder (source/scope/fields → results → metrics/columns/filters/sort wells) with Table and SQL-sandbox modes, the Ask-AI panel (build / write-SQL / agent surfaces), Grid/Chart/Pivot views via the ReportingViz singleton, saved-reports load/rename/delete, a share modal, a schedule modal (add/remove only), and xlsx/csv export that re-runs the definition server-side into a styled workbook. **Offline**, `ops/run_scheduled_reports.py` (Task Scheduler) executes due schedules as their owners via `execute_definition`, renders a matplotlib chart, and mails via Graph. The backend validates definitions per-source, resolves date tokens server-side, clamps scope to permission grants, caps rows (5000 default / 50000 max), and returns `columns/rows/rowCount/truncated/sql/params/resolvedDates`.

**Strengths.** A single validated definition contract feeds web runs, exports, the scheduler, and AI surfaces; permission/scope clamping is server-side everywhere; the pure-helper layering (`schema`/`tokens`/`schedule`/`export`/`chart_render`) makes backend TDD cheap; the Simple pane is genuinely self-serve (registry-driven measures, chips, AI refine, runSeq race guard, zero-column total trick); export quality is high (styled XLSX, embedded charts, formula-injection guard); the test pyramid is real, with working e2e patterns for both API-seeded table sources and route stubs.

**Gaps found in this review** (all verified): the server's `truncated`/`rowCount` flags are returned by `api_run` but **no template ever reads them** — a capped result is indistinguishable from a complete one; the wizard's time step omits `this_week`/`this_quarter` even though `tokens.py` resolves both and translated labels already exist (so AI-drafted quarter reports also lose "Adjust in wizard" via `WIZ_TOKENS`); the wizard's prominent "← Back" button is wired to `setView('library')` — it discards every pick instead of stepping back; Simple export hardcodes `{ format: 'xlsx' }` while Advanced offers CSV from the same endpoint; the schedule modal can only add/remove (the registered PUT update endpoint has no caller, "(disabled)" rows are a dead end) and every schedule mails unconditionally — there is no "mail me only when something is wrong" mode; the Simple pane makes two sequential round-trips per run; the Advanced pane speaks in 18 blocking `window.alert`/`window.confirm` dialogs; result tables have no client-side sort; the Advanced chart is still single-series; modals lack dialog semantics; five CDN assets are availability/privacy liabilities; a couple of dead flags (`fromWizard`, vestigial `groupBy`) mislead readers.

## Improvement options menu

| # | Option | What / why (one line) | Value | Effort | Conflicts / sequencing | Selected |
|---|--------|------------------------|-------|--------|------------------------|----------|
| 1 | **Alert-only schedules** | Threshold condition on a schedule; mail only when the total trips — turns reports into monitoring; runner-up never planned | High | M | None — `schedule.py`, migration `0022`, `ops/`, schedule-modal DOM region only | **YES — Tasks 1–5** |
| 2 | **Schedule enable/disable toggle** | `PUT /schedules/<sid>` exists and validates but no UI calls it; "(disabled)" is a dead end | Med | S | Same modal region as #1 — done together | **YES — Task 5** |
| 3 | **Surface row-limit truncation** | `api_run` returns `truncated`/`rowCount`; no template reads them — capped results silently lie | High | S | Additive in `runCurrent`/`renderResults`; re-anchor if sibling loading-states plan lands first | **YES — Task 6** |
| 4 | **`this_week`/`this_quarter` wizard presets** | Tokens resolve server-side and labels are already translated; only the preset list + `WIZ_TOKENS` omit them | High | S | None (wizard step untouched by in-flight work) | **YES — Task 7** |
| 5 | **Wizard Back steps back** | `rsWizardBack` handler is exactly `setView('library')` — discards all picks; ✕ already exists as the exit | High | S | None | **YES — Task 8** |
| 6 | **Simple CSV export option** | `rsExport` hardcodes xlsx; Advanced feeds the same `/api/reporting/export` with a csv select | Med-High | S | Drill-through Task 3 copies the `rsExport` body — instruction stays valid after this | **YES — Task 9** |
| 7 | Parallelize Simple total+breakdown runs | Two sequential POSTs per run; overlap would halve perceived latency | Med | S | **Rewrites the `runCurrent` dispatch seam the sibling loading-states session presumably owns — flagged, not planned** | No |
| 8 | Inline notices replace `window.alert`/`confirm` | 18 blocking dialogs (17 alert + 1 confirm; Task 5 adds one more in the file's idiom); generali floating-flash + `promptName` modal are the precedents | Med-High | M | Diffuse edits across `_reporting_js.html`; also updates 2 e2e dialog handlers | No — **swap-in #1** |
| 9 | Schedule QoL extras (edit-in-place, send-test-now, local-time hint) | Prevent off-by-an-hour UTC mistakes; verify a schedule without waiting a day | Med | M | Same modal as #1/#2 — sequence after this plan; send-test-now needs a new endpoint | No — swap-in #2 |
| 10 | Client-side table sort (+ paging/sticky header) | Both panes dump up to 5000 rows with no header-click sort | High | M | **Must land after drill-through Tasks 4/5** (same renderers get row-click wiring) | No |
| 11 | Advanced chart parity (multi-series + resolvedDates) | 2-dim results collapse to one summed series in Advanced; resolved date labels Simple-only | Med | L | `_reporting_viz_js.html` is drill-through Task 5's hottest zone | No |
| 12 | Pin report to dashboard | The dashboard widget backend has **no frontend consumer** — this is really "ship the widget dashboard" + a report widget type | High | XL | Needs its own spec+plan (dashboard frontend first); `execute_definition` is the ready primitive | No — Owner roadmap |

*Further runner-ups considered but not menu-ranked: vendor the five CDN assets locally (M — intranet resilience + fonts privacy; an infra/deploy call, not a feature plan's), modal a11y / focus traps (M — best done once, together with the drill-through drawer), dead-code cleanup of the write-only `fromWizard` flag and vestigial `groupBy: []` (S — fold into any future touch of those files; zero user value under this plan's zero-refactor stance).*

**Excluded — already done, planned, or owned elsewhere (not options):**

| Item | Why it is not an option |
|------|--------------------------|
| Drill-through (charts/tables → underlying rows drawer) | Fully planned in `2026-06-11-reporting-drill-through.md`; Task 1 done, Tasks 2–8 queued — do not re-plan |
| Show-query panel, ≤3 wizard breakdowns, multi-series/stacked charts, styled XLSX + embedded chart, chart-PNG button, scheduled-mail inline charts, zero-dim totals, adjust-in-wizard, Simple/Advanced tab split | Merged into `feature/2.5.63` (rich-export + simple-guide + Spec 2) — already beneath this branch |
| Run-button loading/disabled states, library skeleton/failure states, SQL-display polish, parallel Simple runs | In-progress sibling session `plan/reporting-loading-states-sql-display` — flag, don't plan into it |

### Decisions locked in

| # | Question | Decision |
|---|----------|----------|
| 1 | Which options ship | Menu rows 1–6: one M-sized feature (alert-only schedules) + one S-sized parity fix in the same modal (enable/disable toggle) + four S-sized UX fixes. Owner may swap (see Owner actions). |
| 2 | Alert operators | `gt`/`gte`/`lt`/`lte` only — **no `eq`/`ne`** (float-equality footgun). Absent/empty `alertOp` = always send (existing behavior, fully back-compatible, no backfill). |
| 3 | Alert storage / validation | `AlertOp NVARCHAR(8) NULL` + `AlertThreshold FLOAT NULL` via migration `0022`. Validation is **app-side only** in `validate_schedule` — **no DB CHECK constraint**, so the TEST schema mirror stays byte-for-byte equivalent to INT/PROD behavior. |
| 4 | What number the alert checks | Grand total of the **first metric** via a zero-column deep clone (new pure helper `total_definition`, mirroring the Simple stat card — correct for `avg`/`count_distinct`), executed as the owner through the existing `execute_definition`. Definitions without metrics (incl. `kind=='sql'`) use the main result's **row count**. |
| 5 | Not-tripped behavior | Skip the mail, log one info line, still set `LastRunAt` and advance `NextRunAt` (otherwise the schedule re-fires every Task-Scheduler tick). `--dry-run` prints the decision and advances nothing. `alert_trips` never trips on `None`/non-numeric values or unknown ops — a malformed result skips the mail rather than spamming. |
| 6 | Schedule parity scope | Enable/disable toggle only, via the existing unused `PUT` (body rebuilt from the serialized row). PUT stays **full-replace**: a body without alert fields clears them; PUT also recomputes `NextRunAt` (documented). Edit-in-place / send-test-now / local-time hint deferred (menu row 9). |
| 7 | Truncation note | One shared msgid: `"Showing the first {n} rows — narrow the filters or time range to see the rest."` with `n = rowCount`. Simple: appended to `rsMsg` (the resolvedDates idiom). Advanced: an amber `p.reporting-truncated-note` inserted **above** the result table inside `renderResults` (covers curated *and* SQL-sandbox results). Shown only when `truncated` is true. |
| 8 | Preset order & round-trip | This week, This month, Last month, This quarter, Last quarter, Last 3 months, This year, Last year, All time, Custom. `WIZ_TOKENS` gains both tokens so such definitions keep "Adjust in wizard". |
| 9 | Back semantics | Visibility-state stepping (time → breakdown → measure → library), leveraging the existing progressive-reveal step model; the ✕ (`rsWizardClose`) stays the immediate exit; picks are preserved in `state.wiz`. |
| 10 | Simple CSV control | A `<select id="rsExportFormat">` reusing the existing `.reporting-export-format` class and the existing `"Excel"`/`"Export format"` msgids (**zero new strings, zero new CSS**); `chartImage` attaches only for xlsx. |
| 11 | Testing strategy | Pure helpers: unit TDD. Endpoints + runner: integration TDD (the existing ops-module harness with `send_mail` patched). UI with a TEST-reachable path: Playwright TDD on admin-seeded table sources. UI whose precondition TEST cannot produce: Playwright TDD on `page.route` stubs — **registered before `page.goto`** (metrics is fetched at `rp:tabshown`). The INT walkthrough in Task 11 is confirmation, never the only verification. |
| 12 | Merge order vs in-flight work | Phases 1–2 may run any time (zero collision). Phases 3–4 share files (not functions) with drill-through Tasks 2–8 and the sibling session — whichever lands second re-anchors on quoted snippets. |

## Owner actions

1. **Apply migration 0022 to INT manually** after Task 1 commits: `python scripts/db-migrate.py --env INT` (the `SQL_SYNC_SKIP=1` escape hatch suppresses the auto-apply hook). The known CRLF checksum drift may make this fail wholesale — if so, this joins the owed "re-bless INT SchemaMigrations" fix.
2. **PROD deploy coupling — read this:** after Task 4, `_due_schedules` SELECTs `s.AlertOp, s.AlertThreshold`, so the new `ops/run_scheduled_reports.py` **crashes every scheduled run** against a DB without 0022 — not just alert ones. Migration and `ops/` code ship in the same deploy train, so order is automatic **unless someone cherry-picks the ops change alone — don't**. (Pre-existing PROD debts unchanged: the runner's Task Scheduler task, the two reporting RO SQL logins, migrations 0015+.)
3. **Merge-order call vs the sibling session** (`plan/reporting-loading-states-sql-display`): whichever plan executes second rebases and re-anchors `runCurrent`/`renderResults`-area edits on the quoted snippets. Tell the sibling session which message areas Task 6 claims (`rsMsg` append, `renderResults` note). Record in the handoff.
4. **Option swaps:** menu row 8 (alert/confirm → flash sweep) is swap-in #1, row 9 (schedule QoL) swap-in #2 — either can replace Task 8 or 9 if cut; row 10 (table sort) only after drill-through lands; row 12 (pin-to-dashboard) needs its own plan covering the dashboard-frontend prerequisite first — say the word.
5. **INT verification dependency:** Task 7's presets and the alert dry-run check in Task 11 need INT up (real grainable date fields / real schedules). The automated suites do not.
6. Do **not** restore the unrelated `env/CONFLUENCE.env.example` deletion visible in the **main checkout's** git status (`C:\dev\nexora` — this plan worktree itself is clean) — it belongs to `feat/confluence-docs-sync`. Never `git add -A`. Remote policy: execution stops at commits; you push and open the PR.

---

# PHASE 1 — Alert-only schedules: backend (safe immediately, zero in-flight collisions)

### Task 1: Migration 0022 + TEST schema mirror — `AlertOp` / `AlertThreshold`

Schema-only task (no failing test possible before the columns exist; behavior TDD starts in Task 2). The TEST mirror is **not optional** — `scripts/test_db_reset.py` provisions from `sql/test/schema.sql`, and Tasks 3–4's integration tests need the columns.

**Files:**
- Create: `sql/_migrations/NexoraDB/0022_report_schedule_alerts.sql`
- Modify: `sql/test/schema.sql`

- [ ] **Step 1: Create the migration** (next free number after `0021_disable_workitem_count_metric.sql`; pure ASCII — the sqlcmd UTF-8 gotcha does not apply):

```sql
-- 0022_report_schedule_alerts.sql
-- Alert-only scheduled reports: a schedule may carry a threshold condition
-- (AlertOp + AlertThreshold). The runner (ops/run_scheduled_reports.py) only
-- mails when the report's grand total (or row count for non-metric
-- definitions) satisfies it. NULL AlertOp = always send (the default; fully
-- back-compatible). Ops (gt/gte/lt/lte) are validated in the app layer
-- (nx_lib/reporting/schedule.py ALERT_OPS) -- no DB CHECK on purpose, so the
-- TEST schema mirror stays equivalent. Idempotent.

IF COL_LENGTH(N'dbo.ReportSchedules', N'AlertOp') IS NULL
    ALTER TABLE dbo.ReportSchedules ADD AlertOp NVARCHAR(8) NULL;
GO

IF COL_LENGTH(N'dbo.ReportSchedules', N'AlertThreshold') IS NULL
    ALTER TABLE dbo.ReportSchedules ADD AlertThreshold FLOAT NULL;
GO
```

- [ ] **Step 2: Mirror into the TEST schema.** In `sql/test/schema.sql`, inside the `CREATE TABLE dbo.ReportSchedules` block, find the verified lines

```sql
        LastRunAt    DATETIME2 NULL,
        NextRunAt    DATETIME2 NULL,
```

and add directly below:

```sql
        AlertOp      NVARCHAR(8) NULL,
        AlertThreshold FLOAT NULL,
```

- [ ] **Step 3: Rebuild TEST and confirm nothing regressed**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/integration/test_reporting_routes.py -v -k "schedule or runner"
```
Expected: reset succeeds; all existing tests PASS (columns are nullable; nothing reads them yet).

- [ ] **Step 4: Commit, then apply to INT manually** (the escape hatch suppresses the auto-apply hook):

```powershell
git add sql/_migrations/NexoraDB/0022_report_schedule_alerts.sql sql/test/schema.sql
$env:SQL_SYNC_SKIP = "1"; git commit -m "feat(reporting): add schedule alert columns (0022)"; Remove-Item Env:SQL_SYNC_SKIP
python scripts/db-migrate.py --env INT
```
Expected: commit lands; the INT apply either succeeds or fails on the known CRLF checksum drift — if it fails, record it for the owner (Owner action 1) and continue (TEST is what the suite uses).

---

### Task 2: Pure helpers — alert validation, `alert_trips`, `total_definition`

**Files:**
- Modify: `nx_lib/reporting/schedule.py`
- Test: `tests/unit/test_reporting_schedule.py`

- [ ] **Step 1: Write the failing tests.** Append to `tests/unit/test_reporting_schedule.py`, and extend its verified import block

```python
from nx_lib.reporting.schedule import (
    compute_next_run,
    parse_recipients,
    valid_recipients,
    validate_schedule,
)
```

with `ALERT_OPS, alert_trips, total_definition` (alphabetical):

```python
def test_validate_schedule_alert_pair():
    base = {"frequency": "daily", "hour": 6, "recipients": "a@x.com"}
    assert validate_schedule(base) is None  # no alert fields: always send
    assert validate_schedule({**base, "alertOp": "gt", "alertThreshold": 100}) is None
    assert validate_schedule({**base, "alertOp": "lte", "alertThreshold": "-2.5"}) is None
    assert validate_schedule({**base, "alertOp": ""}) is None  # the UI's "Always" option
    assert validate_schedule({**base, "alertOp": "eq", "alertThreshold": 1})  # eq not offered
    assert validate_schedule({**base, "alertOp": "gt"})  # threshold missing
    assert validate_schedule({**base, "alertOp": "gt", "alertThreshold": "soon"})


def test_alert_trips_ops():
    assert alert_trips("gt", 10, 11) is True
    assert alert_trips("gt", 10, 10) is False
    assert alert_trips("gte", 10, 10) is True
    assert alert_trips("lt", 10, 9.5) is True
    assert alert_trips("lte", 10, 10) is True
    assert alert_trips("lte", 10, 11) is False
    assert alert_trips("gt", 0, None) is False  # NULL total never trips
    assert alert_trips("bogus", 0, 1) is False  # unknown op never trips
    assert set(ALERT_OPS) == {"gt", "gte", "lt", "lte"}


def test_total_definition_zero_column_clone():
    rd = {
        "schemaVersion": 1, "source": "docprocessing", "title": "t",
        "columns": [{"field": "doctype"}], "metrics": [{"metric": "doc_count"}],
        "filters": [{"field": "import_date", "op": "between", "value": {"token": "this_month"}}],
        "sort": [{"field": "doc_count", "dir": "desc"}], "rowLimit": 5000,
    }
    td = total_definition(rd)
    assert td["columns"] == [] and td["sort"] == []
    assert td["metrics"] == rd["metrics"] and td["filters"] == rd["filters"]
    assert rd["columns"] == [{"field": "doctype"}]  # original untouched (deep copy)
    assert total_definition({"columns": [{"field": "a"}]}) is None  # no metrics
    assert total_definition({"kind": "sql", "sql": "SELECT 1"}) is None
```

- [ ] **Step 2: Run them, watch them fail**

```powershell
python -m pytest tests/unit/test_reporting_schedule.py -v
```
Expected: collection error — `ImportError: cannot import name 'ALERT_OPS' from 'nx_lib.reporting.schedule'`.

- [ ] **Step 3: Implement.** In `nx_lib/reporting/schedule.py`: add `import copy` above the verified `import re`; below the verified `FORMATS = ("xlsx", "csv")` add:

```python
ALERT_OPS = ("gt", "gte", "lt", "lte")
```

In `validate_schedule`, replace the verified trailing block

```python
    if p.get("frequency") == "monthly":
        dom = p.get("dayOfMonth")
        if dom is None or not 1 <= int(dom) <= 28:
            return "dayOfMonth must be 1-28 for a monthly schedule"
    return None
```

with

```python
    if p.get("frequency") == "monthly":
        dom = p.get("dayOfMonth")
        if dom is None or not 1 <= int(dom) <= 28:
            return "dayOfMonth must be 1-28 for a monthly schedule"
    alert_op = p.get("alertOp")
    if alert_op:  # absent/empty = always send
        if alert_op not in ALERT_OPS:
            return "alertOp must be gt, gte, lt or lte"
        try:
            float(p.get("alertThreshold"))
        except (TypeError, ValueError):
            return "alertThreshold must be a number"
    return None
```

Append the two new helpers at module end:

```python
def alert_trips(op, threshold, value):
    """True when `value` satisfies `<op> threshold` — the alert condition holds
    and the scheduled mail should go out. None / non-numeric values and unknown
    ops never trip (the runner then skips the mail instead of spamming)."""
    try:
        v = float(value)
        t = float(threshold)
    except (TypeError, ValueError):
        return False
    if op == "gt":
        return v > t
    if op == "gte":
        return v >= t
    if op == "lt":
        return v < t
    if op == "lte":
        return v <= t
    return False


def total_definition(definition):
    """Zero-column deep clone whose single result cell is the grand total of the
    definition's first metric — the Simple pane's stat-card trick, reused so the
    alert checks the same number the user sees (correct for avg/count_distinct).
    Returns None for definitions without metrics (incl. sql-kind); callers fall
    back to the row count."""
    if not isinstance(definition, dict) or not definition.get("metrics"):
        return None
    clone = copy.deepcopy(definition)
    clone["columns"] = []
    clone["sort"] = []
    return clone
```

- [ ] **Step 4: Run green**

```powershell
python -m pytest tests/unit/test_reporting_schedule.py -v
```
Expected: all PASS (existing tests included).

- [ ] **Step 5: Commit**

```powershell
git add nx_lib/reporting/schedule.py tests/unit/test_reporting_schedule.py
$env:SQL_SYNC_SKIP = "1"; git commit -m "feat(reporting): pure schedule helpers for alert-only delivery"; Remove-Item Env:SQL_SYNC_SKIP
```

---

### Task 3: Persist and echo alert fields through the schedule endpoints

**Files:**
- Modify: `nx_lib/views/reporting.py` (`_serialize_schedule`, `_schedule_fields`, `api_reports_schedules_get/create/update`)
- Test: `tests/integration/test_reporting_routes.py`

- [ ] **Step 1: Write the failing tests.** Append next to the verified `def test_schedule_validation_400(admin_client):` (the module's `_create_report` helper makes a sql-kind report — fine for schedule CRUD, it is never run):

```python
def test_schedule_alert_fields_roundtrip(admin_client):
    rid = _create_report(admin_client)
    try:
        cr = admin_client.post(
            f"/api/reporting/reports/{rid}/schedules",
            json={"frequency": "daily", "hour": 6, "minute": 0, "format": "csv",
                  "recipients": "a@x.com", "alertOp": "gt", "alertThreshold": 250},
        )
        assert cr.status_code == 200, cr.data
        lst = admin_client.get(f"/api/reporting/reports/{rid}/schedules").get_json()
        assert lst[0]["alertOp"] == "gt" and lst[0]["alertThreshold"] == 250.0

        sid = lst[0]["id"]  # PUT without alert fields clears the condition (full-replace)
        up = admin_client.put(
            f"/api/reporting/reports/{rid}/schedules/{sid}",
            json={"frequency": "daily", "hour": 6, "minute": 0, "format": "csv",
                  "recipients": "a@x.com", "enabled": True},
        )
        assert up.status_code == 200
        lst = admin_client.get(f"/api/reporting/reports/{rid}/schedules").get_json()
        assert lst[0]["alertOp"] is None and lst[0]["alertThreshold"] is None
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid}")


def test_schedule_alert_validation_400(admin_client):
    rid = _create_report(admin_client)
    try:
        for bad in ({"alertOp": "eq", "alertThreshold": 1},
                    {"alertOp": "gt"},
                    {"alertOp": "gt", "alertThreshold": "soon"}):
            r = admin_client.post(
                f"/api/reporting/reports/{rid}/schedules",
                json={"frequency": "daily", "hour": 6, "recipients": "a@x.com", **bad},
            )
            assert r.status_code == 400, r.data
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid}")
```

- [ ] **Step 2: Run them, watch the roundtrip fail**

```powershell
python -m pytest tests/integration/test_reporting_routes.py -v -k "alert"
```
Expected: `test_schedule_alert_fields_roundtrip` FAILS with `KeyError: 'alertOp'` (the serializer doesn't emit it); the validation test already PASSES via Task 2 — fine.

- [ ] **Step 3: Implement.** Five edits in `nx_lib/views/reporting.py`:

  **(a)** In `_serialize_schedule`, find the verified adjacent pair

```python
        "enabled": bool(r.Enabled),
        "lastRunAt": str(r.LastRunAt) if r.LastRunAt else None,
```

  and replace with

```python
        "enabled": bool(r.Enabled),
        "alertOp": r.AlertOp,
        "alertThreshold": r.AlertThreshold,
        "lastRunAt": str(r.LastRunAt) if r.LastRunAt else None,
```

  **(b)** Replace `_schedule_fields` (verified body) wholesale with:

```python
def _schedule_fields(p):
    """Normalized (recipients, format, frequency, hour, minute, weekday, dom,
    enabled, next, alert_op, alert_threshold)."""
    freq = p.get("frequency")
    hour = int(p.get("hour"))
    minute = int(p.get("minute", 0))
    weekday = int(p["weekday"]) if freq == "weekly" else None
    dom = int(p["dayOfMonth"]) if freq == "monthly" else None
    enabled = 1 if p.get("enabled", True) else 0
    nxt = compute_next_run(freq, hour, minute, weekday, dom, utcnow())
    alert_op = p.get("alertOp") or None
    alert_threshold = float(p["alertThreshold"]) if alert_op else None
    return (
        p.get("recipients").strip(),
        (p.get("format") or "xlsx").lower(),
        freq,
        hour,
        minute,
        weekday,
        dom,
        enabled,
        nxt,
        alert_op,
        alert_threshold,
    )
```

  **(c)** In `api_reports_schedules_get`, change the verified SELECT head

```python
            "SELECT ScheduleID, Recipients, Format, Frequency, Hour, Minute, Weekday, "
            "DayOfMonth, Enabled, LastRunAt, NextRunAt FROM dbo.ReportSchedules "
```
  to
```python
            "SELECT ScheduleID, Recipients, Format, Frequency, Hour, Minute, Weekday, "
            "DayOfMonth, Enabled, LastRunAt, NextRunAt, AlertOp, AlertThreshold "
            "FROM dbo.ReportSchedules "
```

  **(d)** The verified unpack line `recipients, fmt, freq, hour, minute, weekday, dom, enabled, nxt = _schedule_fields(p)` appears **once in `api_reports_schedules_create` and once in `api_reports_schedules_update`** — change BOTH to:

```python
    (recipients, fmt, freq, hour, minute, weekday, dom, enabled, nxt, alert_op, alert_thr) = (
        _schedule_fields(p)
    )
```

  **(e)** In `api_reports_schedules_create`, change the verified INSERT

```python
            "INSERT INTO dbo.ReportSchedules "
            "(ReportID, OwnerUserID, Recipients, Format, Frequency, Hour, Minute, "
            " Weekday, DayOfMonth, Enabled, NextRunAt) "
            "OUTPUT INSERTED.ScheduleID VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (report_id, userid, recipients, fmt, freq, hour, minute, weekday, dom, enabled, nxt),
```
  to
```python
            "INSERT INTO dbo.ReportSchedules "
            "(ReportID, OwnerUserID, Recipients, Format, Frequency, Hour, Minute, "
            " Weekday, DayOfMonth, Enabled, NextRunAt, AlertOp, AlertThreshold) "
            "OUTPUT INSERTED.ScheduleID VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (report_id, userid, recipients, fmt, freq, hour, minute, weekday, dom,
             enabled, nxt, alert_op, alert_thr),
```

  In `api_reports_schedules_update`, change the verified UPDATE head

```python
            "UPDATE dbo.ReportSchedules SET Recipients=?, Format=?, Frequency=?, Hour=?, "
            "Minute=?, Weekday=?, DayOfMonth=?, Enabled=?, NextRunAt=?, UpdatedAt=SYSUTCDATETIME() "
            "WHERE ScheduleID=? AND ReportID=?",
```
  to
```python
            "UPDATE dbo.ReportSchedules SET Recipients=?, Format=?, Frequency=?, Hour=?, "
            "Minute=?, Weekday=?, DayOfMonth=?, Enabled=?, NextRunAt=?, AlertOp=?, "
            "AlertThreshold=?, UpdatedAt=SYSUTCDATETIME() "
            "WHERE ScheduleID=? AND ReportID=?",
```
  and add `alert_op,` and `alert_thr,` to its params tuple directly after `nxt,` (before `schedule_id`).

- [ ] **Step 4: Run green** (whole schedule surface, including the pre-existing `test_schedule_crud`):

```powershell
python -m pytest tests/integration/test_reporting_routes.py -v -k "schedule"
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add nx_lib/views/reporting.py tests/integration/test_reporting_routes.py
$env:SQL_SYNC_SKIP = "1"; git commit -m "feat(reporting): persist and echo schedule alert fields"; Remove-Item Env:SQL_SYNC_SKIP
```

---

### Task 4: Runner gate — skip the mail when the threshold doesn't trip

**Files:**
- Modify: `ops/run_scheduled_reports.py`
- Test: `tests/integration/test_reporting_routes.py`

- [ ] **Step 1: Write the failing test.** Append after the verified `test_runner_dry_run_processes_due_table_report` (the pattern being reused — table source over `dbo.Users`, past-due schedule, `run_once`; `patch`, `datetime`, and `engine_nexora_db` are already module-level imports in this file):

```python
def test_runner_alert_skips_mail_and_advances(admin_client):
    # Non-metric definition -> the alert value is the row count (>=1 seeded user).
    # 'gt 1e9' never trips: no mail, NextRunAt advances. 'gte 1' trips: mail sent.
    from ops import run_scheduled_reports

    src = admin_client.post(
        "/api/reporting/admin/sources",
        json={"code": "alert_users", "kind": "curated", "label": "Alert Users",
              "permission": "reporting.source.docprocessing", "provider": "table",
              "engine": "nexora", "baseObject": "dbo.Users",
              "columns": [{"field": "username", "label": "Username", "type": "string",
                           "filterable": True, "sortable": True}],
              "enabled": True, "sortOrder": 16},
    )
    src_id = src.get_json()["id"]
    rep = admin_client.post(
        "/api/reporting/reports",
        json={"name": "Alert Users Report",
              "definition": {"schemaVersion": 1, "source": "alert_users",
                             "visualization": "table", "title": "Alert Users Report",
                             "columns": [{"field": "username"}], "filters": [],
                             "sort": [], "scope": {}, "rowLimit": 10}},
    )
    rid = rep.get_json()["id"]
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT userID FROM dbo.Users WHERE username = 'admin@test.local'")
        owner = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO dbo.ReportSchedules (ReportID, OwnerUserID, Recipients, Format, "
            "Frequency, Hour, Minute, Enabled, NextRunAt, AlertOp, AlertThreshold) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (rid, owner, "a@x.com", "csv", "daily", 6, 0, 1, datetime(2000, 1, 1), "gt", 1e9),
        )
        conn.commit()

        with patch("ops.run_scheduled_reports.send_mail") as sm:
            assert run_scheduled_reports.run_once(dry_run=False) == 0
        sm.assert_not_called()
        cur.execute(
            "SELECT NextRunAt, LastRunAt FROM dbo.ReportSchedules WHERE ReportID = ?", (rid,)
        )
        nxt, last = cur.fetchone()
        assert nxt > datetime(2020, 1, 1) and last is not None  # advanced, not re-fired

        cur.execute(
            "UPDATE dbo.ReportSchedules SET AlertOp='gte', AlertThreshold=1, NextRunAt=? "
            "WHERE ReportID = ?",
            (datetime(2000, 1, 1), rid),
        )
        conn.commit()
        with patch("ops.run_scheduled_reports.send_mail") as sm2:
            assert run_scheduled_reports.run_once(dry_run=False) == 0
        sm2.assert_called_once()
    finally:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.ReportSchedules WHERE ReportID = ?", (rid,))
        conn.commit()
        conn.close()
        admin_client.delete(f"/api/reporting/reports/{rid}")
        admin_client.delete(f"/api/reporting/admin/sources/{src_id}")
```

- [ ] **Step 2: Run it, watch it fail**

```powershell
python -m pytest tests/integration/test_reporting_routes.py -v -k "runner_alert"
```
Expected: FAILS at `sm.assert_not_called()` (today the runner always mails).

- [ ] **Step 3: Implement** in `ops/run_scheduled_reports.py`. Change the verified import line

```python
from nx_lib.reporting.schedule import compute_next_run, parse_recipients, utcnow
```
to
```python
from nx_lib.reporting.schedule import (
    alert_trips,
    compute_next_run,
    parse_recipients,
    total_definition,
    utcnow,
)
```

In `_due_schedules`, change the verified SELECT head

```python
        "SELECT s.ScheduleID, s.ReportID, s.OwnerUserID, s.Recipients, s.Format, "
        "       s.Frequency, s.Hour, s.Minute, s.Weekday, s.DayOfMonth, "
        "       r.Name, r.DefinitionJSON, u.username, u.locale "
```
to
```python
        "SELECT s.ScheduleID, s.ReportID, s.OwnerUserID, s.Recipients, s.Format, "
        "       s.Frequency, s.Hour, s.Minute, s.Weekday, s.DayOfMonth, "
        "       s.AlertOp, s.AlertThreshold, "
        "       r.Name, r.DefinitionJSON, u.username, u.locale "
```

Add two helpers directly above `def _process(...)`:

```python
def _advance(conn, row, now):
    """Record the run and move NextRunAt forward (shared by send and no-trip paths)."""
    nxt = compute_next_run(row.Frequency, row.Hour, row.Minute, row.Weekday, row.DayOfMonth, now)
    cur = conn.cursor()
    cur.execute(
        "UPDATE dbo.ReportSchedules SET LastRunAt = ?, NextRunAt = ?, "
        "UpdatedAt = SYSUTCDATETIME() WHERE ScheduleID = ?",
        (now, nxt, row.ScheduleID),
    )


def _alert_value(row, perms, definition, rows):
    """The number the alert condition checks: the grand total of the first metric
    (zero-column clone run as the owner — the Simple stat-card trick, correct
    for avg/count_distinct), or the row count for definitions without metrics."""
    td = total_definition(definition)
    if td is None:
        return len(rows)
    _cols, t_rows = execute_definition(td, perms, row.OwnerUserID, row.username, row.locale or "en")
    return t_rows[0][0] if t_rows and t_rows[0] else None
```

In `_process`, directly after the verified block

```python
    columns, rows = execute_definition(
        definition, perms, row.OwnerUserID, row.username, row.locale or "en"
    )
```

insert (before the chart render, so a skipped mail also skips matplotlib):

```python
    if row.AlertOp:
        value = _alert_value(row, perms, definition, rows)
        if not alert_trips(row.AlertOp, row.AlertThreshold, value):
            if dry_run:
                print(
                    f"[dry-run] schedule {row.ScheduleID} '{row.Name}': alert "
                    f"{row.AlertOp} {row.AlertThreshold} not tripped (value={value}); no mail"
                )
                return
            app.logger.info(
                f"schedule {row.ScheduleID}: alert not tripped (value={value}), mail skipped"
            )
            _advance(conn, row, now)
            return
```

Finally, replace the verified tail of `_process`

```python
    nxt = compute_next_run(row.Frequency, row.Hour, row.Minute, row.Weekday, row.DayOfMonth, now)
    cur = conn.cursor()
    cur.execute(
        "UPDATE dbo.ReportSchedules SET LastRunAt = ?, NextRunAt = ?, "
        "UpdatedAt = SYSUTCDATETIME() WHERE ScheduleID = ?",
        (now, nxt, row.ScheduleID),
    )
```

with

```python
    _advance(conn, row, now)
```

- [ ] **Step 4: Run green** (the new alert test, the pre-existing dry-run test, and the unit suite):

```powershell
python -m pytest tests/integration/test_reporting_routes.py -v -k "runner"
python -m pytest tests/unit/test_reporting_schedule.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add ops/run_scheduled_reports.py tests/integration/test_reporting_routes.py
$env:SQL_SYNC_SKIP = "1"; git commit -m "feat(reporting): runner skips mail when alert threshold not tripped"; Remove-Item Env:SQL_SYNC_SKIP
```

---

# PHASE 2 — Alert-only schedules: modal UI (modal-only DOM region — low collision)

### Task 5: Schedule modal — alert condition fields + enable/disable toggle

**Files:**
- Modify: `templates/reporting.html` (inside `#rpScheduleModal` only — a DOM region drill-through does not touch)
- Modify: `templates/js/_reporting_js.html` (scheduling section only)
- Modify: `static/css/reporting.css` (append)
- Test: `tests/e2e/test_reporting_schedule.py`

- [ ] **Step 1: Write the failing e2e test.** Append to `tests/e2e/test_reporting_schedule.py` (clone of the existing `test_schedule_modal_adds_schedule` setup — its `_login` already lands on `?tab=advanced`):

```python
@pytest.mark.flaky_e2e
def test_schedule_alert_condition_and_toggle(nexora_server, page):
    _login(page, nexora_server)
    token = page.evaluate("() => document.querySelector('meta[name=\"csrf-token\"]').content")
    headers = {"X-CSRFToken": token, "Content-Type": "application/json"}
    created = page.request.post(
        f"{nexora_server}/api/reporting/reports", headers=headers,
        data={"name": "Alert E2E",
              "definition": {"kind": "sql", "target": "statistics",
                             "sql": "SELECT 1 AS one", "title": "Alert E2E"}})
    assert created.ok, created.text()
    rid = created.json()["id"]
    try:
        page.goto(f"{nexora_server}/reporting?tab=advanced")
        page.wait_for_load_state("domcontentloaded")
        page.locator(f'[data-testid="reporting-saved-reports"] option[value="{rid}"]').wait_for(
            state="attached")
        page.locator('[data-testid="reporting-saved-reports"]').select_option(str(rid))
        page.locator('[data-testid="reporting-schedule"]').click()
        expect(page.locator('[data-testid="reporting-schedule-modal"]')).to_be_visible()

        page.locator('[data-testid="reporting-schedule-alert-op"]').select_option("gt")
        expect(page.locator("#rpSchedAlertValWrap")).to_be_visible()
        page.fill('[data-testid="reporting-schedule-alert-value"]', "100")
        page.fill('[data-testid="reporting-schedule-recipients"]', "ops@example.com")
        with page.expect_response(
            lambda r: r.request.method == "POST" and f"/reports/{rid}/schedules" in r.url
        ):
            page.locator('[data-testid="reporting-schedule-add"]').click()
        schedules = page.request.get(
            f"{nexora_server}/api/reporting/reports/{rid}/schedules").json()
        assert schedules[0]["alertOp"] == "gt" and schedules[0]["alertThreshold"] == 100.0

        with page.expect_response(
            lambda r: r.request.method == "PUT" and f"/reports/{rid}/schedules" in r.url
        ):
            page.locator('[data-testid="reporting-schedule-toggle"]').click()
        expect(page.locator('[data-testid="reporting-schedule-list"]')).to_contain_text("disabled")
        schedules = page.request.get(
            f"{nexora_server}/api/reporting/reports/{rid}/schedules").json()
        assert schedules[0]["enabled"] is False
        page.screenshot(path="var/screenshots/reporting_schedule_alert_toggle.png")
    finally:
        page.request.delete(f"{nexora_server}/api/reporting/reports/{rid}", headers=headers)
```

- [ ] **Step 2: Run it, watch it fail**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_schedule.py -v -k "alert"
```
Expected: timeout on `[data-testid="reporting-schedule-alert-op"]` (element doesn't exist).

- [ ] **Step 3: Modal markup.** In `templates/reporting.html`, inside `#rpScheduleModal`'s `.reporting-admin-grid`, find the verified Format label

```html
        <label>{{ _("Format") }}<select id="rpSchedFormat" class="reporting-input">
          <option value="xlsx">{{ _("Excel") }}</option><option value="csv">CSV</option></select></label>
```

and add directly after it (still inside the grid):

```html
        <label>{{ _("Send") }}<select id="rpSchedAlertOp" class="reporting-input" data-testid="reporting-schedule-alert-op">
          <option value="">{{ _("Always") }}</option>
          <option value="gt">{{ _("Only when the total is above…") }}</option>
          <option value="gte">{{ _("Only when the total is at least…") }}</option>
          <option value="lt">{{ _("Only when the total is below…") }}</option>
          <option value="lte">{{ _("Only when the total is at most…") }}</option></select></label>
        <label id="rpSchedAlertValWrap" hidden>{{ _("Threshold") }}<input id="rpSchedAlertVal" class="reporting-input" type="number" step="any" value="0" data-testid="reporting-schedule-alert-value"></label>
```

Then, between the closing `</div>` of `.reporting-admin-grid` and the verified `<label class="reporting-admin-cols">{{ _("Recipients (comma-separated)") }}` block, add:

```html
      <p id="rpSchedAlertHint" class="reporting-sched-alert-hint" hidden>{{ _("The threshold is checked against the report's grand total (or its row count when the report has no measure).") }}</p>
```

- [ ] **Step 4: JS wiring.** In `templates/js/_reporting_js.html`, scheduling section. After the verified line

```js
  var FREQ_LABELS = { daily: '{{ _("Daily") }}', weekly: '{{ _("Weekly") }}', monthly: '{{ _("Monthly") }}' };
```

add:

```js
  var ALERT_LABELS = { gt: '>', gte: '≥', lt: '<', lte: '≤' };

  function schedAlertChanged() {
    var alertOn = !!document.getElementById('rpSchedAlertOp').value;
    document.getElementById('rpSchedAlertValWrap').hidden = !alertOn;
    document.getElementById('rpSchedAlertHint').hidden = !alertOn;
  }
```

In `openSchedule`, after the verified `schedFreqChanged();` line add `schedAlertChanged();`.

In `renderSchedules`, replace the verified description builder

```js
      var desc = (FREQ_LABELS[s.frequency] || s.frequency) + ' ' + t + ' UTC · ' +
        s.format.toUpperCase() + ' · ' + s.recipients + (s.enabled ? '' : ' (' + '{{ _("disabled") }}' + ')');
```

with

```js
      var desc = (FREQ_LABELS[s.frequency] || s.frequency) + ' ' + t + ' UTC · ' +
        s.format.toUpperCase() + ' · ' + s.recipients +
        (s.alertOp ? ' · ' + '{{ _("only when total") }}' + ' ' +
          (ALERT_LABELS[s.alertOp] || s.alertOp) + ' ' + s.alertThreshold : '') +
        (s.enabled ? '' : ' (' + '{{ _("disabled") }}' + ')');
```

Still inside `renderSchedules`, directly before **its** `var rm = document.createElement('button');` line (the one in this function — the string appears in other functions too), add the toggle:

```js
      var tg = document.createElement('button');
      tg.type = 'button';
      tg.className = 'reporting-link';
      tg.dataset.testid = 'reporting-schedule-toggle';
      tg.textContent = s.enabled ? '{{ _("Disable") }}' : '{{ _("Enable") }}';
      tg.onclick = function () { setScheduleEnabled(s, !s.enabled); };
      li.appendChild(tg);
```

Add next to `deleteSchedule`:

```js
  // Flip Enabled via the (previously UI-less) PUT update endpoint. PUT is
  // full-replace and recomputes NextRunAt, so re-enabling re-anchors the next
  // run. The window.alert matches the file's current idiom (menu row 8 sweeps
  // them all later).
  function setScheduleEnabled(s, enabled) {
    var body = {
      frequency: s.frequency, hour: s.hour, minute: s.minute,
      format: s.format, recipients: s.recipients, enabled: enabled,
    };
    if (s.frequency === 'weekly') body.weekday = s.weekday;
    if (s.frequency === 'monthly') body.dayOfMonth = s.dayOfMonth;
    if (s.alertOp) { body.alertOp = s.alertOp; body.alertThreshold = s.alertThreshold; }
    api('/api/reporting/reports/' + scheduleReportId + '/schedules/' + s.id, {
      method: 'PUT', body: JSON.stringify(body),
    }).then(loadSchedules).catch(function (e) { window.alert(e.message); });
  }
```

In `addSchedule`, after the verified lines

```js
    if (freq === 'weekly') body.weekday = parseInt(document.getElementById('rpSchedWeekday').value, 10);
    if (freq === 'monthly') body.dayOfMonth = parseInt(document.getElementById('rpSchedDom').value, 10);
```

add:

```js
    var alertOp = document.getElementById('rpSchedAlertOp').value;
    if (alertOp) {
      body.alertOp = alertOp;
      body.alertThreshold = parseFloat(document.getElementById('rpSchedAlertVal').value) || 0;
    }
```

In the wiring block guarded by `if (rpSchedule) {`, after the verified line

```js
    document.getElementById('rpSchedFreq').addEventListener('change', schedFreqChanged);
```

add:

```js
    document.getElementById('rpSchedAlertOp').addEventListener('change', schedAlertChanged);
```

- [ ] **Step 5: CSS.** Append to `static/css/reporting.css`:

```css
.reporting-sched-alert-hint { margin: 4px 0 8px; font-size: 12px; color: #6b7280; }
```

- [ ] **Step 6: Run green**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_schedule.py -v
```
Expected: both schedule e2e tests PASS (new + pre-existing).

- [ ] **Step 7: Commit**

```powershell
git add templates/reporting.html templates/js/_reporting_js.html static/css/reporting.css tests/e2e/test_reporting_schedule.py
$env:SQL_SYNC_SKIP = "1"; git commit -m "feat(reporting): schedule modal alert condition and enable toggle"; Remove-Item Env:SQL_SYNC_SKIP
```

---

# PHASE 3 — Result-view & wizard quick wins (shares files, not functions, with in-flight work — see Context)

### Task 6: Surface the row-limit truncation flag in both result views

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (I18N + `runCurrent`)
- Modify: `templates/js/_reporting_js.html` (`renderResults`)
- Modify: `static/css/reporting.css` (append)
- Test: `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Write the failing e2e tests.** Append to `tests/e2e/test_reporting_simple.py` (the file already imports `json` and `expect`). The Simple test uses a real seeded report with `rowLimit: 1` over `dbo.Users` (server returns `truncated: true`, `rowCount: 1`); the Advanced test stubs `/api/reporting/run` (Advanced `run()` POSTs unconditionally, and the stub's column shape `{"field", "header"}` matches the real `api_run` payload):

```python
def test_simple_truncation_note(nexora_server, page):
    """A rowLimit-capped result must say so in the Simple message line."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'trunc_users', kind: 'curated', label: 'Trunc Users',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 30});
          const rep = await post('/api/reporting/reports', {
            name: 'Trunc e2e',
            definition: {schemaVersion: 1, source: 'trunc_users',
              visualization: 'table', title: 'Trunc e2e',
              columns: [{field: 'username'}], filters: [], sort: [],
              scope: {}, rowLimit: 1}});
          return {src: src.id, rep: rep.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-group-mine").get_by_text("Trunc e2e").click()
        msg = page.get_by_test_id("rs-msg")
        expect(msg).to_be_visible()
        expect(msg).to_contain_text("first 1")
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/reports/' + ids.rep);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""", ids)


def test_advanced_truncation_note_renders(nexora_server, page):
    """renderResults shows the note whenever the response carries truncated=true."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    page.route("**/api/reporting/run", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"columns": [{"field": "x", "header": "X"}], "rows": [[1]],
                         "rowCount": 5000, "truncated": True, "sql": None, "params": []})))
    page.get_by_test_id("reporting-run").click()
    note = page.locator(".reporting-truncated-note")
    expect(note).to_be_visible()
    expect(note).to_contain_text("5000")
```

- [ ] **Step 2: Run them, watch them fail**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_simple.py -v -k "truncation"
```
Expected: both FAIL (`rs-msg` stays hidden; `.reporting-truncated-note` count 0).

- [ ] **Step 3: Simple pane.** In `templates/js/_reporting_simple_js.html`, add one I18N key directly after the verified line `showQuery: {{ _("Show query")|tojson }},`:

```js
    truncatedNote: {{ _("Showing the first {n} rows — narrow the filters or time range to see the rest.")|tojson }},
```

  In `runCurrent`, directly after the verified resolved-dates block

```js
    if (rdates.length) {
      var resolvedTxt = rdates.map(function (d) {
        return tokenLabel(d) + ' (' + d.start + ' → ' + d.end + ')';
      }).join(' · ');
      var msg = el('rsMsg');
      msg.textContent = msg.hidden || !msg.textContent
        ? resolvedTxt : msg.textContent + ' — ' + resolvedTxt;
      msg.hidden = false;
    }
```

  add:

```js
    if (res.data.truncated) {
      var tMsg = el('rsMsg');
      var tTxt = I18N.truncatedNote.replace('{n}', String(res.data.rowCount || rows.length));
      tMsg.textContent = (!tMsg.hidden && tMsg.textContent)
        ? tMsg.textContent + ' — ' + tTxt : tTxt;
      tMsg.hidden = false;
    }
```

- [ ] **Step 4: Advanced pane.** In `templates/js/_reporting_js.html`, after the verified line `var I18N_COPIED = {{ _("Copied")|tojson }};` add:

```js
  var I18N_TRUNCATED = {{ _("Showing the first {n} rows — narrow the filters or time range to see the rest.")|tojson }};
```

  In `renderResults`, replace the verified tail

```js
    table.appendChild(tbody);

    wrap.appendChild(table);
  }
```

  with

```js
    table.appendChild(tbody);

    if (data.truncated) {
      var note = document.createElement('p');
      note.className = 'reporting-truncated-note';
      note.textContent = I18N_TRUNCATED.replace('{n}', String(data.rowCount || data.rows.length));
      wrap.appendChild(note);
    }
    wrap.appendChild(table);
  }
```

  (This is the function drill-through Task 5 later wires row clicks into — the note sits outside its tbody loop and merges cleanly either way. The SQL-sandbox response also carries `truncated` at the 50000-row cap, so SQL results get the note for free.)

- [ ] **Step 5: CSS.** Append to `static/css/reporting.css`:

```css
.reporting-truncated-note { margin: 0 0 8px; font-size: 12px; color: #b45309; }
```

- [ ] **Step 6: Run green**

```powershell
python -m pytest tests/e2e/test_reporting_simple.py -v -k "truncation"
```
Expected: both PASS.

- [ ] **Step 7: Commit**

```powershell
git add templates/js/_reporting_simple_js.html templates/js/_reporting_js.html static/css/reporting.css tests/e2e/test_reporting_simple.py
$env:SQL_SYNC_SKIP = "1"; git commit -m "feat(reporting): surface row-limit truncation in both result views"; Remove-Item Env:SQL_SYNC_SKIP
```

---

### Task 7: "This week" and "This quarter" wizard time presets + `WIZ_TOKENS` round-trip

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (`renderTimeStep` preset array, `WIZ_TOKENS`)
- Test: `tests/e2e/test_reporting_simple.py`

TEST table sources have no `grainable` fields (see Context), so these tests stub the catalogs via `page.route` — **registered BEFORE `page.goto`**, because the Simple pane fetches `/api/reporting/metrics` in `initOnce()` at the `rp:tabshown` event (page load) and caches it; a route registered after `goto` never fires and the stub source never appears. The stub shapes match what the pane reads: `renderMeasureStep` matches metrics-map keys against `state.sources` by `s.id` and reads `m.code`/`m.label`; `renderTimeStep` reads `state.wiz.source.fields` and filters on `f.grainable`.

- [ ] **Step 1: Write the failing e2e tests.** Append to `tests/e2e/test_reporting_simple.py`:

```python
WIZ_STUB_SOURCES = [{
    "id": "stub_src", "label": "Stub source", "kind": "curated", "processes": [],
    "fields": [
        {"field": "import_date", "label": "Import date", "type": "date",
         "grainable": True, "filterable": True},
        {"field": "doctype", "label": "Doc type", "type": "string",
         "grainable": False, "filterable": True},
    ],
}]
WIZ_STUB_METRICS = {"stub_src": [
    {"code": "stub_count", "label": "Stub count", "aggregation": "count"},
]}


def _stub_catalogs(page):
    # MUST be registered before page.goto: the Simple pane fetches the metrics
    # catalog in initOnce() at rp:tabshown (page load), not at first wizard open.
    page.route("**/api/reporting/sources", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(WIZ_STUB_SOURCES)))
    page.route("**/api/reporting/metrics", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(WIZ_STUB_METRICS)))


def test_wizard_time_step_offers_week_and_quarter(nexora_server, page):
    _login(page, nexora_server)
    _stub_catalogs(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-measure-list").get_by_text("Stub count").click()
    page.get_by_test_id("rs-breakdown-next").click()
    tl = page.get_by_test_id("rs-time-list")
    expect(tl.get_by_text("This week", exact=True)).to_be_visible()
    expect(tl.get_by_text("This quarter", exact=True)).to_be_visible()


def test_adjust_in_wizard_maps_this_quarter(nexora_server, page):
    """A non-wizard def filtered on {token: this_quarter} keeps 'Adjust in wizard'."""
    _login(page, nexora_server)
    _stub_catalogs(page)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    # Warm the sources cache (fetched lazily at first wizard open; the adjust
    # check reads state.sources/state.metricsBySource).
    page.get_by_test_id("rs-new-report").click()
    page.get_by_test_id("rs-wizard-close").click()
    page.route("**/api/reporting/run", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"columns": [{"field": "stub_count", "header": "Stub count"}],
                         "rows": [[7]], "rowCount": 1, "truncated": False,
                         "sql": "SELECT 7", "params": []})))
    _stub_ai_build(page, definition={
        "schemaVersion": 1, "source": "stub_src", "visualization": "table",
        "title": "quarter stub", "subtitle": None,
        "columns": [], "metrics": [{"metric": "stub_count"}],
        "filters": [{"field": "import_date", "op": "between",
                     "value": {"token": "this_quarter"}}],
        "sort": [], "scope": {"clients": [], "processes": []}, "rowLimit": 5000})
    page.get_by_test_id("rs-ai-prompt").fill("total this quarter")
    page.get_by_test_id("rs-ai-ask").click()
    expect(page.get_by_test_id("rs-result")).to_be_visible()
    expect(page.get_by_test_id("rs-adjust-wizard")).to_be_visible()
```

- [ ] **Step 2: Run them, watch them fail**

```powershell
python -m pytest tests/e2e/test_reporting_simple.py -v -k "week_and_quarter or maps_this_quarter"
```
Expected: both FAIL ("This week"/"This quarter" buttons absent; `rs-adjust-wizard` hidden because `this_quarter` is not in `WIZ_TOKENS`).

- [ ] **Step 3: Implement.** In `templates/js/_reporting_simple_js.html`, in `renderTimeStep`, replace the verified block

```js
    [['this_month', I18N.thisMonth], ['last_month', I18N.lastMonth],
     ['last_quarter', I18N.lastQuarter], ['last_3_months', I18N.last3Months],
     ['this_year', I18N.thisYear], ['last_year', I18N.lastYear],
     ['all_time', I18N.allTime], ['custom', I18N.custom]].forEach(function (p) {
```

with

```js
    [['this_week', I18N.thisWeek], ['this_month', I18N.thisMonth],
     ['last_month', I18N.lastMonth], ['this_quarter', I18N.thisQuarter],
     ['last_quarter', I18N.lastQuarter], ['last_3_months', I18N.last3Months],
     ['this_year', I18N.thisYear], ['last_year', I18N.lastYear],
     ['all_time', I18N.allTime], ['custom', I18N.custom]].forEach(function (p) {
```

Then replace the verified block

```js
  // Wizard presets that renderTimeStep offers; other tokens (e.g. last_n_days,
  // this_week) can't be represented in the wizard UI, so such defs don't map.
  var WIZ_TOKENS = ['this_month', 'last_month', 'last_quarter',
                    'last_3_months', 'this_year', 'last_year'];
```

with

```js
  // Wizard presets that renderTimeStep offers; other tokens (e.g. last_n_days,
  // last_week) can't be represented in the wizard UI, so such defs don't map.
  var WIZ_TOKENS = ['this_week', 'this_month', 'last_month', 'this_quarter',
                    'last_quarter', 'last_3_months', 'this_year', 'last_year'];
```

(`tokens.py` already resolves both server-side — `"this_week": _week_of` and the `"this_quarter"` lambda are verified; `I18N.thisWeek`/`I18N.thisQuarter` already exist and are translated. Zero new msgids.)

- [ ] **Step 4: Run green** (the new tests plus the pre-existing wizard suite must stay green):

```powershell
python -m pytest tests/e2e/test_reporting_simple.py -v -k "week_and_quarter or maps_this_quarter or wizard"
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
$env:SQL_SYNC_SKIP = "1"; git commit -m "feat(reporting): add This week and This quarter wizard presets"; Remove-Item Env:SQL_SYNC_SKIP
```

---

### Task 8: Wizard Back steps back instead of exiting to the library

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (`rsWizardBack` handler)
- Test: `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Write the failing e2e test.** Append to `tests/e2e/test_reporting_simple.py` (real seeded source — no stubs needed; the wizard's steps are progressive-disclosure: `startWizard` hides steps 2+3, `renderBreakdownStep` shows `#rsStepBreakdown`, `renderTimeStep` shows `#rsStepTime` + the Run button, all verified; with a table source the time step renders its "no date field" notice but is still visible):

```python
def test_wizard_back_steps_back_not_exit(nexora_server, page):
    """Back walks time -> breakdown -> measure -> library, preserving picks."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'back_users', kind: 'curated', label: 'Back Users',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 31});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'back_user_count', sourceId: 'back_users', label: 'Back user count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("Back user count").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        expect(page.get_by_test_id("rs-wizard-run")).to_be_visible()

        back = page.get_by_test_id("rs-wizard-back")
        back.click()  # time step -> breakdown step
        expect(page.get_by_test_id("rs-wizard")).to_be_visible()
        expect(page.get_by_test_id("rs-wizard-run")).to_be_hidden()
        expect(page.locator("#rsStepBreakdown")).to_be_visible()

        back.click()  # breakdown step -> measure step
        expect(page.get_by_test_id("rs-wizard")).to_be_visible()
        expect(page.locator("#rsStepBreakdown")).to_be_hidden()

        back.click()  # measure step -> library
        expect(page.get_by_test_id("rs-wizard")).to_be_hidden()
        expect(page.get_by_test_id("rs-new-report")).to_be_visible()
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )
```

- [ ] **Step 2: Run it, watch it fail**

```powershell
python -m pytest tests/e2e/test_reporting_simple.py -v -k "back_steps_back"
```
Expected: FAIL on the first post-click assertion — `rs-wizard` is hidden (Back exited straight to the library).

- [ ] **Step 3: Implement.** Replace the verified one-liner

```js
  el('rsWizardBack').addEventListener('click', function () { setView('library'); });
```

with

```js
  // Back steps one wizard step backwards (picks are preserved in state.wiz);
  // only from step 1 does it exit. The ✕ stays the explicit exit at any point.
  el('rsWizardBack').addEventListener('click', function () {
    if (!el('rsStepTime').hidden) {           // time -> breakdown
      el('rsStepTime').hidden = true;
      el('rsWizardRun').hidden = true;
      return;
    }
    if (!el('rsStepBreakdown').hidden) {      // breakdown -> measure
      el('rsStepBreakdown').hidden = true;
      return;
    }
    setView('library');                       // measure -> out
  });
```

(`state.wiz` is untouched, so re-advancing restores every selection; `reopenWizard` renders all three steps, so Back from a reopened wizard collapses the time step first — correct.)

- [ ] **Step 4: Run green** (full Simple file — `reopenWizard`/adjust flows must not regress):

```powershell
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_simple.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
$env:SQL_SYNC_SKIP = "1"; git commit -m "fix(reporting): wizard Back steps back instead of exiting to library"; Remove-Item Env:SQL_SYNC_SKIP
```

---

### Task 9: CSV export option on the Simple result bar

**Files:**
- Modify: `templates/_reporting_simple.html` (export control)
- Modify: `templates/js/_reporting_simple_js.html` (`rsExport` listener)
- Test: `tests/e2e/test_reporting_simple.py`

- [ ] **Step 1: Write the failing e2e test.** Append to `tests/e2e/test_reporting_simple.py`:

```python
def test_simple_export_csv(nexora_server, page):
    """The Simple export control downloads CSV when the format select says so."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=advanced")
    ids = page.evaluate(
        """async () => {
          const csrf = document.querySelector('meta[name="csrf-token"]').content;
          const post = (url, body) => fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
          }).then(r => r.json());
          const src = await post('/api/reporting/admin/sources', {
            code: 'csv_dl_users', kind: 'curated', label: 'CSV dl Users',
            permission: 'reporting.source.docprocessing', provider: 'table',
            engine: 'nexora', baseObject: 'dbo.Users',
            columns: [{field: 'username', label: 'Username', type: 'string',
                       filterable: true, sortable: true}],
            enabled: true, sortOrder: 32});
          const met = await post('/api/reporting/admin/metrics', {
            code: 'csv_dl_count', sourceId: 'csv_dl_users', label: 'CSV dl count',
            aggregation: 'count', format: 'int'});
          return {src: src.id, met: met.id};
        }"""
    )
    try:
        page.goto(f"{nexora_server}/reporting?tab=simple")
        page.get_by_test_id("rs-new-report").click()
        page.get_by_test_id("rs-measure-list").get_by_text("CSV dl count").click()
        page.get_by_test_id("rs-breakdown-list").get_by_text("Username", exact=True).click()
        page.get_by_test_id("rs-breakdown-next").click()
        page.get_by_test_id("rs-wizard-run").click()
        expect(page.get_by_test_id("rs-result")).to_be_visible()
        page.get_by_test_id("rs-export-format").select_option("csv")
        with page.expect_download() as dl:
            page.get_by_test_id("rs-export").click()
        assert dl.value.suggested_filename.endswith(".csv")
    finally:
        page.evaluate(
            """async (ids) => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const del = url => fetch(url, {method: 'DELETE', headers: {'X-CSRFToken': csrf}});
              await del('/api/reporting/admin/metrics/' + ids.met);
              await del('/api/reporting/admin/sources/' + ids.src);
            }""",
            ids,
        )
```

- [ ] **Step 2: Run it, watch it fail**

```powershell
python -m pytest tests/e2e/test_reporting_simple.py -v -k "export_csv"
```
Expected: FAIL — timeout selecting `rs-export-format` (it does not exist).

- [ ] **Step 3: Markup.** In `templates/_reporting_simple.html`, replace the verified export block

```html
        {% if has_permission('reporting.export') %}
        <button id="rsExport" class="reporting-btn" data-testid="rs-export">{{ _("Export") }}</button>
        {% endif %}
```

with

```html
        {% if has_permission('reporting.export') %}
        <select id="rsExportFormat" class="reporting-export-format" data-testid="rs-export-format" title="{{ _('Export format') }}">
          <option value="xlsx">{{ _("Excel") }}</option>
          <option value="csv">CSV</option>
        </select>
        <button id="rsExport" class="reporting-btn" data-testid="rs-export">{{ _("Export") }}</button>
        {% endif %}
```

("Excel" and "Export format" are existing msgids from the Advanced toolbar — `templates/reporting.html` already uses `title="{{ _('Export format') }}"` on `rpExportFormat`; `.reporting-export-format` is an existing styled class in `reporting.css`. **Zero new strings, zero new CSS.**)

- [ ] **Step 4: JS.** In the `rsExport` click listener in `templates/js/_reporting_simple_js.html`, replace the verified head

```js
      if (!state.current) return;  // error view without a loaded report
      var body = Object.assign({}, state.current.def, { format: 'xlsx' });
      var png = chartPngDataUrl();
      if (png) body.chartImage = png;
```

with

```js
      if (!state.current) return;  // error view without a loaded report
      var fmtSel = el('rsExportFormat');
      var fmt = (fmtSel && fmtSel.value === 'csv') ? 'csv' : 'xlsx';
      var body = Object.assign({}, state.current.def, { format: fmt });
      var png = fmt === 'xlsx' ? chartPngDataUrl() : null;
      if (png) body.chartImage = png;
```

and the verified download line

```js
      a.download = (state.current.name || 'report') + '.xlsx';
```

with

```js
      a.download = (state.current.name || 'report') + '.' + fmt;
```

(Drill-through Task 3 Step 2 copies this body into its `exportDrill` — the copy instruction remains valid; it simply inherits the format variable.)

- [ ] **Step 5: Run green** (the existing xlsx-default export behavior must not regress):

```powershell
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_simple.py -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```powershell
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html tests/e2e/test_reporting_simple.py
$env:SQL_SYNC_SKIP = "1"; git commit -m "feat(reporting): CSV export option on the Simple result bar"; Remove-Item Env:SQL_SYNC_SKIP
```

---

# PHASE 4 — Chores

### Task 10: i18n cycle (de/fr/it)

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`)

- [ ] **Step 1: Extract + update**

```powershell
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
```

- [ ] **Step 2: Translate every new msgid the pybabel diff shows** in de/fr/it, no fuzzy entries. Expected candidates from this plan (trust the diff, not this list — some may already exist elsewhere in the catalog, e.g. `"Send"`, `"Enable"`, `"Disable"`): `"Always"`, `"Only when the total is above…"`, `"Only when the total is at least…"`, `"Only when the total is below…"`, `"Only when the total is at most…"`, `"Threshold"`, `"only when total"`, `"The threshold is checked against the report's grand total (or its row count when the report has no measure)."`, `"Showing the first {n} rows — narrow the filters or time range to see the rest."`. Tasks 7–9 introduce **zero** new msgids (they reuse the already-translated token labels and the existing `"Excel"`/`"Export format"` strings). Alternatively run the `/nx-i18n` skill.

- [ ] **Step 3: Compile + verify**

```powershell
pybabel compile -d translations
python -m pytest tests/unit/test_translations.py -v
```
Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add messages.pot translations
$env:SQL_SYNC_SKIP = "1"; git commit -m "chore(i18n): translate reporting improvement strings (de/fr/it)"; Remove-Item Env:SQL_SYNC_SKIP
```

---

### Task 11: Docs, changelog, full verification

**Files:**
- Modify: `docs/howto/reporting.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update `docs/howto/reporting.md`** (verified heading map):
  - Under `## Scheduled & emailed reports`: add an "Alert-only schedules" paragraph — the Send select (`Always` vs the four "Only when the total is…" conditions), what the threshold compares against (grand total of the first metric via a zero-column re-run; row count for plain-table and SQL reports), that a non-tripped run sends nothing but still advances `LastRunAt`/`NextRunAt`, the new enable/disable toggle, and the caveat that toggling (any PUT) recomputes `NextRunAt`. Mention the `AlertOp`/`AlertThreshold` columns and migration `0022`.
  - Under `### Export (Excel / CSV, and what you see)`: note the Simple result bar now has the same xlsx/csv format select as Advanced, and that the chart is embedded only in Excel exports.
  - Under `## Simple and Advanced tabs` (wizard description): add "This week"/"This quarter" to the time presets (such definitions now keep "Adjust in wizard") and document the Back button's step-back behavior (✕ exits).
  - Where the result views are described (`## What the page does`): one sentence on the truncation note ("Showing the first N rows…") appearing on both tabs whenever the server row limit was hit.

- [ ] **Step 2: Changelog.** Under `## [Unreleased]` → `### Added` in `CHANGELOG.md`:

```markdown
- Reporting: alert-only schedules — a schedule can carry a threshold condition
  (total >, ≥, <, ≤) and only mails when it trips; schedules can now be
  enabled/disabled from the modal (migration 0022).
- Reporting: truncated results now say so — both tabs show "Showing the first
  N rows" whenever the server row limit was hit.
- Reporting Simple: CSV export option beside Export (chart embedding stays
  Excel-only).
- Reporting Simple wizard: "This week" and "This quarter" time presets; the
  Back button steps back through the wizard instead of exiting and discarding
  picks.
```

- [ ] **Step 3: Full suite + INT walkthrough**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/unit tests/integration -v
python -m pytest tests/e2e -v
```
Expected: all PASS. Then on INT (`nx -u -b --loginas:<admin user>`), as confirmation (the automated suites are the verification): (1) wizard → docprocessing measure → time step shows "This week"/"This quarter"; pick "This quarter", run — the message line shows the resolved range and "Adjust in wizard" stays enabled; (2) a >5000-row Advanced run shows the amber note above the grid; (3) Simple Export with CSV selected downloads a `.csv`; (4) schedule modal: create an alert schedule (`above… 999999999`) on a small report, then `python ops/run_scheduled_reports.py --dry-run` prints "alert … not tripped … no mail"; recreate with `above… 0` and the dry-run prints the would-send line; (5) toggle a schedule Disable/Enable. Screenshots to `var/screenshots/`.

- [ ] **Step 4: Commit**

```powershell
git add docs/howto/reporting.md CHANGELOG.md
$env:SQL_SYNC_SKIP = "1"; git commit -m "docs(reporting): alert schedules, CSV export, truncation note"; Remove-Item Env:SQL_SYNC_SKIP
```

---

## Gotchas & notes

- **Commit hygiene:** every commit needs the `SQL_SYNC_SKIP=1` prefix (INT CRLF drift) — always restore the env var afterwards, never `--no-verify`. `.gitlint` rejects titles over 72 chars (all titles above are measured to fit — keep any rewording within the limit). The ruff-format hook may rewrite Python on the first attempt: `git add -u` and commit again.
- **Deploy ordering for 0022 (critical):** after Task 4, `_due_schedules` SELECTs `s.AlertOp, s.AlertThreshold` — the runner **crashes for ALL schedules** against a DB without the migration, not just alert ones. INT: apply manually after Task 1 (`SQL_SYNC_SKIP` suspends the auto-apply). TEST: the `schema.sql` mirror + `test_db_reset.py`. PROD: migration and `ops/` code ship in the same deploy, so order is automatic — never cherry-pick the ops change alone.
- **E2E:** run `python scripts/test_db_reset.py` first (stale `ReportingSqlAck` state breaks order-dependent tests); kill stale port-8765 servers (`Get-NetTCPConnection -LocalPort 8765 | % { Stop-Process -Id $_.OwningProcess -Force }`). E2E text assertions are English — TEST users default to `en`. `tests/unit/test_translations.py` is red from the first new msgid until Task 10 — fine per-task (it gates pre-push, not pre-commit).
- **Stubbed-catalog e2e (Task 7):** register `page.route` for `/api/reporting/sources` + `/api/reporting/metrics` **before `page.goto`** — the metrics catalog is fetched at `rp:tabshown` (page load) and cached in `state.metricsBySource`; `startWizard` only refetches when that cache is empty. A route registered after `goto` never fires for it.
- **Template cache:** restart `nx -u` after every template edit before any manual browser check (e2e is immune — fresh server per fixture).
- **`_schedule_fields` arity change (Task 3)** touches BOTH the create and update endpoints — miss one and you get a `ValueError: not enough values to unpack` at runtime, not at import.
- **Runner fragility:** `runner.py` imports `rv._private` view helpers — do not rename anything in `views/reporting.py` while in there. The alert gate sits before the chart render, so a skipped mail also skips matplotlib.
- **Alert cost note:** a metric-report alert costs one extra query per due schedule run (the zero-column clone) — only for schedules that set a condition; plain schedules are unchanged. `alert_trips` never trips on `None`/non-numeric values or unknown ops, so a malformed result skips the mail rather than spamming.
- **PUT is full-replace and recomputes `NextRunAt`:** a body without alert fields clears them, and the enable/disable toggle re-anchors the next run time. Both documented in Task 11; preserve-NextRunAt semantics would be a backend tweak to `api_reports_schedules_update` later, not a UI change.
- **Drill-through / sibling-plan coexistence:** all frontend edits here are additive and anchored on symbols. If drill-through Tasks 2–8 or the loading-states plan execute first, re-verify each quoted anchor before editing (the snippets, not the line positions, are the contract). Whichever plan lands second rebases and re-anchors. Task 6's `rsMsg` append and `renderResults` note are the two message areas to flag to the sibling session.
- **No deploy-exclude changes, no new permissions, no new dependencies;** `sql/test/seed.sql` untouched (no new permission codes). `env/CONFLUENCE.env.example` shows as deleted in this worktree's git status — leave it alone (owned by `feat/confluence-docs-sync`); never `git add -A`.
