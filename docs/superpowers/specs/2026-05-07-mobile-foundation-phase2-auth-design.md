# Mobile foundation — Phase 2: auth & chrome templates

**Status:** draft
**Author:** brainstormed with user 2026-05-07
**Parent spec:** [2026-05-07-mobile-foundation-design.md](./2026-05-07-mobile-foundation-design.md)
**Prior phase:** [Phase 1 — header polish](./2026-05-07-mobile-foundation-phase1-header-design.md)

## 1. Goal

Bring the 11 standalone "outside-the-app-shell" templates onto the mobile foundation introduced in Phase 0 (tokens, `nx-*` component library, compiled Tailwind v4) **without breaking their current standalone nature** (each owns its own `<!doctype html>`, head, body) and without re-flowing them through the main `_header.html` chrome.

Concretely, every one of these pages should:

- Use one compiled CSS path (`static/css/tailwind.css`) for shared utilities and tokens.
- Pass WCAG 2.1 AA at 375 px viewport (tap targets ≥ 44 × 44, contrast, focus visibility, ARIA correctness).
- Render correctly under all four supported locales.
- Lose their dependency on the **Tailwind v3 browser CDN** (`https://cdn.tailwindcss.com`).
- Stop introducing inline `<style>` blocks (CSP cleanliness).

## 2. Scope — the 11 templates

**Form tier (6) — get the full `nx-card` + `nx-form-field` treatment:**

| Template | Route | Purpose |
| --- | --- | --- |
| `templates/index.html` | `/login` | Username + password form |
| `templates/forgot_password.html` | `/forgot_password` | Email entry → reset link |
| `templates/reset_password.html` | `/set_new_password/<token>` | New password form |
| `templates/init_reset.html` | `/init_reset` | First-login password change |
| `templates/init_2FA.html` | `/init_2FA` | TOTP enrolment + QR + verify |
| `templates/verify_2fa.html` | `/verify_2fa` | 6-digit TOTP entry |

**Chrome tier (5) — preserve their distinct identity, only swap shared head + audit utilities:**

| Template | Route | Purpose |
| --- | --- | --- |
| `templates/hero.html` | `/hero` | Marketing-style landing for unauth visitors |
| `templates/maintenance.html` | `/maintenance` (and rendered on 503) | Maintenance window notice |
| `templates/handlers/403.html` | 403 handler | Forbidden |
| `templates/handlers/404.html` | 404 handler | Not found |
| `templates/handlers/500.html` | 500 handler | Server error |

Out of scope: the in-app pages (everything that already extends/includes `_header.html`) — those are Phase 3+.

Shared partial also touched: `templates/nexoraLogo/_nexoraLogo.html` (loads the Tailwind v3 CDN today; migrated alongside Phase 2 since it's used by the hero page).

## 3. Approach — A. Pragmatic two-tier

Decision locked during brainstorm:

- **Tier 1 (forms):** Strip per-page bespoke styles and rebuild on `nx-card`, `nx-page`, `nx-form-field`, `nx-input`, `nx-btn`. Visually unified across the six form pages — same card shadow, same field spacing, same button hierarchy. Tokens, no inline `style=`, no CDN. **Dark-mode support is added to tier-1** via the token system's dark variants (matched palette, not bolted on per-page).
- **Tier 2 (chrome):** Keep the existing visual character. Replace only the `<head>` block with a shared `_auth_head.html` include, and audit any Tailwind utility classes for v3→v4 renames. Bespoke CSS (e.g. `hero.css`) stays as a separate `<link>`. Existing dark-mode blocks are preserved as-is.

Why two tiers: the forms are functional and benefit from the foundation. The hero/maintenance/error pages are intentionally distinct artifacts and rebuilding them as nx-cards would erase character without solving a real problem.

## 3a. Pre-spec audit findings (2026-05-11)

A pre-approval grep over the 11 templates produced:

- **CDN usage:** 10/11 templates load `cdn.tailwindcss.com`. The one exception is `templates/maintenance.html`, which already loads no Tailwind. The shared partial `templates/nexoraLogo/_nexoraLogo.html` also loads the CDN and will be migrated alongside.
- **v3-only utility classes** (`flex-shrink-0`, `flex-grow-*`, `bg-opacity-*`, `text-opacity-*`, `border-opacity-*`, `decoration-clone`, `overflow-ellipsis`): **zero occurrences in the 11 in-scope templates.** These classes do exist in other templates (admin, generali, workitems) but those are out of Phase 2 scope. The §4.3 v3→v4 audit will therefore likely be a no-op — kept as a safety net.
- **Inline `<style>` blocks:** 1 occurrence, in `templates/maintenance.html`. Will be moved into `src/main.css` (or kept inside `extra_head` only if it can't be tokenized).
- **Inline `style="..."` attributes:** 8 total — `hero.html` (6), `init_reset.html` (1), `reset_password.html` (1). Modest cleanup.

## 4. Implementation recipes

### 4.1. Shared `_auth_head.html`

New partial at `templates/_auth_head.html` containing exactly what the in-app `_header.html` already loads, minus the navigation chrome:

- `<meta charset="UTF-8">`, viewport meta, theme-color
- Favicon links (existing set)
- `<link rel="stylesheet" href="{{ url_for('static', filename='css/tailwind.css') }}">`
- (No Tailwind v3 CDN script. No inline `<style>` block.)
- A `{% block extra_head %}{% endblock %}` for per-page hooks (e.g. hero loads its own CSS, init_2FA includes a small QR-handling script).

Every one of the 11 templates begins with:

```jinja
<!doctype html>
<html lang="{{ get_locale() }}">
{% include "_auth_head.html" %}
<body>
  …
</body>
</html>
```

The `_auth_head.html` partial does **not** open `<body>`; each page owns its own body classes so chrome-tier pages can keep their bespoke layout wrappers.

### 4.2. Tier-1 recipe (form pages)

1. Replace existing `<head>` with `{% include "_auth_head.html" %}` (plus `extra_head` for any per-page CSS that can't be deleted yet).
2. Wrap the form region in `<main class="nx-page">` and inside it `<section class="nx-card">`.
3. Each input gets `<div class="nx-form-field">` with `<label>` + `<input class="nx-input">` (or `nx-select`, etc.).
4. Primary action button: `<button class="nx-btn nx-btn--primary nx-btn--lg">`. Secondary action (cancel/link back): `<a class="nx-link-muted">`.
5. Error states: error string rendered into `<p class="nx-form-field__error" role="alert">` under the offending field; aria-invalid on the input.
6. Strip inline `style="…"` attributes — move what's needed into `src/main.css` as token-aware rules.
7. Delete page-specific CSS files (`password.css`, `_2fa.css` etc.) once the migration of that page is complete. Keep them through the implementation phase so reverts are clean.
8. **Dark-mode coverage:** every nx-* class used on form pages must render correctly under `html.dark`. Where tokens already have dark variants (text, surface, border, focus-ring), the components inherit them automatically. Any new token introduced for this phase ships with both light and dark values in the same `@theme` block. The theme toggle on `/login` continues to write `html.dark` exactly as it does today.

### 4.3. Tier-2 recipe (chrome pages)

1. Replace existing `<head>` with `{% include "_auth_head.html" %}`. If the page has bespoke CSS (e.g. `hero.css`), load it via `{% block extra_head %}<link …>{% endblock %}` — do not move its rules into `src/main.css`.
2. Audit utility classes for Tailwind v3 → v4 renames. Known renames to grep:
   - `flex-shrink-0` → `shrink-0`
   - `flex-grow-*` → `grow-*`
   - `bg-opacity-*`, `text-opacity-*`, `border-opacity-*` → slash syntax (`bg-black/50`)
   - `decoration-clone` → `box-decoration-clone`
   - `overflow-ellipsis` → `text-ellipsis`
3. Do not touch bespoke layout or visual character.
4. Smoke-test at 375 / 768 / 1280 in the browser; fix only what visibly regresses.

### 4.4. Inline-style purge

Every `style="…"` attribute introduced by these 11 templates should be replaced with a token-aware class. If a one-off rule is unavoidable, it lives in `src/main.css` (inside `@layer components` or `@layer utilities`), not in the template.

## 5. Testing & verification

For each of the 11 templates, six gates must pass:

1. **Axe scan** — new `tests/a11y/auth.spec.js` runs axe at 375 × 812 (mobile) and 1280 × 800 (desktop) against:
   - `/login`, `/forgot_password`, `/init_2FA`, `/verify_2fa`, `/hero`, `/maintenance`, and Flask error handlers via deliberately-bad URLs (`/__nonexistent__` for 404, etc.).
   - `/set_new_password/<token>` and `/init_reset` covered via a new dev-only helper route `/dev/mint_reset_token`, guarded by `app.config['ENVIRONMENT'] == 'INT'` (returns 404 otherwise). Issues a short-lived single-use token and seeds `session['pre_auth_userid']` so the reset pages render in their post-auth state.
2. **Tap-target audit** — programmatic Playwright check: every `<button>`, `<a>`, submit input ≥ 44 × 44 px at 375 viewport (`boundingBox()` assertion).
3. **Keyboard flow** — for `/login`: tab order username → password → submit → "forgot password" link → language switcher; ESC on any modal closes; focus restored.
4. **Visual smoke** — Playwright screenshots saved to `screenshots/phase2/<template>-<viewport>.png` at 375 / 768 / 1280 (human review, no pixel-diff).
5. **i18n smoke** — render each template under `de`, `fr`, `it`, `en`; assert no raw `_('…')` strings leak (regex check on the rendered HTML).
6. **CSP check** — `grep -r '<style' templates/index.html templates/forgot_password.html …` returns nothing; same for `cdn.tailwindcss.com`.

Existing test machinery to reuse:

- `playwright.config.js` (chromium-desktop, chromium-mobile = Pixel 5) — add a `chromium-tablet` project at 768×1024 if it makes the matrix cleaner; otherwise reuse mobile project with explicit `page.setViewportSize`.
- Login helper from `tests/a11y/header.spec.js` — `/dev/login/${TEST_USER}` with `ben.streich` fallback.
- New: a `tests/a11y/_fixtures/synthetic_reset_token.js` style helper if needed, or a dev-only Flask route under `ENVIRONMENT == 'INT'` that mints a one-shot reset token.

## 6. Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| Removing Tailwind v3 CDN breaks utility classes used in chrome-tier templates that aren't in our compiled v4 output. | Audit step in 4.3.2; `src/main.css` `@source` directive already scans all `templates/**.html`, so v4 will compile the utilities as long as the class names exist in current form. |
| Bespoke CSS (`hero.css`, `_2fa.css`) drifts from token palette. | Out of scope for Phase 2 — flagged for Phase 9 cleanup. Phase 2 keeps them as-is. |
| Synthetic-token test route accidentally ships to PROD. | Guard with `if app.config['ENVIRONMENT'] != 'INT': abort(404)` at the top of the handler. |
| New `Dismiss`-style gettext keys created during form migration aren't extracted. | Phase 2 acceptance gate runs `pybabel extract` and diffs `messages.pot`; any new keys must have translations queued before merge. |
| Per-locale text overflows tight form layouts (German is long). | Visual smoke gate in step 5.4 includes German. Card grows; inputs don't truncate. |

## 7. Out of scope

- In-app pages (handled in Phases 3+).
- Auth/business logic in `app.py` — pure template work.
- Server-side rate-limiter tuning.
- Email template styling (`forgot_password` sends an HTML email but that template is separate and not in scope here).
- Translation content updates beyond extracting new keys.

## 8. Acceptance criteria

Phase 2 is done when:

1. All 11 templates use `_auth_head.html`.
2. No template loads `cdn.tailwindcss.com`.
3. No template contains a `<style>` block.
4. `npm run test:a11y -- --grep auth` is green on both mobile and desktop projects.
5. Programmatic tap-target audit returns 0 failures.
6. Visual smoke screenshots committed at 375 / 768 / 1280 for each template.
7. `messages.pot` updated and `de`/`fr`/`it` `.po` files have entries (translated or `fuzzy`-marked) for any new keys.
8. `static/css/tailwind.css` rebuilt and committed; deploy.yml `git diff --exit-code` gate passes.
