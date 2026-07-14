# Handoff — Dashboard PROD bugs (Recent-Validations 404 + non-PDBS chart blank) — ALL TASKS DONE

**Date:** 2026-07-14 (morning) · **Branch:** `feature/2.5.64` (merged from worktree branch `plan/dashboard-chart-recent-validations-404`) · **commit-only (remote session — owner pushes)**
**Prior handoff:** `2026-07-13-dashboard-chart-recent-validations-404-plan.md` (same effort, prior day — plan written, ready to execute)
**Plan:** `docs/superpowers/plans/2026-07-13-dashboard-chart-recent-validations-404.md` (updated in place during execution — see below)

## TL;DR

- **Both PROD bugs are fixed, tested, and live-verified on INT.** Executed via
  `subagent-driven-development` in an isolated worktree (a concurrent docfield-permission-gating
  session was live in the main checkout at the same time). 9 commits merged into `feature/2.5.64`.
- **Bug 1** (Recent Validations card 404): fixed — the card, error pages, and a full sweep of
  reporting/prepared-docs partials now route through `API_PREFIX`; a new permanent lint test
  (`tests/unit/test_template_url_prefix.py`) blocks regressions allowlist-free.
- **Bug 2** (chart blanks for non-PDBS processes): the plan's original diagnosis (Task 3) was run
  **twice**. First attempt was inconclusive — this dev box had no VPN/network path at the time.
  Connectivity came back mid-session; the **redo found the real root cause**: a Python `TypeError`
  from mixing `str`-typed dates (legacy T-SQL driver) with `datetime.date`-typed dates (MS02 leg +
  zero-fill) when sorting a merged dict — 83 confirmed PROD `app.log` occurrences over two weeks,
  reproduced locally byte-for-byte. **This did not map onto the plan's A–E branch taxonomy**, so a
  new task ("Task 5.5") was added mid-execution with owner approval and fixed directly. Per-leg
  isolation (Tasks 4/5, the plan's original scope) and cache-error-pinning (Task 6) also shipped —
  real hardening, but NOT what was actually blanking the chart.
- **Live-verified via Playwright on INT** (Task 10): chart renders real merged data from both a
  default-leg process (`01_Invoice_SAP`) and MS02 (`05_PDBS`) simultaneously — the exact scenario
  that used to 500. Screenshots sent to the user.
- **Full local gate: 1237 passed, 1 failed (unrelated), 25 skipped.** Final whole-branch review:
  **Ready to merge = Yes**, 0 Critical/Important findings, 2 Minor (non-blocking, noted below).
- **Worktree merged and removed** — `plan/dashboard-chart-recent-validations-404` no longer exists;
  all its commits are now on `feature/2.5.64`.

## This session's commits (on `feature/2.5.64` after merge, oldest→newest)

```
6ad0340  fix(dashboard): route Recent Validations card through API_PREFIX
5dbe34b  fix(templates): sweep remaining root-relative URLs behind the prefix
87a4bad  docs(plan): record PROD dashboard-stats diagnosis result           (1st attempt, inconclusive)
e0b2c37  fix(dashboard): isolate default T-SQL leg in processed_over_time
32d1e7b  fix(dashboard): per-leg isolation for kpi/hourly/avg endpoints
f5695ff  docs(plan): redo Bug-2 PROD diagnosis, connectivity restored      (2nd attempt, conclusive)
e74367d  fix(dashboard): normalize default-leg date type in processed_over_time   (Task 5.5 — the real fix)
d4d875c  fix(dashboard): stop caching error responses; guard chart fetch
eaa3acf  docs: changelog for dashboard fixes + correct PrefixMiddleware note
```

Plus a merge commit on `feature/2.5.64` (`git merge --no-ff plan/dashboard-chart-recent-validations-404`).

(Earlier same-branch work from the concurrent docfield session — `bdfbb11`, `9b54052`, `a32c7c7`,
`ae83bcb`, `0dbceeb`, `0c7935e`, `97a5de2`, `ee524d7`, `66ca845`, `cc712df` — is **not** this
session's, already merged/present before this worktree was created.)

## What shipped

| Area | Files | Commits |
|---|---|---|
| Bug 1 fix + lint guard | `templates/js/_dashboard_js.html`, `templates/handlers/_error_base.html`, `tests/unit/test_template_url_prefix.py` (new) | `6ad0340` |
| Bug 1 sweep (reporting, prepared-docs) | `templates/js/_reporting_js.html`, `_reporting_simple_js.html`, `_reporting_sources_js.html`, `_reporting_metrics_js.html`, `_reporting_ai_js.html`, `_prepared_documents_js.html` | `5dbe34b` |
| Bug 2 diagnosis (both attempts, same plan-file section) | `docs/superpowers/plans/2026-07-13-dashboard-chart-recent-validations-404.md` | `87a4bad`, `f5695ff` |
| Per-leg isolation (`_default_stat_rows`) | `nx_lib/views/dashboard.py`, `tests/unit/test_dashboard_stats.py` | `e0b2c37`, `32d1e7b` |
| **Bug 2 real root-cause fix (Task 5.5)** | `nx_lib/views/dashboard.py` (date-type normalization), `tests/unit/test_dashboard_stats.py` (repro test), plan doc (new `## Task 5.5` section) | `e74367d` |
| Cache-error hardening | `nx_lib/views/dashboard.py` (`_cacheable_response`), `templates/js/_dashboard_js.html` (`response.ok` guard), `tests/unit/test_dashboard_stats.py`, `tests/integration/test_dashboard_routes.py` | `d4d875c` |
| Docs | `CHANGELOG.md` (3 bullets), `CLAUDE.md` (PrefixMiddleware correction) | `eaa3acf` |

Plan tasks 7 and 8 (conditional on PROD diagnosis branch B/C) were **skipped** — not applicable, the
real finding was a "sixth case" outside the A–E taxonomy, fixed directly as Task 5.5.

## Next steps (owner actions — from the plan's own "Owner actions" section)

1. **O1 — push + PR + deploy + spot-check.** Review `feature/2.5.64`, push, open/merge the PR (full
   pre-push gate incl. Playwright e2e — run `python scripts/test_db_reset.py` first if stale TEST
   state trips anything). After deploy: click a Recent Validations card on PROD (should land on
   `/nexora/workitems?search=<id>`), check the chart + KPI cards for a non-PDBS process, load
   Reporting + Prepared Documents watching console for 404s. Response cache TTL means up to ~5 min
   per user+filter, per IIS worker, before you see the fix live.
2. **O2/O3 — not applicable.** These were conditional on Task 3 landing on branch A (StatisticsDB
   connectivity) or D (dead ingest) — neither applied; StatisticsDB connectivity and ingest are both
   healthy on PROD, confirmed by the redone diagnosis.
3. **Two Minor follow-ups from the final review** (not blocking, no action required now):
   - `dashboard_field_metadata` has an analogous uncached-error-pinning risk to what Task 6 just
     fixed for its four siblings (1-hour TTL, no `response_filter`) — not touched by this plan
     (never touches StatisticsDB), but worth a follow-up if it ever misbehaves.
   - The date-normalization guard (`isinstance(row.d, date)`) is theoretically narrower than an
     unconditional `date.fromisoformat(...)` would be (a hypothetical `datetime.datetime` return
     would slip past `isinstance` unnormalized) — purely theoretical, live diagnosis confirmed the
     actual PROD type is always `str`.

## Gotchas & notes (READ before touching this area again)

- **The plan's own A–E decision tree doesn't cover every failure mode** — this session found a
  "sixth case" (a Python-level type-coercion bug, not a connectivity/data/SQL-syntax/transient
  issue) that required extending the plan mid-execution. If diagnosing a similar "only PDBS works"
  symptom again, don't assume it's always the same root cause — the per-leg isolation fixes
  (Tasks 4-6) are real hardening but were NOT sufficient on their own to fix this bug, because the
  type-mismatch collision happens strictly **after** both legs' SQL already succeeds.
- **Dev box network connectivity was flaky mid-session** — off-VPN with no path to
  PROD/INT/SYAPP01 for the first ~3 hours (confirmed via DNS resolution failure and identical
  DBNETLIB errors on both environments), then came back with no action on this end. If you hit
  similar "SQL Server existiert nicht" errors, check basic connectivity (`Resolve-DnsName SYAPP01`)
  before assuming a PROD-specific credential/firewall problem.
- **A subagent briefly committed to the wrong branch early in execution** (Task 1's implementer
  worked in the main `C:\dev\nexora` checkout instead of the assigned worktree, landing a commit
  directly on `feature/2.5.64` on top of the concurrent docfield session's work). Caught
  immediately via independent verification (never trust a subagent's self-reported branch/location
  claim — always `git log`/`git branch --show-current` yourself), recovered via cherry-pick onto
  the correct worktree branch + `git revert` (not `reset --hard`, since the concurrent session was
  still actively committing) on the shared branch. No lasting damage; flagged as a lesson for
  future worktree-isolated executions to verify subagent location independently after every task,
  not just trust the "Work from: <path>" instruction in the dispatch prompt.
- **`sql/*.sql` dump files show as modified in `git status` in this working tree** (~67 files,
  `NexoraDB`/`GeneraliDB` per-object dumps) — confirmed via `git diff` (zero actual byte
  differences) to be pure line-ending noise from `sql/sync-from-db.py` running for real once INT
  connectivity was restored (previously skipped via `SQL_SYNC_SKIP=1`). **Not real schema drift.**
  Left untouched throughout; if it's still there, it's harmless — don't stage it accidentally with
  a broad `git add`.
- **Full local gate has one pre-existing unrelated failure**:
  `tests/integration/test_workitems_routes.py::test_api_config_fields_perm_state_in_cache_key`.
  Confirmed (both by the plan's execution and independently by the final reviewer) to be unrelated
  to this plan — passes in isolation, passes combined with the dashboard tests, and the diff never
  touches `nx_lib/views/workitems.py`/`nx_lib/hooks.py`/`nx_lib/extensions.py`. Believed to be a
  full-suite ordering artifact tied to the concurrent docfield-permission-gating work. Not chased.
- **The dev server for Task 10's live verification was started from the worktree's own
  `bin/nx.ps1`** (not the main repo's global `nx` command, which is hardcoded to
  `C:\dev\nexora`) — `$AppDir` self-resolves from the invoked script's own path, so running
  `<worktree>\bin\nx.ps1 -u -b --loginas:...` correctly served the worktree's code. If you need to
  live-verify a worktree's code again, use this same trick rather than the global `nx` alias.
- **Chrome extension (`claude-in-chrome`) wasn't connected this session** — Task 10's browser
  verification used a standalone Playwright script instead (`playwright.sync_api`, already
  available in the shared `.venv`), driving the dev-login endpoint (`/dev/login/<username>`) and
  taking screenshots directly. Script lived in the session scratchpad, never committed.

## Untracked / left for owner

- `sql/*.sql` line-ending noise (see Gotchas above) — harmless, not staged.
- `package.json` / `package-lock.json` at repo root (pre-existing, noted in the original plan
  handoff as "not mine, left for owner" — still untouched, still there).
- Worktree `plan-dashboard-chart-recent-validations-404` — **removed** as part of this handoff
  (see below); nothing left behind.

## How to verify

```powershell
# From C:\dev\nexora (feature/2.5.64):
git log --oneline ceae954..HEAD          # this plan's 9 commits + the merge commit
.venv\Scripts\python -m pytest tests/unit/test_dashboard_stats.py tests/unit/test_template_url_prefix.py tests/integration/test_dashboard_routes.py -q --no-cov
# Full local gate (takes ~5 min): python scripts/test_db_reset.py first, then
.venv\Scripts\python -m pytest tests --ignore=tests/e2e -q
# Expect: 1237 passed, 1 failed (test_api_config_fields_perm_state_in_cache_key, unrelated), 25 skipped
```

Screenshots from the live INT verification (chart rendering, card-click navigation, 404 page) were
sent to the user via `SendUserFile` during the session — not committed to the repo (gitignored
`var/screenshots/`).

## Worktree cleanup

`plan/dashboard-chart-recent-validations-404` was merged into `feature/2.5.64` (fast-forward or
no-ff merge, whichever `git merge` produced) and the worktree at
`.claude/worktrees/plan-dashboard-chart-recent-validations-404` was removed; the worktree branch
was deleted. Confirmed via `git worktree list` — no longer present.

## Resuming in a fresh session

Nothing to resume for this plan — it's complete, merged, and live-verified. Only remaining step is
the owner's O1 (push/PR/deploy/spot-check) above. If a fresh session picks up `feature/2.5.64`, the
next thing to do is likely push + open the PR, not more plan execution.

**`var/handoff-pending` deliberately NOT overwritten by this handoff** — it currently points to
`docs/superpowers/handoffs/2026-07-14-execute-reporting-drill-through.md`, a different, still-fully-
pending plan (Tasks 2-8, zero code changes yet) from a concurrent/prior session. Overwriting it
would break that plan's resume path, and this plan has nothing left to resume. If you're picking up
fresh and expected to land here instead of the reporting-drill-through plan, target this file
explicitly: `/reset-session docs/superpowers/handoffs/2026-07-14-dashboard-chart-recent-validations-404-execution-complete.md`.
