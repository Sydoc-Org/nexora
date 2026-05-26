# Mobile UI Foundation — Phase 1: Header / Global Nav — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Project git rule (HARD):** This repo's `CLAUDE.md` prohibits Claude from running any git command that modifies the index or history. Every `Commit` step is **the user's job**, not Claude's. After completing the file edits in a step, surface the diff to the user and stop. Suggested commit messages are advisory.

**Goal:** Polish the existing mobile sidebar / global chrome to use Phase 0 tokens, meet WCAG AA keyboard/focus/ARIA requirements, and have ≥ 44 px tap targets on every interactive element on mobile — without rewriting working code.

**Architecture:** In-place edits to existing files (`_header.css`, `_header.html`, `_headerJS.html`, `_maintenance_banner.html`, `_small_footer.html`, `_nexoraVersion.html`). Add one small new `nx-link-muted` component class to `src/main.css`. Add one new axe-core test in `tests/a11y/header.spec.js` that scans the open drawer at mobile viewport.

**Tech Stack:** Tailwind v4 (existing), `nx-*` design system from Phase 0, Playwright + `@axe-core/playwright` (existing), Flask + Jinja2 (existing).

---

## File Structure

**Created:**
- `tests/a11y/header.spec.js` — axe-core test asserting the open drawer on `/dashboard` has zero WCAG AA violations and that ESC closes it.

**Modified:**
- `src/main.css` — add one `.nx-link-muted` rule to `@layer components`.
- `static/css/tailwind.css` — rebuilt.
- `static/css/_header.css` — lossless light-mode color → token migration; tap-target adjustment on `.sidebar-nav-subitem`.
- `templates/_header.html` — add ARIA attributes to `#sidebar-toggle`, `#nexora-sidebar`, `#sidebar-backdrop`.
- `templates/js/_headerJS.html` — extend existing sidebar handler (lines 442–478) with `aria-expanded`, `inert`, focus management, ESC handler, focus trap.
- `templates/_maintenance_banner.html` — inline-style token sweep; `.mb-dismiss` becomes 44 × 44; localize `aria-label`.
- `templates/_small_footer.html` — replace per-link `text-gray-600 hover:text-blue-500` with `nx-link-muted`; mobile tap-area wrapper.
- `templates/_nexoraVersion.html` — replace `text-gray-500` with `nx-link-muted`-aligned styling.
- `templates/design_system.html` — add "Header / nav (mobile chrome)" section with one `nx-link-muted` example and a docs reference.

**Untouched:**
- `app.py`, all dark-mode rules in `_header.css` (`html.dark …`), the command palette (`#cmdkOverlay`), notification panel, profile dropdown, dashboard / workitems / generali / admin pages.

---

## Task 1: Add `.nx-link-muted` component class

**Files:**
- Modify: `src/main.css`
- Modify: `static/css/tailwind.css` (rebuilt)

- [ ] **Step 1: Read the end of the components layer**

Run:
```bash
grep -nE "^  /\* =+|^}" src/main.css | tail -10
```

Find the section header for "Charts" and the closing `}` of the `@layer components` block. The new rule goes immediately before the layer-closing `}`.

- [ ] **Step 2: Append `.nx-link-muted` to the `@layer components` block**

Use the Edit tool. Find the END of the chart patterns section (the closing `}` of the `@media (min-width: 768px) { .nx-kpi-row { ... } }` block followed by the `@layer components` block's closing `}`):

```css
  @media (min-width: 768px) {
    .nx-kpi-row {
      grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
      gap: 0.75rem;
    }
  }
}
```

Replace with:

```css
  @media (min-width: 768px) {
    .nx-kpi-row {
      grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
      gap: 0.75rem;
    }
  }

  /* ============================================================
     Text links — muted by default, primary on hover. Used in the
     footer, banner, and inline anywhere a non-button-styled link
     fits. Pairs with utility size classes (text-sm, etc.).
     ============================================================ */
  .nx-link-muted {
    color: var(--color-text-secondary);
    text-decoration: none;
    transition: color 0.12s;
  }
  .nx-link-muted:hover { color: var(--color-primary-600); }
  .nx-link-muted:focus-visible {
    outline: none;
    box-shadow: 0 0 0 3px var(--color-focus-ring);
    border-radius: var(--radius-sm);
  }
}
```

- [ ] **Step 3: Build CSS**

Run:
```bash
npm run build:css
```

Expected: `Done in <ms>` with no errors. `static/css/tailwind.css` regenerates.

- [ ] **Step 4: Verify the new class is in the compiled output**

Run:
```bash
grep -oE "\.nx-link-muted[a-zA-Z_-]*" static/css/tailwind.css | sort -u
```

Expected: at least one match for `.nx-link-muted`. There will also be hover and focus-visible rules visible by grepping with broader patterns.

- [ ] **Step 5: Commit (user)**

Files to stage: `src/main.css`, `static/css/tailwind.css`.

Suggested message: `mobile p1: nx-link-muted component class`

---

## Task 2: Token migration in `_header.css`

**Files:**
- Modify: `static/css/_header.css`

> **Migrate only LOSSLESS matches.** Do NOT touch anything inside `html.dark …` rules (dark mode is out of scope). Do NOT migrate values without an exact token match (`#374151`, `#3730a3`, `#f5f3ff`, `#fafafa`, `#22c55e`, `#ef4444`).

- [ ] **Step 1: Make a list of in-scope replacements**

The mappings to apply, **only outside `html.dark …` blocks**:

| Old hex | Replace with |
|---|---|
| `#f9fafb` | `var(--color-bg-page)` |
| `#ffffff` | `var(--color-bg-surface)` |
| `#fff` | `var(--color-bg-surface)` |
| `#f3f4f6` | `var(--color-bg-emphasis)` |
| `#e5e7eb` | `var(--color-border)` |
| `#1f2937` | `var(--color-text-primary)` |
| `#6b7280` | `var(--color-text-secondary)` |
| `#9ca3af` | `var(--color-text-meta)` |
| `#4f46e5` | `var(--color-primary-600)` |
| `#eef2ff` | `var(--color-primary-50)` |
| `#e0e7ff` | `var(--color-primary-100)` |

- [ ] **Step 2: Identify dark-mode regions to skip**

Run:
```bash
grep -nE "^html\.dark|@media.*prefers-color-scheme.*dark" static/css/_header.css
```

Note the line ranges where dark-mode rules begin (e.g. `html.dark #nexora-sidebar { … }`). Each rule typically ends on the next blank line or at the next selector. **Within these blocks, do NOT migrate hex values.**

- [ ] **Step 3: Use the Edit tool with `replace_all: true` per mapping, for each in-scope value**

For each mapping in the table above, do a careful per-value edit. The safest approach: use the Edit tool with `replace_all: true` and `old_string` set to the full property+value pair so you don't accidentally replace dark-mode usages.

Example: instead of `replace_all` on the bare hex `#f9fafb`, edit specific declaration patterns:

For `#f9fafb` (used as background):
```
old_string: "background: #f9fafb;"
new_string: "background: var(--color-bg-page);"
```

Or with a leading shorthand:
```
old_string: "background-color: #f9fafb;"
new_string: "background-color: var(--color-bg-page);"
```

This pattern won't match inside `html.dark …` rules because those use the slate values, not these light-mode hexes.

Repeat for each mapping. Be patient — there are ~10 unique values × roughly 2-3 occurrences each = ~25 edits.

If a hex appears in BOTH a light-mode rule AND somewhere else (e.g. `#1f2937` is light-mode `--color-text-primary` AND a dark-mode bg), the property-value-pair approach naturally distinguishes:
- `color: #1f2937;` → `color: var(--color-text-primary);` (light mode, migrate)
- `background: #1f2937;` → leave as-is (dark mode)

If unsure about a specific occurrence, leave it as a hex. Conservative.

- [ ] **Step 4: Verify dark-mode rules are untouched**

Run:
```bash
grep -A2 "^html\.dark" static/css/_header.css | head -40
```

Confirm the dark-mode rules still have their slate hex values (`#0f172a`, `#1e293b`, etc.). If any `var(--color-…)` accidentally landed inside an `html.dark` block, revert it (use Edit to put the hex back).

- [ ] **Step 5: Verify no light-mode hex from the migration table remains**

For each migrated hex, scan the file:

```bash
for hex in "#f9fafb" "#f3f4f6" "#e5e7eb" "#1f2937" "#6b7280" "#9ca3af" "#4f46e5" "#eef2ff" "#e0e7ff"; do
  count=$(grep -cE "$hex" static/css/_header.css || true)
  echo "$hex: $count remaining"
done
```

Expected: each migrated value should still have SOME occurrences (those inside `html.dark` rules). If a value has 0 remaining and you didn't migrate any dark-mode usages of it (you shouldn't have), that's fine. Sanity-check that the count went DOWN from before.

If counts seem off, run `git diff static/css/_header.css | head -60` to inspect what changed.

- [ ] **Step 6: Smoke-test that nexora still renders**

Make sure nexora is running:
```bash
curl -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8000/
```

Expected: 200/302. If 500, you broke the CSS — review the diff. Common breakage: a token name typo (`var(--color-bg-pgae)` instead of `var(--color-bg-page)`).

The visual rendering can't be verified by curl. Note that the user will smoke-test visually before committing — this step just confirms we didn't break the page.

- [ ] **Step 7: Commit (user)**

Files to stage: `static/css/_header.css`.

Suggested message: `mobile p1: migrate _header.css light-mode colors to tokens`

---

## Task 3: Bump tap-target on `.sidebar-nav-subitem`

**Files:**
- Modify: `static/css/_header.css`

- [ ] **Step 1: Locate the rule**

The rule is around line 175. Open in `static/css/_header.css`:
```css
.sidebar-nav-subitem {
    padding-left: 20px;
}
```

- [ ] **Step 2: Update padding to give breathing room above 44 px**

Use the Edit tool. Replace:

```css
.sidebar-nav-subitem {
    padding-left: 20px;
}
```

With:

```css
.sidebar-nav-subitem {
    padding-left: 20px;
    padding-block: 12px;
}
```

This raises the per-item height from ~44 px (right at the threshold) to ~48 px on mobile.

- [ ] **Step 3: Commit (user)**

Files to stage: `static/css/_header.css`.

Suggested message: `mobile p1: bump sidebar-nav-subitem tap target to 48px`

---

## Task 4: Maintenance banner — token sweep + 44 × 44 dismiss button + locale

**Files:**
- Modify: `templates/_maintenance_banner.html`

- [ ] **Step 1: Migrate inline-style colors (lossless only)**

Open `templates/_maintenance_banner.html`. The inline `<style>` block has color rules for `.mb-info`, `.mb-warning`, `.mb-critical` plus borders/dismiss-button.

Do the following exact edit with the Edit tool:

Find:
```css
  #maintenance-banner.mb-info     { background: #eef2ff; color: #3730a3; border-bottom: 1px solid #c7d2fe; }
```

Replace with:
```css
  #maintenance-banner.mb-info     { background: var(--color-primary-50); color: #3730a3; border-bottom: 1px solid #c7d2fe; }
```

Note: `#3730a3` (indigo-800) and `#c7d2fe` (indigo-200) have NO exact tokens. They're kept hex per the spec.

The warning and critical rules (`#fffbeb` / `#fef2f2` / etc.) have NO exact tokens either — leave them entirely as-is.

- [ ] **Step 2: Convert `.mb-dismiss` to a 44 × 44 icon button**

Find:
```css
  #maintenance-banner .mb-dismiss {
    flex: 0 0 auto;
    background: transparent;
    border: 0;
    color: inherit;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 6px;
    opacity: 0.8;
  }
```

Replace with:
```css
  #maintenance-banner .mb-dismiss {
    flex: 0 0 auto;
    width: 44px;
    height: 44px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: 0;
    color: inherit;
    cursor: pointer;
    padding: 0;
    border-radius: 6px;
    opacity: 0.8;
  }
```

- [ ] **Step 3: Localize the `aria-label` on the dismiss button**

The button is constructed in JS (in the same file). Find:

```javascript
        btn.setAttribute('aria-label', 'Dismiss');
```

Replace with:

```javascript
        btn.setAttribute('aria-label', {{ _('Dismiss') | tojson }});
```

(`| tojson` ensures the translated string is properly JS-string-escaped even if it contains apostrophes.)

- [ ] **Step 4: Smoke-check the banner template renders without Jinja errors**

Make sure nexora is running, then:
```bash
curl -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8000/
```

Expected: 200/302. A Jinja syntax error from the `| tojson` filter would produce 500. (`tojson` is a standard Jinja filter, so this should be fine.)

- [ ] **Step 5: Commit (user)**

Files to stage: `templates/_maintenance_banner.html`.

Suggested message: `mobile p1: maintenance banner — token sweep + 44px dismiss + i18n`

---

## Task 5: Footer + version — adopt `nx-link-muted` and tap-target wrapper

**Files:**
- Modify: `templates/_small_footer.html`
- Modify: `templates/_nexoraVersion.html`

- [ ] **Step 1: Update footer link styling**

Open `templates/_small_footer.html`. Replace each instance of:

```html
class="text-sm text-gray-600 transition-colors duration-300 hover:text-blue-500"
```

with:

```html
class="text-sm nx-link-muted"
```

There are 6 such anchor links. Use the Edit tool with `replace_all: true` on the exact class string.

Some of the existing anchors have trailing whitespace inside the class attribute — be precise. For example, two of them have `hover:text-blue-500 ` (with a trailing space). Edit those specifically OR use `replace_all` on the variant with the trailing space too.

After editing, the structure of each link should look like:

```html
<a href="https://sydoc.ch/ueber-sydoc/" class="text-sm nx-link-muted">
    {{ _('About sydoc') }}
</a>
```

- [ ] **Step 2: Add a mobile tap-area wrapper around the link list**

Currently the link container is:

```html
<div class="flex flex-wrap items-center justify-center gap-4 mt-6 lg:gap-6 lg:mt-0">
```

Replace with:

```html
<div class="flex flex-wrap items-center justify-center gap-4 mt-6 lg:gap-6 lg:mt-0 [&>a]:py-2 [&>a]:min-h-[44px] [&>a]:flex [&>a]:items-center lg:[&>a]:py-0 lg:[&>a]:min-h-0">
```

This applies `py-2`, `min-h-[44px]`, `flex`, and `items-center` to every direct `<a>` child on mobile, and resets them on `lg+` to keep the desktop look unchanged. Tailwind v4's arbitrary child variants (`[&>a]:…`) make this clean.

- [ ] **Step 3: Update `_nexoraVersion.html`**

Open `templates/_nexoraVersion.html`. The current `<p>` has class `mt-6 text-sm text-gray-500 lg:mt-0`. Replace `text-gray-500` with a token-aligned color via inline style; we have a `--color-text-meta` token but no Tailwind utility bound to it.

Find the `<p>` opening tag (it has `class="mt-6 text-sm text-gray-500 lg:mt-0"`) and replace JUST the class attribute with:

```
class="mt-6 text-sm lg:mt-0" style="color: var(--color-text-meta)"
```

Leave the rest of the file unchanged — the year-printing script and the surrounding text stay as-is.

- [ ] **Step 4: Build CSS**

Run:
```bash
npm run build:css
```

The Tailwind compiler scans templates for utility classes; the new `[&>a]:py-2` etc. will be detected on this rebuild. Expected: build succeeds.

- [ ] **Step 5: Verify footer renders without breakage**

```bash
curl -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8000/
```

Expected: 200/302.

- [ ] **Step 6: Commit (user)**

Files to stage: `templates/_small_footer.html`, `templates/_nexoraVersion.html`, `static/css/tailwind.css`.

Suggested message: `mobile p1: footer + version — nx-link-muted + mobile tap targets`

---

## Task 6: ARIA attributes on `_header.html`

**Files:**
- Modify: `templates/_header.html`

- [ ] **Step 1: Update the hamburger toggle**

Find this exact line in `templates/_header.html` (around line 21):

```html
    <button id="sidebar-toggle" class="sidebar-toggle-btn" aria-label="{{ _('Open navigation') }}" type="button">
```

Replace with:

```html
    <button id="sidebar-toggle" class="sidebar-toggle-btn" aria-label="{{ _('Open navigation') }}" aria-controls="nexora-sidebar" aria-expanded="false" type="button">
```

- [ ] **Step 2: Update the backdrop**

Find:

```html
    <div id="sidebar-backdrop" class="sidebar-backdrop"></div>
```

Replace with:

```html
    <div id="sidebar-backdrop" class="sidebar-backdrop" aria-hidden="true"></div>
```

- [ ] **Step 3: Update the `<aside>`**

Find:

```html
    <aside id="nexora-sidebar">
```

Replace with:

```html
    <aside id="nexora-sidebar" role="navigation" aria-label="{{ _('Main navigation') }}">
```

- [ ] **Step 4: Verify the page still renders**

```bash
curl -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8000/
```

Expected: 200/302.

- [ ] **Step 5: Commit (user)**

Files to stage: `templates/_header.html`.

Suggested message: `mobile p1: ARIA attrs on header (controls, expanded, role, label)`

---

## Task 7: JS — focus management, ESC, focus trap, `inert`

**Files:**
- Modify: `templates/js/_headerJS.html`

> The existing handler at lines 442–478 stays intact. We extend `openSidebar` and `closeSidebar`, then append new top-level keydown listeners and an init block.

- [ ] **Step 1: Read the current handler**

Run:
```bash
grep -nA40 "Mobile sidebar drawer toggle" templates/js/_headerJS.html
```

Confirm the structure matches what's documented in the spec (lines 442–478, with `openSidebar`, `closeSidebar`, click handler, link-click close, resize close).

- [ ] **Step 2: Replace the entire handler block with the extended version**

Use the Edit tool. Find this exact block:

```javascript
        /* ---- Mobile sidebar drawer toggle ---- */
        document.addEventListener('DOMContentLoaded', function () {
            const toggle   = document.getElementById('sidebar-toggle');
            const sidebar  = document.getElementById('nexora-sidebar');
            const backdrop = document.getElementById('sidebar-backdrop');
            if (!toggle || !sidebar || !backdrop) return;

            function openSidebar() {
                sidebar.classList.add('open');
                backdrop.classList.add('open');
                toggle.querySelector('i').className = 'fas fa-times';
            }
            function closeSidebar() {
                sidebar.classList.remove('open');
                backdrop.classList.remove('open');
                toggle.querySelector('i').className = 'fas fa-bars';
            }

            toggle.addEventListener('click', (e) => {
                e.stopPropagation();
                if (sidebar.classList.contains('open')) closeSidebar();
                else openSidebar();
            });
            backdrop.addEventListener('click', closeSidebar);

            // Close when a nav link is tapped (keeps drawer UX snappy)
            sidebar.querySelectorAll('a.sidebar-nav-item').forEach(link => {
                link.addEventListener('click', () => {
                    if (window.matchMedia('(max-width: 768px)').matches) closeSidebar();
                });
            });

            // Auto-close when resizing back to desktop
            window.addEventListener('resize', () => {
                if (window.innerWidth > 768) closeSidebar();
            });
        });
```

Replace with:

```javascript
        /* ---- Mobile sidebar drawer toggle (with a11y) ---- */
        document.addEventListener('DOMContentLoaded', function () {
            const toggle   = document.getElementById('sidebar-toggle');
            const sidebar  = document.getElementById('nexora-sidebar');
            const backdrop = document.getElementById('sidebar-backdrop');
            if (!toggle || !sidebar || !backdrop) return;

            const mql = window.matchMedia('(max-width: 768px)');

            function setExpanded(expanded) {
                toggle.setAttribute('aria-expanded', String(expanded));
            }
            function applyInert() {
                /* Sidebar links must not be tab-reachable behind the backdrop on mobile. */
                if (mql.matches && !sidebar.classList.contains('open')) {
                    sidebar.setAttribute('inert', '');
                } else {
                    sidebar.removeAttribute('inert');
                }
            }

            function openSidebar() {
                sidebar.classList.add('open');
                backdrop.classList.add('open');
                toggle.querySelector('i').className = 'fas fa-times';
                setExpanded(true);
                applyInert();
                /* Focus the first focusable element inside the sidebar so keyboard users land in it. */
                const firstFocusable = sidebar.querySelector(
                    'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
                );
                if (firstFocusable) firstFocusable.focus();
            }
            function closeSidebar() {
                sidebar.classList.remove('open');
                backdrop.classList.remove('open');
                toggle.querySelector('i').className = 'fas fa-bars';
                setExpanded(false);
                applyInert();
                /* Return focus to the hamburger so keyboard users don't lose their place. */
                toggle.focus();
            }

            toggle.addEventListener('click', (e) => {
                e.stopPropagation();
                if (sidebar.classList.contains('open')) closeSidebar();
                else openSidebar();
            });
            backdrop.addEventListener('click', closeSidebar);

            // Close when a nav link is tapped (keeps drawer UX snappy)
            sidebar.querySelectorAll('a.sidebar-nav-item').forEach(link => {
                link.addEventListener('click', () => {
                    if (mql.matches) closeSidebar();
                });
            });

            // Auto-close when resizing back to desktop; also re-apply inert
            window.addEventListener('resize', () => {
                if (window.innerWidth > 768) closeSidebar();
                applyInert();
            });
            mql.addEventListener('change', applyInert);

            // ESC closes the drawer when open (mobile only — desktop sidebar is always visible)
            document.addEventListener('keydown', function (e) {
                if (e.key === 'Escape' && sidebar.classList.contains('open')) {
                    closeSidebar();
                    e.preventDefault();
                }
            });

            // Focus trap inside the open drawer
            sidebar.addEventListener('keydown', function (e) {
                if (e.key !== 'Tab' || !sidebar.classList.contains('open')) return;
                const focusables = sidebar.querySelectorAll(
                    'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
                );
                if (!focusables.length) return;
                const first = focusables[0];
                const last  = focusables[focusables.length - 1];
                if (e.shiftKey && document.activeElement === first) {
                    last.focus();
                    e.preventDefault();
                } else if (!e.shiftKey && document.activeElement === last) {
                    first.focus();
                    e.preventDefault();
                }
            });

            // Initial state on page load
            setExpanded(false);
            applyInert();
        });
```

- [ ] **Step 3: Smoke-test that the page still loads and JS runs without errors**

```bash
curl -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8000/
```

Expected: 200/302.

To check for JS console errors, the user will load `/dashboard` in a browser and check devtools console. The implementer can't do this directly. If you have access to a Playwright session, navigate and capture console errors:

```bash
# Optional, if Playwright session is available
npx playwright test --headed --project=chromium-mobile tests/a11y/design-system.spec.js 2>&1 | head -20
```

Otherwise, leave a note in your report that browser-side verification is pending.

- [ ] **Step 4: Commit (user)**

Files to stage: `templates/js/_headerJS.html`.

Suggested message: `mobile p1: sidebar drawer focus mgmt, ESC, focus trap, inert`

---

## Task 8: Add "Header / nav" demo to `/design-system`

**Files:**
- Modify: `templates/design_system.html`

- [ ] **Step 1: Insert a new section after the Toast section**

Open `templates/design_system.html`. Find the Toast section (the last `<section>` in the file):

```html
  <!-- Toast region -->
  <section class="nx-section" aria-labelledby="ds-toast">
```

Just BEFORE the closing `</div>` of `<div class="nx-page" id="design-system">`, insert this new section:

```html
  <!-- Header / nav (mobile chrome) -->
  <section class="nx-section" aria-labelledby="ds-header">
    <h2 class="nx-section__title" id="ds-header">Header / nav (mobile chrome)</h2>
    <div class="nx-card">
      <div class="nx-card-body">
        <p>The global sidebar in <code>templates/_header.html</code> uses a slide-out drawer pattern below 768 px (hamburger top-left). Live demo isn't possible in this preview because the drawer is wired to live nav data; the rules and behaviors documented in <code>docs/superpowers/specs/2026-05-07-mobile-foundation-phase1-header-design.md</code> apply.</p>
        <p style="margin-top: 0.75rem">Inline link example using <code>nx-link-muted</code>:</p>
        <p style="margin-top: 0.5rem">
          Read more in the
          <a href="https://sydoc.ch/" class="nx-link-muted">company website</a>
          or contact
          <a href="mailto:support.helpdesk@sydoc.ch" class="nx-link-muted">support</a>.
        </p>
      </div>
    </div>
  </section>
```

The `<div class="nx-page" id="design-system">` should still close cleanly after this section. Verify the structure:

Run:
```bash
grep -nE "ds-header|ds-toast|</div>\s*$|</section>" templates/design_system.html | tail -20
```

You should see the new `ds-header` section between `ds-toast` and the page-closing `</div>`.

- [ ] **Step 2: Verify the page renders**

Make sure nexora is running. With a logged-in admin session, visit `/design-system` (in a browser or via Playwright) and check the new section appears at the bottom. Or:

```bash
curl -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8000/design-system
```

Expected: 302 (redirects to login if no session) or 200 (if session active).

- [ ] **Step 3: Verify the existing a11y test still passes**

```bash
npm run test:a11y -- --project=chromium-desktop
```

Expected: PASS (`tests/a11y/design-system.spec.js` runs and asserts no violations on the page including the new section).

If FAIL: read the violations array. Most likely cause for a regression here: a missing `aria-labelledby` link or invalid attribute. Fix and re-run.

- [ ] **Step 4: Commit (user)**

Files to stage: `templates/design_system.html`.

Suggested message: `mobile p1: design-system — add header/nav section + nx-link-muted example`

---

## Task 9: Write the `header.spec.js` a11y test

**Files:**
- Create: `tests/a11y/header.spec.js`

> **TDD note:** This test must be written and confirmed FAILING before Task 7's JS extensions. If you've already done Task 7, the test should PASS. If you haven't, it should FAIL on the `aria-expanded` assertion.

- [ ] **Step 1: Create the test file**

Use the Write tool. Path: `tests/a11y/header.spec.js`. Content:

```javascript
// @ts-check
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

/**
 * Asserts that the global header (sidebar drawer) on a real authenticated
 * page has no WCAG 2.1 AA violations when open at mobile width, and that
 * the keyboard-driven open/close interactions work.
 *
 * Pre-requisites:
 *   - nexora running on http://127.0.0.1:8000
 *   - NX_A11Y_USER set or default `ben.streich` exists in INT
 */
const TEST_USER = process.env.NX_A11Y_USER || 'ben.streich';

test.describe('Header drawer a11y (mobile)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/dev/login/${TEST_USER}`);
    await expect(page).not.toHaveURL(/\/dev\/login/);
  });

  test('open drawer has no AA violations and ESC closes it', async ({ page }) => {
    /* Mobile-sized viewport. Pixel 5 device profile is used by the
       `chromium-mobile` project; this test runs at that size automatically.
       For chromium-desktop runs, force a small viewport so the drawer is
       relevant. */
    await page.setViewportSize({ width: 375, height: 812 });

    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/dashboard/);

    /* Open the drawer */
    const toggle = page.locator('#sidebar-toggle');
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await toggle.click();

    /* Drawer is now open; toggle reports expanded */
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const sidebar = page.locator('#nexora-sidebar');
    await expect(sidebar).toHaveClass(/open/);

    /* axe scan with drawer open */
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2))
      .toEqual([]);

    /* ESC closes the drawer, focus returns to toggle */
    await page.keyboard.press('Escape');
    await expect(sidebar).not.toHaveClass(/open/);
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await expect(toggle).toBeFocused();
  });
});
```

- [ ] **Step 2: Make sure nexora is running**

```bash
curl -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8000/
```

If not running, `nx -u` and wait ~5 seconds.

- [ ] **Step 3: Run the test on chromium-desktop**

```bash
npm run test:a11y -- --project=chromium-desktop tests/a11y/header.spec.js
```

If Tasks 6 + 7 are done, expected: PASS.

If Task 6 (ARIA attrs) is NOT yet done, the `aria-expanded` assertion fails (attribute doesn't exist). Run Tasks 6 and 7 first, then re-run.

If you see violations: read the JSON in the assertion error. Common ones on `_header.html`:
- `region`: every page area should be inside a landmark. The new `role="navigation"` from Task 6 helps. The `<main>` element is on the dashboard page itself — not our concern here.
- `color-contrast`: tokens should already meet AA per Phase 0; if anything fails, it's likely the warning/critical hex values in the maintenance banner (which only shows when active — won't trigger unless a banner is live).
- `landmark-unique`: if there are multiple `role="navigation"` without distinguishing labels, the `aria-label="Main navigation"` from Task 6 satisfies this.

Fix accordingly. Iterate up to 2-3 times. If still failing, report DONE_WITH_CONCERNS with the remaining violations.

- [ ] **Step 4: Run the test on chromium-mobile**

```bash
npm run test:a11y -- --project=chromium-mobile tests/a11y/header.spec.js
```

Expected: PASS (the test sets viewport to 375 explicitly, so it works on either project).

- [ ] **Step 5: Run the FULL test suite to confirm nothing regressed**

```bash
npm run test:a11y
```

Expected: both `design-system.spec.js` and `header.spec.js` pass on both projects (4 test runs total).

- [ ] **Step 6: Commit (user)**

Files to stage: `tests/a11y/header.spec.js`.

Suggested message: `mobile p1: a11y test for open drawer + ESC behavior`

---

## Done

After Task 9, Phase 1 is complete. The repo now has:

- `_header.css` migrated to Phase 0 tokens (light-mode only, lossless mappings).
- Sidebar sub-items hit a comfortable 48 px tap target on mobile.
- Maintenance banner uses tokens for the indigo info palette and has a 44 × 44 dismiss button.
- Footer + version reuse the new `nx-link-muted` component class with mobile tap-target padding.
- Header has `aria-controls` / `aria-expanded` / `role="navigation"` / `aria-label` / `aria-hidden` on the right elements.
- Sidebar drawer manages focus correctly on open and close, traps Tab while open, applies `inert` when closed on mobile, and ESC closes it.
- A new axe-core test asserts no AA violations in the open drawer on `/dashboard` and verifies ESC behavior.
- The existing `/design-system` axe test still passes; the page now demonstrates `nx-link-muted`.

**Next phase:** Phase 2 — auth flow migration (`forgot_password`, `init_reset`, `reset_password`, `init_2FA`, `verify_2fa`, `hero`, `index`, `maintenance`, handlers). Open a new brainstorm when ready.
