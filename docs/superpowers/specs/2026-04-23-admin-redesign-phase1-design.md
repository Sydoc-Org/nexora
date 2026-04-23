# Admin Redesign — Phase 1 Design

**Date:** 2026-04-23
**Status:** Design approved, pending implementation plan
**Scope:** Phase 1 of 3 (Foundation). Phases 2 and 3 are out of scope for this spec.

## Context

The existing admin section (`templates/admin/`) serves a small, technical audience — roughly one admin (the author) plus a couple of other technical users. It is used infrequently but for high-stakes tasks (onboarding, permission changes, incident log review).

The current implementation has three problems that warrant a ground-up rethink:

1. **Visual inconsistency.** Pages use pastel icon chips on the overview, indigo action buttons, ad-hoc spacing, and mixed tab/card patterns across pages. Each template duplicates its own header, filter bar, and button styles.
2. **Inefficient workflows.** User editing happens in a cramped modal. Filters are limited (e.g., the Users table cannot be filtered by profile or organization). Log filters lack common presets.
3. **Missing capabilities.** Features the admin needs — audit trail per user, force-logout, health visibility, permission-impact preview, command palette — do not exist today.

This spec addresses 1 and part of 2. Missing capabilities are deferred to Phase 2 and Phase 3.

## Goals

- A single, consistent visual system across every admin page.
- Navigation that reuses the existing sidebar's nested-group pattern (as used by Generali today).
- A full user detail page that replaces the cramped edit modal.
- Improved filtering on Users and Logs.
- Zero new DB tables and minimal new routes — this is primarily a front-end and template refactor.

## Non-goals (Phase 1)

These are explicitly deferred to later phases:

- Audit trail content (only a placeholder section appears on the detail page)
- Force-logout from the Sessions page
- System health metrics / dashboard strip on Overview
- Permission impact preview when editing a profile
- Command palette (Ctrl+K) for admin actions
- Dark-mode parity for admin pages
- Saved filter presets, CSV export of logs

## Target audience

Small technical team (≤3 users), infrequent high-stakes use. Design biases toward information density over hand-holding.

---

## 1. Navigation structure

The existing left sidebar in `templates/_header.html` gets one change: the **Admin** item becomes an expandable `sidebar-nav-group`, mirroring the pattern already used for Generali (see `_header.html` lines 51–109).

### Expanded items under Admin

| Order | Label | Route | Template |
|---|---|---|---|
| 1 | Overview | `admin_dashboard` | `admin/adminOverview.html` |
| 2 | Access Control | `admin_access_control` | `admin/accessControl.html` |
| 3 | Organizations | `admin_organizations_view` | `admin/organizations.html` |
| 4 | Sessions | `admin_sessions_view` | `admin/sessions.html` |
| 5 | Logs | `admin_logs_view` | `admin/logs.html` |

**Behavior:** auto-expanded when any admin subpage is active; collapsible via chevron. Behavior is identical to the existing `generaliNavGroup` handler, so no new JS is required — the group state helper in `js/_headerJS.html` is reused with a new element ID.

**Dropped from the sidebar:** Documentation and ngrok do not warrant top-level sidebar slots. They move into a small "Resources" footer section on the Overview page as plain links.

**Template impact:** the single `Admin` entry in the `nav_items` list (`_header.html` lines 32) is replaced with a `sidebar-nav-group` block structurally identical to the Generali one. No new CSS. ~40 lines of template change.

---

## 2. Visual design system

Direction B ("Stripe / Notion refined"). Warm off-white surfaces, near-black text, indigo reserved for focus/links/active states. Phase 1 is light-mode only.

### Tokens

| Category | Token | Value |
|---|---|---|
| Surface | `page` | `#f7f5f2` |
| Surface | `card` | `#ffffff` |
| Surface | `table-header`, `row-hover` | `#faf8f4` |
| Surface | `button-primary` | `#1a1a1a` |
| Border | `border-main` | `#eae6e0` |
| Border | `row-divider` | `#f5f2ed` |
| Border | `input-border` | `#d8d3cb` |
| Text | `body` | `#1a1a1a` |
| Text | `secondary` | `#6b6760` |
| Text | `meta` (uppercase labels) | `#8a857c` |
| Accent | `indigo` (focus, links, active) | `#6b46c1` |
| Status | `success` | `#257c3d` |
| Status | `warning` | `#b54708` |
| Status | `danger` | `#b42318` |

### Typography

Font is **Inter** (already loaded via `_header.html`).

| Role | Size | Weight | Letter-spacing | Color |
|---|---|---|---|---|
| Page title | 22px | 600 | -0.4px | `body` |
| Page subtitle | 13px | 400 | 0 | `secondary` |
| Section heading | 16px | 600 | -0.2px | `body` |
| Body / table cells | 13px | 400 | 0 | `body` |
| Meta / label (uppercase) | 11px | 600 | 0.6px | `meta` |
| Monospace (codes, IDs, paths) | 12px | 400 | 0 | on `#f3efe9` pill, 3px radius |

### Components

- **Buttons.** Primary is near-black (`#1a1a1a`), not indigo — indigo stays for focus/links only, so primary actions don't compete with navigation cues. Secondary is white with `#d8d3cb` border. Danger is `#b42318`. Ghost is transparent. All buttons: 7px radius, 7px vertical / 14px horizontal padding.
- **Badges.** 4px radius, small uppercase text. Tones: indigo (role=admin), green (active), amber (pending), gray (default role), red (locked).
- **Inputs.** 7px radius, `#d8d3cb` border. Focus is `#6b46c1` border with 3px soft glow (`rgba(107,70,193,0.12)`).
- **Cards.** 10px radius, `#eae6e0` border, white fill.
- **Tables.** 10px radius container, `#faf8f4` header, row divider `#f5f2ed`, hover `#faf8f4`.
- **Icons.** Monochrome. 16px glyphs, same weight as body text. No pastel icon chips.

### CSS integration

The token set and component classes live in a new file `static/css/admin-tokens.css`. Each admin page imports it via `<link>`. Existing Tailwind utility classes continue to work — `admin-tokens.css` defines classes like `.admin-card`, `.admin-btn-primary`, `.admin-badge--indigo` that page templates use directly.

---

## 3. Page structure (template strategy)

**Approach:** Jinja macros in a new file `templates/admin/_admin_helpers.html`.

Each admin page imports the macros and calls them for shared UI. This keeps the existing flat template layout (no `extends` refactor) and makes it easy to add or remove admin pages.

### Macros

| Macro | Purpose |
|---|---|
| `page_header(title, subtitle=None, back_url=None, actions=None)` | Page title block with optional back arrow, subtitle, and action buttons. Replaces the hand-written header currently duplicated on every admin page. |
| `filter_bar(filters)` | Horizontal filter row (search + selects + date range). Used by Users tab and Logs page. |
| `toolbar(search_placeholder, actions)` | Smaller table toolbar (search + primary action). Used by Organizations. |
| `table_header(columns)` | `<thead>` with consistent meta-label styling. |
| `empty_state(icon, message)` | Unified empty-result / loading-state cell for tables. |
| `badge(label, tone='gray')` | Status/role badge. |

### Usage example

```jinja
{% import 'admin/_admin_helpers.html' as a %}
<body class="admin-page">
  {% include '_header.html' %}
  <main class="admin-main">
    {{ a.page_header(
        title=_('Access Control'),
        subtitle=_('42 users · 3 organizations'),
        actions=[{'label': _('Add User'), 'onclick': 'openAddUserModal()', 'variant': 'primary'}]
    ) }}
    {# page-specific content #}
  </main>
</body>
```

Each current admin page shrinks: `organizations.html` lines 17–30 (the header block) become a single macro call.

---

## 4. Per-page changes

### 4.1 Overview (`adminOverview.html`)

- 4-card launcher grid (2×2) for the main admin sections: **Access Control**, **Organizations**, **Sessions**, **Logs**.
- Each card shows the section name + a one-line inline hint (e.g., "42 users · 3 orgs" for Access Control, "3 organizations" for Organizations). Pulled from existing queries used elsewhere.
- Monochrome icons, no pastel chips.
- Small **Resources** section below with plain text links: Documentation (Confluence), ngrok (external dashboard). Rendered as a quiet link list, not cards.
- The overview keeps its role as a launcher, not a dashboard. No stats strip in Phase 1.

### 4.2 Access Control (`accessControl.html`)

Structure unchanged: three tabs (Users / Permissions / Access Profiles).

**Users tab changes:**
- New filter dropdowns in the filter bar: **Access Profile**, **Organization**. Default = "All".
- Clicking any user row navigates to `/admin/users/<id>` (the new detail page).
- The edit modal is removed. The "Add User" button still opens a small modal for *creation only* with a minimal set of fields (username, full name, email, profile, org, password). All editing after creation happens on the detail page.
- The existing `confirmDeleteModal` stays (referenced from the detail page's danger zone).

**Permissions tab:** visual refresh only, no behavior change.

**Access Profiles tab:** visual refresh only. The existing permission drawer pattern (`permissionDrawer`) is unchanged.

### 4.3 User detail (new — `admin/userDetail.html`)

New route `/admin/users/<int:user_id>`. Full page, not a modal.

Sections (in order):
1. **Profile.** Identity + access fields (username, full name, email, access profile, organization). Password reset as an inline action. Save button persists changes via existing `POST /admin/users/edit/<id>` endpoint.
2. **Permission overrides.** Inline version of the existing permission drawer table — same radio-button "None / Deny / Allow" grid, rendered within the page instead of sliding out.
3. **Activity (placeholder).** Empty section with a heading and a "Coming in a future release" subtitle. Reserves layout space for Phase 2's audit trail.
4. **Danger zone.** Red-bordered box at the bottom with a single Delete action. Confirms via the existing `confirmDeleteModal`.

Top of the page: back link ← to Access Control, user's display name as title, username + role badge as subtitle.

### 4.4 Organizations (`organizations.html`)

Visual refresh only. Existing table + modal pattern retained.

- Filter bar gains a **Search** input (filters by name or code client-side — data is already in the rendered table).
- Action buttons restyled per Section 2 tokens.

### 4.5 Active Sessions (`sessions.html`)

Visual refresh only.

- "Last activity" column renders as relative time ("2 min ago") using a small JS helper (`formatRelativeTime`). Absolute timestamp remains available via tooltip.
- Refresh button restyled; auto-refresh every 30s (optional, can be off by default — see Open Questions).
- No force-logout button in Phase 1.

### 4.6 Logs (`logs.html`)

Visual refresh + filter improvements.

**New filters:**
- **Preset time ranges.** Quick buttons next to the date inputs: "Last hour", "Today", "Last 7 days", "Last 30 days". Clicking a preset populates the start/end date inputs client-side and triggers a fetch.
- **Organization filter.** New dropdown alongside the existing Username / Method / Path / Status filters. Joins logs → users → org server-side.

**Unchanged:** log details modal, pagination controls, CSV log format.

---

## 5. Backend / route changes

This is primarily a front-end refactor. Backend changes are limited and backward-compatible.

### New route

```python
@app.route('/admin/users/<int:user_id>')
@require_permission('admin.view')
def admin_user_detail(user_id):
    # Reuses existing user + permission-override helpers already used by the modal.
    ...
```

Renders `templates/admin/userDetail.html`. Returns 404 if the user does not exist.

### Modified endpoints

| Endpoint | Change |
|---|---|
| `GET /api/admin/users/list` | Accept optional `profile` and `organization` query params. When omitted, response is identical to today. |
| Logs fetch endpoint (current URL confirmed during implementation) | Accept optional `organization` param and `preset` param (`1h`, `24h`, `7d`, `30d`) which the server translates to start/end datetimes. Explicit `start`/`end` params override `preset`. |
| Organizations fetch endpoint (current URL confirmed during implementation) | Accept optional `q` query param for search-by-name/code. |

### Database

No schema changes. No new tables. The organization filter on logs joins the logs table (in the stats DB, populated by `cleanup/csvLogs_toDB.ps1`) against `Users` via username to resolve the user's organization.

### Permissions

Route-level guards unchanged. The new detail route uses existing permission codes:
- `admin.view` for read access
- `admin.users.edit` for write actions
- `admin.access.edit` for permission-override changes (reuses existing guard)

---

## 6. Testing

Nexora does not currently have an automated test suite wired to admin routes. Phase 1 verification is manual:

- Each admin page renders with correct permissions (test with a role that has `admin.view` only and a role with full admin rights).
- Nested sidebar expands and highlights correctly for each admin subpage.
- Users filter by profile + organization returns correct rows.
- User detail page save persists changes and reflects on the list.
- User creation flow via modal unchanged (regression check).
- Log preset buttons resolve to correct date ranges in the local timezone.
- Organization filter on logs returns users across all orgs when "All" is selected.

If a test scaffold exists or is added during implementation, the implementation plan should include route-level request tests for the new + modified endpoints.

## 7. Accessibility & i18n

- All new strings wrapped in `_('...')` for Flask-Babel. After implementation: `pybabel extract` + `pybabel update` + translate `.po` files for `de`, `fr`, `it`.
- Focus rings (indigo 3px glow) visible on all interactive elements.
- Tables have proper `<th scope="col">`.
- Buttons have accessible labels (icon-only buttons include `aria-label`).

## 8. Migration / rollout

Single deploy — no feature flag. The admin area is used by a small technical group; behind-the-scenes refactor can land in one go.

Backward compatibility:
- Existing API endpoints remain valid with old parameters.
- Existing route names (`admin_dashboard`, `admin_access_control`, etc.) are preserved.
- Existing permission codes and session keys unchanged.

## Open questions (to resolve during implementation)

- Sessions page auto-refresh: on by default at 30s, or off?
- Exact copy for the "Activity" placeholder on the user detail page.
- Whether to include "All time" as a default log preset or leave it as the implicit no-preset state.

## Out of scope — deferred to Phase 2 / 3

- Audit trail content (placeholder only in Phase 1)
- Force-logout action from Sessions
- System health panel on Overview
- Permission impact preview ("42 users will be affected") when editing a profile
- Command palette (Ctrl+K)
- Dark-mode parity for admin pages
- Saved filter presets
- CSV export of logs

Each of these gets its own spec when promoted into Phase 2 or Phase 3.
