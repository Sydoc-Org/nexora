# Handoff — Sydoc redesign (#427): shared foundation + BPS done, Finance gated on #423

**Date:** 2026-09-30 · **Branch:** `feat/427-sydoc-redesign` in the worktree
`.claude/worktrees/plan-sydoc-finance-bps-redesign` (cut from `plan/sydoc-finance-bps-redesign`) ·
pushed to `origin` up to `571e4096`. This handoff commit is **local only**
(commit-only (remote)), so the branch is 1 ahead of `origin` · issue **#427** · no PR yet.

**Prior handoff:** [`2026-09-30-sydoc-finance-bps-redesign-plan.md`](2026-09-30-sydoc-finance-bps-redesign-plan.md)

## This session's commits

- `2ed2bb0f` feat(bps): add previous-period rows and hours per month (#427) (plan Tasks 6–9)
- `964a3934` feat(ui): add Sydoc brand tokens, mark and the shared band styles (#427) (Tasks 1–3)
- `ffc266bc` feat(ui): add shared Sydoc band macros and period-picker script (#427) (Tasks 4–5)
- `1fa560dc` test(ui): spell the headline en dash as an escape (#427) (fixes a lost `\u` in `ffc266bc`)
- `571e4096` feat(bps): redesign the Sydoc BPS page as the Sydoc-branded pair (#427) (Tasks 10–20)
- (this handoff)

## TL;DR

- Filed **#427** from `ISSUE.md` and cut `feat/427-sydoc-redesign`. **PHASE 0–3 of the plan are
  done**: the shared tokens, mark, band, picker and track, plus the whole BPS backend and front end.
- **CI is green** on `571e4096`, including the integration tests that can't run locally. Run
  36748848198: `test` success, `deploy-dev` success. The new `/bps` is live on
  **dev-nexora.sydoc.ch**.
- **Stopped at plan Task 21 (the gate):** PR **#426** (#423, the Bexio panel) is still **OPEN**, not
  on `main`. PHASE 4 (Finance) rewrites the same four files, so it waits until #426 merges.
- The browser check passed at 1440 and 1024 px, light and dark: headline, arrows, picker, zooming
  to the leaf, Backspace, treemap persisting across a reload, focus returning on Esc, no console
  errors, no horizontal scroll.

## What shipped

| Area | Files | Commit |
|---|---|---|
| BPS backend: `previous_range`/`next_range`, `months_query`/`months_payload`, `prev` on `/api/bps/summary`, new `GET /api/bps/months` (`bps.view`, 60/min), prev/next hrefs on the page | `nx_lib/bps.py`, `nx_lib/views/bps.py`, `tests/unit/test_bps.py`, `tests/integration/test_bps_routes.py` | `2ed2bb0f` |
| Tokens `--nx-sydoc*` / `--nx-gain` / `--nx-loss`, `body.nx-sydoc`, the `nx-sydoc-band` / `-picker` / `-pill` / `-btn` and `nx-track` classes, mark PNG | `static/css/nexora-ui.css`, `static/images/sydoc-mark.png` | `964a3934` |
| Macros `brand` / `headline` / `picker_open` / `picker_close` / `year_switch`; `window.NXSydoc` (`fmt`, `isoWeek`, `periodHeadline`, `monthCells`, `initPicker`) | `templates/_sydoc.html`, `static/js/nx_sydoc.js`, `tests/unit/test_nx_sydoc_js.py` | `ffc266bc`, `1fa560dc` |
| BPS page: band, picker, chart, zoomable Table/Treemap drill-down, per-day leaf; `window.BpsView`; i18n de/fr/it; changelog; howto | `templates/bps.html`, `templates/js/_bps_js.html`, `static/js/bps.js`, `static/js/bps_view.js`, `static/css/bps.css`, `tests/unit/test_bps_view_js.py`, `messages.pot`, `translations/*`, `CHANGELOG.md`, `docs/howto/bps.md` | `571e4096` |

## Next steps

1. **Wait for PR #426 (#423) to merge to `main`.** Then resume at **plan Task 21**
   (`docs/superpowers/plans/2026-09-30-sydoc-finance-bps-redesign.md`):
   - `git fetch origin main` and rebase this branch on it. The rebase needs per-turn opt-in.
   - On conflicts in `translations/*` or `messages.pot`, take `main`'s side and regenerate with
     `/nx-i18n`. Never hand-merge them.
2. Do PHASE 4 (Finance, Tasks 22–27) and then PHASE 5 (docs, Tasks 28–29). Finance reuses the shared
   pieces from this session:
   - `sydoc.headline(..., "finance", month_name, month_year, ...)` keeps the testids
     `finance-month-prev/next`.
   - `sydoc.picker_open("fin-picker", _("Choose month"), "finance-period-picker")`.
   - `NXSydoc.initPicker({root, opener, onOpen})`.
   - `sydoc.year_switch(...)`.
3. When Finance is done: open the PR for `feat/427-sydoc-redesign`. The owner decides whether BPS
   gets its own PR before Finance.
4. Optional owner review: the dark theme below the band was never designed (plan Owner action 5).
   Screenshots are in the worktree's `var/screenshots/bps-dark.png` (gitignored).

## Gotchas & notes

- **Local JS tests can run:** Playwright bundles Node 22 at
  `C:\dev\nexora\.venv\Lib\site-packages\playwright\driver\node.exe`. Put that folder on `PATH` and
  the `test_*_js.py` suites run instead of skipping. The subprocess calls use `encoding="utf-8"`,
  or Windows cp1252 mangles the en dash.
- **ruff RUF001** rejects a literal en dash in Python strings. The tests spell it as the escape
  `"\u2013"` (the `DASH` constant). Don't write it through `sed`, which drops the backslash; that
  cost a fixup commit.
- **`test_datepicker_styles`** lints every hex from the "11. DATE PICKER" header to the **end** of
  `nexora-ui.css`. The Sydoc block therefore sits *above* that section. Put new CSS with raw hexes
  there too, not at the end of the file.
- The **Bash heredoc breaks** on some template/CSS content (unmatched-quote errors). Write the
  content to a scratch file with Write, then splice it in with Python.
- **Unit tier locally:** 11 failed and 6 errors, all environmental:
  - DB-backed tests fail on the placeholder `TEST.env`.
  - `test_config_ms02_docfields` fails because the launcher loads `TEST.env` MS02 variables that
    the test expects unset.
  - `test_cli_doctor` hits its 30 s timing limit.
  - `test_workitem_sources` warm-loop tests are in code this branch doesn't touch.

  CI is green, and CI is the gate.
- **Locale choice:** `nx_sydoc.js`/`bps.js` format `en` dates as `en-GB` ("4 Aug", "Sept"). The
  band's range uses `Intl…formatRange` ("1. – 31. Aug. 2026" in `de`).
- **Design deviations:**
  - The treemap tile ramp in dark mode uses `color-mix` tints; the design has none for dark.
  - The picker's "Running" month reads `Läuft · 796,2 h` and its range ends today, because
    `requestSubmit` would fail the `max=today` check on a month-end date.
- **Dev login** for Playwright on INT is `ben.streich` (`/dev/login/ben.streich?next=…`).

## Untracked / left for owner

- Nothing untracked in the worktree. `var/screenshots/*` are gitignored.
- The launcher (`wt_run.py`) and Playwright probes (`shot.py`, `shot2.py`) are in this session's
  scratchpad and are disposable. The memory "Worktree env launcher" says how to recreate them.
- This handoff commit is not pushed. Push the branch before opening the PR.

## How to verify

```powershell
Set-Location C:\dev\nexora\.claude\worktrees\plan-sydoc-finance-bps-redesign
git log --oneline main..HEAD        # plan commits + 5 feature commits + this handoff
gh run view 36748848198             # test + deploy-dev: success
$env:PATH = "C:\dev\nexora\.venv\Scripts;C:\dev\nexora\.venv\Lib\site-packages\playwright\driver;$env:PATH"
# via the env launcher (see memory "Worktree env launcher"):
#   python wt_run.py TEST -m pytest tests/unit/test_bps.py tests/unit/test_bps_view_js.py tests/unit/test_nx_sydoc_js.py tests/unit/test_translations.py tests/unit/test_datepicker_styles.py -q
```

Then open `https://dev-nexora.sydoc.ch/bps?from=2026-08-01&to=2026-08-31`.

## Resuming in a fresh session

Another handoff shares today's date (the plan handoff). It now carries a forward-pointer banner to
this file, and `/reset-session` also takes an explicit path:
`/reset-session docs/superpowers/handoffs/2026-09-30-sydoc-bps-redesign-shipped.md`.

Read this file, then the plan's **Task 21 onward**
(`docs/superpowers/plans/2026-09-30-sydoc-finance-bps-redesign.md`) and the Finance part of
`docs/design/design_handoff_sydoc_finance_bps/README.md`. First check `gh pr view 426`. If it is
not merged, there is nothing to do on Finance yet.

## Update 2026-10-01 — BPS polished after owner review (read this before Finance)

Three more commits, all pushed and green in CI. `dev-nexora` runs `d1b71376`:

- `ee49c3f0` fix(bps): keep the scroll put when zooming, label narrow tiles
- `f13e692f` fix(bps): fix the UI issues a browser audit of the page found
- `d1b71376` feat(bps): keep the drill-down in the URL, fix arrows and treemap

**What changed in the shared pieces that Finance reuses:**

- **Print rules** for both pages now live in the shared Sydoc block of `nexora-ui.css`, under
  `@media print` with `body.nx-sydoc`. The sidebar is `#nexora-sidebar`; the old `.sidebar` rule in
  `finance.css`'s print block never matched, so drop it in Task 26. Page sheets lose to the
  header's second load of `nexora-ui.css` at equal specificity, so add page print rules with
  `!important` or put them in the shared block.
- **Contrast:** small grey text on the ink band uses the new `--nx-sydoc-ink-muted` (`#7c8492`)
  instead of the design's `#6b7280`, which is 3.8:1 and fails AA. Inactive `.nx-track__btn` text
  is `#636a76`. The 54px year keeps `#6b7280`, because large text only needs 3:1. Use these for
  Finance's band eyebrows/keys. axe-core reports zero violations on `/bps`.
- **`NXSydoc.periodHeadline(from, to, lang, weekLabel, todayIso)`** takes a 5th argument: a month
  up to today reads as that month. A custom range uses `Intl…formatRange`, so it is
  locale-correct ("4. – 19. Aug.").
- **Phone:** the band's stats wrap, and `.nx-track` scrolls inside its own track. There is no
  horizontal page scroll at 390 px. Check Finance's jump index at 390 px the same way.

**BPS behaviour that Finance does not need to copy, for orientation:**

- **Arrows:** they step by the period's own shape and are not clamped (week 39 › week 40). Only
  the picker's date inputs are capped at today, via `[range_to, today]|min` in the template.
  - Prev is inert once the period before would end before the oldest booking.
  - `/api/bps/summary` returns `first` and `latest` from one MIN/MAX query (`bps.span_query`).
- **The drill-down lives in the URL** (`order`, repeated `at`, `billable`, `absences`, `q`):
  - Zooming pushes a history entry; other changes replace the current one.
  - Prev/next and the picker carry the drill-down into the next period.
  - `trimPath()` drops keys the new period lacks.
- **The "Latest booking" stat** in the band turns amber after 4 days. On INT it shows **8 Sept
  2026**: the INT BPS export is stale (an ops issue, not code).
- **Treemap:** groups smaller than 56×50 px merge into a "+ n more" tile, which opens the table.

**Open on BPS (owner's call, not started):**

- A hint where the previous period predates January 2025 (year comparisons overstate growth).
- An app-wide skip link (`_header.html`).
- A CSV per drill-down.
- Arrow keys in the picker grid.

**Testing tips** (this session's scratchpad is gone, so recreate them):

- Playwright's bundled Node at `C:\dev\nexora\.venv\Lib\site-packages\playwright\driver\node.exe`
  runs the JS tests and `node --check`.
- To run axe, inject axe-core from jsdelivr with `bypass_csp=True` in the browser context.
- The dev server does **not** reload Python code. Restart it after changing views.
- Move the mouse off the sidebar before screenshots, or it expands on hover.

**Branch state:** `feat/427-sydoc-redesign` is pushed and has no PR yet. Finance still waits for
PR #426 (#423). Resume at plan Task 21.
