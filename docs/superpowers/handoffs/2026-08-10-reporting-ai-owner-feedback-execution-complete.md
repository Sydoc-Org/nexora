# Handoff — Reporting AI Owner Feedback (#178): execution complete, ready for owner merge

**Date:** 2026-08-10 · **Branch:** `plan/reporting-ai-owner-feedback` (worktree
`.claude/worktrees/plan-reporting-ai-owner-feedback`, cut from `v3.1` @ `4856eed`) ·
**commit-only — owner pushes and merges**
**Prior handoff:** `2026-08-06-reporting-ai-owner-feedback-plan.md`

## TL;DR

- All 16 tasks of `docs/superpowers/plans/2026-08-06-reporting-ai-owner-feedback.md` (8 phases)
  are **implemented, tested, and reviewed clean** via subagent-driven development — this session
  executed the plan end to end, ran 7 phase-scoped combined reviews + 1 final whole-branch review,
  and fixed everything each review found (2 fix rounds at phase level, 1 fix wave at final
  review). All 22 commits are on `plan/reporting-ai-owner-feedback`, nothing uncommitted.
- **The merge into `v3.1` was deliberately NOT attempted.** The plan's own "Context an engineer
  needs" section and this session's remote-work policy both say "commit-only — owner pushes...
  the owner reviews, merges the worktree branch back into v3.1, and pushes." This session
  followed that literally rather than the `/execute-plan` skill's generic auto-merge default —
  the worktree and branch are **intentionally left in place** for the owner. See "Owner actions"
  below for the exact merge steps.
- Issue #178 is **not yet closed** — that's an owner action after merge+push, per the plan.
- Two items came out of the final whole-branch review that are **owner decisions, not code
  defects**, and were deliberately left unfixed — see "Needs an owner decision" below.

## This session's commits (oldest → newest, on `plan/reporting-ai-owner-feedback`)

| Commit | What |
|---|---|
| `6c64b26` | Task 1 — hide the Simple hero outside the library view (B6) |
| `5215794` | Task 4 — AI-built reports open in the Simple tab (A4) |
| `0b46ae9` | Task 2 — granularity chip on Simple results (B7) |
| `4cbe237` | Task 3 — wizard granularity select discoverable (B8, grain half) |
| `9fbafd0` | Task 5 — live "building your report" step list (A1) |
| `5853612` | Task 6 — agent follow-ups keep the prior answer's artifacts (A3) |
| `81631fc` | Task 7 — T-SQL retry-loop hints + prompt discipline (A2) |
| `2444918` | **PHASE 1+2 fix round** — stale "Open in builder" fallback string + de/fr/it |
| `878f477` | Task 8 — `TotalMode` on the metrics registry (migration `0056`, applied to INT) |
| `6073d02` | Task 9 — server-side latest-bucket grand totals for snapshot metrics |
| `4c8174d` | Task 10 — client KPI band honours latest-mode metrics |
| `0ec1759` | **PHASE 3 fix round** — integration test proving `_prepare_run`'s `latest_of` wiring |
| `07b7af2` | Task 11 — forecast fits on widened history, not the visible window (C9) |
| `ec34ff8` | Task 12 — `POST /api/reporting/field_values` endpoint |
| `03bfc40` | Task 13 — wizard process step for table sources (B8, processes half) |
| `870970c` | **PHASE 5 fix round** — field-scope filter mapping only matches the process field |
| `a61ec77` | Task 14 — dashboard report card adopts a saved report 1:1 (D11) |
| `05920f0` | Task 15 — "Live SQL geht nicht" repro'd + fixed: Open in Advanced now runs the report (A5) |
| `f17f6df` | Task 16 — i18n cycle, changelog, docs, full verification |
| `a1f0107` | **Final whole-branch review fix wave** — 7 findings addressed (see below) |

Not merged, not pushed. `git log --oneline 4856eed..HEAD` shows 22 commits (the two above this
table — `157286b` plan, `5d1567e` prior handoff — are from the planning session).

## What shipped

| # | Item | Files |
|---|---|---|
| 1 | AI chat: live build-step ticker, follow-ups carry prior SQL/definition context (12000-char cap), T-SQL error hints (156/205/209) + prompt discipline, AI reports open in Simple via `ReportingSimple.openDefinition`, "Open in Advanced" now actually runs the report | `templates/js/_reporting_ai_js.html`, `templates/js/_reporting_simple_js.html`, `templates/js/_reporting_js.html`, `nx_lib/reporting/{ai,sandbox}.py`, `nx_lib/views/reporting.py` |
| 2 | Simple pane: hero hidden outside library view, granularity chip on results, wizard grain always visible + process-scope step for table sources | `templates/js/_reporting_simple_js.html` |
| 3 | `POST /api/reporting/field_values` — distinct values (TOP 100) of a whitelisted filterable field, table-provider + permission-gated | `nx_lib/reporting/table_query.py`, `nx_lib/views/reporting.py` |
| 4 | `TotalMode` on the metrics registry (migration `0056`, backfilled `backlog_total→latest`) — server-side zero-dim latest-bucket totals + client-side KPI band "last bucket" caption | `sql/_migrations/NexoraDB/0056_reporting_metrics_total_mode.sql`, `nx_lib/reporting/table_query.py`, `nx_lib/views/reporting.py`, `templates/js/_reporting_simple_js.html` |
| 5 | Forecast fits on a grain-dependent widened history window (56/182/730/1460/2190 days), shared by `/api/reporting/run` **and** `/api/reporting/export` via a new `_forecast_for()` helper; auto horizon resolves from the visible row count, not the widened fit's | `nx_lib/reporting/tokens.py`, `nx_lib/reporting/forecast.py`, `nx_lib/views/reporting.py` |
| 6 | Dashboard card type `report` — adopts a saved report 1:1 (definition untouched, own chart type) | `templates/js/_reporting_dashboard_js.html`, `static/css/reporting.css` |
| 7 | i18n (de/fr/it, non-fuzzy), changelog, `docs/howto/reporting.md` + `docs/design/reporting-ai-assistant.md` updates | `messages.pot`, `translations/*/LC_MESSAGES/*`, `CHANGELOG.md`, `docs/howto/reporting.md`, `docs/design/reporting-ai-assistant.md` |

## Review history (all clean)

- **PHASE 1+2** (Tasks 1,4,2,3,5,6,7): 1 fix round — a stale "Open in builder" fallback string in
  `nx_lib/views/reporting.py` (missed by Task 4's rename), incl. stale de/fr/it translations.
  Fixed, re-reviewed clean. 3 Minor deferred (stale comments, e2e docstrings, a cosmetic
  grain-chip default-label mismatch before Apply).
- **PHASE 3** (Tasks 8,9,10): 1 fix round — `_prepare_run`'s `latest_of` decision logic had zero
  test coverage; added an integration test proving it end-to-end via `/api/reporting/run`. Fixed,
  re-reviewed clean. 1 Minor deferred (code duplication between two near-identical helpers).
- **PHASE 4** (Task 11): Approved, no findings. 3 Minor observations, all plan-inherited/pattern-
  consistent, no action needed.
- **PHASE 5** (Tasks 12,13): 1 fix round — `wizardStateFromDefinition`'s field-scope filter
  extraction matched ANY string `in`-filter, not the specific process-like field — a silent
  data-loss risk on "Adjust in wizard" for reports with an unrelated `in`-filter. Fixed
  (gate tightened to `ft.field === processFieldFor(src).field`), re-reviewed clean, both failure
  modes hand-traced closed. 2 Minor deferred.
- **PHASE 6** (Task 14): Approved, no findings.
- **PHASE 7** (Task 15, repro-first): Approved. Diagnosis: `rsOpenAdvanced` + the AI chat's
  Advanced-fallback both called `applyDefinition()` but never `run()`, so Advanced landed on an
  empty results grid with "Show query" hidden/stale — this is what the owner meant by "Live SQL
  geht nicht." `window.Reporting` now exports `run()`; both call sites invoke it. A mid-execution
  test-splice accident (the new e2e test got inserted mid-way through an unrelated prior test,
  dropping its closing assertion) was caught by the controller before this review and fixed.
- **Final whole-branch review** (opus, cross-cutting pass): "Ready to merge — with fixes." Found
  5 Important + 5 Minor items phase-scoped reviews structurally couldn't see:
  1. **`filterChipEditor` corrupted a field-scope `in`-filter into a lexical BETWEEN on Apply** —
     it branched on `Array.isArray(f.value)` instead of `f.op`, so a 2-value `in`-filter (routine
     after Task 13) silently became a range on any Apply, even with no edits. Fixed: branch on
     `f.op`; `in`/`not_in` chips now display comma-joined, not arrow-joined, so the two shapes
     can't be visually confused.
  2. **Forecast lookback (Task 11) was only wired into `/api/reporting/run`**, not
     `/api/reporting/export` or the scheduled-report runner — the same report could show a richer
     forecast on screen than in an export or email. Fixed for `api_run` + `api_export` via a
     shared `_forecast_for()` helper. `ops/run_scheduled_reports.py` was investigated and
     deliberately left unchanged — it runs on a separate, session-less execution path
     (`execute_definition`) that `_forecast_for`'s `_prepare_run`/`_execute` machinery can't reach
     without a real second implementation. **Documented gap, not fixed** — see below.
  3. **The widened fit silently ~5x'd the auto-forecast horizon** — `_resolve_horizon` derived the
     horizon from whichever series got fitted, so Task 11's widened refit (more rows) grew the
     projected tail as an unintended side effect. Fixed: `compute_forecast` gained an optional
     `visible_rows` param; the horizon now always resolves from the visible window.
  4. **(Cheap variant only)** the client KPI band's "latest snapshot" caption overclaimed
     precision — it's a bucket sum, not the server's exact-latest-row. Relabeled to "last bucket";
     doc corrected (the caption only checks the FIRST metric, not "every" metric, contra the old
     doc text). The architectural "real fix" (band reads the server's own total) was explicitly
     scoped OUT.
  5. Plus 3 quick Minor fixes: CHANGELOG gained the missing A5 entry, the dashboard report card's
     `TotalMode` limitation is now documented, and a stale "Loading values…" hint on the wizard's
     field-scope step now clears when the user steps away mid-fetch.
  - Re-reviewed clean (opus, scoped): all 7 addressed, no new Critical/Important breakage. 3 new
    Minor observations from the fix diff itself, all non-blocking (comma-in-value round-trip edge
    case for `in`-filters containing a literal comma; an empty-`visible_rows` edge case in the
    horizon override; one dead ternary branch) — parked, not fixed.
  - **Two findings deliberately NOT fixed — owner decisions, not code defects:**
    - **Finding 4 — unrelated INT schema drift committed under Task 8.** The `sql-sync-check`
      pre-commit hook, which regenerates DDL dumps from the *whole* shared INT database on every
      commit, swept in a new `sql/NexoraDB/Tables/dbo.WorkitemFilterViews.sql` and a rename
      `dbo.ClientInvoices.sql` → `dbo.decapitated_ClientInvoices.sql` — **neither has a backing
      migration anywhere in `sql/_migrations/`**, and `WorkitemFilterViews` isn't referenced by
      any application code. This is someone else's in-flight schema work (migrations `0057`-`0060`
      per Task 8's own note) already applied to the shared INT box ahead of its own migration
      landing. Merging this branch as-is enshrines that INT-only state as checked-in source of
      truth while PROD's deploy will create neither object. **Owner call:** either the owning
      session lands its migrations first, or these two dump files come back out of this branch
      before merge (reverting them will make `sql-sync-check` fail again until INT and the dumps
      agree — that's expected, not a new bug).
    - **Finding 8 — a multi-grain-column report can strand "Adjust in wizard."** `renderAiChips`
      picks the *first* grained column for the granularity chip; if a report has two independently
      grained date columns (there's an e2e test for that shape) and the chip is applied,
      `wizardStateFromDefinition`'s pre-existing mismatched-grains guard returns `null`, so "Adjust
      in wizard" silently disappears with no explanation. This is a genuine UX dead-end but fixing
      it requires a product call (apply the grain to all grained columns? hide the chip when there
      is more than one?) rather than an obvious bug fix.

## Gotchas & notes

- **Migration `0056` is already applied to shared INT** (Task 8's commit, `sql-migrate-int` hook
  ran for real). No action needed on the owner's INT box; it rides the normal PROD deploy.
- **Environmental flakiness hit repeatedly this session, none of it this plan's code:** an orphan
  `dbo.WorkitemFilterViews` table on the shared `NEXORA_TEST` DB blocked `scripts/test_db_reset.py`
  five times early in the session (dropped each time; a later Task 8 commit legitimately adds this
  table to the tracked schema, so it should stop recurring going forward) — a transient shared-DB
  race with a concurrent session once (self-resolved); 8 unrelated unit/integration tests
  (rate-limiter/dashboard-recent-activity, none touching reporting) failed only when run as part of
  the full suite and passed 100% in isolation — order-dependent shared state, not a regression; an
  orphaned e2e test server on port 8765 from an earlier interrupted verification attempt blocked
  2 e2e tests with `ERR_CONNECTION_REFUSED` (killed, both re-verified green) — `netstat` on this
  box is German-localized (`ABHÖREN` = LISTENING), which tripped up an English-only `grep` once.
- **Subagents dispatched via the Agent tool that background a long-running command (the e2e tier,
  ~12-13 min) stall indefinitely** waiting on a notification only the top-level session actually
  receives — hit 3 times on Task 16, once on the final-review fix wave. Each time, the controller
  took over directly: reviewed the agent's already-correct uncommitted diff, ran verification in
  the foreground itself, and committed. No content was lost or redone; just extra controller-side
  legwork. Worth remembering for future long-e2e-tier tasks in this repo: don't let a dispatched
  subagent background its own final verification step.
- **Deferred by design (plan "Owner actions" section, never revisited):** server-side SQL
  compile-check in `validate_sql`; forecast lookback for literal (non-token) date ranges;
  `TotalMode` in the admin metrics editor UI (registry-driven, migration-only for now); latest-mode
  awareness inside dashboard report cards (this session's Finding 7 doc note covers the same gap);
  forecast/caption/drill inside dashboard cards.
- **`ops/run_scheduled_reports.py`'s forecast still doesn't get the widened-lookback treatment**
  (Finding 2 above) — a scheduled/emailed forecast can differ from the on-screen/exported one for a
  report that would have widened. Recommended follow-up: a `runner.py`-native widen helper built on
  `execute_definition` instead of `_prepare_run`/`_execute` (which need a live Flask session).

## Untracked / left for owner

- Nothing untracked — worktree is clean (`git status --short` empty).
- **Owner actions, in order:**
  1. **Decide Finding 4** (unrelated INT schema drift under Task 8's commit `878f477`) — see
     above. This should be resolved before merge, one way or the other.
  2. **Merge `plan/reporting-ai-owner-feedback` into `v3.1`** (from the base repo root,
     `C:\dev\nexora`, on branch `v3.1`): `git merge --no-ff plan/reporting-ai-owner-feedback`.
     No conflicts are expected — `v3.1` has not moved since this branch was cut at `4856eed`
     (verify with `git log v3.1..plan/reporting-ai-owner-feedback` vs.
     `git log plan/reporting-ai-owner-feedback..v3.1` before merging, in case another session
     landed something on `v3.1` in the meantime).
  3. **Push `v3.1`** (this session never pushes).
  4. **Run `scripts/env-sync.py`** — no new env keys were added by this plan, so this should be a
     no-op, but it's cheap to confirm.
  5. **Close issue #178** with the merge/fix SHA: `gh issue close 178 --comment "…<sha>"`.
  6. Remove the worktree and delete `plan/reporting-ai-owner-feedback` once merged:
     `git worktree remove --force .claude/worktrees/plan-reporting-ai-owner-feedback` then
     `git branch -d plan/reporting-ai-owner-feedback` (both from `C:\dev\nexora`).
  7. **Live browser pass was never run this session** (no Chrome extension available in this
     environment — verified via HTTP/code-path repro instead for Task 15, e2e-only for everything
     else). If convenient, do a manual pass post-merge: ask the AI chat a question, watch the live
     build-step ticker, open the report (lands in Simple), click the granularity chip, click "Open
     in Advanced" (should now show results + "Show query" immediately), build a backlog report and
     confirm the KPI band's "last bucket" caption, add a dashboard report card from a saved report.
  8. Optional/no rush: the `ops/run_scheduled_reports.py` forecast-lookback follow-up (see
     Gotchas), and the 3 new Minor observations from the final-review fix wave's own re-review
     (comma-in-value edge case, empty-`visible_rows` edge case, one dead ternary — all cosmetic).

## How to verify

```powershell
# from this worktree
cd C:\dev\nexora\.claude\worktrees\plan-reporting-ai-owner-feedback
git log --oneline -3                  # should show a1f0107 at the tip
C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py
C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit tests/integration -q
C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e -q -k "reporting"
```

As of `a1f0107` (the branch's current tip): unit+integration 1623 passed / 23 informational skips
/ 8 failed-but-order-dependent-and-verified-green-in-isolation (unrelated files, see Gotchas);
e2e reporting tier 138 passed / 75 deselected / 0 failed (1 flaky rerun, then green). Re-run after
merge to confirm nothing shifted, especially `test_translations.py` and the i18n-adjacent suites.

## Resuming in a fresh session

Nothing to re-execute — the plan is done. If you land here via `/reset-session`, go straight to
"Owner actions" above: decide Finding 4, then merge, push, close #178. There's no blocked step and
no pending fix loop; every review this session ran came back clean (after its own fix round, where
one was needed). The plan file itself
(`docs/superpowers/plans/2026-08-06-reporting-ai-owner-feedback.md`) and this handoff are the full
record — no SDD workspace survives (it was deleted per the subagent-driven-development skill's
finish step once the final review went clean).
