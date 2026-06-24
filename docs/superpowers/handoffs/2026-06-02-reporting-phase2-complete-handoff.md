# Handoff — Reporting (BI) Phase 2 complete (live SQL sandbox)

- **Date:** 2026-06-02
- **Branch:** `feature/2.5.63` (committed locally, **NOT pushed** — remote session, commit-only)
- **HEAD:** `5c540a4` — 17 commits ahead of `origin/feature/2.5.63` (unpushed), 40 ahead of `origin/main`
- **Spec:** `docs/superpowers/specs/2026-06-02-reporting-phase2-sql-sandbox-design.md`
- **Plan:** `docs/superpowers/plans/2026-06-02-reporting-phase2-sql-sandbox.md`
- **Phase 1 handoff:** `docs/superpowers/handoffs/2026-06-02-reporting-phase1-handoff.md`

## TL;DR

**Phase 2 of the Reporting page — the live read-only SQL sandbox — is done, reviewed,
tested, and verified live on INT.** Built via subagent-driven development (14 plan tasks,
16 implementation commits; the security-critical sandbox and the routes got full two-stage
review; final holistic review = **Ship**). Backend suite green (605 passed, 24 skipped).
The branch now carries **both** Phase 1 (curated table engine) and Phase 2 (Phase 1 was
never merged). Nothing is pushed — **you push + open the PR**. One **owner action** remains:
provision the read-only SQL login (see §Owner actions) — until then the SQL tab degrades to
a graceful 503.

## What shipped (Phase 2)

The previously-disabled **SQL** tab on `/reporting` now works: a power user with
`reporting.sql.run` can run a single read-only `SELECT` against the **Statistics** DB,
see results in the existing grid, export to `.xlsx`, and save SQL reports.

- **Sandbox** (security boundary): single `SELECT`/`WITH`/set-op only, enforced by a
  **sqlglot AST gate** + keyword blocklist backup + `SELECT TOP (cap) * FROM (<sql>) _q`
  wrap + statement timeout + **dedicated `db_datareader`-only login** + per-run audit +
  20/min rate limit. 28 unit tests.
- **Access:** `reporting.sql.run` is a **grantable** permission (seeded + granted to
  `admin.view` profiles; grant per-user on request). First SQL-tab use shows a **one-time
  acknowledgment** (persisted per user in `ReportingSqlAck`).
- **Audit:** every execution → `dbo.ReportingSqlAudit` row (status `run|rejected|error`)
  **and** an app-logger line.
- Row cap **50 000**, statement timeout **~30 s**, target **Statistics only** (Octopus
  deferred).

## Architecture / file map (Phase 2 additions)

```
nx_lib/reporting/sandbox.py        sqlglot AST validate_select() + wrap_with_cap() (pure, DB-free, 28 tests)
nx_lib/reporting/sources.py        + SQL_ROW_CAP, SQL_TIMEOUT_S, sql_statistics source (kind "sql")
nx_lib/reporting/schema.py         + validate_sql_definition() (save/export SQL-def shape)
nx_lib/views/reporting.py          + _run_sql / _has_acked / _audit_sql, api_sql_run, api_sql_ack,
                                   + api_export SQL branch, api_sources SQL advertisement, kind in list
nx_lib/db.py                       + get_ro_db_url() + engine_statistics_ro (None until creds set)
nx_lib/config.py                   + DB_REPORTING_RO_USER, DB_REPORTING_RO_PWD
templates/reporting.html           SQL editor panel + acknowledgment modal; SQL toggle JS-gated
templates/js/_reporting_js.html    mode switch, runSql/ackThen, saveSql/exportSql (reuses renderResults)
static/css/reporting.css           SQL editor + modal styles
sql/_migrations/NexoraDB/0006_create_reporting_sql_tables.sql   ReportingSqlAudit + ReportingSqlAck (applied to INT)
sql/_migrations/NexoraDB/0007_seed_reporting_sql_permission.sql reporting.sql.run + grant (applied to INT)
sql/test/{schema,seed}.sql         + the two tables + reporting.sql.run for TEST/e2e
tests/unit/test_reporting_sandbox.py        sandbox unit tests
tests/unit/test_reporting_schema.py         + validate_sql_definition tests
tests/integration/test_reporting_routes.py  + sql/run & sql/ack auth tests
tests/e2e/test_reporting_sql.py             Playwright UI-flow smoke (flaky_e2e)
requirements.txt / pyproject.toml / uv.lock + sqlglot
env/*.env.example                  + DB_REPORTING_RO_USER / DB_REPORTING_RO_PWD
CHANGELOG.md, docs/howto/reporting.md, CLAUDE.md, translations/{de,fr,it}, messages.pot
```

## Key decisions (locked during brainstorming)

- Target **Statistics only** this phase (spec originally said Statistics+Octopus; Octopus deferred).
- **No 2FA step-up** — the sandbox already makes SQL safe; access is a grantable perm +
  one-time acknowledgment, not a re-auth ritual.
- **sqlglot AST gate** over pure-regex (added `sqlglot` dep, like Phase 1 added `openpyxl`).
- Audit to **table + logger**. Row cap **50k**, rate limit **20/min**.

## Gotchas & notes (read before resuming)

1. **`engine_statistics_ro` is `None` until the RO creds are set** → `/sql/run` returns
   **503** "SQL source is not configured" (page otherwise fine). This is the current INT
   state; the SQL tab enables and the full UI flow (tab → editor → acknowledgment) works,
   but a run can't return data until the login is provisioned. Browser-verified this way on
   INT (4 screenshots in `var/screenshots/reporting_sql_0{1..4}_*.png`).
2. **`_run_sql` raises `RuntimeError` (→503) BEFORE validation** when the engine is `None`,
   so pre-provisioning, even malformed SQL returns 503 not 400. Once the engine is
   configured this path can't be reached. (Noted as a minor follow-up: add a log line.)
3. **Audit-column name is `RowsReturned`** (not `RowCount` — `RowCount` is reserved-ish in
   T-SQL). Migration `0006` + `_audit_sql` agree; the spec was corrected to match (`5c540a4`).
4. **Blocklist dropped the `xp_`/`sp_` prefixes** during review — they false-reject
   legitimate identifiers (e.g. an `sp_balance` column); `EXEC`/`EXECUTE` + the AST gate
   already block stored-proc invocation. Spec corrected to match.
5. **`api_sources` was made resilient** to a curated-catalog fetch failure (try/except →
   `fields: []`) so one source's catalog error can't 500 the whole sources endpoint (which
   would block the SQL source/button). Rode into the `test:` commit `fe2ba98` (disclosed in
   its body) because re-splitting needs a `git reset` (per-turn opt-in + not pushed) — left
   as-is.
6. **App-wide Python `gettext` is untranslated** — `babel.cfg` uses non-recursive
   `[python: *.py]`, so `nx_lib/**` route messages aren't extracted and fall back to English
   for de/fr/it. Pre-existing across the whole app; **out of scope**. Template/UI strings
   (the user-facing bulk) ARE translated.
7. Same Windows line-ending + gitlint + immutable-migration gotchas as Phase 1 —
   see [[reference_line_endings_windows]] and the Phase 1 handoff.

## How to verify / run

```bash
# Backend suite (fast): expect 605 passed, 24 skipped
python -m pytest tests/unit tests/integration -q

# Sandbox unit tests only (the security boundary): 28 passed
python -m pytest tests/unit/test_reporting_sandbox.py -q

# SQL e2e smoke (needs TEST reseeded; UI flow only — no data in TEST): 1 passed
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_sql.py -o addopts="" -p no:cacheprovider -q

# Manual on INT: nx -u, dev-login arpad.dunai (has reporting.sql.run), open /reporting,
#   click SQL tab → editor → Run → acknowledgment → (503 until the RO login is provisioned)
```

## Owner actions (before the SQL tab returns data)

1. **Provision the read-only SQL login** — a SQL login with **`db_datareader` only** on the
   Statistics DB; set `DB_REPORTING_RO_USER` / `DB_REPORTING_RO_PWD` in `env/INT.env` and
   `env/PROD.env` (gitignored; the `*.env.example` carry the sanitized keys). Restart nexora.
2. Optionally confirm the pyodbc statement-timeout (`conn.dbapi_connection.timeout`) behaves
   on the box once real queries run.

## Open items / next steps

1. **Push `feature/2.5.63` and open the PR `→ main`** (Sydoc-Code/nexora). The branch
   bundles Phase 1 + Phase 2; a paste-ready PR description was produced this session (covers
   both phases, DB/deploy notes, and the owner action). Migrations `0004`/`0005`/`0006`/`0007`
   auto-apply to PROD before the code mirror on deploy.
2. **Deploy note:** `0006`/`0007` are already applied to INT; the deploy workflow applies
   pending migrations to PROD first, so merging creates the tables + perm on PROD. The SQL
   feature stays dark until the RO login is provisioned AND `reporting.sql.run` is granted
   (admins have it via `0007`).
3. **Follow-ups (noted, not built):** Octopus as a 2nd SQL target; charts/matrix viz; a
   saved-report **load** UI (the `kind` field is already returned by the list endpoint for
   it); the unaudited-503 log line; app-wide Python i18n (the `babel.cfg` recursion fix).

## Reporting commits — Phase 2 (oldest → newest)

```
915b597 spec + phase-1 handoff      ea92300 implementation plan
e93f16b sqlglot dep                 eee29d2 sandbox validator (28 tests)
18de397 read-only engine            f6b5310 env-example RO vars
714d36a audit + ack tables (0006)   024f01c reporting.sql.run perm (0007)
fb9d45e sql source registry         0e9d8ff validate_sql_definition
0b0627e sql run/ack/export routes   90416a7 SQL editor + ack markup
e157ccc editor + modal CSS          f33ec1e wire SQL tab (run/export/save)
fe2ba98 e2e smoke + TEST seed        b82d612 docs + translations
5c540a4 spec alignment
```

## Resuming in a fresh session

Point the new session at: this handoff + the Phase 2 spec + plan. The branch is the source
of truth (local, unpushed). The next concrete step is the user pushing + opening the PR and
provisioning the RO login. For further work, brainstorm/plan each follow-up as its own cycle.
