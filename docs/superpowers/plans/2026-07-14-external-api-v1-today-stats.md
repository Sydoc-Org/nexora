# External API v1 — "Today" Stats Endpoint — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Executor model: Sonnet. Multi-agent planning run (explore → dual drafts → adversarial red-team → merge); **every file path, symbol, and quoted snippet below was Grep/Read-verified against the worktree at feature/2.5.64 HEAD (`97678a0`) on 2026-07-14** — trust the anchors, but re-Grep before editing since line numbers drift (this plan quotes code, never line numbers).

**Goal:** Expose the dashboard's "documents imported today" and "documents exported/processed today" KPI numbers as a machine-to-machine JSON API (`GET /api/v1/stats/today`) for one external client's own dashboard, authenticated by a per-client API key — one endpoint, one decorator, one table, one migration, tests, docs.

**Architecture:** Minimal-diff reuse of the existing KPI pipeline: the inline SQL-building in `dashboard_kpi_stats` (`nx_lib/views/dashboard.py`) is extracted into a session-free `compute_today_stats(target_processes)` **in the same module** (the four helpers `_split_stat_configs`/`_ms02_source`/`_default_stat_rows`/`_ms02_stat_rows` are already session-free, and existing tests monkeypatch them as `nx_lib.views.dashboard` attributes — moving them would break the suite). A new tiny module `nx_lib/api_auth.py` provides `require_api_key` (Bearer token → SHA-256 hash → constant-time match against **enabled** `dbo.ApiKeys` rows → client code + process scope on `flask.g`; no session). A new view module `nx_lib/views/api_external.py` wires one GET route via the house `register_routes(app)`/`add_url_rule` pattern, with `@limiter.limit` **outermost** (above auth — the red-team proved the reverse order leaves unauthenticated brute-force unthrottled AND makes the 429 test impossible). The global 404/500/403 handlers in `nx_lib/hooks.py` gain a 2-line `request.path.startswith("/api/v1")` → JSON branch (the exact idiom already used twice in that file). One migration (`0038`) creates `dbo.ApiKeys`; issuance is a dev-side script that prints the raw token once plus the INSERT.

**Tech Stack:** Python 3.13 / Flask (no new dependencies — stdlib `hashlib`/`hmac`/`secrets`), SQL Server migration under `sql/_migrations/NexoraDB/` + hand-maintained `sql/test/schema.sql` mirror, flask-limiter 3.12 (existing singleton), pytest unit + integration (real `NEXORA_TEST` ApiKeys table + established monkeypatch seams). No templates, no JS, no i18n.

---

## Context an engineer needs (read first)

- **Where you work:** the already-created worktree `.claude/worktrees/plan-external-api-v1-today-stats` (absolute: `C:\dev\nexora\.claude\worktrees\plan-external-api-v1-today-stats`) on branch `plan/external-api-v1-today-stats`, based on `feature/2.5.64` at `97678a0` (verified clean at that HEAD). It is merged back into `feature/2.5.64` after execution. **Commit per task on this branch. Do NOT `git push` and do NOT open a PR** — the owner reviews, merges and pushes (the pre-push hook runs the full suite incl. Playwright e2e; the owner runs it).
- **Python for tests:** the worktree has **no `.venv`** (verified). Run all pytest commands from the worktree root using the main clone's interpreter: `C:\dev\nexora\.venv\Scripts\python -m pytest …`. For `scripts/db-migrate.py`, `sql/sync-from-db.py`, `scripts/new-api-key.py` and the dev server use plain `python` (the global interpreter — the same one the pre-commit hooks and `nx` resolve; it has pyodbc + mssql-scripter, and the uv-managed `.venv` has no pip).
- **Worktree env caveat (do this FIRST):** gitignored `env/*.env` files exist only in the main clone (worktree `env/` holds only `*.env.example` — verified). Without them, the SQL pre-commit hooks fail with "Missing DB_SERVER_PRD / DB_UID / DB_PWD in env", `scripts/test_db_reset.py` can't find `env/TEST.env`, and pytest can't connect. Before Task 1: `Copy-Item C:\dev\nexora\env\INT.env env\INT.env` and `Copy-Item C:\dev\nexora\env\TEST.env env\TEST.env` (both gitignored, safe).
- **Anchor on quoted snippets + function names, NEVER line numbers.** Every step quotes the exact code to find; re-`Grep` it if it has moved.
- **TDD is the house rule.** Every code task below is genuine RED → GREEN: write the failing test, run it, implement, run again. Task 2 additionally re-runs the *existing* dashboard suites as characterization pins — if any pre-existing dashboard test goes red after the extraction, STOP and fix the extraction, never the test.
- **No spec exists** — requirements come from the locked-scope decisions table below; do not invent scope (no OAuth, no key-management UI, no OpenAPI, no usage dashboards).
- **Migrations needed: YES — one DDL migration, next free number `0038`** (directory currently tops out at `0037_reporting_processname_label.sql`; **re-list `sql/_migrations/NexoraDB/` at execution time** and bump if taken — a prior handoff earmarked 0038 in prose for a possible validationuser migration that was never created). Idempotent `IF NOT EXISTS` guard, named constraints, `SYSUTCDATETIME()` defaults — house-style anchor is `0033_create_prepared_documents.sql`. `*.sql` is LF-pinned by `.gitattributes` (verified: `*.sql text eol=lf`) — **write it with the Write tool**, never shell heredocs. This migration is real DDL: Task 1 applies it to INT manually and regenerates the per-object dumps, so the new `sql/NexoraDB/Tables/dbo.ApiKeys.sql` is staged in the same commit and the `sql-migrate-int`/`sql-sync-check` hooks no-op/pass (precedent: `dbo.PreparedDocuments.sql`). `SQL_SYNC_SKIP=1 git commit …` only for INT-unreachable flakes, **never** `--no-verify`.
- **TEST DB reality:** `NEXORA_TEST` (real SQL Server) is driven by hand-maintained `sql/test/schema.sql` + `seed.sql` via `scripts/test_db_reset.py` (which refuses unless `DB_NEXORA == 'NEXORA_TEST'` — verified). It has Users/Permission/auth + reporting tables but **no Statconfig and no Statistics DB**. Task 1 adds `dbo.ApiKeys` to `sql/test/schema.sql` (drop line + guarded CREATE, matching the file's reset pattern) so the auth path runs for real; the 200-path integration tests monkeypatch only `compute_today_stats`.
- **`db_conn` fixture trap:** rows written through the `db_conn` fixture's rolled-back transaction are INVISIBLE to the app's separate `raw_connection()`s under READ COMMITTED — integration tests must COMMIT their ApiKeys rows via `engine_nexora_db.raw_connection()` and delete them in `finally` (the tests below do exactly that).
- **i18n: none.** This feature adds **zero `_()` msgids** — JSON API, machine-facing English error strings only. HAZARD: `dashboard_kpi_stats` returns `jsonify({"error": _("Not authorized")})` — do **not** copy that idiom into the new modules or you drag in the full `/nx-i18n` extract→translate→compile cycle and `tests/unit/test_translations.py` fails.
- **Template cache: N/A** — no templates or JS partials are touched (also `tests/unit/test_template_url_prefix.py` cannot trip: it scans only `templates/**/*.html`).
- **GitNexus:** the MCP tools were unavailable at planning time; manual blast-radius was done instead: `dashboard_kpi_stats` has **zero Python callers** (registered once via `add_url_rule`, consumed only by the dashboard JS), so extraction risk is confined to `dashboard.py` + its tests. If the tools are available at execution time, run `gitnexus_impact({target: "dashboard_kpi_stats", direction: "upstream"})` before Task 2 per the house rules; expect LOW.
- **No new permission, no `page_visibility()` entry** — auth is the key row itself; the API has no page link and no session. **No `deploy.yml` changes** — `nx_lib/` ships by default; `sql/`, `scripts/`, `docs/`, `tests/` are already excluded from the robocopy mirror (the migration reaches PROD via the workflow's `db-migrate.py --env PROD` step, which runs from the checkout before the app-pool stop).
- **Rate limiting is part of the security surface here:** the red-team empirically verified (flask-limiter 3.12, pinned in requirements.txt) that decorated limits are enforced **inside the limit-decorator's wrapper**, not in the middleware pass — so `@limiter.limit` must sit ABOVE `@require_api_key` or 401 paths (the key-guessing surface) are never throttled. This deliberately diverges from `reporting.py`'s `@require_permission`-over-`@limiter.limit` stack; a 429 test pins it.
- **Dev server binds port 8000**, not 5000: `nx_main.py` reads `FLASK_RUN_PORT` with default `"8000"` (verified), and `docs/howto/nx.md` documents that nexora always binds 8000. Every live-verification URL in Task 8 and the howto uses 8000.
- **gitlint:** conventional-commit title, imperative, ≤72 chars, no trailing period, non-empty body wrapped ≤100 chars. Commit with `git commit -F - <<'EOF' … EOF` via the Bash tool. If `ruff`/`ruff-format` rewrites a file during the commit hook, re-`git add` and re-run the same commit command.
- **Commit trailer names the EXECUTING model.** The commit blocks below use `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` to match the declared executor; if a different model executes this plan, substitute its real name — never stamp a model that didn't run the work.
- **Pre-commit hooks** (`ruff`, `ruff-format`, `gitlint`, `sql-migrate-int`, `sql-sync-check`) run on every commit; Task 1 applies the migration to INT manually just before its commit, so the hook's re-apply is a recorded no-op.

---

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **GET-only v1 → no CSRF exemption.** Flask-WTF's `CSRFProtect` checks only mutating verbs; the route registers with default methods (GET). A POST is rejected before the view runs (405 in the suite, where `WTF_CSRF_ENABLED=False`; in PROD the CSRF guard may answer 400 first — either way, refused). | Locked scope. Zero config change; pinned by a 405 test. |
| D2 | **Auth = per-client API key in new `dbo.ApiKeys` (migration `0038`)**, columns exactly: `ID INT IDENTITY PK`, `KeyHash CHAR(64) NOT NULL UNIQUE` (SHA-256 hex is exactly 64 ASCII chars), `ClientCode NVARCHAR(32) NOT NULL`, `Label NVARCHAR(255) NULL` (who holds it), `ProcessList NVARCHAR(MAX) NOT NULL` (comma-separated full `Statconfig.ProcessName` values, e.g. `sydoc.05_PDBS`), `Enabled BIT NOT NULL DEFAULT 1`, `CreatedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()`, `LastUsedAt DATETIME2 NULL`. House style per `0033` (idempotent guard, named `PK_`/`UQ_`/`DF_` constraints, `GO`). Mirrored into `sql/test/schema.sql` with BOTH a drop-list line and a guarded CREATE (the file's established reset pattern). | Locked scope + 0033 house style. ProcessList stores the same ProcessName strings the dashboard's `dashboard.filter.process.*` perms resolve to, so they slot directly into the Statconfig `IN (…)` query. Comma-separation over JSON: simplest parse, values never contain commas. |
| D3 | **Key format:** `secrets.token_urlsafe(32)` (random 32 bytes, ~43-char token). **Stored form:** `hashlib.sha256(token).hexdigest()`. **Matching:** fetch the enabled `dbo.ApiKeys` rows, compare per-row with `hmac.compare_digest` (constant-time). No bcrypt. | Locked scope (high-entropy key → sha256 fine). Full-scan + `compare_digest` over a handful of rows avoids DB-side non-constant-time index comparison and makes the unit seam trivial to mock. |
| D4 | **`require_api_key` lives in a NEW module `nx_lib/api_auth.py`**, not `nx_lib/security.py`. | `security.py` is session-coupled by design (everything reads `flask.session`; tests monkeypatch `nx_lib.security.session` as a plain dict via the `fake_session` fixture) and `require_permission` redirects anonymous users to `/login` — both wrong for a machine client. No shared code path exists, so co-locating gains nothing. |
| D5 | **Auth fails CLOSED:** NexoraDB error during key lookup → `503 {"error": "Auth backend unavailable"}`. | Deliberate deviation from the house fail-open pattern for NexoraDB helper reads (e.g. `_enforce_active_session`): failing open here would be an auth bypass; a 401 would mislead the client into thinking the key was revoked. |
| D6 | **Uniform 401** JSON + `WWW-Authenticate: Bearer` for missing/malformed header AND for unknown **and disabled** keys (the lookup filters `WHERE Enabled = 1`, so a disabled key is simply absent); 500 JSON for stats-computation failure; 503 JSON for auth-DB failure. The route itself never emits 403. | Red-team finding: a distinct "API key disabled" 403 is an existence oracle — anyone holding a leaked/revoked key learns it was real. On an internet-reachable unauthenticated surface, revoked must be indistinguishable from never-issued. (The path-aware 403 handler in `hooks.py` stays as generic `/api/v1` safety — D12.) |
| D7 | **`LastUsedAt`:** best-effort `UPDATE … SET LastUsedAt = SYSUTCDATETIME()` on every successful auth, failure logged and swallowed (`_touch_last_used`). | Simplest thing that answers "is the client still using this key?"; a bookkeeping write must never fail an authenticated request. One client at ≤60 req/min → negligible write load. |
| D8 | **Endpoint & shape:** `GET /api/v1/stats/today` → `{"date": "<YYYY-MM-DD>", "imported_today": <int>, "exported_today": <int>, "processes": [<ProcessName>, …]}`. `date` is the **server-local** calendar date the counts refer to (the SQL uses `GETDATE()` on the T-SQL leg / `CURRENT_DATE` on the Postgres leg — same server-local "today"). `exported_today` carries the dashboard's `processed_today` semantics **verbatim**, including the existing asymmetry: the default T-SQL leg counts export-today only among rows whose import date is also today (its `WHERE CAST({col_import} as date) = cast(GETDATE() as date)`), while the MS02 leg counts export-today unconditionally. `processes` echoes the key's scope for client-side debugging. | Locked scope ("exported = processed_today semantics"). The `date` field makes the timezone-of-truth explicit to a client in another timezone. Inheriting the leg asymmetry verbatim = zero risk of changing dashboard numbers; changing it is Owner action 4. |
| D9 | **Extraction seam:** new module-level `compute_today_stats(target_processes) -> (imported_today, processed_today)` **inside `nx_lib/views/dashboard.py`**, containing the Statconfig read (own conn/cursor, closed in `finally`), `_split_stat_configs`, the T-SQL leg, and the MS02 leg. It **raises** on Statconfig-read failure (callers own the error surface — the dashboard's 500 stays uncached via `response_filter=_cacheable_response`; zero-filling would cache zeros for 60s on a NexoraDB blip). The two stat-row legs keep their swallow-and-degrade contract. `target_processes` must be non-empty (both callers guard). The `@cache.cached` decorator stays on the **view only** — the shared function is never cached. The view keeps: session check, perms→scope, the early zero return (**with its `processed_week: 0` quirk** — pinned by `test_kpi_stats_authed_returns_zeros`), backlog, try/except→500. | Existing tests monkeypatch `dv.engine_nexora_db`, `dv.engine_statistics_db`, `dv._ms02_stat_rows`, `dv.total_backlog_count` as `nx_lib.views.dashboard` attributes and call `dv.dashboard_kpi_stats.uncached()` — keeping the function in the same module preserves every seam. `api_external.py` imports it with no cycle (dashboard imports nothing from api_external). |
| D10 | **Empty `ProcessList` on a key → `200` with zeros** and `"processes": []`, without calling `compute_today_stats`. | Mirrors the dashboard's empty-scope early return; a misconfigured key should be debuggable from the payload, not a hard error. |
| D11 | **Rate limit: `@limiter.limit("60 per minute")` OUTERMOST, above `@require_api_key`** — the deliberate OPPOSITE of `reporting.py`'s `@require_permission`-over-`@limiter.limit` stack. In flask-limiter 3.12 decorated limits are enforced inside the limit wrapper (`_check_request_limit(in_middleware=False)`; `resolve_limits` skips decorated limits during the middleware pass), so with auth outermost the 401 paths — exactly the brute-force key-guessing surface, each costing a full `dbo.ApiKeys` scan + SHA-256 — would never be throttled, and a 429 test could never pass. Red-team verified both orders empirically: limiter-outermost 429s unauthenticated requests; auth-outermost never does. In-memory per-worker accepted (the `extensions.py` TODO documents it); `NEXORA_DISABLE_RATELIMIT=1` kill switch exists; the autouse `_reset_rate_limiter` fixture resets before every test. | Locked scope ("in-memory per-worker acceptable for one client") + red-team findings 1–2. 60/min is generous for a dashboard poller (once every 10–60 s). Per-key (vs per-IP) limits would need a custom `key_func` — out of v1 scope. |
| D12 | **JSON errors via path-aware global handlers:** the four handlers in `nx_lib/hooks.py` (`_page_not_found`, `_internal_error`, `_forbidden_page`, `_handle_permission_denied`) each gain `if request.path.startswith("/api/v1"): return jsonify(...)` — the exact idiom already used by `_enforce_active_session` and `_enforce_maintenance_lockout`. Gated on `/api/v1` (NOT `/api/`) so every legacy `/api/*` surface keeps today's behavior — minimal blast radius. 405 (client POSTs the GET-only route) and 429 keep Flask's/flask-limiter's default HTML bodies — status code is what a machine client reads; documented gotcha, YAGNI. | Locked scope offered "path-aware handlers OR in-route"; the decorator/route already return their own JSON, so the handlers only need to cover wrong-path 404 and unhandled 500 (403 kept as 2-line safety for any future `/api/v1` surface) — 2 lines each, tested. |
| D13 | **Key issuance v1 = manual:** new dev-side `scripts/new-api-key.py` prints the raw token ONCE plus a ready-to-run, quote-escaped `INSERT` for SSMS. The 2-line SHA-256 computation is duplicated from `api_auth.hash_api_key` **on purpose** (importing `nx_lib` creates DB engines at import time and requires live env config); both sites carry a keep-in-sync comment. `scripts/` is deploy-excluded, so issuance always runs from the dev box against the target DB. No UI. | Locked scope. Precedents: `scripts/new-process.py` (prints INSERT for review) and `scripts/provision-reporting-ro-logins.sql` (documented one-shot SQL). |
| D14 | **No response cache on the API route.** | The dashboard's 60s cache is session-keyed (`kpi_stats_{userid}_{filter}`) — meaningless without a session. One client at ≤60/min doesn't need caching, and a wrong-scope cache hit would leak another client's numbers. YAGNI. |
| D15 | **Maintenance lockout stays as-is:** `/api/v1` is not in `_MAINTENANCE_LOCKOUT_SKIP_PATHS`, so during a `BlockAccess` window the external client receives the existing `503 {"error": "Maintenance", …}` JSON (the hook's `/api/` branch). | Locked scope ("leave as-is"). Documented in the howto so the client can handle it. |
| D16 | **`ClientCode` is an audit/routing label only** — no FK, no validation against the `CLIENTS` registry. Unknown ProcessList names simply match no Statconfig rows and contribute 0. | The KPI path routes by `Statconfig.ClientCode` per process row, not by the key's client code; validating against `nx_lib/clients.py` would couple auth to Octo env config for zero benefit. |

---

## Owner actions (not for the executor)

1. **Issue the real client's key** (after PROD deploy): `python scripts/new-api-key.py --client-code <code> --label "<client name / contact>" --processes "<ProcessName>,…"` from the dev box, run the printed INSERT against **PROD** NexoraDB in SSMS, and hand the raw token to the client over a secure channel (it is printed once and never stored). You supply the real `ClientCode`, `Label`, and process scope — the executor cannot know them (ProcessList values must be exact `dbo.Statconfig.ProcessName` strings; `SELECT ProcessName FROM dbo.Statconfig` to list).
2. **Client comms:** send the client `docs/howto/external-api.md`'s essentials — base URL `https://nexora.sydoc.ch/nexora/api/v1/stats/today`, `Authorization: Bearer <key>` header, the response shape (note `date` is Sydoc-server-local), 60/min rate limit, that a blocking maintenance window returns a JSON 503, and that a revoked key answers exactly like an invalid one (401).
3. **Rate limit sanity:** 60/min was chosen for a dashboard poller; if the client needs more (or you want less), it is a one-string change in `nx_lib/views/api_external.py` — say the word.
4. **Semantics quirk decision (someday/maybe):** `exported_today` inherits the dashboard's default-leg asymmetry (export-today counted only among import-today rows on the T-SQL leg; unconditional on the MS02 leg). v1 ships it verbatim so API and dashboard always agree. If the client ever needs "all exports today regardless of import date", that is a deliberate semantics change to `compute_today_stats` affecting the dashboard too — its own plan.
5. **Revocation** is `UPDATE dbo.ApiKeys SET Enabled = 0 WHERE Label = '…';` — effective on the next request, and the key then behaves exactly like an unknown key (uniform 401, no existence leak). Rotation = issue a new key, disable the old.
6. **PROD rollout:** migration `0038` reaches PROD automatically on the next deploy after merge to main (the workflow applies migrations before mirroring code, so the endpoint can never ship without its table). ngrok/IIS untouched — no infra change in v1.
7. **Review, merge `plan/external-api-v1-today-stats` back into `feature/2.5.64`, and push** (this session is commit-only; the pre-push gate runs the full suite incl. e2e — run `python scripts/test_db_reset.py` first if TEST state is stale). Reminder: the Confluence docs sync is currently red (known cred/seat issue) — the new howto won't mirror until that's fixed; not this feature's failure.

---

# PHASE 1 — Schema (migration 0038 + TEST mirror)

### Task 1: `dbo.ApiKeys` — migration + test schema

**Files:**
- Create: `sql/_migrations/NexoraDB/0038_create_api_keys.sql`
- Modify: `sql/test/schema.sql` (drop-list line + guarded CREATE at end of file)
- Add after regen: `sql/NexoraDB/Tables/dbo.ApiKeys.sql` (auto-generated — never hand-edit)

**Interfaces:**
- Produces: `dbo.ApiKeys` on INT (manual apply, hook-verified) and on `NEXORA_TEST` (via `test_db_reset.py`) with columns `ID, KeyHash, ClientCode, Label, ProcessList, Enabled, CreatedAt, LastUsedAt` — consumed by `nx_lib/api_auth.py` (Task 3) and the integration tests (Task 4).

- [ ] **Step 1 — Prereqs:** copy the env files into the worktree (gitignored, safe):

```powershell
Copy-Item C:\dev\nexora\env\INT.env env\INT.env
Copy-Item C:\dev\nexora\env\TEST.env env\TEST.env
```

- [ ] **Step 2 — Re-verify the number is free:** list `sql/_migrations/NexoraDB/`; the directory currently tops out at `0037_reporting_processname_label.sql`. If `0038_*` exists, use the next integer and adjust the filename everywhere in this plan.

- [ ] **Step 3 — Write the migration** (Write tool, LF):

```sql
-- 0038_create_api_keys.sql
-- Per-client API keys for the external machine-to-machine JSON API v1
-- (GET /api/v1/stats/today). Only the SHA-256 hex digest of the random
-- 32-byte token is stored (high-entropy key -> bcrypt unnecessary);
-- issuance is manual in v1 via scripts/new-api-key.py (prints the raw
-- token once + the INSERT). ProcessList is a comma-separated list of
-- full dbo.Statconfig ProcessName values (e.g. 'sydoc.05_PDBS') defining
-- the key's stats scope -- the same strings the dashboard's
-- dashboard.filter.process.* permission codes resolve to. ClientCode is
-- an audit label (no FK, not validated against the CLIENTS registry).
-- Disabled keys (Enabled = 0) answer exactly like unknown keys (401) --
-- no existence oracle. No key-management UI, no OAuth, no usage
-- dashboard (YAGNI, v1).
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ApiKeys' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ApiKeys (
        ID          INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ApiKeys PRIMARY KEY,
        KeyHash     CHAR(64) NOT NULL CONSTRAINT UQ_ApiKeys_KeyHash UNIQUE,
        ClientCode  NVARCHAR(32) NOT NULL,
        Label       NVARCHAR(255) NULL,
        ProcessList NVARCHAR(MAX) NOT NULL,
        Enabled     BIT NOT NULL CONSTRAINT DF_ApiKeys_Enabled DEFAULT (1),
        CreatedAt   DATETIME2 NOT NULL CONSTRAINT DF_ApiKeys_CreatedAt DEFAULT (SYSUTCDATETIME()),
        LastUsedAt  DATETIME2 NULL
    );
END
GO
```

- [ ] **Step 4 — Mirror into the TEST schema (TWO edits — the file's reset pattern is drop-children-first at the top, guarded CREATE at the bottom).** First, in the drop list of `sql/test/schema.sql`, directly after the line:

```sql
IF OBJECT_ID('dbo.ReportingSqlAck', 'U') IS NOT NULL DROP TABLE dbo.ReportingSqlAck;
```

add (ApiKeys has no FKs, so this position is safe):

```sql
IF OBJECT_ID('dbo.ApiKeys', 'U') IS NOT NULL DROP TABLE dbo.ApiKeys;
```

Second, append at the very END of the file:

```sql

-- Per-client API keys for the external machine-to-machine API v1
-- (mirrors 0038_create_api_keys.sql). Integration tests insert/delete
-- their own committed rows (tests/integration/test_api_external_routes.py).
IF OBJECT_ID(N'dbo.ApiKeys', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ApiKeys (
        ID          INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ApiKeys PRIMARY KEY,
        KeyHash     CHAR(64) NOT NULL CONSTRAINT UQ_ApiKeys_KeyHash UNIQUE,
        ClientCode  NVARCHAR(32) NOT NULL,
        Label       NVARCHAR(255) NULL,
        ProcessList NVARCHAR(MAX) NOT NULL,
        Enabled     BIT NOT NULL CONSTRAINT DF_ApiKeys_Enabled DEFAULT (1),
        CreatedAt   DATETIME2 NOT NULL CONSTRAINT DF_ApiKeys_CreatedAt DEFAULT (SYSUTCDATETIME()),
        LastUsedAt  DATETIME2 NULL
    );
END;
GO
```

- [ ] **Step 5 — Apply to INT and regenerate the per-object dumps** (plain `python` = the interpreter the pre-commit hooks use; needs `env/INT.env` from Step 1). From the worktree root:

```
python scripts\db-migrate.py --env INT
python sql\sync-from-db.py
```

Expected: `0038_create_api_keys.sql` applied + recorded in `dbo.SchemaMigrations`; a NEW file `sql/NexoraDB/Tables/dbo.ApiKeys.sql` appears (`git status` shows it untracked). If `sync-from-db.py` fails on missing mssql-scripter: `python -m pip install -r sql\requirements.txt` and retry. If the regen changes OTHER dump files you did not cause (parallel INT work), do NOT add them — report the drift to the owner (and only if it blocks the commit, use `SQL_SYNC_SKIP=1` on Step 7 and say so in the report). Only if INT itself is unreachable: fall back to `SQL_SYNC_SKIP=1 git commit …` and run both commands from `C:\dev\nexora` once INT is back.

- [ ] **Step 6 — Apply to NEXORA_TEST and verify:**

Run: `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py`
Expected: completes without error (idempotent; refuses unless DB is `NEXORA_TEST`). Then verify (PowerShell-safe: only single quotes inside the `-c` program):

```powershell
C:\dev\nexora\.venv\Scripts\python -c "import os; os.environ['ENVIRONMENT']='TEST'; from nx_lib.db import engine_nexora_db; c=engine_nexora_db.raw_connection(); cur=c.cursor(); cur.execute('SELECT COUNT(*) FROM dbo.ApiKeys'); print(cur.fetchone()[0]); c.close()"
```

Expected: prints `0`.

- [ ] **Step 7 — Commit** (the `sql-migrate-int` hook no-ops — already applied+recorded; `sql-sync-check` passes because the dump is staged):

```bash
git add sql/_migrations/NexoraDB/0038_create_api_keys.sql sql/NexoraDB/Tables/dbo.ApiKeys.sql sql/test/schema.sql
git commit -F - <<'EOF'
feat(db): ApiKeys table for external API v1 (0038)

Create dbo.ApiKeys (SHA-256 key hash, client code, comma-separated
ProcessList scope, Enabled flag, CreatedAt/LastUsedAt stamps) for the
upcoming machine-to-machine JSON API. Idempotent guard, named
constraints, SYSUTCDATETIME defaults per 0033 house style. Mirror the
table into sql/test/schema.sql (drop line + guarded CREATE, matching
the file's reset pattern) so integration tests exercise the real auth
path against NEXORA_TEST, and stage the regenerated per-object dump
from INT. Raw keys are never stored -- issuance prints the token once
(scripts/new-api-key.py, follow-up commit).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

**Verify:** on INT (read-only), `SELECT TOP 1 * FROM dbo.ApiKeys` → empty result set, no error.

---

# PHASE 2 — Extract the KPI computation (TDD, no behavior change)

### Task 2: `compute_today_stats` seam in `nx_lib/views/dashboard.py`

**Files:**
- Modify: `nx_lib/views/dashboard.py` (add `compute_today_stats`; slim `dashboard_kpi_stats` to call it)
- Test: `tests/unit/test_dashboard_stats.py` (append; existing `_cfg_row`/`_engine_returning`/`_dead_engine`/`_CONFIGS` helpers are reused)

**Interfaces:**
- Produces: `compute_today_stats(target_processes: list[str]) -> tuple[int, int]` — `(imported_today, processed_today)`. Session-free; requires an app context (helper loggers use `current_app`); `target_processes` must be non-empty; RAISES if the Statconfig read fails. Consumed by Task 4's route (`from .dashboard import compute_today_stats`).
- Preserves: `dashboard_kpi_stats` external behavior byte-for-byte (JSON shapes, incl. the no-scope early return's `processed_week: 0`, the cached-view semantics, and `.uncached()` for tests).

- [ ] **Step 1 — Write the failing tests.** In `tests/unit/test_dashboard_stats.py`, add `import pytest` **directly ABOVE the line `from flask import session`** (same third-party block; this exact placement was verified against ruff's isort rules — putting it after the flask import or in the stdlib block fails `I001` and the ruff `--fix` hook will refile it, forcing a re-add + re-commit):

```python
import pytest
from flask import session
```

Then append at the end of the file:

```python
# --------------------------- compute_today_stats --------------------------- #
# Session-free seam shared by the dashboard KPI card and the external API v1
# (/api/v1/stats/today). Extracted verbatim from dashboard_kpi_stats, so the
# numbers must match the route's previous inline computation exactly.


def test_compute_today_stats_sums_both_legs(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning(_CONFIGS))
    # T-SQL leg returns (processed, imported) = (5, 7); MS02 leg adds (2, 3).
    monkeypatch.setattr(dv, "engine_statistics_db", _engine_returning([(5, 7)]))
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(2, 3)])
    with app.app_context():
        assert dv.compute_today_stats(["sydoc.Alpha", "sydoc.05_PDBS"]) == (10, 7)


def test_compute_today_stats_ms02_leg_survives_dead_statistics_db(app, monkeypatch):
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning(_CONFIGS))
    monkeypatch.setattr(dv, "engine_statistics_db", _dead_engine())
    monkeypatch.setattr(dv, "_ms02_stat_rows", lambda sql: [(5, 2)])
    with app.app_context():
        assert dv.compute_today_stats(["sydoc.Alpha", "sydoc.05_PDBS"]) == (2, 5)


def test_compute_today_stats_null_sums_count_as_zero(app, monkeypatch):
    # A Statconfig table with no rows today yields SUM(...) = (NULL, NULL).
    monkeypatch.setattr(dv, "engine_nexora_db", _engine_returning([_CONFIGS[0]]))
    monkeypatch.setattr(dv, "engine_statistics_db", _engine_returning([(None, None)]))
    with app.app_context():
        assert dv.compute_today_stats(["sydoc.Alpha"]) == (0, 0)


def test_compute_today_stats_raises_when_nexora_db_down(app, monkeypatch):
    # Fail-through contract: the Statconfig read must RAISE (not zero-fill) so
    # the dashboard's uncached-500 semantics and the API's JSON 500 both hold --
    # zeros here would be cached/reported as real numbers on a NexoraDB blip.
    monkeypatch.setattr(dv, "engine_nexora_db", _dead_engine("NexoraDB down"))
    with app.app_context():
        with pytest.raises(Exception):
            dv.compute_today_stats(["sydoc.Alpha"])
```

- [ ] **Step 2 — Run, expect RED** (`AttributeError: module 'nx_lib.views.dashboard' has no attribute 'compute_today_stats'`):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_dashboard_stats.py -k compute_today -q`
Expected: `4 failed`

- [ ] **Step 3 — Implement.** In `nx_lib/views/dashboard.py`, insert the new function immediately BEFORE the anchor line `DASHBOARD_LAYOUT_SCHEMA_VERSION = 1` (i.e. right after `_default_stat_rows`, whose body ends with `current_app.logger.error(f"default dashboard stats query failed: {e}")` / `return []`):

```python
def compute_today_stats(target_processes):
    """Session-free 'today' KPI computation shared by the dashboard KPI card
    (dashboard_kpi_stats) and the external API v1 (nx_lib/views/api_external.py).

    target_processes: NON-EMPTY list of full Statconfig ProcessName values
    (e.g. 'sydoc.05_PDBS'); both callers guard the empty case. Returns
    (imported_today, processed_today): imported = import-date-column is today,
    processed = export-date-column is today. Long-standing dashboard semantics
    inherited verbatim: the default T-SQL leg counts export-today only among
    rows whose import date is also today (its WHERE clause), while the MS02
    leg counts export-today unconditionally. 'Today' is server-local --
    GETDATE() on the T-SQL leg, CURRENT_DATE on the MS02 Postgres leg.

    The Statconfig read (NexoraDB) RAISES on failure -- callers own the error
    surface (the dashboard's except->500 stays uncached via
    _cacheable_response; the API returns a JSON 500). The two stat-row legs
    keep their swallow-and-degrade contract (_default_stat_rows /
    _ms02_stat_rows return [] on failure), so a dead Statistics DB still
    yields the healthy leg's numbers. Deliberately NOT cached here -- the
    dashboard view's @cache.cached (session-keyed) stays on the view.
    Deliberately lives in THIS module: it must resolve engine_nexora_db /
    engine_statistics_db / _ms02_stat_rows as nx_lib.views.dashboard
    attributes, which the existing tests monkeypatch.
    """
    processed_today = 0
    imported_today = 0

    conn_nex = None
    cursor_nex = None
    try:
        conn_nex = engine_nexora_db.raw_connection()
        cursor_nex = conn_nex.cursor()
        placeholders = ",".join(["?"] * len(target_processes))
        cursor_nex.execute(
            f"SELECT ProcessName, TableName, ExportColumn, ImportColumn, additionalCondition, ClientCode FROM Statconfig WHERE ProcessName IN ({placeholders})",
            target_processes,
        )
        configs = cursor_nex.fetchall()
    finally:
        if cursor_nex:
            cursor_nex.close()
        if conn_nex:
            conn_nex.close()

    default_configs, ms02_rows = _split_stat_configs(configs)

    if default_configs:
        sub_queries = []
        for row in default_configs:
            col_export = row.ExportColumn
            col_import = row.ImportColumn
            condition = f" {row.additionalCondition}" if row.additionalCondition else ""
            sub_queries.append(f"""
                SELECT
                    SUM(CASE WHEN CAST({col_export} AS DATE) = CAST(GETDATE() AS DATE) THEN 1 ELSE 0 END) as TodayCountExport,
                    SUM(CASE WHEN CAST({col_import} AS DATE) = CAST(GETDATE() AS DATE) THEN 1 ELSE 0 END) as TodayCountExportImport
                FROM [{DB_STATISTICS}].{row.TableName}
                WHERE CAST({col_import} as date) = cast(GETDATE() as date)
                {condition}
            """)

        if sub_queries:
            full_stat_query = f"""
                SELECT SUM(TodayCountExport), SUM(TodayCountExportImport)
                FROM ({' UNION ALL '.join(sub_queries)}) as combined
            """
            srows = _default_stat_rows(full_stat_query)
            if srows:
                processed_today += srows[0][0] or 0
                imported_today += srows[0][1] or 0

    ms02_src = _ms02_source(ms02_rows)
    if ms02_src:
        tbl, exp, imp = ms02_src
        mrows = _ms02_stat_rows(
            f"SELECT "
            f"COUNT(*) FILTER (WHERE {exp}::date = CURRENT_DATE), "
            f"COUNT(*) FILTER (WHERE {imp}::date = CURRENT_DATE) "
            f"FROM {tbl}"
        )
        if mrows:
            processed_today += mrows[0][0] or 0
            imported_today += mrows[0][1] or 0

    return imported_today, processed_today
```

(Note: `fetchall()` fully materializes pyodbc rows, so attribute access on `configs` keeps working after `conn_nex.close()` — established repo pattern.)

Then replace the BODY of `dashboard_kpi_stats` from the line `processed_today = 0` (the first statement after the `if not target_processes:` early-return block, which stays UNCHANGED — including `"processed_week": 0`) through the function's final `finally:` block (its last line is `conn_nex.close()`; the next top-level statement is the `@cache.cached(` decorator of `dashboard_hourly_stats`), with:

```python
    try:
        imported_today, processed_today = compute_today_stats(target_processes)

        current_backlog = 0
        if target_processes:
            proc_params = sorted({p.split(".")[-1] for p in target_processes if "." in p})
            cli_params = sorted({p.split(".")[0] for p in target_processes if "." in p})
            current_backlog += total_backlog_count(proc_params, cli_params)

        return jsonify(
            {
                "processed_today": processed_today,
                "imported_today": imported_today,
                "current_backlog": current_backlog,
            }
        )

    except Exception as e:
        current_app.logger.error(f"Failed to fetch kpi_stats report: {e}")
        return jsonify({"error": str(e)}), 500
```

The `@cache.cached(...)` decorator, the session check (`if "username" not in session: … _("Not authorized")`), the perms→`target_processes` derivation, and the early zero return above it are NOT touched.

- [ ] **Step 4 — Run the new tests, expect GREEN:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_dashboard_stats.py -k compute_today -q`
Expected: `4 passed`

- [ ] **Step 5 — Characterization gate: the ENTIRE existing dashboard suite must stay green** (these pin the refactor — `test_kpi_stats_serves_ms02_and_backlog_when_statistics_db_dead` exercises the full route via `.uncached()` with the same monkeypatch seams; `test_kpi_stats_authed_returns_zeros` pins the 4-key zero shape). If ANY pre-existing test fails, fix the extraction, never the test:

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_dashboard_stats.py tests/integration/test_dashboard_routes.py -q`
Expected: all passed (24 unit — 20 existing + 4 new — plus the 23 integration tests)

- [ ] **Step 6 — Commit:**

```bash
git add nx_lib/views/dashboard.py tests/unit/test_dashboard_stats.py
git commit -F - <<'EOF'
refactor(dashboard): extract session-free compute_today_stats seam

Pull the imported/processed 'today' KPI computation out of
dashboard_kpi_stats into module-level compute_today_stats(
target_processes) -> (imported_today, processed_today) so the external
API v1 endpoint can reuse it without a session. The function stays in
nx_lib/views/dashboard.py so existing monkeypatch seams
(dv.engine_nexora_db, dv.engine_statistics_db, dv._ms02_stat_rows,
dv.total_backlog_count) keep working; the Statconfig read raises
through (callers own the error surface -- the view's 500 stays uncached
via _cacheable_response) and the two stat-row legs keep their
swallow-and-degrade contract. View behavior unchanged: session check,
empty-scope early return (incl. processed_week), backlog, and the
session-keyed cache decorator all stay put.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 3 — API-key auth (TDD)

### Task 3: `nx_lib/api_auth.py` — `require_api_key`

**Files:**
- Create: `nx_lib/api_auth.py`
- Test: `tests/unit/test_api_auth.py` (new file)

**Interfaces:**
- Produces: `require_api_key(f)` decorator — reads `Authorization: Bearer <key>`; on success sets `g.api_client = {"key_id": int, "client_code": str, "processes": list[str]}` and calls the view; failure responses per D5/D6 (uniform 401, 503 fail-closed). Also `hash_api_key(raw_key) -> str` (sha256 hex, the stored form — reused by the issuance script and tests) and module-privates `_parse_process_list`, `_match_key`, `_touch_last_used`. Consumed by Task 4's route.

- [ ] **Step 1 — Write the failing tests.** Create `tests/unit/test_api_auth.py`:

```python
"""Unit tests for nx_lib/api_auth.py -- Bearer API-key auth for /api/v1.

The engine is mocked on the module (precedent:
tests/unit/test_prepared_documents.py -- CI/TEST has no guaranteed rows);
the route-level tests hit the real NEXORA_TEST ApiKeys table instead, see
tests/integration/test_api_external_routes.py. The decorator is exercised
by calling a wrapped probe view inside test_request_context.
"""

import hashlib
import types
from unittest.mock import MagicMock

from flask import g, jsonify

import nx_lib.api_auth as aa
from nx_lib.api_auth import hash_api_key, require_api_key


@require_api_key
def _probe():
    return jsonify(
        {
            "client": g.api_client["client_code"],
            "processes": g.api_client["processes"],
            "key_id": g.api_client["key_id"],
        }
    )


def _key_row(raw="sesame", client="acme", processes="p.a,p.b", kid=7):
    # Shape of the SELECT in _match_key: ID, KeyHash, ClientCode, ProcessList.
    # No Enabled attribute -- disabled rows are filtered out in SQL.
    return types.SimpleNamespace(
        ID=kid,
        KeyHash=hash_api_key(raw),
        ClientCode=client,
        ProcessList=processes,
    )


def _engine_returning(rows):
    cur = MagicMock()
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value = cur
    eng = MagicMock()
    eng.raw_connection.return_value = conn
    return eng


def _dead_engine(msg="NexoraDB down"):
    eng = MagicMock()
    eng.raw_connection.side_effect = RuntimeError(msg)
    return eng


# ------------------------------- helpers ------------------------------- #


def test_hash_api_key_is_sha256_hex():
    assert hash_api_key("abc") == hashlib.sha256(b"abc").hexdigest()
    assert len(hash_api_key("anything")) == 64


def test_parse_process_list_trims_and_drops_blanks():
    assert aa._parse_process_list(" a.b , ,c.d ,") == ["a.b", "c.d"]
    assert aa._parse_process_list("") == []
    assert aa._parse_process_list(None) == []


# ------------------------------ decorator ------------------------------ #


def test_missing_header_returns_401(app):
    with app.test_request_context("/api/v1/stats/today"):
        body, status, headers = _probe()
    assert status == 401
    assert headers["WWW-Authenticate"] == "Bearer"
    assert "Authorization" in body.get_json()["error"]


def test_non_bearer_scheme_returns_401(app):
    with app.test_request_context(
        "/api/v1/stats/today", headers={"Authorization": "Basic Zm9v"}
    ):
        body, status, headers = _probe()
    assert status == 401


def test_empty_bearer_token_returns_401(app):
    with app.test_request_context(
        "/api/v1/stats/today", headers={"Authorization": "Bearer   "}
    ):
        body, status, headers = _probe()
    assert status == 401


def test_unknown_key_returns_401(app, monkeypatch):
    monkeypatch.setattr(aa, "engine_nexora_db", _engine_returning([_key_row(raw="other")]))
    with app.test_request_context(
        "/api/v1/stats/today", headers={"Authorization": "Bearer sesame"}
    ):
        body, status, headers = _probe()
    assert status == 401
    assert body.get_json() == {"error": "Invalid API key"}


def test_disabled_keys_are_filtered_in_sql_and_get_the_same_401(app, monkeypatch):
    # Uniform 401: the lookup scans WHERE Enabled = 1, so a disabled key is
    # simply absent from the candidate rows -- indistinguishable from a
    # never-issued key (no existence oracle for leaked/revoked keys).
    eng = _engine_returning([])
    monkeypatch.setattr(aa, "engine_nexora_db", eng)
    with app.test_request_context(
        "/api/v1/stats/today", headers={"Authorization": "Bearer sesame"}
    ):
        body, status, headers = _probe()
    assert status == 401
    assert body.get_json() == {"error": "Invalid API key"}
    executed_sql = eng.raw_connection.return_value.cursor.return_value.execute.call_args[0][0]
    assert "Enabled = 1" in executed_sql


def test_db_error_fails_closed_with_503(app, monkeypatch):
    # Deliberate deviation from the dashboard helpers' fail-open pattern:
    # auth must fail CLOSED -- a NexoraDB blip yields 503, never a free pass
    # and never a misleading 401 ("key revoked").
    monkeypatch.setattr(aa, "engine_nexora_db", _dead_engine())
    with app.test_request_context(
        "/api/v1/stats/today", headers={"Authorization": "Bearer sesame"}
    ):
        body, status = _probe()
    assert status == 503
    assert body.get_json() == {"error": "Auth backend unavailable"}


def test_good_key_sets_g_and_calls_view(app, monkeypatch):
    monkeypatch.setattr(aa, "engine_nexora_db", _engine_returning([_key_row()]))
    with app.test_request_context(
        "/api/v1/stats/today", headers={"Authorization": "Bearer sesame"}
    ):
        resp = _probe()
    assert resp.status_code == 200
    assert resp.get_json() == {"client": "acme", "processes": ["p.a", "p.b"], "key_id": 7}


def test_key_matching_uses_constant_time_compare(app, monkeypatch):
    calls = []
    real = aa.hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(aa.hmac, "compare_digest", spy)
    monkeypatch.setattr(aa, "engine_nexora_db", _engine_returning([_key_row()]))
    with app.test_request_context(
        "/api/v1/stats/today", headers={"Authorization": "Bearer sesame"}
    ):
        _probe()
    assert calls, "hmac.compare_digest was not used for key matching"


def test_touch_last_used_swallows_db_errors(app, monkeypatch):
    # LastUsedAt is best-effort bookkeeping: a write failure must not fail an
    # otherwise-authenticated request.
    monkeypatch.setattr(aa, "engine_nexora_db", _dead_engine())
    with app.app_context():
        aa._touch_last_used(1)  # must not raise
```

- [ ] **Step 2 — Run, expect RED** (`ModuleNotFoundError: No module named 'nx_lib.api_auth'`):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_api_auth.py -q`
Expected: collection error (import failure)

- [ ] **Step 3 — Implement.** Create `nx_lib/api_auth.py`:

```python
"""API-key (Bearer) authentication for the external machine-to-machine API.

Deliberately separate from nx_lib/security.py: everything there reads the
Flask session (and its test seam monkeypatches nx_lib.security.session as a
plain dict); this module is session-free by design and never redirects.

Keys are random 32-byte tokens (secrets.token_urlsafe(32), issued by
scripts/new-api-key.py); dbo.ApiKeys (migration 0038) stores only the
SHA-256 hex digest. High-entropy keys make bcrypt unnecessary; matching is
constant-time via hmac.compare_digest over the enabled-key list (a handful
of rows in v1 -- revisit if the table ever grows large).

Error contract (all JSON, no login redirect, no i18n -- machine-facing):
  401 missing/malformed header, unknown key, OR disabled key (+
      WWW-Authenticate: Bearer). Uniform on purpose: the lookup filters
      Enabled = 1, so a revoked key is indistinguishable from a
      never-issued one -- no existence oracle on an external surface.
  503 NexoraDB unreachable during lookup (auth fails CLOSED -- deliberate
      deviation from the dashboard helpers' fail-open pattern).
"""

import hashlib
import hmac
from functools import wraps

from flask import current_app, g, jsonify, request

from .db import engine_nexora_db


def hash_api_key(raw_key):
    """SHA-256 hex digest of the raw Bearer token (the stored form). Must
    stay in sync with scripts/new-api-key.py, which duplicates these two
    lines to avoid importing nx_lib (engine creation at import time needs
    live env config)."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _parse_process_list(raw):
    """Comma-separated ProcessList column -> clean list of ProcessName strings."""
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


def _match_key(raw_key):
    """Return the ENABLED dbo.ApiKeys row whose KeyHash matches raw_key, or None.

    Fetches every enabled row (WHERE Enabled = 1 -- disabled keys behave
    exactly like unknown ones, see module docstring) and compares per-row
    with hmac.compare_digest so the comparison is constant-time in Python
    (a WHERE KeyHash = ? lookup would compare inside the index instead).
    Raises on DB failure (the decorator turns that into a 503 -- fail closed).
    """
    presented = hash_api_key(raw_key)
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT ID, KeyHash, ClientCode, ProcessList FROM dbo.ApiKeys WHERE Enabled = 1"
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    for row in rows:
        if hmac.compare_digest(str(row.KeyHash).strip(), presented):
            return row
    return None


def _touch_last_used(key_id):
    """Best-effort LastUsedAt stamp; never fails the request."""
    try:
        conn = engine_nexora_db.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE dbo.ApiKeys SET LastUsedAt = SYSUTCDATETIME() WHERE ID = ?",
                [key_id],
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        current_app.logger.warning(f"ApiKeys LastUsedAt update failed: {e}")


def require_api_key(f):
    """Decorator: authenticate the request via 'Authorization: Bearer <key>'.

    On success sets g.api_client = {"key_id", "client_code", "processes"}
    and calls the view. No session is read or written.
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or not auth[7:].strip():
            return (
                jsonify({"error": "Missing or malformed Authorization header"}),
                401,
                {"WWW-Authenticate": "Bearer"},
            )
        raw_key = auth[7:].strip()
        try:
            row = _match_key(raw_key)
        except Exception as e:
            current_app.logger.error(f"ApiKeys lookup failed: {e}")
            return jsonify({"error": "Auth backend unavailable"}), 503
        if row is None:
            return (
                jsonify({"error": "Invalid API key"}),
                401,
                {"WWW-Authenticate": "Bearer"},
            )
        _touch_last_used(row.ID)
        g.api_client = {
            "key_id": row.ID,
            "client_code": row.ClientCode,
            "processes": _parse_process_list(row.ProcessList),
        }
        return f(*args, **kwargs)

    return wrapper
```

- [ ] **Step 4 — Run, expect GREEN:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_api_auth.py -q`
Expected: `11 passed`

- [ ] **Step 5 — Commit:**

```bash
git add nx_lib/api_auth.py tests/unit/test_api_auth.py
git commit -F - <<'EOF'
feat(api): require_api_key Bearer auth over dbo.ApiKeys

New session-free module nx_lib/api_auth.py: require_api_key reads
'Authorization: Bearer <key>', hashes it (SHA-256) and matches it
against enabled dbo.ApiKeys rows with hmac.compare_digest (constant
time; the table holds a handful of rows in v1). Uniform 401 JSON for
missing/malformed headers and unknown OR disabled keys (the lookup
filters Enabled = 1, so a revoked key is indistinguishable from a
never-issued one -- no existence oracle on an external surface), with
WWW-Authenticate: Bearer; 503 fail-CLOSED when NexoraDB is unreachable
(deliberate deviation from the dashboard helpers' fail-open pattern).
On success sets g.api_client = {key_id, client_code, processes} and
stamps LastUsedAt best-effort. Kept out of nx_lib/security.py, whose
seam is session-coupled by design (tests monkeypatch
nx_lib.security.session).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 4 — The endpoint (TDD, integration)

### Task 4: `nx_lib/views/api_external.py` + `create_app` wiring

**Files:**
- Create: `nx_lib/views/api_external.py`
- Modify: `nx_lib/__init__.py` (import tuple + register call)
- Test: `tests/integration/test_api_external_routes.py` (new file)

**Interfaces:**
- Consumes: `require_api_key` / `g.api_client` (Task 3), `compute_today_stats(target_processes) -> (imported_today, processed_today)` (Task 2), `limiter` singleton from `nx_lib/extensions.py`, `dbo.ApiKeys` in NEXORA_TEST (Task 1).
- Produces: endpoint `api_v1_stats_today` at `GET /api/v1/stats/today` returning `{"date", "imported_today", "exported_today", "processes"}` (D8); `register_routes(app)` wired in `create_app`. Task 5 appends two handler tests to this test file.

- [ ] **Step 1 — Write the failing tests.** Create `tests/integration/test_api_external_routes.py`:

```python
"""Integration tests for the external machine-to-machine API v1
(nx_lib/views/api_external.py + nx_lib/api_auth.py).

dbo.ApiKeys EXISTS in the TEST schema (mirror added alongside migration
0038), so the auth paths run for real against NEXORA_TEST. The db_conn
fixture's rolled-back transaction is INVISIBLE to the app's separate
raw_connection()s, so key rows are committed directly and deleted in a
finally. The 200 path monkeypatches only compute_today_stats -- TEST has
no Statconfig table and no Statistics DB (precedent:
tests/integration/test_dashboard_routes.py).

No login fixtures: this API never touches the session.
"""

import hashlib
import secrets
from datetime import date

import nx_lib.views.api_external as ax
from nx_lib.db import engine_nexora_db

URL = "/api/v1/stats/today"


def _insert_key(raw_key, client_code="testclient", processes="sydoc.TestProc", enabled=1):
    """Commit an ApiKeys row the app can see; returns the KeyHash for cleanup."""
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.ApiKeys (KeyHash, ClientCode, Label, ProcessList, Enabled) "
            "VALUES (?, ?, ?, ?, ?)",
            [key_hash, client_code, "pytest temp key", processes, enabled],
        )
        conn.commit()
    finally:
        conn.close()
    return key_hash


def _delete_key(key_hash):
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.ApiKeys WHERE KeyHash = ?", [key_hash])
        conn.commit()
    finally:
        conn.close()


def _last_used(key_hash):
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT LastUsedAt FROM dbo.ApiKeys WHERE KeyHash = ?", [key_hash])
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def test_no_auth_header_returns_401_json(client):
    resp = client.get(URL)
    assert resp.status_code == 401
    assert resp.is_json
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


def test_non_bearer_scheme_returns_401_json(client):
    resp = client.get(URL, headers={"Authorization": "Basic Zm9vOmJhcg=="})
    assert resp.status_code == 401
    assert resp.is_json


def test_unknown_key_returns_401_json(client):
    resp = client.get(
        URL, headers={"Authorization": f"Bearer {secrets.token_urlsafe(32)}"}
    )
    assert resp.status_code == 401
    assert resp.get_json() == {"error": "Invalid API key"}


def test_disabled_key_gets_the_same_401(client):
    # Uniform 401 (no existence oracle): revoked == never issued.
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, enabled=0)
    try:
        resp = client.get(URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 401
        assert resp.get_json() == {"error": "Invalid API key"}
    finally:
        _delete_key(key_hash)


def test_post_method_not_allowed(client):
    # GET-only v1 (D1). 405 here because the suite runs WTF_CSRF_ENABLED=False;
    # in PROD the CSRF before_request guard may answer 400 first -- either way
    # a mutating verb is refused before the view runs.
    resp = client.post(URL)
    assert resp.status_code == 405


def test_good_key_returns_scoped_stats_and_stamps_last_used(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="sydoc.TestProc, sydoc.Other")
    seen = {}

    def _fake_compute(target_processes):
        seen["processes"] = target_processes
        return (12, 8)  # (imported_today, processed_today)

    monkeypatch.setattr(ax, "compute_today_stats", _fake_compute)
    try:
        resp = client.get(URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert resp.get_json() == {
            "date": date.today().isoformat(),
            "imported_today": 12,
            "exported_today": 8,
            "processes": ["sydoc.TestProc", "sydoc.Other"],
        }
        # Scope comes from the ApiKeys row, whitespace-tolerant.
        assert seen["processes"] == ["sydoc.TestProc", "sydoc.Other"]
        assert _last_used(key_hash) is not None
    finally:
        _delete_key(key_hash)


def test_empty_process_scope_returns_zeros_without_compute(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw, processes="")

    def _must_not_be_called(target_processes):
        raise AssertionError("compute_today_stats must not run for an empty scope")

    monkeypatch.setattr(ax, "compute_today_stats", _must_not_be_called)
    try:
        resp = client.get(URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["imported_today"] == 0
        assert body["exported_today"] == 0
        assert body["processes"] == []
    finally:
        _delete_key(key_hash)


def test_stats_backend_error_returns_500_json(client, monkeypatch):
    raw = secrets.token_urlsafe(32)
    key_hash = _insert_key(raw)

    def _boom(target_processes):
        raise RuntimeError("StatisticsDB exploded")

    monkeypatch.setattr(ax, "compute_today_stats", _boom)
    try:
        resp = client.get(URL, headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Stats backend unavailable"}
    finally:
        _delete_key(key_hash)


def test_rate_limit_429_for_unauthenticated_requests(client):
    # SECURITY PIN for the decorator order (@limiter.limit OUTERMOST, D11):
    # the 60/min limit must throttle unauthenticated requests too -- they are
    # the brute-force surface, and each costs a full dbo.ApiKeys scan. With
    # auth outermost, decorated limits (enforced inside the limit wrapper in
    # flask-limiter 3.12) would never run on 401 paths and this test could
    # never pass. The autouse _reset_rate_limiter fixture ran before this
    # test, so the 61st request in-test must 429. Requires an active limiter:
    # do NOT run the suite with NEXORA_DISABLE_RATELIMIT=1 (only the e2e
    # conftest sets it, in its own subprocess). The no-header 401 path never
    # touches the DB, so this stays fast.
    for _ in range(60):
        assert client.get(URL).status_code == 401
    assert client.get(URL).status_code == 429
```

- [ ] **Step 2 — Run, expect RED:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/integration/test_api_external_routes.py -q`
Expected: collection error (`ModuleNotFoundError: No module named 'nx_lib.views.api_external'`). (After Step 3's module exists but before Step 4's wiring, the requests would 404 instead — both are RED.)

- [ ] **Step 3 — Implement the view module.** Create `nx_lib/views/api_external.py`:

```python
"""External machine-to-machine JSON API, version 1.

One endpoint in v1: GET /api/v1/stats/today -- the dashboard's
imported/processed "today" KPI numbers for the API key's process scope
(dbo.ApiKeys.ProcessList), consumed by an external client's own dashboard.

Auth is per-client API keys (require_api_key in nx_lib/api_auth.py) -- no
session, no CSRF (GET-only; Flask-WTF checks only mutating verbs), and no
i18n: machine-facing English error strings only (do NOT add _() here -- it
would drag in the pybabel cycle). No response cache: the dashboard's
session-keyed cache is meaningless here and one client at 60/min doesn't
need one. PROD serves this under /nexora via PrefixMiddleware:
https://nexora.sydoc.ch/nexora/api/v1/stats/today
"""

from datetime import date

from flask import current_app, g, jsonify

from ..api_auth import require_api_key
from ..extensions import limiter
from .dashboard import compute_today_stats


# NOTE decorator order: @limiter.limit is OUTERMOST -- the deliberate
# OPPOSITE of reporting.py's @require_permission-over-@limiter.limit stack.
# Decorated limits are enforced inside the limit wrapper (flask-limiter
# 3.12), so with auth outermost the 401 paths -- exactly the unauthenticated
# brute-force surface, each a full dbo.ApiKeys scan -- would never be
# throttled. Pinned by test_rate_limit_429_for_unauthenticated_requests.
@limiter.limit("60 per minute")
@require_api_key
def api_v1_stats_today():
    processes = g.api_client["processes"]
    if not processes:
        # Misconfigured key (empty ProcessList): mirror the dashboard's
        # empty-scope zeros rather than erroring -- debuggable from the payload.
        imported_today, processed_today = 0, 0
    else:
        try:
            imported_today, processed_today = compute_today_stats(processes)
        except Exception as e:
            current_app.logger.error(f"external api stats/today failed: {e}")
            return jsonify({"error": "Stats backend unavailable"}), 500
    return jsonify(
        {
            # Server-local calendar date the counts refer to (the SQL uses
            # GETDATE() / CURRENT_DATE -- the same server-local 'today').
            "date": date.today().isoformat(),
            "imported_today": imported_today,
            "exported_today": processed_today,
            "processes": processes,
        }
    )


def register_routes(app):
    app.add_url_rule(
        "/api/v1/stats/today",
        endpoint="api_v1_stats_today",
        view_func=api_v1_stats_today,
    )
```

- [ ] **Step 4 — Wire it in `create_app`.** In `nx_lib/__init__.py`, find:

```python
    from .views import (
        admin,
        auth,
```

Replace with:

```python
    from .views import (
        admin,
        api_external,
        auth,
```

Then find:

```python
    invoices.register_routes(app)
    chat.register_routes(app)
```

Replace with:

```python
    invoices.register_routes(app)
    chat.register_routes(app)
    api_external.register_routes(app)  # machine-to-machine API (Bearer key, no session)
```

- [ ] **Step 5 — Run the new tests, expect GREEN:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/integration/test_api_external_routes.py -q`
Expected: `9 passed` (the rate-limit test takes a few seconds — expected)

- [ ] **Step 6 — App-factory smoke** (the endpoint-set pin in `test_create_app.py` treats NEW endpoints as informational `extra`, so it must stay green):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_create_app.py tests/unit/test_api_auth.py -q`
Expected: all passed

- [ ] **Step 7 — Commit:**

```bash
git add nx_lib/views/api_external.py nx_lib/__init__.py tests/integration/test_api_external_routes.py
git commit -F - <<'EOF'
feat(api): external v1 endpoint GET /api/v1/stats/today

New view module nx_lib/views/api_external.py (add_url_rule pattern,
wired in create_app): returns the dashboard's imported/processed
'today' KPI numbers as JSON ({date, imported_today, exported_today,
processes}), scoped to the API key's ProcessList via
compute_today_stats. Empty scope mirrors the dashboard's zero
response; stats failures return a JSON 500. Rate limit 60/min with
@limiter.limit OUTERMOST -- above require_api_key, the opposite of
reporting.py's stack -- so unauthenticated brute-force requests are
throttled too (decorated limits enforce inside the limit wrapper;
auth-first would leave 401 paths unthrottled). Pinned by a 429 test.
GET-only so no CSRF exemption is needed; no session; no i18n
(machine-facing English strings keep the pybabel cycle out).
Integration tests run the real auth path against NEXORA_TEST ApiKeys
rows and monkeypatch only compute_today_stats (TEST has no Statconfig
or Statistics DB).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 5 — JSON error handlers for `/api/v1` (TDD)

### Task 5: path-aware 404/500/403 in `nx_lib/hooks.py`

**Files:**
- Modify: `nx_lib/hooks.py` (four handler functions)
- Test: `tests/unit/test_hooks.py` (append), `tests/integration/test_api_external_routes.py` (append)

**Interfaces:**
- Produces: any 404/500/403 raised on a `/api/v1*` path returns JSON (`{"error": "Not found"}` / `{"error": "Internal server error"}` / `{"error": "Forbidden"}`); every other path keeps the HTML handler pages (pinned by the pre-existing `test_page_not_found_returns_404` etc. in the same file). Consumed by the external client (wrong path → parseable error).

- [ ] **Step 1 — Write the failing tests.** Append to `tests/unit/test_hooks.py` (verified: the file already imports `_page_not_found`, `_internal_error`, `_forbidden_page`, `_handle_permission_denied`, `PermissionDenied`, `MagicMock`, and uses the `app` fixture):

```python
# ---------- error handlers: /api/v1 JSON branch ----------


def test_page_not_found_api_v1_returns_json(app):
    with app.test_request_context("/api/v1/nope"):
        body, status = _page_not_found(MagicMock())
        assert status == 404
        assert body.get_json() == {"error": "Not found"}


def test_internal_error_api_v1_returns_json(app):
    with app.test_request_context("/api/v1/stats/today"):
        body, status = _internal_error(MagicMock())
        assert status == 500
        assert body.get_json() == {"error": "Internal server error"}


def test_forbidden_api_v1_returns_json(app):
    with app.test_request_context("/api/v1/stats/today"):
        body, status = _forbidden_page(MagicMock())
        assert status == 403
        assert body.get_json() == {"error": "Forbidden"}


def test_permission_denied_api_v1_returns_json(app):
    with app.test_request_context("/api/v1/stats/today"):
        body, status = _handle_permission_denied(PermissionDenied())
        assert status == 403
        assert body.get_json() == {"error": "Forbidden"}
```

And append to `tests/integration/test_api_external_routes.py` (proves the wiring end-to-end through the app, not just the handler functions):

```python
# --------------------------- JSON error handlers --------------------------- #


def test_unknown_api_v1_path_returns_json_404(client):
    resp = client.get("/api/v1/definitely/not/a/route")
    assert resp.status_code == 404
    assert resp.is_json
    assert resp.get_json() == {"error": "Not found"}


def test_non_api_404_still_renders_html(client):
    resp = client.get("/definitely-not-a-page")
    assert resp.status_code == 404
    assert "text/html" in resp.content_type
```

- [ ] **Step 2 — Run, expect RED** (the four unit tests fail unpacking/asserting HTML; the integration 404 test fails `resp.is_json`; `-k api_v1` selects exactly those five):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_hooks.py tests/integration/test_api_external_routes.py -k api_v1 -q`
Expected: `5 failed` (plus deselected notes)

- [ ] **Step 3 — Implement.** In `nx_lib/hooks.py`, replace the four handlers. Find:

```python
def _page_not_found(e):
    return render_template("handlers/404.html"), 404


def _internal_error(e):
    return render_template("handlers/500.html"), 500


def _forbidden_page(e):
    return render_template("handlers/403.html"), 403


def _handle_permission_denied(e):
    return render_template("handlers/403.html"), 403
```

Replace with:

```python
def _page_not_found(e):
    # The external machine-to-machine API (/api/v1) gets JSON error bodies
    # (same idiom as the session-revoked/maintenance hooks above). Gated on
    # /api/v1 -- NOT /api/ -- so the legacy internal /api/* surfaces keep
    # their current HTML behavior.
    if request.path.startswith("/api/v1"):
        return jsonify({"error": "Not found"}), 404
    return render_template("handlers/404.html"), 404


def _internal_error(e):
    if request.path.startswith("/api/v1"):
        return jsonify({"error": "Internal server error"}), 500
    return render_template("handlers/500.html"), 500


def _forbidden_page(e):
    if request.path.startswith("/api/v1"):
        return jsonify({"error": "Forbidden"}), 403
    return render_template("handlers/403.html"), 403


def _handle_permission_denied(e):
    if request.path.startswith("/api/v1"):
        return jsonify({"error": "Forbidden"}), 403
    return render_template("handlers/403.html"), 403
```

(`jsonify` and `request` are already imported at the top of `hooks.py` — verified.)

- [ ] **Step 4 — Run, expect GREEN, plus the whole hooks suite for collateral:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_hooks.py tests/integration/test_api_external_routes.py -q`
Expected: all passed (46 hooks — 42 existing + 4 new — plus 11 integration)

- [ ] **Step 5 — Commit:**

```bash
git add nx_lib/hooks.py tests/unit/test_hooks.py tests/integration/test_api_external_routes.py
git commit -F - <<'EOF'
feat(api): JSON error handlers for /api/v1 paths

Make the global 404/500/403 (+PermissionDenied) handlers in
nx_lib/hooks.py path-aware: requests under /api/v1 get a JSON error
body instead of the HTML handler pages, following the existing
request.path.startswith('/api/') idiom used by the session-revoked and
maintenance hooks in the same file. Legacy internal /api/* surfaces
keep their current HTML behavior (minimal blast radius). 405/429 keep
Flask/flask-limiter defaults -- documented gotcha, harmless for a
GET-only API.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 6 — Issuance script, docs, changelog, CLAUDE.md

### Task 6: `scripts/new-api-key.py` + `docs/howto/external-api.md` + housekeeping

**Files:**
- Create: `scripts/new-api-key.py`
- Create: `docs/howto/external-api.md`
- Modify: `CHANGELOG.md` (`[Unreleased]` → `### Added`)
- Modify: `CLAUDE.md` (Routing module list + Permissions bullet)

**Interfaces:** none downstream (docs + dev tooling). The script reuses the exact hash form `hash_api_key` produces (sha256 hexdigest) — keep them in sync (both sites carry the comment).

- [ ] **Step 1 — The issuance script.** Create `scripts/new-api-key.py`:

```python
"""Generate an external-API key: print the raw token ONCE plus the INSERT.

Dev-side only (scripts/ is excluded from the prod deploy mirror, so this
file never exists on the server). Run it, hand the token to the client over
a secure channel, then execute the printed INSERT against the target
NexoraDB (INT and/or PROD) in SSMS. The raw token is never stored
anywhere -- dbo.ApiKeys holds only its SHA-256 hex digest. The 2-line hash
below is deliberately duplicated from nx_lib/api_auth.py hash_api_key
(importing nx_lib creates DB engines at import time and requires live env
config) -- keep the two in sync.

Usage:
    python scripts/new-api-key.py --client-code default \
        --label "ACME ops dashboard" \
        --processes "sydoc.05_PDBS,compass.01_Invoice_SAP"

--processes takes full dbo.Statconfig ProcessName values (the same strings
the dashboard's dashboard.filter.process.* permission codes resolve to);
list candidates with: SELECT ProcessName FROM dbo.Statconfig.
"""

import argparse
import hashlib
import secrets


def _sq(value):
    """Escape a value for embedding in the printed T-SQL string literal."""
    return str(value).replace("'", "''")


def main():
    ap = argparse.ArgumentParser(
        description="Generate an external-API key + the dbo.ApiKeys INSERT."
    )
    ap.add_argument("--client-code", required=True, help="e.g. 'default' or 'ms02'")
    ap.add_argument("--label", required=True, help="who holds this key (audit note)")
    ap.add_argument(
        "--processes",
        required=True,
        help="comma-separated full Statconfig ProcessName values",
    )
    args = ap.parse_args()

    token = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    processes = ",".join(p.strip() for p in args.processes.split(",") if p.strip())

    print("Raw API key -- hand to the client ONCE, it is not recoverable:\n")
    print(f"    {token}\n")
    print("Run this against the target NexoraDB (SSMS, INT and/or PROD):\n")
    print("INSERT INTO dbo.ApiKeys (KeyHash, ClientCode, Label, ProcessList, Enabled)")
    print(
        f"VALUES ('{key_hash}', '{_sq(args.client_code)}', '{_sq(args.label)}', "
        f"'{_sq(processes)}', 1);"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2 — Smoke-run it** (stdlib-only, no DB, no env needed):

Run: `python scripts\new-api-key.py --client-code default --label "smoke test" --processes "a.b, c.d"`
Expected: prints a ~43-char token, then an INSERT with a 64-char hex hash and ProcessList `'a.b,c.d'`. Do NOT run the INSERT.

- [ ] **Step 3 — The howto.** Create `docs/howto/external-api.md`:

```markdown
# External API v1 (machine-to-machine)

Read-only JSON API for external clients, authenticated with per-client API
keys. One endpoint in v1. Code: routes in `nx_lib/views/api_external.py`,
auth in `nx_lib/api_auth.py`, KPI computation shared with the dashboard
(`compute_today_stats` in `nx_lib/views/dashboard.py`), table created by
`sql/_migrations/NexoraDB/0038_create_api_keys.sql`.

## Base URLs

| Environment | Base URL |
|---|---|
| PROD | `https://nexora.sydoc.ch/nexora/api/v1` |
| INT (dev server) | `http://127.0.0.1:8000/api/v1` |

PROD serves the app under the `/nexora` prefix via `PrefixMiddleware`; the
Flask routes themselves are registered unprefixed, so no code is
prefix-aware. The dev server binds port 8000 (`FLASK_RUN_PORT`).

## Authentication

Send the key as a Bearer token on every request:

    GET /api/v1/stats/today
    Authorization: Bearer <api key>

Keys are per-client rows in `dbo.ApiKeys` (NexoraDB): only the SHA-256 hash
of the key is stored, plus a client code, an audit `Label`, a
comma-separated `ProcessList` scope (full `dbo.Statconfig.ProcessName`
values, e.g. `sydoc.05_PDBS`), an `Enabled` flag and `CreatedAt` /
`LastUsedAt` stamps.

### Issuing a key (v1: manual, dev-side)

`scripts/` is not deployed to prod, so run this from a dev clone:

    python scripts/new-api-key.py --client-code <code> --label "<who holds it>" --processes "<ProcessName>,<ProcessName>"

The script prints the raw token ONCE (hand it to the client over a secure
channel; it is not recoverable) and a ready-to-run `INSERT` for
`dbo.ApiKeys`. Execute the INSERT against the target NexoraDB (INT and/or
PROD) in SSMS.

### Revoking / rotating

    UPDATE dbo.ApiKeys SET Enabled = 0 WHERE Label = '<who holds it>';

Effective on the next request (the auth path has no cache). A disabled key
answers exactly like an unknown key (401 `Invalid API key`) — deliberately
indistinguishable, so a leaked/revoked key confirms nothing. Rotation =
issue a new key, then disable the old row.

## GET /api/v1/stats/today

The dashboard's "imported today" / "processed today" KPI numbers, scoped to
the key's `ProcessList`:

    {
      "date": "2026-07-14",
      "imported_today": 123,
      "exported_today": 117,
      "processes": ["sydoc.05_PDBS"]
    }

- `date` — the **server-local** calendar date the counts refer to (the
  underlying SQL uses `GETDATE()` / `CURRENT_DATE`).
- `imported_today` — documents whose import-date column is today.
- `exported_today` — documents whose export-date column is today (the
  dashboard's `processed_today` semantics, inherited verbatim — on the
  default T-SQL leg this counts export-today among rows also imported
  today).
- `processes` — the key's scope, echoed for debugging. An empty scope
  returns zeros with `"processes": []`. Not cached: every call computes
  fresh numbers.

## Errors (JSON unless noted)

| Status | Body | Meaning |
|---|---|---|
| 401 | `{"error": "Missing or malformed Authorization header"}` | no/bad `Authorization: Bearer` header (`WWW-Authenticate: Bearer` set) |
| 401 | `{"error": "Invalid API key"}` | unknown **or disabled** key (uniform on purpose) |
| 404 | `{"error": "Not found"}` | wrong path under `/api/v1` |
| 405 | HTML (Flask default) | non-GET verb — the API is GET-only |
| 429 | HTML (flask-limiter default) | over 60 requests/minute |
| 500 | `{"error": "Stats backend unavailable"}` or `{"error": "Internal server error"}` | stats query / server failure |
| 503 | `{"error": "Auth backend unavailable"}` | NexoraDB unreachable during auth (fail closed) |
| 503 | `{"error": "Maintenance", "maintenance": {...}}` | blocking maintenance window (global lockout) |

## Operational notes

- Rate limit: 60/min per source IP, checked BEFORE authentication (so
  brute-force key guessing is throttled too), enforced in-memory per worker
  process (see the TODO in `nx_lib/extensions.py`);
  `NEXORA_DISABLE_RATELIMIT=1` disables it (tests/e2e only).
- Every hit lands in the standard CSV request log
  (`var/logs/user/YYYYMMDDHH/nexora_logs.csv`) with empty user fields —
  a free audit trail; `dbo.ApiKeys.LastUsedAt` shows last successful auth.
- No session, no cookies, no CSRF (GET-only), no i18n — error strings are
  English by design (`_()` in these modules would drag in the pybabel
  cycle for machine-facing text).
```

- [ ] **Step 4 — CHANGELOG.** In `CHANGELOG.md`, under `## [Unreleased]` → `### Added` (whatever version the block is working toward at execution time; the section's last bullet currently ends `…previously truncated).`), append:

```
- External API v1 for machine-to-machine clients: `GET /api/v1/stats/today`
  returns the dashboard's "imported today" / "processed today" KPI numbers
  as JSON, scoped per API key. Auth is `Authorization: Bearer <key>` against
  `dbo.ApiKeys` (migration `0038`; only the SHA-256 hash is stored; disabled
  keys answer like unknown ones), new decorator `require_api_key`
  (`nx_lib/api_auth.py`), 60/min rate limit checked before auth, JSON error
  handlers for `/api/v1` paths, key issuance via dev-side
  `scripts/new-api-key.py`. See `docs/howto/external-api.md`.
```

- [ ] **Step 5 — CLAUDE.md.** Two edits.

**Edit A** — Routing bullet. Find:

```
- **Routing:** Routes live in `nx_lib/views/` (`auth`, `admin`, `dashboard`, `workitems`, `chat`, `invoices`, `notifications`, `core`, `generali`, `profile`, `reporting`).
```

Replace with:

```
- **Routing:** Routes live in `nx_lib/views/` (`auth`, `admin`, `dashboard`, `workitems`, `chat`, `invoices`, `notifications`, `core`, `generali`, `profile`, `reporting`, `api_external`).
```

**Edit B** — Permissions bullet. Find:

```
`startpage_redirect_to` picks the landing route based on which perms the user has.
```

Replace with:

```
`startpage_redirect_to` picks the landing route based on which perms the user has. The external machine-to-machine API (`/api/v1/*`, `nx_lib/views/api_external.py`) bypasses sessions and permission codes entirely — it authenticates per-client API keys from `dbo.ApiKeys` (migration `0038`) via `require_api_key` in `nx_lib/api_auth.py` (`Authorization: Bearer`, SHA-256-hashed keys, per-key process scope, uniform 401 for unknown/disabled keys, rate limit checked before auth); see `docs/howto/external-api.md`.
```

- [ ] **Step 6 — Commit:**

```bash
git add scripts/new-api-key.py docs/howto/external-api.md CHANGELOG.md CLAUDE.md
git commit -F - <<'EOF'
docs(api): external API howto, key-gen script, changelog

Add docs/howto/external-api.md (base URLs incl. the PROD /nexora
prefix and the port-8000 dev server, Bearer auth, response shape,
error table, issuance/revocation, operational notes),
scripts/new-api-key.py (prints the raw token once plus the
ready-to-run INSERT; dev-side only, scripts/ is not deployed; hash
logic kept in sync with nx_lib/api_auth.hash_api_key), the CHANGELOG
entry under [Unreleased], and the CLAUDE.md touches (api_external in
the Routing module list; API-key auth note in the Permissions bullet).
No deploy.yml change needed: docs/ and scripts/ are already excluded
from the prod mirror and nx_lib/ ships by default.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 7 — Full gate + live verification on INT

### Task 7: Full local test gate

**Files:** none (verification only).

- [ ] **Step 1 — Reset the TEST DB** (schema changed in Task 1; stale state also breaks order-dependent tests):

Run: `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py`

- [ ] **Step 2 — Full non-e2e tiers** (make sure `NEXORA_DISABLE_RATELIMIT` is NOT set in the shell — the 429 test needs the limiter active):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests --ignore=tests/e2e -q`
Expected: all passed, 0 failed (count grows by 30 new tests: 4 in Task 2, 11 in Task 3, 9 in Task 4, 4 + 2 in Task 5)

- [ ] **Step 3 — Translation guard** (proves the zero-new-msgid claim):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_translations.py -q`
Expected: all passed

- [ ] **Step 4 — `git log --oneline -8`** and confirm the six commits from Tasks 1–6 are present, in order, on `plan/external-api-v1-today-stats`. Nothing to commit in this task. (The e2e tier is untouched by this feature — no templates/JS — and runs in the owner's pre-push gate; if you run it anyway, `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py` first.)

### Task 8: Live verification on INT (curl against the running dev server)

**Files:** none (verification only; the throwaway script goes in your session scratchpad, NEVER the repo). This is a JSON API — no browser, no screenshots.

**Prereq:** migration `0038` was applied to INT in Task 1 Step 5. `env/INT.env` exists in the worktree (Task 1 Step 1).

- [ ] **Step 1 — Write ONE throwaway admin script to your scratchpad directory** (NOT the repo) as `temp_key_admin.py`. All Task 8 DB touches go through it — python `-c` one-liners with `\"` escapes are NOT executable under PowerShell (red-team-verified SyntaxError), and this script sets `ENVIRONMENT` internally so no shell env var is ever set:

```python
# throwaway admin for the live-verify TEMP key on INT (delete key after Task 8!)
# usage: python temp_key_admin.py list | issue <ProcessName> | status | disable | delete
import os
import sys

os.environ["ENVIRONMENT"] = "INT"
sys.path.insert(0, r"C:\dev\nexora\.claude\worktrees\plan-external-api-v1-today-stats")

import hashlib
import secrets

from nx_lib.db import engine_nexora_db

LABEL = "live-verify TEMP - delete me"
cmd = sys.argv[1]
conn = engine_nexora_db.raw_connection()
cur = conn.cursor()
if cmd == "list":
    cur.execute("SELECT ProcessName, ClientCode FROM dbo.Statconfig")
    for r in cur.fetchall():
        print(r.ProcessName, "|", r.ClientCode)
elif cmd == "issue":
    token = secrets.token_urlsafe(32)
    cur.execute(
        "INSERT INTO dbo.ApiKeys (KeyHash, ClientCode, Label, ProcessList) "
        "VALUES (?, 'default', ?, ?)",
        [hashlib.sha256(token.encode("utf-8")).hexdigest(), LABEL, sys.argv[2]],
    )
    conn.commit()
    print("token:", token)
elif cmd == "status":
    cur.execute("SELECT LastUsedAt, Enabled FROM dbo.ApiKeys WHERE Label = ?", [LABEL])
    print(cur.fetchone())
elif cmd == "disable":
    cur.execute("UPDATE dbo.ApiKeys SET Enabled = 0 WHERE Label = ?", [LABEL])
    conn.commit()
    print("disabled")
elif cmd == "delete":
    cur.execute("DELETE FROM dbo.ApiKeys WHERE Label = ?", [LABEL])
    conn.commit()
    print("deleted")
conn.close()
```

Run it with the test venv interpreter (has pyodbc): `C:\dev\nexora\.venv\Scripts\python <scratchpad>\temp_key_admin.py list` — note one real `ProcessName` (ideally a `default`-client one; pick an `ms02` one too if you want to exercise the PG leg).

- [ ] **Step 2 — Issue a TEMP key on INT:**

Run: `C:\dev\nexora\.venv\Scripts\python <scratchpad>\temp_key_admin.py issue <ProcessName>`
Expected: prints `token: <~43 chars>` — record it.

- [ ] **Step 3 — Start the WORKTREE's dev server** (the main clone's `nx -u` would run code WITHOUT this feature — the worktree server is mandatory). From the worktree root, in a background job, with the GLOBAL interpreter (the dev-server convention; the uv venv is test-only and may drift):

```powershell
$env:ENVIRONMENT='INT'; python nx_main.py
```

Note the bound URL from the startup log — **default `http://127.0.0.1:8000`** (`nx_main.py` reads `FLASK_RUN_PORT`, default `"8000"`); adjust the URLs below if different. (Setting `$env:ENVIRONMENT` inside one tool call does not leak — each call is a fresh shell.)

- [ ] **Step 4 — Exercise the endpoint with curl** (substitute the token):

```powershell
curl.exe -s -i -H "Authorization: Bearer <token>" http://127.0.0.1:8000/api/v1/stats/today
```

Expected: `200`, `Content-Type: application/json`, body with today's `date`, non-negative integer `imported_today`/`exported_today`, and `"processes": ["<ProcessName>"]`. Then the negatives:

```powershell
curl.exe -s -i http://127.0.0.1:8000/api/v1/stats/today                                                  # 401 JSON + WWW-Authenticate: Bearer
curl.exe -s -i -H "Authorization: Bearer garbage-token" http://127.0.0.1:8000/api/v1/stats/today         # 401 {"error":"Invalid API key"}
curl.exe -s -i http://127.0.0.1:8000/api/v1/nope                                                         # 404 {"error":"Not found"} (JSON)
```

- [ ] **Step 5 — LastUsedAt + disable → uniform 401:**

Run: `C:\dev\nexora\.venv\Scripts\python <scratchpad>\temp_key_admin.py status`
Expected: a non-NULL `LastUsedAt` and `Enabled = True`. Then:

```powershell
C:\dev\nexora\.venv\Scripts\python <scratchpad>\temp_key_admin.py disable
curl.exe -s -i -H "Authorization: Bearer <token>" http://127.0.0.1:8000/api/v1/stats/today   # 401 {"error":"Invalid API key"} -- disabled == unknown
```

- [ ] **Step 6 — Cleanup (mandatory):** delete the temp key and stop the server:

Run: `C:\dev\nexora\.venv\Scripts\python <scratchpad>\temp_key_admin.py delete`
Stop the background server job. Nothing to commit. Paste the four curl outputs (status lines + JSON bodies, token redacted) into the completion report; optional sanity: the 200 payload's numbers should be plausible vs the INT dashboard for the chosen process.

---

## Gotchas & notes

- **Decorator order is a security property, not style:** `@limiter.limit("60 per minute")` must stay OUTERMOST (above `@require_api_key`). flask-limiter 3.12 enforces decorated limits inside the limit wrapper (`_check_request_limit(in_middleware=False)`; `resolve_limits` skips decorated limits during the middleware pass), so auth-outermost would (a) leave every 401 path — the brute-force surface, each a full `dbo.ApiKeys` scan — unthrottled, and (b) make `test_rate_limit_429_for_unauthenticated_requests` permanently red. Red-team verified both orders empirically against the pinned flask-limiter 3.12. This deliberately diverges from `reporting.py`'s `@require_permission`-over-`@limiter.limit` stack (fine there: those routes sit behind a session).
- **Do NOT move the dashboard helpers.** `tests/unit/test_dashboard_stats.py` and `tests/integration/test_dashboard_routes.py` monkeypatch `dv.engine_nexora_db`, `dv.engine_statistics_db`, `dv._ms02_stat_rows`, `dv.total_backlog_count` as attributes of `nx_lib.views.dashboard`, and call `dv.dashboard_kpi_stats.uncached()` (flask-caching exposes the raw view as `.uncached`). `compute_today_stats` must live in that module and reference those names as module globals — that is exactly why D9 rejects a "cleaner" new module.
- **JSON-shape quirk to preserve:** the dashboard's no-scope early return includes `"processed_week": 0` but the success payload does not. `test_kpi_stats_authed_returns_zeros` pins the 4-key zero shape exactly — leave the early return byte-for-byte alone during Task 2.
- **The extracted function must RAISE on Statconfig failure.** Zero-filling there would make the dashboard cache zeros for 60s on a NexoraDB blip — today the 500 is deliberately NOT cached (`response_filter=_cacheable_response`). The two stat-row legs, by contrast, swallow their own errors by design (each leg degrades independently). `test_compute_today_stats_raises_when_nexora_db_down` pins this.
- **Auth fails CLOSED (503), stats fail OPEN per leg** — two different philosophies in one feature, both deliberate: an auth DB error must never admit a request (or 401 a valid key), while a dead Statistics DB should still serve the healthy MS02 leg's numbers.
- **Uniform 401 for disabled keys is deliberate (D6):** the lookup filters `WHERE Enabled = 1`, so revoked keys are indistinguishable from never-issued ones — no existence oracle. Do not "improve" it into a 403; the howto's revocation section explains the tradeoff to the owner.
- **`exported_today` leg asymmetry is inherited, not a bug:** the default T-SQL leg's `WHERE CAST({col_import} as date) = cast(GETDATE() as date)` means export-today is counted only among import-today rows; the MS02 `COUNT(*) FILTER` leg counts unconditionally. The locked scope says "the dashboard's processed_today semantics" — ship verbatim so API and dashboard always agree (Owner action 4 owns any future change).
- **Test-DB visibility trap:** rows written through the `db_conn` fixture are rolled back AND invisible to the app's `raw_connection()`s — the integration tests commit real `dbo.ApiKeys` rows and delete them in `finally`. If a crashed run leaves orphan rows (`Label = 'pytest temp key'`), they are harmless (unknown random hashes) and vanish on the next `test_db_reset.py` — the reset drops and recreates ApiKeys because Task 1 added BOTH the drop-list line and the guarded CREATE (a CREATE-only mirror would never clean or re-shape the table).
- **`import pytest` placement (ruff isort):** it goes directly ABOVE `from flask import session` in `tests/unit/test_dashboard_stats.py` — verified with `ruff check --select I`. Anywhere else in that block fails `I001`; the ruff hook runs `--fix --exit-non-zero-on-fix`, so a wrong placement fails the commit once — re-`git add` the fixed file and re-run the same commit command.
- **Rate limiter reality:** `limiter = Limiter(key_func=get_remote_address)` — 60/min per source IP, in-memory **per IIS FastCGI worker** (the `extensions.py` TODO documents this; locked scope accepts it). The autouse `_reset_rate_limiter` fixture resets before every test; the e2e conftest sets `NEXORA_DISABLE_RATELIMIT=1` in its own subprocess only — never set it in the shell running the non-e2e suite or the 429 test fails. 429 and 405 responses keep default HTML bodies — status code is the machine-readable part; documented in the howto, deliberately not handled (YAGNI). Per-key limits would need a custom `key_func` — out of v1 scope.
- **POST behavior differs by env, refusal doesn't:** in the suite `WTF_CSRF_ENABLED=False` so a POST gets Flask's 405; in PROD the CSRF before_request guard may answer 400 first. Either way mutating verbs never reach the view — the 405 test pins the suite behavior only.
- **Maintenance lockout applies to `/api/v1`:** it is not in `_MAINTENANCE_LOCKOUT_SKIP_PATHS`, and the hook's existing `/api/` branch already returns `503` JSON — locked scope says leave as-is; the howto documents it for the client.
- **PROD prefix is free:** `PrefixMiddleware` sets `SCRIPT_NAME` under `/nexora`, so `request.path` stays prefix-stripped (`/api/v1/...`) and every `startswith` check keeps working; routes register unprefixed. The external base URL `https://nexora.sydoc.ch/nexora/api/v1/...` appears only in docs.
- **Dev server = global Python on port 8000.** `nx_main.py` defaults `FLASK_RUN_PORT` to `"8000"` and the dev-server convention is the GLOBAL interpreter (the uv `.venv` is test-only and periodically drifts from requirements.txt — "works in script, fails in server"). Task 8 must run the WORKTREE's server (`python nx_main.py` from the worktree root); the main clone's `nx -u` serves code without this feature until the owner merges. Venv interpreter is the fallback if global misbehaves.
- **No i18n, on purpose:** zero `_()` calls in `api_auth.py`/`api_external.py`/the hooks branches. `babel.cfg` DOES scan `nx_lib/**.py`, so one stray `_()` breaks `test_pot_is_in_sync` until the full `/nx-i18n` cycle is run. The dashboard's `_("Not authorized")` stays where it is (existing msgid, untouched).
- **`test_create_app.py` endpoint pin tolerates the new endpoint:** `EXPECTED_NON_GENERALI_ENDPOINTS` treats extras as informational (only `missing` fails) — do not add `api_v1_stats_today` to that set.
- **Coverage ledger:** `tests/unit/test_coverage_thresholds.py` `MIN_COVERAGE` reports as a skip in-suite; adding an entry for `views/api_external.py` is optional housekeeping, deliberately omitted.
- **Bearer greenfield confirmed:** all 11 `Bearer` hits in `nx_lib` are OUTBOUND request headers (Octo/Graph/Bexio); no `/api/v1` string exists in any `.py` — `require_api_key` collides with nothing.
- **`KeyHash CHAR(64)`:** sha256 hex is exactly 64 ASCII chars, so no padding ever occurs; `_match_key` still `.strip()`s defensively. The UNIQUE constraint doubles as a duplicate-issuance guard.
- **PowerShell quoting for `python -c`:** backslash-escaped quotes (`\"`) are NOT an escape in PowerShell and produce Python SyntaxErrors. The only `-c` one-liner in this plan (Task 1 Step 6) uses exclusively single quotes inside the outer double quotes — safe in both shells. Everything else DB-touching goes through the Task 8 scratchpad script, which sets `ENVIRONMENT` via `os.environ` internally (memory rule: never leave shell env vars set).
- **Two interpreters, one rule:** `C:\dev\nexora\.venv\Scripts\python` for pytest, `test_db_reset.py` and the scratchpad script (full test deps incl. pyodbc); plain `python` (global) for `db-migrate.py`/`sync-from-db.py`/`new-api-key.py`/the dev server — the same resolution the pre-commit hooks and `nx` use.
- **Commit trailer:** repo history stamps the model that actually ran the work. The blocks above use `Claude Sonnet 5` for the declared Sonnet executor — substitute the real name if a different model executes. Never copy a planning-model name into an execution commit.
- **`Statconfig` vs `dbo.StatConfig.sql` casing:** the code queries `FROM Statconfig` while the committed dump file is `dbo.StatConfig.sql` (capital C) — known, deliberate, don't "fix" it while extracting.
- **Confluence sync is red** (known cred/seat issue) — a failed `confluence-docs.yml` run after merge is not this feature's failure.
