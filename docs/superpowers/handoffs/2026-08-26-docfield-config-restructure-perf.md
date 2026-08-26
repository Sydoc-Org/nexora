> **Superseded for resume purposes** — see
> [`2026-08-26-post-merge-cleanup-resume-restructure-plan.md`](2026-08-26-post-merge-cleanup-resume-restructure-plan.md)
> (same date, later). This plan is still the one to execute; that file has the up-to-date branch/worktree
> state to resume from.

# Handoff — Issue #98: dead tables dropped, doc-field restructure planned

**Date:** 2026-08-26 · **Branch:** `v3.2.3.1` (main checkout, no worktree) · **2 commits this
session, unpushed** · commit-only (owner pushes) · tree otherwise clean (peer sessions were active —
`nexora-29` mid-push on this branch, `nexora-c0` prepping a CLAUDE.md trim on `chore/trim-agent-context`).

**Prior handoff:**
[`2026-08-26-dashboard-whole-report-card-execution.md`](2026-08-26-dashboard-whole-report-card-execution.md)
(different workstream, peer session — dashboard card, ready to merge from its own worktree).

## TL;DR

- Issue **#98** ("Restructuring of how the Document Field Values and Clients/Processes are mapped in
  the DB") is now **decided, phase 1 shipped, phases 2–3 fully planned**. Owner context that drove
  the decision: white-label rollout coming, 10–50 clients, non-dev onboarding via a future admin UI
  → **Approach B (normalize in DB)**, reversing the 2026-07-28 spec's YAML-in-git leaning.
- **Phase 1 landed** (`9cdb7319`): migration `0072` dropped all ten `decapitated_*` tables for good
  (drop-safety verified: zero live readers, FKs only among themselves), `0073` gave `StatConfig` a
  real composite PK + NOT NULL and `dbo.Logs` a `Timestamp` index (INT **and** PROD data verified
  first). Archived `views/invoices.py` + invoices/chat archive templates + their tests deleted.
  Both migrations already applied to INT; issue labeled `inprogress` with a progress comment.
- **Phases 2–3 plan committed** (`8703f4c6`):
  `docs/superpowers/plans/2026-08-26-docfield-config-restructure-perf.md` — 14 tasks, migrations
  `0074`–`0077`, all anchors Grep-verified. Execute next via `/execute-plan`.
- A background audit workflow (5 auditors + adversarial verify) hit the session usage limit after
  1 of 5 agents; the missing four audits were re-done inline in-session — findings are baked into
  the plan, nothing left in the dead workflow worth recovering.

## This session's commits (oldest → newest)

| Hash | What |
|---|---|
| `9cdb7319` | `refactor(db): drop decapitated tables, StatConfig PK, Logs index (#98)` — migrations 0072+0073, deletes `nx_lib/views/invoices.py`, `templates/archive/{invoices,chat}.html`, `templates/js/archive/{_invoices_js,_chat_js}.html`, `tests/unit/test_invoices_helpers.py`, ten `sql/NexoraDB/Tables/dbo.decapitated_*.sql` dumps; updates CLAUDE.md routing/Bexio lines, CHANGELOG, `nx_lib/__init__.py` comment, two test files (endpoint set + coverage thresholds). |
| `8703f4c6` | `docs(plans): add docfield-config-restructure-perf implementation plan` — the phases 2–3 plan (544 lines). |

## What shipped / what's planned

**Shipped (phase 1):** see `9cdb7319` above. Full test files touched ran green
(`test_create_app.py`, `test_coverage_thresholds.py`: 16 passed).

**Planned (phases 2–3), decisions locked in the plan:**

- `dbo.ProcessSources` merges `SearchConfig` table-plumbing + all of `StatConfig` (verified live on
  INT+PROD: `TableName` identical for all 6 `(ProcessName, ClientCode)` rows), PK
  `(ClientCode, ProcessName)`.
- Tall `dbo.ProcessFieldMappings` (kills the 36 wide `col_*` columns + the 5× `SELECT TOP 0`
  introspection hack), `dbo.FieldLabels`, `dbo.FieldAliases` (PK on `SourceFieldName` — the unique
  key `IndexFieldMappings` never had).
- One cached accessor `nx_lib/mapping_config.py` (60 s TTL, success-only, legacy failure contracts
  preserved verbatim — fail-closed external API, fail-closed doc-field search) replacing ~30 query
  sites across 6 files; file-by-file cutover; legacy tables decapitated at the end (migration 0075).
- Perf phase: `ColumnType`/`IdColumnType` seeded from live target DBs (generated migration 0076),
  sargable predicates (bare typed columns instead of `CAST(... ) COLLATE` / `::text ILIKE`), 60 s
  allow-set cache, batched `WorkitemSourceCache` lookups + composite PK `(WorkItemID, ClientCode)`
  (migration 0077).
- **Out of scope (phase 4, separate issue):** `dbo.Clients` registry table, admin onboarding UI,
  per-client branding — the white-label surface itself.

## Next steps (ordered)

1. `/execute-plan` on `docs/superpowers/plans/2026-08-26-docfield-config-restructure-perf.md` —
   start at Task 1 (migration `0074`). **Re-check migration numbering first** (`ls
   sql/_migrations/NexoraDB/ | tail -3` must end at `0073`; peers also number migrations).
2. After phases 2–3 land: file the phase-4 issue (Clients table + admin UI + branding) — the plan's
   "Out of scope" block and issue #98's comment thread carry the context.
3. Owner: review + push the two commits here (and the peer's dashboard branch merge, separately).

## Gotchas & notes

- **Peers were live this session** — nexora-29 was mid-push on `v3.2.3.1` (its commits may now be
  interleaved above mine in `git log`), nexora-c0 holds a CLAUDE.md trim on `chore/trim-agent-context`
  that it rebases on top of my `9cdb7319` CLAUDE.md edits. Check `ListAgents` + announce files before
  touching CLAUDE.md again.
- **Migrations 0072/0073 are already applied on INT** (pre-commit hook). PROD gets them on the next
  deploy — the drops are guarded/idempotent, and PROD's StatConfig was verified NULL-free/dup-free
  (6 rows) before the PK migration was written.
- The **dropped `decapitated_*` data is gone for good** on INT (renamed-not-dropped safety net since
  0042/0056 was deliberately burned, per owner's "delete them"). PROD still has the tables until
  deploy.
- The plan **supersedes the spec's Approach-A leaning** — `docs/superpowers/specs/
  2026-07-28-mapping-config-migration-design.md` was NOT edited (historical); the plan header
  documents the reversal and why.
- Workflow `wf_5ea7f7de-006` (schema audit) died on the session usage limit (resets 17:50
  Europe/Zurich) — 4 of 5 agents errored. Do NOT try to resume it; its surviving perf findings are
  in the plan's Phase C tasks already.
- Memory note `project_reporting_usability_gaps` says never re-plan alert-only schedules — untouched
  here, just confirming no overlap.
- **`sql-sync-check` now fails on any branch that predates `0072`** (reported by nexora-c0, who hit
  it): those branches still carry the ten `decapitated_*.sql` dumps, but INT no longer has the
  tables. Fix per branch: rebase/merge past `9cdb7319`, or commit with `SQL_SYNC_SKIP=1` and a
  pathspec (never absorb the SQL deletions into an unrelated commit).
- nexora-c0's CLAUDE.md trim landed as `95d4c9d1` on `chore/trim-agent-context` (branch is off
  `cbcd4749`/#191, so it carries the static-JS commit too). It was seeded from my `9cdb7319`
  CLAUDE.md, so my edits survive that merge.

## Untracked / left for owner

- Nothing untracked left by this session. Peer sessions' own dirt (e.g. `sql/**/Security/Users`
  dump drift in c0's worktree) was deliberately never staged.
- `gh` issue #98: labeled `inprogress`, phase-1 comment posted. Close only after phases 2–3 ship.

## How to verify

```powershell
git log --oneline -3                       # 8703f4c6, 9cdb7319 on v3.2.3.1
python scripts/db-migrate.py --env INT     # "up-to-date" (0072/0073 applied)
C:\dev\nexora\.venv\Scripts\python.exe -m pytest tests/unit/test_create_app.py tests/unit/test_coverage_thresholds.py -q --no-cov
gh issue view 98 --json labels,comments -q '.labels[].name'   # bug-free: enhancement + inprogress
```

## Resuming in a fresh session

Run `/reset-session docs/superpowers/handoffs/2026-08-26-docfield-config-restructure-perf.md` (a
same-date peer handoff exists — `/reset-session` without a path may pick the wrong one), then
`/execute-plan` on `docs/superpowers/plans/2026-08-26-docfield-config-restructure-perf.md`.
