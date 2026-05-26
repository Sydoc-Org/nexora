# Mobile UI Foundation — Phase 1: Header / Global Nav — Design Spec

**Status:** draft, pending user review
**Date:** 2026-05-07
**Owner:** benstreich
**Sub-project of:** Mobile UI Foundation initiative (parent spec: `2026-05-07-mobile-foundation-design.md`)
**Phase 0 reference:** `2026-05-07-mobile-foundation-phase0.md` (plan)

## 1. Goal

Polish the existing mobile sidebar / global chrome (`_header.html`, `_maintenance_banner.html`, `_small_footer.html`, `_nexoraVersion.html`) so it (a) uses the Phase 0 token system instead of hardcoded hex/px values, (b) meets WCAG AA keyboard / focus / ARIA requirements, and (c) has a consistent ≥ 44 px tap target on every interactive element on mobile.

This is **polish, not redesign**. The existing CSS-driven slide-out sidebar (visible on `≤ 768 px`) works; we keep the structure and animation intact.

## 2. Non-goals

- Replacing `_header.css` with `nx-*` utility classes (rejected as Approach B during brainstorm — too much churn).
- Migrating dark-mode color values to tokens (dark mode is out of scope per the foundation spec).
- Migrating bespoke values without an exact token match (`#374151`, `#f5f3ff`, `#fafafa`, `#22c55e`, `#ef4444`).
- Replacing the bespoke slide-out with `<el-drawer>` from Tailwind Plus Elements.
- Adding a skip-link to main content (future task).
- Touching the command palette (`#cmdkOverlay`) — out of scope for header chrome.
- Changing notification panel positioning, dark-mode toggle behavior, or profile dropdown — all keep their current UX.

## 3. Approach

**Approach A — In-place polish.** Keep `_header.css` intact. Migrate only lossless color matches to Phase 0 tokens. Add a11y attributes and JS handlers to the existing `_headerJS.html` open/close pair. Bump tap-target sizes where they fall below 44 px on mobile.

Rationale: the user confirmed the existing mobile sidebar works. YAGNI. ~600 lines of working CSS shouldn't be rewritten just to swap files.

## 4. Files & changes

| File | Change |
|---|---|
| `static/css/_header.css` | Replace lossless light-mode color values with `var(--color-*)` tokens (mapping in §5). Bump `.sidebar-nav-subitem` `padding-block` from 10 → 12 px. Keep dark-mode rules (`html.dark …`) untouched. |
| `templates/_header.html` | Add `aria-controls="nexora-sidebar"` and `aria-expanded="false"` to `#sidebar-toggle`. Add `role="navigation"` and `aria-label="{{ _('Main navigation') }}"` to `<aside id="nexora-sidebar">`. Add `aria-hidden="true"` to `#sidebar-backdrop`. |
| `templates/js/_headerJS.html` | Extend the existing `openSidebar` / `closeSidebar` pair (lines 442–478) with `aria-expanded` toggling, `inert` application, focus management, ESC handler, and Tab focus trap. |
| `templates/_maintenance_banner.html` | Map inline `<style>` colors to tokens (lossless only). Convert `.mb-dismiss` to a 44 × 44 icon button. Localize `aria-label="Dismiss"` → `{{ _('Dismiss') }}`. |
| `templates/_small_footer.html` | Replace `text-gray-600 hover:text-blue-500` link styling with a new `nx-link-muted` component class. Wrap link list in a flex container with `min-h-[44px]` per link on mobile. |
| `templates/_nexoraVersion.html` | Replace `text-gray-500` with token-based equivalent (or `nx-text-meta` if we add one — see below). |
| `src/main.css` | Add **one** small new `@layer components` rule: `.nx-link-muted` (text → `--color-text-secondary`, hover → `--color-primary-600`, focus ring). |
| `static/css/tailwind.css` | Rebuilt via `npm run build:css`. |
| `templates/design_system.html` | Add a "Header / nav (mobile chrome)" section with one example of `.nx-link-muted` and a docs reference pointing readers to `_header.html`. The drawer itself is too coupled to live data to mock cleanly — the reference is enough. |
| `tests/a11y/header.spec.js` | New axe-core test: log in, navigate to `/dashboard`, resize to mobile viewport, open the drawer, scan for AA violations, press Escape, assert `aria-expanded="false"`. |

## 5. Token migration map

`_header.css` and inline banner styles use ~40 unique color values. Only lossless matches are migrated.

**Will migrate (light-mode):**

| Hex | Token | Usage |
|---|---|---|
| `#f9fafb` | `var(--color-bg-page)` | Page bg |
| `#ffffff` / `#fff` | `var(--color-bg-surface)` | Cards, sidebar surface, hamburger bg |
| `#f3f4f6` | `var(--color-bg-emphasis)` | Hover bg, dividers |
| `#e5e7eb` | `var(--color-border)` | Borders |
| `#1f2937` | `var(--color-text-primary)` | Body text |
| `#6b7280` | `var(--color-text-secondary)` | Secondary text (resolves to `#596069` per Phase 0 a11y fix) |
| `#9ca3af` | `var(--color-text-meta)` | Meta text (resolves to `#767676` per Phase 0 a11y fix) |
| `#4f46e5` | `var(--color-primary-600)` | Primary brand |
| `#eef2ff` | `var(--color-primary-50)` | Primary tint backgrounds (active item bg) |
| `#e0e7ff` | `var(--color-primary-100)` | Primary tint backgrounds |

**Will NOT migrate (kept as-is):**
- All slate values (`#0f172a`, `#1e293b`, `#273449`, `#334155`, `#475569`, `#64748b`, `#94a3b8`, `#a5b4fc`, `#cbd5e1`, `#e2e8f0`, `#f1f5f9`, `#c7d2fe`, `#818cf8`, `#312e81`, `#111827`) — used only inside `html.dark …` rules; dark-mode tokens are out of scope.
- Bespoke values without exact token (`#374151`, `#3730a3` (indigo-800, no token — `--color-primary-700` is indigo-700 / `#4338ca`), `#f5f3ff`, `#fafafa`, `#22c55e`, `#ef4444`).
- Banner warning palette (`#fffbeb` / `#92400e` / `#fde68a`) and critical palette (`#fef2f2` / `#991b1b` / `#fecaca`) — close to but not identical to `--color-warning-bg` / `--color-danger-bg`. Visual fidelity wins.
- All `rgba(...)` shadow / focus-ring values — kept inline; sidebar uses bespoke shadows different from `--shadow-*`.

## 6. A11y additions

### 6.1 Markup
- `#sidebar-toggle`: add `aria-controls="nexora-sidebar"` and `aria-expanded="false"` (toggled by JS). Existing `aria-label="{{ _('Open navigation') }}"` is kept.
- `#nexora-sidebar`: add `role="navigation"` (overrides the implicit `complementary` role of `<aside>`) and `aria-label="{{ _('Main navigation') }}"`.
- `#sidebar-backdrop`: add `aria-hidden="true"`.
- `.mb-dismiss` (banner close): localize `aria-label="Dismiss"` → `{{ _('Dismiss') }}`.

### 6.2 JS extensions to `_headerJS.html`

Append these to the existing handler at lines 442–478. Do not rewrite — keep current `openSidebar` / `closeSidebar`, the icon-flip behavior, the link-tap close, and the resize close.

```javascript
function setExpanded(expanded) {
  toggle.setAttribute('aria-expanded', String(expanded));
}
function applyInert() {
  if (window.matchMedia('(max-width: 768px)').matches && !sidebar.classList.contains('open')) {
    sidebar.setAttribute('inert', '');
  } else {
    sidebar.removeAttribute('inert');
  }
}

// Inside existing openSidebar() — append AFTER the icon flip:
//   setExpanded(true); applyInert();
//   const firstFocusable = sidebar.querySelector('a, button, [tabindex]:not([tabindex="-1"])');
//   if (firstFocusable) firstFocusable.focus();
//
// Inside existing closeSidebar() — append AFTER the icon flip:
//   setExpanded(false); applyInert();
//   toggle.focus();

// ESC closes
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape' && sidebar.classList.contains('open')) {
    closeSidebar();
    e.preventDefault();
  }
});

// Focus trap when open
sidebar.addEventListener('keydown', function(e) {
  if (e.key !== 'Tab' || !sidebar.classList.contains('open')) return;
  const focusables = sidebar.querySelectorAll(
    'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
  );
  if (!focusables.length) return;
  const first = focusables[0];
  const last  = focusables[focusables.length - 1];
  if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
  else if (!e.shiftKey && document.activeElement === last)  { first.focus(); e.preventDefault(); }
});

// Initial state on load
setExpanded(false);
applyInert();
window.matchMedia('(max-width: 768px)').addEventListener('change', applyInert);
```

### 6.3 Why `inert` over `aria-hidden`
`inert` blocks both focus AND assistive-tech announcements in a single attribute. Supported in every modern browser since 2023 (Chrome ≥ 102, Firefox ≥ 112, Safari ≥ 15.5). Cleaner than the two-attribute combination.

## 7. Tap-target audit

The Phase 0 token `--tap-target-min` = 44 px (`2.75rem`).

| Element | Current size | Action |
|---|---|---|
| `.sidebar-toggle-btn` | 44 × 44 | ✅ no change |
| `.sidebar-nav-item` | ~ 52 px | ✅ no change |
| `.sidebar-nav-subitem` | ~ 44 px (exactly at threshold) | Bump `padding-block` from 10 → 12 px |
| `.sidebar-bottom > button` | inherits `.sidebar-nav-item` | ✅ no change |
| `.mb-dismiss` | ~ 28 px (`padding: 4px 8px`) | Change to `width: 44px; height: 44px; padding: 0;` (icon-only square) |
| Footer link `<a>` | ~ 16 px line-height, no padding | Wrap in flex container with `min-height: 44px` per link on mobile, or apply `py-2` with adjacent `min-h-[44px]` rules |
| `_nexoraVersion.html` `<p>` | display-only, not interactive | ✅ no change |

## 8. Testing

### 8.1 Manual smoke (mandatory)
At 375 / 414 / 768 px on a real or emulated device, on a page that uses `_header.html` (e.g., `/dashboard`):
- Hamburger toggles drawer open/close.
- Tap-on-link inside drawer navigates AND closes drawer.
- Tap-on-backdrop closes drawer.
- ESC closes drawer; focus returns to hamburger.
- Tab cycles within the drawer when open; does not leak to elements behind the backdrop.
- Resize from mobile to desktop while drawer is open → drawer auto-closes (existing resize handler).
- Maintenance banner: trigger one from `/maintenance` admin page; verify it renders correctly on mobile, dismiss button is 44 × 44, dismissal persists in `sessionStorage`.
- Footer links are tappable with a thumb; no overlap.

### 8.2 Automated — new axe test
`tests/a11y/header.spec.js`:
- Logs in via `/dev/login/${NX_A11Y_USER}`.
- Navigates to `/dashboard`.
- Sets viewport to mobile width.
- Clicks `#sidebar-toggle` to open the drawer.
- Runs `AxeBuilder({ page }).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()` — asserts violations array is empty.
- Presses Escape.
- Asserts the drawer closed (`aria-expanded` is `"false"`).

### 8.3 Existing tests
The `tests/a11y/design-system.spec.js` test continues to run as-is. Phase 1 doesn't touch `/design-system` markup beyond the optional small `nx-link-muted` example.

## 9. Risks & open questions

| Risk | Mitigation |
|---|---|
| `inert` not supported on user's actual phone | Browsers in scope (last 2 versions of Chrome/Edge/Safari/Firefox) all support it. If Internet Explorer / pre-2023 mobile Safari are needed, fall back to `aria-hidden` + setting `tabindex="-1"` on every focusable. |
| Focus trap traps the user too aggressively | The Tab handler only fires when sidebar has `.open` class. On desktop the sidebar never gets `.open`, so trap is inactive. Verified by `if (!sidebar.classList.contains('open')) return;`. |
| Maintenance banner color tokens are close-but-not-exact | We chose visual fidelity over consistency: warning/critical palettes stay on their original hex values. Documented above so a future dark-mode pass knows where to revisit. |
| Footer link tap-area changes affect desktop spacing | Use `@media (max-width: 768px)` to scope the `min-height: 44px` rule to mobile only, so desktop spacing stays as-is. |

**Open questions (defer):**
- Should we add a skip-link from the hamburger to "main content"? Not in this phase.
- Should the dark-mode token system be defined now, even if not consumed? Defer to a future "dark-mode token rollout" sub-spec.

## 10. Out of scope (this spec)

- All other migration phases (data lists, dashboard, generali, admin, chat, profile).
- Backend / Flask / route logic changes.
- New permissions, tables, SQL.
- New Python dependencies.
- Replacing Plotly / FontAwesome / Inter.
- Bottom-tab navigation, swipe gestures, dark-mode tokens.
- Service worker / offline / PWA.

## 11. References

- Parent spec: `docs/superpowers/specs/2026-05-07-mobile-foundation-design.md`
- Phase 0 plan: `docs/superpowers/plans/2026-05-07-mobile-foundation-phase0.md`
- Existing sidebar JS: `templates/js/_headerJS.html` lines 442–478
- Existing sidebar CSS: `static/css/_header.css`
- Tap-target standard: WCAG 2.1 SC 2.5.5 (Target Size, AAA — 44 × 44 CSS px)
