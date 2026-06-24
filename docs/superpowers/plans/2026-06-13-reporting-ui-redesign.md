# Reporting UI Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/reporting` look like the rest of the app. Reskin the whole page (Simple tab + Advanced tab + wizard + result views + AI bars + four modals) onto the existing nexora-ui design system (`--nx-*` tokens, `.nx-btn/.nx-card/.nx-input/.nx-select/.nx-table/.nx-tabs/.nx-empty`), plus light layout tidying of the obviously-messy regions (Advanced toolbar/export bar, AI bars, modals, spacing/alignment). **Zero feature changes, zero new behavior, zero information-architecture rethink.** Visual consistency only.

**Architecture:** The page is already ~70% migrated. `templates/reporting.html` already uses shared chrome (`body.nx-app`, `_header.html`, `.nx-page-head`, `.nx-tabs`, `.nx-empty`, the SQL-view `.nx-card`), and `static/css/reporting.css` ends with two appended override blocks (`nexora-ui HARMONIZATION` + `REDESIGN — layout, density & structure`) that, because they are **unlayered and appended-last, win the cascade** and already remap most `.reporting-*` classes onto `--nx-*` tokens. CRITICAL CONSEQUENCE: the early rules near the top of the file (the literal-hex `.reporting-modal-box`, `.reporting-btn-primary`, `.reporting-view-toggle button.active`, `.reporting-pivot-zone`, `.reporting-input`, etc.) are **dead in the cascade** — editing them is a visual no-op. The genuinely-residual hex that still WINS is the **Simple-pane block** (the `.reporting-simple-*` / `.reporting-chartbtn` / `.reporting-sqlview` / `.rs-chip` rules, which sit AFTER the appended blocks and so are the cascade winners). This plan: (1) token-izes that residual Simple-pane hex (the real dark-mode fix); (2) co-applies real `.nx-*` classes on the few controls where the nx component genuinely adds treatment the bespoke rule lacks (buttons — `nx-btn--ghost`/`--sm` variants); (3) does light layout tidy of the messy toolbar/modal regions only where a defect actually survives. **No backend edits** — `nx_lib/views/reporting.py def reporting()` only passes feature flags (`ai_enabled`, `ai_sql_enabled`, `ai_explain_enabled`) and emits no class names.

**Tech Stack:** Flask + Jinja2 templates, plain ES5 IIFE JS partials, Tailwind v4 (CDN, `@layer utilities`) layered over the **unlayered** `nexora-ui.css` design system, Playwright for visual verification. CSS-only + markup-only change set. No new dependency, no SQL, no migration.

## Context an engineer needs (read first)

- **Branch:** work on `feature/2.5.63` (already checked out). Do **not** branch off `main`; do **not** touch `main`.
- **Read the precedent first:** `docs/superpowers/plans/2026-06-11-admin-nexora-ui-integration.md` is the exact shape of this work (migrate a bespoke page onto nexora-ui) and documents the Tailwind-v4 layer trap. Read it before styling anything.
- **The cascade is the whole game.** `static/css/reporting.css` loads AFTER `nexora-ui.css` (`_header.html` loads `nexora-ui.css`; `reporting.html` loads `reporting.css` later in the page). Both stylesheets are **unlayered**; Tailwind utilities are in `@layer utilities`. So: (a) unlayered `.reporting-*` rules always beat layered Tailwind utilities; (b) within `reporting.css`, later rules beat earlier ones at equal specificity. The file has the SAME selector defined twice in many cases — once early on literal hex, once in an appended block on tokens — and **the appended (later) one wins.** Before editing ANY rule, confirm it is the cascade winner (search the whole file for the selector; the LAST definition wins). Editing a dead early rule is a no-op and wastes a task.
- **The hard contract — NEVER rename a `.reporting-*` class.** There are **nine** reporting JS partials: `templates/js/_reporting_js.html`, `_reporting_viz_js.html`, `_reporting_simple_js.html`, `_reporting_ai_js.html`, `_reporting_anim_js.html`, `_reporting_tabs_js.html`, `_reporting_sqlformat_js.html`, `_reporting_metrics_js.html`, `_reporting_sources_js.html`. They *inject DOM carrying `.reporting-*` className strings* and *querySelector by those classes*. `_reporting_metrics_js.html` / `_reporting_sources_js.html` drive the SEPARATE sources/metrics admin pages and inject `.reporting-admin*` / `.reporting-input` DOM (see shared-surface note below). Class names are a contract shared by page markup + 9 JS partials + the e2e suite. The safe move is **restyle in place** (edit the winning CSS rule) or **co-apply** both classes on one element (`class="reporting-btn nx-btn nx-btn--secondary"`). If you ever must drop a class you edit the JS site AND any e2e selector in the SAME task — this plan avoids that entirely.
- **`.reporting-admin*` is a SHARED surface.** The classes `reporting-admin-grid` / `reporting-admin-cols` / `reporting-admin*` are used BOTH in the reporting schedule modal (`templates/reporting.html`) AND in the separate admin pages `templates/reporting_metrics.html` / `templates/reporting_sources.html` (injected by `_reporting_metrics_js.html` / `_reporting_sources_js.html`). **Never edit a `.reporting-admin*` CSS rule** in this plan — a change would regress two other pages. Co-applying `.nx-*` on the schedule-modal markup is fine (it doesn't touch those CSS rules). After ANY `reporting.css` edit, screenshot both admin pages to prove no regression (Task 9).
- **Preserve every `data-testid`, `id`, and `name`.** The reporting e2e suite (11 files: `test_reporting.py`, `test_reporting_simple.py`, `test_reporting_viz.py`, `test_reporting_sql.py`, `test_reporting_save.py`, `test_reporting_load.py`, `test_reporting_share.py`, `test_reporting_schedule.py`, `test_reporting_metrics.py`, `test_reporting_curated.py`, `test_reporting_sources.py`) selects almost entirely by `data-testid` and element `id`, plus a handful of CSS classes (`button.reporting-simple-choice`, `.reporting-simple-choice.is-selected`, `p.reporting-simple-empty`, `.reporting-truncated-note`, `.reporting-error`, `.reporting-pivot-*`, `is-selected`, `active`) and the SQL-token spans (`.sql-kw/.sql-ident/.sql-string/.sql-param/.sql-number/.sql-comment`). Keep all of them on the same logical element. **Do NOT change the chart-note text `"Too many data points to chart"`** — `test_reporting_simple.py` asserts that exact string. **Do NOT touch the `.sql-*` token colors** (lines defining `.sql-kw{color:#cf222e}` etc.) — they are intentional GitHub-style syntax colors and e2e asserts on the spans.
- **Anchor every Edit on a UNIQUE QUOTED SNIPPET — never line numbers.** Several other reporting plans touch these same files (merge-order rule below); line numbers will drift. Where a selector appears twice (early-hex + appended-token), quote enough surrounding text (the declaration body) to target the RIGHT one — and you almost always want the appended (winning) one or the residual Simple-pane one, never the dead early rule.
- **Jinja template-cache restart:** templates are cached for the process lifetime. After any edit to `reporting.html` / `_reporting_simple.html` / a JS partial, **restart the dev server** before browser-verifying (`nx -u -b --loginas:ben.streich`) or you screenshot stale HTML. CSS-only edits to `reporting.css` do NOT need a template restart, but do a hard browser reload (cache-bust). e2e runs its own fresh server, so it is unaffected.
- **e2e constraint:** the TEST environment has **no Statistics DB**, so data-driven reporting e2e skip or use seeded fixtures. This reskin doesn't change data flow, so that's unaffected. Always run `python scripts/test_db_reset.py` before any e2e run (stale `NEXORA_TEST` state, e.g. `ReportingSqlAck`, fails order-dependent tests). The push-time gate runs the FULL suite — but this is a remote session, so we stop at commit.
- **Pre-commit escape hatch:** the `sql-migrate-int` / `sql-sync-check` hooks run on every commit and fail on the known INT `SchemaMigrations` CRLF drift even though this change has no SQL. Commit with the documented hatch. **Never `--no-verify`:**
  ```powershell
  $env:SQL_SYNC_SKIP="1"; git commit -m '<subject>' -m '<body>'; Remove-Item Env:SQL_SYNC_SKIP
  ```
- **i18n cycle (only if NEW strings):** a pure reskin adds **no** new visible strings — it re-flows existing `{{ _("...") }}` labels. **This plan introduces no new strings.** If a light-tidy step ever introduces a genuinely new visible literal, wrap it in `{{ _("...") }}` and run the full `/nx-i18n` cycle (`pybabel extract -F babel.cfg -o messages.pot .` → `pybabel update -i messages.pot -d translations` → translate de/fr/it → `pybabel compile -d translations`) or `test_translations.py` fails. Flag it loudly if a task ends up needing one.
- **Migrations needed: NO.** No schema/data/permission rows. No `sql/_migrations/` file, no `page_visibility()` / `require_permission` change. No new `<link>` (`nexora-ui.css` is already globally loaded by `_header.html` and `reporting.html` already has `<body class="nx-app">`). Edit `reporting.css` IN PLACE — do not create a new stylesheet (a new top-level file would need a `deploy.yml` `/XF` entry). No `deploy.yml` change; all edited files (`templates/`, `static/css/`) are already inside `robocopy /MIR`'d runtime dirs.
- **Sequencing vs in-flight reporting plans.** These touch the SAME files (not the same functions):
  - `docs/superpowers/plans/2026-06-13-reporting-two-breakdown-chart-cap.md` — **shipped** (commits `cbb9b41..10b313f`); no conflict.
  - `docs/superpowers/plans/2026-06-12-reporting-loading-states-sql-display.md` — **status UNVERIFIED in git history**; treat as potentially queued. Anchor every Simple-pane / SQL-view edit on a unique quoted snippet so it re-bases cleanly regardless of landing order. Do NOT assume it landed.
  - `docs/superpowers/plans/2026-06-11-reporting-drill-through.md` (Tasks 2–8 queued, Simple-heavy), `docs/superpowers/plans/2026-06-11-reporting-show-query-multidim-export.md` (Phase 2), `docs/superpowers/plans/2026-06-12-reporting-page-improvement-options.md` — **queued**; touch `reporting.html`, `reporting.css`, `_reporting_simple.html`, the JS partials.
  - **Merge-order rule:** whichever of these lands second re-anchors its edits on QUOTED SNIPPETS, never line numbers. This reskin stays CSS/markup-only and never touches `reporting.py`, keeping the conflict surface minimal.
- **Remote-session policy:** STOP at `git commit`. Do **not** push, do **not** open a PR (the owner reviews + pushes locally). Drive Playwright yourself and capture screenshots to `var/screenshots/` (light AND dark via the sidebar moon toggle, 1440px desktop + 375px mobile) — the user reviews UI work via those screenshots and can't see the screen. `SendUserFile` the before/after pairs.

### Decisions locked in

| Decision | Choice | Why |
|---|---|---|
| Rename `.reporting-*` → `.nx-*`? | **No.** Restyle in place / co-apply both classes. | Class names are a contract with 9 JS partials + e2e. |
| Edit which rule when a selector is defined twice? | **The cascade WINNER (the LAST/appended definition or residual Simple-pane rule).** Never the dead early-hex rule. | Editing an overridden early rule is a visual no-op. |
| New stylesheet vs edit in place? | **Edit `static/css/reporting.css` in place.** | New file needs a `deploy.yml` exclude; file is already shipped & globally token-mapped. |
| Co-apply `.nx-input`/`.nx-select` on inputs? | **No, except where it demonstrably changes the look.** `.reporting-input` is ALREADY tokenized in the appended block (background/border/radius on `--nx-*`) and WINS over `.nx-input` by source order, so co-applying is a near-no-op. Only co-apply on **buttons** (where `nx-btn--ghost`/`--sm`/`--primary`/`--secondary` add real variants the bespoke rule lacks). | Avoids churn + merge surface for zero visual gain (red-team F3/F9). |
| Token-ize residual hex? | **Yes — the Simple-pane / chartbtn / sqlview / rs-chip rules that WIN the cascade** (still on literal `#fff/#57606a/#eef2ff/#4338ca/#d0d7de/#6b7280/#e5e7eb`). | These are the genuine dark-mode defect and the "messy" cause. |
| Selected-chip / scope-badge fill token | **`--nx-accent-tint`** (`= #eef2ff` light / `#312e81` dark). Use `--nx-accent-soft` only for focus-ring/shadow. | Both tokens exist; `--nx-accent-tint` is the fill used elsewhere (e.g. pivot drop-hover). Resolves the A/B divergence. |
| Bogus fallback tokens (`--nx-surface-2`, `--nx-text-muted`, `--rp-border`)? | **Replace them** — none exist in `nexora-ui.css`, so the literal `#fallback` fires (wrong in dark mode). | `--nx-surface-2`→`--nx-accent-tint`, `--nx-text-muted`→`--nx-text-sec`, `--rp-border`→`--nx-border`. |
| Delete redundant override-block rules after co-apply? | **No bulk delete.** Only remove a rule if a per-selector before/after screenshot proves the element is pixel-identical without it. Default: keep `.reporting-*` rules. | Bulk de-dup risks removing a rule doing real layout work (red-team F9). |
| Backend / new strings / migration? | **None.** | Route emits no class names; reskin re-flows existing `_()` labels; no schema. |
| Layout tidy (toolbar / result-bar) | **Conditional.** Only edit if a baseline screenshot shows a real misalignment after token-izing; otherwise skip (no manufactured churn). | Smallest safe diff (stance A discipline). |
| Phasing | **P0 baseline → P1 Simple-pane token fix (the real win, CSS-only) → P2 button co-apply (toolbar/AI/modals, markup) → P3 conditional layout tidy → P4 verify+changelog.** | Highest-value, lowest-risk CSS-only change first; markup (restart-needed) batched; conditional tidy last. |

---

# PHASE 0 — Baseline (capture before / prove green)

### Task 0: Baseline — green e2e + before screenshots

**Files:** none (read-only + screenshots to `var/screenshots/`).

- [ ] Confirm branch + clean tree: `git rev-parse --abbrev-ref HEAD` (expect `feature/2.5.63`), `git status`.
- [ ] Read the precedent: `docs/superpowers/plans/2026-06-11-admin-nexora-ui-integration.md`.
- [ ] Read the two appended override blocks in full so you don't fight the cascade: open `static/css/reporting.css` and read from the comment containing `nexora-ui HARMONIZATION` to end of file. Note which `.reporting-*` selectors are RE-DEFINED there (those early definitions are dead). Note the residual hex still in the Simple-pane block (`.reporting-simple-card`, `.reporting-simple-choice`, `.reporting-chartbtn`, `.reporting-sqlview pre`, `.rs-chip`, `.reporting-ai-loading`) — these WIN and are the real targets.
- [ ] Reset e2e state then run the full reporting suite GREEN as the baseline (record the pass count — this is the invariant):
  ```powershell
  python scripts/test_db_reset.py
  python -m pytest tests/e2e/test_reporting.py tests/e2e/test_reporting_simple.py tests/e2e/test_reporting_viz.py tests/e2e/test_reporting_sql.py tests/e2e/test_reporting_save.py tests/e2e/test_reporting_load.py tests/e2e/test_reporting_share.py tests/e2e/test_reporting_schedule.py tests/e2e/test_reporting_metrics.py tests/e2e/test_reporting_curated.py tests/e2e/test_reporting_sources.py -q
  ```
  If red, STOP and report; do not start a reskin on a broken baseline.
- [ ] Restart the dev server logged in: `nx -u -b --loginas:ben.streich`.
- [ ] Drive Playwright to `/reporting`. Capture BEFORE shots to `var/screenshots/` at 1440px and 375px, **light and dark** (toggle dark via the sidebar moon): Advanced tab (toolbar, field panel, wells, AI panel, SQL panel, empty state), Simple tab (library grid + a wizard step with a selected chip + a run result with stat/chart/table/chart-tools/show-query), each of the four modals open if reachable (`#rpSqlAck`, `#rpShareModal`, `#rpScheduleModal`, `#rpNameModal`). Name them `reporting-before-<surface>-<theme>-<width>.png`. Pay special attention to DARK mode — the residual-hex regions (Simple cards/chips/scope/chart-buttons) will show white-on-dark; those are the defects this plan fixes.
- [ ] `SendUserFile` the before shots so the owner has a baseline.

_No commit (baseline only)._

---

# PHASE 1 — Token-ize the residual Simple-pane hex (the real dark-mode fix; CSS only, zero template/JS risk)

This is the highest-value, lowest-risk change: it edits only `static/css/reporting.css`, touches no markup, no JS, no `data-testid`, needs no template-cache restart. These rules are the cascade WINNERS still on literal hex, so they genuinely render wrong in dark mode and look "messy". Each edit is anchored on a unique quoted declaration. Keep all layout/sizing; change only color/background/border tokens. Do NOT rename any class.

### Task 1: Token-ize Simple-pane library cards, headings, empty & choice chips

**Files:** `static/css/reporting.css`

- [ ] Edit `.reporting-simple-h` — anchor on the declaration `color: #57606a; text-transform: uppercase;` and change `color: #57606a` → `color: var(--nx-text-sec)`.
- [ ] Edit `.reporting-simple-card` — anchor on `border: 1px solid var(--nx-border, #d0d7de); border-radius: 8px; padding: 12px 14px; background: #fff; font-family: inherit;` → change `border: 1px solid var(--nx-border, #d0d7de)` to `border: 1px solid var(--nx-border)`, change `background: #fff` to `background: var(--nx-card)`, and add `color: var(--nx-text);` to the rule.
- [ ] Edit `.reporting-simple-card:hover` — anchor on `border-color: var(--nx-accent, #4f46e5); box-shadow: 0 2px 8px rgba(79,70,229,.12);` → `border-color: var(--nx-accent); box-shadow: 0 2px 8px var(--nx-accent-soft);`.
- [ ] Edit `.reporting-simple-card .rs-card-meta` — anchor on `font-size: 12px; color: #57606a; margin: 0;` → change `color: #57606a` to `color: var(--nx-text-meta)`.
- [ ] Edit `.reporting-simple-empty` — anchor on `font-size: 13px; color: #57606a; padding: 8px 0 4px;` → change `color: #57606a` to `color: var(--nx-text-sec)`.
- [ ] Edit `.reporting-simple-choice` — anchor on `border: 1px solid var(--nx-border, #d0d7de); border-radius: 999px; background: #fff; padding: 7px 14px;` → change the border fallback to `border: 1px solid var(--nx-border)`, `background: #fff` to `background: var(--nx-card)`, and add `color: var(--nx-text);`.
- [ ] Edit `.reporting-simple-choice.is-selected` — anchor on `border-color: var(--nx-accent, #4f46e5); background: #eef2ff; font-weight: 600;` → `border-color: var(--nx-accent); background: var(--nx-accent-tint); font-weight: 600;`.
- [ ] CSS-only: hard-reload `/reporting` (no Jinja restart). Open the Simple tab in light AND dark; confirm library cards and wizard choice chips are now dark-surface in dark mode and the selected chip shows the indigo tint. Screenshot `var/screenshots/reporting-after-simple-cards-<light|dark>-1440.png`.
- [ ] Confirm `data-testid`s still resolve (no element touched): in the Playwright console assert `rs-new-report`, `rs-measure-list`, `rs-breakdown-list`, `rs-time-list`, `reporting-simple` exist; assert `button.reporting-simple-choice` and `.reporting-simple-choice.is-selected` still match (e2e selectors).
- [ ] Commit:
  ```powershell
  $env:SQL_SYNC_SKIP="1"; git commit -m 'style(reporting): tokenize Simple library cards + choice chips' -m 'Replace the residual literal hex in the cascade-winning Simple-pane rules
  for the library cards, section heading, empty state and wizard choice chips
  (#fff/#57606a/#d0d7de/#4f46e5/#eef2ff plus the rgba hover shadow) with --nx-*
  tokens (card/text-sec/text-meta/accent/accent-tint/accent-soft) so the Simple
  tab renders correctly in dark mode and matches the design system. CSS only;
  class names, ids and data-testids unchanged.

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'; Remove-Item Env:SQL_SYNC_SKIP
  ```

### Task 2: Token-ize Simple-pane scope panel, inline label, chart note & chart buttons

**Files:** `static/css/reporting.css`

- [ ] Edit `.reporting-simple-inline` — anchor on `gap: 8px; margin-top: 12px; font-size: 13px; font-weight: 600; color: #555;` → change `color: #555` to `color: var(--nx-text-sec)`.
- [ ] Edit `.reporting-simple-scope` — anchor on `margin-top: 14px; font-size: 14px; border: 1px solid #d1d5db; border-radius: 8px; background: #fff; max-width: 520px;` → change `border: 1px solid #d1d5db` to `border: 1px solid var(--nx-border)` and `background: #fff` to `background: var(--nx-card)`.
- [ ] Edit `.reporting-simple-scope-badge` — anchor on `font-size: 12px; background: #eef2ff; color: #4338ca; border-radius: 999px;` → `background: var(--nx-accent-tint); color: var(--nx-accent);`.
- [ ] Edit `.reporting-simple-chartnote` — anchor on `font-size: 13px; color: #6b7280; margin: 0 0 8px;` → change `color: #6b7280` to `color: var(--nx-text-meta)`.
- [ ] Edit `.reporting-chartbtn` — anchor on `border: 1px solid #e5e7eb; background: #fff; border-radius: 6px; padding: 4px 8px; font-size: 12px; color: #6b7280; cursor: pointer;` → `border: 1px solid var(--nx-border); background: var(--nx-card); border-radius: 6px; padding: 4px 8px; font-size: 12px; color: var(--nx-text-meta); cursor: pointer;`.
- [ ] Edit `.reporting-chartbtn.is-selected` — anchor on `border-color: #4f46e5; color: #4f46e5; background: #eef2ff;` → `border-color: var(--nx-accent); color: var(--nx-accent); background: var(--nx-accent-tint);`.
- [ ] CSS-only: hard-reload. Run a Simple report (or open a saved one) and exercise the scope `<details>` and the chart-tool buttons (`rs-chart-bar/line/pie/stacked/png`) in light AND dark; confirm a selected chart button shows the accent tint. Screenshot `var/screenshots/reporting-after-simple-scope-chart-<light|dark>-1440.png` and a `375` mobile shot.
- [ ] Confirm `rs-stat-card`, `rs-chart-card`, `rs-table-toggle` still resolve.
- [ ] Commit:
  ```powershell
  $env:SQL_SYNC_SKIP="1"; git commit -m 'style(reporting): tokenize Simple scope panel + chart buttons' -m 'Replace literal hex in the cascade-winning Simple-pane scope panel
  (#d1d5db/#fff), scope badge (#eef2ff/#4338ca), inline label (#555),
  chart note (#6b7280) and the chart-tool buttons (#e5e7eb/#fff/#6b7280/
  #4f46e5/#eef2ff) with --nx-* tokens so they are dark-mode-correct and
  consistent. Layout/sizing untouched. CSS only; classes, ids and
  data-testids unchanged.

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'; Remove-Item Env:SQL_SYNC_SKIP
  ```

### Task 3: Token-ize the Show-query panel, AI-loading & chips (incl. bogus fallback tokens)

**Files:** `static/css/reporting.css`

- [ ] Edit `.reporting-sqlview pre` — anchor on `background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px;` → `background: var(--nx-sunken); border: 1px solid var(--nx-border); border-radius: 6px; padding: 10px;` and add `color: var(--nx-text);` to the rule. (Keep `white-space`, `max-height`, monospace `font-family`.)
- [ ] Edit `.reporting-sqlview-params` — anchor on `font-size: 12px; color: #6b7280; margin: 6px 0 0;` → change `color: #6b7280` to `color: var(--nx-text-meta)`.
- [ ] **Do NOT touch** the `.reporting-sqlview pre .sql-kw`, `.sql-string`, `.sql-number`, `.sql-ident`, `.sql-param`, `.sql-comment` rules (the `#cf222e/#0a3069/#0550ae/#953800/#8250df` syntax colors) — these are intentional GitHub-style highlight colors and e2e asserts on the spans.
- [ ] Edit `.reporting-ai-loading` — anchor on `padding: 2.5rem 0; color: var(--nx-text-muted, #6b7280);` → `padding: 2.5rem 0; color: var(--nx-text-sec);` (the `--nx-text-muted` token does NOT exist in `nexora-ui.css`, so the `#6b7280` fallback was firing — replace with the real `--nx-text-sec`).
- [ ] Edit `.rs-chip` — anchor on `background: var(--nx-surface-2, #eef2ff); border: 1px solid var(--nx-border, #c7d2fe);` → `background: var(--nx-accent-tint); border: 1px solid var(--nx-border);` (the `--nx-surface-2` token does NOT exist, so its `#eef2ff` fallback was firing; the `--nx-border` fallback `#c7d2fe` is wrong-coloured too).
- [ ] **Verify each token exists** in `static/css/nexora-ui.css` `:root` before saving: `--nx-sunken`, `--nx-text`, `--nx-text-meta`, `--nx-text-sec`, `--nx-accent-tint`, `--nx-border` all exist. (`--nx-accent-soft`, `--nx-accent-tint`, `--nx-border`, `--nx-card`, `--nx-text-sec` confirmed present in `:root` and `html.dark`.) If `--nx-sunken` does not resolve, substitute the closest existing surface token (`--nx-alt`) rather than inventing a name.
- [ ] CSS-only: hard-reload. Open a Simple result's Show-query panel and (if reachable) the editable AI chips, in light AND dark; confirm the SQL preview block is dark-surface and the syntax colors are unchanged. Screenshot `var/screenshots/reporting-after-sqlview-chips-<light|dark>-1440.png`.
- [ ] Confirm `rs-sql-view` and the `.sql-kw` spans still resolve.
- [ ] Commit:
  ```powershell
  $env:SQL_SYNC_SKIP="1"; git commit -m 'style(reporting): tokenize show-query panel + AI chips' -m 'Token-ize the Simple Show-query SQL preview block (#f9fafb/#e5e7eb) and
  params line (#6b7280), and replace the bogus --nx-surface-2/--nx-text-muted
  fallbacks (neither token exists in nexora-ui.css, so the wrong literal hex
  was firing) on the AI chips and AI-loading indicator with real --nx-* tokens
  (accent-tint/border/text-sec). The intentional .sql-* syntax-highlight colors
  are left untouched. CSS only; classes, ids and data-testids unchanged.

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'; Remove-Item Env:SQL_SYNC_SKIP
  ```

---

# PHASE 2 — Button co-apply (Advanced toolbar, AI/SQL panels, four modals) — markup

The `.reporting-input`/`.reporting-title-input`/`.reporting-export-format` controls are ALREADY tokenized in the appended block (line ~571 `.reporting-input,…{ background: var(--nx-card); border: 1px solid var(--nx-border); border-radius: var(--nx-radius-sm); }`) and that rule WINS over `.nx-input` by source order — so co-applying `nx-input` on them is a near-no-op and is intentionally SKIPPED (Decisions table). What DOES add value is co-applying the `.nx-btn` variants on buttons, because `nx-btn--ghost`/`--sm`/`--primary`/`--secondary` give the canonical button treatment the bespoke `.reporting-btn`/`.reporting-link` rules lack. Co-apply alongside the existing class (never remove `.reporting-*` — the JS injects/queries it). Markup edits → template-cache restart required. Anchor every edit on the quoted markup.

### Task 4: Co-apply nx-btn variants on the Advanced toolbar

**Files:** `templates/reporting.html`

- [ ] Anchor on `<button id="rpRun" class="reporting-btn reporting-btn-primary" data-testid="reporting-run">` → class `"reporting-btn reporting-btn-primary nx-btn nx-btn--primary"`. Keep the inner `<i class="fas fa-play">` and `{{ _("Run") }}`.
- [ ] Anchor on `<button id="rpSave" class="reporting-btn" data-testid="reporting-save">` → append ` nx-btn nx-btn--secondary`.
- [ ] Anchor on `<button id="rpSaveAs" class="reporting-btn" data-testid="reporting-save-as">` → append ` nx-btn nx-btn--secondary`.
- [ ] Anchor on `<button id="rpLoad" class="reporting-btn" data-testid="reporting-load">` → append ` nx-btn nx-btn--secondary`.
- [ ] Anchor on `<button id="rpExport" class="reporting-btn" data-testid="reporting-export">` → append ` nx-btn nx-btn--secondary`. Keep the `<i class="fas fa-file-export">`.
- [ ] For the saved-report link buttons `id="rpRename"`, `id="rpDelete"`, `id="rpShare"` and (inside `{% if has_permission('reporting.schedule') %}`) `id="rpSchedule"` — each `class="reporting-link"` → append ` nx-btn nx-btn--ghost nx-btn--sm`. Preserve every id/data-testid/title/`disabled`.
- [ ] Anchor on `<button type="button" id="rpShowSql" class="reporting-link" hidden` → class `"reporting-link nx-btn nx-btn--ghost nx-btn--sm"` (keep `hidden`).
- [ ] **Tailwind-v4 trap guard:** these elements toggle visibility via the `hidden` *attribute* (`hidden`), not a `.hidden` class, so adding nx button classes is safe. Verify in the browser that nothing meant to be hidden is now showing.
- [ ] Restart server (`nx -u -b --loginas:ben.streich`) — markup changed. Open Advanced tab; screenshot toolbar light+dark at 1440 → `var/screenshots/reporting-after-toolbar-<light|dark>-1440.png`. Compare to baseline: same controls, same order, design-system buttons.
- [ ] Selector-preservation proof: `python scripts/test_db_reset.py` then `python -m pytest tests/e2e/test_reporting.py tests/e2e/test_reporting_save.py tests/e2e/test_reporting_load.py tests/e2e/test_reporting_share.py -q` → GREEN (every `data-testid` still resolves).
- [ ] Commit:
  ```powershell
  $env:SQL_SYNC_SKIP="1"; git commit -m 'style(reporting): toolbar buttons onto nx-btn variants' -m 'Co-apply the design-system .nx-btn variants (primary/secondary/ghost/sm)
  alongside the existing .reporting-btn/.reporting-link classes on the Advanced
  toolbar Run/Save/Save-as/Load/Export buttons, the saved-report rename/delete/
  share/schedule links and Show-SQL. The bespoke classes and every data-testid
  are retained so the reporting JS and e2e are unaffected. Inputs are left as-is
  (their .reporting-* rule is already tokenized and wins the cascade). Markup only.

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'; Remove-Item Env:SQL_SYNC_SKIP
  ```

### Task 5: Co-apply nx-btn variants on the AI panel & SQL panel buttons

**Files:** `templates/reporting.html`

- [ ] Anchor on `<button id="rpAiAsk" class="reporting-btn reporting-btn-primary"` → class `"reporting-btn reporting-btn-primary nx-btn nx-btn--primary"`.
- [ ] For each AI action button `id="rpAiInsert"`, `id="rpAiOpenBuilder"`, `id="rpAiMakeChart"`, `id="rpAiAgentOpenBuilder"`, `id="rpAiAgentInsertSql"` (each `class="reporting-btn"`) → append ` nx-btn nx-btn--secondary`. For `id="rpAiCopy"` (`class="reporting-link"`) → append ` nx-btn nx-btn--ghost nx-btn--sm`.
- [ ] **Do NOT** alter `.reporting-ai-submode` / `.reporting-ai-bar` / `.reporting-ai-thread` / `.reporting-ai-trace` / `.reporting-ai-dots` markup — these are page-unique and animation/loader-bound; their CSS is already token-mapped in the appended block.
- [ ] **Do NOT** co-apply on `<input id="rpAiPrompt" class="reporting-ai-prompt">` — `.reporting-ai-prompt` is in the tokenized input rule that wins the cascade; co-apply would be a no-op.
- [ ] Restart server. Reach the AI panel (click the `reporting-mode-ai` button; requires `reporting.ai.use`, which `ben.streich` has on INT — see Owner actions if the panel is unreachable) and toggle Build / Write-SQL / Agent submodes. Screenshot AI panel + SQL panel light+dark → `var/screenshots/reporting-after-aipanel-<light|dark>-1440.png`.
- [ ] e2e: `python scripts/test_db_reset.py` then `python -m pytest tests/e2e/test_reporting_sql.py -q` → GREEN.
- [ ] Commit:
  ```powershell
  $env:SQL_SYNC_SKIP="1"; git commit -m 'style(reporting): AI/SQL panel buttons onto nx-btn variants' -m 'Co-apply .nx-btn variants on the Advanced Ask-AI Ask button and every AI
  action button (insert/open-builder/make-chart/agent/copy) so they match the
  design-system buttons. The AI submode toggle, dots loader, agent thread/trace
  and the already-tokenized AI prompt input are left untouched. The bespoke
  classes and data-testids are retained. Markup only.

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'; Remove-Item Env:SQL_SYNC_SKIP
  ```

### Task 6: Co-apply nx-card on the four modal boxes + nx-btn on modal actions

**Files:** `templates/reporting.html`

All four modals use `<div class="reporting-modal" hidden>` › `<div class="reporting-modal-box">`. The **outer** `reporting-modal` (dimmed overlay) and the inner `reporting-modal-box` are **animation hooks** for `_reporting_anim_js.html` (it selects `.reporting-modal` and `.reporting-modal-box`) — keep both class names FIRST in the class list. The `.reporting-modal-box` CSS is already tokenized in the appended block (`var(--nx-card)`), so co-applying `nx-card` is mostly belt-and-braces, but it makes the intent explicit and harmless.

- [ ] For EACH of the four `<div class="reporting-modal-box">` (disambiguate by the `<h3>` text that follows — `Live SQL — read-only`, `Share report`, `Schedule report`, and the one whose `<h3 id="rpNameModalTitle">`): change to `class="reporting-modal-box nx-card nx-card--pad"`. Keep `reporting-modal-box` first.
- [ ] Co-apply `.nx-btn` variants on the modal action buttons (inside each `<div class="reporting-modal-actions">`): every `class="reporting-btn"` → append ` nx-btn nx-btn--secondary`; every `class="reporting-btn reporting-btn-primary"` → append ` nx-btn nx-btn--primary`. Targets (each id unique): `rpSqlAckCancel`, `rpSqlAckAccept`, `rpShareAdd`, `rpShareClose`, `rpSchedAdd`, `rpScheduleClose`, `rpNameModalCancel`, `rpNameModalOk`.
- [ ] **Do NOT** co-apply `.nx-input`/`.nx-select` on modal inputs/selects — `.reporting-input` is already tokenized and wins (no-op).
- [ ] **Do NOT** edit any `.reporting-admin*` markup or CSS — `reporting-admin-grid`/`reporting-admin-cols` in the schedule modal are SHARED with `reporting_metrics.html`/`reporting_sources.html`. (You're only adding `nx-card`/`nx-btn` on modal boxes/buttons, which doesn't touch those rules.)
- [ ] **Animation hook check:** confirm `reporting-modal` and `reporting-modal-box` remain the FIRST classes so `_reporting_anim_js.html` still matches them and the Motion scale-in entrance still fires.
- [ ] Restart server. Open each modal: Run a trivial report then Save → `rpNameModal`; in SQL mode click Show-query → `rpSqlAck`; select a saved report you own → enable Share/Schedule. Screenshot all four modals open, light+dark → `var/screenshots/reporting-after-modal-<name>-<light|dark>.png`. Confirm the scale/fade entrance animation still plays (hook intact).
- [ ] e2e: `python scripts/test_db_reset.py` then `python -m pytest tests/e2e/test_reporting_save.py tests/e2e/test_reporting_share.py tests/e2e/test_reporting_schedule.py tests/e2e/test_reporting_sql.py -q` → GREEN (these assert modal ids/testids and `reporting-sql-ack`).
- [ ] Commit:
  ```powershell
  $env:SQL_SYNC_SKIP="1"; git commit -m 'style(reporting): modals onto nx-card + nx-btn actions' -m 'Co-apply nx-card nx-card--pad on each reporting-modal-box (keeping the
  reporting-modal/reporting-modal-box hook classes first so the Motion entrance
  animation still selects them) and nx-btn variants on the SQL-ack/share/
  schedule/name modal action buttons. Inputs are left on their already-tokenized
  .reporting-input rule. The shared .reporting-admin* rules are untouched. All
  ids/data-testids preserved. Markup only.

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'; Remove-Item Env:SQL_SYNC_SKIP
  ```

### Task 7: Co-apply nx-btn on the Simple-tab result-bar buttons

**Files:** `templates/_reporting_simple.html`

The Simple top row (New report / Ask AI / Refine) already uses `nx-btn`. Finish the result-bar action buttons.

- [ ] In the Simple result bar, co-apply on the action buttons: every `class="reporting-btn"` → append ` nx-btn nx-btn--secondary`; every `class="reporting-link"` → append ` nx-btn nx-btn--ghost nx-btn--sm`. Disambiguate each by its `data-testid` (e.g. `rs-export`, `rs-show-sql`, `rs-save`, `rs-exit`) and preserve the testid.
- [ ] **Do NOT rename** `reporting-simple-card`, `reporting-simple-choice`, `reporting-chartbtn`, `reporting-simple-stat`, `reporting-simple-table` — the Simple JS injects/queries these and e2e asserts on them (token-ized in Phase 1, not renamed). **Do NOT** co-apply `.nx-input` on the Simple search/AI inputs (already-tokenized `.reporting-input` wins — no-op).
- [ ] Leave the already-nx result cards (`nx-card nx-card--pad nx-stat reporting-simple-stat`, `nx-card nx-card--pad reporting-simple-chartcard`, `nx-card nx-card--pad reporting-sqlview`) as-is.
- [ ] Restart server. Run a Simple report, screenshot the result bar light+dark → `var/screenshots/reporting-after-simple-resultbar-<light|dark>-1440.png`.
- [ ] e2e: `python scripts/test_db_reset.py` then `python -m pytest tests/e2e/test_reporting_simple.py -q` → GREEN (asserts `button.reporting-simple-choice`, `.is-selected`, `p.reporting-simple-empty`, `.reporting-truncated-note`, `rs-*` testids).
- [ ] Commit:
  ```powershell
  $env:SQL_SYNC_SKIP="1"; git commit -m 'style(reporting): Simple result-bar buttons onto nx-btn' -m 'Co-apply .nx-btn variants alongside the existing .reporting-btn/.reporting-link
  classes on the Simple result-bar actions (export/show-sql/save/exit) so they
  match the design-system buttons. The wizard choice chips, library cards, chart
  buttons and stat/table classes keep their names (JS-injected, e2e-asserted, and
  token-ized in Phase 1). Inputs left as-is. All rs-* data-testids preserved.
  Markup only.

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'; Remove-Item Env:SQL_SYNC_SKIP
  ```

---

# PHASE 3 — Conditional layout tidy (only if a real defect survives)

Stance discipline: after Phases 1–2 the page is token-correct and on design-system buttons. These tasks fix alignment ONLY if a baseline/after screenshot shows a real defect. If the region already looks clean, SKIP and record the decision — do not manufacture churn.

### Task 8: Tidy Simple result-bar / AI-bar alignment (conditional)

**Files:** `static/css/reporting.css` (CSS only — no markup change, no restart)

- [ ] Compare the Phase-0 and Phase-2 screenshots of the Simple result bar (`.reporting-simple-resultbar`) and top row at 1440px. If alignment is clean, **SKIP** — record "Simple bars already aligned after reskin; no edit." Do not commit.
- [ ] If a real defect survives (e.g. action buttons wrap awkwardly because the title doesn't shrink): edit the EXISTING rule, anchored on its quoted body. Specifically, if needed, anchor on `.reporting-simple-rtitle { margin: 0; font-size: 16px; flex: 1; }` and add `min-width: 0;` so the flex title can shrink and the actions stay on one row. Do not restructure markup or add new classes.
- [ ] If edited: hard-reload, screenshot light+dark, then commit:
  ```powershell
  $env:SQL_SYNC_SKIP="1"; git commit -m 'style(reporting): tidy Simple result-bar alignment' -m 'Allow the Simple result-bar title to shrink (min-width: 0) so the action
  buttons stay aligned on one row at desktop width, matching the app spacing
  rhythm. CSS only; no markup, class, id or data-testid changes.

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'; Remove-Item Env:SQL_SYNC_SKIP
  ```

### Task 9: Tidy Advanced toolbar / export bar spacing (conditional)

**Files:** `static/css/reporting.css` (CSS only — no restart)

- [ ] Compare the Phase-0 and Phase-2 toolbar screenshots. The REDESIGN appended block already restyled the toolbar (`.reporting-toolbar`, `.reporting-actions`, `.reporting-actions-sep`). If the export `<select>` + button + separator + run/save actions line up cleanly, **SKIP** — record "Advanced toolbar already clean after reskin." Do not commit.
- [ ] If a real defect survives: make the smallest fix by editing the EXISTING `.reporting-actions` or `.reporting-actions-sep` rule (anchor on its quoted body) — e.g. add/normalize `align-items: center;` and a consistent `gap`. Do not edit any `.reporting-admin*` rule. Do not restructure markup.
- [ ] If edited: hard-reload, screenshot light+dark, then commit:
  ```powershell
  $env:SQL_SYNC_SKIP="1"; git commit -m 'style(reporting): tidy Advanced toolbar/export bar' -m 'Normalize vertical alignment/gap on the Advanced toolbar export controls so
  the format select, export button and separator line up with the run/save
  actions. CSS only; no markup, class, id or data-testid changes.

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'; Remove-Item Env:SQL_SYNC_SKIP
  ```

---

# PHASE 4 — Verify, document, hand off

### Task 10: Full verification, shared-page regression guard, CHANGELOG, hand off

**Files:** `CHANGELOG.md` (+ verification only).

- [ ] **Shared-page regression guard (F5):** restart server, open `templates/reporting_sources.html` and `templates/reporting_metrics.html` routes in the browser (they share `reporting.css` via `.reporting-admin*` / `.reporting-input`), screenshot each light+dark → `var/screenshots/reporting-admin-regression-<sources|metrics>-<light|dark>.png`. Confirm NO visual change vs. how they looked before (the Simple-pane token edits and button co-applies should not have touched these). If anything regressed, an edit strayed onto a shared selector — revert that specific edit.
- [ ] **Full e2e gate (local, not push):** `python scripts/test_db_reset.py` then re-run the full 11-file reporting suite from Task 0. Must MATCH the Task 0 baseline pass count — this is the data-testid/selector/wording preservation proof. If red, debug with superpowers:systematic-debugging: a class restyle/co-apply should not break testid-based e2e, so a red means a `data-testid` was dropped, a hook class was reordered out of first position, or the `"Too many data points to chart"` text changed — fix in place.
- [ ] **i18n no-op check:** `pybabel extract -F babel.cfg -o messages.pot .` then `git diff --stat messages.pot`. If the only diff is the POT header/timestamp → `git checkout -- messages.pot` (no new strings, as expected). If real msgids changed, a string slipped in — STOP and run the full `/nx-i18n` cycle (extract → update → translate de/fr/it → compile) before committing.
- [ ] **Final AFTER sweep:** restart server, capture the complete after-set mirroring Task 0 (Advanced toolbar/wells/AI/SQL, Simple library/wizard/result, four modals) at 1440 + 375, light + dark, named `reporting-after-<surface>-<theme>-<width>.png`. `SendUserFile` the key before/after pairs (especially DARK mode Simple cards/chips/scope/chart-buttons) so the owner can review the reskin.
- [ ] **CHANGELOG:** add ONE entry under the EXISTING `## [Unreleased]` → first `### Changed` subsection (the one whose first bullet begins `- **Reporting Simple wizard: curated breakdown dimensions.**`; do NOT create a new header, do NOT target the later `### Changed` under `## [2.5.61] - 2026-05-28`). Append after that subsection's last existing bullet:
  ```markdown
  - **Reporting page reskinned to the shared nexora-ui design system.** The `/reporting` page (Simple + Advanced tabs, wizard, result views, AI bars and the share/schedule/name/SQL-ack modals) now uses the same `--nx-*` design tokens, cards and buttons as the admin and other pages, and renders correctly in dark mode (the residual hardcoded-hex Simple-pane styling was tokenized). No behavior or feature change.
  ```
- [ ] Run superpowers:verification-before-completion over the claims (e2e green at baseline count, before/after screenshots captured incl. dark mode, shared admin pages unchanged, no new strings, CHANGELOG updated).
- [ ] Commit the changelog:
  ```powershell
  $env:SQL_SYNC_SKIP="1"; git commit -m 'docs(changelog): note reporting nexora-ui reskin' -m 'Record under [Unreleased] Changed that the reporting page was reskinned onto
  the shared nexora-ui design system (tokens, cards, buttons, dark mode) with no
  behavior change.

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>'; Remove-Item Env:SQL_SYNC_SKIP
  ```
- [ ] **STOP. Remote session:** do NOT push, do NOT open a PR. Report the commit list and attach the before/after screenshots for the owner to review and push locally.

---

## Owner actions

- **Review the before/after screenshots** (attached via `SendUserFile`, especially dark-mode Simple-pane) and approve the visual direction. If you want bigger layout changes than "tidy + reskin", that's a separate scope.
- **Push + PR → main** yourself after local review (remote-session policy keeps this plan at `git commit`).
- **AI-panel reachability (Task 5):** the plan assumes `ben.streich` has `reporting.ai.use` on INT so the executor can reach and screenshot the AI panel. If not, that surface is screenshotted from markup/CSS only; the SQL-panel e2e still covers the selectors. Confirm the login user if a different INT account is expected.
- **Loading-states plan landing order:** `2026-06-12-reporting-loading-states-sql-display.md` could not be confirmed in git history. If you have it (or drill-through / show-query / page-improvement-options) in flight, decide landing order; this plan anchors every Simple-pane / SQL-view edit on quoted snippets so whichever lands second re-bases cleanly.

## Gotchas & notes

- **The cascade decides everything — edit the WINNER.** `reporting.css` loads after `nexora-ui.css`; both are unlayered; the file re-defines many `.reporting-*` selectors twice (early literal-hex + appended tokenized). The APPENDED (later) rule wins, so the early hex rules (`.reporting-modal-box`, `.reporting-btn-primary`, `.reporting-view-toggle button.active`, `.reporting-pivot-zone`) are DEAD — editing them is a no-op. The genuinely-residual hex this plan fixes is the Simple-pane block (`.reporting-simple-*`, `.reporting-chartbtn`, `.reporting-sqlview pre`, `.rs-chip`, `.reporting-ai-loading`), which sits after the appended blocks and so wins. Always search the whole file for a selector and edit its LAST definition.
- **Inputs are already tokenized — don't co-apply `.nx-input`.** `.reporting-input`/`.reporting-title-input`/`.reporting-export-format`/`.reporting-ai-prompt`/`.reporting-sql-editor` share an appended tokenized rule that WINS over `.nx-input` by source order. Co-applying `.nx-input` is a near-no-op and just adds churn/merge surface. Co-apply only on BUTTONS, where `nx-btn--ghost`/`--sm`/`--primary`/`--secondary` add real variants.
- **Tailwind-v4 layer trap.** CDN utilities are in `@layer utilities`; unlayered custom rules always beat them. New/edited `.reporting-*` rules win automatically; if you ever need an nx utility to win over a bespoke property, re-assert at equal/higher specificity (`.reporting-x.nx-y { … }`) AFTER the appended blocks — only when a real regression is observed. Elements toggled via the `hidden` *attribute* (modals/panels/Show-SQL) are safe; only a `.hidden` *class* toggle would need a `display:none` re-assertion.
- **Bogus fallback tokens.** `--nx-surface-2`, `--nx-text-muted`, and `--rp-border` do NOT exist in `nexora-ui.css`, so their literal `#fallback` fires (wrong in dark mode). Phase 1 replaces `--nx-surface-2`→`--nx-accent-tint`, `--nx-text-muted`→`--nx-text-sec`. If you encounter `var(--rp-border, #d0d7de)` anywhere, replace with `var(--nx-border)`.
- **Selected-fill token = `--nx-accent-tint`** (`#eef2ff` light / `#312e81` dark); `--nx-accent-soft` is the rgba focus-ring/shadow. Both exist — use tint for is-selected fills, soft for shadows, consistently.
- **NEVER rename a `.reporting-*` class.** Nine JS partials inject/query them; `_reporting_anim_js.html` selects `.reporting-modal`, `.reporting-modal-box`, `.reporting-btn`, `.reporting-mode-toggle button`, `.reporting-view-toggle button` and pre-hides via `.rp-anim*` — keep those classes (and the modal hook classes FIRST in the class list) or the entrance animation dies silently. `_reporting_metrics_js.html`/`_reporting_sources_js.html` drive the shared admin pages.
- **`.reporting-admin*` is shared** with `reporting_sources.html` / `reporting_metrics.html` (different routes, same stylesheet). Never edit `.reporting-admin*` CSS; verify both admin pages are unchanged after the reskin (Task 10).
- **Preserve every `data-testid`/`id`/`name`** on the same logical element — the e2e suite selects on those, not on `.reporting-*` classes, so class co-applies are safe *because* the testids survive. Don't change the chart-note text `"Too many data points to chart"`. Don't touch the `.sql-*` syntax-highlight colors.
- **Restart the dev server after template/markup edits** (Phases 2–3 markup tasks) — Jinja is process-cached; CSS-only edits (Phases 1, 8, 9) only need a hard browser reload.
- **Pre-commit hatch.** Always `$env:SQL_SYNC_SKIP="1"; git commit …; Remove-Item Env:SQL_SYNC_SKIP` (INT `SchemaMigrations` CRLF drift). Never `--no-verify`.
- **Merge-order rule.** Drill-through (Tasks 2–8), show-query-multidim-export Phase 2, page-improvement-options, and the unverified loading-states plan are queued on the same files. Anchor EVERY edit on a unique quoted snippet, never a line number; whichever lands second re-anchors. This plan never touches `reporting.py` to keep the conflict surface minimal.
- **Remote policy.** Stop at `git commit`; drive Playwright + screenshots yourself to `var/screenshots/` (light AND dark, 1440 + 375) and `SendUserFile` the before/after pairs; the owner pushes and opens the PR.
- **Stance discipline.** Phases 8 and 9 are conditional — skip if the region already looks clean after token-izing rather than manufacture churn. Smallest safe diff wins.
