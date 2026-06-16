# Handoff — MS02 client: merged multi-source workitems (spec + plan, design-only)

**Date:** 2026-06-16 (midday) · **Branch:** `feature/2.5.63` · **24 commits ahead of origin** · **commit-only (remote)**
**Prior handoff:** `docs/superpowers/handoffs/2026-06-16-plan-merge-and-dual-session-contention.md` (same date — see tie-break note under "Resuming")
**Durable context in auto-memory:** `project_ms02_multisource_workitems` (the full decision record — read it first), plus `project_int_migration_crlf_drift`, `reference_sql_migrations`, `feedback_caveman_speak`.

## TL;DR

- **Design-only session.** Brainstormed → specced → planned a **new feature**: integrate a new client **"MS02"** into the **shared** workitems list, detail page, CSV export, and dashboard. MS02's workitem runtime is on **Azure Postgres** (same Octo schema, PG dialect) and its Octo API is the **same API at a different domain + creds**. **No code was written** — output is a spec + a phased TDD plan, both committed.
- **Ready for `/execute-plan`** against `docs/superpowers/plans/2026-06-16-ms02-client-merged-workitems.md`. Phases 1–2 build with **no live MS02 access**; Phase 6 (dashboard stats) needs two small owner inputs (below).
- **Owner chose `/execute-plan` themselves** (not subagent-driven inline) — so this session stopped at the plan. The user fed real schema details late (doc-field index table, dashboard-stats table) which are fully folded into the spec/plan.

## This session's commits (oldest → newest)

```
8ca99d4  docs(workitems): design spec for MS02 merged multi-source workitems
6a7342b  docs(workitems): implementation plan for MS02 multi-source workitems
e2b82d0  docs(workitems): doc-field-per-source + MS02 dashboard stats   ⚠ also bundled dbo.ReportSchedules.sql (2-line INT drift) via `-am`
4e322b8  docs(workitems): MS02 dashboard stats = batchtracking (separate DB)
```
Plus the handoff commit (`docs(handoff): …`) this step creates. Working tree was **clean** before the handoff.

## What shipped (design artifacts only)

| File | Commit(s) | What |
|---|---|---|
| `docs/superpowers/specs/2026-06-16-ms02-client-merged-workitems-design.md` | 8ca99d4, e2b82d0, 4e322b8 | The approved design (256 lines). |
| `docs/superpowers/plans/2026-06-16-ms02-client-merged-workitems.md` | 6a7342b, e2b82d0, 4e322b8 | Phased TDD plan, ~22 tasks / **6 phases**. |
| `sql/NexoraDB/Tables/dbo.ReportSchedules.sql` | e2b82d0 (accidental) | 2-line INT-sync drift swept in by `-am` — see Gotchas. |

**The design in one breath:** new `nx_lib/clients.py` (client registry → engine + Octo creds) + `nx_lib/workitem_sources.py` (`SqlServerSource` = existing query lifted verbatim, `PostgresSource` = dialect twin, `WorkitemFilter`, `merge_sorted_rows`, `fetch_merged_page`, routing). Key decisions:
- **Merged list** across both DBs; per-source fetch + Python merge by `ModifiedAt`; single-source path stays byte-identical.
- **Routing = probe-then-cache** (NexoraDB `dbo.WorkitemSourceCache`, migration **0023**) because **IDs are disjoint/globally-unique** (owner-confirmed). **Collision fail-safe** built in (authoritative cache → ambiguity-detecting probe → log-and-default on >1 claimant; escalation = compound identity / UI `?client=`, documented but NOT built).
- **Per-client Octo creds** — fix `get_access_token` (today it signs every domain with the global `OCTO_*`).
- **Doc-field search per-source:** default → `SearchConfig`→StatisticsDB; MS02 → in-query `EXISTS` against its own **`t_documentindexes`** (`Name`/`Stringvalue`, join `workitemid`). Field VALUES stay on the Octo API for everyone.
- **Dashboard stats (Phase 6):** MS02 processing events come from **`public.batchtracking`** in a **separate** Postgres DB **`Praesidialdepartement_BS`** → needs a **second engine** `engine_ms02_stats_pg` (`MS02_STATS_DB_*` env). Cols `datuminexport` (processed) / `datumimportiert` (imported). **No per-process split** — aggregate once, dedupe the ms02 config group to one query. Gated via `Statconfig.ClientCode` (migration **0024**).

## Next steps (ordered)

1. **`/reset-session`** (the `var/handoff-pending` flag points here), then **`/execute-plan`** against `docs/superpowers/plans/2026-06-16-ms02-client-merged-workitems.md`.
2. **Phase 1 is the resume point** — Task 1 (add `psycopg2-binary`), Task 2 (MS02 config), Task 3 (`engine_ms02_pg`), Task 4 (migration 0023). All buildable now; no live MS02 needed.
3. **Build-time confirmations against INT** (the plan's self-review lists them): exact `MS02_` env key spelling (the creds are in `env/INT.env`, **`.claudeignore`-blocked from AI** — names were mirrored from `OCTO_*`/`DB_*`); MS02 Postgres identifier **casing** (the PG SQL quotes `"ID"`/`"Name"`/`"ModifiedAt"`/… — adjust at Task 9); whether the UI doc-field id matches `t_documentindexes."Name"`.
4. **Phase 6 owner inputs** (only blocker for the dashboard-stats phase): the `MS02_STATS_DB_*` creds for `Praesidialdepartement_BS` (likely the MS02 host/login with `dbname=Praesidialdepartement_BS`), and the list of MS02 `ProcessName`s to seed into `Statconfig`.
5. **Stop at commit** (remote) — do **not** push or open a PR; the owner pushes.

## Gotchas & notes (READ)

- **`e2b82d0` accidentally bundled `sql/NexoraDB/Tables/dbo.ReportSchedules.sql`** (2-line INT-sync drift, likely migration `0022` never re-dumped) — I used `git commit -am`. Content is **correct** (matches INT, which `sync-from-db.py --check` wants) and **unpushed**, so harmless. Owner declined/never asked to split; leave it or split into `chore(sql): re-dump ReportSchedules from INT` (would rewrite the unpushed `e2b82d0` — needs explicit OK).
- **Commits need `SQL_SYNC_SKIP=1`** prefix (INT `SchemaMigrations` CRLF drift blocks the `sql-migrate-int` hook on Windows). **gitlint** rejects subjects > 72 chars — bit me twice this session.
- **`.claudeignore` blocks AI reads of `env/*.env`** — the real `MS02_*` key spelling is unverified; the design parameterizes it in exactly one place (`nx_lib/config.py`). Confirm before/at Task 2.
- **Dual-session hazard carried from the prior handoff** (a 2nd Claude session, PID 20560, was sharing this checkout and thrashing the branch). **This session's 4 commits landed cleanly** and the tree is stable (24 ahead, my commits contiguous on top), so it seems parked — but per `project_autopilot_fixer_stashes_untracked` a background `git stash -u` can still sweep **untracked** files. Everything here is committed for that reason. If a file vanishes: `git stash list` → `git checkout "stash@{N}^3" -- <path>`.
- **Caveman-speak preference** (`feedback_caveman_speak`): chat prose is caveman in this repo; code/commits/docs stay normal. (This handoff is a doc → normal.)

## Untracked / left for owner

- **Nothing untracked** — working tree clean.
- **`dbo.ReportSchedules.sql`** already committed inside `e2b82d0` (see Gotchas) — split-or-leave is the owner's call.
- **Phase 6 inputs** (stats DB creds + MS02 `ProcessName` seed list) — owner-provided when Phase 6 is reached.
- `var/handoff-pending` points at this file (gitignored — not committed).
- **Prior owner debt still open** (unrelated): PR `feature/2.5.63` → `main`; PROD reporting RO logins + migrations + scheduled-reports task — see `project_branch_consolidation_2_5_63`.

## How to verify

```powershell
# Design artifacts present:
Test-Path docs/superpowers/specs/2026-06-16-ms02-client-merged-workitems-design.md   # True
Test-Path docs/superpowers/plans/2026-06-16-ms02-client-merged-workitems.md          # True

# This session's 4 commits:
git log --oneline 8ca99d4~1..4e322b8                                                  # the 4 docs(workitems) commits

# NOTHING is built yet (canary files absent):
Test-Path nx_lib/workitem_sources.py                                                 # expect: False
Test-Path nx_lib/clients.py                                                           # expect: False
Select-String -Path nx_lib/db.py -Pattern 'engine_ms02_pg' -Quiet                    # expect: False (no match)

# The accidental drift file is in e2b82d0 (not lost, not a problem):
git show --stat e2b82d0 | Select-String ReportSchedules                              # 1 hit
```

## Resuming in a fresh session

`/reset-session` (the flag in `var/handoff-pending` points here). **Tie-break:** two handoffs share **2026-06-16** — this one and `2026-06-16-plan-merge-and-dual-session-contention.md` (which now has a forward-pointer banner to here). If `/reset-session` picks the wrong file, run:

`/reset-session docs/superpowers/handoffs/2026-06-16-ms02-multisource-workitems-spec-and-plan.md`

**First thing next session:** read `project_ms02_multisource_workitems` in auto-memory (full decision record), then `/execute-plan` against the plan starting at Phase 1. Confirm the branch is stable (`git status`, `git log -3`) before any merge/reset — the dual-session hazard may recur.
