# Handoff — PR #119 shipped to PROD + doc-field cross-source bleed fix

**Date:** 2026-07-14 (afternoon) · **Branch:** `feature/2.5.64` (main clone `C:\dev\nexora`) ·
**commit-only (remote session — owner pushes)**
**Prior handoff:** `2026-07-14-reporting-breakdown-by-process-execution-complete.md` (parallel
session, same afternoon — its worktree was merged into this branch as `5cfebe8`)

## TL;DR

- **PR #119 (`feature/2.5.64` → `main`, 48 commits) was opened, babysat, merged by the owner, and
  the PROD deploy went green** — migrations `0035` + `0036` applied to PROD NexoraDB before the
  app-pool stop (`applied=2`, GeneraliDB up-to-date). Drill-through, dashboard fixes, sensitive
  doc-fields, and the CI speedups are live on `main`/PROD.
- **Owner's PROD smoke test found a real bug:** searching the Validation User doc-field returned
  every MS02 workitem. Root-caused and fixed this session as `837b875` — a doc-field with no
  `SearchConfig` mapping for a source left that source's allow-set `None` (= unconstrained) instead
  of `set()` (= zero rows). Both pre-resolution legs fixed, regression-tested, verified against the
  real INT MS02 DB (2157 rows → 0).
- **This fix is committed but NOT on `main` yet** — owner said "I'll put that on main later".
- A **parallel session** executed the reporting Process-breakdown plan on this same branch during
  this session (commits `e2f027d`…`f476959` + merge `5cfebe8`); see its own handoff for that work.

## This session's commits

Only one code commit belongs to this session (the rest interleaved from the parallel
process-breakdown session):

- `837b875` fix(workitems): zero unmapped source in cross-source doc-field search

(Plus this handoff commit.)

## What shipped

| Area | Files | Commit |
|---|---|---|
| Doc-field bleed fix (both legs) | `nx_lib/views/workitems.py` (default leg ~line 500, ms02 leg ~line 615) | `837b875` |
| Regression test | `tests/integration/test_workitems_routes.py::test_get_workitems_data_unmapped_docfield_zeroes_both_sources` | `837b875` |
| Changelog | `CHANGELOG.md` (`[Unreleased]` → Fixed) | `837b875` |

**The bug, precisely:** `_get_workitems_data` pre-resolves doc-field search into per-source
allow-sets with a three-way contract (`None` = no constraint, `set()` = zero rows, `{ids}` =
allow-list). Both legs did `continue` when the searched field had **zero SearchConfig rows for
their source**, leaving the allow-set `None` — so that source ran unconstrained. Validation User is
mapped only for a `'default'` process, so the MS02/Postgres leg ignored the filter and returned all
PDBS workitems; an ms02-only field (e.g. `pid`) mirror-bled all SQL Server workitems the same way.
Fix: zero mapping rows → `set()`. Broken-config rows and DB errors deliberately keep the old
tolerant no-constraint behavior so a config typo can't blank the whole page.

## Not done / decisions

- **Owner declined a migration for the `col_validationuser` mapping** ("I'll map later") — all
  `SearchConfig.col_validationuser` values stay NULL on PROD; the owner hand-added rows on PROD
  during testing and **deleted them again** after seeing the bleed. INT still carries the hand-set
  test mapping `compass.01_Invoice_SAP` → `ValUserA` (data-only drift, harmless; verified
  `dbo.Compass_Invoice` has `ValUserA/B/C` columns with data).
- ⚠️ **Migration number 0037 is now TAKEN** by the parallel session's
  `0037_reporting_processname_label.sql`. If/when the owner wants the validationuser mapping as a
  migration, it's **0038**.

## Next steps (ordered)

1. **Owner: push `feature/2.5.64` and get `837b875` (+ the Process-breakdown work) onto `main`**
   — owner explicitly said they'll do this themselves. Note the branch carries BOTH sessions' work;
   review the whole diff since `main`.
2. **After the fix deploys to PROD:** owner can re-add the `col_validationuser` mapping row(s) on
   PROD (or ask for migration **0038**) and re-test — expected behavior: compass matches only, zero
   MS02 rows.
3. **Carried over:** pdbsUser PROD spot-check (assign profile to one user in admin UI); drill-through
   isolated live browser pass (see prior handoffs).
4. **Confluence docs sync still red** on every `main` push — known cred/seat issue
   (`project_confluence_docs_sync` memory), not caused by any of this.

## Gotchas & notes

- **Parallel-session interleaving:** while this session babysat PR #119 and fixed the bleed, a
  second session executed the Process-breakdown plan against a worktree and merged it into this
  branch (`5cfebe8`). It also had a wrong-checkout incident that briefly committed to this clone
  (`b33f8eb`, reverted as `a6cb158`, cherry-picked properly as `f476959`) — fully documented in its
  own handoff. Don't be surprised by the revert pair in `git log`.
- **INT verification probe details** (for reproducing): the PG source stores process names
  **without** the client prefix (`05_PDBS`, not `sydoc.05_PDBS` — the route maps this), and
  `WorkitemFilter` needs real `client_names` (`['sydoc','system']`) and the
  `get_activity_instances_to_ignore()` CSV — empty lists render invalid `IN ()` SQL.
- **Untracked junk at repo root:** `package.json` + `package-lock.json` (a stray `headroom-ai`
  dependency, not ours — ruflo-style junk). Deliberately left untracked; safe to delete.
- One transient test ERROR (`test_prepared_documents_clear_400_without_ms02`) during a full-file
  run — passed in isolation and on re-run (67/67); known INT-DB-flake shape, not related.

## Untracked / left for owner

- `package.json` / `package-lock.json` at repo root (junk, see above) — not committed.
- INT `SearchConfig` hand-set compass→`ValUserA` mapping row (data, not schema — sync-from-db
  doesn't track it; harmless).

## How to verify (this handoff's claims)

```powershell
git log --oneline -6            # 5cfebe8, 597d642, 837b875, f476959, a6cb158, b33f8eb
gh pr view 119 --json state,mergeStateStatus   # MERGED
gh run list --branch main --limit 2            # Deploy: success; Confluence sync: failure (known)

# The fix's tests:
C:\dev\nexora\.venv\Scripts\python -m pytest tests/integration/test_workitems_routes.py -q  # 67 passed
C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_workitem_sources.py -q         # 55 passed

# Live INT probe (bleed vs fix, real MS02 Postgres DB):
$env:ENVIRONMENT='INT'; python -c "
from nx_lib import create_app
from nx_lib.views.workitems import get_activity_instances_to_ignore
from nx_lib.workitem_sources import WorkitemFilter, fetch_merged_page
app = create_app()
with app.app_context():
    aii = get_activity_instances_to_ignore()
    for label, ids in [('None', None), ('set()', set())]:
        filt = WorkitemFilter(process_names=['05_PDBS'], client_names=['sydoc','system'],
                              activity_ignore_csv=aii, ms02_docfield_ids=ids)
        rows, total, d = fetch_merged_page(filt, 0, 5)
        print(label, total)   # None -> ~2157, set() -> 0
"
```

## Resuming in a fresh session

`/reset-session` — `var/handoff-pending` points here (several handoffs share today's date; use
`/reset-session docs/superpowers/handoffs/2026-07-14-pr119-merge-docfield-bleed-fix.md` if the
picker grabs another). No implementation work is queued: everything committed, tests green. The
next actions are owner-owned (push branch → next PR to `main`; then optional migration 0038 for the
validationuser mapping).
