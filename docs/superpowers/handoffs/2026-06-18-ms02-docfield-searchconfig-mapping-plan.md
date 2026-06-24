> **➡ SUPERSEDED by a same-date handoff:** the plan in this file has since been **executed in full** (all 9 tasks). For the current state, resume from
> `docs/superpowers/handoffs/2026-06-18-ms02-docfield-searchconfig-execution-complete.md`.

# Handoff — MS02 doc-field search → SearchConfig mapping (plan written, design-only)

**Date:** 2026-06-18 (morning) · **Branch:** `feature/2.5.63` · **55 commits ahead of origin** · **commit-only (remote)**
**Prior handoff:** `docs/superpowers/handoffs/2026-06-16-ms02-multisource-workitems-execution-complete.md` (the MS02 multi-source build this plan amends)
**Durable context in auto-memory:** `project_ms02_multisource_workitems` (the full MS02 decision record — read first), plus `project_int_migration_crlf_drift`, `reference_sql_migrations`, `feedback_caveman_speak`.

## TL;DR

- **Design-only session.** Multi-agent planning run (`/write-plan`) → one phased TDD plan, committed. **No code was written.**
- **What it fixes:** the owner reversed an earlier MS02 decision. MS02 doc-field (document-field) search currently runs an in-query `EXISTS` straight against MS02's own runtime Postgres table `"t_DocumentIndexes"` (the "stupid, won't scale" coupling). The plan moves it onto nexora's **normal mapping layer** — `dbo.SearchConfig`, made client-aware — with the matched VALUE resolved against a **dedicated MS02 Postgres doc-field DB** and pre-resolved to a workitem-id allow-set.
- **Three owner decisions are locked into the plan** (collected via `AskUserQuestion` at the start): (1) reuse `dbo.SearchConfig` (not a new table); (2) value resolved in an MS02 Postgres DB, **no ETL**; (3) that DB is the **same Azure host/login as the MS02 runtime, different dbname** → one new `engine_ms02_docfields_pg`.
- **Ready for `/execute-plan`** against `docs/superpowers/plans/2026-06-18-ms02-docfield-searchconfig-mapping.md`. Phases 1–4 build with **no live MS02 access**; doc-field search only goes *live* once the owner provides the build-time DB/table/column names (Owner-actions in the plan).
- **Fable was unavailable** this session (infra outage) — the 7 planning agents ran on **Opus** instead (a peer model, not a cost-downgrade).

## This session's commits (oldest → newest)

```
50ee1fd  docs(plans): add MS02 doc-field SearchConfig mapping plan
```
Plus the handoff commit (`docs(handoff): …`) this step creates. Working tree was **clean** before the handoff.

## What shipped (one design artifact)

| File | Commit | What |
|---|---|---|
| `docs/superpowers/plans/2026-06-18-ms02-docfield-searchconfig-mapping.md` | 50ee1fd | Phased TDD plan, **9 tasks / 7 phases**, 1380 lines. All file/symbol anchors verified against the live repo. |

**The design in one breath:** `dbo.SearchConfig` gains a `ClientCode` column (default `'default'`, **migration `0027`**, mirroring `Statconfig.ClientCode` from `0024`). The orchestrator `_get_workitems_data` leaves the existing default `SearchConfig→StatisticsDB→docfield_ids` block **byte-identical** and adds a **sibling** MS02 block that reads each `col_<field>` as an EAV `"Name"` value and calls a new pure seam `resolve_ms02_docfield_ids(engine, pairs)` in `nx_lib/workitem_sources.py`. That seam queries the new `engine_ms02_docfields_pg` and returns a **separate** `ms02_docfield_ids` allow-set (three-way contract: `None`=no constraint, `set()`=zero rows, populated=`ANY(%s)`). `PostgresSource._build_where` **deletes** the `"t_DocumentIndexes"` `EXISTS` loop and consumes that set as `twi."ID" = ANY(%s)`.

Key points baked in:
- **Cross-DB constraint:** the doc-field DB is a *separate* Postgres database (a PG connection binds to one DB), so it **cannot be joined** to the runtime DB — hence the pre-resolve-to-ID-set design, mirroring the default source's existing `docfield_ids` pattern. MS02 workitem IDs are globally unique.
- **EAV-vs-columnar crux:** for `'default'` rows `col_<field>` is a StatisticsDB physical *column*; for `'ms02'` rows it's the doc-field `"Name"` *value* to match. `ClientCode` is the switch; the default block now also filters `ClientCode='default'` so a future MS02 row can never bleed into the columnar path.
- **New engine** `engine_ms02_docfields_pg` (+ `MS02_DOCFIELDS_DB_*` env) clones the `engine_ms02_stats_pg` graceful-degrade: stays `None` until `MS02_DOCFIELDS_DB_NAME` is set. HOST/USER/PWD/PORT/TLS default to the `MS02_DB_*` runtime values; only the dbname differs and has no default.
- Plan **supersedes spec §4.6** of `2026-06-16-ms02-client-merged-workitems-design.md` (Task 8 rewrites §4.6 + its summary-table row); touches CHANGELOG + CLAUDE.md "Databases". **Default single-source path stays byte-identical.** No new perm, no i18n, no template change, no `deploy.yml` change.

## Next steps (ordered)

1. **`/reset-session`** (the `var/handoff-pending` flag points here), then **`/execute-plan`** against `docs/superpowers/plans/2026-06-18-ms02-docfield-searchconfig-mapping.md`.
2. **Phase 1 is the resume point** — Task 1 (`MS02_DOCFIELDS_DB_*` config keys), Task 2 (`engine_ms02_docfields_pg`), Task 3 (wire into `clients.py` + `cli_doctor.py` + `admin.py`). All buildable now; engine is `None` in dev/CI (graceful-degrade) so no live MS02 needed.
3. **Phases 2–4** — migration `0027` (SearchConfig `ClientCode`), the pure resolver seam (Task 5, deletes the `t_DocumentIndexes` EXISTS), orchestrator sibling block (Task 6). Phase 5 (MS02 autocomplete) is **optional**. Phase 6 = docs/spec/CHANGELOG. Phase 7 = full-suite + leftover-reference sweep.
4. **Owner build-time confirmations** (the plan's "Owner actions" section, 9 items) — doc-field DB **name**, **table** name, **column** names/casing (likely `"WorkItemID"`/`"Name"`/`"StringValue"`), the MS02 `SearchConfig.ProcessName` key (must be `'sydoc.praesidialdepartement_bs'`, the `'<client>.<process>'` form), and the `col_<field>→"Name"` seed mappings (the migration's INSERT is left commented pending these). Until provided, MS02 doc-field search degrades to no-constraint (page still renders).
5. **Stop at commit** (remote) — do **not** push or open a PR; the owner pushes.

## Gotchas & notes (READ)

- **`SQL_SYNC_SKIP=1` is REQUIRED on commits this session** — INT SQL Server (`INTSQL01`) is **unreachable from this remote box** (`SQL Server existiert nicht` / host unknown), so the `sql-migrate-int` + `sql-sync-check` hooks fail on connect. This is the sanctioned hatch (CLAUDE.md "Git") — `SQL_SYNC_SKIP=1 git commit …`, **never** `--no-verify`. The plan commit `50ee1fd` used it. **Consequence for `/execute-plan`:** migration `0027` **cannot be applied to INT from here** — the `db-migrate.py --env INT` step in Task 4 will fail on connect; either run it from a box with INT access or apply `0027` to INT later. Builder must `SQL_SYNC_SKIP=1` every commit while INT stays unreachable.
- **`end-of-file-fixer` hook** rewrote the plan file's trailing newline on the first commit attempt → re-`git add` and recommit (done). Expect the same for any new file; just re-stage.
- **`0027` may not stay free.** The migrations dir tops out at `0026_ms02_praesidialdepartement_workitems_process.sql` *as of this session*. The MS02 work is unpushed/active — re-list `sql/_migrations/NexoraDB/` at execution and bump if `0027` got taken (Task 4 Step 0 says so).
- **Fable outage.** `/write-plan` mandates Fable agents; Fable 5 returned "currently unavailable" for all 7 agents (0 tokens). I swapped to Opus (peer model) and re-ran — clean. If re-running planning workflows, check Fable availability first.
- **`prepare_process_selection_sql` dead-code note** (from the prior MS02 handoff) still stands — unrelated to this plan; the orchestrator uses `prepare_process_selection_lists` + the un-flattened `target_processes` (the resolver keys on the latter — see the plan's #1 gotcha).
- **Caveman-speak preference** (`feedback_caveman_speak`): chat prose is caveman in this repo; code/commits/docs stay normal. (This handoff is a doc → normal.)
- **Background-agent file-sweep hazard** (`project_autopilot_fixer_stashes_untracked`): a stray `git stash -u` can sweep untracked files. Everything here is committed. If a file vanishes: `git stash list` → `git checkout "stash@{N}^3" -- <path>`.

## Untracked / left for owner

- **Nothing untracked** — working tree clean (only `50ee1fd` this session).
- **Owner build-time inputs** (doc-field DB name/table/columns + SearchConfig seed) — see the plan's Owner-actions; supplied when execution reaches the live-enable point.
- `var/handoff-pending` points at this file (gitignored — not committed).
- **Prior owner debt still open** (unrelated): the whole MS02 multi-source build is **unpushed** on `feature/2.5.63`; PR `feature/2.5.63` → `main`; PROD `psycopg2` + migrations `0023`–`0027` + seed `Statconfig`/`SearchConfig` ms02 rows — see `project_ms02_multisource_workitems` and `project_branch_consolidation_2_5_63`. This plan **stacks on** that unpushed work and must land after it.

## How to verify

```powershell
# Plan artifact present:
Test-Path docs/superpowers/plans/2026-06-18-ms02-docfield-searchconfig-mapping.md   # True

# This session's commit:
git log --oneline -1 50ee1fd                                                         # docs(plans): add MS02 doc-field SearchConfig mapping plan

# NOTHING is built yet (canary symbols absent):
Select-String -Path nx_lib/db.py -Pattern 'engine_ms02_docfields_pg' -Quiet          # expect: False
Select-String -Path nx_lib/config.py -Pattern 'MS02_DOCFIELDS_DB_' -Quiet            # expect: False
Select-String -Path nx_lib/workitem_sources.py -Pattern 'resolve_ms02_docfield_ids' -Quiet  # expect: False

# The OLD coupling the plan deletes still exists (canary that it's not yet executed):
Select-String -Path nx_lib/workitem_sources.py -Pattern 't_DocumentIndexes' -Quiet   # expect: True (the EXISTS still there)
```

## Resuming in a fresh session

`/reset-session` (the flag in `var/handoff-pending` points here). No same-date handoff collision (latest prior is 2026-06-16), so the auto-pick is unambiguous; if needed, target it explicitly:

`/reset-session docs/superpowers/handoffs/2026-06-18-ms02-docfield-searchconfig-mapping-plan.md`

**First thing next session:** read `project_ms02_multisource_workitems` in auto-memory (full MS02 decision record), then `/execute-plan` against `docs/superpowers/plans/2026-06-18-ms02-docfield-searchconfig-mapping.md` starting at **Phase 1, Task 1**. Remember: **INT is unreachable from this box** → `SQL_SYNC_SKIP=1` on every commit and the `0027` apply-to-INT step must run elsewhere.
