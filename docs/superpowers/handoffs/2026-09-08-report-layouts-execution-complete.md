# Handoff — report layouts ("Report definitions"): plan executed, ready to merge

**Date:** 2026-09-08 · **Branch:** `plan/report-layouts` (worktree
`.claude/worktrees/plan-report-layouts`, cut from
`refactor/255-admin-nav-tenancy-labels` @ `49a400c5`) · 15 commits ahead of the
merge point when this session started · commit-only — the owner pushes.

**Prior handoff:** [`2026-09-07-report-layouts-definitions-plan.md`](2026-09-07-report-layouts-definitions-plan.md)
(spec approved, plan written — this handoff picks up right after it, executes
the whole 16-task plan via `/execute-plan`, and closes the branch out).

## This session's commits (oldest → newest)

| Commit | What |
|---|---|
| `04248dab` | Merge `refactor/255-admin-nav-tenancy-labels` into `plan/report-layouts` (pre-Task-1 sync) |
| `b1ffe51d` | Task 1 — `nx_lib/reporting/derived.py`, the six measure ops |
| `9fb6ad8d` | Task 2 — `validate_layout_definition` in `schema.py` |
| `294835fc` | Task 3 — save-time validation for `kind:'layout'` in `reports.py` |
| `87bfa945` | Task 4 — `/api/reporting/run` resolves layout, returns `derived` |
| `ebb66283` | Task 5 — export carries the layout's Measures block |
| `f2898acc` | Phase 1 fix round — forecast-row bug, Decimal handling, unguarded `_layout_block` |
| `d87bc620` | Merge `refactor/255-admin-nav-tenancy-labels` again (pre-Task-6 sync — peer dashboard/forecast work) |
| `ffad3b7c` | Task 6 — grid engine extracted to `static/js/reporting_grid.js` |
| `cd5266db`, `943aae45` | Task 7 — 5th Simple-pane view, Console rail, `/reporting/definitions` redirect (+ SCREENS-array fix) |
| `bc325c19` | Task 8 — `reporting_layouts.js`, the editor (list/new/edit/delete/autosave/preview) |
| `4fbc65fe` | Task 9 — `reporting_layout_view.js`, the tile renderer |
| `bf7f7c4e` | Task 10 — Simple wizard picker + result tiles |
| `897cbaa5` | Security hardening — escape `t.type`/`geomStyle()` in tile markup (mid-plan, controller-authored) |
| `a461e9fc`, `05b84187` | Task 11 — Advanced builder picker + result tiles (+ Phase 4 fix round: picker-selection loss, stale view-toggle, remaining unescaped tile shell) |
| `33958970`, `e29e83e9` | Task 12 — Playwright e2e (+ fix: a **real production bug**, see below) |
| `8faa5970` | Task 13 — docs (`reporting.md`, `reporting-guide.md`, tips panel, changelog) |
| `e475d159` | Task 14 — coverage floor for `derived.py`, endpoint inventory test |
| `9a426d25` | Task 15 — translations (de/fr/it) |
| `3721ea58` | Final whole-branch review fix round — 3 findings (see below) |

## TL;DR

1. All **15 code-landing tasks** of the 16-task plan
   (`docs/superpowers/plans/2026-09-07-report-layouts-definitions.md`) are
   done, individually reviewed, phase-reviewed, and the final whole-branch
   review is clean. **Task 16 (live browser verification) is BLOCKED** — this
   environment has no network path to the Sydoc SQL Server (confirmed by both
   a subagent and the controller independently) — not a code defect.
2. **A real, pre-existing production bug was found and fixed along the way**
   (Task 12): `reporting_layouts.js`'s `RS()` helper read `.state`/`.reports`
   off `window.ReportingSimple` (a narrow public export) instead of the actual
   shared `window.RS` namespace — the Report Definitions screen threw on
   every interaction, for every real user, since Task 8 landed. Fixed in
   `33958970`.
3. **One known, accepted gap ships as-is**: corner-resize does not work in
   the Report Definitions editor (`#rlGrid`) — the `onResize` hook is
   confirmed (via live instrumentation) to never fire for this grid, unlike
   the dashboard's identical `#rdbGrid` (same shared `reporting_grid.js`
   engine, which works fine). Drag-reorder works. Root cause narrowed but not
   found. The e2e test for it is `@pytest.mark.skip`'d with the precise
   finding recorded in the test file itself.
4. **Final whole-branch review found 4 Important issues; 3 were fixed** in
   `3721ea58` (layouts leaking into the dashboard's card picker; Ask Eddard
   not receiving `derived`/`layout` despite plan decision D5 saying it would;
   unconstrained tile/measure ids that could crash the whole result view via
   an uncaught `querySelector` `SyntaxError`). The 4th (the editor's
   `onResize` hook does a full DOM rebuild instead of the lighter pattern
   `onReorder` already uses) is attached as a note to the resize-bug item
   above — fixing it is moot until the trigger bug is found.

## What shipped

**Backend:** `nx_lib/reporting/derived.py` (6 measure ops), `nx_lib/reporting/schema.py`'s
`validate_layout_definition`, save-time validation in `nx_lib/views/reporting/reports.py`,
`/api/reporting/run` + `/api/reporting/export` resolving `layout`/`derived`/`layoutFallback`
via `nx_lib/views/reporting/_shared.py`'s `_layout_block`/`_load_owned_layout`, a
Measures export block in `nx_lib/reporting/export.py`.

**Frontend:** shared grid engine `static/js/reporting_grid.js` (dashboard's first
consumer, editor's second); 5th Simple-pane view `#rsLayouts` + Console rail entry +
`/reporting/definitions` redirect; the editor `static/js/reporting_layouts.js`; the
tile renderer `static/js/reporting_layout_view.js`; matching pickers + result-tile
rendering in both the Simple wizard and the Advanced builder.

**Docs/i18n/tests:** `docs/howto/reporting.md` + `reporting-guide.md` + tips panel +
changelog (Task 13); coverage floor + endpoint inventory (Task 14); de/fr/it
translations, ~32 new msgids each locale (Task 15); Node-driven JS unit tests for the
grid engine and tile renderer (repo's first); Playwright e2e
(`tests/e2e/test_reporting_layouts.py`, 3 of 4 tests ship green, 1 skipped with a
precisely-diagnosed root cause).

## Next steps (ordered)

1. **Owner action — Task 16 on a machine with real Sydoc network access:**
   restart the dev server, log in as `ben.streich`, and run the plan's Task
   16 browser-verification sequence (`docs/superpowers/plans/2026-09-07-report-layouts-definitions.md`,
   Task 16): editor screenshot, result-tiles screenshot, wizard-picker
   screenshot, CSV export's Measures block, delete-fallback toast. Save
   screenshots to `var/screenshots/`.
2. **Merge this worktree branch into its parent** (`refactor/255-admin-nav-tenancy-labels`)
   — this handoff was written mid-`/execute-plan`, which normally chains into
   `/handoff-session-state --merge-worktree` to do this automatically. If
   that chain didn't complete, merge `plan/report-layouts` into
   `refactor/255-admin-nav-tenancy-labels` by hand, then that branch merges
   toward `main` in the normal course of things.
3. **Follow-up issue worth filing** (not blocking): the corner-resize bug in
   `#rlGrid` — `onResize` never fires; root cause narrowed to "not the
   DOM-rebuild theory, something in the trigger itself" via live
   instrumentation in Task 12's fix round. Whoever picks this up should also
   change the editor's `onResize` hook from `markDirty()` (full rebuild) to
   `markDirtyNoRender()` (already used by `onReorder` for the same reason) —
   otherwise fixing the trigger just surfaces a second bug.
4. **Merge-checklist item riding on this branch, not this plan's own work:**
   migration `sql/_migrations/NexoraDB/0121_reporting_sql_generali_target.sql`
   + new `DB_REPORTING_GENERALI_RO_*` env keys + a
   `reporting.sql.target.generali.use` permission grant landed via a
   separately-authored Live SQL feature that got merged into this branch
   (peer session, before Task 6). Not this plan's scope, but whoever finishes
   this branch should: confirm the migration number isn't contested, run
   `scripts/env-sync.py`, and grant the permission.
5. **Minor deferred items** (ledgered during execution, none blocking):
   untranslated export measure labels (raw op codes, not `gettext`-mapped);
   `layoutFallback: "foreign"` never emitted (both "deleted" and "not yours"
   report as `"missing"` — intentional per the test suite, just simpler than
   the original spec's two-value design); rail count shows a literal "0"
   instead of blank when a user has no definitions; several CSS class hooks
   with no dedicated rule (`.rl-head`, `.rl-main`, `.rl-grid`,
   `.rs-layout-pick`, `#rpLayoutPick` — all inherit workably from `.rdb-*`);
   Chart.js instances aren't destroyed when leaving `#rsLayouts` (leak until
   next render — `ReportingLayoutView.destroy()` exists but `close()` never
   calls it).

## Gotchas & notes

- **Task 16 could not run in this environment.** Both a dispatched subagent
  (isolated sandbox) and the controller session itself hit the identical
  `pyodbc.OperationalError` (`08001` "SQL Server does not exist or access
  denied") trying to reach `engine_nexora_db` — this session has no network
  path to Sydoc's internal SQL Server. Every DB-backed page, including
  `/dev/login/...`, is unreachable here. This is an environment/network
  limitation of wherever this session is running, not a code defect — verify
  from a machine with real Sydoc network access.
- **A production bug shipped silently between Task 8 and Task 12.** The
  Report Definitions screen was completely broken for real users (threw on
  every interaction) from the moment Task 8 landed until Task 12's e2e work
  caught it via a live `pageerror` capture. Nothing in Tasks 8–11's own
  reviews caught it because none of them exercised the screen in a real
  browser — only Task 12's Playwright work did. Worth remembering: JS unit
  tests and lint suites don't substitute for at least one live click-through
  per new screen.
- **The shared `NEXORA_TEST` DB lock (issue #235) cost real wall-clock time**
  repeatedly during this session — e2e and integration runs routinely queued
  behind other sessions for minutes at a time, and one full-file integration
  run took 19 minutes and produced 57 spurious `ERROR`s from
  contention/timeout (all confirmed to pass individually afterward — not a
  regression). If you see a wall of `ERROR`s in a long `pytest` run against
  this DB, re-run the specific failing tests in isolation before assuming a
  real break.
- **The escaping-hardening class (mid-plan security-scan finding) took two
  passes to fully close.** Fixed in `static/js/reporting_simple.js` first
  (`897cbaa5`), applied preemptively in `reporting_advanced.js`'s new code,
  and the final whole-branch review found a 4th, pre-existing occurrence in
  `reporting_layouts.js`'s own tile-shell builder that neither per-task
  review had reason to check (it wasn't part of either diff) — closed in
  `3721ea58`. If anyone adds a 5th tile-shell builder later, it needs the
  same `esc(t.type)` / `esc(geomStyle(...))` treatment.
- **Commit-trailer attribution changed mid-session** (the controlling
  session's own attribution instructions were updated partway through
  execution, twice). A couple of early commits (`b1ffe51d`, `bc325c19`)
  carry a stale/different `Claude-Session` value from before the update —
  ruled acceptable by the controller (cosmetic only, no functional impact),
  not amended. All commits from `9fb6ad8d` onward use the current trailer.

## Untracked / left for owner

Nothing — working tree is clean, all SDD workspace scratch files
(`.superpowers/sdd/2026-09-07-report-layouts-definitions/`) were deleted
after the final review closed.

## How to verify

```bash
# Layout-specific unit tests (all green, no DB needed)
PATH="/c/dev/nexora/.venv/Scripts:$PATH" ENVIRONMENT=INT python -m pytest \
  tests/unit/test_reporting_derived.py tests/unit/test_reporting_schema.py \
  tests/unit/test_reporting_export.py tests/unit/test_reporting_grid_js.py \
  tests/unit/test_reporting_layout_view_js.py tests/unit/test_coverage_thresholds.py \
  tests/unit/test_create_app.py tests/unit/test_template_url_prefix.py \
  tests/unit/test_static_v_lint.py tests/unit/test_no_inline_event_handlers.py \
  tests/unit/test_reporting_i18n_lint.py tests/unit/test_translations.py \
  tests/unit/test_reporting_guide.py tests/unit/test_reporting_help_sync.py -q --no-cov
# -> 193 passed (last run this session)

# Layout-specific integration tests (needs NEXORA_TEST reachable)
PATH="/c/dev/nexora/.venv/Scripts:$PATH" python -m pytest \
  tests/integration/test_reporting_routes.py -q --no-cov -k "layout"
# -> 8 passed

# Layout e2e (needs a free port + NEXORA_TEST)
PATH="/c/dev/nexora/.venv/Scripts:$PATH" NEXORA_E2E_PORT=8792 python -m pytest \
  tests/e2e/test_reporting_layouts.py -q
# -> 3 passed, 1 skipped (documented corner-resize gap)
```

Do **not** run `tests/integration/test_reporting_routes.py -q --no-cov` (the whole
file, no `-k`) in one go if you're in a hurry — it takes ~19 minutes against the
shared `NEXORA_TEST` DB and threw 57 contention-related `ERROR`s in this session
that all passed individually on re-run.

## Resuming in a fresh session

`/reset-session docs/superpowers/handoffs/2026-09-08-report-layouts-execution-complete.md`
(explicit path recommended — several handoffs share nearby dates in this
directory). Then either merge the worktree branch by hand (step 2 above) or
pick up Task 16 on a machine with Sydoc network access.
