# White-label + admin onboarding UI (#98 phase 4) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Single-session planning run (recon → draft → self-red-team); **every file path, symbol, and quoted snippet below was Grep/Read-verified against `v3.2.3.1` HEAD (`d0415388`) on 2026-08-27** — anchor on quoted snippets + symbol names, never line numbers; re-Grep before editing. Plan file: `docs/superpowers/plans/2026-08-27-white-label-admin-ui.md`.

**Goal:** Make onboarding a new customer a non-dev, no-deploy task, and let each customer see their own brand inside the app. Today it costs a SQL migration for the process/field mappings, a second migration for the process permission, and (for a customer with their own DB) a code change plus a hand-edited `env/PROD.env` on SYAPP01. After this plan: a customer riding the shared `default` runtime is onboarded entirely through `/admin/*`, and their users see their name, logo and accent in the header.

**Architecture:** Three independent phases. **A** moves the hardcoded `nx_lib/clients.py::CLIENTS` dict into `dbo.Clients` (non-secret facts only; secrets keep living in `env/{ENV}.env`, referenced by a `SecretRef` prefix). **B** adds two admin pages — `/admin/clients` (runtime sources) and `/admin/processes` (the onboarding surface over `ProcessSources` / `ProcessFieldMappings` / `FieldLabels` / `FieldAliases`) — every write calling the `invalidate_mapping_config()` hook that phases 2–3 left behind for exactly this, and process creation auto-provisioning its `workitems.filter.process.<name>` permission row. **C** adds three nullable brand columns to `dbo.Organizations`, a 60 s cached `nx_lib/branding.py` registry injected by a context processor, and the header's accent/logo/wordmark reading it as a *default* that the user's own `/appearance` choice still overrides.

**Tech Stack:** T-SQL migrations (`sql/_migrations/NexoraDB/`), pyodbc via `engine_nexora_db`, Flask-Caching `SimpleCache` (`nx_lib/extensions.py`), Jinja2 + the existing admin chrome (`templates/admin/_admin_helpers.html`), Flask-Babel, pytest.

**Spec:** [`docs/superpowers/specs/2026-08-27-white-label-admin-ui-design.md`](../specs/2026-08-27-white-label-admin-ui-design.md) — read it first. Its "two axes" section (`ClientCode` = runtime source, `Organizations` = the customer) is the thing this plan is easiest to get wrong.

---

## Context an engineer needs (read first)

- **Branch:** execute on `v3.2.3.1` (verify with `git log --oneline -3`; the doc-field restructure landed as `d0415388`). **Parallel sessions are normal on this repo** — work in your own worktree (`git worktree add .claude/worktrees/white-label -b feat/white-label v3.2.3.1`), never in the main checkout, and stage by pathspec only. Commit per task. **Do NOT `git push`, do NOT open a PR** — the owner reviews and pushes.
- **Copy the gitignored env files into the worktree before committing or running tests**: `Copy-Item C:\dev\nexora\env\*.env <worktree>\env\` — the pre-commit hook runs `scripts/db-migrate.py --env INT` (needs `env/INT.env`) and the test suite needs `env/TEST.env`.
- **Python for tests:** `C:\dev\nexora\.venv\Scripts\python.exe -m pytest …`. The dev server (`nx -u`) runs the **global** Python313, not `.venv`. This plan adds no new runtime dependency, so that split does not bite.
- **Migrations needed: YES — three** (`0079` `dbo.Clients` + seed, `0080` admin permissions, `0081` Organizations brand columns). **`0078` was the last one taken at planning time; re-check `ls sql/_migrations/NexoraDB/ | tail -3` and run `python scripts/db-migrate.py --env INT --dry-run` before creating each file** — peers number migrations too. If a number is taken, shift up and update the commit messages.
- **The pre-commit hook auto-applies new migrations to INT and re-dumps per-object DDL** (`sql/sync-from-db.py --check`). After a schema migration, run `python sql/sync-from-db.py` and stage the changed/new files under `sql/NexoraDB/Tables/` in the same commit, or the hook blocks. If INT is unreachable: `SQL_SYNC_SKIP=1 git commit …` — **never** `--no-verify`.
- **gitlint:** conventional-commit title ≤72 chars, imperative, no trailing period; non-empty body wrapped ≤100 chars/line; commit via `git commit -F - <<'EOF' … EOF`. End the body with the executing model's `Co-Authored-By:` trailer.
- **CSP is PROD-only.** Inline `onclick=` works on INT and is silently refused on PROD. `tests/unit/test_no_inline_event_handlers.py` fails the build on any `on<event>=` in a template. Use the house pattern: the `page_header` macro emits `data-nx-click="{{ act.onclick }}"` and a delegated listener dispatches it. Behaviour goes in the paired `templates/js/admin/_<page>_js.html` partial with `addEventListener`.
- **Hand-built URLs in JS must normalize through `API_PREFIX`** or they 404 on PROD (`/nexora` prefix). Enforced by `tests/unit/test_template_url_prefix.py`.
- **Jinja templates are cached for the process lifetime** — restart the dev server (`nx -r`) before any browser verification, or you will review stale HTML.
- **Do not cache branding in `session`.** #155: per-user display config in the session races the cookie and sticks until re-login. `_inject_whats_new` in `nx_lib/hooks.py` documents the rule; phase C follows the same read-fresh-behind-a-short-TTL idiom.
- **The failure contract from `mapping_config.py` is inherited, not re-litigated:** a load error returns `None`, is **never cached**, and the caller degrades. For branding, degrading means "show Nexora branding" — a broken `Organizations` read must never be able to blank the header.
- **TEST DB (`sql/test/schema.sql` + `seed.sql`) has none of the new tables/columns.** Unit and integration tests mock `engine_nexora_db.raw_connection()` (see `tests/unit/test_mapping_config.py` and `tests/unit/test_clients.py` for the two house mocking patterns). Keep the degraded path working rather than seeding the test schema — except for `Organizations`, which *does* exist there; phase C's columns are nullable, so absent columns must be tolerated (Task 9 Step 1 covers it).
- **No deploy-exclude changes.** `var`, `sql`, `scripts`, `tests` and `docs` are already in the `/XD` list in `.github/workflows/deploy.yml` line ~312. `var/branding/` therefore survives `robocopy /MIR` and needs no new SYAPP01 Defender exclusion (it is inside `var\`).
- **i18n: YES.** Phases B and C add user-visible strings. Run the full `pybabel extract → update → compile` cycle and translate de/fr/it non-fuzzy, or `test_translations.py` fails. Use `/nx-i18n`.

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Branding attaches to **`dbo.Organizations`** (3 nullable columns), not a new table, not `ClientCode`. | `Users.organizationCode` already exists and is populated for all 21 INT users; `/admin/organizations` already calls them "Tenant organizations". A `Users.ClientCode` would duplicate and desync. |
| D2 | **In-app only** — header/sidebar logo, wordmark, accent, page title. Login page, error pages and report emails stay Nexora-branded. | Owner's answer. Login is pre-session: no user ⇒ no organization ⇒ would require hostname routing, which was explicitly not chosen. |
| D3 | Secrets stay in `env/{ENV}.env`; `dbo.Clients.SecretRef` holds only the env-key **prefix** (`MS02`; `NULL` = the unprefixed `OCTO_*` keys). | Owner was unsure; this is the recommendation. No new crypto surface, no secrets in DB backups, `scripts/env-sync.py` already covers the one manual step. Only a customer bringing their **own DB** needs it — customers on `default` are fully self-service. Upgrade path: add an `EncryptedSecret` column and prefer it when set. |
| D4 | User's explicit accent **wins**; the org accent replaces the hardcoded `'indigo'` / `'#4f46e5'` fallback in `templates/_header.html`. | Keeps `/appearance` meaningful. One-line change in the existing `eff` fallback chain. |
| D5 | `nx_lib/clients.py` keeps its `ClientConfig` dataclass, `CLIENTS` dict, `octo_creds_for_domain()` and `non_default_clients()` **unchanged in shape** — only `_build_clients()` changes to read `dbo.Clients`. A row missing its engine or Octo domain is skipped. | `octo.py` and `workitem_sources.py` import those three names; zero blast radius, and today's "MS02 registers only when both are present" degradation is preserved verbatim. |
| D6 | `CLIENTS` stays **module-level, built once at import**, exactly as today. No per-request re-read, no TTL. | Runtime sources change ~never (2 rows), and `workitem_sources.py` imports the dict object itself. A TTL here would be a behaviour change with no user benefit. Adding a client needs an app-pool recycle — document it, don't engineer around it. |
| D7 | Saving a new `ProcessSources` row **auto-creates** `workitems.filter.process.<ProcessName>` in `dbo.Permission` (idempotent, `WHERE NOT EXISTS`), and grants nothing. | Without this, step 3 of onboarding stays a migration and the plan fails its goal. Granting stays a deliberate act at `/admin/access-control`. |
| D8 | Every admin write to the four mapping tables calls `invalidate_mapping_config()`. | `nx_lib/mapping_config.py` carries `_TTL = 60  # seconds; admin-UI edits (phase 4) should apply fast` — the hook exists for this phase. Without the call, an edit looks broken for up to 60 s. |
| D9 | Logo upload → `var/branding/<orgcode>.<ext>`, served by one route, `secure_filename` + `magic` MIME sniff, SVG/PNG/JPEG only, 512 KB cap. | House file-upload convention. `var` is `/XD`-excluded so uploads survive `robocopy /MIR`. |
| D10 | Phase A does **not** touch `ProcessSources.ClientCode` values, and nothing parses the `privera.` prefix in process names. | The prefix is convention only. Renaming `default` is listed as an owner action in the spec and is out of scope. |
| D11 | No new top-level files or directories. | Nothing to add to `deploy.yml`'s `/XF` / `/XD` lists. |

## Owner actions (not for the executor)

- **File the phase-4 GitHub issue** if you want one — the `#98` handoff says to; the owner chose "write a design spec first" over filing it in this session. Link both the spec and this plan.
- **Confirm D3** the first time a customer brings their own database — that is when the single manual `env/PROD.env` edit becomes visible. Until then it costs nothing.
- **Decide whether `default` should be renamed** before the customer count grows (spec, Owner actions).

---

# PHASE A — `dbo.Clients` runtime-source registry

Ships alone. After this phase nothing looks different; `nx_lib/clients.py` just reads its two rows from the DB instead of hardcoding them.

### Task 1: Migration `0079` — create + seed `dbo.Clients`

**Files:**
- Create: `sql/_migrations/NexoraDB/0079_clients_registry.sql`
- Regenerate: `sql/NexoraDB/Tables/dbo.Clients.sql` (via `python sql/sync-from-db.py`)

- [ ] **Step 1:** Re-check the free number: `ls sql/_migrations/NexoraDB/ | tail -3` and `python scripts/db-migrate.py --env INT --dry-run`. If `0079` is taken, shift this and every later migration number in this plan.
- [ ] **Step 2:** Write the migration, `GO`-separated and idempotent, following the `0074` house style (`IF OBJECT_ID(...) IS NULL CREATE TABLE`, `IF NOT EXISTS (SELECT 1 FROM ...) INSERT`):

```sql
IF OBJECT_ID('dbo.Clients', 'U') IS NULL
CREATE TABLE dbo.Clients (
    ClientCode          NVARCHAR(50)  NOT NULL,
    DisplayName         NVARCHAR(100) NOT NULL,
    Dialect             NVARCHAR(20)  NOT NULL,   -- 'tsql' | 'postgres'
    RuntimeEngineKey    NVARCHAR(50)  NOT NULL,   -- name of an engine in nx_lib/db.py
    StatsEngineKey      NVARCHAR(50)  NULL,
    StatsDialect        NVARCHAR(20)  NULL,
    DocfieldsEngineKey  NVARCHAR(50)  NULL,
    DocfieldsDialect    NVARCHAR(20)  NULL,
    OctoDomain          NVARCHAR(255) NULL,
    SecretRef           NVARCHAR(50)  NULL,       -- env-key prefix; NULL = unprefixed OCTO_*
    IsActive            BIT NOT NULL CONSTRAINT DF_Clients_IsActive DEFAULT (1),
    CONSTRAINT PK_Clients PRIMARY KEY CLUSTERED (ClientCode)
);
```

- [ ] **Step 3:** Seed the two rows that mirror today's `_build_clients()` exactly — `default` (`tsql`, `engine_octo_db`, stats+docfields `engine_statistics_db`, `OctoDomain` NULL because it comes from `cfg.OCTO_DOMAIN`, `SecretRef` NULL) and `ms02` (`postgres`, `engine_ms02_pg`, `engine_ms02_stats_pg`, `engine_ms02_docfields_pg`, `SecretRef = 'MS02'`). **`OctoDomain` stays NULL for both** — the domain is still read from config in phase A; the column exists for clients added later through the UI.
- [ ] **Step 4:** Run `python scripts/db-migrate.py --env INT`, then `python sql/sync-from-db.py`, and stage the new `sql/NexoraDB/Tables/dbo.Clients.sql` dump alongside.
- [ ] **Step 5:** Commit.

```
feat(db): add dbo.Clients runtime-source registry

Migration 0079 creates dbo.Clients and seeds the two rows that currently live hardcoded in
nx_lib/clients.py. Non-secret facts only — Octo secrets and DB passwords stay in env/{ENV}.env,
referenced by the SecretRef key prefix (#98 phase 4, spec D3). Nothing reads the table yet.

Co-Authored-By: <model> <noreply@anthropic.com>
```

### Task 2: `nx_lib/clients.py` builds `CLIENTS` from the DB

**Files:**
- Edit: `nx_lib/clients.py` — only `_build_clients()`
- Test: `tests/unit/test_clients.py` (exists)

The public surface must not move. These three names are imported elsewhere (`nx_lib/octo.py`: `from .clients import octo_creds_for_domain`; `nx_lib/workitem_sources.py`: `from .clients import CLIENTS, non_default_clients`) and stay byte-identical in behaviour:

```python
CLIENTS = _build_clients()
def octo_creds_for_domain(domain): ...
def non_default_clients(): ...
```

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_clients.py`, mocking `engine_nexora_db.raw_connection()` the way `tests/unit/test_mapping_config.py` does:

```python
def test_build_clients_reads_rows_from_db(...)
def test_build_clients_skips_row_whose_engine_is_none(...)        # today's MS02 degradation
def test_build_clients_skips_inactive_rows(...)
def test_build_clients_falls_back_to_hardcoded_default_on_db_error(...)
def test_secret_ref_resolves_ms02_prefixed_env_keys(...)
def test_secret_ref_null_resolves_unprefixed_octo_keys(...)
def test_octo_creds_for_domain_unchanged_for_unknown_domain(...)  # regression guard
```

- [ ] **Step 2:** Run `C:\dev\nexora\.venv\Scripts\python.exe -m pytest tests/unit/test_clients.py -q --no-cov` — expect FAIL.
- [ ] **Step 3: Implement.** Replace the body of `_build_clients()`. Keep the module docstring's dependency claim true — it currently says *"Module graph (no cycles): clients -> config, db"*, and `engine_nexora_db` is already in `db`, so no new import edge appears. Shape:

```python
_ENGINES = {  # engine key -> module-level engine object from .db
    "engine_octo_db": engine_octo_db,
    "engine_statistics_db": engine_statistics_db,
    "engine_ms02_pg": engine_ms02_pg,
    "engine_ms02_stats_pg": engine_ms02_stats_pg,
    "engine_ms02_docfields_pg": engine_ms02_docfields_pg,
}

def _creds_for(secret_ref):
    """(domain, client_id, secret, grant_type) for an env-key prefix; None ref = unprefixed."""
    p = f"{secret_ref}_" if secret_ref else ""
    return (getattr(cfg, f"{p}OCTO_DOMAIN", None), getattr(cfg, f"{p}OCTO_CLIENT_ID", None),
            getattr(cfg, f"{p}OCTO_CLIENT_SECRET", None), getattr(cfg, f"{p}OCTO_GRANT_TYPE", None))
```

`_build_clients()` then: SELECT the active rows; for each, resolve `RuntimeEngineKey` through `_ENGINES` and the creds through `_creds_for(SecretRef)`; **skip the row when the runtime engine is `None` or the resolved Octo domain is falsy** — that is the existing `if engine_ms02_pg is not None and cfg.MS02_OCTO_DOMAIN:` guard, generalised. Prefer the DB's `OctoDomain` when set, else the env-resolved one.

- [ ] **Step 4: Fallback.** Wrap the load in `try/except`; on any failure log via `current_app.logger` *if* an app context exists (this runs at import time — use a module-level `logging.getLogger(__name__)` instead, `current_app` is not available) and return the hardcoded `default`-only dict so the app still boots against a DB without `dbo.Clients`. This is what keeps the TEST environment green.
- [ ] **Step 5:** Run the unit tests green, then the two consumers' suites: `pytest tests/unit/test_clients.py tests/unit/test_clients_docfields.py tests/unit/test_workitem_sources.py tests/unit/test_octo.py -q --no-cov`.
- [ ] **Step 6:** Sanity-check the real app: `nx --doctor`, then `nx -u` and load `/workitems` — MS02 workitems must still resolve.
- [ ] **Step 7:** Commit.

```
feat(clients): build the client registry from dbo.Clients

_build_clients() now reads the active rows of dbo.Clients and resolves each row's engine by key and
its Octo credentials by SecretRef prefix, replacing the hardcoded dict. The public surface (CLIENTS,
octo_creds_for_domain, non_default_clients) and the skip-when-engine-or-domain-missing degradation
are unchanged. A DB error falls back to a default-only registry so the app still boots.

Co-Authored-By: <model> <noreply@anthropic.com>
```

---

# PHASE B — the admin onboarding surface (needs Phase A)

### Task 3: Migration `0080` — the four new admin permissions

**Files:** create `sql/_migrations/NexoraDB/0080_white_label_admin_permissions.sql`

- [ ] **Step 1:** Re-check the free migration number (`--dry-run`).
- [ ] **Step 2:** Insert five codes with the `0059` idempotent pattern (`INSERT … SELECT … WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = …)`): `admin.view.clients`, `admin.edit.clients`, `admin.view.processes`, `admin.edit.processes`, `admin.edit.organization.branding`. Grant them to whichever access profile already holds `admin.view.organizations`, copying the `AccessProfilePermission` grant block from `0059`.
- [ ] **Step 3:** Apply to INT, run `python sql/sync-from-db.py` (no table shape changed — expect no diff), commit.

```
feat(db): seed white-label admin permissions

Migration 0080 adds admin.view/edit.clients, admin.view/edit.processes and
admin.edit.organization.branding, granted to the profiles that already hold admin.view.organizations.

Co-Authored-By: <model> <noreply@anthropic.com>
```

### Task 4: `page_visibility()` + `/admin/clients` read-only page

**Files:**
- Edit: `nx_lib/security.py` — `def page_visibility():`
- Edit: `nx_lib/views/admin.py` — new view + `def register_routes(app):`
- Create: `templates/admin/clients.html`, `templates/js/admin/_clients_js.html`
- Test: `tests/integration/test_admin_routes.py`

- [ ] **Step 1: Failing test** in `tests/integration/test_admin_routes.py` — `/admin/clients` is 403 without `admin.view.clients` and 200 with it, following the existing admin-route test pattern in that file.
- [ ] **Step 2:** Run it — expect 404.
- [ ] **Step 3:** Add the keys to `page_visibility()` in `nx_lib/security.py`, next to the existing admin entries (`"adminMaintenanceViewPerm": has_permission("admin.maintenance.view"),`):

```python
"adminClientsPagePerm": has_permission("admin.view.clients"),
"adminProcessesPagePerm": has_permission("admin.view.processes"),
```

- [ ] **Step 4:** Add `admin_clients_view()` to `nx_lib/views/admin.py`, copied from `admin_organizations_view()` (same `raw_connection()` / `cursor` / `finally: close` shape, same `render_template(..., logged_in_user=session.get("username"), userid=session.get("userid"), page_visibility=page_visibility())` tail), guarded with `@require_permission("admin.view.clients")`. Register it in `register_routes(app)` beside the organizations block:

```python
app.add_url_rule("/admin/clients", endpoint="admin_clients_view", view_func=admin_clients_view)
```

- [ ] **Step 5:** Build `templates/admin/clients.html` from `templates/admin/organizations.html` — same `<head>`, `{% set active_page = 'clients' %}`, `{% include '_header.html' %}`, `{% import 'admin/_admin_helpers.html' as a %}`, and `a.page_header(...)` for the title. **No inline `onclick=`** — actions go through the macro's `data-nx-click`.
- [ ] **Step 6:** Add the sidebar entry in `templates/_header.html` next to the other admin links, gated on `page_visibility.adminClientsPagePerm`.
- [ ] **Step 7:** Tests green; `pytest tests/unit/test_no_inline_event_handlers.py tests/unit/test_template_url_prefix.py tests/unit/test_template_layout.py -q --no-cov` must also pass.
- [ ] **Step 8:** Commit.

```
feat(admin): add read-only /admin/clients runtime-source page

Lists dbo.Clients behind admin.view.clients, using the organizations page as the template/JS-partial
pattern. Adds the page_visibility keys and the sidebar entry.

Co-Authored-By: <model> <noreply@anthropic.com>
```

### Task 5: `/admin/clients` writes

**Files:** edit `nx_lib/views/admin.py`, `templates/js/admin/_clients_js.html`; test `tests/integration/test_admin_routes.py`

- [ ] **Step 1: Failing tests** — add/edit/delete are 403 without `admin.edit.clients`; add rejects a `Dialect` outside `{tsql, postgres}`; add rejects an unknown `RuntimeEngineKey`; delete refuses a `ClientCode` still referenced by `dbo.ProcessSources`.
- [ ] **Step 2:** Run — expect 404.
- [ ] **Step 3: Implement** `api_admin_clients_add/edit/delete`, modelled on `admin_add_organization` / `admin_edit_organization` / `admin_delete_organization` (JSON in, `jsonify({"success": …})` out, parameterised SQL). **Validate server-side**: `Dialect` in the allowlist, engine keys against the `_ENGINES` mapping from Task 2, `ClientCode` `^[a-z0-9_]{2,50}$`. Refuse the delete with a 409 when `ProcessSources` still references the code.
- [ ] **Step 4:** Register the three routes in `register_routes(app)`.
- [ ] **Step 5:** Front-end in `templates/js/admin/_clients_js.html` — `addEventListener` + the `data-nx-click` delegation the other admin partials use; every fetch URL built through the `API_PREFIX` idiom.
- [ ] **Step 6:** Note in the page's help text that a new client needs an **app-pool recycle** to take effect (D6) and, if it brings its own DB, the matching `env/{ENV}.env` keys (D3).
- [ ] **Step 7:** Tests green. Commit.

```
feat(admin): CRUD for dbo.Clients runtime sources

Add/edit/delete behind admin.edit.clients with server-side validation of dialect, engine key and
client-code shape. Deleting a client still referenced by dbo.ProcessSources is refused with 409.

Co-Authored-By: <model> <noreply@anthropic.com>
```

### Task 6: `/admin/processes` — read side

**Files:** edit `nx_lib/views/admin.py`, `nx_lib/security.py` (done in Task 4); create `templates/admin/processes.html`, `templates/js/admin/_processes_js.html`; test `tests/integration/test_admin_routes.py`

- [ ] **Step 1: Failing test** — `/admin/processes` 403/200 on `admin.view.processes`; `/api/admin/processes/list?client=default` returns the six INT rows' shape.
- [ ] **Step 2:** Run — expect 404.
- [ ] **Step 3: Implement** the page view plus `api_admin_processes_list()`. **Read through `nx_lib/mapping_config.py`, not raw SQL** — `sources_for(client)` and `mappings_for(client, processes)` already exist and return the frozen `ProcessSource` / `FieldMapping` dataclasses. Handle `registry()` returning `None` by rendering an explicit "config unavailable" state, never an empty-looking success.
- [ ] **Step 4:** Template + JS partial, same chrome as Task 4. Group by client, then by process, with the field mappings as a nested table.
- [ ] **Step 5:** Tests green; commit.

```
feat(admin): add read-only /admin/processes mapping page

Lists ProcessSources and their field mappings per client, read through the cached mapping_config
registry rather than raw SQL. A registry load failure renders an explicit unavailable state.

Co-Authored-By: <model> <noreply@anthropic.com>
```

### Task 7: `/admin/processes` — writes + permission auto-provisioning

**Files:** edit `nx_lib/views/admin.py`, `templates/js/admin/_processes_js.html`; test `tests/integration/test_admin_routes.py`, `tests/unit/test_mapping_config.py`

This is the task that makes onboarding self-service. Keep it strict.

- [ ] **Step 1: Failing tests** —
  - add/edit/delete are 403 without `admin.edit.processes`;
  - adding a `ProcessSources` row creates `workitems.filter.process.<name>` in `dbo.Permission` exactly once, and is idempotent on repeat (D7);
  - every write calls `invalidate_mapping_config()` (assert with a patch on the symbol) (D8);
  - deleting a `ProcessSources` row is refused while `ProcessFieldMappings` rows reference it (the FK `FK_ProcessFieldMappings_ProcessSources` would raise anyway — return a 409 instead of a 500);
  - `ProcessName` and `FieldKey` are validated against `^[A-Za-z0-9_.\-]{1,100}$`;
  - `TableName` / `ColumnName` are rejected unless they match a strict identifier pattern.
- [ ] **Step 2:** Run — expect FAIL.
- [ ] **Step 3: Implement** `api_admin_process_source_add/edit/delete` and `api_admin_field_mapping_add/edit/delete`.

  **Injection is the real risk here.** `ProcessSources.TableName` / `TableAlias` / `JoinCondition` and `ProcessFieldMappings.ColumnName` are **interpolated into SQL** by the query builders downstream — they are config, not parameters. An admin-editable field that reaches a query builder must be validated on the way in:

```python
_IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_."\[\]]{0,99}$')   # table/column/alias
```

  `JoinCondition`, `TimeFilter`, `SuggestionTimeFilter` and `ExtraCondition` are free-form SQL fragments by design (they always were). Do **not** expose them in the UI in this task — keep them read-only, editable only by a migration, and say so in the page's help text. Revisit only if the owner asks.

- [ ] **Step 4:** Auto-provision the permission inside the same transaction as the `ProcessSources` insert, mirroring `0059`'s idempotent shape:

```sql
INSERT INTO dbo.Permission (Code, Description)
SELECT ?, ?
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = ?);
```

- [ ] **Step 5:** Call `invalidate_mapping_config()` after every successful write (import it from `nx_lib.mapping_config`).
- [ ] **Step 6:** Front-end writes in the JS partial; `API_PREFIX` for every URL.
- [ ] **Step 7:** Tests green. Commit.

```
feat(admin): write access for process sources and field mappings

Adding a process source now also provisions its workitems.filter.process.<name> permission row
(idempotent, granted to nobody), and every write invalidates the mapping-config cache so edits apply
within the request. Identifier fields that reach the query builders are validated against a strict
pattern; the free-form SQL fragment columns stay read-only in the UI.

Co-Authored-By: <model> <noreply@anthropic.com>
```

### Task 8: Phase B chores — i18n, docs, changelog

**Files:** `translations/{de,fr,it}/LC_MESSAGES/messages.po`, `messages.pot`, `docs/howto/white-label.md` (new), `CLAUDE.md`, `CHANGELOG.md`

- [ ] **Step 1:** Run the extract → update → compile cycle (`/nx-i18n`), translate every new msgid in de/fr/it non-fuzzy. **After `pybabel update`, diff-sweep the `.po` files** — it silently mangles malformed msgstr lines.
- [ ] **Step 2:** Write `docs/howto/white-label.md`: the two axes, the onboarding walkthrough (organization → client if needed → processes → field mappings → grant the permission at `/admin/access-control`), the app-pool-recycle caveat for new clients (D6), and the env-key step for an own-DB client (D3).
- [ ] **Step 3:** Add a one-line pointer in `CLAUDE.md` near the multi-source paragraph — a pointer, not a paragraph.
- [ ] **Step 4:** `CHANGELOG.md` under `[Unreleased]` → `### Added`.
- [ ] **Step 5:** `pytest tests/unit/test_translations.py -q --no-cov` green. Commit.

```
docs(white-label): document the admin onboarding surface

Adds docs/howto/white-label.md covering the ClientCode/Organization split and the end-to-end
onboarding walkthrough, plus the de/fr/it translations for the two new admin pages.

Co-Authored-By: <model> <noreply@anthropic.com>
```

---

# PHASE C — per-organization branding (independent of B; needs nothing from it)

### Task 9: Migration `0081` + `nx_lib/branding.py`

**Files:**
- Create: `sql/_migrations/NexoraDB/0081_organization_branding.sql`, `nx_lib/branding.py`
- Test: `tests/unit/test_branding.py` (new)
- Regenerate: `sql/NexoraDB/Tables/dbo.Organizations.sql`

- [ ] **Step 1:** Re-check the migration number; write `0081` adding three nullable columns with `IF COL_LENGTH('dbo.Organizations','BrandName') IS NULL ALTER TABLE …` guards: `BrandName NVARCHAR(100) NULL`, `BrandAccentHex NVARCHAR(7) NULL`, `BrandLogoFile NVARCHAR(255) NULL`. Apply to INT, run `sql/sync-from-db.py`, stage the regenerated dump.
- [ ] **Step 2: Failing test** `tests/unit/test_branding.py`, mocking `engine_nexora_db.raw_connection()` as in `tests/unit/test_mapping_config.py`:

```python
def test_brand_for_org_returns_none_for_unknown_code(...)
def test_brand_for_org_returns_row_fields(...)
def test_registry_load_failure_returns_none_and_is_not_cached(...)   # second call re-queries
def test_invalidate_branding_drops_cache(...)
def test_missing_brand_columns_degrade_to_none(...)                  # TEST DB has no such columns
def test_invalid_accent_hex_is_dropped(...)                          # reuse ui_prefs._HEX_RE
```

- [ ] **Step 3:** Run — expect `ModuleNotFoundError`.
- [ ] **Step 4: Implement** `nx_lib/branding.py`, structurally a small copy of `nx_lib/mapping_config.py`:

```python
_CACHE_KEY = "org_branding_registry"
_TTL = 60  # seconds; admin edits should apply fast

def registry() -> dict | None: ...          # {orgcode: {"name","accent_hex","logo_file"}}; None on failure, NEVER cached
def brand_for_org(code: str) -> dict | None: ...
def invalidate_branding() -> None: ...
```

  Validate `BrandAccentHex` on read with the existing pattern from `nx_lib/ui_prefs.py` — `_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")` — and drop the value if it fails, rather than letting a bad hex reach the inline style block. Catch the "column does not exist" error explicitly so the TEST database (whose `Organizations` predates the columns) degrades to `None` instead of erroring per request.

- [ ] **Step 5:** Tests green. Commit.

```
feat(branding): add organization brand columns and cached registry

Migration 0081 gives dbo.Organizations nullable BrandName/BrandAccentHex/BrandLogoFile. The new
nx_lib/branding.py loads them into one 60s success-only cached registry with an invalidate hook,
mirroring mapping_config: a load error returns None, is never cached, and callers fall back to
Nexora branding.

Co-Authored-By: <model> <noreply@anthropic.com>
```

### Task 10: Inject the brand and apply it in the header

**Files:** edit `nx_lib/hooks.py`, `templates/_header.html`, `templates/nexora_logo/_nexora_logo.html`; test `tests/unit/test_branding.py`, `tests/integration/test_admin_routes.py`

- [ ] **Step 1: Failing test** — a logged-in user whose org has `BrandName`/`BrandAccentHex` gets them in the rendered header; a user whose org has none renders exactly today's markup (byte-compare the logo block); a `branding.registry()` failure also renders today's markup.
- [ ] **Step 2:** Run — expect FAIL.
- [ ] **Step 3:** Add the context processor in `nx_lib/hooks.py`, right beside the existing one:

```python
def _inject_ui_prefs():
    return {"ui_prefs": session.get("ui_prefs") or {}}
```

  becomes accompanied by `_inject_brand()`, which returns `{"brand": brand_for_org(session.get("organizationcode")) or {}}` and is registered next to `app.context_processor(_inject_ui_prefs)`. **Read fresh per render behind the 60 s cache — do not put it in `session`** (D5, #155). The session key is `session["organizationcode"]` — **all lowercase**, set at both login paths in `nx_lib/views/auth.py` (`session["organizationcode"] = org_code`); the DB column is `Users.organizationCode`. Do not add a new session key.
- [ ] **Step 4:** In `templates/_header.html`, extend the pre-paint block. The existing line is:

```js
var stored = {{ ui_prefs | tojson }};
```

  Add `var brand = {{ brand | tojson }};` beside it, then change **only the two accent fallbacks** in the `eff` object:

```js
accent:     stored.accent     || (brand.accent_hex ? 'custom' : 'indigo'),
accentHex:  stored.accentHex  || brand.accent_hex || '#4f46e5',
```

  The user's own choice still wins (D4), and the whole `applyCustomAccent()` token-derivation machinery is reused untouched.
- [ ] **Step 5:** In `templates/nexora_logo/_nexora_logo.html`, render `brand.name` in place of the "nexora" wordmark when set, and swap the CSS-art black-hole block for `<img src="{{ url_for('branding_logo', orgcode=...) }}">` when `brand.logo_file` is set. Keep both fallbacks literal — an org with no branding must produce today's DOM.
- [ ] **Step 6:** Tests green. Restart the dev server (`nx -r`) — templates are cached for the process lifetime — and eyeball `/dashboard` as a Privera user and as a Sydoc user.
- [ ] **Step 7:** Commit.

```
feat(branding): apply per-organization brand in the header

A context processor injects the viewer's organization brand, and the header pre-paint block uses it
as the accent default and the wordmark/logo source. The user's own /appearance accent still wins;
an org with no branding renders exactly the previous markup.

Co-Authored-By: <model> <noreply@anthropic.com>
```

### Task 11: Logo upload + the branding panel on `/admin/organizations`

**Files:** edit `nx_lib/views/admin.py`, `templates/admin/organizations.html`, `templates/js/admin/_organizations_js.html`; test `tests/integration/test_admin_routes.py`

- [ ] **Step 1: Failing tests** — the branding save is 403 without `admin.edit.organization.branding`; a non-image upload is rejected by MIME sniff even with an `.svg` name; a >512 KB upload is rejected; a successful save calls `invalidate_branding()`; the serve route 404s for an unknown org and requires a logged-in session.
- [ ] **Step 2:** Run — expect FAIL.
- [ ] **Step 3: Implement** `api_admin_organization_branding_save()` (JSON for name/accent, `multipart/form-data` for the logo) and `branding_logo(orgcode)`. House upload convention lives in **`nx_lib/files.py`** — `is_file_allowed(filename, file_stream)`, which pairs `secure_filename` with `magic.from_buffer(header, mime=True)` against `ALLOWED_MIME_TYPES`. Reuse it; never trust the client content type. If `image/svg+xml` is not already in `ALLOWED_MIME_TYPES`, extend that set rather than hand-rolling a second check — and note that SVG is script-capable, so serve it with `Content-Disposition: inline` plus `Content-Security-Policy: sandbox`, or restrict the allowlist to PNG/JPEG if the owner prefers. Write to `var/branding/<orgcode>.<ext>`; create the directory on first write.
- [ ] **Step 4:** Validate the accent server-side with the same `_HEX_RE`; store `NULL` for an empty submission so the org falls back to Nexora branding.
- [ ] **Step 5:** Call `invalidate_branding()` after every successful save.
- [ ] **Step 6:** Add the branding panel to `templates/admin/organizations.html` (name, accent colour input, logo file input, live preview swatch) and wire it in the JS partial with `addEventListener` — no inline handlers.
- [ ] **Step 7:** Tests green. Commit.

```
feat(admin): per-organization branding panel with logo upload

Organization admins can set a brand name, accent hex and logo. Uploads are MIME-sniffed with magic,
capped at 512 KB, restricted to SVG/PNG/JPEG and stored under var/branding/, which deploy.yml
already excludes from the robocopy mirror. Saves invalidate the branding cache.

Co-Authored-By: <model> <noreply@anthropic.com>
```

### Task 12: Phase C chores + browser verification

**Files:** `translations/*`, `messages.pot`, `docs/howto/white-label.md`, `CHANGELOG.md`, `var/screenshots/`

- [ ] **Step 1:** i18n cycle for the new strings (`/nx-i18n`), de/fr/it non-fuzzy, `.po` diff-sweep after `pybabel update`.
- [ ] **Step 2:** Extend `docs/howto/white-label.md` with the branding section: what is brandable, the user-accent-wins precedence rule, where logos live, and the explicit statement that login, error pages and emails stay Nexora-branded (D2).
- [ ] **Step 3:** `CHANGELOG.md` under `[Unreleased]` → `### Added`.
- [ ] **Step 4: Verify in the real app, not mocks.** Restart the dev server, set a brand on the Privera org, then drive the browser yourself on your own port (`nx -u -b --loginas:ben.streich --no-conflict`) and screenshot `/dashboard` and `/admin/organizations` **before and after** into `var/screenshots/`. Kill the browser when done.
- [ ] **Step 5:** Full targeted suite: `pytest tests/unit/test_branding.py tests/unit/test_clients.py tests/unit/test_translations.py tests/unit/test_no_inline_event_handlers.py tests/unit/test_template_url_prefix.py tests/integration/test_admin_routes.py -q --no-cov`.
- [ ] **Step 6:** Commit.

```
docs(white-label): document branding and add de/fr/it strings

Covers what is brandable, the user-accent-wins precedence, logo storage under var/branding/, and the
deliberate exclusion of the login page, error pages and report emails.

Co-Authored-By: <model> <noreply@anthropic.com>
```

---

## Gotchas & notes

- **The two axes.** `ClientCode` is a *runtime source* (2 values, `default`/`ms02`); an Organization is a *customer* (5 values today). Most customers ride `default`. Any task that starts treating them as the same thing is wrong — re-read the spec's "two axes" section.
- **`CLIENTS` is built at import.** A client added through `/admin/clients` does nothing until the app pool recycles (D6). Say so in the UI; do not add a TTL to make it feel live — `workitem_sources.py` imports the dict object itself, so a rebuilt dict would not be seen by it anyway.
- **`invalidate_mapping_config()` is not optional.** Miss it on one write path and that edit appears broken for up to 60 s, which will read as a bug in the admin UI, not as a cache.
- **Config fields are interpolated into SQL, not parameterised.** `TableName`, `TableAlias`, `ColumnName`, `JoinCondition`, `TimeFilter`, `ExtraCondition` all reach query builders as text. Task 7 validates the identifier-shaped ones and deliberately keeps the free-form SQL fragments out of the UI. Do not "finish the job" by exposing them without a separate decision.
- **`IndexFieldMappings` dup-key trap is already fixed** — `FieldAliases.SourceFieldName` is the PK, so the admin UI gets a constraint violation instead of a silently-winning duplicate row. Surface it as a 409, not a 500.
- **CSP is PROD-only.** Everything with an inline `onclick=` works perfectly on INT and is dead on PROD. `tests/unit/test_no_inline_event_handlers.py` is the guard; the `page_header` macro's `data-nx-click="{{ act.onclick }}"` is the sanctioned pattern.
- **`var/branding/` survives deploys** because `var` is in `deploy.yml`'s `/XD` list — `/XD` directories are never copied *and* never purged. It is also inside `var\`, so no new SYAPP01 Defender exclusion is needed.
- **Jinja template cache** — restart the dev server after every template edit or you will review stale HTML and conclude the change did not work.
- **Parallel sessions number migrations too.** `0079`–`0081` were free on 2026-08-27; re-check with `--dry-run` before writing each file.
- **`sql-sync-check` fails on branches predating `0072`.** If this branch is cut from an older base, rebase past `9cdb7319` rather than absorbing the SQL deletions into an unrelated commit.
- **pybabel silently mangles malformed msgstr lines** — diff-sweep the `.po` files after every `pybabel update`.
- **Phases are independent.** C needs nothing from B, and B needs only A's table (not even its code change). Ship A, stop, and the app is unchanged; ship C alone and onboarding is still manual but customers see their brand.
