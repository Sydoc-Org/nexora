# Handoff — permission structure (#238) spec approved + plan written, ready for /execute-plan

**Date:** 2026-09-01 · **Branch:** `plan/permission-structure-rename-grid` in worktree
`.claude/worktrees/plan-permission-structure-rename-grid` (cut from `v3.2.4.1` @ `630cb99d`) ·
**2 commits ahead of `v3.2.4.1`, nothing pushed** · commit-only (remote session) · plan-only, nothing
executed yet.

**Prior handoffs:** the pending flag pointed at
[`.claude/worktrees/plan-tenant-kernel-ms02-pilot/docs/superpowers/handoffs/2026-08-31-tenant-kernel-ms02-pilot-plan.md`](../../../.claude/worktrees/plan-tenant-kernel-ms02-pilot/docs/superpowers/handoffs/2026-08-31-tenant-kernel-ms02-pilot-plan.md)
(**not consumed** — this session did unrelated #238 work; that tenant-kernel plan is still queued in
its own worktree, which also runs a dev server on `:8002`). Newest in this tree:
[`2026-08-31-beautify-phase-0-1-plan.md`](2026-08-31-beautify-phase-0-1-plan.md).

## This session's commits

| Commit | Branch | What |
|---|---|---|
| `630cb99d` | `v3.2.4.1` (main checkout) | `docs(specs)`: the approved design, `docs/superpowers/specs/2026-09-01-permission-structure-design.md` |
| `861fa66c` | `plan/permission-structure-rename-grid` | `docs(plans)`: the implementation plan + spec renumbered to migrations 0086–0088 |
| this file | `plan/permission-structure-rename-grid` | handoff |

## TL;DR

- Issue #238 ("Permission Structure", title-only) was read against the live INT catalogue: 144 codes,
  10 profiles, 855 profile rows of which 446 are semantically empty DENYs, three duplicated
  per-process families, ten per-profile assign meta-codes, 22 orphan codes, no naming convention,
  a 144-row per-profile drawer as the editor.
- Owner approved (AskUserQuestion, 2026-09-01): **full rename** to `<area>.<object>.<action>[.<scope>]`,
  **grid editor** permissions × profiles, **`generali.*` → `tenant.generali.*` now**, **one release
  with phased commits**, rank rule **`target.Rank <= actor.Rank`**, **accept the deploy blip**.
- **Deliverables:** spec (`630cb99d`) with Appendix A mapping all 144 → 112 codes, and the plan
  `docs/superpowers/plans/2026-09-01-permission-structure-rename-grid.md` (`861fa66c`): 4 phases,
  15 tasks, every anchor Grep-verified, migrations **0086/0087/0088**.
- Issue #238 is labelled `inprogress`; `noconcreteplan` removed. Not commented on yet.

## What shipped

| File | Commit | Notes |
|---|---|---|
| `docs/superpowers/specs/2026-09-01-permission-structure-design.md` | `630cb99d`, renumbered in `861fa66c` | design authority; Appendix A = the code mapping the migration and sweep copy |
| `docs/superpowers/plans/2026-09-01-permission-structure-rename-grid.md` | `861fa66c` | 15 tasks; Phase 1 cleanup+rank, Phase 2 process scope, Phase 3 rename, Phase 4 grid |
| `var/screenshots/238_*.png` (gitignored) | — | before-state screenshots of access control, profile drawer, matrix, user detail |

## Next steps

1. **Resume in the worktree**, not the main checkout: `.claude/worktrees/plan-permission-structure-rename-grid`
   on `plan/permission-structure-rename-grid`. First copy the secrets in (gitignored, absent in
   worktrees): `cp ../../../env/INT.env ../../../env/TEST.env env/`; prepend `C:\dev\nexora\.venv\Scripts`
   to `PATH`.
2. `/execute-plan` on `docs/superpowers/plans/2026-09-01-permission-structure-rename-grid.md`, start
   at **Task 1** (test schema + seed). Run `python scripts/db-migrate.py --env INT --dry-run` before
   creating 0086 — the tenant-kernel worktree owns 0083–0085 and they are applied on INT.
3. After Phase 4: Playwright screenshots of the grid → `SendUserFile` (remote owner), then the plan's
   Task 15 Step 8 issue comment. Owner deploys off-hours (deploy blip, spec D6) and closes #238.
4. Merge the worktree back into `v3.2.4.1` when the plan is executed (`/execute-plan` does this with
   `--merge-worktree`); the spec commit `630cb99d` is already on `v3.2.4.1`.

## Gotchas & notes

- **Main checkout working tree is dirty with peer noise, deliberately uncommitted:** 13 modified
  `sql/NexoraDB/Tables/*.sql` dumps + 4 untracked `dbo.Tenant*.sql` dumps — INT drift from the
  tenant-kernel worktree's migrations 0083–0085. Never bundle them. Both commits this session used
  `SQL_SYNC_SKIP=1` for that reason; the plan's commits will need it too until that worktree merges.
- **Dev server on `:8000` = main checkout** (restarted this session because it served stale code:
  `/api/admin/users` 404 + `NX.toast` TypeError were staleness, not bugs). Worktree code needs its own
  instance: `nx -u --no-conflict`. `:8002` belongs to the tenant-kernel worktree — leave it.
- **Hidden code stores the rename must hit** (all in the plan): `dbo.ReportingSources.Permission`,
  `nx_lib/reporting/sources.py`, `nx_lib/whats_new.py` (`perm` + the `admin_permission_matrix`
  `endpoint` → must become `admin_permissions` or What's New 500s), `sql/test/seed.sql`.
- **`/api/admin/*` writes don't clear the user cache** (`_invalidate_user_cache` checks the `/admin`
  prefix only) — latent today; the new grants API clears it explicitly (plan Task 12).
- **Process codes carry no client in the key:** `ProcessName` is already `<client>.<name>`;
  `_permission_reduction()` takes its last two segments → `process.<client>.<name>.view`.
- **INT counts measured 2026-09-01** for the plan's proofs: after 0086 → 122 codes / 340 profile
  rows; after 0087 → 111 / 289; after 0088 → 112 codes. Data-driven migrations tolerate PROD drift.
- `NX.api`/`NX.apiSafe` prefix leading-slash URLs themselves — pass `'/api/…'`, never
  `${API_PREFIX}api/…` (PROD would get `/nexora/nexora/…`).
- Kundenmagazin survives only as an external link in a mail template; `kundenmagazin.*` codes are
  orphans and go in 0086. `tenant.ms02.*` stays (tenant-kernel pre-seed).

## Untracked / left for owner

- The 17 dirty/untracked `sql/NexoraDB/**` dumps in the **main** checkout — peer session's.
- `var/handoff-pending` in the main checkout now points here (it previously pointed at the
  unconsumed tenant-kernel handoff listed above — that plan is still queued).
- No GitHub comment on #238 yet; the spec + plan are the answer to "ideas?" — post the plan's Phase
  table as a comment when execution starts, if wanted.

## How to verify

```
git -C .claude/worktrees/plan-permission-structure-rename-grid log --oneline -3   # 861fa66c, 630cb99d, e97ae2d6
git -C .claude/worktrees/plan-permission-structure-rename-grid status --short    # clean
ls .claude/worktrees/plan-permission-structure-rename-grid/docs/superpowers/plans/2026-09-01-permission-structure-rename-grid.md
gh issue view 238 --json labels -q '[.labels[].name]'   # inprogress, enhancement, documentation
```

Nothing is red. No test suite was run this session (docs-only).

## Resuming in a fresh session

`/reset-session .claude/worktrees/plan-permission-structure-rename-grid/docs/superpowers/handoffs/2026-09-01-permission-structure-rename-grid-plan.md`
(pass the path — the file lives in the worktree, not the main tree), then read the plan and spec and
`/execute-plan` from the worktree. No other 2026-09-01 handoff exists in either tree.
