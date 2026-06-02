# Handoff — Reporting (BI) Phase 3 complete (Octopus target · load UI · charts + pivot)

- **Date:** 2026-06-02
- **Branch:** `feature/2.5.63` (committed locally, **NOT pushed** — remote session, commit-only)
- **HEAD:** `e3fa874` — **45 commits ahead of `origin/main`**, 22 ahead of `origin/feature/2.5.63`
- **Phase 2 handoff:** `docs/superpowers/handoffs/2026-06-02-reporting-phase2-complete-handoff.md`

## TL;DR

**Phase 3 of the Reporting page is done, tested, and browser-verified on INT.**
Four follow-ups from the Phase 2 handoff were built end-to-end on `feature/2.5.63`
(which now carries phases 1 + 2 + 3): a **2nd live-SQL target (Octopus)**, a
**saved-report load/rename/delete UI**, **chart + drag-and-drop pivot** result
views, and the small **503-log-line** polish. Backend suite green (**612 passed,
24 skipped**), 2 new Playwright e2e pass, and all three front-end features were
driven live on INT (4 screenshots in `var/screenshots/reporting_p3_*`). Nothing
is pushed — **you push + open the PR**. **Two owner actions** remain: provision
the Statistics **and** Octopus read-only SQL logins (see §Owner actions).

## What shipped (Phase 3)

1. **Octopus as a 2nd live-SQL target.** The SQL tab's **Target** dropdown now
   lists every target the caller may reach. Octopus is gated by a new,
   independently grantable **`reporting.sql.target.octopus`** permission
   (migration `0008`, seeded to `admin.view` profiles) on top of the base
   `reporting.sql.run`. Runs on its own dedicated `db_datareader`-only login
   (`engine_octo_ro` over OctoDB); `None` until provisioned → graceful 503.
2. **Saved-report load UI.** A "Saved reports" dropdown on the toolbar with
   **Load / Rename / Delete** (wired to the pre-existing list/get/update/delete
   endpoints). Load restores a curated definition into the builder or a SQL
   definition into the SQL editor, switching mode by the saved `kind`.
3. **Chart + pivot result views.** A **Grid / Chart / Pivot** toggle appears
   after a run and re-visualizes the current result set (curated *or* SQL) in
   place. Chart = Chart.js bar/line/pie/doughnut. Pivot = a vanilla HTML5
   drag-and-drop multi-dimension matrix (Rows/Columns/Values, per-measure
   sum/avg/count/min/max, row + grand totals).
4. **Polish.** The unconfigured-RO-engine 503 path now logs a warning instead of
   raising silently (Phase 2 gotcha #2). *(Rode in with commit `e527c9d` because
   it shares `reporting.py` with the Octopus change and patch-level staging
   wasn't available in this session.)*

## Architecture / file map (Phase 3)

```
nx_lib/config.py                 + DB_REPORTING_OCTO_RO_USER / _PWD
nx_lib/db.py                     get_ro_db_url(uid,pwd) generalized; + engine_octo_ro (None until set)
nx_lib/reporting/sources.py      + sql_octopus source (perm reporting.sql.target.octopus)
nx_lib/views/reporting.py        + engine_octo_ro import, _SQL_TARGET_ENGINES/_SQL_TARGET_PERMISSION,
                                 + _authorize_sql_target() (sql/run + export); 503 log line
templates/reporting.html         Chart.js script; Saved-reports toolbar group; Grid/Chart/Pivot toggle;
                                 #rpChart/#rpPivot containers; include _reporting_viz_js.html; agnostic modal text
templates/js/_reporting_js.html  multi-target loadSources; load/rename/delete; resetViews/setView; lastResult
templates/js/_reporting_viz_js.html  NEW — window.ReportingViz: mountChart (Chart.js) + mountPivot (DnD matrix)
static/css/reporting.css         saved-reports group; view toggle; chart container; pivot shelf/chips/matrix
sql/_migrations/NexoraDB/0008_seed_reporting_sql_octopus_permission.sql  (applied to INT)
sql/test/{schema,seed}.sql       + dbo.Reports table; + reporting.sql.target.octopus
env/*.env.example                + DB_REPORTING_OCTO_RO_USER / _PWD (all 4)
tests/unit/test_reporting_sql_targets.py     NEW — per-target auth
tests/unit/test_reporting_schema.py          + octopus-target-allowed test
tests/integration/test_reporting_routes.py   + octopus no-perm 403
tests/e2e/test_reporting_load.py             NEW — saved-report load round-trip
tests/e2e/test_reporting_viz.py              NEW — chart + pivot via ReportingViz
CHANGELOG.md, docs/howto/reporting.md, CLAUDE.md, translations/{de,fr,it}, messages.pot
```

## Key decisions (locked with the owner up front)

- **Octopus access = separate permission** `reporting.sql.target.octopus`
  (Octopus is the runtime DB → gate it independently from Statistics).
- **Full interactive pivot** (drag-and-drop multi-dimension) **+ charts**, the
  most ambitious viz option. Built vanilla (no jQuery/pivottable) to match the
  house style; charts reuse **Chart.js** (already the dashboard's lib).
- **Stack on `feature/2.5.63`** (one PR carries phases 1+2+3).
- Octopus RO env vars named **`DB_REPORTING_OCTO_RO_USER` / `_PWD`** (mirrors the
  Statistics `DB_REPORTING_RO_*` pattern; owner had no preference).

## Gotchas & notes (read before resuming)

1. **INT has no live-data path right now** for verifying reporting end-to-end:
   the curated run 500s because INT's Statistics DB is missing a process table
   (`dbo.PriveraPosteingang`) — a **pre-existing INT data gap, unrelated to this
   work** (`api_run`/`_execute`, untouched) — and the RO SQL logins aren't
   provisioned (503). The phase-3 screenshots therefore used representative
   **sample data injected client-side** (a stubbed `/api/reporting/run`) driven
   through the *real* Grid/Chart/Pivot wiring. The pivot math was verified
   (Acme Invoice 1700.50, grand total 7640.75).
2. **Two RO logins now.** Statistics (`DB_REPORTING_RO_*`) and Octopus
   (`DB_REPORTING_OCTO_RO_*`) are independent — each target stays 503 until its
   own login is set.
3. **Save still creates a new report.** Loading a report then editing + Save
   makes a copy; updating a loaded report's body in place is a noted follow-up
   (the PUT endpoint already exists; Rename uses it for name-only changes).
4. **Pivot column headers are a single composite line** (`colKey · measure
   (agg)`). The dimensionality is real (multi-field Rows/Columns nest); only the
   *header rendering* is flattened. Multi-level `thead` is a cosmetic follow-up.
5. **Chart.js is loaded unversioned from jsdelivr without SRI** — matches
   `dashboard.html` and the page's other CDN tags. A repo-wide "pin + SRI all
   CDN assets" pass is a worthwhile separate follow-up (an advisory hook flags it).
6. **Migration `0008` is already applied to INT** (by the commit's pre-commit
   hook). The deploy workflow applies pending migrations to PROD before the code
   mirror, so merging creates the permission on PROD.
7. App-wide Python `gettext` i18n is still English-only (Phase 2 gotcha #6,
   `babel.cfg` non-recursive) — out of scope. The new **template/JS** strings
   (the user-facing bulk) ARE translated to de/fr/it.

## How to verify / run

```bash
# Backend suite: expect 612 passed, 24 skipped
python -m pytest tests/unit tests/integration -q

# New phase-3 e2e (reseed TEST first): 2 passed
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_load.py tests/e2e/test_reporting_viz.py \
  -o addopts="" -p no:cacheprovider -q

# Manual on INT: nx -u, /dev/login/<admin>, /reporting — Saved-reports dropdown,
#   SQL tab shows Statistics + Octopus targets, Grid/Chart/Pivot toggle after a run.
```

## Owner actions (before the SQL targets return data)

1. **Provision BOTH read-only SQL logins** (`db_datareader` only), set in
   `env/INT.env` and `env/PROD.env`, then restart nexora:
   - Statistics → `DB_REPORTING_RO_USER` / `DB_REPORTING_RO_PWD`
   - Octopus    → `DB_REPORTING_OCTO_RO_USER` / `DB_REPORTING_OCTO_RO_PWD`
2. **Push `feature/2.5.63` and open the PR `→ main`** (bundles phases 1+2+3).
   Migrations `0004`–`0008` auto-apply to PROD before the code mirror.
3. (Pre-existing) Fix INT Statistics' missing process table(s) if you want the
   curated source to return data on INT — independent of this work.

## Next up — the untouched backlog (do this next)

There is **no fixed phase roadmap**: phases 1–3 cleared everything that was
specced plus every follow-up the Phase-2 handoff had noted. What remains is the
backlog below — **this is the next thing to do.** Each is independent; pick and
brainstorm/plan one (or a coherent group) as its own cycle.

**A. Deferred capabilities (from the Phase-1 spec §3 "Non-goals", still open):**

1. **Scheduled / emailed reports** — run a saved report on a schedule and email
   the Excel output. (Largest; needs a scheduler + Graph mail + storage.)
2. **Cross-user sharing & a shared report library** — today `dbo.Reports` is
   per-owner (`OwnerUserID`); add sharing/visibility + a browse UI.
3. **DB-backed source-registration UI** — the source registry is code-defined in
   `nx_lib/reporting/sources.py`; move it to a table + admin UI.
4. **CSV export** — currently Excel-only (`openpyxl`); add a CSV download path.
5. **Generali sources** — curated reporting sources over the Generali DB.
6. **Workitems / Octopus as a *curated* source** — Octopus is reachable only via
   live SQL today; add a curated catalog + query builder for it (and Workitems).

**B. Smaller follow-ups / polish:**

7. **Update-a-loaded-report-in-place** — Save always creates a new report; when
   one is loaded, offer overwrite (the PUT endpoint already exists).
8. **Multi-level pivot column headers** — the pivot column header is a single
   composite line today; render a proper nested `thead` for multi-field Columns.
9. **Pivot / chart export** — export the pivot matrix or chart image (export
   currently uses the flat grid rows only).
10. **Repo-wide CDN pin + SRI** — pin versions and add Subresource Integrity to
    the jsdelivr/cdnjs `<script>`/`<link>` tags (Chart.js, flatpickr,
    font-awesome, …) across the templates.
11. **App-wide Python `gettext` i18n** — `babel.cfg` uses non-recursive
    `[python: *.py]`, so `nx_lib/**` route messages aren't extracted and fall
    back to English for de/fr/it (pre-existing, app-wide; not reporting-only).

## Phase-3 commits (oldest → newest)

```
e527c9d feat(reporting): add Octopus as a 2nd live-SQL target (+ 503 log polish)
fb5b83c feat(reporting): add a saved-report load/rename/delete UI
27ee064 feat(reporting): add chart + drag-and-drop pivot result views
e3fa874 docs(reporting): document phase-3 + translate new strings
```

## Resuming in a fresh session

Point the new session at this handoff. The branch is the source of truth (local,
unpushed). Next concrete steps are the owner pushing + opening the PR and
provisioning the two RO logins. **The next build work is the backlog in
§"Next up — the untouched backlog"** — brainstorm/plan one item (or a coherent
group) as its own cycle.
