# Handoff — Feature ideation workflow + drill-through spec & plan (plan-only session)

- **Date:** 2026-06-11 (evening)
- **Branch:** `feature/2.5.63`. **67 commits ahead of `origin/feature/2.5.63`** — commit-only
  (remote); the owner pushes + opens the PR.
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-11-simple-guide-wizard-complete.md`.
  The rich-export plan context lives in
  `docs/superpowers/handoffs/2026-06-11-show-query-multidim-export-plan.md`.
- **This session's commits (oldest → newest):**
  - `1d6de8b` docs(reporting): drill-through design spec + implementation plan
  - *(this handoff commit)*

---

## TL;DR

1. **Ran a 26-agent feature-ideation workflow** over the reporting page (5 recon readers,
   6 ideation lenses, dedup, 14 per-candidate feasibility checks against real code).
   **All 14 candidates feasible**; ranked list preserved below — do not re-run the workflow.
2. **Owner picked drill-through** (click a chart element / aggregate row → slide-over drawer
   with the underlying document rows, workitem deep-links, CSV/XLSX export) and said
   **"only plan"** — spec + 8-task plan written and committed (`1d6de8b`), **zero
   implementation**.
3. Key recon wins: `is_null`/`is_not_null`/`lt` **already exist** in `FILTER_OPS` with SQL
   emission in both builders → feature needs **no migration, no permission, no dependency,
   no new endpoint**. Only backend work is a 1-line `is_null` projection/filter symmetry
   fix in `query.py`.
4. **SQL pre-commit hooks passed clean without `SQL_SYNC_SKIP=1`** — the INT CRLF drift is
   confirmed resolved.

## What shipped

| What | File(s) | Commit |
|------|---------|--------|
| Design spec (owner decisions, recon facts, transform rules, drawer UX, security, testing) | `docs/superpowers/specs/2026-06-11-reporting-drill-through-design.md` | `1d6de8b` |
| Implementation plan (8 TDD tasks, complete code, phase gate) | `docs/superpowers/plans/2026-06-11-reporting-drill-through.md` | `1d6de8b` |

Owner decisions locked into the spec: click targets = charts **and** aggregate-table rows
on **both** tabs (not the big-number card, not pivot cells); detail columns = fixed smart
set (`workitem_id`, `processname`, `import_date`, `export_date` + breakdown fields ∩
catalog); panel = slide-over drawer from the right; approach = client-side definition
transform through the existing `/api/reporting/run` + the `is_null` symmetry fix.

## The 14-candidate ranked list (from the ideation workflow — keep, don't re-derive)

Top tier (value 5/5): **1. Drill-through** (M — this session's pick) · **2. Pin to
dashboard** (L — the dashboard widget backend in `nx_lib/views/dashboard.py` is fully
built and dormant; only the `DashboardLayouts` migration is missing; owner showed
interest). Strong (4/5): **3. Alert-only schedules** (M — threshold/delta conditions on
existing schedules; 4-of-6-lens convergence, strongest demand signal; owner showed
interest) · **4. Compare with previous period** (L) · **5. Honest totals for distinct
counts** (M) · **6. Plain-language subtitle + explain-this-report** (M) · **7. AI agent
reliability pack + golden-question evals** (M — note: max-turns artifact return is already
shipped server-side, only a UI banner missing) · **8. Run trust strip / freshness stamp /
outage shield** (M) · **9. Schedules & deliveries hub with receipts + auto-pause** (L —
silent non-delivery hole is real) · **10. Copy-link deep links + share notifications** (M)
· **11. Stats view + one-shot AI insight caption** (M — `compute_stats` is built but
AI-only today) · **12. Metric glossary tooltips** (M — `Description` column already exists
in `dbo.ReportingMetrics`, pure plumbing) · **13. Derived ratio metrics** (M — semantic
Slice 3) · **14. Parameterized saved SQL reports** (L — needs a new run-by-id endpoint to
be safe). Nearly all frontend work conflicts with rich-export Phase 2 and must sequence
after it.

## Next steps (ordered)

1. **Finish the rich-export plan on the worktree** (`.claude/worktrees/rich-export`,
   branch `feat/rich-export`): Phase 1 backend is committed there (7 commits, HEAD
   `df221a0`); Phase 2 frontend (plan Tasks 7–10) + i18n/docs (Tasks 11–13) are pending.
   Plan: `docs/superpowers/plans/2026-06-11-reporting-show-query-multidim-export.md`.
2. **Merge `feat/rich-export` into `feature/2.5.63`.**
3. **Execute the drill-through plan**
   (`docs/superpowers/plans/2026-06-11-reporting-drill-through.md`): Task 1 (backend
   `is_null` symmetry fix) is **startable any time, even before steps 1–2**; Tasks 2–8
   (frontend) are gated on the rich-export merge (the plan has an explicit gate check).
4. **Owner: push + open PR → `main`** (67 commits waiting). Run
   `python scripts/test_db_reset.py` first (pre-push gate runs the full e2e suite).
5. Standing PROD checklist (unchanged): provision the two reporting RO SQL logins, wire
   the scheduled-reports Task Scheduler task, repair the `0011` em-dash label, apply
   migrations `0015`–`0021` (auto on deploy).

## Gotchas & notes

- **CRLF drift is RESOLVED:** this session's commits ran the `sql-migrate-int` +
  `sql-sync-check` hooks clean, no `SQL_SYNC_SKIP=1` needed. Stop prefixing it unless the
  hook actually complains again.
- **The `is_null` asymmetry** (drill's only backend work): `build_table_query` projects an
  unmapped field as `NULL AS [field]` but drops the whole process subquery when a filter
  references it — so "(null)" groups under-report on drill until plan Task 1 lands. The
  fix + 3 unit tests are fully written out in the plan.
- **Drill plan anchors on function names, not line numbers** — rich-export Phase 2 will
  shift every line in the frontend files. Re-grep the anchors after the merge.
- **Workflow artifacts are ephemeral:** the full ideation output lives in a temp file
  (`%TEMP%\claude\...\wp13jnc5t.output`) that will not survive; the ranked list above and
  the per-candidate verdicts in the spec are the durable record.

## Untracked / left for owner

- `env/CONFLUENCE.env.example` deletion — still unstaged, belongs to the Confluence
  docs-sync feature (concurrent session); leave it for that feature's commit.
- Push + PR are always owner-side (remote/commit-only rule).

## How to verify

```powershell
git show --stat 1d6de8b          # the spec + plan commit (2 files, ~1047 lines)
git -C .claude/worktrees/rich-export log --oneline -8   # rich-export Phase 1 state
python -m pytest tests/unit/test_reporting_query.py -v  # green today; Task 1 adds 3 tests
```

## Resuming in a fresh session

Run `/reset-session` (reads `var/handoff-pending`), or target this file explicitly:
`/reset-session docs/superpowers/handoffs/2026-06-11-drill-through-plan.md`.

**Five handoffs share 2026-06-11** — use the explicit path if the flag is gone.

The resume point is **Next steps 1–3 above**: finish + merge the rich-export plan, then
execute the drill-through plan (`docs/superpowers/plans/2026-06-11-reporting-drill-through.md`).
Drill-through Task 1 (backend) can be done immediately if a quick win is wanted. The
execution-mode choice (subagent-driven vs inline) is still owed by the owner for both plans.
