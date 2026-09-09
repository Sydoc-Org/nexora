# White-label admin onboarding (issue #98 phase 4)

Self-service admin surface for onboarding a customer without a SQL migration or a deploy, for the
common case. Covers **phase A/B** — the `dbo.Clients` runtime-source registry and the
`/admin/clients` + `/admin/processes` admin pages — and **phase C**, per-organization branding (see
the branding section at the bottom).

Design background: `docs/superpowers/specs/2026-08-27-white-label-admin-ui-design.md`.

## The three axes

Three different things get informally called "the client", and conflating them is the easiest way
to get this wrong.

**Axis 1 — `ClientCode` (runtime source).** Answers *"which runtime DB, which SQL dialect, which
Octo tenant?"*. Values today: `default`, `ms02`, `generali`. Infrastructure-level, changes almost
never. Lives in `dbo.Clients` (migration `0079`) and is read into `nx_lib/clients.py::CLIENTS` at
app start. It is also the `ClientCode` column on `dbo.ProcessSources`, `dbo.ProcessFieldMappings`,
`dbo.WorkitemSourceCache` and, since `0096`, `dbo.TenantEntities` — a generated entity's table
lives in exactly one database, so the entity names it.

**Axis 2 — `Organizations.organizationcode` (the customer).** Answers *"who does this user work
for?"* — `PRVR`, `LKTR`, … Self-service today at `/admin/organizations`.

**Axis 3 — `Tenants.TenantCode` (the portal).** Answers *"which organizations share one branded
navigation, and which pages does it show?"*. A tenant is **not** a data connection: since migration
`0096` a `dbo.Tenants` row is just `TenantCode`, `DisplayName`, `IsActive`, and the organizations
whose `Organizations.TenantCode` points at it are its members. Its `TenantEntities`/`TenantFields`/
`TenantPages` children describe the generated `/t/<code>/<page>` surface, and each entity names the
axis-1 connection its table lives in (`TenantEntities.ClientCode`) — so one tenant may span
connections and one connection may serve several tenants. Three tenants exist on INT: `ms02`
**Mobscn** (PDBS), `generali` (GNRL) and `sydoc` (ElektroMaterial, Privera, Compass). Tenants, their
members and their custom pages are edited at `/admin/tenants/manage`; entities and fields are still
seeded by migration. Full detail: `docs/design/ms02-multisource.md`.

**Who sees a tenant — membership or grant.** A user whose organization belongs to the tenant sees
its sidebar group and its generated pages by right (`nx_lib/views/tenant.py::_can_view`); anyone
else — sydoc staff working Generali, say — needs `tenant.<code>.view`. Editing generated records is
always the explicit `tenant.<code>.edit` grant. A tenant-scoped user (`tenant_scoped`, set in
`nx_lib/hooks.py`) sees only their tenant group in place of the global Dashboard / Reporting /
Workitems links. Since `0104` sydoc AG (SYDC) is a member of the `sydoc` tenant and ISS (SSIX) of
`generali`; sydoc staff keep every tenant group and the Global entries through their
`tenant.<code>.view` grants and page permissions, so only `demo` (DMEO) sits outside a tenant.

**A tenant's own users never see it named.** `tenant_solo` (also from `_inject_tenant_nav`) is true
for a user who belongs to exactly one tenant and holds no grant on another. For them the tenant *is*
the portal, so the UI never spells it out: the sidebar renders the mounted pages flat with no label,
and the pages title themselves "Dashboard" / "Workitems" rather than "`<Tenant>` Dashboard" /
"`<Tenant>` Workitems". Staff and cross-tenant members keep the names — they have several tenants to
tell apart. Adding a name back to a page a solo member can reach is a regression, not a feature.

**Mounted pages and the tenant dashboard.** A `custom` row in `dbo.TenantPages` carries a
`LayoutJSON` with `endpoint` (an argument-less GET route), `label`, `icon`, an optional `active`
marker (the `active_page` value the target sets) and an optional `query` object of string pairs that
becomes the link's query string. `LayoutJSON` carries no permission key: a mounted page needs
`tenant.<code>.view` *and* whatever the target route itself declares (`dashboard.view`,
`workitems.view`, ...), which `_tenant_nav_page` reads off the view function via the
`required_permissions` attribute `require_permission`/`require_any_permission` stamp on it, dropping
the sidebar entry when the user holds none of them (#300) — a mounted page never offers a link that
403s on click. The mounted **Dashboard** and **Workitems** pages use exactly that:
since migrations `0097`/`0098` they link `/dashboard?tenant=<code>` and `/workitems?tenant=<code>`.
`nx_lib/views/tenant.py::apply_tenant_scope` resolves the tenant (404 unknown, 403 not viewable),
stores it in `session['tenant_scope']`, and every process allow-list on both pages — the dashboard
KPIs, the workitems list, field config, suggestions, import — comes through
`nx_lib/process_helpers.py::granted_processes`, which intersects the user's process grants
(`process.<client>.<name>.view` since migration `0087`, or the legacy `*.filter.process.*` codes)
with the processes whose organization belongs to that tenant
(`nx_lib/tenant/registry.py::tenant_processes`; an unresolvable scope narrows to nothing). A user
inside a tenant lands on their tenant's pages by default; staff without a pick get the **Global
Dashboard** / **Global Workitems** (every process they may see, across tenants). The scope is
sticky: a URL without the parameter keeps it (the workitems page rewrites its own URL with the
filter state), the global sidebar entries clear it with an explicit empty `?tenant=`, and a
remembered tenant that no longer resolves is dropped silently. The scoped pages render
`active_page = tenant_<code>_dashboard` /
`tenant_<code>_workitems`, so only that tenant's entry lights up in the sidebar. Prepared Documents
is MS02's own intake register with no process filter, so it is not scoped.

**The admin UI names these by role, not by table (#255).** The routes, `data-testid`s, permission
codes and DB columns keep their original names; only the labels changed, and the three pages now sit
in a collapsible **Tenants** group in the admin sidebar:

| Route | UI label | Axis |
|---|---|---|
| `/admin/tenants/manage` | **Manage** (Tenants) | create/edit tenants, their organizations and mounted pages (`admin.tenants.view` / `admin.tenants.edit`, migration `0095`); entities/fields stay migration-only |
| `/admin/tenants` | **Overview** (Tenants) | read-only join of all three: tenant → organizations → users, access profiles, data connection, process configurations; plus pages; plus what is not in a tenant (#256 phase 1) |
| `/admin/organizations` | **Organizations** (name kept) | 2 — who the users work for |
| `/admin/clients` | **Data Connections** | 1 — where the data lives |
| `/admin/processes` | **Process Configurations** | Octo process sources + their field mappings |

Note the last one is Octo-specific: `dbo.ProcessSources` describes Octo processes, so a **data-only**
tenant (a plain table or view, `TenantEntities.Kind = 'entries'`/`'lookup'`) needs an axis-1 client
row and tenant descriptors but no process source at all.

Worked example, migration `0126`: the MediaMarkt scan protocol. One `entries` entity over
`SYDOC_Statistik.dbo.MediaMarkt_Batches` (`EngineRole = 'stats'` on the `default` client), ten
`TenantFields`, one `crud` page — `/t/sydoc/mediamarkt` exists with no page code. Two field roles
carry behaviour on generated CRUD pages: **`person`** is never typed, `nx_lib/views/tenant.py`
stamps it with the current username on every insert and update (the "Visum" column); **`flag`**
renders as a checkbox and stores `0`/`1`. `date` gives a date picker and the list's date-range
filter, `count`/`money` a numeric input, everything else a text input.

**Since migration `0090` (#257) the organization is the hub that ties the axes together.**
`dbo.Organizations` carries `TenantCode` (axis 3) and is referenced by
`ProcessSources.OrganizationCode` and `AccessProfile.OrganizationCode`. Which axis-1 connections an
organization rides is **derived, never stored**: it is the set of `ClientCode`s on its process
configurations (migration `0096` dropped the `Organizations.ClientCode` copy, together with
`Tenants.ClientCode` and the pre-0090 `Tenants.OrganizationCode` pointer — all three agreed with the
process sources in every row and only waited to drift). A profile bound to an organization is
assignable only to that organization's users (`nx_lib/views/admin/users.py::_profile_org_mismatch`);
a profile with `OrganizationCode = NULL` is global (`Global Admin`, `Enterprise Admin`,
`Sydoc Supervisor`). Profile names follow `<Organization> <Role>` since migration `0105`. `/admin/tenants` renders exactly this tree and flags what is still unassigned.

**Data-only connections.** A `dbo.Clients` row without an Octo domain is a *data-only* connection
(Generali: `generali` → `engine_generali_db`, migration `0091`): it loads into `CLIENTS` with
`octo_domain = None` and serves tenant pages, but `nx_lib/clients.py::workitem_clients()` excludes it
from workitem routing. Only `default` still needs a domain. Adding a new database means one line in
`_engines()` plus a `dbo.Clients` row.

**Most customers ride the shared `default` runtime.** Privera, ElektroMaterial and Compass all do.
A customer needs a new `ClientCode` only when they bring their own database — so far that has
happened exactly once, for MS02. This is exactly why onboarding a `default`-riding customer needs
zero env edits and zero deploys: only step 3 of the walkthrough below (a process source) touches the
DB at all, and it does so through the admin UI, not a migration.

## `/admin/clients` — runtime sources

Permissions: `admin.clients.view` (read), `admin.clients.edit` (add/edit/delete). Both are granted to
`Enterprise Admin` and `Global Admin` by migration `0080`.

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

**Configured is not loaded.** The table on this page is `dbo.Clients` — what is *configured*. The
**Runtime state** column is the resolved truth: whether the running process actually holds that code
in its `CLIENTS` registry. They diverge routinely, because migration `0079`'s seed is unconditional
and PROD therefore gets an `ms02` row whether or not `env/PROD.env` carries the `MS02_*` keys. Without
them `_build_clients()` skips the row and the client is **"Configured, not loaded"** — `Active: Yes`
in the table, serving nothing. Same for an unresolvable engine key or Octo domain, and for any row
after a registry-wide load failure.

**Registry-wide degradation is surfaced, not just logged.** If reading `dbo.Clients` at import fails
outright, `nx_lib/clients.py` records the reason in its module-level `REGISTRY_DEGRADED_REASON` and
the app runs on the hardcoded `default`-only registry for the rest of the process lifetime — every
other runtime source is gone until the next app-pool recycle. The `logger.error` on that path fires
*before* Flask configures logging, so it reaches stderr (`var/logs/system/waitress-stdout*`) but never
`app.log`; the recorded reason is what `/admin/clients` and `/admin/status` render as a red banner.
There is deliberately no retry loop and no TTL — `CLIENTS` being import-time-only is a locked design
decision; this only makes the degradation visible.

## `/admin/processes` — process sources and field mappings

Permissions: `admin.processes.view` (read), `admin.processes.edit` (add/edit/delete). Both granted to
`Enterprise Admin` and `Global Admin` by migration `0080`.

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
deliberately looser pattern (`_COLUMN_TYPE_RE` in `nx_lib/views/admin/processes.py`) that also permits spaces —
they are never interpolated into SQL, only compared against literal type buckets such as
`character varying`.

`ClientCode` is additionally checked against `dbo.Clients` — it must be an existing runtime source,
and the form offers a picker rather than a free-text box. There is no database FK (`ProcessSources`
predates `dbo.Clients`, and migration `0079` deliberately adds none), so this server-side existence
check is the only thing stopping a typo like `defualt` from creating a process source, provisioning
its permission, and yielding config that can never resolve.

### `ProcessName` must be exactly `<customer>.<process>` — a hard rule, not a convention

This used to be described as "customer-prefixed by convention only". That is **wrong**, and the
admin UI made the mistake reachable. The permission auto-provisioned for a process is
`process.<ProcessName>.view`, and every consumer reconstructs the process name out of
that code as **exactly the last two dot-segments** (`nx_lib/views/workitems.py`,
`nx_lib/process_helpers.py`: `parts[-2], parts[-1]`). So the name must be two segments — no more, no
fewer:

| Typed name | Derived back as | Result |
|---|---|---|
| `acme.01_Invoice` | `acme.01_Invoice` | correct |
| `Invoice` | `process.Invoice` | grant never matches — silent, permanent, no error |
| `acme.eu.01_Invoice` | `eu.01_Invoice` | grant never matches — same silent dead end |
| `x.acme.01_Invoice` | `acme.01_Invoice` | **collides** with another customer's grant |

`_PROCESS_NAME_RE` (`nx_lib/views/admin/processes.py`) therefore enforces
`^[A-Za-z0-9_\-]{1,49}\.[A-Za-z0-9_\-]{1,50}$`, matched by the form's `pattern` attribute, and the
add endpoint additionally rejects with **409** any name whose two-segment reduction already belongs
to a different `(ClientCode, ProcessName)` pair — the permission code carries no client, so two
process names that reduce alike share one entitlement. `FieldKey` keeps the looser
`_FIELD_KEY_RE` shape: it never becomes a permission code.

**Adding a process source auto-provisions its permission.** Saving a new `(ClientCode, ProcessName)`
row also creates a `process.<ProcessName>.view` permission row in the same request, in
one transaction — otherwise step 3 of the onboarding table below would still require a migration and
the whole point of this page would be lost. The permission is created **granted to nobody**: granting
it to a user or access profile stays a deliberate, separate step at `/admin/permissions`. Deleting
a process source does **not** delete its permission row — that would silently revoke access nobody
asked to change; re-adding the same process later reuses the existing permission (the insert is
idempotent, mirroring migration `0059`'s shape).

Deleting a process source is refused with **409** while it still has field mappings — remove those
first.

### `admin.processes.edit` is a high-trust permission

Read the identifier validation above as *injection* hardening, not as a security boundary between
customers. It is not one. `admin.processes.edit` lets a holder rewrite `TableName` on an **existing**
process source, and `_IDENT` accepts any qualified identifier in either dialect. A holder can
therefore repoint an already-granted `process.privera.02_Posteingang.view` at a different
customer's statistik table: no new grant is needed, no permission changes, and nothing is audited.
The practical meaning of the permission is **"can point any granted process at any table in the
runtime database"** — which is inherent to an editable config surface, not a defect to be patched.

Grant it accordingly. Migration `0080` hands it to every access profile that already holds
`admin.organizations.view` (`Enterprise Admin`, `Global Admin`); treat adding anyone else to that set
as the cross-tenant data-access decision it is.

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
3. **Add a process source** at `/admin/processes` — `ClientCode = default` (picked from the list of
   existing clients), `ProcessName` in the **required** `<customer>.<process>` shape, e.g.
   `acme.01_Invoice` (see the hard rule above — any other shape is rejected), and its
   table/column mapping. This
   step auto-creates the `process.acme.01_Invoice.view` permission, granted to nobody.
4. **Add field mappings** for that process source on the same page, one row per doc-field.
5. **Grant the permission** at `/admin/permissions` — tick
   `process.acme.01_Invoice.view` to the users or access profiles who should see that
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

## Branding (phase C)

Per-organization white-labelling: a customer sees their own logo, wordmark and accent colour inside
the app, without a deploy and without a per-customer template.

**Branding attaches to the Organization, not to `ClientCode`.** It is a property of the customer
(axis 2), never of the runtime source (axis 1) — the three organizations riding the shared `default`
runtime each get their own brand, and MS02's own `ClientCode` has no branding of its own. The
registry is keyed by `organizationcode` and nothing in the branding path ever looks at `ClientCode`.

### What is brandable

Three things, all stored on `dbo.Organizations` by migration `0081` (nullable — `NULL` everywhere
means "unbranded", which renders exactly today's Nexora markup):

| Column | Effect |
|---|---|
| `BrandName` | the wordmark in the header/sidebar — replaces the literal `nexora` in `templates/nexora_logo/_nexora_logo.html` |
| `BrandAccentHex` | the organization's default accent colour (`#rrggbb`) |
| `BrandLogoFile` | the header/sidebar logo image; filename only, resolved under `var/branding/` |

Everything else — page layout, fonts, the favicon, the product name in page titles — is out of scope
and unchanged.

### The precedence rule — the org accent is a *default*, not an override

This is the part that is easy to get backwards:

1. **The user's own `/appearance` accent wins.** If the user ever picked an accent, that is what they
   see, on every organization.
2. **Otherwise the organization accent applies** — `BrandAccentHex` replaces the built-in `indigo` /
   `#4f46e5` default.
3. **Otherwise the built-in `indigo` / `#4f46e5`.**

Mechanically, in `templates/_header.html`'s pre-paint block: `stored.accentHex || brand.accent_hex
|| '#4f46e5'` (and the matching `stored.accent || (brand.accent_hex ? 'custom' : 'indigo')`). The
org brand only ever fills the slot the user left empty. Deliberately: an org brand must never
silently undo a personal accessibility or preference choice (issue #155's spirit).

**`stored` includes the localStorage mirror.** The pre-paint block merges `localStorage`'s
`nexora-ui-prefs` *under* the DB row (`Object.assign({}, localStorage, db)`) as offline resilience,
so a locally-remembered accent also outranks the org accent. That is the intended reading of rule 1 —
it is still the user's own choice — but it surprises you while testing: clearing
`Users.ui_prefs.accent` alone is not enough to see the org accent in a browser that has visited
`/appearance` before. Clear `nexora-ui-prefs` from localStorage too.

The brand is injected by a context processor in `nx_lib/hooks.py` (`_inject_brand`), read **fresh per
render** through `nx_lib/branding.py` and **never** cached in `flask.session` — same rule as UI prefs
(#155). The staleness budget is the registry's own 60-second TTL, and every admin save calls
`invalidate_branding()`, so an edit shows up on the next page load, not a minute later.

### The registry and its failure contract

`nx_lib/branding.py` is one cached accessor over all five organizations — `registry()`,
`brand_for_org(code)`, `invalidate_branding()`. It mirrors `nx_lib/mapping_config.py`'s contract and
should not be weakened:

- 60-second TTL, **success-only caching** — an empty-but-successful load is a valid, cacheable result;
- a load error returns `None` and is **never** cached, so a transient DB blip does not pin
  "unbranded" for a minute;
- callers degrade to Nexora branding on `None` (`brand_for_org(...) or {}`), never to an error page;
- the TEST database's `Organizations` table predates the brand columns, so pyodbc's "invalid column
  name" (SQLSTATE `42S22`) is caught explicitly and logged at INFO rather than ERROR;
- an accent that is not `^#[0-9a-fA-F]{6}$` is dropped to `None` on read, so a bad row cannot inject
  anything into the pre-paint style block.

### Logos on disk

Uploaded logos live in **`var/branding/<orgcode>.<ext>`** (`PATHS.branding` in `nx_lib/config.py`).
The stored filename is derived from the organization code, never from the uploaded filename.

- **Allowed types: SVG, PNG, JPEG. Cap: 512 KB.** Enforced server-side in
  `nx_lib/views/admin/organizations.py::api_admin_organization_branding_save` — extension check first, then the
  size check, then `nx_lib/files.py::is_file_allowed` (`secure_filename` + a libmagic sniff of the
  actual bytes). The client-declared content type is never consulted, and nothing touches the disk
  until all three checks pass.
- **`var/` survives deploys.** It is in `deploy.yml`'s robocopy `/XD` list, and `/XD` directories are
  never copied *and* never purged by `/MIR` — so uploads made on PROD stay put across deploys. It is
  also already inside `var\`, so no new SYAPP01 Defender exclusion is needed.
- **Serving:** `GET /branding/<orgcode>/logo` (`nx_lib/views/core.py::branding_logo`), the same idiom
  as `/avatar/<user_id>` — any logged-in user may fetch it, no extra permission. `orgcode` never
  touches the filesystem; it is only a dict key into the registry, so a hostile value simply 404s.
  Because SVG is allowed and SVG is script-capable, every response carries
  `Content-Security-Policy: sandbox` and `X-Content-Type-Options: nosniff` (spec D9) — it must never
  be treated as same-origin executable content.
- **The sandbox CSP is set twice, on purpose.** CSP is PROD-only, and PROD's Talisman
  `after_request` assigns `Content-Security-Policy` *unconditionally* — it would silently replace the
  header the view sets, handing the response the global policy whose `script-src` allows jsdelivr /
  cdnjs / tailwindcss. So the view sets the header (the whole story on INT/dev/TEST, where there is
  no Talisman) **and** `branding_logo.talisman_view_options` declares the sandbox policy through
  Talisman's own per-view override, which wins on PROD. `tests/integration/test_admin_routes.py`
  asserts this against a second app with Talisman installed the way `nx_lib/__init__.py` does —
  asserting it in TEST alone passes vacuously.

### Editing a brand

The branding panel on `/admin/organizations` sits behind **`admin.organizations.branding.edit`**
(seeded by migration `0080`, granted to `Enterprise Admin` and `Global Admin`). A viewer holding only
`admin.organizations.view` never sees the panel or its per-row button. `POST
/admin/organizations/<organizationcode>/branding` accepts JSON (name + accent only) or
`multipart/form-data` (plus `logo`); a save without an upload leaves the stored logo untouched.
Every successful save calls `invalidate_branding()`.

### Explicitly *not* branded (decision D2)

**The login page, the error pages and scheduled-report emails stay Nexora-branded.** This is
deliberate, not an oversight:

- **Login and the rest of the pre-session flow** (`index.html`, `verify_2fa.html`,
  `forgot_password.html`, `reset_password.html`, `set_password.html`, `init_2FA.html`,
  `init_reset.html`) — there is no session, therefore no user, therefore no organization. Branding
  the login page would mean guessing the customer from the hostname or the typed username, which is
  a different feature with its own security questions. These pages include
  `templates/nexora_logo/_nexora_logo.html`, and `_inject_brand` yields `{}` for them because it is
  gated on `"userid" in session` — the same gate `branding_logo` uses.

  **That gate is load-bearing, not belt-and-braces.** `logout()` pops `username`, `uuid` and
  `userid` but leaves `organizationcode` in the session, so keying the context processor on
  `organizationcode` alone kept branding the landing page after logout — and the logo `<img>`
  rendered broken, because `branding_logo` 401s without a `userid`. Caught in browser verification
  and fixed by the gate; don't remove it without also clearing `organizationcode` on logout.
- **Error pages** (`templates/handlers/*.html`) — they must render when the DB is down, which is
  exactly when the branding registry returns `None`. A branded error page would be a second thing
  that can fail while something is already failing.
- **Scheduled-report emails** — out of scope for this phase; they render outside a request context
  and would need their own brand-resolution path.

### Known rough edges

Small, known, and left for a later pass rather than discovered by the next person:

- **Changing a logo's file format orphans the old file.** Uploading `PRVR.png` over an existing
  `PRVR.svg` writes the new file and repoints `BrandLogoFile`; the old `PRVR.svg` stays on disk
  forever. It is never served (the serve route reads `BrandLogoFile`, not the directory), so this is
  disk litter, not a leak — and deleting the organization sweeps every `<code>.<ext>` for the four
  allowed extensions, so the litter does not survive the org.
- **There is no "remove logo" button.** A brand name and an accent can be cleared by emptying the
  field; a logo can only be replaced. Clearing one today means a manual `UPDATE` plus
  `invalidate_branding()` (or waiting out the 60-second TTL).
- **The file write is not atomic with the DB commit.** `target.write_bytes(...)` happens before
  `conn.commit()`, so a commit failure leaves the new image on disk with the old filename still in
  the row. Same "never served" consequence as above; worth fixing if this ever grows a delete path.

Deleting an organization (`DELETE /admin/organizations/delete/<code>`) removes its logo files and
calls `invalidate_branding()` — otherwise the dead org keeps its brand, and `/branding/<code>/logo`
keeps serving its image, for up to the registry's 60-second TTL.
