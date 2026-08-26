# Doc-field config restructure + query performance (#98 phases 2–3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Single-session planning run (recon → draft → self-red-team); **every file path, symbol, and quoted snippet below was Grep/Read-verified against `v3.2.3.1` HEAD (`9cdb7319`) on 2026-08-26** — anchor on quoted snippets + symbol names, never line numbers; re-Grep before editing. Plan file: `docs/superpowers/plans/2026-08-26-docfield-config-restructure-perf.md`.

**Goal:** Replace the four legacy mapping tables (`SearchConfig` with its ~36 wide `col_*` columns, the `StatConfig` heap, `IndexFieldMappings`, `Search_Field_Labels`) with a normalized schema (`ProcessSources`, `ProcessFieldMappings`, `FieldLabels`, `FieldAliases`) behind ONE cached accessor module (`nx_lib/mapping_config.py`), then use the new `ColumnType` metadata to make doc-field search predicates sargable, cache the per-request allow-set resolution, and batch the `WorkitemSourceCache` lookups. Adding a semantic doc-field goes from "DDL migration + 6 file touches" to "two INSERTs"; a doc-field search stops re-scanning every stat table on every pagination click.

**Architecture:** Migration `0074` creates + backfills the new tables from the legacy ones in place (each environment self-backfills; the legacy tables stay live during cutover). `nx_lib/mapping_config.py` loads all four tables into one frozen registry (tiny: ~6+36+38+56 rows) cached 60 s success-only, and every consumer (`views/workitems.py`, `views/dashboard.py`, `views/reporting.py`, `reporting/catalog.py`, `process_helpers.py`, `octo.py`) cuts over file-by-file. When every consumer is on the registry, migration `0075` decapitates the legacy tables (house convention from `0042`/`0056`: rename with `decapitated_` prefix, drop in a later cycle). Phase 3 seeds `ColumnType`/`IdColumnType` from the live target DBs (generated migration `0076`), teaches the two predicate builders to emit bare typed columns, adds a 60 s allow-set cache, and replaces the per-row `WorkitemSourceCache` round-trips with one batched lookup plus composite-PK migration `0077`.

**Tech Stack:** T-SQL migrations (`sql/_migrations/NexoraDB/`), pyodbc/psycopg via existing engines, Flask-Caching `SimpleCache` (`nx_lib/extensions.py` — `cache = Cache(config={"CACHE_TYPE": "SimpleCache", ...})`), pytest.

**Spec:** `docs/superpowers/specs/2026-07-28-mapping-config-migration-design.md` — this plan implements **Approach B** (normalize in DB), *not* the spec's leaning-A: the owner decided 2026-08-26 that future clients are onboarded by non-devs through an admin UI (white-label rollout, 10–50 clients), which requires DB-resident config. The spec's Approach-A rationale is superseded; its problem analysis and its "one accessor module is not optional" conclusion stand.

---

## Context an engineer needs (read first)

- **Branch:** execute on `v3.2.3.1` (or the cycle branch it merged into — check `git log --oneline -3` first). **Parallel sessions are normal on this repo**: do the work in your own worktree (`git worktree add .claude/worktrees/docfield-restructure -b feat/docfield-restructure v3.2.3.1`), never in the main checkout, and stage by pathspec only. Commit per task. **Do NOT `git push`, do NOT open a PR** — the owner reviews and pushes.
- **Copy the gitignored env files into the worktree before committing or running tests**: `Copy-Item C:\dev\nexora\env\*.env <worktree>\env\` — the pre-commit hook runs `scripts/db-migrate.py --env INT` (needs `env/INT.env`) and the test suite needs `env/TEST.env`.
- **Python for tests:** `C:\dev\nexora\.venv\Scripts\python.exe -m pytest …`. The dev server (`nx -u`) runs the **global** Python313, not `.venv` — no new runtime deps are added by this plan, so that doesn't bite here.
- **Migrations needed: YES — four** (`0074` create+backfill, `0075` decapitate legacy tables, `0076` seed column types, `0077` WorkitemSourceCache composite PK). Migration numbers were free at planning time; **re-check `ls sql/_migrations/NexoraDB/ | tail -3` and run `python scripts/db-migrate.py --env INT --dry-run` before creating each file** — parallel sessions also number migrations. If a number is taken, shift everything up and update the commit messages.
- **The pre-commit hook auto-applies new migrations to INT and re-dumps per-object DDL** (`sql/sync-from-db.py --check`). After a migration that changes schema, run `python sql/sync-from-db.py` and stage the changed/new/deleted files under `sql/NexoraDB/Tables/` in the same commit, or the hook blocks the commit. If INT is unreachable: `SQL_SYNC_SKIP=1 git commit …` — **never** `--no-verify`.
- **gitlint:** conventional-commit title ≤72 chars, imperative, no trailing period, non-empty body wrapped ≤100 chars/line; commit via `git commit -F - <<'EOF' … EOF` (Bash tool). End the body with the executing model's `Co-Authored-By:` trailer.
- **Legacy tables stay live until Task 10.** Every cutover task must leave the app fully working with BOTH schemas present. Never edit the legacy tables' dump files by hand.
- **Failure contract is sacred:** the legacy helpers cache **only on success** (a cached empty error-fallback once disabled doc-field search app-wide for an hour — see the docstring on `get_valid_search_columns`), the external API **fails closed** on `None` (`get_search_columns_for_processes` returning `None`), and an active doc-field search **fails closed per source** (unresolved → empty allow-set, never unconstrained — the 2026-07-20 STAGING flood). Every accessor function in this plan reproduces the exact same `None`/empty semantics its legacy counterpart had. Do not "simplify" these.
- **TEST DB (`sql/test/schema.sql` + `seed.sql`) contains NONE of these tables** — unit/integration tests mock `engine_nexora_db.raw_connection()`; e2e runs with doc-field search naturally disabled (config load fails → legacy returns `[]`). Keep that property: the accessor must degrade identically when its tables are absent. Do not add the new tables to `sql/test/schema.sql`.
- **Jinja templates are cached for the process lifetime** — irrelevant here (no template changes), but restart the dev server (`nx -r`) before any manual browser verification anyway so stale processes don't confuse you.
- **StatisticsDB and the MS02 Postgres doc-field DB are NOT tracked in this repo** — never write to them; Task 11's introspection script is read-only (`INFORMATION_SCHEMA` / `information_schema`).
- **i18n: none.** No new user-facing strings (log messages are untranslated by convention). No permission changes. No deploy-exclude changes (`scripts` and `sql` are already in the `robocopy /XD` list in `.github/workflows/deploy.yml`).

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Approach B (normalize in DB), superseding the spec's leaning-A. | Owner decision 2026-08-26: non-dev client onboarding via future admin UI needs DB-resident config; white-label rollout 10–50 clients. |
| D2 | `ProcessSources` merges `SearchConfig` table-plumbing AND all of `StatConfig` into one row per `(ClientCode, ProcessName)`. | Verified on INT 2026-08-26: all 6 processes have identical `TableName` in both tables (`FULL OUTER JOIN` check); the two tables describe the same stat table twice. |
| D3 | New tables are **new** (create + backfill), not `sp_rename`d conversions; legacy tables stay live until every consumer is cut over, then get decapitated (`0075`) per the `0042`/`0056` house convention. Actual `DROP` happens in a later cycle, like `0072` did for the previous batch. | Incremental, revertible cutover; no big-bang. |
| D4 | One registry blob (all four tables) cached 60 s via the existing `cache` (`nx_lib/extensions.py`), success-only, with an `invalidate_mapping_config()` hook. Legacy per-helper TTLs (some 3600 s) shrink to 60 s. | Rows are tiny (~140 total); one load kills all per-request config round-trips; 60 s makes future admin-UI edits apply fast. Success-only preserves the no-cached-error rule. |
| D5 | `ProcessFieldMappings.ColumnType` / `ProcessSources.IdColumnType` are nullable; `NULL` ⇒ the legacy CAST/`::text` predicate shape. Types are seeded by a generated migration (`0076`), not resolved at runtime. | Progressive enhancement with zero behavior risk; the sargable path only activates where a type is known. |
| D6 | Sargable rules — SQL Server: text-typed column ⇒ bare `alias.col <op> ?` for ALL ops (LIKE included); int-typed ⇒ native-bound `eq`/`neq` (unparseable value ⇒ `1=0`/`1=1`), other ops keep CAST. PG: int-typed ⇒ `"col" = ANY/= %s` native for `eq` and id lookups; everything else keeps `::text ILIKE`. | `eq`/`startswith` on an indexed text column become seeks; comparisons follow the column's collation, which is the DB default CI these DBs use (parity asserted in Task 12's test against live INT data). PG `varchar::text` is binary-coercible (index still usable) — only int columns genuinely need the native path. |
| D7 | Allow-set cache: key = SHA-1 of `(leg, sorted(target_processes), pairs-with-op-and-comb)`, TTL 60 s, caches resolved results **including empty set**, never caches the error/`None` path. | Pagination/export re-resolution was the top per-request cost; 60 s staleness on repeat identical searches is acceptable (documented in Gotchas). Fail-closed states must stay uncached. |
| D8 | `WorkitemSourceCache` gets PK `(WorkItemID, ClientCode)` (`0077`); `_cache_lookup` treats >1 row for an id as ambiguous (log + return `None` ⇒ re-probe), mirroring `get_source_for_workitem`'s collision fail-safe; `fetch_merged_page`'s warm loop does ONE batched lookup and probes only misses. | Fixes the latent id-collision pin (PK was `WorkItemID` alone) and the up-to-1000 sequential round-trips per page. |
| D9 | `FieldAliases.SourceFieldName` is the PK (the unique key `IndexFieldMappings` never had — the MWST dup-key trap, `0052`). No FK from `ProcessFieldMappings.FieldKey` to `FieldLabels` — labels are optional (code falls back to `field_key.replace("_", " ").title()`). | Constraint kills the silent-override bug class; optional labels stay optional. |
| D10 | `FieldMetadata` (read defensively in `reporting/catalog.py`, does not exist on INT) is untouched. `sql/test/schema.sql` is untouched. | YAGNI; test env intentionally exercises the degraded path. |

## Owner actions (not for the executor)

1. Review + merge the worktree branch, push. Migrations `0074`–`0077` auto-apply to PROD on deploy (before app-pool stop; failed migration aborts the deploy). No env keys change — no `env-sync` needed.
2. After the deploy, spot-check: doc-field search on Workitems (field + value-first), dashboard cards, reporting Simple tab field list, one MS02 PID register stamp.
3. Optional: create indexes on the hot StatisticsDB columns (e.g. the per-process date column in `TimeFilter`, the most-searched value columns) — that DB is not repo-tracked, so it's a manual SSMS action informed by Task 12's parity/perf notes.
4. Later cycle: `DROP` the `decapitated_Search*`/`decapitated_Statconfig`/`decapitated_IndexFieldMappings` tables (same pattern as `0072`).

---

# PHASE A — new schema + accessor

### Task 1: Migration `0074` — create + backfill the normalized tables

**Files:**
- Create: `sql/_migrations/NexoraDB/0074_normalized_mapping_schema.sql`
- Modify (regenerated): `sql/NexoraDB/Tables/dbo.ProcessSources.sql`, `dbo.ProcessFieldMappings.sql`, `dbo.FieldLabels.sql`, `dbo.FieldAliases.sql` (all new, produced by `sql/sync-from-db.py`)

**Interfaces:**
- Produces: tables `dbo.ProcessSources`, `dbo.ProcessFieldMappings`, `dbo.FieldLabels`, `dbo.FieldAliases`, backfilled from the legacy tables. Every later task reads these.

- [ ] **Step 1:** Re-check numbering: `ls sql/_migrations/NexoraDB/ | tail -3` must end at `0073_statconfig_pk_logs_timestamp_index.sql`; `python scripts/db-migrate.py --env INT --dry-run` must show 0 pending. If not, renumber this plan's migrations accordingly.
- [ ] **Step 2:** Create `sql/_migrations/NexoraDB/0074_normalized_mapping_schema.sql` with exactly this content:

```sql
-- 0074: normalized doc-field / process mapping schema (#98 phase 2).
-- Replaces the wide SearchConfig (one col_* column per semantic field, DDL
-- migration per new field), the PK-less StatConfig heap, IndexFieldMappings
-- (no unique key -- the 0052 dup-override trap) and Search_Field_Labels.
-- The legacy tables STAY LIVE until every consumer reads the new tables
-- through nx_lib/mapping_config.py; 0075 then decapitates them.
--
-- Backfill is in-place from the legacy rows (each environment self-backfills)
-- and guarded on the target being empty, so the pre-commit hook can re-apply
-- this file. Verified on INT + PROD 2026-08-26: SearchConfig and StatConfig
-- agree on TableName for all 6 (ProcessName, ClientCode) rows, so they merge
-- into one ProcessSources row losslessly.

IF OBJECT_ID('dbo.ProcessSources', 'U') IS NULL
CREATE TABLE dbo.ProcessSources (
    ClientCode           NVARCHAR(50)  NOT NULL,
    ProcessName          NVARCHAR(100) NOT NULL,
    TableName            NVARCHAR(100) NULL,
    TableAlias           NVARCHAR(10)  NULL,
    JoinCondition        NVARCHAR(255) NULL,
    TimeFilter           NVARCHAR(255) NULL,
    SuggestionTimeFilter NVARCHAR(255) NULL,
    ExportColumn         NVARCHAR(100) NULL,
    ImportColumn         NVARCHAR(100) NULL,
    WorkitemColumn       NVARCHAR(100) NULL,
    ExtraCondition       NVARCHAR(100) NULL,
    IdColumnType         NVARCHAR(30)  NULL,  -- seeded by 0076; NULL = legacy ::text path
    CONSTRAINT PK_ProcessSources PRIMARY KEY CLUSTERED (ClientCode, ProcessName)
);
GO

IF OBJECT_ID('dbo.FieldLabels', 'U') IS NULL
CREATE TABLE dbo.FieldLabels (
    FieldKey     NVARCHAR(100) NOT NULL,
    EnglishLabel NVARCHAR(200) NOT NULL,
    GermanLabel  NVARCHAR(200) NULL,
    FrenchLabel  NVARCHAR(200) NULL,
    ItalianLabel NVARCHAR(200) NULL,
    IsSensitive  BIT NOT NULL CONSTRAINT DF_FieldLabels_IsSensitive DEFAULT (0),
    CONSTRAINT PK_FieldLabels PRIMARY KEY CLUSTERED (FieldKey)
);
GO

IF OBJECT_ID('dbo.ProcessFieldMappings', 'U') IS NULL
CREATE TABLE dbo.ProcessFieldMappings (
    ClientCode  NVARCHAR(50)  NOT NULL,
    ProcessName NVARCHAR(100) NOT NULL,
    FieldKey    NVARCHAR(100) NOT NULL,
    ColumnName  NVARCHAR(100) NOT NULL,
    ColumnType  NVARCHAR(30)  NULL,  -- native type in the target DB; seeded by 0076
    CONSTRAINT PK_ProcessFieldMappings PRIMARY KEY CLUSTERED (ClientCode, ProcessName, FieldKey),
    CONSTRAINT FK_ProcessFieldMappings_ProcessSources
        FOREIGN KEY (ClientCode, ProcessName)
        REFERENCES dbo.ProcessSources (ClientCode, ProcessName)
);
GO

IF OBJECT_ID('dbo.FieldAliases', 'U') IS NULL
CREATE TABLE dbo.FieldAliases (
    SourceFieldName NVARCHAR(100) NOT NULL,
    TargetKey       NVARCHAR(100) NOT NULL,
    CONSTRAINT PK_FieldAliases PRIMARY KEY CLUSTERED (SourceFieldName)
);
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ProcessSources)
INSERT INTO dbo.ProcessSources (ClientCode, ProcessName, TableName, TableAlias, JoinCondition,
    TimeFilter, SuggestionTimeFilter, ExportColumn, ImportColumn, WorkitemColumn, ExtraCondition)
SELECT COALESCE(s.ClientCode, c.ClientCode),
       COALESCE(s.ProcessName, c.ProcessName),
       COALESCE(s.TableName, c.TableName),
       s.TableAlias, s.JoinCondition, s.TimeFilter, s.SuggestionTimeFilter,
       c.ExportColumn, c.ImportColumn, c.WorkitemColumn, c.additionalCondition
FROM dbo.SearchConfig s
FULL OUTER JOIN dbo.StatConfig c
  ON c.ProcessName = s.ProcessName AND c.ClientCode = s.ClientCode;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.FieldLabels)
INSERT INTO dbo.FieldLabels (FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel, IsSensitive)
SELECT FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel, IsSensitive
FROM dbo.Search_Field_Labels;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.FieldAliases)
INSERT INTO dbo.FieldAliases (SourceFieldName, TargetKey)
SELECT SourceFieldName, MIN(TargetKey)
FROM dbo.IndexFieldMappings
GROUP BY SourceFieldName;  -- dups were repaired in 0052; GROUP BY is belt-and-braces
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ProcessFieldMappings)
INSERT INTO dbo.ProcessFieldMappings (ClientCode, ProcessName, FieldKey, ColumnName)
SELECT s.ClientCode, s.ProcessName, v.FieldKey, v.ColumnName
FROM dbo.SearchConfig s
CROSS APPLY (VALUES
    ('doctype', s.col_doctype), ('docbarcode', s.col_docbarcode), ('crdno', s.col_crdno),
    ('crdname', s.col_crdname), ('bankpk', s.col_bankpk), ('grossamount', s.col_grossamount),
    ('netamount', s.col_netamount), ('vatamount', s.col_vatamount), ('doccurrency', s.col_doccurrency),
    ('invoicenr', s.col_invoicenr), ('istec', s.col_istec), ('esrreference', s.col_esrreference),
    ('ordernumber', s.col_ordernumber), ('client', s.col_client), ('docsource', s.col_docsource),
    ('ownernr', s.col_ownernr), ('tenancynr', s.col_tenancynr), ('registered', s.col_registered),
    ('branch', s.col_branch), ('docdate', s.col_docdate), ('forwarding', s.col_forwarding),
    ('department', s.col_department), ('postcode', s.col_postcode), ('recipient', s.col_recipient),
    ('confidentiality', s.col_confidentiality), ('propertynr', s.col_propertynr),
    ('separatorsheet', s.col_separatorsheet), ('docid', s.col_docid),
    ('archiveboxno', s.col_archiveboxno), ('targetsystemfilename', s.col_targetsystemfilename),
    ('emailfromaddress', s.col_emailfromaddress), ('batchname', s.col_batchname),
    ('pid', s.col_pid), ('dossierpositioninbatch', s.col_dossierpositioninbatch),
    ('pagecount', s.col_pagecount), ('validationuser', s.col_validationuser)
) AS v(FieldKey, ColumnName)
WHERE v.ColumnName IS NOT NULL;
GO
```

- [ ] **Step 3:** Verify the `CROSS APPLY` column list is complete against the live DDL: `grep -c "col_" sql/NexoraDB/Tables/dbo.SearchConfig.sql` — the VALUES list above has 36 entries; if the dump shows more `col_*` columns than 36 (a migration added one since planning), add the missing pairs.
- [ ] **Step 4:** Apply + verify parity counts (read-only, against INT):

```
python scripts/db-migrate.py --env INT
```

Then run this one-off check (Bash heredoc, uses `env/INT.env` like `scripts/test_db_reset.py` does):

```python
# parity: ProcessSources row count == FULL OUTER JOIN count of legacy pair;
# ProcessFieldMappings count == number of non-NULL col_* cells in SearchConfig;
# FieldLabels/FieldAliases counts == legacy counts (aliases after GROUP BY).
```

Expected on INT (2026-08-26 baseline): ProcessSources 6, FieldLabels 38, FieldAliases 56, ProcessFieldMappings = non-NULL cell count (assert equality in the script, don't hardcode).
- [ ] **Step 5:** `python sql/sync-from-db.py` — stage the four new dump files it creates.
- [ ] **Step 6:** Commit:

```
git add sql/_migrations/NexoraDB/0074_normalized_mapping_schema.sql sql/NexoraDB/Tables/dbo.ProcessSources.sql sql/NexoraDB/Tables/dbo.ProcessFieldMappings.sql sql/NexoraDB/Tables/dbo.FieldLabels.sql sql/NexoraDB/Tables/dbo.FieldAliases.sql
git commit -F - <<'EOF'
feat(db): normalized mapping schema ProcessSources + field tables (#98)

Migration 0074 creates ProcessSources (merges SearchConfig table plumbing
with StatConfig -- verified identical TableName per process on INT+PROD),
tall ProcessFieldMappings (kills the wide col_* columns), FieldLabels and
FieldAliases (PK on SourceFieldName -- the unique key IndexFieldMappings
never had), and backfills all four from the legacy tables in place. Legacy
tables stay live until every consumer is cut over (0075 decapitates them).

Co-Authored-By: <executing model trailer>
EOF
```

### Task 2: `nx_lib/mapping_config.py` — the cached registry accessor

**Files:**
- Create: `nx_lib/mapping_config.py`
- Test: `tests/unit/test_mapping_config.py`

**Interfaces (later tasks consume exactly these):**

```python
registry() -> MappingRegistry | None          # None on load failure; cached 60s success-only
invalidate_mapping_config() -> None
valid_field_keys() -> set[str]                # {} on failure (legacy get_valid_search_columns -> [])
field_keys_for_processes(processes) -> set[str] | None   # None on failure (API fails closed)
sensitive_field_keys() -> set[str] | None
labels() -> dict[str, dict] | None            # field_key -> {"en","de","fr","it","sensitive"}
field_aliases() -> dict[str, str]             # {} on failure (legacy get_index_field_mappings -> {})
sources_for(client, processes=None) -> list[ProcessSource]
mappings_for(client, processes, field_keys=None) -> list[FieldMapping]
```

`ProcessSource` and `FieldMapping` are frozen dataclasses:

```python
@dataclass(frozen=True)
class ProcessSource:
    client: str; process: str; table: str | None; alias: str | None
    join_condition: str | None; time_filter: str | None
    suggestion_time_filter: str | None; export_column: str | None
    import_column: str | None; workitem_column: str | None
    extra_condition: str | None; id_column_type: str | None

@dataclass(frozen=True)
class FieldMapping:
    client: str; process: str; field_key: str
    column: str; column_type: str | None
```

- [ ] **Step 1: Write the failing test** `tests/unit/test_mapping_config.py`. Mock `engine_nexora_db.raw_connection()` the same way the existing config-helper tests do (see `tests/unit/test_process_helpers.py` for the house mocking pattern). Cover at minimum:

```python
def test_registry_loads_all_four_tables_in_one_connection(...)
def test_registry_load_failure_returns_none_and_is_not_cached(...)   # second call re-queries
def test_valid_field_keys_empty_on_failure(...)
def test_field_keys_for_processes_none_on_failure(...)               # API fail-closed contract
def test_sensitive_field_keys_none_on_failure(...)
def test_mappings_for_filters_client_processes_and_fields(...)
def test_sources_for_default_and_ms02_partition(...)
def test_invalidate_drops_cache(...)
def test_field_aliases_empty_on_failure(...)
```

- [ ] **Step 2:** Run: `C:\dev\nexora\.venv\Scripts\python.exe -m pytest tests/unit/test_mapping_config.py -q --no-cov` — expected FAIL: `ModuleNotFoundError: No module named 'nx_lib.mapping_config'`.
- [ ] **Step 3: Implement** `nx_lib/mapping_config.py`. Skeleton (fill the load with the four straight SELECTs; no `SELECT TOP 0` introspection anywhere):

```python
"""Single cached accessor for the doc-field / process mapping config (#98).

Loads dbo.ProcessSources / ProcessFieldMappings / FieldLabels / FieldAliases
(migration 0074) into one frozen registry. Replaces ~30 hand-rolled SELECTs
against the legacy SearchConfig/Statconfig/IndexFieldMappings/
Search_Field_Labels tables.

Failure contract (inherited from the legacy helpers, do not weaken):
- a load error returns None from registry() and is NEVER cached (a cached
  empty fallback once disabled doc-field search app-wide for an hour);
- callers that historically failed OPEN behind session permissions coerce
  None to an empty value themselves; the external API keeps failing CLOSED
  on None (see field_keys_for_processes).
"""

from dataclasses import dataclass

from flask import current_app

from .db import engine_nexora_db
from .extensions import cache

_CACHE_KEY = "mapping_config_registry"
_TTL = 60  # seconds; admin-UI edits (phase 4) should apply fast


def registry():
    reg = cache.get(_CACHE_KEY)
    if reg is not None:
        return reg
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT ClientCode, ProcessName, TableName, TableAlias, JoinCondition, "
            "TimeFilter, SuggestionTimeFilter, ExportColumn, ImportColumn, "
            "WorkitemColumn, ExtraCondition, IdColumnType FROM ProcessSources"
        )
        sources = { (r.ClientCode, r.ProcessName): ProcessSource(...) for r in cur.fetchall() }
        cur.execute("SELECT ClientCode, ProcessName, FieldKey, ColumnName, ColumnType FROM ProcessFieldMappings")
        ...
        cur.execute("SELECT FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel, IsSensitive FROM FieldLabels")
        ...
        cur.execute("SELECT SourceFieldName, TargetKey FROM FieldAliases")
        ...
        reg = MappingRegistry(sources=sources, mappings=mappings, labels=labels, aliases=aliases)
        cache.set(_CACHE_KEY, reg, timeout=_TTL)  # success-only
        return reg
    except Exception as e:
        current_app.logger.error(f"mapping_config load: {e}")
        return None
    finally:
        if conn:
            conn.close()
```

Field keys are stored lowercased at load (`FieldKey.lower()`) so every membership check matches the legacy lowercase convention (`col_*` names were compared `.lower()` throughout).
- [ ] **Step 4:** Run: `C:\dev\nexora\.venv\Scripts\python.exe -m pytest tests/unit/test_mapping_config.py -q --no-cov` — expected PASS.
- [ ] **Step 5: Commit**

```
git add nx_lib/mapping_config.py tests/unit/test_mapping_config.py
git commit -F - <<'EOF'
feat(config): cached mapping_config registry over the 0074 tables (#98)

One frozen registry (ProcessSources/ProcessFieldMappings/FieldLabels/
FieldAliases) cached 60s success-only, with the legacy failure contract
preserved: None on load error (never cached), fail-closed None for the
external-API surface, lowercased field keys. No consumer cut over yet.

Co-Authored-By: <executing model trailer>
EOF
```

---

# PHASE B — consumer cutover (one file per task; legacy tables still live)

**Shared cutover rules for Tasks 3–9:**
- Each task first updates that file's tests (they mock cursors returning legacy-shaped rows — replace with `monkeypatch` of the `mapping_config` functions, which is strictly simpler), runs them RED where the assertion changed, then edits the consumer, then GREEN.
- Grep check after each task: the edited file must contain **zero** occurrences of `SearchConfig`, `Statconfig`, `IndexFieldMappings`, `Search_Field_Labels`, `SELECT TOP 0` (except in comments explaining history).
- Run the file's full test module + `ruff check` before each commit.

### Task 3: `views/workitems.py` — config helpers

**Files:** Modify: `nx_lib/views/workitems.py` · Test: `tests/integration/test_workitems_routes.py` (existing doc-field/config tests)

Replace these five helpers' bodies with registry reads (signatures and return conventions unchanged — their ~20 intra-file callers keep working):

- `get_valid_search_columns()` — anchored on its docstring `"""Whitelist of SearchConfig col_<field> columns.` — becomes a thin wrapper returning `[f"col_{k}" for k in mapping_config.valid_field_keys()]`. **Keep returning `col_`-prefixed lowercase names for now** — the call sites strip/compare with the prefix; Task 4 removes the prefix convention inside the resolution blocks it rewrites, and Task 6 finishes the rest. (Deliberate two-step: keeps this task mechanical.)
- `get_search_columns_for_processes(processes)` — anchored on `f"SELECT * FROM SearchConfig WHERE ProcessName IN ({placeholders})"` — becomes `mapping_config.field_keys_for_processes(processes)` mapped to `col_`-prefixed names; **must still return `None` on failure** (external API fail-closed — `nx_lib/views/api_external.py` depends on it).
- `get_sensitive_field_keys()` / `get_sensitive_field_tokens()` — anchored on `"SELECT FieldKey FROM Search_Field_Labels WHERE IsSensitive = 1"` — read `mapping_config.sensitive_field_keys()` / build tokens from `mapping_config.labels()` (same `None`-on-failure, success-only caching now lives in the registry; delete the per-helper `cache.get/set` blocks).
- The `/api/config_fields` endpoint body — anchored on `cursor.execute("SELECT TOP 0 * FROM SearchConfig")` under the `_cache_key = f"config_fields_` block — builds `search_options` from `mappings_for` + `labels()` instead of the introspection + wide-row walk. Keep the endpoint's own 3600 s response cache and its `sensitive_blocked_keys()` filtering exactly as they are.
- The second labels+introspection site (CSV-export/detail headers; anchored on the OTHER `cursor.execute("SELECT TOP 0 * FROM SearchConfig")` occurrence near `SELECT FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel FROM Search_Field_Labels` later in the file) — same replacement.

- [ ] Update the affected tests in `tests/integration/test_workitems_routes.py` (grep it for `SearchConfig` / `Search_Field_Labels` mocks) to monkeypatch `nx_lib.mapping_config` instead; run RED.
- [ ] Rewrite the five sites; run `C:\dev\nexora\.venv\Scripts\python.exe -m pytest tests/integration/test_workitems_routes.py tests/unit/test_mapping_config.py -q --no-cov` — GREEN.
- [ ] Grep gate: `grep -n "Search_Field_Labels\|SELECT TOP 0" nx_lib/views/workitems.py` → only the two doc-field resolution blocks (Task 4) and suggestion endpoints (Task 6) may still hit `SearchConfig`.
- [ ] Commit: `refactor(workitems): config helpers read mapping_config registry (#98)` (body: which five helpers, contract unchanged, `None`-on-failure preserved for the external API).

### Task 4: `views/workitems.py` — the two doc-field resolution blocks

**Files:** Modify: `nx_lib/views/workitems.py` · Test: `tests/integration/test_workitems_routes.py`

The default block is anchored on the comment `# Doc-field search is pre-resolved (against SearchConfig -> StatisticsDB) into` and its per-pair query `FROM SearchConfig` / `AND ClientCode = 'default'`; the MS02 block on `# --- MS02 columnar doc-field pre-resolution (sibling to the default block) ---`. Both currently run **one `SearchConfig` query per pair per leg**. Rewrite:

- One `mapping_config.mappings_for(client, target_processes)` + `sources_for(client, target_processes)` call per leg, before the pair loop (registry is cached — zero NexoraDB round-trips).
- Per pair, per matching `FieldMapping`, build the same UNION-ALL parts (default leg) / specs list (MS02 leg) as today. The `id_col` extraction from `JoinCondition` (`re.split(r"\s*=\s*", ...)` on the default leg, `_ms02_id_column(...)` on the MS02 leg) moves to operate on `ProcessSource.join_condition`/`ProcessSource.alias` — logic unchanged.
- **Predicate shape unchanged in this task** (still `CAST(... AS NVARCHAR(MAX)) COLLATE DATABASE_DEFAULT` / `::text ILIKE`) — Task 12 does sargability. This task is a pure config-source swap.
- MS02 specs stay `(table, id_col, field_col, time_filter)` 4-tuples in this task (Task 12 widens them).
- Preserve exactly: value-first fan-out across non-sensitive keys, forced-empty pair on unmapped field, tolerant-skip on unusable mapping rows, fail-closed folding (`docfield_ids` / `ms02_docfield_ids` semantics, `# Fail CLOSED:` block untouched).

- [ ] Update the doc-field search tests (grep `test_workitems_routes.py` for `docfield`) to seed via monkeypatched registry; RED → rewrite → GREEN.
- [ ] Also run: `C:\dev\nexora\.venv\Scripts\python.exe -m pytest tests/integration/test_api_external_routes.py -q --no-cov` (the external API shares these paths).
- [ ] Commit: `refactor(workitems): docfield resolution reads mapping registry (#98)`.

### Task 5: `views/workitems.py` — PID specs, register stamp, prepared-docs gate

**Files:** Modify: `nx_lib/views/workitems.py` · Test: `tests/integration/test_workitems_routes.py`

- `_ms02_pid_specs(target_processes)` — anchored on `f"SELECT TableName, TableAlias, JoinCondition, {col} FROM SearchConfig "` — build from `mappings_for("ms02", target_processes, field_keys={"pid"})` + `sources_for("ms02", ...)`. Same `[]`-when-unseeded contract.
- `_ms02_prepared_docs_processes()` — anchored on `f"SELECT DISTINCT ProcessName FROM SearchConfig "` — becomes the distinct processes of `mappings_for("ms02", None, field_keys={"pid"})`.
- `_stamp_in_register(rows)` itself doesn't query config (it calls the two above) — verify only.

- [ ] Tests RED→GREEN as before, then commit: `refactor(workitems): pid specs + register gate on mapping registry (#98)`.

### Task 6: `views/workitems.py` — suggestion endpoints (+ drop the `col_` convention)

**Files:** Modify: `nx_lib/views/workitems.py` · Test: `tests/integration/test_workitems_routes.py`

- `/api/docfield_values` field-specific path — anchored on `f"SELECT * FROM SearchConfig WHERE {target_col_name} IS NOT NULL "` — and `_docfield_values_all_fields` — anchored on `f"SELECT * FROM SearchConfig WHERE ({non_null}) "` — read the registry; keep the 600 s suggestion caches and their key shapes (they encode the sensitive-perm column set — a security property, see the `# Cache key includes the column set` comment).
- With every `SearchConfig` read gone from the file, retire the `col_` prefix internally: `get_valid_search_columns()`/`get_search_columns_for_processes()` now return **bare lowercase field keys**; update their remaining call sites in this file and in `nx_lib/views/api_external.py` (grep both for `col_` and `removeprefix("col_")` — delete the prefix round-trips).
- Grep gate: `grep -n "SearchConfig\|col_" nx_lib/views/workitems.py nx_lib/views/api_external.py` → zero matches outside comments.

- [ ] Tests RED→GREEN (`test_workitems_routes.py` + `test_api_external_routes.py`), commit: `refactor(workitems): suggestions on registry, retire col_ prefix (#98)`.

### Task 7: `views/dashboard.py`

**Files:** Modify: `nx_lib/views/dashboard.py` · Test: `tests/unit/test_dashboard_stats.py`, `tests/integration/test_dashboard_routes.py`

Five near-identical sites, all anchored on `FROM Statconfig WHERE ProcessName IN ({placeholders})` (grep the file; one variant selects fewer columns). Each becomes `mapping_config.sources_for(client=None, processes=target_processes)` → the existing `_split_stat_configs(configs)` splitter takes `ProcessSource` objects instead of pyodbc rows — update its attribute access (`ExportColumn` → `.export_column` etc.) once, in one place.

- [ ] Tests (grep the two test files for `Statconfig` mocks) RED→GREEN, grep gate `grep -c "Statconfig" nx_lib/views/dashboard.py` → 0, commit: `refactor(dashboard): stat sources from mapping registry (#98)`.

### Task 8: `views/reporting.py` + `reporting/catalog.py`

**Files:** Modify: `nx_lib/views/reporting.py`, `nx_lib/reporting/catalog.py` · Test: `tests/unit/test_reporting_catalog.py`, `tests/unit/test_reporting_query.py`, `tests/unit/test_reporting_ai_schema.py`, `tests/integration/test_reporting_routes.py`

- `_load_stat_configs` (anchored on `f"SELECT * FROM Statconfig WHERE ProcessName IN ({ph}) AND ISNULL(ClientCode, 'default') <> 'ms02'"`) and `_load_field_col_maps` (anchored on its `cur.execute("SELECT TOP 0 * FROM SearchConfig")`) in `views/reporting.py` → registry reads (`sources_for` filtered to `client != 'ms02'`; `mappings_for`).
- `reporting/catalog.py`: the availability map (anchored on `f"SELECT ProcessName, {select_cols} FROM SearchConfig WHERE ClientCode = 'default'"`) and the Statconfig synthetic-date block (anchored on `"SELECT * FROM Statconfig WHERE ISNULL(ClientCode, 'default') <> 'ms02'"`) → registry reads. The `Search_Field_Labels` labels read (anchored on `"FROM Search_Field_Labels"`) → `mapping_config.labels()`. **Leave the `FieldMetadata` block exactly as is (D10).** `date_availability(...)` gets `ProcessSource` objects — its defensive `getattr(r, "WorkitemColumn", None)` reads become plain attribute access.
- [ ] Tests RED→GREEN, grep gates on both files, commit: `refactor(reporting): catalog + stat configs from mapping registry (#98)`.

### Task 9: `process_helpers.py` + `octo.py`

**Files:** Modify: `nx_lib/process_helpers.py`, `nx_lib/octo.py` · Test: `tests/unit/test_process_helpers.py`, `tests/unit/test_octo.py`

- `build_stat_query(proc)` — anchored on `query = "SELECT TableName, ExportColumn, additionalCondition FROM Statconfig WHERE ProcessName = ?"` — returns the same 3-tuple shape from `sources_for(client=None, processes=[proc])` (callers index the row positionally — check them via grep `build_stat_query(`).
- `get_index_field_mappings()` in `octo.py` — anchored on `cursor.execute("SELECT SourceFieldName, TargetKey FROM IndexFieldMappings")` — returns `mapping_config.field_aliases()`; delete its own `@cache.cached` decorator (the registry caches now) but keep the function as the stable seam its callers import.
- [ ] Tests RED→GREEN, commit: `refactor(config): process_helpers + octo on mapping registry (#98)`.

### Task 10: decapitate the legacy tables + docs sweep

**Files:**
- Create: `sql/_migrations/NexoraDB/0075_decapitate_legacy_mapping_tables.sql`
- Modify: `CLAUDE.md`, `docs/design/ms02-multisource.md`, `CHANGELOG.md`; regenerated dumps under `sql/NexoraDB/Tables/`

- [ ] **Repo-wide grep gate first** — must all be zero (code; docs handled below): `grep -rn "SearchConfig\|Statconfig\|StatConfig\|IndexFieldMappings\|Search_Field_Labels" nx_lib/ --include="*.py" | grep -v "decapitated"`.
- [ ] Run the FULL gate before decapitating (order-dependent e2e: `python scripts/test_db_reset.py` first): `C:\dev\nexora\.venv\Scripts\python.exe -m pytest -q` — all green.
- [ ] Write `0075_decapitate_legacy_mapping_tables.sql` following the `0042` sp_rename convention verbatim (guards: `OBJECT_ID(old) IS NOT NULL AND OBJECT_ID(new) IS NULL`; sp_rename's second arg is the BARE new name; four renames: `SearchConfig`→`decapitated_SearchConfig`, `StatConfig`→`decapitated_StatConfig`, `IndexFieldMappings`→`decapitated_IndexFieldMappings`, `Search_Field_Labels`→`decapitated_Search_Field_Labels`). Header states data is preserved and a later cycle drops them (like `0072` dropped the previous batch).
- [ ] `python scripts/db-migrate.py --env INT && python sql/sync-from-db.py` — stage renamed dumps.
- [ ] Docs sweep in the same commit: `grep -rn "SearchConfig\|Statconfig\|IndexFieldMappings\|Search_Field_Labels" CLAUDE.md docs/ --include="*.md" -l` — update **CLAUDE.md** (the Databases section's `dbo.Statconfig.ClientCode` / `dbo.SearchConfig.ClientCode` sentences → the new table names + `nx_lib/mapping_config.py`; note CLAUDE.md may have been trimmed to map-not-manual by `chore/trim-agent-context` — if the sentences moved to `docs/design/architecture-conventions.md`, fix them THERE and keep CLAUDE.md to a one-line pointer, don't regrow it), **`docs/design/ms02-multisource.md`** (its SearchConfig/StatConfig references), and add the CHANGELOG entry (`### Changed` — normalized mapping schema, accessor, legacy tables decapitated). Historical plans/handoffs under `docs/superpowers/` are immutable — do NOT edit those.
- [ ] Restart dev server + smoke in browser (`nx -r`, then `nx -u -b --loginas:ben.streich`): Workitems doc-field search returns rows; dashboard renders; Reporting Simple tab lists fields. Screenshot to `var/screenshots/` if running remote.
- [ ] Commit: `refactor(db)!: decapitate legacy mapping tables after cutover (#98)` (body: migration 0075, all consumers on mapping_config, docs synced).

---

# PHASE C — performance (needs Phase B complete)

### Task 11: seed `ColumnType` / `IdColumnType` (script + generated migration `0076`)

**Files:**
- Create: `scripts/seed_column_types.py`, `sql/_migrations/NexoraDB/0076_seed_column_types.sql` (generated, then committed)

- [ ] Write `scripts/seed_column_types.py` (read-only against the target DBs): for every `ProcessSources` row + its `ProcessFieldMappings`, resolve each mapped column's native type — SQL Server rows (client `default`) from StatisticsDB `INFORMATION_SCHEMA.COLUMNS` (table name minus the `dbo.` prefix), PG rows (client `ms02`) from `information_schema.columns` on the MS02 doc-field DB (strip `public."…"` quoting). Also resolve the id column's type (parse it from `JoinCondition` exactly the way the runtime does) into `IdColumnType`. The script PRINTS a complete migration file body of guarded `UPDATE dbo.ProcessFieldMappings SET ColumnType = '<type>' WHERE ClientCode = ... AND ProcessName = ... AND FieldKey = ...;` / `UPDATE dbo.ProcessSources SET IdColumnType = ...;` statements. Unresolvable columns (table/column missing) are emitted as SQL comments, never as UPDATEs — `NULL` keeps the legacy path (D5).
- [ ] Run it, review the output by eye (types must be plausible: amounts `numeric`/`money`, dates `datetime`/`date`, ids `int`/`varchar`), save as `0076_seed_column_types.sql`, apply to INT, `sync-from-db.py` (dumps don't change — data-only migration).
- [ ] Commit: `feat(db): seed mapping column types from live target DBs (#98)` (script + generated 0076).

### Task 12: sargable predicates (SQL Server + PG)

**Files:** Modify: `nx_lib/views/workitems.py`, `nx_lib/workitem_sources.py` · Test: `tests/unit/test_docfield_predicates.py` (new), `tests/integration/test_workitems_routes.py`

- [ ] **Step 1: failing unit tests** in new `tests/unit/test_docfield_predicates.py` for a new pure helper `_docfield_predicate(alias, column, column_type, op_key, value)` in `views/workitems.py`:

```python
# text type + eq        -> ("s.DocType = ?", ["Invoice"])          (bare column, seekable)
# text type + contains  -> ("s.DocType LIKE ?", ["%Inv%"])         (bare column, still a scan but no CAST)
# int type + eq         -> ("s.CrdNo = ?", [1216])                 (native int bind)
# int type + eq, non-numeric value -> ("1=0", [])                  (can't match; no scan)
# int type + neq, non-numeric value -> ("1=1", [])
# int type + contains   -> CAST fallback (legacy shape)
# NULL type + anything  -> CAST fallback:
#   ("CAST(s.X AS NVARCHAR(MAX)) COLLATE DATABASE_DEFAULT LIKE ?", ["%v%"])
```

Type buckets: `_TEXT_TYPES = {"varchar", "nvarchar", "char", "nchar", "text"}`, `_INT_TYPES = {"int", "bigint", "smallint", "tinyint", "integer"}` (module constants next to `DOCFIELD_OPS`).
- [ ] **Step 2:** RED, then implement `_docfield_predicate` and swap the default resolution block's predicate construction — anchored on `safe_col = f"CAST({alias}.{db_column} AS NVARCHAR(MAX))"` — to call it (the `FieldMapping.column_type` is already in hand since Task 4). GREEN.
- [ ] **Step 3: PG leg.** Widen the MS02 spec tuples to `(table, id_col, field_col, time_filter, field_type)` at their build site in the MS02 resolution block, and teach `resolve_ms02_docfield_ids` / `_ms02_columnar_sql` — anchored on `sql = f'SELECT DISTINCT "{id_col}" FROM {table} WHERE "{field_col}"::text {value_clause}'` — the typed path: int-typed field + `eq` → `"{field_col}" = %s` with `int(value)` (unparseable → forced-empty spec); everything else keeps `::text ILIKE`. Same for the id side everywhere `"{id_col}"::text = ANY(%s)` appears (`_ms02_columnar_sql`, `resolve_ms02_pid_to_wids`, `resolve_ms02_wids_to_pids`): when the source's `IdColumnType` is int-typed, emit `"{id_col}" = ANY(%s)` with int lists. Keep the 4-tuple accepted for backward compat (`len(spec)` guard) so `_ms02_pid_specs` callers can migrate in the same commit.
- [ ] **Step 4: live parity check on INT** (this is the step that catches collation surprises, D6): run a one-off script comparing old-shape vs new-shape result sets on StatisticsDB for each mapped text column with a real sampled value, ops `eq` + `contains` (`SELECT` with CAST+COLLATE vs bare column). Any mismatch → that column keeps `ColumnType = NULL` (UPDATE it back in a fixup migration) and gets a note in the plan's Gotchas. Document the checked columns in the commit body.
- [ ] **Step 5:** Full workitems + sources tests green, commit: `perf(workitems): sargable docfield predicates from ColumnType (#98)`.

### Task 13: allow-set result cache (60 s)

**Files:** Modify: `nx_lib/views/workitems.py` · Test: `tests/integration/test_workitems_routes.py`

- [ ] Failing test: two identical `/api/workitems` doc-field requests hit the resolution path once (assert via monkeypatched resolver call counter); an error-path resolution (StatisticsDB raise) is NOT cached (second call re-resolves).
- [ ] Implement in `_get_workitems_data`, wrapping each leg's whole pair-fold: key `f"docfield_ids_{leg}_" + hashlib.sha1(repr((sorted(target_processes), pairs_normalized)) .encode()).hexdigest()` where `pairs_normalized` is the tuple of `(field, value, op, comb)` for non-empty values, `leg` is `default` / `ms02`; store `("v", result_set)` sentinel tuples (so a legitimately-empty resolved set is distinguishable from a cache miss), TTL 60; **never** store when the leg ended in the error/`None` path (D7). Sensitive-field filtering happens BEFORE the key is built (blocked pairs are dropped from `pairs_normalized`), so users with different sensitive perms naturally get different keys.
- [ ] GREEN, commit: `perf(workitems): cache resolved docfield allow-sets 60s (#98)`.

### Task 14: batched `WorkitemSourceCache` + composite PK (`0077`)

**Files:**
- Create: `sql/_migrations/NexoraDB/0077_workitemsourcecache_composite_pk.sql`
- Modify: `nx_lib/workitem_sources.py` · Test: `tests/unit/test_workitem_sources.py` (grep for the existing cache tests; create the file if none exists)

- [ ] Migration `0077` (idempotent):

```sql
-- 0077: WorkitemSourceCache PK (WorkItemID) -> (WorkItemID, ClientCode) (#98).
-- Ids collide across clients (1216 on INT); a single-column PK could only
-- ever pin one client per id. Reader treats >1 row per id as ambiguous.
DECLARE @pk sysname = (
    SELECT kc.name FROM sys.key_constraints kc
    WHERE kc.parent_object_id = OBJECT_ID('dbo.WorkitemSourceCache') AND kc.type = 'PK'
      AND 1 = (SELECT COUNT(*) FROM sys.index_columns ic
               WHERE ic.object_id = kc.parent_object_id AND ic.index_id = kc.unique_index_id)
);
IF @pk IS NOT NULL
    EXEC('ALTER TABLE dbo.WorkitemSourceCache DROP CONSTRAINT ' + @pk);
IF NOT EXISTS (SELECT 1 FROM sys.key_constraints
               WHERE parent_object_id = OBJECT_ID('dbo.WorkitemSourceCache') AND type = 'PK')
    ALTER TABLE dbo.WorkitemSourceCache
        ADD CONSTRAINT PK_WorkitemSourceCache PRIMARY KEY CLUSTERED (WorkItemID, ClientCode);
GO
```

- [ ] Failing tests: `_cache_lookup_many(["1","2","3"])` issues ONE query and returns `{"1": "ms02"}` for hits; an id with two rows is OMITTED from the map (ambiguous → re-probe); `_cache_lookup` returns `None` (+ error log) when its id has >1 rows.
- [ ] Implement `_cache_lookup_many(workitem_ids)` next to `_cache_lookup` (chunked `WHERE WorkItemID IN (...)` at 1000 params, one connection); change `_cache_lookup` — anchored on `"SELECT ClientCode FROM WorkitemSourceCache WHERE WorkItemID = ?"` — to `fetchall()` + ambiguity guard; `_cache_store`'s MERGE `ON` clause gains `AND tgt.ClientCode = src.ClientCode`. Rewrite the warm loop in `fetch_merged_page` — anchored on the comment `# Warm the routing cache for non-default rows on this page.` — to: collect non-default page ids → one `_cache_lookup_many` → `get_source_for_workitem(...)` only for ids missing from the map (keep passing `sources=sources`).
- [ ] Apply migration to INT, `sync-from-db.py`, stage dump. GREEN, changelog entry (`### Changed` perf items for Tasks 12–14 can share one block), commit: `perf(sources): batched source-cache lookup + composite PK (#98)`.

---

## Final gate (after Task 14)

- [ ] `python scripts/test_db_reset.py` then the full suite: `C:\dev\nexora\.venv\Scripts\python.exe -m pytest -q` — all green (pre-push runs this plus e2e; use a per-session `NEXORA_E2E_PORT`, and netstat-kill orphaned TEST servers first if e2e errors with "port in use").
- [ ] `ruff check nx_lib/ tests/` clean.
- [ ] Browser smoke with screenshots (remote rule): doc-field search field+value, value-first search, suggestions dropdown, dashboard, reporting Simple tab, MS02 prepared-docs register column.
- [ ] Verify CHANGELOG has the Added/Changed entries (0074 schema + accessor from Task 10, perf trio from Task 14).

## Gotchas & notes

- **Do not renumber someone else's migration.** Re-run the `--dry-run` check before EVERY migration-creating task; parallel sessions are normal here.
- **`registry()` returning `None` vs empty registry:** an empty-but-loaded registry (tables exist, zero rows) is a valid success and IS cached — only exceptions produce `None`. This mirrors `get_valid_search_columns` caching `[]` only when the query succeeded.
- **The 60 s allow-set cache means a repeat of the *identical* doc-field search can be up to 60 s stale** (a workitem imported seconds ago missing from a re-run). Accepted trade-off (D7) — mention it in the CHANGELOG entry.
- **Collation edge (D6/Task 12 Step 4):** bare-column comparison follows the column's collation. All StatisticsDB columns are expected on the server default (CI); the live parity check is the enforcement, and `ColumnType = NULL` is the per-column opt-out.
- **`ExtraCondition` was `Statconfig.additionalCondition`** — dashboard/reporting interpolate it into WHERE clauses verbatim. It is admin-controlled config (same trust level as `TimeFilter`); keep it flowing verbatim, don't "sanitize" it.
- **`sydoc.05_PDBS` exists ONLY as an `ms02` row** (no `default` twin) — the catalog's `ClientCode = 'default'` scoping comment describes a hypothetical. Registry filters must preserve per-client partitioning exactly (`sources_for("default")` must NOT return ms02 rows and vice versa).
- **`e2e` never sees these tables** (TEST schema omits them). If an e2e test starts failing with doc-field UI visible, the accessor is failing OPEN somewhere — that's a bug in the accessor, not the test.
- **pyodbc named-attribute access (`row.ProcessName`) disappears with the registry** — dataclass attributes are snake_case. The `_split_stat_configs` / `date_availability` updates in Tasks 7–8 are where that seam is crossed; grep for `getattr(r,` and `row.` in the touched functions when in doubt.
- **`octo.py`'s `get_index_field_mappings` keeps its name and dict contract** — its callers (`get_extensions_urls_fields` and friends) are hot-path detail rendering; only the storage moved.
- **After 0075 lands, `sync-from-db.py` renames the legacy dumps to `decapitated_*` files** — stage the renames (git sees delete+add), same as Task 1's new files.
