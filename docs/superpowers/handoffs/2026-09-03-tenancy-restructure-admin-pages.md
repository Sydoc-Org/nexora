# Handoff — tenancy restructure: org-centric model, three tenants, tenant admin pages

**Date:** 2026-09-03 · **Branch:** `refactor/255-admin-nav-tenancy-labels` (main checkout, no
worktree; cut from `origin/main` @ `a3e1a52d`) · **7 commits ahead of `origin/main`, nothing
pushed** · commit-only — the owner reviews and pushes.

**Prior handoffs:** [`2026-09-02-tenant-kernel-execution-complete.md`](2026-09-02-tenant-kernel-execution-complete.md)
(the tenant kernel this session builds on; its Task 10 cutover never ran and is now moot — see
Gotchas) and `2026-09-02-beautify-phase-2-3-execution-complete.md` — that one lives on branch
`v3.2.4.1`, not on this branch cut from `main`; the `var/handoff-pending` flag pointed at it at session
start and this session did unrelated work, so it was **not consumed** (the flag now points here).

## This session's commits (oldest → newest)

| Commit | What |
|---|---|
| `0bced853` | `refactor(admin)`: Clients → **Data Connections**, Processes → **Process Configurations**; nested collapsible **Tenants** sidebar group; `ms02` labelled **Mobscn** (migration `0089`); two pre-existing bugs fixed (sidebar expand rules held nested groups open; `/admin/processes` help text lost its `<customer>.<process>` placeholders) |
| `f4f9155d` | `feat(admin)`: `/admin/tenants` overview page (#256 phase 1) |
| `3c962798` | `feat(tenancy)`: **organization-centric model**, migration `0090` (#257) |
| `59e94a3d` | `fix(admin)`: the Organizations page **keeps its name** (a "Customers" rename was a misread of the brief, reverted) |
| `07782e01` | `feat(tenancy)`: **Generali is a tenant** — data-only connection, migrations `0091`/`0092` |
| `247b10e8` | `feat(tenancy)`: tenant-scoped sidebar, Mobscn pages, the **Sydoc** tenant — migrations `0093`/`0094`/`0095` |
| `97a66fe0` | `feat(admin)`: **tenant management page** `/admin/tenants/manage` (#256 phase 2) |

## TL;DR

1. **The data model is organization-centric now** (owner's diagram, 2026-09-03): *Tenant → Organizations →
   {Users, Access profiles, Data connection, Process configurations}.* Migration `0090` added four
   nullable FKs — `Organizations.TenantCode`, `Organizations.ClientCode`, `ProcessSources.OrganizationCode`,
   `AccessProfile.OrganizationCode` — all backfilled from conventions the data already followed.
   `Tenants.OrganizationCode` (pre-0090 pointer) is **nullable and legacy**; `Organizations.TenantCode` is
   the relation that counts.
2. **Three tenants exist on INT:** `ms02` **Mobscn** (PDBS), `generali` **Generali** (GNRL, data-only
   connection `engine_generali_db`, eight mounted pages), `sydoc` **Sydoc** (ElektroMaterial, Privera,
   Compass — Compass got its missing `CMPS` organization row). **Tenant-scoped users see only their tenant
   group** in the sidebar (Dashboard / Workitems / Prepared Documents); sydoc staff (SYDC, no tenant) keep
   the global navigation.
3. **Access profiles bind to an organization** (NULL = global). A bound profile is only assignable to that
   organization's users — enforced on user add/edit (400), on binding a profile users elsewhere hold
   (409), and in the profile pickers on Access Control and the user page.
4. **Two admin pages are new:** `/admin/tenants` (read-only overview of the whole tree) and
   `/admin/tenants/manage` (tenants, their organizations, mounted pages). Entities/fields and the generated
   list/crud pages stay **migration-only**. Full unit tier green (`1229 passed`), e2e header tests green,
   every flow verified live on INT as three different users.

---

## What shipped

### Naming and navigation (`0bced853`, `59e94a3d`)

| File | Change |
|---|---|
| `templates/_header.html` | Admin submenu gained a nested collapsible **Tenants** group (`#adminTenantsNavGroup`, generic `data-nx-nav-group` wiring): Overview · Manage · Organizations · Data Connections · Process Configurations. Hardcoded Generali group **removed** (`07782e01`). Global Dashboard/Reporting/Workitems links render only when `not tenant_scoped` (`247b10e8`). Custom tenant pages use `p.icon` and match `active_page in (p.endpoint, p.active)`. |
| `static/css/_header.css` | All four `#<id>.<x>-open .sidebar-nav-subitems` rules take `>` (descendant form held a nested group open when closed); a `:has()` rule lifts the parent's measured `max-height` while a nested group is open (ids spelled out — a generic selector loses on specificity). |
| `templates/admin/clients.html`, `processes.html`, `admin_overview.html`, `templates/js/_header_js.html`, `modals/_organizations_modals.html` | Labels: Data Connections / Process Configurations; Organizations keeps its name. `processes.html` help text entity-encodes `<customer>.<process>` / `<name>` (that paragraph renders unescaped). |
| `sql/_migrations/NexoraDB/0089_rename_ms02_display_name.sql` | `dbo.Clients` + `dbo.Tenants` DisplayName `ms02` → **Mobscn**. Code stays `ms02`. |
| `tests/e2e/test_header.py` | `test_header_admin_tenants_subgroup_expands_and_navigates` — asserts the group's `nx-nav-open` class, **not** Playwright visibility (a max-height-clipped child still reports a box). |

### Organization-centric model (`3c962798`)

| File | Change |
|---|---|
| `sql/_migrations/NexoraDB/0090_organization_centric_tenancy.sql` | The four FK columns + backfill (tenant pointer; `<customer>.` process-name prefix; `priveraUser`-style profile names). `compass.*` / `compassUser` had no organization → stayed NULL/global (Compass org arrived in `0094`; `compassUser` **still global**, see Gotchas). |
| `nx_lib/views/admin/organizations.py`, `templates/admin/organizations.html`, `modals/_organizations_modals.html`, `templates/js/admin/_organizations_js.html` | Tenant + Data connection columns and pickers; edit modal writes both; after-save **reloads** (client-side row rebuild removed). Pickers degrade to empty when `dbo.Tenants`/`dbo.Clients` are unreadable (TEST). |
| `nx_lib/views/admin/processes.py`, `templates/admin/processes.html`, `_processes_js.html`, `nx_lib/mapping_config.py` | `OrganizationCode` on process sources (picker + chip); `ProcessSource.organization` in the registry. |
| `nx_lib/views/admin/permissions.py`, `templates/admin/access_control.html`, `_access_control_js.html` | Profile drawer has an Organization picker; cards show the binding; user-form profile picker filters by chosen organization (`filterProfilesByOrg`). 409 when binding would strand users. |
| `nx_lib/views/admin/users.py`, `templates/admin/user_detail.html`, `_user_detail_js.html` | `_profile_org_mismatch()` → 400 on add/edit; user-detail picker filters too. |
| `sql/test/schema.sql` | The three columns added to `Organizations` / `AccessProfile` (no FKs — TEST has no `Tenants`/`Clients` tables). |

### Overview page (`f4f9155d`, reworked in `3c962798`)

`nx_lib/views/admin/tenants.py` (`build_tenant_tree()` pure, tested in
`tests/unit/test_admin_tenants_tree.py`), `templates/admin/tenants.html`, `static/js/admin_tenants.js`.
One card per tenant → organization blocks → four boxes; then "Organizations not in a tenant" and
"Shared across organizations" (connections nobody rides, unassigned process configurations, global
profiles). Gated `admin.view.organizations`; connection/config boxes honour `admin.view.clients` /
`admin.view.processes`.

### Generali as a tenant (`07782e01`)

| File | Change |
|---|---|
| `sql/_migrations/NexoraDB/0091_generali_tenant.sql` | `generali` client (`engine_generali_db`, no Octo), `GNRL` organization, `generali` tenant, eight `custom` pages (`LayoutJSON`: endpoint/label/icon/active). Its grant step matched nothing (used `Effect='ALLOW'`; the table uses `'A'`). |
| `sql/_migrations/NexoraDB/0092_generali_tenant_view_grants.sql` | Corrected: `tenant.generali.view` to every profile/user holding any `generali.*` grant (6 profile rows + 1 override on INT). |
| `nx_lib/clients.py` | `engine_generali_db` in `_engines()`. A `dbo.Clients` row **without an Octo domain now loads** as a data-only connection (only `default` still needs one). `workitem_clients()` = connections with a domain; `api_external.py` and the client-hint routing in `workitem_sources.py` use it, so a data-only connection never gets probed as a workitem source. |
| `nx_lib/views/tenant.py::_tenant_nav_page` | Reads optional `label` / `icon` / `active` from `LayoutJSON`. |

### Tenant-scoped sidebar, Mobscn pages, Sydoc (`247b10e8`)

| File | Change |
|---|---|
| `nx_lib/tenant/registry.py` | `organization_tenant(org_code)` — cached (60 s) map from `Organizations.TenantCode`; **fails closed to None = not scoped**. `Tenant.organization_code: str | None`. |
| `nx_lib/hooks.py::_inject_tenant_nav` | Adds `tenant_scoped` (the session user's tenant, via `session["organizationcode"]`). |
| `sql/_migrations/NexoraDB/0093_ms02_tenant_pages.sql` | Mobscn: `dashboard` custom page added; `workitems`/`prepared` get label/icon/active; generated **PDBS Dossiers** list page → `draft` (row and entity/field descriptors kept). |
| `sql/_migrations/NexoraDB/0094_sydoc_tenant.sql` | `ALTER Tenants.OrganizationCode NULL`; `CMPS` organization; `sydoc` tenant with LKTR/PRVR/CMPS; `compass.*` source → CMPS; `tenant.sydoc.view` to member-org profiles + `globalAdmin`; three mounted pages. |
| `sql/_migrations/NexoraDB/0095_tenant_admin_permissions.sql` | `admin.view.tenants` / `admin.edit.tenants`, seeded like `0080` to profiles holding `admin.view.organizations`. |

### Tenant management page (`97a66fe0`)

`nx_lib/views/admin/tenant_manage.py` (validators `validate_tenant_payload` / `validate_page_payload` /
`mountable_endpoints` are pure and tested in `tests/unit/test_admin_tenant_manage.py`),
`templates/admin/tenants_manage.html`, `templates/js/admin/_tenants_manage_js.html`, `nx_lib/security.py`
(`adminTenantsPagePerm`). Endpoints: `POST /admin/tenants/add`, `POST /admin/tenants/edit/<code>`,
`DELETE /admin/tenants/delete/<code>` (409 while organizations remain), `POST /admin/tenants/<code>/pages/add`,
`POST .../pages/<key>/status`, `DELETE .../pages/<key>`. Every write calls `invalidate_tenant_config()`;
creating a tenant calls `provision_tenant_permissions()`. Membership = `Organizations.TenantCode`; ticking an
organization owned by another tenant moves it. **Organization codes are validated before any write** (a bad
code answers 400, not an FK 500).

---

## Next steps (ordered)

1. **Owner: review and push** `refactor/255-admin-nav-tenancy-labels`. Seven commits; the branch name is the
   original relabel — a PR titled for the tenancy restructure reads better. Issues to link: #255 (closed),
   #256 (phase 2 landed, entities/fields remain), #257 (model + tenants), #238 (permission rename, related).
2. **PROD env keys:** none added. Migrations `0089`–`0095` apply on push to `main` via `deploy.yml`; `0090`
   and `0094` carry DDL (new columns, `Tenants.OrganizationCode` → NULL). Run `scripts/env-sync.py` anyway
   (habit), nothing is expected.
3. **Drop the legacy pointer** — a later migration removes `Tenants.OrganizationCode` once
   `nx_lib/tenant/registry.py` stops selecting it (`Tenant.organization_code`) and
   `nx_lib/views/admin/tenants.py::build_tenant_tree` drops its fallback branch. Small, deliberate follow-up.
4. **`compassUser` → CMPS:** bind once the DMEO/"demo" situation is clear (see Gotchas). One `UPDATE` in a
   migration, then the 409 rule protects it.
5. **#238 (permission-structure rename)** is where `generali.*` → `tenant.generali.*` and the
   `.organizational`/`.transorganizational` scoping fold into the tenant model. Plan:
   `docs/superpowers/plans/2026-09-01-permission-structure-rename-grid.md` on the unpushed worktree branch
   `plan/permission-structure-rename-grid`; its migrations were numbered `0086`–`0088` — **those numbers are
   still free** but the plan's assumptions about profiles predate `AccessProfile.OrganizationCode`.
6. **#256 remainder:** entity/field editors for `list`/`crud` pages. Not started. Reuse the registry's
   `_IDENT_RE` for every identifier.
7. Optional polish: `DELETE /admin/tenants/delete/<code>` leaves the `tenant.<code>.view/.edit` Permission rows
   (harmless); the Generali `custom` pages carry English-only labels from `LayoutJSON` (the old hardcoded group
   was translated).

## Gotchas & notes

- **The `demo` organization (DMEO) vanished from INT during the session** — it existed at 09:00, was gone by
  15:50. Nothing in this branch deletes organizations; the owner moved `demo.user` to PDBS and most likely
  deleted the empty org via the UI. `invite.demo` (held `compassUser`) is presumably gone or moved too —
  check before binding `compassUser`.
- **The venv-PATH trap** (memory saved: `reference_venv_path_breaks_sql_sync_hook`): prepending
  `.venv/Scripts` to `PATH` in a Bash call makes the `sql-sync-check` hook fail with
  *"mssql-scripter produced no files"* — the `mssql-scripter` launcher runs `python -m mssqlscripter` with the
  venv Python, which lacks the package. **Commit without the venv PATH prefix.** `SQL_SYNC_SKIP=1` is only
  legitimate when the commit carries no SQL. The hook also flags an **untracked** `sql/_migrations/*.sql` as
  drift — stage the migration first.
- **`Tenants.OrganizationCode` is legacy.** Three readers remain: the registry select, `build_tenant_tree`'s
  fallback, and `tenant_manage.py` (writes the single org or NULL). `visible_tenant_nav` does not use it.
- **Tenant-scoped ≠ permission.** `tenant_scoped` (org → tenant) hides the global links; the tenant *group*
  still needs `tenant.<code>.view`. A scoped user without that permission sees an empty sidebar — grant the
  permission (Access Control) when adding a user to a tenant organization.
- **Custom page mounts don't check the target page's own permission** (known kernel gap, documented in
  `_tenant_nav_page`'s docstring): a Mobscn user without `workitems.view` sees a Workitems link that 403s.
- **`page_visibility` key count test** (`tests/unit/test_security.py`) enumerates keys — it now says 21; any
  new key must be added there.
- **Playwright visibility vs. max-height clipping:** a child inside a `max-height: 0; overflow: hidden`
  container still reports a non-empty box → `to_be_hidden()` never holds. Assert on classes instead
  (see `tests/e2e/test_header.py`).
- **`ngettext()` is used for the first time** (`%(num)d field(s)`, `%(num)d organization(s)`);
  `tests/unit/test_translations.py::_translations_map` normalises plural msgstr tuples vs lists for it.
- **The tenant-kernel handoff's "Task 10 cutover"** (`2026-09-02-tenant-kernel-execution-complete.md`) is
  superseded: MS02's generated `list` page is `draft` and its users reach Workitems through the mounted page.
- Design-system input for the overview came from `ui-ux-pro-max` (data-dense dashboard style; house tokens
  kept, no new fonts/colours).

## Untracked / left for owner

- `docs/design/Dashboard_redesign/` — appeared at 14:05 today, **not mine**, not committed.
- `var/screenshots/255_*.png`, `256_*.png`, `257_*.png` — gitignored evidence of every page state.
- `var/handoff-pending` — currently points at the beautify handoff; this handoff overwrites it (step 6).

## How to verify

```powershell
# fast tier (all green at 97a66fe0: 1229 passed, 29 skipped)
$env:PATH = "C:\dev\nexora\.venv\Scripts;$env:PATH"
python -m pytest tests/unit -q -x -p no:randomly -p no:cacheprovider

# the pieces this session touched most
python -m pytest tests/unit/test_admin_tenants_tree.py tests/unit/test_admin_tenant_manage.py `
  tests/unit/test_tenant_registry.py tests/unit/test_hooks.py tests/unit/test_clients.py `
  tests/unit/test_translations.py tests/unit/test_security.py -q -p no:randomly -p no:cacheprovider

# e2e header (nested Tenants group) -- CI-only tier, run by hand; needs the TEST db reset first
python scripts/test_db_reset.py
$env:NEXORA_E2E_PORT = "8123"; python -m pytest tests/e2e/test_header.py -q -k admin -p no:randomly

# live: three users, three sidebars
bin\nx.ps1 -u --no-conflict          # then /dev/login/ben.streich (global + all groups),
                                      # /dev/login/demo.user (Mobscn only), /dev/login/germaine.heldner (Sydoc only)
# pages: /admin/tenants, /admin/tenants/manage, /admin/organizations, /admin/access_control
```

Migrations `0089`–`0095` are applied on INT (`python scripts/db-migrate.py --env INT --dry-run` → up-to-date).

## Resuming in a fresh session

Run `/reset-session docs/superpowers/handoffs/2026-09-03-tenancy-restructure-admin-pages.md` (the flag
in `var/handoff-pending` points here). Start at **Next steps 1** (owner pushes) or **3** (drop the legacy
pointer) if the branch is already merged. Everything else in this file is context, not a to-do.
