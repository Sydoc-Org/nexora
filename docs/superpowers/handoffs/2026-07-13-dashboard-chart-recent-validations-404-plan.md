# Handoff — Dashboard PROD bugs (Recent-Validations 404 + non-PDBS chart blank) — PLAN written

**Date:** 2026-07-13 (evening) · **Branch:** `feature/2.5.64` · **+7 unpushed at handoff-write time** (+1 with this handoff) · **commit-only (remote session — owner pushes)**
**Prior handoff:** `2026-07-13-docfield-permission-gating-plan.md` (same day — that effort's EXECUTION is running concurrently in this tree, see Gotchas)

## TL;DR

- A **complete implementation plan** for the two PROD dashboard bugs is written and committed
  (`b7531ba`): `docs/superpowers/plans/2026-07-13-dashboard-chart-recent-validations-404.md`.
  **No product code changed this session** — planning only.
- Bug 1 (**confirmed**, do not re-investigate): the Recent Validations card onclick uses a
  root-relative `/workitems?search=<id>` that escapes the `/nexora` PROD prefix
  (`PrefixMiddleware`, wired only when `ENVIRONMENT=PROD`) → IIS root-site 404. Same latent defect
  class found in the reporting `api()` helpers/fetches, the error pages, and the prepared-docs
  partial — the plan sweeps all of them + adds a permanent template-lint test.
- Bug 2 (**failure geometry confirmed, PROD trigger not yet**): a failing default StatisticsDB
  (T-SQL) leg 500s `dashboard_processed_over_time` (and its three siblings) before the healthy
  MS02/Postgres leg runs, and the 500 gets pinned in the response cache — hence "only PDBS works".
  Plan Task 3 is a bounded **read-only** PROD diagnosis (owner authorized: SMB app.log on SYAPP01 +
  read-only SELECTs) with an A–E decision tree; Tasks 4–6 are unconditional resilience fixes.
- This ran through the full `/write-plan` multi-agent workflow (3 explore → 2 opposed drafts →
  red-team: 7 findings → merge; run `wf_9488ebd7-ed3`, survived a mid-run account-limit upgrade).
  **Every anchor was re-verified by the orchestrator** (75 scripted verbatim checks + manual
  route-shape reads) after the merge.
- **Next: `/execute-plan`** — but coordinate with the concurrent docfield execution first (below).

## This session's commit

```
b7531ba  docs(plans): add dashboard-chart-recent-validations-404 plan   (this session)
```

(The other unpushed commits — `1995473`, `cd73a8a`, `674207d`, `a32c7c7`, `9b54052`, `bdfbb11` —
belong to the pr115/docfield efforts, not this session.)

## What the plan covers (so you don't re-derive it)

- **Task 1–2 (Bug 1):** card onclick → `${API_PREFIX}workitems?...` (idiom already on line 4 of
  `_dashboard_js.html`); error-page home links → `url_for('index')`; normalize the four reporting
  `api()` helpers (33 call sites untouched), 4 bare fetches, and the prepared-docs
  `window.API_PREFIX || "/"` fallback (`window.API_PREFIX` is assigned nowhere); new
  `tests/unit/test_template_url_prefix.py` lint ships allowlist-free.
- **Task 3 (Bug 2 diagnosis):** self-contained pyodbc probe (parses `env/PROD.env`, no `nx_lib`
  import), app.log read, per-row chart-subquery replay, A–E branch table; result appended to the
  plan file itself.
- **Task 4–6:** `_default_stat_rows` mirror of `_ms02_stat_rows` in all four legacy endpoints
  (per-leg isolation), `response_filter=_cacheable_response` on the four cache decorators (errors
  never pinned; proven by an integration test), `response.ok` guard in the chart updater
  (console-only → **no i18n cycle**).
- **Task 7/8 (conditional on diagnosis branch B/C):** corrective idempotent Statconfig data
  migration (next free number was **0036** — re-list at execution time) / `_bracket_tsql_name`
  SQL-builder fix.
- **Task 9–10:** changelog + fixes the stale CLAUDE.md PrefixMiddleware bullet; live INT browser
  verification with screenshots.

## Next steps (ordered)

1. **Check the concurrent docfield execution finished** (its handoff will say so; its plan is
   `docs/superpowers/plans/2026-07-13-docfield-permission-gating.md`). Two sessions editing
   `feature/2.5.64` simultaneously is asking for staged-file collisions.
2. **`/execute-plan`** → `docs/superpowers/plans/2026-07-13-dashboard-chart-recent-validations-404.md`,
   task-by-task (subagent-driven). Re-run `git status` / `git log` / re-list
   `sql/_migrations/NexoraDB/` at start — the plan's snapshot is from this evening.
3. Owner actions live in the plan (`O1`–`O3`): PROD delivery/spot-check, and the branch-A/branch-D
   infra chases if the diagnosis lands there.

## Gotchas & notes (READ before executing)

- **CONCURRENT SESSION IS LIVE IN THIS TREE:** during this handoff,
  `tests/integration/test_workitems_routes.py` picked up uncommitted edits (+37 lines) from the
  docfield-execution session, and commits `a32c7c7`/`9b54052`/`bdfbb11` landed mid-planning-run.
  Never `git add -A`/`.`/`-u` — only explicit paths. If its uncommitted edits are still present
  when you start, ask the owner whether that session is still running.
- **INT SQL is unreachable from this box right now** ("Der angegebene Host ist unbekannt" —
  likely off-VPN): every commit needs `SQL_SYNC_SKIP=1 git commit ...` until it's back. The Task 3
  INT comparison probe and Task 7's auto-apply also need INT reachable.
- **Migration numbering:** `0035` is taken (docfield). Plan says 0036-next — re-verify.
- The plan's Bug-2 tests rely on flask-caching's `.uncached` and on monkeypatching engines **on the
  view module** (`nx_lib.views.dashboard.engine_*`) — rationale and traps are in the plan's Context
  + Gotchas sections; don't improvise around them.
- PROD access for Task 3 is **read-only and bounded** — no writes, no restarts, no config edits,
  no secrets in output. That authorization came from the owner this session.

## Untracked / left for owner

- `package.json` + `package-lock.json` sitting untracked at repo root — **not mine, not
  committed**; they appeared alongside plugin/tooling activity. Owner: delete or claim them (if
  committed by accident they'd also need `deploy.yml` excludes).
- `tests/integration/test_workitems_routes.py` modified — belongs to the concurrent docfield
  session; untouched by me.
- All 8 unpushed commits are the owner's to push (full pre-push gate; e2e tier).

## How to verify

```powershell
# From C:\dev\nexora (feature/2.5.64):
git log --oneline origin/feature/2.5.64..HEAD   # 8 commits incl. b7531ba + this handoff
git show --stat b7531ba                          # the plan file, 942 lines
# The plan is the deliverable — open it:
#   docs/superpowers/plans/2026-07-13-dashboard-chart-recent-validations-404.md
# No tests run this session (planning only). Executor's per-task tests are in the plan.
```

## Resuming in a fresh session

Run `/reset-session` (the `var/handoff-pending` flag points here), then follow "Next steps".
**Four handoffs share today's date** — if the flag is gone, target this file explicitly:
`/reset-session docs/superpowers/handoffs/2026-07-13-dashboard-chart-recent-validations-404-plan.md`.
The plan to execute: `docs/superpowers/plans/2026-07-13-dashboard-chart-recent-validations-404.md`.
