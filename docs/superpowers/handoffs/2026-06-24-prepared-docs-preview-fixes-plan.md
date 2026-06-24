> ➡️ **SUPERSEDED — this plan has been executed.** See the execution handoff:
> `docs/superpowers/handoffs/2026-06-24-prepared-docs-preview-fixes-execution-complete.md`
> (all 4 tasks committed `69b2085..e493d25`, final review READY TO MERGE).

# Handoff — Prepared Documents Preview & Register Polish (PLAN ONLY, not executed)

**Date:** 2026-06-24 · **Branch:** `feature/2.5.63` · **149 commits unpushed** · **commit-only (remote)** · no dedicated plan worktree
**Prior handoff:** `docs/superpowers/handoffs/2026-06-24-prepared-docs-workitem-preview-execution-complete.md` (the predecessor feature this builds on)
**Plan (written, NOT executed):** `docs/superpowers/plans/2026-06-24-prepared-docs-preview-fixes.md`
**Spec:** none (this was a `/write-plan` run; no spec authored for this slug)

## TL;DR

- **A plan was written and committed — no code changed yet.** Next session runs `/execute-plan`.
- Covers **three reported defects** on the MS02 "Prepared Documents" register + its read-only Octo
  Workitem-preview modal: (1) ragged register table — centered headers render left over centered
  body cells; (2) the "Prepared documents" entry button on the Workitems overview shows for every
  process; (3) the preview-modal timeline (Import→Extraction→Validation→Delivery) renders all-grey.
- **Locked decision (owner-confirmed this session):** the entry button is visible **only when an
  MS02 prepared-docs target process is selected** (`process_name in _ms02_target_processes()`, e.g.
  `sydoc.05_PDBS`) — hidden on "All Processes" and every non-PDBS process.
- Built via the multi-agent planning workflow (explore → dual minimal/structural drafts →
  adversarial red-team → merge). **Agents ran on Opus 4.8 — Fable 5 was unavailable.** Every
  file/symbol/snippet anchor was re-verified against the live repo before commit.

## This session's commit

```
681b839  docs(plans): add prepared-docs-preview-fixes implementation plan
```
(1 file, 528 insertions — the plan only. No source, no tests, no migration.)

## What the plan delivers (4 phases, 5 tasks — bite-sized, TDD, commit-per-task)

| Phase | Bug | Fix (minimal-diff) | Key files |
|---|---|---|---|
| **P1** | Column alignment | Swap the 3 centered HEADER `<th>` from Tailwind `text-center` (loses to `.nx-table thead th{text-align:left}`, specificity 0,1,2) to the shared `.nx-table .align-center` helper (0,2,0 — wins). Body cells already center; untouched. | `templates/prepared_documents.html` |
| **P2** | Button gating | Compute `prepared_docs_process_match` (perm + `ms02_active` + `process_name in _ms02_target_processes()`) in `workitems_overview()`; tighten the Jinja `{% if %}`. Rewrite the now-inverted link test + add hidden-on-all sibling. | `nx_lib/views/workitems.py`, `templates/workitems_overview.html`, `tests/integration/test_workitems_routes.py` |
| **P3** | Preview timeline grey | New never-raising `resolve_octo_wid_stage(engine, wid)` in `nx_lib/workitem_sources.py` (mirrors the list query's Status/CurrentStage CASE-over-`t_ActivityInstances`-join, ROW_NUMBER latest slice). `prepared_documents()` calls it with `CLIENTS["default"].runtime_engine`, emits `data-status`/`data-current-stage` on the Preview button; `openPreview` forwards them into `render`'s existing `opts.status`/`opts.currentStage` fallback. **Shared panel partial NOT edited.** | `nx_lib/workitem_sources.py`, `nx_lib/views/workitems.py`, `templates/prepared_documents.html`, `templates/js/_prepared_documents_js.html`, tests |
| **P4** | Docs sync | CHANGELOG (correct the stale "decoupled from the process filter" line) + CLAUDE.md. | `CHANGELOG.md`, `CLAUDE.md` |

**No migration. No new permission. No new i18n strings** (all labels already `_()`-wrapped; the new
`data-*` values are DB-sourced) → **no pybabel cycle**. All verified in the plan's Context section.

## Next steps (ordered)

1. **`/execute-plan`** from `C:\dev\nexora` (branch `feature/2.5.63`). It reads the newest plan
   (`docs/superpowers/plans/2026-06-24-prepared-docs-preview-fixes.md`) and runs P1→P4 task-by-task
   (subagent-driven recommended). Each task is test-first with a paste-ready commit message.
2. **Owner browser-verify** the UI bits the executor screenshots — esp. **O1** below (the lit
   timeline needs a reachable Octo, which dev/CI lack).
3. **Owner: push** `feature/2.5.63` + open the PR to `main` (remote / commit-only — never done here).

## Owner actions baked into the plan (not the executor's job)

- **O1 — live timeline correctness.** Dev/CI has no reachable Octo, so `resolve_octo_wid_stage`
  returns `{None, None}` locally → timeline stays grey. The executor verifies the data plumbing via
  tests + a **synthetic** browser check (inject a fake `data-status`/`data-current-stage`). The owner
  confirms the right step lights for a real PDBS document's stage on INT/PROD after deploy.
- **O3 — Bug-1 scope.** Verified root cause is header **text alignment**. If Image #1's raggedness
  also includes uneven **column widths**, the owner decides whether to add `table-fixed`/`<colgroup>`
  — the plan deliberately does NOT pin widths speculatively (flagged in the P1 screenshot).
- **Assumption to watch:** the wid from `resolve_ms02_pid_to_wids` is treated as a **default-client**
  Octo id queryable via `t_WorkItems.ID`. If PROD shows a persistently grey timeline for documents
  known to be mid-pipeline, the wid id-space is wrong — flag it.

## Gotchas & notes (READ)

- **Plan agents ran on Opus 4.8, not Fable 5** (Fable was down — `/write-plan` mandates Fable but the
  session model is the top tier, so this is not a downgrade). The commit trailer reflects Opus.
- **Working-directory quirk.** This session ran from
  `C:\dev\nexora\.claude\worktrees\plan-prepared-docs-workitem-preview` — a **leftover folder** from
  the predecessor plan session. It is **gitignored** and is **NOT** a registered git worktree
  (`git worktree list` doesn't show it; `git rev-parse --show-toplevel` resolves to `C:\dev\nexora`),
  so all git/file ops acted on the `feature/2.5.63` main working tree. **No dedicated `plan/...`
  worktree was created.** `/execute-plan` should run from `C:\dev\nexora` directly. (Harmless leftover
  folder; the owner may `rm -rf` it.)
- **Anchors verified, not assumed.** Before committing, the load-bearing claims were grep-confirmed
  against HEAD: the `.nx-table thead th` / `.nx-table .align-center` rules; the three
  `px-6 py-3 text-center` headers; the `{% if prepared_import_perm and ms02_active %}` gate +
  `prepared-docs-link`; `_ms02_target_processes`, `process_name`, the `octo_status[pid] = {...}` loop,
  `prepared_import_perm`/`ms02_active`; the SQL-Server CASE block + `INNER JOIN t_ActivityInstances` +
  `ROW_NUMBER() OVER(...)`; `runtime_engine=engine_octo_db`; the `render` `opts.status`/`opts.currentStage`
  fallback + `const stages`; the real `openPreview(wid)` body (incl. `attachLightbox`/`ensureFieldConfig`,
  which the plan's rewrite preserves verbatim); and all three referenced test functions.
- **Plan's anchor rule:** snippets, never line numbers. Re-grep before each edit (files drift).
- **`SQL_SYNC_SKIP=1`** prefix on commits (known INT `SchemaMigrations` CRLF drift); the plan's commit
  templates already include it. Never `--no-verify`. (This session's commit hooks actually passed.)
- **Pre-existing red tests still loom** (NOT this feature):
  `tests/unit/test_octo.py::test_get_extensions_urls_fields_{single_doc,batch_doc_iterates_children,non_batch_container_recurses}`
  — the Octo media-host double-scheme bug. They gate the pre-push e2e run; owner fixes/updates them.

## Untracked / left for owner (pre-existing strays, NOT this session)

- `.claude/helpers/notify-toast.ps1` (M), `.claudeignore` (M) — modified, not staged.
- `scripts/new-process.py` (untracked).
- `sql/_migrations/NexoraDB/0032_ignore_pdbs_deletion_marker_activities.sql` (untracked) — a separate
  PDBS migration, **not** part of these three fixes; if wanted it needs its **own** commit + an INT
  apply. The plan touches no SQL.

## How to verify (plan exists; nothing executed)

```powershell
# From C:\dev\nexora (feature/2.5.63):
git log -1 --stat                                     # 681b839, the plan file only
git status --porcelain                                # only the 4 pre-existing strays above
# The plan itself (read before executing):
#   docs/superpowers/plans/2026-06-24-prepared-docs-preview-fixes.md
# After /execute-plan, the plan's own per-task commands gate each step, e.g.:
python -m pytest tests/integration/test_workitems_routes.py -k "prepared" -x
python -m pytest tests/unit/test_workitem_sources.py -k resolve_octo_wid_stage -x
```

## Resuming in a fresh session

`/reset-session` (the flag in `var/handoff-pending` points here), then **`/execute-plan`** — it picks
the newest plan, which is `docs/superpowers/plans/2026-06-24-prepared-docs-preview-fixes.md`.

**Same-date tie-break:** `2026-06-24` also has
`…-prepared-docs-workitem-preview-execution-complete.md` (a DONE/merged feature, no action). To target
this plan handoff explicitly:
`/reset-session docs/superpowers/handoffs/2026-06-24-prepared-docs-preview-fixes-plan.md`.
