# Tenant platform — design spec (umbrella + kernel)

**Date:** 2026-08-31 · **Status:** approved design, pre-plan · **Owner:** benstreich
**Base:** the 2026-08-31 beautify campaign (generali view package + descriptor CRUD factory,
`docs/superpowers/plans/2026-08-31-beautify-phase-0-1.md` Task 14) — executes **before** this.
**Related:** #98 phase 4 white-label admin UI (shipped — `dbo.Clients`, `/admin/clients`,
`/admin/processes`, org branding), #220 Generali DB restructure
(`docs/superpowers/plans/2026-08-27-generali-db-restructure.md`), `docs/howto/white-label.md`
(two-axes doctrine).

## Purpose

Make **tenant** a first-class Nexora concept: a customer area with its own data, its own generated
pages, its own dashboard and reporting — onboarded through the admin center by describing what the
data means (the "data box"), with Eddard assisting. Generali is the prototype the concept is
modeled on; MS02 is rebuilt as the pilot; Geschäft-client onboarding converges onto the same
concept later.

**The baseline tenant is data-only.** Most tenants will not have an Octo runtime or workitems at
all — their substance is input/output-management data (scanned documents, deliveries, effort
entries), like Generali today. Octo/workitems integration is an *optional attachment* a tenant may
have (MS02 does), never a requirement of the model. Any design element that only works when Octo is
present is by definition part of the optional attachment, not the kernel.

## The three-layer model

Two layers already exist; one is new.

| Layer | Table | Meaning | Exists? |
|---|---|---|---|
| Customer | `dbo.Organizations` | who the people belong to; branding (name/accent/logo) | yes (#98 C) |
| Connection | `dbo.Clients` | where data physically lives: engine key, dialect, SecretRef | yes (#98 A) |
| **Tenant** | **`dbo.Tenants`** (new) | a customer area: `TenantCode` PK, `OrganizationCode` FK, `ClientCode` FK (its data connection), `IsActive` | **new** |

- One organization can own a tenant *and* still have users using the shared portal.
- A tenant references exactly one data connection. The connection may be external
  (bring-your-own DB — the MS02 pattern) or Nexora-hosted (the Generali pattern).
- Existing surfaces are unchanged: `Organizations` keeps branding, `Clients` keeps engines and
  secrets (env-file SecretRef, per white-label D3).

## The data box (descriptors)

Three new NexoraDB tables describe what a tenant's data *means*. They are the entire definition of
a tenant's generated UI.

| Table | One row per | Holds |
|---|---|---|
| `TenantEntities` | table/view in the tenant DB | `TenantCode` FK, `EntityKey`, `SourceObject` (schema-qualified name), `Kind` (`documents` \| `entries` \| `lookup`), labels de/fr/it, display order |
| `TenantFields` | column of an entity | entity FK, `ColumnName`, `SemanticRole` (`date` \| `money` \| `category` \| `person` \| `identifier` \| `count` \| `text` \| `flag`), optional lookup-entity ref, labels de/fr/it, visibility, order |
| `TenantPages` | generated page of a tenant | `TenantCode` FK, `PageKey`, `PageType` (`list` \| `crud` \| `dashboard` \| `report` \| `custom`), entity ref, layout JSON |

- Entity kinds map to page behavior: `documents` → read-only list/search/reporting (the Generali
  `ReportJob`/`Documents` shape), `entries` → CRUD (the effort-cluster shape), `lookup` → filter
  and join fodder, never a page of its own.
- `PageType = 'custom'` is the escape hatch: a code-registered page mounted into the tenant area
  (used by the MS02 document viewer, below). Bespoke stays possible; generated is the default.
- The workitems-feature tables (`ProcessSources`/`ProcessFieldMappings`/`FieldLabels`/
  `FieldAliases`) stay as they are — they are the workitems flavor of the same idea. Converging
  them into the box is sub-project 5, deliberately not forced now.
- Descriptor rows have a `Status` (`draft` \| `active`): Eddard writes drafts, only an admin
  activates. Generated pages read `active` rows only.

## The page engine

`nx_lib/tenant/` — grown from the beautify Task 14 `register_crud(app, desc)` factory, which is
its seed and must land first.

- Reads the box through a cached registry with the **`mapping_config` failure contract**: 60 s TTL,
  a load error returns `None` and is never cached, callers render an explicit "configuration
  unavailable" state — never an empty-looking success, never an unconstrained query (fail closed).
- Generates per tenant: list pages (filters, pagination, Excel export), CRUD pages for `entries`
  entities (permission-gated add/edit/delete, the descriptor-factory pattern), a tenant dashboard
  (pin-to-dashboard cards scoped by `TenantCode`), and auto-registered `dbo.ReportingSources`
  rows so tenant data is queryable in reporting and by Eddard with zero extra wiring.
- Routes live under `/t/<TenantCode>/<PageKey>` and are registered at boot from the DB. Adding a
  tenant therefore needs an app-pool recycle — the same documented caveat as `dbo.Clients` (D6 of
  the white-label spec). Say it in the UI; do not engineer a hot-reload.
- Frontend follows #191: one shared `static/js/tenant_pages.js`, thin Jinja shims per page holding
  only data + translated strings; all URLs through `API_PREFIX`.

**Security invariant:** every `SourceObject` and `ColumnName` from the box is interpolated into
SQL by the query builders — config, not parameters. Strict identifier validation
(`^[A-Za-z_][A-Za-z0-9_."\[\]]{0,99}$`, the white-label Task 7 discipline) is enforced on write
*and* on read; a row failing it is treated as absent. Free-form SQL fragments do not exist in the
box, by design.

## Data paths

| Path | How | Ships in |
|---|---|---|
| External DB | `dbo.Clients` row + one `env/{ENV}.env` secret block (MS02 pattern, unchanged; `scripts/env-sync.py` covers the manual step) | kernel (exists) |
| Nexora-hosted + CSV upload | a `Tenant_<Code>` database on the Nexora SQL Server; admin uploads CSVs mapped through the box descriptors | sub-project 2 |
| Nexora-hosted + scheduled import | the `scripts/generali-import` pattern generalized to a descriptor-driven importer | sub-project 4 (with the Generali migration) |

## MS02 pilot (sub-project 1 proof)

MS02 is rebuilt as the **first descriptor-driven tenant** — the pilot that proves generation.

- Tenant row + box descriptors over its PG statistik tables (wide columnar
  `public."DossierStatistik"` etc.; PascalCase identifiers stay quoted).
- Generated: list/search, statistics, dashboard, reporting.
- **One bespoke mount:** the workitem document viewer (Octo media, field/table overlays,
  `nx_lib/octo.py`) is Octo-coupled machinery that generation will not reproduce. It mounts as a
  `custom` page in the MS02 tenant area, reusing the shared renderer. This is the "optional Octo
  attachment" of the baseline principle — the only part of MS02 that is not data-only.
- After cutover: MS02 leaves `nx_lib/workitem_sources.py` and the `mapping_config` registry;
  shared `/workitems` serves `default` only and the probe-then-cache multi-source routing shrinks
  back to one source. The compound (client, id) identity caution stays until the cutover completes.
- Cutover is gated on feature parity verified in the browser against INT, page by page, before any
  shared-path removal.

## Generali migration (sub-project 4)

Generali migrates **onto the platform**, page by page, after #220's phases have given it English
names and real types (clean schema in, clean descriptors out).

- The effort cluster (`AttendanceEntries`, `BaseServiceEntries`, `ProjectEntries`,
  `QualityCheckEntries`) is already descriptor-shaped after beautify Task 14 — those pages go
  first and cheapest.
- `Documents` (2.47M rows) becomes a `documents` entity; the PDQM/reporting pages follow.
- Truly bespoke pages (month report) stay `custom` mounts until proven generatable.
- `nx_lib/views/generali.py` shrinks toward deletion; `/generali/*` URLs get redirects to
  `/t/generali/*` in the final step, not before.

## Eddard (sub-project 3)

Rides the existing provider-agnostic reporting-AI plumbing. Three assists, one rule:
**Eddard only writes `draft` descriptor/layout rows; an admin activates.**

1. **Infer the box:** profile the tenant DB (`INFORMATION_SCHEMA` + value sampling, the #220
   profiling pass as a tool) and propose entities, semantic roles, de/fr/it labels.
2. **Style the presentation:** propose `TenantPages` layout JSON — which fields matter, column
   order, dashboard cards, chart types.
3. **Conversational onboarding:** an admin-center chat where the admin describes the tenant
   ("this DB holds scanned insurance documents…") and Eddard fills drafts from conversation +
   schema.

## Permissions & navigation

- Creating a tenant auto-provisions `tenant.<code>.view` and `tenant.<code>.edit` in
  `dbo.Permission` (idempotent `WHERE NOT EXISTS`, granted to nobody — the white-label D7 idiom).
  Granting stays a deliberate act at `/admin/access-control`.
- The sidebar gains one section per tenant the viewer can see, gated through `page_visibility()`.
- Tenant admin surfaces extend the existing admin center (`/admin/clients` grows tenant rows;
  a new `/admin/tenants/<code>` holds the box editor in sub-project 2).

## Sub-projects & sequencing

Each sub-project gets its own spec→plan cycle; this document is the umbrella and the kernel's
design authority.

| # | Sub-project | Content | Gate |
|---|---|---|---|
| 0 | *(queued)* beautify campaign 0+1, 2a–c, 3; #220 phases | the CRUD factory seed; clean Generali schema | already planned |
| 1 | **Tenant kernel + MS02 pilot** | `dbo.Tenants`, box tables, `nx_lib/tenant/` engine, MS02 rebuilt, cutover | beautify Task 14 merged |
| 2 | **Onboarding UI** | box editor in the admin center, hosted-DB + CSV-upload path | kernel shipped |
| 3 | **Eddard onboarding** | profiler, layout proposals, conversational flow | onboarding UI shipped |
| 4 | **Generali migration** | page-by-page onto the platform; scheduled importer generalized | #220 renames shipped |
| 5 | **Geschäft convergence** | `/admin/processes` becomes a flavor of the box; one onboarding story | 1–4 stable |

## Decisions locked

| # | Decision | Rationale |
|---|---|---|
| T1 | Tenants are **data-first**; Octo/workitems is an optional `custom` attachment. | Owner: most tenants are pure input/output-management data. Kernel must not assume Octo. |
| T2 | Full-tenant model (Generali-style areas), realized through **generated pages from descriptors**, with `custom` mounts as the escape hatch. | Owner chose full tenants; generation keeps them affordable. |
| T3 | MS02 is the **pilot**, rebuilt on the platform now, leaving the shared workitems path after verified parity. | Owner: re-architect now; pilot proves generation on real data. |
| T4 | Generali **migrates onto the platform** progressively after #220. | One system in the end; effort cluster is already descriptor-shaped. |
| T5 | Both data paths (external DB / Nexora-hosted+import); hosted arrives in sub-project 2, scheduled imports in 4. | Owner. Matches the two real precedents. |
| T6 | Eddard assists all three ways but writes only `draft` rows; admin activates. | AI accelerates onboarding without owning live config. |
| T7 | Box tables are new; the workitems mapping tables are not absorbed until sub-project 5. | Don't force-unify two working systems mid-flight. |
| T8 | Boot-time route registration; app-pool recycle per new tenant, documented. | The `dbo.Clients` D6 precedent; hot-reload is engineering nobody asked for. |
| T9 | Strict identifier validation on every box value that reaches SQL; no free-form SQL in the box. | Descriptors are interpolated, not parameterised — the white-label Task 7 lesson. |

## Open questions (for sub-project 1 planning)

- **Q1 — `/t/<code>` vs vanity paths.** Does Generali keep `/generali/*` as a redirect forever, or
  do tenants get configurable path slugs? (Kernel assumes `/t/<code>`, redirects later.)
- **Q2 — Hosted-DB provisioning mechanics.** Creating `Tenant_<Code>` databases from the app needs
  a deliberately narrow mechanism (dedicated provisioning login or an operator-run script).
  Decide in sub-project 2, not the kernel.
- **Q3 — MS02 parity checklist.** Exact page inventory MS02 must reach before leaving the shared
  workitems path — enumerate at kernel-planning time against the live INT feature set.
- **Q4 — Per-tenant rate limits / compression / logging.** Assume house defaults apply; confirm
  nothing per-tenant is needed for v1.

## Testing

- **Unit:** descriptor→SQL builders (both dialects), identifier validation (reject on write and
  read), registry failure contract (None never cached; fail-closed page states).
- **Integration:** generated routes 403 without / 200 with the tenant permission; draft rows
  invisible; degraded-registry rendering; the house admin-route test pattern.
- **E2E:** one MS02 pilot page end-to-end against INT.
- **House guards stay binding:** `test_no_inline_event_handlers`, `test_template_url_prefix`,
  `test_translations` (all tenant-page chrome is translated de/fr/it).
