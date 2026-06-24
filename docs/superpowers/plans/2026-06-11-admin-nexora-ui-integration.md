# Admin Section nexora-ui Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the entire Admin section (7 pages + 6 JS partials + shared macros) from the legacy `admin-tokens.css` precursor system (`--a-*` / `.admin-*`) onto the app-wide **nexora-ui** design system (`--nx-*` / `.nx-*`), so Admin looks and behaves in unison with Workitems, Dashboard, Invoices, Chat and the Generali pages.

**Architecture:** The `--a-*` tokens are value-identical to `--nx-*` (admin-tokens was the Phase-1 precursor that nexora-ui promoted app-wide), so this is a mechanical class/token migration plus structural upgrades: the nx page-head with gradient icon chip, `nx-filter` bars, `nx-table`, `nx-label` badges, `nx-tabs`, and nx-card-based modals (which also retires the `!important` dark-mode override hacks in admin-tokens.css and fixes the permission drawer being white in dark mode). Admin-only components (health cards, log method/status pills, overview launcher cards, toggles) move to a new slim page-scoped `static/css/admin.css` re-based on `--nx-*` tokens — same pattern as `dashboard.css` / `workitems_overview.css`.

**Tech Stack:** Flask/Jinja2 templates, Tailwind v4 browser CDN (utilities in `@layer`), `static/css/nexora-ui.css` (loaded globally by `templates/_header.html`), Playwright e2e (`tests/e2e/test_admin.py`), Flask-Babel i18n.

---

## Context an engineer needs before starting

### Current vs target state

Every admin page today: links `static/css/admin-tokens.css` in `<head>`, uses `<body class="admin-page">`, a bare `<main>` (sized by `body.admin-page main` in admin-tokens.css), imports `admin/_admin_helpers.html` macros that emit `.admin-*` markup, and renders modals with raw Tailwind utilities whose dark mode is forced by `!important` overrides in admin-tokens.css lines 230–306.

Target: `<body class="nx-app">`, `<main class="nx-main">`, macros emitting `.nx-*` markup, modals built like the Generali ones (`nx-card` panel + `nx-section` header + `nx-input`/`nx-select` fields + `nx-btn` footer), no admin-tokens.css link on admin pages.

### Token equivalence (for inline `style="..."` swaps)

| legacy | nexora-ui | | legacy | nexora-ui |
|---|---|---|---|---|
| `--a-page` | `--nx-page` | | `--a-text` | `--nx-text` |
| `--a-card` | `--nx-card` | | `--a-text-sec` | `--nx-text-sec` |
| `--a-alt` | `--nx-alt` | | `--a-text-meta` | `--nx-text-meta` |
| `--a-border` | `--nx-border` | | `--a-indigo` | `--nx-accent` |
| `--a-border-input` | `--nx-border-strong` | | `--a-indigo-soft` | `--nx-accent-soft` |
| `--a-row-divider` | `--nx-divider` | | `--a-success` | `--nx-success` |
| `--a-mono-bg` | `--nx-sunken` | | `--a-warning` | `--nx-warning` |
| `--a-ink` | `--nx-accent` | | `--a-danger` | `--nx-danger` |
| `--a-ink-hover` | `--nx-accent-hover` | | `--a-b-{indigo,green,amber,gray,red}` | `--nx-l-{…}` |
| `--a-bg-alt`, `--a-bg` (used in user_detail.html but **never defined** — latent bug) | `--nx-alt`, `--nx-page` | | `--a-b-*-fg` | `--nx-l-*-fg` |

### Class mapping (the core of every task)

| legacy class | nexora-ui replacement |
|---|---|
| `body.admin-page` | `body.nx-app` |
| (bare) `<main>` | `<main class="nx-main">` |
| `.admin-header` block | `.nx-page-head` structure (see Task 2 macro code) |
| `.admin-title` / `.admin-subtitle` / `.admin-section` / `.admin-meta` | `.nx-title` / `.nx-subtitle` / `.nx-section` / `.nx-meta` |
| `.admin-mono` | `.nx-mono` (bare monospace — drops the gray chip background, matching Workitems/Invoices IDs) |
| `.admin-btn admin-btn-primary` | `.nx-btn nx-btn--primary` |
| `.admin-btn admin-btn-secondary` | `.nx-btn nx-btn--secondary` |
| `.admin-btn admin-btn-danger` | `.nx-btn nx-btn--danger` |
| `.admin-btn admin-btn-ghost` | `.nx-btn nx-btn--ghost` (row actions add `nx-btn--sm`) |
| `.admin-badge admin-badge--X` | `.nx-label nx-label--X` (X ∈ indigo/green/amber/red/gray) |
| `.admin-input` / `.admin-select` | `.nx-input` / `.nx-select` |
| `.admin-input-icon` | `.nx-input-icon` (icon `<i>` + `.nx-input` child; nexora-ui already does `padding-left:32px`) |
| `.admin-filter-bar` | `.nx-filter` (labels: see macro code — `.nx-filter label` styling does not exist, keep explicit label classes) |
| `.admin-card` | `.nx-card` (`.nx-card--pad` where padding 20px+ wanted) |
| `.admin-card-link` | `.nx-card--link` |
| `.admin-table-wrap` / `.admin-table` | `.nx-table-wrap` / `.nx-table` |
| `.acl-tabs`/`.acl-tab-btn`, `.perm-tabs`/`.perm-tab-btn` (inline styles) | `.nx-tabs` / `.nx-tab` (delete the inline `<style>` blocks) |
| `.admin-empty`, `.log-method--*`, `.log-status--*`, `.health-*`, `.admin-overview-card*`, `.ml-toggle`, `.sev-*`, `.log-preset*`, `.saved-preset*` | **keep the class names**, restyled on `--nx-*` tokens in the new `static/css/admin.css` (Task 1) — avoids touching ~40 JS injection sites for purely admin-local components |

### Invariants — never change these

- **`data-testid` attributes** — `tests/e2e/test_admin.py` has 40+ selectors (`admin-overview-*`, `admin-org-*`, `admin-ac-*`, `admin-logs-*`, `admin-userdetail-*`, `admin-maintenance-*`).
- **Element IDs and `name=` attributes** — all JS partials select by ID; permission radios serialize via `name="perm_{{ PermissionID }}"` with values `None|D|A`.
- **`data-*` attributes** — `data-search`, `data-perm-id`, `data-perm-code`, `data-perm-group`, `data-perm-sub-group`, `data-organization`, `data-user-id`, `data-preset`.
- **Show/hide mechanics** — JS toggles `hidden`, `opacity-0`, `scale-95`, `translate-x-full`; keep those utility classes and the `.modal-content` class (queried by `_organizations_js.html:56` and `_access_control_js.html`).
- **CSRF hidden inputs**, **`{{ _('...') }}` i18n calls** (258 strings in `templates/admin/` — reuse them verbatim; new user-visible strings require the `/nx-i18n` cycle).
- **`#notification-container`** toast markup and its Tailwind animation classes (theme-agnostic, out of scope).
- **Flatpickr** wiring on `#maintStartAt` / `#maintEndAt`.

### ⚠️ Tailwind v4 cascade-layer gotcha (bit us twice already)

The CDN `@tailwindcss/browser` build emits utilities inside `@layer utilities`; **unlayered rules in our CSS files always win over them**, regardless of order. Two precedents:
- `0627674` re-asserted `.nx-input.pl-10` because `pl-10` silently lost to `.nx-input`'s padding.
- 2026-06-11: `.nx-flash { display:flex }` beat `.hidden { display:none }`, rendering empty error strips in every Generali add-modal — fixed by `.nx-flash.hidden { display:none }` in nexora-ui.css.

Rule of thumb for this migration: never rely on a Tailwind utility to override a property that an unlayered `.nx-*`/`.admin-*` rule also sets. If you must combine (e.g. `hidden` on an element whose custom class sets `display`), add a scoped re-assertion (`.foo.hidden { display:none }`) to the stylesheet that owns `.foo`.

### Verification loop (used by every page task)

```powershell
# from C:\dev\nexora (main checkout — has venv + env/INT.env)
.\bin\nx.ps1 -r                                  # restart dev server (Jinja templates cache for process lifetime)
nx -u -b --loginas:ben.streich                   # logged-in browser session for Playwright
# drive the page, light AND dark (sidebar moon toggle), screenshot to var/screenshots/
python -m pytest tests/e2e/test_admin.py -q      # expected: all passed
```

Visual acceptance per page: side-by-side with `/workitems` — same fonts, same table chrome, same button/badge shapes, brand-gradient only on primary CTAs and the page icon chip; dark mode has no white flashes; 375 px width has no horizontal scroll.

---

## File structure

| File | Action | Responsibility |
|---|---|---|
| `static/css/admin.css` | **create** | Admin-only components on `--nx-*` tokens (empty cells, log pills, health cards, overview launchers, toggles, presets) |
| `templates/admin/_admin_helpers.html` | rewrite macros | Shared page-header / toolbar / filter / table / empty / badge emitting `.nx-*` |
| `templates/admin/{admin_overview,organizations,sessions,logs,maintenance,user_detail,access_control}.html` | convert | Page shells, tables, modals, tabs |
| `templates/admin/modals/_organizations_modals.html` | convert | Org add/edit + confirm-delete modals → nx-card panels |
| `templates/js/admin/_{organizations,sessions,logs,maintenance,user_detail,access_control}_js.html` | targeted edits | JS-injected markup class swaps only |
| `static/css/admin-tokens.css` | untouched (this pass) | Still loaded by `templates/profile.html` (`body.admin-page` + `--a-*`); retire fully when profile migrates |
| `templates/admin/archive/*`, `templates/admin/modals/_user_modals.html` | untouched | Dead code (only referenced by the archived page); delete in a separate cleanup PR |
| `CHANGELOG.md` | update | `[Unreleased] → Changed` entry |

---

### Task 0: Baseline

**Files:** none modified.

- [ ] **Step 1: Reset e2e DB state** (stale `NEXORA_TEST` state fails order-dependent e2e)

```powershell
python scripts/test_db_reset.py
```

- [ ] **Step 2: Run the admin e2e suite, confirm green BEFORE touching anything**

```powershell
python -m pytest tests/e2e/test_admin.py -q
```
Expected: `all passed`. If not green, stop and fix/report before migrating (you can't distinguish your breakage from pre-existing failures otherwise).

- [ ] **Step 3: Capture "before" screenshots** of all 7 admin pages, light + dark, into `var/screenshots/admin-before-*.png` (drive with Playwright via `nx -u -b --loginas:ben.streich`).

### Task 1: `static/css/admin.css` — admin-only components on nx tokens

**Files:**
- Create: `static/css/admin.css`

- [ ] **Step 1: Create the file with this exact content**

```css
/* ============================================================
   NEXORA ADMIN — page-scoped components on nexora-ui tokens.
   Generic chrome (buttons, tables, inputs, badges, cards) comes
   from nexora-ui.css; only admin-unique structures live here.
   ============================================================ */

/* Empty / loading table cells (JS partials inject class="admin-empty") */
.admin-empty { padding: 32px 16px; text-align: center; color: var(--nx-text-meta); font-size: 13px; }

/* HTTP method / status pills (Logs + user-detail Activity; injected by JS) */
.log-method { font-weight: 700; font-family: var(--nx-mono); font-size: 11px; margin-right: 6px; }
.log-method--GET    { color: #2563eb; }
.log-method--POST   { color: #15803d; }
.log-method--PUT    { color: #b54708; }
.log-method--DELETE { color: #b42318; }
html.dark .log-method--GET    { color: #60a5fa; }
html.dark .log-method--POST   { color: #4ade80; }
html.dark .log-method--PUT    { color: #fbbf24; }
html.dark .log-method--DELETE { color: #f87171; }
.log-status { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; font-family: var(--nx-mono); }
.log-status--ok    { background: var(--nx-l-green); color: var(--nx-l-green-fg); }
.log-status--warn  { background: var(--nx-l-amber); color: var(--nx-l-amber-fg); }
.log-status--error { background: var(--nx-l-red);   color: var(--nx-l-red-fg); }

/* Health strip on the admin overview */
.health-strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 20px; }
.health-card { padding: 16px 18px; }
.health-card-label { font-size: 11px; font-weight: 600; letter-spacing: 0.6px; text-transform: uppercase; color: var(--nx-text-meta); margin-bottom: 6px; }
.health-card-value { font-size: 24px; font-weight: 600; letter-spacing: -0.4px; color: var(--nx-text); line-height: 1.2; font-family: var(--nx-mono); font-variant-numeric: tabular-nums; }
.health-card-value.is-danger { color: var(--nx-danger); }
.health-card-sub { font-size: 12px; color: var(--nx-text-sec); margin-top: 4px; }
.health-db-list { display: flex; flex-wrap: wrap; gap: 6px; }
.health-db-pill { display: inline-flex; align-items: center; gap: 6px; padding: 3px 8px; border-radius: var(--nx-radius-pill); font-size: 11px; font-weight: 500; background: var(--nx-l-gray); color: var(--nx-l-gray-fg); }
.health-db-pill--ok  { background: var(--nx-l-green); color: var(--nx-l-green-fg); }
.health-db-pill--err { background: var(--nx-l-red);   color: var(--nx-l-red-fg); }
.health-db-pill .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; opacity: 0.7; }

/* Overview launcher cards (2x2 grid on /admin) */
.admin-overview-card { padding: 28px 28px 24px; min-height: 180px; display: flex; flex-direction: column; }
.admin-overview-card-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 18px; }
.admin-overview-card-icon { font-size: 22px; color: var(--nx-text-meta); opacity: 0.55; transition: opacity var(--nx-dur) var(--nx-ease), color var(--nx-dur) var(--nx-ease); }
.admin-overview-card:hover .admin-overview-card-icon { opacity: 1; color: var(--nx-accent); }
.admin-overview-card-number { font-size: 44px; font-weight: 600; letter-spacing: -1px; color: var(--nx-text); line-height: 1; font-family: var(--nx-mono); font-variant-numeric: tabular-nums; }
.admin-overview-card-number--text { font-size: 32px; letter-spacing: -0.6px; font-family: var(--nx-font); }
.admin-overview-card-label { font-size: 13px; color: var(--nx-text-sec); margin-top: 4px; }
.admin-overview-card-desc { font-size: 12px; color: var(--nx-text-meta); margin: auto 0 0; padding-top: 16px; }

/* Maintenance: severity pills (rendered by _maintenance_js.html) + toggle switch */
.sev-pill { display: inline-flex; align-items: center; gap: 0.375rem; padding: 0.125rem 0.5rem; border-radius: var(--nx-radius-pill); font-size: 0.75rem; font-weight: 600; }
.sev-info     { background: var(--nx-l-indigo); color: var(--nx-l-indigo-fg); }
.sev-warning  { background: var(--nx-l-amber);  color: var(--nx-l-amber-fg); }
.sev-critical { background: var(--nx-l-red);    color: var(--nx-l-red-fg); }
.ml-toggle { position: relative; display: inline-block; width: 36px; height: 20px; }
.ml-toggle input { opacity: 0; width: 0; height: 0; }
.ml-toggle-slider { position: absolute; cursor: pointer; inset: 0; background: var(--nx-sunken); border: 1px solid var(--nx-border); border-radius: var(--nx-radius-pill); transition: 0.2s; }
.ml-toggle-slider:before { position: absolute; content: ""; height: 14px; width: 14px; left: 2px; top: 2px; background: var(--nx-card); border-radius: var(--nx-radius-pill); transition: 0.2s; box-shadow: 0 1px 2px rgba(0,0,0,0.15); }
.ml-toggle input:checked + .ml-toggle-slider { background: var(--nx-accent); border-color: var(--nx-accent); }
.ml-toggle input:checked + .ml-toggle-slider:before { transform: translateX(16px); background: #fff; }

/* Logs: time presets + saved filters (moved from logs.html inline styles) */
.log-preset-row { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; align-items: center; }
.log-preset { padding: 5px 10px; border-radius: 6px; background: var(--nx-card); border: 1px solid var(--nx-border-strong); font-size: 12px; color: var(--nx-text-sec); cursor: pointer; }
.log-preset:hover { background: var(--nx-alt); color: var(--nx-text); }
.log-preset.is-active { background: var(--nx-accent); color: #fff; border-color: var(--nx-accent); }
.saved-preset-row { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; align-items: center; min-height: 30px; }
.saved-preset-label { font-size: 11px; font-weight: 600; letter-spacing: 0.6px; text-transform: uppercase; color: var(--nx-text-meta); }
.saved-preset { display: inline-flex; align-items: center; gap: 6px; padding: 4px 4px 4px 10px; border-radius: 14px; background: var(--nx-card); border: 1px solid var(--nx-border-strong); font-size: 12px; color: var(--nx-text); cursor: pointer; }
.saved-preset:hover { background: var(--nx-alt); }
.saved-preset .name { line-height: 1; }
.saved-preset .del { display: inline-flex; width: 18px; height: 18px; align-items: center; justify-content: center; border-radius: 50%; color: var(--nx-text-meta); font-size: 10px; }
.saved-preset .del:hover { background: var(--nx-sunken); color: var(--nx-danger); }
.saved-preset-empty { font-size: 12px; color: var(--nx-text-meta); font-style: italic; }
.save-preset-btn { padding: 4px 10px; border-radius: 14px; background: transparent; border: 1px dashed var(--nx-border-strong); font-size: 12px; color: var(--nx-text-sec); cursor: pointer; }
.save-preset-btn:hover { border-style: solid; color: var(--nx-text); }

/* Logs: dark <pre> payload scrollbars (moved from logs.html inline styles) */
.code-scroll::-webkit-scrollbar { width: 8px; height: 8px; }
.code-scroll::-webkit-scrollbar-track { background: #1f2937; }
.code-scroll::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 4px; }
.code-scroll::-webkit-scrollbar-thumb:hover { background: #6b7280; }
```

- [ ] **Step 2: Commit**

```powershell
git add static/css/admin.css
git commit -m "feat(ui): admin-only components restyled on nexora-ui tokens"
```
(If the line-ending pre-commit hook normalises CRLF and aborts, `git add` + commit again — passes the 2nd time. If `sql-migrate-int` fails on a machine without INT env, use `$env:SQL_SYNC_SKIP="1"; git commit ...`.)

### Task 2: Rewrite `_admin_helpers.html` macros to emit nx markup

**Files:**
- Modify: `templates/admin/_admin_helpers.html` (whole file)

This single task restyles the header/toolbar/filter/empty/badge of **every** admin page at once (the `--nx-*` tokens are `:root`-scoped and nexora-ui.css is loaded by `_header.html` on every page, so nx classes already work before the per-page body-class flips land).

- [ ] **Step 1: Replace the entire file content with:**

```jinja
{# ------------------------------------------------------------------
   Admin UI macros — shared building blocks for every admin page.
   Usage:  {% import 'admin/_admin_helpers.html' as a %}
   Markup follows the nexora-ui design system (.nx-* classes).
   ------------------------------------------------------------------ #}

{% macro page_header(title, subtitle=None, back_url=None, actions=None, icon=None) %}
  <div class="nx-page-head nx-rise">
    <div class="nx-page-head__main">
      <div class="nx-page-head__title">
        {% if back_url %}
          <a href="{{ back_url }}" class="nx-btn nx-btn--ghost nx-btn--sm" aria-label="{{ _('Back') }}" data-testid="admin-helpers-back">
            <i class="fas fa-arrow-left"></i>
          </a>
        {% endif %}
        {% if icon %}<span class="nx-page-icon"><i class="fas {{ icon }}"></i></span>{% endif %}
        <div>
          <h1 class="nx-title">{{ title }}</h1>
          {% if subtitle %}<p class="nx-subtitle">{{ subtitle }}</p>{% endif %}
        </div>
      </div>
    </div>
    {% if actions %}
      <div class="nx-page-head__actions">
        {% for act in actions %}
          <button type="button" onclick="{{ act.onclick }}" class="nx-btn nx-btn--{{ act.variant|default('primary') }}" data-testid="admin-helpers-page-action-{{ act.testid|default(loop.index) }}">
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
  <div class="nx-filter mb-6">
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
    {% for f in filters %}
      <div>
        <label for="{{ f.id }}" class="block text-xs font-bold uppercase tracking-widest mb-1" style="color: var(--nx-text-meta)">{{ f.label }}</label>
        {% if f.type == 'search' %}
          <div class="nx-input-icon">
            <i class="fas fa-search"></i>
            <input type="text" id="{{ f.id }}" class="nx-input" placeholder="{{ f.placeholder|default('') }}" data-testid="admin-helpers-filter-{{ f.id }}">
          </div>
        {% elif f.type == 'select' %}
          <select id="{{ f.id }}" class="nx-select" data-testid="admin-helpers-filter-{{ f.id }}">
            {% for opt in f.options %}
              <option value="{{ opt.value }}">{{ opt.label }}</option>
            {% endfor %}
          </select>
        {% elif f.type == 'date' %}
          <input type="date" id="{{ f.id }}" class="nx-input" data-testid="admin-helpers-filter-{{ f.id }}">
        {% endif %}
      </div>
    {% endfor %}
    </div>
  </div>
{% endmacro %}


{% macro toolbar(search_id, search_placeholder, actions=None) %}
  <div style="display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:16px;flex-wrap:wrap">
    <div class="nx-input-icon" style="width:280px">
      <i class="fas fa-search"></i>
      <input type="text" id="{{ search_id }}" class="nx-input" placeholder="{{ search_placeholder }}" data-testid="admin-helpers-toolbar-{{ search_id }}">
    </div>
    {% if actions %}
      <div class="nx-page-head__actions">
        {% for act in actions %}
          <button type="button" onclick="{{ act.onclick }}" class="nx-btn nx-btn--{{ act.variant|default('primary') }}" data-testid="admin-helpers-toolbar-action-{{ act.testid|default(loop.index) }}">
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
  <span class="nx-label nx-label--{{ tone }}">{{ label }}</span>
{% endmacro %}
```

Notes: `page_header` h2→h1 (matches every nx page; there is exactly one per page). `empty_state` keeps `.admin-empty` (now styled by admin.css from Task 1). `filter_bar`'s grid wrapper matches the Workitems filter recipe.

- [ ] **Step 2: Restart server, eyeball `/admin` and `/admin/logs`** — headers/toolbars already render in nx style while bodies are still legacy (tokens are identical, so no visual clash).

- [ ] **Step 3: Run e2e** `python -m pytest tests/e2e/test_admin.py -q` → all passed (testids unchanged).

- [ ] **Step 4: Commit**

```powershell
git add templates/admin/_admin_helpers.html
git commit -m "feat(ui): admin shared macros emit nexora-ui markup"
```

### Task 3: Convert `/admin` overview page

**Files:**
- Modify: `templates/admin/admin_overview.html`

- [ ] **Step 1: Head + shell.** Replace lines 7–8 (`output.css` link stays):

```html
    <link rel="stylesheet" href="{{ url_for('static', filename='css/output.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/admin.css') }}">
```
Change `<body class="admin-page">` → `<body class="nx-app">` and `<main>` → `<main class="nx-main">`.

- [ ] **Step 2: Give the page header the admin icon chip.** In the `a.page_header(...)` call add `icon='fa-shield-halved'`.

- [ ] **Step 3: Health + launcher cards.** Replace every `class="admin-card admin-card-link health-card"` → `class="nx-card nx-card--link health-card"`, `class="admin-card health-card"` → `class="nx-card health-card"`, `class="admin-card admin-card-link admin-overview-card"` → `class="nx-card nx-card--link admin-overview-card"`. Replace both `class="admin-meta"` → `class="nx-meta"`. Add `nx-rise-2` to the `health-strip` div and `nx-rise-3` to the launcher grid div (stagger animation, matching other pages).

- [ ] **Step 4: Resources links.** Replace both `style="color:var(--a-indigo);text-decoration:none"` → `style="color:var(--nx-accent);text-decoration:none"`.

- [ ] **Step 5: Verify** (loop from Context): restart, open `/admin` light+dark, screenshot `var/screenshots/admin-overview-nx-{light,dark}.png`; `python -m pytest tests/e2e/test_admin.py -q -k overview` → passed.

- [ ] **Step 6: Commit**

```powershell
git add templates/admin/admin_overview.html
git commit -m "feat(ui): apply nexora-ui to admin overview"
```

### Task 4: Convert Organizations (page + modals + JS)

**Files:**
- Modify: `templates/admin/organizations.html`
- Modify: `templates/admin/modals/_organizations_modals.html`
- Modify: `templates/js/admin/_organizations_js.html`

- [ ] **Step 1: Page shell** — same head/body/main changes as Task 3 Step 1 (link `admin.css` instead of `admin-tokens.css`; `nx-app`; `nx-main`). Add `icon='fa-building'` to `a.page_header(...)`.

- [ ] **Step 2: Table.** `admin-table-wrap` → `nx-table-wrap`, `admin-table` → `nx-table`, `admin-mono` → `nx-mono`. Row buttons: `class="edit-organization-btn admin-btn admin-btn-ghost"` → `class="edit-organization-btn nx-btn nx-btn--ghost nx-btn--sm"`; the delete button `class="admin-btn admin-btn-ghost" style="color:var(--a-danger)"` → `class="nx-btn nx-btn--ghost nx-btn--sm" style="color:var(--nx-danger)"`.

- [ ] **Step 3: Modals** — replace the entire content of `templates/admin/modals/_organizations_modals.html` with the following (every id, testid, name, `onclick` and the `.modal-content` class + `hidden opacity-0` / `scale-95` mechanics preserved exactly — JS queries them):

```html
<div id="confirmationModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-60 hidden opacity-0 transition-opacity duration-300 ease-in-out">
    <div class="modal-content nx-card w-full max-w-sm text-center transform scale-95 transition-transform duration-300 ease-in-out">
        <div class="mx-auto flex-shrink-0 flex items-center justify-center h-12 w-12 rounded-full" style="background:var(--nx-l-red)">
            <i class="fas fa-exclamation-triangle fa-lg" style="color:var(--nx-danger)"></i>
        </div>
        <h3 class="nx-section mt-4" id="confirmTitle">{{ _("Delete Organization") }}</h3>
        <div class="mt-2">
            <p class="text-sm" style="color:var(--nx-text-sec)" id="confirmMessage">
            </p>
        </div>
        <div class="mt-6 flex justify-center space-x-4">
            <button id="cancelBtn" type="button" class="nx-btn nx-btn--secondary" data-testid="admin-org-modal-confirmation-cancel">
                {{ _("Cancel") }}
            </button>
            <button id="confirmBtn" type="button" class="nx-btn nx-btn--danger" data-testid="admin-org-modal-confirmation-confirm">
                {{ _("Confirm") }}
            </button>
        </div>
    </div>
</div>

<div id="organizationModal"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 hidden opacity-0 transition-opacity duration-300 ease-in-out"
    onclick="closeModal(event)">
    <div
        class="modal-content nx-card w-full max-w-md transform scale-95 transition-transform duration-300 ease-in-out">
        <h3 id="modalTitle" class="nx-section mb-4">{{ _("Add a new Organization") }}</h3>
        <form id="organizationForm" data-testid="admin-org-modal-form">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
             <input type="hidden" id="organizationcode" name="organizationcode">
            <div class="space-y-4">
                <div>
                    <label for="organizationname" class="block text-xs font-bold uppercase tracking-widest mb-1" style="color: var(--nx-text-meta)">{{ _("Organization Name") }}</label>
                    <input type="text" id="organizationname" name="organizationname"
                        class="nx-input"
                        required data-testid="admin-org-modal-name">
                </div>
            </div>
            <div class="flex justify-end mt-6 gap-2">
                <button type="button" onclick="closeModal()"
                    class="nx-btn nx-btn--secondary" data-testid="admin-org-modal-cancel">{{ _("Cancel") }}</button>
                <button type="submit"
                    class="nx-btn nx-btn--primary" data-testid="admin-org-modal-save">{{ _("Save Organization") }}</button>
            </div>
        </form>
    </div>
</div>
```
This is also the canonical confirm-delete recipe referenced by Tasks 7 and 9: centered `nx-card max-w-sm text-center`, warning orb on `var(--nx-l-red)`, `nx-section` title, `var(--nx-text-sec)` body, `nx-btn nx-btn--secondary` + `nx-btn nx-btn--danger` footer.

- [ ] **Step 4: JS partial** — in `_organizations_js.html` (lines 93–97): `admin-mono` → `nx-mono`; `admin-btn admin-btn-ghost` → `nx-btn nx-btn--ghost nx-btn--sm` (both buttons); `var(--a-danger)` → `var(--nx-danger)`.

- [ ] **Step 5: Verify**: restart; on `/admin/organizations` exercise add → edit → delete (confirm modal) in light and dark; screenshots `var/screenshots/admin-orgs-nx-{light,dark}.png`; `python -m pytest tests/e2e/test_admin.py -q -k org` → passed.

- [ ] **Step 6: Commit**

```powershell
git add templates/admin/organizations.html templates/admin/modals/_organizations_modals.html templates/js/admin/_organizations_js.html
git commit -m "feat(ui): apply nexora-ui to admin organizations"
```

### Task 5: Convert Sessions (page + JS)

**Files:**
- Modify: `templates/admin/sessions.html`
- Modify: `templates/js/admin/_sessions_js.html`

- [ ] **Step 1: Page shell** — head/body/main as in Task 3 Step 1; `icon='fa-signal'` on `page_header`; `admin-table-wrap`/`admin-table` → `nx-table-wrap`/`nx-table`.

- [ ] **Step 2: JS partial** — `_sessions_js.html`: line 66 `mono.className = 'admin-mono'` → `'nx-mono'`; line 86 `btn.className = 'admin-btn admin-btn-ghost revoke-session-btn'` → `'nx-btn nx-btn--ghost nx-btn--sm revoke-session-btn'`; line 105 `var(--a-danger)` → `var(--nx-danger)`. (`admin-empty` cells at 39/51/105 stay — styled by admin.css.)

- [ ] **Step 3: Verify**: `/admin/sessions` light+dark, revoke button visible; screenshots; `python -m pytest tests/e2e/test_admin.py -q -k session` → passed.

- [ ] **Step 4: Commit**

```powershell
git add templates/admin/sessions.html templates/js/admin/_sessions_js.html
git commit -m "feat(ui): apply nexora-ui to admin sessions"
```

### Task 6: Convert System Logs (page + JS)

**Files:**
- Modify: `templates/admin/logs.html`
- Modify: `templates/js/admin/_logs_js.html`

- [ ] **Step 1: Page shell** — head/body/main as in Task 3 Step 1; `icon='fa-clipboard-list'`. **Delete the whole inline `<style>` block (lines 10–29)** — its rules moved to `admin.css` in Task 1 (token-swapped).

- [ ] **Step 2: Filter bar.** `admin-filter-bar` → `nx-filter` and wrap the seven field divs in the responsive grid (`<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">…</div>`); each `<label>` gets `class="block text-xs font-bold uppercase tracking-widest mb-1" style="color: var(--nx-text-meta)"`; `admin-input-icon` → `nx-input-icon`; `admin-input` → `nx-input`; `admin-select` → `nx-select`.

- [ ] **Step 3: Table + pagination.** `admin-table-wrap`/`admin-table` → `nx-table-wrap`/`nx-table`. Pagination bar: `var(--a-border)` → `var(--nx-border)`, `var(--a-text-sec)` → `var(--nx-text-sec)`; `admin-btn admin-btn-secondary` → `nx-btn nx-btn--secondary` (both prev/next).

- [ ] **Step 4: Log-details modal chrome.** Keep the dark `<pre>` exactly as is (it is intentionally terminal-styled). Convert only the chrome: on `#modalPanel` replace `bg-white` with the nx surface (`class="relative transform overflow-hidden rounded-xl text-left shadow-2xl transition-all sm:my-8 sm:w-full sm:max-w-2xl opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95" style="background:var(--nx-card)"`); header/footer `bg-gray-50` → `style="background:var(--nx-alt)"`, `border-gray-100` → `style="border-color:var(--nx-divider)"` (merge with existing style attrs); title `text-gray-900` → `style="color:var(--nx-text)"`; the meta labels `text-gray-400/800` → `var(--nx-text-meta)`/`var(--nx-text)`; bottom Close button → `class="nx-btn nx-btn--secondary"` (keep its `onclick` + testid).

- [ ] **Step 5: JS partial** — `_logs_js.html`: line 77/80 `admin-mono` → `nx-mono`; line 82 `admin-btn admin-btn-ghost` → `nx-btn nx-btn--ghost nx-btn--sm` and `var(--a-indigo)` → `var(--nx-accent)`; lines 23/49/94 `admin-empty` stays; line 94 `var(--a-danger)` → `var(--nx-danger)`.

- [ ] **Step 6: Verify**: `/admin/logs` — presets toggle, saved filters, search, open a log-details modal, light+dark; screenshots; `python -m pytest tests/e2e/test_admin.py -q -k log` → passed.

- [ ] **Step 7: Commit**

```powershell
git add templates/admin/logs.html templates/js/admin/_logs_js.html
git commit -m "feat(ui): apply nexora-ui to admin system logs"
```

### Task 7: Convert Maintenance Banners (page + JS)

**Files:**
- Modify: `templates/admin/maintenance.html`
- Modify: `templates/js/admin/_maintenance_js.html`

- [ ] **Step 1: Page shell** — head/body/main as in Task 3 Step 1; `icon='fa-screwdriver-wrench'`. **Delete the inline `<style>` block (lines 12–31)** — `.sev-*` and `.ml-toggle` moved to admin.css. Keep the Flatpickr `<link>`/`<script>` lines untouched.

- [ ] **Step 2: Table.** `admin-table-wrap`/`admin-table` → `nx-table-wrap`/`nx-table`; spinner cell `style="color:#4f46e5;…"` → `style="color:var(--nx-accent);font-size:24px"`.

- [ ] **Step 3: Add/Edit modal (`#maintModal`).** Panel `class="bg-white rounded-lg shadow-2xl w-full max-w-lg p-6"` → `class="nx-card w-full max-w-lg"`; title `class="text-2xl font-bold mb-4"` → `class="nx-section mb-4"`. Every form control loses its Tailwind soup: `class="bg-gray-50 border border-gray-300 text-sm rounded-lg block w-full p-2.5 focus:ring-indigo-500 focus:border-indigo-500"` → `class="nx-input"` (inputs/textarea) or `class="nx-select"` (`#maintSeverity`); `#maintAnnounce` keeps its width: `class="nx-input w-24"`. Labels → `class="block text-xs font-bold uppercase tracking-widest mb-1" style="color: var(--nx-text-meta)"`. The block-access warning box: `class="border border-red-200 rounded-lg p-3 bg-red-50"` → `style="border:1px solid var(--nx-l-red-fg);background:var(--nx-l-red);border-radius:var(--nx-radius-sm);padding:12px"`, inner heading/text `text-red-700`/`text-red-600` → `style="color:var(--nx-l-red-fg)"`. Footer: Cancel → `class="nx-btn nx-btn--secondary"`, Save → `class="nx-btn nx-btn--primary"`. `#maintError` keeps `hidden text-xs mt-3` but add `style="color:var(--nx-danger)"` (it has no display-setting custom class, so `hidden` keeps working — see the layer gotcha).

- [ ] **Step 4: Delete modal (`#maintDeleteModal`).** Panel → `class="nx-card w-full max-w-sm text-center"`; warning orb `bg-red-100` circle → `style="background:var(--nx-l-red)"` with icon `style="color:var(--nx-danger)"`; buttons → `nx-btn nx-btn--secondary` / `nx-btn nx-btn--danger` (keep ids/testids/onclicks).

- [ ] **Step 5: JS partial** — `_maintenance_js.html`: line 109 `tdWindow.className = 'admin-mono'` → `'nx-mono'`; lines 143/148 `editBtn.className`/`delBtn.className = 'admin-btn admin-btn-ghost'` → `'nx-btn nx-btn--ghost nx-btn--sm'`. Also grep the partial for `var(--a-` and swap per the token table.

- [ ] **Step 6: Verify**: `/admin/maintenance` — add banner (Flatpickr opens, severity select, toggles flip), edit, delete, validation error shows in `#maintError`, light+dark; screenshots; `python -m pytest tests/e2e/test_admin.py -q -k maintenance` → passed.

- [ ] **Step 7: Commit**

```powershell
git add templates/admin/maintenance.html templates/js/admin/_maintenance_js.html
git commit -m "feat(ui): apply nexora-ui to admin maintenance banners"
```

### Task 8: Convert User Detail (page + JS)

**Files:**
- Modify: `templates/admin/user_detail.html`
- Modify: `templates/js/admin/_user_detail_js.html`

- [ ] **Step 1: Page shell** — head/body/main as in Task 3 Step 1 (no `icon` — the back-arrow + user identity is the header). **Delete the inline `.perm-tabs` `<style>` block (lines 12–17).**

- [ ] **Step 2: Profile card.** `class="admin-card"` → `class="nx-card nx-card--pad"` (all three section cards + danger card); `admin-section` → `nx-section`; `admin-meta` labels → `nx-meta`; `admin-input` → `nx-input`; `admin-select` → `nx-select`; `admin-btn admin-btn-secondary` → `nx-btn nx-btn--secondary`; `admin-btn admin-btn-primary` → `nx-btn nx-btn--primary`.

- [ ] **Step 3: Tabs.** Replace

```html
<ul class="perm-tabs">
  <li><button id="perm-tab-effective-btn" … class="perm-tab-btn is-active" …></li>
  <li><button id="perm-tab-overrides-btn" … class="perm-tab-btn" …></li>
</ul>
```
with (keep ids, onclicks, testids, inner icons/text):

```html
<div class="nx-tabs" style="margin-bottom:16px">
  <button id="perm-tab-effective-btn" type="button" onclick="switchPermTab('effective')" class="nx-tab is-active" data-testid="admin-userdetail-tab-effective">
    <i class="fas fa-shield-halved"></i> {{ _('Effective Permissions') }}
  </button>
  <button id="perm-tab-overrides-btn" type="button" onclick="switchPermTab('overrides')" class="nx-tab" data-testid="admin-userdetail-tab-overrides">
    <i class="fas fa-sliders"></i> {{ _('Overrides') }}
  </button>
</div>
```
Then in `_user_detail_js.html`, `switchPermTab` toggles `is-active` on the buttons — verify it targets ids (it does) and only update it if it adds/removes `perm-tab-btn` itself (grep `perm-tab-btn` in the partial; if present, swap for `nx-tab`).

- [ ] **Step 4: Tables + inline tokens.** `admin-table-wrap`/`admin-table` → `nx-table-wrap`/`nx-table` (×3: effective, overrides, activity); `admin-input-icon` → `nx-input-icon`; `admin-input` → `nx-input` (both searches); `admin-mono` → `nx-mono` (perm codes); every `var(--a-text-sec)` → `var(--nx-text-sec)`, `var(--a-text-meta)` → `var(--nx-text-meta)`, `var(--a-border)` → `var(--nx-border)`, `var(--a-danger)` → `var(--nx-danger)`, `var(--a-bg-alt)` → `var(--nx-alt)`, `var(--a-bg)` → `var(--nx-page)` (perm group rows — this also fixes the two undefined-token rows). Pagination buttons → `nx-btn nx-btn--secondary`; ghost link button → `nx-btn nx-btn--ghost nx-btn--sm`; danger-zone buttons → `nx-btn nx-btn--secondary` / `nx-btn nx-btn--danger`. Danger card border: `style="border-color:var(--nx-danger)"`.

- [ ] **Step 5: Confirm-delete modal.** It uses raw inline styles with hard-coded `#fff` (white-on-dark bug today). Replace the panel's `style="background:#fff;border-radius:10px;…"` with `class="nx-card w-full max-w-sm text-center"` (keep the outer `#confirmDeleteModal` wrapper + its `style="display:none;…"` mechanics — JS flips `style.display`); inner text colors → `var(--nx-text-sec)`; buttons already mapped in Step 4.

- [ ] **Step 6: JS partial** — `_user_detail_js.html`: line 321 `span.className = 'admin-badge'` → `'nx-label'`; lines 322–325 `admin-badge--gray/green/red/amber` → `nx-label--gray/green/red/amber`; lines 376/592 `admin-mono` → `nx-mono`; `admin-empty` sites (427/444/459/483/540/555/566/617) stay; `log-status`/`log-method` sites (513–516/589) stay (admin.css). Grep the partial for `var(--a-` and swap per the token table.

- [ ] **Step 7: Verify**: open a user from access control — edit profile field + save, switch tabs, filter permissions, set an override + save, activity pagination, sign-out-everywhere, delete-user modal (cancel), light+dark; screenshots; `python -m pytest tests/e2e/test_admin.py -q -k userdetail` → passed.

- [ ] **Step 8: Commit**

```powershell
git add templates/admin/user_detail.html templates/js/admin/_user_detail_js.html
git commit -m "feat(ui): apply nexora-ui to admin user detail"
```

### Task 9: Convert Access Control (page + JS) — the big one

**Files:**
- Modify: `templates/admin/access_control.html`
- Modify: `templates/js/admin/_access_control_js.html`

- [ ] **Step 1: Page shell** — head/body/main as in Task 3 Step 1; `icon='fa-id-badge'`. **Delete the inline `.acl-tabs` `<style>` block (lines 10–15).**

- [ ] **Step 2: Tabs** — same transformation as Task 8 Step 3: `<ul class="acl-tabs">…</ul>` → `<div class="nx-tabs" style="margin-bottom:20px">` with the three buttons as `class="nx-tab"` (+ `is-active` on users), ids/onclicks/testids unchanged. Grep `_access_control_js.html` for `acl-tab-btn`; `switchTab()` toggles `is-active` — if it queries `.acl-tab-btn`, change that selector to `.nx-tab`.

- [ ] **Step 3: Users tab.** `admin-filter-bar` → `nx-filter` + responsive grid wrapper (as Task 6 Step 2); labels get the meta-label classes; `admin-input-icon`/`admin-input`/`admin-select` → nx equivalents; Clear-filters → `nx-btn nx-btn--secondary` (keep `style="width:100%"`), Add-User → `nx-btn nx-btn--primary` (keep `style="width:100%"`); `admin-table-wrap`/`admin-table` → nx.

- [ ] **Step 4: Permissions tab.** Toolbar search `admin-input-icon`/`admin-input` → nx; Add-Permission → `nx-btn nx-btn--primary`; table wrap/table → nx.

- [ ] **Step 5: Profiles tab.** Count text `var(--a-text-sec)` → `var(--nx-text-sec)`; Add-Profile → `nx-btn nx-btn--primary`; profile cards `class="admin-card"` → `class="nx-card nx-card--pad"`; `admin-section` → `nx-section`; edit pencil → `nx-btn nx-btn--ghost nx-btn--sm`; card footer `var(--a-border)` → `var(--nx-border)`, `var(--a-text-meta)` → `var(--nx-text-meta)`.

- [ ] **Step 6: User-add modal (`#userModal`).** Panel keeps `modal-content` (JS queries it): `class="modal-content nx-card w-full max-w-md p-0 transform scale-95 transition-transform duration-300"`; backdrop wrapper unchanged (`hidden opacity-0` mechanics). Header h3 → `nx-section`, close → `nx-btn nx-btn--ghost nx-btn--sm`; all field `class="w-full border border-gray-300 rounded-lg text-sm p-2.5 focus:ring-indigo-500 focus:border-indigo-500"` → `class="nx-input"` (inputs) / `class="nx-select"` (selects); labels → meta-label classes; form gets `class="space-y-4 px-6 py-4"` and the header div `px-6 pt-5 pb-4` with `style="border-bottom:1px solid var(--nx-divider)"` (mirror the Task 4 recipe); footer Cancel → `nx-btn nx-btn--secondary`, Create → `nx-btn nx-btn--primary`.

- [ ] **Step 7: Confirm-delete modal (`#confirmDeleteModal`).** Panel `bg-white rounded-xl …` → `nx-card w-full max-w-sm p-0 transform scale-95 transition-transform duration-300` + `text-center` padding container; icon/text/buttons per the Task 4 confirm-delete recipe (keep ids/testids).

- [ ] **Step 8: Permission meta modal (`#permissionMetaModal`).** Same recipe; `#permMetaCode` keeps `font-mono` → use `class="nx-input nx-mono"`; helper text `text-gray-400` → `style="color:var(--nx-text-meta)"`; header/footer borders → `var(--nx-divider)`; footer bg `bg-gray-50` → `style="background:var(--nx-alt)"`.

- [ ] **Step 9: Permission drawer (`#permissionDrawer`).** Today it's `bg-white` with no dark-mode override — **white drawer in dark mode (existing bug this fixes)**. Replace surface utilities with tokens, keep ALL mechanics (`translate-x-full` transition, ids, testids):
  - drawer root: drop `bg-white`, add `style="background:var(--nx-card)"`
  - header div: drop `bg-white border-gray-200`, add `style="background:var(--nx-card);border-bottom:1px solid var(--nx-border)"`; `#drawerTitle` `text-gray-800` → `style="color:var(--nx-text)"`; `#drawerSubtitle` `text-gray-500` → `style="color:var(--nx-text-sec)"`; close button → `nx-btn nx-btn--ghost nx-btn--sm`
  - `#drawerProfileMeta`: `bg-gray-50 border-gray-100` → `style="background:var(--nx-alt);border-bottom:1px solid var(--nx-divider)"`; its two inputs → `class="nx-input"` + meta-label classes
  - search row: `bg-white border-gray-100` → tokens as above; `#drawerPermSearch` → `class="nx-input"` wrapped in `nx-input-icon` (replace the hand-rolled absolute icon div)
  - permission table: thead `text-gray-700 bg-gray-100` → `style="background:var(--nx-alt);color:var(--nx-text-sec)"` (keep `sticky top-0 z-10`); group rows `bg-gray-200 border-gray-300` → `style="background:var(--nx-alt);border-bottom:1px solid var(--nx-border);cursor:pointer;user-select:none"`; sub-group rows `bg-gray-50 border-gray-200` → `style="background:var(--nx-page);border-bottom:1px solid var(--nx-divider);cursor:pointer;user-select:none"`; permission rows `border-b hover:bg-gray-50` → `class="permission-row" style="border-bottom:1px solid var(--nx-divider)"` (hover via existing `.nx-table`-like behaviour is NOT available here — add `.permission-row:hover { background: var(--nx-alt); }` to `static/css/admin.css`); code/description text grays → `var(--nx-text)` / `var(--nx-text-sec)`
  - footer: `bg-gray-50 border-gray-200` → tokens; Cancel → `nx-btn nx-btn--secondary`, Save Changes → `nx-btn nx-btn--primary`; `var(--a-text-meta)` → `var(--nx-text-meta)`
  - radio inputs keep their Tailwind color classes (`text-red-600` etc. — semantic, fine in both themes)

- [ ] **Step 10: JS partial** — `_access_control_js.html`: lines 446/453 `admin-empty` stays, `var(--a-danger)` → `var(--nx-danger)`; grep the whole partial for `admin-btn|admin-badge|admin-mono|var(--a-` and swap per the mapping/token tables (user rows render action buttons + override-count badges — expect several sites; row action buttons → `nx-btn nx-btn--ghost nx-btn--sm`, badges → `nx-label nx-label--X`).

- [ ] **Step 11: Verify** (this page has the most behaviour): all three tabs, user search/filter/clear, add-user modal, delete user (confirm), add/edit permission modal, permission drawer for a profile AND for overrides (group collapse, search, radio set, save, impact counts), light+dark — drawer must be dark in dark mode now; screenshots `var/screenshots/admin-ac-nx-{light,dark}.png`; `python -m pytest tests/e2e/test_admin.py -q` → all passed.

- [ ] **Step 12: Commit**

```powershell
git add templates/admin/access_control.html templates/js/admin/_access_control_js.html static/css/admin.css
git commit -m "feat(ui): apply nexora-ui to admin access control"
```

### Task 10: Retire admin-tokens.css from admin pages + final sweep

**Files:**
- Modify: none beyond verification — Tasks 3–9 already swapped each page's `<link>` from `admin-tokens.css` to `admin.css`.

- [ ] **Step 1: Confirm no admin template still references the legacy system**

```powershell
# all three should return ONLY templates/profile.html (and archive/) hits or nothing:
grep -rn "admin-tokens" templates/admin/
grep -rn "admin-page" templates/admin/
grep -rn "var(--a-" templates/admin/ templates/js/admin/
```
Expected: no matches in `templates/admin/` (the archived `templates/admin/archive/` may match — ignore it; it is unreachable). `templates/profile.html` still loads admin-tokens.css **by design** — do not touch it; note the follow-up "migrate profile.html, then delete admin-tokens.css" in the changelog entry.

- [ ] **Step 2: Full e2e**

```powershell
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_admin.py -q
```
Expected: all passed.

- [ ] **Step 3: i18n check** — this migration adds no new user-facing strings (all labels reuse existing `_('...')` calls). Confirm:

```powershell
pybabel extract -F babel.cfg -o messages.pot . ; git diff --stat messages.pot
```
Expected: only the POT-Creation-Date header changes → `git checkout -- messages.pot`. If real new strings appear, run the full `/nx-i18n` cycle (extract → update → translate de/fr/it → compile) and include the catalogs in the commit.

### Task 11: Changelog + docs + final review

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add under `[Unreleased] → Changed`:**

```markdown
- **Admin section on nexora-ui.** All seven admin pages (overview, organizations,
  sessions, system logs, maintenance banners, user detail, access control) now
  use the app-wide `nexora-ui` design system (`.nx-*` components, brand-gradient
  page icon chips, `nx-table`/`nx-filter`/`nx-label`/`nx-tabs`, nx-card modals)
  instead of the legacy `admin-tokens.css` precursor. Admin-only components
  (health cards, log method/status pills, launcher cards, toggles) moved to the
  page-scoped `static/css/admin.css` re-based on `--nx-*` tokens. Fixes the
  permission drawer and user-detail confirm dialog staying white in dark mode.
  `admin-tokens.css` remains only for `profile.html` (follow-up: migrate profile,
  then delete it). No route/permission/`data-testid` changes.
```

- [ ] **Step 2: Run the full pre-push verification** (the push gate runs the whole suite):

```powershell
python scripts/test_db_reset.py
python -m pytest tests/ -q
```
Expected: all passed (e2e included).

- [ ] **Step 3: Dark-mode + responsive sweep** — every admin page at 1440 px and 375 px, light + dark, screenshots to `var/screenshots/`; compare against the Task 0 "before" set.

- [ ] **Step 4: Commit**

```powershell
git add CHANGELOG.md
git commit -m "docs(changelog): admin nexora-ui migration entry"
```

- [ ] **Step 5: Request review** (superpowers:requesting-code-review) before merging/pushing per branch policy.

---

## Self-review notes

- **Spec coverage:** "like all the other pages / all in unison" → Tasks 2–9 convert every admin surface incl. modals, tabs, drawer; Task 1 keeps admin-unique components visually consistent via shared tokens; dark mode and motion (`nx-rise`) included.
- **Out of scope (explicit):** `templates/profile.html` (still on admin-tokens by design), `templates/admin/archive/*` + `modals/_user_modals.html` (dead code — separate cleanup), `#notification-container` toast styling, `output.css` links.
- **Known risk areas:** `_access_control_js.html` is the largest partial — Step 10's grep-and-map is mandatory, not optional; `switchTab`/`switchPermTab` may select by the legacy tab class (checked in Tasks 8/9); the Tailwind layer gotcha whenever `hidden` meets a display-setting custom class.
