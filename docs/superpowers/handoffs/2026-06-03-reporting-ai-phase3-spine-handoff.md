# Handoff — Reporting AI Phase 3 (agentic loop + stats spine) implemented

- **Date:** 2026-06-03
- **Branch:** `feature/2.5.63`, worked in an **isolated worktree** at
  `C:/dev/nexora.wt/reporting-phase3` (the main checkout was on `feature/2.5.63.1`
  with the owner's live UI work — left untouched). Git mode: **commit-only (remote)**
  — **nothing pushed**. After this session the branch is **23 commits ahead of
  `origin/feature/2.5.63`** (the prior 17 + 5 feat/docs commits + this handoff).
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-03-reporting-ai-phase2-polish-handoff.md`
- **Build spec:** `docs/superpowers/plans/2026-06-03-reporting-ai-phase3.md` (TDD, task-by-task).

## TL;DR

- The Phase-2 **"4 open minors" were already cleared** by the prior session
  (`3956a1b`) — confirmed, not redone.
- Implemented the **Phase 3 spine** (design doc §3 Tier-2 / §10) end-to-end with TDD:
  a deterministic **stats engine**, a provider-neutral **tool layer**, the **agentic
  tool-loop** (`ask_agentic`) with self-repair + a turn cap + Azure/Anthropic
  tool-calling, and a new **schema-only drafter route** `POST /api/reporting/ai/agent`
  (Surface C).
- **No new dependency, permission, table, or migration.** Egress stays schema-only.
- **77 reporting tests green** (incl. 13 stats + 10 tool + 9 agentic + 7 new route +
  translations), ruff clean. All offline — no live provider needed.

## Commits this session (local/unpushed, on `feature/2.5.63`)

```
231e383 docs(reporting): Phase 3 plan + agentic loop/stats docs
7f5d672 feat(reporting): agentic drafter route /ai/agent (Phase 3d)
048795b feat(reporting): agentic tool-loop driver with self-repair (Phase 3c)
7f385e0 feat(reporting): AI tool layer over gate/run/definition/stats (Phase 3b)
61c2a20 feat(reporting): deterministic stdlib stats engine (Phase 3a)
<this>  docs(handoff): reporting AI Phase 3 spine
```

## What shipped (by file)

| File | Change |
|---|---|
| `nx_lib/reporting/stats.py` | **NEW.** Pure-stdlib (`statistics`/`math`, no pandas/scipy) `compute_stats(columns, rows, spec)` — ops: describe, group_by, percentiles (linear interp), value_counts, correlation, top_n; `StatsError` on bad spec/unknown column. |
| `nx_lib/reporting/ai_tools.py` | **NEW.** `TOOL_SPECS` (provider-neutral) + `ToolRegistry` dispatching validate_sql / run_sql / build_definition / compute_stats to the existing rails; tools return `{ok, ...}` envelopes and never raise across the boundary. `run_sql`/`build_definition` are injected (request scope). |
| `nx_lib/reporting/ai.py` | **+** `AssistantTurn`, `AiAgenticResult`, `ask_agentic` (model→tool→model loop, self-repair, `DEFAULT_MAX_TURNS=6`), `_make_agent_step` + translators/parsers for Azure (`tool_calls`/role:tool) and Anthropic (`tool_use`/`tool_result`). `ask`/`ask_definition` untouched. |
| `nx_lib/views/reporting.py` | **+** route `POST /api/reporting/ai/agent` (`reporting_ai_agent`), `_AGENT_SYSTEM`, `_extract_agent_artifacts`. Gated `reporting.ai.use`; binds only data-free tools (`build_definition`; `validate_sql` iff `reporting.ai.sql`); honours `AI_DAILY_LIMIT`; audits `Surface='agent'` (misconfig on `AiError`, blocked on cap); returns `{answer, definition, sql, toolTrace, turns, stoppedReason}`. |
| `tests/unit/test_reporting_stats.py`, `test_reporting_ai_tools.py`, `test_reporting_ai_agentic.py` | **NEW.** 13 + 10 + 9 unit tests (loop logic via scripted `agent_step`; provider parsing via fake `transport`). |
| `tests/integration/test_reporting_ai_routes.py` | **+7** route tests (perm gate, 503/400/429, happy path + artifact extraction, misconfig audit, SQL-tool gating). |
| `CHANGELOG.md`, `docs/design/reporting-ai-assistant.md` (§12 + status), `docs/howto/reporting.md` (Agent/Surface C), `CLAUDE.md` (3rd AI route) | Docs in sync. Plan: `docs/superpowers/plans/2026-06-03-reporting-ai-phase3.md`. |

## The governance line (important)

Surface C (3d) is a **self-repairing drafter**: the model uses only **data-free**
tools (build_definition / validate_sql) and is grounded by the source catalog / SQL
schema in the prompt. **No result rows ever reach the model** — egress stays
schema-only, matching the design's default posture.

Activating `run_sql` / `compute_stats` *inside the live loop* feeds their results
back to the model (so it can narrate numbers) = **data egress**. That is **Phase 3e**,
gated behind a new **`reporting.ai.explain_data`** permission and the design's
open decision §13-Q2 (is sending rows/stats to the model acceptable?). The stats
engine + tool layer are built and tested; only their in-loop activation waits on
that decision. **Do not wire run_sql/compute_stats into the loop without it.**

## Owner actions / next steps

1. **Review + (when ready) merge.** This is a worktree on `feature/2.5.63`. To push:
   the pre-push gate runs the **full Playwright e2e** — run `python scripts/test_db_reset.py`
   first (stale `NEXORA_TEST` state, e.g. `ReportingSqlAck`, fails order-dependent e2e).
   The prior handoffs' PROD-rollout items still apply (RO-login unblock, AI env on PROD,
   rotate the Azure key, scheduled-reports Task Scheduler).
2. **Phase 3d Task 7 (UI) — not done.** The "Ask AI → Agent" sub-mode (visible
   tool-step trace + follow-up conversation) is specced in the plan but needs the live
   server for browser verification; build + screenshot on a session with env. Until
   then the route has no UI entry point.
3. **Phase 3e — decide the egress question**, then wire run_sql/compute_stats into the
   loop behind `reporting.ai.explain_data` (new migration + perm seed), + glossary RAG.

## Gotchas & notes

- **Worktree needs env.** A fresh worktree has no `env/*.env` (gitignored, main-tree
  only). Copied them in (`Copy-Item C:\dev\nexora\env\*.env …`) so `conftest` (which
  sets `ENVIRONMENT=TEST` → loads `env/TEST.env`) can build the app. They stay
  gitignored — `git status` clean.
- **Pre-commit SQL hook drift.** From the fresh worktree, `sql-migrate-int` reports the
  11 already-applied migrations as "edited" (checksum mismatch — line-ending/worktree
  artefact, *not* a real edit; `sql-sync-check` passes). These commits add **zero SQL**,
  so I used the sanctioned `SQL_SYNC_SKIP=1 git commit …` escape hatch (skips the SQL
  hooks; gitlint/ruff still run). **Not** `--no-verify`.
- **gitlint** requires a body (B6) and ≤72-char title (T1) — every commit has both.
- Tests run from the worktree with the **main venv**: `C:/dev/nexora/.venv/Scripts/python.exe`.
- **No frontend changed** this session (route + Python only), so no screenshots.

## How to verify (all green at `7f5d672`/`231e383`)

```powershell
# from C:\dev\nexora.wt\reporting-phase3 (env/*.env copied in)
C:\dev\nexora\.venv\Scripts\python.exe -m pytest tests/unit/test_reporting_stats.py `
  tests/unit/test_reporting_ai_tools.py tests/unit/test_reporting_ai_agentic.py `
  tests/unit/test_reporting_ai.py tests/unit/test_reporting_ai_schema.py `
  tests/integration/test_reporting_ai_routes.py tests/unit/test_translations.py -q
# -> 77 passed
C:\dev\nexora\.venv\Scripts\python.exe -m ruff check nx_lib/reporting/stats.py `
  nx_lib/reporting/ai_tools.py nx_lib/reporting/ai.py nx_lib/views/reporting.py
# -> All checks passed!
```

## Resuming in a fresh session

The Phase 3 spine is complete, tested, and committed (offline). The realistic next
tasks are **Phase 3d Task 7 (the Agent UI, browser-verified)** and **Phase 3e (the
data-egress decision → run_sql/compute_stats in-loop + `reporting.ai.explain_data` +
glossary RAG)**. The plan doc is the spec of record; §13-Q2 in the design doc is the
decision that gates 3e.
