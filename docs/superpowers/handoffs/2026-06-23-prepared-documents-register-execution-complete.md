> ➡️ **Newer same-date handoff:** a later session (same day) wrote the *prepared-docs ⇄ workitem preview* PLAN. To resume **that**, see `docs/superpowers/handoffs/2026-06-23-prepared-docs-workitem-preview-plan.md`. This register handoff remains valid for its own owner-owed items (push, PR, PROD verification).

# Handoff — Prepared Documents Register (MS02): EXECUTION COMPLETE

**Date:** 2026-06-23 (evening) · **Branch:** `feature/2.5.63` · **125 commits ahead of origin** · **commit-only (remote)**
**Prior handoff:** `docs/superpowers/handoffs/2026-06-23-prepared-documents-register-plan.md` (the plan-only session this executes)
**Plan:** `docs/superpowers/plans/2026-06-23-prepared-documents-register.md` · **Spec:** `docs/superpowers/specs/2026-06-23-prepared-documents-register-design.md`
**SDD ledger (scratch, gitignored):** `.superpowers/sdd/progress.md` — full per-task review record.

## TL;DR

- **All 11 plan tasks built, each reviewed (spec + quality), final whole-branch review = "Ready to merge: Yes".** No Critical/Important findings anywhere; only cosmetic Minors (listed below).
- The MS02 prepared-docs Excel import is now a **persistent, accumulating, upsert-by-PID register** on its own page (`GET /prepared_documents`), backed by new table `dbo.PreparedDocuments` (**migration `0033`**, applied to INT). The old transient `?pidImport=` session-overlay is **fully torn down** (default workitems path is byte-identical to pre-overlay, proven against history).
- **NOT pushed** (remote/commit-only). Suite is green for this feature; the only failing tests are **3 pre-existing, unrelated** `test_octo` failures.
- **`var/handoff-pending` points here.** Resume with `/reset-session` (nothing left to build for this feature — see "Next steps").

## Migration renumber (important)

The plan/spec say migration **`0031`**, but `0031_fix_ms02_statconfig_dossierstatistik.sql` and `0032_ignore_pdbs_deletion_marker_activities.sql` were already on disk, so the table shipped as **`0033_create_prepared_documents.sql`**. CHANGELOG/CLAUDE.md/the SQL header/commit subjects all correctly say `0033`. The `0029` references (the reused `workitems.import.preparedaudit` permission) are correct and unchanged.

## This session's commits (oldest→newest)

```
3a838d9  feat(db): add dbo.PreparedDocuments register table (migration 0033)   [Task 1]
7efe047  feat(dashboard): MS02 across all dashboard charts   <-- EXTERNAL, NOT this feature (see Gotchas)
74bf54e  feat(prepared-docs): add PreparedDocuments data-access module          [Task 2]
4a64650  test(prepared-docs): fix DB-failure test to use app context            [Task 2 fix]
f015c91  feat(workitems): persist prepared-docs upload + add register page routes [Tasks 3+4]
b3eb286  feat(prepared-docs): add register page template + paired JS partial     [Task 5]
29eb6e6  refactor(workitems): remove the transient pidImport overlay machinery   [Task 6]
ccc2639  refactor(workitems): prepared-import button -> register page link       [Task 7]
4ba84ca  feat(security): register prepared-documents page in page_visibility()    [Task 8]
4eb4e61  chore(i18n): translate prepared-docs register strings for de/fr/it       [Task 9]
5e370c9  fix(i18n): correct German typo in prepared-docs clear-confirm            [Task 9 fix]
2d18918  docs(prepared-docs): document standalone register; retire overlay notes  [Task 10]
```
Plus the handoff commit this step creates. (Task 11 was verification-only — no commit.)

## What shipped (by area)

| Area | Files | Commits |
|---|---|---|
| **DB** | `sql/_migrations/NexoraDB/0033_create_prepared_documents.sql` (+ auto-dump `sql/NexoraDB/Tables/dbo.PreparedDocuments.sql`) | `3a838d9` |
| **Data access** | `nx_lib/prepared_documents.py` (upsert-by-PID via pre-SELECT+MERGE, count, OFFSET/FETCH page, clear) + `tests/unit/test_prepared_documents.py` | `74bf54e`, `4a64650` |
| **Routes** | `nx_lib/views/workitems.py`: `import_prepared_audit` rewritten to upsert; new `prepared_documents` (GET) + `clear_prepared_documents_route` (POST); both gated `@require_permission("workitems.import.preparedaudit")` + in-body `ms02_active` (403 page / 400 clear). `+` integration tests | `f015c91` |
| **Templates** | `templates/prepared_documents.html` + `templates/js/_prepared_documents_js.html` (assets match `workitems_overview.html`; live Octo soft-status column) | `b3eb286` |
| **Teardown** | removed `?pidImport=` reader, `WorkitemFilter.pid_import_active`, `SqlServerSource` short-circuit, synthetic-row/merge block, CSV guard, `_ms02_pid_processes`, import-col cells; workitems button → link | `29eb6e6`, `ccc2639` |
| **Wiring/i18n/docs** | `nx_lib/security.py` (`preparedDocsPagePerm`); de/fr/it catalogs; `CHANGELOG.md` + `CLAUDE.md` | `4ba84ca`, `4eb4e61`, `5e370c9`, `2d18918` |

## Next steps (ordered)

1. **Owner: push** `feature/2.5.63` (125 commits unpushed) after local review. Not done here (remote/commit-only).
2. **Owner: PR → `main`** (this feature + the large accumulated 2.5.63 backlog).
3. **PROD after deploy:** migration `0033` auto-applies before the pool stops — verify `dbo.PreparedDocuments` exists. Ensure the MS02 `SearchConfig col_pid` row is seeded on PROD so the live Octo status column resolves (a mismatch only degrades the column to "—"; the register still persists + renders). No new permission (reuses `0029`).
4. **Live-verify on INT/PROD** with a real MS02 operator account (e.g. `demo.user` holds the perm) — see "How to verify". Dev can render the page but cannot reach the MS02 columnar/Octo DBs.
5. **Optional cosmetic cleanups** (Minor, non-blocking — see below).

## Gotchas & notes (READ)

- **EXTERNAL commit `7efe047` "feat(dashboard): MS02 across all dashboard charts"** landed on the branch during this session (a background agent committed the dashboard WIP that was modified-but-uncommitted at session start, plus the untracked `0031_fix_*` migration). **It is NOT part of this feature** — different files (`dashboard.py`, `test_dashboard_stats.py`, CHANGELOG/CLAUDE.md, `0031_fix`). Left in place; reviewed as out-of-scope.
- **3 PRE-EXISTING failing tests (NOT from this work; will block the push gate):** `tests/unit/test_octo.py::test_get_extensions_urls_fields_{single_doc,batch_doc_iterates_children,non_batch_container_recurses}` fail with a **doubled scheme** — `'https://https://test.invalid/x.png' != 'https://cdn/x.png'` — from the octo media-host rewrite work (`f4592d3`), predating session HEAD `661d0ab`. This feature never touches `octo.py`/`test_octo.py`. **Owner: fix the octo double-`https://` rewrite OR update those 3 stale tests before pushing** (the pre-push gate runs the full suite).
- **`test_pot_is_in_sync` now PASSES** (Task 9 closed it).
- **Insert/update classification uses pre-SELECT + MERGE, NOT `OUTPUT $action`** (driver-safe, mirrors `_cache_store`). The `UQ_PreparedDocuments_PID` constraint self-defends against concurrent duplicate PIDs.
- **The `if not pid_specs:` warning early-return was intentionally REMOVED** — the register persists rows regardless of PID-column seeding; Octo status degrades to "—".
- **i18n summary msgid** `Imported %(total)s rows (%(new)s new, %(updated)s updated).` — this repo's Flask-Babel `%`-formats even on empty kwargs, so the template passes the `%(...)s` placeholders back as literal kwargs to keep the msgid intact AND render the literal text the JS `.replace()` needs. Don't "simplify" that.
- **Template cache:** restart `nx -u` after any template edit before browser checks.

## Untracked / left for owner (deliberately NOT committed)

- **` M .claudeignore`** — a subagent added `!.superpowers/sdd/` (to un-block reading the SDD scratch workspace). NOT part of this feature. Revert with `git checkout -- .claudeignore`, or keep it if you want AI tools to read `.superpowers/sdd/`.
- **`scripts/new-process.py`** — untracked StatConfig-insert helper, a known background-agent stray (dev-side, excluded from the deploy mirror). Not committed.
- **`sql/_migrations/NexoraDB/0032_ignore_pdbs_deletion_marker_activities.sql`** — untracked migration, not from this plan. Decide separately (record with `db-migrate.py --mark-applied` if already run on INT, else commit on its own).
- `var/handoff-pending` points here (gitignored — not committed).

## Cosmetic Minors (non-blocking, "when convenient")

- `nx_lib/prepared_documents.py`: `(row.get("collected_by") or "") or None` simplifies to `... or None` (same for `prepared_by`).
- `nx_lib/workitem_sources.py` (~line 638): `resolve_ms02_pid_to_wids` docstring still says "synthetic-row generation"; it now feeds the live Octo status column — reword.
- `clear_prepared_documents_route` reuses the import's "This import is only available for the MS02 client." string (off-label for a 'clear' action; plan-verbatim).
- No `_header.html` top-nav entry for `/prepared_documents` (by design — Decision 8, reached from the workitems-page link).

## How to verify

```powershell
git -C C:\dev\nexora log --oneline -12              # the 11 feature commits + external 7efe047
python scripts/test_db_reset.py                     # reset NEXORA_TEST state first
python -m pytest tests/unit/ tests/integration/ --no-cov -q   # 3 failed (octo, pre-existing) / ~1155 passed
python -m pytest tests/integration/test_workitems_routes.py -k prepared_documents -v  # 7/7 green
python -m pytest tests/unit/test_prepared_documents.py -v       # 6/6 green
python -m pytest tests/unit/test_translations.py -q             # 7/7 green
ruff check nx_lib/ tests/ ; ruff format --check nx_lib/ tests/  # clean
```
Live UI (INT/PROD only — dev cannot reach the MS02 data): `nx -u -b --loginas:demo.user`, then visit `/prepared_documents`. `ms02_active` is satisfiable on dev (page returns 200, not 403), but with no MS02 data the register is empty and Octo status shows "—".

## Resuming in a fresh session

`/reset-session` (the flag in `var/handoff-pending` points here). **This feature is fully built and reviewed — nothing left to implement.** The next session's job is the owner-side items above (push, PR, PROD verification, optional cosmetic cleanups, and the pre-existing octo-test fix that gates the push).

**Same-date tie-break:** many handoffs share `2026-06-23`. If `/reset-session` auto-picks the wrong one, target this file explicitly: `/reset-session docs/superpowers/handoffs/2026-06-23-prepared-documents-register-execution-complete.md`.
