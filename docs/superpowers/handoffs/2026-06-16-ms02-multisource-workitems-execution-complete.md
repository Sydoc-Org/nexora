# Handoff — MS02 multi-source workitems: EXECUTION COMPLETE

**Date:** 2026-06-16 (afternoon) · **Branch:** `feature/2.5.63` · **50 commits ahead of origin** · **commit-only (remote — owner pushes)**
**Prior handoff:** `docs/superpowers/handoffs/2026-06-16-ms02-multisource-workitems-spec-and-plan.md` (the design-only session that produced the spec + plan this one executed).
**Durable context in auto-memory:** `project_ms02_multisource_workitems` (now marked EXECUTION COMPLETE — read it first), plus `feedback_caveman_speak`, `reference_sql_migrations`.

## TL;DR

- **`/execute-plan` ran the full MS02 plan to completion** — all ~22 tasks across 6 phases, built test-first via subagent-driven development with per-task + final adversarial review. **25 commits** this session (`472a353..3567d03`), all on `feature/2.5.63`, **unpushed**.
- A second client **MS02** (Azure Postgres runtime + 2nd Octo domain) is now merged into the shared **workitems list, detail, CSV export, and dashboard** (activity feed + C+A backlog + processed-over-time + processed/imported KPIs). New `nx_lib/workitem_sources.py` + `nx_lib/clients.py`; engines `engine_ms02_pg` + `engine_ms02_stats_pg`; migrations **0023** + **0024** applied to INT.
- **Tests green:** 783 unit + 53 integration + 6 e2e + `test_translations`. The PG paths and the merged list were **validated live against the real MS02 DBs** on INT.
- **No worktree was used** (executed in the main checkout) — plain handoff, nothing to merge.
- **Owner still owes:** push + PR→main; PROD `psycopg2-binary` + migrations; **seed `Statconfig` ms02 rows** to activate MS02 dashboard stats; optional TLS `verify-full`.

## This session's commits (oldest → newest)

```
472a353 build(deps): add psycopg2-binary for the MS02 Postgres runtime DB
69848b7 build(deps): sync uv.lock for psycopg2-binary
b8fa371 feat(config): read MS02 Postgres + Octo credentials from env
ea83190 feat(db): add MS02 Postgres engine with graceful degrade + health pings
432aeb1 feat(db): add WorkitemSourceCache routing table (migration 0023)
a021cf9 fix(db): make MS02 Postgres TLS mode configurable (verify-full path)   ← security-review hardening
71cc3c6 feat(clients): client registry mapping tenants to engine + Octo creds
ddb7507 fix(octo): sign access-token requests with per-client credentials
220a1a9 feat(workitems): SqlServerSource + merge primitive for multi-source list
08db6d6 feat(workitems): NexoraDB filter-id resolution + row enrichment helpers
12cbf32 feat(workitems): PostgresSource dialect twin for MS02 runtime DB
7acc286 feat(workitems): real per-client routing (probe-then-cache)
cc5a87d feat(workitems): merge orchestrator with per-source resilience
0b56467 refactor(workitems): drive list through multi-source orchestrator
a354e43 feat(workitems): source-agnostic single-workitem tag fetch
9d18efe feat(dashboard): multi-source backlog + activity feed
446d448 feat(workitems): banner when a workitem source is degraded
135e724 test(e2e): merged workitems list smoke
a1f8f77 docs(workitems): document MS02 multi-source client + psycopg2 prod step
065a0c4 chore(i18n): translate degraded-source banner strings (de/fr/it)
bec2306 feat(db): add MS02 stats engine for the Praesidialdepartement_BS DB
2bd5f37 feat(db): add Statconfig.ClientCode for multi-source dashboard stats   ← migration 0024
c5f39c5 feat(dashboard): include MS02 stats in processed-over-time + KPIs
03c1c56 docs(dashboard): document MS02 multi-source dashboard statistics
3567d03 refactor(workitems): type-safe merge tiebreak + document count invariant   ← final-review hardening
```
Working tree was **clean** before this handoff. Plus the handoff commit this step creates.

## What shipped

| Area | Files | Notes |
|---|---|---|
| Deps | `pyproject.toml`, `requirements.txt`, `uv.lock` | `psycopg2-binary==2.9.12` |
| Config | `nx_lib/config.py` | `MS02_*` (runtime + Octo + TLS knobs) + `MS02_STATS_DB_*` |
| Engines | `nx_lib/db.py` | `get_pg_url(...)`, `engine_ms02_pg`, `engine_ms02_stats_pg` (graceful-degrade); admin + `nx --doctor` pings |
| Registry | `nx_lib/clients.py` | `ClientConfig` (+`stats_engine`/`stats_dialect`), `CLIENTS`, `octo_creds_for_domain`, `non_default_clients` |
| Source layer | `nx_lib/workitem_sources.py` (new) | `WorkitemFilter`, `merge_sorted_rows`, `SqlServerSource`, `PostgresSource`, NexoraDB enrich, probe-then-cache routing, `fetch_merged_page`, `single_workitem_tags`, `recent_activity_rows`, `total_backlog_count` |
| Octo | `nx_lib/octo.py` | `get_access_token` signs per-client (per-domain cache key); stub `get_domain_for_workitem` removed |
| Views | `nx_lib/views/workitems.py`, `nx_lib/views/dashboard.py`, `nx_lib/process_helpers.py` | list/detail/dashboard rewired to the orchestrator; `prepare_process_selection_lists` added |
| UI | `templates/js/_workitems_overview_js.html` | degraded-source banner (`degradedSources`) |
| Migrations | `sql/_migrations/NexoraDB/0023_*.sql`, `0024_*.sql` (+ per-object dumps) | **applied to INT**: `dbo.WorkitemSourceCache`, `dbo.Statconfig.ClientCode` |
| Tests | `tests/unit/test_*`, `tests/integration/*`, `tests/e2e/test_workitems.py` | ~30 new tests across the feature |
| i18n | `messages.pot`, `translations/{de,fr,it}/…` | banner strings translated (no fuzzy) |
| Docs | `CHANGELOG.md`, `CLAUDE.md`, `env/*.env.example`, `docs/howto/iis.md` | feature + `MS02_*`/`MS02_STATS_DB_*` keys + psycopg2 prod step |

## Next steps (ordered)

1. **Review the diff locally**, then **push** `feature/2.5.63` and **open the PR → `main`** (owner does this; remote session stops at commit). Note the pre-push gate runs the full suite incl. e2e — run `python scripts/test_db_reset.py` first if the e2e state is stale.
2. **PROD deploy:** the deploy workflow auto-applies migrations **0023 + 0024**. Separately install the Postgres driver on the prod interpreter: `D:\sydoc\tools\py\python.exe -m pip install psycopg2-binary` (binary wheel, not mirrored by robocopy). See `docs/howto/iis.md`.
3. **Activate MS02 dashboard stats:** seed `dbo.Statconfig` with one `ClientCode='ms02'` row per MS02 ProcessName to expose (template is in migration `0024`, commented). Until seeded, MS02 stats are dormant by design (list/detail already work without it).
4. **Optional TLS hardening:** set `MS02_DB_SSLMODE=verify-full` + provision the Azure root-CA bundle and point `MS02_DB_SSLROOTCERT` at it (dev + prod) to close the documented MITM gap. Default stays `sslmode=require` (non-breaking).
5. **Full live MS02 validation** (needs a user with MS02 process perms): confirm MS02 rows merge into `/workitems`, an MS02 workitem's detail renders its document, and the dashboard shows MS02 once seeded. Screenshot to `var/screenshots/`.

## Gotchas & notes (READ)

- **The plan's env-key names were WRONG; corrected during execution.** Real keys in `env/INT.env`: `MS02_DB_SERVER_PRD`, `MS02_DB_OCTO_RUNTIME`, `MS02_DB_UID`, `MS02_DB_PWD`, `MS02_OCTO_DOMAIN`, `MS02_CLIENT_ID`, `MS02_CLIENT_SECRET`, `MS02_GRANT_TYPE` (no `MS02_DB_PORT`). `config.py` maps these to internal attrs — the single read point.
- **MS02 Postgres identifiers are case-preserved PascalCase** (verified live) and MUST be double-quoted: `"t_WorkItems"`, `"t_Processes"`, `"t_ActivityInstances"`, `"t_DocumentIndexes"`, `"t_ActivityTypes"`; doc-field cols `"WorkItemID"`/`"Name"`/`"StringValue"`. The plan guessed unquoted lowercase — that would have failed; the committed code is correct.
- **INT CRLF drift appears RESOLVED** — `db-migrate --env INT` and normal commits ran **clean** this session (SQL hooks PASSED). `SQL_SYNC_SKIP=1` was used defensively but is no longer required. This supersedes the warning in `project_int_migration_crlf_drift` — re-verify before relying on it.
- **Behavior change (deliberate):** a total OctoDB outage on `/api/workitems` now returns **200 + empty list + `degradedSources:["default"]`** (banner) instead of a 500. Graceful-degrade for the multi-source design — confirm no monitoring depended on the old 500.
- **Dead code (minor):** `prepare_process_selection_sql` in `nx_lib/process_helpers.py` now has no production callers (only its own tests). Harmless; delete or rewire later.
- **MS02 stats engine reuses MS02 creds** (`MS02_STATS_DB_*` default to the MS02 host/login + `dbname=Praesidialdepartement_BS`) — verified reachable; `public.batchtracking` cols `datuminexport`/`datumimportiert`/`workitemid` (lowercase).

## Untracked / left for owner

- **Nothing untracked** — working tree clean (screenshots live under gitignored `var/screenshots/`).
- `var/handoff-pending` points at this file (gitignored — not committed).
- Owner actions in "Next steps" (push/PR, PROD driver+migrations, Statconfig seed, TLS).

## How to verify

```powershell
# Feature present, app boots, suites green:
python -c "from nx_lib import create_app; create_app(); print('ok')"   # ENVIRONMENT=INT
python -m pytest tests/unit -q                                          # 783 passed, 24 skipped
python -m pytest tests/integration/test_workitems_routes.py tests/integration/test_dashboard_routes.py -q   # 53 passed
python -m pytest tests/e2e/test_workitems.py -q --reruns 2 --only-rerun flaky_e2e                            # 6 passed
python -m pytest tests/unit/test_translations.py -q                     # 7 passed

# Migrations applied to INT:
python scripts/db-migrate.py --env INT --dry-run                        # up-to-date (0023 + 0024 applied)

# This session's commits:
git log --oneline 537080e..HEAD                                         # 25 commits
```

## Resuming in a fresh session

`/reset-session` (the flag in `var/handoff-pending` points here). **Tie-break:** three handoffs share **2026-06-16**. The flag is authoritative; if `/reset-session` picks the wrong file, run:

`/reset-session docs/superpowers/handoffs/2026-06-16-ms02-multisource-workitems-execution-complete.md`

**First thing next session:** read `project_ms02_multisource_workitems` in auto-memory (post-execution record), confirm branch state (`git status`, `git log -3`), then work the owner "Next steps" — there is **no more building to do**; the remaining items are push/PR + PROD provisioning + the `Statconfig` seed.
