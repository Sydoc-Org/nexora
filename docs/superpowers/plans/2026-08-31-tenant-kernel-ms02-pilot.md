# Tenant kernel + MS02 pilot (tenant platform sub-project 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Single-session planning run (recon → draft → self-red-team); every file path, symbol and quoted snippet below was Grep/Read-verified against `plan/tenant-kernel-ms02-pilot` (cut from `v3.2.4.1` at `1af51271`) on 2026-08-31 — anchor on quoted snippets + symbol names, never line numbers; **re-Grep every anchor at execution time** (see the sequencing gate below). Plan file: `docs/superpowers/plans/2026-08-31-tenant-kernel-ms02-pilot.md`.

**Goal:** Build the tenant platform's kernel — `dbo.Tenants` + the descriptor "data box" tables, a cached tenant registry, a descriptor→SQL page engine with generated list/CRUD/export pages under `/t/<code>/*`, per-tenant permissions and sidebar navigation — and prove it by rebuilding MS02 as the first descriptor-driven tenant, cutting its workitems out of the shared `/workitems` merged list after verified parity.

**Architecture:** Three new NexoraDB descriptor tables + `dbo.Tenants` feed a 60 s cached registry (`nx_lib/tenant/registry.py`, a structural twin of `nx_lib/mapping_config.py` with the same failure contract). One **parametrized** route family (`/t/<tenant_code>/<page_key>` + `/api/t/...`) serves every tenant from the registry — no per-tenant route registration; the app-pool-recycle caveat (spec T8) survives via `CLIENTS` (engines still resolve at import). Query building follows the beautify Task 14 `register_crud(app, desc)` descriptor pattern so sub-project 4 can later collapse generali onto it, but imports nothing from `nx_lib/views/generali/`. The MS02 cutover is one bit: `dbo.Clients.ServesWorkitems`, honored only by the shared *list* path — probe/detail/viewer machinery keeps seeing MS02.

**Tech Stack:** T-SQL migrations (`sql/_migrations/NexoraDB/`), pyodbc + psycopg2 via the engines in `nx_lib/db.py`, Flask-Caching `SimpleCache`, Jinja2 + one generic tenant page template, vanilla JS per #191 (shim partial + `static/js/tenant_pages.js`), Flask-Babel, pytest.

**Spec:** [`docs/superpowers/specs/2026-08-31-tenant-platform-design.md`](../specs/2026-08-31-tenant-platform-design.md) (commit `1af51271`) — decisions T1–T9 are locked; do not re-litigate them. This plan resolves Q1 (kernel uses `/t/<code>`, `/generali/*` untouched), defers Q2 (hosted-DB provisioning → sub-project 2), enumerates Q3 (parity checklist, Task 9) and assumes Q4 (house defaults; nothing per-tenant).

---

## Context an engineer needs (read first)

- **SEQUENCING GATE — do not start until the beautify campaign (phases 0+1) is merged.** It is executing NOW on its own branch (2026-08-31). Its Task 13/14 turn `nx_lib/views/generali.py` into a package with the `register_crud` descriptor factory this kernel patterns itself on, and its Task 16 splits `nx_lib/views/admin.py` into a package — **several anchors quoted below (`nx_lib/views/admin.py`, `templates/_header.html`) will have moved or changed by then. Re-Grep every anchor against the merged base before editing.** Cut your worktree from the post-beautify release branch, not from `v3.2.4.1`.
- **Branch/worktree:** parallel sessions are normal here — work in your own worktree (`git worktree add .claude/worktrees/tenant-kernel -b feat/tenant-kernel <post-beautify-base>`), stage by pathspec, commit per task, **no `git push`, no PR** (the owner reviews and pushes). The planning worktree `.claude/worktrees/plan-tenant-kernel-ms02-pilot` (branch `plan/tenant-kernel-ms02-pilot`) holds only this plan; merge/delete it when the plan lands.
- **Copy the gitignored env files into the worktree first**: `Copy-Item C:\dev\nexora\env\*.env <worktree>\env\` — pre-commit runs `scripts/db-migrate.py --env INT` and tests need `env/TEST.env`.
- **Python for tests:** `.venv\Scripts\python.exe -m pytest …` — the dev server (`bin/nx.ps1 -u`) runs global Python313.
- **Migrations needed: YES — three** (`0083` box tables, `0084` MS02 seed + permissions, `0085` cutover flag). `0082` was the last committed NexoraDB migration at planning time, **and a peer session is landing Kundenmagazin tables with their own migrations** — run `ls sql/_migrations/NexoraDB/ | tail -3` and `python scripts/db-migrate.py --env INT --dry-run` before creating each file; shift numbers if taken.
- **After every schema migration** run `python sql/sync-from-db.py` and stage the regenerated `sql/NexoraDB/Tables/*.sql` in the same commit, or the `sql-sync-check` hook blocks. Never hand-edit dumps. If the hook blocks on unrelated peer drift: `SQL_SYNC_SKIP=1 git commit …` — never `--no-verify`.
- **gitlint:** conventional-commit subject ≤72 chars, imperative, no trailing period; non-empty body wrapped ≤100 chars/line; `git commit -F -` with a here-doc; end with the executing model's `Co-Authored-By:` trailer.
- **CSP is PROD-only** — no inline `on<event>=` handlers (`tests/unit/test_no_inline_event_handlers.py` enforces). Behaviour goes in `static/js/tenant_pages.js` + `addEventListener`; the shim partial holds only Jinja data and translated strings (#191). No Jinja syntax in `static/js/*.js` (lint enforces).
- **Hand-built URLs in JS must normalize through `API_PREFIX`** (`tests/unit/test_template_url_prefix.py`). After beautify Task 9/10, `window.API_PREFIX` is global via `nx_core.js` — do not declare a local copy.
- **Jinja templates are cached for the process lifetime** — restart the dev server (`bin/nx.ps1 -r` or `-u`) before any browser verification.
- **TEST DB (`sql/test/schema.sql`) has none of the new tables.** Unit/integration tests mock `engine_nexora_db.raw_connection()` — the two house mocking patterns live in `tests/unit/test_mapping_config.py` and `tests/unit/test_clients.py`. Keep the degraded path working rather than seeding the test schema.
- **The failure contract is inherited from `nx_lib/mapping_config.py`, not re-litigated:** a load error returns `None`, is **never cached**, and callers render an explicit "configuration unavailable" state — never an empty-looking success, never an unconstrained query.
- **Descriptor identifiers are interpolated into SQL, not parameterised** (spec T9). Every `SourceObject`/`ColumnName` is validated against the strict identifier pattern on write *and* on read; a row failing it is dropped with a log line, never used.
- **i18n: YES.** The generic tenant page chrome adds user-visible strings. Full `pybabel extract → update → compile` cycle (`/nx-i18n`), de/fr/it non-fuzzy, and **diff-sweep the `.po` files after `pybabel update`** (it silently mangles malformed msgstr lines).
- **No deploy-exclude changes.** No new top-level files/dirs; `nx_lib/tenant/`, templates and static JS are all inside runtime-shipped trees (`deploy.yml` untouched).
- **Verification loop:** each task ends with its named tests green; JS/template tasks get a browser pass (`bin/nx.ps1 -u -b --loginas:ben.streich --no-conflict`, screenshots to `var/screenshots/`, kill the browser when done).

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| K1 | **One parametrized route family** (`/t/<tenant_code>/<page_key>`), not per-tenant boot-time registration. | Strictly less code and no recycle for page edits; spec T8's documented recycle caveat survives unchanged because a new tenant's *engine* still resolves through import-time `CLIENTS` (dbo.Clients D6). The spec's substance (recycle per new tenant, documented) holds. |
| K2 | The kernel **does not import** `nx_lib/views/generali/` code. It follows the `register_crud(app, desc)` descriptor shape (same keys where sensible) so sub-project 4 can converge them. | Generali descriptors are code-dicts over GeneraliDB; tenant descriptors are DB rows. Sharing shape, not code, keeps both shippable. |
| K3 | `TenantEntities.EngineRole` ∈ `runtime`/`stats`/`docfields` picks the engine off the tenant's `ClientConfig` (`runtime_engine`/`stats_engine`/`docfields_engine`) with the matching dialect field. | dbo.Clients already models the three engine slots per client; the box only needs to say which slot an entity lives in. |
| K4 | Cutover bit is `dbo.Clients.ServesWorkitems BIT NOT NULL DEFAULT 1`, honored **only** by the shared list path (`non_default_source_instances()` for listing). Probe/detail (`get_source_for_workitem`, `get_domain_for_workitem`) keep seeing every client. | The MS02 document viewer stays a custom mount on the shared machinery (spec, MS02 pilot section); killing probe would break it. One bit, one filter, reversible by migration. |
| K5 | Kernel cutover scope = the shared `/workitems` merged list + its search. The dashboard's MS02 stat blocks and `/prepared_documents` keep working unchanged (both are reachable from the MS02 tenant nav as custom mounts). | Progressive parity per spec; the dashboard reads `mapping_config`, which this plan does not touch. Completing those moves is sub-project follow-on, listed at the end. |
| K6 | `ReportingSources` auto-registration ships as `sync_tenant_reporting_sources()` and registers **only tenants whose entity engine is T-SQL** (resolvable in `_CURATED_ENGINES` terms). MS02 (PG) is skipped with a logged notice. | `_CURATED_ENGINES` in `nx_lib/views/reporting.py` maps to T-SQL engines and `build_generic_query` emits T-SQL; teaching the curated provider PG is real work that belongs to a later sub-project (Owner actions). Honest deferral beats a broken checkbox. |
| K7 | Kernel tenant creation happens **by migration** (MS02 seed). The runtime create-tenant path (and its permission auto-provisioning) is sub-project 2's admin UI; the kernel exposes `provision_tenant_permissions(cursor, code)` for it to reuse but wires no UI. | YAGNI: the kernel has exactly one tenant to create and a migration is its natural home. |
| K8 | Descriptor rows carry `Status` (`draft`/`active`); the registry loads **active only**. Eddard (sub-project 3) will write drafts. | Spec T6. The kernel seeds MS02 rows directly `active`. |
| K9 | Lookup entities resolve app-side (id → name map fetched per page render), not by SQL JOIN in v1. | The MS02 pilot's wide columnar tables need no joins; generali-style lookups arrive with sub-project 4. Smallest correct engine. |

## Owner actions (not for the executor)

- **Green-light or park PG reporting support** (K6): MS02 tenant data appears in the reporting builder only after the curated `table` provider learns the PG dialect (`build_generic_query` + `_CURATED_ENGINES` keyed per tenant engine). Until then the MS02 tenant's numbers live on its tenant pages only.
- **Confirm which MS02 PG database serves tenant list reads** at execution time (Task 8 probes both): the ms02 `ProcessSources` rows drive statistics via `stats_engine` *and* doc-field search via `docfields_engine` against same-named wide tables. The seed defaults to `docfields`; flip the seeded `EngineRole` to `stats` if the probe says otherwise.
- **Decide the flip moment for `0085`** (Task 10): committing it cuts INT over immediately (pre-commit auto-applies); PROD follows on the next deploy. Task 9's parity screenshots are the evidence to decide on.

---

# PHASE A — schema + registry

### Task 1: Migration `0083` — `dbo.Tenants` + the data-box tables

**Files:**
- Create: `sql/_migrations/NexoraDB/0083_tenant_box_tables.sql`
- Regenerate: `sql/NexoraDB/Tables/dbo.Tenants.sql`, `dbo.TenantEntities.sql`, `dbo.TenantFields.sql`, `dbo.TenantPages.sql` (via `python sql/sync-from-db.py`)

**Interfaces:**
- Produces: the four tables exactly as below — Task 2's registry SELECTs name every column.

- [ ] **Step 1:** Re-check the free number: `ls sql/_migrations/NexoraDB/ | tail -3` and `python scripts/db-migrate.py --env INT --dry-run`. If `0083` is taken (Kundenmagazin peer!), shift this and every later migration number in this plan.
- [ ] **Step 2:** Write the migration, `GO`-separated, idempotent (`IF OBJECT_ID(...) IS NULL`), constraints named per house style:

```sql
IF OBJECT_ID('dbo.Tenants', 'U') IS NULL
CREATE TABLE dbo.Tenants (
    TenantCode        NVARCHAR(50)  NOT NULL,
    DisplayName       NVARCHAR(100) NOT NULL,
    OrganizationCode  NVARCHAR(5)   NOT NULL,  -- dbo.Organizations.organizationcode
    ClientCode        NVARCHAR(50)  NOT NULL,  -- dbo.Clients.ClientCode (data connection)
    IsActive          BIT NOT NULL CONSTRAINT DF_Tenants_IsActive DEFAULT (1),
    CONSTRAINT PK_Tenants PRIMARY KEY CLUSTERED (TenantCode),
    CONSTRAINT FK_Tenants_Organizations FOREIGN KEY (OrganizationCode)
        REFERENCES dbo.Organizations (organizationcode),
    CONSTRAINT FK_Tenants_Clients FOREIGN KEY (ClientCode)
        REFERENCES dbo.Clients (ClientCode)
);
GO
IF OBJECT_ID('dbo.TenantEntities', 'U') IS NULL
CREATE TABLE dbo.TenantEntities (
    TenantCode    NVARCHAR(50)  NOT NULL,
    EntityKey     NVARCHAR(100) NOT NULL,
    SourceObject  NVARCHAR(256) NOT NULL,  -- schema-qualified table/view, identifier-validated
    Kind          NVARCHAR(16)  NOT NULL,  -- documents | entries | lookup
    EngineRole    NVARCHAR(16)  NOT NULL CONSTRAINT DF_TenantEntities_EngineRole DEFAULT ('runtime'),
    IdColumn      NVARCHAR(128) NOT NULL,
    LabelEn       NVARCHAR(120) NOT NULL,
    LabelDe       NVARCHAR(120) NULL,
    LabelFr       NVARCHAR(120) NULL,
    LabelIt       NVARCHAR(120) NULL,
    SortOrder     INT NOT NULL CONSTRAINT DF_TenantEntities_SortOrder DEFAULT (100),
    Status        NVARCHAR(8)  NOT NULL CONSTRAINT DF_TenantEntities_Status DEFAULT ('draft'),
    CONSTRAINT PK_TenantEntities PRIMARY KEY CLUSTERED (TenantCode, EntityKey),
    CONSTRAINT FK_TenantEntities_Tenants FOREIGN KEY (TenantCode) REFERENCES dbo.Tenants (TenantCode),
    CONSTRAINT CK_TenantEntities_Kind CHECK (Kind IN ('documents','entries','lookup')),
    CONSTRAINT CK_TenantEntities_EngineRole CHECK (EngineRole IN ('runtime','stats','docfields')),
    CONSTRAINT CK_TenantEntities_Status CHECK (Status IN ('draft','active'))
);
GO
IF OBJECT_ID('dbo.TenantFields', 'U') IS NULL
CREATE TABLE dbo.TenantFields (
    TenantCode    NVARCHAR(50)  NOT NULL,
    EntityKey     NVARCHAR(100) NOT NULL,
    ColumnName    NVARCHAR(128) NOT NULL,  -- identifier-validated
    SemanticRole  NVARCHAR(16)  NOT NULL,  -- date|money|category|person|identifier|count|text|flag
    LookupEntity  NVARCHAR(100) NULL,      -- EntityKey of a Kind='lookup' entity
    LabelEn       NVARCHAR(120) NOT NULL,
    LabelDe       NVARCHAR(120) NULL,
    LabelFr       NVARCHAR(120) NULL,
    LabelIt       NVARCHAR(120) NULL,
    IsVisible     BIT NOT NULL CONSTRAINT DF_TenantFields_IsVisible DEFAULT (1),
    SortOrder     INT NOT NULL CONSTRAINT DF_TenantFields_SortOrder DEFAULT (100),
    Status        NVARCHAR(8)  NOT NULL CONSTRAINT DF_TenantFields_Status DEFAULT ('draft'),
    CONSTRAINT PK_TenantFields PRIMARY KEY CLUSTERED (TenantCode, EntityKey, ColumnName),
    CONSTRAINT FK_TenantFields_TenantEntities FOREIGN KEY (TenantCode, EntityKey)
        REFERENCES dbo.TenantEntities (TenantCode, EntityKey),
    CONSTRAINT CK_TenantFields_SemanticRole CHECK (SemanticRole IN
        ('date','money','category','person','identifier','count','text','flag')),
    CONSTRAINT CK_TenantFields_Status CHECK (Status IN ('draft','active'))
);
GO
IF OBJECT_ID('dbo.TenantPages', 'U') IS NULL
CREATE TABLE dbo.TenantPages (
    TenantCode  NVARCHAR(50)  NOT NULL,
    PageKey     NVARCHAR(100) NOT NULL,
    PageType    NVARCHAR(16)  NOT NULL,  -- list | crud | custom  (dashboard/report arrive later)
    EntityKey   NVARCHAR(100) NULL,      -- required for list/crud, NULL for custom
    LayoutJSON  NVARCHAR(MAX) NULL,      -- custom: {"endpoint": "...", "icon": "..."}
    SortOrder   INT NOT NULL CONSTRAINT DF_TenantPages_SortOrder DEFAULT (100),
    Status      NVARCHAR(8)  NOT NULL CONSTRAINT DF_TenantPages_Status DEFAULT ('draft'),
    CONSTRAINT PK_TenantPages PRIMARY KEY CLUSTERED (TenantCode, PageKey),
    CONSTRAINT FK_TenantPages_Tenants FOREIGN KEY (TenantCode) REFERENCES dbo.Tenants (TenantCode),
    CONSTRAINT CK_TenantPages_PageType CHECK (PageType IN ('list','crud','custom')),
    CONSTRAINT CK_TenantPages_Status CHECK (Status IN ('draft','active'))
);
GO
```

- [ ] **Step 3:** Apply: `python scripts/db-migrate.py --env INT`, then `python sql/sync-from-db.py`; stage the four new dumps alongside the migration.
- [ ] **Step 4:** Commit.

```
feat(db): add dbo.Tenants and the tenant data-box tables

Migration 0083 creates Tenants, TenantEntities, TenantFields and TenantPages — the descriptor
tables of the tenant platform kernel (spec 2026-08-31-tenant-platform-design). Draft/active status
gates what the registry loads; nothing reads the tables yet.

Co-Authored-By: <model> <noreply@anthropic.com>
```

### Task 2: `nx_lib/tenant/registry.py` — the cached box registry

**Files:**
- Create: `nx_lib/tenant/__init__.py`, `nx_lib/tenant/registry.py`
- Test: `tests/unit/test_tenant_registry.py` (new)

**Interfaces:**
- Produces (imported by Tasks 3–6):
  - `@dataclass(frozen=True) Tenant(code, display_name, organization_code, client_code, active)`
  - `@dataclass(frozen=True) TenantEntity(tenant, key, source_object, kind, engine_role, id_column, labels: dict, sort_order)`
  - `@dataclass(frozen=True) TenantField(tenant, entity, column, semantic_role, lookup_entity, labels: dict, visible, sort_order)`
  - `@dataclass(frozen=True) TenantPage(tenant, key, page_type, entity, layout: dict | None, sort_order)`
  - `@dataclass(frozen=True) TenantRegistry(tenants: dict[str, Tenant], entities, fields, pages)`
  - `registry() -> TenantRegistry | None` · `invalidate_tenant_config() -> None`
  - `tenant(code) -> Tenant | None` · `pages_for(code) -> list[TenantPage]` · `entity_for(code, entity_key) -> TenantEntity | None` · `fields_for(code, entity_key) -> list[TenantField]`
  - `_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_."\[\]]{0,99}$')` (module constant, reused by Task 3 and the sub-project-2 admin writes)

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_tenant_registry.py`, mocking `engine_nexora_db.raw_connection()` exactly the way `tests/unit/test_mapping_config.py` does:

```python
def test_registry_loads_active_rows_only(...)          # a Status='draft' row is absent
def test_registry_load_failure_returns_none_and_is_not_cached(...)  # 2nd call re-queries
def test_registry_success_is_cached_for_ttl(...)       # 2nd call within TTL: no engine hit
def test_invalidate_tenant_config_drops_cache(...)
def test_unsafe_source_object_row_is_dropped_and_logged(...)  # "bad;--name" entity absent
def test_unsafe_column_name_row_is_dropped_and_logged(...)
def test_pages_for_orders_by_sort_order(...)
def test_layout_json_parse_error_yields_layout_none(...)
```

- [ ] **Step 2:** Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_tenant_registry.py -q --no-cov` — expect `ModuleNotFoundError`.
- [ ] **Step 3: Implement** `nx_lib/tenant/registry.py` as a structural twin of `nx_lib/mapping_config.py` (same `cache` from `nx_lib/extensions.py`, `_CACHE_KEY = "tenant_config_registry"`, `_TTL = 60`, success-only caching, `current_app.logger.error` on failure → `return None`). Load with four SELECTs filtered `WHERE Status = 'active'` (Tenants: `WHERE IsActive = 1`); JSON-parse `LayoutJSON` with a try/except that degrades to `None`; validate `SourceObject`, `IdColumn` and every `ColumnName` against `_IDENT_RE`, dropping (and logging) any failing row **at load time** so nothing downstream ever sees an unsafe identifier. `nx_lib/tenant/__init__.py` re-exports the public names above.
- [ ] **Step 4:** Run the tests green, then `.venv\Scripts\python.exe -m pytest tests/unit -q --no-cov` (no regressions).
- [ ] **Step 5:** Commit.

```
feat(tenant): add the cached tenant/data-box registry

nx_lib/tenant/registry.py loads Tenants + TenantEntities/TenantFields/TenantPages (active rows
only) into one frozen 60s-cached registry with the mapping_config failure contract: a load error
returns None and is never cached. Identifier-shaped descriptor values are validated on load and
unsafe rows dropped, so the page engine can never interpolate an unvalidated name.

Co-Authored-By: <model> <noreply@anthropic.com>
```

# PHASE B — the page engine

### Task 3: `nx_lib/tenant/queries.py` — descriptor→SQL builders (both dialects)

**Files:**
- Create: `nx_lib/tenant/queries.py`
- Test: `tests/unit/test_tenant_queries.py` (new)

**Interfaces:**
- Consumes: `TenantEntity`, `TenantField`, `_IDENT_RE` from Task 2.
- Produces (used by Task 4):
  - `quote_ident(name, dialect) -> str` — `[name]`-style for `tsql`, `"name"` for `postgres`; raises `ValueError` on an `_IDENT_RE` miss (belt-and-braces after registry validation).
  - `build_list_query(entity, fields, dialect, *, filters=None, sort=None, offset=0, limit=50) -> (count_sql, page_sql, params)` — `filters` is `[(column, op, value)]` with `op` ∈ `{'eq','contains','gte','lt'}`; every value is a bound parameter (`?` for tsql, `%s` for postgres); pagination is `OFFSET ? ROWS FETCH NEXT ? ROWS ONLY` vs `LIMIT %s OFFSET %s`.
  - `build_insert(entity, fields, dialect)`, `build_update(entity, fields, dialect)`, `build_delete(entity, dialect)` — parameterised by the entity's `id_column`; only for `Kind='entries'`.

- [ ] **Step 1: Failing tests** asserting exact SQL text and params for both dialects, plus:

```python
def test_list_query_tsql_pagination_and_quoting(...)
def test_list_query_postgres_pagination_and_quoting(...)
def test_contains_filter_binds_like_parameter(...)     # value reaches params, never the SQL text
def test_quote_ident_raises_on_unsafe_name(...)
def test_build_update_sets_only_visible_fields(...)
def test_build_delete_is_parameterised_by_id(...)
```

- [ ] **Step 2:** Run — expect FAIL.
- [ ] **Step 3: Implement.** Pure functions, no DB access, no Flask import — mirror the dialect discipline in `nx_lib/workitem_sources.py` (its `_MS02_IDENT` guard and `%s`/`?` marker split are the precedent; PG identifiers are case-preserved PascalCase and must stay double-quoted). Order by the first `SemanticRole='date'` field DESC when no sort is given, else `id_column`.
- [ ] **Step 4:** Tests green. Commit.

```
feat(tenant): descriptor-to-SQL builders for both dialects

Pure query builders over the box descriptors: quoted identifiers per dialect (brackets vs double
quotes), bound parameters for every value, OFFSET/FETCH vs LIMIT/OFFSET pagination, and CRUD
statements keyed on the entity id column. No DB access; identifier misses raise.

Co-Authored-By: <model> <noreply@anthropic.com>
```

### Task 4: `nx_lib/views/tenant.py` — the parametrized route family

**Files:**
- Create: `nx_lib/views/tenant.py`
- Edit: `nx_lib/__init__.py` (register beside the other view modules — Grep `views` imports there and mirror the existing `register_routes(app)` fan-out; do NOT use Blueprints, per the house rule)
- Test: `tests/integration/test_tenant_routes.py` (new)

**Interfaces:**
- Consumes: registry API (Task 2), builders (Task 3), `CLIENTS` from `nx_lib.clients`, `require_permission`/`has_permission` from `nx_lib.security`.
- Produces: endpoints `tenant_page` (`/t/<tenant_code>/<page_key>`), `api_tenant_list`, `api_tenant_add`, `api_tenant_edit`, `api_tenant_delete`, `api_tenant_export` (`/api/t/<tenant_code>/<page_key>/...`); helper `visible_tenant_nav() -> list[dict]` for Task 6.

- [ ] **Step 1: Failing tests** in `tests/integration/test_tenant_routes.py`, following the admin-route test pattern in `tests/integration/test_admin_routes.py` (session fixture + permission patching):

```python
def test_tenant_page_403_without_view_permission(...)      # tenant.<code>.view
def test_tenant_page_404_for_unknown_tenant_or_page(...)
def test_tenant_page_200_with_permission(...)
def test_tenant_page_renders_unavailable_state_when_registry_none(...)
def test_api_list_403_without_view_permission(...)
def test_api_list_engine_missing_returns_503_not_empty(...)  # ClientConfig engine is None
def test_api_write_403_without_edit_permission(...)          # tenant.<code>.edit
def test_api_write_404_for_documents_entity(...)             # CRUD only on Kind='entries'
def test_custom_page_redirects_to_layout_endpoint(...)
```

- [ ] **Step 2:** Run — expect 404s/FAIL.
- [ ] **Step 3: Implement the page view.** Permission gate is dynamic (the code embeds the tenant): check inside the view, not via decorator —

```python
def tenant_page(tenant_code, page_key):
    if not has_permission(f"tenant.{tenant_code}.view"):
        raise PermissionDenied()
    t = tenant(tenant_code)
    pages = pages_for(tenant_code)
    page = next((p for p in pages if p.key == page_key), None)
    if t is None or page is None:
        abort(404)
    if page.page_type == "custom":
        endpoint = (page.layout or {}).get("endpoint")
        return redirect(url_for(endpoint)) if endpoint else abort(404)
    ...
```

  A `registry()` of `None` renders the explicit unavailable state (same template block as Step 5's `tenant/page.html`), never an empty page. `render_template` tail mirrors the admin views: `logged_in_user=session.get("username"), userid=session.get("userid"), page_visibility=page_visibility()`.
- [ ] **Step 4: Implement the APIs.** `api_tenant_list`: resolve entity → engine via K3 (`CLIENTS.get(t.client_code)` + `engine_role`); engine `None` → 503 JSON (`{"success": False, "unavailable": True}`); run count+page SQL from Task 3; serialize with field labels for the current locale. Writes: `Kind='entries'` only, server-side value validation by `SemanticRole` (`date` → ISO date parse, `money`/`count` → numeric, else text), parameterised SQL, `jsonify({"success": ...})` shape as in `nx_lib/views/admin.py`. Export: xlsx via `openpyxl` (locally imported, as `parse_prepared_xlsx` in `nx_lib/workitem_sources.py` does).
- [ ] **Step 5:** Register in `nx_lib/__init__.py` beside the other `register_routes(app)` calls.
- [ ] **Step 6:** Tests green; run `.venv\Scripts\python.exe -m pytest tests/integration/test_tenant_routes.py tests/unit -q --no-cov`.
- [ ] **Step 7:** Commit.

```
feat(tenant): parametrized /t/<code>/<page> route family

One route family serves every tenant from the cached registry: generated list pages and
entries-CRUD APIs gated on tenant.<code>.view/.edit, custom pages redirecting to their mounted
endpoint, xlsx export, and explicit 503/unavailable states when the registry or the tenant's
engine is down. No per-tenant registration; engines still resolve via import-time CLIENTS.

Co-Authored-By: <model> <noreply@anthropic.com>
```

### Task 5: The generic tenant page — template, shim, JS

**Files:**
- Create: `templates/tenant/page.html`, `templates/js/_tenant_page_js.html`, `static/js/tenant_pages.js`
- Test: extend `tests/integration/test_tenant_routes.py` (rendered-page assertions); the house lint tests cover the rest

- [ ] **Step 1:** Build `templates/tenant/page.html` from `templates/admin/clients.html`'s chrome (same `<head>`, `{% include '_header.html' %}`, `{% import 'admin/_admin_helpers.html' as a %}`; `{% set active_page = 'tenant_' ~ tenant_code ~ '_' ~ page_key %}`). Render: the entity's visible fields as a table with header labels from the field's locale label dict, a filter row (text inputs per `identifier`/`text`/`category` field, date-range for the first `date` field — native `<input type="date">`), pagination controls, an Export button, and (for `crud` pages) Add/Edit/Delete affordances. Include the unavailable-state block (`{% if unavailable %}`) with an explicit message.
- [ ] **Step 2:** `templates/js/_tenant_page_js.html` is a **shim** (#191): sets `window.NX_TENANT = {code: ..., page: ..., entity: ..., fields: [...], i18n: {...}}` from Jinja + translated strings, then nothing else; behaviour lives in `static/js/tenant_pages.js` loaded via `static_v('js/tenant_pages.js')`. All fetch URLs built with the global `API_PREFIX` idiom; `addEventListener` only — zero inline handlers.
- [ ] **Step 3:** `static/js/tenant_pages.js`: `loadRecords` (fetch list + render rows), filter debounce, pagination, `exportToExcel` (navigates to the export URL), and the CRUD modal handlers for `crud` pages. Reuse `NX.*` helpers from `nx_core.js` (beautify Task 9) — do not re-declare `esc`/`api`.
- [ ] **Step 4:** Lint gates green: `pytest tests/unit/test_no_inline_event_handlers.py tests/unit/test_template_url_prefix.py tests/unit/test_template_layout.py -q --no-cov`.
- [ ] **Step 5:** Browser smoke needs a tenant — defer the visual pass to Task 9 (MS02 seeded); here assert the rendered HTML in the integration tests (field labels present, unavailable block when forced).
- [ ] **Step 6:** Commit.

```
feat(tenant): generic tenant page template with #191 shim and shared JS

One Jinja page renders any generated tenant list/CRUD page from the box descriptors; the JS shim
carries only data and translated strings while static/js/tenant_pages.js holds the behaviour,
reusing the nx_core helper surface and the API_PREFIX idiom.

Co-Authored-By: <model> <noreply@anthropic.com>
```

### Task 6: Sidebar navigation + permission helper

**Files:**
- Edit: `templates/_header.html`, `nx_lib/hooks.py`
- Create: `provision_tenant_permissions` in `nx_lib/tenant/registry.py` (K7)
- Test: extend `tests/integration/test_tenant_routes.py`; `tests/unit/test_tenant_registry.py`

- [ ] **Step 1: Failing tests:** a user holding `tenant.ms02.view` sees the tenant group in the rendered header; a user without it sees none; `provision_tenant_permissions` inserts `tenant.<code>.view`/`.edit` idempotently (mocked cursor asserts the `WHERE NOT EXISTS` shape).
- [ ] **Step 2:** Add `visible_tenant_nav()` (in `nx_lib/views/tenant.py`): registry tenants × `has_permission(f"tenant.{t.code}.view")` → `[{"code", "label", "pages": [...]}]`, empty list on registry `None`. Inject via a context processor in `nx_lib/hooks.py` — register `app.context_processor(_inject_tenant_nav)` beside the existing `app.context_processor(_inject_brand)`.
- [ ] **Step 3:** In `templates/_header.html`, add a `{% for t in tenant_nav %}` group block **modeled on the generali group** (anchor: `id="generaliNavGroup"`; the surrounding `sidebar-nav-group`/`sidebar-nav-subitems` classes and chevron markup are the pattern) — one group per tenant, one subitem per page (list/crud pages link `url_for('tenant_page', tenant_code=t.code, page_key=p.key)`; custom pages link their layout endpoint). Keep the generali block itself untouched.
- [ ] **Step 4:** `provision_tenant_permissions(cursor, code)` in `nx_lib/tenant/registry.py`, mirroring the idempotent insert `api_admin_process_source_add` uses (`INSERT INTO dbo.Permission ... WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = ?)`) for the two codes; granted to nobody (granting stays at `/admin/access-control`).
- [ ] **Step 5:** Tests green; restart the dev server and eyeball the sidebar with and without the permission once Task 8 has seeded MS02 (fold into Task 9's browser pass if preferred).
- [ ] **Step 6:** Commit.

```
feat(tenant): per-tenant sidebar navigation and permission provisioning

A context processor injects the tenants visible to the session (registry x tenant.<code>.view);
the header renders one nav group per tenant modeled on the generali group. Tenant permission
pairs are provisioned idempotently and granted to nobody.

Co-Authored-By: <model> <noreply@anthropic.com>
```

### Task 7: `ReportingSources` sync (T-SQL tenants only, K6)

**Files:**
- Create: `nx_lib/tenant/reporting_sync.py`
- Test: `tests/unit/test_tenant_reporting_sync.py` (new)

- [ ] **Step 1: Failing tests:** a tenant entity on a `tsql` engine upserts one `dbo.ReportingSources` row (`Kind='curated'`, `Provider='table'`, `Code='tenant_<code>_<entitykey>'`, `Permission='tenant.<code>.view'`, `BaseObject=SourceObject`, `ColumnsJSON` from the visible fields); a `postgres`-dialect tenant is skipped and logged; re-running updates rather than duplicates (match on `Code` — `UQ_ReportingSources_Code` backs this).
- [ ] **Step 2:** Run — expect FAIL.
- [ ] **Step 3: Implement** `sync_tenant_reporting_sources()`: read the registry, resolve each `documents` entity's dialect off the tenant's `ClientConfig` per K3, upsert via MERGE-on-Code for tsql, log-and-skip otherwise. **The `Engine` column value must be a `_CURATED_ENGINES` key** (`nx_lib/views/reporting.py`: `_CURATED_ENGINES = { "nexora": ..., "statistics": ..., "generali": ..., "octopus": ... }`) — map `engine_statistics_db`-backed entities to `'statistics'`, `engine_generali_db` to `'generali'`; anything unmappable is skipped with the same logged notice. No caller in the kernel besides tests (sub-project 2's admin writes will call it; MS02 is PG so the pilot registers nothing — that is the K6 deferral, stated in the module docstring).
- [ ] **Step 4:** Tests green. Commit.

```
feat(tenant): reporting-source sync for T-SQL tenant entities

sync_tenant_reporting_sources() upserts one curated ReportingSources row per documents entity
whose engine speaks T-SQL, keyed on Code for idempotence. Postgres tenants (MS02) are skipped
with a logged notice until the curated table provider learns the PG dialect (spec K6 deferral).

Co-Authored-By: <model> <noreply@anthropic.com>
```

# PHASE C — the MS02 pilot

### Task 8: Migration `0084` — seed the MS02 tenant from the mapping tables

**Files:**
- Create: `sql/_migrations/NexoraDB/0084_seed_ms02_tenant.sql`
- Regenerate: `sql/NexoraDB/Tables/*.sql` for any changed dumps

- [ ] **Step 1:** Re-check the free number (`--dry-run`).
- [ ] **Step 2: Probe the data home first** (Owner action #2): against INT, `SELECT TOP 3 * FROM dbo.ProcessSources WHERE ClientCode = 'ms02'` to list the wide tables, then confirm which MS02 PG database actually holds them (compare `MS02_STATS_DB_*` vs `MS02_DOCFIELDS_DB_*` targets with a `SELECT 1 FROM <table> LIMIT 1` through each engine — `python - <<'EOF'` one-liner using `nx_lib.db`). Set the seed's `EngineRole` accordingly (`'docfields'` default).
- [ ] **Step 3:** Write the migration, idempotent throughout (`WHERE NOT EXISTS`):
  - `dbo.Tenants`: `('ms02', 'MS02', <organizationcode>, 'ms02', 1)` — resolve the organization code at authoring time with `SELECT organizationcode, Organization FROM dbo.Organizations` on INT and pick the MS02 customer's row (do not guess; record the choice in the migration comment).
  - `dbo.Permission`: `tenant.ms02.view` + `tenant.ms02.edit` via the `WHERE NOT EXISTS` shape; grant to the access profiles that already hold `workitems.view` **only if the owner asks** — default: granted to nobody.
  - `dbo.TenantEntities`: `INSERT ... SELECT DISTINCT 'ms02', ProcessName, TableName, 'documents', '<EngineRole>', WorkitemColumn, ProcessName, 100, 'active' FROM dbo.ProcessSources WHERE ClientCode = 'ms02' AND TableName IS NOT NULL` (adjust the label columns; `IdColumn` = `WorkitemColumn`).
  - `dbo.TenantFields`: `INSERT ... SELECT` from `dbo.ProcessFieldMappings` (ms02 rows) joined to `dbo.FieldLabels` on `FieldKey` for the four locale labels; `SemanticRole` seeds as `'text'` except: map `ColumnType` int-ish (`int`,`bigint`,`integer`,`smallint`) → `'count'`, date-ish (`date`,`timestamp`) → `'date'`; all `'active'`.
  - `dbo.TenantPages`: one `('ms02', <entitykey>, 'list', <entitykey>, NULL, ..., 'active')` row per seeded entity, plus two custom mounts: `('ms02', 'workitems', 'custom', NULL, '{"endpoint": "workitems_overview"}', 10, 'active')` and `('ms02', 'prepared', 'custom', NULL, '{"endpoint": "prepared_documents"}', 20, 'active')` (endpoints verified: `nx_lib/views/workitems.py` registers `endpoint="workitems_overview"` and `endpoint="prepared_documents"`).
- [ ] **Step 4:** Apply to INT, `python sql/sync-from-db.py`, stage dumps, commit.

```
feat(db): seed the ms02 pilot tenant from the mapping tables

Migration 0084 creates the ms02 Tenants row, its tenant.ms02.view/.edit permissions (granted to
nobody) and transforms the ms02 ProcessSources/ProcessFieldMappings/FieldLabels rows into active
TenantEntities/TenantFields plus one generated list page per entity and custom mounts for the
shared workitems viewer and the prepared-documents page.

Co-Authored-By: <model> <noreply@anthropic.com>
```

### Task 9: Browser parity verification (the Q3 gate — no cutover before this is green)

**Files:** `var/screenshots/` artifacts only; fix-up commits as needed.

- [ ] **Step 1:** Grant yourself `tenant.ms02.view`/`.edit` on INT via `/admin/access-control` (or a throwaway SQL grant noted for removal).
- [ ] **Step 2:** Restart + auto-login: `bin/nx.ps1 -u -b --loginas:ben.streich --no-conflict`.
- [ ] **Step 3: Enumerate the parity checklist against the live feature set** (this is spec Q3, answered here): for each MS02-visible capability on `/workitems` — merged list rows, id-prefix search, status/stage filters, date range, doc-field search, xlsx export, row → document viewer — record whether the MS02 tenant pages cover it or the custom mount carries it. **Deep-link check for the viewer mount:** Grep `templates/js/_workitems_overview_js.html` (or its post-beautify shim + `static/js/` module) for the URL query parameters the overview honors on load (search/client preselection); tenant list rows link the viewer through those (fallback: `/workitems?search=<id>` — the row click then opens the panel with the client hint from the row).
- [ ] **Step 4:** Screenshot each MS02 tenant page and its shared-`/workitems` counterpart side by side into `var/screenshots/` (`tenant-ms02-<page>-{tenant,shared}.png`).
- [ ] **Step 5:** File every gap as a fix-up commit on this branch (descriptor tweaks via a follow-up migration if the box needs different labels/roles — migrations are immutable once applied).
- [ ] **Step 6:** Kill the browser. Present the checklist + screenshots to the owner — **Task 10 needs their explicit go** (Owner action #3).

### Task 10: Cutover — `dbo.Clients.ServesWorkitems`

**Files:**
- Create: `sql/_migrations/NexoraDB/0085_clients_serves_workitems.sql`
- Edit: `nx_lib/clients.py`, `nx_lib/workitem_sources.py`
- Test: `tests/unit/test_clients.py`, `tests/unit/test_workitem_sources.py` (both exist)
- Regenerate: `sql/NexoraDB/Tables/dbo.Clients.sql`

- [ ] **Step 1: Failing tests:**

```python
# test_clients.py
def test_build_clients_reads_serves_workitems_flag(...)      # row flag lands on ClientConfig
def test_serves_workitems_defaults_true_on_db_error(...)     # hardcoded fallback stays True
# test_workitem_sources.py
def test_active_sources_for_listing_excludes_non_serving(...)  # ms02 flag off -> absent
def test_active_sources_default_still_includes_all(...)        # probe/detail path unchanged
```

- [ ] **Step 2:** Run — expect FAIL.
- [ ] **Step 3:** Migration `0085`: `IF COL_LENGTH('dbo.Clients','ServesWorkitems') IS NULL ALTER TABLE dbo.Clients ADD ServesWorkitems BIT NOT NULL CONSTRAINT DF_Clients_ServesWorkitems DEFAULT (1);` then `UPDATE dbo.Clients SET ServesWorkitems = 0 WHERE ClientCode = 'ms02';` — **authored only after the owner's Task 9 go**, because the pre-commit hook applies it to INT at commit time.
- [ ] **Step 4:** `nx_lib/clients.py`: add `serves_workitems: bool = True` to `class ClientConfig:`; include `ServesWorkitems` in the `_build_clients()` SELECT (anchor: `"SELECT ClientCode, DisplayName, Dialect, RuntimeEngineKey, "`) and pass it through; tolerate the column's absence (older DBs) by catching the column error into the existing fallback path.
- [ ] **Step 5:** `nx_lib/workitem_sources.py`: give the two functions a listing flavor —

```python
def active_sources(for_listing=False):
    sources = [SqlServerSource()]
    sources.extend(non_default_source_instances(for_listing=for_listing))
    return sources

def non_default_source_instances(for_listing=False):
    instances = []
    for client in non_default_clients():
        if for_listing and not client.serves_workitems:
            continue
        if client.dialect == "postgres":
            instances.append(PostgresSource(CLIENTS_code=client.code))
    return instances
```

  Then switch **only the merged-list callers** to `for_listing=True` — Grep `active_sources()` and `non_default_source_instances()` call sites in `nx_lib/views/workitems.py` / `nx_lib/views/dashboard.py` (the list/overview/recent/backlog paths); leave `get_source_for_workitem`'s probe default untouched (K4).
- [ ] **Step 6:** Tests green, plus `pytest tests/unit/test_clients.py tests/unit/test_workitem_sources.py tests/integration -q --no-cov`.
- [ ] **Step 7:** Browser: shared `/workitems` shows no MS02 rows; an MS02 document opened from the tenant list still renders the viewer (probe path alive); screenshots to `var/screenshots/`.
- [ ] **Step 8:** `python sql/sync-from-db.py`, stage the `dbo.Clients.sql` dump, commit.

```
feat(tenant): cut ms02 workitems over to the tenant area

Migration 0085 adds dbo.Clients.ServesWorkitems and flips ms02 off. The shared workitems merged
list and dashboard probing now skip non-serving clients, while the detail/probe path still sees
every client so the ms02 viewer custom mount keeps working. Parity was verified in the browser
before the flip (see var/screenshots/, Task 9).

Co-Authored-By: <model> <noreply@anthropic.com>
```

### Task 11: Chores — i18n, changelog, docs

**Files:** `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po`, `CHANGELOG.md`, `CLAUDE.md`, `docs/design/ms02-multisource.md`

- [ ] **Step 1:** `/nx-i18n` cycle for the tenant page chrome + sidebar strings; translate de/fr/it non-fuzzy; diff-sweep the `.po` files; `pytest tests/unit/test_translations.py -q --no-cov` green.
- [ ] **Step 2:** `CHANGELOG.md` `[Unreleased]` → `### Added` (tenant kernel, MS02 tenant area) + `### Changed` (MS02 left the shared workitems list).
- [ ] **Step 3:** `CLAUDE.md`: one pointer line for the tenant platform near the multi-source paragraph (spec + this plan), and amend the multi-source line to note MS02's list now lives at `/t/ms02/*`. A map, not a manual.
- [ ] **Step 4:** `docs/design/ms02-multisource.md`: short "2026 status" note at the top — MS02 list/search moved to the tenant area; probe/detail machinery unchanged and still authoritative for the viewer.
- [ ] **Step 5:** Full gate: fast tier + `python scripts/test_db_reset.py` + integration suite green (prepend `.venv\Scripts` to PATH).
- [ ] **Step 6:** Commit.

```
docs(tenant): changelog, translations and doc pointers for the kernel

Adds the de/fr/it strings for the generated tenant pages, records the kernel and the ms02 cutover
in the changelog, and points CLAUDE.md and the ms02 design doc at the tenant platform spec.

Co-Authored-By: <model> <noreply@anthropic.com>
```

---

## Follow-on (later sub-projects — do NOT start here)

1. **Onboarding UI** (sub-project 2): `/admin/tenants/<code>` box editor, runtime tenant creation calling `provision_tenant_permissions` + `sync_tenant_reporting_sources`, hosted-DB + CSV path (spec Q2).
2. **Eddard** (sub-project 3): draft-writing profiler/styler/chat over the `Status='draft'` lane.
3. **Generali migration** (sub-project 4, after #220): effort cluster onto `entries` descriptors; PG curated-provider work if the owner green-lights MS02 reporting (K6).
4. **Cutover completion:** move the dashboard's MS02 stat blocks and retire the ms02 `ProcessSources` doc-field rows once the tenant pages fully replace them (K5 remainder).

## Gotchas & notes

- **The beautify campaign moves your anchors.** `nx_lib/views/admin.py` → `nx_lib/views/admin/` package (Task 16), `templates/_header.html` gains `nx_core.js` (Task 9), generali partials become shims. Everything quoted here was verified pre-beautify — re-Grep is not optional.
- **Peer migrations race yours.** Two `0079` files already coexist in `sql/_migrations/NexoraDB/`; the Kundenmagazin session is landing more. `--dry-run` before every number claim; renumber without drama.
- **`REGISTRY_DEGRADED_REASON` in `nx_lib/clients.py`** — when dbo.Clients can't load, every non-default client vanishes for the process lifetime and the tenant pages will 503 on engine resolution. `/admin/clients` surfaces it; check there before debugging "the tenant engine is broken".
- **Do not put tenant nav or permissions in `session`** — read fresh behind the registry's 60 s TTL (#155 precedent; the branding context processor is the pattern).
- **`SemanticRole` seeding is heuristic** (Task 8) — wrong roles render suboptimal filters, they never break queries. Fixing a role is a follow-up migration, not a hand-edit (immutability).
- **`FK_TenantFields_TenantEntities` means entity deletes need field deletes first** — surface as 409 in sub-project 2's admin writes, same as `FK_ProcessFieldMappings_ProcessSources` today.
- **The export endpoint streams user-filtered data** — it must run the same permission gate and the same filters as the list API (one code path, not a copy).
- **MS02 PG identifiers are case-preserved** — every generated identifier must go through `quote_ident`; a bare `SELECT WorkItemID` finds nothing on PG.
