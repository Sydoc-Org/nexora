# Handoff — Prepared Documents ⇄ Workitem Preview (PLAN ONLY, ready to execute)

**Date:** 2026-06-23 (evening/late) · **Branch:** `feature/2.5.63` · **Planning worktree:** `plan/prepared-docs-workitem-preview` · **128 commits ahead of origin** · **commit-only (remote)**
**Prior handoff:** `docs/superpowers/handoffs/2026-06-23-prepared-documents-register-execution-complete.md` (the shipped register this feature builds on)
**Spec:** `docs/superpowers/specs/2026-06-23-prepared-docs-workitem-preview-design.md` (`173d44e`)
**Plan:** `docs/superpowers/plans/2026-06-23-prepared-docs-workitem-preview.md` (`563998a`) — **on disk in the worktree**

## TL;DR

- **Planning session only — NO product code shipped.** Brainstormed → spec → multi-agent `/write-plan` produced a **4-phase plan** (1500 lines) to cross-link the MS02 Prepared Documents register and the Workitems detail view.
- **Spec + plan both committed**, the spec on `feature/2.5.63` (`173d44e`) and the plan on the **worktree branch `plan/prepared-docs-workitem-preview`** (`563998a`). Resume with **`/execute-plan`** — it runs in this worktree and merges back at the end.
- **Fable 5 was unavailable** → the 7 planning agents (explore ×3 → dual drafts → red-team → merge) ran on **Opus**. A dedicated verifier re-checked **every** file/symbol/snippet anchor against the live repo → **all anchors verified**; it surfaced one design gap (now pinned in the plan's Gotchas).
- **Not pushed** (remote / commit-only).

## What the plan builds (for the next session)

| Phase | What | Key files |
|---|---|---|
| **P1** | Extract the Workitems detail panel into a shared client-side partial `NexoraWorkitemDetail.render(wid, container, {readOnly, perms})` + container-scoped lightbox. Refactor the Workitems row-expand to consume it (behaviour unchanged). **Riskiest — do first, regression-tested.** | new `templates/js/_workitem_detail_panel_js.html`; `templates/js/_workitems_overview_js.html` |
| **P2** | Read-only **preview modal** on the register's Octo-Status cell, mirroring the full detail panel (images, source highlighting, fields, audit, tags, comments) + an "Open in Workitems" link. | `templates/prepared_documents.html`, `templates/js/_prepared_documents_js.html`, `nx_lib/views/workitems.py` (route passes `details_*` perms) |
| **P3** | Reverse **"In register" chip** on the Workitems detail panel → register filtered by `?pid`; new `pids_in_register()` + `resolve_ms02_wids_to_pids()` + a `_stamp_in_register()` enrichment in `_get_workitems_data`. | `nx_lib/prepared_documents.py`, `nx_lib/workitem_sources.py`, `nx_lib/views/workitems.py` |
| **P4** | Docs (CHANGELOG, CLAUDE.md) + i18n (de/fr/it) + final verification. | `CHANGELOG.md`, `CLAUDE.md`, `translations/` |

Read-only, **MS02-only**, **no new permission**, **no new migration** (reuses `workitems.import.preparedaudit` + `workitems.details.view.*`; `dbo.PreparedDocuments` already exists).

## This session's commits

```
173d44e  docs(spec): register<->workitem detail cross-linking design   (on feature/2.5.63)
563998a  docs(plans): add prepared-docs-workitem-preview implementation plan   (on plan/ worktree branch)
```
Plus the handoff commit this step creates.

## Next steps (ordered)

1. **`/execute-plan`** — builds the 4 phases TDD-per-task **in this worktree** (`plan/prepared-docs-workitem-preview`); on completion `--merge-worktree` merges it into `feature/2.5.63` and removes the worktree. **P1** (shared-panel extraction) is fully startable now and is the riskiest — verify the Workitems row-expand in the browser after each P1 task (the integration suite asserts route status/markers, NOT the JS DOM, so a closure/scope break can pass tests yet break runtime).
2. **Owner: push** `feature/2.5.63` (128 commits unpushed) once this + the register land and are reviewed. Not done here (remote / commit-only).
3. **Live-verify on INT** (not dev): the full *image* preview needs the Octo media host (PROD-reachable, blank on dev). Fields/audit/tags/comments render everywhere.

## Gotchas & notes (READ)

- **One design gap is pinned in the plan's Gotchas (line ~1490).** The Workitems page populates a **module-scope `let mentionableUsers`** that is never mirrored to `window`, but the refactored row-expand reads `window.mentionableUsers` — so the assignee/@-mention list would render EMPTY after P1 unless the executor assigns `window.mentionableUsers = <populated list>` in `fetchMentionableUsers` (or declares the page var on `window`). The integration suite won't catch this (it doesn't assert the JS DOM) — **browser-verify the assignee dropdown after P1.**
- **Pre-existing red tests (NOT this feature, will gate the push):** `tests/unit/test_octo.py::test_get_extensions_urls_fields_{single_doc,batch_doc_iterates_children,non_batch_container_recurses}` — octo media-host double-`https://` bug, predates this work. Owner must fix octo OR update those 3 stale tests before pushing.
- **Fable outage:** planning agents ran on Opus (Fable 5 unavailable today, same as the register plan). Quality unaffected.
- **Anchor caveat:** the plan cites line numbers as navigation only; `_workitems_overview_js.html` is large + recently edited, so **re-grep the verbatim snippet before each edit** (the plan's edit anchors are the snippets, not the line numbers).
- **The `.claudeignore` working-tree edit** (`!.superpowers/sdd/`, a subagent side-effect from the register execution) is in the MAIN checkout (`C:\dev\nexora`), not this worktree — still uncommitted, still the owner's call (`git checkout -- .claudeignore` or keep).

## Untracked / left for owner

- In the MAIN checkout (`C:\dev\nexora`, branch `feature/2.5.63`): the uncommitted ` M .claudeignore` side-effect + the strays `scripts/new-process.py` and `sql/_migrations/NexoraDB/0032_ignore_pdbs_deletion_marker_activities.sql` — none are this feature's; left alone.
- `var/handoff-pending` points at this file (gitignored — not committed).

## How to verify

```powershell
git -C C:\dev\nexora worktree list        # plan-prepared-docs-workitem-preview present, branch plan/prepared-docs-workitem-preview
# in the worktree:
git log --oneline -2                       # 563998a plan, 173d44e spec
Test-Path docs/superpowers/plans/2026-06-23-prepared-docs-workitem-preview.md   # True
Select-String docs/superpowers/plans/2026-06-23-prepared-docs-workitem-preview.md -Pattern 'NexoraWorkitemDetail' -Quiet   # True
```
**Nothing is built yet** — this session only wrote + committed the spec + plan. The feature is entirely ahead in `/execute-plan`.

## Resuming in a fresh session

`/reset-session` (the flag in `var/handoff-pending` points here). To build the feature, use **`/execute-plan`** — it resumes in the worktree `.claude/worktrees/plan-prepared-docs-workitem-preview` (branch `plan/prepared-docs-workitem-preview`) and merges back on completion.

**Same-date tie-break:** many handoffs share `2026-06-23`. If `/reset-session` auto-picks the wrong one, target this file explicitly: `/reset-session docs/superpowers/handoffs/2026-06-23-prepared-docs-workitem-preview-plan.md`.
