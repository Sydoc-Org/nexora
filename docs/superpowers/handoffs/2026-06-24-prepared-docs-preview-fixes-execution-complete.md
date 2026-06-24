# Handoff — Prepared Documents Preview & Register Polish (EXECUTED — ready to merge)

**Date:** 2026-06-24 · **Branch:** `feature/2.5.63` · **156 commits ahead of origin** · **commit-only (remote)** · no plan worktree
**Prior handoff:** `docs/superpowers/handoffs/2026-06-24-prepared-docs-preview-fixes-plan.md` (the PLAN-only handoff this executes)
**Plan executed:** `docs/superpowers/plans/2026-06-24-prepared-docs-preview-fixes.md`
**SDD ledger:** `.superpowers/sdd/progress.md` (full per-task review record; gitignored scratch)

## TL;DR

- **All 4 plan tasks executed, reviewed, and committed.** 6 commits on `feature/2.5.63`
  (`69b2085..e493d25`). Nothing left to implement.
- Fixed the three reported MS02 "Prepared Documents" defects: (1) ragged register columns —
  centered headers now match centered body cells; (2) the "Prepared documents" toolbar link now
  shows **only when an MS02 prepared-docs target process is selected**; (3) the preview-modal
  timeline now reflects the document's live Octo stage instead of rendering all-grey.
- **Final whole-feature review (opus): READY TO MERGE.** No Critical, no Important. All 6 binding
  plan constraints (D1–D6) independently verified. The 4 carried Minor findings are all
  defer-to-owner or non-issues — none merge-blocking.
- **Owner still owes:** `git push` + PR→main (remote/commit-only — never done here), and the live
  browser verification that dev/CI cannot do (Owner actions O1/O3 — see below).

## This session's commits (oldest → newest)

```
3273159  fix(prepared-docs): center register check-column headers           (Bug 1)
e7bb3ef  fix(workitems): gate prepared-docs link to MS02 target processes   (Bug 2; amended once for test hygiene)
4a1f11b  feat(workitems): add never-raising per-wid Octo stage resolver     (Bug 3.1)
1297a76  feat(prepared-docs): carry Octo status/stage to the preview button (Bug 3.2)
edbdcb7  fix(prepared-docs): light preview timeline from the wid's stage    (Bug 3.3)
e493d25  docs(prepared-docs): changelog + CLAUDE.md for preview/register polish (docs)
```
(The handoff commit for THIS doc lands on top of `e493d25`.)

## What shipped (9 files, +256 / −17)

| Bug | Fix | Files | Commit |
|---|---|---|---|
| **1** Column alignment | Swapped the 3 centered HEADER `<th>` from Tailwind `text-center` → shared `.nx-table .align-center` helper (specificity (0,2,0) beats the (0,1,2) `.nx-table thead th` rule). Body cells untouched. | `templates/prepared_documents.html`, `tests/integration/test_workitems_routes.py` | `3273159` |
| **2** Button gating | Compute `prepared_docs_process_match` (perm + `ms02_active` + `process_name in _ms02_target_processes()`) in `workitems_overview()`; tightened the Jinja gate to a single bool. Rewrote the now-inverted link test + added hidden-on-all sibling. | `nx_lib/views/workitems.py`, `templates/workitems_overview.html`, `tests/integration/test_workitems_routes.py` | `e7bb3ef` |
| **3** Preview timeline | New never-raising `resolve_octo_wid_stage(engine, wid)` in `nx_lib/workitem_sources.py` (CASE-over-`t_ActivityInstances`-join, ROW_NUMBER latest slice — **byte-identical** to the list query's CASE). `prepared_documents()` resolves it via `CLIENTS["default"].runtime_engine`, emits `data-status`/`data-current-stage` on the Preview button; `openPreview` forwards them into `render`'s existing `opts.status`/`opts.currentStage` fallback. **Shared panel partial NOT edited.** | `nx_lib/workitem_sources.py`, `nx_lib/views/workitems.py`, `templates/prepared_documents.html`, `templates/js/_prepared_documents_js.html`, `tests/unit/test_workitem_sources.py`, `tests/integration/test_workitems_routes.py` | `4a1f11b`, `1297a76`, `edbdcb7` |
| **docs** | CHANGELOG (`### Fixed` bullets + corrected the stale "decoupled from the process filter" line) + CLAUDE.md prepared-docs paragraph. | `CHANGELOG.md`, `CLAUDE.md` | `e493d25` |

**No migration, no new permission, no new i18n strings** (verified: whole-feature file list is exactly
these 9 files — no `messages.pot`, no `sql/_migrations/**`). No pybabel cycle needed.

## How it was executed (subagent-driven development)

Fresh implementer subagent per task → task review (spec + quality) → fix loop → next; then one
opus whole-feature review. Models: sonnet implementers/reviewers, opus for the Bug-3 review and the
final review. Notable in-flight finding: **Bug-2's brief session-seed recipe was wrong** — a
`_reload_user_permissions` before_request hook (`nx_lib/hooks.py`) overwrites `session["permissions"]`
from the DB each request, so the test had to monkeypatch `nx_lib.hooks.load_permissions_for_user`
instead of seeding via `session_transaction()`. Production gate logic was unaffected; the dead seed
was removed in the `e7bb3ef` amend. Full review trail in `.superpowers/sdd/progress.md`.

## Next steps (ordered)

1. **Owner: `git push`** `feature/2.5.63` and **open the PR → main** (remote/commit-only — the agent
   never pushes).
2. **Owner: live browser-verify** the UI on INT/PROD after deploy — see O1/O3 below. This could NOT
   be done locally (reason in Gotchas).
3. Optional post-merge polish (non-blocking Minors): add 2 degrade-path unit tests
   (`resolve_octo_wid_stage` empty-fetch + non-int wid); consider a batched status query if the
   register page's per-PID Octo round-trip (N+1, ≤40/page) shows latency on the Defender-scanned
   PROD path.

## Owner actions baked into the plan (not the agent's job)

- **O1 — live timeline correctness.** Dev/CI has no reachable Octo, so `resolve_octo_wid_stage`
  returns `{None, None}` locally → timeline stays grey. The data plumbing is verified by tests + the
  shared-render fallback; the owner confirms the right step lights for a real PDBS document's stage on
  INT/PROD.
- **O3 — Bug-1 column-width scope.** The fix addresses header **text alignment**. If a real
  (MS02-populated) register still shows ragged **column widths**, the owner decides whether to add
  `table-fixed`/`<colgroup>` — deliberately NOT pinned speculatively (plan D4).

## Gotchas & notes (READ)

- **Browser verification was IMPOSSIBLE locally — by design, not skipped lazily.**
  `prepared_documents()` raises `PermissionDenied` → 403 whenever `ms02_active` is False
  (`nx_lib/views/workitems.py:1900-1901`), and dev/CI has **no MS02 Postgres engine**
  (`"ms02" not in CLIENTS` / `engine_ms02_docfields_pg is None`). So the register page, its headers
  (Bug 1), the gated toolbar button (Bug 2 needs `ms02_active` True), and the preview timeline (Bug 3
  needs Octo data) are ALL unreachable in a browser here. No screenshot was fabricated. The rendered
  markup IS verified by route-render integration tests that gate-and-mock `ms02_active=True` (all
  green). Owner does the real browser confirmation (O1/O3).
- **D5 intentional duplication.** `resolve_octo_wid_stage`'s two CASE blocks are deliberately
  byte-identical to the list query's `SqlServerSource` WorkitemCTE CASE (so the preview can never
  disagree with the list). The final reviewer confirmed character-level parity and did NOT flag the
  duplication. Do not "DRY" it.
- **Engine handle is make-or-break.** The route passes `CLIENTS["default"].runtime_engine`
  (== `engine_octo_db`), NOT `engine_ms02_docfields_pg` (the PG docfields engine, wrong id-space →
  permanently grey timeline). Verified.
- **`SQL_SYNC_SKIP=1`** was prefixed on every commit (known INT `SchemaMigrations` CRLF drift). Never
  `--no-verify`. The `ruff-format`/line-ending pre-commit hooks fired and self-corrected on first
  attempts; all commits landed clean.
- **Pre-existing red tests still loom (NOT this feature):**
  `tests/unit/test_octo.py::test_get_extensions_urls_fields_{single_doc,batch_doc_iterates_children,non_batch_container_recurses}`
  — the Octo media-host double-scheme bug. They gate the pre-push e2e run; owner fixes/updates them
  before pushing.

## Untracked / left for owner (pre-existing strays — NOT staged, NOT this session)

- `.claude/helpers/notify-toast.ps1` (M), `.claudeignore` (M) — modified, not staged. (`.claudeignore`
  carries an earlier `!.superpowers/sdd/` negation that lets AI tools read the SDD scratch ledger.)
- `scripts/new-process.py` (untracked).
- `sql/_migrations/NexoraDB/0032_ignore_pdbs_deletion_marker_activities.sql` (untracked) — a separate
  PDBS migration, **not** part of these fixes; needs its **own** commit + INT apply if wanted.
- **Leftover folder** `.claude/worktrees/plan-prepared-docs-workitem-preview` — a gitignored copy
  (NOT a registered git worktree; `git worktree list` doesn't show it). All work happened at
  `C:\dev\nexora`. Harmless; owner may `rm -rf` it.

## How to verify

```powershell
# From C:\dev\nexora (feature/2.5.63):
git log --oneline 69b2085..HEAD              # the 6 feature commits + this handoff
git status --porcelain                       # only the 4 strays above
git diff --name-only 69b2085..e493d25        # the 9 feature files; no pot / no sql/_migrations
# Feature test slice (was green at handoff: 25 passed, 0 failed):
python -m pytest tests/integration/test_workitems_routes.py -k "prepared or workitems_overview" tests/unit/test_workitem_sources.py -x
# (test_octo.py x3 are pre-existing reds unrelated to this feature — see Gotchas.)
```

## Resuming in a fresh session

This feature is **done and ready to merge** — the main open items are owner-only (push + PR + live
verify). If resuming: `/reset-session` (the `var/handoff-pending` flag points here).

**Same-date tie-break:** `2026-06-24` also has `…-prepared-docs-preview-fixes-plan.md` (PLAN-only,
now superseded — a banner at its top points here) and `…-prepared-docs-workitem-preview-execution-complete.md`
(the predecessor feature, already merged). To target this handoff explicitly:
`/reset-session docs/superpowers/handoffs/2026-06-24-prepared-docs-preview-fixes-execution-complete.md`.
