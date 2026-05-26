# Mobile UI Foundation — Design Spec

**Status:** draft, pending user review
**Date:** 2026-05-07
**Owner:** benstreich
**Sub-project of:** "Better mobile UI across all pages" (multi-spec initiative)

## 1. Goal

Make every nexora page work well on phones (≥ 375 px) while staying coherent on tablets and desktops, by introducing a small, mobile-first design system and migrating every page to it.

This is sub-project #1 of a larger initiative. It produces:
1. A token system + breakpoint conventions.
2. A pattern library of reusable mobile-aware components (`nx-*` classes).
3. A migration to apply both to every existing page in the app, in one rollout.

Subsequent sub-projects (data-list polish, dashboard polish, admin polish, etc.) will build on this foundation in their own specs.

## 2. Non-goals

- Backend / Flask / route changes (apart from one new `/design-system` preview route).
- New permissions, tables, SQL migrations (apart from the optional `design.view` perm).
- New Python dependencies.
- Replacing Plotly, FontAwesome, Inter, or other third-party libraries.
- Dark mode (tokens are structured to allow it later; not implemented now).
- i18n / Babel changes. Existing `{{ _('…') }}` strings are reused as-is.
- Bottom-tab navigation.
- Introducing a JavaScript framework (Vue, React, etc.).
- Service worker / offline / PWA installability.
- Visual-regression service (Chromatic, Percy). Per-PR screenshots are sufficient.

## 3. Approach (recap)

**Approach A — Pragmatic Refresh.** Compiled Tailwind v4 (build on dev only, committed CSS for IIS deploy), token-first design, page-by-page rollout in `main`. Old per-page CSS is deleted as each page migrates. Mid-state co-existence is accepted.

Rationale: smallest deploy-process change while still getting real Tailwind features (`@theme`, `@apply`, `@layer`); incremental risk; learns from real users early.

## 4. Architecture

### 4.1 New files
- `package.json` — declares `tailwindcss@^4` and `@tailwindcss/cli@^4` as devDeps. Single script: `"build:css": "tailwindcss -i src/main.css -o static/css/tailwind.css --minify"`.
- `src/main.css` — single source of truth for tokens + components. Contains:
  - `@import "tailwindcss";`
  - A `@theme` block defining all tokens.
  - A `@layer components` block defining all `.nx-*` classes via `@apply`.
- `static/css/tailwind.css` — compiled output, **committed** so deploy stays "copy files." No Node.js on the IIS server.

### 4.2 Modified files
- `templates/_header.html` — remove `<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4">`; add `<link rel="stylesheet" href="{{ url_for('static', filename='css/tailwind.css') }}">`. Tailwind Plus Elements `<script>` stays.
- `.gitignore` — add `node_modules/`, `src/.cache/` if needed. `src/` itself is tracked.
- `app.py` — add a `/design-system` route gated by `@require_permission('admin.view')` rendering `templates/design_system.html`. ~10 lines.

### 4.3 New template
- `templates/design_system.html` — internal preview page rendering every `nx-*` component in every state. Used for development and as a stable Playwright/axe-core target.

### 4.4 Deprecated over time
- All per-page CSS files in `static/css/` (`dashboard.css`, `profile.css`, `workitems_overview.css`, `_header.css`, `forgot_password.css`, `reset_password.css`, `index.css`, `hero.css`, `jdvance.css`). As each page migrates, its bespoke rules either become Tailwind utilities, become an `nx-*` class, or remain (only for things genuinely page-specific, e.g., a Plotly tweak).
- `static/css/admin-tokens.css` — fully superseded by the global token set; deleted at the end of the admin-pages phase.

### 4.5 Build & deploy
- **Dev:** `npm install` once, `npm run build:css` (or `--watch`) when authoring CSS.
- **CI gate:** the existing `deploy.yml` workflow rebuilds CSS and aborts the deploy if `static/css/tailwind.css` is out of sync with `src/main.css` — keeps committed CSS in sync. (Earlier draft used a separate `build-and-test.yml`; consolidated into `deploy.yml` because the project uses direct push to `main` rather than PR review, so a separate CI workflow would only fire post-merge.)
- **Deploy:** unchanged. CSS file is committed; IIS just serves it.

### 4.6 Token flow
- The `@theme` block emits CSS custom properties at `:root` (e.g., `--color-primary-600`, `--space-4`, `--text-base`).
- Tailwind utilities resolve to those variables automatically (`bg-primary-600` → `background: var(--color-primary-600)`).
- Hand-written CSS (Plotly tweaks, anything outside Tailwind) references the same variables. **One source of truth for all colors and sizes.**

## 5. Token system

### 5.1 Colors
Naming follows `--color-{role}-{shade}` for brand and `--color-{role}` for semantics.

| Token | Hex | Notes |
|---|---|---|
| `--color-bg-page` | `#f9fafb` | Default page background |
| `--color-bg-surface` | `#ffffff` | Cards, modals |
| `--color-bg-muted` | `#f9fafb` | Table header, row hover |
| `--color-bg-emphasis` | `#f3f4f6` | Mono code background, dividers |
| `--color-border` | `#e5e7eb` | Default borders |
| `--color-border-strong` | `#d1d5db` | Input borders |
| `--color-text-primary` | `#1f2937` | Default body text |
| `--color-text-secondary` | `#596069` | Subtitles, descriptions (darkened from `#6b7280` to meet WCAG AA at 11 px) |
| `--color-text-meta` | `#767676` | Meta labels, timestamps (darkened from `#9ca3af` to meet WCAG AA at 11 px) |
| `--color-text-on-primary` | `#ffffff` | Text on primary buttons |
| `--color-primary-50` | `#eef2ff` | |
| `--color-primary-100` | `#e0e7ff` | |
| `--color-primary-500` | `#6366f1` | |
| `--color-primary-600` | `#4f46e5` | Default primary |
| `--color-primary-700` | `#4338ca` | Primary hover |
| `--color-success` | `#059669` | |
| `--color-success-bg` | `#d1fae5` | |
| `--color-warning` | `#d97706` | |
| `--color-warning-bg` | `#fef3c7` | |
| `--color-danger` | `#dc2626` | |
| `--color-danger-bg` | `#fee2e2` | |
| `--color-focus-ring` | `rgba(79,70,229,0.12)` | 3 px shadow on focus |

### 5.2 Typography
- **Family:** Inter (body), `SF Mono` / Consolas (mono).
- **Scale (mobile-first):**
  - `--text-xs` 11 px
  - `--text-sm` 13 px
  - `--text-base` 14 px (default body on desktop / dense views)
  - `--text-md` 16 px (default body on mobile)
  - `--text-lg` 18 px
  - `--text-xl` 22 px
  - `--text-2xl` 28 px (page heroes)
- **Weights:** 400, 500, 600, 700.
- **Letter-spacing:** −0.4 px on h1/h2, +0.6 px uppercase on meta labels.

### 5.3 Spacing
Tailwind 4 px scale: `0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24` (corresponds to 0–96 px).
Mobile-aware:
- `--space-page-x-mobile` 16 px
- `--space-page-x-desktop` 40 px

### 5.4 Radii & shadows
- `--radius-sm` 4 px, `--radius-md` 7 px (existing button radius), `--radius-lg` 12 px, `--radius-pill` 9999 px.
- `--shadow-sm` (cards), `--shadow-md` (menus, popovers), `--shadow-lg` (drawers, sheets).

### 5.5 Mobile-aware additions
- `--tap-target-min: 44px` — enforced on every tappable element.
- Breakpoint variables (Tailwind defaults documented as tokens): `sm 640`, `md 768`, `lg 1024`, `xl 1280`. Mobile baseline = no prefix.
- Z-index: header 50, drawer/sheet 100, modal 200, toast 300.

## 6. Pattern library

All patterns live in `src/main.css` `@layer components`. Each is authored as Tailwind compositions via `@apply`.

### 6.1 Layout & chrome
- `nx-page` — outer wrapper, applies mobile/desktop padding tokens.
- `nx-page-header` — title + actions; stacks on mobile, side-by-side from `sm`.
- `nx-section` — vertical-rhythm container.
- `nx-card`, `nx-card-header`, `nx-card-body`, `nx-card-footer`.

### 6.2 Forms & inputs
- `nx-form-field` — wraps label + input + help/error in a single column. Full-width on mobile.
- `nx-input`, `nx-select`, `nx-textarea`, `nx-checkbox`, `nx-radio` — 44 px tap targets, focus ring, error variant.
- `nx-action-bar` — sticky bottom bar (Save / Cancel) on mobile; inline on `md+`.

### 6.3 Data display
- `nx-table-stack` — default for most tables. Real `<table>` on `md+`; reflows to stacked cards below `md` via CSS only. Cells need `data-label="…"` attribute so the column label shows on mobile.
- `nx-table-scroll` — variant for "summary" tables that must keep tabular shape; horizontal scroll with sticky first column on mobile.
- `nx-empty-state` — icon + title + description + optional CTA.
- `nx-skeleton-row` — shimmer placeholder while loading lists.

### 6.4 Feedback & overlays
- `nx-modal` — uses Tailwind Plus Elements `<el-dialog>`. Bottom-sheet (`<md`) slides up from bottom, ~90 vh tall; centered modal on `md+`. Focus trap + restore handled by the element library.
- `nx-toast` — top-right desktop, top-center mobile. Z-300.
- `nx-badge` — status chip; color variants from semantic tokens (`indigo`, `green`, `amber`, `red`, `gray`).

### 6.5 Buttons & affordances
- `nx-btn` with variants `primary` / `secondary` / `danger` / `ghost` and sizes `sm` / `md` / `lg`. Min 44 px tap target.
- `nx-btn-icon` — icon-only; requires `aria-label`.

### 6.6 Charts
- `nx-chart-shell` — card wrapper with header (title + actions) + body sized to 100 % width. A small JS helper attaches a `ResizeObserver` and calls `Plotly.Plots.resize(el)` on changes.
- "Summary numbers" pattern — KPI tiles always render above the chart so phone users see the headline numbers without rendering the chart at all.

### 6.7 Header / nav (light touch)
- Existing sidebar in `_header.html` keeps its desktop behavior.
- Below `md`, sidebar collapses to a hamburger that opens a drawer (Tailwind Plus Elements `<el-drawer>`). Existing nav links reused.

### 6.8 Out of scope for the foundation
- Bottom-tab navigation.
- Swipe gestures on rows.
- Dark mode.
- Animation library (use Tailwind transitions).

## 7. Per-page migration

### 7.1 Per-page checklist
1. Open the template. Identify regions: page header, sections, cards, tables, forms, modals, charts.
2. Wrap the page in `class="nx-page"`.
3. Replace inline-styled headers/sections/cards with `nx-page-header`, `nx-section`, `nx-card`.
4. **Tables:** add `class="nx-table-stack"` to `<table>` and `data-label="…"` to every `<td>`.
5. **Forms:** wrap each input in `nx-form-field`; replace inline buttons with `nx-btn`. Use `nx-action-bar` for primary actions on long forms.
6. **Modals:** convert to `nx-modal` (`<el-dialog>`).
7. **Charts:** wrap Plotly containers in `nx-chart-shell`; add a "summary numbers" tile row above the chart.
8. Delete the page's bespoke CSS file in `static/css/` (or shrink it to genuinely page-specific rules).
9. Smoke-test at 375 / 640 / 768 / 1024 / 1280. Run any Playwright coverage that exists (`nx -u -b --loginas:<user>`).
10. Open one PR titled `mobile: <page name> migration`. Include before/after screenshots at mobile + desktop, saved under `screenshots/`.

### 7.2 Co-existence rules
- `tailwind.css` is global from phase 0; loaded on every page via `_header.html`.
- Old per-page CSS files keep linking from templates that haven't migrated yet. Both load together.
- `static/css/admin-tokens.css` keeps loading on admin pages until phase 7 migrates them. The new `--color-*` tokens use distinct names from the legacy `--a-*` tokens, so both can coexist without collision.
- Tailwind utilities win specificity contests in nearly all cases. Phase 0 verifies this on a representative page; conflicts get a one-line override in `src/main.css`.

## 8. Rollout sequence

| Phase | Pages | Why this order |
|---|---|---|
| 0 — Foundation | `package.json`, `src/main.css`, `static/css/tailwind.css`, `templates/design_system.html`, `_header.html` script swap, axe-core test | Everything depends on this |
| 1 — Header / nav | `_header.html`, `_maintenance_banner.html`, `_small_footer.html`, `_nexoraVersion.html` | Global impact — every page benefits immediately |
| 2 — Auth flow | `forgot_password`, `init_reset`, `reset_password`, `init_2FA`, `verify_2fa`, `hero`, `index`, `maintenance`, handlers (403/404/500) | Small, low-risk, validates the system |
| 3 — Profile | `profile.html` + `_profileJS.html` | Validates form & card patterns |
| 4 — Workitems & invoices | `workitems_overview`, `invoices` + JS partials | Primary internal pain point (tables) |
| 5 — Dashboard | `dashboard.html` + `_dashboardJS.html` | Validates chart pattern |
| 6 — Generali tenant | `generali-dashboard`, `generali_baseservices`, `generali_additionalservices`, `generali_documents`, `generali_importstatus`, `generali_monthreport`, `generali_pdqm`, `generali_projectmanagement`, `generali_reporting` + JS partials | Apply patterns once proven |
| 7 — Admin | `adminOverview`, `accessControl`, `logs`, `sessions`, `userDetail`, `organizations`, `maintenance` + admin modals | Most complex; benefits from battle-tested patterns |
| 8 — Chat | `chat.html` + `_chatJS.html` | Standalone; anytime |

**Estimate:** phase 0 ≈ 3 days; phases 1–8 ≈ 1 day per page on average × ~30 pages ≈ 4–6 weeks elapsed depending on parallel work.

## 9. Testing & verification

### 9.1 Per PR (mandatory)
- Manual smoke at 375 / 640 / 768 / 1024 / 1280 in browser devtools.
- Before/after screenshots at mobile (375) and desktop (1280) attached to the PR description; files saved to `screenshots/`.
- Run any existing Playwright tests for the page.
- Run `npm run build:css` and verify the committed CSS is in sync.

### 9.2 Per phase (mandatory)
- Full existing Playwright suite green at each phase boundary.
- One real-device pass on a phone (one iOS or Android sample) at phase boundaries.
- Lighthouse mobile check on the page that anchors each phase (e.g., `workitems_overview` for phase 4, `dashboard` for phase 5, `adminOverview` for phase 7). Targets: Performance ≥ 75, Accessibility ≥ 90.

### 9.3 Phase 0 test surfaces
- New `/design-system` route gated by `@require_permission('admin.view')`. Renders every `nx-*` component in every state.
- One axe-core via Playwright smoke test against `/design-system` asserting WCAG AA contrast and labels (`tests/a11y/design-system.spec.js`). Covers `chromium-desktop` + `chromium-mobile` (Pixel 5) projects.
- **Run locally** before pushing changes that touch the design system: `npm run test:a11y`. Not run in CI — direct-push-to-main workflow makes a CI gate post-hoc.

### 9.4 Accessibility floor (every component)
- WCAG AA contrast.
- Visible focus ring on every focusable element.
- Keyboard nav: tab order, Enter/Space activate, Esc closes overlays.
- Icon-only buttons require `aria-label`.
- Bottom-sheet modals trap focus and restore on close.

### 9.5 Browser matrix
- Last 2 versions of Chrome, Edge, Safari, Firefox.
- Mobile Safari (iOS 16+), Chrome Android (latest).
- No IE, no legacy Edge.

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Old per-page CSS conflicts with Tailwind utilities | Phase 0 verifies on a representative page; one-line overrides in `src/main.css` if needed |
| Tailwind v4 is recent | Stick to well-documented features (`@theme`, `@apply`, `@layer`); avoid bleeding-edge |
| Plotly resize in flex/grid containers | `nx-chart-shell` calls `Plotly.Plots.resize` via `ResizeObserver` |
| Tailwind Plus Elements + custom CSS | Already used in `_header.html`; behavior is known |
| Dev setup adds Node.js | One-paragraph README + `npm install && npm run build:css`. No Node.js on deploy |
| Mid-state visual inconsistency for 4–6 weeks | Accepted; sequence faster if it becomes painful |
| Committed CSS file size | Compiled Tailwind ≈ 50–150 KB minified, ~15–25 KB gzipped. Negligible |

## 11. Open questions (defer)

- **CSS rebuild enforcement:** lightweight GH Action (`npm run build:css` + `git diff --exit-code`) is the spec's default. User can swap to a pre-commit hook or trust-based instead.
- **`/design-system` permission:** spec defaults to gating behind `admin.view`. A new `design.view` perm would need an SQL migration; decided not worth it.

## 12. References

- Existing token system: `static/css/admin-tokens.css` (admin-only Phase 1).
- CLAUDE.md project conventions (especially: Babel workflow, SQL handling, git rule, screenshots folder).
- Existing related specs:
  - `2026-04-23-admin-redesign-phase1-design.md`
  - `2026-04-23-admin-redesign-phase2-design.md`
