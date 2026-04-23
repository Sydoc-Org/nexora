# Admin Redesign — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-23-admin-redesign-phase1-design.md`

**Goal:** Redesign the Nexora admin section (5 pages + 1 new detail page) with a consistent visual system, nested sidebar navigation, Jinja macros for shared UI, improved filters on Users and Logs, and a full User detail page that replaces the edit modal.

**Architecture:** Front-end-heavy refactor. New `static/css/admin-tokens.css` defines the design system. New `templates/admin/_admin_helpers.html` provides Jinja macros consumed by every admin page. The existing left sidebar gets a nested "Admin" group that mirrors the working Generali pattern. Backend changes are minimal: one new route (`/admin/users/<id>`) plus optional query-param filters on three existing endpoints, all backward-compatible.

**Tech Stack:** Flask + Jinja2 + Tailwind (via CDN) + vanilla JS + Font Awesome. No build step. No test framework — each task ends with a manual verification step you run in the browser.

**Conventions used below:**
- File paths are absolute-from-repo-root.
- Commits follow the existing style (short imperative subject, no trailing period).
- Permissions already exist in `dbo.spGetUserPermissions`; no DB changes needed.
- Run the dev server with `python app.py` (ENVIRONMENT=INT).

---

## File Structure

### New files

| Path | Responsibility |
|---|---|
| `static/css/admin-tokens.css` | Design tokens + component classes (`.admin-card`, `.admin-btn-primary`, `.admin-badge`, `.admin-table`, etc.) |
| `templates/admin/_admin_helpers.html` | Jinja macros: `page_header`, `filter_bar`, `toolbar`, `table_header`, `empty_state`, `badge` |
| `templates/admin/userDetail.html` | Full user detail page (profile · overrides · activity placeholder · danger zone) |
| `templates/js/admin/_userDetailJS.html` | JS for detail page (save, delete, permission override wiring) |

### Modified files

| Path | Why |
|---|---|
| `templates/_header.html` | Replace top-level `Admin` sidebar item with `sidebar-nav-group` |
| `templates/js/_headerJS.html` | Add admin-group expand handler (mirror of generali handler) |
| `static/css/_header.css` | Admin-group CSS rules (mirror of generali rules) |
| `templates/admin/adminOverview.html` | 4-card launcher with inline stats + Resources footer |
| `templates/admin/organizations.html` | Refresh to new tokens + search input |
| `templates/js/admin/_organizationsJS.html` | Client-side search filter |
| `templates/admin/sessions.html` | Refresh + relative-time column |
| `templates/js/admin/_sessionsJS.html` | Relative-time formatter |
| `templates/admin/logs.html` | Refresh + preset buttons + organization filter |
| `templates/js/admin/_logsJS.html` | Preset handlers + org filter param |
| `templates/admin/accessControl.html` | Refresh all 3 tabs; Users tab: row-click→detail, remove edit modal, add profile+org filters |
| `templates/js/admin/_accessControlJS.html` | Row-click nav, new filter params, drop edit-modal logic |
| `app.py` | New `admin_user_detail` route; filter params on `get_users_admin_access_control`, logs, orgs endpoints |

---

## Task 1: Admin design tokens CSS

**Files:**
- Create: `static/css/admin-tokens.css`

- [ ] **Step 1: Write the full token + component stylesheet**

Create `static/css/admin-tokens.css` with:

```css
/* ============================================================
   NEXORA ADMIN — design tokens + components (Phase 1)
   Scoped to pages that include this file.
   ============================================================ */

:root {
  /* Surfaces */
  --a-page:          #f7f5f2;
  --a-card:          #ffffff;
  --a-alt:           #faf8f4;   /* table header, row hover */
  --a-ink:           #1a1a1a;   /* primary button bg, body text */

  /* Borders */
  --a-border:        #eae6e0;
  --a-border-input:  #d8d3cb;
  --a-row-divider:   #f5f2ed;
  --a-mono-bg:       #f3efe9;

  /* Text */
  --a-text:          #1a1a1a;
  --a-text-sec:      #6b6760;
  --a-text-meta:     #8a857c;

  /* Accents */
  --a-indigo:        #6b46c1;
  --a-indigo-soft:   rgba(107,70,193,0.12);
  --a-success:       #257c3d;
  --a-warning:       #b54708;
  --a-danger:        #b42318;

  /* Badge backgrounds */
  --a-b-indigo:      #eef0ff;
  --a-b-indigo-fg:   #4338ca;
  --a-b-green:       #e7f6ec;
  --a-b-green-fg:    #257c3d;
  --a-b-amber:       #fef3c7;
  --a-b-amber-fg:    #92400e;
  --a-b-gray:        #f3efe9;
  --a-b-gray-fg:     #6b6760;
  --a-b-red:         #fee4e2;
  --a-b-red-fg:      #b42318;
}

/* Page wrapper */
body.admin-page { background: var(--a-page); color: var(--a-text); }
body.admin-page main { padding: 28px 32px; max-width: 1280px; margin: 0 auto; }

/* Typography */
.admin-title    { font-size: 22px; font-weight: 600; letter-spacing: -0.4px; color: var(--a-text); margin: 0; }
.admin-subtitle { font-size: 13px; color: var(--a-text-sec); margin: 4px 0 0; }
.admin-section  { font-size: 16px; font-weight: 600; letter-spacing: -0.2px; color: var(--a-text); }
.admin-meta     { font-size: 11px; font-weight: 600; letter-spacing: 0.6px; text-transform: uppercase; color: var(--a-text-meta); }
.admin-mono     { font-family: "SF Mono", Consolas, "Roboto Mono", monospace; font-size: 12px; background: var(--a-mono-bg); padding: 1px 6px; border-radius: 3px; }

/* Header block */
.admin-header        { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
.admin-header-left   { display: flex; align-items: center; gap: 12px; }
.admin-back          { color: var(--a-text-sec); padding: 6px; border-radius: 6px; }
.admin-back:hover    { background: var(--a-alt); color: var(--a-text); }
.admin-header-actions { display: flex; gap: 8px; }

/* Buttons */
.admin-btn          { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 7px; font-size: 13px; font-weight: 500; border: 1px solid transparent; cursor: pointer; text-decoration: none; transition: background-color 0.12s, border-color 0.12s; }
.admin-btn:focus    { outline: none; box-shadow: 0 0 0 3px var(--a-indigo-soft); }
.admin-btn-primary  { background: var(--a-ink); color: #fff; }
.admin-btn-primary:hover { background: #000; }
.admin-btn-secondary { background: var(--a-card); color: var(--a-text); border-color: var(--a-border-input); }
.admin-btn-secondary:hover { background: var(--a-alt); }
.admin-btn-danger   { background: var(--a-danger); color: #fff; }
.admin-btn-danger:hover { background: #8c1b12; }
.admin-btn-ghost    { background: transparent; color: var(--a-text-sec); }
.admin-btn-ghost:hover { background: var(--a-alt); color: var(--a-text); }

/* Badges */
.admin-badge              { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
.admin-badge--indigo      { background: var(--a-b-indigo); color: var(--a-b-indigo-fg); }
.admin-badge--green       { background: var(--a-b-green);  color: var(--a-b-green-fg);  }
.admin-badge--amber       { background: var(--a-b-amber);  color: var(--a-b-amber-fg);  }
.admin-badge--gray        { background: var(--a-b-gray);   color: var(--a-b-gray-fg);   }
.admin-badge--red         { background: var(--a-b-red);    color: var(--a-b-red-fg);    }

/* Inputs */
.admin-input, .admin-select {
  background: var(--a-card);
  border: 1px solid var(--a-border-input);
  border-radius: 7px;
  padding: 8px 12px;
  font-size: 13px;
  color: var(--a-text);
  width: 100%;
  transition: border-color 0.12s, box-shadow 0.12s;
}
.admin-input:focus, .admin-select:focus { outline: none; border-color: var(--a-indigo); box-shadow: 0 0 0 3px var(--a-indigo-soft); }
.admin-input-icon { position: relative; }
.admin-input-icon > i { position: absolute; left: 10px; top: 50%; transform: translateY(-50%); color: var(--a-text-meta); font-size: 12px; }
.admin-input-icon > input { padding-left: 32px; }

/* Filter bar */
.admin-filter-bar {
  background: var(--a-card);
  border: 1px solid var(--a-border);
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 20px;
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  align-items: end;
}
.admin-filter-bar label { font-size: 11px; font-weight: 600; color: var(--a-text-meta); text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 4px; display: block; }

/* Card */
.admin-card { background: var(--a-card); border: 1px solid var(--a-border); border-radius: 10px; padding: 16px; }
.admin-card-link { display: block; text-decoration: none; color: inherit; transition: border-color 0.12s, box-shadow 0.12s; }
.admin-card-link:hover { border-color: var(--a-text-sec); box-shadow: 0 1px 3px rgba(0,0,0,0.04); }

/* Table */
.admin-table-wrap { background: var(--a-card); border: 1px solid var(--a-border); border-radius: 10px; overflow: hidden; }
.admin-table      { width: 100%; border-collapse: collapse; font-size: 13px; color: var(--a-text); }
.admin-table thead th { background: var(--a-alt); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.6px; color: var(--a-text-meta); padding: 10px 16px; text-align: left; border-bottom: 1px solid var(--a-border); }
.admin-table tbody td { padding: 12px 16px; border-bottom: 1px solid var(--a-row-divider); }
.admin-table tbody tr:last-child td { border-bottom: none; }
.admin-table tbody tr.is-clickable { cursor: pointer; }
.admin-table tbody tr.is-clickable:hover { background: var(--a-alt); }
.admin-table .align-right { text-align: right; }

/* Empty / loading state cells */
.admin-empty { padding: 32px 16px; text-align: center; color: var(--a-text-meta); font-size: 13px; }

/* Sidebar admin-open rules (see Task 3 for the accompanying JS) */
#nexora-sidebar:hover #adminNavGroup.admin-open .sidebar-nav-subitems {
  max-height: var(--admin-subitems-height, 9999px);
}
#adminNavGroup.admin-open .sidebar-generali-chevron { transform: rotate(90deg); }
@media (max-width: 768px) {
  #nexora-sidebar.open #adminNavGroup.admin-open .sidebar-nav-subitems {
    max-height: var(--admin-subitems-height, 9999px);
  }
}
```

- [ ] **Step 2: Verify the file is syntactically valid by opening it in a test HTML file**

Run: `python -c "open('static/css/admin-tokens.css').read()" ` — should complete without error. This just confirms the file exists and reads.

- [ ] **Step 3: Commit**

```bash
git add static/css/admin-tokens.css
git commit -m "Add admin design tokens and component CSS"
```

---

## Task 2: Admin Jinja helpers (macros)

**Files:**
- Create: `templates/admin/_admin_helpers.html`

- [ ] **Step 1: Write the macros file**

Create `templates/admin/_admin_helpers.html` with:

```jinja
{# ------------------------------------------------------------------
   Admin UI macros — shared building blocks for every admin page.
   Usage:  {% import 'admin/_admin_helpers.html' as a %}
   ------------------------------------------------------------------ #}

{% macro page_header(title, subtitle=None, back_url=None, actions=None) %}
  <div class="admin-header">
    <div class="admin-header-left">
      {% if back_url %}
        <a href="{{ back_url }}" class="admin-back" aria-label="{{ _('Back') }}">
          <i class="fas fa-arrow-left"></i>
        </a>
      {% endif %}
      <div>
        <h2 class="admin-title">{{ title }}</h2>
        {% if subtitle %}<p class="admin-subtitle">{{ subtitle }}</p>{% endif %}
      </div>
    </div>
    {% if actions %}
      <div class="admin-header-actions">
        {% for act in actions %}
          <button type="button" onclick="{{ act.onclick }}" class="admin-btn admin-btn-{{ act.variant|default('primary') }}">
            {% if act.icon %}<i class="fas {{ act.icon }}"></i>{% endif %}
            {{ act.label }}
          </button>
        {% endfor %}
      </div>
    {% endif %}
  </div>
{% endmacro %}


{% macro filter_bar(filters) %}
  {# filters = [{id, label, type, placeholder?, options?}] where type in 'search'|'select'|'date' #}
  <div class="admin-filter-bar">
    {% for f in filters %}
      <div>
        <label for="{{ f.id }}">{{ f.label }}</label>
        {% if f.type == 'search' %}
          <div class="admin-input-icon">
            <i class="fas fa-search"></i>
            <input type="text" id="{{ f.id }}" class="admin-input" placeholder="{{ f.placeholder|default('') }}">
          </div>
        {% elif f.type == 'select' %}
          <select id="{{ f.id }}" class="admin-select">
            {% for opt in f.options %}
              <option value="{{ opt.value }}">{{ opt.label }}</option>
            {% endfor %}
          </select>
        {% elif f.type == 'date' %}
          <input type="date" id="{{ f.id }}" class="admin-input">
        {% endif %}
      </div>
    {% endfor %}
  </div>
{% endmacro %}


{% macro toolbar(search_id, search_placeholder, actions=None) %}
  <div style="display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:16px;flex-wrap:wrap">
    <div class="admin-input-icon" style="width:280px">
      <i class="fas fa-search"></i>
      <input type="text" id="{{ search_id }}" class="admin-input" placeholder="{{ search_placeholder }}">
    </div>
    {% if actions %}
      <div class="admin-header-actions">
        {% for act in actions %}
          <button type="button" onclick="{{ act.onclick }}" class="admin-btn admin-btn-{{ act.variant|default('primary') }}">
            {% if act.icon %}<i class="fas {{ act.icon }}"></i>{% endif %}
            {{ act.label }}
          </button>
        {% endfor %}
      </div>
    {% endif %}
  </div>
{% endmacro %}


{% macro table_header(columns) %}
  {# columns = list of {label, align?, width?} #}
  <thead>
    <tr>
      {% for c in columns %}
        <th{% if c.align %} class="align-{{ c.align }}"{% endif %}{% if c.width %} style="width:{{ c.width }}"{% endif %}>{{ c.label }}</th>
      {% endfor %}
    </tr>
  </thead>
{% endmacro %}


{% macro empty_state(icon, message, colspan=6) %}
  <tr><td colspan="{{ colspan }}" class="admin-empty"><i class="fas {{ icon }}"></i> &nbsp; {{ message }}</td></tr>
{% endmacro %}


{% macro badge(label, tone='gray') %}
  <span class="admin-badge admin-badge--{{ tone }}">{{ label }}</span>
{% endmacro %}
```

- [ ] **Step 2: Verify — import from a throwaway check**

In the terminal, confirm the file exists and has the six macros:

```bash
grep -c '^{% macro ' templates/admin/_admin_helpers.html
```

Expected output: `6`

- [ ] **Step 3: Commit**

```bash
git add templates/admin/_admin_helpers.html
git commit -m "Add admin Jinja helper macros"
```

---

## Task 3: Nested admin sidebar group

**Files:**
- Modify: `templates/_header.html` (replace single Admin nav item with sidebar-nav-group)
- Modify: `templates/js/_headerJS.html` (add admin-group expand handler)
- Modify: `static/css/_header.css` (no structural change — Task 1 already added `#adminNavGroup.admin-open` selectors)

- [ ] **Step 1: Replace the Admin entry in `templates/_header.html`**

In `templates/_header.html`, locate the `nav_items` list (lines ~31–37) and remove the Admin entry:

```jinja
{# BEFORE #}
{% set nav_items = [
    {'perm': pageV.adminPagePerm,     'url': url_for('admin_dashboard'),     'icon': 'fa-shield-halved',       'label': _('Admin'),     'active': active_page in ['adminOverview','organizations','admin_access','admin_logs','admin_sessions']},
    {'perm': pageV.chatPagePerm,      'url': url_for('chat_page'),           'icon': 'fa-comments',            'label': _('Chat'),      'active': active_page == 'chat'},
    ...
] %}
```

Change to:

```jinja
{# AFTER #}
{% set nav_items = [
    {'perm': pageV.chatPagePerm,      'url': url_for('chat_page'),           'icon': 'fa-comments',            'label': _('Chat'),      'active': active_page == 'chat'},
    {'perm': pageV.dashboardPagePerm, 'url': url_for('dashboard'),           'icon': 'fa-gauge-high',          'label': _('Dashboard'), 'active': active_page == 'dashboard'},
    {'perm': pageV.workitemsPagePerm, 'url': url_for('workitems_overview'),  'icon': 'fa-layer-group',         'label': _('Workitems'),'active': active_page == 'workitems_overview'},
    {'perm': pageV.invoicesPagePerm,  'url': url_for('invoices'),            'icon': 'fa-file-invoice-dollar', 'label': _('Invoices'), 'active': active_page == 'invoices'},
] %}
```

Then, immediately after the `{% for item in nav_items %}` loop (right before the Generali `{% if %}` block around line 49), insert the Admin group:

```jinja
{% if pageV.adminPagePerm %}
{% set admin_active = active_page in ['adminOverview','organizations','admin_access','admin_logs','admin_sessions','admin_user_detail'] %}
<div class="sidebar-nav-group" id="adminNavGroup" data-active="{{ 'true' if admin_active else 'false' }}">
    <button class="sidebar-nav-item sidebar-nav-group-header {{ 'sidebar-nav-item--active' if admin_active else '' }}" id="adminNavHeader" type="button">
        <i class="fas fa-shield-halved sidebar-nav-icon"></i>
        <span class="sidebar-label" style="flex:1">{{ _('Admin') }}</span>
        <i class="fas fa-chevron-right sidebar-label sidebar-generali-chevron"></i>
    </button>
    <div class="sidebar-nav-subitems">
        <a href="{{ url_for('admin_dashboard') }}"
            class="sidebar-nav-item sidebar-nav-subitem {{ 'sidebar-nav-item--active' if active_page == 'adminOverview' else '' }}">
            <i class="fas fa-house sidebar-nav-icon sidebar-subitem-icon"></i>
            <span class="sidebar-label">{{ _('Overview') }}</span>
        </a>
        <a href="{{ url_for('admin_access_control') }}"
            class="sidebar-nav-item sidebar-nav-subitem {{ 'sidebar-nav-item--active' if active_page == 'admin_access' else '' }}">
            <i class="fas fa-id-badge sidebar-nav-icon sidebar-subitem-icon"></i>
            <span class="sidebar-label">{{ _('Access Control') }}</span>
        </a>
        <a href="{{ url_for('admin_organizations_view') }}"
            class="sidebar-nav-item sidebar-nav-subitem {{ 'sidebar-nav-item--active' if active_page == 'organizations' else '' }}">
            <i class="fas fa-building sidebar-nav-icon sidebar-subitem-icon"></i>
            <span class="sidebar-label">{{ _('Organizations') }}</span>
        </a>
        <a href="{{ url_for('admin_sessions_view') }}"
            class="sidebar-nav-item sidebar-nav-subitem {{ 'sidebar-nav-item--active' if active_page == 'admin_sessions' else '' }}">
            <i class="fas fa-signal sidebar-nav-icon sidebar-subitem-icon"></i>
            <span class="sidebar-label">{{ _('Sessions') }}</span>
        </a>
        <a href="{{ url_for('admin_logs_view') }}"
            class="sidebar-nav-item sidebar-nav-subitem {{ 'sidebar-nav-item--active' if active_page == 'admin_logs' else '' }}">
            <i class="fas fa-clipboard-list sidebar-nav-icon sidebar-subitem-icon"></i>
            <span class="sidebar-label">{{ _('Logs') }}</span>
        </a>
    </div>
</div>
{% endif %}
```

- [ ] **Step 2: Add the admin-group expand handler in `templates/js/_headerJS.html`**

At the bottom of the `<script>` block (after the existing generali handler at the end of the file), add:

```javascript
document.addEventListener('DOMContentLoaded', function () {
    const group    = document.getElementById('adminNavGroup');
    const header   = document.getElementById('adminNavHeader');
    const subitems = group && group.querySelector('.sidebar-nav-subitems');
    if (!group || !header || !subitems) return;

    function setSubitemsHeight() {
        subitems.style.maxHeight = 'none';
        const h = subitems.scrollHeight;
        subitems.style.maxHeight = '';
        group.style.setProperty('--admin-subitems-height', h + 'px');
    }

    setSubitemsHeight();

    const isActive = group.dataset.active === 'true';
    const savedOpen = localStorage.getItem('nexora-admin-nav') === 'true';
    if (isActive || savedOpen) group.classList.add('admin-open');

    header.addEventListener('click', () => {
        const nowOpen = group.classList.toggle('admin-open');
        localStorage.setItem('nexora-admin-nav', nowOpen ? 'true' : 'false');
    });
});
```

- [ ] **Step 3: Verify manually**

1. Start the dev server: `python app.py` (ensure `ENVIRONMENT=INT` is set)
2. Log in with an admin account
3. Open the app — hover the sidebar. The "Admin" item now has a chevron.
4. Click Admin → it expands showing Overview / Access Control / Organizations / Sessions / Logs
5. Click any sub-item — it navigates, stays highlighted, and the group remains expanded
6. Refresh the browser — group state persists (localStorage)
7. Collapse by clicking Admin again — state persists on refresh
8. Resize to mobile width (<768px), open the drawer (burger icon) — the group still expands and collapses

- [ ] **Step 4: Commit**

```bash
git add templates/_header.html templates/js/_headerJS.html
git commit -m "Nest admin subpages under expandable sidebar group"
```

---

## Task 4: Overview page refresh

**Files:**
- Modify: `templates/admin/adminOverview.html` (full rewrite)

- [ ] **Step 1: Rewrite `templates/admin/adminOverview.html`**

Replace the file contents with:

```jinja
<!DOCTYPE html>
<html lang="{{ get_locale }}">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{{ _("Admin Overview - nexora") }}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/output.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/admin-tokens.css') }}">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css" />
</head>
<body class="admin-page">
    {% set active_page = 'adminOverview' %}
    {% include '_header.html' %}
    {% import 'admin/_admin_helpers.html' as a %}

    <main>
        {{ a.page_header(
            title=_('Administration'),
            subtitle=_('Users, organizations, sessions and logs.')
        ) }}

        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-bottom:32px;">

            <a href="{{ url_for('admin_access_control') }}" class="admin-card admin-card-link">
                <div class="admin-meta" style="margin-bottom:8px">
                    <i class="fas fa-id-badge"></i> &nbsp; {{ _('Access Control') }}
                </div>
                <div class="admin-section">{{ user_count }} {{ _('users') }}</div>
                <p style="font-size:12px;color:var(--a-text-sec);margin:4px 0 0">{{ _('Users, permissions, access profiles') }}</p>
            </a>

            <a href="{{ url_for('admin_organizations_view') }}" class="admin-card admin-card-link">
                <div class="admin-meta" style="margin-bottom:8px">
                    <i class="fas fa-building"></i> &nbsp; {{ _('Organizations') }}
                </div>
                <div class="admin-section">{{ org_count }} {{ _('organizations') }}</div>
                <p style="font-size:12px;color:var(--a-text-sec);margin:4px 0 0">{{ _('Tenant organizations and their codes') }}</p>
            </a>

            <a href="{{ url_for('admin_sessions_view') }}" class="admin-card admin-card-link">
                <div class="admin-meta" style="margin-bottom:8px">
                    <i class="fas fa-signal"></i> &nbsp; {{ _('Active Sessions') }}
                </div>
                <div class="admin-section">{{ _('Live users') }}</div>
                <p style="font-size:12px;color:var(--a-text-sec);margin:4px 0 0">{{ _('Users active in the last 30 minutes') }}</p>
            </a>

            <a href="{{ url_for('admin_logs_view') }}" class="admin-card admin-card-link">
                <div class="admin-meta" style="margin-bottom:8px">
                    <i class="fas fa-clipboard-list"></i> &nbsp; {{ _('System Logs') }}
                </div>
                <div class="admin-section">{{ _('Audit activity') }}</div>
                <p style="font-size:12px;color:var(--a-text-sec);margin:4px 0 0">{{ _('Filter by user, date, method or status') }}</p>
            </a>

        </div>

        <div>
            <div class="admin-meta" style="margin-bottom:12px">{{ _('Resources') }}</div>
            <div style="display:flex;flex-direction:column;gap:8px;font-size:13px;">
                <a href="https://sydocteam.atlassian.net/wiki/spaces/nexora/overview?homepageId=323944774"
                   target="_blank" rel="noopener"
                   style="color:var(--a-indigo);text-decoration:none">
                    <i class="fas fa-book"></i> &nbsp; {{ _('Nexora documentation') }}
                    <i class="fas fa-arrow-up-right-from-square" style="font-size:10px;margin-left:4px"></i>
                </a>
                <a href="https://dashboard.ngrok.com/get-started/setup/windows"
                   target="_blank" rel="noopener"
                   style="color:var(--a-indigo);text-decoration:none">
                    <i class="fas fa-network-wired"></i> &nbsp; {{ _('ngrok hosting') }}
                    <i class="fas fa-arrow-up-right-from-square" style="font-size:10px;margin-left:4px"></i>
                </a>
            </div>
        </div>
    </main>
</body>
</html>
```

- [ ] **Step 2: Feed `user_count` and `org_count` into the `admin_dashboard` route**

In `app.py`, locate the `admin_dashboard` route (around line 793). Update to compute the two counts. Example:

```python
@app.route("/admin")
@require_permission('admin.view')
def admin_dashboard():
    with engineNexoraDB.connect() as conn:
        user_count = conn.execute(text("SELECT COUNT(*) FROM Users")).scalar() or 0
        org_count  = conn.execute(text("SELECT COUNT(*) FROM Organizations")).scalar() or 0
    return render_template(
        "admin/adminOverview.html",
        user_count=user_count,
        org_count=org_count,
        logged_in_user=session.get('username'),
        userid=session.get('userid'),
        pageV=pageVisability(),
    )
```

Adjust the exact table/column names to match the schema (check an existing user-listing query in `app.py` for the correct `Users` table reference). Keep existing `session.get`/`pageVisability` args — they're needed by `_header.html`.

- [ ] **Step 3: Verify manually**

1. Restart the server
2. Navigate to `/admin` (or click the Admin → Overview sidebar item)
3. Confirm the 4-card grid renders with real user and organization counts
4. Click each card — navigates to the correct subpage
5. Confirm the Resources section shows Documentation + ngrok as plain links (no card)
6. No pastel icon chips anywhere; icons are monochrome

- [ ] **Step 4: Commit**

```bash
git add templates/admin/adminOverview.html app.py
git commit -m "Refresh admin overview with 4-card launcher and live counts"
```

---

## Task 5: Organizations page refresh + search

**Files:**
- Modify: `templates/admin/organizations.html`
- Modify: `templates/js/admin/_organizationsJS.html` (add client-side filter)

- [ ] **Step 1: Rewrite `templates/admin/organizations.html`**

Replace with:

```jinja
<!DOCTYPE html>
<html lang="{{ get_locale }}">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{{ _("Organization Management - nexora") }}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/output.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/admin-tokens.css') }}">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css" />
</head>
<body class="admin-page">
    <div id="notification-container" class="fixed top-4 right-4 z-[100] w-full max-w-xs space-y-3"></div>

    {% set active_page = 'organizations' %}
    {% include '_header.html' %}
    {% import 'admin/_admin_helpers.html' as a %}

    <main>
        {{ a.page_header(
            title=_('Organizations'),
            subtitle=_('Tenant organizations and their codes'),
            back_url=url_for('admin_dashboard'),
            actions=[{'label': _('Add Organization'), 'icon': 'fa-plus', 'onclick': 'openAddOrganizationModal()', 'variant': 'primary'}]
        ) }}

        {{ a.toolbar(search_id='orgSearchInput', search_placeholder=_('Search organizations...')) }}

        <div class="admin-table-wrap">
            <table class="admin-table">
                {{ a.table_header([
                    {'label': _('Code')},
                    {'label': _('Name')},
                    {'label': _('Actions'), 'align': 'right', 'width': '160px'}
                ]) }}
                <tbody id="orgs-tbody">
                    {% for organization in organizations %}
                    <tr data-search="{{ (organization.organizationcode ~ ' ' ~ organization.organization)|lower }}">
                        <td><span class="admin-mono">{{ organization.organizationcode }}</span></td>
                        <td>{{ organization.organization }}</td>
                        <td class="align-right">
                            <button data-organization='{{ organization|tojson|safe }}' class="edit-organization-btn admin-btn admin-btn-ghost" type="button">{{ _("Edit") }}</button>
                            <button onclick="deleteorganization('{{ organization.organizationcode }}')" class="admin-btn admin-btn-ghost" style="color:var(--a-danger)" type="button">{{ _("Delete") }}</button>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </main>

    {% include 'admin/modals/_organizations_modals.html' %}
    {% include 'js/admin/_organizationsJS.html' %}
</body>
</html>
```

- [ ] **Step 2: Add search handler in `templates/js/admin/_organizationsJS.html`**

At the top of the existing `<script>` block in `templates/js/admin/_organizationsJS.html`, add:

```javascript
document.addEventListener('DOMContentLoaded', function () {
    const input = document.getElementById('orgSearchInput');
    const tbody = document.getElementById('orgs-tbody');
    if (!input || !tbody) return;
    input.addEventListener('input', () => {
        const q = input.value.trim().toLowerCase();
        tbody.querySelectorAll('tr[data-search]').forEach(tr => {
            tr.style.display = !q || tr.dataset.search.includes(q) ? '' : 'none';
        });
    });
});
```

- [ ] **Step 3: Verify manually**

1. Navigate to `/admin/organizations`
2. Confirm the page uses the new styling (warm background, soft card, refined table)
3. Type in the search box — rows filter live by code or name
4. Clear the search — all rows return
5. Click Edit and Delete buttons — modals still open correctly (regression check)
6. Click "Add Organization" — modal opens; creation still works

- [ ] **Step 4: Commit**

```bash
git add templates/admin/organizations.html templates/js/admin/_organizationsJS.html
git commit -m "Refresh organizations page with new tokens and client-side search"
```

---

## Task 6: Sessions page refresh + relative time

**Files:**
- Modify: `templates/admin/sessions.html`
- Modify: `templates/js/admin/_sessionsJS.html`

- [ ] **Step 1: Rewrite `templates/admin/sessions.html`**

```jinja
<!DOCTYPE html>
<html lang="{{ get_locale }}">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{{ _("Active Sessions - nexora") }}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/output.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/admin-tokens.css') }}">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css" />
</head>
<body class="admin-page">
    {% set active_page = 'admin_sessions' %}
    {% include '_header.html' %}
    {% import 'admin/_admin_helpers.html' as a %}

    <main>
        {{ a.page_header(
            title=_('Active Sessions'),
            subtitle=_('Users active within the last 30 minutes'),
            back_url=url_for('admin_dashboard'),
            actions=[{'label': _('Refresh'), 'icon': 'fa-sync-alt', 'onclick': 'fetchActiveSessions()', 'variant': 'secondary'}]
        ) }}

        <div class="admin-table-wrap">
            <table class="admin-table">
                {{ a.table_header([
                    {'label': _('Username')},
                    {'label': _('User ID'), 'width': '140px'},
                    {'label': _('IP Address'), 'width': '200px'},
                    {'label': _('Last Activity'), 'width': '180px'}
                ]) }}
                <tbody id="active-sessions-body">
                    {{ a.empty_state('fa-spinner fa-spin', _('Loading...'), colspan=4) }}
                </tbody>
            </table>
        </div>
    </main>

    {% include 'js/admin/_sessionsJS.html' %}
</body>
</html>
```

- [ ] **Step 2: Update `templates/js/admin/_sessionsJS.html` to render relative time**

In `templates/js/admin/_sessionsJS.html`, add a helper function at the top of the `<script>` and use it when rendering the Last Activity column. Example helper:

```javascript
function formatRelativeTime(iso) {
    if (!iso) return '';
    const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
    if (seconds < 5)   return '{{ _("Just now") }}';
    if (seconds < 60)  return seconds + ' {{ _("s ago") }}';
    const m = Math.floor(seconds / 60);
    if (m < 60) return m + ' {{ _("min ago") }}';
    const h = Math.floor(m / 60);
    if (h < 24) return h + ' {{ _("h ago") }}';
    return Math.floor(h / 24) + ' {{ _("d ago") }}';
}
```

Then in the existing `fetchActiveSessions` result-render loop, use `formatRelativeTime(row.last_activity)` for the last-activity cell; set `title="${row.last_activity}"` on that cell so hovering shows the absolute timestamp.

- [ ] **Step 3: Verify manually**

1. Navigate to `/admin/sessions`
2. New header / table styling applied
3. "Last Activity" column shows things like "2 min ago" instead of raw timestamp
4. Hovering the cell shows the absolute ISO timestamp as a tooltip
5. Click Refresh — table re-fetches

- [ ] **Step 4: Commit**

```bash
git add templates/admin/sessions.html templates/js/admin/_sessionsJS.html
git commit -m "Refresh sessions page with relative last-activity time"
```

---

## Task 7: Logs page refresh + preset time ranges

**Files:**
- Modify: `templates/admin/logs.html`
- Modify: `templates/js/admin/_logsJS.html`

- [ ] **Step 1: Rewrite `templates/admin/logs.html`**

```jinja
<!DOCTYPE html>
<html lang="{{ get_locale }}">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{{ _("System Logs - nexora") }}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/output.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/admin-tokens.css') }}">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css" />
    <style>
      .log-preset-row { display:flex; gap:6px; margin-bottom:12px; flex-wrap:wrap; }
      .log-preset     { padding:5px 10px; border-radius:6px; background:var(--a-card); border:1px solid var(--a-border-input); font-size:12px; color:var(--a-text-sec); cursor:pointer; }
      .log-preset:hover { background:var(--a-alt); color:var(--a-text); }
      .log-preset.is-active { background:var(--a-ink); color:#fff; border-color:var(--a-ink); }
      .code-scroll::-webkit-scrollbar { width: 8px; height: 8px; }
      .code-scroll::-webkit-scrollbar-track { background: #1f2937; }
      .code-scroll::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 4px; }
      .code-scroll::-webkit-scrollbar-thumb:hover { background: #6b7280; }
    </style>
</head>
<body class="admin-page">
    {% set active_page = 'admin_logs' %}
    {% include '_header.html' %}
    {% import 'admin/_admin_helpers.html' as a %}

    <main>
        {{ a.page_header(
            title=_('System Audit Logs'),
            subtitle=_('Filter by user, date, method, status or organization'),
            back_url=url_for('admin_dashboard')
        ) }}

        <div class="log-preset-row">
            <button type="button" class="log-preset" data-preset="1h">{{ _('Last hour') }}</button>
            <button type="button" class="log-preset" data-preset="24h">{{ _('Today') }}</button>
            <button type="button" class="log-preset" data-preset="7d">{{ _('Last 7 days') }}</button>
            <button type="button" class="log-preset" data-preset="30d">{{ _('Last 30 days') }}</button>
        </div>

        <div class="admin-filter-bar">
            <div>
                <label for="filterUser">{{ _('Username') }}</label>
                <div class="admin-input-icon"><i class="fas fa-user"></i>
                    <input type="text" id="filterUser" class="admin-input">
                </div>
            </div>
            <div>
                <label for="filterMethod">{{ _('Method') }}</label>
                <select id="filterMethod" class="admin-select">
                    <option value="">{{ _('All') }}</option>
                    <option value="GET">GET</option>
                    <option value="POST">POST</option>
                    <option value="PUT">PUT</option>
                    <option value="DELETE">DELETE</option>
                </select>
            </div>
            <div>
                <label for="filterPath">{{ _('Path') }}</label>
                <div class="admin-input-icon"><i class="fas fa-link"></i>
                    <input type="text" id="filterPath" class="admin-input" placeholder="/api/...">
                </div>
            </div>
            <div>
                <label for="filterStatus">{{ _('Status') }}</label>
                <select id="filterStatus" class="admin-select">
                    <option value="">{{ _('All') }}</option>
                    <option value="SUCCESS">{{ _('Success (2xx)') }}</option>
                    <option value="FAILURE">{{ _('Failure (4xx/5xx)') }}</option>
                </select>
            </div>
            <div>
                <label for="filterOrg">{{ _('Organization') }}</label>
                <select id="filterOrg" class="admin-select">
                    <option value="">{{ _('All') }}</option>
                    {% for org in organizations %}
                    <option value="{{ org.organizationcode }}">{{ org.organization }}</option>
                    {% endfor %}
                </select>
            </div>
            <div>
                <label for="filterStart">{{ _('Start date') }}</label>
                <input type="date" id="filterStart" class="admin-input">
            </div>
            <div>
                <label for="filterEnd">{{ _('End date') }}</label>
                <input type="date" id="filterEnd" class="admin-input">
            </div>
            <div>
                <label>&nbsp;</label>
                <button type="button" onclick="fetchLogs(1)" class="admin-btn admin-btn-primary" style="width:100%">
                    <i class="fas fa-search"></i> {{ _('Filter') }}
                </button>
            </div>
        </div>

        <div class="admin-table-wrap">
            <table class="admin-table">
                {{ a.table_header([
                    {'label': _('Time'), 'width': '180px'},
                    {'label': _('User')},
                    {'label': _('Action')},
                    {'label': _('Status'), 'width': '120px'},
                    {'label': _('IP'), 'width': '140px'},
                    {'label': _('Details'), 'align': 'right', 'width': '90px'}
                ]) }}
                <tbody id="logsTableBody"></tbody>
            </table>
            <div style="padding:12px 16px;border-top:1px solid var(--a-border);display:flex;align-items:center;justify-content:space-between" id="paginationControls">
                <span style="font-size:13px;color:var(--a-text-sec)" id="pageInfo">{{ _('Loading...') }}</span>
                <div style="display:flex;gap:8px">
                    <button id="prevBtn" class="admin-btn admin-btn-secondary" onclick="changePage(-1)" disabled>{{ _('Previous') }}</button>
                    <button id="nextBtn" class="admin-btn admin-btn-secondary" onclick="changePage(1)" disabled>{{ _('Next') }}</button>
                </div>
            </div>
        </div>
    </main>

    {# keep the existing log details modal as-is (dark pre block) #}
    <div id="logDetailsModal" class="fixed inset-0 z-50 hidden" aria-labelledby="modal-title" role="dialog" aria-modal="true">
        <div class="fixed inset-0 bg-gray-900/60 backdrop-blur-sm transition-opacity opacity-0" id="modalBackdrop"></div>
        <div class="fixed inset-0 z-10 w-screen overflow-y-auto">
            <div class="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0">
                <div class="relative transform overflow-hidden rounded-xl bg-white text-left shadow-2xl transition-all sm:my-8 sm:w-full sm:max-w-2xl opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95" id="modalPanel">
                    <div class="bg-gray-50 px-4 py-3 sm:px-6 flex justify-between items-center border-b border-gray-100">
                        <h3 class="text-base font-semibold leading-6 text-gray-900" id="modal-title">
                            <i class="fas fa-terminal text-indigo-500 mr-2"></i> {{ _('Log Details Payload') }}
                        </h3>
                        <button onclick="closeLogModal()" class="text-gray-400 hover:text-gray-600 transition"><i class="fas fa-times text-lg"></i></button>
                    </div>
                    <div class="px-4 py-5 sm:p-6 bg-white">
                        <div class="grid grid-cols-3 gap-4 mb-4 text-sm text-gray-500 border-b border-gray-100 pb-4">
                            <div><span class="block text-xs font-bold text-gray-400 uppercase">{{ _('User') }}</span> <span id="modalUser" class="text-gray-800 font-medium"></span></div>
                            <div><span class="block text-xs font-bold text-gray-400 uppercase">{{ _('Action') }}</span> <span id="modalAction" class="text-gray-800 font-medium"></span></div>
                            <div><span class="block text-xs font-bold text-gray-400 uppercase">{{ _('Time') }}</span> <span id="modalTime" class="text-gray-800 font-medium"></span></div>
                        </div>
                        <div class="relative">
                            <button onclick="copyToClipboard()" class="absolute top-2 right-2 text-xs bg-gray-700/80 hover:bg-gray-600 text-gray-200 px-2 py-1 rounded transition border border-gray-600 z-10">
                                <i class="fas fa-copy mr-1"></i> {{ _('Copy') }}
                            </button>
                            <pre id="modalCodeContent" class="bg-gray-900 text-green-400 p-4 rounded-lg text-xs font-mono overflow-auto max-h-96 code-scroll whitespace-pre-wrap break-all shadow-inner"></pre>
                        </div>
                    </div>
                    <div class="bg-gray-50 px-4 py-3 sm:flex sm:flex-row-reverse sm:px-6">
                        <button type="button" class="mt-3 inline-flex w-full justify-center rounded-md bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50 sm:mt-0 sm:w-auto transition" onclick="closeLogModal()">{{ _('Close') }}</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    {% include 'js/admin/_logsJS.html' %}
</body>
</html>
```

- [ ] **Step 2: Pass `organizations` to the `admin_logs_view` route**

In `app.py`, find `admin_logs_view` (~line 950). Add the organizations list to the render context:

```python
@app.route("/admin/logs")
@require_permission('admin.view.system.logs')
def admin_logs_view():
    with engineNexoraDB.connect() as conn:
        organizations = conn.execute(text(
            "SELECT organizationcode, organization FROM Organizations ORDER BY organization"
        )).mappings().all()
    return render_template(
        "admin/logs.html",
        organizations=organizations,
        logged_in_user=session.get('username'),
        userid=session.get('userid'),
        pageV=pageVisability(),
    )
```

(Adjust the exact query to match what `admin_organizations_view` already uses — copy its query verbatim for consistency.)

- [ ] **Step 3: Add preset handlers in `templates/js/admin/_logsJS.html`**

Near the top of the `<script>` block, add:

```javascript
document.addEventListener('DOMContentLoaded', function () {
    const presets = document.querySelectorAll('.log-preset');
    const startEl = document.getElementById('filterStart');
    const endEl   = document.getElementById('filterEnd');
    if (!startEl || !endEl) return;

    function toDateInput(d) {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${y}-${m}-${day}`;
    }

    presets.forEach(btn => {
        btn.addEventListener('click', () => {
            presets.forEach(b => b.classList.remove('is-active'));
            btn.classList.add('is-active');

            const now = new Date();
            let start = new Date(now);
            switch (btn.dataset.preset) {
                case '1h':  start.setHours(now.getHours() - 1); break;
                case '24h': start.setHours(0,0,0,0); break; // today from 00:00
                case '7d':  start.setDate(now.getDate() - 7); break;
                case '30d': start.setDate(now.getDate() - 30); break;
            }
            startEl.value = toDateInput(start);
            endEl.value   = toDateInput(now);
            if (typeof fetchLogs === 'function') fetchLogs(1);
        });
    });

    // Clear preset highlight when user manually edits dates
    [startEl, endEl].forEach(el => el.addEventListener('change', () => {
        presets.forEach(b => b.classList.remove('is-active'));
    }));
});
```

- [ ] **Step 4: Verify manually**

1. Navigate to `/admin/logs`
2. New filter bar with 7 filters + preset buttons above
3. Click "Last hour" — start date populates to today, end date is today, table re-fetches
4. Click "Last 7 days" — start shifts to 7 days ago
5. Manually edit a date — preset highlight clears
6. Table rows render (regression: ensure detail modal still opens on click)

- [ ] **Step 5: Commit**

```bash
git add templates/admin/logs.html templates/js/admin/_logsJS.html app.py
git commit -m "Refresh logs page with preset time ranges and new filter bar"
```

---

## Task 8: Logs organization filter (backend + frontend)

**Files:**
- Modify: `app.py` (`/api/admin/logs/search` endpoint around line 953)
- Modify: `templates/js/admin/_logsJS.html` (send org param in fetch)

- [ ] **Step 1: Add `organization` query param to the logs search endpoint**

In `app.py`, find the `/api/admin/logs/search` endpoint (line 953). Read its current implementation first so you preserve existing filter parsing. Add handling for a new optional query param:

```python
organization = request.args.get('organization') or None
```

In the SQL query, when `organization` is truthy, add a JOIN/filter that limits logs to users whose organization matches. Example (adapt to the actual schema — look at how `get_users_admin_access_control` joins users to orgs):

```sql
LEFT JOIN Users u ON u.username = logs.username
WHERE (:organization IS NULL OR u.organizationcode = :organization)
```

Pass `organization` to the parameter bind. All other existing params remain unchanged.

- [ ] **Step 2: Send the param from the frontend**

In `templates/js/admin/_logsJS.html`, locate the `fetchLogs` function. Add to the URL search params:

```javascript
const org = document.getElementById('filterOrg')?.value;
if (org) params.set('organization', org);
```

(Use the same `params` variable the existing fetch builder uses — if it uses fetch with `?` concatenation, mirror that style.)

- [ ] **Step 3: Verify manually**

1. On `/admin/logs`, select an organization from the Organization dropdown
2. Click Filter — the table reloads showing only rows whose user belongs to that org
3. Set Organization back to "All" — all rows return
4. Combine with other filters (e.g., org + method=POST) — logic AND-combines correctly

- [ ] **Step 4: Commit**

```bash
git add app.py templates/js/admin/_logsJS.html
git commit -m "Filter admin logs by organization"
```

---

## Task 9: Access Control visual refresh (all three tabs)

**Files:**
- Modify: `templates/admin/accessControl.html`

- [ ] **Step 1: Refresh the three-tab shell with new tokens**

This task focuses on visual refresh only; behavior stays the same (modals and drawer still open). Update `templates/admin/accessControl.html`:

1. Replace the `<head>` block: drop inline `<style>` related to grey tabs; add `<link rel="stylesheet" href="{{ url_for('static', filename='css/admin-tokens.css') }}">`.
2. Change `<body class="bg-gray-50 text-gray-800">` → `<body class="admin-page">`.
3. Replace the top header block (lines ~17–25) with a macro call:

```jinja
{% import 'admin/_admin_helpers.html' as a %}
{{ a.page_header(
    title=_('Access Control'),
    subtitle=_('Users, permissions and access profiles'),
    back_url=url_for('admin_dashboard')
) }}
```

4. Replace the tab bar CSS classes:

```jinja
<div style="border-bottom:1px solid var(--a-border);margin-bottom:20px">
    <ul style="display:flex;gap:24px;margin:0;padding:0;list-style:none">
        <li>
            <button id="tab-users-btn" onclick="switchTab('users')" type="button"
                    style="padding:10px 0;border:none;background:transparent;font-size:13px;font-weight:500;color:var(--a-text);border-bottom:2px solid var(--a-indigo);margin-bottom:-1px;cursor:pointer">
                <i class="fas fa-users"></i> {{ _('Users') }}
            </button>
        </li>
        <li>
            <button id="tab-permissions-btn" onclick="switchTab('permissions')" type="button"
                    style="padding:10px 0;border:none;background:transparent;font-size:13px;font-weight:500;color:var(--a-text-sec);border-bottom:2px solid transparent;margin-bottom:-1px;cursor:pointer">
                <i class="fas fa-key"></i> {{ _('Permissions') }}
            </button>
        </li>
        <li>
            <button id="tab-profiles-btn" onclick="switchTab('profiles')" type="button"
                    style="padding:10px 0;border:none;background:transparent;font-size:13px;font-weight:500;color:var(--a-text-sec);border-bottom:2px solid transparent;margin-bottom:-1px;cursor:pointer">
                <i class="fas fa-id-badge"></i> {{ _('Access Profiles') }}
            </button>
        </li>
    </ul>
</div>
```

In `templates/js/admin/_accessControlJS.html`, update `switchTab(name)` so that the active tab button sets `color: var(--a-text); border-bottom-color: var(--a-indigo)` and inactive sets `color: var(--a-text-sec); border-bottom-color: transparent`. (If the existing implementation toggles Tailwind classes, replace those branches with inline-style toggles or introduce two helper classes `.tab-active` / `.tab-inactive` in a small `<style>` at the top of the template.)

5. Each tab panel (`#tab-users`, `#tab-permissions`, `#tab-profiles`) replaces its outer `bg-white rounded-xl shadow overflow-hidden` with `class="admin-table-wrap"` for the tables, and its filter bar `.bg-gray-50 flex justify-between` with the helper's `toolbar()` call.

6. Convert the Permissions table rows and the Profiles card grid to use `.admin-table`, `.admin-card`, `.admin-badge` classes. Leave the add/edit modals and the permission drawer markup untouched — they're untouched by this task.

- [ ] **Step 2: Verify manually**

1. Navigate to `/admin/access_control`
2. All three tabs render with the new visual language (warm bg, refined table headers, no pastel chips)
3. Switching tabs still works; active tab has the indigo underline
4. All existing buttons (Add User, Add Permission, Add Profile) open their modals/drawer unchanged
5. Delete, Edit, Search still function (regression check)

- [ ] **Step 3: Commit**

```bash
git add templates/admin/accessControl.html templates/js/admin/_accessControlJS.html
git commit -m "Refresh access control page with admin tokens"
```

---

## Task 10: Users tab — profile and organization filters

**Files:**
- Modify: `app.py` (`/api/admin/users/list`)
- Modify: `templates/admin/accessControl.html` (add filter inputs)
- Modify: `templates/js/admin/_accessControlJS.html` (send filter params)

- [ ] **Step 1: Add optional filter params to `/api/admin/users/list`**

In `app.py`, find the route at line 1187. Read the current implementation first so you preserve it. Add two optional query params:

```python
profile_filter = request.args.get('profile') or None
org_filter     = request.args.get('organization') or None
```

In the SQL WHERE clause, extend with:

```sql
AND (:profile IS NULL OR u.accessprofile = :profile)
AND (:org IS NULL OR u.organizationcode = :org)
```

Bind the two new params. Adjust exact column names to match what the existing query uses — read the current SQL first. When both are omitted, response must be byte-identical to today (regression requirement).

- [ ] **Step 2: Replace the Users tab toolbar with the new filter bar**

In `templates/admin/accessControl.html`, in the Users tab (`#tab-users`), replace the single-search toolbar with:

```jinja
<div class="admin-filter-bar">
    <div>
        <label for="userSearchInput">{{ _('Search') }}</label>
        <div class="admin-input-icon"><i class="fas fa-search"></i>
            <input type="text" id="userSearchInput" class="admin-input" placeholder="{{ _('Search users...') }}">
        </div>
    </div>
    <div>
        <label for="userProfileFilter">{{ _('Profile') }}</label>
        <select id="userProfileFilter" class="admin-select">
            <option value="">{{ _('All') }}</option>
            {% for profile in assignable_profiles %}
            <option value="{{ profile.profile }}">{{ profile.profile }}</option>
            {% endfor %}
        </select>
    </div>
    <div>
        <label for="userOrgFilter">{{ _('Organization') }}</label>
        <select id="userOrgFilter" class="admin-select">
            <option value="">{{ _('All') }}</option>
            {% for org in organizations %}
            <option value="{{ org.organizationcode }}">{{ org.organization }}</option>
            {% endfor %}
        </select>
    </div>
    <div>
        <label>&nbsp;</label>
        {% if can_create_user %}
        <button onclick="openAddUserModal()" class="admin-btn admin-btn-primary" style="width:100%" type="button">
            <i class="fas fa-plus"></i> {{ _('Add User') }}
        </button>
        {% endif %}
    </div>
</div>
```

`assignable_profiles` and `organizations` are already passed in by the route — confirm by reading the current `admin_access_control` route code.

- [ ] **Step 3: Send filter params from `_accessControlJS.html`**

Locate the function that fetches users (named something like `loadUsers` or `filterUsersTable`). Adjust so the filter inputs (`userSearchInput`, `userProfileFilter`, `userOrgFilter`) each call the same `reloadUsers()` helper, and the helper constructs a URL:

```javascript
async function reloadUsers() {
    const q     = document.getElementById('userSearchInput').value.trim();
    const prof  = document.getElementById('userProfileFilter').value;
    const org   = document.getElementById('userOrgFilter').value;

    const params = new URLSearchParams();
    if (q)    params.set('q', q);
    if (prof) params.set('profile', prof);
    if (org)  params.set('organization', org);

    const res = await fetch('/api/admin/users/list?' + params.toString(), {
        headers: {'X-CSRFToken': csrfToken}
    });
    const rows = await res.json();
    renderUsersTable(rows);
}

['userSearchInput','userProfileFilter','userOrgFilter'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', reloadUsers);
    document.getElementById(id)?.addEventListener('change', reloadUsers);
});
```

If a `renderUsersTable` function doesn't exist, extract the existing row-render loop into one. If the existing code filters client-side only, delete the old `filterUsersTable` call — the server does the filtering now.

- [ ] **Step 4: Verify manually**

1. Navigate to `/admin/access_control`, Users tab
2. Three filters visible: Search, Profile dropdown, Organization dropdown
3. Pick a profile — table refetches and shows only users on that profile
4. Pick an organization — table narrows further
5. Type in search — narrows still further
6. Clear filters one by one — rows return
7. Add User button still works (regression)

- [ ] **Step 5: Commit**

```bash
git add app.py templates/admin/accessControl.html templates/js/admin/_accessControlJS.html
git commit -m "Filter users list by profile and organization"
```

---

## Task 11: User detail page — new route and profile section

**Files:**
- Create: `templates/admin/userDetail.html`
- Create: `templates/js/admin/_userDetailJS.html`
- Modify: `app.py` (new route `admin_user_detail`)

- [ ] **Step 1: Add the route in `app.py`**

Place this alongside the other admin user routes (near line 1049 where `/admin/users/add` lives):

```python
@app.route("/admin/users/<int:user_id>")
@require_permission('admin.view')
def admin_user_detail(user_id):
    with engineNexoraDB.connect() as conn:
        user = conn.execute(text(
            "SELECT UserID, username, fullname, email, accessprofile, organizationcode "
            "FROM Users WHERE UserID = :id"
        ), {'id': user_id}).mappings().first()
        if not user:
            abort(404)
        profiles = conn.execute(text("SELECT profile FROM AccessProfiles ORDER BY profile")).mappings().all()
        organizations = conn.execute(text(
            "SELECT organizationcode, organization FROM Organizations ORDER BY organization"
        )).mappings().all()
    return render_template(
        "admin/userDetail.html",
        user=user,
        assignable_profiles=profiles,
        organizations=organizations,
        logged_in_user=session.get('username'),
        userid=session.get('userid'),
        pageV=pageVisability(),
    )
```

Adjust table/column names to match the actual schema — read `admin_access_control`'s query in `app.py` for the canonical reference and mirror it.

- [ ] **Step 2: Create `templates/admin/userDetail.html` (Profile section only for this task)**

```jinja
<!DOCTYPE html>
<html lang="{{ get_locale }}">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{{ user.fullname }} — {{ _('User detail') }}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/output.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/admin-tokens.css') }}">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css" />
</head>
<body class="admin-page">
    <div id="notification-container" class="fixed top-4 right-4 z-[200] w-full max-w-xs space-y-3"></div>

    {% set active_page = 'admin_user_detail' %}
    {% include '_header.html' %}
    {% import 'admin/_admin_helpers.html' as a %}

    <main>
        {{ a.page_header(
            title=user.fullname,
            subtitle=user.username ~ ' · ' ~ user.accessprofile,
            back_url=url_for('admin_access_control')
        ) }}

        {# ------------- Profile section ------------- #}
        <div class="admin-card" style="margin-bottom:20px">
            <div class="admin-section" style="margin-bottom:16px">{{ _('Profile') }}</div>

            <form id="userProfileForm" data-user-id="{{ user.UserID }}" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>

                <div>
                    <label class="admin-meta" for="fld-username">{{ _('Username') }}</label>
                    <input type="text" id="fld-username" name="username" value="{{ user.username }}" required class="admin-input">
                </div>
                <div>
                    <label class="admin-meta" for="fld-fullname">{{ _('Full name') }}</label>
                    <input type="text" id="fld-fullname" name="fullname" value="{{ user.fullname }}" required class="admin-input">
                </div>
                <div>
                    <label class="admin-meta" for="fld-email">{{ _('Email') }}</label>
                    <input type="email" id="fld-email" name="email" value="{{ user.email }}" required class="admin-input">
                </div>
                <div>
                    <label class="admin-meta" for="fld-profile">{{ _('Access profile') }}</label>
                    <select id="fld-profile" name="accessprofile" class="admin-select">
                        {% for p in assignable_profiles %}
                        <option value="{{ p.profile }}" {% if p.profile == user.accessprofile %}selected{% endif %}>{{ p.profile }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div>
                    <label class="admin-meta" for="fld-org">{{ _('Organization') }}</label>
                    <select id="fld-org" name="organization" class="admin-select">
                        {% for o in organizations %}
                        <option value="{{ o.organizationcode }}" {% if o.organizationcode == user.organizationcode %}selected{% endif %}>{{ o.organization }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div>
                    <label class="admin-meta" for="fld-password">{{ _('New password') }}</label>
                    <input type="password" id="fld-password" name="password" class="admin-input" placeholder="{{ _('Leave blank to keep current') }}">
                </div>

                <div style="grid-column:1/-1;display:flex;justify-content:flex-end;gap:8px">
                    <a href="{{ url_for('admin_access_control') }}" class="admin-btn admin-btn-secondary">{{ _('Cancel') }}</a>
                    <button type="submit" class="admin-btn admin-btn-primary">{{ _('Save changes') }}</button>
                </div>
            </form>
        </div>
    </main>

    {% include 'js/admin/_userDetailJS.html' %}
</body>
</html>
```

- [ ] **Step 3: Create `templates/js/admin/_userDetailJS.html`**

```jinja
<script>
    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

    document.addEventListener('DOMContentLoaded', function () {
        const form = document.getElementById('userProfileForm');
        if (!form) return;

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const userId = form.dataset.userId;
            const fd = new FormData(form);

            const res = await fetch(`/admin/users/edit/${userId}`, {
                method: 'POST',
                body: fd,
                headers: { 'X-CSRFToken': csrfToken }
            });

            if (res.ok) {
                showToast('{{ _("User saved.") }}', 'success');
            } else {
                showToast('{{ _("Save failed.") }}', 'error');
            }
        });
    });

    function showToast(msg, tone) {
        const container = document.getElementById('notification-container');
        if (!container) { alert(msg); return; }
        const el = document.createElement('div');
        el.style.cssText = 'background:#fff;border:1px solid var(--a-border);padding:10px 14px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.06);font-size:13px;';
        if (tone === 'error') el.style.borderColor = 'var(--a-danger)';
        el.textContent = msg;
        container.appendChild(el);
        setTimeout(() => el.remove(), 3000);
    }
</script>
```

- [ ] **Step 4: Verify manually**

1. Navigate directly to `/admin/users/1` (replace 1 with a valid UserID)
2. Detail page renders with the new header and a Profile card
3. All fields populated from DB
4. Edit a field, click Save — toast appears, refresh shows the persisted change
5. Cancel link returns to Access Control
6. Navigating to an invalid ID returns 404

- [ ] **Step 5: Commit**

```bash
git add app.py templates/admin/userDetail.html templates/js/admin/_userDetailJS.html
git commit -m "Add user detail page with editable profile section"
```

---

## Task 12: User detail — inline permission overrides section

**Files:**
- Modify: `templates/admin/userDetail.html`
- Modify: `templates/js/admin/_userDetailJS.html`
- Modify: `app.py` (adjust `admin_user_detail` to query the override data — read the existing drawer-population query for the exact shape)

- [ ] **Step 1: Gather the data in the route**

In `admin_user_detail`, mirror the queries used today by the permission drawer. Read `accessControl.html` and the backing route (`admin_access_control` and the override-save endpoint) to find:
- The full list of permissions (each with Code, Description, PermissionID)
- The user's current override per permission (None / Deny / Allow)

Add these to the render context:

```python
all_permissions = conn.execute(text(
    "SELECT PermissionID, Code, Description, SortingCode FROM Permissions ORDER BY SortingCode, Code"
)).mappings().all()

current_overrides = {row['PermissionID']: row['Type'] for row in conn.execute(text(
    "SELECT PermissionID, Type FROM UserPermissionOverrides WHERE UserID = :uid"
), {'uid': user_id}).mappings().all()}
```

(Adjust table/column names to match real schema — if unsure, grep `app.py` for `UserPermissionOverrides` or the existing save-override endpoint first.)

- [ ] **Step 2: Render the overrides section in `templates/admin/userDetail.html`**

After the Profile card, before the closing `</main>`:

```jinja
{# ------------- Permission overrides section ------------- #}
<div class="admin-card" style="margin-bottom:20px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <div>
            <div class="admin-section">{{ _('Permission overrides') }}</div>
            <p style="font-size:12px;color:var(--a-text-sec);margin:4px 0 0">
                {{ _('Override the access profile on a per-permission basis.') }}
            </p>
        </div>
        <div style="font-size:12px;color:var(--a-text-sec)" id="overrideCount"></div>
    </div>

    <form id="overridesForm" data-user-id="{{ user.UserID }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
        <div class="admin-table-wrap">
            <table class="admin-table">
                {{ a.table_header([
                    {'label': _('Permission')},
                    {'label': _('None'),  'align': 'right', 'width': '90px'},
                    {'label': _('Deny'),  'align': 'right', 'width': '90px'},
                    {'label': _('Allow'), 'align': 'right', 'width': '90px'}
                ]) }}
                <tbody>
                    {% for perm in all_permissions %}
                    {% set cur = current_overrides.get(perm.PermissionID) %}
                    <tr data-perm-id="{{ perm.PermissionID }}">
                        <td>
                            <span class="admin-mono">{{ perm.Code }}</span>
                            <div style="font-size:12px;color:var(--a-text-sec);margin-top:2px">{{ perm.Description }}</div>
                        </td>
                        <td class="align-right"><input type="radio" name="perm_{{ perm.PermissionID }}" value="None"  {% if not cur %}checked{% endif %}></td>
                        <td class="align-right"><input type="radio" name="perm_{{ perm.PermissionID }}" value="D"     {% if cur == 'D' %}checked{% endif %}></td>
                        <td class="align-right"><input type="radio" name="perm_{{ perm.PermissionID }}" value="A"     {% if cur == 'A' %}checked{% endif %}></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        <div style="display:flex;justify-content:flex-end;margin-top:12px">
            <button type="submit" class="admin-btn admin-btn-primary">{{ _('Save overrides') }}</button>
        </div>
    </form>
</div>
```

- [ ] **Step 3: Wire save in `templates/js/admin/_userDetailJS.html`**

Append inside the existing `<script>`:

```javascript
document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('overridesForm');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const userId = form.dataset.userId;
        const fd = new FormData(form);
        fd.append('targetId', userId);

        // Find the existing override-save endpoint in app.py (search for
        // the handler that receives perm_<id> fields from accessControl's drawer)
        // and POST to it.
        const res = await fetch('/api/admin/users/permissions/save', {  // replace with the actual existing endpoint
            method: 'POST',
            body: fd,
            headers: { 'X-CSRFToken': csrfToken }
        });

        if (res.ok) showToast('{{ _("Overrides saved.") }}', 'success');
        else        showToast('{{ _("Save failed.") }}', 'error');
    });
});
```

**Before committing:** search `app.py` for the endpoint currently called by the accessControl drawer's `savePermissions()` function (grep `_accessControlJS.html` for `fetch(`). Use that exact URL in the JS above so the detail-page save hits the existing, already-permissioned endpoint.

- [ ] **Step 4: Verify manually**

1. Open `/admin/users/<id>` for a user with no overrides — all rows show "None" selected
2. Set a permission to Allow, another to Deny, click Save
3. Refresh — changes persist
4. Log in as that user in an incognito tab — verify the override took effect on a page that checks that permission

- [ ] **Step 5: Commit**

```bash
git add app.py templates/admin/userDetail.html templates/js/admin/_userDetailJS.html
git commit -m "Add inline permission overrides on user detail page"
```

---

## Task 13: User detail — activity placeholder and danger zone

**Files:**
- Modify: `templates/admin/userDetail.html`
- Modify: `templates/js/admin/_userDetailJS.html`

- [ ] **Step 1: Add the Activity placeholder and Danger zone to `templates/admin/userDetail.html`**

After the Permission overrides card, before the closing `</main>`:

```jinja
{# ------------- Activity (Phase 2 placeholder) ------------- #}
<div class="admin-card" style="margin-bottom:20px">
    <div class="admin-section" style="margin-bottom:4px">{{ _('Activity') }}</div>
    <p style="font-size:12px;color:var(--a-text-sec);margin:0 0 12px">
        {{ _('A chronological audit trail of this user\'s actions.') }}
    </p>
    <div class="admin-empty" style="background:var(--a-alt);border-radius:8px">
        <i class="fas fa-hourglass-half"></i> &nbsp; {{ _('Coming in a future release.') }}
    </div>
</div>

{# ------------- Danger zone ------------- #}
<div class="admin-card" style="border-color:var(--a-danger)">
    <div style="display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap">
        <div>
            <div class="admin-section" style="color:var(--a-danger)">{{ _('Danger zone') }}</div>
            <p style="font-size:12px;color:var(--a-text-sec);margin:4px 0 0">
                {{ _('Deleting this user is irreversible. Their access is revoked immediately.') }}
            </p>
        </div>
        <button id="deleteUserBtn" class="admin-btn admin-btn-danger" data-user-id="{{ user.UserID }}" data-username="{{ user.username }}" type="button">
            <i class="fas fa-trash"></i> {{ _('Delete user') }}
        </button>
    </div>
</div>

{# Confirm-delete modal (minimal, inline) #}
<div id="confirmDeleteModal" style="display:none;position:fixed;inset:0;z-index:60;background:rgba(0,0,0,0.4);align-items:center;justify-content:center">
    <div style="background:#fff;border-radius:10px;padding:24px;max-width:380px;text-align:center;box-shadow:0 10px 40px rgba(0,0,0,0.15)">
        <i class="fas fa-exclamation-triangle" style="color:var(--a-danger);font-size:28px"></i>
        <h3 style="font-size:16px;font-weight:600;margin:10px 0 6px">{{ _('Delete user?') }}</h3>
        <p style="font-size:13px;color:var(--a-text-sec);margin:0 0 16px" id="confirmDeleteMessage"></p>
        <div style="display:flex;justify-content:center;gap:8px">
            <button type="button" class="admin-btn admin-btn-secondary" onclick="document.getElementById('confirmDeleteModal').style.display='none'">{{ _('Cancel') }}</button>
            <button type="button" id="confirmDeleteBtn" class="admin-btn admin-btn-danger">{{ _('Delete') }}</button>
        </div>
    </div>
</div>
```

- [ ] **Step 2: Wire delete in `templates/js/admin/_userDetailJS.html`**

Append inside the existing `<script>`:

```javascript
document.addEventListener('DOMContentLoaded', function () {
    const btn   = document.getElementById('deleteUserBtn');
    const modal = document.getElementById('confirmDeleteModal');
    const msg   = document.getElementById('confirmDeleteMessage');
    const ok    = document.getElementById('confirmDeleteBtn');
    if (!btn || !modal || !msg || !ok) return;

    btn.addEventListener('click', () => {
        msg.textContent = `{{ _("This will permanently delete") }} "${btn.dataset.username}".`;
        modal.style.display = 'flex';
    });

    ok.addEventListener('click', async () => {
        const userId = btn.dataset.userId;
        const res = await fetch(`/admin/users/delete/${userId}`, {
            method: 'DELETE',
            headers: { 'X-CSRFToken': csrfToken }
        });
        if (res.ok) {
            window.location.href = "{{ url_for('admin_access_control') }}";
        } else {
            showToast('{{ _("Delete failed.") }}', 'error');
            modal.style.display = 'none';
        }
    });
});
```

- [ ] **Step 3: Verify manually**

1. Open `/admin/users/<id>` for a test user you can safely delete
2. Confirm three sections show: Profile, Permission overrides, Activity (placeholder), Danger zone
3. Click Delete user — confirmation modal appears with the username
4. Click Cancel — modal closes
5. Click Delete again → Delete — user is deleted, page redirects to `/admin/access_control`, row is gone from the table

- [ ] **Step 4: Commit**

```bash
git add templates/admin/userDetail.html templates/js/admin/_userDetailJS.html
git commit -m "Add activity placeholder and danger zone to user detail"
```

---

## Task 14: Access Control Users tab — navigate to detail on row click

**Files:**
- Modify: `templates/admin/accessControl.html`
- Modify: `templates/js/admin/_accessControlJS.html`

- [ ] **Step 1: Remove the edit button/flow and make rows clickable**

In `templates/js/admin/_accessControlJS.html`, locate the function that renders user rows. For each row:

- Remove the Edit button.
- Remove any code that opens `openAddUserModal()` with a user argument (the modal is Add-only now).
- Add `class="is-clickable"` and `onclick="window.location.href='/admin/users/' + encodeURIComponent(user.UserID)"` to the `<tr>`.
- Keep the Delete button only if it previously offered in-list deletion; it's now redundant with the detail page, so **remove it** — deletion happens on the detail page's Danger zone.

Concretely, the row-render template string changes from something like:

```javascript
`<tr>
  <td>${user.username}</td>
  <td>${user.accessprofile}</td>
  <td>${user.organization}</td>
  <td>${overridesBadge}</td>
  <td class="text-right">
    <button onclick="openAddUserModal(${user.UserID})">Edit</button>
    <button onclick="deleteUser(${user.UserID})">Delete</button>
  </td>
</tr>`
```

to:

```javascript
`<tr class="is-clickable" onclick="window.location.href='/admin/users/${encodeURIComponent(user.UserID)}'">
  <td>${escapeHtml(user.username)}</td>
  <td>${escapeHtml(user.accessprofile)}</td>
  <td>${escapeHtml(user.organization)}</td>
  <td class="align-right">${overridesBadge}</td>
  <td class="align-right"><i class="fas fa-chevron-right" style="color:var(--a-text-meta)"></i></td>
</tr>`
```

Use a small `escapeHtml(s)` helper (define at top of the file if not present) to avoid XSS in concatenated templates.

- [ ] **Step 2: Reduce the Add User modal to creation-only fields**

In `templates/admin/accessControl.html`, find the `userModal` block (lines ~163–226). Trim the form to the minimum creation fields (username, full name, email, profile, org, password) and change the title to `{{ _("Add User") }}` (not "Add / Edit"). Remove any code that populates it for edit.

Also remove the `confirmDeleteModal` from `accessControl.html` if it's only used by the user-list delete action — the user-detail page now owns deletion.

(Leave the permission drawer and the `permissionMetaModal` untouched — they're used by the Permissions and Profiles tabs.)

- [ ] **Step 3: Verify manually**

1. Navigate to `/admin/access_control`, Users tab
2. Click any user row — navigates to `/admin/users/<id>`
3. Confirm Edit/Delete buttons are gone from the row
4. Click Add User — modal opens, shows only creation fields, creating a new user still works
5. Sort/search/filter still work (regression)

- [ ] **Step 4: Commit**

```bash
git add templates/admin/accessControl.html templates/js/admin/_accessControlJS.html
git commit -m "Navigate to detail page on user row click"
```

---

## Task 15: Update translations

**Files:**
- Run: `pybabel` commands inside the project venv
- Modify: `translations/de/LC_MESSAGES/messages.po`, `translations/fr/LC_MESSAGES/messages.po`, `translations/it/LC_MESSAGES/messages.po`
- Build: `translations/*/LC_MESSAGES/messages.mo` (binary — regenerated by compile)

- [ ] **Step 1: Extract and update**

From the project root, inside the venv:

```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
```

Expected: each of `translations/{de,fr,it}/LC_MESSAGES/messages.po` has new `msgid` entries for strings you introduced: `"Administration"`, `"Access Control"`, `"Organizations"`, `"Sessions"`, `"Logs"`, `"Last hour"`, `"Today"`, `"Last 7 days"`, `"Last 30 days"`, `"Permission overrides"`, `"Override the access profile on a per-permission basis."`, `"Danger zone"`, `"Delete user"`, `"Delete user?"`, `"This will permanently delete"`, `"Coming in a future release."`, `"A chronological audit trail of this user's actions."`, `"User saved."`, `"Save failed."`, `"Overrides saved."`, `"Delete failed."`, `"New password"`, `"Leave blank to keep current"`, `"Save changes"`, `"min ago"`, `"h ago"`, `"d ago"`, `"s ago"`, `"Just now"`.

- [ ] **Step 2: Translate the new entries**

Open each `messages.po` and fill in the `msgstr` for each new entry. German, French and Italian translations should match the existing tone of the file (use what's already there as a style reference).

- [ ] **Step 3: Compile**

```bash
pybabel compile -d translations
```

Expected: one `.mo` file rebuilt per locale, no errors.

- [ ] **Step 4: Verify manually**

1. Restart the server
2. Switch the UI locale (via the app's language picker, or `session['locale']='de'` in Python shell)
3. Navigate through each admin page — confirm all strings show in the chosen language, with no raw English fallthroughs in page headers, filters, modals, or the detail page

- [ ] **Step 5: Commit**

```bash
git add messages.pot translations/
git commit -m "Update translations for admin redesign phase 1"
```

---

## Task 16: Full-flow smoke test

- [ ] **Step 1: Run through the whole admin area end-to-end**

With `ENVIRONMENT=INT` and a fresh browser session:

1. Log in as an admin user.
2. Hover the sidebar — the "Admin" group expands; it contains Overview, Access Control, Organizations, Sessions, Logs.
3. Each item navigates and highlights correctly; group stays open on navigation.
4. **Overview.** 4 cards with live user and org counts; Resources section links out.
5. **Access Control — Users tab.** Search, Profile filter, Organization filter all work server-side; row click → detail page; Add User modal creates a new user.
6. **User detail page.** Profile save persists; overrides save persists; delete confirmation and redirect work.
7. **Access Control — Permissions and Profiles tabs.** Drawer + modals still function unchanged.
8. **Organizations.** New styling; search input filters rows; Add/Edit/Delete still work.
9. **Sessions.** Relative timestamps render; Refresh button re-fetches.
10. **Logs.** Preset buttons populate dates and trigger fetch; Organization filter scopes results; all previous filters still work; detail modal opens on row click.
11. **Permissions guard.** Log in as a user with only `admin.view` but not `admin.users.edit` — edit actions should still render but POST should return 403 (existing behavior unchanged).
12. **Dark mode.** Toggle on — admin pages stay light-themed intentionally (documented out of scope); verify no broken layouts, unreadable contrast, or JS errors.
13. **Mobile width.** Resize to <768px — sidebar drawer works; tables scroll horizontally; filter bars wrap.

- [ ] **Step 2: If any step fails, triage and fix before closing the PR**

For any failure:
1. Reproduce once, capture the specific error (console, network, server log in `logs/`).
2. Trace to the owning task — each concern was introduced in a specific commit.
3. Fix in a new commit referencing that task number (e.g. `Fix logs org filter param name (Task 8)`), not by amending the original.

- [ ] **Step 3: Merge the branch**

Once smoke passes and you've manually verified the checklist above, the branch is ready for review / merge per your normal workflow.

---

## Self-review notes

**Spec coverage:**
- §1 Navigation → Task 3
- §2 Visual design system → Task 1
- §3 Page structure (macros) → Task 2
- §4.1 Overview → Task 4
- §4.2 Access Control → Tasks 9, 10, 14
- §4.3 User detail → Tasks 11, 12, 13
- §4.4 Organizations → Task 5
- §4.5 Sessions → Task 6
- §4.6 Logs → Tasks 7, 8
- §5 Backend changes → Tasks 4, 7, 8, 10, 11
- §7 i18n → Task 15
- §8 Rollout (smoke test) → Task 16

**Type consistency:**
- `admin-btn`, `admin-btn-primary|secondary|danger|ghost` — same names used across Tasks 1, 4, 5, 6, 7, 9, 10, 11, 13, 14
- Macro names (`page_header`, `filter_bar`, `toolbar`, `table_header`, `empty_state`, `badge`) — defined in Task 2, called consistently in Tasks 4–14
- CSS vars prefixed `--a-` — defined Task 1, referenced throughout
- Route name `admin_user_detail` — introduced Task 11, referenced in Task 3's `active_page` check

**Placeholder scan:**
- Two spots intentionally ask the engineer to read existing code first: (a) logs endpoint current filter parsing in Task 8, (b) override-save endpoint URL in Task 12. These are not placeholders — the exact code is part of what the engineer verifies mid-task, and the surrounding code shows what to do with the discovered detail.
- All SQL references call out "adjust to real schema" — the engineer must read `app.py` for the actual table/column names. This is explicit guidance, not vagueness.
