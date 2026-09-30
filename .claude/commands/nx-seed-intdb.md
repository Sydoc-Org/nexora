---
description: Seed the INT databases with plausible synthetic data for tables nexora only reads (collector-owned tables that are empty or stale on INT)
argument-hint: "[backlog-history] [--days N] [--clear]"
---

Fill a read-only INT table with plausible synthetic data so a feature that consumes it can actually be verified, or delete exactly the rows an earlier seed wrote. Arguments: `$1` = seeder name (default `backlog-history`), plus an optional `--days N`, or `--clear`.

**Why this exists.** Some tables are written in production by collectors that live outside the repo and run on Task Scheduler — nexora only ever `SELECT`s from them. On INT those collectors are often unscheduled, so the table is empty or months stale and you cannot tell a broken query from an empty table. Screenshotting an empty chart proves nothing.

**Two front-ends, one module.** The logic lives in `nx_lib/seed.py`. The CLI is `scripts/seed-int-db.py`; the admin overview (`/admin`, INT only, permission `admin.seed.manage`) has *Seed INT data* and *Clear seed* buttons over the same module (`nx_lib/views/admin/seed.py`, `/api/admin/seed` GET/POST/DELETE). Every seed run records the keys of the rows it wrote in `dbo.SeedRuns` (NexoraDB, migration 0141); clearing deletes those rows and nothing else, and re-seeding replaces the seeder's own earlier rows without touching real collector rows.

Steps:

1. **Dry run first, always.** `ENVIRONMENT=INT .venv/Scripts/python.exe scripts/seed-int-db.py --what $1 --days <N>` prints the target server/database and the exact rows it would write, and writes nothing. Read it. Confirm the server is the INT one.
2. **Apply** by adding `--yes`. Add `--seed <int>` for a reproducible random walk.
3. **Clear** with `scripts/seed-int-db.py --clear` (dry run lists the tracked runs) then `--clear --yes`. Rows seeded by the pre-0141 CLI are not tracked and must be cleaned once by hand.
4. **Verify against the app, not the script's own output.** Restart if templates changed (`bin/nx.ps1 -r`), then hit the endpoint that reads the table and look at the numbers — e.g. `curl -s "http://127.0.0.1:8000/api/dashboard/backlog_trend?range=14"` with a logged-in cookie, or drive the page in a browser.
5. **`scripts/seed-int-db.py --list`** shows the available seeders and the tracked runs.

**Guards you must not weaken.** `seed_refusal()` refuses to run unless `ENVIRONMENT=INT` *and* the resolved SQL server does not contain `prd`/`prod`. The check is on the resolved **value**, never the variable name: `DB_SERVER_PRD` is called that in every environment file but holds `INTSQL01` on INT. The admin routes additionally 404 outside INT, so STAGING and PROD neither show nor serve them. The real collectors own these tables in production — never point this at PROD, and never add a `--force` that skips the environment check.

**Adding a seeder.** In `nx_lib/seed.py` write a `plan_<thing>(days, rng, report)` that fills `report.rows` (one dict per row, every column that identifies the row) and `report.summary`, a `write_<thing>(rows)` and a `delete_<thing>(rows)` whose WHERE matches **every** written column, then add a `Seeder(...)` entry to `SEEDERS`. Plan must write nothing; preserve the source system's exact spelling of any identifier (see `plan_backlog_history`'s note on Octo's display-cased `ClientName` versus `dbo.ProcessSources`' lower-cased names — seeding the "tidier" spelling would paper over a real mismatch the readers have to handle).

`scripts/` is already in `deploy.yml`'s `/XD` exclude list, so the CLI never reaches production; the module and routes do, but are inert there.
