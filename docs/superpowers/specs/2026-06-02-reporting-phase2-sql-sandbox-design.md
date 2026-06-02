# Reporting Phase 2 — Live read-only SQL sandbox (Statistics)

- **Date:** 2026-06-02
- **Branch:** feature/2.5.63
- **Status:** Approved (brainstorming) — pending implementation plan
- **Author:** benstreich (with Claude)
- **Builds on:** `docs/superpowers/specs/2026-06-02-reporting-foundation-design.md` (Phase 1)
- **Phase 1 handoff:** `docs/superpowers/handoffs/2026-06-02-reporting-phase1-handoff.md`

## 1. Background & motivation

Phase 1 shipped the curated **Reporting** page: a table-first report builder over the
Document Processing source, with filters, combine, custom headers, save/load, and Excel
export, all behind `reporting.*` permissions. The page already renders a `Table | SQL`
toggle with the **SQL tab disabled ("coming soon")**.

Phase 2 enables that SQL tab: a **live, read-only SQL sandbox** so power users can run
their own `SELECT` queries against the Statistics database when the curated builder can't
express what they need (and so the owner can hand a user a ready-made query to paste).

This spec **refines** the Phase-1 spec's forward-looking "Phase 2" notes (§9, §17, §18 of
the foundation design). Where they differ, **this document wins** — the differences are
called out in §3.

## 2. Goals

- Enable the existing **SQL tab** in the Reporting page.
- Accept a **single read-only `SELECT` / `WITH … SELECT`** statement and return tabular
  results, reusing the Phase-1 results grid.
- Enforce a **security boundary** good enough to expose to non-admin reporting users:
  AST validation + keyword blocklist + row cap + statement timeout + a **dedicated
  read-only DB login** + per-execution audit + strict rate limiting.
- Make the capability **grantable** (`reporting.sql.run`) and **opt-in** (one-time
  acknowledgment), with the owner deciding who gets it.
- **Export** SQL results to `.xlsx` (reuse Phase-1 export) and **save/load** SQL queries as
  named reports (reuse the Phase-1 `Reports` table).
- **Audit** every execution to a table **and** the app logger.

## 3. Non-goals / changes from the Phase-1 forward notes

- **Statistics only.** The Phase-1 spec named *Statistics + Octopus*. Phase 2 targets the
  **Statistics DB only**; Octopus is deferred to a later follow-up once the pattern is
  proven.
- **No 2FA step-up.** Considered, but rejected: the sandbox already makes SQL safe (the RO
  login cannot write), so access is gated by a **grantable permission + a one-time
  acknowledgment**, not a re-auth ritual.
- Charts/matrix, scheduled reports, cross-user sharing, CSV — still deferred (Phase-1 §3).
- No SQL **autocomplete / schema browser** in this cut (a plain editor textarea).
- No multi-statement, no parameterized user queries, no temp tables/CTE-writes.

## 4. Decisions (locked during brainstorming)

| # | Decision | Choice |
|---|----------|--------|
| P1 | Target DB(s) | **Statistics only** (Octopus deferred) |
| P2 | RO login | Owner-provisioned `db_datareader`-only login; new `DB_REPORTING_RO_*` env vars; `engine_statistics_ro` |
| P3 | Access model | **Grantable** `reporting.sql.run` + **one-time acknowledgment**; seeded/granted to `admin.view` profiles, grantable per-user on request |
| P4 | Validation engine | **sqlglot AST gate** (single `SELECT`/`WITH`), keyword blocklist as backup |
| P5 | Row cap | **50 000** (`SQL_ROW_CAP`, reuses the curated `MAX_ROW_LIMIT` ceiling) |
| P6 | Rate limit | **20 / minute** on `/api/reporting/sql/run` |
| P7 | Audit sink | **`ReportingSqlAudit` table + app logger** line, every run |
| P8 | SQL tab scope | **Run + Export + Save** (full parity with curated) |
| P9 | Statement timeout | Per-query timeout on the RO connection (≈30 s; finalized in plan) |

## 5. Architecture

Phase 2 extends the existing `nx_lib/reporting/` package and `nx_lib/views/reporting.py`;
no new top-level directory.

```
nx_lib/
  reporting/
    sandbox.py      (new) validate_select() + wrap_with_cap() + blocklist — pure, DB-free
    schema.py       (+)   validate_sql_definition() for {kind:"sql",...} save/export defs
    sources.py      (+)   register kind:"sql" source (id "sql_statistics")
  views/
    reporting.py    (+)   api_sql_run, api_sql_ack; export/save extended for kind:"sql"
  db.py             (+)   get_ro_db_url() + engine_statistics_ro singleton
  config.py         (+)   DB_REPORTING_RO_USER, DB_REPORTING_RO_PWD
templates/
  reporting.html            (+) enable SQL tab markup
  js/_reporting_js.html      (+) SQL editor, run/export/save, acknowledgment modal
static/css/reporting.css     (+) SQL editor styles
sql/_migrations/NexoraDB/
  0006_create_reporting_sql_tables.sql   ReportingSqlAudit + ReportingSqlAck
  0007_seed_reporting_sql_permission.sql reporting.sql.run + grant to admin.view profiles
requirements.txt             (+) sqlglot
```

### Data flow (live SQL)

Browser (SQL tab) → `POST /api/reporting/sql/run` → `nx_lib/views/reporting.py`
→ `nx_lib/reporting/sandbox.py` (validate + wrap) → `engine_statistics_ro`
(RO `db_datareader` login, statement timeout) → rows → audit (`engine_nexora_db`
`ReportingSqlAudit` + logger) → JSON `{columns, rows, rowCount, truncated}`.

Saved SQL reports → `engine_nexora_db` `Reports` table (`DefinitionJSON.kind = "sql"`).

## 6. The sandbox (`nx_lib/reporting/sandbox.py`) — security boundary

Pure, DB-free module (unit-tested in isolation). Public surface:

- `validate_select(sql: str) -> str` — raises `SqlSandboxError(rule, message)` on any
  violation, else returns the trimmed SQL. Layers:
  1. **Non-empty / length cap** (reject absurdly long input, e.g. > 20 000 chars).
  2. **AST parse** with `sqlglot.parse(sql, dialect="tsql")`. Reject if it does not parse,
     or if it yields **more than one statement** (blocks `SELECT 1; DROP …` and the
     `) _q; DROP …` breakout, because the second statement parses as a separate node).
  3. **SELECT-only**: the single root expression must be a `sqlglot.exp.Select` or a
     `With` whose body is a `Select`. Reject `Insert/Update/Delete/Merge/Create/Drop/
     Alter/Command/Set/Use/...`.
  4. **AST walk**: reject the subtree if it contains any non-read node type
     (DML/DDL/`Command`/`Into` for `SELECT INTO`).
  5. **Keyword blocklist (backup, case-insensitive, comment-stripped, matched on word
     boundaries to avoid false positives like a column named `intolerance`):** `INSERT,
     UPDATE, DELETE, MERGE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE, EXEC, EXECUTE,
     INTO, BACKUP, RESTORE, SHUTDOWN, OPENROWSET, OPENQUERY, OPENDATASOURCE` plus the
     `xp_` / `sp_` prefixes. This is belt-and-suspenders behind the AST gate; the AST gate
     is the authority.
- `wrap_with_cap(sql: str, cap: int) -> str` — returns
  `SELECT TOP (<cap>) * FROM ( <sql> ) AS _q`. The cap holds regardless of the inner query.
  `cap` is an int interpolated by the server (never user-supplied text).

Defense-in-depth summary: (1) AST single-SELECT gate → (2) blocklist backup → (3) `TOP`
row cap → (4) statement timeout → (5) RO `db_datareader` login (writes impossible) →
(6) audit → (7) rate limit. Layers 1–2 are app-layer; 3–7 hold even if 1–2 are bypassed.

## 7. Endpoints (`nx_lib/views/reporting.py`)

| Method | Path | Perm | Notes |
|--------|------|------|-------|
| POST | `/api/reporting/sql/run` | `reporting.sql.run` | CSRF, `@limiter.limit("20 per minute")`, requires prior acknowledgment |
| POST | `/api/reporting/sql/ack` | `reporting.sql.run` | records one-time acknowledgment for the caller |

`api_sql_run` logic:
1. Require perm (decorator) + CSRF.
2. JSON body `{ "target": "statistics", "sql": "<text>" }`. Reject if `target` ∉
   `{"statistics"}` → `400`.
3. Require the caller has **acknowledged** (else `409` with a flag the UI uses to show the
   modal). Acknowledgment state lives in `ReportingSqlAck`.
4. `sandbox.validate_select(sql)` → `wrap_with_cap(sql, SQL_ROW_CAP)`.
5. Execute on `engine_statistics_ro` with a statement timeout.
6. `columns` from `cursor.description` (names only); `rows` from fetch.
7. **Audit** (table + logger): userid, username, target, sql, rowCount, status, durationMs.
8. Return `{columns:[{field,header}], rows, rowCount, truncated}` where
   `truncated = rowCount >= SQL_ROW_CAP`.

Errors: validation → `400` (message names the violated rule), audit `status="rejected"`;
missing ack → `409`; exec error/timeout → `500` (generic message), audit `status="error"`.
`api_sources` advertises the SQL source `{id:"sql_statistics", kind:"sql", acknowledged:
<bool>}` only when the caller holds `reporting.sql.run`.

## 8. Permissions & wiring

- `reporting.sql.run` — new code. **Grantable** to any reporting user; the owner flips it on
  per user (the "ask me" path).
- **Seed** (`0007`): insert the permission code, and **grant it to the access profiles that
  already hold `admin.view`** (mirrors how `0005` granted the Phase-1 base perms) — so the
  owner/admins have it out of the box and it is immediately testable. Idempotent.
- No change to `page_visibility()` / `startpage_redirect_to` (page access stays
  `reporting.view`). The SQL **tab** is gated client-side on the SQL source being present in
  the `/api/reporting/sources` response, and server-side by the route decorator.

## 9. Database (`sql/_migrations/NexoraDB/`)

`0006_create_reporting_sql_tables.sql` (idempotent `IF NOT EXISTS`):

- **`ReportingSqlAudit`** — `Id INT IDENTITY PK, UserID, Username NVARCHAR, TargetDB
  NVARCHAR, SqlText NVARCHAR(MAX), RowCount INT, Status NVARCHAR(16)
  (run|rejected|error), DurationMs INT, CreatedAt DATETIME2 DEFAULT SYSUTCDATETIME()`.
- **`ReportingSqlAck`** — `UserID INT PK, AcceptedAt DATETIME2 DEFAULT SYSUTCDATETIME()`.

`0007_seed_reporting_sql_permission.sql` — insert `reporting.sql.run` + grant to
`admin.view` profiles (idempotent).

Saved SQL reports reuse the existing **`Reports`** table; `DefinitionJSON` stores
`{kind:"sql", target, sql, title, headers?}`. Curated reports are `kind:"table"` (default
when `kind` absent).

## 10. Read-only engine (`nx_lib/db.py`, `nx_lib/config.py`)

- `config.py`: `DB_REPORTING_RO_USER`, `DB_REPORTING_RO_PWD` via `os.environ.get` (same
  pattern as `DB_UID`/`DB_PWD`).
- `db.py`: `get_ro_db_url(d)` (reuses `DB_SERVER_PRD`, RO creds) + module-level
  `engine_statistics_ro` (smaller pool, `pool_pre_ping`). If the RO creds are **unset**, the
  engine is `None` and the SQL source is **unavailable** (graceful degradation on boxes
  without the login yet — keeps local/test green before provisioning).
- **Statement timeout:** set the per-query timeout on the pyodbc connection/cursor
  (`connection.timeout` seconds) when executing sandbox SQL. Exact mechanism confirmed in
  the plan.

## 11. Frontend (enable the disabled SQL tab)

`templates/reporting.html` + `templates/js/_reporting_js.html` + `static/css/reporting.css`:

- **SQL editor**: monospace `<textarea>`, target selector (Statistics only for now), **Run**
  button. Results render in the **existing grid** (DOM via `textContent` — XSS-safe, as in
  Phase 1).
- **Acknowledgment modal**: shown the first time a user opens the SQL tab (or when the API
  returns `409`); on accept → `POST /api/reporting/sql/ack`, then proceed. Copy:
  read-only over Statistics, queries are logged, double-check before running. i18n via
  `{{ _('…') }}`.
- **Export**: reuse the Phase-1 Export (perm `reporting.export`, `rows_to_xlsx`); columns
  come from the SQL result.
- **Save / Load**: reuse Save/Load; a saved `kind:"sql"` report, when loaded, switches to
  the SQL tab and populates the editor. The list endpoint returns `kind` so the UI can badge
  SQL reports.

## 12. Dependencies

- **`sqlglot`** added to `requirements.txt` (pure-Python, MIT, no native build — consistent
  with how Phase 1 added `openpyxl`; uv-managed for IIS).

## 13. Testing

- **Unit** (`tests/unit/test_reporting_sandbox.py`): `validate_select` accepts a benign
  `SELECT` and `WITH … SELECT`; rejects each blocklisted keyword, multi-statement input, the
  `) _q; DROP …` breakout, comment-obfuscation (`/* */`, `--`), `SELECT … INTO`, and every
  non-SELECT statement type; `wrap_with_cap` output shape and cap interpolation.
- **Integration** (`tests/integration/test_reporting_routes.py`): `/api/reporting/sql/run`
  → `403` without `reporting.sql.run`; `409` before acknowledgment; `400` on bad target and
  on rejected SQL; CSRF enforced; `/api/reporting/sql/ack` records state.
- **e2e** (Playwright, `flaky_e2e`): admin dev-login (`arpad.dunai` on INT) opens the SQL
  tab, accepts the modal, runs a `SELECT`, sees the grid, exports `.xlsx`, saves + reloads.
  Add `reporting.sql.run` to TEST `sql/test/seed.sql`. Screenshots → `var/screenshots/`.

## 14. Docs (part of the change)

- `CHANGELOG.md` → `[Unreleased]` Added entries (SQL sandbox, audit table, `reporting.sql.run`).
- `docs/howto/reporting.md` → SQL sandbox section: rules, acknowledgment, RO-login
  provisioning, audit location.
- `CLAUDE.md` → new routes, `reporting.sql.run` perm, `DB_REPORTING_RO_*` env vars,
  `sqlglot` dep, `ReportingSqlAudit`/`ReportingSqlAck` tables, `engine_statistics_ro`.
- `env/*.env.example` → `DB_REPORTING_RO_USER`, `DB_REPORTING_RO_PWD` (sanitized).
- `deploy.yml` → no new top-level dir → no robocopy-exclude change expected (confirm).

## 15. Owner actions / prerequisites

- **Provision the RO login**: a SQL login with **`db_datareader` only** on the Statistics
  DB; set `DB_REPORTING_RO_USER` / `DB_REPORTING_RO_PWD` in `env/INT.env` + `env/PROD.env`
  (never committed; `env/*.env.example` carries the sanitized keys).
- Confirm the pyodbc **statement-timeout** mechanism + the desired timeout (≈30 s).
- Confirm `SQL_ROW_CAP = 50000` is acceptable as the high ceiling.

## 16. Rollout

Migrations `0006`/`0007` auto-apply to INT via the pre-commit hook and to PROD via the
deploy workflow (before code mirror). The SQL feature stays dark until (a) the RO login is
provisioned and (b) `reporting.sql.run` is granted to a user — so merging is safe even
before provisioning. Phasing within Phase 2 (for the plan): (1) sandbox + RO engine +
endpoint + audit + tests; (2) UI tab + acknowledgment + export/save reuse; (3) docs +
migrations + seed.
