# MS02 client — merged multi-source workitems (Azure Postgres + second Octo endpoint)

**Status:** Design approved 2026-06-16. Awaiting spec review → implementation plan.
**Author:** session 2026-06-16.
**Scope:** Surface a new client ("MS02") inside the **shared** workitems detail page and dashboard. MS02's workitem runtime data lives in **Azure Postgres** (same schema as the existing Octo SQL Server runtime DB, Postgres dialect); MS02's Octo API is the **same API at a different domain with its own credentials**.

> **Parameters.** `client_code = ms02`; env prefix `MS02_`. Throughout, "the default client" = today's single Octo source (`engine_octo_db` + `OCTO_*` env). The concrete `MS02_*` env key names are mirrored from the existing `OCTO_*`/`DB_*` set below and must be confirmed against `env/INT.env` (AI-blocked by `.claudeignore`; values never appear in this doc).

---

## 1. Goal & non-goals

**Goal.** A user browsing the workitems list, opening a workitem detail page, exporting CSV, or viewing the dashboard sees MS02 workitems **merged in alongside** the existing (default) workitems, as one combined, globally-sorted, paginated list. Detail-page document rendering and Octo calls for an MS02 workitem transparently route to MS02's Postgres runtime DB and MS02's Octo endpoint.

**Non-goals (YAGNI).**
- **Reporting** source registry is **not** extended here (the reporting `SOURCE_ENGINES` map stays as-is). Only the workitems detail page + dashboard are in scope.
- **No Generali-style separate pages** and **no new permission family.** The merged view reuses the existing `workitems.*` permissions; MS02 visibility rides the existing per-user allowed-process / allowed-client config (the `tp.Name IN (...)` / `tp.ClientName IN (...)` allow-list already in the list query).
- No ETL/replication of MS02 data into SQL Server.

---

## 2. Current state (what the code already gives us)

- **Octo client layer (`nx_lib/octo.py`) is already domain-parameterized.** Every call — `get_workitemdata_param`, `get_extensions_urls_fields`, `get_media`, `get_activity_type_name` — takes `domain=None` and defaults to `OCTO_DOMAIN`. The token cache key is already per-domain (`octo_access_token_{domain}`).
- **`get_domain_for_workitem(workitem_id)` is a stub** that always returns `OCTO_DOMAIN`. It is the intended routing hook — currently unwired.
- **The workitems detail page already routes per workitem.** `workitems.py` calls `get_domain_for_workitem(workitem_id)` at the detail view and CSV export (lines ~591, ~1040, ~1074, ~1147) and threads the resulting `domain` into the Octo calls.
- **The dashboard does NOT route** — `dashboard.py:1463` hardcodes `OCTO_DOMAIN`.
- **Runtime-DB queries are single-source T-SQL against `engine_octo_db`.** The list count+data pass, `get_single_workitem`, the detail-page runtime query, CSV export's row source, and two dashboard sites all run SQL Server-specific SQL (`ROW_NUMBER`, `FOR JSON PATH`, `OFFSET … FETCH`, `#temp` tables, `LIKE`, three-part `[NexoraDB].dbo.x` cross-DB joins).

### Two bugs/gaps surfaced by this work

1. **`get_access_token(domain)` signs every domain with the global `OCTO_CLIENT_ID/OCTO_CLIENT_SECRET`.** A second Octo endpoint with its own credentials will not authenticate until token acquisition resolves credentials per client. **Must fix.**
2. **Dashboard hardcodes `OCTO_DOMAIN`** (`dashboard.py:1463`) — must become `get_domain_for_workitem(row.ID)`.

---

## 3. Architecture — source-adapter module

Add **`nx_lib/workitem_sources.py`**: a thin abstraction that quarantines every per-source difference (engine, SQL dialect, Octo credentials) so the views stay readable and a third client later is trivial.

### 3.1 Client registry

A config-driven registry (built once at import, from env). One entry per client:

```
ClientConfig:
    code            # "default" | "ms02"
    runtime_engine  # engine_octo_db | engine_ms02_pg
    dialect         # "tsql" | "postgres"
    octo_domain     # OCTO_DOMAIN | MS02_OCTO_DOMAIN
    octo_client_id  # OCTO_CLIENT_ID | MS02_OCTO_CLIENT_ID
    octo_secret     # OCTO_CLIENT_SECRET | MS02_OCTO_CLIENT_SECRET
    octo_grant_type # OCTO_GRANT_TYPE | MS02_OCTO_GRANT_TYPE (default to default's)
```

The `ms02` entry is present **only when its env vars are set** (graceful degrade — see §3.4). When MS02 is absent, behaviour is byte-for-byte today's single-source path.

### 3.2 `WorkitemSource` interface

```
class WorkitemSource(Protocol):
    code: str
    # returns normalized rows (dicts with a stable shape) + a total count for this source
    def list_workitems(self, filt: WorkitemFilter, limit: int) -> tuple[list[Row], int]: ...
    def get_single(self, workitem_id: str) -> Row | None: ...
    def detail_runtime(self, workitem_id: str) -> DetailRuntime | None: ...
    def dashboard_rows(self, ...) -> ...: ...
    def has_workitem(self, workitem_id: str) -> bool:   # cheap existence probe for routing
```

Two implementations:
- **`SqlServerSource`** — wraps `engine_octo_db`; SQL is the existing T-SQL, lifted verbatim where possible.
- **`PostgresSource`** — wraps `engine_ms02_pg`; SQL is the **dialect twin** (see §4.2).

A module-level `active_sources()` returns the registered sources (default always; ms02 when configured), and `source_for(client_code)` resolves one.

### 3.3 Routing — probe-then-cache

Because the two clients are partitioned by database, "which client owns id X" = "which runtime DB contains X."

- **Cache table `dbo.WorkitemSourceCache` (NexoraDB)** — `WorkItemID → ClientCode`, plus `ResolvedAt`.
- **`get_source_for_workitem(id)`**: cache hit → return; miss → probe each source's `has_workitem(id)` (default first, deterministic), cache the winner, return it. Unknown id → default (preserves today's behaviour / 404 path).
- **`get_domain_for_workitem(id)`** (now real): `get_source_for_workitem(id)` → that client's `octo_domain`.
- **Cache warming**: the merged list already knows each row's source, so it **upserts `id → client` as it renders**. Detail pages opened from the list are therefore pre-warmed and never probe.

### 3.4 New engine

```python
# nx_lib/db.py
if cfg.MS02_DB_HOST and cfg.MS02_DB_NAME and cfg.MS02_DB_USER and cfg.MS02_DB_PWD:
    engine_ms02_pg = create_engine(
        get_pg_url(...),   # postgresql+psycopg2://…?sslmode=require
        pool_size=5, max_overflow=10, pool_timeout=30,
        pool_recycle=1800, pool_pre_ping=True,
    )
else:
    engine_ms02_pg = None
```

- New `get_pg_url(...)` helper (URL-encoded creds, `sslmode=require` for Azure).
- Add **`psycopg2-binary`** to `requirements.txt` (and `sql/requirements.txt` is unrelated — leave it).
- `ping_db` / `_ping_db_probe` already issue `SELECT 1`, which is valid Postgres — works unchanged. Add `engine_ms02_pg` to the admin DB-ping list (`admin.py`) and to `nx --doctor`.
- Graceful-degrade guard mirrors `engine_statistics_ro` / `engine_octo_ro`, so other dev/test boxes without MS02 env boot normally.

---

## 4. The merged list (the heart)

### 4.1 Filter taxonomy

The existing list WHERE clause splits cleanly:

| Filter | Source of truth | PG handling |
|---|---|---|
| process name `tp.Name`, client `tp.ClientName`, `Status`, `ActivityInstanceName`, `id LIKE`, `ModifiedAt` range | runtime DB (`t_*`) | **portable** — translate dialect, run on each source |
| doc-field search | **per source** (see §4.6) — default: `SearchConfig`→StatisticsDB; MS02: its own `t_documentindexes` | default pre-resolves to an ID set (existing block) for the SQL Server source; MS02 applies an in-query `EXISTS` against `t_documentindexes`. **No shared id-set.** |
| **tag** (`Workitem_Tags`/`Tags`), **priority** (`Workitem_Metadata`), **assigned-user** (`Workitem_Metadata`) | **NexoraDB** | **pre-resolve to an ID set** from NexoraDB (same pattern as doc-field), then `id IN (...)` on both sources |

So NexoraDB-dependent filters are lifted out of the per-source query and turned into an allow-set of IDs — the per-source SQL becomes pure runtime-DB SQL that ports to Postgres.

### 4.2 Dialect twins (T-SQL → Postgres)

- `OFFSET ? ROWS FETCH NEXT ? ROWS ONLY` → `LIMIT ? OFFSET ?`
- `ROW_NUMBER() OVER(PARTITION BY … )` dedupe → same window function (portable) or `DISTINCT ON` — keep window function for parity.
- `FOR JSON PATH` tag subqueries → **removed from the runtime query**; tags/priority/metadata become app-side enrichment (§4.3), so neither source emits JSON.
- `#temp` tables for large doc-field ID sets → the ID set is already materialized in Python; pass as `id IN (...)` / `= ANY(%s)` (Postgres array) without temp tables. (SQL Server side keeps temp tables if the set is huge.)
- `CASE … LIKE '%C+A%'` stage derivation → identical (`LIKE` portable).
- `ISNULL(...)` → `COALESCE(...)`.
- Parameter marker: pyodbc uses `?`, psycopg2 uses `%s`. The source impl owns its own marker; the `WorkitemFilter` carries dialect-neutral predicate parts + params and each source renders them.

### 4.3 NexoraDB enrichment (Postgres source only)

The **SQL Server source keeps its in-query cross-DB joins** to NexoraDB (`Workitem_Metadata` for Priority, `Workitem_Tags`⋈`Tags` for tags) — zero behaviour change, lowest risk. The **Postgres source cannot join NexoraDB in-query**, so after it fetches base rows it enriches Priority + tags app-side over its row ids via the shared `enrich_rows_from_nexora` helper. Both sources emit the same normalized row shape; the small duplication (in-query for SS, app-side for PG) is deliberate, to avoid refactoring the proven default query.

(NexoraDB-backed **filters** — tag/priority/assigned — are pre-resolved to an ID set for the PG source via `resolve_nexora_filter_ids`, since those metadata rows live in NexoraDB for workitems of **every** client.)

### 4.4 Pagination & count

- Each source runs the shared (portable) WHERE + `ORDER BY ModifiedAt DESC`, returning its top **`offset + limit`** rows.
- Merge in Python by `ModifiedAt DESC` (tie-break on `WorkItemID` for stable order), slice `[offset : offset + limit]`.
- `total = Σ per-source counts`.
- Correct for global ordering. Cost grows with page depth; acceptable for operational queue depths. **Confirm the page size** (`limit`) during planning and note worst-case depth.

### 4.5 Resilience

Per-source query runs under a wall-clock timeout (same philosophy as `ping_db`). If MS02's Postgres is slow/unreachable, the list **degrades to default-only + a non-blocking banner** ("MS02 source temporarily unavailable") rather than hanging or erroring the whole page. A down second source must never take down the list.

### 4.6 Doc-field search is per source (`t_documentindexes`)

For the default client, doc-field search resolves via `SearchConfig` (NexoraDB) → StatisticsDB and is pre-applied as an ID set (existing block, kept inside the SQL Server source). MS02 has **no StatisticsDB**; its document index values live in its own Postgres OctoDB table **`t_documentindexes`** — a key-value store with columns `Name` (field name) and `Stringvalue` (value), joined to a workitem by `workitemid`. The Postgres source therefore resolves doc-field search **in-query**, one `EXISTS` per `(docfield, docvalue)` pair:

```sql
AND EXISTS (SELECT 1 FROM t_documentindexes di
           WHERE di.workitemid = twi."ID" AND di."Name" = %s AND di."Stringvalue" LIKE %s)
```

So `WorkitemFilter` carries the **raw** `(docfields, docvalues)` pairs; each source resolves them against its own stats store. **Field VALUES** on the detail page / CSV export are unaffected — they continue to come from the (per-client, domain-routed) Octo thin-document API for every client; `t_documentindexes` is **search-only**. *Confirm at build time:* the MS02 `t_documentindexes` identifier casing, and whether the UI doc-field identifier matches `t_documentindexes."Name"` (a name-mapping may be needed).

---

## 5. Detail page, single-workitem, CSV export, dashboard

- **Detail page** (`workitem_detail`): runtime-DB query routes via `get_source_for_workitem(id)` → source impl; Octo calls already route via `get_domain_for_workitem(id)` (now real). Document rendering / field & table source highlighting are unchanged — they consume Octo output that's already domain-routed.
- **`get_single_workitem`**: route to the owning source; tags via app-side enrichment.
- **CSV export**: rows come from the merged list path; per-row Octo via the row's domain (already plumbed at line ~591/602).
- **Dashboard (OctoDB-based bits)**: the two `engine_octo_db` sites (KPI backlog `C+A` count; activity feed) become source-aware; `dashboard.py:1463` `OCTO_DOMAIN` → `get_domain_for_workitem(row.ID)`. Counts that today come from one OctoDB query become a sum across sources.

### 5.1 Dashboard statistics (multi-source)

The dashboard's Statistics-DB-backed widgets (`processed_over_time`, `kpi_stats` processed/imported counts, and the other chart endpoints) are driven by `Statconfig` (NexoraDB): `ProcessName → (TableName, ExportColumn, ImportColumn, additionalCondition)`, aggregated against `[{DB_STATISTICS}].{TableName}`. MS02's processing-event data lives in a **separate MS02 Postgres table** (owner-provided name + real export/import timestamp columns) — **not** in `t_documentindexes`.

Design: extend `Statconfig` with a `ClientCode` column (default `'default'`). MS02 processes get rows with `ClientCode='ms02'`, `TableName` = the MS02 stats table, and the MS02 export/import column names. The dashboard groups configs by `ClientCode` and runs each group's aggregation against that client's stats engine (`engine_statistics_db` T-SQL vs `engine_ms02_pg` Postgres), summing per-client results in Python. The central seam is the `Statconfig`→`[(engine, sql, params)]` builder (≈`dashboard.py:1186–1201`): make it emit one tuple per `ClientCode` group with the right engine + dialect-rendered SQL, and every widget that routes through it becomes multi-source at once. PG dialect twins: `CAST(col AS DATE)`→`col::date`, `DATEADD(day,-14,GETDATE())`→`CURRENT_DATE - 14`, `GETDATE()`→`NOW()`, and drop the `[DB_STATISTICS].` prefix (the MS02 table is local to its PG DB). Same graceful-degrade as the list: a down MS02 contributes nothing; default widgets still render.

**Source-aware query-site inventory (the work):** list count pass, list data pass, `get_single_workitem`, detail-page runtime query, CSV export row source, dashboard count query, dashboard per-workitem fetch.

---

## 6. Octo credential routing

- `octo.py` gains `_octo_creds_for_domain(domain)` (or resolves via the client registry by domain): returns `(client_id, secret, grant_type)` for that client.
- `get_access_token(domain)` uses the resolved creds instead of the module-global `OCTO_CLIENT_ID/SECRET`. Default domain → default creds (unchanged behaviour); MS02 domain → `MS02_OCTO_*`.
- All other Octo functions are already domain-routed — no signature changes.

---

## 7. Config / env

New keys in `env/INT.env` (already present under `MS02_`; **confirm exact spelling**, mirror of the existing set):

| Purpose | Existing (default) | New (MS02) |
|---|---|---|
| PG host | `DB_SERVER_PRD` | `MS02_DB_HOST` |
| PG database | `DB_OCTO_RUNTIME` | `MS02_DB_NAME` |
| PG user | `DB_UID` | `MS02_DB_USER` |
| PG password | `DB_PWD` | `MS02_DB_PWD` |
| PG port | (1433) | `MS02_DB_PORT` (5432) |
| Octo domain | `OCTO_DOMAIN` | `MS02_OCTO_DOMAIN` |
| Octo client id | `OCTO_CLIENT_ID` | `MS02_OCTO_CLIENT_ID` |
| Octo client secret | `OCTO_CLIENT_SECRET` | `MS02_OCTO_CLIENT_SECRET` |
| Octo grant type | `OCTO_GRANT_TYPE` | `MS02_OCTO_GRANT_TYPE` (default → default's) |

`nx_lib/config.py` reads these with `os.environ.get`. Add sanitised placeholders to `env/INT.env.example` (and PROD/STAGING/TEST `.example`). PROD provisioning of the real values is owner-side, post-merge.

---

## 8. Database migration

**`sql/_migrations/NexoraDB/0023_create_workitem_source_cache.sql`** — create `dbo.WorkitemSourceCache (WorkItemID NVARCHAR(255) PRIMARY KEY, ClientCode NVARCHAR(50) NOT NULL, ResolvedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME())`, idempotent (`IF NOT EXISTS`). No seed rows (self-populating). Applied to INT by the pre-commit hook; to PROD by the deploy workflow.

---

## 9. Testing

- **Pure unit tests** (no DB): row normalization for each dialect; the merge+paginate+count helper over fixture rows from two sources; the filter taxonomy split (which filters become ID-sets); routing `get_source_for_workitem` decision table (cache hit / probe / unknown).
- **Integration** (real Azure PG, creds in `env/INT.env`): `PostgresSource.list_workitems` / `get_single` / `has_workitem` against the live MS02 DB; skipped (not failed) when `engine_ms02_pg is None`.
- **Resilience**: simulate PG timeout → list returns default-only + banner.
- **Browser (Playwright, `nx -u -b --loginas:<user>`):** merged list shows both sources; open an MS02 workitem's detail page (document renders via MS02 Octo); dashboard includes MS02 counts. **Screenshots** to `var/screenshots/` (frontend-visible change; restart server first for template cache).
- Respect the pre-push e2e gate (`python scripts/test_db_reset.py` first).

---

## 10. Risks & edge cases

- **Cross-source ID collision.** Confirmed disjoint/globally-unique IDs (owner, 2026-06-16), so an id maps to exactly one DB and probe-then-cache is correct today. **Fail-safe for the future** (a second Postgres client on the same server with an overlapping id space): routing trusts (1) the cache, which the merged list warms *authoritatively* from the row's real source; (2) a probe that checks **all** non-default sources and detects ambiguity rather than first-match-wins; (3) on >1 claimant, logs loudly and falls back to `default` (visible failure, never silent wrong-routing). The structural escalation when overlap becomes routine is **compound identity** — the UI carries the client tag (`?client=`) so routing never guesses; this is documented in the plan and intentionally not built now (YAGNI).
- **`media_info_{wid}` / `media_data_{wid}` cache keys are per-id** — safe iff IDs are globally unique (expected). Confirm with the GUID check above.
- **Cross-cloud latency** (on-prem IIS → Azure PG): mitigated by per-source timeout + degrade (§4.5) and a small PG pool.
- **Deep pagination** cost (§4.4): bounded by realistic queue depth; revisit only if a real workflow pages thousands deep.
- **SQL Server enrichment refactor** (§4.3) touches a working query — must be behaviour-preserving, guarded by tests comparing old vs new output on the same IDs.

---

## 11. Deploy / docs

- `psycopg2-binary` in `requirements.txt`.
- No new top-level files needing `deploy.yml` excludes (the spec/docs are dev-side; `nx_lib/workitem_sources.py` ships with `nx_lib/`).
- **Docs to update in the same change:** `CHANGELOG.md` (`[Unreleased]` → Added); `CLAUDE.md` Databases section (new `engine_ms02_pg`, the MS02 client, the source-adapter module); `docs/howto/*` if a workitems/architecture doc references the single OctoDB source; `env/*.env.example`.
- SYAPP01 Defender: no new per-request **file** paths, so no exclusion needed.

---

## 12. Build order (for the plan)

1. Config + engine + graceful degrade + `psycopg2-binary` + doctor/admin ping. (testable: doctor shows MS02)
2. Migration 0023 (cache table).
3. Client registry + Octo credential routing fix (`get_access_token`). (testable: MS02 token acquisition)
4. `workitem_sources.py`: interface + `SqlServerSource` (lift existing SQL) + behaviour-preserving enrichment refactor. (testable: default list identical to today)
5. `PostgresSource` (dialect twins) + filter-taxonomy ID-set pre-resolution. (testable: MS02-only list against live PG)
6. Routing (`get_source_for_workitem`, real `get_domain_for_workitem`, cache warm). (testable: detail page routes)
7. Merge into the list endpoint (pagination, count, resilience). (testable: merged list, Playwright + screenshots)
8. Single-workitem + detail runtime + CSV export source-awareness.
9. Dashboard source-awareness + `OCTO_DOMAIN` fix.
10. Docs + changelog + `.env.example`.
