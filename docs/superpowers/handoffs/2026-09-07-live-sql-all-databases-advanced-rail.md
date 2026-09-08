# Handoff — Advanced back in the rail, Live SQL reaches every reporting database

**Date:** 2026-09-07 · **Branch:** `refactor/255-admin-nav-tenancy-labels` · **118 ahead of
`origin/main`, nothing pushed** · commit-only (remote). **Several other sessions commit on this
same branch and share the git index — read Gotchas before you touch anything.**

**Prior handoff:** [`2026-09-07-dashboard-card-chart-tools.md`](2026-09-07-dashboard-card-chart-tools.md)
(same date — pass this file's path to `/reset-session` explicitly).

## This session's commits

| Commit | What |
|---|---|
| `f1ecd04a` | Advanced nav entry un-parked in the Workspace rail; Live SQL reports *why* a query failed (`err.detail` through `NX.api`); driver rejections → 400/WARNING; Table↔SQL mode switch resets the result area; Advanced filter row fits its column |
| `0775b27d` | third Live SQL target (Generali) with its own RO login + grant + migration `0121`; Target picker names the real database; per-table **Query the first 100 rows** button in the Structure panel; Sources-rail dedupe prefers a reachable source |

Peers landed `228e6951`, `c3c8b785`, `d3e1f060`, `e0bdda2c`, `9719c04c`, `13ab9dfc` in between
(dashboard card chart tools, Present margins, grid row spans, Eddard forecast context).

## TL;DR

1. **Advanced is discoverable again.** The rail entry was parked `hidden` on 2026-08-26; it now
   sits last in the Workspace group. Everything below was found by actually clicking through the
   pane that nobody could reach.
2. **Live SQL says what went wrong.** `NX.api` was building its `Error` from `body.error` and
   throwing `body.detail` away, so every failure read "Could not run query" and nothing else. It
   now carries `err.detail`/`err.status` and Advanced prints it as a second line
   ("Invalid object name 'Workitem'."). Driver rejections are **400 at WARNING**, not 500 at ERROR.
3. **Live SQL covers all three reporting databases** — `SYDOC_Statistik`, `RuntimeDatabase`,
   `Generali` — and the Target picker names the *database*, not a registry label. **NexoraDB is
   deliberately not a target at any permission level** (password hashes + TOTP secrets); a unit
   test pins that.
4. **Owner setup outstanding:** the Generali target answers 503 / shows "not set up yet" until its
   read-only login exists. See *Next steps*.

## What shipped

### `f1ecd04a` — Advanced in the rail + Live SQL error reporting

| File | Change |
|---|---|
| `templates/reporting.html` | `#rcNavAdvanced` loses `hidden` |
| `static/js/nx_core.js` | `api()` keeps `err.detail` + `err.status` off the JSON error body |
| `static/js/reporting_advanced.js` | `showError(msg, detail)` renders the detail line and forces grid view (an error raised from Chart/Pivot used to render into a hidden container); `resetResultArea()` called on a real mode change |
| `nx_lib/views/reporting/run.py` | `pyodbc.ProgrammingError` → 400 + humanized `detail`, logged WARNING; connection/timeout still 500 |
| `static/css/reporting.css` | `.reporting-error-detail`; `.reporting-filter-row` wraps so the field select gets its own row |
| `templates/js/_reporting_js.html` | `builderEmptyTitle/Hint`, `sqlEmptyTitle/Hint` |
| tests | `test_sql_run_driver_rejection_is_400_with_reason` |

### `0775b27d` — every reporting database, named for real

| File | Change |
|---|---|
| `nx_lib/config.py`, `nx_lib/db.py` | `DB_REPORTING_GENERALI_RO_USER/PWD` → `engine_generali_ro` (None ⇒ 503, **never** a fallback to `engine_generali_db`) |
| `nx_lib/reporting/sources.py` | `sql_generali` source; the three SQL labels are now plain fallbacks (`Statistics`, `Octo runtime`, `Generali`) |
| `nx_lib/views/reporting/_shared.py` | `generali` in `_SQL_TARGET_ENGINES` / `_SQL_TARGET_PERMISSION`; new `_SQL_TARGET_DB` (target → `cfg.DB_*` name) |
| `nx_lib/views/reporting/run.py` | `/api/reporting/sources` sql entries gain `db` + `configured` |
| `static/js/reporting_advanced.js` | picker labels from `db`, disables an unconfigured target with "not set up yet", opens on the first configured one; publishes `window.ReportingSqlDbs`; `rc:sqlquery` listener writes `SELECT TOP (100) * FROM [schema].[table]` and runs it |
| `static/js/reporting_schema.js` | per-table **Query the first 100 rows** button (only when `ReportingSqlDbs` says that database is reachable) |
| `templates/js/_reporting_tabs_js.html` | rail dedupe: a *reachable* source wins the per-database card slot |
| `sql/_migrations/NexoraDB/0121_…` | `reporting.sql.target.generali.use` (**applied to INT already**) |
| `scripts/provision-reporting-ro-logins.sql`, `env/*.env.example` ×4 | third login |
| docs | `CLAUDE.md` engine table, `docs/howto/reporting.md` (targets table, picker, Structure query, owner setup), `docs/howto/reporting-guide.md`, `templates/_reporting_help.html`, `CHANGELOG.md` |
| tests | `test_reporting_sql_targets.py`: generali registered + gated, **`test_nexora_is_not_a_target`**, `_SQL_TARGET_DB` covers every target, code registry ↔ gate agreement |

## Next steps (ordered)

1. **Bring the Generali target online** (owner-only, needs SSMS + env access):
   - `scripts/provision-reporting-ro-logins.sql` is already half-filled in the working tree with
     the real DB names (`SYDOC_Statistik`, `RuntimeDatabase`, `Generali`) and blank login/password
     slots. Fill the three login names + passwords, run it in **SQLCMD Mode** against
     `DB_SERVER_PRD`. It is idempotent (re-running rotates passwords).
   - Put `DB_REPORTING_GENERALI_RO_USER` / `_PWD` into `env/INT.env` **and**
     `\\syapp01\d$\sydoc\nexora\env\PROD.env` — the env files are gitignored, so the `.example`
     keys change nothing on the server by themselves. `python scripts/env-sync.py` prints what is
     missing where.
   - Restart nexora; the picker should show `Generali` enabled instead of "not set up yet".
2. **Push the branch and open the PR** — 118 commits, none pushed (remote/commit-only rule).
   Migration `0121` applies to PROD automatically on push to `main` via `deploy.yml`, *before* the
   app pool stops.
3. Optional, only if someone hits it: the per-table quick query uses `SELECT *`, which on a
   blob-bearing table (`t_DocumentMedia`: 100 rows = **58 MB**, 8.2 s on INT) is slow, and on a
   genuinely huge table it hits the 30 s sandbox timeout. The owner looked at this and called it
   expected ("it's actually just a huge table"), so it was **left as `*` on purpose**. If it
   becomes annoying, the fix is small: `reporting_schema.js` already knows every column's type, so
   have the button list the non-LOB columns instead of `*`.

## Gotchas & notes

- **A peer's `pre-commit` run stashes your *unstaged* edits repo-wide.** A dev server started or
  restarted inside that window imports the HEAD version of your files and keeps serving it after
  the stash is restored. This cost ~30 minutes here: `grep` showed the edit on disk, `__pycache__`
  looked fresh, and `/api/reporting/sources` kept returning the old payload through **three**
  restarts. The tell is file mtimes moving forward on their own, later than the server's start
  time. **`git add` your work before restarting a server while a peer is committing.**
- **…but staging then exposes you to their next broad `git add`.** `e0bdda2c` (a peer's commit)
  swallowed a `static/css/reporting.css` hunk of mine — the `min-width: 0` on
  `.reporting-fields/.reporting-results/.reporting-wells` that stops a wide result stretching the
  whole builder past the window. It is in HEAD either way; `0775b27d`'s message records the split
  so the CHANGELOG entry and the code don't read as inconsistent. **Pathspec commits are the only
  real protection on contested files.**
- The prior handoff notes "the shared tree does not import right now (`nx_lib.db` lacks
  `engine_generali_ro`)" — that was this session mid-change. **Resolved:** `0775b27d` landed it.
- `nx --down-all` stops **every** nexora on the machine, including port 8000 and peers'. Use
  `nx -d --port:<n>`. Restart a `--no-conflict` instance with `nx -r --port:<n>` (`--port` is
  rejected *together with* `--no-conflict`).
- The `sql-sync-check` hook failed once early on with pre-existing INT-vs-repo object drift that
  belonged to neither branch (it "organized" 49 NexoraDB + 28 GeneraliDB objects). `f1ecd04a` was
  committed with `SQL_SYNC_SKIP=1` and a note in the message; later commits passed the hook clean.
- The `mypy` hook can die with `AssertionError: Cannot find pyparsing.warnings.…` — a corrupt
  incremental cache, not your code. `rm -rf .mypy_cache` and re-commit (the first run after that
  reports "files were modified by this hook" because it rebuilt the cache; the next one passes).
- gitlint caps the subject at **72 chars** — "…every reporting database, named for real" was 73
  and got rejected.
- Nothing is red. `tests/unit` 1645 passed; `tests/integration/test_reporting_routes.py` +
  `test_reporting_metrics_routes.py` 94 passed. The 12 reporting-route failures seen at the start
  of the session were a stale `NEXORA_TEST` — fixed by `python scripts/test_db_reset.py`.

## Untracked / left for owner

Deliberately **not** committed:

- `scripts/provision-reporting-ro-logins.sql` — the owner's half-filled local copy (real DB names
  in, credential slots blank). The script's own header says never to commit a filled-in copy. The
  committed version has placeholders.
- `CHANGELOG.md` — a peer's unstaged bullet.
- `docs/nexora-architecture.drawio`, `docs/nx-architecture.drawio`, `docs/architecture/`,
  `docs/.$*.drawio.bkp` — the owner's diagram work.

## How to verify

```powershell
# unit + the reporting integration suites (reset TEST first if routes fail oddly)
python scripts/test_db_reset.py
python -m pytest tests/unit -q --no-cov
python -m pytest tests/integration/test_reporting_routes.py tests/integration/test_reporting_metrics_routes.py -q --no-cov

# the new target registry specifically
python -m pytest tests/unit/test_reporting_sql_targets.py -q --no-cov

# in the app (own port, never the owner's 8000)
bin\nx.ps1 -u --no-conflict          # note the port it prints
bin\nx.ps1 -d --port:<n>             # ...and stop only that one afterwards
```

Then, logged in at `/reporting?tab=advanced`: **Advanced** is in the rail; the **SQL** tab's Target
picker reads `Generali — not set up yet [disabled]` / `RuntimeDatabase` / `SYDOC_Statistik`; a bad
table name shows the driver reason under "Could not run query"; switching Table↔SQL clears the
result area; clicking a Sources card → expanding a table → **Query the first 100 rows** returns
100 rows on the right target.

Screenshots (sent to the owner): `var/screenshots/adv-fix-0{1..4}-*.png`,
`sql-01-structure-query-btn.png`, `sql-03-one-click-fixed.png`.

## Resuming in a fresh session

Point the next session at **this file** — several handoffs share 2026-09-07, so
`/reset-session docs/superpowers/handoffs/2026-09-07-live-sql-all-databases-advanced-rail.md`
targets it explicitly. Everything for this thread of work is committed; the only open item that
needs a human is step 1 of *Next steps* (the Generali read-only login), then the push.
