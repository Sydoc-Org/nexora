# Handoff — Reporting: AI cost cap, JSON-serialize fix, RO-login rotation + Phase 2 plan

- **Date:** 2026-06-03
- **Branch:** `feature/2.5.63`. Git mode this session was **commit-only (remote)** —
  **nothing pushed**. The branch is **4 commits ahead of `origin/feature/2.5.63`**
  (5 once this handoff commit lands). The owner pushes + opens the PR.
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-03-reporting-ai-enabled-int-live-verified-handoff.md`
- **Phase 2 plan (new this session):** `docs/superpowers/plans/2026-06-03-reporting-ai-phase2.md`

## Feature commits (this session, all local/unpushed)

```
81ca59c fix(reporting): RO-login script rotates password on re-run
ea7990d fix(reporting): JSON-serialize binary/time result cells (500 on run)
d12f4d3 docs(reporting): Phase 2 "Build a report" implementation plan
803cac4 feat(reporting): AI daily cost cap + RO-login provisioning script
```
(+ this handoff commit on top — the latest hash.)

## TL;DR

- Started from "Reporting AI is live on INT" and worked the **operational backlog** +
  a couple of real bugs found while doing it.
- **Shipped (code):** a per-user/day **AI cost cap** (`AI_DAILY_LIMIT`), a **RO-login
  provisioning script**, a fix for a **500 when a query returns binary/time cells**, and a
  fix so the provisioning script **rotates** an existing login's password on re-run.
- **Shipped (plan):** a complete TDD implementation plan for **Reporting AI Phase 2**
  (Surface A: NL → report-definition → builder auto-fill). Not implemented yet.
- **Live op state:** the owner provisioned + rotated the RO logins, but the **INT RO login
  currently fails auth (18456)** because the *old* script didn't rotate the server password
  on re-run. **One `ALTER LOGIN` unblocks it** (see Owner actions #1). The JSON fix is proven
  by tests but **not yet live-verified** (blocked behind that login issue).

## What shipped

| File(s) | Change | Commit |
|---|---|---|
| `nx_lib/views/reporting.py` + `tests/integration/test_reporting_ai_routes.py` | `AI_DAILY_LIMIT` cap: `_ai_daily_limit`/`_ai_asks_today`; `/api/reporting/ai/ask` returns **429 before any provider call** when the cap is hit, audited `Status='blocked'`. `0`=unlimited. 3 tests. | `803cac4` |
| `scripts/provision-reporting-ro-logins.sql` | NEW idempotent SQLCMD one-shot creating the two `db_datareader` RO logins. **Lives under `scripts/`** (already deploy-`/XD`-excluded). | `803cac4` |
| `env/{INT,PROD,STAGING,TEST}.env.example`, `CHANGELOG.md`, `CLAUDE.md`, `docs/howto/reporting.md`, `messages.pot`, `translations/{de,fr,it}/…` | `AI_DAILY_LIMIT` documented + de/fr/it for the new 429 string. | `803cac4` |
| `docs/superpowers/plans/2026-06-03-reporting-ai-phase2.md` | NEW Phase-2 plan (Surface A, no new perm/table/migration; gated `reporting.ai.use` only; self-validate + 1 retry). | `d12f4d3` |
| `nx_lib/views/reporting.py` (`_json_safe`/`_rows_json_safe`) + `tests/unit/test_reporting_json_safe.py` + `tests/integration/test_reporting_routes.py` + `CHANGELOG.md` | **Bug fix:** `/api/reporting/sql/run` and `/run` returned raw pyodbc cells to `jsonify`; `bytes`/`bytearray`/`memoryview` (varbinary, rowversion, image) and `datetime.time` aren't JSON-serializable → 500. Cells coerced at the response boundary (binary→`0x…` hex, time→ISO; date/datetime/Decimal/UUID pass through). | `ea7990d` |
| `scripts/provision-reporting-ro-logins.sql` + `CHANGELOG.md` | **Bug fix:** the `IF NOT EXISTS … CREATE LOGIN … ELSE (leave unchanged)` guard silently skipped password changes on re-run. ELSE now `ALTER LOGIN … WITH PASSWORD = :setvar`, so re-running **rotates** the password to match the env files. | `81ca59c` |

## Owner actions / next steps

1. **Unblock INT RO login (do this first).** The app sends the *new* env password but the INT
   SQL server still has the *old* one (the original script didn't rotate on re-run) → every RO
   query 500s as "Could not run query" with `Login failed for user 'nexora_reporting_ro' (18456)`
   in `var/logs/system/app.log`. Fix on the **INT `DB_SERVER_PRD`** (no nexora restart needed —
   password is checked per connection):
   ```sql
   ALTER LOGIN [nexora_reporting_ro]      WITH PASSWORD = N'<DB_REPORTING_RO_PWD from env/INT.env>';
   ALTER LOGIN [nexora_reporting_octo_ro] WITH PASSWORD = N'<DB_REPORTING_OCTO_RO_PWD from env/INT.env>';
   ```
   (Or just re-run the now-fixed `scripts/provision-reporting-ro-logins.sql` with `:setvar`
   passwords equal to the env values — it now `ALTER`s on re-run.) Then run a SQL query in the
   sandbox: a binary column should render as `0x…` (proves both the RO login and the JSON fix).
2. **Push + PR.** 4 (soon 5) commits are unpushed on `feature/2.5.63`. Pre-push runs the full
   e2e gate — `python scripts/test_db_reset.py` first. Then PR → `main` → deploy.
3. **PROD.** INT/PROD `DB_SERVER_PRD` may be **different hosts** — run the provisioning/rotation
   on the **PROD** server too, set the four `DB_REPORTING_*_RO_*` vars in `env/PROD.env` **on the
   prod box** (gitignored; doesn't deploy), apply AI migrations `0013`/`0014` (`python
   scripts/db-migrate.py --env PROD`), set the `AI_*` keys, and (optionally) `AI_DAILY_LIMIT`.
4. **Rotate the Azure key** (was exposed in an earlier transcript). Optionally cap `AI_DAILY_LIMIT`.
5. **Scheduled reports:** wire the Windows Task Scheduler task
   (`ops/run_scheduled_reports.py --once`, `ENVIRONMENT=PROD`) — see `docs/howto/reporting.md`.
6. **Reporting AI Phase 2:** implement from `docs/superpowers/plans/2026-06-03-reporting-ai-phase2.md`
   when desired (subagent-driven or inline). Needs nothing above except the AI provider (live on INT).

## Gotchas & notes

1. **The 18456 is a credential mismatch, not the JSON bug.** The JSON fix (`ea7990d`) is proven by
   a regression test that reproduces the exact `Object of type bytes is not JSON serializable` and
   now returns `0x000102`. Live confirmation is just gated behind Owner action #1.
2. **Provisioning script must run on EACH SQL server the env points at.** `get_ro_db_url` defaults
   the server to `cfg.DB_SERVER_PRD`, which can differ between `env/INT.env` and `env/PROD.env`.
3. **Re-running the script now rotates** the password (ALTER LOGIN). The owner's real passwords are
   **only** in the gitignored env files + this session's chat transcript — never in git (the script
   was always committed with placeholders). They've already rotated once.
4. **Windows line endings:** the `mixed-line-ending` pre-commit hook auto-fixes CRLF in `.sql` and
   aborts that commit — just `git add` + re-commit (happened once this session). See
   `…/memory/reference_line_endings_windows.md`.
5. **Stray empty files** (`limit`, `no`, `SQL_ROW_CAP`, `cannot`) appeared from accidental shell
   redirects and were removed. If `git status` shows new 0-byte junk at the repo root, delete it.
6. **Cost cap is safe-by-default:** `AI_DAILY_LIMIT` unset/`0` ⇒ unlimited, so INT behaviour is
   unchanged until the owner sets it.

## How to verify

```powershell
# Fast unit/integration (no live DB needed — the fix tests patch _run_sql):
python -m pytest tests/unit/test_reporting_json_safe.py tests/integration/test_reporting_routes.py `
  tests/integration/test_reporting_ai_routes.py tests/unit/test_translations.py `
  -o addopts="" -p no:cacheprovider -q
python -m ruff check nx_lib/views/reporting.py
# Live (after Owner action #1): nx -u -b --loginas:ben.streich → /reporting → SQL tab →
#   SELECT CAST(0x0102 AS VARBINARY(2)) AS B, CAST('13:45:00' AS TIME) AS T  → renders 0x0102 / 13:45:00
```

## Resuming in a fresh session

Most-likely first task is **Owner action #1** (the `ALTER LOGIN` to unblock the INT RO login), then
a live smoke of the SQL sandbox + AI. After that it's push/PR (#2) and the PROD rollout (#3), or
building **Phase 2** from its plan. This handoff is the state of record; the Phase-2 plan is the
build spec.
