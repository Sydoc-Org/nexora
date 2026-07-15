# Handoff — reporting logic audit + AI-agent fixes shipped; pin-to-dashboard plan ready

**Date:** 2026-07-15 · **Branch:** `feature/2.5.64` (72 commits ahead of origin, incl. earlier
sessions' work) · **commit-only (owner pushes)**
**Prior handoff:** `2026-07-15-reporting-editorial-ledger-reskin-execution-complete.md` (same day;
reskin execution, Task 12 blocked on VPN/DNS — that outage did NOT recur this session, INT was fine)

## TL;DR

- **Live audit of the reporting page** (Playwright vs INT) found much of the stale gap-list already
  shipped (quarter tokens, grain, show-query, drill-through) and three real bugs — **all three fixed,
  verified live, committed**: the dead AI Agent surface, the stale drill drawer after Refine, and
  missing zero-fill of empty date buckets.
- **The AI Agent surface (Surface C) now completes end-to-end** against Azure gpt-4o-mini: builds a
  valid definition, validates + runs SQL, answers with real fetched numbers, and returns Open-in-builder
  artifacts. It had died at max_turns on essentially every ask.
- **Pin-to-dashboard implementation plan written + committed** —
  `docs/superpowers/plans/2026-07-15-reporting-pin-to-dashboard.md` (6 TDD tasks, migration `0040`,
  anchors repo-verified). **Alert-only schedules were descoped: recon proved they ALREADY shipped**
  (migration `0022`, `alert_trips` in `nx_lib/reporting/schedule.py`, runner + UI + tests).
- **Claude Code toast notifications fixed** (`.claude/settings.json`): hooks now run via
  `sh -c '… ${CLAUDE_PROJECT_DIR:-.} …'` — the old cmd-style `%VAR%` never expands under the sh hook
  runner, which is why every Stop/Notification/PermissionRequest fire errored. Takes effect on the
  next session start.

## This session's commits (oldest → newest)

1. `0c6186c` fix(claude): run notify hooks via sh so CLAUDE_PROJECT_DIR expands
2. `b2f9f39` fix(reporting): make the AI agent surface actually complete
3. `a2c75c9` fix(reporting): stale drill drawer close + date-bucket zero-fill
4. `159a2dc` docs(reporting): changelog + agent-gate docs; translate LIMIT gate msg
5. `3c5d3ff` docs(plans): add reporting-pin-to-dashboard implementation plan

## What shipped

| Area | Files | Commit |
|---|---|---|
| Notify-toast hooks (sh wrapper) | `.claude/settings.json` | `0c6186c` |
| Agent tool schema + arg coercion | `nx_lib/reporting/ai_tools.py` | `b2f9f39` |
| Teaching validator/sandbox errors, LIMIT→TOP gate | `nx_lib/reporting/schema.py`, `tokens.py`, `sandbox.py` | `b2f9f39` |
| Source-anchor prompt fixes + turn cap 6→10 | `nx_lib/reporting/ai.py`, `nx_lib/views/reporting.py` | `b2f9f39` |
| Data tools stay bound on builder-only source (tests updated) | `tests/integration/test_reporting_ai_routes.py` | `b2f9f39` |
| Drill drawer closes on new run (both panes) | `templates/js/_reporting_simple_js.html`, `_reporting_js.html` | `a2c75c9` |
| Zero-fill date-grain buckets (Simple pane) | `templates/js/_reporting_simple_js.html` | `a2c75c9` |
| Changelog, reporting.md gate note, de/fr/it for `tsql_limit` msg | `CHANGELOG.md`, `docs/howto/reporting.md`, `translations/*` | `159a2dc` |
| Pin-to-dashboard plan | `docs/superpowers/plans/2026-07-15-reporting-pin-to-dashboard.md` | `3c5d3ff` |

### The agent-fix layers (what actually made it work — full detail in the commit body)

1. `build_definition`'s tool spec was a bare `{"type": "object"}` → model guessed the definition
   shape wrong every turn. Now carries the full v1 JSON schema (`_DEFINITION_PARAM_SCHEMA`).
2. Models stringify the nested `definition` arg → coerced (`json.loads`) and **written back into
   `args`** so the trace/artifact extraction (`_extract_agent_artifacts`) sees the dict.
3. Validator errors now teach (filters-list example, grainable field list, literal-ISO-dates hint on
   token misuse). New sandbox rule `tsql_limit` rejects `LIMIT` with "use TOP (n)" — sqlglot's
   lenient tsql parse had let it through to the real server (TOP and LIMIT parse to the SAME AST
   node, so the reject is textual).
4. The selected builder source (UI default, often PDQM) is grounding, not a gate: data tools stay
   bound with `explain_data`, and the prompt says the selection is not the question's subject.
5. Turn cap 6→10 — a full build→validate→run→answer loop needs the headroom.

## Next steps (ordered)

1. **Owner: review + push `feature/2.5.64`** (pre-push gate runs the full suite; run
   `python scripts/test_db_reset.py` first per the standing gotcha).
2. **Execute the pin plan:** `/execute-plan` →
   `docs/superpowers/plans/2026-07-15-reporting-pin-to-dashboard.md`. No worktree was created for
   the plan (only stray untracked junk in the clone, see below) — execution can create one or work
   on `feature/2.5.64` directly; the plan's Context section assumes the branch.
3. **Optional next lever for agent quality:** the remaining agent weakness is run_sql table-guessing
   (it invented `dbo.Bucher_Document` etc. before landing a working query) — schema grounding text
   and/or a better model on INT would lift it; gpt-4o-mini is the current ceiling.

## Gotchas & notes

- **Alert-only schedules exist** — do not re-plan them (migration `0022_report_schedule_alerts.sql`;
  `ALERT_OPS`/`alert_trips`/`total_definition` in `nx_lib/reporting/schedule.py`;
  `ops/run_scheduled_reports.py`; e2e `tests/e2e/test_reporting_schedule.py`). Several memory files
  still list them as "runner-up ideas" — stale.
- **Drill-through, show-query, multi-breakdown, quarter tokens, grain emission: all shipped and
  verified live this session.** The old reporting-usability gap list is done except agent-quality
  polish.
- **Zero-fill** applies only to single-dimension + metric + bounded `between` (literal or resolved
  token) date-grain results; it bails whenever a data row falls outside the generated bucket
  sequence (dialect drift guard). KPI band counts the filled buckets (Q1 sparse data → "Buckets 3,
  avg 0,667" — intentional).
- **Toast hooks load at session start** — the fix in `0c6186c` shows no effect until the user's NEXT
  Claude Code session/`/clear`.
- **`0040` is the next free migration number** (0039 = metric labels). Re-check at execution time.
- The dormant dashboard **widget engine stays dormant** (pin plan D1) — pins are a standalone
  `dbo.ReportingPins` table; do not add a `report` widget type.

## Untracked / left for owner

- `package.json` + `package-lock.json` at repo root (a lone `headroom-ai` npm dep — tool junk, not
  nexora's; probably a plugin install gone astray). **Deliberately not committed, not deleted** —
  owner decides; `.gitignore`-ing or deleting both is likely right.
- `var/screenshots/audit-*.png` — session audit screenshots (gitignored path, kept for reference).

## How to verify

```powershell
# fast tier (all green at handoff time)
.\.venv\Scripts\python -m pytest tests --ignore=tests/e2e -q
# the suites this session touched
.\.venv\Scripts\python -m pytest tests -k "reporting_ai or ai_tools or sandbox or tokens" -q
.\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -q   # 56 passed this session
# live agent check (INT, AI configured): /reporting → Advanced → Ask AI → Agent →
#   "which process had the most documents in June 2026 and how many?"
#   → expect a numeric answer + Open in builder, no ⚠ banner
```

## Resuming in a fresh session

Read this handoff, then open
`docs/superpowers/plans/2026-07-15-reporting-pin-to-dashboard.md` and start at Task 1 (migration
`0040`). Three handoffs share the date 2026-07-15 — `/reset-session <path>` targets a specific file
if the picker grabs the wrong one.
