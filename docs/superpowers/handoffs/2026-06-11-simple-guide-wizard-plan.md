> **Newer handoff exists for this date:** see
> `docs/superpowers/handoffs/2026-06-11-show-query-multidim-export-plan.md` (show-query /
> multi-breakdowns / rich-export plan session, later the same day).

# Handoff — Simple Guide wizard improvements: 11-task plan written (not executed)

- **Date:** 2026-06-11
- **Branch:** `feature/2.5.63`. **38 commits ahead of `origin/feature/2.5.63`** — commit-only
  (remote); the owner pushes + opens the PR.
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-11-admin-ui-plan-redstrip-fix.md`
  (same date — admin-ui worktree plan + red-strip fix; see Gotchas: that plan was *executed and
  merged* by a concurrent session). Before that:
  `docs/superpowers/handoffs/2026-06-11-ai-fixes-complete-verified.md`.
- **This session's commits (oldest → newest):**
  - `43e0d3e` docs(reporting): plan for Simple Guide wizard improvements *(the only commit from
    this session)*

---

## TL;DR

1. **Owner gave a 9-item feedback list on the Simple Guide (wizard)** — duplicate metrics,
   breakdown-list bloat/missing dimensions, unexplained missing charts, no chart-type switch,
   tiny process-scope control, saved reports not adjustable, Back/exit navigation, Save-as
   browser prompt. A 6-agent exploration workflow mapped every subsystem; **all facts were
   live-verified** (line numbers, INT DB queries).
2. **`docs/superpowers/plans/2026-06-11-reporting-simple-guide-improvements.md` — 11 tasks,
   PLAN ONLY, nothing executed.** No backend/migration changes anywhere — pure template/JS/CSS.
3. **Owner chose "review plan first"** (AskUserQuestion) — the plan file was sent to them.
   **Execution has NOT started**; waiting on their verdict + execution mode.
4. Headline finding: the "two identical metrics" item is **already fixed** (migration `0021`,
   `workitem_count.Enabled=0` live-verified on INT at ~12:35) — plan Task 1 is verify-only.

## The 9 asks → plan tasks

| Owner ask | Plan task | Note |
|---|---|---|
| Two identical metrics (doc/workitem count) | T1 | Already shipped (`0021`); verify in browser only |
| Breakdown bloat (Processname, Bank PK, crdno, barcode, doc date) | T2 | Root cause: alphabetical sort + `slice(0,12)` in `renderBreakdownStep()` — wanted fields fall off the cap |
| Add Document Source (first), Type, Forwarding, Owner/Property/Tenancy no., Registered | T2 | All 7 verified present in live catalog (`Search_Field_Labels` / `SearchConfig`) |
| Explain missing graph | T3 | + top-50 charting for >50-row category breakdowns |
| Button to change/add graphs | T4 | bar/line/pie/doughnut switcher; type persists as `def.chartType` (validator ignores unknown keys — verified); "more graphs" declared out of scope |
| Bigger "Limit to specific processes" | T5 | Bordered row + live "n / m" badge; msgid unchanged |
| Saved reports adjustable in wizard/filters | T6 | Chips/refine already work for saved reports (Task 14, `7aaecda`); plan adds a def→wizard reverse-mapper so "Adjust in wizard" appears for any wizard-shaped definition |
| Wizard Back → adjustment + exit button | T7 | Result-view Back re-enters wizard; ✕ exit buttons on result + wizard |
| Save-as custom textbox (Advanced) | T8 | `.reporting-modal` name dialog replaces `window.prompt` (also fixes Rename); zero new i18n |
| — | T9-T11 | i18n cycle (translations pre-written in the plan), docs/changelog, full verification walkthrough |

## What shipped

| File | Commit | What |
|------|--------|------|
| `docs/superpowers/plans/2026-06-11-reporting-simple-guide-improvements.md` | `43e0d3e` | The 11-task implementation plan (1009 lines, complete code in every step) |

## Next steps (ordered)

1. **Owner verdict on the plan** — they are reading it now. Five judgment calls were flagged in
   chat for their review (all also in the plan's "Decisions locked in" table):
   `workitem_id` added to the hide-list; >50 categories chart top-50 instead of hiding;
   wizard's own "← Back" still exits to library (only *result* Back re-enters the wizard);
   "more graphs" out of scope; metric dedupe is verify-only.
2. **Execute the plan** once approved — owner still owes the mode choice: subagent-per-task
   with review between, or inline batch-to-end. Tasks are ordered with dependencies
   (T6 before T7; T3 before T4).
3. Standing owner items (unchanged from prior handoffs): push + PR → `main` (38 commits
   waiting), PROD checklist (RO SQL logins, scheduled-reports Task Scheduler task, `0011`
   em-dash repair; migrations `0015`–`0021` auto-apply on deploy).

## Gotchas & notes

- **A concurrent session executed the admin-ui plan during this session** and merged it into
  `feature/2.5.63` (`98f1770`…`f1fcc78`, merge `f070f35`, 12:06–12:47) — not this session's
  work, and **no handoff exists for that execution**. Its precursor handoff
  (`2026-06-11-admin-ui-plan-redstrip-fix.md`) said *"e2e from the main checkout is still owed
  before push"* — **verify the admin pages e2e before pushing.**
- **Plan line anchors are valid at `43e0d3e`**: the concurrent admin-ui range touched only
  `templates/generali_reporting.html` + `templates/js/_generali_reporting_js.html` — none of the
  Simple-wizard files the plan edits.
- The plan's live-DB facts (metric `Enabled` flags, field catalog) were queried against INT
  NexoraDB on 2026-06-11 ~12:35.
- Pre-commit hooks (incl. `sql-migrate-int` + sync check) **passed clean** this session — no
  `SQL_SYNC_SKIP=1` needed; the INT CRLF drift did not reproduce. gitlint bounced one commit
  for a missing body (B6) — always include a body.
- TEST env has no Statistics DB → plan Tasks 2 & 5 (docprocessing-only behavior) are
  browser-verified on INT, not e2e; all other tasks have e2e specs using seeded table sources.
- The exploration workflow's full output (6 structured agent reports) lives in the session temp
  dir — disposable; everything needed survived into the plan.

## Untracked / left for owner

- Nothing uncommitted (clean tree at `43e0d3e`).
- The plan file was sent to the owner via the session for review; their notes come back next
  session.

## How to verify

```powershell
git log -1 --stat                                  # 43e0d3e, plan file only
python scripts/db-migrate.py --env INT --dry-run   # expect: up-to-date (0021 applied)
# No app code changed this session - suites unaffected. Owed by the CONCURRENT
# admin-ui merge (not this session): admin-pages e2e before push.
```

## Resuming in a fresh session

Run `/reset-session` (reads `var/handoff-pending`), or target this file explicitly —
**three other handoffs share this date**, so if the flag is gone use
`/reset-session docs/superpowers/handoffs/2026-06-11-simple-guide-wizard-plan.md`.
The single resume point is: **ask the owner for their plan verdict** (plus the five flagged
judgment calls and the execution mode), then execute
`docs/superpowers/plans/2026-06-11-reporting-simple-guide-improvements.md` Tasks 1–11 in order.
