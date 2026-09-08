---
description: Seed the INT databases with plausible synthetic data for tables nexora only reads (collector-owned tables that are empty or stale on INT)
argument-hint: "[backlog-history] [--days N]"
---

Fill a read-only INT table with plausible synthetic data so a feature that consumes it can actually be verified. Arguments: `$1` = seeder name (default `backlog-history`), plus an optional `--days N`.

**Why this exists.** Some tables are written in production by collectors that live outside the repo and run on Task Scheduler — nexora only ever `SELECT`s from them. On INT those collectors are often unscheduled, so the table is empty or months stale and you cannot tell a broken query from an empty table. Screenshotting an empty chart proves nothing.

Steps:

1. **Dry run first, always.** `ENVIRONMENT=INT .venv/Scripts/python.exe scripts/seed-int-db.py --what $1 --days <N>` prints the target server/database and the exact rows it would write, and writes nothing. Read it. Confirm the server is the INT one.
2. **Apply** by adding `--yes`. Each seeder is idempotent — it deletes the window it is about to write, so re-running replaces rather than stacks. Add `--seed <int>` for a reproducible random walk.
3. **Verify against the app, not the script's own output.** Restart if templates changed (`bin/nx.ps1 -r`), then hit the endpoint that reads the table and look at the numbers — e.g. `curl -s "http://127.0.0.1:8000/api/dashboard/backlog_trend?range=14"` with a logged-in cookie, or drive the page in a browser.
4. **`scripts/seed-int-db.py --list`** shows the available seeders.

**Guards you must not weaken.** The script refuses to run unless `ENVIRONMENT=INT` *and* the resolved SQL server does not contain `prd`/`prod`. The check is on the resolved **value**, never the variable name: `DB_SERVER_PRD` is called that in every environment file but holds `INTSQL01` on INT. The real collectors own these tables in production — never point this at PROD, and never add a `--force` that skips the environment check.

**Adding a seeder.** Write a `seed_<thing>(days, apply_it)` function in `scripts/seed-int-db.py` and add one entry to the `SEEDERS` dict. It must: print what it will write before writing, do nothing at all when `apply_it` is false, delete its own window before inserting, and preserve the source system's exact spelling of any identifier (see `seed_backlog_history`'s note on Octo's display-cased `ClientName` versus `dbo.ProcessSources`' lower-cased names — seeding the "tidier" spelling would paper over a real mismatch the readers have to handle).

`scripts/` is already in `deploy.yml`'s `/XD` exclude list, so nothing here reaches production.
