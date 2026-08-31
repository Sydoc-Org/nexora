# Handoff — tenant platform spec + kernel plan written, execution gated on beautify

**Date:** 2026-08-31 · **Branch:** `plan/tenant-kernel-ms02-pilot` (worktree
`.claude/worktrees/plan-tenant-kernel-ms02-pilot`, cut from `v3.2.4.1` at `1af51271`) ·
**commit-only** (owner pushes) · plan-only session, nothing executed.

**This session's commits (oldest→newest):**

- `1af51271` — `docs(specs): add tenant-platform umbrella design spec` (**on `v3.2.4.1` in the
  main checkout**, before the worktree was cut — already in both histories)
- `4ac51678` — `docs(plans): add tenant-kernel-ms02-pilot implementation plan` (**worktree branch
  only**)
- the handoff commit (this file + a forward-pointer banner on the same-date beautify handoff)

**Prior handoff:** [`2026-08-31-beautify-phase-0-1-plan.md`](2026-08-31-beautify-phase-0-1-plan.md)
— its campaign is **already executing in a peer session on its own branch**; do not consume or
re-run it from here.

## TL;DR

- Owner-approved direction: **tenant becomes a first-class concept** — data-first tenants (the
  Generali shape; Octo is an optional attachment), a descriptor "data box" driving generated
  pages, Eddard writing only drafts. Spec: `docs/superpowers/specs/2026-08-31-tenant-platform-design.md`
  (T1–T9 locked, five sub-projects sequenced).
- **Sub-project 1 is fully planned:** `docs/superpowers/plans/2026-08-31-tenant-kernel-ms02-pilot.md`
  — `dbo.Tenants` + box tables (migrations `0083`–`0085`), `nx_lib/tenant/` registry + dialect
  query builders, parametrized `/t/<code>/*` routes, per-tenant permissions/nav,
  T-SQL-only ReportingSources sync (PG deferred, K6), MS02 seeded from the mapping tables, and a
  parity-gated `ServesWorkitems` cutover.
- **Execution is GATED: do not start until the beautify campaign (phases 0+1) merges** — the
  kernel patterns on its Task 14 `register_crud` factory and several plan anchors move in its
  Task 13/16 splits. Re-grep every anchor against the post-beautify base.
- Owner decisions honored: full-tenant model, MS02 as pilot of the generated system, Generali
  migrates later (sub-project 4, after #220), both data paths, Eddard = drafts only.

## What shipped

| Commit | What |
|---|---|
| `1af51271` | umbrella spec (docs only, on `v3.2.4.1` + this branch) |
| `4ac51678` | sub-project 1 implementation plan (docs only, this branch) |
| this file | handoff + banner on the same-date beautify handoff |

## Next steps

1. **Wait for the beautify campaign to merge** (peer session, own branch). Nothing here executes
   before that.
2. Then `/execute-plan` on `docs/superpowers/plans/2026-08-31-tenant-kernel-ms02-pilot.md`,
   starting at Task 1, in a **fresh worktree cut from the post-beautify base** (the plan's Context
   section has the command). This planning worktree is NOT the execution vessel — the plan is
   docs-only; merge `plan/tenant-kernel-ms02-pilot` into the release branch (owner or next
   session) and delete it, then cut fresh.
3. Owner, separately (also in the plan's Owner actions): green-light or park **PG reporting
   support** (K6 — MS02 numbers stay on tenant pages until then); confirm the **MS02 PG database**
   for tenant list reads (Task 8 probes); give the explicit **cutover go** after Task 9's parity
   screenshots.

## Gotchas & notes

- **The plan branch holds the plan.** The main checkout (`v3.2.4.1`) has the spec but NOT the plan
  file until `plan/tenant-kernel-ms02-pilot` merges. The `var/handoff-pending` flag therefore
  points at this handoff **via the worktree-relative path** — from `C:\dev\nexora` the file is
  `.claude/worktrees/plan-tenant-kernel-ms02-pilot/docs/superpowers/handoffs/2026-08-31-tenant-kernel-ms02-pilot-plan.md`.
- **Same-date tie-break:** `2026-08-31-beautify-phase-0-1-plan.md` shares today's date; it carries
  a forward-pointer banner to this file (committed on this branch only).
- **Peer migration race is live:** two `0079_*.sql` files already coexist and a peer session is
  landing Kundenmagazin tables — the plan's every migration task re-checks numbering with
  `db-migrate.py --env INT --dry-run` before claiming `0083`–`0085`.
- Main-checkout working tree still carries the peer noise the beautify handoff described
  (`M CLAUDE.md`, untracked `dbo.KundenmagazinIssues*.sql` dumps) — not ours, leave it.
- Memory `project_tenant_platform_direction.md` records the direction for future sessions.

## How to verify

```
git -C C:\dev\nexora\.claude\worktrees\plan-tenant-kernel-ms02-pilot log --oneline -3
ls C:\dev\nexora\.claude\worktrees\plan-tenant-kernel-ms02-pilot\docs\superpowers\plans\2026-08-31-tenant-kernel-ms02-pilot.md
git -C C:\dev\nexora log --oneline -2    # 1af51271 spec on v3.2.4.1
```

## Resuming in a fresh session

`/reset-session .claude/worktrees/plan-tenant-kernel-ms02-pilot/docs/superpowers/handoffs/2026-08-31-tenant-kernel-ms02-pilot-plan.md`
(`/reset-session <path>` targets a specific file — needed today because two 2026-08-31 handoffs
exist), then read the spec + plan and check whether beautify has merged (`git log --oneline -10`
on the release branch). If merged: merge/delete this plan worktree+branch, cut the execution
worktree, `/execute-plan`. If not: wait or pick up other work.
