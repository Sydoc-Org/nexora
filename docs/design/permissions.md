# Permissions — grammar, rank, dynamic families

How a permission code is shaped, how a user ends up holding one, and where the codes live.
The 2026-09 rename that produced this shape (issue #238) is specified in
`docs/superpowers/specs/2026-09-01-permission-structure-design.md`; its Appendix A holds the full
old → new mapping, and migration `0088` applied it.

## Grammar

```
<area>[.<object>[.<sub>]].<action>[.<scope>]
```

- Lowercase, dot-separated. Underscores and capitals appear **only** inside external identifiers
  (process names such as `03_Invoice_New`, reporting source codes such as `generali_pdqm`).
- `<action>` is one of `view add edit delete use run export schedule manage bypass import restart`.
- `<scope>` is optional: `org` (records of the actor's organization), `all` (every organization),
  `pastdeadline` (the deadline modifier on `add`). No scope means own records.
- Areas: `admin workitems dashboard reporting process tenant api jd`. `tenant.<code>` and
  `process.<client>` are two-segment areas.
- `<area>.view` alone is the area's landing page and gates everything beneath it. The admin grid
  greys the children of an area (or of an `<object>.view`) until that `.view` is granted. This is a
  UI convention only: the server checks each code on its own.

The regex is `PERMISSION_CODE_RE` in `nx_lib/security.py`:

```
^[a-z]+(\.[a-z]+)?(\.[A-Za-z0-9_]+)*\.(view|add|edit|delete|use|run|export|schedule|manage|bypass|import|restart)(\.(org|all|pastdeadline))?$
```

## Resolution order

`dbo.fnUserHasPermission(@UserID, @PermCode)` and `dbo.spGetUserPermissions(@UserID)` agree on one
rule, evaluated in this order:

1. a user override with `Effect = 'D'` → denied;
2. a user override with `Effect = 'A'` → granted;
3. a row in `dbo.AccessProfilePermission` for the user's profile → granted;
4. otherwise denied.

Profile grants are **allow-only rows** since migration `0086`: a row means granted, no row means
nothing. `dbo.UserPermissionOverride` is the only place a deny exists.

## Rank

`dbo.AccessProfile.Rank` (migration `0086`) decides which profiles an admin may hand out:

> an actor may assign profile *P* to a user iff `P.Rank <= actor.profile.Rank`.

| profile | rank |
|---|---|
| Enterprise Admin | 100 |
| Global Admin | 90 |
| Sydoc Supervisor, ISS Supervisor | 50 |
| every other profile | 10 |

`assignable_profile_ids()` in `nx_lib/security.py` implements it; the user add/edit routes and the
Access Control page consult it. A user without a profile may assign nothing. A newly created
profile inherits its creator's rank. Rank governs profile assignment only; editing a user of higher
rank stays governed by `admin.users.edit`. The ten `admin.assign.user.accessprofile.*` codes this
replaced are gone.

**Enterprise Admin holds every permission.** Migration `0106` grants the profile every code and adds
the trigger `dbo.trPermission_GrantEnterpriseAdmin` on `dbo.Permission`, so a code added later, by
migration or from the admin grid, is granted to it in the same statement.

## Dynamic families

Codes the app mints at runtime rather than a migration:

| family | shape | minted by |
|---|---|---|
| process scope | `process.<client>.<name>.view` | `/admin/processes` on saving a `(ClientCode, ProcessName)` row, granted to nobody |
| reporting source | `reporting.source.<code>.use` | the `Permission` column of `dbo.ReportingSources` |
| tenant | `tenant.<code>.view`, `tenant.<code>.edit`, `tenant.<code>.<object>.<action>[.<scope>]` | the tenant kernel when a tenant is created |

One `process.<client>.<name>.view` code per process replaced the three older per-process families
(`workitems.filter.process.*`, `dashboard.filter.process.*`, `reporting.scope.process.*`).
`process_grants()` / `granted_processes()` in `nx_lib/process_helpers.py` read them; every
process allow-list (dashboard, workitems, reporting view and runner) goes through those helpers.

## Adding a code

1. New migration under `sql/_migrations/NexoraDB/`, inserting with `WHERE NOT EXISTS` and a
   description in the imperative ("Edit users", "Add attendance records for the whole organization").
   The code is granted to nobody; Enterprise Admin picks it up through the trigger.
2. Add the same row to `sql/test/seed.sql` so the test tier sees it.
3. Guard the route with `@require_permission("<code>")`; the convention test rejects a literal that
   does not match the grammar.
4. Grant it to profiles at `/admin/permissions`.

## Where codes are stored

- `dbo.Permission` — the catalogue (code, description).
- `dbo.AccessProfilePermission` — profile grants; `dbo.UserPermissionOverride` — per-user allow/deny.
- `dbo.ReportingSources.Permission` — the per-source `reporting.source.<code>.use` string.
- `nx_lib/whats_new.py` — each card's `perm` decides who sees it.
- `sql/test/seed.sql` — the test catalogue and the three test profiles.

## The grid

`/admin/permissions` (`admin.profiles.view`) shows every permission, grouped area → object by
`group_permissions()` in `nx_lib/security.py`, against every profile, one checkbox per cell. Ticked
cells are rows in `dbo.AccessProfilePermission`. Saving posts only the changed cells to
`POST /api/admin/profiles/grants` (`admin.profiles.edit`), which inserts or deletes rows, clears the
user permission cache (the `/api/admin/*` prefix is outside the hook that clears it on `/admin`
writes) and reloads the caller's own session permissions. Clicking a permission's name lists who
holds it. Catalogue actions (add, rename, delete a code) sit on the same page behind
`admin.permissions.edit`. This page replaced the per-profile permission drawer on Access Control and
the read-only Permission Matrix.

A badge on a cell (#275) counts `dbo.UserPermissionOverride` rows for users of that profile on that
permission — e.g. a user overriding a permission their profile doesn't grant. The "Columns" picker
shows/hides and reorders profile columns; both choices are per-viewer (`localStorage`, key
`nx.permsGrid.columns`), not server-side prefs — there's nothing here worth a `dbo.Users.ui_prefs` key.

## User overrides

`/admin/users/<id>` renders the override table from the same `group_permissions()` tree, so the
grouping reads exactly as the grid does (`tenant.generali › attendance`). Each row is a
none / deny / allow radio saved to `dbo.UserPermissionOverride`.

## Tests

- `tests/unit/test_permission_codes.py` — every literal passed to `require_permission` /
  `has_permission` in `nx_lib/` and `templates/`, every code in `sql/test/seed.sql` and every code in
  migration `0088` matches the grammar.
- `nx --doctor` — the Permissions section warns about referenced codes missing in `dbo.Permission`
  (dynamic families excluded) and about profiles left at Rank 0.
