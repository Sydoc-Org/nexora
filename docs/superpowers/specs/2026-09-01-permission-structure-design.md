# Permission structure — design (#238)

**Status:** approved design, 2026-09-01. Implementation plan follows via `/write-plan`.
**Issue:** [#238 Permission Structure](https://github.com/Sydoc-Code/nexora/issues/238)

## Why

The permission catalogue grew by accretion. Today (INT, 2026-09-01):

| thing | count |
|---|---|
| codes in `dbo.Permission` | 144 |
| access profiles | 10 |
| users | 21 |
| profile-permission rows | 855, of which 446 are `DENY` |
| user override rows | 9 (4 users) |
| codes referenced anywhere in the code base | ~100 |

What makes it confusing:

1. **Half the profile table is noise.** A user has exactly one profile and the default is deny,
   so a profile-level `DENY` row is identical to no row. The editor still shows None / Deny /
   Allow radios per row and pre-selects Deny on 446 rows.
2. **Per-process grants are triplicated.** The same (client, process) exists as
   `workitems.filter.process.X`, `dashboard.filter.process.X` and `reporting.scope.process.X`.
   Every profile grants the three identically; `/admin/processes` auto-provisions only the first.
3. **Meta-permission per profile.** Assigning profile X needs
   `admin.assign.user.accessprofile.<lowercased name>` — ten codes coupled to profile names.
   The live matrix is strictly hierarchical (enterpriseAdmin: all; globalAdmin: seven).
4. **22 orphan codes.** `invoices.*` (page retired, #177), `kundenmagazin.*`,
   `admin.interact.users.all`, `admin.view.mobscn.processmanagement`, the ten assign codes.
5. **No naming convention.** Verb-first (`admin.edit.user`) and noun-first
   (`workitems.details.view.images`) coexist; `generali.additionalservices.view` gates the
   *attendance* page; descriptions contradict codes ("View ms Project on dashboard" for a
   workitems filter).
6. **The editor is a 144-row drawer** per profile; inconsistencies between profiles are invisible.

## Decisions (approved 2026-09-01)

| # | decision | choice |
|---|---|---|
| D1 | rename scope | **full rename** to one grammar, grants preserved by `PermissionID` |
| D2 | profile editor | **grid**: permissions × profiles, checkbox cells |
| D3 | Generali family | moves to **`tenant.generali.*`** now, ahead of the tenant platform |
| D4 | delivery | **one release**, four phased commits on one branch |
| D5 | rank rule | may assign a profile whose rank is **at or below** the actor's own rank |
| D6 | deploy | **accept the blip**: migrations run before the app pool stops; deploy off-hours |

## Grammar

```
<area>[.<object>[.<sub>]].<action>[.<scope>]
```

- Lowercase, dot-separated. Underscores and capitals appear **only** inside external
  identifiers (process names such as `03_Invoice_New`, reporting source codes such as
  `generali_pdqm`).
- `<action>` is one of: `view add edit delete use run export schedule manage bypass import restart`.
- `<scope>` is optional: `org` (records of the actor's organization), `all` (every
  organization), `pastdeadline` (the deadline modifier on `add`). No scope = own records.
- `<area>.view` alone is the area's landing page and gates everything beneath it. In the UI the
  children of an area (or of an `<object>.view`) are greyed until the parent `.view` is granted.
  This is a UI convention only — the server checks each code on its own, as today.
- Areas: `admin workitems dashboard reporting process tenant api jd`. `tenant.<code>` and
  `process.<client>` are two-segment areas.
- Descriptions are English, imperative, "Verb object, qualifier" (`Edit users`,
  `Add attendance records for the whole organization`).

Enforced by `tests/unit/test_permission_codes.py`: every literal passed to
`require_permission` / `has_permission` in `nx_lib/` and `templates/`, every code in
`sql/test/seed.sql`, and every code in migration `0088` must match

```
^[a-z]+(\.[a-z]+)?(\.[A-Za-z0-9_]+)*\.(view|add|edit|delete|use|run|export|schedule|manage|bypass|import|restart)(\.(org|all|pastdeadline))?$
```

Dynamic families (codes minted by the app at runtime):

| family | shape | minted by |
|---|---|---|
| process scope | `process.<client>.<name>.view` | `/admin/processes` on saving a `(ClientCode, ProcessName)` row (granted to nobody) |
| reporting source | `reporting.source.<code>.use` | `dbo.ReportingSources.Permission` (registry column) |
| tenant | `tenant.<code>.view`, `tenant.<code>.edit`, `tenant.<code>.<object>.<action>[.<scope>]` | tenant kernel (future) |

## Data model

### `dbo.AccessProfilePermission`
Drop `Effect` and `CK_AccessProfilePermission_Effect`. A row means *granted*. The 446 `DENY`
rows are deleted first (semantically empty — see Why §1).

### `dbo.UserPermissionOverride`
Unchanged. Keeps `Effect IN ('A','D')`; overrides are the only place a deny exists.

### `dbo.AccessProfile`
Add `Rank int NOT NULL CONSTRAINT DF_AccessProfile_Rank DEFAULT 0`. Seed by name:

| profile | rank |
|---|---|
| enterpriseAdmin | 100 |
| globalAdmin | 90 |
| nexoraSupervisor, issSupervisor | 50 |
| every other profile | 10 |

**Rule (D5):** an actor may assign profile *P* to a user iff `P.Rank <= actor.profile.Rank`.
A user without a profile may assign nothing. This replaces the ten
`admin.assign.user.accessprofile.*` codes. Consequence vs today: globalAdmin gains the right to
assign globalAdmin and pdbsUser. Rank governs profile assignment only — editing a user of higher
rank stays governed by `admin.users.edit`, as today (ceiling noted; per-rank edit protection is a
one-line extension if ever wanted).

### `dbo.fnUserHasPermission(@UserID, @PermCode)`
Resolution order shrinks to: user `D` → 0; user `A` → 1; profile row exists → 1; else 0.

### `dbo.spGetUserPermissions(@UserID)`
Set-based rewrite (one query, no per-code UDF calls):

```sql
SELECT p.Code
FROM dbo.Permission p
WHERE NOT EXISTS (SELECT 1 FROM dbo.UserPermissionOverride o
                  WHERE o.UserID=@UserID AND o.PermissionID=p.PermissionID AND o.Effect='D')
  AND ( EXISTS (SELECT 1 FROM dbo.UserPermissionOverride o
                WHERE o.UserID=@UserID AND o.PermissionID=p.PermissionID AND o.Effect='A')
     OR EXISTS (SELECT 1 FROM dbo.Users u JOIN dbo.AccessProfilePermission ap ON ap.AccessID=u.accessid
                WHERE u.userID=@UserID AND ap.PermissionID=p.PermissionID) );
```

### `dbo.ReportingSources.Permission`
Holds code strings; migration `0088` rewrites them with the same mapping.

### `dbo.Permission`
Unchanged shape. 144 → **112** codes (see Appendix A). One new code: `admin.permissions.edit`
(catalogue edits), seeded to every profile holding `admin.edit.accessprofile` today.

## Migrations (NexoraDB, `GO`-separated, idempotent, data-driven)

PROD's catalogue may differ from INT's (different processes, older seeds). Every step keys on
*codes that exist*; a missing old code is skipped, never invented. Numbers are 0086–0088: the
tenant-kernel worktree claimed 0083–0085 on 2026-09-01 and they are applied on INT.

**`0086_permission_cleanup_and_rank.sql`**
1. `DELETE dbo.AccessProfilePermission WHERE Effect='D'`.
2. Drop `CK_AccessProfilePermission_Effect`, drop column `Effect`.
3. Add `AccessProfile.Rank` with default 0; `UPDATE` ranks by name (table above; unknown names keep 0
   and are listed by the doctor check).
4. Delete orphan codes and their `AccessProfilePermission` / `UserPermissionOverride` rows:
   `invoices.%`, `kundenmagazin.%`, `admin.interact.users.all`,
   `admin.view.mobscn.processmanagement`, `admin.assign.user.accessprofile.%`.
5. `CREATE OR ALTER` `fnUserHasPermission` and `spGetUserPermissions` as above.

**`0087_process_scope.sql`**
1. For every code matching `workitems.filter.process.%`, `dashboard.filter.process.%`,
   `reporting.scope.process.%`: derive `<client>.<name>` (the suffix after the prefix), insert
   `process.<client>.<name>.view` with description `Process <client>.<name>: workitems, dashboard
   and reports` where not exists.
2. Profile grants: for each new code, insert one `AccessProfilePermission` row per profile holding
   *any* of the three old codes. User overrides: `D` if any old override is `D`, else `A`.
3. Delete the old family codes and their grant rows.

**`0088_permission_rename.sql`**
1. A `#map(OldCode, NewCode, NewDescription)` temp table from Appendix A.
2. `UPDATE dbo.Permission SET Code=m.NewCode, Description=m.NewDescription` by join on `OldCode`
   (grants ride along on `PermissionID`). Guard: fail loudly if any `NewCode` already exists with a
   different `PermissionID` (a re-run is a no-op because the `OldCode`s are gone).
3. Insert `admin.permissions.edit` where not exists; grant it to every profile that holds
   `admin.profiles.edit` after step 2.
4. `UPDATE dbo.ReportingSources SET Permission=m.NewCode` by join.
5. Rewrite every remaining description from Appendix A (codes whose code did not change still get
   the new description).

**Deploy (D6).** `deploy.yml` applies migrations *before* stopping the app pool; the old build
then checks old codes against renamed rows for the minutes until the new build serves. Users
see 403s in that window. Accepted; deploy off-hours. Nothing to sync in `env/`.

## Code changes

### Sweep (one-off)
`scripts/rename_permissions.py` holds the Appendix A mapping, rewrites string literals in
`nx_lib/`, `templates/`, `tests/`, `sql/test/seed.sql`, `docs/`, prints a diff summary, and is
**deleted in the same commit** once run. The mapping stays in migration `0088` and Appendix A.

### Runtime
- `nx_lib/security.py`: `has_permission` / `require_permission` unchanged. New helper
  `group_permissions(rows) -> tree` (area → object → codes) shared by the grid and user detail;
  `page_visibility()` values renamed, keys unchanged.
- `nx_lib/process_helpers.py`, `views/workitems.py`, `views/dashboard.py`, `views/reporting.py`,
  `reporting/runner.py`, `reporting/ai*.py`: one prefix `process.` and one suffix `.view` instead
  of three prefixes; `_selected_pairs` parses `process.<client>.<name>.view`.
- `views/admin/processes.py`: auto-provision `process.<client>.<name>.view`. White-label doc
  wording follows.
- `views/admin/users.py`, `views/admin/permissions.py`: replace the `admin.assign.*` checks with
  the rank rule (one query for the actor's rank at check time); `assignable_profiles` = profiles
  with `Rank <= actor rank`.
- `views/generali/_crud.py` + descriptors: `view_perm` field removed — it is always
  `f"{perm_prefix}.view"` once attendance is `tenant.generali.attendance.*`. Scope suffixes
  `.org` / `.all` / `.pastdeadline`.
- `reporting/sources.py`, `whats_new.py`: literal codes renamed by the sweep.
- Catalogue APIs (`/api/admin/permissions/add|edit/<id>|delete/<id>`) re-gated to
  `admin.permissions.edit`.

### Admin UI
**New page `/admin/permissions`** (perm `admin.profiles.view`; replaces `/admin/permission_matrix`,
whose route, template and nav entry are deleted):
- Rows: permissions grouped area → object, collapsible, monospace code + description; children
  greyed while the governing `.view` is unchecked in that column.
- Columns: profiles ordered by rank desc, header shows name, rank, user count; sticky.
- Cells: one checkbox. Dirty cells are highlighted; the footer shows "N changes" + Save.
- Filter box narrows rows by code or description.
- Row click opens a side panel "who holds this" (existing holders API) and, for
  `admin.permissions.edit` holders, an inline description editor.
- Save: `POST /api/admin/profiles/grants` with `{changes:[{accessId, permissionId, granted}]}`;
  gated by `admin.profiles.edit`; inserts/deletes rows, invalidates the user cache
  (`_invalidate_user_cache`), returns the applied count.
- Data reaches the page as Jinja-rendered JSON in a `<script nonce>` shim; behaviour lives in
  `static/js/admin_permissions.js` (#191 pattern: `NX.api`, `API_PREFIX`).

**`/admin/access_control`** keeps the Users and Profiles tabs. The Profiles tab cards gain a
rank badge; the card edit is a small modal for name, description, rank (`/api/admin/access_profile/save`
shrinks to those three fields). The 144-row drawer, its JS gating logic and the Permissions tab
are deleted.

**`/admin/users/<id>`** keeps overrides as the only three-state control (inherit / allow /
deny), rendered with `group_permissions`. Effective-permission API unchanged.

### Tests
- `tests/unit/test_permission_codes.py`: grammar regex over referenced literals, `seed.sql`, and
  migration `0088` (Appendix A mapping is the fixture).
- `tests/integration/test_admin_routes.py`: grant/revoke via the grid API; rank rule 403 on user
  add/edit when `target.Rank > actor.Rank`; catalogue edit needs `admin.permissions.edit`.
- Existing permission-guard, workitems, dashboard, reporting, Generali tests: codes swept; the
  process-scope tests assert the single family.
- `sql/test/seed.sql`: new catalogue, `Rank` column, no `Effect` on profile rows.
- e2e (CI-only): one smoke on `/admin/permissions` — toggle a cell, save, reload, state persists.
- `nx --doctor`: new check "referenced permission codes missing in DB" and "profiles with Rank 0".

### Docs
- New `docs/design/permissions.md`: grammar, resolution order, dynamic families, rank rule,
  add-a-code idiom (`WHERE NOT EXISTS`, granted to nobody), the grid page. Pointer added to
  `CLAUDE.md` and `docs/design/architecture-conventions.md`.
- `docs/howto/white-label.md`: process code shape and the D7 idiom wording.
- `docs/howto/reporting.md` (+ `reporting-guide.md` / `_reporting_help.html` only if a user-facing
  gate name appears there): `reporting.*` renames.
- `docs/superpowers/specs/*tenant*`: note that `tenant.generali.*` already exists.
- `CHANGELOG.md` `[Unreleased]`: Changed (rename, grid), Removed (deny at profile level, assign
  codes, matrix page, orphans), Added (rank, process scope, `admin.permissions.edit`).
- What's New: one card for admins, gated by `admin.profiles.view`.

## Phases (one branch, four commits)

| # | commit | contents | verification |
|---|---|---|---|
| 1 | `refactor(permissions): drop profile-level deny, add profile rank` | 0086, fn/proc rewrite, rank checks replace assign codes, orphans deleted, seed updated | targeted integration tests, `db-migrate --dry-run` |
| 2 | `refactor(permissions): one process scope code per (client, process)` | 0087, helpers, process auto-provisioning, tests | workitems/dashboard/reporting scope tests |
| 3 | `refactor(permissions): rename catalogue to <area>.<object>.<action>` | 0088, sweep (script run then deleted), seed, convention test, docs, changelog | full unit + integration suite |
| 4 | `feat(admin): permissions grid replaces drawer and matrix` | page, API, JS, access-control slimming, user detail grouping, e2e smoke, What's New card | Playwright screenshots sent to Ben |

Each phase leaves INT migrated and the suite green. Hand-off between phases via
`/handoff-session-state` if a session ends.

## Risks

| risk | mitigation |
|---|---|
| PROD catalogue differs from INT | all three migrations are data-driven; unknown codes are skipped; doctor check lists strays |
| a literal escapes the sweep | convention test + guard tests; `grep -rn "\.filter\.process\|\.scope\.process\|generali\." nx_lib templates tests` must be empty after phase 3 |
| deploy blip (D6) | off-hours deploy; window equals deploy duration |
| stale 30 s permission cache after save | grid save calls `_invalidate_user_cache`, as the drawer did |
| Generali descriptor change | `test_generali_scope.py` and the Generali route tests cover `.org` / `.all` |

## Appendix A — code mapping (144 → 112)

`DELETE` = code and its grant rows are removed. `= ` = code unchanged (description still rewritten).

### admin (36 → 25)

| old | new | description |
|---|---|---|
| admin.view | = | View the admin area |
| admin.view.users | admin.users.view | View users |
| admin.create.user | admin.users.add | Add users |
| admin.edit.user | admin.users.edit | Edit users |
| admin.delete.user | admin.users.delete | Delete users |
| admin.edit.user.override | admin.users.overrides.edit | Edit per-user permission overrides |
| admin.view.accessprofiles.useroverrides | admin.profiles.view | View access profiles and the permissions grid |
| admin.edit.accessprofile | admin.profiles.edit | Edit access profiles and their grants |
| *(new)* | admin.permissions.edit | Edit the permission catalogue (descriptions, add, delete) |
| admin.assign.user.accessprofile.* (10) | DELETE | replaced by `AccessProfile.Rank` |
| admin.view.organizations | admin.organizations.view | View organizations |
| admin.add.organization | admin.organizations.add | Add organizations |
| admin.edit.organization | admin.organizations.edit | Edit organizations |
| admin.delete.organization | admin.organizations.delete | Delete organizations |
| admin.edit.organization.branding | admin.organizations.branding.edit | Edit organization branding |
| admin.view.clients | admin.clients.view | View the client registry |
| admin.edit.clients | admin.clients.edit | Edit the client registry |
| admin.view.processes | admin.processes.view | View process source mappings |
| admin.edit.processes | admin.processes.edit | Edit process source mappings (high trust) |
| admin.view.active.sessions | admin.sessions.view | View active sessions |
| admin.view.system.logs | admin.logs.view | View system logs |
| admin.status.view | = | View the system status page |
| admin.maintenance.view | = | View the maintenance page |
| admin.maintenance.edit | = | Edit and release maintenance periods |
| admin.maintenance.bypass | = | Bypass the maintenance lockout |
| admin.restart | admin.server.restart | Restart the local dev server (dev only) |
| admin.interact.users.all | DELETE | orphan |
| admin.view.mobscn.processmanagement | DELETE | orphan |

### workitems (22 → 16)

| old | new | description |
|---|---|---|
| workitems.view | = | View the workitems page |
| workitems.details.view | = | View workitem details |
| workitems.details.view.audit | workitems.details.audit.view | View the workitem audit trail |
| workitems.details.view.fields | workitems.details.fields.view | View extracted fields |
| workitems.details.view.images | workitems.details.images.view | View document images |
| workitems.details.view.confidence | workitems.details.confidence.view | View extraction confidence scores |
| workitems.details.view.source_location | workitems.details.sources.view | View where values were found on the page (needs images.view) |
| workitems.filter.datetime | workitems.filter.date.view | Filter by date |
| workitems.filter.status | workitems.filter.status.view | Filter by status |
| workitems.filter.status.deleted | workitems.filter.deleted.view | Filter for deleted workitems (internal; needs status.view) |
| workitems.filter.stage | workitems.filter.stage.view | Filter by process stage |
| workitems.filter.workitemid | workitems.filter.id.view | Search by workitem id |
| workitems.filter.documentfields | workitems.filter.docfields.view | Filter by document fields |
| workitems.filter.documentfields.sensitive | workitems.filter.docfields.sensitive.view | Filter by sensitive document fields (needs docfields.view) |
| workitems.filter.process.* (6) | → process.* | see process |
| workitems.import.workitem | workitems.import.run | Import a workitem |
| workitems.import.preparedaudit | workitems.prepared.view | View the prepared-documents import and audit page |

### dashboard (7 → 1)

| old | new | description |
|---|---|---|
| dashboard.view | = | View the dashboard |
| dashboard.filter.process.* (6) | → process.* | see process |

### reporting (19 → 14)

| old | new | description |
|---|---|---|
| reporting.view | = | View the reporting page |
| reporting.export | = | Export reports to Excel |
| reporting.schedule | = | Schedule reports for email delivery |
| reporting.sql.run | = | Run live read-only SQL in the sandbox |
| reporting.sql.target.octopus | reporting.sql.target.octopus.use | Target the Octo runtime DB in the sandbox |
| reporting.ai.use | = | Use the AI assistant |
| reporting.ai.sql | reporting.ai.sql.use | Receive AI-drafted SQL (needs sql.run) |
| reporting.ai.explain_data | reporting.ai.explain.use | Let the AI run queries and explain results (data egress; needs sql.run) |
| reporting.admin.sources | reporting.sources.manage | Manage the data-source registry |
| reporting.sources.schema | reporting.sources.schema.view | Browse tables and columns of a source |
| reporting.semantic.admin | reporting.metrics.manage | Manage the canonical metrics registry |
| reporting.source.docprocessing | reporting.source.docprocessing.use | Use the Document Processing source |
| reporting.source.workitems | reporting.source.workitems.use | Use the Workitems (Octo) source |
| reporting.source.generali.pdqm | reporting.source.generali_pdqm.use | Use the Generali PDQM source |
| reporting.scope.process.* (5) | → process.* | see process |

### process (0 → 6, data-driven)

| old (three families) | new | description |
|---|---|---|
| {workitems.filter,dashboard.filter,reporting.scope}.process.compass.01_Invoice_SAP | process.compass.01_Invoice_SAP.view | Process compass.01_Invoice_SAP: workitems, dashboard and reports |
| … elektromaterial.02_Invoice | process.elektromaterial.02_Invoice.view | Process elektromaterial.02_Invoice: … |
| … privera.02_InitialScan | process.privera.02_InitialScan.view | … |
| … privera.02_Posteingang | process.privera.02_Posteingang.view | … |
| … privera.03_Invoice_New | process.privera.03_Invoice_New.view | … |
| … sydoc.05_PDBS (no reporting twin today) | process.sydoc.05_PDBS.view | … |

### tenant (48 → 48)

| old | new | description |
|---|---|---|
| generali.dashboard.view | tenant.generali.view | View the Generali dashboard |
| generali.documentlist.view | tenant.generali.documents.view | View the Generali document list |
| generali.importstatus.view | tenant.generali.importstatus.view | View the Generali import status |
| generali.additionalservices.view | tenant.generali.attendance.view | View the attendance page (Zusätzliche Leistungen) |
| generali.attendance.add | tenant.generali.attendance.add | Add own attendance records |
| generali.attendance.add.organizational | tenant.generali.attendance.add.org | Add attendance records for the own organization |
| generali.attendance.add.transorganizational | tenant.generali.attendance.add.all | Add attendance records for every organization |
| generali.attendance.add.bypass.deadline | tenant.generali.attendance.add.pastdeadline | Add attendance records past the deadline |
| generali.attendance.edit.organizational | tenant.generali.attendance.edit.org | Edit attendance records of the own organization |
| generali.attendance.edit.transorganizational | tenant.generali.attendance.edit.all | Edit attendance records of every organization |
| generali.attendance.delete.organizational | tenant.generali.attendance.delete.org | Delete attendance records of the own organization |
| generali.attendance.delete.transorganizational | tenant.generali.attendance.delete.all | Delete attendance records of every organization |
| generali.baseservices.{view,add,add.organizational,add.transorganizational,add.bypass.deadline,edit.organizational,edit.transorganizational,delete.organizational,delete.transorganizational} | tenant.generali.baseservices.{view,add,add.org,add.all,add.pastdeadline,edit.org,edit.all,delete.org,delete.all} | same pattern, "base service records" |
| generali.pdqm.{…same nine…} | tenant.generali.pdqm.{…} | same pattern, "PDQM records" |
| generali.projectmanagement.{…same nine…} | tenant.generali.projectmanagement.{…} | same pattern, "project management records" |
| generali.reporting.{view,add,add.bypass.deadline,edit.organizational,edit.transorganizational,delete.organizational,delete.transorganizational} | tenant.generali.reporting.{view,add,add.pastdeadline,edit.org,edit.all,delete.org,delete.all} | same pattern, "reporting records" (no org/all on add today) |
| tenant.ms02.view | = | View the MS02 pilot tenant pages |
| tenant.ms02.edit | = | Edit the MS02 pilot tenant data |

### api, jd (2 → 2)

| old | new | description |
|---|---|---|
| api.docs.view | = | View the in-app API documentation |
| jd.view | = | View the JD page |

### deleted (22)

`invoices.view`, `invoices.view.compass`, `invoices.view.elektromaterial`, `invoices.view.privera`,
`invoices.download`, `invoices.filter.date`, `invoices.filter.invoiceid`, `invoices.filter.status`,
`kundenmagazin.manage`, `kundenmagazin.manage.all`, `admin.interact.users.all`,
`admin.view.mobscn.processmanagement`, `admin.assign.user.accessprofile.{compassuser,
elektromaterialuser, enterpriseadmin, globaladmin, isssupervisor, issuser, nexorasupervisor,
nexorauser, pdbsuser, priverauser}`.

Totals: 144 − 22 deleted − 17 process codes + 6 process codes + 1 new = **112**.
