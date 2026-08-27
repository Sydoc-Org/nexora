# White-label + admin onboarding UI (#98 phase 4) — Design

**Status: decided 2026-08-27** (owner answered the four blocking questions in-session). Implementation
plan: [`docs/superpowers/plans/2026-08-27-white-label-admin-ui.md`](../plans/2026-08-27-white-label-admin-ui.md).

Predecessor: [`2026-07-28-mapping-config-migration-design.md`](2026-07-28-mapping-config-migration-design.md)
(Approach B chosen) and the phases 2–3 plan
[`2026-08-26-docfield-config-restructure-perf.md`](../plans/2026-08-26-docfield-config-restructure-perf.md),
merged into `v3.2.3.1` as `d0415388`. Both explicitly deferred this: *"Out of scope (phase 4,
separate issue): `dbo.Clients` registry table, admin onboarding UI, per-client branding — the
white-label surface itself."*

---

## Problem

The owner is onboarding 10–50 customers onto nexora. Today, adding one is a developer task spread
across five places, three of which need a SQL migration and a deploy:

| # | What | Where it lives today |
|---|------|----------------------|
| 1 | The customer exists | `INSERT dbo.Organizations` — already self-service at `/admin/organizations` |
| 2 | Their processes are queryable | `INSERT dbo.ProcessSources` (+ `ProcessFieldMappings`, `FieldLabels`, `FieldAliases`) — **migration only** |
| 3 | Their processes are visible to anyone | `INSERT dbo.Permission (Code)` = `workitems.filter.process.<process>` — **migration only** |
| 4 | Someone is granted that permission | `/admin/access-control` — already self-service |
| 5 | Their data has its own runtime DB | hardcoded in `nx_lib/clients.py` + `MS02_*` keys in `env/{ENV}.env` — **code change + hand-edited env on SYAPP01** |

Steps 2, 3 and 5 are the blockers. Phases 2–3 already did the hard half of step 2 — the config is
now normalized, DB-resident, and behind one cached accessor (`nx_lib/mapping_config.py`, 60 s TTL
with an `invalidate_mapping_config()` hook that exists *specifically* for this phase). Nothing yet
writes those tables.

Separately, every customer sees the Nexora black-hole logo, the "nexora" wordmark and the indigo
default accent. White-label means a Privera user sees Privera.

## The two axes (read this before naming anything)

The word "client" is already taken, and conflating the two axes is the main way this design can go
wrong. Verified against INT on 2026-08-27:

```
Organizations:   DMEO=demo  LKTR=ElektroMaterial  PRVR=Privera  SSIX=ISS  SYDC=sydoc AG
Users/org:       DMEO=2  LKTR=2  PRVR=2  SSIX=3  SYDC=12
ProcessSources:  ('default', 'compass.01_Invoice_SAP')            ('default', 'privera.02_Posteingang')
                 ('default', 'elektromaterial.02_Invoice')        ('default', 'privera.03_Invoice_New')
                 ('default', 'privera.02_InitialScan')            ('ms02',    'sydoc.05_PDBS')
```

**Axis 1 — `ClientCode` (runtime source).** `default` | `ms02`. Answers *"which runtime DB, which
dialect, which Octo tenant?"*. Infrastructure-level, changes ~never, two values today. Lives in
`nx_lib/clients.py::CLIENTS` and is the `ClientCode` column on `ProcessSources` /
`ProcessFieldMappings` / `WorkitemSourceCache`.

**Axis 2 — `Organizations.organizationcode` (the customer).** `PRVR`, `LKTR`, … Answers *"who does
this user work for?"* via `dbo.Users.organizationCode`. Five values today, 10–50 tomorrow. The
`/admin/organizations` page already calls them *"Tenant organizations and their codes"*.

Most customers ride the **`default`** runtime — Privera, ElektroMaterial and Compass all do. A
customer only needs a new `ClientCode` when they bring their own database, which so far has happened
exactly once (MS02).

**Consequence, and the central decision of this design:**

- **Branding attaches to the Organization** — that is what a user belongs to, and no new user column
  is needed (`Users.organizationCode` already exists and is populated for all 21 users).
- **Runtime config attaches to the Client** — `dbo.Clients` replaces the hardcoded `CLIENTS` dict.
- Process visibility stays where it is: `workitems.filter.process.<name>` permissions. Process names
  are already customer-prefixed (`privera.02_Posteingang`), which is *convention only* — no code
  parses the prefix, and this design does not start.

Because these are separate axes, **onboarding a customer that rides `default` — the common case —
becomes fully self-service with zero env edits and zero deploys.** Only a customer bringing their own
DB needs the one manual env step described under Secrets.

## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Branding attaches to **`dbo.Organizations`** (new nullable columns), not to a new table and not to `ClientCode`. | It is already the tenant axis and already has a self-service admin page. A `Users.ClientCode` column would duplicate `organizationCode` and desync from it. |
| D2 | **In-app only.** Header/sidebar logo, wordmark, accent, page `<title>`. Login page, error pages and scheduled-report emails stay Nexora-branded. | Owner's answer. Login is pre-session — there is no user, so no organization, so branding would have to be resolved by hostname, which is the *"per hostname"* option the owner did not pick. |
| D3 | **Secrets stay in `env/{ENV}.env`.** `dbo.Clients` stores non-secret connection facts plus `SecretRef` — the env-key prefix (`MS02`) whose `*_OCTO_CLIENT_SECRET` / `*_DB_PASSWORD` keys are read at boot, exactly as today. | Owner was unsure; this is the recommendation. No new crypto or key-management surface, secrets stay out of DB backups (they are already a sore spot — see `reference_sql_backup_tool`), and `scripts/env-sync.py` already exists for the one manual step. Cost is one env edit per **own-DB** customer, which is rare. Upgrade path if it ever bites: add an `EncryptedSecret` column alongside `SecretRef` and prefer it when set — no schema rewrite. |
| D4 | User's explicit accent choice **wins over** the org accent; the org accent replaces the hardcoded `'indigo'` / `'#4f46e5'` default. | Preserves `/appearance` — a Privera user who picked emerald keeps emerald. The org brand is a *default*, not an override. One-line change at the existing `eff` fallback chain in `templates/_header.html`. |
| D5 | Org branding is injected by a **context processor** reading a 60 s cached registry (`nx_lib/branding.py`), mirroring `mapping_config.py`. **Never** cached in `session`. | #155 — caching per-user display config in the session is the bug that made appearance edits stick until re-login. `_inject_whats_new` already documents this idiom: *"a session cache races the cookie"*. |
| D6 | Logo upload lands in **`var/branding/<orgcode>.<ext>`**, served by one permission-free route (any logged-in user), `secure_filename` + `magic` MIME sniff, SVG/PNG/JPEG only. | `var` is already in `deploy.yml`'s `/XD` list, so the mirror neither copies nor purges it — uploads survive deploys. Also inside `var\`, so no new SYAPP01 Defender exclusion is needed. |
| D7 | `dbo.Clients` is **seeded from the current hardcoded registry** and `nx_lib/clients.py` keeps its exact `ClientConfig` dataclass + `CLIENTS` dict shape, just built from DB rows. A row whose engine or Octo domain is missing is skipped, preserving today's *"MS02 registers only when both are present"* degradation. | Zero blast radius on `octo.py` / `workitem_sources.py`, which import `CLIENTS`, `octo_creds_for_domain()` and `non_default_clients()`. |
| D8 | The process/mapping admin UI **auto-provisions** the `workitems.filter.process.<name>` permission row when a new `ProcessSources` row is saved, and calls `invalidate_mapping_config()` on every write. | Otherwise step 3 of the onboarding table stays a migration and the whole exercise fails its goal. The 60 s TTL means an admin edit that does *not* invalidate looks broken for a minute. |
| D9 | No `Users.ClientCode`, no per-hostname routing, no branded emails, no custom fonts/CSS upload. | YAGNI — D2 scope. Each is a clean later addition on top of this model. |

## Model

**`dbo.Clients`** (new, phase A) — one row per runtime source, PK `ClientCode`:

| column | note |
|---|---|
| `ClientCode` | `default`, `ms02` — FK target for `ProcessSources.ClientCode` (not enforced; `ProcessSources` predates it) |
| `DisplayName` | admin-UI label |
| `Dialect` | `tsql` \| `postgres` |
| `RuntimeEngineKey`, `StatsEngineKey`, `DocfieldsEngineKey` | names of engines in `nx_lib/db.py` (`engine_octo_db`, `engine_ms02_pg`, …) |
| `OctoDomain` | non-secret |
| `SecretRef` | env-key prefix; `NULL` = the default client's unprefixed `OCTO_*` keys |
| `IsActive` | soft-disable without deleting rows |

**`dbo.Organizations`** (extended, phase C) — three nullable columns: `BrandName`,
`BrandAccentHex` (`#rrggbb`, same validation as `ui_prefs.accentHex`), `BrandLogoFile`. All `NULL`
⇒ today's Nexora branding, which is what every existing row gets.

**`nx_lib/branding.py`** (new, phase C) — `brand_for_org(code) -> dict | None`, one cached registry
of all orgs (tens of rows), 60 s success-only, `invalidate_branding()` hook. Same failure contract as
`mapping_config.registry()`: a load error returns `None`, is never cached, and the caller degrades to
Nexora branding — branding must never be able to take the app down.

## Admin surface

Three touches, reusing the existing admin chrome (`templates/admin/_admin_helpers.html` macros, the
`admin/<page>.html` + `templates/js/admin/_<page>_js.html` pairing, `data-nx-click` delegation — never
inline `onclick=`, which `tests/unit/test_no_inline_event_handlers.py` forbids because the PROD CSP
silently drops it):

1. **`/admin/clients`** — CRUD over `dbo.Clients`. Rare, small, mostly read. New permissions
   `admin.view.clients` / `admin.edit.clients`.
2. **`/admin/processes`** — the onboarding surface. Per client: `ProcessSources` rows, their
   `ProcessFieldMappings`, and the shared `FieldLabels` / `FieldAliases`. Saving a new process row
   also creates its `workitems.filter.process.<name>` permission (D8). New permissions
   `admin.view.processes` / `admin.edit.processes`.
3. **`/admin/organizations`** — existing page gains a branding panel per org (name, accent, logo
   upload). New permission `admin.edit.organization.branding`.

## Out of scope

Branded login page and error pages; branded scheduled-report emails; per-hostname tenant domains;
per-org custom CSS/fonts; `Users.ClientCode`; any change to how process *visibility* is granted;
encrypted-at-rest secrets (D3 upgrade path noted, deliberately not built).

## Owner actions

- **Confirm D3** the first time a customer brings their own DB — that is the moment the one manual
  env edit becomes visible. Until then it costs nothing.
- **Decide whether `default` should be renamed** (it is the Sydoc-hosted Octo runtime that most
  customers ride, so the name is misleading in a 50-customer world). Renaming touches
  `ProcessSources`, `WorkitemSourceCache` and every `?client=` URL — **not** done in this phase.
