# Handoff — Reporting Forecast Toggle (#168): execution complete, ready to merge

**Date:** 2026-08-05 · **Branch:** `plan/reporting-forecast-toggle` (worktree
`.claude/worktrees/plan-reporting-forecast-toggle`, cut from `feature/2.5.65` @ `e5eea54`) ·
**commit-only — owner pushes**
**Prior handoff:** `2026-08-05-reporting-forecast-toggle-plan.md` (same date — see note below;
`/reset-session docs/superpowers/handoffs/2026-08-05-reporting-forecast-toggle-execution-complete.md`
targets this file specifically if the auto-picker grabs the wrong one)

## TL;DR

- All 10 tasks of `docs/superpowers/plans/2026-08-05-reporting-forecast-toggle.md` (5 phases) are
  **implemented, tested, and merged into `feature/2.5.65`** via subagent-driven development — this
  session executed the plan end to end, ran 5 phase-scoped combined reviews + 1 final whole-branch
  review, fixed everything each review found, and merged.
- **The worktree has been removed and its branch deleted** (per `--merge-worktree`) — `feature/2.5.65`
  now has the feature at its tip. There is nothing left to execute; the plan's workspace
  (`.superpowers/sdd/...`) was deleted too, git history is the record.
- Final review caught one real, plan-anticipated bug before merge: Simple tab's display zero-fill
  (This year/month/quarter/week presets) was colliding with the forecast's anchor bucket, producing
  duplicate rows/labels — fixed, with a genuine regression test, in the last commit
  (`83023b5`).
- Issue #168 is **not yet closed** — that's an owner action after push (see Next steps).

## This session's commits (oldest → newest, on `plan/reporting-forecast-toggle` before merge)

| Commit | What |
|---|---|
| `dcd7c07` | Task 1 — `forecast_series` core (OLS trend + seasonal indices + prediction intervals) |
| `aa8d4ea` | Task 2 — `compute_forecast` + `forecast_export_rows` |
| `6ab96ee` | Task 3 — schema validation for the `forecast` definition block |
| `7ed5821` | Task 4 — `/api/reporting/run` forecast payload block |
| `77518ac` | Task 5 — Simple toggle/horizon UI, chart dashed line + band |
| `d8b2b6a` | Task 6 — Simple marked table rows + drill exclusion |
| `865e202` | **PHASE 2 fix round** — legend was leaking the forecast line; a chart note was getting clobbered |
| `7b0298b` | Task 7 — Advanced toggle, viz overlay, grid rows |
| `6b09170` | Task 8 — exports mark forecast rows (marker column, xlsx grey-italic) |
| `7ef3280` | Task 9 — scheduled mails carry the forecast + runner `grainable_fields` drive-by fix |
| `3f5df90` | **PHASE 4 fix round** — `forecast_export_rows` was unguarded in the scheduled runner |
| `99eae4f` | Task 10 — i18n cycle (de/fr/it), changelog, docs, full verify |
| `83023b5` | **Final-review fix round** — zero-fill/anchor collision, 2 stale-toggle-state bugs (Simple) |

Then merged (`--no-ff`) into `feature/2.5.65` and the worktree/branch were removed — see
"Worktree cleanup" below for the merge commit hash.

## What shipped

| # | Item | Files |
|---|---|---|
| 1 | Pure-stdlib forecast engine: OLS trend + additive seasonal indices per grain, 95% prediction intervals, zero-clamp for nonnegative series | `nx_lib/reporting/forecast.py`, `tests/unit/test_reporting_forecast.py` |
| 2 | Definition schema gains optional `forecast: {enabled, horizon}`, whitelist-validated | `nx_lib/reporting/schema.py` |
| 3 | `/api/reporting/run` bolts on a `forecast` response block (same pattern as `comparison`) | `nx_lib/views/reporting.py`, `tests/integration/test_reporting_routes.py` |
| 4 | Simple tab: toggle + horizon select, dashed chart line + band, marked table rows, drill exclusion | `templates/_reporting_simple.html`, `templates/js/_reporting_simple_js.html`, `static/css/reporting.css`, `tests/e2e/test_reporting_simple.py` |
| 5 | Advanced tab: same UX mirrored into the builder + viz + grid | `templates/reporting.html`, `templates/js/_reporting_js.html`, `templates/js/_reporting_viz_js.html`, `tests/e2e/test_reporting.py` |
| 6 | Exports (csv/xlsx) gain a trailing `Forecast` marker column; xlsx styles predicted rows grey-italic | `nx_lib/reporting/export.py`, `nx_lib/views/reporting.py`, `tests/unit/test_reporting_export.py` |
| 7 | Scheduled mails: PNG gets a dashed extension + band, attachment gets marked rows; drive-by fix for a latent runner bug (missing `grainable_fields` bounced any scheduled table-source report with a date grain) | `nx_lib/reporting/chart_render.py`, `nx_lib/reporting/runner.py`, `ops/run_scheduled_reports.py`, `tests/unit/test_reporting_chart_render.py`, `tests/unit/test_reporting_runner.py` |
| 8 | i18n (6 new msgids, de/fr/it, non-fuzzy), changelog, `docs/howto/reporting.md` "Forecast" section + definition-JSON key doc | `messages.pot`, `translations/*/LC_MESSAGES/*`, `CHANGELOG.md`, `docs/howto/reporting.md` |

## Review history (all clean before merge)

- **PHASE 1** (Tasks 1-4): Approved, no Critical/Important. 4 Minor deferred (see ledger excerpt
  below — the ledger itself was deleted with the workspace, key points captured here).
- **PHASE 2** (Tasks 5-6): 1 fix round — legend leaked the forecast dataset (D6 violation — the
  plan's own code snippet only filtered `_band`, its text said `_band`+`_forecast`; resolved in
  favor of the stated decision) + a chart-note clobber bug. Both fixed, re-reviewed clean.
- **PHASE 3** (Task 7): Approved, no Critical/Important — explicitly verified the Phase 2 legend fix
  carried forward correctly from the start (Advanced implementer was told about it up front).
- **PHASE 4** (Tasks 8-9): 1 fix round — `forecast_export_rows` was unguarded in the scheduled
  runner, violating the "forecast failure must never take down the run" policy. Fixed + new
  regression test proving mail still sends on a marking failure.
- **PHASE 5** (Task 10): Approved, clean — i18n/changelog/docs verified consistent, full verify
  green (1609 passed/30 informational skips/0 failed non-e2e; 88 e2e passed). **Live browser pass
  was skipped** (documented reason: worktree had no `env/INT.env`, and the `nx` CLI is hardcoded to
  `C:\dev\nexora` which had a separate concurrent session running) — the automated e2e suites
  covered the surface instead.
- **Final whole-branch review** (most capable model, cross-cutting pass): "With fixes" — found 3
  Important items the phase-scoped reviews structurally couldn't see:
  1. **Zero-fill/anchor collision (Simple tab)** — the plan's own flagged gotcha
     ("Gotchas & notes" → *Client zero-fill vs server forecast*), deferred to the skipped manual
     check. `zeroFillDateBuckets` fills to the filter's date-range end (e.g. "This year" → Dec 31);
     `compute_forecast` anchors at the last real data bucket. For any current-period token with
     incomplete data, this duplicated buckets between fake trailing zeros and the appended forecast.
     Fixed: rows are trimmed to `forecast.anchor` before both chart and table consume them, in one
     shared point. New regression test: `test_forecast_trims_zero_filled_rows_past_anchor`.
  2. **Simple never cleared a stale `def.forecast` on ineligibility** (Advanced did) — fixed to
     mirror Advanced.
  3. **Toggle UI went stale on Simple's empty-result/error paths** — fixed by calling
     `syncForecastCtl` on those early-return branches too.
  - Re-reviewed clean: all 3 addressed, no new breakage. e2e 89 passed, unit+integration
    reporting-forecast suites 72 passed.
  - One out-of-scope observation, deferred (not blocking, not part of this fix): `renderKpiBand`
    still reads the un-trimmed zero-filled `rows`, so the KPI band could still be diluted by fake
    trailing zeros when forecast is on for a current-period token. Follow-up ticket candidate.

## Gotchas & notes

- **Pre-existing, unrelated repo bug found and flagged (NOT fixed here):** `matplotlib` has been
  missing from `requirements.txt` since commit `472a353` (2026-06-16) even though
  `nx_lib/reporting/chart_render.py` imports it unconditionally. A clean-checkout
  `pip install -r requirements.txt` fails `tests/unit/test_reporting_chart_render.py` collection
  **today, on any branch** — this branch's new chart-render tests inherit that failure on a truly
  clean venv (worked around locally by installing matplotlib directly into the worktree's `.venv`,
  `requirements.txt` itself was left untouched as out of scope). **Worth a one-line follow-up fix
  on `feature/2.5.65`** (re-add `matplotlib` to `requirements.txt`) — flagging for the owner, not
  yet actioned.
- **Deferred by design (plan "Owner actions", never revisited):** multi-metric bands, exported
  bounds columns, AI assistant awareness of the forecast key.
- **Minor findings deferred across all phases** (none blocking, none fixed): stale
  `def.forecast` edge cases already covered by the final fix; `_resolve_horizon` duplication;
  `_t_quantile` dead-code branch; `.reporting-forecast-ctl` (Advanced checkbox) has no CSS — renders
  with default browser styling vs Simple's polished toggle; no "not enough history" messaging in
  Advanced (Simple has it); legend force-on (`|| fcActive` / `|| !!fcSeries`) is self-cancelling
  since the very next filter strips exactly what it forced visible; `onHover` still promises a
  cursor-pointer on forecast/band points that `onClick` correctly refuses to drill; horizon values
  outside the four offered `<select>` options (`auto/7/14/30`) round-trip to an empty string on
  reload even though the schema allows `1..60`; PNG unit test only checks magic bytes, not that the
  dashed line/band are actually drawn.
- **`nx_lib/reporting/chart_render.py`** — two small Minor gaps noted by the final review, not
  fixed: `forecast["series"][0]` access is unguarded against an empty `series` list (never produced
  by `compute_forecast` today, but `forecast=` is a public kwarg); the overlay guard requires
  `chart_type in ("line", "bar")` but the plotting chain's `else` renders a bar for any unrecognized
  `chartType`, so an oddball `chartType` value would show a forecast on screen but not in the mail.
- **Worktree removed:** `.claude/worktrees/plan-reporting-forecast-toggle` no longer exists as a
  registered worktree — don't look for it. The plan's SDD workspace
  (`.superpowers/sdd/2026-08-05-reporting-forecast-toggle/`) was deleted after the final review went
  clean, per the subagent-driven-development skill's finish step — the ledger detail above is
  reconstructed from this session's transcript, not a surviving file.

## Untracked / left for owner

- Nothing untracked survived — a stray `.git_commit_msg.txt` scratch file (left behind by one of
  the implementer subagents after a `git commit -F -` heredoc) was found and deleted before this
  handoff; it was never part of any commit.
- **Owner actions, in order:**
  1. Review the merged `feature/2.5.65` (this session merged `plan/reporting-forecast-toggle` into
     it directly, `--no-ff`, and deleted the source branch — see "Worktree cleanup" below for the
     merge commit).
  2. **Push `feature/2.5.65`** (this session is commit-only, never pushes).
  3. **Close issue #168** with the fix SHA once pushed: `gh issue close 168 --comment "…<sha>"`.
  4. Optional/no rush: fix the `matplotlib` / `requirements.txt` gap flagged above (unrelated
     pre-existing bug); consider a follow-up ticket for the `renderKpiBand` un-trimmed-rows
     observation; consider closing the CSS gap on `.reporting-forecast-ctl` for Advanced/Simple
     visual parity.
  5. **The live browser pass from Task 10 was never actually run** (environment-forced skip). If
     convenient, do it once: open `/reporting`, build a Backlog History (or docprocessing doc-count)
     report broken down by month over "This year", toggle Forecast, check the dashed line + band +
     marked rows in light **and** dark theme, click a forecast point (nothing should happen), export
     CSV and confirm the marker column — this is the same check the plan originally asked for.

## How to verify

```powershell
# from feature/2.5.65 (worktree gone — run from the main checkout C:\dev\nexora)
git log --oneline -20                 # forecast commits should be present, merged
C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py
C:\dev\nexora\.venv\Scripts\python -m pytest tests --ignore=tests/e2e -q
C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py tests/e2e/test_reporting.py -q
```

All suites were green as of `83023b5` (pre-merge): 1609 passed/30 informational skips/0 failed
(non-e2e), 89 e2e passed. Re-run after merge to confirm nothing shifted.

## Resuming in a fresh session

There is no pending execution work for this plan — it's done and merged. If you land here via
`/reset-session`, there's nothing to resume: check `git log` on `feature/2.5.65` to confirm the
merge landed, then move to the owner actions above (push, close #168) or pick up a new task.
Because this handoff shares today's date with the plan handoff
(`2026-08-05-reporting-forecast-toggle-plan.md`), that older file now carries a forward-pointer
banner at its top — if `/reset-session` picks it up instead, follow the banner here.
