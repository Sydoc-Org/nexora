# Mobile foundation — Phase 2 (auth & chrome) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **ABSOLUTE GIT RULE (project CLAUDE.md):** Never stage, commit, push, amend, reset, or run any git command that modifies the index or history. The "Commit" step in each task means **show the user the changed files**, then stop. The user runs all git operations.

**Goal:** Bring the 11 standalone "outside-the-app-shell" templates (login + 5 form pages + hero + maintenance + 3 error handlers) onto the Phase 0 mobile foundation — compiled Tailwind v4, design tokens, dark-mode support, a11y at AA — without re-flowing them through the in-app `_header.html` chrome.

**Architecture:** Two tiers. **Tier 1** (forms, 6 templates) rebuilds onto `nx-card` + `nx-form-field` + `nx-input` + `nx-btn` with dark-mode parity. **Tier 2** (hero + maintenance + 3 error handlers, 5 templates) keeps its bespoke visual identity but swaps the `<head>` block to a new shared `_auth_head.html` partial that loads `static/css/tailwind.css` (no more `cdn.tailwindcss.com`).

**Tech stack:** Tailwind v4 (CSS-first config in `src/main.css`, compiled via `@tailwindcss/cli`), Flask + Jinja2, Flask-Babel for i18n, Playwright + `@axe-core/playwright` for tests.

**Source spec:** [docs/superpowers/specs/2026-05-07-mobile-foundation-phase2-auth-design.md](../specs/2026-05-07-mobile-foundation-phase2-auth-design.md)

---

## File Structure

**Created:**
- `templates/_auth_head.html` — shared `<head>` partial for unauth pages
- `tests/a11y/auth.spec.js` — axe + tap-target test suite for the 11 templates
- `tests/a11y/_helpers/mint-reset-token.js` — Playwright helper that calls the dev mint route
- `screenshots/phase2/` — visual smoke output folder

**Modified:**
- `src/main.css` — adds dark-mode tokens + `@custom-variant dark`
- `static/css/tailwind.css` — rebuilt output (do not edit by hand)
- `app.py` — adds `/dev/mint_reset_token` route (INT-only)
- `templates/index.html` — rebuild on `nx-card` / `nx-form-field` / `nx-input` / `nx-btn`
- `templates/forgot_password.html` — same recipe
- `templates/reset_password.html` — same recipe
- `templates/init_reset.html` — same recipe
- `templates/init_2FA.html` — same recipe
- `templates/verify_2fa.html` — same recipe
- `templates/hero.html` — swap `<head>` only, preserve hero.css
- `templates/maintenance.html` — swap `<head>`, externalize inline styles to `static/css/maintenance.css`
- `templates/handlers/403.html` — swap `<head>` + utility audit
- `templates/handlers/404.html` — swap `<head>` + utility audit + fix invalid nested-anchor button
- `templates/handlers/500.html` — swap `<head>` + utility audit
- `templates/nexoraLogo/_nexoraLogo.html` — strip CDN, fix doubled `<h1>` issue
- `howtocss.txt` — append Phase 2 conventions
- `.github/workflows/deploy.yml` — add CDN-grep gate alongside CSS-sync gate
- `translations/*/LC_MESSAGES/messages.po` — extracted strings updated
- `messages.pot` — regenerated

**Deleted (only after migration verified):**
- `static/css/index.css` (after Task 5 verified)
- `static/css/forgot_password.css` (after Task 6 verified)
- `static/css/reset_password.css` (after Task 7 + Task 8 verified — used by both)

Bespoke CSS **kept**: `static/css/hero.css`, `static/css/_nexoraLogo.css`. Added: `static/css/maintenance.css`.

---

## Task 1: Add dark-mode tokens + custom-variant to src/main.css

**Why first:** every tier-1 component reads tokens via `var(--color-…)`. Adding `html.dark` overrides means every nx-* component "becomes dark-aware" with zero per-component churn. The `@custom-variant dark` line must live in `src/main.css` so the v4 compiler emits dark variants for utilities (currently it's only declared inline inside `_header.html`).

**Files:**
- Modify: `src/main.css`

- [ ] **Step 1: Add the custom-variant declaration at the top**

Insert immediately after `@import "tailwindcss";` (line 1) and before the existing `@theme` block:

```css
/* Enable Tailwind's `dark:` variant when html has the .dark class.
   This is what the existing theme toggle on /login already toggles. */
@custom-variant dark (&:where(.dark, .dark *));
```

- [ ] **Step 2: Add `@layer base` block with `html.dark` token overrides**

Append at the end of `src/main.css` (after the last `@layer components` closing `}`):

```css
/* ============================================================
   Dark-mode token overrides.
   Activated by class="dark" on <html>; the unauth /login theme
   toggle already writes this class to localStorage + DOM.
   Color values chosen for WCAG AA contrast on the dark surface.
   ============================================================ */
@layer base {
  html.dark {
    --color-bg-page:        #0f172a;  /* slate-900 */
    --color-bg-surface:     #1e293b;  /* slate-800 */
    --color-bg-muted:       #1e293b;
    --color-bg-emphasis:    #334155;  /* slate-700 */

    --color-border:         #334155;
    --color-border-strong:  #475569;  /* slate-600 */

    --color-text-primary:   #f1f5f9;  /* slate-100 — 15.8:1 on slate-900 */
    --color-text-secondary: #cbd5e1;  /* slate-300 — 11.0:1 on slate-900 */
    --color-text-meta:      #94a3b8;  /* slate-400 — 6.6:1 on slate-900 */
    --color-text-on-primary:#ffffff;

    /* Brand stays — indigo holds up on dark; just lift focus ring opacity */
    --color-focus-ring:     rgb(129 140 248 / 0.32);

    /* Semantic — tweak to keep contrast in dark */
    --color-success-bg:     #052e2b;
    --color-warning-bg:     #3f2a0a;
    --color-danger-bg:      #3a0e10;

    /* Elevation shadows on dark need more opacity to read */
    --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.4);
    --shadow-md: 0 4px 12px -2px rgb(0 0 0 / 0.5);
    --shadow-lg: 0 12px 32px -4px rgb(0 0 0 / 0.6);
  }

  html.dark body {
    background: var(--color-bg-page);
    color: var(--color-text-primary);
  }
}
```

- [ ] **Step 3: Rebuild the compiled CSS**

Run: `npm run build:css`
Expected: completes silently. `static/css/tailwind.css` is regenerated.

- [ ] **Step 4: Manual smoke at /design-system**

Start nexora (`pwsh -File nx.ps1 -u`), open `/design-system`, open devtools, run `document.documentElement.classList.add('dark')`, confirm cards/inputs/buttons flip to the dark palette with readable contrast. Then `document.documentElement.classList.remove('dark')` to confirm light mode still works.

- [ ] **Step 5: Surface diff (no commit)**

Show the user the modified files (`src/main.css`, `static/css/tailwind.css`). Note that dark-mode is now token-supported across every nx-* component.

---

## Task 2: Create the shared `_auth_head.html` partial

**Files:**
- Create: `templates/_auth_head.html`

- [ ] **Step 1: Write the partial**

Create `templates/_auth_head.html` with this content:

```jinja
{# Shared <head> for unauth/standalone pages. Each consuming page
   sets `page_title` before including this partial:
       {% set page_title = _('Login - nexora') %}
       {% include '_auth_head.html' %}

   Optional: set `extra_css_files = ['css/hero.css']` to load
   page-specific stylesheets in addition to tailwind.css. #}
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <title>{{ page_title or 'nexora' }}</title>

    <link rel="stylesheet" href="{{ url_for('static', filename='css/tailwind.css') }}">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
    <link rel="icon" type="image/x-icon" href="{{ url_for('static', filename='images/favicon.ico') }}">

    {% for css_file in (extra_css_files or []) %}
        <link rel="stylesheet" href="{{ url_for('static', filename=css_file) }}">
    {% endfor %}
</head>
```

Notes:
- **No** `cdn.tailwindcss.com` script.
- **No** inline tailwind style block — the `@custom-variant dark` lives in `src/main.css` (Task 1).
- Uses `{% set page_title = ... %}` + `{% include %}` rather than `{% extends %}`/`{% block %}` because the existing codebase uses include-style composition for these pages.

- [ ] **Step 2: Surface diff (no commit)**

Show the user the new file. The partial isn't included by anything until Task 5+.

---

## Task 3: Add dev-only `/dev/mint_reset_token` route

**Why:** Phase 2 §5.1 test gate axe-scans `/set_new_password/<token>` and `/init_reset`, both of which require a valid session/token. The dev route mints one in INT only, guarded so it 404s in PROD.

**Files:**
- Modify: `app.py` — add new route near existing `/dev/login/<username>` route (~line 783).

- [ ] **Step 1: Investigate how the real reset flow validates tokens**

Run `Grep` in `app.py` for `set_new_password` and read the route + any helper. Find:
- What serializer (if any) is used (likely `itsdangerous.URLSafeTimedSerializer`).
- The salt value used.
- Any DB lookup the token triggers (e.g. a `PasswordResetTokens` table).

You **must** mint a token that the real route accepts. If the real flow uses a DB-backed token, insert a row with the right shape; if it uses `itsdangerous`, use the same signer + salt.

- [ ] **Step 2: Add the route**

Locate the existing `@app.route("/dev/login/<username>")` block. Add immediately after the `dev_login` function ends:

```python
@app.route("/dev/mint_reset_token/<username>")
def dev_mint_reset_token(username):
    """INT-only helper for a11y tests. Mints a single-use reset token for `username`
    and stashes `pre_auth_userid` in session so /init_reset and /set_new_password
    render in their authed state. Returns the URLs the caller should navigate to."""
    if os.environ.get("ENVIRONMENT") != "INT":
        abort(404)

    cursor = None
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT userid FROM Users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if not row:
            abort(404)
        userid = str(row[0])
        session['pre_auth_userid'] = userid

        # Mint a token compatible with set_new_password — adapt this block
        # to whatever scheme that route uses (Step 1 above).
        from itsdangerous import URLSafeTimedSerializer
        signer = URLSafeTimedSerializer(app.config['SECRET_KEY'], salt='reset-password')
        token = signer.dumps(userid)

        return {
            "userid": userid,
            "token": token,
            "init_reset_url": url_for('init_reset'),
            "set_new_password_url": f"/set_new_password/{token}",
        }
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
```

The salt `'reset-password'` is a placeholder — replace with the actual salt the real route uses. If the real flow doesn't use `itsdangerous`, replace the mint logic with whatever does work (e.g. `INSERT INTO PasswordResetTokens (token, userid, expiresAt) VALUES (...)`).

- [ ] **Step 3: Smoke test in INT**

Start nexora: `pwsh -File nx.ps1 -u`
Browser: `http://localhost:5000/dev/mint_reset_token/ben.streich`
Expected: JSON with `userid`, `token`, `init_reset_url`, `set_new_password_url`.

Then navigate to the `set_new_password_url` value. Page should render the reset form (not redirect to login).

- [ ] **Step 4: Verify PROD guard**

Use `pwsh -Command '$env:ENVIRONMENT="PROD"; pwsh -File nx.ps1 -u'` in a temporary shell (per the project rule, **never** leave the env var overwritten in your main shell). Hit the same URL: must return 404. Close that shell.

- [ ] **Step 5: Surface diff (no commit)**

---

## Task 4: Write the a11y test scaffold

**Files:**
- Create: `tests/a11y/auth.spec.js`
- Create: `tests/a11y/_helpers/mint-reset-token.js`

- [ ] **Step 1: Create the mint helper**

`tests/a11y/_helpers/mint-reset-token.js`:

```js
// Helper: hit the INT-only /dev/mint_reset_token route and return the URLs.
// Used by auth.spec.js to render reset pages in their authed state.
const { request } = require('@playwright/test');

async function mintResetToken(baseURL, username) {
  const ctx = await request.newContext({ baseURL });
  const res = await ctx.get(`/dev/mint_reset_token/${username}`);
  if (!res.ok()) {
    throw new Error(`mint_reset_token failed: ${res.status()} ${await res.text()}`);
  }
  return res.json();
}

module.exports = { mintResetToken };
```

- [ ] **Step 2: Create the spec**

`tests/a11y/auth.spec.js`:

```js
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const { mintResetToken } = require('./_helpers/mint-reset-token');

const TEST_USER = process.env.NX_A11Y_USER || 'ben.streich';

// Pages we can axe-scan without any auth/session state.
const UNAUTH_PAGES = [
  { path: '/login',           name: 'login' },
  { path: '/forgot_password', name: 'forgot_password' },
  { path: '/hero',            name: 'hero' },
  { path: '/maintenance',     name: 'maintenance' },
  { path: '/__definitely_not_a_real_page__', name: '404', expectStatus: 404 },
];

for (const page_ of UNAUTH_PAGES) {
  test(`a11y: ${page_.name}`, async ({ page }) => {
    const resp = await page.goto(page_.path);
    if (page_.expectStatus) expect(resp.status()).toBe(page_.expectStatus);
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });
}

test('a11y: init_reset', async ({ page, baseURL }) => {
  const { init_reset_url } = await mintResetToken(baseURL, TEST_USER);
  await page.goto(init_reset_url);
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
});

test('a11y: set_new_password', async ({ page, baseURL }) => {
  const { set_new_password_url } = await mintResetToken(baseURL, TEST_USER);
  await page.goto(set_new_password_url);
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
});

// init_2FA and verify_2fa need a deeper session prime (post-bcrypt, pre-2FA).
// Smoke them manually; flagged in Task 17.

// Keyboard flow for the login form: tab order username -> password -> submit -> forgot password.
// ESC handling is N/A on /login (no modals); add it here if /login ever gets a modal.
test('keyboard: login tab order', async ({ page }) => {
  await page.goto('/login');
  await page.keyboard.press('Tab');
  let id = await page.evaluate(() => document.activeElement && document.activeElement.id);
  // The page may have a leading skip-link or theme toggle; advance until we reach username.
  for (let i = 0; i < 5 && id !== 'username'; i++) {
    await page.keyboard.press('Tab');
    id = await page.evaluate(() => document.activeElement && document.activeElement.id);
  }
  expect(id).toBe('username');

  await page.keyboard.press('Tab');
  expect(await page.evaluate(() => document.activeElement && document.activeElement.id)).toBe('password');

  // Next focusable should be either the "forgot password" link or the submit button,
  // depending on visual ordering. The submit button must be reachable in <= 3 more Tabs.
  let reachedSubmit = false;
  for (let i = 0; i < 3; i++) {
    await page.keyboard.press('Tab');
    const t = await page.evaluate(() => document.activeElement && document.activeElement.tagName);
    if (t === 'BUTTON') { reachedSubmit = true; break; }
  }
  expect(reachedSubmit).toBe(true);
});

// Tap-target audit (44x44 minimum) at 375 viewport.
test('tap-targets: login at 375', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/login');
  const failures = await page.locator('button, a, input[type="submit"], input[type="button"]')
    .evaluateAll((els) => els
      .map(el => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) return null;
        if (r.width < 44 || r.height < 44) {
          return { tag: el.tagName, text: (el.innerText || el.value || '').slice(0, 40),
                   w: r.width, h: r.height };
        }
        return null;
      })
      .filter(Boolean));
  expect(failures, JSON.stringify(failures, null, 2)).toEqual([]);
});
```

- [ ] **Step 3: Run the suite**

```powershell
pwsh -File nx.ps1 -u  # one terminal
npm run test:a11y -- --grep "a11y: login"  # another
```

Expected at this point: the `a11y: login` test will likely **FAIL** because login still uses the old template. That's expected — Task 5 fixes it. Confirm the test infra works (axe loads, the URL responds, violations are listed).

- [ ] **Step 4: Surface diff (no commit)**

---

## Task 5: Migrate `templates/index.html` (login)

**Files:**
- Modify: `templates/index.html`
- Defer-delete (Task 19): `static/css/index.css`

- [ ] **Step 1: Replace the full template content**

Overwrite `templates/index.html` with:

```jinja
{% set page_title = _("Login - nexora") %}
<!doctype html>
<html lang="{{ get_locale }}">
{% include '_auth_head.html' %}

<body class="min-h-screen flex flex-col bg-[var(--color-bg-page)] text-[var(--color-text-primary)]">

    {% include '_maintenance_banner.html' %}

    <header class="bg-[var(--color-bg-surface)] shadow-sm">
        <div class="container mx-auto flex items-center justify-between px-6 py-4">
            {% include 'nexoraLogo/_nexoraLogo.html' %}
        </div>
    </header>

    <main class="nx-page flex-grow flex items-center justify-center">
        <section class="nx-card w-full max-w-md mx-auto" aria-labelledby="login-heading">
            <div class="nx-card-header">
                <h1 id="login-heading" class="nx-card-header__title text-center">{{ _("Sign in") }}</h1>
            </div>
            <div class="nx-card-body">
                {% if error %}
                <div role="alert" class="mb-4 px-3 py-2 rounded-md text-sm"
                     style="background: var(--color-danger-bg); color: var(--color-danger);">
                    {{ error }}
                </div>
                {% endif %}

                <form method="POST" action="{{ url_for('login') }}" novalidate>
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>

                    <div class="nx-form-field">
                        <label for="username" class="nx-form-field__label">{{ _("Username") }}</label>
                        <input type="text" id="username" name="username"
                               class="nx-input" autocomplete="username"
                               aria-required="true" required
                               placeholder='{{ _("Your Username") }}'>
                    </div>

                    <div class="nx-form-field">
                        <label for="password" class="nx-form-field__label">{{ _("Password") }}</label>
                        <input type="password" id="password" name="password"
                               class="nx-input" autocomplete="current-password"
                               aria-required="true" required
                               placeholder="••••••••••">
                    </div>

                    <div class="flex items-center justify-end mb-4">
                        <a href="{{ url_for('forgot_password') }}" class="nx-link-muted text-sm">
                            {{ _("Forgot password") }}?
                        </a>
                    </div>

                    <button type="submit" class="nx-btn nx-btn--primary nx-btn--lg w-full">
                        {{ _("Sign in") }}
                    </button>
                </form>
            </div>
        </section>
    </main>

    {% include '_small_footer.html' %}
</body>
</html>
```

Key changes vs. the old file:
- Drops `cdn.tailwindcss.com` script and `index.css` link.
- Replaces every bespoke utility chain with `nx-card`, `nx-form-field`, `nx-input`, `nx-btn`.
- Adds `aria-labelledby`, `autocomplete`, `aria-required` where appropriate.
- The visible "Username" label replaces the icon-decorated input — screen readers get a real label.

- [ ] **Step 2: Rebuild CSS**

```powershell
npm run build:css
```

- [ ] **Step 3: Visual smoke**

Browser at `/login`: confirm the page renders. Toggle dark mode via devtools console: `document.documentElement.classList.toggle('dark')` and confirm contrast remains readable.

- [ ] **Step 4: Run the axe test for login**

```powershell
npm run test:a11y -- --grep "a11y: login"
```

Expected: PASS on both `chromium-desktop` and `chromium-mobile`.

- [ ] **Step 5: Run tap-target audit**

```powershell
npm run test:a11y -- --grep "tap-targets: login"
```

Expected: PASS.

- [ ] **Step 6: Surface diff (no commit)**

Show user the modified `templates/index.html`. **Do not delete `static/css/index.css` yet** — that happens in Task 19.

---

## Task 6: Migrate `templates/forgot_password.html`

**Files:**
- Modify: `templates/forgot_password.html`

- [ ] **Step 1: Replace template content**

```jinja
{% set page_title = _("Forgot password - nexora") %}
<!doctype html>
<html lang="{{ get_locale }}">
{% include '_auth_head.html' %}

<body class="min-h-screen flex flex-col bg-[var(--color-bg-page)] text-[var(--color-text-primary)]">

    <header class="bg-[var(--color-bg-surface)] shadow-sm">
        <div class="container mx-auto flex items-center justify-between px-6 py-4">
            {% include 'nexoraLogo/_nexoraLogo.html' %}
        </div>
    </header>

    <main class="nx-page flex-grow flex items-center justify-center">
        <section class="nx-card w-full max-w-md mx-auto" aria-labelledby="forgot-heading">
            <div class="nx-card-header">
                <h1 id="forgot-heading" class="nx-card-header__title text-center">{{ _("Forgot your password") }}?</h1>
                <p class="text-sm text-center mt-2" style="color: var(--color-text-secondary);">
                    {{ _("No problem. Enter the email address associated with your account and we'll send you a link to reset your password") }}.
                </p>
            </div>
            <div class="nx-card-body">
                {% if error %}
                <div role="alert" class="mb-4 px-3 py-2 rounded-md text-sm"
                     style="background: var(--color-danger-bg); color: var(--color-danger);">
                    {{ error }}
                </div>
                {% endif %}
                {% if message %}
                <div role="status" class="mb-4 px-3 py-2 rounded-md text-sm"
                     style="background: var(--color-success-bg); color: var(--color-success);">
                    {{ message }}
                </div>
                {% endif %}

                <form method="POST" action="{{ url_for('request_password_reset') }}" novalidate>
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>

                    <div class="nx-form-field">
                        <label for="email" class="nx-form-field__label">{{ _("Email address") }}</label>
                        <input type="email" id="email" name="email"
                               class="nx-input" autocomplete="email"
                               aria-required="true" required
                               placeholder="your.email@example.com">
                    </div>

                    <button type="submit" class="nx-btn nx-btn--primary nx-btn--lg w-full mb-4">
                        {{ _("Send reset link") }}
                    </button>
                </form>

                <div class="text-center">
                    <a href="{{ url_for('login') }}" class="nx-link-muted text-sm">
                        <i class="fas fa-arrow-left mr-1" aria-hidden="true"></i> {{ _("Back to login") }}
                    </a>
                </div>
            </div>
        </section>
    </main>

    {% include '_small_footer.html' %}
</body>
</html>
```

- [ ] **Step 2: Rebuild + axe**

```powershell
npm run build:css
npm run test:a11y -- --grep "a11y: forgot_password"
```

Expected: PASS on both projects.

- [ ] **Step 3: Visual smoke**

`/forgot_password` in browser, toggle dark mode, confirm both states render.

- [ ] **Step 4: Surface diff (no commit)**

---

## Task 7: Migrate `templates/reset_password.html`

**Files:**
- Modify: `templates/reset_password.html`

- [ ] **Step 1: Replace template content**

```jinja
{% set page_title = _("Reset password - nexora") %}
<!doctype html>
<html lang="{{ get_locale }}">
{% include '_auth_head.html' %}

<body class="min-h-screen flex flex-col bg-[var(--color-bg-page)] text-[var(--color-text-primary)]">

    <header class="bg-[var(--color-bg-surface)] shadow-sm">
        <div class="container mx-auto flex items-center justify-between px-6 py-4">
            {% include 'nexoraLogo/_nexoraLogo.html' %}
        </div>
    </header>

    <main class="nx-page flex-grow flex items-center justify-center">
        <section class="nx-card w-full max-w-md mx-auto" aria-labelledby="reset-heading">
            <div class="nx-card-header">
                <h1 id="reset-heading" class="nx-card-header__title text-center">{{ _("Set a new password") }}</h1>
                <p class="text-sm text-center mt-2" style="color: var(--color-text-secondary);">
                    {{ _("Your new password must be different from your previously used password.") }}
                </p>
            </div>
            <div class="nx-card-body">
                {% if error %}
                <div role="alert" class="mb-4 px-3 py-2 rounded-md text-sm"
                     style="background: var(--color-danger-bg); color: var(--color-danger);">
                    {{ error }}
                </div>
                {% endif %}
                {% if message %}
                <div role="status" class="mb-4 px-3 py-2 rounded-md text-sm"
                     style="background: var(--color-success-bg); color: var(--color-success);">
                    {{ message }}
                </div>
                {% endif %}

                <form id="resetForm" method="POST" action="{{ url_for('set_new_password') }}" novalidate>
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>

                    <div class="nx-form-field">
                        <label for="new-password" class="nx-form-field__label">{{ _("New password") }}</label>
                        <input type="password" id="new-password" name="new-password"
                               class="nx-input" autocomplete="new-password"
                               aria-required="true" required
                               placeholder='{{ _("Enter your new password") }}'>
                    </div>

                    <div class="nx-form-field">
                        <label for="confirm-password" class="nx-form-field__label">{{ _("Confirm new password") }}</label>
                        <input type="password" id="confirm-password" name="confirm-password"
                               class="nx-input" autocomplete="new-password"
                               aria-required="true" required
                               placeholder='{{ _("Confirm your new password") }}'>
                    </div>

                    <button type="submit" class="nx-btn nx-btn--primary nx-btn--lg w-full mb-4">
                        {{ _("Reset password") }}
                    </button>
                </form>

                <div class="text-center">
                    <a href="{{ url_for('login') }}" class="nx-link-muted text-sm">
                        <i class="fas fa-arrow-left mr-1" aria-hidden="true"></i> {{ _("Back to login") }}
                    </a>
                </div>
            </div>
        </section>
    </main>

    {% include '_small_footer.html' %}
</body>
</html>
```

- [ ] **Step 2: Rebuild + axe**

```powershell
npm run build:css
npm run test:a11y -- --grep "a11y: set_new_password"
```

Expected: PASS on both projects (this test uses the mint helper from Task 4).

- [ ] **Step 3: Visual smoke (with mint route)**

Browser: visit `/dev/mint_reset_token/ben.streich`, copy the `set_new_password_url`, paste it. Confirm the form renders. Toggle dark mode.

- [ ] **Step 4: Surface diff (no commit)**

---

## Task 8: Migrate `templates/init_reset.html`

**Files:**
- Modify: `templates/init_reset.html`

Structurally identical to Task 7 except:
- `page_title` = `_('Initial Password Reset - nexora')`
- Form `action` = `url_for('init_reset_password')`
- Submit button text = `_("Continue")`

- [ ] **Step 1: Replace template content**

```jinja
{% set page_title = _("Initial Password Reset - nexora") %}
<!doctype html>
<html lang="{{ get_locale }}">
{% include '_auth_head.html' %}

<body class="min-h-screen flex flex-col bg-[var(--color-bg-page)] text-[var(--color-text-primary)]">

    <header class="bg-[var(--color-bg-surface)] shadow-sm">
        <div class="container mx-auto flex items-center justify-between px-6 py-4">
            {% include 'nexoraLogo/_nexoraLogo.html' %}
        </div>
    </header>

    <main class="nx-page flex-grow flex items-center justify-center">
        <section class="nx-card w-full max-w-md mx-auto" aria-labelledby="initreset-heading">
            <div class="nx-card-header">
                <h1 id="initreset-heading" class="nx-card-header__title text-center">{{ _("Set a new password") }}</h1>
                <p class="text-sm text-center mt-2" style="color: var(--color-text-secondary);">
                    {{ _("Your new password must be different from your previously used password.") }}
                </p>
            </div>
            <div class="nx-card-body">
                {% if error %}
                <div role="alert" class="mb-4 px-3 py-2 rounded-md text-sm"
                     style="background: var(--color-danger-bg); color: var(--color-danger);">
                    {{ error }}
                </div>
                {% endif %}
                {% if message %}
                <div role="status" class="mb-4 px-3 py-2 rounded-md text-sm"
                     style="background: var(--color-success-bg); color: var(--color-success);">
                    {{ message }}
                </div>
                {% endif %}

                <form id="resetForm" method="POST" action="{{ url_for('init_reset_password') }}" novalidate>
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>

                    <div class="nx-form-field">
                        <label for="new-password" class="nx-form-field__label">{{ _("New password") }}</label>
                        <input type="password" id="new-password" name="new-password"
                               class="nx-input" autocomplete="new-password"
                               aria-required="true" required
                               placeholder='{{ _("Enter your new password") }}'>
                    </div>

                    <div class="nx-form-field">
                        <label for="confirm-password" class="nx-form-field__label">{{ _("Confirm new password") }}</label>
                        <input type="password" id="confirm-password" name="confirm-password"
                               class="nx-input" autocomplete="new-password"
                               aria-required="true" required
                               placeholder='{{ _("Confirm your new password") }}'>
                    </div>

                    <button type="submit" class="nx-btn nx-btn--primary nx-btn--lg w-full mb-4">
                        {{ _("Continue") }}
                    </button>
                </form>

                <div class="text-center">
                    <a href="{{ url_for('login') }}" class="nx-link-muted text-sm">
                        <i class="fas fa-arrow-left mr-1" aria-hidden="true"></i> {{ _("Back to login") }}
                    </a>
                </div>
            </div>
        </section>
    </main>

    {% include '_small_footer.html' %}
</body>
</html>
```

- [ ] **Step 2: Rebuild + axe**

```powershell
npm run build:css
npm run test:a11y -- --grep "a11y: init_reset"
```

- [ ] **Step 3: Surface diff (no commit)**

---

## Task 9: Migrate `templates/init_2FA.html`

**Files:**
- Modify: `templates/init_2FA.html`

- [ ] **Step 1: Replace template content**

```jinja
{% set page_title = _("Setup 2FA - nexora") %}
<!doctype html>
<html lang="{{ get_locale }}">
{% include '_auth_head.html' %}

<body class="min-h-screen flex flex-col bg-[var(--color-bg-page)] text-[var(--color-text-primary)]">

    <header class="bg-[var(--color-bg-surface)] shadow-sm">
        <div class="container mx-auto flex items-center justify-between px-6 py-4">
            {% include 'nexoraLogo/_nexoraLogo.html' %}
        </div>
    </header>

    <main class="nx-page flex-grow flex items-center justify-center px-4">
        <section class="nx-card w-full max-w-md mx-auto" aria-labelledby="init2fa-heading">
            <div class="nx-card-header">
                <h1 id="init2fa-heading" class="nx-card-header__title text-center">{{ _("Secure Your Account") }}</h1>
                <p class="text-sm text-center mt-2" style="color: var(--color-text-secondary);">
                    {{ _("Scan the QR code below with your Authenticator App (Microsoft or Google Authenticator).") }}
                </p>
            </div>
            <div class="nx-card-body">
                {% with messages = get_flashed_messages(category_filter=["error"]) %}
                {% if messages %}
                <div role="alert" class="mb-4 px-3 py-2 rounded-md text-sm"
                     style="background: var(--color-danger-bg); color: var(--color-danger);">
                    {% for msg in messages %}<p>{{ msg }}</p>{% endfor %}
                </div>
                {% endif %}
                {% endwith %}

                <div class="flex justify-center mb-6">
                    {% if qr_code %}
                    <div class="p-2 rounded-lg" style="border: 1px solid var(--color-border);">
                        <img src="data:image/png;base64,{{ qr_code }}"
                             alt="{{ _('2FA QR Code') }}" class="w-48 h-48" width="192" height="192">
                    </div>
                    {% else %}
                    <p style="color: var(--color-danger);">{{ _("Error generating QR code. Please refresh.") }}</p>
                    {% endif %}
                </div>

                <div class="text-center mb-8">
                    <p class="text-xs mb-1" style="color: var(--color-text-meta);">{{ _("Can't scan the code?") }}</p>
                    <p class="text-xs mb-2" style="color: var(--color-text-meta);">{{ _("Enter this code manually:") }}</p>
                    <p class="font-mono text-sm font-medium py-1 px-3 rounded inline-block select-all"
                       style="background: var(--color-bg-emphasis);">{{ secret }}</p>
                </div>

                <form action="{{ url_for('init_2FA') }}" method="POST" novalidate>
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>

                    <div class="nx-form-field">
                        <label for="code" class="nx-form-field__label">{{ _("Enter 6-digit Code") }}</label>
                        <input type="text" name="code" id="code"
                               class="nx-input"
                               inputmode="numeric" pattern="[0-9]*"
                               autocomplete="one-time-code"
                               aria-required="true" required
                               placeholder="123456">
                    </div>

                    <button type="submit" class="nx-btn nx-btn--primary nx-btn--lg w-full flex items-center justify-center gap-2">
                        <i class="fas fa-check-circle" aria-hidden="true"></i>
                        {{ _("Verify and Enable") }}
                    </button>
                </form>
            </div>
        </section>
    </main>

    {% include '_small_footer.html' %}
</body>
</html>
```

- [ ] **Step 2: Rebuild**

```powershell
npm run build:css
```

- [ ] **Step 3: Manual smoke (no auto-test — needs deeper session prime)**

Log in as a user whose `twoFA` flag is `0` (or temporarily flip a test user's flag in INT). Confirm the page renders, QR shows, layout looks correct at 375px and 1280px. Toggle dark mode.

- [ ] **Step 4: Surface diff (no commit)**

---

## Task 10: Migrate `templates/verify_2fa.html`

**Files:**
- Modify: `templates/verify_2fa.html`

- [ ] **Step 1: Replace template content**

```jinja
{% set page_title = _("Two-Factor Authentication - nexora") %}
<!doctype html>
<html lang="{{ get_locale }}">
{% include '_auth_head.html' %}

<body class="min-h-screen flex flex-col bg-[var(--color-bg-page)] text-[var(--color-text-primary)]">

    <header class="bg-[var(--color-bg-surface)] shadow-sm">
        <div class="container mx-auto flex items-center justify-between px-6 py-4">
            {% include 'nexoraLogo/_nexoraLogo.html' %}
        </div>
    </header>

    <main class="nx-page flex-grow flex items-center justify-center px-4">
        <section class="nx-card w-full max-w-md mx-auto" aria-labelledby="verify2fa-heading">
            <div class="nx-card-header">
                <div class="flex justify-center mb-4">
                    <span class="inline-flex items-center justify-center w-16 h-16 rounded-full"
                          style="background: var(--color-primary-50); color: var(--color-primary-600);"
                          aria-hidden="true">
                        <i class="fas fa-shield-alt text-2xl"></i>
                    </span>
                </div>
                <h1 id="verify2fa-heading" class="nx-card-header__title text-center">{{ _("Two-Factor Authentication") }}</h1>
                <p class="text-sm text-center mt-2" style="color: var(--color-text-secondary);">
                    {{ _("Please enter the code from your authenticator app to continue.") }}
                </p>
            </div>
            <div class="nx-card-body">
                {% with messages = get_flashed_messages(category_filter=["error"]) %}
                {% if messages %}
                <div role="alert" class="mb-4 px-3 py-2 rounded-md text-sm"
                     style="background: var(--color-danger-bg); color: var(--color-danger);">
                    {% for msg in messages %}<p class="flex items-center"><i class="fas fa-exclamation-circle mr-2" aria-hidden="true"></i>{{ msg }}</p>{% endfor %}
                </div>
                {% endif %}
                {% endwith %}

                <form action="{{ url_for('verify_2fa') }}" method="POST" novalidate>
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>

                    <div class="nx-form-field">
                        <label for="code" class="nx-form-field__label sr-only">{{ _("6-digit code") }}</label>
                        <input type="text" name="code" id="code"
                               class="nx-input text-center text-2xl tracking-widest font-mono"
                               inputmode="numeric" pattern="[0-9]*"
                               autocomplete="one-time-code"
                               aria-required="true" required autofocus
                               placeholder="000 000">
                    </div>

                    <button type="submit" class="nx-btn nx-btn--primary nx-btn--lg w-full">
                        {{ _("Verify Identity") }}
                    </button>
                </form>
            </div>
        </section>
    </main>

    {% include '_small_footer.html' %}
</body>
</html>
```

Note: visible label hidden via `sr-only` because the visual design uses the input itself as the obvious affordance (large, centered, monospaced). Screen readers still get the label.

- [ ] **Step 2: Rebuild + manual smoke**

```powershell
npm run build:css
```

Trigger via login flow (user with 2FA already initialized). Smoke at 375/1280 + dark mode.

- [ ] **Step 3: Surface diff (no commit)**

---

## Task 11: Migrate `templates/hero.html` (Tier 2)

**Files:**
- Modify: `templates/hero.html`

Tier-2 recipe — preserve hero.css, swap the head.

- [ ] **Step 1: Replace the `<!doctype>` + `<head>` block**

Current top of file (lines 1–13):

```jinja
<!DOCTYPE html>
<html lang="{{ get_locale }}">
<head>
    <meta charset="UTF-8">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <title>Secure Document Tracking - nexora</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
    <link rel="icon" type="image/x-icon" href="{{ url_for('static',filename='images/favicon.ico') }}">
    <link rel="stylesheet" href="{{ url_for('static',filename='css/hero.css') }}">

</head>
```

Replace with:

```jinja
{% set page_title = "Secure Document Tracking - nexora" %}
{% set extra_css_files = ['css/hero.css'] %}
<!doctype html>
<html lang="{{ get_locale }}">
{% include '_auth_head.html' %}
```

The rest of the file (`<body>` and below) stays untouched.

- [ ] **Step 2: Utility audit**

Run `Grep` in `templates/hero.html` for `flex-shrink-0|flex-grow-|bg-opacity-|text-opacity-|border-opacity-|decoration-clone|overflow-ellipsis`.
Expected: zero matches (per the §3a audit). If anything appears, rename per spec §4.3.2.

- [ ] **Step 3: Rebuild + visual smoke at 375/768/1280**

```powershell
npm run build:css
```

Open `/hero` in browser, resize devtools to each viewport, screenshot each to `screenshots/phase2/hero-{375,768,1280}.png`. Confirm preloader still works.

- [ ] **Step 4: a11y smoke (axe)**

```powershell
npm run test:a11y -- --grep "a11y: hero"
```

Expected: PASS. If new violations appear (likely from `hero.css` colors that fail AA contrast), flag for a follow-up Phase 9 cleanup rather than touching hero.css now — spec §6 preserves hero.css.

- [ ] **Step 5: Surface diff (no commit)**

---

## Task 12: Migrate `templates/maintenance.html` (Tier 2)

**Files:**
- Create: `static/css/maintenance.css`
- Modify: `templates/maintenance.html`

This template has a substantial inline `<style>` block (~110 lines). Externalize it for CSP cleanliness.

- [ ] **Step 1: Create `static/css/maintenance.css`**

Copy the content between `<style>` and `</style>` in the current `templates/maintenance.html` (lines 10–119) into a new file `static/css/maintenance.css`. Do not retokenize the colors — spec §6 says preserve bespoke CSS.

- [ ] **Step 2: Replace `templates/maintenance.html` `<head>` block**

Replace lines 1–120 (the `<!doctype>`, `<head>`, `<style>...</style>`, `</head>`) with:

```jinja
{% set page_title = _("Maintenance - nexora") %}
{% set extra_css_files = ['css/maintenance.css'] %}
<!doctype html>
<html lang="{{ get_locale }}">
{% include '_auth_head.html' %}
```

The `<body>` content and the auto-refresh script at the bottom of the file stay untouched.

- [ ] **Step 3: Rebuild + axe + visual smoke**

```powershell
npm run build:css
npm run test:a11y -- --grep "a11y: maintenance"
```

Visual smoke at 375/1280, screenshots to `screenshots/phase2/maintenance-{375,1280}.png`.

- [ ] **Step 4: Surface diff (no commit)**

---

## Task 13: Migrate `templates/handlers/403.html` (Tier 2)

**Files:**
- Modify: `templates/handlers/403.html`

- [ ] **Step 1: Read the current file**

Read `templates/handlers/403.html` in full so the exact existing structure is in context.

- [ ] **Step 2: Replace the `<head>` block**

Replace the existing `<!doctype>` / `<html>` / `<head>...</head>` opening with:

```jinja
{% set page_title = "403 - nexora" %}
<!doctype html>
<html lang="{{ get_locale }}">
{% include '_auth_head.html' %}
```

- [ ] **Step 3: Utility audit**

Grep this file for v3-only utility classes (`flex-shrink-0|flex-grow-|bg-opacity-|text-opacity-|border-opacity-|decoration-clone|overflow-ellipsis`). Per §3a, zero matches expected. Rename any that appear.

- [ ] **Step 4: Rebuild**

```powershell
npm run build:css
```

There's no direct `/handlers/403` route. Manual smoke: temporarily wrap any non-essential admin route in `app.py` to `raise PermissionDenied()`, hit it as a logged-in user, screenshot at 375/1280. Revert the change immediately.

- [ ] **Step 5: Surface diff (no commit)**

---

## Task 14: Migrate `templates/handlers/404.html` (Tier 2)

**Files:**
- Modify: `templates/handlers/404.html`

- [ ] **Step 1: Replace `<head>`**

Replace the existing top-of-file block:

```jinja
<!DOCTYPE html>
<html lang="{{ get_locale }}">
<head>
    <meta charset="UTF-8">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <title>404 - nexora</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
    <link rel="icon" type="image/x-icon" href="{{ url_for('static',filename='images/favicon.ico') }}">
</head>
```

with:

```jinja
{% set page_title = "404 - nexora" %}
<!doctype html>
<html lang="{{ get_locale }}">
{% include '_auth_head.html' %}
```

- [ ] **Step 2: Fix the "Go back" button (invalid HTML, broken a11y)**

The existing template has:

```html
<button class="...">
    <svg>...</svg>
    <span><a href="javascript:window.history.back();">Go back</a></span>
</button>
```

A `<a>` nested inside a `<button>` is invalid HTML and confuses assistive tech. Replace with a single button:

```html
<button type="button" onclick="window.history.back()"
        class="flex items-center justify-center w-1/2 px-5 py-2 text-sm text-gray-700 transition-colors duration-200 bg-white border rounded-lg gap-x-2 sm:w-auto hover:bg-gray-100 min-h-[44px]">
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5 rtl:rotate-180" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M6.75 15.75L3 12m0 0l3.75-3.75M3 12h18" />
    </svg>
    <span>{{ _("Go back") }}</span>
</button>
```

Also wrap the "Take me home" anchor with `min-h-[44px] flex items-center justify-center` on the inner button so tap-target is ≥ 44px.

- [ ] **Step 3: Utility audit**

Grep for v3-only utility classes. Zero matches expected.

- [ ] **Step 4: Rebuild + axe**

```powershell
npm run build:css
npm run test:a11y -- --grep "a11y: 404"
```

Expected: PASS (the test hits `/__definitely_not_a_real_page__`).

- [ ] **Step 5: Surface diff (no commit)**

---

## Task 15: Migrate `templates/handlers/500.html` (Tier 2)

**Files:**
- Modify: `templates/handlers/500.html`

- [ ] **Step 1: Read the current file**

Read `templates/handlers/500.html` in full.

- [ ] **Step 2: Replace `<head>` (same recipe as Tasks 13–14)**

Replace the existing `<!doctype>` / `<html>` / `<head>...</head>` with:

```jinja
{% set page_title = "500 - nexora" %}
<!doctype html>
<html lang="{{ get_locale }}">
{% include '_auth_head.html' %}
```

- [ ] **Step 3: Utility audit**

Grep this file for v3-only utility classes. Zero matches expected per §3a.

- [ ] **Step 4: Rebuild**

```powershell
npm run build:css
```

No direct route to axe-scan. Manual smoke: temporarily add to `app.py`:

```python
@app.route('/dev/500')
def dev_500():
    if os.environ.get("ENVIRONMENT") != "INT":
        abort(404)
    raise RuntimeError("test")
```

Hit it, screenshot at 375/1280, then remove that route before completing the task.

- [ ] **Step 5: Surface diff (no commit)**

---

## Task 16: Migrate `templates/nexoraLogo/_nexoraLogo.html`

**Files:**
- Modify: `templates/nexoraLogo/_nexoraLogo.html`
- Possibly modify: `static/css/_nexoraLogo.css` (if it tag-couples selectors)

This partial is included by every one of the 11 templates and by `_header.html`. It currently loads its own `cdn.tailwindcss.com` script AND wraps itself in a full `<!doctype html><html><head><body>` block — which is wrong, because Jinja `{% include %}` drops that content inside the consuming page's `<body>`. Browsers tolerate the nested document, but it's invalid.

- [ ] **Step 1: Check the CSS for tag-coupled selectors**

Read `static/css/_nexoraLogo.css`. Search for `h1.nexora-title` and `h2.nexora-subtitle`. If selectors are tag-coupled, the CSS will need updating too. If they're class-only (`.nexora-title`), the CSS stays.

- [ ] **Step 2: Rewrite the partial as a fragment**

Replace the entire file content with:

```jinja
{# Brand mark — included inside an existing <body>. Provides the
   "black hole" logo + "nexora" wordmark. Styles in
   static/css/_nexoraLogo.css. Tailwind utilities resolve via the
   parent page's compiled tailwind.css. #}
<a href="{{ url_for('index') }}" class="brand title-wrap flex items-center gap-3" aria-label="nexora">
  <div class="bh" aria-hidden="true">
    <div class="bh-penumbra" aria-hidden="true"></div>
    <div class="bh-core"></div>
    <div class="bh-einstein-ring"></div>
    <div class="bh-disk"></div>
    <div class="bh-sparks" aria-hidden="true">
      <i></i><i></i>
    </div>
  </div>
  <div class="flex flex-col items-start">
    <span class="nexora-title text-3xl font-semibold tracking-tight">nexora</span>
    <span class="nexora-subtitle text-xs font-semibold tracking-tight mt-1">powered by sydoc</span>
  </div>
</a>
```

Changes vs. original:
- Drops the surrounding `<!doctype>` / `<html>` / `<head>` / `<body>` (this is a fragment, not a document).
- Drops the `cdn.tailwindcss.com` script.
- Converts `<h1>` and `<h2>` to `<span>` — the wordmark is decorative, not a heading. The pages including this partial already have their own real `<h1>`.

- [ ] **Step 3: If Step 1 found tag-coupled selectors, update the CSS**

In `static/css/_nexoraLogo.css`, replace any `h1.nexora-title` with `.nexora-title` and any `h2.nexora-subtitle` with `.nexora-subtitle`.

- [ ] **Step 4: Rebuild + visual smoke across includes**

```powershell
npm run build:css
```

Check the logo on `/login`, `/forgot_password`, `/hero`, **and** `/dashboard` (which uses `_header.html` that also includes this partial). All four must still render the logo identically.

- [ ] **Step 5: Surface diff (no commit)**

---

## Task 17: Full a11y sweep + visual smoke screenshots

**Files:**
- Create: `screenshots/phase2/` directory
- Test: `npm run test:a11y` (all of `tests/a11y/auth.spec.js`)
- Possibly create + delete: a temporary smoke-screenshot spec file

- [ ] **Step 1: Run the full auth test suite**

```powershell
pwsh -File nx.ps1 -u  # one terminal
npm run test:a11y -- tests/a11y/auth.spec.js  # another
```

Expected: every test passes on both `chromium-desktop` and `chromium-mobile`. If anything fails, fix the offending template before continuing.

- [ ] **Step 2: Generate visual smoke screenshots**

Write a temporary spec at `tests/a11y/_smoke/phase2-screens.spec.js`:

```js
const { test } = require('@playwright/test');
const { mintResetToken } = require('../_helpers/mint-reset-token');

const TEST_USER = process.env.NX_A11Y_USER || 'ben.streich';
const VIEWPORTS = [
  { name: '375',  w: 375,  h: 812 },
  { name: '768',  w: 768,  h: 1024 },
  { name: '1280', w: 1280, h: 800 },
];
const PAGES = [
  { path: '/login',           name: 'login' },
  { path: '/forgot_password', name: 'forgot_password' },
  { path: '/hero',            name: 'hero' },
  { path: '/maintenance',     name: 'maintenance' },
  { path: '/__nope__',        name: '404' },
];

for (const vp of VIEWPORTS) {
  for (const p of PAGES) {
    test(`screenshot light: ${p.name} @ ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.w, height: vp.h });
      await page.goto(p.path);
      await page.screenshot({ path: `screenshots/phase2/${p.name}-${vp.name}.png`, fullPage: true });
    });
    test(`screenshot dark: ${p.name} @ ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.w, height: vp.h });
      await page.goto(p.path);
      await page.evaluate(() => document.documentElement.classList.add('dark'));
      await page.screenshot({ path: `screenshots/phase2/${p.name}-${vp.name}-dark.png`, fullPage: true });
    });
  }
}

for (const vp of VIEWPORTS) {
  test(`screenshot: reset_pages @ ${vp.name}`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width: vp.w, height: vp.h });
    const { init_reset_url, set_new_password_url } = await mintResetToken(baseURL, TEST_USER);
    await page.goto(init_reset_url);
    await page.screenshot({ path: `screenshots/phase2/init_reset-${vp.name}.png`, fullPage: true });
    await page.goto(set_new_password_url);
    await page.screenshot({ path: `screenshots/phase2/set_new_password-${vp.name}.png`, fullPage: true });
  });
}
```

Run: `npm run test:a11y -- tests/a11y/_smoke/phase2-screens.spec.js`
Expected: all "tests" pass; screenshots land in `screenshots/phase2/`.

- [ ] **Step 3: Human review**

Browse `screenshots/phase2/`, visually confirm all 11 templates look acceptable at 375/768/1280 in both light and dark. Flag any regressions to the user.

- [ ] **Step 4: Delete the temporary smoke spec**

```powershell
Remove-Item -LiteralPath "tests/a11y/_smoke/phase2-screens.spec.js"
Remove-Item -LiteralPath "tests/a11y/_smoke" -Recurse  # if empty
```

(Keep the screenshots — they're the artifact.)

- [ ] **Step 5: Surface diff (no commit)**

Show the user the list of screenshot files and the test output.

---

## Task 18: pybabel — extract / update / compile new strings

**Files:**
- Modify: `messages.pot`
- Modify: `translations/de/LC_MESSAGES/messages.po`
- Modify: `translations/fr/LC_MESSAGES/messages.po`
- Modify: `translations/it/LC_MESSAGES/messages.po`
- Regenerate: corresponding `.mo` files

- [ ] **Step 1: Extract**

```powershell
pybabel extract -F babel.cfg -o messages.pot .
```

Expected: writes `messages.pot`. Likely new keys:
- `Go back` (from 404 button rewrite in Task 14)
- `2FA QR Code` (from Task 9 — the `alt` attribute)
- `6-digit code` (from Task 10 — the sr-only label)

Existing keys reused should not appear as new.

- [ ] **Step 2: Update each locale**

```powershell
pybabel update -i messages.pot -d translations
```

- [ ] **Step 3: Translate new keys**

Open each of `translations/{de,fr,it}/LC_MESSAGES/messages.po` and fill in translations. Use existing translations as a style guide. Suggested for the new keys:

| Key | de | fr | it |
| --- | --- | --- | --- |
| `Go back` | `Zurück` | `Retour` | `Indietro` |
| `2FA QR Code` | `2FA QR-Code` | `Code QR 2FA` | `Codice QR 2FA` |
| `6-digit code` | `6-stelliger Code` | `Code à 6 chiffres` | `Codice a 6 cifre` |

Remove any `#, fuzzy` markers from entries you've translated.

- [ ] **Step 4: Compile**

```powershell
pybabel compile -d translations
```

Expected: `.mo` files regenerate without errors.

- [ ] **Step 5: Smoke test each locale**

Start nexora, log out, visit `/login` in each language. Verify no raw `{{ _('...') }}` strings or English fallback for the new keys.

- [ ] **Step 6: Surface diff (no commit)**

---

## Task 19: Delete dead CSS + update CI gate + howtocss.txt

**Files:**
- Delete: `static/css/index.css`
- Delete: `static/css/forgot_password.css`
- Delete: `static/css/reset_password.css`
- Modify: `howtocss.txt`
- Modify: `.github/workflows/deploy.yml`

- [ ] **Step 1: Verify the CSS files are no longer referenced**

Use the Grep tool on the entire `templates/` tree for `index.css`, `forgot_password.css`, `reset_password.css`. Expected: zero matches after Tasks 5–8 were applied.

- [ ] **Step 2: Delete the files**

```powershell
Remove-Item -LiteralPath "static/css/index.css"
Remove-Item -LiteralPath "static/css/forgot_password.css"
Remove-Item -LiteralPath "static/css/reset_password.css"
```

Keep `static/css/hero.css`, `static/css/_nexoraLogo.css`, `static/css/maintenance.css`, and any other still-referenced files.

- [ ] **Step 3: Add CDN-grep CI gate to deploy.yml**

Edit `.github/workflows/deploy.yml`. After the existing "CSS sync check" step, add:

```yaml
      - name: Reject Tailwind v3 CDN in templates
        run: |
          set -e
          BAD=$(grep -rl "cdn.tailwindcss.com" templates/ || true)
          if [ -n "$BAD" ]; then
            echo "::error::Tailwind v3 CDN found in:"
            echo "$BAD"
            exit 1
          fi
```

This gate ensures no future commit re-introduces the v3 CDN.

- [ ] **Step 4: Append to howtocss.txt**

Add at the bottom of `howtocss.txt`:

```
PHASE 2 AUTH/CHROME TEMPLATES
  - All standalone (unauth) pages use templates/_auth_head.html
    instead of a per-page <head>. Each consuming page does:
        {% set page_title = _("...") %}
        {% set extra_css_files = ['css/foo.css'] %}  -- optional
        <!doctype html>
        <html lang="{{ get_locale }}">
        {% include '_auth_head.html' %}
        <body>...</body>
        </html>
  - cdn.tailwindcss.com is no longer permitted anywhere. The CI gate
    in deploy.yml will reject any PR that re-adds it.
  - Dark-mode tokens live in src/main.css under @layer base html.dark.
    Adding the .dark class to <html> triggers them; the /login theme
    toggle already does this.
  - INT-only helper /dev/mint_reset_token/<username> mints a reset
    token for a11y testing. Returns 404 in PROD.
```

- [ ] **Step 5: Final rebuild + full regression sweep**

```powershell
npm run build:css
npm run test:a11y -- tests/a11y/auth.spec.js
npm run test:a11y -- tests/a11y/header.spec.js
npm run test:a11y -- tests/a11y/design-system.spec.js
```

Expected: all green.

- [ ] **Step 6: Surface diff (no commit)**

Final state: 11 templates migrated, 1 partial fixed, 1 shared head added, 1 dev route added, 1 CI gate added, 3 dead CSS files deleted. Phase 2 ready for the user's git workflow.

---

## Acceptance checklist (run before declaring Phase 2 done)

- [ ] `grep -rl "cdn.tailwindcss.com" templates/` returns nothing.
- [ ] `grep -rl "<style" templates/index.html templates/forgot_password.html templates/reset_password.html templates/init_reset.html templates/init_2FA.html templates/verify_2fa.html templates/hero.html templates/handlers/` returns nothing. (maintenance.html may be excepted only if Task 12 externalization was reverted.)
- [ ] `npm run test:a11y` exits with code 0 on both `chromium-desktop` and `chromium-mobile`.
- [ ] `static/css/tailwind.css` rebuilt and reflects the dark-mode tokens.
- [ ] All 11 templates render correctly in light + dark + each of {en, de, fr, it}.
- [ ] No tier-1 button or interactive control is < 44 × 44px at 375 viewport.
- [ ] `pybabel extract -F babel.cfg -o messages.pot .` produces no surprising diff after Task 18.
