# White-label admin onboarding (issue #98 phase 4)

Self-service admin surface for onboarding a customer without a SQL migration or a deploy, for the
common case. Covers what shipped in **phase A/B**: the `dbo.Clients` runtime-source registry and the
`/admin/clients` + `/admin/processes` admin pages. Branding (phase C) is a separate, not-yet-shipped
piece — see the note at the bottom.

Design background: `docs/superpowers/specs/2026-08-27-white-label-admin-ui-design.md`.

## The two axes

Two different things are both informally called "the client", and conflating them is the easiest way
to get this wrong.

**Axis 1 — `ClientCode` (runtime source).** Answers *"which runtime DB, which SQL dialect, which
Octo tenant?"*. Values today: `default`, `ms02`. Infrastructure-level, changes almost never. Lives in
`dbo.Clients` (migration `0079`) and is read into `nx_lib/clients.py::CLIENTS` at app start. It is
also the `ClientCode` column on `dbo.ProcessSources`, `dbo.ProcessFieldMappings` and
`dbo.WorkitemSourceCache`.

**Axis 2 — `Organizations.organizationcode` (the customer).** Answers *"who does this user work
for?"* — `PRVR`, `LKTR`, … Self-service today at `/admin/organizations`.

**Most customers ride the shared `default` runtime.** Privera, ElektroMaterial and Compass all do.
A customer needs a new `ClientCode` only when they bring their own database — so far that has
happened exactly once, for MS02. This is exactly why onboarding a `default`-riding customer needs
zero env edits and zero deploys: only step 3 of the walkthrough below (a process source) touches the
DB at all, and it does so through the admin UI, not a migration.

## `/admin/clients` — runtime sources

Permissions: `admin.view.clients` (read), `admin.edit.clients` (add/edit/delete). Both are granted to
`enterpriseAdmin` and `globalAdmin` by migration `0080`.

The table lists five columns per `dbo.Clients` row — `ClientCode`, `DisplayName`, `Dialect`
(`tsql` | `postgres`), `RuntimeEngineKey` and `IsActive`. The add/edit modal covers all ten writable
columns: those five plus `StatsEngineKey`, `StatsDialect`, `DocfieldsEngineKey`, `DocfieldsDialect`,
`OctoDomain` and `SecretRef`. (`ClientCode` is the primary key and is read-only when editing —
changing it would strand every `dbo.ProcessSources` row pointing at the old code.) The engine keys
name engines defined in `nx_lib/db.py`, e.g. `engine_octo_db`, `engine_ms02_pg`; the four
stats/doc-field columns are nullable and empty means `NULL`.

The edit form deliberately carries every writable column, including the four nullable ones the table
doesn't show: the UPDATE writes all ten, so a form that omitted them would silently NULL a client's
stats and doc-field engine bindings on any save — MS02 statistics would break and doc-field search
would fail closed after the next app-pool recycle.

Add/edit validates server-side (never trust the page's own JS checks): `ClientCode` must match
`^[a-z0-9_]{2,50}$`, `DisplayName` is required, dialect fields must be `tsql` or `postgres`, engine
keys must name an engine that actually exists, and `SecretRef` must look like an env-key prefix
(`^[A-Z0-9_]{0,20}$`) — **never** a secret value itself (see Secrets, below).

Delete is refused with **409** while any `dbo.ProcessSources` row still references the `ClientCode` —
deleting it out from under the mapping-config registry (`nx_lib/mapping_config.py`) or the running
`CLIENTS` registry would break every workitem view for that client.

**A new or edited client row needs an app-pool recycle.** `CLIENTS` is built once at import
(`nx_lib/clients.py::_build_clients()`), not re-read per request. Saving a row in the admin UI updates
`dbo.Clients` immediately; the running app keeps using its in-memory registry until the pool recycles.
A `dbo.Clients` row whose engine or Octo domain is missing/unresolvable is silently skipped when the
registry is built (same degrade-gracefully contract the hardcoded dict had), and a DB error at boot
degrades the whole registry to `default`-only.

## `/admin/processes` — process sources and field mappings

Permissions: `admin.view.processes` (read), `admin.edit.processes` (add/edit/delete). Both granted to
`enterpriseAdmin` and `globalAdmin` by migration `0080`.

Reads and writes `dbo.ProcessSources` and `dbo.ProcessFieldMappings` (migration `0074`) entirely
through the cached registry in `nx_lib/mapping_config.py` — never raw SQL for reads. The page groups
by `ClientCode` (the runtime source, not the customer), then by process name, with each process's
field mappings nested underneath.

If the registry fails to load, the page renders an explicit "mapping config unavailable" state rather
than an empty-looking success, and the JSON mirror (`/api/admin/processes/list`) returns **503**.

**Writable columns** for a process source: `TableName`, `TableAlias`, `ExportColumn`,
`ImportColumn`, `WorkitemColumn`, `IdColumnType`. For a field mapping: `ColumnName`, `ColumnType`.
Every write is followed by `invalidate_mapping_config()` so the 60-second cache doesn't leave an
admin staring at a stale page wondering if the save worked.

Every identifier that gets interpolated into SQL elsewhere (`ClientCode`, `ProcessName`, `FieldKey`,
`TableName`, `TableAlias`, column names) is validated server-side against a strict identifier
pattern before it is written. Column types (`ColumnType`, `IdColumnType`) are checked against a
deliberately looser pattern (`_COLUMN_TYPE_RE` in `nx_lib/views/admin.py`) that also permits spaces —
they are never interpolated into SQL, only compared against literal type buckets such as
`character varying`.

**Adding a process source auto-provisions its permission.** Saving a new `(ClientCode, ProcessName)`
row also creates a `workitems.filter.process.<ProcessName>` permission row in the same request, in
one transaction — otherwise step 3 of the onboarding table below would still require a migration and
the whole point of this page would be lost. The permission is created **granted to nobody**: granting
it to a user or access profile stays a deliberate, separate step at `/admin/access-control`. Deleting
a process source does **not** delete its permission row — that would silently revoke access nobody
asked to change; re-adding the same process later reuses the existing permission (the insert is
idempotent, mirroring migration `0059`'s shape).

Deleting a process source is refused with **409** while it still has field mappings — remove those
first.

### Scope limits — deliberately not editable here

- **`JoinCondition`, `TimeFilter`, `SuggestionTimeFilter` and `ExtraCondition`** on `ProcessSources`
  are free-form SQL fragments. They stay **migration-only**, on purpose — exposing free-form SQL
  fragments to an admin-UI text box is not a validation problem you can solve with a regex. They
  render read-only everywhere in `/admin/processes`, for every permission level.
- **`FieldLabels` and `FieldAliases`** are read-only in the admin UI for now. There is no write path
  for them yet.

## End-to-end onboarding walkthrough

For the common case — a new customer riding the shared `default` runtime, no new database:

1. **Create the organization** at `/admin/organizations` (already existed before this phase) — this
   is the customer, e.g. `organizationcode = ACME`.
2. **Skip `/admin/clients`** — `default` already exists and this customer uses it. Only create a new
   client row here if the customer is bringing its own database (see below).
3. **Add a process source** at `/admin/processes` — `ClientCode = default`, `ProcessName` (by
   convention prefixed with the customer, e.g. `acme.01_Invoice`), and its table/column mapping. This
   step auto-creates the `workitems.filter.process.acme.01_Invoice` permission, granted to nobody.
4. **Add field mappings** for that process source on the same page, one row per doc-field.
5. **Grant the permission** at `/admin/access-control` — attach
   `workitems.filter.process.acme.01_Invoice` to the users or access profiles who should see that
   customer's workitems. Nothing is visible to anyone until this step happens.

No SQL migration, no deploy, no app-pool recycle for this path — the whole thing is admin-UI writes
plus a 60-second cache invalidation.

### Onboarding a customer that brings its own database

Only needed the rare time a customer can't share the `default` runtime (so far: MS02).

1. Add the DB connection to `env/{ENV}.env` on the target machine by hand — **secrets are never
   stored in `dbo.Clients`** (see Secrets, below). `scripts/env-sync.py` diffs the committed
   `env/PROD.env.example` against the local and SYAPP01 copies and prints copy-pasteable lines for
   anything missing; run it after adding new keys.
2. Create the client row at `/admin/clients` — `ClientCode`, `DisplayName`, `Dialect`, the engine
   keys pointing at engines already wired in `nx_lib/db.py`, `OctoDomain`, and `SecretRef` set to the
   env-key prefix (e.g. `MS02`) used in step 1.
3. **Recycle the app pool.** `CLIENTS` is built once at import; the new row is invisible to the
   running app until it restarts.
4. Continue with the walkthrough above, using the new `ClientCode` in place of `default` when adding
   process sources.

## Secrets

`dbo.Clients.SecretRef` holds only an **env-key prefix** (e.g. `MS02`), never a secret value itself.
At boot, `nx_lib/clients.py` reads that prefix's `*_OCTO_CLIENT_SECRET` / `*_DB_PASSWORD` keys (or the
unprefixed `OCTO_*` keys when `SecretRef` is `NULL`, i.e. the `default` client) from
`env/{ENV}.env` — exactly as before this phase. This keeps secrets out of `dbo.Clients` and out of
DB backups. The admin-UI validation on `SecretRef` (`^[A-Z0-9_]{0,20}$`) is a shape check, not a
secret-detector — it rejects anything that doesn't look like a prefix (lower-case, spaces,
punctuation), but is not a guarantee that a pasted secret can never sneak into the field.

## Not shipped yet: branding

Per-organization branding (logo, wordmark, accent color) is **phase C** of this effort and has not
landed as of this writing. This document will grow a branding section when it does.
