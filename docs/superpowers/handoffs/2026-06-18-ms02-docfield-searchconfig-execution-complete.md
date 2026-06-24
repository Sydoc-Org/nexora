# Handoff — MS02 doc-field search → SearchConfig mapping (EXECUTION COMPLETE, all 9 tasks)

**Date:** 2026-06-18 (midday) · **Branch:** `feature/2.5.63` · **69 commits ahead of origin** · **commit-only (remote — owner pushes)**
**Prior handoff:** `docs/superpowers/handoffs/2026-06-18-ms02-docfield-searchconfig-mapping-plan.md` (the design-only plan session this executes)
**Plan executed:** `docs/superpowers/plans/2026-06-18-ms02-docfield-searchconfig-mapping.md` (9 tasks / 7 phases — **all complete**)
**Durable context in auto-memory:** `project_ms02_multisource_workitems` (full MS02 decision record — read first), plus `project_int_migration_crlf_drift`, `reference_sql_migrations`, `feedback_caveman_speak`.

## TL;DR

- **`/execute-plan` ran to completion.** All 9 plan tasks built via subagent-driven development (fresh implementer + spec-compliance review + code-quality review per task; Tasks 5/6 and the final holistic pass reviewed on Opus). **13 commits**, working tree clean.
- **What it does:** MS02 doc-field (document-field) search no longer runs an in-query `EXISTS` against MS02's runtime `"t_DocumentIndexes"`. It now routes through `dbo.SearchConfig` (made client-aware via a new `ClientCode` column, migration `0027`), resolves the matched field VALUE against a **dedicated** MS02 Postgres doc-field DB (new `engine_ms02_docfields_pg`), pre-resolves to a workitem-id allow-set, and applies it as `twi."ID" = ANY(%s)`. **The default-client path is byte-identical** (only gains a defensive `AND ClientCode='default'`).
- **Bonus security fix:** code review surfaced a **pre-existing CRITICAL SQL injection** in `api_docfield_values` (`field` request arg interpolated into the SearchConfig query unguarded). Fixed with the project's existing `get_valid_search_columns()` whitelist (`1f378f6`).
- **⚠ One blocking owner follow-up:** migration `0027` could **not** be applied to INT (INT SQL Server was unreachable from this box the entire session — `08001 SQL Server existiert nicht`, flapping). Until `0027` lands on INT, the default block's `AND ClientCode='default'` raises *"Invalid column name 'ClientCode'"* (swallowed) → **default doc-field search silently returns ALL rows on INT**. PROD is safe (deploy applies migrations before mirroring code). **Apply `0027` to INT first thing when SQL is reachable.**
- **MS02 doc-field search stays a graceful no-op** (page still renders) until the owner provisions `MS02_DOCFIELDS_DB_NAME` and seeds the MS02 `SearchConfig` row — the plan's build-time Owner-actions.

## This session's commits (oldest → newest)

```
15773bb  feat(config): add MS02_DOCFIELDS_DB_* keys for doc-field index DB      (Task 1)
bebf27f  test(config): assert MS02_DOCFIELDS_DB_PWD defaults to runtime PWD      (Task 1, review fix)
cbc3712  feat(db): add engine_ms02_docfields_pg for the MS02 doc-field index DB (Task 2)
3248f25  test(ms02): pytest.skip the env-gated docfields config/engine tests     (Task 2, review fix)
82d0ec4  feat(clients): wire docfields_engine into the client registry + probes  (Task 3)
fd8d8f6  feat(db): make SearchConfig client-aware + MS02 docfield seed (0027)     (Task 4)
6129c7c  docs(db): clarify 0027 owner must uncomment the whole seed block         (Task 4, review fix)
07c7cb2  feat(workitems): MS02 EAV doc-field resolver; drop in-query EXISTS       (Task 5)
48c1bfb  test(workitems): cover MS02 resolver mid-loop empty + no-names skip      (Task 5, review fix)
b8faccb  feat(workitems): pre-resolve MS02 doc-field search in the orchestrator   (Task 6)
8bbf128  feat(workitems): MS02 doc-field autocomplete from the doc-field DB       (Task 7, optional)
1f378f6  fix(security): whitelist field arg in api_docfield_values (SQLi)         (Task 7, review fix — pre-existing vuln)
12f62fc  docs(ms02): document SearchConfig-driven doc-field search; supersede 4.6 (Task 8)
```
Plus the `docs(handoff): …` commit this step creates. **No worktree** — work landed directly on `feature/2.5.63`. Working tree clean before the handoff.

## What shipped (by phase)

| Phase / Task | Commits | Files |
|---|---|---|
| **1 — Config + engine + registry** | `15773bb`,`bebf27f`,`cbc3712`,`3248f25`,`82d0ec4` | `nx_lib/config.py` (`MS02_DOCFIELDS_DB_*`), `nx_lib/db.py` (`engine_ms02_docfields_pg`, graceful-degrade to `None`), `nx_lib/clients.py` (`docfields_engine`/`docfields_dialect`), `nx_lib/cli_doctor.py` + `nx_lib/views/admin.py` (health probes), 4× `env/*.env.example`, 3 new unit-test files |
| **2 — Migration** | `fd8d8f6`,`6129c7c` | `sql/_migrations/NexoraDB/0027_searchconfig_ms02_docfields.sql` — adds `dbo.SearchConfig.ClientCode NVARCHAR(50) NOT NULL DEFAULT 'default'` (idempotent), MS02 seed left fully commented |
| **3 — Resolver seam** | `07c7cb2`,`48c1bfb` | `nx_lib/workitem_sources.py` — `WorkitemFilter.ms02_docfield_ids`, `_MS02_DOCFIELD_*` constants, `build_ms02_docfield_sql`, `resolve_ms02_docfield_ids`; **deleted** the `t_DocumentIndexes` EXISTS from `PostgresSource._build_where` (→ `twi."ID" = ANY(%s)`) |
| **4 — Orchestrator** | `b8faccb` | `nx_lib/views/workitems.py` `_get_workitems_data` — MS02 sibling block (SearchConfig `ClientCode='ms02'` → docfields DB → `ms02_docfield_ids`); default loop byte-identical bar `AND ClientCode='default'` |
| **5 — Autocomplete (optional)** | `8bbf128`,`1f378f6` | `nx_lib/views/workitems.py` `api_docfield_values` — MS02 EAV suggestions branch + **SQLi whitelist fix** |
| **6 — Docs** | `12f62fc` | `CHANGELOG.md`, `CLAUDE.md`, spec `2026-06-16-ms02-client-merged-workitems-design.md` §4.6 + summary row superseded |

**Design in one breath:** `dbo.SearchConfig.ClientCode` routes each row — `'default'` rows are columnar (`col_<field>` = a StatisticsDB physical column, resolved on `engine_statistics_db` → `docfield_ids` → `SqlServerSource`); `'ms02'` rows are EAV (`col_<field>` = the doc-field `"Name"` VALUE, resolved on `engine_ms02_docfields_pg` → `ms02_docfield_ids` → `PostgresSource`). The two allow-sets are **separate `WorkitemFilter` fields**, so a mixed `prcfW=all` request never lets one source's match shrink the other's. Both degrade to "no constraint, page renders" when the engine/config is absent. No ETL.

## Next steps (ordered)

1. **Owner: review the 13 commits locally, then `git push`** `feature/2.5.63` (remote/commit-only rule — this session did not push). This work **stacks on** the still-unpushed MS02 multi-source build already on the branch; it must land after it. PR `feature/2.5.63` → `main` is also owner-owed (see `project_branch_consolidation_2_5_63`).
2. **⚠ Apply migration `0027` to INT the moment SQL Server is reachable:** `python scripts/db-migrate.py --env INT` (idempotent — `IF NOT EXISTS`). Then run `python sql/sync-from-db.py` (or just commit any SQL change to trigger the hook) so `sql/NexoraDB/Tables/dbo.SearchConfig.sql` regenerates with the `ClientCode` column — it is **currently NOT regenerated** (still pre-`0027`). Until `0027` is applied on INT, **default-client doc-field search on INT no-op-filters** (returns all rows). PROD applies automatically on deploy.
3. **Owner build-time confirmations (plan Owner-actions) to take MS02 doc-field search live:**
   - Set `MS02_DOCFIELDS_DB_NAME` (+ optionally the other `MS02_DOCFIELDS_DB_*`) in gitignored `env/INT.env` / `env/PROD.env`. Until set, `engine_ms02_docfields_pg` is `None` and MS02 doc-field search/autocomplete is a no-op.
   - Seed the MS02 `SearchConfig` row: uncomment the **entire** guarded `IF NOT EXISTS … INSERT … GO` block in `0027` (the comment now says so explicitly) and fill each `col_<field>` with the owner-confirmed EAV `"Name"` value. `ProcessName` must be the `'<client>.<process>'` key (`'sydoc.praesidialdepartement_bs'`, same as the `0025` Statconfig seed) — a wrong key silently returns all MS02 rows.
   - Confirm the `_MS02_DOCFIELD_*` table/column identifiers (`nx_lib/workitem_sources.py:356-359`) match the dedicated doc-field DB's actual casing (they default to `t_DocumentIndexes`/`WorkItemID`/`Name`/`StringValue`).
   - PROD: `psycopg2-binary` is already a prod obligation from the MS02 multi-source work; nothing new.

## Gotchas & notes (READ)

- **INT SQL Server was UNREACHABLE the entire session** (`pyodbc 08001 SQL Server existiert nicht`, flapping). Consequences: (a) `0027` not applied to INT (deferred — see step 2); (b) every commit that touched no SQL still tripped the `sql-migrate-int`/`sql-sync-check` hooks, so each was committed with the sanctioned `SQL_SYNC_SKIP=1` hatch (never `--no-verify`); (c) the full integration suite can't run (the login fixture queries live SQL).
- **`SQL_SYNC_SKIP=1` is required on every commit** while INT stays unreachable — the handoff commit too.
- **Unit suite: 792 passed, 24 skipped, 6 failed + 6 errors — ALL 12 are environmental** (identical `pyodbc 08001`, in `test_db.py` live-engine pings, `test_security.py`, `test_maintenance.py`, `test_users.py`). Re-ran the failing set in isolation to confirm: every one is the SQL-Server-down connection error, **none touch MS02 doc-field code**. All new MS02 unit tests pass.
- **Leftover-reference sweep clean:** no runtime `EXISTS … t_DocumentIndexes` anywhere in `nx_lib`; the only two remaining mentions are the `_MS02_DOCFIELD_TABLE = "t_DocumentIndexes"` config constant + its comment (intended).
- **Known Minor nits (not fixed — low value / out of scope):** (1) `WorkitemFilter.docfields`/`docvalues` are now effectively dead (the EXISTS that read them was deleted; autocomplete reads `request.args` directly) — the "kept for autocomplete" comment is slightly stale; candidate for a future cleanup. (2) The optional MS02 autocomplete is either/or for `process=all` (if any `ms02` row matches the field it returns MS02-only suggestions, skipping the default StatisticsDB list) — search itself merges both sources correctly; only the dropdown is either/or.
- **Task 7 was the plan's OPTIONAL phase.** Implemented because it's fully specified, low-risk (degrades to `[]` when the engine is `None`), and completes MS02 autocomplete parity. The owner can drop `8bbf128` if they prefer the bare degrade-to-`[]` — but **keep `1f378f6`** (the security fix is independent and important).
- **Caveman-speak preference** (`feedback_caveman_speak`): chat prose is caveman in this repo; code/commits/docs stay normal. This handoff is a doc → normal.

## Untracked / left for owner

- **Nothing untracked** — working tree clean; only the 13 listed commits (+ this handoff).
- **`var/handoff-pending`** points at this file (gitignored — not committed).
- **Deferred ops:** `0027` INT apply + `dbo.SearchConfig.sql` dump regen (step 2); MS02 env + seed (step 3).

## How to verify

```powershell
# All 13 session commits present:
git log --oneline ad99fcd..HEAD            # 13 commits, 15773bb..12f62fc

# The old runtime coupling is gone (only the constant remains):
Select-String -Path nx_lib/workitem_sources.py -Pattern 'EXISTS .*t_DocumentIndexes' -Quiet   # False
Select-String -Path nx_lib/workitem_sources.py -Pattern 'resolve_ms02_docfield_ids' -Quiet     # True

# New symbols exist:
Select-String -Path nx_lib/db.py -Pattern 'engine_ms02_docfields_pg' -Quiet   # True
Select-String -Path nx_lib/config.py -Pattern 'MS02_DOCFIELDS_DB_' -Quiet     # True

# MS02 doc-field unit tests (no live DB needed) — all green:
python -m pytest tests/unit/test_workitem_sources.py tests/unit/test_config_ms02_docfields.py tests/unit/test_db_ms02_docfields_engine.py tests/unit/test_clients_docfields.py -q

# Integration tests COLLECT (full run blocked while SQL Server is unreachable):
python -m pytest tests/integration/test_workitems_routes.py --co -q -k docfield
```

The full unit suite's 6 failures + 6 errors are **all** the SQL-Server-down `pyodbc 08001` (live-DB tests: `test_db`, `test_security`, `test_maintenance`, `test_users`) — environmental, not regressions. Re-run once INT/SQL is reachable to confirm green.

## Resuming in a fresh session

`/reset-session` (the `var/handoff-pending` flag points here). **Same-date collision:** the plan-session handoff `docs/superpowers/handoffs/2026-06-18-ms02-docfield-searchconfig-mapping-plan.md` shares today's date and now carries a forward-pointer banner to this file. If auto-pick grabs the wrong one, target this one explicitly:

`/reset-session docs/superpowers/handoffs/2026-06-18-ms02-docfield-searchconfig-execution-complete.md`

**First thing next session:** the implementation is done and reviewed. The real work is the **owner follow-ups** above — push, apply `0027` to INT, then provision the MS02 doc-field DB name + seed the `SearchConfig` row to take it live. Read `project_ms02_multisource_workitems` in auto-memory for the full MS02 decision record.
