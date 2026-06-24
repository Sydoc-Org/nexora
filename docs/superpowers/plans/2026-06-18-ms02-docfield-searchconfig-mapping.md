# MS02 Doc-Field Search via SearchConfig Mapping — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop MS02 doc-field (document-field) search from running an in-query `EXISTS` straight against MS02's own runtime table `"t_DocumentIndexes"`. Route it through nexora's normal mapping layer (`dbo.SearchConfig`, made source/dialect-aware) and resolve the matched field VALUE against a *dedicated* MS02 Azure-Postgres doc-field database (a new `engine_ms02_docfields_pg`, NOT the runtime DB, NOT the on-prem StatisticsDB). Because that doc-field DB is a separate Postgres database (a PG connection binds to one database), matches are **pre-resolved to a workitem-ID allow-set** and applied to the runtime query as `twi."ID" = ANY(%s)`, exactly mirroring the default source's `docfield_ids` pattern. No ETL, no ingestion pipeline. The default single-source path stays byte-identical.

**Architecture:** `dbo.SearchConfig` gains a `ClientCode` column (default `'default'`, migration `0027`) — the same routing convention already used for `dbo.Statconfig.ClientCode` (migration `0024`). The orchestrator `_get_workitems_data` (in `nx_lib/views/workitems.py`) leaves the existing default-source `SearchConfig → StatisticsDB → docfield_ids` block **literally untouched** (byte-identical) and adds a **sibling** block: for MS02-mapped processes it reads each `col_<field>` as an EAV `"Name"` VALUE, builds literal `(name, value)` pairs in the view (where the `col_<field>` whitelist already lives), and hands them to ONE small pure seam — `resolve_ms02_docfield_ids(engine, pairs)` in `nx_lib/workitem_sources.py` — which queries `engine_ms02_docfields_pg` (`WHERE "Name" IN (...) AND "StringValue" LIKE %value%`) and returns a *separate* `ms02_docfield_ids` allow-set under the canonical three-way contract (None = no constraint; empty = force zero rows; populated = ID set). `PostgresSource._build_where` deletes the `"t_DocumentIndexes"` `EXISTS` loop and consumes that set via `twi."ID" = ANY(%s)`, identical to the `resolve_nexora_filter_ids` allow-set already there. The one extracted seam is justified because it is the single place that touches the new doc-field engine, it is purely unit-testable on mocked cursors (no live DB in CI), and it keeps `workitem_sources` free of any `views` import (no import cycle). The new engine degrades to `None` until `MS02_DOCFIELDS_DB_*` env vars are set, same as `engine_ms02_pg` / `engine_ms02_stats_pg`.

**Tech Stack:** Python 3, Flask, SQLAlchemy 2.0 + pyodbc (SQL Server) + psycopg2-binary (Postgres, already a dependency), pytest (unit + integration).

**Design spec:** `docs/superpowers/specs/2026-06-16-ms02-client-merged-workitems-design.md`. **This plan SUPERSEDES section 4.6** of that spec (the live heading is `### 4.6 Doc-field search is per source (`t_documentindexes`)`) and the summary-table row at ~line 116 — both currently document the now-reversed in-query-`EXISTS` decision. A task here updates them; do not silently diverge from the committed spec.

---

## Context an engineer needs (read first)

- **Branch:** `feature/2.5.63`. This work STACKS on the unpushed MS02 multi-source work already on this branch (`engine_ms02_pg`, `clients.py`, `PostgresSource`, migrations `0023`–`0026`). Do NOT branch off `main`; commit onto `feature/2.5.63`.
- **Remote session = commit only.** Commits are allowed on this feature branch, but **do not push and do not open a PR** — the owner does that after local review. The last step of every task stops at `git commit`.
- **Anchor on snippets, never line numbers.** Every "find X" step below quotes the exact code to locate; line numbers in this plan are reading aids and will drift.
- **Migrations needed: yes.** One new file `sql/_migrations/NexoraDB/0027_searchconfig_ms02_docfields.sql` (verified next free number — the directory tops out at `0026_ms02_praesidialdepartement_workitems_process.sql`). It (a) adds `dbo.SearchConfig.ClientCode` and (b) seeds MS02 rows (INSERT left commented pending owner values). **Re-list `sql/_migrations/NexoraDB/` at execution to confirm `0027` is still free** (the underlying MS02 branch may have added more) and bump if needed. NEVER hand-edit `sql/NexoraDB/Tables/dbo.SearchConfig.sql` (auto-generated from INT by `sync-from-db.py`) — the migration regenerates it.
- **Pre-commit hook escape hatch:** the `sql-migrate-int` hook auto-applies the migration to INT. On Windows it can flake on stale CRLF checksums for migrations `0001`–`0003` (known INT drift). If it fails on checksum drift (not a real SQL error), commit with `SQL_SYNC_SKIP=1 git commit ...`. NEVER use `--no-verify`. Make the migration idempotent (`IF NOT EXISTS` guards) so the hook can re-apply it safely.
- **i18n needed?** No. This change is backend-only (engine + resolver + mapping). No new user-facing strings, no `pybabel` cycle. The optional autocomplete task returns data, not new translatable strings.
- **Template-cache restart?** Not needed — no template or JS partial changes on any path here. (If you smoke-test in the browser, restart the dev server first — Jinja templates are cached process-lifetime — but no template edits are required.)
- **TEST / CI has NO Statistics DB and NO MS02 engines.** `engine_ms02_docfields_pg` is `None` in CI. Every new test must tolerate `engine is None` and empty result sets; SQL-builder unit tests assert on generated SQL/params via mocked cursors, never a live connection. The integration harness already tolerates `(200, 500)` because routes can legitimately 500 when engines are absent (see `test_api_workitems_returns_degraded_key` → `assert resp.status_code in (200, 500)`). The pre-push gate runs the full suite including Playwright e2e — run `python scripts/test_db_reset.py` first if e2e order-dependent state is stale.
- **Integration-test fixtures (verified live):** the logged-in client is `user_client`; full workitems perms come from `workitems_all_perms`; a no-permission client is `noperm_client`. Do NOT use `client`, `client_logged_in`, or `client` — they do not exist and error at collection.
- **The single-source DEFAULT path must stay byte-identical.** `docfield_ids` (StatisticsDB-resolved, SQL-Server-only), the `SqlServerSource` branch, and the default SearchConfig rows must not change behavior. The new `ClientCode` column DEFAULTs to `'default'` so existing rows behave exactly as today, and the existing default docfield loop is left untouched (a sibling block is added beside it).
- **No new dependency** (`psycopg2-binary` already in `requirements.txt`, used by `engine_ms02_pg`). **No new top-level file/dir** — the change lives entirely inside already-tracked/excluded dirs (`nx_lib/`, `sql/`, `docs/`, `tests/`, `env/*.env.example`), so `deploy.yml` `/XF`/`/XD` needs no change.
- **No new permission** and **no `page_visibility()` change.** Doc-field search is already gated by `workitems.filter.documentfields`; the MS02 process visibility perm already exists from migration `0026`.

---

## Decisions locked in

| # | Decision | Detail |
|---|---|---|
| 1 | **Mapping table = reuse `dbo.SearchConfig`** (NexoraDB). Do NOT invent a new table. | Extend it source/dialect-aware: add `ClientCode NVARCHAR(50) NOT NULL DEFAULT 'default'` (mirrors `dbo.Statconfig.ClientCode`, migration `0024`) and seed MS02 process rows. The column name MUST NOT start with `col_` so `get_valid_search_columns()` ignores it. |
| 2 | **SearchConfig drives the search; the field VALUE is resolved against an MS02 Postgres DB.** NO ETL / NO ingestion. | NexoraDB `SearchConfig` is the mapping for every client; it tells the resolver which doc-field `"Name"` to match. The actual value match runs live against the MS02 doc-field Postgres DB — NOT the on-prem StatisticsDB. Nothing is copied into StatisticsDB. |
| 3 | **Value DB = same Azure host/login as the MS02 runtime (`MS02_DB_*`), DIFFERENT dbname.** | Scaffold exactly ONE new engine `engine_ms02_docfields_pg` bound to that dbname, with new `MS02_DOCFIELDS_DB_*` env vars whose HOST/USER/PWD/PORT/TLS defaults reuse the MS02 runtime values; only `MS02_DOCFIELDS_DB_NAME` differs and has **no default** (engine stays `None` until set — same graceful-degrade as `engine_ms02_pg` / `engine_ms02_stats_pg`). |
| — | **EAV-vs-columnar crux** | For DEFAULT rows `col_<field>` holds a StatisticsDB physical COLUMN name (`WHERE CAST(alias.column ...) LIKE ?`). For MS02 (an EAV `"Name"`/`"StringValue"` index) `col_<field>` holds the doc-field **`"Name"` VALUE to match** (`WHERE "Name" = <col_field value> AND "StringValue" LIKE %value%`). `ClientCode` is the switch that selects the resolution path + engine. |
| — | **Cross-DB constraint** | The doc-field DB is a separate Postgres database from the MS02 runtime DB; a single PG connection binds to one database, so you CANNOT join them in one query. The resolver MUST pre-resolve to a workitem-ID allow-set and constrain the runtime query with `twi."ID" = ANY(%s)`. MS02 workitem IDs are globally unique (established by the multi-source design). |
| — | **Graceful degrade** | If `engine_ms02_docfields_pg` is `None`, or no `SearchConfig` row maps the MS02 process/field, doc-field search imposes **NO** constraint for MS02 and never errors the page — mirror the **default docfield block's** `if matching_ids is None: continue` behaviour. |
| — | **Default path byte-identical** | This change is MS02-only. `docfield_ids` (the StatisticsDB-resolved set consumed by `SqlServerSource`) and the SQL Server source's SQL must not change. Add a *separate* `WorkitemFilter.ms02_docfield_ids` field; never overload `docfield_ids`. |

---

## Owner actions (build-time confirmations — do NOT fabricate)

These are owner-provided and must be supplied before MS02 doc-field search becomes live. Until they are, the engine stays `None` and search degrades to no-constraint (the page still renders).

1. **Doc-field VALUE database NAME** on the MS02 Azure host (a different dbname from the runtime DB and from `Praesidialdepartement_BS`). Set `MS02_DOCFIELDS_DB_NAME` in the gitignored `env/INT.env` and `env/PROD.env`.
2. **Doc-field index TABLE name and COLUMN names** in that DB. Likely PascalCase double-quoted `"WorkItemID"` / `"Name"` / `"StringValue"` (mirroring the old runtime `"t_DocumentIndexes"`), but this is a DIFFERENT database — CONFIRM the exact table + column identifiers + casing. They feed the `_MS02_DOCFIELD_*` constants in Task 5 (one place); change them there only if the confirmed names differ.
3. **The MS02 doc-field `"Name"` strings + which `col_<field>` each maps to**, for the `0027` seed INSERT (left commented in the migration). E.g. is the searchable "barcode" field's EAV `"Name"` literally `"Barcode"`?
4. **Whether the UI doc-field identifier equals the EAV `"Name"`** or needs a name-mapping (spec §4.6 flags this). The `col_<field>` mechanism IS that mapping (UI sends `field=barcode` → `col_barcode` → its seeded EAV `"Name"` value) — confirm the seeded values.
5. **The MS02 `SearchConfig.ProcessName` key.** It MUST be the `'<client>.<process>'` form `target_processes` carries (e.g. `'sydoc.praesidialdepartement_bs'`, the same key used in the `0025` Statconfig seed). Confirm the exact value for the live MS02 process. A WRONG key means the resolver finds no config row → no constraint → search silently returns ALL MS02 rows.
6. **EAV `"Name"` value width.** `dbo.SearchConfig.col_<field>` columns are `varchar(100)`. Confirm each owner-provided EAV `"Name"` fits in 100 chars. If any exceeds it, the migration must also widen the relevant `col_<field>` column (a separate `ALTER`), which will also change the auto-generated `dbo.SearchConfig.sql` — flag it.
7. **Multi-process OR-vs-AND semantics.** With one MS02 process today this is moot. If MS02 later has multiple processes mapping the SAME field, the resolver's chosen semantics are: **OR within a field** (`"Name" IN (...)` across the mapped values) then **AND across distinct fields**. If the owner wants different semantics, change `resolve_ms02_docfield_ids` and its test. Confirm.
8. **Workitem-ID type compatibility.** Confirm the doc-field DB's `WorkItemID` column joins cleanly to the runtime `twi."ID"` (same type/representation; globally unique per the multi-source design), since the allow-set is applied as `twi."ID" = ANY(%s)` on the runtime DB.
9. **PROD ops:** `psycopg2-binary` already on the prod interpreter (existing MS02 obligation); set `MS02_DOCFIELDS_DB_*` in `env/PROD.env`; migration `0027` auto-applies via the deploy workflow. Optionally set `MS02_DB_SSLMODE=verify-full` + `MS02_DB_SSLROOTCERT` once the Azure root-CA bundle is on the host — the new engine reuses those same MS02 TLS knobs.

---

# PHASE 1 — Config keys + new engine (graceful-degrade)

### Task 1: Add `MS02_DOCFIELDS_DB_*` config keys

**Files:**
- Modify: `nx_lib/config.py` (immediately after the `MS02_STATS_DB_*` block, ending at the `MS02_STATS_DB_PORT = ...` line)
- Modify: `env/INT.env.example`, `env/PROD.env.example`, `env/STAGING.env.example`, `env/TEST.env.example`
- Test: `tests/unit/test_config_ms02_docfields.py` (create)

**Interfaces:**
- Produces: `cfg.MS02_DOCFIELDS_DB_HOST/NAME/USER/PWD/PORT` (str|None).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_config_ms02_docfields.py
"""MS02 doc-field DB config keys exist and default sanely.

The doc-field DB reuses the MS02 runtime host/login; only the dbname differs and
has NO default (engine degrades to None until the owner sets it).
"""

import os

from nx_lib import config as cfg


def test_ms02_docfields_keys_exist():
    for name in (
        "MS02_DOCFIELDS_DB_HOST",
        "MS02_DOCFIELDS_DB_NAME",
        "MS02_DOCFIELDS_DB_USER",
        "MS02_DOCFIELDS_DB_PWD",
        "MS02_DOCFIELDS_DB_PORT",
    ):
        assert hasattr(cfg, name), f"missing config.{name}"


def test_ms02_docfields_name_has_no_default():
    # The doc-field dbname must NOT default to a fabricated value: when the env
    # var is unset the engine has to stay None. (Env-conditional so a box that
    # HAS it set still passes.)
    if not os.environ.get("MS02_DOCFIELDS_DB_NAME"):
        assert cfg.MS02_DOCFIELDS_DB_NAME is None


def test_ms02_docfields_host_defaults_to_runtime_host():
    # HOST/USER/PWD/PORT default to the MS02 runtime values.
    assert cfg.MS02_DOCFIELDS_DB_HOST == cfg.MS02_DB_HOST
    assert cfg.MS02_DOCFIELDS_DB_USER == cfg.MS02_DB_USER
    assert cfg.MS02_DOCFIELDS_DB_PORT == cfg.MS02_DB_PORT
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_config_ms02_docfields.py -v`
Expected: FAIL — `AttributeError` on the missing `MS02_DOCFIELDS_DB_*` attributes.

- [ ] **Step 3: Add the config block**

In `nx_lib/config.py`, find the end of the `MS02_STATS_DB_*` block (the line `MS02_STATS_DB_PORT = os.environ.get("MS02_STATS_DB_PORT", MS02_DB_PORT)`) and insert directly after it:

```python

# MS02 doc-field index DB (separate Postgres DB on the same Azure host/login as
# the MS02 runtime DB, but a DIFFERENT database name). A PG connection is bound
# to one database, so the doc-field index needs its own engine. Defaults reuse
# the MS02_DB_* server/login/port/TLS; ONLY the dbname differs and has NO safe
# default -- the owner supplies MS02_DOCFIELDS_DB_NAME, so until it is set the
# engine (Task 2) degrades to None and MS02 doc-field search stays a no-op.
MS02_DOCFIELDS_DB_HOST = os.environ.get("MS02_DOCFIELDS_DB_HOST", MS02_DB_HOST)
MS02_DOCFIELDS_DB_NAME = os.environ.get("MS02_DOCFIELDS_DB_NAME")
MS02_DOCFIELDS_DB_USER = os.environ.get("MS02_DOCFIELDS_DB_USER", MS02_DB_USER)
MS02_DOCFIELDS_DB_PWD = os.environ.get("MS02_DOCFIELDS_DB_PWD", MS02_DB_PWD)
MS02_DOCFIELDS_DB_PORT = os.environ.get("MS02_DOCFIELDS_DB_PORT", MS02_DB_PORT)
```

- [ ] **Step 4: Add the sanitised env-example block (all four files)**

In each of `env/INT.env.example`, `env/PROD.env.example`, `env/STAGING.env.example`, `env/TEST.env.example`, immediately after the `MS02_STATS_DB_PORT=...` line (match each file's existing MS02 layout; if a file lacks the `MS02_STATS_DB_*` block, append after the last MS02 line present), add:

```ini
# MS02 doc-field index DB (separate Postgres DB on the same host).
# Defaults reuse the MS02 runtime host/login; only the dbname differs and has
# NO default -- set MS02_DOCFIELDS_DB_NAME to enable MS02 doc-field search.
MS02_DOCFIELDS_DB_HOST=
MS02_DOCFIELDS_DB_NAME=
MS02_DOCFIELDS_DB_USER=
MS02_DOCFIELDS_DB_PWD=
MS02_DOCFIELDS_DB_PORT=5432
```

- [ ] **Step 5: Run the test green**

Run: `python -m pytest tests/unit/test_config_ms02_docfields.py -v`
Expected: PASS.

- [ ] **Step 6: ruff + commit**

```bash
ruff check nx_lib/config.py tests/unit/test_config_ms02_docfields.py
ruff format nx_lib/config.py tests/unit/test_config_ms02_docfields.py
git add nx_lib/config.py env/INT.env.example env/PROD.env.example env/STAGING.env.example env/TEST.env.example tests/unit/test_config_ms02_docfields.py
git commit -m "feat(config): add MS02_DOCFIELDS_DB_* env keys for the doc-field index DB"
```

Commit body:
```
The MS02 doc-field index lives in its own Postgres database on the same Azure
host/login as the MS02 runtime DB. HOST/USER/PWD/PORT/TLS default to the
MS02_DB_* runtime values; only the dbname differs and has no default, so the
engine degrades to None until MS02_DOCFIELDS_DB_NAME is provisioned. Mirrors
the MS02_STATS_DB_* block.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

### Task 2: Scaffold `engine_ms02_docfields_pg`

**Files:**
- Modify: `nx_lib/db.py` (immediately after the `engine_ms02_stats_pg` block, which ends `else:` / `engine_ms02_stats_pg = None`)
- Test: `tests/unit/test_db_ms02_docfields_engine.py` (create)

**Interfaces:**
- Produces: `nx_lib.db.engine_ms02_docfields_pg` (SQLAlchemy `Engine` | `None`).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_db_ms02_docfields_engine.py
"""engine_ms02_docfields_pg exists and degrades to None without its dbname."""

import nx_lib.db as db
from nx_lib import config as cfg


def test_engine_attr_exists():
    # The symbol must always be importable (value may be None in CI/TEST).
    assert hasattr(db, "engine_ms02_docfields_pg")


def test_engine_none_when_dbname_absent():
    # On CI/dev without MS02_DOCFIELDS_DB_NAME the engine must be None
    # (graceful-degrade, same as engine_ms02_pg / engine_ms02_stats_pg).
    if not cfg.MS02_DOCFIELDS_DB_NAME:
        assert db.engine_ms02_docfields_pg is None


def test_engine_is_none_or_engine():
    eng = db.engine_ms02_docfields_pg
    assert eng is None or hasattr(eng, "raw_connection")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_db_ms02_docfields_engine.py -v`
Expected: FAIL — `AttributeError: module 'nx_lib.db' has no attribute 'engine_ms02_docfields_pg'`.

- [ ] **Step 3: Add the engine block**

In `nx_lib/db.py`, find the end of the `engine_ms02_stats_pg` block (the `else:` / `engine_ms02_stats_pg = None` lines, just before the `# Read-only engine for the Reporting live-SQL sandbox.` comment) and insert directly after it:

```python

# MS02 doc-field index DB (separate Postgres DB on the same Azure host/login as
# the MS02 runtime DB). A PG connection is bound to one database, so the
# doc-field index needs its own engine -- a third MS02 engine alongside the
# runtime (engine_ms02_pg) and dashboard-stats (engine_ms02_stats_pg) ones.
# Same graceful-degrade pattern; reuses the MS02 TLS settings. Doc-field search
# pre-resolves matches against this DB into a workitem-ID allow-set (it is never
# joined in-query to the runtime DB).
if (
    cfg.MS02_DOCFIELDS_DB_HOST
    and cfg.MS02_DOCFIELDS_DB_NAME
    and cfg.MS02_DOCFIELDS_DB_USER
    and cfg.MS02_DOCFIELDS_DB_PWD
):
    engine_ms02_docfields_pg = create_engine(
        get_pg_url(
            cfg.MS02_DOCFIELDS_DB_HOST,
            cfg.MS02_DOCFIELDS_DB_NAME,
            cfg.MS02_DOCFIELDS_DB_USER,
            cfg.MS02_DOCFIELDS_DB_PWD,
            cfg.MS02_DOCFIELDS_DB_PORT,
            sslmode=cfg.MS02_DB_SSLMODE,
            sslrootcert=cfg.MS02_DB_SSLROOTCERT,
        ),
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )
else:
    engine_ms02_docfields_pg = None
```

- [ ] **Step 4: Run the test green**

Run: `python -m pytest tests/unit/test_db_ms02_docfields_engine.py -v`
Expected: PASS (engine is `None` in TEST; symbol exists).

- [ ] **Step 5: ruff + commit**

```bash
ruff check nx_lib/db.py tests/unit/test_db_ms02_docfields_engine.py
ruff format nx_lib/db.py tests/unit/test_db_ms02_docfields_engine.py
git add nx_lib/db.py tests/unit/test_db_ms02_docfields_engine.py
git commit -m "feat(db): add engine_ms02_docfields_pg for the MS02 doc-field index DB"
```

Commit body:
```
Clone the engine_ms02_stats_pg block for a third MS02 Postgres engine bound to
the doc-field index DB, because a PG connection binds to one database. Same
graceful-degrade pattern: stays None until MS02_DOCFIELDS_DB_NAME is
configured, so dev/test boxes boot normally. Reuses get_pg_url + the MS02 TLS
knobs + the same pool sizing.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

### Task 3: Wire the engine into the client registry + health probes

**Files:**
- Modify: `nx_lib/clients.py` (the `from .db import ...` line, the `ClientConfig` dataclass, the `default` + `ms02` branches in `_build_clients`)
- Modify: `nx_lib/cli_doctor.py` (the `from .db import (...)` block + the `targets` list)
- Modify: `nx_lib/views/admin.py` (the `from ..db import (...)` block + the ping `targets`)
- Test: `tests/unit/test_clients_docfields.py` (create)

**Interfaces:**
- Produces: `ClientConfig.docfields_engine` (object|None), `ClientConfig.docfields_dialect` (str). `default` → `engine_statistics_db` / `"tsql"`; `ms02` → `engine_ms02_docfields_pg` / `"postgres"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_clients_docfields.py
"""ClientConfig carries a per-client doc-field engine + dialect."""

from nx_lib.clients import CLIENTS, ClientConfig


def test_clientconfig_has_docfields_fields():
    fields = ClientConfig.__dataclass_fields__
    assert "docfields_engine" in fields
    assert "docfields_dialect" in fields


def test_default_client_docfields_dialect_is_tsql():
    assert CLIENTS["default"].docfields_dialect == "tsql"


def test_ms02_client_docfields_dialect_is_postgres_when_registered():
    # ms02 may be absent on a box without MS02 runtime creds; only assert when
    # it is registered. Its doc-field engine may still be None.
    if "ms02" in CLIENTS:
        assert CLIENTS["ms02"].docfields_dialect == "postgres"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_clients_docfields.py -v`
Expected: FAIL — the dataclass has no `docfields_engine`/`docfields_dialect`.

- [ ] **Step 3: Import the engine + extend the dataclass + wire `_build_clients`**

In `nx_lib/clients.py`, change the import line:

```python
from .db import engine_ms02_pg, engine_ms02_stats_pg, engine_octo_db, engine_statistics_db
```
to:
```python
from .db import (
    engine_ms02_docfields_pg,
    engine_ms02_pg,
    engine_ms02_stats_pg,
    engine_octo_db,
    engine_statistics_db,
)
```

In the `ClientConfig` dataclass, add the two fields after `stats_dialect: str = "tsql"`:

```python
    stats_engine: object = None
    stats_dialect: str = "tsql"
    docfields_engine: object = None
    docfields_dialect: str = "tsql"
```

In `_build_clients`, the `"default"` ClientConfig, change the trailing two lines:

```python
            stats_engine=engine_statistics_db,
            stats_dialect="tsql",
```
to:
```python
            stats_engine=engine_statistics_db,
            stats_dialect="tsql",
            docfields_engine=engine_statistics_db,
            docfields_dialect="tsql",
```

In the `"ms02"` ClientConfig, change:

```python
            stats_engine=engine_ms02_stats_pg,
            stats_dialect="postgres",
```
to:
```python
            stats_engine=engine_ms02_stats_pg,
            stats_dialect="postgres",
            docfields_engine=engine_ms02_docfields_pg,
            docfields_dialect="postgres",
```

(`docfields_engine=engine_ms02_docfields_pg` may be `None` — that is fine; the resolver checks for `None` before querying, and ms02 registration is gated on the *runtime* engine + Octo domain, not the doc-field engine.)

- [ ] **Step 4: Run the client test green**

Run: `python -m pytest tests/unit/test_clients_docfields.py -v`
Expected: PASS.

- [ ] **Step 5: Add to the `nx --doctor` ping list**

In `nx_lib/cli_doctor.py`, inside `_check_databases`, add `engine_ms02_docfields_pg` to the `from .db import (...)` block (keep alphabetical), then add to the `targets` list directly after the `engine_ms02_stats_pg` conditional line:

```python
        *([(engine_ms02_stats_pg, "MS02 stats (PG)")] if engine_ms02_stats_pg is not None else []),
        *(
            [(engine_ms02_docfields_pg, "MS02 docfields (PG)")]
            if engine_ms02_docfields_pg is not None
            else []
        ),
    ]
```

- [ ] **Step 6: Add to the admin DB-health grid**

In `nx_lib/views/admin.py`, add `engine_ms02_docfields_pg` to the `from ..db import (...)` block (keep alphabetical), then in the `ping_dbs_parallel([...])` list add directly after the `engine_ms02_stats_pg` conditional tuple:

```python
            *(
                [(engine_ms02_stats_pg, "MS02 stats (PG)")]
                if engine_ms02_stats_pg is not None
                else []
            ),
            *(
                [(engine_ms02_docfields_pg, "MS02 docfields (PG)")]
                if engine_ms02_docfields_pg is not None
                else []
            ),
        ],
```

- [ ] **Step 7: Verify nothing broke + run the unit set**

Run: `python -c "import nx_lib.clients, nx_lib.cli_doctor, nx_lib.views.admin; print('ok')"`
Expected: prints `ok` (no ImportError).
Run: `python -m pytest tests/unit/test_clients_docfields.py tests/unit/test_config_ms02_docfields.py tests/unit/test_db_ms02_docfields_engine.py -v`
Expected: PASS.

- [ ] **Step 8: ruff + commit**

```bash
ruff check nx_lib/clients.py nx_lib/cli_doctor.py nx_lib/views/admin.py tests/unit/test_clients_docfields.py
ruff format nx_lib/clients.py nx_lib/cli_doctor.py nx_lib/views/admin.py tests/unit/test_clients_docfields.py
git add nx_lib/clients.py nx_lib/cli_doctor.py nx_lib/views/admin.py tests/unit/test_clients_docfields.py
git commit -m "feat(clients): wire docfields_engine into the client registry + probes"
```

Commit body:
```
ClientConfig gains docfields_engine/docfields_dialect (default ->
engine_statistics_db/tsql for columnar StatisticsDB resolution; ms02 ->
engine_ms02_docfields_pg/postgres for EAV resolution). The dialect field is the
switch the doc-field resolver branches on; ms02's engine may be None
(graceful-degrade) without blocking client registration. The new engine joins
the nx --doctor and admin DB-health ping lists with the same `is not None`
guard the stats engine uses.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

# PHASE 2 — SearchConfig migration (ClientCode column + MS02 seed)

### Task 4: Migration `0027` — `SearchConfig.ClientCode` + MS02 rows

**Files:**
- Create: `sql/_migrations/NexoraDB/0027_searchconfig_ms02_docfields.sql`
- (Auto-regenerated by the hook: `sql/NexoraDB/Tables/dbo.SearchConfig.sql` — never hand-edit.)

**Interfaces:**
- Produces: `dbo.SearchConfig.ClientCode NVARCHAR(50) NOT NULL DEFAULT 'default'`; a commented MS02 seed template keyed on `ProcessName='sydoc.praesidialdepartement_bs'` with `ClientCode='ms02'`.

- [ ] **Step 0: Confirm `0027` is still the next free number**

Run (Glob tool): list `sql/_migrations/NexoraDB/*.sql`. If a higher number than `0026` now exists, bump the new filename accordingly.

- [ ] **Step 1: Write the migration**

Create `sql/_migrations/NexoraDB/0027_searchconfig_ms02_docfields.sql`:

```sql
-- 0027_searchconfig_ms02_docfields.sql
-- Make dbo.SearchConfig source/dialect-aware so doc-field search can route
-- between the default StatisticsDB (columnar) and the MS02 doc-field DB (EAV).
-- Mirrors dbo.Statconfig.ClientCode (migration 0024).
--
-- (1) ADD ClientCode: which client/dialect a SearchConfig row belongs to.
--     'default' rows -> col_<field> is a StatisticsDB physical COLUMN name,
--     resolved as `CAST(alias.col AS NVARCHAR(MAX)) LIKE ?` on engine_statistics_db.
--     'ms02'    rows -> col_<field> is an EAV "Name" VALUE, resolved as
--     `WHERE "Name" = <col_field> AND "StringValue" LIKE %value%` on
--     engine_ms02_docfields_pg (a SEPARATE Postgres DB). The DEFAULT 'default'
--     keeps every existing row behaving exactly as today (byte-identical path).
--     NOT prefixed 'col_' on purpose: get_valid_search_columns() only picks up
--     'col_'-prefixed columns, so ClientCode is ignored by the field enumerator.
--
-- (2) Seed MS02 SearchConfig row(s). OWNER-PROVIDED build-time values (see the
--     plan's Owner-actions section) -- DO NOT guess:
--       * ProcessName MUST be the '<client>.<process>' key target_processes
--         carries (e.g. 'sydoc.praesidialdepartement_bs', same key as the 0025
--         Statconfig seed). Wrong key => the resolver finds no config and
--         (graceful-degrade) imposes NO doc-field constraint, silently
--         returning ALL rows.
--       * For an EAV row, TableName/TableAlias/JoinCondition/TimeFilter/
--         SuggestionTimeFilter are columnar-StatisticsDB semantics and are
--         MEANINGLESS for MS02 -- leave them NULL; the EAV resolver ignores
--         them and uses engine_ms02_docfields_pg.
--       * Each col_<field> value holds the doc-field "Name" string to match in
--         the EAV index (e.g. col_docbarcode = 'Barcode'), NOT a column name.
--         col_<field> is varchar(100): confirm each EAV "Name" fits (Owner #6).
--     Fill the col_<field> -> EAV-Name mappings the MS02 search UI exposes, then
--     uncomment.

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.SearchConfig') AND name = 'ClientCode'
)
BEGIN
    ALTER TABLE dbo.SearchConfig
        ADD ClientCode NVARCHAR(50) NOT NULL
        CONSTRAINT DF_SearchConfig_ClientCode DEFAULT 'default';
END
GO

-- MS02 doc-field mapping row. Columnar columns stay NULL (EAV resolution does
-- not join StatisticsDB). Each col_<field> = the doc-field "Name" to match.
-- OWNER: fill the col_<field> -> "Name" values, then uncomment:
-- IF NOT EXISTS (SELECT 1 FROM dbo.SearchConfig WHERE ProcessName = 'sydoc.praesidialdepartement_bs')
-- BEGIN
--     INSERT INTO dbo.SearchConfig
--         (ProcessName, TableName, TableAlias, JoinCondition, TimeFilter,
--          SuggestionTimeFilter, ClientCode, col_docbarcode /*, col_<field> ... */)
--     VALUES
--         ('sydoc.praesidialdepartement_bs', NULL, NULL, NULL, NULL,
--          NULL, 'ms02', 'Barcode' /*, '<EAV Name>' ... */);
-- END
-- GO
```

- [ ] **Step 2: Apply to INT (and confirm no real SQL error)**

Run: `python scripts/db-migrate.py --env INT`
Expected: applies `0027`, records it in `dbo.SchemaMigrations`, re-dumps `sql/NexoraDB/Tables/dbo.SearchConfig.sql` with the new `ClientCode` column. If it errors on CRLF checksum drift for an *earlier* migration (not `0027` SQL), that is the known INT drift — proceed and use the `SQL_SYNC_SKIP=1` hatch at commit.

- [ ] **Step 3: Verify the column exists + existing rows are 'default'**

In SSMS (or via the migrator login):
```sql
SELECT name FROM sys.columns WHERE object_id = OBJECT_ID('dbo.SearchConfig') AND name = 'ClientCode';
SELECT DISTINCT ClientCode FROM dbo.SearchConfig;
```
Expected: `ClientCode` returned; `DISTINCT ClientCode` yields only `default` (no MS02 row yet — that is owner-seeded).

- [ ] **Step 4: Commit (SQL hatch only if the hook flakes on CRLF drift)**

```bash
git add sql/_migrations/NexoraDB/0027_searchconfig_ms02_docfields.sql sql/NexoraDB/Tables/dbo.SearchConfig.sql
git commit -m "feat(db): make SearchConfig client-aware + MS02 docfield seed (0027)"
```
If the `sql-migrate-int` hook fails on stale CRLF checksums for `0001`–`0003`:
```bash
SQL_SYNC_SKIP=1 git commit -m "feat(db): make SearchConfig client-aware + MS02 docfield seed (0027)"
```

Commit body:
```
Add dbo.SearchConfig.ClientCode (NVARCHAR(50) NOT NULL DEFAULT 'default'),
mirroring dbo.Statconfig.ClientCode from migration 0024, so doc-field search
can route per client. Existing rows default to 'default' and keep the columnar
StatisticsDB path byte-identical. The MS02 EAV seed INSERT is left commented:
ProcessName + the col_<field> -> EAV "Name" mappings are owner-provided
build-time confirmations.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

# PHASE 3 — The doc-field resolver seam (EAV-aware, pre-resolved, unit-tested)

### Task 5: Add `WorkitemFilter.ms02_docfield_ids` + the pure resolver seam; delete the `t_DocumentIndexes` EXISTS

This is the one extracted seam. The default columnar StatisticsDB resolver stays where it is (Task 6 leaves it byte-identical). The MS02 EAV resolver is a pure, unit-testable helper taking literal `(name, value)` pairs + an engine — so it imports nothing from `views` (no cycle) and re-runs no whitelist (the orchestrator owns the `col_<field>` whitelist).

**Files:**
- Modify: `nx_lib/workitem_sources.py` (add `_MS02_DOCFIELD_*` constants + `build_ms02_docfield_sql` + `resolve_ms02_docfield_ids`; extend `WorkitemFilter`; rewire `PostgresSource._build_where`)
- Test: `tests/unit/test_workitem_sources.py` (extend)

**Interfaces:**
- Produces: `WorkitemFilter.ms02_docfield_ids: set | None = None` (MS02-resolved allow-set; separate from the SQL-Server-only `docfield_ids`).
- Produces: `build_ms02_docfield_sql(names: list) -> str` — pure; returns the per-pair EAV lookup SQL using `"Name" IN (...)` + `"StringValue" LIKE %s` against the configured doc-field table. Caller binds `names` + the LIKE value.
- Produces: `resolve_ms02_docfield_ids(engine, pairs) -> set | None`, where `pairs = [(names_list, value), ...]` (one entry per searched docfield; `names_list` is the OR-set of EAV `"Name"` values that docfield maps to). Returns `None` (no constraint) when `engine is None`, `pairs` is empty, or a query errors; an empty `set()` when a pair matched nothing (force zero rows); else the AND-intersected ID set across docfields. Never raises.
- Consumes (in `_build_where`): `filt.ms02_docfield_ids` via the existing three-way `None`/empty/`ANY(%s)` contract.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_workitem_sources.py` (the file already imports `MagicMock, patch`, `nx_lib.workitem_sources as ws`, and uses an `app` fixture with `app.app_context()`):

```python
def test_build_ms02_docfield_sql_uses_quoted_eav_identifiers():
    sql = ws.build_ms02_docfield_sql(["Barcode", "Doctype"])
    # Quoted PascalCase EAV identifiers + psycopg2 %s markers, no '?' marker.
    assert '"Name" IN (%s, %s)' in sql
    assert '"StringValue" LIKE %s' in sql
    assert "?" not in sql
    assert '"WorkItemID"' in sql  # selects the workitem id column


def test_resolve_ms02_docfield_ids_engine_none_returns_none():
    assert ws.resolve_ms02_docfield_ids(None, [(["Barcode"], "123")]) is None


def test_resolve_ms02_docfield_ids_empty_pairs_returns_none():
    assert ws.resolve_ms02_docfield_ids(MagicMock(), []) is None


def test_resolve_ms02_docfield_ids_intersects_pairs(app):
    engine = MagicMock()
    cur = engine.raw_connection.return_value.cursor.return_value
    # First docfield matches {1,2,3}; second {2,3,4}; AND => {2,3}.
    cur.fetchall.side_effect = [[(1,), (2,), (3,)], [(2,), (3,), (4,)]]
    with app.app_context():
        result = ws.resolve_ms02_docfield_ids(
            engine, [(["Barcode"], "1"), (["Doctype"], "x")]
        )
    assert result == {2, 3}


def test_resolve_ms02_docfield_ids_empty_match_forces_empty(app):
    engine = MagicMock()
    cur = engine.raw_connection.return_value.cursor.return_value
    cur.fetchall.side_effect = [[]]  # a docfield matched nothing
    with app.app_context():
        result = ws.resolve_ms02_docfield_ids(engine, [(["Barcode"], "nope")])
    assert result == set()


def test_resolve_ms02_docfield_ids_query_error_returns_none(app):
    engine = MagicMock()
    engine.raw_connection.side_effect = Exception("boom")
    with app.app_context():
        assert ws.resolve_ms02_docfield_ids(engine, [(["Barcode"], "1")]) is None


def test_build_where_emits_any_for_populated_ms02_docfield_ids(app):
    src = ws.PostgresSource.__new__(ws.PostgresSource)  # skip __init__
    src.code = "ms02"
    src.engine = None
    filt = ws.WorkitemFilter(
        process_names=["p"],
        client_names=["c"],
        activity_ignore_csv="",
        ms02_docfield_ids={10, 20},
    )
    with app.app_context(), patch.object(ws, "resolve_nexora_filter_ids", return_value=None):
        where, params = src._build_where(filt)
    assert 'twi."ID" = ANY(%s)' in where
    assert "t_DocumentIndexes" not in where
    assert "EXISTS" not in where
    assert any(isinstance(p, list) and set(p) == {10, 20} for p in params)


def test_build_where_empty_ms02_docfield_ids_forces_no_rows(app):
    src = ws.PostgresSource.__new__(ws.PostgresSource)
    src.code = "ms02"
    src.engine = None
    filt = ws.WorkitemFilter(
        process_names=["p"], client_names=["c"], activity_ignore_csv="",
        ms02_docfield_ids=set(),
    )
    with app.app_context(), patch.object(ws, "resolve_nexora_filter_ids", return_value=None):
        where, _ = src._build_where(filt)
    assert "1=0" in where
    assert "t_DocumentIndexes" not in where


def test_build_where_none_ms02_docfield_ids_adds_no_clause(app):
    src = ws.PostgresSource.__new__(ws.PostgresSource)
    src.code = "ms02"
    src.engine = None
    filt = ws.WorkitemFilter(
        process_names=["p"], client_names=["c"], activity_ignore_csv="",
        ms02_docfield_ids=None,
    )
    with app.app_context(), patch.object(ws, "resolve_nexora_filter_ids", return_value=None):
        where, _ = src._build_where(filt)
    assert "t_DocumentIndexes" not in where
    assert "ANY(%s)" not in where


def test_build_where_ignores_raw_docfields_for_ms02(app):
    # Raw docfields/docvalues must NO LONGER produce an in-query EXISTS.
    src = ws.PostgresSource.__new__(ws.PostgresSource)
    src.code = "ms02"
    src.engine = None
    filt = ws.WorkitemFilter(
        process_names=["p"], client_names=["c"], activity_ignore_csv="",
        docfields=["barcode"], docvalues=["123"],
    )
    with app.app_context(), patch.object(ws, "resolve_nexora_filter_ids", return_value=None):
        where, _ = src._build_where(filt)
    assert "t_DocumentIndexes" not in where
    assert "EXISTS" not in where
```

(We patch `resolve_nexora_filter_ids` to `None` so `_build_where` touches no live NexoraDB even if a base filter field is added later.)

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/unit/test_workitem_sources.py -v -k "ms02_docfield or build_where or build_ms02"`
Expected: FAIL — `ms02_docfield_ids` is not a `WorkitemFilter` field, the helpers do not exist, and the EXISTS block is still present.

- [ ] **Step 3a: Add the new `WorkitemFilter` field + fix the stale docstring**

In `nx_lib/workitem_sources.py`, replace the `docfields`/`docvalues`/`docfield_ids` block of `WorkitemFilter`:

```python
    # Raw doc-field search pairs. Each source resolves them against its OWN stats
    # store (spec §4.6): SqlServerSource via SearchConfig->StatisticsDB (the
    # orchestrator pre-resolves those into `docfield_ids` below); PostgresSource
    # in-query against its own t_documentindexes (Name/Stringvalue).
    docfields: list = field(default_factory=list)
    docvalues: list = field(default_factory=list)
    # StatisticsDB-resolved id allow-set for the SQL SERVER source ONLY (default
    # client's stats store). PostgresSource ignores this and uses the raw pairs.
    docfield_ids: set | None = None
```

with:

```python
    # Raw doc-field search pairs, kept for the autocomplete endpoint only. The
    # ACTUAL search is now ALWAYS pre-resolved by the orchestrator into a per-
    # source id allow-set:
    #   - SqlServerSource (default): SearchConfig -> StatisticsDB -> docfield_ids.
    #   - PostgresSource  (MS02):    SearchConfig -> engine_ms02_docfields_pg
    #                                (separate EAV doc-field DB) -> ms02_docfield_ids.
    # Neither source resolves the raw pairs in-query anymore.
    docfields: list = field(default_factory=list)
    docvalues: list = field(default_factory=list)
    # StatisticsDB-resolved id allow-set for the SQL SERVER source ONLY.
    docfield_ids: set | None = None
    # MS02 doc-field DB-resolved id allow-set for the Postgres source ONLY. Kept
    # separate from docfield_ids so a request that mixes default + MS02 processes
    # never lets one source's doc-field match shrink the other source's results.
    # None = no constraint; empty set = force zero rows; populated = ANY(%s).
    ms02_docfield_ids: set | None = None
```

- [ ] **Step 3b: Replace the in-query EXISTS block in `PostgresSource._build_where`**

Replace this block (find the comment `# Doc-field search -> in-query EXISTS against MS02's own t_DocumentIndexes`):

```python
        # Doc-field search -> in-query EXISTS against MS02's own t_DocumentIndexes
        # (Name/StringValue), one per (docfield, docvalue) pair, AND semantics.
        for name, value in zip(filt.docfields or [], filt.docvalues or [], strict=False):
            name = (name or "").strip()
            value = (value or "").strip()
            if not name or not value:
                continue
            clauses.append(
                'EXISTS (SELECT 1 FROM "t_DocumentIndexes" di '
                'WHERE di."WorkItemID" = twi."ID" AND di."Name" = %s AND di."StringValue" LIKE %s)'
            )
            params.append(name)
            params.append(f"%{value}%")
        return " AND ".join(clauses), params
```

with:

```python
        # Doc-field search -> pre-resolved id allow-set against the SEPARATE MS02
        # doc-field DB (engine_ms02_docfields_pg). The orchestrator resolves the
        # SearchConfig-mapped EAV match into filt.ms02_docfield_ids BEFORE this
        # runs, because a single PG connection binds to one database and cannot
        # join the doc-field DB to the runtime DB in-query. Same three-way
        # contract as the NexoraDB allow-set above.
        if filt.ms02_docfield_ids is not None:
            if not filt.ms02_docfield_ids:
                clauses.append("1=0")
            else:
                clauses.append('twi."ID" = ANY(%s)')
                params.append(list(filt.ms02_docfield_ids))
        return " AND ".join(clauses), params
```

- [ ] **Step 3c: Add the EAV identifier constants + the pure resolver helpers**

Add a module-level block right after `resolve_nexora_filter_ids` (and before `_pgmarks`), mirroring its structure:

```python
# OWNER-CONFIRMED doc-field index identifiers (see the plan's Owner-actions).
# These name the table + columns in the SEPARATE MS02 doc-field DB. Defaults
# mirror the runtime t_DocumentIndexes; if the owner confirms different names
# for THIS database, change them here (one place) -- both the resolver and the
# autocomplete branch read them.
_MS02_DOCFIELD_TABLE = "t_DocumentIndexes"
_MS02_DOCFIELD_ID_COL = "WorkItemID"
_MS02_DOCFIELD_NAME_COL = "Name"
_MS02_DOCFIELD_VALUE_COL = "StringValue"


def build_ms02_docfield_sql(names):
    """Per-docfield EAV lookup SQL for the MS02 doc-field index DB.

    ``names`` is the OR-set of EAV "Name" values one searched docfield maps to.
    Returns the SQL; the caller binds the ``names`` values then the LIKE value.
    Table/column identifiers are config constants (quoted, never user input);
    the matched values are bound %s params -> no injection.
    """
    name_ph = ", ".join(["%s"] * len(names))
    return (
        f'SELECT DISTINCT "{_MS02_DOCFIELD_ID_COL}" FROM "{_MS02_DOCFIELD_TABLE}" '
        f'WHERE "{_MS02_DOCFIELD_NAME_COL}" IN ({name_ph}) '
        f'AND "{_MS02_DOCFIELD_VALUE_COL}" LIKE %s'
    )


def resolve_ms02_docfield_ids(engine, pairs):
    """Resolve MS02 doc-field search to a workitem-id allow-set.

    ``pairs`` is ``[(names_list, value), ...]`` -- one entry per searched
    docfield, where ``names_list`` is the OR-set of EAV "Name" values that
    docfield maps to (from SearchConfig.col_<field>) and ``value`` is the user's
    search term. Each docfield matches any of its Names (OR via "Name" IN(...));
    docfields are AND-intersected.

    Three-way contract (mirrors the DEFAULT docfield pre-fetch block in
    _get_workitems_data -- matching_ids=None -> continue/no-constraint; NOT
    resolve_nexora_filter_ids, which returns set() on error):
      * None      -> no constraint (engine absent, no pairs, or any error).
                     The page must still render.
      * set()     -> a docfield matched nothing -> force zero MS02 rows.
      * {ids...}  -> intersected allow-set -> twi."ID" = ANY(%s).
    Never raises: on error it logs and returns None (no constraint).
    """
    if engine is None or not pairs:
        return None

    result = None
    conn = None
    try:
        conn = engine.raw_connection()
        cur = conn.cursor()
        for names, value in pairs:
            if not names:
                continue  # docfield with no mapped Name -> no constraint from it
            sql = build_ms02_docfield_sql(names)
            cur.execute(sql, [*names, f"%{value}%"])
            ids = {row[0] for row in cur.fetchall()}
            if not ids:
                return set()  # a docfield matched nothing -> whole result empty
            result = ids if result is None else (result & ids)
        return result
    except Exception as e:
        current_app.logger.error(f"resolve_ms02_docfield_ids: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()
```

- [ ] **Step 4: Run the tests green**

Run: `python -m pytest tests/unit/test_workitem_sources.py -v`
Expected: all green, including the existing `PostgresSource` tests (they patch `resolve_nexora_filter_ids` and do not exercise doc-fields, so they are unaffected by the EXISTS removal).

- [ ] **Step 5: Prove the runtime EXISTS string is gone**

Run: `python -c "import pathlib,sys; t=pathlib.Path('nx_lib/workitem_sources.py').read_text(); sys.exit('EXISTS (SELECT 1 FROM \"t_DocumentIndexes\"' in t)"`
Expected: exit 0 (the in-query EXISTS literal is absent; only the `_MS02_DOCFIELD_TABLE = "t_DocumentIndexes"` config constant remains).

- [ ] **Step 6: ruff + commit**

```bash
ruff check nx_lib/workitem_sources.py tests/unit/test_workitem_sources.py
ruff format nx_lib/workitem_sources.py tests/unit/test_workitem_sources.py
git add nx_lib/workitem_sources.py tests/unit/test_workitem_sources.py
git commit -m "feat(workitems): add MS02 EAV doc-field resolver; drop t_DocumentIndexes EXISTS"
```

Commit body:
```
Delete the in-query EXISTS against MS02's runtime t_DocumentIndexes from
PostgresSource._build_where. Add resolve_ms02_docfield_ids + build_ms02_docfield_sql:
a pure, unit-tested seam that resolves MS02 doc-field (names, value) pairs
against the separate engine_ms02_docfields_pg into a workitem-id allow-set under
the canonical three-way contract (None = no constraint, empty = force zero rows,
populated = intersected set), then constrains the runtime query via
twi."ID" = ANY(%s) -- a PG connection binds to one DB, so the doc-field DB
cannot be joined in-query. ms02_docfield_ids is a new, separate WorkitemFilter
field so it never contaminates the default source's docfield_ids. Engine None /
error / no pairs all degrade to no-constraint and never raise. The seam takes
literal (names, value) pairs + the engine, so workitem_sources imports nothing
from views (no cycle) and the col_<field> whitelist stays in the orchestrator.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

# PHASE 4 — Wire the orchestrator (sibling block) + route tolerance

### Task 6: Resolve the MS02 allow-set beside the default block; thread it into `WorkitemFilter`

The existing default docfield loop is left **byte-identical**. We add a sibling block that builds literal `(names, value)` pairs from MS02-tagged SearchConfig rows and calls the pure resolver. We also add a one-line defensive `AND ClientCode = 'default'` to the existing default SELECT so a future MS02 row can never bleed into the columnar path.

**Files:**
- Modify: `nx_lib/views/workitems.py` (`_get_workitems_data` + the workitem-sources import + the `engine_ms02_docfields_pg` import)
- Test: `tests/integration/test_workitems_routes.py` (extend)

**Interfaces:**
- Consumes: `resolve_ms02_docfield_ids(engine, pairs)` from `workitem_sources`; `engine_ms02_docfields_pg` from `db`.
- Produces: `WorkitemFilter(..., ms02_docfield_ids=<set|None>)`.

- [ ] **Step 1: Write the failing integration test**

Add to `tests/integration/test_workitems_routes.py` (use the verified `user_client` + `workitems_all_perms` fixtures; assert the harness-standard `(200, 500)` and gate body checks under the 200 branch, exactly like `test_api_workitems_returns_degraded_key`):

```python
def test_api_workitems_docfield_tolerates_absent_ms02_engine(user_client, workitems_all_perms):
    """A doc-field query for an MS02 process must not error beyond the harness
    tolerance when engine_ms02_docfields_pg is None (CI default)."""
    resp = user_client.get(
        "/api/workitems",
        query_string={
            "prcfW": "sydoc.praesidialdepartement_bs",
            "docfield": "doctype",
            "docvalue": "invoice",
        },
    )
    assert resp.status_code in (200, 500)
    if resp.status_code == 200:
        body = resp.get_json()
        assert "workitems" in body
        assert "pagination" in body


def test_api_workitems_docfield_mixed_processes_tolerated(user_client, workitems_all_perms):
    resp = user_client.get(
        "/api/workitems",
        query_string={"prcfW": "all", "docfield": "doctype", "docvalue": "x"},
    )
    assert resp.status_code in (200, 500)
```

- [ ] **Step 2: Run it to verify it fails (or errors on the import)**

Run: `python -m pytest tests/integration/test_workitems_routes.py -v -k "ms02_engine or mixed_processes"`
Expected: FAIL/error until the orchestrator imports + calls `resolve_ms02_docfield_ids`.

- [ ] **Step 3a: Add the imports**

In `nx_lib/views/workitems.py`, extend the db import:

```python
from ..db import engine_nexora_db, engine_statistics_db
```
to:
```python
from ..db import engine_ms02_docfields_pg, engine_nexora_db, engine_statistics_db
```

Add `resolve_ms02_docfield_ids` to the `from ..workitem_sources import (...)` group (alphabetical), e.g.:

```python
from ..workitem_sources import (
    WorkitemFilter,
    fetch_merged_page,
    get_domain_for_workitem,
    resolve_ms02_docfield_ids,
    single_workitem_tags,
)
```
(match the file's actual current member list; just add `resolve_ms02_docfield_ids`.)

- [ ] **Step 3b: Defensively scope the existing default SELECT to `ClientCode='default'`**

In `_get_workitems_data`, in the default docfield loop, change the existing query so it never reads MS02 rows. Find:

```python
                query = f"""
                    SELECT ProcessName, TableName, TableAlias, JoinCondition, TimeFilter, {target_config_col}
                    FROM SearchConfig
                    WHERE {target_config_col} IS NOT NULL
                    AND ProcessName IN ({placeholders})
                """
```
and add the `ClientCode` predicate:
```python
                query = f"""
                    SELECT ProcessName, TableName, TableAlias, JoinCondition, TimeFilter, {target_config_col}
                    FROM SearchConfig
                    WHERE {target_config_col} IS NOT NULL
                    AND ClientCode = 'default'
                    AND ProcessName IN ({placeholders})
                """
```
(`ClientCode` is the column added by migration `0027`, default `'default'`, so for an INT/PROD that has applied `0027` this is a no-op for every existing row; it only excludes future MS02 rows. The MS02 sibling block filters `ClientCode = 'ms02'` symmetrically.)

- [ ] **Step 3c: Initialise `ms02_docfield_ids` beside `docfield_ids`**

Find the `docfield_ids = None` initialiser above the `if has_permission("workitems.filter.documentfields") and target_processes:` guard and add next to it:

```python
    docfield_ids = None
    ms02_docfield_ids = None
```

- [ ] **Step 3d: Add the MS02 sibling block**

Immediately after the default docfield loop's outer `finally:` that closes `cursor_nex`/`conn_nex` (and before `status_map = {"Ready": 0, ...}`), add:

```python
    # --- MS02 EAV doc-field pre-resolution (sibling to the default block) ---
    # Resolves through the SAME SearchConfig mapping but against the separate
    # MS02 doc-field DB (EAV "Name"/"StringValue"). The default block above
    # (StatisticsDB -> docfield_ids) is untouched and byte-identical; this is a
    # parallel, independent allow-set so a mixed default+MS02 request never
    # cross-shrinks. None = no constraint; the resolver short-circuits when the
    # engine is absent. Guarded by the same permission + target_processes.
    if (
        has_permission("workitems.filter.documentfields")
        and target_processes
        and engine_ms02_docfields_pg is not None
    ):
        valid_db_columns = get_valid_search_columns()
        conn_nex2 = None
        cursor_nex2 = None
        try:
            conn_nex2 = engine_nexora_db.raw_connection()
            cursor_nex2 = conn_nex2.cursor()
            pairs = []
            for docfield, docvalue in zip(docfields, docvalues, strict=False):
                docfield = (docfield or "").lower().strip()
                docvalue = (docvalue or "").strip()
                if not docfield or not docvalue:
                    continue
                target_config_col = f"col_{docfield}"
                # Whitelist the column name (same guard the default path uses)
                # before interpolating it -- blocks injection via `docfield`.
                if target_config_col not in valid_db_columns:
                    continue
                placeholders = ",".join(["?"] * len(target_processes))
                cursor_nex2.execute(
                    f"SELECT {target_config_col} FROM SearchConfig "
                    f"WHERE {target_config_col} IS NOT NULL "
                    f"AND ClientCode = 'ms02' "
                    f"AND ProcessName IN ({placeholders})",
                    target_processes,
                )
                # Each row's col_<field> value IS an EAV "Name" to match. A
                # docfield mapping to several MS02 rows ORs its Names together.
                names = [r[0] for r in cursor_nex2.fetchall() if r[0]]
                if not names:
                    continue  # no MS02 mapping for this docfield -> no constraint
                pairs.append((names, docvalue))
            if pairs:
                ms02_docfield_ids = resolve_ms02_docfield_ids(
                    engine_ms02_docfields_pg, pairs
                )
        except Exception as e:
            current_app.logger.error(f"Error in MS02 docfield pre-fetch block: {e}")
            ms02_docfield_ids = None
        finally:
            if cursor_nex2:
                cursor_nex2.close()
            if conn_nex2:
                conn_nex2.close()
```

- [ ] **Step 3e: Thread it into `WorkitemFilter` and fix the stale comments**

Find the `WorkitemFilter(...)` construction's docfield kwargs:

```python
        docfields=docfields or [],  # raw pairs -> PostgresSource (t_DocumentIndexes)
        docvalues=docvalues or [],
        docfield_ids=docfield_ids,  # StatisticsDB-resolved set -> SqlServerSource only
    )
```
and replace with:
```python
        docfields=docfields or [],  # raw pairs kept for autocomplete only
        docvalues=docvalues or [],
        docfield_ids=docfield_ids,  # StatisticsDB-resolved -> SqlServerSource only
        ms02_docfield_ids=ms02_docfield_ids,  # MS02 doc-field DB-resolved -> PostgresSource
    )
```

- [ ] **Step 4: Run the integration test + the unit suite to confirm PASS**

```bash
python -m pytest tests/integration/test_workitems_routes.py -v -k "ms02_engine or mixed_processes"
python -m pytest tests/unit/test_workitem_sources.py -v
```
Expected: green. CI has no MS02 engine, so `engine_ms02_docfields_pg is None` → the MS02 block is skipped and `ms02_docfield_ids` stays `None`; the default path is unchanged. CSV export (`export_workitems_csv`) reuses `_get_workitems_data`, so it inherits the fix with no separate edit.

- [ ] **Step 5: Confirm the default path is byte-identical for a default-only request**

Run: `python -m pytest tests/integration/test_workitems_routes.py tests/unit/test_workitem_sources.py -v`
Expected: all existing default-source assertions unchanged and green.

- [ ] **Step 6: ruff + commit**

```bash
ruff check nx_lib/views/workitems.py tests/integration/test_workitems_routes.py
ruff format nx_lib/views/workitems.py tests/integration/test_workitems_routes.py
git add nx_lib/views/workitems.py tests/integration/test_workitems_routes.py
git commit -m "feat(workitems): pre-resolve MS02 doc-field search in the orchestrator"
```

Commit body:
```
_get_workitems_data adds a sibling block that resolves MS02 doc-field search via
the SearchConfig (ClientCode='ms02') mapping against engine_ms02_docfields_pg,
producing a separate ms02_docfield_ids allow-set threaded into WorkitemFilter.
The existing default StatisticsDB -> docfield_ids loop is left byte-identical;
it only gains a defensive AND ClientCode='default' so a future MS02 row can
never bleed into the columnar path. The col_<field> whitelist stays in the view
and literal (names, value) pairs are handed to the pure resolver. CSV export
inherits the fix (it reuses _get_workitems_data). Degrades to no constraint when
the engine is absent or no MS02 mapping row matches; never errors the page.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

# PHASE 5 — Autocomplete parity (optional, in-scope only if owner wants suggestions)

`api_docfield_values` reads `SearchConfig → [DB_STATISTICS].{TableName}` on `engine_statistics_db`. For an MS02 process it finds no columnar config (the MS02 row has NULL `TableName`) and returns `[]` — autocomplete is silently empty but never 500s on that path. This phase gives the MS02 search box suggestions. It is **optional**: if the owner defers it, the route already degrades to `[]` for MS02 — record it as an Owner follow-up and skip to Phase 6.

### Task 7 (optional): MS02 EAV branch in `api_docfield_values`

**Files:**
- Modify: `nx_lib/views/workitems.py` (`api_docfield_values` + the `engine_ms02_docfields_pg` import added in Task 6)
- Test: `tests/integration/test_workitems_routes.py` (extend)

- [ ] **Step 1: Write the test**

```python
def test_api_docfield_values_ms02_degrades_without_engine(user_client, workitems_all_perms):
    """For an MS02 process with no doc-field engine, autocomplete returns [] (200)
    or stays within harness tolerance; never an uncaught error."""
    resp = user_client.get(
        "/api/docfield_values",
        query_string={
            "process": "sydoc.praesidialdepartement_bs",
            "field": "doctype",
            "q": "inv",
        },
    )
    assert resp.status_code in (200, 401, 500)
    if resp.status_code == 200:
        assert isinstance(resp.get_json(), list)
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/integration/test_workitems_routes.py -v -k "docfield_values_ms02"`
Expected: with no MS02 branch yet, the route already returns `[]` (the MS02 SearchConfig row has no columnar `TableName`), so this may PASS trivially. That is fine — it locks the "never uncaught error" contract before the branch is added.

- [ ] **Step 3: Add the MS02 EAV branch**

In `api_docfield_values`, right after `configs = cur.execute(query, db_params).fetchall()` and its `if not configs: return jsonify([])`, add the MS02 short-circuit (it sits BEFORE the existing StatisticsDB `cache_key = f"docfield_vals_{process}_{field}"` block, so MS02 processes short-circuit and default processes fall through unchanged):

```python
        # MS02 (EAV) processes resolve suggestions from the separate doc-field DB,
        # not [DB_STATISTICS]. A row whose ClientCode='ms02' carries the EAV
        # "Name" value in col_<field>; query DISTINCT "StringValue" for it.
        # `SELECT * FROM SearchConfig` already surfaces ClientCode after 0027.
        ms02_names = [
            getattr(c, target_col_name)
            for c in configs
            if (getattr(c, "ClientCode", "default") or "default") == "ms02"
            and getattr(c, target_col_name)
        ]
        if ms02_names:
            from ..db import engine_ms02_docfields_pg
            from ..workitem_sources import (
                _MS02_DOCFIELD_NAME_COL,
                _MS02_DOCFIELD_TABLE,
                _MS02_DOCFIELD_VALUE_COL,
            )

            if engine_ms02_docfields_pg is None:
                return jsonify([])
            ms02_cache_key = f"docfield_vals_ms02_{process}_{field}"
            all_vals = cache.get(ms02_cache_key)
            if all_vals is None:
                df_conn = None
                raw_vals = []
                try:
                    name_ph = ",".join(["%s"] * len(ms02_names))
                    df_conn = engine_ms02_docfields_pg.raw_connection()
                    df_cur = df_conn.cursor()
                    df_cur.execute(
                        f'SELECT DISTINCT "{_MS02_DOCFIELD_VALUE_COL}" '
                        f'FROM "{_MS02_DOCFIELD_TABLE}" '
                        f'WHERE "{_MS02_DOCFIELD_NAME_COL}" IN ({name_ph}) '
                        f'AND "{_MS02_DOCFIELD_VALUE_COL}" IS NOT NULL '
                        f'AND "{_MS02_DOCFIELD_VALUE_COL}" <> %s '
                        f'ORDER BY "{_MS02_DOCFIELD_VALUE_COL}" LIMIT 500',
                        [*ms02_names, ""],
                    )
                    raw_vals = [r[0] for r in df_cur.fetchall()]
                    df_cur.close()
                except Exception as e:
                    current_app.logger.error(f"/api/docfield_values ms02 error: {e}")
                    raw_vals = []
                finally:
                    if df_conn:
                        df_conn.close()
                all_vals = sorted(set(raw_vals))
                cache.set(ms02_cache_key, all_vals, timeout=600)
            q_lower = q.lower()
            return jsonify([v for v in all_vals if not q or q_lower in v.lower()][:15])
```

(The `_MS02_DOCFIELD_*` constants are the single source of truth in `workitem_sources.py` — imported here, not re-declared. The view already imports `current_app`, `jsonify`, `cache`.)

- [ ] **Step 4: Run the test green**

Run: `python -m pytest tests/integration/test_workitems_routes.py -v -k "docfield_values"`
Expected: green; default-process autocomplete behaviour unchanged.

- [ ] **Step 5: ruff + commit**

```bash
ruff check nx_lib/views/workitems.py tests/integration/test_workitems_routes.py
ruff format nx_lib/views/workitems.py tests/integration/test_workitems_routes.py
git add nx_lib/views/workitems.py tests/integration/test_workitems_routes.py
git commit -m "feat(workitems): MS02 doc-field autocomplete from the doc-field DB"
```

Commit body:
```
api_docfield_values now serves suggestions for MS02 (ClientCode='ms02')
processes from engine_ms02_docfields_pg (DISTINCT "StringValue" for the mapped
"Name"), instead of the empty result it returned when looking up an MS02 process
in [DB_STATISTICS]. Default-process autocomplete is unchanged. Reuses the
_MS02_DOCFIELD_* identifier constants. Degrades to [] when the engine is absent;
never raises uncaught.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

# PHASE 6 — Docs, spec §4.6, CHANGELOG

### Task 8: Update CHANGELOG, CLAUDE.md, and supersede spec §4.6

**Files:**
- Modify: `CHANGELOG.md` (`[Unreleased]`)
- Modify: `CLAUDE.md` (the "Databases" engine list + the "Multi-source workitems" paragraph)
- Modify: `docs/superpowers/specs/2026-06-16-ms02-client-merged-workitems-design.md` (§4.6 body + the summary-table row at ~line 116)

- [ ] **Step 1: CHANGELOG** — under `## [Unreleased]` (which has `### Added` but no `### Changed` yet), insert a `### Changed` subsection before `### Added`:

```markdown
### Changed

- MS02 doc-field (document-field) search now resolves through nexora's `dbo.SearchConfig` mapping (made source/dialect-aware via the new `ClientCode` column, migration `0027`) instead of an in-query `EXISTS` against MS02's own `t_DocumentIndexes` runtime table. The matched field VALUE is resolved against a dedicated MS02 Azure-Postgres doc-field database via the new `engine_ms02_docfields_pg` engine + `MS02_DOCFIELDS_DB_*` env vars (graceful-degrade to `None` until configured); matches are pre-resolved to a workitem-id allow-set and applied as `twi."ID" = ANY(...)`, mirroring the default source. No ETL/ingestion. Default-client doc-field search is unchanged.
```

And under the existing `### Added`:

```markdown
- `engine_ms02_docfields_pg` (+ `MS02_DOCFIELDS_DB_*` env vars) — a dedicated SQLAlchemy engine for the MS02 doc-field index database, and a source/dialect-aware `dbo.SearchConfig.ClientCode` column (migration `0027`).
```

- [ ] **Step 2: CLAUDE.md "Databases"** — add a bullet immediately after the `engine_ms02_stats_pg` bullet:

```markdown
- `engine_ms02_docfields_pg` — the MS02 client's doc-field index DB (Azure Postgres, same host/login as the MS02 runtime, a *different* dbname); stays `None` until `MS02_DOCFIELDS_DB_*` are set (defaults reuse the MS02 runtime host/login; only the dbname differs). Doc-field search pre-resolves matches against it into a workitem-id allow-set — no ETL, never joined in-query to the runtime DB.
```

- [ ] **Step 3: CLAUDE.md "Multi-source workitems (MS02 client)" paragraph** — append:

```markdown
Doc-field (document-field) search is also `SearchConfig`-driven for every client: `dbo.SearchConfig.ClientCode` (migration `0027`, mirroring `Statconfig.ClientCode` from `0024`) routes `'default'` rows to StatisticsDB (columnar) and `'ms02'` rows to `engine_ms02_docfields_pg` (EAV `"Name"`/`"StringValue"`), each pre-resolved to a separate workitem-id allow-set (`resolve_ms02_docfield_ids` in `nx_lib/workitem_sources.py`) and applied as `id = ANY(...)` — superseding the old direct `t_DocumentIndexes` coupling (design spec §4.6).
```

- [ ] **Step 4: Spec §4.6** — the live heading is `### 4.6 Doc-field search is per source (`t_documentindexes`)`. Replace the §4.6 heading + body (the prose, the ```sql EXISTS``` block, and the "raw pairs" sentence) with a superseded note + the new design:

```markdown
### 4.6 Doc-field search via SearchConfig (superseded direct t_documentindexes coupling)

> **Superseded (2026-06-18).** The original design resolved MS02 doc-field search
> via an in-query `EXISTS` against MS02's own runtime `t_documentindexes`. That
> direct coupling does not scale and has been replaced: doc-field search now flows
> through nexora's normal mapping layer (`dbo.SearchConfig`, made client-aware via
> the `ClientCode` column, migration `0027`) for ALL clients, and the MS02 field
> VALUE is resolved against a DEDICATED MS02 doc-field Postgres database
> (`engine_ms02_docfields_pg`, a different dbname from the runtime DB). Because a
> single Postgres connection binds to one database, the doc-field DB cannot be
> joined to the runtime DB in-query; matches are PRE-RESOLVED to a workitem-id
> allow-set and applied as `twi."ID" = ANY(%s)`, mirroring the default source's
> `docfield_ids`. No ETL. See migration `0027`,
> `nx_lib/workitem_sources.resolve_ms02_docfield_ids`, and
> `docs/superpowers/plans/2026-06-18-ms02-docfield-searchconfig-mapping.md`.

For both clients, `dbo.SearchConfig` (NexoraDB) is the mapping. A `ClientCode`
column routes each row: `'default'` rows are columnar (`col_<field>` = a
StatisticsDB physical column, resolved on `engine_statistics_db`); `'ms02'` rows
are EAV (`col_<field>` = the doc-field `"Name"` VALUE to match, resolved on
`engine_ms02_docfields_pg` as `WHERE "Name" = <col_field> AND "StringValue" LIKE %value%`).
The orchestrator pre-resolves each client's matches into a SEPARATE id allow-set
(default → `docfield_ids` for the SQL Server source; MS02 → `ms02_docfield_ids`
for the Postgres source). `t_DocumentIndexes` is no longer queried at runtime.
**Field VALUES** on the detail page / CSV export are unchanged — they still come
from the per-client domain-routed Octo thin-document API; the doc-field DB is
search-only.
```

- [ ] **Step 5: Spec summary table (~line 116)** — the live row is:

```markdown
| doc-field search | **per source** (see §4.6) — default: `SearchConfig`→StatisticsDB; MS02: its own `t_documentindexes` | default pre-resolves to an ID set (existing block) for the SQL Server source; MS02 applies an in-query `EXISTS` against `t_documentindexes`. **No shared id-set.** |
```
Replace it with:
```markdown
| doc-field search | **`SearchConfig`-driven for both** (see §4.6); `ClientCode` routes columnar (default→StatisticsDB) vs EAV (MS02→`engine_ms02_docfields_pg`, a separate doc-field DB) | **each pre-resolves to its OWN id allow-set** — default→`docfield_ids` (SQL Server), MS02→`ms02_docfield_ids` (Postgres), applied as `id = ANY(...)`. No in-query `EXISTS`; the doc-field DB is never joined to the runtime DB. Sets are per-source (never shared/intersected across sources). |
```

- [ ] **Step 6: Commit**

```bash
git add CHANGELOG.md CLAUDE.md docs/superpowers/specs/2026-06-16-ms02-client-merged-workitems-design.md
git commit -m "docs(ms02): document SearchConfig-driven doc-field search; supersede spec 4.6"
```

Commit body:
```
CHANGELOG Added/Changed entries for engine_ms02_docfields_pg, the
MS02_DOCFIELDS_DB_* env vars, and the SearchConfig.ClientCode column (0027).
CLAUDE.md gains the engine bullet and the doc-field sentence in the multi-source
paragraph. Spec section 4.6 + its summary-table row are rewritten as superseded:
MS02 doc-field search is now SearchConfig -> a separate doc-field DB -> a
pre-resolved id allow-set, not an in-query EXISTS against t_DocumentIndexes.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

# PHASE 7 — Final verification

### Task 9: Full suite + leftover-reference sweep

- [ ] **Step 1: Run the full unit + integration suites**

Run: `python -m pytest tests/unit tests/integration -q`
Expected: green. (Do NOT run the pre-push e2e gate here — it runs on `git push`, out of scope for this remote session. For a local e2e dry run, first `python scripts/test_db_reset.py` to clear stale `NEXORA_TEST` state.)

- [ ] **Step 2: Prove no stale runtime coupling remains**

Run (Grep tool): search `EXISTS .*t_DocumentIndexes` across `nx_lib/`. Expected: zero matches. A remaining match of the bare string `t_DocumentIndexes` is acceptable ONLY as the `_MS02_DOCFIELD_TABLE` config constant in `workitem_sources.py` (and as the env-example default) — not as a runtime EXISTS join.

- [ ] **Step 3 (remote session): STOP at commit**

Do not push, do not open a PR. Confirm `git status` is clean and `git log --oneline -10` shows the task commits. Hand the branch back to the owner for local review + PR→main (which must land after the underlying MS02 multi-source work, still unpushed on this branch).

---

## Gotchas & notes

- **`ProcessName` keying is the #1 landmine.** The MS02 sibling resolver matches `SearchConfig.ProcessName` against `target_processes`, which carry the `'<client>.<process>'` form (e.g. `'sydoc.praesidialdepartement_bs'`, same key as `Statconfig` in migration `0025`). If the seed row is keyed wrong, the resolver finds no config row → returns `None` → no constraint → search appears to "work" but returns ALL MS02 rows. The route-tolerance tests will NOT catch a *wrong* key, only an absent engine — confirm Owner-action #5. Note `prepare_process_selection_lists` flattens to BARE process/client names for `WorkitemFilter.process_names`/`client_names`; that flattened form is NOT what the resolver uses — it uses the un-flattened `target_processes`.
- **Error-degrade attribution (subtle).** `resolve_ms02_docfield_ids` returns `None` on error (no constraint). This mirrors the DEFAULT docfield pre-fetch block (`matching_ids = None` → `continue`), NOT `resolve_nexora_filter_ids`, which returns `set()` on error (force zero rows). Keep the docstring's attribution to the default docfield block; the two precedents genuinely disagree on error semantics and we deliberately pick the no-constraint one (a doc-field DB hiccup must never silently empty the list).
- **Two independent allow-sets, never intersected across sources.** `docfield_ids` (default/StatisticsDB) constrains `SqlServerSource`; `ms02_docfield_ids` (MS02 doc-field DB) constrains `PostgresSource`. Separate `WorkitemFilter` fields, separate per-source clauses. A mixed `prcfW='all'` request must not let an MS02-only doc-field match shrink default results or vice versa.
- **EAV-vs-columnar overload of `col_<field>`.** Default rows: `col_<field>` is a physical column name. MS02 rows: it is reinterpreted as an EAV `"Name"` literal. The switch is `SearchConfig.ClientCode` (`'ms02'` vs `'default'` in each block's WHERE), never a guess. The default block now filters `ClientCode = 'default'`; the MS02 block filters `ClientCode = 'ms02'` — they can never read each other's rows.
- **`ClientCode` must NOT start with `col_`.** `get_valid_search_columns()` whitelists only `col_*` columns (to block injection of the `field` param into a column reference). A `col_`-prefixed routing column would pollute that whitelist. `ClientCode` is safely ignored.
- **`SELECT * FROM SearchConfig` now returns `ClientCode`.** `api_docfield_values` does `SELECT *`, so after `0027` every row carries `ClientCode` and the Task-7 `getattr(c, "ClientCode", "default")` branch works. The `api_*_page_init` field enumerators filter to `col_*` columns, so the extra column never leaks into field lists.
- **`col_<field>` is varchar(100).** The owner-provided EAV `"Name"` values are stored there. If any `"Name"` exceeds 100 chars the seed INSERT silently truncates — widen the column in the migration (Owner-action #6). Likely fine for short EAV names.
- **Multi-process semantics.** `resolve_ms02_docfield_ids` ORs the mapped `"Name"` values within a docfield (`"Name" IN (...)`) and ANDs across docfields. With one MS02 process this is moot; if MS02 gains multiple processes mapping the same field and OR-across-processes is wanted, that is already the chosen behaviour. If AND-across-processes is wanted instead, change the resolver + its test (Owner-action #7).
- **Owner-provided identifiers live in ONE place** — the `_MS02_DOCFIELD_*` constants in `workitem_sources.py`. The resolver and the autocomplete branch both read them; change casing/names there only (Owner-action #2).
- **Cross-DB join is impossible by design.** `engine_ms02_docfields_pg` (doc-field DB) and `engine_ms02_pg` (runtime DB) are different databases on the same host; a psycopg2 connection binds to one. Hence pre-resolve to IDs + `twi."ID" = ANY(%s)`. MS02 workitem IDs are globally unique, so the cross-DB ID constraint is sound (Owner-action #8 confirms the column type matches).
- **Graceful-degrade is the CI path.** TEST/CI has `engine_ms02_docfields_pg is None` and no StatisticsDB, so `resolve_ms02_docfield_ids` returns `None` on its first guard and the orchestrator's MS02 block is skipped entirely. Every new test exercises the no-constraint branch; never write a test that assumes the engine is non-`None`.
- **`MS02_DB_PORT` exists.** Despite the brief's note, `config.py` defines `MS02_DB_PORT = os.environ.get("MS02_DB_PORT", "5432")`. The plan correctly reuses it as the doc-field port default — do not "fix" that line.
- **INT CRLF drift.** The `sql-migrate-int` hook may fail on stale CRLF checksums for `0001`–`0003` — unrelated to `0027`. Distinguish a real SQL error (fix it) from checksum drift (use `SQL_SYNC_SKIP=1 git commit`). The migration is idempotent so re-application is safe. Check PROD `SchemaMigrations` state before deploy.
- **CSV export is free.** `export_workitems_csv` reuses `_get_workitems_data`, so the orchestrator fix flows through with no separate edit.
- **No deploy.yml change, no i18n cycle, no template restart.** Everything is inside already-tracked/excluded dirs; no new top-level path; backend-only (no new translatable strings); no template edits.
- **Remote-session git guardrail.** Branch `feature/2.5.63`; commit only — no `git push`, no PR. This stacks on the unpushed MS02 multi-source work and must not be merged ahead of the owner's pending PR→main for that underlying work.
