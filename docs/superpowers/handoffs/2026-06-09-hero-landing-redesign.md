# Handoff — Public landing (hero) page redesign + auth/2FA brand consistency (NOT pushed)

- **Date:** 2026-06-09
- **Branch:** `feature/2.5.63`. Git mode this session: **commit-only (remote session)** —
  **nothing was pushed.** Owner pushes + opens the PR.
- **How the work landed:** built on an isolated worktree branch `feature/2.5.63-hero-ui`
  (worktree at `C:\dev\nexora.wt\hero-ui`), then **merged into `feature/2.5.63`** locally.
- **Feature commits (this session, all local-only):**
  - `344c2ab` feat(ui): bring hero landing + 2FA pages onto nexora-ui design
  - `10bdc3d` feat(ui): bolder full-bleed gradient hero band
  - `302ddb0` feat(ui): redesign hero into a dark enterprise "Trust & Authority" fold
  - `a8b9bff` feat(ui): make the enterprise hero light by default + token-based
  - `bd0986c` feat(ui): smooth the landing flow into one continuous wash
  - `07cc185` feat(ui): trim hero to core sections + blend the footer
  - `d0385c7` fix(ui): drop the redundant hero Sign In button
  - `8a25993` Merge feature/2.5.63-hero-ui into feature/2.5.63
  - This handoff commit is the latest (also local-only).
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-09-reporting-ai-table-source-coercion-handoff.md`

## TL;DR

- The user asked to extend the recent `nexora-ui` redesign to the **starting pages**. The
  login + forgot/reset/init-reset pages were **already** on `nexora-ui`; the real gaps were
  the public **`hero.html`** landing page and the two **2FA** pages (still off-brand blue).
- The hero went through several iterations (gradient → dark enterprise → **light**) guided by
  the `ui-ux-pro-max` skill, which flags a full-bleed purple wash as a generic-AI
  anti-pattern. **Final = a light, token-based "Trust & Authority" hero**: eyebrow status
  pill, single primary CTA, trust-signal row, and a product-window mock of the document
  status card. It's built entirely on `--nx-*` tokens so it follows the app's `html.dark`
  automatically (**light by default, dark = user preference**).
- Per user feedback the page was also **smoothed** (one continuous wash instead of stacked
  colour bands) and **trimmed** ("Getting Started" + "FAQ" sections removed), the footer was
  blended into the wash, and a redundant duplicate "Sign In" CTA was dropped.
- 2FA pages + the shared footer were brought onto the brand. Everything is **presentational**
  — no routes/permissions/DB/i18n msgids changed (all copy reuses existing strings).

## What shipped (this session)

### Hero / landing — `templates/hero.html` + `static/css/hero.css`
| Area | Change |
|------|--------|
| Hero fold | Light "Trust & Authority" layout: `.hero-band` (light surface + restrained indigo→violet aurora + faint masked grid), `.hero-eyebrow` status pill (live pulse dot), white-card `.hero-window` product mock (traffic-light chrome + status bars), `.hero-trust` signal row, single `.hero-cta` primary button. Dark glass→**light** header (`.hero-header`). |
| Page flow | Removed the alternating white/tint **section bands** — all sections + closing CTA + footer now flow on **one continuous light wash** (`body.hero-body` multi-radial). Closing CTA is a soft glow (`.hero-band-cta`), not a slab. |
| Trimmed | **Removed** the "Getting Started is Easy" and "Frequently Asked Questions" sections. Page is now hero → "Visualize Your Document's Journey" → "Why use nexora?" → CTA → footer. |
| Tokens | `hero.css` rewritten onto `--nx-*` tokens (dark-ready). Dead CSS removed (`.hero-hero*`/`.hero-glass*`, `.hero-band-grad/-white/-tint`, `.hero-signin`, `.hero-cta-inverse`, `.hero-step-num`, `.hero-faq-item`, `.faq-*`, blob keyframes). |
| JS | `templates/js/_hero_js.html`: removed the now-dead FAQ accordion handler. Preloader logo-flight + the process-step animation hooks are **unchanged**. |

### Auth / 2FA + shared footer
| File | Change |
|------|--------|
| `templates/init_2FA.html` | off-brand `bg-blue-600` button → `bg-gradient-primary`; `rounded-lg shadow-md` card → `rounded-xl shadow-2xl`; focus ring blue→indigo. |
| `templates/verify_2fa.html` | blue shield badge → gradient chip; blue button → `bg-gradient-primary`; branded card + focus. |
| `templates/_small_footer.html` | link hover `text-blue-500` → `text-indigo-600`; removed `bg-white` so it blends into the page wash with a hairline top border. **Shared partial** — affects all pre-login pages (login/forgot/reset/2FA), consistently. |

### Tests / docs
| File | Change |
|------|--------|
| `tests/e2e/test_misc_pages.py` | removed `test_hero_faq_accordion_toggles` (FAQ section deleted) + the now-unused `import re`. `test_hero_renders_anonymous` + `test_hero_access_portal_navigates_to_login` still cover the hero. |
| `CHANGELOG.md` | `[Unreleased] → Changed` entry describing the hero + 2FA + footer work (auto-merged cleanly with the reporting entries). |

## Owner actions / next steps

1. **Run it live to confirm:** `nx -u` from `C:\dev\nexora` (a restart is required — Jinja
   caches templates for the process lifetime), then open `/` (the landing page renders for
   anonymous users). Also eyeball `/login`, `/init_2FA`, `/verify_2fa`.
2. **(Optional) squash** the 7 hero commits before pushing: `git rebase -i b70e09c` on
   `feature/2.5.63` — or leave the merge as-is.
3. **Push + PR:** `git push` then open `feature/2.5.63` → `main`. (Not done here — remote
   session is commit-only.)
4. **Remove the worktree when satisfied:**
   `git worktree remove C:\dev\nexora.wt\hero-ui` then
   `git branch -d feature/2.5.63-hero-ui`. (The worktree still holds a copied, gitignored
   `env/INT.env` with live secrets + a dev-only render harness under `var/_preview/` — both
   go away with the worktree.)

## Gotchas & notes

- **Light by default, dark via tokens.** The hero is fully `--nx-*`-token-based, so it flips
  to dark wherever the app sets `html.dark`. The public page has no dark toggle, so in
  practice it renders light. This was an explicit user requirement ("dark should be a user
  preference, not forced").
- **No new i18n strings.** Every label reuses an existing msgid (e.g. the trust pills reuse
  "Real-time tracking" / "Document history" / "Secure access"; the eyebrow reuses
  "Real-time updates"). So `messages.pot` / de-fr-it were untouched and the translation suite
  stays green. Keep it that way if you tweak copy, or run `/nx-i18n`.
- **Verification was done via standalone Jinja renders + Playwright**, not the live server:
  the worktree session couldn't read the main checkout's gitignored `env/INT.env` (Claude
  Code file-access guard), so a tiny render harness (`var/_preview/render_preview.py`, served
  over `python -m http.server`) rendered the real templates+CSS and screenshots went to
  `C:\dev\nexora.wt\hero-ui\var\screenshots\` (gitignored). The renders use the real
  templates, so the live app matches.
- **Commits used `SQL_SYNC_SKIP=1`** (the known INT SchemaMigrations CRLF drift, see
  `project_int_migration_crlf_drift`). The `mixed-line-ending` pre-commit hook converted
  CRLF→LF on edited templates a couple of times → re-`add` + re-commit (handled inline).
- **gitlint:** subject ≤72, body mandatory, body lines ≤100, no em-dashes in the subject
  (one commit had to be retried after an em-dash pushed the title to 73 chars).
- The merge into `feature/2.5.63` was a **real merge** (a background process had advanced the
  branch to `b70e09c` mid-session); `CHANGELOG.md` was the only overlapping file and git
  **auto-merged** it with no conflict.

## How to verify

```powershell
# from C:\dev\nexora on feature/2.5.63
git log --oneline -9
# live (restart picks up the new templates):
nx -u
#   -> open http://<dev-host>/  (landing page, anonymous) and /login, /init_2FA, /verify_2fa
# the standalone screenshots from this session (if you want a quick look without a server):
#   C:\dev\nexora.wt\hero-ui\var\screenshots\hero-v7-desktop.png (final), *-mobile.png, login/2fa
```

## Resuming in a fresh session

The landing-page + auth/2FA redesign is **complete and committed (local-only) on
`feature/2.5.63`** (merge `8a25993`). Realistic next moves: (1) owner runs `nx -u` to eyeball
it live, optionally squashes, then **pushes + opens the PR → `main`**; (2) remove the
`feature/2.5.63-hero-ui` worktree/branch. If more landing tweaks are wanted, the work is in
`templates/hero.html` + `static/css/hero.css` (all `--nx-*`-token-driven). Memory pointers:
`project_nexora_ui_design_system`, `feedback_caveman_speak`, `project_branch_consolidation_2_5_63`.
