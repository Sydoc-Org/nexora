# Handoff — Reporting redesign + dashboard builder: ALL 17 TASKS EXECUTED, reviewed, ready for owner push

**Date:** 2026-07-22 · **Branch:** `feature/2.5.64` (no worktree — plan ran directly on the branch, per
its own "Context an engineer needs" section) · **63 commits ahead of origin, unpushed**
**commit-only — owner reviews and pushes**
**Prior handoff:** `2026-07-20-reporting-redesign-dashboard-builder-plan.md` (the plan write-up this
execution consumed)

## TL;DR

- **All 17 tasks of `docs/superpowers/plans/2026-07-20-reporting-redesign-dashboard-builder.md` are
  implemented, committed, and reviewed** — 8 phases, each closed out with a batched spec-compliance +
  code-quality review (per `/execute-plan`'s phase-review override), plus a final whole-branch review
  on the full plan diff. 5 of 8 phase reviews needed fixes (all applied + verified); 3 were Approved
  clean on first pass. The final whole-branch review found 1 Critical + 2 Important, all fixed.
- **One deliberate, owner-approved deviation from the plan's "zero backend changes" architecture:**
  `api_reports_list` (`nx_lib/views/reporting.py`) gained a server-computed `previewKind` field — the
  list endpoint never sent a usable `definition` field, so the client-side badge/preview-type guess was
  dead code. Asked the owner via `AskUserQuestion` mid-execution; they chose the small backend
  enrichment over the two zero-backend alternatives. No migration, no new endpoint/permission.
- **The final whole-branch review caught a real stored-XSS bug**: a dashboard card's `span` (from
  `DefinitionJSON`, which the CRUD endpoints persist without shape validation per the plan's own design)
  was interpolated into an HTML attribute without numeric coercion, unlike its escaped siblings — a
  crafted/shared dashboard could inject markup into any viewer's session. Fixed with one `parseInt`,
  plus two new regression tests for gaps the same review found (D5 preview-cache round-trip, D17
  Advanced-select exclusion).
- **Owner action required next:** review the diff, run the pre-push suite (incl. e2e —
  `scripts/test_db_reset.py` first per house convention), and push. Nothing in this range was pushed.

## Concurrent-session note (read before touching the tree)

A **different, unrelated session was actively committing to this same branch/clone for most of this
plan's execution** — a security/bug-hunt remediation pass, tracked by
`docs/superpowers/plans/2026-07-20-bug-hunt-remediation.md`, which finished and handed off at
`docs/superpowers/handoffs/2026-07-21-bug-hunt-remediation-execution-complete.md` (its own handoff
independently corroborates the `MaintenanceBanner` root-cause finding below). Of the 63 commits ahead
of origin, roughly half are that session's — touching `nx_lib/views/{auth,invoices,generali,dashboard,
workitems,admin,core}.py`, `templates/js/_{header,dashboard,generali_documents,workitems_overview}_js.html`
— **never** any file this plan touched. Every task in this session verified `git status`/`git diff
--stat` before staging and used explicit file paths; every commit's `git show --stat` was
controller-verified clean. The final whole-branch review's diff was scoped to exactly the 11
application-code files this plan touched, confirmed via an exact per-file commit-count cross-check
that zero concurrent-session commits touch any of them across the entire range.

## This session's commits (oldest → newest, 22 total)

Phase 1 (foundation — tokens, Chart defaults, masthead tabs, ledger retirement):
- `c60e6d0` feat(reporting): studio tokens, Chart.js Inter defaults, masthead tabs
- `4dba4a2` feat(reporting): retire Editorial Ledger serif/mono skin
- `00d8771` fix(reporting): neutralize base .nx-tab margin in segmented tabs *(Phase 1 review fix)*

Phase 2 (landing — hero, report cards):
- `4878f1f` feat(reporting): landing hero with AI command bar and suggestions
- `10ee918` feat(reporting): library report cards with preview thumbnails
- `e8fca5b` fix(reporting): compute previewKind server-side for library cards *(Phase 2 review fix —
  the owner-approved backend enrichment)*

Phase 3 (wizard — progress rail):
- `7557c03` feat(reporting): wizard progress rail and studio step layout
- `625097e` feat(reporting): wizard chip pills, coverage bars, step footer
- `774b321` fix(reporting): retire picked-counter once past the breakdown step *(Phase 3 review fix)*

Phase 4 (result view):
- `526d4ca` feat(reporting): studio result header with overflow menu
- `180df58` feat(reporting): studio result body with KPI rail and table card
- `ffb8cb6` fix(reporting): restore rail assertion, gate table card visibility *(Phase 4 review fix —
  restored an assertion an earlier task accidentally deleted from an unrelated test)*

Phase 5 (drill drawer):
- `aeedacf` feat(reporting): studio drill drawer with filter context chips *(Approved clean, no fix)*

Phase 6 (Advanced builder skin):
- `bb712b3` feat(reporting): advanced builder studio skin *(Approved clean, no fix)*

Phase 7 (dashboard builder — the plan's biggest, highest-risk phase):
- `6a0b189` feat(reporting): dashboard builder skeleton as kind-dashboard reports
- `328ff82` feat(reporting): dashboard card renderers with per-card runs
- `5755c00` feat(reporting): dashboard global filters and per-card overrides
- `6823138` feat(reporting): dashboard edit mode with drag reorder and card CRUD
- `31d9817` feat(reporting): dashboard KPI trends, drill-through and export
- `56dc3bf` fix(reporting): drill grain from card def, dedupe ids on reopen *(Phase 7 review fix)*

Phase 8 (dark mode + chores):
- `281d868` style(reporting): dark-mode pass over the studio redesign *(Approved clean, no fix)*
- `323bef6` docs(reporting): redesign changelog, howto, i18n and supersede stamp

Post-plan, from the final whole-branch review:
- `dfb2e56` fix(reporting): escape dashboard card span, cover preview cache and D17

## What shipped (by category)

| Category | Phase(s) | Key files |
|---|---|---|
| Studio tokens + Chart.js defaults + masthead tabs + ledger retirement | 1 | `nexora-ui.css`, `reporting.html`, `reporting.css` |
| Landing hero + AI command bar + library cards w/ real previews | 2 | `_reporting_simple.html`, `_reporting_simple_js.html`, `reporting.py` |
| Wizard progress rail + chip/coverage-bar restyle | 3 | `_reporting_simple.html`, `_reporting_simple_js.html` |
| Result header regroup (⋯ menu) + KPI rail/chart/table card | 4 | `_reporting_simple.html`, `_reporting_simple_js.html` |
| Drill drawer restyle + reusable context-chip surface | 5 | `reporting.html`, `_reporting_drill_js.html` |
| Advanced builder chrome reskin (zero behavior change) | 6 | `_reporting_js.html`, `reporting.css` |
| **Dashboard builder** — new `kind:'dashboard'` saved-report type, KPI/line/bar/donut/table cards, global+per-card filters, drag-reorder, Edit/Done autosave, KPI trends, drill-through, per-card export | 7 | `_reporting_dashboard_js.html` (new), `test_reporting_dashboard.py` (new) |
| Dark mode + i18n (de/fr/it) + changelog + docs + supersede stamp | 8 | `reporting.css`, `translations/*`, `CHANGELOG.md`, `docs/howto/reporting.md` |

Consolidated CHANGELOG entry (Added: dashboard builder; Changed: full redesign) is under
`[Unreleased]` in `CHANGELOG.md`, committed in `323bef6`. Translations (de/fr/it, 27 new dashboard
msgids + the wizard/landing/drill strings from earlier tasks) synced in the same commit —
malformed-msgstr trap checked both by the implementer and independently re-derived by the Phase 8
reviewer; zero corruption (unlike the documented prior "T-SQL" incident). `docs/howto/reporting.md`
gained a full **Dashboards** section (definition shape, access model, filter-merge semantics, export,
KPI trend behavior). `docs/superpowers/plans/2026-07-15-reporting-pin-to-dashboard.md` stamped
superseded at line 2.

## Next steps (ordered)

1. **Owner reviews the diff.** Full range for this plan alone (excluding the concurrent session's
   interleaved commits): every commit listed above under "This session's commits," `13cab2e..dfb2e56`
   filtered to the 11 app-code paths (see "How to verify").
2. **Run the pre-push suite.** `.venv\Scripts\python scripts\test_db_reset.py` first (stale
   `NEXORA_TEST` state breaks order-dependent tests), then the pre-push gate (full suite incl.
   Playwright e2e).
3. **Push `feature/2.5.64`.** Nothing in this range has been pushed.
4. **Nothing else queued from this plan** — all 17 tasks are done, both fix passes (per-phase and
   final-review) landed. The design mock stays in the owner's Downloads folder per the plan's own
   instruction — safe to archive once the owner confirms the redesign matches intent.

## Gotchas & notes

- **Owner actions called out in the plan itself** (`docs/superpowers/plans/2026-07-20-reporting-redesign-dashboard-builder.md`, "Owner actions" section) still apply:
  1. Review + push (this handoff's main ask).
  2. Whole-workbook dashboard export (one XLSX, sheet per card) was explicitly deferred (D9, v1 =
     per-card only) — say the word if wanted.
  3. Custom drag image (tilted card + dashed drop slot, mock `2b`) was explicitly skipped (D10,
     nice-to-have) — cosmetic upgrade path, noted in `reporting.css` comments.
- **Known, disclosed, NOT fixed (real but non-blocking, correctly left as follow-ups rather than chased
  beyond this plan's scope — all surfaced by the final whole-branch review):**
  - Total-kind library cards always render `—` instead of a metric label: Task 4 assumed
    `r.definition.metrics[0].label` would be available as a fallback, but Task 2's `previewKind`
    enrichment (the approved backend deviation) sends only a derived string, never the raw
    `definition` — the fallback branch is dead code. Cosmetic, not a crash.
  - `api_reports_list` now fetches the full `DefinitionJSON` per row just to derive `previewKind` (one
    word) — correctness is fine, but for users with many large reports this grows the response payload
    unnecessarily. Could move to a `JSON_VALUE` SQL projection like the existing `Kind` column already
    does.
  - `toggleEditing` in the dashboard module fires `save()` without awaiting it — a very fast Done→Edit→
    Done double-click faster than one network round-trip could in theory create two saved-report rows.
    Low probability, not guarded.
  - Dashboard card add/remove/duplicate re-run ALL cards via a full grid re-render, rather than the
    already-built selective `rerunCardsWhereChanged` path (global-filter edits correctly use the
    selective path; CRUD mutations don't). Performance-only, fine at v1's ≤15-card scale.
  - KPI trend (vs. previous period) is only reachable when a card's effective filters already contain a
    `between`-op date-range filter — which only happens via *adopting* a saved report that has one, since
    the dashboard's own global-filter popover doesn't offer a `between` op in v1 (D11's stated v1 scope).
    A real, if narrow, UX limitation — not a bug.
- **Test suite state:** full unit+integration tier showed 2 failures at the end of Task 17 and again
  during the final review — **independently root-caused, twice, to the SAME pre-existing gap the
  concurrent bug-hunt session's own handoff also found**: `sql/test/schema.sql` (the TEST DB snapshot
  `scripts/test_db_reset.py` applies) has never included the `MaintenanceBanner` table at all (0 grep
  hits, confirmed via `git log`), a standing fixture gap predating both sessions entirely. The
  implementer's own diagnosis attributed it to a different, unrelated cause (`dbo.Notifications`
  schema) — that specific attribution was wrong, but the "pre-existing, not a regression" conclusion
  held up under independent re-verification. If the owner sees the same 2 failures
  (`tests/integration/test_notifications_routes.py::test_get_notifications_authed_table_missing_returns_500`
  and `test_mark_as_read_...`) on a fresh run, that's expected.
- **Separately flagged for the owner (unrelated to this plan):** a pre-existing broken saved report on
  INT ("Docs and workitems per process per month 2026") references an unknown metric `workitem_count` —
  a data issue discovered during Task 16's manual dark-mode verification, not caused by anything in
  this session.
- **`.superpowers/sdd/` ledger:** this plan's full execution ledger — every task, every controller
  investigation, every phase review's complete findings — lives at
  `.superpowers/sdd/reporting-redesign-dashboard-builder/progress.md` (gitignored). The top-level
  `.superpowers/sdd/progress.md` belongs to the concurrent bug-hunt session, not this plan — a naming
  collision the two sessions navigated by namespacing this plan's scratch files into the subdirectory
  partway through execution (see that file's own header note for the full story).

## Untracked / left for owner

- Nothing from this plan was left uncommitted — `git status` is clean for this session's work.
- Screenshots from every phase (`var/screenshots/redesign-task*.png`, `redesign-final-*.png`) were sent
  to the owner live during execution and also remain on disk — not committed (gitignored `var/`), safe
  to leave or clean up.
- If any of the concurrent bug-hunt session's files still show as uncommitted when this is read (should
  be none — that session's own handoff reports a clean tree), don't stage/revert them.

## How to verify

```powershell
git log --oneline 13cab2e..dfb2e56 -- static/css/nexora-ui.css templates/reporting.html `
  static/css/reporting.css templates/_reporting_simple.html templates/js/_reporting_simple_js.html `
  tests/e2e/test_reporting_simple.py nx_lib/views/reporting.py templates/js/_reporting_drill_js.html `
  templates/js/_reporting_js.html templates/js/_reporting_dashboard_js.html `
  tests/e2e/test_reporting_dashboard.py   # this plan's 22 commits, filtered clean of concurrent noise
.\.venv\Scripts\python scripts\test_db_reset.py
.\.venv\Scripts\python -m pytest tests --ignore=tests/e2e -q       # expect 2 known-unrelated failures (see above)
.\.venv\Scripts\python -m pytest tests/e2e -q -k "reporting"       # expect all green
```

## Resuming in a fresh session

Nothing to resume — this plan is **complete**. `/reset-session` lands here via `var/handoff-pending`.
The next piece of work is the owner reviewing/pushing this branch. If a newer handoff exists by the
time this is read, `/reset-session docs/superpowers/handoffs/2026-07-22-reporting-redesign-dashboard-builder-execution-complete.md`
targets this file explicitly.
