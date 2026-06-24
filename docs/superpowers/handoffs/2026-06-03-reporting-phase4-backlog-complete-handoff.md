# Handoff — Reporting (BI) Phase 4: the entire backlog, cleared

- **Date:** 2026-06-03
- **Branch:** `feature/2.5.63` (committed locally, **NOT pushed** — remote session, commit-only)
- **HEAD:** `90fa8d4` — **54 commits ahead of `origin/main`**
- **Phase 3 handoff:** `docs/superpowers/handoffs/2026-06-02-reporting-phase3-complete-handoff.md`

## TL;DR

**Every item in the Phase-3 "Next up" backlog is done, tested, and committed**
on `feature/2.5.63`. That backlog was all of A1–A6 and B7–B11 — 11 items —
delivered as **7 feature commits** (`b81f5e2` → `90fa8d4`). The generic,
whitelist-safe `table` source provider built for A3 turned A5/A6 into seed data,
and a session-independent runner makes A1's scheduled delivery reuse the exact
same query path as the web UI. Backend suite green, new e2e green, and every
front-end feature was driven live on the TEST server (screenshots under
`var/screenshots/reporting_*`). **Nothing is pushed — you push + open the PR.**
Owner actions below (the two RO SQL logins from Phase 3 are still pending, plus a
Task-Scheduler task for A1, and a column review for the seeded Generali/Octopus
sources).

## What shipped (Phase 4) — backlog item → commit

| Backlog | Item | Commit |
|---|---|---|
| B7, B8, A4, B9 | Save-in-place, **CSV export**, view-aware export (pivot→sheet, chart→PNG), **nested pivot headers** | `b81f5e2` |
| A2 | **Cross-user sharing** + shared library (`Visibility` + `ReportShares`) | `e62c594` |
| A3 | **DB-backed source registry** + admin page + generic `table` provider | `6fe9a8e` |
| A5, A6 | **Generali PDQM** + **Workitems (Octopus)** curated sources (seed) | `94dab89` |
| A1 | **Scheduled / emailed reports** (runner + Graph mail + Task Scheduler) | `b27cb37` |
| B11 | **App-wide Python gettext** extraction + ~150 strings translated | `d6cc55d` |
| B10 | **CDN pin + Subresource Integrity** across all templates | `90fa8d4` |

### Detail

1. **B7/B8/A4/B9 — builder polish + export (`b81f5e2`).** Save overwrites a
   loaded report in place (PUT); new **Save as** forks. **CSV export** (UTF-8
   BOM, formula-guarded) via an Excel/CSV selector. Export is **view-aware**:
   grid→rows, pivot→the computed matrix (new `POST /api/reporting/export/grid`),
   chart→PNG. Pivot **Columns** render a proper multi-level nested `<thead>`.
   Also fixed `sql/test/schema.sql` so the TEST reset is idempotent again (Phase
   3 added `dbo.Reports` with an FK to `Users` but never dropped it first).
2. **A2 — sharing (`e62c594`).** Migration `0009`: `Reports.Visibility`
   (`private`/`shared`) + `ReportShares` (per-user, optional `CanEdit`, FK
   `ON DELETE CASCADE`). CRUD is sharing-aware; owner-only share endpoints; the
   Saved-reports dropdown groups **My reports** / **Shared with me**; a Share
   dialog manages visibility + people. In-place Save honours edit rights.
3. **A3 — source registry (`6fe9a8e`).** Migration `0010`: `dbo.ReportingSources`
   + `reporting.admin.sources`. Code defaults are overlaid with DB rows
   (`merge_sources`); curated sources bind to a **provider**: `docprocessing`
   (built-in) or a new generic **`table`** provider
   (`nx_lib/reporting/table_query.py`) that builds a whitelist-validated,
   fully-parameterized `SELECT` over a registered `BaseObject`/`Engine`. Admin
   page `/reporting/sources`.
4. **A5/A6 — curated sources (`94dab89`).** Migration `0011` seeds two
   `table`-provider sources from the live INT schema — **Generali PDQM**
   (`dbo.PDQMReport`) and **Workitems** (`dbo.t_Documents`) — each gated by its
   own permission. Columns are admin-tunable at `/reporting/sources`. The
   `table` provider applies **no** process row-scoping, so the source permission
   is the whole gate (documented).
5. **A1 — scheduled reports (`b27cb37`).** Migration `0012`: `dbo.ReportSchedules`
   + `reporting.schedule`. A Schedule dialog (daily/weekly/monthly, UTC time,
   recipients, xlsx/csv) + owner-only CRUD. `ops/run_scheduled_reports.py`
   (ships to the server) processes due schedules, runs each **as its owner** via
   `nx_lib/reporting/runner.py` (session-independent; reuses the web builders),
   and mails the file via `nx_lib/mail.py` (Graph `/me/sendMail`). `--dry-run`
   for smoke tests.
6. **B11 — i18n extraction (`d6cc55d`).** `babel.cfg` only extracted root `*.py`,
   so all `nx_lib/**` route/flash messages fell back to English. Now recursive
   over `nx_lib/**.py`; the ~150 newly-surfaced messages are translated to
   de/fr/it and `test_translations.py` enforces full coverage.
7. **B10 — CDN pin + SRI (`90fa8d4`).** All jsdelivr/cdnjs `<script>`/`<link>`
   tags pinned to explicit versions with `integrity` + `crossorigin` (88 tags,
   34 templates). Hashes are from the immutable pinned bytes (no behaviour
   change). Google Fonts CSS is intentionally left without SRI.

## Architecture additions (Phase 4)

```
nx_lib/reporting/table_query.py   NEW — generic whitelist-safe single-object provider
nx_lib/reporting/runner.py        NEW — session-independent execute_definition(...)
nx_lib/reporting/schedule.py      NEW — compute_next_run / validate / parse_recipients
nx_lib/mail.py                    NEW — Graph sendMail (ROPC) with attachments
ops/run_scheduled_reports.py      NEW — Task-Scheduler runner (--once/--dry-run)
nx_lib/reporting/sources.py       + merge_sources / code_sources / accessible (provider key)
nx_lib/views/reporting.py         + export/grid, sharing, schedules, admin-sources endpoints;
                                  provider-dispatching _prepare_run/_execute
templates/reporting_sources.html  NEW — source-registry admin page (+ _reporting_sources_js)
sql/_migrations/NexoraDB/0009..0012  sharing, source registry, seed sources, schedules
```

## Owner actions (before everything is live on PROD)

1. **Push `feature/2.5.63` and open the PR `→ main`.** Migrations `0004`–`0012`
   auto-apply to PROD before the code mirror (`.github/workflows/deploy.yml`).
2. **(Carried from Phase 3) Provision the two read-only SQL logins** and set them
   in `env/PROD.env`, then restart nexora — until then the live-SQL targets 503:
   - Statistics → `DB_REPORTING_RO_USER` / `DB_REPORTING_RO_PWD`
   - Octopus    → `DB_REPORTING_OCTO_RO_USER` / `DB_REPORTING_OCTO_RO_PWD`
3. **Scheduled reports (A1):** create a Windows Task Scheduler task on the app
   server that runs, e.g. every 15 min:
   `D:\sydoc\tools\py\python.exe D:\sydoc\nexora\ops\run_scheduled_reports.py --once`
   with `ENVIRONMENT=PROD`. Run once with `--dry-run` first. Graph mail uses the
   existing `GRAPH_*` creds. Grant `reporting.schedule` to whoever may schedule.
4. **Review the seeded curated sources' columns/permissions** at
   `/reporting/sources` — the Generali/Octopus column sets came from the INT
   schema and the `table` provider has no row-scoping, so grant
   `reporting.source.generali.pdqm` / `reporting.source.workitems` deliberately.

## Gotchas & notes

1. **The two RO logins are still unprovisioned**, so the live-SQL sandbox and any
   SQL-kind scheduled report 503 until set (Phase-3 carryover, item 2 above).
2. **`table`-provider sources have no process row-scoping** — the source
   permission is the entire gate. The seeded Generali/Octopus sources are
   admin-only by default. (`docprocessing` keeps its `reporting.scope.process.*`
   scoping.)
3. **Scheduled SQL reports** run against the **RO** SQL engines (audited); curated
   schedules run against the source's engine. A schedule whose report the owner
   can no longer access fails that one schedule and the runner continues.
4. **GitNexus MCP was not connected** this session, so the CLAUDE.md
   "impact analysis before editing" step was done by hand; edits were localized
   to the reporting module + new files.
5. **B10 left Google Fonts without SRI** on purpose (UA-dependent stylesheet).
6. App-wide **template/JS + Python** strings are now all translated (B11). New
   reporting strings are de/fr/it too.

## How to verify / run

```bash
# Backend suite (unit + integration)
python -m pytest tests/unit tests/integration -q

# Phase-4 e2e (reseed TEST first)
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_save.py tests/e2e/test_reporting_share.py \
  tests/e2e/test_reporting_sources.py tests/e2e/test_reporting_curated.py \
  tests/e2e/test_reporting_schedule.py tests/e2e/test_reporting_viz.py \
  -o addopts="" -p no:cacheprovider -q

# Scheduled-report runner smoke (no mail sent)
ENVIRONMENT=INT python ops/run_scheduled_reports.py --dry-run
```

## Next up — the backlog is empty

The Phase-1 spec's "Non-goals" and every Phase-2/3 follow-up are now delivered.
Genuinely-open, smaller follow-ups noticed along the way (none blocking):

- **Multi-level pivot `thead` for the *export*** — the on-screen pivot headers
  are nested; the flat export still uses single-line composite headers.
- **Update a *loaded shared* report's schedule list** is owner-only by design;
  edit-grant holders can edit the body but not schedules.
- **Per-schedule "last run" / error surfacing in the UI** — `LastRunAt` is stored
  and shown, but runner failures are only in the app log today.
- **CDN SRI for Google Fonts** — intentionally skipped; revisit if self-hosting
  fonts.

## Resuming in a fresh session

Point the new session at this handoff. The branch is the source of truth (local,
unpushed). The next concrete steps are the **owner actions** above (push + PR,
provision the RO logins, wire the Task Scheduler task). `CHANGELOG.md` keeps these
under `[Unreleased]` — promote to a dated `[2.5.63]` section when the version
ships.
