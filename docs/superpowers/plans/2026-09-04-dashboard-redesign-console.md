# Dashboard redesign — console layout (option 1a) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Anchor on **function names and quoted snippets**, never line numbers — re-Grep before every edit.

**Goal:** Rebuild `/dashboard` as a borderless operations console — page head with live indicator, filter row with a 14/30/90-day range control, a four-KPI hairline strip with day-over-day deltas and sparklines, one full-width tabbed chart (Over time / Today by hour), and a 14-day per-process backlog trend fed from `dbo.BacklogHistory` — dropping every `nx-card` frame, the Recent Validations feed and the standalone hourly card.

**Architecture:** Four new/changed JSON endpoints on the existing `nx_lib/views/dashboard.py` blueprint supply deltas, 7-point sparkline series, a `range` window and the backlog trend; two new per-day aggregation helpers (`_kpi_daily_counts`, `_avg_processing_by_day`) and one `dbo.BacklogHistory` reader (`_backlog_history`) sit beside the existing `compute_*` functions. The page follows the **reporting-console precedent**: reusable console component classes go into `static/css/nexora-ui.css`, page-specific styling into a rewritten `static/css/dashboard.css`, and every colour rides the `--nx-*` tokens so the user's accent pick, dark mode and tenant branding keep working. Behaviour moves out of the Jinja partial into `static/js/dashboard.js` per the #191 shim pattern.

**Tech Stack:** Flask + Jinja2, pyodbc raw cursors through `engine_statistics_db` / `engine_ms02_stats_pg`, Chart.js 4.5.1 (already bundled), hand-rolled inline SVG for the sparklines (no extra library), vanilla JS on `window.NX`, pytest (unit + integration against `NEXORA_TEST`), Playwright e2e (CI-only).

**Spec:** `docs/design/Dashboard_redesign/design_handoff_dashboard_console/README.md` (full measurements) and `ISSUE.md` (scope). The prototype `Dashboard Redesign.dc.html` **option 1a** is the approved layout; 1b/1c are context only. No `docs/superpowers/specs/` entry exists — the handoff README *is* the spec.

## Global Constraints

- **The prototype's amber is `var(--nx-accent)`, not a hardcoded hue.** `nexora-ui.css` ships indigo (`#4f46e5`) as the default accent and amber is one of seven user-selectable accents (`html[data-accent="amber"]`). The designer's demo simply had amber selected. Every prototype `#d97706` / `#ea580c` / `#b45309` / `#fef3e2` / `#fef7ed` maps to `--nx-accent` / `--nx-violet` / `--nx-accent-hover` / `--nx-accent-tint` / `--nx-accent-soft`. Never write those hexes into `dashboard.css`.
- **Chart series colours are the exception** — a categorical palette must stay distinguishable regardless of the accent, so `#d97706 #7c3aed #0891b2 #db2777 #059669` become new `--nx-series-1..5` tokens with dark-mode twins (values lifted from the kit's `tokens/colors.css` and `tokens/themes.css`).
- **English is the source locale.** The handoff is written in German because the demo ran in German. Every string enters the code as English (`_("Refresh")`, `_("Over time")`, `_("Backlog")`, `_("vs. yesterday")`, …) and the German text from the README goes into `translations/de/LC_MESSAGES/messages.po`.
- Hand-built URLs in JS go through `window.API_PREFIX`; use `window.NX.esc` / `NX.api` / `NX.formatDate` rather than reimplementing them. No inline `onclick=` — `tests/unit/test_no_inline_event_handlers.py` fails the build (CSP is PROD-only, so an inline handler works fine on INT and dies silently on PROD).
- Every new `static/` asset is referenced through `static_v('…')` — `tests/unit/test_static_v_lint.py` enforces it.
- Never un-hide an element that carries `[display:none]!` by setting `style.display` — `tests/unit/test_display_none_important.py` enforces `classList.add/remove('[display:none]!')`.
- Templates are cached for the process lifetime: `bin/nx.ps1 -r` after every template edit before any browser check.
- **No migrations.** `dbo.BacklogHistory` lives on the Statistics DB, which nexora does not track under `sql/` (vendor/runtime surface) and which the standalone collector creates itself. Nothing in `sql/_migrations/` changes.
- Never `--no-verify`. If the SQL pre-commit hooks block on unrelated INT drift, use `SQL_SYNC_SKIP=1 git commit …`. **Expect this on every commit in this plan** — INT currently carries drift from a peer worktree (`sql/NexoraDB/Views/dbo.vEmFieldExtractionQuality.sql` untracked on INT, plus regenerated `sql/GeneraliDB/**` files). Those regenerated files are left unstaged in the working tree: they are not yours, never stage them, and never `git add -u`.
- **Every commit needs a body — gitlint rejects a bare `-m` one-liner with `B6 Body message is missing`.** The per-task commit blocks below show only the subject line for brevity. Keep that subject verbatim, then add a blank line and two to four wrapped lines (≤100 chars) saying *why*. Use `git commit -F -` with a here-doc. Measured on Task 1, 2026-09-04.
- **The test snippets below re-import for readability; the real files already import what they need.** `tests/unit/test_dashboard_stats.py` already has `date`, `timedelta` and `import nx_lib.views.dashboard as dv` at module level. Drop the per-test `from datetime import …` / `from nx_lib.views import dashboard as dv` lines when pasting — ruff flags the shadowing re-imports.
- **`_row()` in `tests/unit/test_dashboard_stats.py` is `_row(client_code, name="p", table=None, exp=None, imp=None)`.** Pass the table in the *third* slot, not the second: `_row("default", "t1", "dbo.t1", "ExportDate", "ImportDate")`. Getting this wrong leaves `table=None` and `_ms02_source()` silently builds `(None, '"None"', '"None"')` — invisible while the row readers are monkeypatched, wrong the moment they are not.
- Remote-session policy: commit, never push, never open a PR.

---

## Context an engineer needs (read first)

- **Branch / worktree:** planned in worktree `.claude/worktrees/plan-dashboard-redesign-console` on branch `plan/dashboard-redesign-console`, cut from `refactor/255-admin-nav-tenancy-labels` @ `ebbcdf07`. Execute there. The main checkout has uncommitted work in `nx_lib/tenant/registry.py` and `nx_lib/views/tenant.py` — never stage those.
- **Worktree has no secrets or venv.** `env/*.env` are gitignored, so a fresh worktree only carries the `.example` files and every DB call dies inside `URLSafeTimedSerializer` with `TypeError: 'NoneType' object is not iterable`. Before Task 1: `cp ../../../env/INT.env ../../../env/TEST.env env/` (never commit them). The venv lives in the main checkout — prepend `C:\dev\nexora\.venv\Scripts` to `PATH` for `pytest` / `python`.
- **In-flight work that touches the same lines:**
  - `docs/superpowers/plans/2026-09-01-permission-structure-rename-grid.md` renames `dashboard.filter.process.*` → `process.<client>.<name>.view` and replaces `_allowed_processes()`'s parser with a shared `granted_processes(perms)`. **This plan does not touch `_allowed_processes()` or `_PROCESS_PERM_PREFIX`** — every task reads the allow-list through the existing `_allowed_processes()` call, so whichever plan lands second only has to re-run its own tests.
  - The tenancy work on the current branch (#255, migration `0097`) owns the two-title `dashboard_tenant` block in `templates/dashboard.html` and `session['dashboard_tenant']`. **Keep both.** The redesign drops the *marketing subtitle*, not the tenant-aware title.
- **`test_dashboard_signin_escape.py::test_dashboard_template_uses_escaped_name` reads `templates/dashboard.html` as text** and asserts `"fullname|e" in src` (security audit #193, finding 9). The sign-in note moves into the new muted head line but **must keep the exact expression** `name="<strong>"|safe ~ fullname|e ~ "</strong>"|safe`.
- **How the dashboard's data flows today:** `dashboard()` resolves the tenant scope, calls `_allowed_processes()`, normalizes `?prcfD=` into `session['process_name_dashboard']`, and renders. Every JSON endpoint re-reads that session key, runs it through `normalize_process_selection(process_name, allowed_processes)[1]` to get `target_processes` (full `<client>.<process>` names), and resolves `dbo.ProcessSources` rows via `_statconfig_sources()` → `_split_stat_configs()` → a T-SQL leg (`_default_stat_rows`) plus an MS02 Postgres leg (`_ms02_stat_rows`). Each leg swallows its own failures so one dead source never blanks the other.
- **`dbo.BacklogHistory` (Statistics DB), created by `ops/backlog_history/backlog_history.py`:** `BacklogHistoryID`, `SnapshotAt DATETIME2(0)` (server-local), `SourceCode NVARCHAR(50)`, `ClientName NVARCHAR(255) NULL`, `ProcessName NVARCHAR(255) NULL`, `BacklogCount INT`, index on `SnapshotAt`. Written every 30 min per (source, client, process). `ClientName`/`ProcessName` come from Octo's `t_Processes.ClientName` / `.Name` — the same pair space `target_processes` splits into, so scoping is a Python set-membership test on `(ClientName, ProcessName)`, never an interpolated `IN` list.
- **TEST has no Statistics DB and no Octo tables.** Every integration test for these endpoints monkeypatches the row readers (`dv._default_stat_rows`, `dv._ms02_stat_rows`, `dv.total_backlog_count`) — see the existing `test_kpi_stats_route_still_200s_on_genuinely_quiet_day` in `tests/unit/test_dashboard_stats.py` for the shape. The e2e dashboard tests deliberately assert page chrome only.
- **Existing e2e does *not* reference `#activity-feed` or the hourly card.** `tests/e2e/test_dashboard.py` covers the title, the absence of a 500 and the scope picker. The ISSUE's "e2e tests updated for the removed feed and hourly card" is wrong — e2e work here is **additive** (new tabs + range control), not repair.
- **`views/dashboard.py` has a 25 % coverage floor** in `tests/unit/test_coverage_thresholds.py`. The new helpers arrive with unit tests, so the floor is not at risk; do not lower it.
- **`static/css/dashboard.css` is ~70 % dead code.** `.progress-step`, `.progress-icon`, `.timeline-*`, `.animate-rotate`, `.animate-pulse-icon` are referenced nowhere in `templates/` or `static/js/`. Task 8 deletes them. `.skeleton-shimmer` and the flatpickr overrides stay (the page still loads flatpickr).
- **Migrations needed: NO. i18n needed: YES (Task 12, `/nx-i18n`). Deploy excludes: none** (no new top-level paths; `static/js/dashboard.js` is inside an already-mirrored directory). **Env keys: none.**

## Decisions locked in

| # | Decision | Rationale |
|---|---|---|
| D1 | The prototype's amber is `var(--nx-accent)`. No hardcoded accent hex in `dashboard.css`. | Exactly what `static/css/reporting-console.css` already does ("All colors ride the nexora-ui.css tokens, so the user's accent pick and dark mode apply for free"). Hardcoding amber would break the seven accent themes *and* tenant branding, which the handoff explicitly says must keep working. |
| D2 | Chart series get real `--nx-series-1..5` tokens, light + dark. | A categorical palette must stay distinguishable independent of the accent. Values come from the kit's `tokens/colors.css` / `tokens/themes.css`. |
| D3 | Sparklines are hand-built inline SVG polylines, not Chart.js instances. | 4 extra Chart.js canvases per refresh for a 7-point axis-less line is pure overhead; the prototype draws them as SVG too. ~12 lines of JS. |
| D4 | `_kpi_daily_counts()` is a **new sibling** of `compute_today_stats()`, not a refactor of it. | Eight tests (`test_compute_today_stats_*`, plus the external-API suite) fake `_default_stat_rows` with bare 2-tuples and would break on a changed row shape. The new helper repeats `compute_today_stats`'s **exact predicates**, so each sparkline's last point equals that KPI's big number by construction. |
| D5 | The 14/30/90 range persists in the **session** (`session['dashboard_range']`), set through the existing `POST api/dashboard/set_filter`. | The process filter already persists exactly this way; a `ui_prefs` key would need an allowlist entry, a save path and a pre-paint read for a value that is not an appearance pref. `ponytail:` comment names `ui_prefs` as the upgrade path if users ask for cross-device stickiness. |
| D6 | `api/dashboard/recent_activity` is **deleted**, not merely unhooked — route, view, `recent_activity_rows()`, its 7 integration tests, its 2 unit tests and the `test_create_app.py` endpoint inventory entry. | Grep proves nothing else calls it (`grep -rn recent_activity nx_lib/ --include=*.py` hits only `views/dashboard.py` and `workitem_sources.py:1559`). Leaving a dead endpoint behind means keeping ~350 lines of tests for a feature no page renders. One `git revert` brings it back. |
| D7 | Avg. processing time gets a real 7-point series from one `GROUP BY` query (`_avg_processing_by_day`), rewriting `compute_avg_processing_time` as a one-line caller. | Its two tests monkeypatch `_default_stat_rows` with a callable taking `sql` only, so the row shape it returns is the *fake's* choice — safe to change, unlike D4's 2-tuple fakes. All four KPIs then carry a sparkline and the strip stays visually symmetric. |
| D8 | Backlog series comes from `dbo.BacklogHistory` (last snapshot per day), while the big "Current backlog" number stays live from `total_backlog_count()`. | Snapshots are ≤30 min stale, so the last point tracks the live number closely; querying Octo 14× for history would be far more expensive. The delta ("+48 since yesterday") = live value − yesterday's last snapshot. |
| D9 | Behaviour moves to `static/js/dashboard.js`; `templates/js/_dashboard_js.html` keeps only the Jinja-rendered data and the translated strings on `window`. | The #191 convention, and the partial would otherwise pass 600 lines. |
| D10 | Reusable console classes (`.nx-kpi-strip`, `.nx-segmented`, `.nx-chart-head`, `.nx-legend`, `.nx-section-rule`, `.nx-tabs--slim`) land in `nexora-ui.css`; only dashboard-specific rules go in `dashboard.css`. | The handoff's "How to implement against the kit" section, so the next migrated page reuses them. `.nx-tabs`/`.nx-tab` already **are** underline tabs with an accent border — Task 7 adds a slim modifier instead of a second tab component. |
| D11 | `.nx-scope` (the shared scope picker) is **not** modified. The dashboard's slim sizing is scoped as `.nx-dash-filter .nx-scope-btn`. | The component is used by workitems and reporting too; a global height change would ripple into pages this plan does not test. |
| D12 | The `dashboard_tenant` two-title block and the `?tenant=` scoping stay exactly as they are. | Landed three commits ago on this branch (#255 / migration `0097`). The redesign drops the marketing subtitle only. |

## Owner actions

- **⚠ The collector is not running on INT** (unblocked for dev, still open for real). Measured 2026-09-04: `dbo.BacklogHistory` on the INT Statistics DB held **6 rows, all from a single timestamp on 2026-08-04** — one manual smoke run, nothing since; `ops/backlog_history/backlog_history.py` was never put on INT's Task Scheduler. **Dev is now unblocked**: 14 days × 6 processes of synthetic snapshots were seeded on 2026-09-04 via `/nx-seed-intdb` (`scripts/seed-int-db.py`), random-walked backwards from the last real values, so Task 4 can be verified. Two caveats a developer will notice and must not chase as bugs:
  - The seeded magnitudes extrapolate from a **month-old** real snapshot, so they are the right shape but not today's truth.
  - Seeded totals (~1046) will not match the dashboard's live **Current backlog** KPI (58 for `ben.streich` at time of writing) — the KPI is live from Octo and scoped to the session's grants, the trend is unscoped historical snapshots. Expected, and the same divergence D8 already documents.

  Still owed: **schedule the collector on INT** (every 30 min, per the README in `ops/backlog_history/`) so this stops needing synthetic data.
- Before the PROD deploy, run the same check against PROD (`SELECT COUNT(*), MIN(SnapshotAt), MAX(SnapshotAt) FROM dbo.BacklogHistory`). If PROD's collector has also been down, the new section ships as an empty chart labelled "14-day trend" — decide whether to hold the section behind the data or ship it and let it fill in.
- **The Recent Validations panel that D6 deletes is currently the only populated panel on the page** (three live `03_Invoice_New` workitems with extracted fields, screenshot `var/screenshots/dashboard_baseline_before_redesign.png`). Its removal is a deliberate design decision, not a dead-code cleanup — confirm you still want it gone before Task 12 runs.
- `scripts/env-sync.py` as usual before deploying (no new keys expected).

---

# PHASE 1 — Backend data

### Task 1: `_kpi_daily_counts()` — 7-point imported/processed series

**Files:**
- Modify: `nx_lib/views/dashboard.py`
- Test: `tests/unit/test_dashboard_stats.py`

**Interfaces:**
- Produces: `nx_lib.views.dashboard._kpi_daily_counts(target_processes, days) -> dict[datetime.date, dict[str, int]]` — each value is `{"imported": int, "processed": int}`, zero-filled across the trailing `days` days (today last). Tasks 2 and 4 consume nothing from it; Task 5's `dashboard_kpi_stats` does.

- [ ] **Step 1: Write the failing unit test** — append to `tests/unit/test_dashboard_stats.py`:

```python
def test_kpi_daily_counts_sums_both_legs_and_zero_fills(app, monkeypatch):
    """Same predicates as compute_today_stats, one row per day. The default leg
    groups by import date (imported = every row, processed = those exported the
    same day); the MS02 leg counts each column independently."""
    from datetime import date, timedelta

    from nx_lib.views import dashboard as dv

    today = date.today()
    monkeypatch.setattr(
        dv, "_statconfig_sources", lambda tp: [_row("default", "t1"), _row("ms02", "public.\"D\"")]
    )
    monkeypatch.setattr(dv, "_default_stat_rows", lambda sql: [(today, 10, 4), (today - timedelta(days=1), 6, 6)])
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(today, 3)])

    with app.test_request_context():
        out = dv._kpi_daily_counts(["c.p"], 3)

    assert len(out) == 3                                    # zero-filled window
    assert out[today] == {"imported": 13, "processed": 7}   # 10+3 imported, 4+3 processed
    assert out[today - timedelta(days=1)] == {"imported": 6, "processed": 6}
    assert out[today - timedelta(days=2)] == {"imported": 0, "processed": 0}


def test_kpi_daily_counts_normalizes_str_typed_dates(app, monkeypatch):
    """The legacy `DRIVER={SQL Server}` pyodbc driver returns DATE columns as
    str on PROD -- same trap dashboard_processed_over_time already guards."""
    from datetime import date

    from nx_lib.views import dashboard as dv

    today = date.today()
    monkeypatch.setattr(dv, "_statconfig_sources", lambda tp: [_row("default", "t1")])
    monkeypatch.setattr(dv, "_default_stat_rows", lambda sql: [(today.isoformat(), 5, 2)])
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [])

    with app.test_request_context():
        out = dv._kpi_daily_counts(["c.p"], 2)

    assert out[today] == {"imported": 5, "processed": 2}
```

`_row(...)` is the existing local helper in this file — Grep `def _row(` and reuse it verbatim; if its signature differs, adapt these two calls to it rather than adding a second helper.

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/unit/test_dashboard_stats.py -q -k kpi_daily_counts`
Expected: FAIL — `AttributeError: module 'nx_lib.views.dashboard' has no attribute '_kpi_daily_counts'`.

- [ ] **Step 3: Implement**, directly below `compute_today_stats` in `nx_lib/views/dashboard.py`:

```python
def _kpi_daily_counts(target_processes, days):
    """{date: {"imported": n, "processed": n}} for the trailing ``days`` days,
    zero-filled so a sparse client still draws a continuous sparkline.

    Per-day generalization of compute_today_stats using its EXACT predicates:
    the default T-SQL leg groups by import date (imported = every row in scope,
    processed = the subset exported that same day), the MS02 leg counts each
    column independently. That equality is the point -- each sparkline's last
    point is then the same number as the KPI above it.

    ponytail: a sibling rather than a refactor of compute_today_stats -- eight
    tests fake _default_stat_rows with bare (imported, processed) 2-tuples and
    would break on a changed row shape. Upgrade path: fold the two together
    when those fakes are rewritten to yield dated rows.
    """
    days = max(1, int(days))
    out = {}

    configs = _statconfig_sources(target_processes)
    default_configs, ms02_rows = _split_stat_configs(configs)

    sub_queries = []
    for row in default_configs:
        condition = f" {row.extra_condition}" if row.extra_condition else ""
        sub_queries.append(f"""
            SELECT CAST({row.import_column} AS DATE) as d,
                   COUNT(*) as imported,
                   SUM(CASE WHEN CAST({row.export_column} AS DATE) = CAST({row.import_column} AS DATE)
                            THEN 1 ELSE 0 END) as processed
            FROM [{DB_STATISTICS}].{row.table}
            WHERE CAST({row.import_column} AS DATE) >= CAST(DATEADD(day, -{days - 1}, GETDATE()) AS DATE)
            {condition}
            GROUP BY CAST({row.import_column} AS DATE)
        """)

    if sub_queries:
        full_query = f"""
            SELECT d, SUM(imported), SUM(processed)
            FROM ({' UNION ALL '.join(sub_queries)}) as combined
            GROUP BY d
        """
        for row in _default_stat_rows(full_query):
            d = row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0])[:10])
            cell = out.setdefault(d, {"imported": 0, "processed": 0})
            cell["imported"] += row[1] or 0
            cell["processed"] += row[2] or 0

    ms02_src = _ms02_source(ms02_rows)
    if ms02_src:
        tbl, exp, imp = ms02_src
        for col, key in ((imp, "imported"), (exp, "processed")):
            for d, c in _ms02_stat_rows(
                f"SELECT {col}::date AS d, COUNT(*) AS c "
                f"FROM {tbl} "
                f"WHERE {col} >= CURRENT_DATE - {days - 1} "
                f"GROUP BY {col}::date"
            ):
                out.setdefault(d, {"imported": 0, "processed": 0})[key] += c or 0

    today = datetime.now().date()
    for i in range(days):
        out.setdefault(today - timedelta(days=i), {"imported": 0, "processed": 0})
    return {d: out[d] for d in sorted(out) if d >= today - timedelta(days=days - 1)}
```

`days` is interpolated, never parameterized — it is an `int()`-coerced server-side constant (7 here, or a value from Task 3's allowlist), so no injection surface. `date`, `datetime` and `timedelta` are already imported at the top of the module.

- [ ] **Step 4: Run it to verify it passes**

Run: `pytest tests/unit/test_dashboard_stats.py -q -k kpi_daily_counts`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add nx_lib/views/dashboard.py tests/unit/test_dashboard_stats.py
git commit -m "feat(dashboard): per-day imported/processed counts for KPI sparklines"
```

### Task 2: `_avg_processing_by_day()` — 7-point average-time series

**Files:**
- Modify: `nx_lib/views/dashboard.py`
- Test: `tests/unit/test_dashboard_stats.py`

**Interfaces:**
- Produces: `_avg_processing_by_day(target_processes, days, *, strict=False) -> dict[date, float]` — seconds, mean-of-means per day, days with no matching rows absent (NOT zero-filled: a zero average is a lie, a missing point is a gap).
- Changes: `compute_avg_processing_time(target_processes, *, strict=False)` keeps its signature and `float | None` return, now implemented as `_avg_processing_by_day(target_processes, 1, strict=strict).get(datetime.now().date())`.

- [ ] **Step 1: Write the failing unit test** — append to `tests/unit/test_dashboard_stats.py`:

```python
def test_avg_processing_by_day_groups_and_means_the_legs(app, monkeypatch):
    from datetime import date, timedelta

    from nx_lib.views import dashboard as dv

    today = date.today()
    monkeypatch.setattr(
        dv, "_statconfig_sources", lambda tp: [_row("default", "t1"), _row("ms02", "public.\"D\"")]
    )
    monkeypatch.setattr(dv, "_default_stat_rows", lambda sql, *a, **k: [(today, 100.0), (today - timedelta(days=1), 200.0)])
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql, *a, **k: [(today, 300.0)])

    with app.test_request_context():
        out = dv._avg_processing_by_day(["c.p"], 3)

    assert out[today] == 200.0                       # mean-of-means: (100 + 300) / 2
    assert out[today - timedelta(days=1)] == 200.0   # single leg contributes alone
    assert (today - timedelta(days=2)) not in out    # gaps stay gaps, not zeros


def test_compute_avg_processing_time_still_returns_todays_scalar(app, monkeypatch):
    """The external API's contract (float seconds or None) is unchanged."""
    from datetime import date

    from nx_lib.views import dashboard as dv

    monkeypatch.setattr(dv, "_avg_processing_by_day", lambda tp, days, strict=False: {date.today(): 42.0})
    with app.test_request_context():
        assert dv.compute_avg_processing_time(["c.p"]) == 42.0

    monkeypatch.setattr(dv, "_avg_processing_by_day", lambda tp, days, strict=False: {})
    with app.test_request_context():
        assert dv.compute_avg_processing_time(["c.p"]) is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/unit/test_dashboard_stats.py -q -k "avg_processing_by_day or still_returns_todays_scalar"`
Expected: FAIL — `AttributeError: … has no attribute '_avg_processing_by_day'`.

- [ ] **Step 3: Implement** — replace the whole body of `compute_avg_processing_time` (keep its docstring, append the note below) with the two functions:

```python
def _avg_processing_by_day(target_processes, days, *, strict=False):
    """{date: avg_seconds} over the trailing ``days`` days -- per source,
    AVG(export - import) grouped by export date; the default-client and MS02
    buckets then contribute one average each per day, combined as a plain
    mean-of-means (NOT weighted by row count). Days with no matching rows are
    ABSENT rather than zero: a zero average would draw a cliff in the
    sparkline where the truth is "no documents finished that day"."""
    days = max(1, int(days))
    per_day = {}

    configs = _statconfig_sources(target_processes)
    default_configs, ms02_rows = _split_stat_configs(configs)

    sub_queries = []
    for row in default_configs:
        if not row.import_column:
            continue
        condition = f" {row.extra_condition}" if row.extra_condition else ""
        sub_queries.append(f"""
            SELECT CAST({row.export_column} AS DATE) as d,
                   AVG(CAST(DATEDIFF(second, {row.import_column}, {row.export_column}) AS FLOAT)) as avg_sec
            FROM [{DB_STATISTICS}].{row.table}
            WHERE CAST({row.export_column} AS DATE) >= CAST(DATEADD(day, -{days - 1}, GETDATE()) AS DATE)
            AND {row.import_column} IS NOT NULL
            AND {row.export_column} > {row.import_column}
            {condition}
            GROUP BY CAST({row.export_column} AS DATE)
        """)

    if sub_queries:
        full_query = f"""
            SELECT d, AVG(avg_sec) as overall_avg
            FROM ({' UNION ALL '.join(sub_queries)}) as combined
            WHERE avg_sec IS NOT NULL
            GROUP BY d
        """
        srows = (
            _default_stat_rows(full_query, strict=True) if strict else _default_stat_rows(full_query)
        )
        for row in srows:
            if row[1] is None:
                continue
            d = row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0])[:10])
            per_day.setdefault(d, []).append(float(row[1]))

    ms02_src = _ms02_source(ms02_rows)
    if ms02_src:
        tbl, exp, imp = ms02_src
        ms02_sql = (
            f"SELECT {exp}::date AS d, AVG(EXTRACT(EPOCH FROM ({exp} - {imp}))) "
            f"FROM {tbl} "
            f"WHERE {exp} >= CURRENT_DATE - {days - 1} "
            f"AND {imp} IS NOT NULL AND {exp} > {imp} "
            f"GROUP BY {exp}::date"
        )
        mrows = _ms02_stat_rows(ms02_sql, strict=True) if strict else _ms02_stat_rows(ms02_sql)
        for row in mrows:
            if row[1] is None:
                continue
            per_day.setdefault(row[0], []).append(float(row[1]))

    return {d: sum(v) / len(v) for d, v in per_day.items()}
```

and then:

```python
def compute_avg_processing_time(target_processes, *, strict=False):
    """<KEEP THE EXISTING DOCSTRING VERBATIM, then append:>

    Today's slice of _avg_processing_by_day -- one implementation, so the KPI
    number and its sparkline can never disagree."""
    return _avg_processing_by_day(target_processes, 1, strict=strict).get(datetime.now().date())
```

- [ ] **Step 4: Run the full stats suite** (the two pre-existing avg tests must still pass)

Run: `pytest tests/unit/test_dashboard_stats.py -q`
Expected: PASS. If `test_avg_processing_time_serves_ms02_when_statistics_db_dead` fails, its fake returns a bare `[(300.0,)]` — widen it to `[(date.today(), 300.0)]`; that is the intended shape change, not a regression.

- [ ] **Step 5: Run the external-API suite** — the other `compute_avg_processing_time` caller

Run: `pytest tests/unit/test_api_auth.py tests/integration -q -k "avg or api_v1"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add nx_lib/views/dashboard.py tests/unit/test_dashboard_stats.py
git commit -m "refactor(dashboard): average processing time grouped by day"
```

### Task 3: `_backlog_history()` — read `dbo.BacklogHistory`

**Files:**
- Modify: `nx_lib/views/dashboard.py`
- Test: `tests/unit/test_dashboard_stats.py`

**Interfaces:**
- Produces: `_backlog_history(target_processes, days) -> dict[date, dict[str, int]]` — outer key the snapshot date, inner key the full `"<client>.<process>"` name, value the **last** snapshot of that day summed across `SourceCode`s. Days present only where snapshots exist. Consumed by Task 4 (`backlog_trend`) and Task 5 (`kpi_stats`' backlog delta + sparkline).
- Produces: `RANGE_CHOICES = (14, 30, 90)` and `normalize_range(value) -> int` (returns `14` for anything not in the tuple). Consumed by Tasks 4, 5 and 6.

- [ ] **Step 1: Write the failing unit test** — append to `tests/unit/test_dashboard_stats.py`:

```python
def test_backlog_history_takes_the_last_snapshot_per_day_and_sums_sources(app, monkeypatch):
    """Two snapshots the same day -> the later one wins; two SourceCodes for
    the same (client, process) -> summed. Pairs outside target_processes are
    dropped in Python, never through an interpolated IN list."""
    from datetime import date, datetime, timedelta

    from nx_lib.views import dashboard as dv

    today = date.today()
    def at(day, hour):
        return datetime.combine(day, datetime.min.time()).replace(hour=hour)

    yesterday = today - timedelta(days=1)
    rows = [
        # (SnapshotAt, SourceCode, ClientName, ProcessName, BacklogCount)
        # NOTE the display-cased "Privera": BacklogHistory carries Octo's
        # t_Processes.ClientName, target_processes carries ProcessSources'
        # lower-cased name. Verified on INT 2026-09-04.
        (at(today, 8), "octo", "Privera", "02_Posteingang", 500),
        (at(today, 20), "octo", "Privera", "02_Posteingang", 612),
        (at(today, 20), "ms02", "Privera", "02_Posteingang", 8),
        (at(today, 20), "octo", "Privera", "99_NotGranted", 999),
        (at(yesterday, 20), "octo", "Privera", "02_Posteingang", 564),
    ]
    monkeypatch.setattr(dv, "_default_stat_rows", lambda sql, params=None: rows)

    with app.test_request_context():
        out = dv._backlog_history(["privera.02_Posteingang"], 14)

    # keyed by the canonical (lower-cased) ProcessSources spelling, not Octo's
    assert out[today] == {"privera.02_Posteingang": 620}    # 612 + 8, the 08:00 row discarded
    assert out[yesterday] == {"privera.02_Posteingang": 564}
    assert all("99_NotGranted" not in k for day in out.values() for k in day)


def test_backlog_history_is_empty_when_the_statistics_db_is_dead(app, monkeypatch):
    """_default_stat_rows already swallows and logs; an empty trend must render
    as an empty chart, never as a 500."""
    from nx_lib.views import dashboard as dv

    monkeypatch.setattr(dv, "_default_stat_rows", lambda sql, params=None: [])
    with app.test_request_context():
        assert dv._backlog_history(["sydoc.02_Posteingang"], 14) == {}


def test_normalize_range_falls_back_to_fourteen(app):
    from nx_lib.views import dashboard as dv

    assert dv.normalize_range("30") == 30
    assert dv.normalize_range(90) == 90
    assert dv.normalize_range("7") == 14
    assert dv.normalize_range(None) == 14
    assert dv.normalize_range("'; DROP TABLE x --") == 14
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/unit/test_dashboard_stats.py -q -k "backlog_history or normalize_range"`
Expected: FAIL — `AttributeError: … has no attribute '_backlog_history'`.

- [ ] **Step 3: Implement** — add near the top of `nx_lib/views/dashboard.py`, just below `_PROCESS_PERM_PREFIX`:

```python
# The 14 / 30 / 90-day windows the range control offers. Anything else
# normalizes to 14 -- the value reaches SQL by string interpolation (a
# server-side int, never user text), so the allowlist IS the sanitizer.
RANGE_CHOICES = (14, 30, 90)


def normalize_range(value):
    """One of RANGE_CHOICES, or 14. Accepts str or int; never raises."""
    try:
        days = int(value)
    except (TypeError, ValueError):
        return RANGE_CHOICES[0]
    return days if days in RANGE_CHOICES else RANGE_CHOICES[0]
```

and, below `_avg_processing_by_day`:

```python
_BACKLOG_HISTORY_SQL = """
SELECT SnapshotAt, SourceCode, ClientName, ProcessName, BacklogCount
FROM dbo.BacklogHistory
WHERE SnapshotAt >= CAST(DATEADD(day, ?, CAST(GETDATE() AS DATE)) AS DATETIME2(0))
ORDER BY SnapshotAt
"""


def _backlog_history(target_processes, days):
    """{date: {"<client>.<process>": count}} from dbo.BacklogHistory (Statistics
    DB), one point per day per process: the LAST snapshot of that day, summed
    across SourceCodes (a pair can be served by both the Octo and MS02
    runtimes). Rows outside ``target_processes`` are dropped here in Python --
    14 days x a handful of processes is a few hundred rows, and a Python
    membership test beats interpolating a pair list into the WHERE clause.

    Matching is CASE-INSENSITIVE and that is load-bearing, not defensive:
    BacklogHistory.ClientName comes from Octo's t_Processes.ClientName and is
    display-cased ('Privera', 'ElektroMaterial', 'Compass'), while
    target_processes comes from dbo.ProcessSources.ProcessName and is
    lower-cased ('privera.03_Invoice_New'). Verified on INT 2026-09-04. An
    exact match silently drops every non-MS02 process and leaves a chart that
    looks plausible but is missing most of the backlog.

    The collector (ops/backlog_history/backlog_history.py, every 30 min) owns
    the table; nexora only reads it. A dead Statistics DB yields {} through
    _default_stat_rows' swallow-and-log contract, which the callers render as
    an empty chart."""
    days = max(1, int(days))
    # Keep the canonical (ProcessSources) spelling as the output key, looked up
    # by its folded form, so the API returns names the rest of the app knows.
    wanted = {p.casefold(): p for p in target_processes}

    # (date, client.process) -> {source_code: (snapshot_at, count)} -- keep the
    # latest snapshot per source before summing, so an early-morning row from
    # one source never outranks an evening row from another.
    latest = {}
    for snapshot_at, source_code, client, process, count in _default_stat_rows(
        _BACKLOG_HISTORY_SQL, (-(days - 1),)
    ):
        name = wanted.get(f"{client}.{process}".casefold())
        if name is None:
            continue
        at = snapshot_at if isinstance(snapshot_at, datetime) else datetime.fromisoformat(str(snapshot_at))
        slot = latest.setdefault((at.date(), name), {})
        prev = slot.get(source_code)
        if prev is None or at >= prev[0]:
            slot[source_code] = (at, count or 0)

    out = {}
    for (day, name), by_source in latest.items():
        out.setdefault(day, {})[name] = sum(c for _at, c in by_source.values())
    return {d: out[d] for d in sorted(out)}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `pytest tests/unit/test_dashboard_stats.py -q -k "backlog_history or normalize_range"`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add nx_lib/views/dashboard.py tests/unit/test_dashboard_stats.py
git commit -m "feat(dashboard): read the per-process backlog history snapshots"
```

### Task 4: `GET api/dashboard/backlog_trend`

**Files:**
- Modify: `nx_lib/views/dashboard.py`
- Test: `tests/integration/test_dashboard_routes.py`, `tests/unit/test_create_app.py`

**Interfaces:**
- Produces: `GET /api/dashboard/backlog_trend?range=14` → `{"labels": ["2026-08-22", …], "series": [{"name": "sydoc.02_Posteingang", "values": [612, …], "current": 612}], "total": 1247, "prev_total": 1199}`. Endpoint name `dashboard_backlog_trend`. Series are capped at 4 by current count, the remainder folded into one `"Other"` series; a single selected process collapses to one series named `"Backlog"`.

- [ ] **Step 1: Write the failing integration test** — append to `tests/integration/test_dashboard_routes.py`:

```python
def test_backlog_trend_returns_labels_and_capped_series(user_client, monkeypatch):
    """Five processes -> four named series plus one folded "Other"; labels are
    the zero-filled day window, oldest first."""
    from datetime import date, timedelta

    from nx_lib.views import dashboard as dv

    today = date.today()
    names = [f"c.p{i}" for i in range(5)]
    monkeypatch.setattr(dv, "_allowed_processes", lambda: names)
    monkeypatch.setattr(
        dv,
        "_backlog_history",
        lambda tp, days: {
            today - timedelta(days=1): {n: 10 * (i + 1) for i, n in enumerate(names)},
            today: {n: 100 * (i + 1) for i, n in enumerate(names)},
        },
    )

    resp = user_client.get("/api/dashboard/backlog_trend?range=14")
    assert resp.status_code == 200
    body = resp.get_json()

    assert len(body["labels"]) == 14
    assert body["labels"][-1] == today.isoformat()
    assert [s["name"] for s in body["series"]] == ["c.p4", "c.p3", "c.p2", "c.p1", "Other"]
    assert body["series"][0]["values"][-1] == 500
    assert body["series"][-1]["values"][-1] == 100          # the folded remainder
    assert body["total"] == 1500
    assert body["prev_total"] == 150


def test_backlog_trend_collapses_to_one_series_for_a_single_process(user_client, monkeypatch):
    from datetime import date

    from nx_lib.views import dashboard as dv

    today = date.today()
    monkeypatch.setattr(dv, "_allowed_processes", lambda: ["c.p1"])
    monkeypatch.setattr(dv, "_backlog_history", lambda tp, days: {today: {"c.p1": 77}})

    resp = user_client.get("/api/dashboard/backlog_trend")
    body = resp.get_json()
    assert [s["name"] for s in body["series"]] == ["Backlog"]
    assert body["series"][0]["values"][-1] == 77


def test_backlog_trend_empty_when_nothing_is_granted(noperm_client):
    """No grants -> empty payload, not a 500 and not somebody else's numbers."""
    resp = noperm_client.get("/api/dashboard/backlog_trend")
    assert resp.status_code in (200, 403)
    if resp.status_code == 200:
        assert resp.get_json() == {"labels": [], "series": [], "total": 0, "prev_total": 0}
```

Grep the top of `tests/integration/test_dashboard_routes.py` for the fixtures it already uses (`user_client`, and whichever no-permission client exists) and match them exactly; if there is no `noperm_client`, drop the third test rather than inventing a fixture.

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/integration/test_dashboard_routes.py -q -k backlog_trend`
Expected: FAIL with 404 — the route does not exist yet.

- [ ] **Step 3: Implement** — add below `dashboard_avg_processing_time` in `nx_lib/views/dashboard.py`:

```python
_BACKLOG_SERIES_CAP = 4


@require_permission("dashboard.view")
@cache.cached(
    timeout=300,
    key_prefix=make_cache_key,  # type: ignore[arg-type]  # callable prefix, stubs say str
    response_filter=_cacheable_response,
)
def dashboard_backlog_trend():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    empty = {"labels": [], "series": [], "total": 0, "prev_total": 0}
    allowed_processes = _allowed_processes()
    process_name = session.get("process_name_dashboard", "all")
    target_processes = normalize_process_selection(process_name, allowed_processes)[1]
    if not target_processes:
        return jsonify(empty)

    days = normalize_range(request.args.get("range") or session.get("dashboard_range"))

    try:
        history = _backlog_history(target_processes, days)
        if not history:
            return jsonify(empty)

        today = datetime.now().date()
        window = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]

        current = history.get(max(history), {})
        ranked = sorted(current, key=lambda n: (-current[n], n))
        if len(target_processes) == 1:
            groups = [(_("Backlog"), list(current))]
        elif len(ranked) > _BACKLOG_SERIES_CAP:
            groups = [(n, [n]) for n in ranked[:_BACKLOG_SERIES_CAP]]
            groups.append((_("Other"), ranked[_BACKLOG_SERIES_CAP:]))
        else:
            groups = [(n, [n]) for n in ranked]

        series = [
            {
                "name": label,
                "values": [sum(history.get(d, {}).get(n, 0) for n in members) for d in window],
                "current": sum(current.get(n, 0) for n in members),
            }
            for label, members in groups
        ]
        totals = [sum(s["values"][i] for s in series) for i in range(len(window))]
        return jsonify(
            {
                "labels": [d.isoformat() for d in window],
                "series": series,
                "total": totals[-1] if totals else 0,
                "prev_total": totals[-2] if len(totals) > 1 else 0,
            }
        )
    except Exception as e:
        current_app.logger.error(f"Failed to fetch backlog_trend: {e}")
        return jsonify({"error": _("An unexpected error occurred")}), 500
```

`make_cache_key` must learn about the range — see Task 6. Then register it in `register_routes(app)`, right after the `avg_processing_time` rule:

```python
    app.add_url_rule(
        "/api/dashboard/backlog_trend",
        endpoint="dashboard_backlog_trend",
        view_func=dashboard_backlog_trend,
    )
```

- [ ] **Step 3a: Make sure INT has backlog history to draw.** Already done on 2026-09-04 — 14 days × 6 processes were seeded, so this step is a re-check, not fresh work. If the window has since gone stale (or you need 30/90 days for the wider ranges), re-seed with the `/nx-seed-intdb` command:

```bash
ENVIRONMENT=INT .venv/Scripts/python.exe scripts/seed-int-db.py --days 14          # dry run
ENVIRONMENT=INT .venv/Scripts/python.exe scripts/seed-int-db.py --days 14 --seed 42 --yes
```

It refuses to run outside `ENVIRONMENT=INT` and against any server whose name contains `prd`/`prod`, and it is idempotent (deletes its own window first). Verify:

```bash
ENVIRONMENT=INT .venv/Scripts/python.exe -c "
from nx_lib.db import engine_statistics_db as e
from sqlalchemy import text
print(tuple(e.connect().execute(text('SELECT COUNT(*), MIN(SnapshotAt), MAX(SnapshotAt) FROM dbo.BacklogHistory')).one()))"
```

Then, once the endpoint exists, `curl -s "http://127.0.0.1:8000/api/dashboard/backlog_trend?range=14"` (with a logged-in session cookie) must return 14 labels and **6** series (5 named + `Other`, since INT has 6 processes). **If `series` holds only `sydoc.05_PDBS`, the casefold match in `_backlog_history` regressed** — that is the exact failure mode, measured on INT: an exact match returns 1 series of 6 and still draws a plausible chart.

- [ ] **Step 4: Add the endpoint to the inventory test** — in `tests/unit/test_create_app.py`, add `"dashboard_backlog_trend",` to the list that already contains `"api_recent_activity"` (Grep that literal), keeping the list's existing ordering convention.

- [ ] **Step 5: Run**

Run: `pytest tests/integration/test_dashboard_routes.py tests/unit/test_create_app.py -q -k "backlog_trend or endpoints or routes"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add nx_lib/views/dashboard.py tests/integration/test_dashboard_routes.py tests/unit/test_create_app.py
git commit -m "feat(dashboard): backlog_trend endpoint with per-process series"
```

### Task 5: KPI deltas + sparklines on `kpi_stats` and `avg_processing_time`

**Files:**
- Modify: `nx_lib/views/dashboard.py`
- Test: `tests/integration/test_dashboard_routes.py`

**Interfaces:**
- Changes: `GET api/dashboard/kpi_stats` gains `prev_imported`, `prev_processed`, `prev_backlog`, and `series: {"imported": [7 ints], "processed": [7 ints], "backlog": [7 ints]}`. Existing keys (`imported_today`, `processed_today`, `current_backlog`) are unchanged — the external API and its tests keep working.
- Changes: `GET api/dashboard/avg_processing_time` gains `prev_avg_minutes` (`float | None`) and `series: [7 floats-or-null]` (minutes).

- [ ] **Step 1: Write the failing integration test** — append to `tests/integration/test_dashboard_routes.py`:

```python
def test_kpi_stats_carries_previous_day_and_seven_point_series(user_client, monkeypatch):
    from datetime import date, timedelta

    from nx_lib.views import dashboard as dv

    today = date.today()
    monkeypatch.setattr(dv, "_allowed_processes", lambda: ["c.p1"])
    monkeypatch.setattr(dv, "compute_today_stats", lambda tp: (595, 60))
    monkeypatch.setattr(dv, "total_backlog_count", lambda pairs: 1247)
    monkeypatch.setattr(
        dv,
        "_kpi_daily_counts",
        lambda tp, days: {
            today - timedelta(days=i): {"imported": 500 + i, "processed": 90 - i}
            for i in range(days - 1, -1, -1)
        },
    )
    monkeypatch.setattr(
        dv, "_backlog_history", lambda tp, days: {today - timedelta(days=1): {"c.p1": 1199}, today: {"c.p1": 1247}}
    )

    body = user_client.get("/api/dashboard/kpi_stats").get_json()

    assert body["imported_today"] == 595 and body["current_backlog"] == 1247
    assert body["prev_imported"] == 501 and body["prev_processed"] == 89
    assert body["prev_backlog"] == 1199
    assert len(body["series"]["imported"]) == 7
    assert body["series"]["backlog"][-1] == 1247


def test_avg_processing_time_carries_previous_day_and_series(user_client, monkeypatch):
    from datetime import date, timedelta

    from nx_lib.views import dashboard as dv

    today = date.today()
    monkeypatch.setattr(dv, "_allowed_processes", lambda: ["c.p1"])
    monkeypatch.setattr(
        dv,
        "_avg_processing_by_day",
        lambda tp, days, strict=False: {today: 3600.0, today - timedelta(days=1): 7200.0},
    )

    body = user_client.get("/api/dashboard/avg_processing_time").get_json()

    assert body["avg_display"] == "1.0h"
    assert body["prev_avg_minutes"] == 120.0
    assert len(body["series"]) == 7
    assert body["series"][-1] == 60.0
    assert body["series"][0] is None          # no data that day -> a gap, not a zero
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/integration/test_dashboard_routes.py -q -k "carries_previous_day"`
Expected: FAIL — `KeyError: 'prev_imported'`.

- [ ] **Step 3: Implement in `dashboard_kpi_stats`** — replace its `return jsonify({...})` block (the one holding `"processed_today": processed_today,`) with:

```python
        # 7 points including today, oldest first -- the sparkline window.
        counts = _kpi_daily_counts(target_processes, 7)
        cdays = sorted(counts)
        backlog_hist = _backlog_history(target_processes, 7)
        bdays = sorted(backlog_hist)
        # Live number for today, snapshots for the past: the collector's most
        # recent row is up to 30 min old, so today's own point uses the value
        # actually shown above it.
        backlog_series = [sum(backlog_hist[d].values()) for d in bdays]
        if backlog_series:
            backlog_series[-1] = current_backlog
        prev_backlog = backlog_series[-2] if len(backlog_series) > 1 else 0

        return jsonify(
            {
                "processed_today": processed_today,
                "imported_today": imported_today,
                "current_backlog": current_backlog,
                "prev_imported": counts[cdays[-2]]["imported"] if len(cdays) > 1 else 0,
                "prev_processed": counts[cdays[-2]]["processed"] if len(cdays) > 1 else 0,
                "prev_backlog": prev_backlog,
                "series": {
                    "imported": [counts[d]["imported"] for d in cdays],
                    "processed": [counts[d]["processed"] for d in cdays],
                    "backlog": backlog_series,
                },
            }
        )
```

Also widen the early return for "nothing granted" so the frontend never has to branch on a missing key:

```python
    if not target_processes:
        return jsonify(
            {
                "processed_today": 0,
                "imported_today": 0,
                "current_backlog": 0,
                "prev_imported": 0,
                "prev_processed": 0,
                "prev_backlog": 0,
                "series": {"imported": [], "processed": [], "backlog": []},
            }
        )
```

The existing early return also carries a stale `"processed_week": 0` key that no caller reads (`grep -rn processed_week nx_lib templates static tests` hits only `nx_lib/views/dashboard.py` and one test). Drop it — and update `test_kpi_stats_authed_returns_zeros` in `tests/integration/test_dashboard_routes.py`, which asserts the early-return dict **exactly**, to the new shape:

```python
    assert body == {
        "processed_today": 0,
        "imported_today": 0,
        "current_backlog": 0,
        "prev_imported": 0,
        "prev_processed": 0,
        "prev_backlog": 0,
        "series": {"imported": [], "processed": [], "backlog": []},
    }
```

- [ ] **Step 4: Implement in `dashboard_avg_processing_time`** — Read the function first; it currently calls `compute_avg_processing_time(target_processes)` and formats with `format_avg_processing_display`. Replace that pair with:

```python
        series_sec = _avg_processing_by_day(target_processes, 7)
        today = datetime.now().date()
        window = [today - timedelta(days=i) for i in range(6, -1, -1)]
        avg_sec = series_sec.get(today)
        prev_sec = series_sec.get(today - timedelta(days=1))

        avg_minutes, avg_display = (
            format_avg_processing_display(avg_sec) if avg_sec is not None else (None, "—")
        )
        return jsonify(
            {
                "avg_minutes": avg_minutes,
                "avg_display": avg_display,
                "prev_avg_minutes": round(prev_sec / 60, 1) if prev_sec is not None else None,
                # minutes, None where no documents finished that day
                "series": [
                    round(series_sec[d] / 60, 1) if d in series_sec else None for d in window
                ],
            }
        )
```

Keep whatever additional keys the current response already returns (Grep the function's `jsonify` call and merge rather than replace).

- [ ] **Step 5: Run**

Run: `pytest tests/integration/test_dashboard_routes.py tests/unit/test_dashboard_stats.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add nx_lib/views/dashboard.py tests/integration/test_dashboard_routes.py
git commit -m "feat(dashboard): day-over-day deltas and sparkline series on the KPI endpoints"
```

### Task 6: `range` on `processed_over_time`, persisted in the session

**Files:**
- Modify: `nx_lib/views/dashboard.py`
- Test: `tests/integration/test_dashboard_routes.py`

**Interfaces:**
- Changes: `GET api/dashboard/processed_over_time?range=30` honours the window; without the parameter it falls back to `session['dashboard_range']`, then 14.
- Changes: `POST api/dashboard/set_filter` accepts an optional `range` alongside `process_name` and stores `session['dashboard_range']`; it returns `{"ok": True, "process_name": …, "range": …}`.
- Changes: `make_cache_key()` and the three `key_prefix` lambdas include the resolved range, so a 30-day response can never be served to a 14-day request.
- Changes: `dashboard()` passes `dash_range=…` to the template.

- [ ] **Step 1: Write the failing integration test** — append to `tests/integration/test_dashboard_routes.py`:

```python
def test_processed_over_time_honours_the_range_parameter(user_client, monkeypatch):
    from nx_lib.views import dashboard as dv

    seen = {}
    monkeypatch.setattr(dv, "_allowed_processes", lambda: ["c.p1"])
    monkeypatch.setattr(dv, "_statconfig_sources", lambda tp: [])

    def _spy(sql, *a, **k):
        seen["sql"] = sql
        return []

    monkeypatch.setattr(dv, "_default_stat_rows", _spy)

    body = user_client.get("/api/dashboard/processed_over_time?range=30").get_json()
    assert len(body["labels"]) == 30

    body = user_client.get("/api/dashboard/processed_over_time?range=7").get_json()
    assert len(body["labels"]) == 14          # not an allowed choice -> default


def test_set_filter_persists_the_range_in_the_session(user_client, monkeypatch):
    from nx_lib.views import dashboard as dv

    monkeypatch.setattr(dv, "_allowed_processes", lambda: ["c.p1"])
    monkeypatch.setattr(dv, "_statconfig_sources", lambda tp: [])
    monkeypatch.setattr(dv, "_default_stat_rows", lambda sql, *a, **k: [])

    resp = user_client.post("/api/dashboard/set_filter", json={"process_name": "all", "range": 90})
    assert resp.get_json()["range"] == 90

    # the next request needs no ?range= to stay on 90 days
    body = user_client.get("/api/dashboard/processed_over_time").get_json()
    assert len(body["labels"]) == 90
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/integration/test_dashboard_routes.py -q -k "honours_the_range or persists_the_range"`
Expected: FAIL — 14 labels for the 30-day request (the window is hardcoded).

- [ ] **Step 3: Implement in `dashboard_processed_over_time`** — resolve the window once, right after `target_processes` is computed:

```python
    days = normalize_range(request.args.get("range") or session.get("dashboard_range"))
```

then in the loop over `default_configs` replace `DATEADD(day, -14, GETDATE())` with `DATEADD(day, -{days - 1}, GETDATE())`, in the MS02 leg replace `CURRENT_DATE - 14` with `CURRENT_DATE - {days - 1}`, and replace the zero-fill loop

```python
        for i in range(15):
```

with

```python
        for i in range(days):
```

so the response always carries exactly `days` labels.

- [ ] **Step 4: Implement the session write** — in `dashboard_set_filter`, after `session["process_name_dashboard"] = process_name`:

```python
    # ponytail: the range rides the session, like the process filter above it --
    # not nx_lib/ui_prefs.py, which is the pre-paint appearance allowlist. Move
    # it there if users ask for the choice to follow them across devices.
    if "range" in (request.json or {}):
        session["dashboard_range"] = normalize_range(request.json.get("range"))
    return jsonify(
        {
            "ok": True,
            "process_name": process_name,
            "range": session.get("dashboard_range", RANGE_CHOICES[0]),
        }
    )
```

- [ ] **Step 5: Put the range in every cache key** — `make_cache_key` becomes:

```python
def make_cache_key(*args, **kwargs):
    days = normalize_range(request.args.get("range") or session.get("dashboard_range"))
    return (
        f"{request.path}_{session.get('userid')}_"
        f"{session.get('process_name_dashboard','all')}_"
        f"{session.get('dashboard_tenant','')}_{days}"
    )
```

and the three inline `key_prefix=lambda: f"kpi_stats_…"` / `hourly_stats_…` / `avg_processing_time_…` lambdas each gain `_{normalize_range(session.get('dashboard_range'))}` at the end. (`hourly_stats` ignores the range, but a uniform key costs nothing and removes the "which endpoints are range-aware?" question from every future edit.)

- [ ] **Step 6: Pass the initial range to the template** — in `dashboard()`, beside `process_name=process_name,` in the `render_template` call add:

```python
            dash_range=normalize_range(session.get("dashboard_range")),
```

- [ ] **Step 7: Run**

Run: `pytest tests/integration/test_dashboard_routes.py tests/unit/test_dashboard_stats.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add nx_lib/views/dashboard.py tests/integration/test_dashboard_routes.py
git commit -m "feat(dashboard): 14/30/90-day range drives the charts and rides the session"
```

---

# PHASE 2 — Tokens and reusable console classes

### Task 7: Series, control-height and slim type tokens

**Files:**
- Modify: `static/css/nexora-ui.css`
- Test: `tests/unit/test_ui_chrome_regressions.py`

**Interfaces:**
- Produces: `--nx-series-1 … --nx-series-5` (light in `:root`, dark under `html.dark`), `--ctl-h` / `--ctl-h-lg`, `--fs-eyebrow` / `--fs-micro` / `--fs-meta` / `--fs-control` / `--fs-title` / `--fs-kpi`. Consumed by Tasks 8–11.

- [ ] **Step 1: Write the failing token test** — append to `tests/unit/test_ui_chrome_regressions.py`:

```python
def test_series_tokens_exist_in_both_themes():
    """A categorical chart palette must be defined independently of the accent
    (which the user can switch to any of seven hues) and must have dark twins."""
    css = (REPO_ROOT / "static" / "css" / "nexora-ui.css").read_text(encoding="utf-8")
    # Split on the dark ROOT block, not the bare string: "html.dark" also
    # appears in the file's table-of-contents comment on line 11 and in the
    # per-accent html.dark[data-accent="..."] blocks far below.
    light, dark = css.split("\nhtml.dark {", 1)
    for i in range(1, 6):
        assert f"--nx-series-{i}:" in light, f"--nx-series-{i} missing from the light palette"
        assert f"--nx-series-{i}:" in dark, f"--nx-series-{i} missing from the dark palette"


def test_slim_control_height_token_exists():
    css = (REPO_ROOT / "static" / "css" / "nexora-ui.css").read_text(encoding="utf-8")
    assert "--ctl-h:" in css
```

`REPO_ROOT` is already defined at the top of `tests/unit/test_ui_chrome_regressions.py` as `Path(__file__).resolve().parents[2]` — reuse it, do not add a second one.

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/unit/test_ui_chrome_regressions.py -q -k "series_tokens or slim_control"`
Expected: FAIL — `--nx-series-1 missing from the light palette`.

- [ ] **Step 3: Implement** — in `static/css/nexora-ui.css`, inside the light `:root` block (immediately after the `--nx-success/--nx-warning/--nx-danger` status lines, Grep `--nx-danger:  #dc2626;`):

```css
  /* Categorical chart series — deliberately independent of --nx-accent so a
     multi-series chart stays readable under all seven accent picks. */
  --nx-series-1: #d97706;
  --nx-series-2: #7c3aed;
  --nx-series-3: #0891b2;
  --nx-series-4: #db2777;
  --nx-series-5: #059669;

  /* Slim-console control height + type ramp (dashboard console, #dashboard-redesign) */
  --ctl-h:      29px;
  --ctl-h-lg:   33px;
  --fs-eyebrow: 10px;
  --fs-micro:   11px;
  --fs-meta:    11.5px;
  --fs-control: 12.5px;
  --fs-title:   15px;
  --fs-kpi:     32px;
```

and in the `html.dark` block (after its `--nx-danger:  #f87171;` line):

```css
  --nx-series-1: #fbbf24;
  --nx-series-2: #a78bfa;
  --nx-series-3: #22d3ee;
  --nx-series-4: #f472b6;
  --nx-series-5: #34d399;
```

Finally, beside the existing `html.nx-compact body.nx-app .nx-main` rule, add the compact-density shrink:

```css
html.nx-compact { --ctl-h: 27px; --ctl-h-lg: 30px; }
```

- [ ] **Step 4: Run**

Run: `pytest tests/unit/test_ui_chrome_regressions.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add static/css/nexora-ui.css tests/unit/test_ui_chrome_regressions.py
git commit -m "feat(ui): chart-series, slim control-height and console type tokens"
```

### Task 8: Reusable console component classes

**Files:**
- Modify: `static/css/nexora-ui.css`

**Interfaces:**
- Produces the class families the dashboard markup (Task 10) uses and the next migrated page reuses: `.nx-kpi-strip` / `.nx-kpi` / `.nx-kpi__label` / `.nx-kpi__value` / `.nx-kpi__delta` / `.nx-kpi__spark`, `.nx-segmented` / `.nx-segmented__btn`, `.nx-tabs--slim` (modifier on the existing `.nx-tabs`/`.nx-tab`), `.nx-chart-head` / `.nx-chart-head__title` / `.nx-chart-head__meta`, `.nx-legend` / `.nx-legend__item` / `.nx-legend__swatch`, `.nx-section-rule`, `.nx-eyebrow`, `.nx-live-dot`.

- [ ] **Step 1: Read the component sources for the exact values** — the kit's reference implementations under `docs/design/Dashboard_redesign/design_handoff_dashboard_console/design_system/components/console/` (`KpiStrip`/`SegmentedControl`/`UnderlineTabs`/`ChartHeader`/`SeriesLegend`) and `core/` (`SectionRule`, `Label`). They are JSX that never runs here — lift the numbers, not the code.

- [ ] **Step 2: Append the classes** to `static/css/nexora-ui.css`, in a clearly fenced section at the end of the Components block:

```css
/* ============================================================
   Console kit — slim, borderless layout primitives shared by the
   Dashboard console and (next) the other migrated pages.
   Every colour rides the --nx-* tokens, so the user's accent pick,
   dark mode and tenant branding apply for free. Prototype hexes are
   NOT reproduced here: the design's amber IS --nx-accent.
   ============================================================ */

/* Uppercase group label, 10px/700 */
.nx-eyebrow {
  font-size: var(--fs-eyebrow); font-weight: 700; text-transform: uppercase;
  letter-spacing: .09em; color: var(--nx-text-meta);
}

/* Hairline that separates two borderless sections */
.nx-section-rule { border-top: 1px solid var(--nx-border); }

/* Live/"fresh data" dot */
.nx-live-dot {
  width: 7px; height: 7px; border-radius: var(--nx-radius-pill);
  background: var(--nx-success); flex-shrink: 0;
}

/* ---------- KPI strip: no cards, hairlines only ---------- */
.nx-kpi-strip {
  display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
  border-bottom: 1px solid var(--nx-border);
}
.nx-kpi {
  padding: 18px 30px 16px;
  border-left: 1px solid var(--nx-divider);
  min-width: 0;
}
.nx-kpi:first-child { border-left: none; }
.nx-kpi__label {
  font-size: var(--fs-eyebrow); font-weight: 700; text-transform: uppercase;
  letter-spacing: .09em; color: var(--nx-text-meta); margin: 0;
}
.nx-kpi__body {
  display: flex; align-items: flex-end; justify-content: space-between;
  gap: 16px; margin-top: 10px;
}
.nx-kpi__value {
  font-family: var(--nx-mono); font-variant-numeric: tabular-nums;
  font-size: var(--fs-kpi); font-weight: 600; letter-spacing: -1.4px;
  line-height: 1; color: var(--nx-text); margin: 0;
}
.nx-kpi__delta {
  font-size: var(--fs-micro); font-weight: 600; margin: 6px 0 0;
  color: var(--nx-text-meta);
}
.nx-kpi__delta--good { color: var(--nx-success); }
.nx-kpi__delta--bad  { color: var(--nx-accent-hover); }
.nx-kpi__delta span { font-weight: 400; color: var(--nx-text-meta); }
.nx-kpi__spark { width: 120px; height: 36px; opacity: .9; flex-shrink: 0; }
.nx-kpi__spark path { stroke-linejoin: round; }

@media (max-width: 1024px) {
  .nx-kpi-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .nx-kpi { padding: 14px 18px 12px; }
  .nx-kpi:nth-child(odd)  { border-left: none; }
  .nx-kpi:nth-child(n+3)  { border-top: 1px solid var(--nx-divider); }
}

/* ---------- Segmented control ---------- */
.nx-segmented {
  display: inline-flex; height: var(--ctl-h); overflow: hidden;
  border: 1px solid var(--nx-border); border-radius: calc(var(--nx-radius-scale, 1) * 8px);
  background: var(--nx-card);
}
.nx-segmented__btn {
  border: none; border-left: 1px solid var(--nx-border); background: transparent;
  padding: 0 10px; font-family: inherit; font-size: var(--fs-meta); font-weight: 600;
  color: var(--nx-text-meta); cursor: pointer;
}
.nx-segmented__btn:first-child { border-left: none; }
.nx-segmented__btn:hover { color: var(--nx-text); }
.nx-segmented__btn.is-active { background: var(--nx-accent-tint); color: var(--nx-accent-hover); }
.nx-segmented__btn:focus-visible {
  outline: none; box-shadow: inset 0 0 0 2px var(--nx-accent);
}

/* ---------- Slim underline tabs (modifier on .nx-tabs/.nx-tab) ---------- */
.nx-tabs--slim { gap: 16px; margin: 0; border-bottom: none; }
.nx-tabs--slim .nx-tab { font-size: 12px; font-weight: 600; padding: 0 0 5px; margin-bottom: 0; }

/* ---------- Chart header ---------- */
.nx-chart-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.nx-chart-head__title {
  font-size: var(--fs-title); font-weight: 700; letter-spacing: -0.02em;
  color: var(--nx-text); margin: 0;
}
.nx-chart-head__meta {
  font-size: var(--fs-micro); color: var(--nx-text-meta);
  font-variant-numeric: tabular-nums;
}
.nx-chart-head__spacer { margin-left: auto; }

/* ---------- Series legend ---------- */
.nx-legend { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
.nx-legend__item {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: var(--fs-micro); color: var(--nx-text-sec);
}
.nx-legend__swatch { width: 16px; border-top: 2.5px solid currentColor; }
.nx-legend__swatch--dashed { border-top-style: dashed; }
.nx-legend__swatch--dotted { border-top-style: dotted; }
.nx-legend__count { color: var(--nx-text-meta); font-variant-numeric: tabular-nums; }
```

- [ ] **Step 3: Lint the sheet** — the repo's CSS regression tests read these files as text:

Run: `pytest tests/unit/test_ui_chrome_regressions.py tests/unit/test_display_none_important.py tests/unit/test_static_v_lint.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add static/css/nexora-ui.css
git commit -m "feat(ui): console kit classes for KPI strip, segmented control and chart headers"
```

---

# PHASE 3 — Page rebuild

### Task 9: `dashboard.css` — drop the dead rules, add the page layout

**Files:**
- Modify: `static/css/dashboard.css`

**Interfaces:**
- Produces: `.nx-dash-head`, `.nx-dash-head__meta`, `.nx-dash-filter`, `.nx-dash-chart`, `.nx-dash-chart__body`, `.nx-dash-backlog`, `.nx-dash-backlog__body`. Consumed by Task 10's markup.

- [ ] **Step 1: Prove the dead rules are dead** before deleting them:

Run: `grep -rn "progress-step\|progress-icon\|timeline-item\|timeline-icon\|timeline-connector\|animate-rotate\|animate-pulse-icon" templates static/js nx_lib`
Expected: no hits (the selectors exist only in `static/css/dashboard.css`). If any hit appears, keep that rule and note it in the commit body.

- [ ] **Step 2: Rewrite the file** — keep `html`, `body`, `.skeleton-shimmer` + `@keyframes shimmer` and the whole `/* --- Flatpickr … --- */` block verbatim; delete `.progress-*`, `.timeline-*`, `@keyframes rotate`, `.animate-rotate`, `@keyframes pulse-soft`, `.animate-pulse-icon`; replace the `@media (max-width: 768px)` block's `.timeline-*` lines. Then append:

```css
/* ============================================================
   Dashboard console (option 1a). Layout only — every component
   used here (.nx-kpi-strip, .nx-segmented, .nx-tabs--slim,
   .nx-chart-head, .nx-legend) lives in nexora-ui.css so the next
   migrated page reuses it. No hardcoded colours: the design's
   amber IS var(--nx-accent).
   ============================================================ */

/* Row 1 — page head. One flex row; the live indicator + refresh button
   sit right of a spacer. Replaces the two-line title/subtitle block. */
.nx-dash-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.nx-dash-head__meta {
  font-size: var(--fs-meta); color: var(--nx-text-meta);
  font-variant-numeric: tabular-nums; margin: 2px 0 0;
}
.nx-dash-head__right {
  margin-left: auto; display: flex; align-items: center; gap: 12px;
}
.nx-dash-head__live { display: inline-flex; align-items: center; gap: 6px; }

/* Row 2 — filter row, closed by a rule. D11: the shared .nx-scope
   component is sized here, never edited in nexora-ui.css. */
.nx-dash-filter {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  margin-top: 18px; padding-bottom: 14px;
  border-bottom: 1px solid var(--nx-border);
}
.nx-dash-filter__spacer { margin-left: auto; }
.nx-dash-filter .nx-scope { min-width: 260px; }
.nx-dash-filter .nx-scope-btn {
  min-height: var(--ctl-h); padding: 0 9px; font-size: var(--fs-control); font-weight: 500;
}
.nx-dash-filter .nx-scope-summary {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* Row 4 — main chart: full content width, no frame. */
.nx-dash-chart { padding: 16px 0 8px; }
.nx-dash-chart__body { height: 290px; margin-top: 14px; }

/* Row 5 — backlog trend: no frame, separated by a top rule only. */
.nx-dash-backlog { padding: 18px 0 4px; margin-top: 10px; }
.nx-dash-backlog__body { height: 200px; margin-top: 10px; }

@media (max-width: 768px) {
  .nx-dash-chart__body { height: 220px; }
  .nx-dash-backlog__body { height: 180px; }
}
```

- [ ] **Step 3: Verify no accent hex survived**

Run: `grep -nE "#(d97706|ea580c|b45309|fef3e2|fef7ed|1f2937|9ca3af|e5e7eb|f3f4f6|059669)" static/css/dashboard.css`
Expected: hits only inside the retained flatpickr block (`#111827`, `#6b7280` there are pre-existing and out of scope). Any hit in the new console section is a bug — replace it with the matching `--nx-*` token.

- [ ] **Step 4: Commit**

```bash
git add static/css/dashboard.css
git commit -m "refactor(dashboard): console layout styles replace the dead card-era CSS"
```

### Task 10: `dashboard.html` — the console markup

**Files:**
- Modify: `templates/dashboard.html`
- Test: `tests/unit/test_dashboard_signin_escape.py`, `tests/unit/test_template_layout.py`

**Interfaces:**
- Produces the DOM contract Task 11's JS binds to: `#dash-refresh`, `#dash-live-time`, `#dash-countdown`, `#dash-range` (with `.nx-segmented__btn[data-range]`), `#kpi-imported|processed|backlog|avgtime` each wrapping `.nx-kpi__value` / `.nx-kpi__delta` / `.nx-kpi__spark`, `#dash-view-tabs` (with `.nx-tab[data-view="time"|"hour"]`), `#chart-title`, `#chart-meta`, `#processedOverTimeChart`, `#hourlyChart`, `#hourlyChartEmpty`, `#backlog-total`, `#backlog-delta`, `#backlog-legend`, `#backlogTrendChart`.
- Removed: the `nx-stat` KPI cards, the `Recent Validations` card and `#activity-feed`, the standalone hourly card, every `nx-card` on the page, the `nx-subtitle` marketing line.

- [ ] **Step 1: Replace the `<main class="nx-main">` body.** Keep `<head>` as it is (flatpickr, Chart.js, Font Awesome and `static_v('css/dashboard.css')` all stay), keep the `{% set active_page = … %}` line and `{% include '_header.html' %}` untouched (#255 / migration `0097`), and keep the two closing `{% include %}`s. The new body:

```html
  <main class="nx-main">
    <div class="nx-dash-head nx-rise">
      <span class="nx-page-icon"><i class="fas fa-gauge-high"></i></span>
      <div>
        {% if dashboard_tenant %}
        <h1 class="nx-title" data-testid="dashboard-title">{{ _("%(tenant)s Dashboard", tenant=dashboard_tenant.display_name) }}</h1>
        {% else %}
        <h1 class="nx-title" data-testid="dashboard-title">{{ _("Global Dashboard") }}</h1>
        {% endif %}
        {# One muted line replaces the marketing subtitle. The name MUST stay
           |e-escaped -- test_dashboard_signin_escape.py pins this expression
           (security audit #193, finding 9). #}
        <p class="nx-dash-head__meta" data-testid="dashboard-signin-note">{{ _("Signed in as %(name)s", name="<strong>"|safe ~ fullname|e ~ "</strong>"|safe)|safe }}{% if prev_login_at %} · {{ _("last sign-in %(when)s", when=prev_login_at|datetimeformat('dd.MM.yyyy HH:mm')) }}{% endif %}</p>
      </div>
      <div class="nx-dash-head__right">
        <span class="nx-dash-head__live nx-dash-head__meta">
          <span class="nx-live-dot"></span>
          <span>{{ _("Updated") }} <span id="dash-live-time">—</span> · {{ _("next in") }} <span id="dash-countdown">30</span>s</span>
        </span>
        <button type="button" class="nx-btn nx-btn--secondary nx-btn--sm" id="dash-refresh" data-testid="dashboard-refresh">
          <i class="fas fa-rotate" aria-hidden="true"></i> {{ _("Refresh") }}
        </button>
      </div>
    </div>

    <div class="nx-dash-filter">
      <span id="prcfDLabel" class="nx-eyebrow">{{ _("Process") }}</span>
      <div class="nx-scope nx-scope--inline" data-testid="dashboard-process-filter">
        <input type="text" id="prcfD" name="prcfD" class="hidden" value="{{ process_name }}" readonly
               tabindex="-1" data-testid="dashboard-process-filter-value">
        <button type="button" class="nx-scope-btn" aria-expanded="false" aria-labelledby="prcfDLabel"
                data-testid="dashboard-process-filter-btn">
          <span class="nx-scope-summary"></span>
          <i class="fas fa-chevron-down" aria-hidden="true"></i>
        </button>
        <div class="nx-scope-menu" hidden role="group" aria-label="{{ _('Filter by client and process') }}"
             data-testid="dashboard-process-filter-menu"></div>
      </div>
      <span class="nx-dash-filter__spacer"></span>
      <div class="nx-segmented" id="dash-range" role="group" aria-label="{{ _('Time range') }}"
           data-testid="dashboard-range">
        {% for days in (14, 30, 90) %}
        <button type="button" class="nx-segmented__btn{% if days == dash_range %} is-active{% endif %}"
                data-range="{{ days }}" aria-pressed="{{ 'true' if days == dash_range else 'false' }}">{{ days }} {{ _("d") }}</button>
        {% endfor %}
      </div>
    </div>

    <div class="nx-kpi-strip nx-rise-2">
      {% for kid, label in [
           ('imported',  _("Imported today")),
           ('processed', _("Processed today")),
           ('backlog',   _("Current backlog")),
           ('avgtime',   _("Avg. processing time")) ] %}
      <div class="nx-kpi" id="kpi-{{ kid }}">
        <p class="nx-kpi__label">{{ label }}</p>
        <div class="nx-kpi__body">
          <div>
            <p class="nx-kpi__value"><span class="skeleton-shimmer block w-16 h-8 rounded-lg"></span></p>
            <p class="nx-kpi__delta"></p>
          </div>
          <svg class="nx-kpi__spark" viewBox="0 0 120 36" preserveAspectRatio="none" aria-hidden="true"></svg>
        </div>
      </div>
      {% endfor %}
    </div>

    <div class="nx-dash-chart nx-rise-3">
      <div class="nx-chart-head">
        <h3 class="nx-chart-head__title" id="chart-title">{{ _("Documents processed over time") }}</h3>
        <span class="nx-chart-head__meta" id="chart-meta"></span>
        <span class="nx-chart-head__spacer"></span>
        <div class="nx-tabs nx-tabs--slim" id="dash-view-tabs" role="tablist" data-testid="dashboard-view-tabs">
          <button type="button" class="nx-tab is-active" data-view="time" role="tab" aria-selected="true">{{ _("Over time") }}</button>
          <button type="button" class="nx-tab" data-view="hour" role="tab" aria-selected="false">{{ _("Today by hour") }}</button>
        </div>
      </div>
      <div class="nx-dash-chart__body" id="chart-body-time"><canvas id="processedOverTimeChart"></canvas></div>
      <div class="nx-dash-chart__body [display:none]!" id="chart-body-hour"><canvas id="hourlyChart"></canvas></div>
      <div class="nx-empty [display:none]!" id="hourlyChartEmpty">
        <div class="nx-empty__art"><i class="fa-solid fa-chart-column"></i></div>
        <p class="nx-empty__title">{{ _("No documents processed yet today.") }}</p>
      </div>
    </div>

    <div class="nx-dash-backlog nx-section-rule nx-rise-3">
      <div class="nx-chart-head">
        <h3 class="nx-chart-head__title">{{ _("Backlog") }}</h3>
        <span class="nx-chart-head__meta"><span id="backlog-total">—</span> {{ _("open") }} · <span id="backlog-delta"></span></span>
        <span class="nx-chart-head__spacer"></span>
        <div class="nx-legend" id="backlog-legend"></div>
      </div>
      <p class="nx-eyebrow" id="backlog-eyebrow">{{ _("Trend") }}</p>
      <div class="nx-dash-backlog__body"><canvas id="backlogTrendChart"></canvas></div>
    </div>
  </main>
```

`.nx-btn--secondary` (white on a `--nx-border-strong` outline) is the existing modifier matching the design's "`#fff` on `1px solid #e5e7eb`" refresh button; `.nx-btn--sm` brings it down to 12px. Both are already in `nexora-ui.css` — do not add a new button variant.

- [ ] **Step 2: Verify the security test still pins the sign-in expression**

Run: `pytest tests/unit/test_dashboard_signin_escape.py -q`
Expected: PASS. If `test_dashboard_template_uses_escaped_name` fails, the `fullname|e` expression was altered — restore it character-for-character.

- [ ] **Step 3: Run the template lints**

Run: `pytest tests/unit/test_template_layout.py tests/unit/test_no_inline_event_handlers.py tests/unit/test_display_none_important.py tests/unit/test_template_url_prefix.py -q`
Expected: PASS. `test_display_none_important` will fail if Task 11's JS later touches `style.display` on `#chart-body-hour` / `#hourlyChartEmpty` — those two carry `[display:none]!`, so they are toggled with `classList` only.

- [ ] **Step 4: Commit**

```bash
git add templates/dashboard.html
git commit -m "feat(dashboard): borderless console markup replaces the card grid"
```

### Task 11: `static/js/dashboard.js` + the data shim

**Files:**
- Create: `static/js/dashboard.js`
- Modify: `templates/js/_dashboard_js.html`

**Interfaces:**
- Consumes: `window.NX` (`esc`, `api`, `toast`, `formatDate`), `window.API_PREFIX`, `window.csrfToken`, and `window.NX_DASH = { strings: {...}, range: <int>, refreshMs: 30000 }` written by the shim.
- Produces: no globals beyond the IIFE; all behaviour bound on `DOMContentLoaded`.

- [ ] **Step 1: Reduce the shim to data + strings** — `templates/js/_dashboard_js.html` becomes:

```html
{# #191 shim: only Jinja-rendered data and translated strings live here.
   Behaviour is in static/js/dashboard.js, which has no url_for() and no
   gettext -- it reads both off window. #}
<script nonce="{{ csp_nonce() }}">
  window.NX_DASH = {
    range: {{ dash_range|tojson }},
    refreshMs: 30000,
    strings: {
      noData:        {{ _("No data to display") | tojson }},
      documents:     {{ _("Documents processed") | tojson }},
      overTime:      {{ _("Documents processed over time") | tojson }},
      byHour:        {{ _("Documents processed today, by hour") | tojson }},
      daysMeta:      {{ _("%(days)s days · peak %(peak)s") | tojson }},
      hourMeta:      {{ _("peak %(peak)s at %(hour)s") | tojson }},
      vsYesterday:   {{ _("vs. yesterday") | tojson }},
      trendDays:     {{ _("Trend, %(days)s days") | tojson }},
      sinceYesterday:{{ _("%(delta)s since yesterday") | tojson }},
      refreshFailed: {{ _("Could not refresh the dashboard") | tojson }}
    }
  };
</script>
<script src="{{ static_v('js/dashboard.js') }}" nonce="{{ csp_nonce() }}" defer></script>
```

- [ ] **Step 2: Write `static/js/dashboard.js`** — port the surviving logic from the old partial (`nxAxis`, `applyChartTheme`, the `noDataPlugin`, `animateValue`, the `processedOverTimeChart` config **including its `mousemove` chartArea-clamp workaround and its comment**, the hourly bar config) and add the new behaviour. Delete `shuffleObject`, `escapeHtml`, `onActivityFeedClick` and `updateActivityFeed` — the feed is gone (Task 12), and `NX.esc` covers escaping. Structure:

```js
/* Dashboard console (option 1a). Behaviour only -- strings and Jinja data
   arrive on window.NX_DASH; see templates/js/_dashboard_js.html. */
(function () {
  'use strict';

  const S = window.NX_DASH.strings;
  const P = window.API_PREFIX;
  const SERIES_DASH = [[], [6, 4], [2, 3], [10, 3, 2, 3], [4, 2]];

  let processedChart, hourlyChart, backlogChart;
  let view = 'time';
  let range = window.NX_DASH.range || 14;
  let countdown = window.NX_DASH.refreshMs / 1000;

  function token(name, fallback) {
    return (getComputedStyle(document.body).getPropertyValue(name) || fallback).trim();
  }
  function nxAxis() {
    return { grid: token('--nx-divider', '#f3f4f6'), text: token('--nx-text-meta', '#9ca3af') };
  }
  function seriesColor(i) { return token(`--nx-series-${(i % 5) + 1}`, '#d97706'); }

  /* ---------- sparklines: 7 points, hand-built polyline (D3) ---------- */
  function drawSparkline(svg, values, color) {
    svg.innerHTML = '';
    const pts = (values || []).filter((v) => v !== null && v !== undefined);
    if (pts.length < 2) return;
    const min = Math.min(...pts), max = Math.max(...pts);
    const span = max - min || 1;
    const step = 120 / (pts.length - 1);
    const xy = pts.map((v, i) => [i * step, 34 - ((v - min) / span) * 30]);
    const line = xy.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join('');
    const area = `${line}L120,36L0,36Z`;
    svg.insertAdjacentHTML('beforeend',
      `<path d="${area}" fill="${color}" fill-opacity="0.14" stroke="none"></path>` +
      `<path d="${line}" fill="none" stroke="${color}" stroke-width="1.6"></path>`);
  }

  /* ---------- one KPI cell ---------- */
  function renderKpi(id, value, prev, series, opts) {
    const cell = document.getElementById(`kpi-${id}`);
    if (!cell) return;
    const valueEl = cell.querySelector('.nx-kpi__value');
    const deltaEl = cell.querySelector('.nx-kpi__delta');
    valueEl.textContent = opts.display !== undefined ? opts.display : Number(value || 0).toLocaleString();

    deltaEl.className = 'nx-kpi__delta';
    if (prev === null || prev === undefined || value === null || value === undefined) {
      deltaEl.textContent = '';
    } else {
      const diff = value - prev;
      // Direction-aware: fewer backlog items / less processing time is good.
      const good = opts.lowerIsBetter ? diff <= 0 : diff >= 0;
      deltaEl.classList.add(good ? 'nx-kpi__delta--good' : 'nx-kpi__delta--bad');
      const shown = opts.formatDelta ? opts.formatDelta(diff)
        : `${diff >= 0 ? '+' : ''}${prev ? Math.round((diff / prev) * 100) : 0}%`;
      deltaEl.innerHTML = `${window.NX.esc(shown)} <span>${window.NX.esc(S.vsYesterday)}</span>`;
    }
    drawSparkline(cell.querySelector('.nx-kpi__spark'), series,
      opts.lowerIsBetter ? token('--nx-success', '#059669') : token('--nx-accent', '#d97706'));
  }
```

Then the five update functions and the wiring. Requirements each must satisfy — implement them in this order, running the browser check in Task 14 after each is visible:

- `updateKpis()` — one `Promise.all` over `api/dashboard/kpi_stats` and `api/dashboard/avg_processing_time`; feeds `renderKpi` four times. `imported`/`processed` use percentage deltas; `backlog` uses `lowerIsBetter: true` with `formatDelta: (d) => (d >= 0 ? '+' : '') + d.toLocaleString()`; `avgtime` uses `display: body.avg_display`, `lowerIsBetter: true`, `formatDelta` in hours (`(d/60).toFixed(1) + 'h'`), and `series` = the minutes array. Keep the existing `animateValue` count-up for the three integer KPIs.
- `updateOverTime()` — `api/dashboard/processed_over_time?range=${range}`; sets `#chart-meta` from `S.daysMeta` with `days`/`peak`.
- `updateHourly()` — unchanged endpoint; toggles `#hourlyChartEmpty` and `#chart-body-hour` with `classList.add/remove('[display:none]!')`, **never** `style.display`.
- `updateBacklog()` — `api/dashboard/backlog_trend?range=${range}`; builds one Chart.js dataset per series with `borderColor: seriesColor(i)`, `borderDash: SERIES_DASH[i]`, `borderWidth: 2`, `pointRadius: 0`, `tension: 0.3`, `fill: false`; writes `#backlog-total`, `#backlog-delta` (from `S.sinceYesterday`), `#backlog-eyebrow` (`S.trendDays`) and renders `#backlog-legend` with one `.nx-legend__item` per series whose `.nx-legend__swatch` gets `style.color = seriesColor(i)` plus the `--dashed`/`--dotted` modifier matching `SERIES_DASH[i]`.
- `setView(next)` — client-side only, no refetch: toggles `is-active`/`aria-selected` on the two `.nx-tab`s, swaps `#chart-title` between `S.overTime`/`S.byHour`, swaps which `.nx-dash-chart__body` carries `[display:none]!`, and re-renders `#chart-meta`.
- `setRange(next)` — updates `is-active`/`aria-pressed`, `POST api/dashboard/set_filter` with `{ range: next }` (CSRF header from `window.csrfToken`), then `updateOverTime()` + `updateBacklog()` + `updateKpis()`.
- `setProcessFilter(value)` — `POST api/dashboard/set_filter` with `{ process_name: value }`, then refresh all four. Must remain reachable from the page-level `NexoraProcessPicker` binding, so expose it as `window.setProcessFilter = setProcessFilter;` (that one global is the existing contract with `templates/dashboard.html`'s inline picker init).
- `refreshAll()` + `tick()` — `refreshAll()` runs the four updaters, stamps `#dash-live-time` with `new Date().toLocaleTimeString()` and resets `countdown`; a `setInterval(tick, 1000)` decrements `#dash-countdown` and calls `refreshAll()` at zero. `#dash-refresh` click → `refreshAll()`. This replaces the old two `setInterval`s.
- The `MutationObserver` on `document.documentElement` re-themes `[processedChart, hourlyChart, backlogChart]` on a dark-mode toggle — keep it, add `backlogChart` to the array.

- [ ] **Step 3: Restore the picker binding** — `templates/dashboard.html`'s trailing inline script keeps calling `setProcessFilter(e.target.value)`. Confirm it still works after the shim change (the `defer`ed `dashboard.js` runs before `DOMContentLoaded`, so `window.setProcessFilter` exists by the time the listener can fire).

- [ ] **Step 4: Lint**

Run: `pytest tests/unit/test_static_v_lint.py tests/unit/test_no_inline_event_handlers.py tests/unit/test_display_none_important.py tests/unit/test_template_url_prefix.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add static/js/dashboard.js templates/js/_dashboard_js.html
git commit -m "feat(dashboard): tabs, range control, sparklines and backlog trend behaviour"
```

---

# PHASE 4 — Removal and chores

### Task 12: Delete the Recent Validations feed end-to-end (D6)

**Files:**
- Modify: `nx_lib/views/dashboard.py`, `nx_lib/workitem_sources.py`
- Test: `tests/integration/test_dashboard_routes.py`, `tests/unit/test_workitem_sources.py`, `tests/unit/test_create_app.py`

- [ ] **Step 1: Re-prove nothing else calls it**

Run: `grep -rn "recent_activity" nx_lib templates static tests --include="*.py" --include="*.html" --include="*.js" | grep -v "^tests/"`
Expected: hits only in `nx_lib/views/dashboard.py` (the view + its route registration) and `nx_lib/workitem_sources.py` (`recent_activity_rows` and its log line). If anything else appears, stop and keep the endpoint — D6's premise is that nothing else uses it.

- [ ] **Step 2: Delete the server side** — in `nx_lib/views/dashboard.py` remove the `# --------- recent activity ---------` section (the whole `api_recent_activity` function with its `@require_permission` / `@cache.cached` decorators) and its `app.add_url_rule("/api/dashboard/recent_activity", …)` block in `register_routes`. Then drop the now-unused imports: `get_activity_instances_to_ignore` from `..process_helpers`, `recent_activity_rows` and `get_domain_for_workitem` from `..workitem_sources`, `get_extensions_urls_fields` / `get_workitemdata_param` from `..octo`, and `sensitive_blocked_tokens` / `strip_sensitive_fields` from `.workitems`. **Grep each one in the file before removing its import** — `normalize_process_selection` and `total_backlog_count` are still used, and the `.workitems` helpers may have other callers here.

- [ ] **Step 3: Delete `recent_activity_rows`** from `nx_lib/workitem_sources.py` (the function starting `def recent_activity_rows(pairs, activity_ignore_map, top=3):`).

- [ ] **Step 4: Delete the tests** — remove from `tests/integration/test_dashboard_routes.py`: `test_recent_activity_authed_returns_empty_list`, `test_recent_activity_forwards_row_client_as_hint`, `test_recent_activity_skips_row_when_workitemdata_lookup_fails`, `test_recent_activity_strips_sensitive_fields_without_perm`, `test_recent_activity_rows_include_client_key`, `test_recent_activity_route_derives_granted_pairs_not_cross_product`, plus the `- GET  /api/dashboard/recent_activity …` line from the module docstring's endpoint list. From `tests/unit/test_workitem_sources.py`: `test_recent_activity_rows_and_total_backlog_count_pass_pairs_through` keeps its `total_backlog_count` half — rewrite it to exercise only that, and delete `test_recent_activity_rows_merges_and_caps` outright. From `tests/unit/test_create_app.py`: remove `"api_recent_activity",` from the endpoint inventory.

- [ ] **Step 5: Run the whole fast tier**

Run: `python scripts/test_db_reset.py && pytest tests/unit tests/integration -q`
Expected: PASS, and `views/dashboard.py` still clears its 25 % coverage floor in `test_coverage_thresholds.py`.

- [ ] **Step 6: Commit**

```bash
git add nx_lib/views/dashboard.py nx_lib/workitem_sources.py tests
git commit -m "refactor(dashboard): remove the Recent Validations feed and its endpoint"
```

### Task 13: Translations (de/fr/it)

**Files:**
- Modify: `translations/{de,fr,it}/LC_MESSAGES/messages.po`, `messages.pot`

- [ ] **Step 1: Run the extract→update cycle** — invoke the `nx-i18n` skill, or by hand:

Run: `pybabel extract -F babel.cfg -o messages.pot . && pybabel update -i messages.pot -d translations`

- [ ] **Step 2: Fill the German column from the handoff** — the README's copy is the intended German, so translate rather than invent:

| msgid | de |
|---|---|
| `Refresh` | `Aktualisieren` |
| `Updated` | `Aktualisiert` |
| `next in` | `neu in` |
| `Process` | `Prozess` |
| `d` | `T` |
| `Time range` | `Zeitraum` |
| `Imported today` | `Heute importiert` |
| `Processed today` | `Heute verarbeitet` |
| `Current backlog` | `Aktueller Rückstand` |
| `Avg. processing time` | `Durchschn. Verarbeitungszeit` |
| `vs. yesterday` | `vs. gestern` |
| `Over time` | `Zeitverlauf` |
| `Today by hour` | `Heute nach Stunde` |
| `Documents processed over time` | `Verarbeitete Dokumente im Zeitverlauf` |
| `Documents processed today, by hour` | `Heute verarbeitete Dokumente nach Stunde` |
| `Backlog` | `Rückstand` |
| `Trend` | `Verlauf` |
| `Trend, %(days)s days` | `Verlauf %(days)s Tage` |
| `open` | `offen` |
| `%(delta)s since yesterday` | `%(delta)s seit gestern` |
| `%(days)s days · peak %(peak)s` | `%(days)s Tage · Spitze %(peak)s` |
| `peak %(peak)s at %(hour)s` | `Spitze %(peak)s um %(hour)s` |
| `Other` | `Andere` |
| `last sign-in %(when)s` | `letzte Anmeldung %(when)s` |
| `Could not refresh the dashboard` | `Dashboard konnte nicht aktualisiert werden` |

French and Italian get the same treatment (`Actualiser` / `Aggiorna`, `Arriéré` / `Arretrato`, …). Every msgid must be non-fuzzy in all three or `tests/unit/test_translations.py` fails.

- [ ] **Step 3: Compile and diff-sweep** — `pybabel` silently mangles malformed `msgstr` lines, so read the diff before committing:

Run: `pybabel compile -d translations && git diff --stat translations`
Expected: only the intended additions; no unrelated msgstr churn.

- [ ] **Step 4: Run the translation gate**

Run: `pytest tests/unit/test_translations.py tests/unit/test_i18n.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add messages.pot translations
git commit -m "chore(i18n): translate the dashboard console strings"
```

### Task 14: Browser verification and e2e

**Files:**
- Modify: `tests/e2e/test_dashboard.py`

- [ ] **Step 1: Restart the dev server** (Jinja templates are cached for the process lifetime)

Run: `bin/nx.ps1 -r`
Expected: the server comes back on INT.

- [ ] **Step 2: Drive the page yourself** — `bin/nx.ps1 -u -b --loginas:ben.streich --no-conflict`, then in your own browser on your own port (never the user's Chrome):
  1. `/dashboard` at 1400×900 — screenshot `var/screenshots/dashboard_console_1a.png`.
  2. Click **30 d**, then **90 d** — both charts must redraw and the KPI deltas must survive; screenshot `var/screenshots/dashboard_console_range90.png`.
  3. Click the **Today by hour** tab — the title, meta and canvas swap with no refetch of the over-time series (check the network panel); screenshot `var/screenshots/dashboard_console_hourly.png`.
  4. Narrow to 1000px — the KPI strip must become 2×2 with its hairlines intact; screenshot `var/screenshots/dashboard_console_narrow.png`.
  5. Toggle dark mode from the profile menu — every colour must flip, including the four backlog series; screenshot `var/screenshots/dashboard_console_dark.png`.
  6. Switch the accent to violet on `/appearance` and return — nothing may still be amber except the chart series; screenshot `var/screenshots/dashboard_console_violet.png`.
  7. Console must be free of errors, and no request may 404.

  Kill the browser when done.

- [ ] **Step 3: Add the additive e2e tests** to `tests/e2e/test_dashboard.py` (chrome-level only — TEST has no Statistics DB, so never assert on data):

```python
@pytest.mark.flaky_e2e
def test_dashboard_view_tabs_switch_the_chart_body(nexora_server, page):
    """The hourly chart is a tab on the main chart now, not its own card."""
    _login(page, nexora_server)
    tabs = page.locator('[data-testid="dashboard-view-tabs"]')
    expect(tabs).to_be_visible()
    expect(page.locator("#chart-body-time")).to_be_visible()
    tabs.locator('[data-view="hour"]').click()
    expect(page.locator("#chart-body-hour")).to_be_visible()
    expect(page.locator("#chart-body-time")).to_be_hidden()


@pytest.mark.flaky_e2e
def test_dashboard_range_control_marks_the_picked_window(nexora_server, page):
    _login(page, nexora_server)
    control = page.locator('[data-testid="dashboard-range"]')
    expect(control.locator(".nx-segmented__btn")).to_have_count(3)
    control.locator('[data-range="30"]').click()
    expect(control.locator('[data-range="30"]')).to_have_class(__import__("re").compile("is-active"))


@pytest.mark.flaky_e2e
def test_dashboard_has_no_card_frames_and_no_activity_feed(nexora_server, page):
    """Option 1a is borderless: no nx-card on the page, and the feed is gone."""
    _login(page, nexora_server)
    page.wait_for_load_state("domcontentloaded")
    assert page.locator("main .nx-card").count() == 0
    assert page.locator("#activity-feed").count() == 0
```

- [ ] **Step 4: Run them** (e2e is CI-only in the pre-push gate since v3.2.4.1, but run them locally once; set `NEXORA_E2E_PORT` and check for an orphan TEST `nx_main` first)

Run: `pytest tests/e2e/test_dashboard.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/test_dashboard.py
git commit -m "test(e2e): cover the dashboard console tabs, range control and borderless layout"
```

### Task 15: Changelog, What's New, docs

**Files:**
- Modify: `CHANGELOG.md`, `nx_lib/whats_new.py`, `docs/design/Dashboard_redesign/design_handoff_dashboard_console/README.md`

- [ ] **Step 1: Add the `[Unreleased]` entries** — under `### Added` in `CHANGELOG.md`:

```markdown
- **The Dashboard is a console.** The page loses every card frame: the four
  KPIs are one borderless strip separated by hairlines, each with its
  day-over-day change and a seven-day sparkline; the throughput chart spans
  the full content width with underline tabs (**Over time** / **Today by
  hour** — the separate hourly card is gone); and a new **Backlog** section
  draws a 14/30/90-day trend line per process from the half-hourly
  `dbo.BacklogHistory` snapshots. A 14 d / 30 d / 90 d range control drives
  both charts and sticks for the session. The header carries a live indicator
  with the last refresh time, a countdown to the next one, and a Refresh
  button that forces one now.
- `GET api/dashboard/backlog_trend?range=14|30|90` returns
  `{labels, series:[{name, values, current}], total, prev_total}` — per-process
  backlog history, scoped by the active process filter, capped at four named
  series plus "Other".
```

and under `### Removed`:

```markdown
- **Recent Validations** and `GET api/dashboard/recent_activity`. The feed
  showed three workitems' extracted fields on a page nobody used it from; the
  workitems page is the place to look at workitems.
```

and under `### Changed`:

```markdown
- `api/dashboard/kpi_stats` also returns the previous day's value and a
  seven-point daily series per KPI; `api/dashboard/avg_processing_time` the
  same in minutes. `api/dashboard/processed_over_time` accepts `range`.
```

- [ ] **Step 2: Add one What's New card** — in `nx_lib/whats_new.py`, prepend an entry to the newest release's `entries` list (or open a new release dict if this ships in a new version):

```python
            {
                "title": _("A denser Dashboard"),
                "body": _(
                    "The Dashboard reads like a console now. Each KPI shows how "
                    "it moved since yesterday plus a seven-day sparkline, the "
                    "throughput chart fills the width and holds the hourly view "
                    "as a tab, and a new Backlog section traces the last 14, 30 "
                    "or 90 days per process. The Recent Validations column is "
                    "gone — the workitems page is where workitems live."
                ),
                "perm": "dashboard.view",
                "endpoint": "dashboard",
                "icon": "gauge-high",
            },
```

- [ ] **Step 3: Mark the handoff as implemented** — append to `docs/design/Dashboard_redesign/design_handoff_dashboard_console/README.md`:

```markdown
---

## Implementation status (2026-09-XX)

Implemented per `docs/superpowers/plans/2026-09-04-dashboard-redesign-console.md`.
Deliberate divergences from the text above:

- **Colour.** The prototype's amber `#d97706` is `var(--nx-accent)` in the app, not a
  fixed hue — the app ships indigo by default and amber is one of seven user-selectable
  accents. Only the chart series keep fixed colours, as `--nx-series-1..5`.
- **Copy.** English is the source locale, so every string entered the code in English
  and the German wording above lives in `translations/de/LC_MESSAGES/messages.po`.
- **Range persistence** rides the session (like the process filter), not `ui_prefs.py`.
- **Page title** stays tenant-aware (`<Tenant> Dashboard` / `Global Dashboard`, #255 /
  migration `0097`); only the marketing subtitle was dropped.
- **e2e** work was additive — the pre-existing dashboard e2e never referenced the
  activity feed or the hourly card.
```

- [ ] **Step 4: Run the doc/curation gates**

Run: `pytest tests/unit/test_whats_new.py tests/unit/test_translations.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md nx_lib/whats_new.py docs/design/Dashboard_redesign
git commit -m "docs(dashboard): changelog, What's New card and handoff status for the console redesign"
```

---

## Gotchas & notes

- **The `#chart-meta` peak values** come from the data the JS already holds — do not add an endpoint for them.
- **`processed_over_time` and the "Processed today" KPI count differently** and always have: the KPI (via `compute_today_stats`) counts export-today only among rows whose *import* date is also today, while the chart counts export dates independently. Task 1's `_kpi_daily_counts` deliberately copies the KPI's predicate so the sparkline agrees with the number above it — the main chart's line may sit higher. That is pre-existing behaviour, not a bug introduced here; do not "fix" one to match the other without an owner decision.
- **`normalize_range` is the only sanitizer** for the value that reaches SQL through f-string interpolation. Never widen it to pass arbitrary integers through.
- **The client-name casing between `BacklogHistory` and `ProcessSources` does not match** (`Privera` vs `privera`) — `_backlog_history` casefolds for exactly this reason. Measured on INT 2026-09-04. An exact-match "cleanup" would silently drop five of the six INT processes and leave a chart that still draws.
- **INT's backlog history is synthetic**, seeded 2026-09-04 via `/nx-seed-intdb` because the collector was never scheduled there. Re-seed with `scripts/seed-int-db.py --days 30 --yes` before verifying the 30/90-day ranges — a 14-day seed makes the wider windows look (correctly) half-empty.
- **`BacklogHistory.SnapshotAt` comes back as `str`, not `datetime`** — the legacy `DRIVER={SQL Server}` pyodbc driver again (measured: `'2026-08-22 20:00:00'`). `_backlog_history`'s `datetime.fromisoformat` normalization is load-bearing; without it the day-bucketing raises `AttributeError: 'str' object has no attribute 'date'`.
- **`_backlog_history` filters in Python on purpose.** Do not "optimize" it into an interpolated `IN (…)` pair list — that is exactly the shape `_pair_predicate`'s docstring in `nx_lib/workitem_sources.py` warns about (two independent IN-lists authorize the full cross product instead of only the granted pairs).
- **A dead Statistics DB must render an empty chart, never a 500.** `_default_stat_rows` already swallows and logs; the endpoints return their `empty` payload. Do not add a `strict=True` here.
- **`html.nx-compact`** (density = compact) shrinks `--ctl-h`; check the filter row at compact density before calling the layout done.
- **`nx-rise` and stacking contexts:** the entrance animation uses fill-mode `backwards`, not `both` — a `both` on the KPI strip would bury the scope picker's menu under it.
- **Chart.js theme flip:** the `MutationObserver` re-themes only `options.scales` colours. The backlog series colours are read once at construction, so a dark-mode toggle needs `backlogChart.data.datasets[i].borderColor = seriesColor(i)` inside `applyChartTheme` too, or the four lines keep their light values.
- **First push from this worktree may trip on CRLF.** If `git commit` reports line-ending churn on files you did not touch, that is the known Windows trap — do not "normalize" the repo; commit with an explicit pathspec.
