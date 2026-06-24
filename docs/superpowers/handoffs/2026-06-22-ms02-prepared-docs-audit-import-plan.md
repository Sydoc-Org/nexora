> **➡️ SUPERSEDED — the plan below was EXECUTED.** The feature is built (all 11 tasks, final review READY TO MERGE). For the current state see
> `docs/superpowers/handoffs/2026-06-22-ms02-prepared-docs-audit-import-execution-complete.md`.

# Handoff — MS02 prepared-documents Excel import + audit display (plan written, design-only)

**Date:** 2026-06-22 (morning) · **Branch:** `feature/2.5.63` · **74 commits ahead of origin** · **commit-only (remote)**
**Prior handoff:** `docs/superpowers/handoffs/2026-06-18-ms02-docfield-searchconfig-execution-complete.md` (the MS02 doc-field SearchConfig build this feature stacks on)
**Durable context in auto-memory:** `project_ms02_multisource_workitems` (full MS02 decision record — read first), plus `reference_ms02_media_host_dns`, `project_int_migration_crlf_drift`, `reference_sql_migrations`, `feedback_caveman_speak`.

## TL;DR

- **Design-only session.** Multi-agent planning run (`/write-plan`) → one phased TDD plan, committed. **No feature code was written.**
- **What it builds:** an **MS02-only** Excel-upload control on the workitems list. The sheet has two columns — `PID` (a **personal number**, NOT a process id, NOT a workitem id) and `Prepared` (informational only). Each PID resolves **through the existing MS02 doc-field EAV index** (`engine_ms02_docfields_pg`) to its workitem(s); the matched workitems show in the list so the user opens each and reads **the full Octo audit** (which is already rendered today). **Display-only — no reconcile** of the `Prepared` flag against the audit.
- **Four owner decisions locked into the plan** (collected via `AskUserQuestion` up front, + the user's mid-flight "PID = personal number not process id"): (1) **MS02 client only**; (2) the PID **is an extracted/indexed doc-field** → resolve via the EAV index; (3) deliverable = **extend the workitems list**, MS02-only, behind a **new permission**; (4) **display the audit only**, no verify logic.
- **Ready for `/execute-plan`** against `docs/superpowers/plans/2026-06-22-ms02-prepared-docs-audit-import.md` — **11 tasks / 9 phases**, 1395 lines. Resume point: **Phase 1, Task 1** (`parse_prepared_xlsx` pure helper). Phases 1–8 build with **no live MS02 access** (engines `None` in dev/CI → graceful-degrade); the import only goes *live* once the owner seeds the `col_pid` EAV `"Name"` + sets `MS02_DOCFIELDS_DB_NAME` (Owner actions in the plan).
- **Fable was unavailable** this session (infra outage — all 7 agents returned "Claude Fable 5 is currently unavailable"). The planning agents re-ran on **Opus 4.8** (a peer model, not a cost-downgrade). Commit trailer is therefore Opus, not Fable.
- **Every file/symbol/snippet anchor in the plan was verified verbatim against the live repo — zero fabrications found.** (See "How to verify".)

## This session's commits (oldest → newest)

```
a1b25a9  docs(plans): add MS02 prepared-docs audit-import plan
```
Plus the handoff commit (`docs(handoff): …`) this step creates. Working tree was **clean** before the handoff.

## What shipped (one design artifact)

| File | Commit | What |
|---|---|---|
| `docs/superpowers/plans/2026-06-22-ms02-prepared-docs-audit-import.md` | a1b25a9 | Phased TDD plan, **11 tasks / 9 phases**, 1395 lines. Every file/symbol/snippet anchor verified against the live repo. |

**The design in one breath:** this **stacks directly on the just-shipped MS02 doc-field machinery** (already present on this branch: `resolve_ms02_docfield_ids`, `build_ms02_docfield_sql`, the `_MS02_DOCFIELD_*` constants, `engine_ms02_docfields_pg`, `WorkitemFilter.ms02_docfield_ids` → `PostgresSource._build_where` → `twi."ID" = ANY(%s)`). It adds: (1) a pure `parse_prepared_xlsx(data)` (openpyxl, already a dep; row-capped at 10000); (2) a **sibling** resolver `resolve_ms02_pid_ids(engine, eav_names, pid_values)` doing `"Name" IN (...) AND "StringValue" = ANY(%s)` — **the inverse shape** of the search resolver (one field, MANY exact PIDs, OR-ed — do NOT overload the AND/LIKE search resolver); (3) an MS02-gated POST route `/import_prepared_audit` (`@require_permission("workitems.import.preparedaudit")`, libmagic MIME sniff + workbook parse, never writes the xlsx to disk) that resolves PIDs → MS02 workitem ids, stashes the id-set in the **server session under a short token**, and returns `{token, prepared, matched, total}`; (4) `_get_workitems_data` reads `?pidImport=<token>` back out of the session and intersects it into `ms02_docfield_ids`, plus a new `WorkitemFilter.pid_import_active` that short-circuits `SqlServerSource.list_workitems` to `([], 0)` (MS02-only results); (5) an MS02-only upload control + banner in `workitems_overview.html` / `_workitems_overview_js.html`, wired by modifying the existing `fetchAndUpdateWorkitems` (append `pidImport` to the FETCH url only, keep the `pushState` url clean).

Key points baked in:
- **Audit display = REUSE, not new UI.** The audit is already fetched AND rendered today: JS `loadHistory(workitemId)` → `/api/get_audithistory/<id>` (gated `workitems.details.view.audit`, client-routed via `get_domain_for_workitem` to the MS02 Octo domain). The feature does **zero** audit-rendering work — it only surfaces the matched workitems. (Don't conflate with `octo.py`'s `&WithDocumentAudits=true`, which is the per-extension source-highlight audit — a different surface.)
- **Session token, not a URL id-list.** One PID → many workitems, so a raw `?pidWorkitemId=…` list would be huge. The id-set rides in `session["pid_import:<token>"]`; an unknown/expired token → empty set (zero MS02 rows) but still forces MS02-only — never silently drops the filter.
- **No hardcoded process key.** Migration `0028` renamed the MS02 process to `05_PDBS` (live key `sydoc.05_PDBS`, perm `workitems.filter.process.sydoc.05_PDBS`). The route reads the EAV `"Name"` from the `'ms02'` `SearchConfig` `col_pid` row **dynamically** from the user's `target_processes` (`ProcessName IN (...)`), exactly like the orchestrator — a future rename Just Works. Do **not** copy the stale `praesidialdepartement_bs` text from `0025`/`0026`/`0027`.
- **New permission `workitems.import.preparedaudit`** (migration `0029`, schema-exact clone of `0018`'s pattern: idempotent `INSERT` into `dbo.Permission`, then Effect `'A'` to every profile with `admin.view`). Per-control perm → **intentionally NOT in `page_visibility()`**, mirroring `workitems.import.workitem`.
- **Default single-source path stays byte-identical.** The PID set funnels only into `ms02_docfield_ids` (PostgresSource). Touches CHANGELOG + CLAUDE.md + a one-line spec §4.6 note. i18n: **yes** (new strings → pybabel de/fr/it). `deploy.yml`: **no change** (all files in already-mirrored dirs).

## Next steps (ordered)

1. **`/reset-session`** (the `var/handoff-pending` flag points here), then **`/execute-plan`** against `docs/superpowers/plans/2026-06-22-ms02-prepared-docs-audit-import.md`.
2. **Phase 1, Task 1 is the resume point** — `parse_prepared_xlsx` pure helper (TDD, in-memory openpyxl workbooks, no engine). Then Phase 2 (`resolve_ms02_pid_ids` sibling resolver), Phase 3 (`.xlsx` in the `nx_lib/files.py` MIME whitelist), Phase 4 (orchestrator `pidImport` thread + `SqlServerSource` suppression). All buildable now; MS02 engines are `None` in dev/CI (graceful-degrade) so no live MS02 needed.
3. **Phase 5** = migration `0029` (perm seed). **Phase 6** = the `/import_prepared_audit` route. **Phase 7** = template control + JS handler (restart `nx -u` after template edits; Jinja cache). **Phase 8** = i18n + docs + changelog. **Phase 9** = full-suite verification.
4. **Owner build-time confirmations** (the plan's "Owner actions", 7 items): the **personal-number EAV `"Name"`** seeded as the `'ms02'` `SearchConfig` `col_pid` value; `MS02_DOCFIELDS_DB_NAME` in `env/INT.env`+`env/PROD.env`; PID format alignment (Excel float coercion / zero-padding); the new perm granted to the MS02 operator profile(s); the prod libmagic `.xlsx` MIME value. Until the `col_pid` seed + dbname land, the import resolves nothing (route returns a `warning`, list empty — graceful, not a bug).
5. **Stop at commit** (remote) — do **not** push or open a PR; the owner pushes.

## Gotchas & notes (READ)

- **INT was REACHABLE this session** (unlike 2026-06-18). The commit `a1b25a9` used `SQL_SYNC_SKIP=1` as a precaution, but the SQL hooks actually **Passed** (`Apply pending SQL migrations to INT … Passed`). **Consequence for `/execute-plan`:** migration `0029`'s `db-migrate.py --env INT` step (Phase 5) **should apply from this box** — but re-check connectivity at execution; if INT goes unreachable, fall back to `SQL_SYNC_SKIP=1` on every commit and apply `0029` elsewhere. **Never `--no-verify`.**
- **`0029` may not stay free.** The migrations dir tops out at `0028_rename_ms02_process_to_05_pdbs.sql` *as of this session*. The MS02 work is unpushed/active — re-list `sql/_migrations/NexoraDB/` at execution and bump if `0029` got taken (the plan's Task 5 Step 0 says so).
- **Resolver shape trap.** `resolve_ms02_docfield_ids` (existing) = AND across fields, ONE `LIKE` value each. `resolve_ms02_pid_ids` (new) = the personal-number `"Name"`(s), MANY exact values OR-ed (`= ANY`). **Do NOT reuse the search resolver for PIDs** — it would intersect single-value LIKE calls and return ~nothing. The plan red-team (Finding F-shape) and Gotchas both flag this.
- **Fable outage.** `/write-plan` mandates Fable agents; Fable 5 returned "currently unavailable" for all 7 agents (0 tokens). Swapped to Opus 4.8 (peer model) by dropping the `model: 'fable'` override in the persisted workflow script and re-running — clean (920k subagent tokens, ~52 min, 191 tool uses). If re-running planning workflows, check Fable availability first.
- **MS02 media/DNS caveat** (`reference_ms02_media_host_dns`): MS02 Octo returns media URLs on bare host `mobscn02`, unresolvable from dev, so MS02 page images never render locally (placeholders) — **not a bug**. The audit is a separate Octo API call and should render; verify the full flow on **INT**, not dev, when Phase 7 browser-tests.
- **Caveman-speak preference** (`feedback_caveman_speak`): chat prose is caveman in this repo; code/commits/docs stay normal. (This handoff is a doc → normal.)
- **Background-agent file-sweep hazard** (`project_autopilot_fixer_stashes_untracked`): a stray `git stash -u` can sweep untracked files. Everything here is committed. If a file vanishes: `git stash list` → `git checkout "stash@{N}^3" -- <path>`.

## Untracked / left for owner

- **Nothing untracked** — working tree clean (only `a1b25a9` this session).
- **Owner build-time inputs** (the `col_pid` EAV `"Name"` seed + `MS02_DOCFIELDS_DB_NAME`) — see the plan's Owner-actions; supplied when execution reaches the live-enable point.
- `var/handoff-pending` points at this file (gitignored — not committed).
- **Prior owner debt still open** (unrelated, inherited): the whole MS02 multi-source + doc-field build is **unpushed** on `feature/2.5.63` (74 commits ahead); PR `feature/2.5.63` → `main`; PROD `psycopg2` + migrations `0023`–`0028` + seed `Statconfig`/`SearchConfig` ms02 rows — see `project_ms02_multisource_workitems` and `project_branch_consolidation_2_5_63`. This plan **stacks on** that unpushed work and must land after it.

## How to verify

```powershell
# Plan artifact present:
Test-Path docs/superpowers/plans/2026-06-22-ms02-prepared-docs-audit-import.md   # True

# This session's commit:
git log --oneline -1 a1b25a9     # docs(plans): add MS02 prepared-docs audit-import plan

# The doc-field machinery the plan STACKS ON is already present (anchors verified):
Select-String -Path nx_lib/workitem_sources.py -Pattern 'resolve_ms02_docfield_ids' -Quiet  # True
Select-String -Path nx_lib/workitem_sources.py -Pattern '_MS02_DOCFIELD_TABLE'      -Quiet  # True
Select-String -Path nx_lib/db.py               -Pattern 'engine_ms02_docfields_pg'   -Quiet  # True

# NOTHING from THIS plan is built yet (canary symbols absent until /execute-plan):
Select-String -Path nx_lib/workitem_sources.py -Pattern 'resolve_ms02_pid_ids'  -Quiet  # expect: False
Select-String -Path nx_lib/workitem_sources.py -Pattern 'parse_prepared_xlsx'   -Quiet  # expect: False
Select-String -Path nx_lib/views/workitems.py  -Pattern 'import_prepared_audit' -Quiet  # expect: False
Test-Path sql/_migrations/NexoraDB/0029_seed_workitems_prepared_audit_permission.sql     # expect: False
```

## Resuming in a fresh session

`/reset-session` (the flag in `var/handoff-pending` points here). No same-date handoff collision (latest prior is 2026-06-18), so the auto-pick is unambiguous; if needed, target it explicitly:

`/reset-session docs/superpowers/handoffs/2026-06-22-ms02-prepared-docs-audit-import-plan.md`

**First thing next session:** read `project_ms02_multisource_workitems` in auto-memory (full MS02 decision record), then `/execute-plan` against `docs/superpowers/plans/2026-06-22-ms02-prepared-docs-audit-import.md` starting at **Phase 1, Task 1** (`parse_prepared_xlsx`). The plan is self-contained (anchors verified, owner actions enumerated, every task is TDD with paste-ready commits). MS02 engines are `None` in dev → build everything; the import only goes live once the owner seeds `col_pid` + `MS02_DOCFIELDS_DB_NAME`.
