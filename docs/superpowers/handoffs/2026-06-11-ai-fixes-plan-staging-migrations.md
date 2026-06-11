> **Newer same-date handoff exists:** `2026-06-11-admin-ui-plan-redstrip-fix.md`
> (Generali red-strip fix + admin nexora-ui migration plan, on branch `feat/admin-ui-integration`).

# Handoff — Stakeholder tour findings → 16-task AI-fixes plan + STAGING unblocked

- **Date:** 2026-06-11
- **Branch:** `feature/2.5.63`. **5 commits ahead of `origin/feature/2.5.63`** (origin at
  `356bd4e`) — commit-only (remote); the owner pushes + opens the PR.
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-10-relative-tokens-ai-refine-complete.md`
  (F1 relative-date tokens + F2 AI refine complete, pushed).
- **This session's commits (oldest → newest):**
  - `554cfc3` docs(handoff): F1 relative-date tokens + F2 AI refine complete *(prior session's handoff — never pushed)*
  - `9f3bae4` docs(reporting): plan for the five AI bugs from stakeholder tour
  - `725fd71` docs(reporting): extend AI plan - metric consolidation + date rule
  - `fca66c0` feat(tooling): db-migrate accepts --env STAGING
  - `be2bdc8` docs(reporting): plan tasks 14-15 - tweak any Simple result

---

## TL;DR

1. **Stakeholder browser tour of `/reporting` on INT** (as ben.streich, screenshots in
   `var/screenshots/stake-*.png`): happy path works well (AI ask → cards/chips/table, refine,
   chip edits, save/library, wizard with correct month grain, Open-in-Advanced, complex
   2-dim×2-metric run, xlsx export). Six AI bugs found and audit-verified.
2. **`docs/superpowers/plans/2026-06-11-reporting-ai-fixes.md` — 16 TDD tasks, PLAN ONLY,
   nothing executed.** Covers all six bugs + the metric consolidation + "tweak any result".
3. **Measurement verdict (owner-tested on PROD):** `COUNT(*)`, `COUNT(WorkitemID)`,
   `COUNT(DISTINCT WorkItemID)`, `COUNT(Barcode)` all equal — stats tables are one row per
   workitem. `workitem_count` is redundant → plan Task 12 disables it (migration `0021`).
4. **STAGING 403 on /reporting fixed at the root:** STAGING NexoraDB had only migration `0001`;
   `db-migrate.py` now accepts `--env STAGING` (`fca66c0`) and all **19 pending migrations were
   applied to STAGING** this session. Permissions self-granted via the `0005` seed
   (profile has `admin.view`). Verified live in the browser with prod-copy volumes.

---

## The six AI bugs (full detail in the plan's Background section)

| # | Bug | Plan task |
|---|-----|-----------|
| 1 | No `this_quarter`/`last_quarter` tokens — "last quarter" → `last_3_months` (wrong window) | 1–3, 10, 11 |
| 2 | AI never emits `grain` — "per month" buckets per raw day while claiming monthly | 4 |
| 3 | "Distinct X per Y" → model groups by the counted field → every count = 1, gate says valid | 5–6 |
| 4 | Agent dead end: `run_sql` "unknown SQL target", audit shows ~every agent run = `max_turns`, empty answer | 7 |
| 5 | Metric-less source misdrafts + UI shows model explanation instead of gate error | 8–9 |
| 6 | "April 2026" filtered on **Document Date** instead of export/import date (owner-reported) | 13 |

Plus: Task 12 = migration `0021` disabling `workitem_count`; Tasks 14–15 = refine bar +
editable chips on **every** Simple result and an "Adjust in wizard" re-entry button
(owner request); Task 16 = full verification incl. 8 live browser checks.

## What shipped (code this session — only the STAGING unblock)

| File | Commit | What |
|------|--------|------|
| `scripts/db-migrate.py` | `fca66c0` | `--env` choices now `INT\|STAGING\|PROD` (STAGING applies without confirm, like INT) |
| `docs/howto/db-migrations.md`, `CLAUDE.md`, `CHANGELOG.md` | `fca66c0` | Doc sync for the new env target |
| *(STAGING DB state)* | — | Migrations `0002`–`0020` applied to STAGING NexoraDB; GeneraliDB was already current |

**STAGING root cause (for the record):** ben.streich's grants there were `generali.reporting.*`
(wrong family — that's the old Generali page), and the `reporting.%` codes didn't exist in
`dbo.Permission` at all (only migration `0001` was applied; `fnUserHasPermission` default-denies
unknown codes). After applying the migrations, `spGetUserPermissions(1019)` returns the full
18-code `reporting.*` set and the page renders (proof: `var/screenshots/staging-01-reporting-works.png`,
338'150 docs this year, real month buckets).

## Data finding that drove Task 12

- INT row-vs-distinct gaps were **test-data noise**.
- STAGING May: Posteingang 12'178 rows vs 11'379 distinct — but **729 of 799 extras are
  `WorkItemID IS NULL`** rows; only 12 workitems genuinely multi-document (~0.6%).
- PROD (owner-tested): all four count variants identical → one row per workitem, no NULLs.
- Decision (owner, via AskUserQuestion): **one metric only** — disable `workitem_count`,
  keep `doc_count`; `workitem_id` stays as a column/filter field.

## Next steps (ordered)

1. **Execute the plan:** `docs/superpowers/plans/2026-06-11-reporting-ai-fixes.md`, Tasks 1–16
   in order (verification is Task 16, run last). Subagent-driven execution recommended.
   Line anchors in the plan were verified against `be2bdc8` — match on quoted code if drifted.
2. **Owner: push + open the PR** — 5 commits waiting, incl. the 2026-06-10 handoff.
3. **PROD deploy checklist** (unchanged, from earlier handoffs): RO SQL logins, scheduled-reports
   Task Scheduler task, `0011` em-dash label repair; migrations auto-apply on deploy
   (now `0015`–`0021` once Task 12 lands).
4. Optional STAGING niceties: `env/STAGING.env` lacks the reporting RO SQL logins and the AI
   provider config → SQL tab and Ask-AI 503/hide there; copy from INT if wanted.
5. Optional cleanup: the stray `generali.reporting.*` `UserPermissionOverride` rows on
   ben.streich@STAGING (wrong-family grants from the 403 hunt) — remove via admin UI if unintended.

## Gotchas & notes

- **The dev server is still running against STAGING** (started with `nx -r --env:staging`).
  Run `& bin\nx.ps1 -r` to get back to INT before normal dev/e2e work.
- STAGING now has `0020`, so its wizard shows "Workitem count (distinct)" until plan Task 12
  (migration `0021`) executes and STAGING gets it (`python scripts/db-migrate.py --env STAGING`).
- gitlint: subject ≤ 72 chars (two commits bounced this session before passing).
- The `sql-migrate-int`/`sql-sync-check` hooks **passed** all session (INT reachable; the old
  CRLF-drift failure did not reproduce) — `SQL_SYNC_SKIP=1` was still prefixed out of habit and
  the plan's commit commands keep it; harmless either way.
- The AI result object quirk documented in plan Task 15: AI results set `fromWizard: true`
  (means "ephemeral") — the new wizard re-entry button must use the `builtBy: 'wizard'` marker.
- Stakeholder-tour artifacts: `var/screenshots/stake-01…16.png` + `staging-01-reporting-works.png`
  (gitignored, already sent to the owner).
- Memory `project_reporting_usability_gaps` updated with: gap-#3 live verification, the agent
  max_turns pattern, the PROD count-parity finding, and the plan pointer.

## Untracked / left for owner

- Nothing uncommitted in the repo (clean tree).
- Throwaway query scripts live outside the repo in `%TEMP%\nx-stake\` (staging_months.py,
  staging_dupes.py, staging_perms.py, audit_peek.py) — disposable evidence gatherers.

## How to verify

```powershell
# Suites (all green as of the 2026-06-10 push; this session changed no app code):
.venv\Scripts\python.exe -m pytest tests\unit\ tests\integration\ -q

# STAGING is fully migrated:
.venv\Scripts\python.exe scripts\db-migrate.py --env STAGING --dry-run   # expect: up-to-date

# STAGING reporting works (server must run with --env:staging):
# /dev/login/ben.streich -> /reporting -> wizard runs with real volumes
```

## Resuming in a fresh session

Run `/reset-session` (reads `var/handoff-pending`) or
`/reset-session docs/superpowers/handoffs/2026-06-11-ai-fixes-plan-staging-migrations.md`.
The single resume point is: **execute
`docs/superpowers/plans/2026-06-11-reporting-ai-fixes.md` starting at Task 1** (no task has
been started). Ask the owner whether to run subagent-driven or inline before starting.
