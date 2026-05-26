# Mobile UI Foundation — Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Project git rule (HARD):** This repo's `CLAUDE.md` prohibits Claude from running any git command that modifies the index or history. Every `Commit` step in this plan is **the user's job, not Claude's**. After completing the file edits in a step, surface the diff to the user and stop; the user runs `git add` / `git commit`. The provided commit messages are suggestions.

**Goal:** Build the mobile-first design foundation — compiled Tailwind v4 pipeline, a global token + pattern library (`nx-*` classes), a `/design-system` preview route, and a Playwright + axe-core a11y regression test — so subsequent per-page migrations have a stable, tested base to apply.

**Architecture:** Single source of truth is `src/main.css` (Tailwind v4 `@theme` + `@layer components`). Compiled to `static/css/tailwind.css`, committed to keep IIS deploy as "copy files." `_header.html` swaps the Tailwind browser CDN for the compiled link. A new authenticated `/design-system` route renders every `nx-*` component for development reference and as a stable target for an axe-core a11y test.

**Tech Stack:** Tailwind CSS v4 (CSS-first config) · `@tailwindcss/cli` · Tailwind Plus Elements (already loaded; reused) · Inter font · FontAwesome (kept) · Plotly (kept) · Flask + Jinja2 + Python 3 (existing) · Playwright + `@axe-core/playwright` (new dev-only) · GitHub Actions (existing `deploy.yml` + new `build-and-test.yml`)

---

## File Structure

**Created:**
- `package.json` — declares Tailwind + Playwright dev dependencies and `build:css` / `test:a11y` scripts
- `package-lock.json` — auto-generated, committed
- `src/main.css` — single source of truth: tokens (`@theme`) + components (`@layer components`)
- `static/css/tailwind.css` — compiled output, committed
- `static/js/nx-chart.js` — tiny ResizeObserver → `Plotly.Plots.resize` helper for `nx-chart-shell`
- `templates/design_system.html` — renders every `nx-*` component in every state
- `playwright.config.js` — Playwright configuration
- `tests/a11y/design-system.spec.js` — axe-core scan against `/design-system`
- `.github/workflows/build-and-test.yml` — CI: rebuilds CSS, asserts no diff, runs a11y test
- `howtocss.txt` — dev workflow doc (build commands, where tokens/patterns live, how to add a pattern, how to migrate a page)

**Modified:**
- `templates/_header.html` — swap Tailwind browser CDN `<script>` for compiled CSS `<link>`; include `static/js/nx-chart.js`
- `app.py` — add `/design-system` route gated by `@require_permission('admin.view')`
- `.gitignore` — add `node_modules/`, `playwright-report/`, `test-results/`

**Untouched (this phase):**
- All other templates and per-page CSS files. Migration phases 1–8 will edit them in their own plans.
- `static/css/admin-tokens.css` — kept until phase 7 (admin-pages migration) per the spec's co-existence rules.

---

## Task 1: Initialize npm + Tailwind v4 CLI

**Files:**
- Create: `package.json`
- Create: `package-lock.json` (auto-generated)
- Modify: `.gitignore`

- [ ] **Step 1: Verify Node.js is installed**

Run:
```bash
node --version
npm --version
```

Expected: Node ≥ 20.x, npm ≥ 10.x. If missing, install Node LTS from nodejs.org and re-run. (Node is required only on the developer machine, not on the IIS server.)

- [ ] **Step 2: Create `package.json`**

Create `package.json` with this exact content:

```json
{
  "name": "nexora-frontend",
  "private": true,
  "version": "0.1.0",
  "description": "Frontend build pipeline for nexora (Tailwind v4 + Playwright a11y test).",
  "scripts": {
    "build:css": "tailwindcss -i src/main.css -o static/css/tailwind.css --minify",
    "watch:css": "tailwindcss -i src/main.css -o static/css/tailwind.css --watch",
    "test:a11y": "playwright test"
  },
  "devDependencies": {
    "@tailwindcss/cli": "^4.0.0",
    "tailwindcss": "^4.0.0"
  }
}
```

- [ ] **Step 3: Install dependencies**

Run:
```bash
npm install
```

Expected: `node_modules/` is created and `package-lock.json` is generated. No errors.

- [ ] **Step 4: Verify the Tailwind CLI works**

Run:
```bash
npx tailwindcss --help
```

Expected: prints Tailwind CLI usage. Confirms `@tailwindcss/cli` is installed.

- [ ] **Step 5: Update `.gitignore`**

Add `node_modules/` to the existing Ruflo block (or create a new "Frontend tooling" block). Edit `.gitignore` to insert these lines after the existing `# Ruflo / Claude-flow` block:

```gitignore
# Frontend tooling
node_modules/
playwright-report/
test-results/
```

- [ ] **Step 6: Commit (user)**

Files to stage: `package.json`, `package-lock.json`, `.gitignore`.

Suggested message: `mobile foundation: add npm + tailwind v4 CLI`

---

## Task 2: Create `src/main.css` with the token system

**Files:**
- Create: `src/main.css`
- Create: `static/css/tailwind.css` (built artifact)

- [ ] **Step 1: Create `src/main.css` with imports + `@theme` block**

Create `src/main.css` with this exact content:

```css
@import "tailwindcss";

/* ============================================================
   Nexora design tokens — single source of truth.
   Emitted as CSS variables on :root; consumed by Tailwind
   utilities and any hand-written CSS (Plotly, etc.).
   ============================================================ */

@theme {
  /* Colors — surfaces & text */
  --color-bg-page:        #f9fafb;
  --color-bg-surface:     #ffffff;
  --color-bg-muted:       #f9fafb;
  --color-bg-emphasis:    #f3f4f6;

  --color-border:         #e5e7eb;
  --color-border-strong:  #d1d5db;

  --color-text-primary:   #1f2937;
  --color-text-secondary: #6b7280;
  --color-text-meta:      #9ca3af;
  --color-text-on-primary:#ffffff;

  /* Brand — indigo */
  --color-primary-50:     #eef2ff;
  --color-primary-100:    #e0e7ff;
  --color-primary-500:    #6366f1;
  --color-primary-600:    #4f46e5;
  --color-primary-700:    #4338ca;

  /* Semantic */
  --color-success:        #059669;
  --color-success-bg:     #d1fae5;
  --color-warning:        #d97706;
  --color-warning-bg:     #fef3c7;
  --color-danger:         #dc2626;
  --color-danger-bg:      #fee2e2;

  --color-focus-ring:     rgb(79 70 229 / 0.12);

  /* Typography */
  --font-body: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --font-mono: "SF Mono", Consolas, "Roboto Mono", monospace;

  --text-xs:    0.6875rem;  /* 11px */
  --text-sm:    0.8125rem;  /* 13px */
  --text-base:  0.875rem;   /* 14px — desktop default */
  --text-md:    1rem;       /* 16px — mobile body default */
  --text-lg:    1.125rem;   /* 18px */
  --text-xl:    1.375rem;   /* 22px */
  --text-2xl:   1.75rem;    /* 28px — page heroes */

  /* Spacing — 4px scale (Tailwind defaults are inherited; these are mobile-aware additions) */
  --space-page-x-mobile:  1rem;   /* 16px */
  --space-page-x-desktop: 2.5rem; /* 40px */

  /* Radii */
  --radius-sm:   0.25rem;   /* 4px */
  --radius-md:   0.4375rem; /* 7px — matches existing buttons */
  --radius-lg:   0.75rem;   /* 12px */
  --radius-pill: 9999px;

  /* Shadows */
  --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.04);
  --shadow-md: 0 4px 12px -2px rgb(0 0 0 / 0.08);
  --shadow-lg: 0 12px 32px -4px rgb(0 0 0 / 0.12);

  /* Mobile ergonomics */
  --tap-target-min: 2.75rem; /* 44px */

  /* Z-index scale */
  --z-header:  50;
  --z-drawer:  100;
  --z-modal:   200;
  --z-toast:   300;
}

/* Set body defaults so every page gets a consistent base
   even before its template adopts nx-* classes. */
@layer base {
  body {
    font-family: var(--font-body);
    font-size: var(--text-md);            /* 16px on mobile */
    color: var(--color-text-primary);
    background: var(--color-bg-page);
  }

  @media (min-width: 768px) {
    body {
      font-size: var(--text-base);        /* 14px on desktop / dense views */
    }
  }
}

@layer components {
  /* Patterns are added in subsequent tasks. */
}
```

- [ ] **Step 2: Build the CSS**

Run:
```bash
npm run build:css
```

Expected: `static/css/tailwind.css` is created. Open the file and verify it contains:
- The Tailwind preflight reset
- The `:root` block emitting all the `--color-*`, `--text-*`, etc. variables
- Body styles inside the appropriate `@layer base`
- Minified output (no comments, single line or condensed lines)

Expected file size: between 30 KB and 80 KB minified at this point.

- [ ] **Step 3: Commit (user)**

Files to stage: `src/main.css`, `static/css/tailwind.css`.

Suggested message: `mobile foundation: src/main.css token system + initial build`

---

## Task 3: Wire compiled CSS into `_header.html`

**Files:**
- Modify: `templates/_header.html`

- [ ] **Step 1: Inspect current header**

Run:
```bash
grep -nE "tailwindcss|tailwind\.css|<link.*\.css" templates/_header.html
```

Expected output includes a line like:
```
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
```
plus the Font Awesome and `_header.css` `<link>` tags.

- [ ] **Step 2: Replace the Tailwind browser CDN with the compiled CSS link**

Edit `templates/_header.html`:

Find:
```html
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
```

Replace with:
```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/tailwind.css') }}">
```

Do NOT remove the Tailwind Plus Elements `<script>` (`@tailwindplus/elements@1`) — that's a separate runtime library, still needed.
Do NOT remove the FontAwesome `<link>`.
Do NOT remove the existing `_header.css` `<link>`.

- [ ] **Step 3: Smoke-test that pages still render**

Start nexora and visit a few pages.

Run:
```bash
nx -u
```

Then in a browser visit each of these and confirm they render without obvious style breakage:
- `http://127.0.0.1:8000/` (login / hero)
- After login: dashboard, workitems, profile, an admin page
- A Generali page if you have permission

There WILL be some visual differences vs. the CDN build (CDN ships every utility; compiled ships only what's used). At this point we haven't authored any utility classes yet, so most existing utility classes used in templates may not be present in the compiled output. Templates currently using `class="flex flex-col gap-4 ..."` etc. may render with no styles.

**This is expected and accepted** — we are explicitly in the "mid-state co-existence" window described in the spec. Per-page CSS files (`_header.css`, `dashboard.css`, etc.) keep providing visual structure until each page is migrated.

What we DO need to confirm at this step:
- Pages don't crash / Flask renders 200
- The header logo/nav still appears (because `_header.css` is still loaded)
- The new tokens are present — open devtools, inspect `<body>`, check that `getComputedStyle(document.body).getPropertyValue('--color-primary-600')` returns `#4f46e5`.

- [ ] **Step 4: Add a per-template forced rebuild check**

Tailwind v4 scans template content to know which utilities to emit. Confirm `src/main.css` picks up the templates folder by running:

```bash
grep -E "@source" src/main.css
```

Expected: no `@source` directives present yet. Tailwind v4's default scan covers the project root; we'll add an explicit `@source` directive if scan misses templates (verified below).

Run:
```bash
npm run build:css
```

Then check the compiled output for at least one Tailwind utility that you know is used in `_header.html` (e.g., `flex` or `items-center`). If those classes are missing, add this near the top of `src/main.css` (after the import line):

```css
@source "../templates/**/*.html";
```

Rebuild and re-verify.

- [ ] **Step 5: Commit (user)**

Files to stage: `templates/_header.html`, possibly `src/main.css` (if `@source` was added) and `static/css/tailwind.css`.

Suggested message: `mobile foundation: serve compiled tailwind.css from _header.html`

---

## Task 4: Layout patterns — `nx-page`, `nx-section`, `nx-card`

**Files:**
- Modify: `src/main.css`
- Modify: `static/css/tailwind.css` (rebuilt)

- [ ] **Step 1: Add layout patterns to `@layer components`**

Edit `src/main.css`. Inside `@layer components { }`, add:

```css
/* ============================================================
   Layout & chrome
   ============================================================ */
.nx-page {
  width: 100%;
  max-width: 100rem; /* 1600px — matches existing admin layout */
  margin-inline: auto;
  padding-inline: var(--space-page-x-mobile);
  padding-block: 1.25rem;
}
@media (min-width: 768px) {
  .nx-page {
    padding-inline: var(--space-page-x-desktop);
    padding-block: 1.75rem;
  }
}

.nx-page-header {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1.25rem;
}
.nx-page-header__title {
  font-size: var(--text-xl);
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--color-text-primary);
  margin: 0;
}
.nx-page-header__subtitle {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  margin: 0;
}
.nx-page-header__actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}
@media (min-width: 640px) {
  .nx-page-header {
    flex-direction: row;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
  }
  .nx-page-header__title {
    font-size: var(--text-2xl);
  }
}

.nx-section {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 1.5rem;
}
.nx-section__title {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}
.nx-section__meta {
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-text-meta);
}

.nx-card {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}
.nx-card-header {
  padding: 1rem 1rem 0.75rem;
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}
.nx-card-header__title {
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}
.nx-card-body  { padding: 1rem; }
.nx-card-footer{
  padding: 0.75rem 1rem;
  border-top: 1px solid var(--color-border);
  background: var(--color-bg-muted);
}
@media (min-width: 768px) {
  .nx-card-header { padding: 1.25rem 1.25rem 1rem; }
  .nx-card-body   { padding: 1.25rem; }
  .nx-card-footer { padding: 1rem 1.25rem; }
}
```

- [ ] **Step 2: Build CSS**

Run:
```bash
npm run build:css
```

Expected: build succeeds. `static/css/tailwind.css` now contains the new component classes.

- [ ] **Step 3: Visual sanity check via the temporary scratch page**

Create a temporary file `templates/_nx_scratch.html`:

```html
{% extends "_header.html" %}
{% block content %}
<div class="nx-page">
  <header class="nx-page-header">
    <div>
      <h1 class="nx-page-header__title">Page header title</h1>
      <p class="nx-page-header__subtitle">Subtitle text describing the page</p>
    </div>
    <div class="nx-page-header__actions">
      <button>Primary</button><button>Secondary</button>
    </div>
  </header>
  <section class="nx-section">
    <h2 class="nx-section__title">Section title</h2>
    <div class="nx-card">
      <div class="nx-card-header"><h3 class="nx-card-header__title">Card title</h3></div>
      <div class="nx-card-body">Card body content lives here.</div>
      <div class="nx-card-footer">Card footer</div>
    </div>
  </section>
</div>
{% endblock %}
```

(If `_header.html` doesn't expose a `content` block, register a temporary route in `app.py` that just returns the fragment — the goal is purely visual, not architectural.)

Add a temporary route in `app.py` near the bottom (just before `if __name__ == '__main__':`):
```python
@app.route('/_nx_scratch')
def _nx_scratch():
    return render_template('_nx_scratch.html')
```

Visit `http://127.0.0.1:8000/_nx_scratch` at 375 px and 1280 px window widths. Verify:
- Page padding is 16 px on mobile, 40 px on desktop.
- Header title is 22 px on mobile, 28 px on desktop.
- Card has rounded corners, subtle shadow, bordered footer with muted background.

Delete the temporary file and route once verified — they're scratch only.

- [ ] **Step 4: Commit (user)**

Files to stage: `src/main.css`, `static/css/tailwind.css`.

Suggested message: `mobile foundation: layout patterns (page, section, card)`

---

## Task 5: Button + badge patterns — `nx-btn`, `nx-btn-icon`, `nx-badge`

**Files:**
- Modify: `src/main.css`
- Modify: `static/css/tailwind.css` (rebuilt)

- [ ] **Step 1: Add button + badge patterns to `@layer components`**

Append to the components layer in `src/main.css`:

```css
/* ============================================================
   Buttons & badges
   ============================================================ */
.nx-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.375rem;
  min-height: var(--tap-target-min);
  padding: 0 1rem;
  font-size: var(--text-sm);
  font-weight: 500;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: var(--color-bg-surface);
  color: var(--color-text-primary);
  cursor: pointer;
  text-decoration: none;
  transition: background-color 0.12s, border-color 0.12s, color 0.12s;
  white-space: nowrap;
}
.nx-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--color-focus-ring);
}
.nx-btn:disabled,
.nx-btn[aria-disabled="true"] {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Sizes — default is md (uses tap-target-min). sm collapses height for desktop-dense rows. */
.nx-btn--sm { min-height: 2rem;   padding: 0 0.625rem; font-size: var(--text-xs); }
.nx-btn--lg { min-height: 3rem;   padding: 0 1.25rem;  font-size: var(--text-md); }

/* Variants */
.nx-btn--primary {
  background: var(--color-primary-600);
  color: var(--color-text-on-primary);
  border-color: var(--color-primary-600);
}
.nx-btn--primary:hover { background: var(--color-primary-700); border-color: var(--color-primary-700); }

.nx-btn--secondary {
  background: var(--color-bg-surface);
  color: var(--color-text-primary);
  border-color: var(--color-border-strong);
}
.nx-btn--secondary:hover { background: var(--color-bg-muted); }

.nx-btn--danger {
  background: var(--color-danger);
  color: var(--color-text-on-primary);
  border-color: var(--color-danger);
}
.nx-btn--danger:hover { background: #b91c1c; border-color: #b91c1c; }

.nx-btn--ghost {
  background: transparent;
  color: var(--color-text-secondary);
  border-color: transparent;
}
.nx-btn--ghost:hover { background: var(--color-bg-muted); color: var(--color-text-primary); }

/* Icon-only button — square, no text. aria-label is required. */
.nx-btn-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width:  var(--tap-target-min);
  height: var(--tap-target-min);
  padding: 0;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: background-color 0.12s, color 0.12s;
}
.nx-btn-icon:hover         { background: var(--color-bg-muted); color: var(--color-text-primary); }
.nx-btn-icon:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--color-focus-ring); }

/* Status badge — pill chip. Color set via modifier. */
.nx-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.125rem 0.5rem;
  font-size: var(--text-xs);
  font-weight: 500;
  border-radius: var(--radius-pill);
  background: var(--color-bg-emphasis);
  color: var(--color-text-secondary);
}
.nx-badge--indigo  { background: var(--color-primary-50);  color: var(--color-primary-700); }
.nx-badge--green   { background: var(--color-success-bg);  color: #065f46; }
.nx-badge--amber   { background: var(--color-warning-bg);  color: #92400e; }
.nx-badge--red     { background: var(--color-danger-bg);   color: #991b1b; }
.nx-badge--gray    { background: var(--color-bg-emphasis); color: var(--color-text-secondary); }
```

- [ ] **Step 2: Build CSS**

Run:
```bash
npm run build:css
```

- [ ] **Step 3: Commit (user)**

Files to stage: `src/main.css`, `static/css/tailwind.css`.

Suggested message: `mobile foundation: button & badge patterns`

---

## Task 6: Form patterns — `nx-form-field`, inputs, `nx-action-bar`

**Files:**
- Modify: `src/main.css`
- Modify: `static/css/tailwind.css` (rebuilt)

- [ ] **Step 1: Add form patterns to `@layer components`**

Append to the components layer in `src/main.css`:

```css
/* ============================================================
   Forms & inputs
   ============================================================ */
.nx-form-field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  margin-bottom: 1rem;
}
.nx-form-field__label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
}
.nx-form-field__hint {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}
.nx-form-field__error {
  font-size: var(--text-xs);
  color: var(--color-danger);
}
.nx-form-field--required .nx-form-field__label::after {
  content: " *";
  color: var(--color-danger);
}

.nx-input,
.nx-select,
.nx-textarea {
  width: 100%;
  min-height: var(--tap-target-min);
  padding: 0 0.75rem;
  font-family: var(--font-body);
  font-size: var(--text-md);
  color: var(--color-text-primary);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  box-sizing: border-box;
  transition: border-color 0.12s, box-shadow 0.12s;
}
.nx-textarea {
  min-height: 6rem;
  padding: 0.625rem 0.75rem;
  resize: vertical;
}
.nx-input:focus,
.nx-select:focus,
.nx-textarea:focus {
  outline: none;
  border-color: var(--color-primary-600);
  box-shadow: 0 0 0 3px var(--color-focus-ring);
}
.nx-input--error,
.nx-select--error,
.nx-textarea--error { border-color: var(--color-danger); }

@media (min-width: 768px) {
  .nx-input, .nx-select, .nx-textarea { font-size: var(--text-base); }
}

/* Checkbox / radio — keep native control for a11y, style the wrapper */
.nx-checkbox,
.nx-radio {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  min-height: var(--tap-target-min);
  cursor: pointer;
}
.nx-checkbox input,
.nx-radio input {
  width: 1.125rem;
  height: 1.125rem;
  accent-color: var(--color-primary-600);
}

/* Sticky bottom action bar — mobile only. Inline on md+. */
.nx-action-bar {
  position: sticky;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  gap: 0.5rem;
  padding: 0.75rem var(--space-page-x-mobile);
  background: var(--color-bg-surface);
  border-top: 1px solid var(--color-border);
  box-shadow: var(--shadow-md);
  z-index: 10;
}
.nx-action-bar > .nx-btn { flex: 1; }
@media (min-width: 768px) {
  .nx-action-bar {
    position: static;
    padding: 0;
    background: transparent;
    border-top: 0;
    box-shadow: none;
    justify-content: flex-end;
  }
  .nx-action-bar > .nx-btn { flex: 0 0 auto; }
}
```

- [ ] **Step 2: Build CSS**

Run:
```bash
npm run build:css
```

- [ ] **Step 3: Commit (user)**

Files to stage: `src/main.css`, `static/css/tailwind.css`.

Suggested message: `mobile foundation: form patterns (field, inputs, action bar)`

---

## Task 7: Data-display patterns — `nx-table-stack`, `nx-table-scroll`, `nx-empty-state`, `nx-skeleton-row`

**Files:**
- Modify: `src/main.css`
- Modify: `static/css/tailwind.css` (rebuilt)

- [ ] **Step 1: Add data-display patterns to `@layer components`**

Append to the components layer in `src/main.css`:

```css
/* ============================================================
   Data display
   ============================================================ */

/* nx-table-stack — real <table> on md+, reflows to stacked cards below md.
   Each <td> needs data-label="…" so the column label appears on mobile. */
.nx-table-stack {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}
.nx-table-stack thead th {
  text-align: left;
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-text-secondary);
  background: var(--color-bg-emphasis);
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--color-border);
}
.nx-table-stack tbody td {
  padding: 0.625rem 0.75rem;
  border-bottom: 1px solid var(--color-bg-emphasis);
  color: var(--color-text-primary);
  vertical-align: middle;
}
.nx-table-stack tbody tr:last-child td { border-bottom: 0; }

@media (max-width: 767.98px) {
  .nx-table-stack thead { display: none; }
  .nx-table-stack tbody tr {
    display: block;
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    margin-bottom: 0.5rem;
    padding: 0.625rem 0.75rem;
  }
  .nx-table-stack tbody td {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 0.75rem;
    padding: 0.25rem 0;
    border-bottom: 0;
  }
  .nx-table-stack tbody td::before {
    content: attr(data-label);
    flex: 0 0 auto;
    font-size: var(--text-xs);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--color-text-meta);
  }
  /* If the cell has no data-label, suppress the empty pseudo-element. */
  .nx-table-stack tbody td:not([data-label])::before { content: none; }
}

/* nx-table-scroll — keeps real table on mobile, horizontal scroll with sticky first column. */
.nx-table-scroll {
  width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.nx-table-scroll table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}
.nx-table-scroll thead th {
  position: sticky;
  top: 0;
  background: var(--color-bg-emphasis);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-text-secondary);
  padding: 0.5rem 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--color-border);
}
.nx-table-scroll tbody td { padding: 0.625rem 0.75rem; border-bottom: 1px solid var(--color-bg-emphasis); }
@media (max-width: 767.98px) {
  .nx-table-scroll thead th:first-child,
  .nx-table-scroll tbody td:first-child {
    position: sticky;
    left: 0;
    background: var(--color-bg-surface);
    box-shadow: 1px 0 0 var(--color-border);
  }
}

/* nx-empty-state — for empty lists. */
.nx-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  text-align: center;
  padding: 2.5rem 1rem;
  color: var(--color-text-secondary);
}
.nx-empty-state__icon { font-size: 2rem; color: var(--color-text-meta); }
.nx-empty-state__title {
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--color-text-primary);
}
.nx-empty-state__description { font-size: var(--text-sm); max-width: 28rem; }

/* nx-skeleton-row — shimmer placeholder while loading. */
@keyframes nx-skeleton-shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
.nx-skeleton-row {
  height: 1rem;
  border-radius: var(--radius-sm);
  background: linear-gradient(90deg,
    var(--color-bg-emphasis) 0%,
    var(--color-bg-muted) 50%,
    var(--color-bg-emphasis) 100%);
  background-size: 200% 100%;
  animation: nx-skeleton-shimmer 1.4s ease-in-out infinite;
}
@media (prefers-reduced-motion: reduce) {
  .nx-skeleton-row { animation: none; }
}
```

- [ ] **Step 2: Build CSS**

Run:
```bash
npm run build:css
```

- [ ] **Step 3: Commit (user)**

Files to stage: `src/main.css`, `static/css/tailwind.css`.

Suggested message: `mobile foundation: data-display patterns (table-stack, table-scroll, empty, skeleton)`

---

## Task 8: Overlay patterns — `nx-modal`, `nx-toast`

**Files:**
- Modify: `src/main.css`
- Modify: `static/css/tailwind.css` (rebuilt)

> **Background:** `_header.html` already loads Tailwind Plus Elements (`@tailwindplus/elements@1`), which provides `<el-dialog>` with focus-trap and Escape-to-close. We style its parts with `.nx-modal-*` classes so templates use the element with our visuals applied.

- [ ] **Step 1: Add overlay patterns to `@layer components`**

Append to the components layer in `src/main.css`:

```css
/* ============================================================
   Overlays — modal / sheet / toast
   ============================================================ */

/* The overlay surface that <el-dialog> renders behind itself.
   On md+ we center the panel; on mobile we slide it up from the bottom. */
.nx-modal[open],
.nx-modal[aria-modal="true"] {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  background: rgb(0 0 0 / 0.4);
  padding: 0;
}
.nx-modal__panel {
  background: var(--color-bg-surface);
  width: 100%;
  max-width: 36rem;
  max-height: 90vh;
  border-top-left-radius: var(--radius-lg);
  border-top-right-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}
.nx-modal__header {
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}
.nx-modal__title {
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}
.nx-modal__body  { padding: 1rem 1.25rem; overflow-y: auto; flex: 1 1 auto; }
.nx-modal__footer{
  padding: 0.75rem 1.25rem;
  border-top: 1px solid var(--color-border);
  background: var(--color-bg-muted);
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}

@media (min-width: 768px) {
  .nx-modal[open],
  .nx-modal[aria-modal="true"] { align-items: center; padding: 1.5rem; }
  .nx-modal__panel {
    border-radius: var(--radius-lg);
  }
}

/* Toast — fixed positioning at top, stacks vertically. */
.nx-toast-region {
  position: fixed;
  top: 0.75rem;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  z-index: var(--z-toast);
  pointer-events: none;
  width: calc(100% - 1.5rem);
  max-width: 28rem;
}
.nx-toast {
  pointer-events: auto;
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--color-primary-600);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  padding: 0.75rem 1rem;
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  display: flex;
  align-items: flex-start;
  gap: 0.625rem;
}
.nx-toast--success { border-left-color: var(--color-success); }
.nx-toast--warning { border-left-color: var(--color-warning); }
.nx-toast--danger  { border-left-color: var(--color-danger);  }

@media (min-width: 768px) {
  .nx-toast-region { left: auto; right: 1rem; transform: none; }
}
```

- [ ] **Step 2: Build CSS**

Run:
```bash
npm run build:css
```

- [ ] **Step 3: Commit (user)**

Files to stage: `src/main.css`, `static/css/tailwind.css`.

Suggested message: `mobile foundation: overlay patterns (modal, toast)`

---

## Task 9: Chart pattern — `nx-chart-shell` + Plotly resize helper

**Files:**
- Modify: `src/main.css`
- Modify: `static/css/tailwind.css` (rebuilt)
- Create: `static/js/nx-chart.js`
- Modify: `templates/_header.html` (include the new JS)

- [ ] **Step 1: Add chart-shell pattern to `@layer components`**

Append to the components layer in `src/main.css`:

```css
/* ============================================================
   Charts
   ============================================================ */
.nx-chart-shell {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}
.nx-chart-shell__header {
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.nx-chart-shell__title {
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}
.nx-chart-shell__actions { display: flex; gap: 0.5rem; }
.nx-chart-shell__body {
  position: relative;
  width: 100%;
  min-height: 16rem;
  padding: 0.75rem;
}
.nx-chart-shell__body > .js-plotly-plot,
.nx-chart-shell__body > .plotly-graph-div {
  width: 100% !important;
}

/* KPI tile row that sits above charts on dashboards. Mobile: 2-col grid. md+: row. */
.nx-kpi-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.5rem;
  margin-bottom: 1rem;
}
.nx-kpi {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 0.75rem 0.875rem;
}
.nx-kpi__label {
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-text-meta);
}
.nx-kpi__value {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--color-text-primary);
  margin-top: 0.125rem;
}
@media (min-width: 768px) {
  .nx-kpi-row {
    grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
    gap: 0.75rem;
  }
}
```

- [ ] **Step 2: Create the resize helper JS**

Create `static/js/nx-chart.js`:

```javascript
/* nx-chart.js — observes every .nx-chart-shell__body and asks Plotly
   to resize the contained chart whenever the body's width changes.
   Loaded globally from _header.html. */
(function () {
  if (typeof window === 'undefined') return;

  function resizeIn(body) {
    var plot = body.querySelector('.js-plotly-plot, .plotly-graph-div');
    if (plot && window.Plotly && typeof window.Plotly.Plots === 'object') {
      try { window.Plotly.Plots.resize(plot); } catch (e) { /* noop */ }
    }
  }

  function attach(body) {
    if (body.__nxChartObserver) return;
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', function () { resizeIn(body); });
      return;
    }
    var ro = new ResizeObserver(function () { resizeIn(body); });
    ro.observe(body);
    body.__nxChartObserver = ro;
  }

  function init() {
    document.querySelectorAll('.nx-chart-shell__body').forEach(attach);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Re-scan when new chart shells get added dynamically (e.g., HTMX swaps).
  if (typeof MutationObserver !== 'undefined') {
    new MutationObserver(init).observe(document.documentElement, { childList: true, subtree: true });
  }
})();
```

- [ ] **Step 3: Include the JS in `_header.html`**

Edit `templates/_header.html`. Find the existing `<script src="https://cdn.jsdelivr.net/npm/@tailwindplus/elements@1" type="module"></script>` line and add this immediately after it:

```html
<script src="{{ url_for('static', filename='js/nx-chart.js') }}" defer></script>
```

- [ ] **Step 4: Build CSS**

Run:
```bash
npm run build:css
```

- [ ] **Step 5: Commit (user)**

Files to stage: `src/main.css`, `static/css/tailwind.css`, `static/js/nx-chart.js`, `templates/_header.html`.

Suggested message: `mobile foundation: chart shell pattern + Plotly resize helper`

---

## Task 10: Set up Playwright + axe-core

**Files:**
- Modify: `package.json` (devDeps)
- Create: `playwright.config.js`

- [ ] **Step 1: Add Playwright + axe-core to `package.json` devDeps**

Open `package.json` and update the `devDependencies` block to:

```json
"devDependencies": {
  "@axe-core/playwright": "^4.10.0",
  "@playwright/test": "^1.48.0",
  "@tailwindcss/cli": "^4.0.0",
  "tailwindcss": "^4.0.0"
}
```

- [ ] **Step 2: Install dependencies**

Run:
```bash
npm install
```

- [ ] **Step 3: Install the Chromium browser**

Run:
```bash
npx playwright install chromium
```

Expected: Playwright downloads Chromium (≈ 150 MB). Stored under `%LOCALAPPDATA%\ms-playwright` on Windows — does NOT pollute the repo or `node_modules/`.

- [ ] **Step 4: Create `playwright.config.js`**

Create `playwright.config.js` at repo root:

```javascript
// @ts-check
const { defineConfig, devices } = require('@playwright/test');

/**
 * Playwright config for nexora a11y tests.
 * Assumes nexora is already running on http://127.0.0.1:8000 (via `nx -u`).
 * The test suite logs in using the dev/login route to bypass 2FA.
 */
module.exports = defineConfig({
  testDir: './tests/a11y',
  fullyParallel: false,           /* nexora's session model is single-tenant per browser context */
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: 'http://127.0.0.1:8000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [
    { name: 'chromium-desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'chromium-mobile',  use: { ...devices['iPhone 13'] } },
  ],
});
```

- [ ] **Step 5: Verify Playwright is wired**

Run:
```bash
npx playwright --version
```

Expected: prints the installed version.

- [ ] **Step 6: Commit (user)**

Files to stage: `package.json`, `package-lock.json`, `playwright.config.js`.

Suggested message: `mobile foundation: install Playwright + axe-core`

---

## Task 11: Write the failing a11y test

**Files:**
- Create: `tests/a11y/design-system.spec.js`

> **TDD note:** This step writes a test that depends on `/design-system` existing. It will FAIL at Step 4. Task 12 will create the route + template that makes it PASS.

- [ ] **Step 1: Create the test file**

Create `tests/a11y/design-system.spec.js`:

```javascript
// @ts-check
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

/**
 * Asserts that the /design-system page (which renders every nx-* component)
 * has no WCAG 2.1 AA violations.
 *
 * Pre-requisites:
 *   1. nexora is running on http://127.0.0.1:8000 (start it with `nx -u`).
 *   2. A test user exists with admin.view permission. The dev/login route
 *      (/dev/login/<username>) is used to bypass 2FA in INT.
 *
 * Configure the test username via env var or fall back to `benstreich`:
 *   $env:NX_A11Y_USER = "your_test_user"; npm run test:a11y
 */
const TEST_USER = process.env.NX_A11Y_USER || 'benstreich';

test.describe('/design-system a11y', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/dev/login/${TEST_USER}`);
    /* dev/login redirects to the user's start page on success */
    await expect(page).not.toHaveURL(/\/dev\/login/);
  });

  test('renders without WCAG AA violations', async ({ page }) => {
    await page.goto('/design-system');
    await expect(page).toHaveURL(/\/design-system$/);

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();

    /* If this fails, the violations array describes each rule + the
       offending DOM nodes. Read the report and fix in src/main.css or
       templates/design_system.html. */
    expect(results.violations, JSON.stringify(results.violations, null, 2))
      .toEqual([]);
  });
});
```

- [ ] **Step 2: Make sure nexora is running**

Run:
```bash
nx -u
```

Confirm `http://127.0.0.1:8000/` responds.

- [ ] **Step 3: Run the test**

Run:
```bash
npm run test:a11y -- --project=chromium-desktop
```

- [ ] **Step 4: Verify the test FAILS**

Expected: the `goto('/design-system')` call gets a 404, the URL assertion fails, and the test reports an error like "Expected URL /design-system but got 404 page" or similar.

This is the EXPECTED state — `/design-system` doesn't exist yet. Task 12 builds it.

- [ ] **Step 5: Commit (user)**

Files to stage: `tests/a11y/design-system.spec.js`.

Suggested message: `mobile foundation: failing a11y test for /design-system`

---

## Task 12: Build `/design-system` route + template

**Files:**
- Modify: `app.py` (add route)
- Create: `templates/design_system.html`

- [ ] **Step 1: Add the route to `app.py`**

Find the existing imports / route section in `app.py` and add this route. Place it near the other `@require_permission('admin.view')` routes for consistency. If there's no obvious cluster, place it just above the `if __name__ == '__main__':` block.

```python
@app.route('/design-system')
@require_permission('admin.view')
def design_system():
    """Internal preview page for the nx-* design system patterns.
    Used during development and as a stable target for the axe-core a11y test.
    Gated by admin.view because it's an internal tool, not user-facing."""
    return render_template('design_system.html')
```

If `render_template` and `require_permission` aren't already in scope at that point in the file, they should be — they're used by other routes. Verify with:
```bash
grep -nE "from flask import|@require_permission" app.py | head -5
```

- [ ] **Step 2: Create the design-system template**

Create `templates/design_system.html`:

```html
{% extends "_header.html" %}
{% block title %}Design system — nexora{% endblock %}
{% block content %}
<div class="nx-page" id="design-system">

  <header class="nx-page-header">
    <div>
      <h1 class="nx-page-header__title">Design system</h1>
      <p class="nx-page-header__subtitle">
        Internal reference for the <code>nx-*</code> component library.
        Edit <code>src/main.css</code> and <code>templates/design_system.html</code>
        to extend.
      </p>
    </div>
    <div class="nx-page-header__actions">
      <button class="nx-btn nx-btn--secondary" type="button">Secondary</button>
      <button class="nx-btn nx-btn--primary"   type="button">Primary action</button>
    </div>
  </header>

  <!-- Buttons -->
  <section class="nx-section" aria-labelledby="ds-buttons">
    <h2 class="nx-section__title" id="ds-buttons">Buttons</h2>
    <div class="nx-card">
      <div class="nx-card-body" style="display:flex; flex-wrap:wrap; gap:0.5rem;">
        <button class="nx-btn nx-btn--primary"   type="button">Primary</button>
        <button class="nx-btn nx-btn--secondary" type="button">Secondary</button>
        <button class="nx-btn nx-btn--danger"    type="button">Danger</button>
        <button class="nx-btn nx-btn--ghost"     type="button">Ghost</button>
        <button class="nx-btn nx-btn--primary nx-btn--sm" type="button">Small primary</button>
        <button class="nx-btn nx-btn--primary nx-btn--lg" type="button">Large primary</button>
        <button class="nx-btn-icon" type="button" aria-label="Close">
          <i class="fa-solid fa-xmark" aria-hidden="true"></i>
        </button>
      </div>
    </div>
  </section>

  <!-- Badges -->
  <section class="nx-section" aria-labelledby="ds-badges">
    <h2 class="nx-section__title" id="ds-badges">Badges</h2>
    <div class="nx-card">
      <div class="nx-card-body" style="display:flex; flex-wrap:wrap; gap:0.5rem;">
        <span class="nx-badge nx-badge--indigo">Indigo</span>
        <span class="nx-badge nx-badge--green">Resolved</span>
        <span class="nx-badge nx-badge--amber">In progress</span>
        <span class="nx-badge nx-badge--red">Blocked</span>
        <span class="nx-badge nx-badge--gray">Draft</span>
      </div>
    </div>
  </section>

  <!-- Form fields -->
  <section class="nx-section" aria-labelledby="ds-form">
    <h2 class="nx-section__title" id="ds-form">Form fields</h2>
    <div class="nx-card">
      <div class="nx-card-body">
        <div class="nx-form-field nx-form-field--required">
          <label class="nx-form-field__label" for="ds-name">Full name</label>
          <input class="nx-input" id="ds-name" type="text" placeholder="e.g. Anna Müller">
          <span class="nx-form-field__hint">Shown to colleagues in workitem assignments.</span>
        </div>
        <div class="nx-form-field">
          <label class="nx-form-field__label" for="ds-role">Role</label>
          <select class="nx-select" id="ds-role">
            <option>Engineer</option>
            <option>Manager</option>
            <option>Admin</option>
          </select>
        </div>
        <div class="nx-form-field">
          <label class="nx-form-field__label" for="ds-bio">Notes</label>
          <textarea class="nx-textarea" id="ds-bio" rows="3" placeholder="Optional notes"></textarea>
        </div>
        <div class="nx-form-field">
          <label class="nx-form-field__label" for="ds-broken">Email (with error)</label>
          <input class="nx-input nx-input--error" id="ds-broken" type="email" value="not-an-email" aria-invalid="true" aria-describedby="ds-broken-err">
          <span class="nx-form-field__error" id="ds-broken-err">That doesn't look like a valid email.</span>
        </div>
        <label class="nx-checkbox">
          <input type="checkbox"> I agree to the terms.
        </label>
      </div>
      <div class="nx-action-bar">
        <button class="nx-btn nx-btn--secondary" type="button">Cancel</button>
        <button class="nx-btn nx-btn--primary"   type="submit">Save</button>
      </div>
    </div>
  </section>

  <!-- Table-stack -->
  <section class="nx-section" aria-labelledby="ds-table">
    <h2 class="nx-section__title" id="ds-table">Table — stacks on mobile</h2>
    <div class="nx-card">
      <div class="nx-card-body" style="padding:0;">
        <table class="nx-table-stack">
          <thead>
            <tr>
              <th scope="col">Ticket</th>
              <th scope="col">Subject</th>
              <th scope="col">Status</th>
              <th scope="col">Updated</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td data-label="Ticket"><code>#28114</code></td>
              <td data-label="Subject">VPN access on new laptop</td>
              <td data-label="Status"><span class="nx-badge nx-badge--amber">In progress</span></td>
              <td data-label="Updated">2 h ago</td>
            </tr>
            <tr>
              <td data-label="Ticket"><code>#28113</code></td>
              <td data-label="Subject">Outlook crashes after sync</td>
              <td data-label="Status"><span class="nx-badge nx-badge--red">Blocked</span></td>
              <td data-label="Updated">5 h ago</td>
            </tr>
            <tr>
              <td data-label="Ticket"><code>#28110</code></td>
              <td data-label="Subject">Printer driver missing on PRT-04</td>
              <td data-label="Status"><span class="nx-badge nx-badge--green">Resolved</span></td>
              <td data-label="Updated">yesterday</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <!-- Empty state -->
  <section class="nx-section" aria-labelledby="ds-empty">
    <h2 class="nx-section__title" id="ds-empty">Empty state</h2>
    <div class="nx-card">
      <div class="nx-card-body">
        <div class="nx-empty-state" role="status">
          <div class="nx-empty-state__icon" aria-hidden="true"><i class="fa-regular fa-folder-open"></i></div>
          <p class="nx-empty-state__title">No invoices yet</p>
          <p class="nx-empty-state__description">Once you receive your first invoice it will appear here.</p>
          <button class="nx-btn nx-btn--primary" type="button">Create invoice</button>
        </div>
      </div>
    </div>
  </section>

  <!-- Skeleton row -->
  <section class="nx-section" aria-labelledby="ds-skeleton">
    <h2 class="nx-section__title" id="ds-skeleton">Skeleton (loading)</h2>
    <div class="nx-card">
      <div class="nx-card-body" style="display:flex; flex-direction:column; gap:0.5rem;">
        <div class="nx-skeleton-row" style="width:60%"></div>
        <div class="nx-skeleton-row" style="width:90%"></div>
        <div class="nx-skeleton-row" style="width:75%"></div>
      </div>
    </div>
  </section>

  <!-- Chart shell -->
  <section class="nx-section" aria-labelledby="ds-chart">
    <h2 class="nx-section__title" id="ds-chart">Chart shell</h2>
    <div class="nx-kpi-row">
      <div class="nx-kpi"><div class="nx-kpi__label">Open</div><div class="nx-kpi__value">42</div></div>
      <div class="nx-kpi"><div class="nx-kpi__label">In progress</div><div class="nx-kpi__value">17</div></div>
      <div class="nx-kpi"><div class="nx-kpi__label">Resolved</div><div class="nx-kpi__value">128</div></div>
      <div class="nx-kpi"><div class="nx-kpi__label">Blocked</div><div class="nx-kpi__value">3</div></div>
    </div>
    <div class="nx-chart-shell">
      <div class="nx-chart-shell__header">
        <h3 class="nx-chart-shell__title">Tickets by status (placeholder)</h3>
        <div class="nx-chart-shell__actions">
          <button class="nx-btn nx-btn--ghost nx-btn--sm" type="button">7d</button>
          <button class="nx-btn nx-btn--ghost nx-btn--sm" type="button">30d</button>
        </div>
      </div>
      <div class="nx-chart-shell__body">
        <!-- Real Plotly chart goes here on dashboard pages.
             Show a static stand-in here so a11y test runs without Plotly. -->
        <div class="nx-skeleton-row" style="width:100%; height:14rem;"></div>
      </div>
    </div>
  </section>

  <!-- Modal trigger -->
  <section class="nx-section" aria-labelledby="ds-modal">
    <h2 class="nx-section__title" id="ds-modal">Modal / bottom sheet</h2>
    <div class="nx-card">
      <div class="nx-card-body">
        <p>The modal uses Tailwind Plus Elements <code>&lt;el-dialog&gt;</code> for focus trap.
        Click the button to open. On mobile it slides up from the bottom; on md+ it centers.</p>
        <button class="nx-btn nx-btn--primary" type="button" id="ds-open-modal">Open modal</button>
      </div>
    </div>

    <el-dialog>
      <dialog class="nx-modal" aria-labelledby="ds-modal-title">
        <div class="nx-modal__panel">
          <header class="nx-modal__header">
            <h2 class="nx-modal__title" id="ds-modal-title">Confirm action</h2>
            <button class="nx-btn-icon" type="button" aria-label="Close" data-dialog-close>
              <i class="fa-solid fa-xmark" aria-hidden="true"></i>
            </button>
          </header>
          <div class="nx-modal__body">
            <p>Are you sure you want to proceed? This action cannot be undone.</p>
          </div>
          <footer class="nx-modal__footer">
            <button class="nx-btn nx-btn--secondary" type="button" data-dialog-close>Cancel</button>
            <button class="nx-btn nx-btn--primary"   type="button">Confirm</button>
          </footer>
        </div>
      </dialog>
    </el-dialog>

    <script>
      document.getElementById('ds-open-modal')?.addEventListener('click', function () {
        const dialog = document.querySelector('#design-system el-dialog dialog');
        if (dialog) dialog.showModal();
      });
      document.querySelectorAll('#design-system [data-dialog-close]').forEach(function (el) {
        el.addEventListener('click', function () {
          const dialog = el.closest('dialog');
          if (dialog) dialog.close();
        });
      });
    </script>
  </section>

  <!-- Toast region -->
  <section class="nx-section" aria-labelledby="ds-toast">
    <h2 class="nx-section__title" id="ds-toast">Toast</h2>
    <div class="nx-card">
      <div class="nx-card-body">
        <p>Toasts render in a fixed region at the top of the viewport.
           This page renders one inline as an a11y example:</p>
        <div class="nx-toast nx-toast--success" role="status">
          <i class="fa-solid fa-check" aria-hidden="true"></i>
          <span>Saved successfully.</span>
        </div>
      </div>
    </div>
  </section>
</div>
{% endblock %}
```

- [ ] **Step 3: Verify the page renders manually**

Make sure nexora is running (`nx -u`). Visit:

```
http://127.0.0.1:8000/dev/login/<your_admin_user>
```

Then:

```
http://127.0.0.1:8000/design-system
```

Expected: every section renders. The modal opens / closes. Resize the window to 375 px wide and verify:
- Page padding shrinks to 16 px
- Header title shrinks to 22 px and the actions wrap below the title
- The table reflows: thead disappears, each row becomes a card, cells show their `data-label` value
- The action bar in the form section sticks to the viewport bottom
- The KPI tiles render in 2 columns

- [ ] **Step 4: Run the a11y test — should now PASS**

```bash
npm run test:a11y -- --project=chromium-desktop
```

Expected: PASS.

If it FAILS with violations:
- Read the JSON dumped on failure — each violation lists the rule and the offending nodes.
- Common fixes:
  - `aria-hidden` icons inside text-bearing buttons that already have visible text → keep the icon `aria-hidden="true"` and let the visible text be the accessible name.
  - Missing `for` ↔ `id` association on labels → make sure every `<label>` has a `for` and the matching input has an `id`.
  - Color-contrast → adjust the offending token usage; the design tokens were chosen to meet AA but custom usage might fall short.

- [ ] **Step 5: Run the a11y test on the mobile project too**

```bash
npm run test:a11y -- --project=chromium-mobile
```

Expected: PASS at the iPhone 13 viewport. Same fixes apply if anything mobile-specific surfaces (e.g., the bottom action bar should not occlude focusable elements; the modal footer buttons should be reachable).

- [ ] **Step 6: Commit (user)**

Files to stage: `app.py`, `templates/design_system.html`.

Suggested message: `mobile foundation: /design-system route + template (a11y test now green)`

---

## Task 13: CI workflow — CSS in-sync check + Playwright a11y test

**Files:**
- Create: `.github/workflows/build-and-test.yml`

> **Server requirement:** the a11y test needs nexora running. The CI workflow boots nexora as a background service before invoking Playwright. Because nexora's `app.py` reads `INT.env`, the CI box must have access to the same DBs INT does — meaning this workflow should only run from runners that can reach the INT SQL servers. Existing `deploy.yml` is a precedent for "use INT credentials in CI." Mirror that.

- [ ] **Step 1: Inspect the existing `deploy.yml` for runner / secrets pattern**

Run:
```bash
cat .github/workflows/deploy.yml
```

Note which runner label is used (`runs-on:`). The new workflow should use the same runner so it has the same network access to INT DBs. If INT credentials live in `INT.env` (committed), no secret extraction is needed; if they're pulled from GH secrets, mirror that.

- [ ] **Step 2: Create `.github/workflows/build-and-test.yml`**

Create the file. Replace `<RUNNER>` in the template below with the runner label observed in step 1 (likely `self-hosted` or `windows-latest` — adjust to match deploy.yml):

```yaml
name: Build & a11y test

on:
  pull_request:
    paths:
      - 'src/**'
      - 'static/**'
      - 'templates/**'
      - 'package.json'
      - 'package-lock.json'
      - 'playwright.config.js'
      - 'tests/**'
      - '.github/workflows/build-and-test.yml'
  push:
    branches: [main]

jobs:
  css-in-sync:
    runs-on: <RUNNER>
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - name: Install dependencies
        run: npm ci
      - name: Build CSS
        run: npm run build:css
      - name: Verify static/css/tailwind.css is in sync with src/main.css
        run: git diff --exit-code static/css/tailwind.css

  a11y:
    runs-on: <RUNNER>
    needs: css-in-sync
    env:
      ENVIRONMENT: INT
      NX_A11Y_USER: a11y_test_user
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - name: Install Node dependencies
        run: npm ci
      - name: Install Chromium
        run: npx playwright install --with-deps chromium
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'
          cache: pip
      - name: Install Python dependencies
        run: pip install -r requirements.txt
      - name: Boot nexora in background
        shell: bash
        run: |
          python app.py &
          echo $! > nexora.pid
          for i in {1..40}; do
            if curl -fs http://127.0.0.1:8000/healthz >/dev/null 2>&1 \
               || curl -fs http://127.0.0.1:8000/ >/dev/null 2>&1; then
              echo "nexora is up"; exit 0
            fi
            sleep 1
          done
          echo "nexora failed to start"; exit 1
      - name: Run a11y tests
        run: npm run test:a11y
      - name: Stop nexora
        if: always()
        shell: bash
        run: |
          if [ -f nexora.pid ]; then
            kill "$(cat nexora.pid)" 2>/dev/null || true
          fi
      - name: Upload Playwright report on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: playwright-report
          retention-days: 14
```

- [ ] **Step 3: Configure the test user via GitHub secret**

The CI workflow above reads `NX_A11Y_USER` from the workflow `env:`. Don't create a new test user — use an existing INT admin user (the one you already log in with for manual testing is fine, e.g., `benstreich`).

Two options for setting the value:

**Option A (recommended): GitHub repository secret.** In the repo on GitHub: Settings → Secrets and variables → Actions → New repository secret. Name: `NX_A11Y_USER`, Value: an existing admin username. Then change the workflow's `env:` block from:

```yaml
NX_A11Y_USER: a11y_test_user
```

to:

```yaml
NX_A11Y_USER: ${{ secrets.NX_A11Y_USER }}
```

**Option B (simpler): hard-code the username in the workflow.** Replace `a11y_test_user` directly with the real admin username. Acceptable if the username isn't sensitive — this repo's INT.env is already committed, so usernames are not a guarded secret anyway.

Pick one and update the YAML accordingly. No SQL changes needed.

- [ ] **Step 4: Verify the workflow YAML is valid**

Run a YAML syntax check (e.g., paste into actionlint, or use the GitHub UI's Actions → Workflows preview). No runtime check is possible without a PR.

- [ ] **Step 5: Commit (user)**

Files to stage: `.github/workflows/build-and-test.yml`. (Do NOT commit any SQL — the user appends it to `environment_transfer_queries.tmp.sql` and runs it manually per the project's git rule.)

Suggested message: `mobile foundation: CI workflow for CSS sync + a11y`

---

## Task 14: Author `howtocss.txt`

**Files:**
- Create: `howtocss.txt`

Match the project's existing convention (`howtoiis.txt`, `howtongrok.txt`, `howtobabel.txt`). Plain text, terse, copy-paste-able commands.

- [ ] **Step 1: Create `howtocss.txt`**

Write `howtocss.txt`:

```
nexora frontend / Tailwind v4 — how to

PREREQUISITES
  - Node.js 20+ (npm 10+) installed locally. Not needed on the IIS server.
  - Run `npm install` once after cloning or after package.json changes.

WHERE THINGS LIVE
  - Source CSS:           src/main.css
    - @theme block:       all design tokens (colors, type, spacing, radii, shadows, breakpoints)
    - @layer components:  every nx-* component class
  - Built CSS:            static/css/tailwind.css   (committed; do NOT edit by hand)
  - Resize helper JS:     static/js/nx-chart.js
  - Design preview:       templates/design_system.html  (route: /design-system, admin.view)
  - Per-page CSS:         static/css/<page>.css         (deprecated as each page migrates)

BUILD
  - One-shot:             npm run build:css
  - Watch mode:           npm run watch:css        (rebuilds on src/main.css change)
  - Always re-build before committing CSS-related changes; the CI workflow
    "Build & a11y test" fails if static/css/tailwind.css is out of sync.

A11Y TEST
  - Make sure nexora is running:    nx -u
  - Run the test:                   npm run test:a11y
  - Run only desktop project:       npm run test:a11y -- --project=chromium-desktop
  - Run only mobile project:        npm run test:a11y -- --project=chromium-mobile
  - Override the test user:         $env:NX_A11Y_USER = "your_admin_user"; npm run test:a11y

ADDING A NEW PATTERN
  1. Open src/main.css.
  2. Inside @layer components, append a .nx-<name> rule. Use @apply for Tailwind
     compositions where useful; raw CSS is fine for things Tailwind utilities
     don't cover well (pseudo-elements, complex media queries, etc.).
  3. Reference tokens through their CSS custom properties (var(--color-…)) so
     the pattern stays in sync if a token changes.
  4. Run npm run build:css.
  5. Add a section to templates/design_system.html that demonstrates the new
     pattern in every state (default, hover, focus, disabled, error, etc.).
  6. npm run test:a11y to confirm a11y is still clean.
  7. Commit src/main.css + static/css/tailwind.css + templates/design_system.html.

MIGRATING A PAGE TO THE FOUNDATION
  1. Read the spec: docs/superpowers/specs/2026-05-07-mobile-foundation-design.md
     (section 7 has the per-page checklist)
  2. Wrap the page in <div class="nx-page">.
  3. Replace the page's bespoke header with nx-page-header.
  4. Replace cards / sections with nx-card / nx-section.
  5. Tables -> nx-table-stack (default) or nx-table-scroll (variant), with
     data-label="…" on every <td>.
  6. Forms -> wrap each input in nx-form-field; use nx-input/nx-select etc.;
     replace inline buttons with nx-btn variants.
  7. Modals -> wrap in <el-dialog> + .nx-modal; use the existing pattern
     in templates/design_system.html as a reference.
  8. Charts -> wrap Plotly containers in nx-chart-shell; ensure they have
     class "js-plotly-plot" or the plotly default so nx-chart.js can find them.
  9. Smoke at 375 / 640 / 768 / 1024 / 1280 px in browser devtools.
 10. Delete (or shrink) static/css/<page>.css.
 11. Open one PR titled `mobile: <page name> migration`. Include before/after
     screenshots at mobile and desktop, saved to screenshots/.

GOTCHAS
  - Do NOT re-add the Tailwind browser CDN <script>. The compiled CSS is loaded
    from _header.html via <link rel="stylesheet">.
  - admin-tokens.css still loads on admin pages until those pages migrate
    (phase 7). Its --a-* variables are namespaced separately from the new
    --color-* tokens, so they coexist without conflict.
  - Tailwind v4 scans .html files in the project automatically. If a utility
    class you wrote in a template doesn't apply, run `npm run build:css` and
    confirm it ended up in static/css/tailwind.css. If not, double-check the
    @source directive at the top of src/main.css.
  - Plotly charts must live inside .nx-chart-shell__body for the resize
    helper to find them.
```

- [ ] **Step 2: Commit (user)**

Files to stage: `howtocss.txt`.

Suggested message: `mobile foundation: howtocss.txt dev workflow doc`

---

## Done

After Task 14, Phase 0 is complete. The repo now has:

- A compiled Tailwind v4 pipeline driven by `src/main.css` → `static/css/tailwind.css`.
- A complete token system + `nx-*` component library covering every pattern in the spec.
- A `/design-system` route that previews every component and serves as a stable a11y test target.
- Playwright + axe-core wired up with a green a11y test on both desktop and mobile viewports.
- A CI workflow that fails PRs if the committed CSS drifts from `src/main.css` or the a11y test regresses.
- A `howtocss.txt` doc explaining how to extend the system or migrate a page.

**Next step:** open a new brainstorming session for Phase 1 (header / global nav migration). The patterns and infrastructure are now in place; phase 1 is mostly applying them to `_header.html`, `_maintenance_banner.html`, `_small_footer.html`, and `_nexoraVersion.html`.
