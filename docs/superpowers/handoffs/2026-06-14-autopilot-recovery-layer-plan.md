# Handoff — Spec + Plan written: autopilot recovery layer (diagnose · escalate · skip)

**Date:** 2026-06-14 (evening) · **Branch:** `feature/2.5.63` · **179 commits unpushed** · **commit-only (remote)**
**Prior handoff:** `docs/superpowers/handoffs/2026-06-14-push-feature-branch-fix-gate-plan.md`
**The spec this hands off:** `docs/superpowers/specs/2026-06-14-autopilot-recovery-layer-design.md` (`da4fa12`)
**The plan this hands off:** `docs/superpowers/plans/2026-06-14-autopilot-recovery-layer.md` (`59d1b22`)

## TL;DR

- User's complaint: the n8n autopilot "stops on almost every issue." Root cause: it makes **one**
  fixer pass then **halts the whole run** (the first bad issue freezes the queue), with diagnosis-free
  halt comments.
- Designed (didn't build) a **recovery layer**: a deterministic infra probe + an LLM **diagnostician**
  that classifies *why* a halt happened, a **2-attempt escalation ladder**, **smart-skip** loop
  semantics (skip one stuck issue & continue; stop the whole run only on a **deterministically-computed
  `poison`** state), **pre-plan triage** that asks the owner before building a vague issue, and a
  Telegram clarify-reply round-trip.
- Both artifacts are **adversarially red-teamed and committed**: the spec (4-lens review, 37 findings —
  4 blockers + 10 majors folded in) and the plan (12 findings — 2 blockers + 3 majors resolved by the
  merge agent, then independently anchor-verified against the live repo).
- **Nothing is built yet.** Next session runs `/execute-plan` on the plan.

## This session's commits (oldest→newest, after prior handoff `636b0f4`)

```
da4fa12 docs(autopilot): spec the diagnose/escalate/skip recovery layer
59d1b22 docs(plans): add autopilot recovery-layer implementation plan
```
(`6e1d4d7 chore(i18n)` below them in `git log` is the autopilot's own #93 run from earlier, not this
session.)

## What shipped

| File | Commit | What |
|---|---|---|
| `docs/superpowers/specs/2026-06-14-autopilot-recovery-layer-design.md` (new) | `da4fa12` | The design: failure taxonomy, deterministic-poison rule, per-script crash-proof output contract, n8n canvas rewire, two new trust surfaces + controls, 8-step build order |
| `docs/superpowers/plans/2026-06-14-autopilot-recovery-layer.md` (new, 1843 lines) | `59d1b22` | 8-phase, test-first implementation plan: 7 new files + edits to 8 existing, each task with a runnable pwsh assertion and a paste-ready commit |

## Next steps (ordered) — for `/execute-plan` or a human

Resume at **`docs/superpowers/plans/2026-06-14-autopilot-recovery-layer.md`**, top. Phases:

1. **Phase 1** — `probe-infra.ps1` + `RECOVERY-PLAYBOOK.md` + `cost-guard.ps1 -Cost` mode (pure, offline-testable).
2. **Phase 2** — per-issue `baseline` (run before `clean?`) + per-issue `run.log` header in `run-phase.ps1`.
3. **Phase 3** — refactor `solve-blocked.ps1` → `fix-attempt.ps1` (`-SinceSha`, `costUsd`, ALREADY-DONE corroboration).
4. **Phase 4** — `diagnose-halt.ps1` (deterministic guards + constrained read-only classifier + evidence framing).
5. **Phase 5** — `recover.ps1` (ladder + deterministic poison + child-stdout capture + top-level try/catch + attempts ledger) + edits to `comment-result.ps1` / `setup-labels.ps1` / `fetch-queue.ps1`.
6. **Phase 6** — `triage.ps1` + the n8n canvas rewire (swap node, Switch + fallback + collector, move baseline, triage branch, Telegram nodes).
7. **Phase 7** — `n8n-clarify-reply.workflow.json` + `run-phase.ps1` author-checked clarification pull.
8. **Phase 8** — the six-case interactive smoke gate (OWNER action — live n8n + INT), then Activate.

Each PowerShell task is test-first: write the `tests/*.assert.ps1`, run it RED, implement, run GREEN,
commit. Use **subagent-driven-development** (fresh subagent per task) or `/execute-plan`.

## Gotchas & notes (READ)

- **The live autopilot stashes your untracked files.** It bit this session — the fixer's pre-flight
  `git stash push -u` swept the in-progress spec into `stash@{0}` while building #93. Before any long
  uncommitted work in `C:\dev\nexora`: confirm `pwsh -NoProfile -File tools/autopilot/fetch-queue.ps1`
  prints `[]` (empty queue ⇒ no run starts) and `var/autopilot.lock` is absent; **commit each task as
  soon as it is green**. Recover a stashed untracked file via `git checkout "stash@{N}^3" -- <path>`.
- **Fable 5 is unavailable on this box** (both the spec review and the planning run failed on
  `claude-fable-5`). Agents ran on **Opus 4.8** (the strongest available — preserves "don't downgrade
  design work"). If a future skill mandates Fable, expect the same and substitute.
- **Two red-team blockers in the plan were real and are fixed** (verify they survive execution): a TDD
  harness that couldn't go green on a clean checkout (fixed via `-SkipDeterministicGates`), and a
  **dead triage regex** `-match …,'Singleline'` that always returns `False` (fixed to `(?s)…` — I
  confirmed live the comma form is `False` and `(?s)` captures multiline). Also the `-SinceSha`
  plan-commit trap (a bare plan commit must not count as a feature commit) and the `--allowedTools`
  flag (confirmed real via `claude --help`).
- **Test mechanism is standalone pwsh assertions + `Parser::ParseFile`** — **no Pester 5** on this box
  (only legacy 3.4.0; no `*.Tests.ps1`, no `tests/` dir). The plan creates `tools/autopilot/tests/`.
- **This session had no git worktree.** The shell cwd was the empty `.claude/worktrees/plan-
  reporting-page-improvement-options` scratch subdir, but `git rev-parse --show-toplevel` resolves to
  `C:\dev\nexora` — it's a plain subdir of the main repo, same `.git`, same HEAD. All work happened
  directly on `feature/2.5.63`. **Use absolute repo-root paths when executing.**
- **SQL_SYNC_SKIP=1 on every commit** (INT `SchemaMigrations` CRLF drift fails the `sql-migrate-int`
  pre-commit hook on Windows; `.gitattributes` still has no `*.sql eol=lf`). Never `--no-verify`.
- **n8n re-import is destructive of edges** — import the rewired workflow only via `start-n8n.ps1`
  (keeps `executeCommand` enabled), then verify all Switch routes + the fallback + loop-back edges
  survived. The Switch needs typeVersion 3.x with the Fallback Output enabled (n8n 2.8.4 confirmed).

## Untracked / left for owner (Owner actions in the plan, can't run unattended)

- **#0 — confirm `claude --allowedTools` is honoured** on this box (`claude -p --allowedTools Read
  'reply OK'`) BEFORE Phase 4 relies on it; fallback `--permission-mode plan`.
- Run `setup-labels.ps1` once (creates `autopilot-needs-input`).
- Re-import the rewired `n8n-autopilot.workflow.json` (workflow `PzQXpt99pIIV7fJv`) via `start-n8n.ps1`;
  wire the 4 new Telegram nodes to `autopilot-telegram` + chat id; import `n8n-clarify-reply.workflow.json`;
  set the Error Workflow; run the 6-case smoke gate; then **Activate**.
- Nothing is uncommitted this session (tree clean). No code changed yet — only the spec + plan docs.

## How to verify

```powershell
git log --oneline -2    # -> 59d1b22 docs(plans)... ; da4fa12 docs(autopilot)...
git status --short      # -> clean
pwsh -NoProfile -File tools/autopilot/fetch-queue.ps1   # -> [] (autopilot idle; safe to work)
# the plan and spec exist:
Test-Path docs/superpowers/plans/2026-06-14-autopilot-recovery-layer.md
Test-Path docs/superpowers/specs/2026-06-14-autopilot-recovery-layer-design.md
```

## Resuming in a fresh session

`/reset-session` (the flag in `var/handoff-pending` points here). **Several handoffs share today's
date** — if the flag is gone, run
`/reset-session docs/superpowers/handoffs/2026-06-14-autopilot-recovery-layer-plan.md` to target this
file. Then open `docs/superpowers/plans/2026-06-14-autopilot-recovery-layer.md` and run `/execute-plan`
(or work it task-by-task with subagent-driven-development). No worktree — execution runs on
`feature/2.5.63` directly in `C:\dev\nexora`.
