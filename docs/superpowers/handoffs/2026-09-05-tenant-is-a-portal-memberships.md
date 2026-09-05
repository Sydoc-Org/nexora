# Handoff — a tenant is a portal: memberships, scoped Dashboard/Workitems, process grants in both shapes

**Date:** 2026-09-05 · **Branch:** `refactor/255-admin-nav-tenancy-labels` (main checkout, no
worktree; cut from `origin/main` @ `a3e1a52d`) · **22 commits ahead of `origin/main`, nothing
pushed** · commit-only — the owner reviews and pushes.

**Prior handoff:** [`2026-09-03-tenancy-restructure-admin-pages.md`](2026-09-03-tenancy-restructure-admin-pages.md)
(the organization-centric model and the three tenants this session reshapes). Its Next step 3 ("drop the
legacy pointer") is done here by `0096`; step 5 (#238) has meanwhile been applied to INT from its own
worktree — see Gotchas.

## Commits since the last handoff (oldest → newest)

| Commit | What |
|---|---|
| `bb094f49` | `refactor(tenancy)`: **a tenant is a portal, not a data connection** — migration `0096` |
| `caadb582` | `chore(i18n)`: translations for the `0096` strings |
| `fb908370` | `test(tenancy)`: integration tests caught up with `0090` and the nav page keys |
| `def8eb4e` | `fix(ui)`: checkbox/radio size floor — **parallel session, not this work** |
| `ebbcdf07` | `fix(header)`: mounted tenant pages highlight only inside the user's tenant |
| `c6df1b9f` | `feat(dashboard)`: the tenant Dashboard shows only the tenant's processes — migration `0097` |
| `64ea14ce` | `feat(scripts)`: `scripts/seed-int-db.py` — **parallel session, not this work** |
| `88769304` | `feat(workitems)`: the tenant Workitems page shows only the tenant's processes — migration `0098` |
| `26909d46` | `style(admin)`: Tenants admin group icon `fa-city`, Manage `fa-sliders` |
| `82bfad1e` | `feat(header)`: a user inside exactly one tenant gets a flat sidebar section, not a group |
| `79a55438` | `fix(scripts)`: seeder magnitudes from the live runtime — **parallel session, not this work** |
| `0dae9db0` | `fix(branding)`: an organization's brand accent beats a stored personal pick |
| `db7bc4c1` | `fix(permissions)`: process grants read in both the `0087` and the legacy code shapes |
| `1250543d` | `feat(tenancy)`: ISS joins `generali`, sydoc AG joins `sydoc` — migration `0104` |

## TL;DR

1. **A tenant is a branded portal**: a set of organizations sharing navigation, look and a permission
   group. It is **not** a data connection any more. Migration `0096` dropped `Tenants.ClientCode`,
   `Tenants.OrganizationCode` and `Organizations.ClientCode`; the connection lives on the thing that reads
   it (`ProcessSources.ClientCode`, new `TenantEntities.ClientCode`). The admin overview derives an
   organization's connections from its process sources.
2. **Who sees a tenant = membership OR `tenant.<code>.view`** (`nx_lib/views/tenant.py::can_view_tenant`).
   A member of exactly one tenant gets its pages **flat** under a section label; staff and multi-tenant
   users keep collapsible groups. Since `0104` only `demo` (DMEO) sits outside a tenant: ISS (SSIX) is in
   `generali`, sydoc AG (SYDC) in `sydoc` — **sydoc staff now land on the Sydoc Dashboard by default**.
3. **The tenant Dashboard and Workitems are the tenant's** (`0097`/`0098`): `/dashboard?tenant=<code>` and
   `/workitems?tenant=<code>` narrow the process allow-list to the tenant's organizations' processes and
   title themselves "<Tenant> Dashboard/Workitems"; the global entries are **Global Dashboard / Global
   Workitems** and link with `?tenant=` (empty) to clear the **sticky session scope**. Prepared Documents
   stays unscoped.
4. **INT permission codes changed under this branch** (#238's `0086`/`0087`, applied from another
   worktree): one `process.<client>.<name>.view` per process. `process_helpers.process_grants` reads both
   that and the legacy `*.filter.process.*` / `reporting.scope.process.*` families, and every allow-list
   (dashboard, workitems, reporting view + runner) goes through it. Full unit tier green at `db7bc4c1`
   (`1508 passed, 29 skipped`).

---

## What shipped

### Tenant = portal (`bb094f49`, `caadb582`, `fb908370`)

| File | Change |
|---|---|
| `sql/_migrations/NexoraDB/0096_tenant_is_a_portal.sql` | Adds `TenantEntities.ClientCode` (backfilled from `Tenants.ClientCode`, `THROW` if NULL, NOT NULL + FK); drops `Organizations.ClientCode`, `Tenants.ClientCode`, `Tenants.OrganizationCode` with their FKs. `sql/test/schema.sql` follows. |
| `nx_lib/tenant/registry.py` | `Tenant(code, display_name, active)`; `TenantEntity.client_code`; `organization_tenant()` via `organization_tenant_map()` (60 s cache, None on failure); `processes_of_tenant()` (pure) + `tenant_processes(code) -> set | None`; `provision_tenant_permissions()`. |
| `nx_lib/views/tenant.py` | `can_view_tenant()` (membership or grant); `_resolve_client_engine` uses `CLIENTS.get(entity.client_code)`; `_layout_query()` turns `LayoutJSON.query` string pairs into `url_for` args. |
| `nx_lib/views/admin/tenants.py`, `organizations.py`, `tenant_manage.py` + templates/JS | No connection column/picker anywhere; overview derives `clients` from process sources (`missing: True` when a source names an unknown connection). `_SCOPED_ENDPOINTS` adds `query`/`active` when mounting `dashboard` / `workitems_overview`. |
| `docs/howto/white-label.md`, `docs/superpowers/specs/2026-08-31-tenant-platform-design.md` | Axis 3 rewritten (portal, membership-or-grant); spec amendment dated 2026-09-03. |

### Scoped Dashboard / Workitems, sticky scope (`ebbcdf07`, `c6df1b9f`, `88769304`, `82bfad1e`)

| File | Change |
|---|---|
| `sql/_migrations/NexoraDB/0097_tenant_dashboard_scope.sql`, `0098_tenant_workitems_scope.sql` | `JSON_MODIFY` on every tenant's mounted `dashboard` / `workitems_overview` page: `active = tenant_<code>_dashboard|_workitems`, `query = {"tenant": "<code>"}`. |
| `nx_lib/views/tenant.py::apply_tenant_scope` | `?tenant=<code>` sets `session['tenant_scope']`; `?tenant=` (present, empty) clears; **absent keeps** (Workitems rewrites its own URL); member without a scope defaults to their own tenant; unknown explicit → 404, not viewable → 403; stale remembered scope dropped silently. Call it **before** a view's catch-all `try`. |
| `nx_lib/process_helpers.py::granted_processes(prefix)` | Session grants ∩ `tenant_processes(scope)`; unresolvable scope → **empty set, never everything**. Replaced thirteen grant-parsing blocks in `dashboard.py`, `workitems.py`, `prepare_process_selection_*`, `_selected_pairs`. |
| `templates/_header.html` | Global entries = `url_for('dashboard', tenant='')` **Global Dashboard** / **Global Workitems**; macro `tenant_page_link(t, p, sub, active_page, tenant_scoped)`; active rule: tenant-specific marker matches exactly for anyone, plain endpoint match only inside own tenant; flat branch when `tenant_nav|length == 1 and tenant_nav[0].code == tenant_scoped` (`.sidebar-section-label`, `data-testid="header-nav-tenant-<code>-label"`). |
| `templates/dashboard.html`, `workitems_overview.html` | `active_page = tenant_<code>_dashboard|_workitems` when scoped; titles `%(tenant)s Dashboard` / `Global Dashboard` (`data-testid="dashboard-title"`, `workitems-title`). Dashboard cache keys include the scope. |

### Branding, icons (`26909d46`, `0dae9db0`)

`templates/_header.html` pre-paint resolver is **brand-first** (`accent: brand.accent_hex ? 'custom' : stored…`);
`templates/appearance.html` shows the brand swatch + note (`data-testid="appearance-accent-branded"`) instead of
the picker; `tests/integration/test_appearance_branding.py` new. Tenants admin group icon `fa-city`.

### Process grants in both shapes (`db7bc4c1`)

`nx_lib/process_helpers.py::process_grants(perms, prefix)` (pure; `_PROCESS_VIEW_RE`), used by
`granted_processes`, `nx_lib/views/reporting.py::_allowed_processes` and
`nx_lib/reporting/runner.py::_allowed_processes_from_perms`. Reporting deliberately skips the tenant scope.

### Memberships (`1250543d`)

`sql/_migrations/NexoraDB/0104_iss_and_sydoc_join_tenants.sql` — two `UPDATE dbo.Organizations SET TenantCode`.
ISS's `tenant.generali.view` grants stay **by design** (owner, 2026-09-05). Verified live as `robin.krieg`
(flat Generali portal) and `mauro.buehler` (Sydoc Dashboard by default, Generali group via grant);
screenshots `var/screenshots/0104_*.png`.

---

## Next steps (ordered)

1. **Owner: review and push** the branch (22 commits). PR title for the tenancy restructure, not the
   relabel. Link #255 (closed), #256 (phase 2 landed; entity/field editors open), #257, #238.
2. **PROD env keys:** none added. Migrations `0089`–`0098` + `0104` apply on push to `main`; `0090`, `0094`,
   `0096` carry DDL. Run `scripts/env-sync.py` by habit. **`0099`–`0103` belong to
   `feat/254-field-extraction-quality`** — whichever branch merges first leaves a numbering gap, which the
   migrator tolerates (applies by filename, records each).
3. **#238 permission rework** (worktree `.claude/worktrees/plan-permission-structure-rename-grid`, locked):
   owns `/admin/processes` provisioning (still writes `workitems.filter.process.<name>`) and the Access
   Control grid grouping (old prefixes). It can drop its own Task 6 helper and use `process_grants`.
   Owner confirmed 2026-09-05 this waits for that branch.
4. **`compassUser` → CMPS**, **#256 entity/field editors**, and `DELETE /admin/tenants/delete/<code>` leaving
   `tenant.<code>.*` Permission rows — all carried over from the prior handoff, untouched.
5. Small INT data oddities noticed, not fixed: `GeneraliUser` profile holds `tenant.ms02.view/.edit`; the
   Privera logo file the `BrandLogoFile` names is missing (404); PDBS `BrandAccentHex` is `#000000`.

## Gotchas & notes

- **INT is shared by three worktrees.** `dbo.SchemaMigrations` holds `0099`–`0103` from
  `C:\dev\nexora-254` and `0086`/`0087` from the #238 worktree, none of which exist in this branch's
  tree. **Next free number is `0105`.** Check with
  `SELECT TOP 5 * FROM dbo.SchemaMigrations ORDER BY 1 DESC` (the columns are not named `Version`) and
  `ls` every worktree's `sql/_migrations/NexoraDB` before numbering.
- **`sql-sync-check` is red on this branch** because INT carries the foreign view
  `vEmFieldExtractionQuality` (nexora-254). Every commit here used `SQL_SYNC_SKIP=1`; migrations were
  applied by hand first (`python scripts/db-migrate.py --env INT --db NexoraDB`). Do **not** commit the
  regenerated dump of that view. Memory: `reference_table_drop_sync_check_trap`.
- **Peer pre-commit stash flicker:** a parallel session's commit stashes unstaged files for 30–60 s; an
  edit "vanishing" is that, not data loss. A dev server started in that window caches the **old**
  template — restart it (`bin\nx.ps1 -r --port:<n>`).
- **Permission codes on INT are the `0087` shape.** TEST and PROD are still the legacy shape until #238
  ships; `process_grants` covers both. `demo.user` needed no permission change — they hold
  `process.sydoc.05_PDBS.view`, `tenant.ms02.view`, `dashboard.view`, `workitems.view`.
- **Sticky scope semantics** (above) mean a bare `/dashboard` is not the global view for a member; the
  Global sidebar entries carry `?tenant=` on purpose. Tests: `tests/integration/test_dashboard_routes.py`,
  `test_workitems_routes.py` (patch `tv.tenant`, `tv.can_view_tenant`, `tv.organization_tenant`);
  patching the registry's `organization_tenant` needs `sys.modules["nx_lib.tenant.registry"]`, not the
  dotted string (the re-export catches it otherwise).
- **`/t/<code>/…` answers 403 before 404** for a tenant the session may not view; Mobscn's code is `ms02`,
  not `mobscn`; the PDBS Dossiers page is `draft`.
- **Custom page mounts still don't check the target page's own permission** (kernel gap from the prior
  handoff, unchanged).
- **Playwright:** own instance via `bin\nx.ps1 -u --no-conflict` (takes 8003 when 8001 is busy), stop with
  `bin\nx.ps1 -d --port:<n>`. Orphan chrome: filter `Name='chrome.exe'` and run via
  `powershell.exe -NoProfile` from Bash — an unfiltered loop kills its own shell. Bash-launched `pwsh`
  hangs; use the PowerShell tool.
- **Unit tier launched in the background survives the session** but its output file lands under the
  *previous* session's task dir — re-run rather than hunt for it.

## Untracked / left for owner

- `docs/design/Dashboard_redesign/` — **not mine**, not committed (appeared 2026-09-03).
- `var/screenshots/0104_*.png`, `255_*`, `256_*`, `257_*` — gitignored evidence.
- The owner's port-8000 instance (PID 14592) restarted at some point on 2026-09-05; membership changes need
  no restart (60 s registry cache).

## How to verify

```powershell
# full unit tier (green at db7bc4c1: 1508 passed, 29 skipped, ~8.5 min)
$env:ENVIRONMENT = "INT"; .venv\Scripts\python -m pytest tests/unit -q -p no:cacheprovider

# the pieces this session touched most
.venv\Scripts\python -m pytest tests/unit/test_process_helpers.py tests/unit/test_tenant_registry.py `
  tests/unit/test_admin_tenants_tree.py tests/unit/test_admin_tenant_manage.py tests/unit/test_dashboard_stats.py `
  tests/integration/test_tenant_routes.py tests/integration/test_dashboard_routes.py `
  tests/integration/test_workitems_routes.py tests/integration/test_appearance_branding.py -q -p no:cacheprovider
# integration needs the TEST db: python scripts/test_db_reset.py first

# migrations: up to date on INT (0096-0098, 0104 applied)
.venv\Scripts\python scripts/db-migrate.py --env INT --dry-run

# live
bin\nx.ps1 -u --no-conflict     # /dev/login/robin.krieg (flat Generali), /dev/login/mauro.buehler (Sydoc default),
                                # /dev/login/ben.streich (all groups + Global entries), /dashboard?tenant= (global)
```

## Resuming in a fresh session

Run `/reset-session docs/superpowers/handoffs/2026-09-05-tenant-is-a-portal-memberships.md` (the flag in
`var/handoff-pending` points here). Start at **Next steps 1** (owner pushes). Nothing on this branch is
red; everything else in this file is context, not a to-do.
