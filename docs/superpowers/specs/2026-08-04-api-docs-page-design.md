# In-app API Documentation page — design

**Date:** 2026-08-04
**Status:** Approved, ready for plan
**Issue:** #157

## Problem

`docs/howto/external-api.md` is the only reference for the external machine-to-machine
API (`/api/v1/*`) — a git file, not reachable from inside the portal. Issue #157 asks for
an in-app page so both external API clients and internal Sydoc staff can look up the API
definition without a repo checkout.

## Decisions (from brainstorming)

- **Access model:** gated behind login (not public) — reuses the portal's existing
  permission system rather than inventing a second, unauthenticated trust boundary.
  External clients get a portal account (existing pattern for tenant users) in addition
  to their API key.
- **Content depth:** same technical content as `external-api.md` (auth, quick-start curl,
  request/response, error table, rate limits), restructured as a real reference UI, built
  to accommodate future v1 endpoints without a redesign. No interactive "try it" tester —
  out of scope for v1 of this page.
- **Permission:** new dedicated code `api.docs.view`, independent of every other
  permission. Seeded to every access profile that already grants `admin.view` (mirrors
  migrations `0018`/`0029`/`0035`/`0044`), individually grantable beyond that.
- **Placement:** new top-level sidebar item "API Docs" at route `/api-docs` — the only nav
  pattern that exists in this codebase (Dashboard/Reporting/Workitems/Invoices all follow
  it), gated by `pageV.apiDocsPagePerm`.
- **Layout:** sidebar-of-endpoints + detail-pane (Stripe/Twilio-style), not one long
  scrolling page — chosen specifically so a second v1 endpoint is a new list item + detail
  section, not a redesign.

## Architecture

### 1. Permission — migration `sql/_migrations/NexoraDB/00NN_add_api_docs_permission.sql`

```sql
INSERT INTO dbo.Permission (Code, Description)
SELECT 'api.docs.view', 'View the in-app API documentation page'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'api.docs.view');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'api.docs.view'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
```

Wired into `nx_lib/security.py::page_visibility()` as `apiDocsPagePerm`, and into
`nx_lib/views/core.py` (or a new small view module — decide at plan time based on where
the route naturally fits) behind `@require_permission('api.docs.view')`.

### 2. Route + templates

- **Route:** `GET /api-docs` → `templates/api_docs.html` + paired
  `templates/js/_api_docs_js.html`.
- **Sidebar:** new entry in `templates/_header.html`'s `nav_items` list, same shape as the
  existing Dashboard/Reporting/Workitems/Invoices entries (`pageV.apiDocsPagePerm`, icon,
  label, active-state check on `active_page == 'api_docs'`).

### 3. Page structure

Left mini-nav, two groups:

- **Guide** — Getting Started (base URLs, quick-start curl), Authentication (API key /
  Bearer model, issuing/revoking), Errors & Rate Limits (the existing error table + the
  60/min limit note).
- **Endpoints** — one entry per v1 endpoint. Today: `GET /stats/today` only. Each entry's
  detail section: method+path, description, auth requirement, example request, example
  response, field-by-field response notes (mirrors the existing `external-api.md`
  breakdown of `date`/`imported_today`/`exported_today`/`processes`).

Clicking a left-nav item swaps the active detail section — plain vanilla JS toggle, same
idiom as the existing admin/generali nav-group toggle already in `_header.html`. No new
JS framework or state library.

### 4. Content source of truth

`docs/howto/external-api.md` stays the git-authored source per this repo's documentation
convention. The page presents the same facts as structured HTML, not a markdown render —
this is a restructuring for readability, not a second copy that can silently diverge in
substance (both describe the same one endpoint today; kept in sync by hand, which is
proportionate at this scale).

### 5. Visual design

Reuse existing `static/css/nexora-ui.css` components (cards, buttons, the
accent/density/motion appearance system) — no new visual language introduced. Code blocks
(curl examples, JSON responses) use the `highlight.js` CDN include already loaded in
`templates/workitems_overview.html` — no new dependency added for this page.

### 6. i18n

All user-facing strings (nav label, section headings, static copy) via `_()`. Machine
example payloads (the actual JSON in code blocks) stay unlocalized like the API itself.
Standard `pybabel extract → update → compile` cycle for de/fr/it.

## Testing

- Route/permission test in the style of `test_template_url_prefix.py`: page renders
  behind `api.docs.view`, 403s without it.
- Visual confirmation via `nx-ui-verify` (screenshot, no new browser-test infra).

## Out of scope (this version)

- Interactive "try it" request tester.
- Auto-generating page content from route introspection or an OpenAPI spec — the API
  surface is one endpoint; not worth the machinery yet.
- Public/unauthenticated access.
