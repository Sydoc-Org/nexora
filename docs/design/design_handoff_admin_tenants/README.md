# Handoff: nexora Admin – Tenants, Organizations & Admin Overview

## Overview
Redesign of the nexora admin area for tenancy. It replaces the "old boxes" look of the admin pages with the flatter, modern style already used by Dashboard, Workitems and Reporting, and restructures the tenancy pages:

- **Tenants Overview + Manage Tenants are merged** into one page, "Manage tenants" (`admin_tenants_view` + `admin_tenants_manage`).
- Each tenant and each organization gets a **detail page with tabs** instead of scattered modals and inline panels.
- **Data Connections** (`clients.html`) and **Process Configurations** (`processes.html`) are no longer separate sidebar items. Connections live on Manage tenants; process sources live on the organization they belong to.
- **Admin Overview** landing page restyled.

**Scope rule:** the redesign uses only the functions that exist today in `templates/admin/tenants_manage.html`, `organizations.html`, `clients.html` and `processes.html` (same fields, validation patterns and help texts). The one deliberate addition is **Reorder** of member navigation (writes `SortOrder`). Everything else that is read-only today stays read-only.

## About the Design Files
The files in this bundle are **design references created in HTML**, i.e. prototypes showing the intended look and behavior, not production code. Recreate them in the existing nexora stack (Flask/Jinja templates, `nexora-ui.css` + `admin.css`, `_admin_helpers.html` macros, the vanilla JS in `templates/js/admin/*`). Keep the existing endpoints, CSRF handling, `can_edit` / `can_edit_branding` gating and `data-testid`s. Only markup, CSS and the client-side JS for sheets/tabs change.

Open `Tenants Prototype.dc.html` in a browser (keep `support.js` next to it). All data in it is mock and lives in memory, with Undo on destructive actions.

## Fidelity
**High-fidelity.** Colors, type, spacing and interactions are final. Map the literal values below onto the matching `nexora-ui.css` tokens (`--nx-*`) instead of hard-coding hex values.

---

## Global layout
- App shell: sidebar 220px (existing `_header.html` sidebar) + `main` (flex:1, padding `32px 40px 64px`, content `max-width:1260px; margin:0 auto`). Background `#f9fafb`.
- **Sidebar change** (Admin group → Tenants sub-group): items are now only **Manage** (`fa-sliders`, → merged tenants page) and **Organizations** (`fa-building`). Remove "Overview", "Data Connections" and "Process Configurations". The nav list must scroll (`overflow-y:auto; overflow-x:hidden; min-height:0`).
- **Breadcrumbs** (detail pages): 11.5px `#9ca3af`, links `#6b7280`, current `#1f2937` 500, separators `fa-chevron-right` 8px. Tenant: `Manage tenants › Generali`. Org: `Organizations › Org` or `Manage tenants › Tenant › Org` depending on entry point.
- **Page header**: 44×44 icon tile (radius 12, gradient `135deg #4f46e5→#7c3aed`, shadow `0 8px 20px -6px rgba(79,70,229,.55)`, white 18px FA icon), H1 24px/600/-0.5px, subtitle 11.5px `#9ca3af`. Primary action at the right.
- **Tabs / filters (used everywhere, one style)**: row with `gap:20px`, bottom border `1px #e5e7eb`; each tab 12.5px/600, `padding-bottom:9px`, `margin-bottom:-1px`, active = ink `#1f2937` + `border-bottom:2px solid #4f46e5`, inactive = `#6b7280` + transparent border; count after label 500 `#9ca3af`. Search input (260px, 29px high) sits right-aligned in the same row.
- **Side sheets** replace all centered modals: `position:fixed` right, width 440–500px, white, shadow `-12px 0 32px rgba(16,24,40,.12)`, backdrop `rgba(17,24,39,.28)` (click closes). Header: kicker (10px uppercase label) + title 17px/600, close ✕. Body scrolls, padding `20px 24px`, 2-col grid gap 14px. Footer: Cancel (secondary) + primary save, right-aligned, top border. Enter animation: `translateX(40px)→0`, opacity 0→1, 220ms ease.
- **Confirm dialog** (delete): centered 420px card, radius 12, title 16px/600, body 12.5px `#6b7280`, Cancel + red `#dc2626` confirm.
- **Toast**: bottom-center, `#1f2937` bg, white 12.5px, green check `#34d399`, optional **Undo** link `#a5b4fc`. Auto-hide 4s.

## Screens

### 1. Admin Overview (`Admin Overview.dc.html` → `admin_overview.html`)
- Header: shield icon tile, "Administration", subtitle `Environment INT · nexora v…`. Right: INT/STAGING segmented switch (existing), "Restart nexora" secondary button (existing).
- KPI strip: 4 equal columns between top/bottom `#e5e7eb` borders, dividers `#f3f4f6`. Label 10px/700 uppercase `.09em` `#9ca3af`; value mono 32px/600/-1.4px; sub 11px/600 `#9ca3af`. Failed logins value in `#dc2626`. Database health column = pills (`#d1fae5/#065f46` ok, `#fee2e2/#991b1b` error).
- Two link groups side by side (gap 48px): **Tenancy** and **Access & monitoring**. Group header 15px/700 + 11px sub, bottom border. Rows: 32px icon tile `#f3f4f6`, label 13px/600, description 11.5px `#9ca3af`, right meta 11.5px/600 (`#92400e` when something needs attention, else `#9ca3af`), chevron. Row padding 14px 0, border `#f3f4f6`.
- Because of the sidebar change, the Tenancy links **Data Connections** and **Process Configurations** should point to Manage tenants › Data connections and Organizations respectively (or be dropped).
- Footer "Resources" links (documentation, ngrok).

### 2. Manage tenants (merged `tenants.html` + `tenants_manage.html`)
- Header: `fa-city` tile, "Manage tenants", subtitle "A tenant groups organizations. Its members see the tenant's pages instead of the global navigation." Primary **New tenant**.
- Tabs **All / Active / Inactive** with counts + search (tenant name, code, org names/codes, user names).
- KPI strip (4 cols): Tenants (n active), Organizations (n not in a tenant), Tenant users (across n orgs), Mounted pages (n in draft).
- **All tenants** table: Tenant (28px initial tile + name 13px/600 + mono code), Organizations (list: name + mono code; "No organization yet"), Users (right), Data connection (7px dot + `code · loaded` / `configured, not loaded`), Pages (`active / total`), Status (dot + Active / Pilot / Inactive), chevron. Row hover `#f5f7ff`, inactive rows opacity .65. Click a row to open the Tenant detail.
- **Needs attention** (amber count pill `#fef3c7/#92400e`): computed issues, each with an action link: orgs not in a tenant (→ org Tenant tab), no one holds `tenant.<code>.view` (→ tenant Access tab), tenant without orgs.
- **Data connections** section (from `clients.html`): help line about the app-pool recycle and env keys. Table: Code (mono), Display name, Dialect, Runtime engine (mono), Used by (org names derived from process sources), Active (Yes/No), Runtime state (`fa-circle-check` Loaded in `#6b7280`, or red `fa-triangle-exclamation` "Configured, not loaded" with the existing explanatory tooltip), edit/delete icon buttons. **Add connection** opens a sheet.

### 3. Tenant detail
- Header: 44px initial tile (tenant tint), name + status pill, meta `code · n organizations · n users`. Buttons **Edit tenant** (opens tenant sheet) and **Delete** (red outline → confirm).
- Tabs: **Organizations · Pages · Access**.
- **Organizations**: table with Organization (28px accent tile + name + code), Users (avatar stack + count), Access profiles (pills), Data connection, Processes; row opens Org detail. Empty state: dashed box + "Add organizations" (opens tenant sheet).
- **Pages**: left, a table (icon tile, label, target mono, type Custom/List, Draft|Active segmented toggle (Active = `#d1fae5/#065f46`, Draft = `#f3f4f6/#4b5563`), remove (custom pages only; list/crud pages show a lock). Footnote: generated list/crud pages come from migrations. **Mount page** opens the mount sheet. Right (440px): **Member preview**, a mini browser window (26px chrome bar with `nexora / <tenant> / <key>`) showing the tenant sidebar (active pages only + locked "Global Reporting") and a skeleton of the selected page (dashboard skeleton for dashboard/reports, table skeleton otherwise), accented in the tenant colour. Clicking a row or sidebar item selects it. **Reorder** button toggles up/down arrows per sidebar item (new: persists `SortOrder`).
- **Access** (read-only): profiles holding `tenant.<code>.view` with scope and user count; amber warning if none. Link "Manage in Permissions".

### 4. Organizations list (`organizations.html`)
- Header `fa-building`, subtitle "Organizations, their codes and tenant", primary **Add organization** (org sheet).
- Tabs: All + one per tenant + **No tenant**, with counts; search (name, code, users).
- Table: Organization (accent tile + name + code), Tenant ("Not in a tenant" in `#9ca3af`), Users, Data connection, Branding summary (Custom logo + colour / Custom colour / Custom logo / nexora default). Row → Org detail.

### 5. Organization detail
- Header: accent tile with mono, name, meta `CODE · Tenant <link> · Created dd.mm.yyyy`. **Edit** (org sheet: name + tenant) and **Delete** (confirm; process sources become unassigned).
- Tabs: **Users · Access profiles · Data & processes · Branding · Tenant**.
- **Users** (read-only): name/login, access profile, last sign-in.
- **Access profiles** (read-only): icon, name, Bound/Global tag (`#eef2ff/#4338ca` vs `#f3f4f6/#4b5563`), user count.
- **Data & processes** (from `processes.html` / `clients.html`):
  - Data connection card(s), derived from the distinct `ClientCode`s of the org's process sources: name, code, dialect, runtime engine, Octo domain, runtime state, **Edit** (client sheet). Empty state when the org has no sources.
  - **Process sources**: help line (name must be `<customer>.<process>`; adding creates `process.<client>.<name>.view` granted to nobody). **Add process source** (org preselected). One card per source: mono process name, `Table … · client …`, buttons **Add field / Edit / Delete**; field-mapping table Field key · Column · Column type with edit/delete icons; empty "No field mappings for this process."
- **Branding** (from the existing branding panel): Brand name, Accent colour (native colour picker + hex input + Clear), Logo (SVG/PNG/JPEG ≤512 KB, Upload/Replace), Discard / Save branding (disabled until dirty). Right side: live "what members see" preview (sidebar + dashboard in the accent).
- **Tenant**: radio list of tenants + "No tenant" (current marked); on change an amber note explains what members will see, then Cancel / **Move organization** (= existing edit-org `tenantcode`).

## Sheets (forms): fields and validation are the existing ones
| Sheet | Fields | Rules |
|---|---|---|
| Tenant (new/edit) | Display name, Code (mono), Active toggle, Organizations checklist with filter | code `[a-z0-9_]{2,50}`, unique. Ticking an org in another tenant shows an amber "moves here from X" row + warning. In edit, un-ticking warns that the org leaves the tenant |
| Mount page | Page (endpoint select), Key, Label, Icon (live FA preview), Sort order, Active page (optional) | key `[a-z0-9_.\-]{1,100}`, unique in tenant. icon `fa-[a-z0-9\-]{1,40}`. active `[A-Za-z0-9_\-]{0,60}`. Label is required. New pages are Draft |
| Organization | Organization name, Tenant select ("Not in a tenant") | name is required. Amber note when the tenant changes |
| Data connection | Client code, Display name, Dialect (tsql/postgres), Runtime engine key, Stats engine key*, Stats dialect*, Doc-field engine key*, Doc-field dialect*, Octo domain*, Secret ref*, Active | code `[a-z0-9_]{2,50}`, unique. Name and engine are required. Secret ref `[A-Z0-9_]{0,20}`. Note: applies after an app-pool recycle. All ten columns must always be posted (see the comment in `clients.html`) |
| Process source | Client code (select from dbo.Clients), Process name, Organization ("Unassigned"), Table name, Table alias* (≤10), Export/Import/Workitem column*, Id column type* | process `[A-Za-z0-9_\-]{1,49}\.[A-Za-z0-9_\-]{1,50}`, unique per client. Table is required. Lock note: join/time filters/extra condition are migration-only |
| Field mapping | Client code (ro), Process name (ro), Field key, Column name, Column type* | key `[A-Za-z0-9_.\-]{1,100}`, unique per process. Column is required |

\* optional. Errors are shown inline under the fields (11.5px `#dc2626`) and the offending input's border turns red.

## Interactions & state
- Detail pages are routed views (tenant by code, org by code), and the active tab should be part of the URL/hash so it survives a reload.
- Every save or delete shows a toast. Deletes go through the confirm dialog. The prototype's **Undo** is a nice-to-have. Drop it if the backend can't support it.
- Hover: table rows `#f5f7ff`, icon buttons `#f3f4f6` (danger `#fee2e2` + `#dc2626`), secondary buttons `#f9fafb`.
- Simple entry animation for new rows/cards: `opacity 0, translateY(6px) → none`, 200–250ms ease.

## Design tokens
- **Font**: Inter 400/500/600/700; mono `ui-monospace, 'SF Mono', Consolas, monospace` for codes, keys, engines, numbers in KPIs.
- **Type scale**: H1 24/600; section H3 15/700/-0.02em; body 12.5–13; meta 11–11.5; labels 10/700 uppercase `.09em`; KPI 32 mono/600/-1.4px.
- **Ink**: `#1f2937` primary, `#6b7280` secondary, `#9ca3af` meta, `#d1d5db` faint icons.
- **Lines**: `#e5e7eb` section/table header, `#f3f4f6` row separators, `#d1d5db` input borders.
- **Surfaces**: page `#f9fafb`, cards/sheets `#fff`, hover `#f5f7ff`, selected `#eef2ff`.
- **Primary**: gradient `#4f46e5 → #7c3aed` (buttons, icon tiles), solid `#4f46e5` (tab underline, focus), `#4338ca` (text on light indigo), `#a5b4fc` / `#c7d2fe` (light borders).
- **Status**: green `#059669` dot / `#d1fae5` bg / `#065f46` text. Amber `#d97706` / `#fef3c7` / `#92400e`. Red `#dc2626` / `#fee2e2` / `#fecaca` border / `#991b1b` text. Neutral `#f3f4f6` / `#4b5563`.
- **Radius**: 7px buttons/inputs, 8–10px cards/tiles, 12px page icon tile & dialogs, 999px pills/avatars.
- **Shadows**: primary button `0 2px 8px -2px rgba(79,70,229,.45)`; sheet `-12px 0 32px rgba(16,24,40,.12)`; dialog `0 24px 48px rgba(16,24,40,.2)`; preview window `0 8px 24px -12px rgba(16,24,40,.18)`.
- **Spacing**: main padding 32/40; section gaps 18–32px; table cell padding 11–14px vertical, 12px right; sheet padding 20/24.
- **Controls**: button 5×10 (small, 12px) or 8×14 (13px); input height 29px (search) / 33px (forms); toggle 36×20 with 14px knob.

## Assets
- Icons: Font Awesome 6.4.2 (already loaded in nexora).
- Logos: placeholder only. Use the uploaded org logo via `branding_logo` (`/branding/<orgcode>/logo`).

## Files
- `Tenants Prototype.dc.html`: the full interactive prototype (Manage tenants, Tenant detail, Organizations, Organization detail, all sheets). The main reference.
- `Admin Overview.dc.html`: Admin landing page.
- `Admin Sidebar.dc.html`: sidebar with the new Tenants group (`variant="new"`).
- `support.js`: runtime needed to open the `.dc.html` files locally.
- `screenshots/`: reference captures, scaled to fit about 925px wide, so use the HTML files for exact sizes:
  - `00-admin-overview`
  - `01-manage-tenants`, `02-manage-data-connections`
  - `03-tenant-organizations`, `04-tenant-pages`, `05-tenant-access`, `06-tenant-pages-member-preview`, `07-sheet-edit-tenant`
  - `08-organizations-list`, `09-org-users`, `10-org-data-processes`, `11-sheet-process-source`, `12-org-branding`, `13-org-tenant`
  - `14-sheet-data-connection`

Source templates to change in nexora: `templates/admin/tenants.html`, `tenants_manage.html`, `organizations.html`, `modals/_organizations_modals.html`, `clients.html`, `processes.html`, `admin_overview.html`, `_header.html` (sidebar), `static/css/admin.css`, `templates/js/admin/_tenants_manage_js.html`, `_organizations_js.html`, `_clients_js.html`, `_processes_js.html`.
