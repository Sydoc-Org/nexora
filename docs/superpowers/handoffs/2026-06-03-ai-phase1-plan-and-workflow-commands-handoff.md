# Handoff — Reporting AI Phase-1 plan + `/hcc` & `/clh` workflow commands

- **Date:** 2026-06-03
- **Branch:** `feature/2.5.63` (committed locally, **NOT pushed** — commit-only)
- **Feature commit:** this session's commit is the latest on the branch (run `git log -1`);
  it adds the Phase-1 plan doc. The `/hcc` + `/clh` commands and memory updates live
  **outside the repo** (under `C:\Users\bes\.claude\`) and are not part of any commit.
- **Prior handoff:** `docs/superpowers/handoffs/2026-06-03-reporting-animations-ai-design-handoff.md`

## TL;DR

- Turned the **AI-assistant design doc** into a concrete, TDD, bite-sized
  **Phase-1 implementation plan** — `docs/superpowers/plans/2026-06-03-reporting-ai-phase1.md`.
  Scope locked with the owner: **plan-only this session** (no code), **all registered
  sources**, **provider-agnostic shell** (owner still deciding Azure vs Claude — ups/downs
  table is in the plan), **commit-only**.
- Built a pair of personal **workflow slash commands** (user-level, all projects):
  **`/hcc`** = write handoff → commit (no push) → prompt `/clear`; **`/clh`** = read the
  latest handoff → orient → front-load questions → run to completion.
- Confirmed (via the `claude-code-guide` agent) that **no command/skill/hook can
  auto-run `/clear`** — only the user can; `/hcc` automates everything up to that.

## What shipped

| File | Location | Change |
|---|---|---|
| `docs/superpowers/plans/2026-06-03-reporting-ai-phase1.md` | **repo** (committed) | NEW — Reporting AI **Phase-1** plan: 7 TDD tasks (migration → provider-agnostic `ai.py` → bounded schema serializer → gated/audited `POST /api/reporting/ai/ask` → "Ask AI" panel → env → docs/i18n), provider ups/downs table, self-review. |
| `hcc.md` | `C:\Users\bes\.claude\commands\` (**not** in repo) | NEW — `/hcc` handoff+commit+clear command. |
| `clh.md` | `C:\Users\bes\.claude\commands\` (**not** in repo) | NEW — `/clh` continue-from-latest-handoff command. |
| `reference_hcc_command.md` + `MEMORY.md` | `…\.claude\projects\C--dev-nexora\memory\` (**not** in repo) | NEW/updated — records the `/hcc`+`/clh` pair. |

Also: removed two **0-byte junk files** (`-` and `SQL)`) accidentally created in the
working tree this session; not committed.

## Plan in one paragraph (so the next session needn't re-read it all)

Phase 1 = an **"Ask AI" mode** on the Reporting page that turns a NL question into
**runnable T-SQL placed in the existing SQL editor** (no auto-run) + a 1-line
explanation. A new server-side, **provider-agnostic** client (`nx_lib/reporting/ai.py`,
via `requests` — **no new dependency**) drafts SQL from a **bounded, cached schema
serialization** (`nx_lib/reporting/ai_schema.py`, from the RO targets' `INFORMATION_SCHEMA`
+ curated catalogs across all accessible sources), **self-validates** it through the
existing `sandbox.validate_select` gate, and a gated route `POST /api/reporting/ai/ask`
returns `{sql, explanation, valid}` and audits to a new `dbo.ReportingAiAudit`. New perms
`reporting.ai.use` / `reporting.ai.sql` (seeded like `0007`/`0008`). **Egress is
schema-only — never result rows.** No new execution path: running still goes through the
unchanged `/api/reporting/sql/run`. `AI_PROVIDER=none` by default → the route 503s like an
unconfigured RO source until a key is provisioned.

## Owner actions / next steps

1. **Decide the AI provider** (Azure OpenAI vs Claude API) — the plan's top has the
   ups/downs table. This gates the env/secrets shape but **not** the build (the shell is
   provider-agnostic; default `AI_PROVIDER=none`).
2. **Choose how to execute Phase 1** when ready: subagent-driven (fresh agent per task,
   review between) or inline (batch with checkpoints). Then build it task-by-task.
3. **(Carried, unchanged)** Push `feature/2.5.63` + open the PR `→ main` (HEAD is far ahead
   of `origin/main`); provision the two RO SQL logins (`DB_REPORTING_RO_*`,
   `DB_REPORTING_OCTO_RO_*`); wire the scheduled-reports Task Scheduler task. See the
   prior two handoffs.
4. Optional: if you want `/hcc` + `/clh` **team-shared**, move them into the repo's
   `.claude/commands/` and commit (they're personal/user-level today).

## Gotchas & notes

1. **`/hcc` + `/clh` are not in the repo.** They live under `C:\Users\bes\.claude\commands\`
   (user-level → every project). A fresh clone on another machine won't have them unless
   promoted to `.claude/commands/` (owner action 4).
2. **No code was written for the AI assistant** — this is a plan only, by the owner's
   choice. Nothing in `nx_lib/`, `templates/`, `static/`, `sql/` changed.
3. **Provider quality vs compliance:** Azure = tenant-resident (compliance default);
   Claude = best T-SQL quality but data leaves the tenant (needs zero-retention terms).
   Either way Phase-1 egress is the question + schema metadata only.
4. **No new dependency** in the plan — it uses the already-present `requests` + `sqlglot`.
   No `deploy.yml` change either (all plan files are runtime-internal or `docs/`-excluded).

## How to verify

```powershell
# Read the plan and confirm the branch state
git -C C:\dev\nexora log -1 --stat
```
```bash
# The /hcc and /clh commands exist at the user level:
#   C:\Users\bes\.claude\commands\hcc.md
#   C:\Users\bes\.claude\commands\clh.md
# Try them: type /clh in a fresh session (loads this handoff), or /hcc to wrap up.
```

To start building Phase 1 later, open the plan and follow Task 1 → Task 7:
`docs/superpowers/plans/2026-06-03-reporting-ai-phase1.md`.

## Resuming in a fresh session

Type **`/clh`** — it will load this handoff, orient you, and ask the gating questions
(most importantly: **execute Phase 1 now?** and the **provider** decision). The plan is
the source of truth for the build; the branch is local and unpushed.
