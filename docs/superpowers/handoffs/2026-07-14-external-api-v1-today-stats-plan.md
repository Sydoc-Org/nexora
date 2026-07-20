> **Newer same-date handoff:** the session pointer now targets
> `2026-07-14-external-api-v1-today-stats-execution-complete.md` (all 8 tasks implemented, tested,
> and live-verified on INT). This file's content remains valid for the plan-writing session itself.

# Handoff — External API v1 ("today" stats) plan written

**Date:** 2026-07-14 (evening) · **Branch:** `plan/external-api-v1-today-stats` (worktree
`.claude/worktrees/plan-external-api-v1-today-stats`, based on `feature/2.5.64` @ `97678a0`) ·
**commit-only (remote session — owner pushes)**
**Prior handoff:** `2026-07-14-pr119-merge-docfield-bleed-fix.md` (see forward-pointer banner added
to the top of that file)

## TL;DR

- **A complete implementation plan for the external client-facing API v1 is written, verified and
  committed** — `docs/superpowers/plans/2026-07-14-external-api-v1-today-stats.md` (commit
  `f3645bf`). **Nothing is implemented yet**; execution is the next session's job via
  `/execute-plan` inside this worktree.
- Scope: `GET /api/v1/stats/today` returns the dashboard's "imported today" / "exported (processed)
  today" KPI numbers as JSON for one external client's own dashboard, authenticated with per-client
  API keys (new `dbo.ApiKeys`, migration `0038`). One endpoint, one decorator, one table, one
  migration, tests, docs — deliberately no OAuth / key UI / OpenAPI in v1.
- The session started as a feasibility question ("how hard would an API be?"); a 4-agent recon
  established the big picture: **the app is already internet-reachable via ngrok**
  (`https://nexora.sydoc.ch`), the KPI data plumbing is already headless-capable, and the only
  genuinely missing piece is inbound machine auth — hence the small v1.
- The plan came out of a 7-agent planning workflow (3 explorers → 2 opposed drafts → adversarial
  red-team → merge). The red-team raised 8 findings (1 critical: rate-limiter decorator order is a
  security property); all are resolved in the final document, and the orchestrating session then
  re-verified every file/symbol/snippet anchor against the worktree by hand.

## This session's commits

- `f3645bf` — docs(plans): add external-api-v1-today-stats implementation plan
- (this handoff commit follows)

## What shipped

| File | Content |
|---|---|
| `docs/superpowers/plans/2026-07-14-external-api-v1-today-stats.md` | 1660-line plan: 8 tasks in 7 phases — migration `0038` (`dbo.ApiKeys` + `sql/test/schema.sql` mirror) → `compute_today_stats` extraction in `nx_lib/views/dashboard.py` → `nx_lib/api_auth.py` (`require_api_key`) → `nx_lib/views/api_external.py` endpoint + `create_app` wiring → JSON error handlers for `/api/v1` in `nx_lib/hooks.py` → `scripts/new-api-key.py` + `docs/howto/external-api.md` + CHANGELOG + CLAUDE.md → full test gate → live INT curl verification. Locked decisions D1–D16, Owner actions, Gotchas. |

## Key design decisions (full rationale in the plan's D1–D16 table)

- **Bearer API key**, `secrets.token_urlsafe(32)`, stored as SHA-256 hex, matched with
  `hmac.compare_digest`; **uniform 401** for unknown AND disabled keys (no existence oracle);
  **auth fails CLOSED** (503 on NexoraDB error) — deliberate deviation from the house fail-open
  pattern.
- **`@limiter.limit("60 per minute")` OUTERMOST**, above `@require_api_key` — the OPPOSITE of
  `reporting.py`'s stack, red-team-verified against flask-limiter 3.12: auth-outermost would leave
  the unauthenticated brute-force surface unthrottled. Pinned by a 429 test.
- **`compute_today_stats` stays inside `nx_lib/views/dashboard.py`** — existing tests monkeypatch
  `dv.engine_*`/`dv._ms02_stat_rows` as module attributes and call
  `dashboard_kpi_stats.uncached()`; a "cleaner" new module would break every seam.
- **`exported_today` = the dashboard's `processed_today` semantics verbatim**, including the
  T-SQL-leg asymmetry (export-today counted only among import-today rows) — API and dashboard must
  agree; changing it is Owner action 4.

## Next steps

1. **Fresh session → `/execute-plan`** — resumes at
   `docs/superpowers/plans/2026-07-14-external-api-v1-today-stats.md`, working **inside the
   existing worktree** `.claude/worktrees/plan-external-api-v1-today-stats` (branch
   `plan/external-api-v1-today-stats`). **Do NOT merge or remove the worktree before execution** —
   it is the execution vessel.
2. After execution: owner reviews, merges `plan/external-api-v1-today-stats` → `feature/2.5.64`,
   and pushes (pre-push gate runs the full suite incl. e2e; `scripts/test_db_reset.py` first if
   TEST state is stale).
3. Owner-only, after PROD deploy: issue the real client key + client comms (plan "Owner actions"
   1–2); sanity-check the 60/min rate limit (Owner action 3).

## Gotchas & notes

- **The worktree already has `env/INT.env` + `env/TEST.env`** copied from the main clone
  (gitignored) — the plan's Task 1 Step 1 is effectively pre-done; the SQL pre-commit hooks run for
  real in this worktree.
- **EOL stat-churn after SQL hooks:** the plan commit's `sql-sync-check` pass left ~68 per-object
  dump files under `sql/` showing ` M` in `git status` with a **0-byte `git diff`** (line-ending
  noise from the fresh-worktree regen). Cleaned with `git restore sql/`. Expect the same churn
  after future commits in this worktree — restore it, never commit it.
- **Migration `0038` was verified free** at planning time (dir tops out at `0037`); the plan
  re-checks at execution start (a prior handoff once earmarked 0038 in prose for a validationuser
  migration that never materialized).
- Plan-embedded test counts (20 dashboard unit / 23 dashboard integration / 42 hooks tests) were
  re-verified against the live files this session.
- **Recon findings worth remembering** (from the feasibility phase, not in the plan): the whole
  portal is internet-reachable through ngrok with **no tunnel auth** (an IP allowlist in ngrok's
  traffic policy would be cheap hardening — `ngrok.yaml` lives only on SYAPP01, outside git);
  `web.config` denies the OPTIONS verb (no browser CORS — the client's *server* must call us);
  every deploy restarts the ngrok service (brief public downtime; client needs retries).
- The first planning-workflow run lost 3 of 7 agents to a transient network outage (ENOTFOUND);
  resumed from the run cache — no quality impact, all 7 completed on the resume.

## Untracked / left for owner

- Main clone `C:\dev\nexora` has two untracked files (`package.json`, `package-lock.json`) — not
  this session's work (tool junk, most likely); left untouched.
- Nothing uncommitted in this worktree.

## How to verify

```powershell
git -C C:\dev\nexora\.claude\worktrees\plan-external-api-v1-today-stats log --oneline -3
# -> f3645bf docs(plans): add external-api-v1-today-stats implementation plan (+ this handoff)
git -C C:\dev\nexora\.claude\worktrees\plan-external-api-v1-today-stats status --porcelain
# -> clean (restore sql/ if EOL churn reappears)
```

No code changed this session — there is nothing new to test until `/execute-plan` runs.

## Resuming in a fresh session

- `/reset-session` picks this handoff up via `var/handoff-pending`. Several handoffs share the
  2026-07-14 date — if the flag is already consumed, target this file explicitly:
  `/reset-session docs/superpowers/handoffs/2026-07-14-external-api-v1-today-stats-plan.md`.
- Then run `/execute-plan` to implement the plan task-by-task.
