# Handoff — MS02 prepared-documents Excel import + audit display (BUILT, all 11 tasks complete)

**Date:** 2026-06-22 (afternoon) · **Branch:** `feature/2.5.63` · **87 commits ahead of origin** · **commit-only (remote)**
**Prior handoff:** `docs/superpowers/handoffs/2026-06-22-ms02-prepared-docs-audit-import-plan.md` (the design-only session that wrote the plan this session executed)
**Plan executed:** `docs/superpowers/plans/2026-06-22-ms02-prepared-docs-audit-import.md` (11 tasks / 9 phases)
**Durable context in auto-memory:** `project_ms02_multisource_workitems` (full MS02 decision record — read first), plus `reference_ms02_media_host_dns`, `project_int_migration_crlf_drift`, `reference_sql_migrations`, `feedback_caveman_speak`.

## TL;DR

- **The whole plan is built and committed** — 12 feature commits on `feature/2.5.63` (`32f890a`..`e92d57a`). Subagent-driven execution: fresh implementer per task → spec+quality review → fix loop. No worktree (work landed directly on the feature branch).
- **Final whole-branch review (Opus): READY TO MERGE.** No Critical, no Important. Verified the full token lifecycle, intersection semantics, byte-identical default path, MS02 suppression, SQL-injection surface (none), and PII handling (uploaded file never written to disk; ids ride a session token).
- **Migration `0029` is APPLIED to INT** (1 `dbo.Permission` row + 2 `AccessProfilePermission` rows, verified). Hooks passed without `SQL_SYNC_SKIP` — INT CRLF drift appears clean this session.
- **Tests green:** full `tests/unit tests/integration` = **1124 passed / 24 skipped (informational coverage gates) / 0 failed**; `ruff check` + `ruff format --check` clean (157 files); `test_translations.py` 7/7 (de/fr/it).
- **Not yet pushed** (remote / commit-only). Owner pushes + opens the PR. **Owner build-time enablement still required** before the import resolves anything live (the `col_pid` SearchConfig seed + `MS02_DOCFIELDS_DB_NAME`) — see Next steps.

## This session's commits (oldest → newest)

```
32f890a  feat(workitems): add pure parse_prepared_xlsx PID/Prepared Excel parser
18ed0a4  feat(workitems): add resolve_ms02_pid_ids sibling resolver
87cea5d  feat(files): allow .xlsx uploads in the libmagic MIME whitelist
6b2014c  feat(workitems): thread pidImport token into workitem list
46e9daa  test(workitems): cover pidImport intersection branch          (Task 4 review fix)
6316a58  feat(db): seed workitems.import.preparedaudit permission (0029)
37df372  feat(workitems): add MS02-only import_prepared_audit upload route
c23e0c7  fix(workitems): distinguish PID-resolver error from zero-match + harden  (Task 6 review fix)
07167e7  feat(workitems): MS02-only Prepared-documents upload control + banner
ebd36db  feat(workitems): wire Prepared-documents upload -> PID filter + banner
0864a78  chore(i18n): translate MS02 prepared-documents import strings (de/fr/it)
e92d57a  docs: record MS02 prepared-documents import + resolve_ms02_pid_ids
```
Plus the handoff commit this step creates. Working tree is clean except one **unrelated** untracked file — see "Untracked / left for owner".

## What shipped (by phase / file)

| Phase / Task | Files | What |
|---|---|---|
| 1 — parser | `nx_lib/workitem_sources.py`, `tests/unit/test_prepared_xlsx_parser.py` | Pure `parse_prepared_xlsx(bytes)->(pairs,error)`: openpyxl, header case-insensitive/order-agnostic, dedup (first wins), 10000-row cap, integer PIDs never gain `.0`, **never raises** (logging via a context-safe suppressing helper since the parser may run outside an app context). |
| 2 — resolver | `nx_lib/workitem_sources.py`, `tests/unit/test_workitem_sources.py` | `build_ms02_pid_sql` + `resolve_ms02_pid_ids` — sibling to `resolve_ms02_docfield_ids`: personal-number `"Name"`(s) matched against MANY exact PIDs via `"StringValue" = ANY(%s)`. Three-way contract (`None`/`set()`/`{ids}`), reuses the `_MS02_DOCFIELD_*` constants. |
| 3 — upload MIME | `nx_lib/files.py`, `tests/unit/test_files_xlsx.py` | `.xlsx` added to `ALLOWED_MIME_TYPES` (office-openxml + `application/zip` + `application/octet-stream`). Local libmagic reports `application/zip`. |
| 4 — orchestrator | `nx_lib/views/workitems.py`, `nx_lib/workitem_sources.py`, `tests/unit/test_workitems_pid_filter.py`, `tests/unit/test_workitem_sources.py` | `_get_workitems_data` reads `?pidImport=<token>` → `session["pid_import:<token>"]` → intersects into `ms02_docfield_ids`. New `WorkitemFilter.pid_import_active` → `SqlServerSource.list_workitems` early-returns `([],0)` (MS02-only). Default path byte-identical when absent. |
| 5 — migration | `sql/_migrations/NexoraDB/0029_seed_workitems_prepared_audit_permission.sql`, `sql/test/seed.sql` | Seeds `workitems.import.preparedaudit` (idempotent, Effect `'A'` to every `admin.view` profile), modelled on `0018`. **Applied to INT.** |
| 6 — route | `nx_lib/views/workitems.py`, `tests/integration/test_workitems_routes.py` | `POST /import_prepared_audit` (`@require_permission`, MS02-gated, libmagic sniff + workbook parse, file never written to disk, dynamic `col_pid`/process-key read, `secrets.token_urlsafe` session stash). Review fix: resolver `None` (DB error) → 500, distinct from `set()` zero-match. |
| 7 — template | `nx_lib/views/workitems.py`, `templates/workitems_overview.html` | Render flags `prepared_import_perm` + `ms02_active`; MS02-gated upload control + dismissible banner. |
| 8 — JS | `templates/js/_workitems_overview_js.html` | `uploadPreparedAudit` POSTs then re-queries via the existing `fetchAndUpdateWorkitems` with `?pidImport=<token>` on the **fetch URL only** (address bar stays clean). All additions placed in the same closure as `fetchAndUpdateWorkitems`. |
| 9 — i18n | `messages.pot`, `translations/{de,fr,it}/…` | New strings translated, non-fuzzy; `test_translations.py` 7/7. |
| 10 — docs | `CHANGELOG.md`, `CLAUDE.md`, `docs/superpowers/specs/2026-06-16-ms02-client-merged-workitems-design.md` | Changelog `[Unreleased]` entry, CLAUDE.md MS02 paragraph appended, spec §4.6 one-liner. |
| 11 — verify | (no files) | Full suite + ruff + i18n all green (see How to verify). |

## Next steps (ordered)

1. **Owner: push + open PR** `feature/2.5.63` → `main` (this whole branch — 87 commits — is unpushed; this feature stacks on the prior MS02 multi-source + doc-field work). Not done here (remote / commit-only).
2. **Owner build-time enablement** (until these land, the import resolves nothing — the route returns a `warning`, the list is empty; graceful, NOT a bug):
   - **Seed `col_pid`** in a `'ms02'` `dbo.SearchConfig` row (`ClientCode='ms02'`, `ProcessName='sydoc.05_PDBS'`, `col_pid='<the EAV "Name" the personal number is indexed under>'`). The route reads `col_pid` dynamically and whitelists it via `get_valid_search_columns()`. (If you prefer a different `col_<field>` name, change the `_MS02_PID_SEARCH_FIELD` constant in `nx_lib/views/workitems.py`.)
   - **Set `MS02_DOCFIELDS_DB_NAME`** in `env/INT.env` + `env/PROD.env` (standing MS02 obligation — `engine_ms02_docfields_pg` is `None` until set).
   - **Confirm PID format** matches the indexed `"StringValue"` byte-for-byte (Excel float coercion / zero-padding — Owner action #3 in the plan).
   - **Confirm SYAPP01 prod libmagic** MIME for a real `.xlsx` (whitelist accepts office-openxml/zip/octet-stream; widen `ALLOWED_MIME_TYPES["xlsx"]` if prod emits something else — Owner action #7).
   - **Grant `workitems.import.preparedaudit`** to the MS02 operator profile(s) (the `0018`-style seed already gives it to `admin.view` profiles).
   - PROD: `psycopg2-binary` already required; migration `0029` auto-applies on deploy.
3. **Verify the live UI on INT** (NOT dev — see Gotchas): upload a small two-column `.xlsx`, confirm the matched MS02 workitems list and that opening a row shows the existing Octo audit (`loadHistory` → `/api/get_audithistory/<id>`).
4. **Optional follow-ups** (all Minor, the final review cleared them for merge — owner's call):
   - **#1 (most substantive):** the import session token is never evicted — repeated uploads accumulate stale `session["pid_import:*"]` entries (≤10k ints each), bounded by session lifetime + the cleanup cron. ~3-line fix: pop prior `pid_import:*` keys before writing the new token.
   - **#2:** the route returns a `prepared` `{pid:bool}` map the JS never reads (plan-mandated Decision #7; could drop).
   - **#3:** `activePidToken` persists across normal filter changes (intersect stays correct; UX-only).
   - **#4:** `parse_prepared_xlsx` error strings are bare English (parser kept context-free) — wrap them at the route boundary so de/fr/it users don't see English on a malformed upload.

## Gotchas & notes (READ)

- **PID is NOT a workitem id and NOT a process id** — it's a personal number, indexed as a doc-field in the MS02 EAV DB. Resolution is ALWAYS through `engine_ms02_docfields_pg` via the seeded `"Name"`.
- **Resolver shape is the INVERSE of the search resolver.** `resolve_ms02_docfield_ids` = AND across fields, ONE `LIKE` each. `resolve_ms02_pid_ids` = the personal-number `"Name"`(s), MANY exact values OR-ed (`= ANY`). They are siblings — do not merge them.
- **MS02 media/DNS caveat** (`reference_ms02_media_host_dns`): MS02 Octo returns media URLs on bare host `mobscn02`, unresolvable from dev → page images never render locally. The **audit** is a separate Octo API call. Verify the full flow on **INT**, not dev.
- **Local dev shows NO control:** `engine_ms02_docfields_pg` is `None` locally → `ms02_active` is false → the control is gated off. Nothing to screenshot locally; the JS additions are null-guarded (inert when the control is absent). The integration suite covers `/workitems` rendering. Live UI verification is the INT step above.
- **INT CRLF drift was clean this session** — commits + the `sql-migrate-int`/`sql-sync-check` hooks passed without `SQL_SYNC_SKIP=1`. If a future commit trips the known 0001–0003 checksum drift, prefix `SQL_SYNC_SKIP=1 git commit`. Never `--no-verify`.
- **Template cache:** restart `nx -u` after the template/JS edits or browser/e2e tests see stale HTML.
- **Caveman-speak preference** (`feedback_caveman_speak`): chat prose is caveman in this repo; code/commits/docs stay normal. (This handoff is a doc → normal.)

## Untracked / left for owner

- **`scripts/new-process.py`** — an UNTRACKED interactive `StatConfig`-insert helper that appeared mid-session (mtime 13:19; **not** part of this feature, not created by any task — likely a background-agent/ruflo stray, per `reference_ruflo_stashes_work`). Deliberately **NOT committed** and **not deleted** (didn't create it; surfacing per policy). Owner: keep/commit/remove as you see fit. It lives in `scripts/` (dev-side, excluded from the deploy mirror), so it's harmless either way.
- `.superpowers/sdd/` — gitignored SDD scratch (task briefs, per-task reports, review packages, `progress.md` ledger). Safe to delete.
- `var/handoff-pending` points at this file (gitignored — not committed).

## How to verify

```powershell
# Canary symbols PRESENT (feature built):
Select-String nx_lib/workitem_sources.py -Pattern 'resolve_ms02_pid_ids','parse_prepared_xlsx' -Quiet   # True
Select-String nx_lib/views/workitems.py  -Pattern 'import_prepared_audit' -Quiet                         # True
Test-Path sql/_migrations/NexoraDB/0029_seed_workitems_prepared_audit_permission.sql                     # True

# Migration row on INT:
#   SELECT Code FROM dbo.Permission WHERE Code = 'workitems.import.preparedaudit';   -- 1 row

# Tests (reset order-dependent state first):
python scripts/test_db_reset.py
python -m pytest tests/unit tests/integration -q          # 1124 passed / 24 skipped / 0 failed
python -m pytest tests/unit/test_translations.py -v        # 7 passed
ruff check nx_lib/ tests/                                  # All checks passed!
ruff format --check nx_lib/ tests/                         # 157 files already formatted
```

## Resuming in a fresh session

`/reset-session` (the flag in `var/handoff-pending` points here). **Same-date collision:** the design-only handoff `2026-06-22-ms02-prepared-docs-audit-import-plan.md` shares today's date and now carries a forward-pointer banner to this file. If `/reset-session` auto-picks the wrong one, target this file explicitly:

`/reset-session docs/superpowers/handoffs/2026-06-22-ms02-prepared-docs-audit-import-execution-complete.md`

**The build is done.** The remaining work is owner-side: push + PR, the `col_pid`/`MS02_DOCFIELDS_DB_NAME` enablement, and INT live-flow verification (see Next steps). The optional Minor follow-ups are listed above if you want to pick one up.
