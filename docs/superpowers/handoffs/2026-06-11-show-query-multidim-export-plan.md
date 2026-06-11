> **Newer handoff exists for this date:** see
> `docs/superpowers/handoffs/2026-06-11-simple-guide-wizard-complete.md` (Simple Guide wizard
> improvements — all 11 tasks executed and verified, later the same day).

# Handoff — Show-query / multi-breakdowns / rich-export: spec + 13-task plan written (not executed)

- **Date:** 2026-06-11 (afternoon session)
- **Branch:** `feature/2.5.63`. **63 commits ahead of `origin/feature/2.5.63`** — commit-only
  (remote); the owner pushes + opens the PR.
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-11-simple-guide-wizard-plan.md`
  (same date — the simple-guide plan this session must sequence behind; that plan was being
  *executed by a concurrent session while this one ran*, see Gotchas).
- **This session's commits (oldest → newest):**
  - `e43faaf` docs(reporting): plan show-query, multi-breakdowns, rich export *(the only
    commit from this session)*
  - *(plus this handoff commit)*

---

## TL;DR

1. **Owner asked for three reporting upgrades:** show the SQL behind a run, allow more than one
   breakdown category (reference ask: *"Document count by document source over last 3 months,
   per month, by export date"*), and make export less "lame" than bare tables.
2. **Spec + 13-task plan written and committed (`e43faaf`), nothing executed:**
   `docs/superpowers/specs/2026-06-11-reporting-show-query-multidim-export-design.md` and
   `docs/superpowers/plans/2026-06-11-reporting-show-query-multidim-export.md`.
3. **Owner answered the three open decisions** (AskUserQuestion): SQL visible to **everyone**
   who can run reports (no new perm/migration); wizard allows **up to three** breakdowns
   (≤1 date; 2 dims chart as multi-series + stacked option, 3 dims = table-only + note);
   export gets **XLSX-with-embedded-chart + Simple chart-PNG button + matplotlib charts in
   scheduled mails** — **PDF explicitly deselected**.
4. **Headline recon find:** the backend *already* supports N-dimension `GROUP BY`
   (`definition.columns` is uncapped; Advanced UI already multi-selects). Only the wizard UI,
   the chart code (plots first dim only) and missing tests block the ask — so the plan is
   mostly frontend + tests.

## The 3 asks → plan tasks

| Owner ask | Plan tasks | Note |
|---|---|---|
| Show the query that was run | T2 (echo `sql`+`params` from `/api/reporting/run`) + T7 (panels on both tabs) | `api_run()` already holds `(sql, params)` from `_prepare_run()`; never returned today |
| >1 breakdown category | T1 (pin multi-dim GROUP BY in unit tests) + T8 (wizard chips, max 3) + T9 (2-dim → multi-series chart, stacked option; 3-dim → note) | Breakdown step gains a **Continue** button (chips can't auto-advance); existing e2e updated |
| Export beyond tables | T3 (XLSX title block + `chart_png=`) + T4 (`nx_lib/reporting/chart_render.py`, matplotlib) + T5 (`send_mail` inline images) + T6 (scheduler embeds chart in mail body + XLSX) + T10 (Simple PNG button + `chartImage` wiring) | pillow already present; **matplotlib is the only new dependency** (deploy.yml:18 auto-installs) |
| — | T11–T13 | i18n (translations pre-written in the plan), docs/changelog, full verification + INT walkthrough |

## What shipped

| File | Commit | What |
|------|--------|------|
| `docs/superpowers/specs/2026-06-11-reporting-show-query-multidim-export-design.md` | `e43faaf` | Design: decisions, per-feature design, rejected export approaches (PDF, headless browser, QuickChart), security notes |
| `docs/superpowers/plans/2026-06-11-reporting-show-query-multidim-export.md` | `e43faaf` | 13 tasks in 3 phases, complete code in every step, TDD ordering |

## Next steps (ordered)

1. **Let the concurrent simple-guide execution finish.** During this session its Tasks 6–9
   landed (`b81271c`, `71e6e0c`, `d852ff6`, `e82bf16`); its Task 10 (docs+changelog) was
   **mid-flight uncommitted** at handoff time and Task 11 (full verification) still open.
2. **Execute the new plan Phase 1 (Tasks 1–6, backend-only)** — safe regardless of step 1;
   zero file overlap. Owner still owes the execution-mode choice (subagent-per-task vs inline).
3. **Execute Phase 2 (Tasks 7–10, frontend)** only after the simple-guide plan is fully
   committed — the gate in the plan header (its Task 6–8 commits) is **already satisfied**;
   just confirm the tree is clean of `templates/js/_reporting_simple_js.html` first.
4. Phase 3 (T11–T13 chores), then standing owner items (push + PR → `main` — now 63 commits —
   plus the PROD checklist from prior handoffs).

## Gotchas & notes

- **A concurrent session was executing the simple-guide plan in this same checkout** the whole
  time. The uncommitted `CHANGELOG.md` + `docs/howto/reporting.md` edits in the tree are **its
  Task 10 work — deliberately not committed here**. Ditto the `env/CONFLUENCE.env.example`
  deletion (docs-sync leftover, not this session's).
- **The new plan anchors on function names + quoted code, not line numbers** — written that way
  precisely because the concurrent commits shift lines in every Simple-pane file.
- Key verified facts baked into the plan: `_prepare_run()` returns `(columns, sql, params,
  engine)`; `rows_to_xlsx(columns, rows, *, title)` at `nx_lib/reporting/export.py:20`;
  `send_mail()` builds a Graph payload (inline images = `isInline` + `contentId`);
  `pillow==11.3.0` already in requirements; scheduled runner is `ops/run_scheduled_reports.py`
  `_process()`; integration tests for the run endpoint live in
  `tests/integration/test_reporting_routes.py`.
- **matplotlib design constraints** (in plan T4): `Agg` backend, `MPLCONFIGDIR` →
  `var/mpl-cache` (self-creating, inside the Defender exclusion), set **before** first import.
- 3-dim results deliberately never chart — summing across the third dim would silently lie for
  distinct-count metrics.
- Pre-commit SQL hooks **passed clean twice** this session — the INT CRLF drift did not
  reproduce (second session in a row; the standing `SQL_SYNC_SKIP=1` advice may be obsolete).
  gitlint bounced one commit for a 74-char title — keep subjects ≤72.
- E2E constraint as always: TEST env has no Statistics DB → docprocessing behavior is
  INT-browser-verified; all plan e2e uses seeded table sources.

## Untracked / left for owner

- `CHANGELOG.md`, `docs/howto/reporting.md` (modified), `env/CONFLUENCE.env.example` (deleted) —
  all belong to the concurrent session / earlier work; left uncommitted on purpose.
- Recon workflow output (4 agent reports) lives in session temp — disposable; everything needed
  survived into the spec/plan.

## How to verify

```powershell
git show --stat e43faaf      # 2 files, ~1700 insertions, docs only
# No app code changed this session - all suites unaffected by it.
# The concurrent simple-guide session owes its own Task 11 verification run.
```

## Resuming in a fresh session

Run `/reset-session` (reads `var/handoff-pending`) — **five handoffs now share this date**, so
if the flag is gone, target explicitly:
`/reset-session docs/superpowers/handoffs/2026-06-11-show-query-multidim-export-plan.md`.
The single resume point is: **confirm the simple-guide plan finished (Tasks 10–11), then ask
the owner for execution mode and run
`docs/superpowers/plans/2026-06-11-reporting-show-query-multidim-export.md` Phase 1 (Tasks
1–6) — Phase 2 only on a clean tree.**
