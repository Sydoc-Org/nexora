# Handoff — Prepared-docs import: button fix + 5-column Excel + merge/standalone (PLAN ONLY, not executed)

**Date:** 2026-06-23 (midday) · **Branch:** `feature/2.5.63` · **95 commits ahead of origin** · **commit-only (remote)**
**Prior handoff:** `docs/superpowers/handoffs/2026-06-23-ms02-docfield-columnar-pdf-media.md` (same-date; the columnar rewrite + `0030` it shipped as `1fa8437` is what this plan stacks on)
**Plan file (in the worktree):** `.claude/worktrees/plan-prepared-import-button-extra-fields/docs/superpowers/plans/2026-06-23-prepared-import-button-extra-fields.md`
**Durable context in auto-memory:** `project_ms02_multisource_workitems`, `reference_ms02_media_host_dns`, `feedback_caveman_speak`, `project_int_migration_crlf_drift`, `project_flask_template_cache`, `reference_dev_server_global_python`.

## TL;DR

- **Planning session only — NO product code shipped.** A `/write-plan` multi-agent run produced an 8-task / 6-phase implementation plan for three coupled fixes to the MS02 "prepared documents" Excel import on the workitems page.
- **The plan lives in an OPEN worktree** (`.claude/worktrees/plan-prepared-import-button-extra-fields`, branch `plan/prepared-import-button-extra-fields`, off `feature/2.5.63` HEAD `1fa8437`), committed there as **`7c5b5d4`**. The worktree is the **execution vessel** — it was deliberately **NOT merged and NOT deleted** (this is the `/write-plan` path; no `--merge-worktree`). Resume with `/execute-plan`.
- **Fable 5 was unavailable**, so the 7 planning agents (explore ×3 → minimal/structural drafts ×2 → red-team → merge) ran on **Sonnet**. Red-team surfaced **19 findings (5 critical)** against the live repo; all resolved in the merge. Every file path / symbol / quoted snippet was re-verified against HEAD `1fa8437`.
- **Not pushed** (remote / commit-only). The plan commit sits on the worktree branch only.

## What the plan covers (the actual feature work, for the NEXT session to build)

1. **Restore the vanished import button.** Root cause (verified, not config): the `syncPreparedBtn` JS block in `templates/js/_workitems_overview_js.html` keeps `#preparedAuditWrap` `hidden` unless the *selected process filter* (`#prcfW`) is in `pid_processes` — so on the default "all" view the button never shows. Fix: drop `and pid_processes` from **both** `{% if prepared_import_perm and ms02_active and pid_processes %}` guards in `templates/workitems_overview.html` (lines ~321 and ~335), delete the `syncPreparedBtn` block, show the button whenever perm + `ms02_active`. **`col_pid` IS already seeded** (user-confirmed) — seeding was never the problem.
2. **5-column Excel** (was 2): `PID, Collected (0/1), CollectedBy (name), Prepared (0/1 — the real 4th header is a typo'd "PreparedBy"), PreparedBy (name)`. Extend `parse_prepared_xlsx` (now returns dicts), typo/case/order-tolerant.
3. **Merge + standalone display.** New per-PID resolver `resolve_ms02_pid_to_wids(engine, specs, pids) -> {pid: [wid,...]}`; richer session stash (`{ids, payloads, pid_to_wids}`); `_get_workitems_data` merges imported values onto matched rows and appends **synthetic rows for unmatched PIDs (page 1 only)**; 4 extra table columns toggled via a `no-import-cols` CSS class on `#workitemsTable`. Default (no `pidImport`) path stays byte-identical.

**No migration needed.** Next free number would be `0031`, but nothing schema-level changes. i18n: 4 new column headers + banner strings (German "Prepared" → `Vorbereitet`, not `Bereit`).

## This session's commits

```
7c5b5d4  docs(plans): add prepared-import button + 5-col values plan   (on worktree branch plan/prepared-import-button-extra-fields — NOT on feature/2.5.63)
```
Plus the handoff commit this step creates (on `feature/2.5.63`, main checkout).

## Next steps (ordered)

1. **`/execute-plan`** — it picks up the latest plan in the worktree and builds the 8 tasks subagent-by-subagent, then (with `--merge-worktree`) merges `plan/prepared-import-button-extra-fields` back into `feature/2.5.63` and removes the worktree. Start there.
   - The plan mandates TDD per task; CI/TEST has **no MS02 engine** so route tests expect `400` with `"MS02"` in the body (MS02 gate fires first); parser tests need no Flask context.
   - **Restart `nx -u`** after the template/JS edits (Jinja cache) before any browser/e2e check.
2. **Owner: push** `feature/2.5.63` (95 commits unpushed) once execution lands and is reviewed. Not done here (remote / commit-only).
3. **Live-verify on INT** (not dev): MS02 media host is unresolvable from dev (`reference_ms02_media_host_dns`), and the import only resolves against the live MS02 columnar DB.

## Gotchas & notes (READ)

- **The plan file is NOT on disk in the main checkout** — it was committed only on the worktree branch. To read/execute it, work inside `.claude/worktrees/plan-prepared-import-button-extra-fields`. `/execute-plan` handles this.
- **Do NOT merge or delete the worktree manually** — `/execute-plan` owns the merge-back. Merging it early would defeat the execution-vessel pattern.
- **Resolution is COLUMNAR, not EAV** (commit `1fa8437` + migration `0030`): `resolve_ms02_pid_ids`/`resolve_ms02_docfield_ids` query `public."DossierStatistik"` via `SearchConfig.col_*` columns, guarded by the `_MS02_IDENT` regex. The plan's new `resolve_ms02_pid_to_wids` reuses `_MS02_IDENT` + `_as_workitem_ids` (both real, verified).
- **Two Jinja guards, not one** (red-team F02): missing the second one leaves the success banner `<div>` absent from the DOM and the JS `getElementById('preparedAuditBanner')` returns null.
- **Synthetic-row pagination limit** (red-team F06): synthetic rows + the `total_items` bump only happen on `offset == 0` (page 1). Documented as a known limitation in the plan's Gotchas.
- **SQL pre-commit hooks fail in the worktree** (no `env/INT.env` there → "Missing DB_SERVER_PRD"): the plan commit used `SQL_SYNC_SKIP=1` (docs-only; never `--no-verify`). Same applies to any worktree commit until the env file is present.
- **Workflow script (for resume/iteration):** `C:\Users\bes\.claude\projects\C--dev-nexora\2116514a-7619-4d9f-a846-2702d23b9608\workflows\scripts\plan-prepared-import-button-extra-fields-wf_660cad51-135.js` (agents currently set to `model: 'sonnet'` after the Fable outage).
- **Caveman-speak** for chat in this repo (`feedback_caveman_speak`); docs/code/commits stay normal (this handoff is a doc → normal).

## Untracked / left for owner

- **`scripts/new-process.py`** — still-untracked `StatConfig`-insert helper, a known background-agent stray (`reference_ruflo_stashes_work`); harmless (dev-side, excluded from the deploy mirror). Not committed.
- The new worktree `.claude/worktrees/plan-prepared-import-button-extra-fields` (+ its `plan/…` branch) is intentionally left open as the execution vessel.
- `var/handoff-pending` points at this file (gitignored — not committed).

## How to verify

```powershell
# Plan committed on the worktree branch:
git -C C:\dev\nexora log --oneline -1 plan/prepared-import-button-extra-fields   # 7c5b5d4 docs(plans): add prepared-import...
git -C C:\dev\nexora worktree list                                              # lists plan-prepared-import-button-extra-fields

# Plan file present in the worktree:
Test-Path C:\dev\nexora\.claude\worktrees\plan-prepared-import-button-extra-fields\docs\superpowers\plans\2026-06-23-prepared-import-button-extra-fields.md   # True

# Button-gone root cause (the gate to delete):
Select-String templates/js/_workitems_overview_js.html -Pattern 'syncPreparedBtn' -Quiet   # True
```

## Resuming in a fresh session

`/reset-session` (the flag in `var/handoff-pending` points here). To actually build the feature, use **`/execute-plan`** — it resumes in the worktree.

**Same-date tie-break:** four handoffs now share `2026-06-23`. If `/reset-session` auto-picks the wrong one, target this file explicitly: `/reset-session docs/superpowers/handoffs/2026-06-23-prepared-import-button-extra-fields-plan.md`.

**Nothing is built yet** — this session only wrote and committed the plan. The feature is entirely ahead in `/execute-plan`.
