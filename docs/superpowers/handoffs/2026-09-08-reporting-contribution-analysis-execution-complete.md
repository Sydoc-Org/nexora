# Handoff — reporting contribution analysis ("Why did it move?") executed, reviewed, merged into the feature branch

**Date:** 2026-09-08 · **Branch:** `feat/reporting-contribution-analysis` (merged from the plan
worktree `plan/reporting-contribution-analysis`; the main checkout `C:\dev\nexora` was on a peer's
branch `refactor/255-admin-nav-tenancy-labels` at the time, so the merge was done inside the
worktree — `git switch feat/reporting-contribution-analysis` in the main checkout to see it) ·
**~18 commits ahead of `origin/main` @ `69dc932d` (HEAD `d00a382e`), nothing pushed** · commit-only (remote session) ·
execution complete, worktree removed and plan branch deleted.

**Prior handoff:** [`2026-09-07-reporting-contribution-analysis-plan.md`](2026-09-07-reporting-contribution-analysis-plan.md)
(spec + plan, consumed by this session).

## This session's commits (oldest → newest, all on `plan/reporting-contribution-analysis`)

| Commit | What |
|---|---|
| `fe2db282` | `feat(reporting)`: contribution helper — `pick_dimensions`, `single_dimension_definition` |
| `13dd80ef` | `feat(reporting)`: `contribution_rows`, `fill_shares`, `is_ratio_metric` |
| `bd11e3a1` | `feat(reporting)`: `POST /api/reporting/contribution` + integration tests |
| `0b6cbf45` | `feat(reporting)`: Total delta chip is a Why? button |
| `7c1c00c1` | `feat(reporting)`: drawer module `static/js/reporting_contribution.js` + shim + CSS |
| `24863a52` | `fix(reporting)`: endpoint 400s a malformed token, never 500s a dimension, 403 inside loop |
| `fc59f3b1` | `feat(reporting)`: wire the chip on the Simple band and dashboard whole-report cards |
| `903ef744` | `test(e2e)`: drawer opens from the chip and drills through |
| `9cea1f95` | `docs(reporting)`: howto, user guide, tips panel, changelog, spec D3 alignment |
| `426f2f03` | `chore(i18n)`: de/fr/it strings |
| `156984dd` | `fix(reporting)`: drawer survives a declined drill and Escape/backdrop close |
| `58701283` | `fix(reporting)`: drawer restores the export buttons on every close |
| `1bf5a3c8` | `fix(reporting)`: no Why? chip on `latest`-mode (level) metrics; skip unfilterable dims |
| `1c570f3e` | this handoff (first version) |
| `30b1f1eb` | `feat(reporting)`: merge of the plan branch into `feat/reporting-contribution-analysis` |
| `d00a382e` | `fix(reporting)`: sources rail keeps one card per database when the health probe fails |

## TL;DR

- **Feature shipped on the branch:** the Total delta chip on the Simple KPI band (and dashboard
  whole-report cards) is a **Why?** button. It opens the drill slide-over with one tab per dimension
  (process first, then string-typed catalog columns, cap 3) ranking values by contribution to the
  change vs. the existing shifted prior window; rows click through to drill-through. New endpoint
  `POST /api/reporting/contribution`, pure helper `nx_lib/reporting/contribution.py`. No migration,
  no permission, no env key, no deploy exclude.
- **Reviews:** Phase 1 clean; Phase 2 clean after 1 fix round; Phase 3 clean after 2 fix rounds;
  final whole-branch review clean after 1 fix wave. Every ruling is in the ledger
  (`.superpowers/sdd/…/progress.md`, git-ignored, lived in the worktree) and repeated below.
- **Verified for real:** INT browser walkthrough on the worktree server (Simple tab → Generali
  Documents, "This year" → chip → drawer with three tabs → row → drill-through). Screenshots
  `var/screenshots/contribution_simple.png`, `contribution_drill.png` (sent to the owner).
- **Tests:** unit 15, integration 7 (+79 neighbouring), e2e 4 local, translations 7, full fast-tier
  suite 2341 passed with 2 unrelated rate-limiter flakes that pass in isolation.

## What shipped

| Area | Files | Commits |
|---|---|---|
| Helper | `nx_lib/reporting/contribution.py`, `tests/unit/test_reporting_contribution.py` | `fe2db282`, `13dd80ef`, `1bf5a3c8` |
| Endpoint | `nx_lib/views/reporting/run.py` (`api_contribution`, `_grand_total`, route), `tests/integration/test_reporting_contribution_api.py` | `bd11e3a1`, `24863a52` |
| Front end | `static/js/reporting_simple_result.js` (chip button, `#rsKpiBand` listener, `RS.el` fallback), `static/js/reporting_contribution.js`, `templates/js/_reporting_contribution_js.html`, `templates/js/_reporting_simple_js.html`, `templates/reporting.html`, `static/css/reporting.css`, `static/js/reporting_dashboard.js` | `0b6cbf45`, `7c1c00c1`, `fc59f3b1`, `156984dd`, `58701283`, `1bf5a3c8` |
| e2e | `tests/e2e/test_reporting_contribution.py` (4 cases), `tests/e2e/test_reporting_simple.py` (title assertion relaxed) | `903ef744`, `156984dd`, `58701283` |
| Docs | `docs/howto/reporting.md`, `docs/howto/reporting-guide.md`, `templates/_reporting_help.html`, `CHANGELOG.md`, spec `docs/superpowers/specs/2026-09-07-reporting-contribution-analysis-design.md` | `9cea1f95` |
| i18n | `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` | `426f2f03` |

## Rulings made on the owner's behalf (in order)

1. **D3** header totals come from `total_definition()` clones (first metric only), not from summing
   dimension rows — exact for `avg`/`count_distinct`; cost: 2 extra cheap queries.
2. Implementers were dispatched concurrently with phase reviews on disjoint files to save
   wall-clock; cost paid once: a pre-commit stash conflict reverted Task 9's edits, redone.
3. `contribution_rows` keeps the plan signature (no `field`/`metric` kwargs); spec §2 aligned in
   Task 9.
4. `_grand_total` aggregates only the first metric (reviewer minor promoted into fix round 1).
5. Three unused msgids (`current`, `change`, `shareOfChange`) stay — already translated; removing
   them costs another pybabel cycle for zero user value.
6. Final fix wave = gate the Why? chip off `latest`-mode metrics + skip `filterable is False`
   dimensions. Deferred: `(empty)` folds `""` and drills `is_null` (a row of empty strings drills
   to zero rows); sentinel collision on literal "(empty)"/"(other)" values; 8 queries/call under
   `api_run`'s 120/min; a11y roles on rows/tabpanels; e2e gaps ((other) unclickable, empty state,
   dashboard surface, backdrop/Escape); `_whyWired` comment; `var band` shadowing; integration
   teardown resets `LastLoginAt` to NULL.

## Next steps

0. **INT is dark right now** (since 2026-09-08 08:30): every request logs
   `[08001] SQL Server does not exist or access denied` for the INT server in `var/logs/system/app.log`;
   the TEST DB answers. Restore that connection first — until then Reporting shows no data, no chip,
   no drawer. Then `bin
x.ps1 -r` and check the Sources rail shows one card per database.

1. **Owner:** review the branch, `git push`, open the PR against `main`. Consider creating a GitHub
   issue and renaming the branch to `feat/<nnn>-reporting-contribution-analysis`.
2. Post-merge: open a dashboard whole-report card with a time preset once in the browser and click
   its Why? chip — that surface shares the renderer but was not browser-verified here (the
   dashboard tab redirected to the library for `ben.streich` on INT).
3. Follow-ups (each small, none blocking): a11y pass over the drawer tablist; `(empty)` vs empty
   string drill; a lower rate limit for the endpoint if the reporting DB feels it.
4. **Roadmap from the 2026-09-07 brainstorm** (owner picked tracks Insight + History + Eddard
   proactive; contribution analysis was feature 1). Each item is its own brainstorm → spec → plan
   cycle (`superpowers:brainstorming`, then `/write-plan`, then `/execute-plan`); none has a spec yet.
   Suggested order, smallest useful step first:
   1. **Chart annotations** (Insight) — pin a dated note on a report's time axis ("new client
      onboarded", "mailroom outage"), shown as a marker on the chart and listed under it. Needs a
      NexoraDB migration (`ReportingAnnotations`: report id, date, text, author) — claim the next
      `NNNN` in the issue first.
   2. **Anomaly radar** (Insight) — reuse the contribution helper's shifted-window totals to flag a
      bucket that deviates > N σ from its trailing mean; badge on the KPI band, list in a drawer.
      Pure helper in `nx_lib/reporting/`, no migration.
   3. **Eddard weekly card** (Eddard proactive) — a scheduled run that asks the AI assistant for a
      3-line summary of the week's movers (built on `api_contribution` + anomaly output) and posts
      it as a dashboard card / email via the existing schedule delivery.
   4. **Snapshots** (History) — persist a report's result rows per run so past values survive
      source edits; needs a migration and a retention job.
   5. **Cycle-time metrics** (History) — time between workitem states as a first-class metric in
      the wizard measure list; depends on which states each source exposes.
   6. **Target lines** — after the sibling `plan/report-layouts` branch lands (it owns the chart
      option surface this would extend).
5. Deferred minors from the final review, still open: a11y roles on drawer rows/tabpanels; e2e
   gaps (dashboard card, empty state, backdrop/Escape); `(empty)` vs empty-string drill; sentinel
   collision on literal "(empty)"/"(other)"; a dedicated rate limit (8 queries/call); three
   unused msgids.

## Gotchas & notes

- **Sources rail fix (`d00a382e`):** the rail groups cards by database using the health probe's
  `db` name; with the probe down it used to fall back to the source *label*, so the six Generali
  table sources became six cards. Now `GET /api/reporting/sources` also returns `engine`, and the
  rail falls back to an engine-keyed label (`ENGINE_LABELS` in `templates/js/_reporting_tabs_js.html`).
  Covered by `tests/e2e/test_reporting_rail.py` (probe stubbed to 503, expects 2 cards). The
  wizard's measure list still shows one group per source under a Generali heading — by design.

- **Level metrics:** for `total_mode = "latest"` metrics (Backlog) the chip stays a plain span on
  purpose — the drawer sums the window, the chip shows the latest bucket; they cannot agree.
- **Drill shell is shared:** `ReportingContribution` owns `#rdPanel` until `release()` (rdClose,
  backdrop, Escape, or the hand-over to `ReportingDrill.open`), which also restores the export
  buttons it hides.
- **`RS.el` load order:** `reporting_simple_result.js` loads before `reporting_simple.js`; it now
  carries `RS.el = RS.el || window.NX.el;`.
- **Shared TEST DB lock:** a peer session's e2e run held it for ~15 min mid-session; every pytest
  run queues behind it. Never kill the holder. Implementer subagents that background a test run
  stop and wait — resume them with a foreground run instruction.
- **Main checkout noise, deliberately untouched:** untracked `docs/.$*.drawio.bkp`,
  `docs/architecture/`, `sql/NexoraDB/Views/dbo.vFieldExtractionQuality.sql`; the sql-sync hook
  regenerates INT-drift dumps under `sql/NexoraDB/` on every commit (restored with
  `git restore -- sql/NexoraDB`). All commits used `SQL_SYNC_SKIP=1`; nothing else was bypassed.
- Two rate-limiter integration tests (`test_rate_limit_429_for_unauthenticated_requests`,
  `test_verify_2fa_rate_limit_eventually_429`) failed inside the 10-minute full run and pass alone —
  order-dependent, pre-existing.
- The sibling worktree `plan-report-layouts` (`plan/report-layouts`) still exists and overlaps
  `run.py`, `reporting.css`, `reporting_simple.js`, `reporting_dashboard.js`, the reporting docs and
  `CHANGELOG.md`; this branch's edits there are append-only, so whichever lands second re-anchors.

## Untracked / left for owner

- Nothing of this session's is uncommitted. Peer noise above is not ours.
- Push and PR are the owner's (remote session policy).

## How to verify

```powershell
$env:PATH = "C:\dev\nexora\.venv\Scripts;$env:PATH"
git log --oneline origin/main..HEAD                       # 18 commits incl. spec, plan, handoffs
python scripts/test_db_reset.py
pytest tests/unit/test_reporting_contribution.py tests/integration/test_reporting_contribution_api.py -q --no-cov   # 22 passed
$env:NEXORA_E2E_PORT = 5177; pytest tests/e2e/test_reporting_contribution.py tests/e2e/test_reporting_rail.py -q --no-cov   # 5 passed
pytest tests/unit/test_translations.py tests/unit/test_reporting_help_sync.py -q --no-cov
```

## Resuming in a fresh session

`/reset-session` picks the newest handoff; if another `2026-09-08-*` handoff appears, run
`/reset-session docs/superpowers/handoffs/2026-09-08-reporting-contribution-analysis-execution-complete.md`.
Spec: `docs/superpowers/specs/2026-09-07-reporting-contribution-analysis-design.md`; plan:
`docs/superpowers/plans/2026-09-07-reporting-contribution-analysis.md` (all tasks done).
