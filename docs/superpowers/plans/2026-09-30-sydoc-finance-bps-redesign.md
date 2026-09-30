# Sydoc Finance + Sydoc BPS redesign (mirrored, Sydoc-branded) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `/finance` and `/bps` as a mirrored pair with the approved design **1a** from the handoff bundle. Both get a dark ink header band with the Sydoc mark and orange accent, the period as a 54px headline with prev/next arrows, and a shared period-picker modal. Finance gets a ledger layout (identity column plus statement lines with a comparison bar), orange share bars, a one-row jump index, and a per-customer **timeline** of billable bookings. BPS gets totals and a composition bar in the band, a restyled daily chart, a zoomable **Table (default) / Treemap** drill-down with gain/loss against the previous period, and a compact per-day bookings list at the leaf.

**Architecture:** The app shell stays as it is. Shared pieces go in one place each:
- CSS: `nx-sydoc-*` and `nx-track` classes plus the new `--nx-sydoc*` / `--nx-gain` / `--nx-loss` tokens, in `static/css/nexora-ui.css`.
- Markup: Jinja macros in a new `templates/_sydoc.html` (brand row, headline nav, picker shell).
- Behaviour: a new `static/js/nx_sydoc.js` (`window.NXSydoc`), with pure helpers (period headline, ISO week, month-grid model) plus a DOM `initPicker()` that is only called explicitly.

Page behaviour stays in `static/js/finance.js` / `static/js/bps.js`. The BPS pure logic (squarify, deltas, per-day grouping, drill levels) moves into a new `static/js/bps_view.js` (`window.BpsView`), so the Node-harness tests can reach it.

Backend changes are small:
- `nx_lib/bps.py` gains `previous_range()` and `months_query()` / `months_payload()`.
- `/api/bps/summary` gains a `prev` block.
- A new lazy endpoint `/api/bps/months` serves the picker's hours per month.
- `nx_lib/finance.py`'s `Section` gains an optional `nav` label.
- The `finance()` view passes per-month close state and split headline parts.

No SQL migration and no new permission.

**Tech Stack:** Flask + Jinja2, Flask-Babel (de/fr/it), vanilla JS (no build step), Chart.js 4.5.1 (already loaded on `/bps`), Font Awesome 6.4.2, pytest (unit + integration), Node-harness JS unit tests (pattern: `tests/unit/test_reporting_layout_view_js.py`), Playwright via `/nx-ui-verify`.

**Spec:** the design handoff, committed to `docs/design/design_handoff_sydoc_finance_bps/`. `README.md` there is the **visual spec of record**: every px, hex and state in this plan comes from it, and where this plan says "per README §X", the README's numbers are binding. The `.dc.html` prototypes (open them with `support.js` beside them) show the approved **1a** at the top and today's page (0a) below. There is no `docs/superpowers/specs/` entry. Issue: **to be filed from `ISSUE.md`** (Owner action 1).

---

## Context an engineer needs (read first)

- **Branch / worktree:** this plan was written on `plan/sydoc-finance-bps-redesign` in the worktree `.claude/worktrees/plan-sydoc-finance-bps-redesign`, cut from `main` @ `fd17c21b` (after #425 "BPS history"). Before Task 1, cut `feat/<issue>-sydoc-redesign` from it (branch-name guard: `<type>/<slug>` with the issue number). **Never touch `C:\dev\nexora`**. That checkout is on `feat/423-finance-bexio` with uncommitted Bexio work.
- **Sequencing vs #423 (Bexio invoice panel), the one real conflict.** #423 edits `templates/finance.html` (a new `#fin-bexio` section built on `nx-fin-section` / `nx-fin-section__tile`), `templates/js/_finance_js.html` (a `bexio:` strings block and a second `<script>` for `finance_bexio.js`), `static/css/finance.css` (+36 lines) and `nx_lib/finance.py` (`billed_clients()`). This plan rewrites all four. Therefore:
  - **PHASE 0–3 (shared + BPS) touch none of those files** and can start now.
  - **PHASE 4 (Finance) starts only after #423 is merged to `main`** and this branch is rebased on it (Task 21 is the gate).
  - Do not hand-merge `translations/*.po` or `messages.pot`. Regenerate them (`/nx-i18n`) after the rebase.
- **Anchor on function names and quoted snippets, never line numbers.** Re-Grep before every edit. Line numbers in this repo drift daily.
- **Worktree has no env files or venv.** See memory "Worktree env launcher": prefix `$env:PATH = "C:\dev\nexora\.venv\Scripts;$env:PATH"` for `pytest`/`python`. Run the server and `nx -u` via the scratchpad launcher. `env/*.env` cannot be read by Claude, so the owner copies `env/INT.env` into the worktree before the first browser check (Owner action 3).
- **Tests you can run locally:** `tests/unit` only. `TEST.env` points at a placeholder server, so integration tests 503 locally and **run in CI**. Write and update them anyway; CI is the gate. **No e2e tests cover `/finance` or `/bps`** (checked `tests/e2e/`), so the README's "update e2e selectors" step has no target. Keep the listed `data-testid`s on their new equivalents regardless.
- **Node is not installed on the dev box** (`node: command not found`). The JS unit tests follow `test_reporting_layout_view_js.py` and `skipif(NODE is None)`, so they skip locally. Owner action 4 is an optional `winget install OpenJS.NodeJS.LTS` so they run.
- **Jinja template cache:** restart the dev server after template edits. `/nx-ui-verify` restarts it.
- **Commits:** `$env:PATH` with the venv first, or the mypy hook fails (memory "Commit hooks need venv PATH"). If the SQL hooks block on unrelated INT drift, use `SQL_SYNC_SKIP=1 git commit ...`. Never use `--no-verify`. gitlint: imperative subject ≤72 chars with no trailing period, a non-empty wrapped body, and the `Co-Authored-By` trailer.
- **i18n cycle:** `/nx-i18n` (extract → update → translate de/fr/it → compile). `tests/unit/test_translations.py` fails on any untranslated or fuzzy msgid. Shim strings use `{name}` placeholders, **never** `%(name)s` (see the comment at the top of `templates/js/_finance_js.html`).
- **URL prefix:** PROD serves under `/nexora`. JS keeps using `window.NX.apiSafe('/api/...')` (prefix-aware) and builds navigation URLs from `new URL(window.location.href)` as today. `tests/unit/test_template_url_prefix.py` enforces this. New static files are referenced with `static_v()` (`tests/unit/test_static_v_lint.py`).
- **Dark mode is `html.dark`** (not `prefers-color-scheme`). The token blocks are `:root` and `html.dark` at the top of `static/css/nexora-ui.css`. The design has no dark theme: keep the band at `#0b0d12` and use the existing dark tokens below it (README "Fidelity").
- **Current data facts that override the README:**
  - BPS history now starts **3 January 2025** (#424, `docs/howto/bps.md`). The README's "No data before the first BPS export month (3 Aug 2026)" is stale, so the BPS picker derives "No data" from the per-month hours (D5).
  - `templates/js/_bps_js.html`'s `emptyPeriod` string still says "The BPS export starts on 3 August 2026." That is pre-existing drift; Task 12 fixes it.
- **Migrations needed: NO.** **New permission: NO** (`finance.view`, `finance.month.edit`, `bps.view` are unchanged). **Deploy excludes:** none, because `docs/` is already in `/XD` of `.github/workflows/deploy-env.yml` and every new runtime file sits under `static/` or `templates/`.

## Decisions locked in

| # | Decision | Rationale |
|---|---|---|
| D1 | Order: shared foundation → BPS → Finance. Finance waits for #423 to merge. | BPS files do not overlap #423; Finance files do (see Context). |
| D2 | The BPS view choice (Table/Treemap) persists in `localStorage` key `nx.bps.view`, wrapped in try/catch, default `table`. **Not** `ui_prefs`. | Per-viewer convenience. `ui_prefs` would need an allowlist entry in `nx_lib/ui_prefs.py` for a single page toggle. |
| D3 | "Previous period" = the previous calendar month when the range is exactly one calendar month, otherwise the same number of days immediately before (`bps.previous_range`). | README "New data needed". Makes "vs. July" exact for the default month view. |
| D4 | The BPS picker's per-month hours come from a **new lazy endpoint** `GET /api/bps/months` (`bps.view`, `60 per minute`), fetched on first picker open: one query over all history, `Datum` at `grain: "month"`. | Keeps page render and summary fast. `build_generic_query` already supports month grain, and `Datum` is `grainable` in 0124. |
| D5 | A BPS month cell is disabled with "No data" when it has zero hours, and future months are disabled too. No hard-coded first-data constant. | #424 moved the first date; a constant would drift again. |
| D6 | Finance picker month states are rendered **server-side** into the shim. `closed` = Month present in `dbo.FinanceMonthClose` (one `SELECT DISTINCT Month`). `running` = the current month. `open` = every other month in `month_options()`. No new endpoint. | The close table is tiny; the page already reads it. README's "latest invoiceable" reading is simplified to "every ended, unclosed month": all of them are open. |
| D7 | Shared pieces: CSS in `nexora-ui.css` (`nx-sydoc-band`, `nx-sydoc-picker`, `nx-track`, `nx-sydoc-pill`, `nx-sydoc-btn`); Jinja macros in `templates/_sydoc.html`; JS in `static/js/nx_sydoc.js`. | README "Files to touch": the two pages must stay a mirrored pair without copy-paste. |
| D8 | Pure JS logic gets Node-harness unit tests (`window.NXSydoc`, `window.BpsView`). DOM code is verified in the browser (`/nx-ui-verify`). | Existing precedent; no JS build or test runner in the repo. |
| D9 | Finance breakdown and matrix blocks keep their `<table>` markup and collapse logic (`nx-fin-more`, `is-more`) and are restyled to the README grid. The BPS drill-down table becomes a list of `<button>` rows inside `role="table"`-free markup: README "Keyboard: rows and tiles are buttons". | Reuse where the design allows; buttons where the design demands zooming. |
| D10 | Finance headline parts (`month_name`, `month_year`) are formatted server-side with `format_date(..., "LLLL")` / `"yyyy"`. BPS headline parts are computed client-side by `NXSydoc.periodHeadline()` (month / "Week N" / "Jun – Aug" / "1 – 31 Aug"). | Finance already formats `month_label` server-side; BPS ranges are arbitrary. |
| D11 | Prev/next at the range ends render as an inert `<span aria-disabled="true">` at opacity .35, as today's disabled "next". Finance prev is inert at the oldest of `month_options()`. BPS prev is always live (history is long); BPS next is inert when the next month starts after today. | README "Opacity .35 and inert at the range ends". |
| D12 | The Sydoc mark is a cropped PNG `static/images/sydoc-mark.png` (crop box `(1040, 130, 1240, 366)` of `static/images/sydoc-logo.png`, resized to 88×104), shown at 22×26. | README asks for a separate asset; the crop was verified visually during planning. |
| D13 | Sydoc orange only on these two pages via `body.nx-sydoc`. Controls outside the band keep `--nx-accent` for focus rings and checkboxes. | README "Accent note". |
| D14 | The Bexio panel (#423) becomes a ledger-style row in the Finance page: identity column "Bexio · Invoices" plus refresh action, and its existing body on the right, placed between the confirm panel and "Internal customers" as today. Its jump-index entry goes in the services group. `finance_bexio.js` rendering is otherwise untouched. | Keeps #423 behaviour while fitting the new layout; its internals are not part of this design. |
| D15 | Nothing is removed from the payloads or APIs. Only presentation changes, plus additive fields (`nav`, `prev`, `months`). | Month close snapshots stored in `dbo.FinanceMonthClose` must keep rendering. |

## Owner actions

1. **File the issue** from `docs/design/design_handoff_sydoc_finance_bps/ISSUE.md` (for example `gh issue create --title "Redesign Sydoc Finance + Sydoc BPS as a mirrored, Sydoc-branded pair" --body-file docs/design/design_handoff_sydoc_finance_bps/ISSUE.md`). Then give the number to the executor, who names the branch `feat/<n>-sydoc-redesign` and uses `(#<n>)` in commits and the changelog. Claude does not post issues unprompted.
2. **Merge #423** (Bexio panel) before PHASE 4 starts. If #423 is abandoned, Task 21 says what to drop.
3. Copy `env/INT.env` (and `env/TEST.env`) into the worktree's `env/` before the first `/nx-ui-verify` (Task 20).
4. Optional: install Node LTS on the dev box (`winget install OpenJS.NodeJS.LTS`) so the JS unit tests run locally instead of skipping.
5. A dark theme for below the band is **not designed**. Review Task 20 / Task 33's dark screenshots and say if it needs a design pass.

---

# PHASE 0 — Branch and design bundle

### Task 0: Branch and verify the bundle is in the tree

- [ ] **Step 1:** In the worktree, `git switch -c feat/<n>-sydoc-redesign` (from `plan/sydoc-finance-bps-redesign`, which carries the bundle and this plan).
- [ ] **Step 2:** `git ls-files docs/design/design_handoff_sydoc_finance_bps` should list `README.md`, `ISSUE.md`, both `.dc.html`, `support.js`, `assets/*`. They were committed with the plan. If they are missing, stop and ask.

---

# PHASE 1 — Shared foundation (tokens, mark, band, picker)

### Task 1: Sydoc tokens and the `body.nx-sydoc` modifier

**Files:** Modify `static/css/nexora-ui.css`.

- [ ] **Step 1:** In the `:root` token block (anchor: the line `  --nx-page:        #f9fafb;`), add after the radius tokens (anchor `  --nx-radius-hero: calc(var(--nx-radius-scale, 1) * 16px);`):

```css
  /* Sydoc's own books (Finance, BPS) -- README of design_handoff_sydoc_finance_bps */
  --nx-sydoc:           #e3633f;
  --nx-sydoc-hover:     #ec7656;
  --nx-sydoc-soft:      #f08a6c;
  --nx-sydoc-ink-text:  #b2401f;
  --nx-sydoc-band:      #111318;
  --nx-sydoc-band-line: rgba(255,255,255,.08);
  --nx-sydoc-band-ctl:  rgba(255,255,255,.14);
  --nx-gain:            #047857;
  --nx-loss:            #b91c1c;
```

- [ ] **Step 2:** In the `html.dark {` block (anchor `  --nx-page:        #0f172a;`), add:

```css
  --nx-sydoc-band:      #0b0d12;
  --nx-sydoc-ink-text:  #f08a6c;
  --nx-gain:            #34d399;
  --nx-loss:            #f87171;
```

- [ ] **Step 3:** After the sidebar rule (anchor `.sidebar-nav-item--active::before {` … `background: var(--nx-brand-grad);`), add:

```css
body.nx-sydoc .sidebar-nav-item--active::before { background: var(--nx-sydoc); }
body.nx-app.nx-sydoc .nx-main { padding-top: 36px; }
```

- [ ] **Step 4:** `python -m pytest tests/unit -q -k "css or static" -p no:cacheprovider` should be green. Commit:

```
feat(ui): add Sydoc brand tokens and the nx-sydoc page modifier (#<n>)

Finance and BPS are Sydoc's own books and get their own accent: orange
tokens, gain/loss colours for both themes, the orange active-nav bar and a
36px top padding, all scoped to body.nx-sydoc.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### Task 2: The Sydoc mark asset

**Files:** Create `static/images/sydoc-mark.png`.

- [ ] **Step 1:** One-off (do **not** commit a script). Run from the worktree:

```powershell
python -c "from PIL import Image; Image.open('static/images/sydoc-logo.png').crop((1040,130,1240,366)).resize((88,104), Image.LANCZOS).save('static/images/sydoc-mark.png', optimize=True)"
```

- [ ] **Step 2:** Read the PNG with the Read tool. It should be the orange document glyph with the small squares at the top right. Commit `feat(ui): add the cropped Sydoc mark for the ink band (#<n>)` with a one-line body.

### Task 3: Shared band / picker / track CSS

**Files:** Modify `static/css/nexora-ui.css` (new section at the end, headed `/* ---- Sydoc band + period picker (Finance, BPS) ---- */`).

Write these classes with every value from README "Shared pieces" (the hexes go through the Task 1 tokens where one exists):

- [ ] **Step 1: Band.**
  - `.nx-sydoc-band`: background `var(--nx-sydoc-band)`, radius `var(--nx-radius-hero)`, color `#e5e7eb`, overflow hidden, padding `22px 30px 26px`. Modifier `.nx-sydoc-band--flush` uses `22px 30px 0` (Finance).
  - `.nx-sydoc-band__row1`: flex, gap 10px, center.
  - `.nx-sydoc-mark`: 22×26, `background: url('../images/sydoc-mark.png') center/contain no-repeat`.
  - `.nx-sydoc-eyebrow`: 10px/700, uppercase, .12em, `var(--nx-sydoc-soft)`. `--muted` variant uses `#6b7280`.
  - `.nx-sydoc-band__spacer`: `flex:1`.
- [ ] **Step 2: Band buttons.**
  - `.nx-sydoc-btn`: 32px high, radius 8px, 12.5px/600, gap 7px, `i{color:#9ca3af}`.
  - Variants `--primary` (bg `var(--nx-sydoc)`, text `#111318`, `i` inherits, hover `var(--nx-sydoc-hover)`), `--ghost` (transparent, `1px solid var(--nx-sydoc-band-ctl)`, `#e5e7eb`, hover `rgba(255,255,255,.06)`) and `--link` (no border, `#d1d5db`, hover bg `rgba(255,255,255,.06)` and white).
- [ ] **Step 3: Row 2 and headline.**
  - `.nx-sydoc-band__row2`: margin-top 22px, flex, align end, gap 40px, wrap. `.nx-sydoc-band__lead`: `flex:1 1 520px`.
  - `.nx-sydoc-band__h1`: 14px/600, `#9ca3af`, −.01em, margin 0.
  - `.nx-sydoc-headline`: margin-top 6px, flex, center, gap 14px.
  - `.nx-sydoc-nav`: 36×36 round, `1px solid var(--nx-sydoc-band-ctl)`, `#d1d5db`, hover `rgba(255,255,255,.08)`. `[aria-disabled="true"]` gets opacity .35 and `pointer-events:none`.
  - `.nx-sydoc-period`: button reset, nowrap, baseline, gap 12px. `__main` is 54px/600, −2.2px, lh 1, white. `__year` is 54px/400, `#6b7280`, tabular-nums. `__chev` is 14px `#6b7280`, `align-self:center`.
  - `.nx-sydoc-hint`: margin-top 12px, 12.5px/1.5, `#9ca3af`, max-width 64ch.
- [ ] **Step 4: Status grid.**
  - `.nx-sydoc-stats`: 2-col grid, gap `4px 36px`.
  - `__k`: 10px/700 uppercase .1em `#6b7280`. `__v`: 14px/600 `#f3f4f6` nowrap.
  - `.nx-sydoc-dot`: 8px circle; `--live` `#34d399`, `--running` `#f59e0b`, `--failed` `var(--nx-danger)`.
- [ ] **Step 5: Track switch.**
  - `.nx-track`: inline-flex, bg `#f3f4f6`, padding 3px, radius 10px.
  - `.nx-track__btn`: 27px high, padding `0 11px`, radius 7px, 11.5px/600, nowrap, transparent, `#6b7280`. `.is-active` / `[aria-pressed="true"]`: white, shadow `0 1px 2px rgba(16,24,40,.1)`, `#1f2937`.
  - Dark: `html.dark .nx-track{background:var(--nx-alt)}` and active `background:var(--nx-card);color:var(--nx-text)`.
- [ ] **Step 6: Picker.**
  - `.nx-sydoc-picker`: fixed inset 0, `rgba(17,19,24,.45)`, flex column, align center, padding-top 150px, z-index above the sidebar. `[hidden]` is display none. Fade in with `@keyframes nx-sydoc-fade` 150ms `var(--nx-ease)`, disabled under `@media (prefers-reduced-motion: reduce)`.
  - `__panel`: white (`var(--nx-card)`), radius 14px, shadow per README, width 440px (`--wide` 460px), `max-width: calc(100vw - 32px)`.
  - `__head` (padding `16px 18px 14px`, bottom border `#f3f4f6`), `__title` (15px/700/−.02em), `__close` (28×28, r7).
  - `__section` (padding `14px 18px 0`), `__year` (padding `16px 18px 6px`; 30×30 round buttons; year 22px/600/−.8px tabular).
  - `__grid`: 3 cols, gap 8px, margin-top 14px.
  - `__cell`: height 62px (`--compact` 58px), padding `10px 12px`, r10, `1px #e5e7eb`.
    - `__cell-name`: 14px/600. `__cell-status`: 11px, with modifiers `--closed` `#9ca3af`, `--open` `#047857`, `--running` `#b45309`.
    - `.is-selected`: bg/border `#111318`, white name, status `var(--nx-sydoc-soft)`. `[disabled]`: opacity .4.
  - `__legend` (padding `12px 18px 16px`, 11px `#6b7280`, gap 14px) and `__foot` (top border, padding `14px 18px 18px`; date inputs 32px r7 `1px #d1d5db`; labels 10px uppercase).
  - `.nx-sydoc-pill`: 30px, r99, 12px/600. Inactive: white, `1px #e5e7eb`, `#374151`. `.is-active`: `#111318` bg and border, white.
  - `.nx-sydoc-btn--ink`: 32px, `#111318`, white, r8.
- [ ] **Step 7: Responsive** `@media (max-width: 1023px)`: `.nx-sydoc-period__main, __year { font-size: 40px; letter-spacing: -1.6px }`; `.nx-sydoc-band__row2 { gap: 20px }`.
- [ ] **Step 8:** Commit `feat(ui): add the shared Sydoc band, period picker and track styles (#<n>)`.

### Task 4: Shared Jinja macros

**Files:** Create `templates/_sydoc.html`.

- [ ] **Step 1:** Write macros (imported with `{% import '_sydoc.html' as sydoc %}`; `_()` is available in imported macros only `with context`, so import it that way):
  - `brand(second_eyebrow)` renders `.nx-sydoc-band__row1`'s left part: `<span class="nx-sydoc-mark" aria-hidden="true"></span>`, then `<span class="nx-sydoc-eyebrow">{{ _("Sydoc internal") }}</span>`, then the muted eyebrow.
  - `headline(h1, testid, main, year, prev_href, next_href, prev_label, next_label, picker_id)` renders the h1 (`data-testid="{{ testid }}-title"`) and the three controls.
    - Prev/next render as `<a class="nx-sydoc-nav" href=... aria-label=... data-testid="{{ testid }}-month-prev|next">`, or as an inert `<span class="nx-sydoc-nav" aria-disabled="true">` when the href is falsy.
    - The period button is `<button type="button" class="nx-sydoc-period" aria-haspopup="dialog" aria-controls="{{ picker_id }}" data-testid="{{ testid }}-period-button">`, with `<span class="nx-sydoc-period__main" data-role="period-main">`, `__year` (`data-role="period-year"`) and `<i class="fas fa-chevron-down nx-sydoc-period__chev" aria-hidden="true"></i>`.
  - `picker_open(id, title, wide=False)` / `picker_close()`: the overlay (`hidden`, `role="dialog" aria-modal="true" aria-labelledby="{{ id }}-title"`), panel and head with close button (`data-role="picker-close"`, `aria-label="{{ _('Close') }}"`). Page-specific content goes between the two calls.
- [ ] **Step 2:** No test yet: the macros are exercised by the page integration tests in Tasks 13 and 23. Commit with Task 5.

### Task 5: `static/js/nx_sydoc.js` (pure helpers + picker controller)

**Files:** Create `static/js/nx_sydoc.js`, `tests/unit/test_nx_sydoc_js.py`.

- [ ] **Step 1: Failing test.** `tests/unit/test_nx_sydoc_js.py`, harness copied from `tests/unit/test_reporting_layout_view_js.py` (`SRC = Path("static/js/nx_sydoc.js")`, `global.window = { NX: {} }; global.document = {};`, `eval(...)`, `const V = window.NXSydoc;`):

```python
def _run(expr):
    js = _HARNESS + f"process.stdout.write(JSON.stringify({expr}));"
    return json.loads(subprocess.run([NODE, "-e", js, str(SRC)], capture_output=True, text=True, check=True).stdout)


def test_iso_week_matches_iso_8601():
    assert _run("[V.isoWeek('2026-09-21'), V.isoWeek('2026-01-01'), V.isoWeek('2027-01-03')]") == [39, 1, 53]


def test_period_headline_names_a_month_a_week_a_span_and_a_range():
    out = _run("""[
      V.periodHeadline('2026-08-01','2026-08-31','en'),
      V.periodHeadline('2026-09-21','2026-09-27','en'),
      V.periodHeadline('2026-06-01','2026-08-31','en'),
      V.periodHeadline('2026-08-04','2026-08-19','en')]""")
    assert out[0] == {"main": "August", "year": "2026", "kind": "month"}
    assert out[1] == {"main": "Week 39", "year": "2026", "kind": "week"}
    assert out[2] == {"main": "Jun – Aug", "year": "2026", "kind": "months"}
    assert out[3] == {"main": "4 – 19 Aug", "year": "2026", "kind": "range"}


def test_month_cells_mark_future_months_disabled():
    cells = _run("V.monthCells(2026, '2026-09-30', 'en')")
    assert [c["key"] for c in cells][:2] == ["2026-01", "2026-02"]
    assert cells[8]["future"] is False and cells[9]["future"] is True
    assert cells[0]["name"] == "Jan"
```

  The week label comes in through an argument so it stays translatable: `periodHeadline(from, to, lang, weekLabel = 'Week {n}')`.
- [ ] **Step 2:** `python -m pytest tests/unit/test_nx_sydoc_js.py -q`. It skips without Node (expected locally) and fails in any Node environment.
- [ ] **Step 3: Implement** `static/js/nx_sydoc.js` as an IIFE assigning `window.NXSydoc = { fmt, isoWeek, periodHeadline, monthCells, initPicker }`.
  - `isoWeek(iso)`: standard ISO-8601 (Thursday rule, UTC dates).
  - `periodHeadline(from, to, lang, weekLabel)`. Dates are parsed as UTC; use `Intl.DateTimeFormat(lang, {month:'long', timeZone:'UTC'})`, `{month:'short'}` and `{day:'numeric'}`.
    - Whole calendar month → `{main: long month, year, kind: 'month'}`.
    - Monday..Sunday span of 7 days → `{main: fmt(weekLabel,{n}), year: ISO-week year, kind:'week'}`.
    - First-of-month to end-of-month spanning more than one month in the same year → `'Jun – Aug'`.
    - Anything else → `'4 – 19 Aug'` (same month) or `'28 Jul – 3 Aug'`, year = `to`'s year.
    - Use the `–` en dash with thin spacing as in the README: `' – '`.
  - `monthCells(year, todayIso, lang)` returns 12 `{key:'YYYY-MM', name: short month, future: bool}`.
  - `initPicker({root, opener, onClose})`: shows `root` (remove `hidden`), traps Tab inside the panel, closes on Esc, a click on the overlay outside `__panel`, or `[data-role="picker-close"]`, and returns focus to `opener`. It returns `{open(), close()}` and is **only** called by page code. `opener.addEventListener('click', open)`.
  - `fmt` is the same `{name}` substitution both pages have today (moved here; the pages keep their local alias `const fmt = window.NXSydoc.fmt`).
- [ ] **Step 4:** The test passes wherever Node exists. Also run `python -m pytest tests/unit/test_static_v_lint.py tests/unit/test_template_url_prefix.py -q`.
- [ ] **Step 5:** Commit Tasks 4 and 5 together:

```
feat(ui): add shared Sydoc band macros and period-picker script (#<n>)

templates/_sydoc.html renders the brand row, the period headline with its
prev/next arrows and the picker shell; static/js/nx_sydoc.js holds the pure
period helpers (ISO week, headline text, month grid) and a focus-trapping
modal controller. Finance and BPS both use them, so the pair stays mirrored.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

# PHASE 2 — BPS backend: previous period and per-month hours

### Task 6: `bps.previous_range`

**Files:** Modify `nx_lib/bps.py`, `tests/unit/test_bps.py`.

- [ ] **Step 1: Failing test** (append to `tests/unit/test_bps.py`, which already imports `datetime as dt` and `nx_lib.bps as bps`; re-Grep the import lines first):

```python
def test_previous_range_is_the_previous_month_for_a_whole_month():
    assert bps.previous_range(dt.date(2026, 8, 1), dt.date(2026, 8, 31)) == (
        dt.date(2026, 7, 1), dt.date(2026, 7, 31))
    assert bps.previous_range(dt.date(2026, 3, 1), dt.date(2026, 3, 31)) == (
        dt.date(2026, 2, 1), dt.date(2026, 2, 28))


def test_previous_range_is_the_same_length_just_before_otherwise():
    assert bps.previous_range(dt.date(2026, 9, 21), dt.date(2026, 9, 27)) == (
        dt.date(2026, 9, 14), dt.date(2026, 9, 20))
    assert bps.previous_range(dt.date(2026, 6, 1), dt.date(2026, 8, 31)) == (
        dt.date(2026, 3, 1), dt.date(2026, 5, 31))
```

  (Jun 1–Aug 31 is 92 days, and the 92 days before end on May 31 and start on Mar 1.)
- [ ] **Step 2:** Run it and expect `AttributeError`: `python -m pytest tests/unit/test_bps.py -q -k previous_range`.
- [ ] **Step 3: Implement** below `range_filters` in `nx_lib/bps.py`:

```python
def previous_range(first, last):
    """The period a range is compared with ("vs. July"): the previous calendar
    month when the range is exactly one month, else as many days just before."""
    prev_last = first - dt.timedelta(days=1)
    whole_month = (
        first.day == 1
        and (last + dt.timedelta(days=1)).day == 1
        and (first.year, first.month) == (last.year, last.month)
    )
    if whole_month:
        return prev_last.replace(day=1), prev_last
    return prev_last - dt.timedelta(days=(last - first).days), prev_last
```

- [ ] **Step 4: `next_range`, the mirror (for the headline's next arrow).** Tests:

```python
def test_next_range_is_the_next_month_or_the_next_span_and_stops_at_today():
    today = dt.date(2026, 9, 30)
    assert bps.next_range(dt.date(2026, 8, 1), dt.date(2026, 8, 31), today) == (
        dt.date(2026, 9, 1), dt.date(2026, 9, 30))
    assert bps.next_range(dt.date(2026, 9, 14), dt.date(2026, 9, 20), today) == (
        dt.date(2026, 9, 21), dt.date(2026, 9, 27))
    assert bps.next_range(dt.date(2026, 9, 1), dt.date(2026, 9, 30), today) is None
```

  Implement below `previous_range`:

```python
def next_range(first, last, today=None):
    """The period after a range (the next month, or as many days after it), or
    None when it would start after today."""
    today = today or dt.date.today()
    start = last + dt.timedelta(days=1)
    if start > today:
        return None
    if first.day == 1 and start.day == 1 and (first.year, first.month) == (last.year, last.month):
        end = (start.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
        return start, end
    return start, start + dt.timedelta(days=(last - first).days)
```

  Next of September 2026 on 30 Sep 2026 is October, which starts after today, so the result is `None`. `parse_range` does not clamp the end to today; the inert arrow is what keeps the reader out of the future.
- [ ] **Step 5: Page hrefs.** In `bps_page()` add `prev_first, prev_last = bps.previous_range(first, last)` and `nxt = bps.next_range(first, last, today)`, then pass
  `prev_href=url_for("bps", **{"from": prev_first.isoformat(), "to": prev_last.isoformat()})` and
  `next_href=url_for("bps", **{"from": nxt[0].isoformat(), "to": nxt[1].isoformat()}) if nxt else None`
  (add `url_for` to the `flask` import).
- [ ] **Step 6:** Green. Commit `feat(bps): name the periods before and after a range (#<n>)`.

### Task 7: `bps.months_query` / `months_payload`

**Files:** Modify `nx_lib/bps.py`, `tests/unit/test_bps.py`.

- [ ] **Step 1: Failing tests.** These use the module-level `CATALOG` constant of `tests/unit/test_bps.py`. Planning verified that the builder emits exactly this SQL with `params == []` and a `[Datum] IS NULL OR [Datum] >= '19010101'` guard, so a NULL-month bucket can come back:

```python
def test_months_query_sums_hours_per_calendar_month():
    sql, params = bps.months_query("dbo.BPS_ProjectReportAll", CATALOG)
    assert "DATEFROMPARTS(YEAR([Datum]), MONTH([Datum]), 1)" in sql
    assert "GROUP BY" in sql and params == []


def test_months_payload_keys_by_yyyy_mm_and_drops_empty_months():
    rows = [(dt.date(2025, 1, 1), Decimal("12.5")), (dt.date(2026, 8, 1), Decimal("1300.5")),
            (dt.date(2026, 9, 1), None), (None, Decimal("3"))]
    assert bps.months_payload(rows) == {"2025-01": 12.5, "2026-08": 1300.5}
```

- [ ] **Step 2:** Run and see it fail.
- [ ] **Step 3: Implement** below `entries_query`:

```python
MONTHS_ROW_CAP = 1000


def months_query(base_object, catalog):
    """Hours per calendar month over the whole history -- the period picker's cells."""
    fields = _require(catalog, ("Datum", "Stunden"))
    resolved = resolve_metrics([{"metric": "hours"}], _TOTALS, fields)
    rd = {
        "columns": [{"field": "Datum", "grain": "month"}],
        "filters": [],
        "metrics": [{"metric": "hours"}],
        "sort": [],
    }
    return build_generic_query(
        rd, base_object, catalog, row_cap=MONTHS_ROW_CAP, resolved_metrics=resolved
    )


def months_payload(rows):
    """[(month start, hours)] -> {'YYYY-MM': hours}, months without hours left out."""
    out = {}
    for r in rows:
        value = _num(r[1])
        if value and r[0] is not None:
            out[_day(r[0])[:7]] = value
    return out
```

- [ ] **Step 4:** Green, plus the whole `tests/unit/test_bps.py`. Commit `feat(bps): sum the hours per month for the period picker (#<n>)`.

### Task 8: `/api/bps/summary` returns the previous period

**Files:** Modify `nx_lib/views/bps.py`, `tests/integration/test_bps_routes.py`.

- [ ] **Step 1: Failing integration test** (append; it uses the existing `fake_source` fixture, whose combos branch answers every `GROUP BY [Aufgabe], [Kunde], [Projektpaket], [Benutzer]` query):

```python
def test_summary_carries_the_previous_period_rows(admin_client, fake_source):
    body = admin_client.get("/api/bps/summary?from=2026-08-01&to=2026-08-31").get_json()
    assert body["prev"]["from"] == "2026-07-01" and body["prev"]["to"] == "2026-07-31"
    assert {r["task"] for r in body["prev"]["rows"]} == {"Change", "Vacation"}
    combos = [p for s, p in fake_source if "GROUP BY [Aufgabe], [Kunde]" in s]
    assert [p[:2] for p in combos] == [["2026-08-01", "2026-09-01"], ["2026-07-01", "2026-08-01"]]
```

  The last assertion pins the order: current first, then previous. If the combos SQL does not contain that exact `GROUP BY` text, copy the substring the existing fixture matches on.
- [ ] **Step 2:** It fails in CI (it cannot run locally, per Context). Do a local sanity check with a throwaway script that calls `bps.summary_queries` twice. Optional.
- [ ] **Step 3: Implement** in `api_bps_summary`. After `combos_q, days_q = bps.summary_queries(base_object, catalog, first, last)` add `prev_first, prev_last = bps.previous_range(first, last)` and `prev_q, _ = bps.summary_queries(base_object, catalog, prev_first, prev_last)`. In the execute `try`, add `prev_combos = _execute(engine, *prev_q)` **after** the two existing calls. After `payload = bps.summary_payload(...)`:

```python
    prev = bps.summary_payload(prev_combos, [], prev_first, prev_last)
    payload["prev"] = {"from": prev["from"], "to": prev["to"], "rows": prev["rows"]}
```

  Update the module docstring's first paragraph with one sentence: "…and the same rows for the period before it (the drill-down's gain/loss column)."
- [ ] **Step 4:** Run `python -m pytest tests/unit -q -p no:cacheprovider` locally; the integration test runs in CI. Commit `feat(bps): return the previous period's rows with the summary (#<n>)`.

### Task 9: `GET /api/bps/months`

**Files:** Modify `nx_lib/views/bps.py`, `tests/integration/test_bps_routes.py`.

- [ ] **Step 1: Failing tests.** Add `"/api/bps/months"` to the `test_bps_needs_bps_view` parametrize list. Extend the `fake_source` fixture's `execute` with a first branch `if "DATEFROMPARTS" in sql: return [(dt.date(2026, 7, 1), Decimal("10")), (dt.date(2026, 8, 1), Decimal("1.5"))]`, placed **before** the `GROUP BY [Datum]` branch. Then:

```python
def test_months_lists_hours_per_month(admin_client, fake_source):
    body = admin_client.get("/api/bps/months").get_json()
    assert body == {"months": {"2026-07": 10, "2026-08": 1.5}, "error": None}


def test_months_reports_an_unregistered_source_in_place(admin_client):
    body = admin_client.get("/api/bps/months").get_json()
    assert "bps_projects" in body["error"]
```

- [ ] **Step 2: Implement** a view after `api_bps_entries`:

```python
@require_permission("bps.view")
@limiter.limit("60 per minute")
def api_bps_months():
    try:
        base_object, catalog, engine, _label = _source()
        sql, params = bps.months_query(base_object, catalog)
    except LookupError as e:
        return _error(str(e))
    except (bps.BpsSpecError, TableQueryError) as e:
        return _error(gettext("This page does not match its registered source."), detail=str(e))
    try:
        rows = _execute(engine, sql, params)
    except Exception as e:
        current_app.logger.warning(f"bps: months query failed: {e}")
        return _error(gettext("Could not read the source."), detail=_db_detail(e))
    return jsonify({"months": bps.months_payload(rows), "error": None})
```

  Register it in `register_routes`: `app.add_url_rule("/api/bps/months", endpoint="api_bps_months", view_func=api_bps_months)`. Add `- GET /api/bps/months          hours per month (the period picker)` to the test module docstring's route list.
- [ ] **Step 3:** Unit tier green locally. Commit `feat(bps): serve hours per month for the period picker (#<n>)`.

---

# PHASE 3 — BPS front end

### Task 10: `static/js/bps_view.js` (pure drill-down logic)

**Files:** Create `static/js/bps_view.js`, `tests/unit/test_bps_view_js.py`.

`window.BpsView` exposes the functions below. `bps.js` keeps state and DOM only.

- [ ] **Step 1: Failing tests.** Same harness pattern, `SRC = Path("static/js/bps_view.js")`:

```python
def test_squarify_fills_the_area_and_keeps_order():
    rects = _run("V.squarify([{h:6},{h:6},{h:4},{h:3},{h:2},{h:2},{h:1}], 600, 400)")
    assert len(rects) == 7
    area = sum(r["w"] * r["h"] for r in rects)
    assert abs(area - 600 * 400) < 1e-6
    assert all(r["x"] >= -1e-9 and r["y"] >= -1e-9 and r["x"] + r["w"] <= 600 + 1e-6 and r["y"] + r["h"] <= 400 + 1e-6 for r in rects)
    assert [r["i"] for r in rects] == list(range(7))


def test_delta_says_new_flat_up_or_down():
    assert _run("[V.delta(5,0).dir, V.delta(0,0).dir, V.delta(12,10).dir, V.delta(9,10).dir]") == ["new", "flat", "up", "down"]
    assert _run("V.delta(12,10)") == {"dir": "up", "ratio": 0.2, "diff": 2}


def test_level_zooms_along_the_order_and_sums_prev():
    rows = "[{task:'A',customer:'X',person:'p',hours:3,count:1,category:'billable'},{task:'A',customer:'Y',person:'q',hours:1,count:2,category:'service'},{task:'B',customer:'X',person:'p',hours:2,count:1,category:'service'}]"
    prev = "[{task:'A',customer:'X',person:'p',hours:1,count:1,category:'billable'}]"
    top = _run(f"V.level({rows}, {prev}, ['Aufgabe','Kunde','Benutzer'], [])")
    assert [(g["key"], g["hours"], g["prev"]) for g in top] == [("A", 4, 1), ("B", 2, 0)]
    assert top[0]["billable"] == 3 and top[0]["cat"] == "partly"
    zoomed = _run(f"V.level({rows}, {prev}, ['Aufgabe','Kunde','Benutzer'], ['A'])")
    assert [g["key"] for g in zoomed] == ["X", "Y"]


def test_by_day_groups_entries_and_totals_them():
    out = _run("V.byDay([{date:'2026-08-03',hours:1.5},{date:'2026-08-03',hours:0.5},{date:'2026-08-04',hours:2}])")
    assert [(d["date"], d["hours"], len(d["entries"])) for d in out] == [("2026-08-03", 2, 2), ("2026-08-04", 2, 1)]
```

- [ ] **Step 2:** Run it: it skips without Node and fails with Node.
- [ ] **Step 3: Implement**:
  - `squarify(items, W, H)`: port the prototype's loop (anchor in `Sydoc BPS.dc.html`: `const worst = (rw, side) =>` and `const place = rw =>`), made pure. It takes `items` already sorted by `h` desc and returns `[{i, x, y, w, h}]` in item order. The caller applies the 4px GAP when it draws.
  - `delta(value, prev)` returns `{dir:'new'|'flat'|'up'|'down', ratio, diff}`. `prev === 0 && value > 0` → `new`, equal → `flat`. Round `ratio` and `diff` to 4 places so the floats compare exactly in tests.
  - `category(g)` returns `'billable'` when `billable === hours`, `'absence'` when `absence / hours > .5`, `'partly'` when `billable > 0`, and `'service'` otherwise. These are the README table-marker and treemap-tile colour rules.
  - `level(rows, prevRows, order, path)`:
    1. Filter both row sets by `path` (dims = `order.slice(0, path.length)`, field map `{Aufgabe:'task', Kunde:'customer', Benutzer:'person'}`, as `FIELD` in `bps.js`).
    2. Group by `order[path.length]`.
    3. Return `[{key, hours, billable, service, absence, count, prev, cat}]` sorted by hours desc, then key.
  - `byDay(entries)`: groups in date order and returns `[{date, hours, count, entries}]`.
- [ ] **Step 4:** Green where Node exists. Commit `feat(bps): add pure drill-down helpers (squarify, deltas, levels) (#<n>)`.

### Task 11: BPS page markup (band, picker, chart, drill-down shells)

**Files:** Modify `templates/bps.html`, `tests/integration/test_bps_routes.py`.

- [ ] **Step 1: Failing integration test.** Change `test_bps_page_renders_and_is_in_the_sidebar` to additionally assert:

```python
    assert 'class="nx-app nx-sydoc"' in html
    assert 'data-testid="bps-period-picker"' in html and 'data-testid="bps-period"' in html
    assert 'data-testid="bps-period-button"' in html
    assert "from=2026-07-01" in html and "from=2026-09-01" in html  # prev/next arrows
    assert 'data-testid="bps-kpis"' in html and 'data-testid="bps-tree"' in html
    assert 'data-testid="bps-view"' in html
```

  Keep the existing `value="2026-08-01"` / `value="2026-08-31"` asserts: the picker's range inputs carry them.
- [ ] **Step 2: Rewrite the `<main>`** of `templates/bps.html` (keep `<head>` and add `<link>`/`<script>` for nothing new; the shared CSS is in `nexora-ui.css`). Change `<body class="nx-app">` to `<body class="nx-app nx-sydoc">`. Add `{% import '_sydoc.html' as sydoc with context %}`. Structure, per README "Screen: Sydoc BPS":
  1. `<section class="nx-sydoc-band nx-rise" data-testid="bps-band">`:
     - Row 1: `sydoc.brand(_("BPS"))`, spacer, `bps-finance-link` (`nx-sydoc-btn nx-sydoc-btn--link`, only `{% if can_finance %}`), `bps-export` / `bps-export-csv` (ghost; keep the `id` and `href` expression).
     - Row 2: `sydoc.headline(_("Sydoc BPS"), "bps", range_from ~ " – " ~ range_to, "", prev_href, next_href, _("Previous period"), _("Next period"), "bps-picker")`. `prev_href`/`next_href` come from `bps_page()` (Task 6 Step 5). `bps.js` replaces the fallback main/year text with the `periodHeadline()` result.
     - Then the hint `<p class="nx-sydoc-hint">` with the existing sentence "Every hour booked in the BPS timetool, by task, customer and person, down to the single booking."
     - Then `.nx-sydoc-stats`: **Period** (`data-role="range-text"`) and **Source** (`id="bps-status"` with `role="status"` and `data-testid="bps-status"`, holding `<span class="nx-sydoc-dot">` plus `<span id="bps-status-text">`).
     - Divider `<hr class="nx-bps-band__rule">`, totals `<div class="nx-bps-totals" id="bps-kpis" data-testid="bps-kpis" aria-busy="true">` (skeleton spans inside), composition bar `<div class="nx-bps-comp" id="bps-comp" aria-hidden="true">` and labels `<div class="nx-bps-comp__labels" id="bps-comp-labels">`.
  2. `#bps-error` (unchanged markup) directly under the band.
  3. **Picker**: `sydoc.picker_open("bps-picker", _("Choose period"), wide=True)` with `data-testid="bps-period-picker"`. Inside:
     - Quick pills: 4 × `<button type="button" class="nx-sydoc-pill" data-preset="last-month|this-month|last-week|quarter">`, the same keys as `PRESETS`.
     - Year switcher: `data-role="year-prev|year|year-next"`.
     - `<div class="nx-sydoc-picker__grid nx-sydoc-picker__grid--compact" data-role="months">`.
     - Footer: **the existing GET form** `<form id="bps-period" method="get" action="{{ url_for('bps') }}" data-testid="bps-period">`, with `bps-from` / `bps-to` date inputs (same `name`, `value`, `max`, `required`, testids) and `<button type="submit" class="nx-sydoc-btn nx-sydoc-btn--ink">{{ _("Show range") }}</button>`.
     - Close with `sydoc.picker_close()`.
  4. Chart section: head (`h2#bps-chart-title` "Hours per day", `#bps-chart-meta`) plus `.nx-bps-chart__canvas` with the **same** `<canvas id="bps-chart" …>` including its `aria-label`.
  5. Drill-down `<section class="nx-bps-explorer" data-testid="bps-tree" id="bps-tree">`.
     - Toolbar: title; `<div class="nx-track" id="bps-order" data-testid="bps-order" role="group">` with the three existing `data-order` buttons (class `nx-track__btn`); spacer; two chip `<button type="button" class="nx-bps-chip" aria-pressed>` elements with `id="bps-billable-only"` / `id="bps-hide-absences"` and the same testids (hide-absences `aria-pressed="true"`); the search `label.nx-bps-search` (same input id/testid).
     - Crumb row: `<div class="nx-bps-crumbs">` with `<button id="bps-back" class="nx-bps-back" hidden aria-label="{{ _('Up one level') }}">`, `<nav id="bps-crumbs" aria-label="{{ _('Drill-down path') }}">`, spacer, `<span id="bps-level-meta">`, and `<div class="nx-track" id="bps-view" data-testid="bps-view">` with `data-view="table"` (`fa-list`, "Table") and `data-view="map"` (`fa-table-cells-large`, "Treemap").
     - Body: `<div id="bps-drill" aria-live="polite"></div>`.
     - Legend row `#bps-legend`: three swatches plus `<span id="bps-legend-hint">`.
     - The existing `p.nx-bps-rule` with its exact `_()` call. **Do not change that msgid.**
- [ ] **Step 3:** Remove the old `.nx-bps-head`, the old form row, `.nx-kpi-strip`, and the `<table id="bps-tree">`. Their ids now live on the new elements.
- [ ] **Step 4:** Commit with Tasks 12–19 (the page is broken until `bps.js` is rewritten; keep them one coherent commit series and do not push in between).

### Task 12: BPS shim strings

**Files:** Modify `templates/js/_bps_js.html`.

- [ ] **Step 1:** Add `months: null` to `window.NX_BPS` (filled lazily from `/api/bps/months`).
- [ ] **Step 2:** Add these strings, all `{name}` placeholders:
  - `weekLabel: _("Week {n}")`, `rangeText: _("{from} – {to}")`, `bookingsLoaded: _("{n} bookings loaded")`
  - `ofHours: _("{pct} of all hours")` (exists as `ofTotal`; reuse it and add no duplicate)
  - `vsPrev: _("vs. {period}")`, `notBooked: _("not booked in {period}")`, `isNew: _("New")`
  - `colHours: _("Hours")` (exists), `colBillable: _("Billable")` (reuse `catBillable`), `colBookings: _("Bookings")` (exists as `bookings`), `split: _("Split")`
  - `allOf: { Aufgabe: _("All tasks"), Kunde: _("All customers"), Benutzer: _("All people") }`
  - `plural: { Aufgabe: _("{n} tasks"), Kunde: _("{n} customers"), Benutzer: _("{n} people") }`, `levelMeta: _("{items} · {h}")`, `leafMeta: _("{h} · {n} bookings")`
  - `showMore: _("Show {n} more")`, `showFewer: _("Show fewer")`, `noComment: _("No comment")`
  - `hintTable: _("Bar length is hours relative to the largest row; colours are its split. Click a row to zoom in.")`
  - `hintMap: _("Tile size is hours; the strip under each tile is its split. Click a tile to zoom in.")`
  - `chartMeta: _("{days} days · {n} h · weekends shaded")` (**replaces** the old `chartMeta` msgid)
  - `noData: _("No data")`, `runningH: _("Running · {h}")`, `hUnit: _("{n} h")` (exists as `h`)
- [ ] **Step 3:** Change `emptyPeriod` to `_("Nothing was booked in this period. The BPS history starts in January 2025.")` (fixes the #424 drift).
- [ ] **Step 4:** Remove strings that are no longer used: `colDate`, `colPackage`, `colComment`, `expand`, `partly`, `billableTag`, `dayTotal` **only if** Grep confirms `bps.js` no longer references them after Task 13–19. Do that sweep in Task 19.

### Task 13: `bps.js`, band totals and composition bar

**Files:** Modify `static/js/bps.js`, `templates/bps.html` (script tags).

- [ ] **Step 1:** In `templates/js/_bps_js.html`, load `nx_sydoc.js` and `bps_view.js` **before** `bps.js` (both with `static_v()`, the `csp_nonce()` nonce and `defer`).
- [ ] **Step 2:** Replace `kpisHtml(t)` with `totalsHtml(t)` per README "Band (below Row 2)":
  - Total hours: the eyebrow `S.totalHours`, `hours(t.hours)` at `.nx-bps-totals__big`, and the `h` suffix.
  - A 3-col grid: Service hours with `fmt(S.ofTotal, …)`, Bookings, and People with `S.withHours`.
  - Keep `data-testid="bps-kpi-total|service|bookings|people"` on the cells.
- [ ] **Step 3:** Add `compHtml(t)`. It emits three `<span class="nx-bps-comp__seg nx-bps-comp__seg--billable|service|absence" style="width:X%">` (widths = share of `t.hours`) and the labels grid with `grid-template-columns` set to the same percentages. Each cell holds a swatch, a label, `{h} h` and a suffix. Billable's suffix is `fmt(S.ofService, …)`; the other two use `fmt(S.ofTotal, …)`.
- [ ] **Step 4:** In `load()`, replace `kpis.innerHTML = kpisHtml(p.totals)` with the totals and comp render. Status text becomes `fmt(S.bookingsLoaded, {n})`, with the green dot class `nx-sydoc-dot--live` on success and `--failed` on error. `data-role="range-text"` gets `fmt(S.rangeText, {from: formatDate(p.from), to: formatDate(p.to)})`.

### Task 14: `bps.js`, chart restyle

- [ ] **Step 1:** In `drawChart()`, per README "Hours per day":
  - `scales.y.ticks.display = false`.
  - Grid: `y.grid` becomes `{ color: token('--nx-divider'), borderDash: [3, 3], drawTicks: false }`, with `y.ticks.maxTicksLimit` driving 2 lines. Simplest route: `afterBuildTicks: ax => { ax.ticks = [{value:0},{value:ax.max/2}] }`.
  - `x.ticks.callback` returns the day number (`isoDate(days[i].date).getDate()`), `font.size = 10.5`.
  - `maxBarThickness` becomes `Math.max(4, (canvas.clientWidth / days.length) - 6)`.
  - Billable colour: the chart keeps `--bps-billable` (`#7c3aed` light).
- [ ] **Step 2:** Add an inline plugin `{id:'nxWeekends', beforeDatasetsDraw(c){…}}`. It fills `#f3f4f6` (dark: `token('--nx-alt')`) behind every Saturday/Sunday column. Use `c.scales.x.getPixelForValue(i)` ± half the category width, with a 4px top radius via `ctx.roundRect` where it exists.
- [ ] **Step 3:** Meta text becomes `fmt(S.chartMeta, {days, n})`. The tooltip is unchanged.

### Task 15: `bps.js`, drill state, breadcrumb, keyboard

- [ ] **Step 1:** Replace `state.open` with `state.path = []` and add `state.view` (read via `try { localStorage.getItem('nx.bps.view') } catch {}`, default `'table'`) and `state.prevRows` (from `p.prev.rows`, `[]` if absent). Remove `buildTree`, `sorted`, `rowsHtml`, `renderTree`, `tagHtml` and `shareHtml` after their replacements land.
- [ ] **Step 2:** `render()` does the following:
  1. `const groups = BpsView.level(visibleRows(), visiblePrev(), state.order, state.path)`. `visiblePrev()` applies the same filters to `state.prevRows`.
  2. Crumbs: `S.allOf[state.order[0]]`, then each path key, separated by `<i class="fas fa-chevron-right">`. Earlier crumbs are `<button data-depth="k">`; the current crumb is `<span aria-current="page">`. `#bps-back` is hidden at depth 0.
  3. Level meta: `fmt(S.levelMeta, {items: fmt(S.plural[dim], {n}), h})`.
  4. At `state.path.length === state.order.length` it renders the leaf (Task 18). Otherwise it renders table or map.
  5. The legend hint follows the view.
- [ ] **Step 3:** Events:
  - A click on `[data-zoom]` (row or tile) runs `state.path.push(key)` and then `render()`, then focuses the first focusable element in `#bps-drill`.
  - A crumb click runs `state.path.length = depth`. `#bps-back` pops one level.
  - `keydown` on `#bps-drill`: `Backspace` (when not typing in an input) or `Alt+ArrowLeft` pops one level.
  - Order change, and search input after the 150ms debounce, run `state.path = []`.
  - Chip buttons toggle `aria-pressed` and set `billableOnly` / `hideAbsences`. The filters apply at every level.
  - View track: set `state.view`, `try { localStorage.setItem(...) } catch {}`, re-render, update `aria-pressed`.
- [ ] **Step 4:** Keep `entriesCache` keyed by the path string (`path.join('␟')`).

### Task 16: `bps.js`, table view

- [ ] **Step 1:** `tableHtml(groups, dim)` per README "Table view":
  - A header grid with `S.names[dim]`, `S.colHours`, `S.catBillable`, `S.bookings`, `fmt(S.vsPrev, {period: prevName})` and `S.split`.
  - One `<button type="button" class="nx-bps-trow" data-zoom="${esc(key)}">` per group with: the marker `.nx-bps-mark--${g.cat}`, name, hours (mono), billable (`·` when 0), count, the vs cell and the split track.
  - The vs cell uses `BpsView.delta`. Icon `fa-arrow-trend-up|down|minus`; class `is-up|is-down|is-flat`; line 2 is `+12.5 h` / `−3.0 h`, or `fmt(S.notBooked, {period})` when `prev === 0`, or `S.isNew` on line 1.
  - The split track bar width is `g.hours / groups[0].hours`, with 3 inner segments by `billable/service/absence` and the pct of the level total.
  - Closing chevron cell.
  - A total row of class `nx-bps-trow nx-bps-trow--total` (a `<div>`, not a button).
- [ ] **Step 2:** `prevName`: when `p.prev` is a whole month (use `NXSydoc.periodHeadline(prev.from, prev.to, lang).kind === 'month'`), it is the long month name ("July"). Otherwise it is the short range text from the same helper (`main`).

### Task 17: `bps.js`, treemap view

- [ ] **Step 1:** `mapHtml(groups)`:
  - Measure `#bps-drill`'s `clientWidth` (W) and use H = 440.
  - `BpsView.squarify(groups.map(g => ({h: g.hours})), W, H)`.
  - For each rect, emit `<button type="button" class="nx-bps-tile nx-bps-tile--${g.cat}" data-zoom=… title="${name} · ${h} h · ${n} bookings" style="left:${x}px;top:${y}px;width:${w-4}px;height:${h-4}px">`.
  - Text block only when w > 70 and h > 46; the `--big` class when w > 220 and h > 110; the delta pill when w > 110 and h > 70 (`↗ +8% vs. July`).
  - Split strip `.nx-bps-tile__strip` with 3 flex segments.
- [ ] **Step 2:** Re-render the map on `resize` (debounced 150ms) only while `state.view === 'map'`.

### Task 18: `bps.js`, leaf per-day list, picker wiring, headline

- [ ] **Step 1: Leaf.** `leafHtml(res)`:
  - Filter the entries as `entriesHtml` does today, then `BpsView.byDay(list)`.
  - One `.nx-bps-day` block per day. Left column (sticky): `3 Aug` + `MON`, the day total (mono) and `{n} bookings`. Right column: 30px rows `.nx-bps-bk` (`comment` with `title`, or `S.noComment` italic; `package`; hours with 2 decimals).
  - Show the first 5 per day. Add `<button class="nx-bps-more" data-day="…">` with `fmt(S.showMore, {n})` / `S.showFewer`, toggling a `state.openDays` Set.
  - Level meta at the leaf is `fmt(S.leafMeta, {h, n})`, computed from **the listed entries**, as the README requires.
  - `truncated` → `S.entriesCut`.
  - Load through the existing `loadEntries` (path → params via `PARAM`); keep the cache.
- [ ] **Step 2: Headline.** On init, `const hl = NXSydoc.periodHeadline(CFG.from, CFG.to, lang, S.weekLabel)` fills `[data-role="period-main"]` / `[data-role="period-year"]`.
- [ ] **Step 3: Prev/next** hrefs are rendered by the server (Task 6 Step 5, D11), so no JS is needed.
- [ ] **Step 4: Picker.**
  - `NXSydoc.initPicker({root: document.getElementById('bps-picker'), opener: document.querySelector('[data-testid="bps-period-button"]')})`.
  - On first open, fetch `/api/bps/months` (via `NX.apiSafe`) into `CFG.months` and render `NXSydoc.monthCells(viewYear, CFG.today, lang)`.
  - Cell status: `fmt(S.hUnit, {n: hours(v)})`; the current month is `fmt(S.runningH, …)`; no hours → `S.noData` + `disabled`; future → `disabled`; the month matching `CFG.from`/`CFG.to` → `is-selected`.
  - A cell click sets `bps-from`/`bps-to` to that month and runs `form.requestSubmit()`.
  - The year buttons move `viewYear`.
  - Pills: move the existing `PRESETS` handling from `form.querySelectorAll('[data-preset]')` to `#bps-picker [data-preset]`, with the same active computation and `is-active` class.
- [ ] **Step 5:** Remove the old `form.querySelectorAll('[data-preset]')` block once the picker version works.

### Task 19: `static/css/bps.css`, rewrite

**Files:** Modify `static/css/bps.css`.

- [ ] **Step 1:** Keep the `--bps-*` token block at the top (both themes). Delete rules for the removed markup: `.nx-bps-head*`, `.nx-bps-filter*`, `.nx-bps-kpis`, `.nx-bps-tree*`, `.nx-bps-row*`, `.nx-bps-toggle`, `.nx-bps-tag*`, `.nx-bps-share*` and `.nx-bps-e*`. Grep each against the new templates and JS before deleting.
- [ ] **Step 2:** Add, with every value from README "Screen: Sydoc BPS":
  - `.nx-bps-band__rule` (1px `var(--nx-sydoc-band-line)`, `margin:24px -30px 0`, no border).
  - `.nx-bps-totals` / `__big` (40px/600/−1.6px) / `__grid` (3 cols gap `4px 40px`) / `__v` (20px/600/−.6px).
  - `.nx-bps-comp` (14px, r7, gap 3px, flex), `__seg--billable {background:#8b5cf6}` (band hue), `--service`, `--absence`, `__labels`.
  - `.nx-bps-chart` (margin-top 30px), `__canvas {height:220px}`.
  - `.nx-bps-explorer` (margin-top 34px), `.nx-bps-toolbar`, `.nx-bps-chip` (off/on per README, with `::before` swatch), `.nx-bps-search` (240×31, r99).
  - `.nx-bps-crumbs`, `.nx-bps-back`.
  - `.nx-bps-trow` grid `minmax(0,1fr) 100px 100px 90px 120px 220px 28px` and gap `0 12px`; hover `var(--nx-alt)`; `--head`, `--total`; `.nx-bps-mark--billable|partly|service|absence`; `.is-up {color:var(--nx-gain)}` / `.is-down {color:var(--nx-loss)}`.
  - `.nx-bps-split`.
  - `.nx-bps-map {position:relative;height:440px;margin-top:10px}`, `.nx-bps-tile` (absolute, r10, the tint/text triplets per README, hover `filter:brightness(.96)`), `__strip`, `__pill`.
  - `.nx-bps-day` (grid `96px minmax(0,1fr)`, gap 20px), `__when {position:sticky;top:0}`, `.nx-bps-bk` (30px grid `minmax(0,1fr) 180px 64px`), `.nx-bps-more` (`var(--nx-sydoc-ink-text)`).
  - `.nx-bps-legend`.
  - Dark: tile tints via `color-mix(in srgb, var(--bps-*) 22%, var(--nx-card))` under `html.dark`.
  - `@media (max-width: 1023px)`: the table grid drops the Split column and the totals grid wraps.
- [ ] **Step 3:** Sweep the unused shim strings (Task 12 Step 4). Grep `S\.<name>` in `static/js/bps.js` for each candidate.
- [ ] **Step 4:** Run `python -m pytest tests/unit -q -p no:cacheprovider`. `test_translations.py` fails until Task 20; that is expected.

### Task 20: BPS i18n, browser check, commit

- [ ] **Step 1:** `/nx-i18n` (extract → update → translate de/fr/it → compile). New msgids come from Tasks 4, 11 and 12 (for example "Sydoc internal", "BPS", "Choose period", "Quick", "Show range", "Table", "Treemap", "Split", "All tasks", "Week {n}", "No comment", "Show {n} more", "vs. {period}", "not booked in {period}", "Up one level", "Drill-down path", "Close", "Previous period", "Next period"). Keep German accounting terms consistent with existing `.po` entries (grep `msgid "Billable"` for the chosen `de` term).
- [ ] **Step 2:** `python -m pytest tests/unit -q -p no:cacheprovider` is green, including `test_translations.py`.
- [ ] **Step 3:** `/nx-ui-verify` on `/bps?from=2026-08-01&to=2026-08-31` (INT has data from 2025), light and dark. Screenshots go to `var/screenshots/`. Check against `Sydoc BPS.dc.html` 1a:
  - band, headline "August 2026", prev/next (next goes to September, and is inert when that is past today)
  - picker (months with hours, "No data" before Jan 2025, quick pills, range form submits `?from=&to=`), Esc and outside-click close, focus returns
  - chart weekends
  - table default, zoom 3 levels to the leaf, Backspace up, crumbs, treemap toggle persisted across a reload
  - chips/search reset the path
  - the vs column shows July
  - leaf meta equals the listed sum
  - no console errors, no horizontal scroll at 1024px
- [ ] **Step 4:** Commit Tasks 11–20 as one commit:

```
feat(bps): redesign the Sydoc BPS page as the Sydoc-branded pair (#<n>)

Ink band with the period headline, totals and a composition bar; a period
picker with hours per month and the old presets; weekends shaded in the daily
chart; and a zoomable drill-down (Table by default, or a squarified Treemap)
with gain/loss against the previous period and a compact per-day list of
bookings at the leaf. The view choice is remembered per browser.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

# PHASE 4 — Finance (starts only after #423 is on `main`)

### Task 21: Gate, rebase on #423

- [ ] **Step 1:** `git fetch origin main`, then `git log origin/main --oneline | Select-String "#423"`. If #423 is not merged, **stop here** and hand off. Do not proceed into Finance.
- [ ] **Step 2:** `git rebase origin/main`. On conflicts in `translations/*` or `messages.pot`, take `origin/main`'s version and regenerate with `/nx-i18n` after the rebase. Never hand-merge them.
- [ ] **Step 3:** Re-read `templates/finance.html` (the `#fin-bexio` section), `templates/js/_finance_js.html` (the `bexio:` block and the second `<script>`), `static/css/finance.css` (`.nx-fin-bexio*`) and `static/js/finance_bexio.js`: its selectors for `[data-role="meta"]`, `[data-role="body"]` and `#fin-bexio-refresh`. D14 must keep exactly those selectors working.
- [ ] **Step 4:** If #423 was abandoned instead (Owner action 2), skip every Bexio item in Tasks 23–27.

### Task 22: `Section.nav` short label

**Files:** Modify `nx_lib/finance.py`, `tests/unit/test_finance.py`.

- [ ] **Step 1: Failing test:**

```python
def test_every_section_has_a_short_nav_label():
    labels = {d["key"]: d["nav"] for d in finance.section_descriptors()}
    assert labels["privera_invoice"] == "Rechnungen"
    assert labels["privera_nachsendungen"] == "Zustellung"
    assert labels["xpert"] == "Xpert"
    assert labels["bucherer"] == "EasyTax"
    assert labels["compass"] == "Compass"
    assert labels["frigemo"] == "Frigemo"  # falls back to the client
    assert all(labels.values())
```

  (Check the module's import alias first, for example `from nx_lib import finance` or `import nx_lib.finance as finance`.)
- [ ] **Step 2:** Run and see it fail with a `KeyError` on `nav`.
- [ ] **Step 3: Implement.**
  - Add `nav: str | None = None` to `class Section` (after `link`).
  - Set `nav=` on: `compass` ("Compass"), `privera_posteingang` ("Posteingang"), `privera_invoice` ("Rechnungen"), `privera_nachsendungen` ("Zustellung"), `privera_neuzugaenge` ("Neuzugänge"), `xpert` ("Xpert"), `bucherer` ("EasyTax") and `bps` (`N_("Billable services")`, translated like `title`).
  - In `section_descriptors()` add `"nav": s.nav or s.title or s.client`.
  - In the `finance()` view's descriptor loop, translate `nav` like `title`: `d["nav"] = translate(d["nav"])`. The client names are proper nouns, and gettext returns an unknown msgid unchanged.
- [ ] **Step 4:** Green. Commit `feat(finance): give each section a short jump-index label (#<n>)`.

### Task 23: Finance view, month states and headline parts

**Files:** Modify `nx_lib/views/finance.py`, `tests/integration/test_finance_routes.py`.

- [ ] **Step 1: Failing test changes.**
  - In `test_finance_page_renders_every_section_shell`, replace `assert 'value="2026-08" selected' in html` with `assert 'data-month="2026-08"' in html`, `assert 'data-testid="finance-period-button"' in html` and `assert 'class="nx-app nx-sydoc"' in html`. Keep the `month=2026-07` (prev arrow) and `export.csv?month=2026-08` asserts.
  - In `test_finance_page_ignores_a_garbage_month`, replace the `finance-month-select` assert with `'data-testid="finance-period-button"'`.
  - Add `test_finance_page_marks_closed_months_for_the_picker`: monkeypatch `nx_lib.views.finance._closed_months_safe` to return `{"2026-07"}`, GET `/finance?month=2026-08`, and assert `'"state": "closed"' in html`. There is no DB round trip.
- [ ] **Step 2: Implement.**
  - Add `_closed_months()` next to `_closed()`: `SELECT DISTINCT Month FROM dbo.FinanceMonthClose`, returning a set. Add a `_closed_months_safe()` wrapper modelled on `_closed_safe` (logs and returns `set()`).
  - In `finance()`: build `months=[{"value": key, "label": _month_label(y, m), "name": format_date(dt.date(y, m, 1), "LLL"), "state": "running" if (y, m) == (today.year, today.month) else ("closed" if key in closed_months else "open")} for key, y, m in month_options(today)]`.
  - Pass `month_name=format_date(dt.date(year, month, 1), "LLLL")` and `month_year=str(year)`.
  - Set `prev_month=None` when `month_key(prev_y, prev_m)` is not among the option keys (D11).
  - The template renders `data-month="{{ month }}"` on the picker root.
- [ ] **Step 3:** In the shim, `months: {{ months|tojson }}` (it replaces the `<select>` options).
- [ ] **Step 4:** Unit tier green. Integration runs in CI.

### Task 24: Finance page markup (band, jump index, picker, ledger shells)

**Files:** Modify `templates/finance.html`.

- [ ] **Step 1:** Set `<body class="nx-app nx-sydoc">` and add `{% import '_sydoc.html' as sydoc with context %}`.
- [ ] **Step 2:** Replace `.nx-fin-head` and `.nx-fin-filter` with `<section class="nx-sydoc-band nx-sydoc-band--flush nx-rise" data-testid="finance-band">`:
  - Row 1: `sydoc.brand(_("Accounting"))`, spacer, then `#fin-close-toggle`, keeping `id`, `aria-*`, `data-action` and `data-testid="finance-close-toggle"` (class `nx-sydoc-btn nx-sydoc-btn--primary`, same `{% if closed %}` icon/label branches). Then the CSV link (ghost, same `href`, `finance-export-csv`) and `#fin-print` (ghost, `finance-print`).
  - Row 2: `sydoc.headline(_("Sydoc Finance"), "finance", month_name, month_year, prev_href, next_href, …)`, where the hrefs are `url_for('finance', month=prev_month)` when set. Testids come out as `finance-month-prev`, `finance-month-next` and `finance-period-button`.
  - Hint `<p class="nx-sydoc-hint">` with the **exact three existing** `{% if is_current_month %}…{% elif closed %}…{% else %}…{% endif %}` msgids.
  - Stats:
    - **Status**: running → amber dot + `_("Running")`; closed → `fa-lock` + the existing `_("Closed %(when)s by %(who)s", …)`, keeping `data-testid="finance-closed-badge"` on that span; else → green dot + `_("Open · live")`.
    - **Sources**: `id="fin-status" role="status" data-testid="finance-status"` with `#fin-status-text`. Its `is-failed` class colours it danger.
  - Jump index `<nav class="nx-fin-jump" aria-label="{{ _('Sections') }}">`. Per group: `<a class="nx-fin-jump__item nx-fin-jump__item--{{ s.group }}" href="#fin-{{ s.key }}" title="{{ s.client }}{% if s.title %} · {{ s.title }}{% endif %}"><span class="nx-fin-jump__tile">{{ s.client[:2] }}</span><span class="nx-fin-jump__label">{{ s.nav }}</span></a>`, with `<span class="nx-fin-jump__sep" aria-hidden="true"></span>` between groups. The Bexio entry (`#fin-bexio`, tile `Bx`, label `_("Bexio")`) goes last in the services group (D14).
- [ ] **Step 3:** `#fin-confirm` stays unchanged, directly under the band.
- [ ] **Step 4: Picker.** `sydoc.picker_open("fin-picker", _("Choose month"))` with `data-month="{{ month }}"`, the year switcher and `data-role="months"` grid (filled by JS from `CFG.months`), then the legend: `fa-lock` "Closed, figures frozen" · green dot "Open, live" · amber dot "Still running". Close with `sydoc.picker_close()`.
- [ ] **Step 5: Group headers.** `<div class="nx-fin-group nx-rise-3"><h2>{{ _("Internal customers") }}</h2><span class="nx-fin-group__count">{{ internal_sections|length }}</span><span class="nx-fin-group__rule"></span></div>`, and the same for External / Services.
- [ ] **Step 6: `section_shell(s)` macro.**
  - Wrapper: `<section class="nx-fin-section nx-fin-section--{{ s.group }}" id="fin-{{ s.key }}" data-key … data-testid="finance-section-{{ s.key }}" aria-busy="true">`.
  - Left `<div class="nx-fin-id">`: `<h3 class="nx-fin-id__client">{{ s.client }}</h3>`, `{% if s.title %}<p class="nx-fin-id__title">{{ s.title }}</p>{% endif %}`, `<p class="nx-fin-id__meta" data-role="meta">`, `<div class="nx-fin-id__state" data-role="state">`, `<p class="nx-fin-id__note" data-role="note" hidden>`.
    - When `s.link and page_visibility.bpsPagePerm`, add `<a class="nx-fin-bpsbtn" href="{{ url_for(s.link) }}" data-role="month-link" data-testid="finance-section-link-{{ s.key }}">{{ _("All hours in Sydoc BPS") }} <i class="fas fa-arrow-right"></i></a>`.
  - Right `<div class="nx-fin-lines" data-role="body">` with the skeleton: 3 × `.nx-fin-skel__line` (shimmer).
  - Drop `.nx-fin-section__tile`.
- [ ] **Step 7: Bexio section (D14).** Same two-column shape. Identity: client `_("Bexio")`, title `_("Invoices")`, `data-role="meta"`, and the refresh button `#fin-bexio-refresh` moved under the meta. The right column is `data-role="body"`. Keep `id="fin-bexio"`, `data-testid="finance-bexio"` and `aria-busy`.

### Task 25: Finance shim and `finance.js`

**Files:** Modify `templates/js/_finance_js.html`, `static/js/finance.js`.

- [ ] **Step 1: Shim.**
  - Add `months`, `strings.figure` ("Figure"), `strings.change` ("Change"), `strings.prevMonthName` (server: `format_date` of the previous month, "LLLL"), `strings.monthName` (`month_name`), `strings.noComment`, `strings.showAllN` ("Show all {n}"), `strings.billableBookings` ("Billable bookings"), `strings.oneListPer` ("one list per customer, as on the invoice"), `strings.perDim` (exists as `per`; reuse), `strings.closedShort` ("Closed"), `strings.openShort` ("Open"), `strings.running` ("Running").
  - Load `nx_sydoc.js` before `finance.js`. Keep the Bexio `<script>` and `bexio:` block untouched.
- [ ] **Step 2: Remove** the `// ---- month picker` block (the `select` change handler). Add `NXSydoc.initPicker` on `#fin-picker`. The grid is 12 cells from `NXSydoc.monthCells(viewYear, …)`, merged with `CFG.months` by key:
  - a cell absent from `CFG.months` is `disabled`
  - status per `state` (`fa-lock` + `S.closedShort` / dot + `S.openShort` / dot + `S.running`)
  - `CFG.month` is `is-selected`
  - a click navigates to `?month=` exactly like the removed handler (`new URL(window.location.href)` + `searchParams.set`)
  - the year switcher stays within the years present in `CFG.months`
- [ ] **Step 3: Statement lines.** Replace `figuresHtml(figures)` with `linesHtml(figures)`:
  - A header grid with `S.figure`, `S.monthName`, `S.prevMonthName` and `S.change`.
  - Per figure: `<div class="nx-fin-line" data-testid="finance-figure-${code}">` with the label, `<span class="nx-fin-line__value" data-value>` (mono 17px), prev (mono 13px) and change.
  - Change is the comparison bar: a track, a fill at `value / max(value, prev)`, and a `.nx-fin-cmp__prev` marker at `prev / max − 1px`.
  - Keep `deltaHtml`'s rules (unchanged / new / ±%) but render them as `<span class="nx-fin-delta">▲ +5%</span>`: neutral ink, `▲`/`▼` prefix, `S.unchanged` / `S.isNew` wording. **Keep the msgids**: capitalisation comes from CSS `text-transform: capitalize` on the first letter, because `S.unchanged` = "unchanged" today.
  - Multi-block sections keep `nx-fin-block__basis` above each block's lines.
- [ ] **Step 4: Breakdowns.** In `breakdownHtml`, keep the `<table>`, its collapse and "Show all" logic, and its total row (D9). Restyle via CSS (Task 26). `shareHtml` fill becomes orange through CSS only. The `matrixHtml` output is unchanged.
- [ ] **Step 5: `render()`.** Move the note into the left column: set `[data-role="note"]` text and `hidden=false` when `p.note`, and stop appending the note in `sectionHtml`. The state pill goes in `[data-role="state"]` as today (Live / closed / drift labels, unchanged). The drift `<details>` stays in the right column. `errorHtml` renders into the right column as today (`nx-fin-error`).
- [ ] **Step 6: Billable services** (`bookingsHtml`, rewritten):
  1. `linesHtml(bk.figures)`.
  2. `<div class="nx-fin-tables">` with Per Task (the existing `perTask` breakdown) and **Per Customer**: rows from `bk.groups` (`key`, `hours`, `count`), where each key cell is `<a href="#bk-${i}">` and the grid has 4 columns (key · hours · bookings · share).
  3. Divider `<div class="nx-fin-divider"><span class="nx-eyebrow">${S.billableBookings}</span><span>${S.oneListPer}</span><span class="nx-fin-divider__rule"></span></div>`.
  4. Timeline per customer. For each group `g` at index `i`:
     - `<div class="nx-fin-tl" id="bk-${i}" data-testid="finance-bookings-${sectionKey}">` with a head (name · `fmt(S.bookings,{n})` · spacer · `{hours} h`).
     - Group `g.rows` by the `Datum` column (`idx.Datum`), in the order the rows already come (sorted by `Kunde, Datum, Benutzer`).
     - Per day: `.nx-fin-tl__day`, containing the date (`3 Aug` via `Intl.DateTimeFormat(lang,{day:'numeric',month:'short'})` and weekday `{weekday:'short'}` uppercased by CSS), the rail with its dot, and items. Each item has the comment (`Beschreibung`, or `S.noComment` italic), the line `Aufgabe · Projektpaket · Benutzer`, and hours with 2 decimals.
     - Show the first 4 bookings **across the customer** (count items, not days). The rest carry `is-more`. The footer button `.nx-fin-more` (existing delegated handler; its `closest('.nx-fin-table')` lookup must also match `.nx-fin-tl`, so change it to `closest('.nx-fin-table, .nx-fin-tl')`) shows `fmt(S.showAllN,{n})` / `S.showFewer`.
  5. `bk.truncated` note, as today.
  - Empty month: the existing `nx-fin-empty` message.
- [ ] **Step 7:** Status text for `#fin-status-text`: reuse `S.loaded` / `S.allLoaded` / `S.someFailed`. The README's "11 of 11 loaded" is the same counter.

### Task 26: `static/css/finance.css`, rewrite

- [ ] **Step 1:** Delete rules for the removed markup: `.nx-fin-head*`, `.nx-fin-filter*`, `.nx-fin-month*`, `.nx-fin-section__head/__tile/__title/__sub/__spacer`, `.nx-fin-kpis`, `.nx-fin-bk*` and `.nx-fin-skel__tile`. Keep `.nx-fin-matrix*`, `.nx-fin-drift*`, `.nx-fin-error*`, `.nx-fin-confirm*` and `.nx-fin-bexio*` (restyle the tile away). Grep each class before deleting.
- [ ] **Step 2:** Add, with values from README "Screen: Sydoc Finance":
  - `.nx-fin-jump` (nowrap, overflow hidden, padding `0 16px`, top border `var(--nx-sydoc-band-line)`, margin-top 22px, and `margin: 22px -30px 0` so it bleeds to the band edges). `__item` (44px, 12px/500 `#d1d5db`, 2px transparent bottom border, hover white + `var(--nx-sydoc)`, `flex:0 1 auto; min-width:0`). `__label` (ellipsis). `__tile` per group (the three colour pairs). `__sep` (1×18, `rgba(255,255,255,.12)`, 6px margin).
  - `.nx-fin-group` (flex, gap 12px, margin-top 34px, `+ .nx-fin-group` sibling rule 38px). `h2` (12px/700 upper .1em `var(--nx-text-meta)`), `__count` (mono 11px/600), `__rule`.
  - `.nx-fin-section` becomes the grid `260px minmax(0,1fr)`, gap 48px, padding 26px 0, bottom border `var(--nx-border)`, with `:last-of-type` getting no border. `.nx-fin-id__*` per README.
  - `.nx-fin-bpsbtn` (30px, `#111318`, white, arrow `var(--nx-sydoc-soft)`, hover `#1f2937`).
  - `.nx-fin-lines__head`, `.nx-fin-line` grid `minmax(0,1fr) 150px 110px 170px`, `__value` (mono 17px/600/−.5px), `__prev`, `.nx-fin-cmp` (64×6 track, fill `var(--nx-text)`, prev marker 2×12 `var(--nx-sydoc)`), `.nx-fin-delta` (12px/600, min-width 48px).
  - `.nx-fin-tables` becomes `repeat(auto-fit, minmax(300px, 1fr))`, gap 28px, margin-top 20px. The breakdown `table` restyle: rows 12.5px, padding 6px 0, hairline `#f3f4f6`, `.nx-fin-share__bar` 56×4, fill `var(--nx-sydoc)`, pct mono 11.5px width 40px.
  - `.nx-fin-divider`, `.nx-fin-tl` (head, `__day` grid `84px 18px minmax(0,1fr)`, `__rail` 1px line + 9px dot `2px solid var(--nx-sydoc)`, `__item` grid `minmax(0,1fr) 72px`, footer padding `10px 0 0 112px`). `.nx-fin-more` color `var(--nx-sydoc-ink-text)`, nowrap.
  - Skeleton lines `.nx-fin-skel__line`.
  - Dark: borders and hairlines via `var(--nx-border)` / `var(--nx-divider)`; `.nx-fin-bpsbtn` stays ink.
- [ ] **Step 3: Responsive** `@media (max-width: 1023px)`: `.nx-fin-section { grid-template-columns: 1fr; gap: 16px }`; `.nx-fin-line` drops the `.nx-fin-cmp` bar (`display:none`) and uses `minmax(0,1fr) 110px 90px 70px`.
- [ ] **Step 4: Print** (update the existing `@media print` block, anchor `body.nx-app, body.nx-app .nx-main { background: #fff; color: #000; padding: 0; max-width: none; }`):
  - Hide `.nx-sydoc-band .nx-sydoc-btn, .nx-sydoc-nav, .nx-fin-jump, .nx-sydoc-period__chev, .nx-fin-bpsbtn, #fin-bexio-refresh`.
  - `.nx-sydoc-band { background:none; color:#000; padding:0 }`; `.nx-sydoc-period__main, .nx-sydoc-period__year { font-size:20px; color:#000; letter-spacing:0 }`.
  - `.is-more { display: revert !important }` so every collapsed list prints expanded.

### Task 27: Finance i18n, browser check, commit

- [ ] **Step 1:** `/nx-i18n`. New msgids: "Accounting", "Choose month", "Closed, figures frozen", "Open, live", "Still running", "Running", "Open · live", "Figure", "Change", "Billable bookings", "one list per customer, as on the invoice", "All hours in Sydoc BPS", "No comment", "Show all {n}", "Closed", "Open", "Sections", "Bexio", "Invoices", and the `nav` labels already covered by `N_()`. "All hours" and "Month" may become unused. Let pybabel mark them obsolete and **do not** keep dead msgids in the `.po` files.
- [ ] **Step 2:** `python -m pytest tests/unit -q -p no:cacheprovider` is green.
- [ ] **Step 3:** `/nx-ui-verify` on `/finance?month=2026-08`, light and dark, against `Sydoc Finance.dc.html` 1a. Check:
  - the band, jump index on one row at 1280px and at 1024px (ellipsis, no wrap)
  - the picker (closed months locked, current month running, future months disabled; Esc/outside close)
  - the prev arrow inert at the oldest month
  - ledger rows, the comparison bar, and breakdown collapse / "Show all"
  - matrix scroll (Privera)
  - the billable services timeline (first 4, then "Show all n")
  - customer anchors jump to the timeline
  - close → confirm → reload shows "Closed … by …" and the lock; reopen
  - the Bexio row renders and refreshes
  - print preview (`page.emulate_media(media="print")` screenshot)
  - no console errors
- [ ] **Step 4:** Commit Tasks 23–27:

```
feat(finance): redesign Sydoc Finance as the Sydoc-branded pair (#<n>)

Ink band with the month as the headline, a one-row jump index and a month
picker that shows which months are closed; each client is a ledger row
(identity left, statement lines with a comparison bar right); billable BPS
bookings are a timeline per customer instead of tables. Figures, month
close and the CSV export are unchanged.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

# PHASE 5 — Docs and wrap-up

### Task 28: Docs, changelog, issue text

- [ ] **Step 1:** Update `docs/howto/bps.md`:
  - "## The page": band, picker (quick presets and per-month hours from `/api/bps/months`), table/treemap drill-down, the `nx.bps.view` localStorage key, and the previous-period rule (`bps.previous_range`).
  - "## Files": add `static/js/bps_view.js`, `static/js/nx_sydoc.js`, `templates/_sydoc.html`.
- [ ] **Step 2:** Update `docs/howto/finance.md`:
  - "## Export and print" (the print rules).
  - "## Adding a client": the optional `nav=` label.
  - "## Files": the shared pieces.
- [ ] **Step 3:** `CHANGELOG.md` under `[Unreleased]` → `### Changed`: one entry, **Sydoc Finance and Sydoc BPS redesign** (#<n>), naming the band/picker, the ledger + timeline, the table/treemap drill-down, the new `GET /api/bps/months` and the `prev` block on `/api/bps/summary`.
- [ ] **Step 4:** `CLAUDE.md`: in the **Sydoc BPS** paragraph, add "; shared Sydoc band/picker: `templates/_sydoc.html` + `static/js/nx_sydoc.js`". Keep it to one line.
- [ ] **Step 5:** Commit `docs(finance,bps): document the redesigned pages (#<n>)`.

### Task 29: Final check

- [ ] **Step 1:** `ruff check nx_lib tests && ruff format --check nx_lib tests`.
- [ ] **Step 2:** `python -m pytest tests/unit -q -p no:cacheprovider` is green.
- [ ] **Step 3:** Grep for leftovers: `finance-month-select`, `nx-fin-section__tile`, `nx-bps-tree-body`, `nx-kpi-strip nx-fin-kpis`, `kpisHtml`, `renderTree`. All should be gone, except in `docs/design/**` and `CHANGELOG.md`.
- [ ] **Step 4:** Push the branch and open the PR (feature branch; allowed by policy). CI runs the integration tier. Then run `/handoff-session-state`.

---

## Gotchas & notes

- **`bps-period` testid:** the form keeps `data-testid="bps-period"`. The macro's headline button is `<prefix>-period-button` (`bps-period-button`, `finance-period-button`), so the two never collide.
- **The picker form must stay a real GET form** with `name="from"` / `name="to"`. The URL is the source of truth and the integration test asserts the input values.
- **`fin-status` / `bps-status` keep their ids.** `updateStatus()` / `setStatus()` look them up and toggle `is-done` / `is-failed`. Style the dot from those classes (`.is-failed .nx-sydoc-dot { background: var(--nx-danger) }`).
- **Closed-month snapshots are old payloads.** `dbo.FinanceMonthClose.Payload` rows written before this change carry no new fields. The renderer must only read what `assemble_section` already emits (it does: `nav` is on the descriptor, not the payload).
- **`deltaHtml` wording:** `S.unchanged`/`S.isNew` are lower-case msgids ("unchanged", "new"). Capitalise with CSS, not by changing the msgid, which would force a retranslation for nothing.
- **Chart.js weekend plugin:** draw in `beforeDatasetsDraw` so the bars paint over it. Recompute on resize (Chart.js calls plugins on every draw, so there is no extra listener).
- **Treemap width** reads `clientWidth` at render time. With the drill container hidden or at zero width (initial layout), fall back to 1200 and re-render on the first `resize`.
- **Squarify needs items sorted by hours desc.** `BpsView.level()` already sorts that way; do not re-sort in `mapHtml`.
- **Backspace in the search field** must delete text, not zoom out. Check `e.target.closest('input, textarea, select')` first.
- **Do not port the prototypes' inline styles.** Everything goes into `nx-sydoc-*` / `nx-fin-*` / `nx-bps-*` classes (README "About the design files"). CSP forbids nothing here, but it is the design contract.
- **`N_()` for `nav`:** only the `bps` section's nav ("Billable services") needs translating; client names are proper nouns. The `finance()` view still passes every `nav` through `gettext` like `title`, and unknown msgids pass through unchanged.
- **Dark theme** is not designed (Owner action 5). The band tokens handle the band; everything below uses existing tokens, and hard-coded README hexes are allowed only inside the band and picker.
- **The writing-plans skill file was not found on this machine** during planning. This plan follows the two most recent plans' format instead.
