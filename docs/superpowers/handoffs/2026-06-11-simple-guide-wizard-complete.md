> **Newer handoff exists for this date:** `docs/superpowers/handoffs/2026-06-11-drill-through-plan.md` (feature ideation + drill-through spec & plan) — resume from that one.

# Handoff — Simple Guide wizard improvements: all 11 tasks executed and verified

- **Date:** 2026-06-11
- **Branch:** `feature/2.5.63`. **65 commits ahead of `origin/feature/2.5.63`** — commit-only
  (remote); the owner pushes + opens the PR.
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-11-simple-guide-wizard-plan.md`
  (same date — the plan this session executed). The concurrent session's handoff
  `docs/superpowers/handoffs/2026-06-11-show-query-multidim-export-plan.md` describes the
  **next** feature wave (show-query / multi-breakdowns / rich-export, 13-task plan written,
  nothing executed yet).
- **This session's commits (oldest → newest):**
  - `a61baa8` feat(reporting): curate wizard breakdown dimensions for docprocessing *(T2)*
  - `d446306` feat(reporting): explain absent charts, chart top-50 categories *(T3)*
  - `12bc43a` feat(reporting): chart-type switcher on Simple results *(T4)*
  - `3c375c4` feat(reporting): prominent scope control with live selection badge *(T5)*
  - `b81271c` feat(reporting): adjust-in-wizard for saved reports via def mapper *(T6)*
  - `71e6e0c` feat(reporting): Back re-enters wizard; add exit-to-library buttons *(T7)*
  - `d852ff6` feat(reporting): name modal replaces window.prompt for Save as/Rename *(T8)*
  - `e82bf16` chore(i18n): translate new wizard chart/navigation strings (de/fr/it) *(T9)*
  - `bea55d7` docs(reporting): wizard curation, chart switcher, nav, save dialog *(T10)*
  - *(this handoff commit)*

---

## TL;DR

1. **All 11 tasks from the Simple Guide wizard improvement plan executed and committed.**
   Pure template/JS/CSS changes — no backend or migration changes.
2. **9 features shipped:** curated breakdown dims, chart-absence explanations + top-50,
   bar/line/pie/doughnut switcher, prominent scope badge, adjust-in-wizard reverse-mapper
   for saved/AI reports, result-Back→wizard navigation, ✕ exit buttons, Save-as/Rename name
   modal, i18n (9 strings de/fr/it), docs + changelog.
3. **T1 was verify-only** (migration `0021` already live; single metric confirmed in browser).
   **T11 ran tests and took 7 INT screenshots** (no commit).
4. **A concurrent session wrote the next plan** (`show-query/multi-breakdowns/rich-export`,
   13 tasks) — see that handoff for next steps.

## What shipped

| Task | File(s) | Commit | What |
|------|---------|--------|------|
| T2 | `templates/js/_reporting_simple_js.html` | `a61baa8` | `DOCPROC_DIM_ORDER`/`DOCPROC_DIM_HIDE` constants; curation block in `renderBreakdownStep()`; processname-first special-case deleted |
| T3 | `templates/_reporting_simple.html`, `_reporting_simple_js.html`, `reporting.css`, `test_reporting_simple.py` | `d446306` | `rsChartNote` element; `chartCardNote()` helper; `mountChart()` rework (3 no-chart cases + top-50 slice); total-only note in `runCurrent()`; e2e test |
| T4 | same 4 files | `12bc43a` | `rsChartTools` toolbar markup (bar/line/pie/doughnut); `SIMPLE_PALETTE`; `renderChart(type)`; `mountChart()` split; click handler; type persisted in `def.chartType`; e2e test |
| T5 | `_reporting_simple.html`, `_reporting_simple_js.html`, `reporting.css` | `3c375c4` | `rsScopeBadge` span; `updateScopeBadge()` in `renderBreakdownStep()`; CSS restyle (5 rules) |
| T6 | `_reporting_simple_js.html`, `test_reporting_simple.py` | `b81271c` | `WIZ_TOKENS`; `wizardStateFromDefinition()`; `adjustInWizard()`; catalog preload in `openReport()`; button gate widened; listener rewired; e2e test |
| T7 | `_reporting_simple.html`, `_reporting_simple_js.html`, `reporting.css`, `test_reporting_simple.py` | `71e6e0c` | `rsWizardClose` + `rsExit` buttons; `.reporting-simple-wizbar` wrapper; `exitToLibrary()`; smart Back handler; e2e test |
| T8 | `templates/reporting.html`, `templates/js/_reporting_js.html`, `test_reporting_save.py` | `d852ff6` | `rpNameModal` in initial markup; `promptName()` helper; `doSave()` + `renameSelectedReport()` converted to modal; e2e test |
| T9 | `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` + `.mo` | `e82bf16` | 9 new msgids translated (chart notes, chart-type labels, "Back to library") |
| T10 | `docs/howto/reporting.md`, `CHANGELOG.md` | `bea55d7` | Wizard + result-view bullets updated; Save & load section updated; 4 Added + 4 Changed entries under [Unreleased] |

## Next steps (ordered)

1. **Owner: push + open PR → `main`** (65 commits waiting, all committed-clean).
   Run `python scripts/test_db_reset.py` first (pre-push gate runs the full e2e suite).
2. **Execute the show-query / multi-breakdowns / rich-export plan** (13 tasks, already written):
   `docs/superpowers/plans/2026-06-11-reporting-show-query-multidim-export.md`.
   See `docs/superpowers/handoffs/2026-06-11-show-query-multidim-export-plan.md` for the
   full context and execution-mode choice still owed by the owner.
3. Standing PROD checklist (unchanged): provision the two reporting RO SQL logins, wire the
   scheduled-reports Task Scheduler task, repair the `0011` em-dash label, apply migrations
   `0015`–`0021` (auto on deploy).

## Gotchas & notes

- **Unstaged deletion: `env/CONFLUENCE.env.example`** — deleted by a concurrent session (the
  Confluence docs-sync work) but not committed. Do NOT `git restore` it blindly; the concurrent
  session deleted it intentionally as part of that feature. Just leave it for that feature's PR.
- **T11 e2e errors (109):** all `RuntimeError: Port 8765 already in use` — the dev server
  started for browser screenshots was still running when the full suite ran. Not real failures.
  Pre-push gate (`git push`) will re-run the suite clean.
- **`test_schedule_crud` flake:** failed once in the full-suite run; passes in isolation.
  Pre-existing ordering issue, not a regression from this session's changes.
- **16 e2e tests in `test_reporting_simple.py`** all pass individually (confirmed throughout
  the session task-by-task).
- **INT CRLF drift:** `SQL_SYNC_SKIP=1` may be needed on next commit with SQL changes (T9
  clean-committed without it, suggesting no SQL changes triggered the hook).

## Untracked / left for owner

- `env/CONFLUENCE.env.example` deletion — unstaged, not this session's work; leave it.
- Screenshots in `var/screenshots/simple-guide-*.png` — gitignored artifacts, for review only.
- Push + PR are always owner-side (remote session).

## How to verify

```powershell
git log --oneline a61baa8^..bea55d7     # the 9 feature commits from this session
python scripts/test_db_reset.py
python -m pytest tests/e2e/test_reporting_simple.py tests/e2e/test_reporting_save.py -v
# expect: 16 + 2 = 18 tests, all PASS
python -m pytest tests/unit/test_translations.py -v
# expect: 7 PASS
```

## Resuming in a fresh session

Run `/reset-session` (reads `var/handoff-pending`), or target this file explicitly:
`/reset-session docs/superpowers/handoffs/2026-06-11-simple-guide-wizard-complete.md`.

Three other handoffs share today's date — use the explicit path if the flag is gone.

The single resume point is: **execute the show-query / multi-breakdowns / rich-export plan**
(`docs/superpowers/plans/2026-06-11-reporting-show-query-multidim-export.md`, 13 tasks, not
started). Read `docs/superpowers/handoffs/2026-06-11-show-query-multidim-export-plan.md` first
for owner decisions already locked in.
