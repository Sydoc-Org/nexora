> **⏩ Newer same-date handoff:** a later 2026-06-24 session wrote a follow-up plan —
> `docs/superpowers/handoffs/2026-06-24-prepared-docs-preview-fixes-plan.md` (three preview/register
> polish fixes, **not yet executed**). If you're resuming the newest work, target that file.

# Handoff — Prepared Documents ⇄ Workitem Preview (EXECUTION COMPLETE, merged)

**Date:** 2026-06-24 · **Built on branch:** `plan/prepared-docs-workitem-preview` (worktree) → **merged `--no-ff` into `feature/2.5.63`** · **commit-only (remote)** · worktree removed + branch deleted at end of session
**Prior handoff:** `docs/superpowers/handoffs/2026-06-23-prepared-docs-workitem-preview-plan.md` (the PLAN-ONLY session this executes)
**Spec:** `docs/superpowers/specs/2026-06-23-prepared-docs-workitem-preview-design.md`
**Plan (executed):** `docs/superpowers/plans/2026-06-23-prepared-docs-workitem-preview.md`

## TL;DR

- **Feature fully built and merged.** Executed the 4-phase / 16-task plan via subagent-driven development (fresh implementer + spec/quality reviewer per task). All 16 tasks complete.
- **Two cross-task `window.*` mirror bugs were caught by the review loop** (not the test suite — the integration suite asserts routes/markers, not the JS DOM): the assignee dropdown going empty (`window.mentionableUsers`, fixed `f22ec2f`) and field labels regressing to raw keys (`window.fieldConfig`, found by the **final whole-branch review**, fixed `c88df0c`).
- **Green:** full unit+integration suite **1175 passed**, the only reds are the 3 pre-existing `test_octo` failures (unrelated; see Gotchas). `ruff check` + `ruff format --check` clean. Final whole-branch review (opus): **Ready to merge**.
- **Not pushed** (remote / commit-only). The interactive browser smoke is **deferred to the owner** (see Gotchas).

## This session's commits (oldest → newest, on `plan/prepared-docs-workitem-preview`, now in `feature/2.5.63`)

```
902540d  refactor(workitems): scaffold shared NexoraWorkitemDetail partial (P1.1)
193145c  refactor(workitems): move detail loaders+source helpers into partial (P1.2)
f22ec2f  fix(workitems): pass mentionableUsers to relocated loadCollaborationData (P1.2 review fix)
aef7b49  refactor(workitems): row-expand uses NexoraWorkitemDetail.render (P1.3)
7498f09  refactor(workitems): lightbox engine container-scoped via attachLightbox (P1.4)
16b1c07  test(workitems): assert panel read-only branch omits controls (P1.5)
455f45a  feat(prepared-docs): preview button + modal/lightbox shells (P2.1)
99c3f2d  test: add pid kwarg to prepared_documents mocks for forward compat (P2.2)
3c0fa45  feat(prepared-docs): wire Preview btn to read-only shared panel (P2.3)
47b9789  test(prepared-docs): preview-degradation assert + modal strings de/fr/it (P2.4)
159554c  feat(prepared-docs): pids_in_register helper + optional pid filter (P3.1)
82fac7a  feat(prepared-docs): register ?pid exact-match filter + Show-all (P3.2)
35a5906  feat(workitems): stamp pid + in_register on visible MS02 rows (P3.3)
4ca1d21  feat(workitems): render 'In register' chip in detail panel header (P3.4)
949a7ed  chore(i18n): reverse chip + show-all strings de/fr/it (P3.5)
b1c2d86  docs: changelog + CLAUDE.md for prepared-docs/workitem cross-linking (P4.1)
c88df0c  fix(workitems): mirror fieldConfig to window for shared panel labels (final-review fix)
```
Plus the handoff commit + the `--no-ff` merge commit this step creates.

## What shipped

| Phase | What | Key files |
|---|---|---|
| **P1** | Extracted the Workitems detail panel into a shared client-side partial `window.NexoraWorkitemDetail.render(wid, container, {readOnly, perms, inRegisterPid})` + container-scoped `attachLightbox(idMap)`. Refactored the Workitems row-expand to consume it (behaviour unchanged). 13 loaders/source helpers + the lightbox engine moved; page aliases them from `window`. | new `templates/js/_workitem_detail_panel_js.html`; `templates/js/_workitems_overview_js.html`; `templates/workitems_overview.html` |
| **P2** | Read-only **Preview modal** on the register's Octo-Status cell mirroring the full detail panel (images/source-highlighting/fields/audit/tags/comments) beside the renamed "Open in Workitems" link; write controls **omitted**. | `nx_lib/views/workitems.py` (`prepared_documents` perms), `templates/prepared_documents.html`, `templates/js/_prepared_documents_js.html` |
| **P3** | Reverse **"In register" chip** on the Workitems detail panel → `prepared_documents?pid=<pid>`; register `?pid=` exact filter + "Show all" reset; `pids_in_register()` + `resolve_ms02_wids_to_pids()` + pure `_stamp_in_register()` in `_get_workitems_data`. | `nx_lib/prepared_documents.py`, `nx_lib/workitem_sources.py`, `nx_lib/views/workitems.py`, templates |
| **P4** | CHANGELOG + CLAUDE.md + de/fr/it i18n (`Preview`/`Open in Workitems`/`Workitem preview`/`In register`/`Show all`). | `CHANGELOG.md`, `CLAUDE.md`, `translations/`, `messages.pot` |

Read-only, **MS02-only**, **no new permission** (reuses `workitems.import.preparedaudit` + `workitems.details.view.*`), **no new migration** (`dbo.PreparedDocuments` already exists).

## Next steps (ordered)

1. **Owner: interactive browser smoke** (deferred — see Gotchas). On INT/PROD as an MS02 user with a populated register, verify: (a) Workitems row-expand unchanged incl. lightbox/click-to-locate AND **field labels render with friendly names, not raw keys** (the `c88df0c` fix — exercise both a fresh page-init load and a process-filter change that triggers `fetchFieldConfig`), AND the **assignee dropdown is populated** (the `f22ec2f` fix); (b) register **Preview** modal read-only mirror; (c) reverse **"In register"** chip → `?pid` filtered register → Show all. Full image preview needs the Octo media host (PROD-reachable, blank on dev).
2. **Owner: push** `feature/2.5.63` (now ~145 commits unpushed) once reviewed, then open the PR to `main`. Not done here (remote / commit-only).
3. **Owner: fix or update the 3 pre-existing `test_octo` reds** before the pre-push e2e gate (unrelated to this feature — see Gotchas).

## Gotchas & notes (READ)

- **Pre-existing red tests (NOT this feature):** `tests/unit/test_octo.py::test_get_extensions_urls_fields_{single_doc,batch_doc_iterates_children,non_batch_container_recurses}` — the Octo media-host double-scheme bug. The full suite is otherwise **1175 passed**. These 3 will gate the pre-push e2e run; the owner must fix octo OR update the 3 stale tests before pushing. Do not let a "suite green" claim hide them.
- **Interactive browser smoke deferred to the owner.** This was an autonomous remote session: the `nx` dev server serves from the shell CWD (would need driving from this worktree), and dev cannot reach MS02/Octo media for the P2/P3 visuals — so the JS-DOM smoke (assignee dropdown, field labels, lightbox, preview modal, chip) was **not run here**. The plan already designates visual verification an Owner action. Code verification is fully green and the final whole-branch review passed; the one symptom most worth eyeballing is **field labels rendering friendly names** in an expanded Workitems row (the cross-task bug the suite can't see).
- **Two cross-task `window.*` mirror bugs (both fixed):** the shared partial (a separate IIFE) reads `window.mentionableUsers` and `window.fieldConfig`, but the page declared module-scope `let mentionableUsers` / `let fieldConfig` and didn't mirror them. Left unfixed these silently emptied the assignee dropdown and degraded field labels to raw keys — invisible to the route/marker tests. Fixed in `f22ec2f` (mentionableUsers, caught mid-P1) and `c88df0c` (fieldConfig, caught by the final review). If you touch either var on the workitems page, keep the `window.* = ...` mirror at every assignment site.
- **No new migration / permission / deploy-exclude change.** The one new file (`templates/js/_workitem_detail_panel_js.html`) is under `templates/` (already mirrored to prod). Confirmed.
- **`SQL_SYNC_SKIP=1`** was needed on some commits (INT `SchemaMigrations` CRLF drift / INT reachability) — no SQL changes in this feature; `--no-verify` was never used.

## Untracked / left for owner

- SDD scratch under `.superpowers/sdd/` (task briefs, implementer/reviewer reports, the progress ledger, review-package diffs) is **gitignored** (self-ignoring `.gitignore`) — not committed. The worktree removal takes it with the worktree.
- Background-agent strays noted in the prior plan handoff live in the **MAIN checkout** (`C:\dev\nexora`), not this worktree — untouched.

## How to verify

```powershell
# After merge, from C:\dev\nexora (feature/2.5.63):
git log --oneline -3                                  # merge commit + c88df0c handoff/fix at the top
git worktree list                                     # plan-prepared-docs-workitem-preview is GONE
python scripts/test_db_reset.py
python -m pytest tests/unit tests/integration -q      # 1175 passed, 3 failed (the known test_octo reds only)
ruff check nx_lib tests ; ruff format --check nx_lib tests   # clean
python -m pytest tests/unit/test_translations.py -q   # 7 passed (pot in sync; de/fr/it complete)
```

## Resuming in a fresh session

`/reset-session` (the flag in `var/handoff-pending` points here). The feature is **done and merged into `feature/2.5.63`** — no `/execute-plan` needed. The remaining work is owner-only (browser smoke, push, PR, the pre-existing octo reds).

**Same-date tie-break:** if another handoff shares `2026-06-24`, target this file explicitly: `/reset-session docs/superpowers/handoffs/2026-06-24-prepared-docs-workitem-preview-execution-complete.md`.
