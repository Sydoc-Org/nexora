# Handoff — Prepared Documents Register (MS02): standalone persistent list (PLAN ONLY, not executed)

**Date:** 2026-06-23 (afternoon/late) · **Branch:** `feature/2.5.63` · **112 commits ahead of origin** · **commit-only (remote)**
**Prior handoff:** `docs/superpowers/handoffs/2026-06-23-prepared-import-button-extra-fields-execution-complete.md` (the 5-column overlay this register REPLACES)
**Spec:** `docs/superpowers/specs/2026-06-23-prepared-documents-register-design.md` (`8faa40a`)
**Plan:** `docs/superpowers/plans/2026-06-23-prepared-documents-register.md` (`d32b89a`) — on disk in the main checkout (NO worktree this session)
**Durable context in auto-memory:** `project_ms02_multisource_workitems`, `project_ms02_docfield_columnar`, `project_int_migration_crlf_drift`, `project_flask_template_cache`, `reference_dev_server_global_python`, `feedback_caveman_speak`.

## TL;DR

- **Planning session only — NO product code shipped.** The user reframed the MS02 prepared-docs Excel import: it should **not** be a transient filter checking "is this PID already in Octo" — it is its **own persistent intake register** (a preprocess list; "No match" is normal). Brainstorm → spec → `/write-plan` produced a **6-phase / 11-task** implementation plan.
- **Spec + plan both committed on `feature/2.5.63`** (`8faa40a`, `d32b89a`). **No worktree** — work directly on the branch. The plan is on disk in the main checkout; resume with `/execute-plan`.
- **Fable 5 was unavailable** → the 7 planning agents (explore ×3 → minimal/structural drafts ×2 → red-team → merge) ran on **Opus**. Red-team surfaced **8 findings**; all resolved in the merge. Every file path / symbol / quoted snippet re-verified against live HEAD `d32b89a`.
- **Not pushed** (remote / commit-only).

## What the plan builds (the feature work, for the NEXT session)

1. **New table `dbo.PreparedDocuments`** (migration `0031`, NexoraDB): `ID PK, PID NVARCHAR(100) UNIQUE, Collected BIT, CollectedBy, Prepared BIT, PreparedBy, UploadedBy, UploadedAt, UpdatedAt`. **No `ClientCode`** (MS02-only, gated by `ms02_active`; YAGNI). Upsert key = `PID`.
2. **New data-access module `nx_lib/prepared_documents.py`** — owns ALL I/O against the table: upsert-by-PID, paginated read (`ORDER BY ID DESC OFFSET/FETCH`), count, clear. Uses the proven `_cache_store` MERGE pattern (no `OUTPUT $action`; a pre-`SELECT EXISTS` per PID classifies insert vs update — driver-safe).
3. **Rewrite `import_prepared_audit`** — keeps its front half (auth + MS02 gate + MIME sniff + `parse_prepared_xlsx`), swaps the back half from resolve-to-ids + session stash to a per-PID upsert; returns `{inserted, updated, total}`.
4. **New page `GET /prepared_documents`** (+ `POST /prepared_documents/clear`) → `templates/prepared_documents.html` + `templates/js/_prepared_documents_js.html`. Real DB pagination; live (non-stored) Octo soft-status column via the retained `resolve_ms02_pid_to_wids`; upload + clear-list controls live here.
5. **Tear down the old overlay** — delete the `pidImport` session stash, the `?pidImport=` block + row-merge + synthetic rows in `_get_workitems_data`, `WorkitemFilter.pid_import_active`, the `SqlServerSource.list_workitems` short-circuit, the CSV synthetic guard, and the workitems-page `pid_processes` / `_ms02_pid_processes` plumbing. Default workitems path returns **byte-identical**.
6. **Wiring** — `page_visibility()` entry; relink the workitems-page button to the new page; **reuse** `workitems.import.preparedaudit` (migration `0029`) — **no new permission**; i18n (de/fr/it); CHANGELOG; CLAUDE.md MS02 paragraph.

## Decisions locked in (from brainstorming)

| Decision | Choice |
|---|---|
| List model | Accumulating, **upsert by PID** (one row per PID) |
| Octo cross-reference | **Live soft-status** column (not stored, not the purpose) |
| Visibility | **Shared** across MS02 users (one global table; `UploadedBy` = audit stamp) |
| Behavior | **Read-only + clear-whole-list** (no per-row edit/tracking) for v1 |
| Permission | **Reuse** `workitems.import.preparedaudit` — no new perm |
| Schema | **No `ClientCode`** column (YAGNI; MS02-only) |

## This session's commits

```
8faa40a  docs(spec): prepared-documents standalone register (MS02)
d32b89a  docs(plans): add prepared-documents register implementation plan
```
Plus the handoff commit this step creates.

## Next steps (ordered)

1. **`/execute-plan`** — builds the 11 tasks TDD-per-task **directly on `feature/2.5.63`** (no worktree to merge this time). **Phase 1** (migration `0031` + `nx_lib/prepared_documents.py` with its unit test) is fully startable now.
   - Migration `0031` creates a real table → the `sql-migrate-int` pre-commit hook auto-applies it to INT and `sql-sync-check` regenerates `sql/NexoraDB/Tables/dbo.PreparedDocuments.sql` (do NOT hand-write that dump).
   - **Restart `nx -u`** after the new templates (Jinja process-lifetime cache) before any browser/e2e check.
   - CI/TEST has **no MS02 engine** → upload route `400`s with `"MS02"` in the body; the new page raises `403`; DB I/O in unit tests is mocked.
2. **Owner: push** `feature/2.5.63` (112 commits unpushed) once execution lands and is reviewed. Not done here (remote / commit-only).
3. **Live-verify on INT** (not dev): the MS02 columnar DB + media host are unresolvable from dev (`reference_ms02_media_host_dns`).

## Gotchas & notes (READ)

- **Teardown-heavy.** This deletes the `pidImport` overlay the two predecessor plans (`...prepared-docs-audit-import` + `...prepared-import-button-extra-fields`) just built. **Task 6 first VERIFIES** `pid_import_active` is feature-only (`grep`) before removing it.
- **`import-col` cell counts** (red-team F3): **8** real-row `<td>` + **4** synthetic `<td>` in `_workitems_overview_js.html`, plus **4** `<th>` in `workitems_overview.html`. The plan instructs grep-and-remove **every** occurrence (re-grep to confirm) rather than counting — miss one and the row goes malformed once `no-import-cols` is gone.
- **`has_permission` test trap** (red-team F6): route bodies use the `wv`-module-local `has_permission`; `workitems_all_perms` only patches `nx_lib.security.has_permission`. Page-render tests must ALSO `monkeypatch.setattr(wv, "has_permission", lambda code: True)` for the gated upload/clear controls to render.
- **`if not pid_specs:` early-return is intentionally REMOVED** (Task 3): the register persists rows regardless of whether the PID column is seeded; Octo status degrades to a dash. A test asserts upload still returns 200 with counts when `_ms02_pid_specs` is empty (the default CI path).
- **`engine_nexora_db`** is the real symbol (CLAUDE.md's `engineNexoraDB` is prose shorthand) — verified in `nx_lib/db.py`.
- **Octo soft-status link is best-effort:** `?search=<wid>` is perm-gated (`workitems.filter.workitemid`) AND a `LIKE`-substring match — documented as a soft reference, not an exact deep-link.
- **Workflow script (resume/iterate):** `C:\Users\bes\.claude\projects\C--dev-nexora\e6b2c517-e1ce-4454-a47e-27f289946253\workflows\scripts\plan-prepared-documents-register-wf_ee2d1148-422.js` (agents set to `model: 'opus'` after the Fable 5 outage).
- **Caveman-speak** for chat in this repo (`feedback_caveman_speak`); docs/code/commits stay normal (this handoff is a doc → normal).

## Untracked / left for owner

- **`scripts/new-process.py`** — still-untracked `StatConfig`-insert helper, a known background-agent stray (`reference_ruflo_stashes_work`); harmless (dev-side, excluded from the deploy mirror). Not committed.
- `var/handoff-pending` points at this file (gitignored — not committed).

## How to verify

```powershell
git -C C:\dev\nexora log --oneline -3        # d32b89a plan, 8faa40a spec
Test-Path C:\dev\nexora\docs\superpowers\plans\2026-06-23-prepared-documents-register.md   # True
Select-String docs/superpowers/plans/2026-06-23-prepared-documents-register.md -Pattern 'dbo\.PreparedDocuments' -Quiet   # True
```

## Resuming in a fresh session

`/reset-session` (the flag in `var/handoff-pending` points here). To actually build the feature, use **`/execute-plan`** — **no worktree this time**; it works directly on `feature/2.5.63`.

**Same-date tie-break:** many handoffs share `2026-06-23`. If `/reset-session` auto-picks the wrong one, target this file explicitly: `/reset-session docs/superpowers/handoffs/2026-06-23-prepared-documents-register-plan.md`.

**Nothing is built yet** — this session only wrote and committed the spec + plan. The feature is entirely ahead in `/execute-plan`.
