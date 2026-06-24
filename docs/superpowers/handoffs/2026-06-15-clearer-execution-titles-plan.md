> ⏭️ **Newer same-date handoff:** `docs/superpowers/handoffs/2026-06-15-autopilot-concurrent-issues-plan.md` supersedes this one for resuming. Use `/reset-session <path>` to target a specific file.

# Handoff — clearer-execution-titles plan written

**Date:** 2026-06-15 (plan-only session) · **Branch:** `feature/2.5.63` · **202 commits unpushed** · **commit-only (remote)**
**Prior handoff:** `docs/superpowers/handoffs/2026-06-14-watchdog-run-modes-comment-plan.md`
**Durable context also in auto-memory:** `project_n8n_autopilot` (the autopilot loop that filed this issue).

## TL;DR

- A `/write-plan` run produced an implementation plan for GitHub issue *"Clearer Execution title name"*
  (#94-style run identification, filed through the autopilot).
- **Deliverable is the plan only** — no code change yet. The feature: make it obvious which GitHub
  issue an autopilot run is building (and for how long) on two surfaces — (A) `nx status` / `nx -s`
  prints `autopilot: #<n> <title>  -- building <elapsed> (<phase>)`, the canonical surface; (B) all
  four per-item n8n Telegram notifications name the issue title alongside its number.
- **Next session: execute the plan** — 8 tasks across 5 phases. Resume at
  `docs/superpowers/plans/2026-06-15-clearer-execution-titles.md`.

## This session's commits (only one authored here)

```
5d5687e docs(plans): add clearer-execution-titles implementation plan
```

Note: `92cc8d3 feat(autopilot): bot identity for the autopilot's own comments only` also appeared on
the branch during this session but was **NOT authored by this session** — a background autopilot/agent
committed it onto `feature/2.5.63`. Left as-is; flag to the owner if unexpected.

## What shipped

| Area | File | Commit |
|------|------|--------|
| Plan | `docs/superpowers/plans/2026-06-15-clearer-execution-titles.md` | `5d5687e` |

The plan was produced by a 7-agent Workflow (3 explore → 2 dual drafts → red-team → merge).
**Fable 5 was unavailable** (Mythos-access outage), so the agents ran on **Opus** instead of Fable.
The red-team agent attacked both drafts against the live repo; all 8 findings were resolved in the
merge. After the merge I independently re-verified **every** anchor against the live repo:
- `bin/nx.ps1`: `status` arm `Write-Ok "Running  (PID $($p.Id) ..."`, the `$AppDir = Split-Path -Parent
  (Split-Path -Parent $MyInvocation.MyCommand.Definition)` def, `Write-Dim` helper, the `-s/--status`
  help row — all confirmed.
- `tools/autopilot/lock.ps1`: `LastWriteTime` mtime idiom, the `stream-json`/`--remote-control` claude
  probe, `$MaxAgeHours = 3.0` — confirmed (the plan's `nx status` helper mirrors these exactly, and
  explicitly forbids `[datetimeoffset]::Parse`, which throws at runtime).
- `tools/autopilot/run-phase.ps1`: the run.log header `=== $Phase #$IssueNumber ===`, the plan-branch
  `gh issue view ... --json title,body,author,comments`, the `Select-Object -Last 1` final-stdout
  contract — confirmed.
- `n8n-autopilot.workflow.json`: `run-exec` command is the literal `pwsh ... -Phase execute` (no `=`,
  no `-IssueNumber`); all four notify node texts (`notify-built`/`notify-recovered`/`notify-skip`/
  `notify-questions`) match the plan's "from" strings; `split-to-items` maps `q.map(i => ({ json: i }))`
  so `.title` propagates to the `Loop Over Items` item — confirmed.
- `tools/autopilot/start-n8n.ps1`: the `$lock = '...autopilot.lock'` / `Remove-Item $lock` cleanup
  block — confirmed (plan adds a sibling run-state cleanup beside it).
- Test patterns: `canvas-args.assert.ps1` uses `Assert([bool]$cond,[string]$msg)`; `readme-signals.
  assert.ps1` uses `Assert($label,$cond)` — the plan correctly uses each file's distinct signature.
- `docs/howto/nx.md` status rows, `CHANGELOG.md` `[Unreleased]`/`### Added`, `deploy.yml` `/XD tools`
  + `/XF nx.ps1` — confirmed (no deploy change needed).

## Next steps (ordered)

1. **Execute the plan** — `docs/superpowers/plans/2026-06-15-clearer-execution-titles.md`. Phases:
   - **Phase 0 / Task 0** — read-only ground-truth re-verification + green test baseline.
   - **Phase 1** — Task 1 `run-phase.ps1` writes/preserves `var/autopilot/run-state.json`; Task 2
     thread `-IssueNumber` into the `run-exec` n8n node; Task 3 clear leaked run-state on n8n startup.
   - **Phase 2** — Task 4 `nx status` shows the in-flight issue (new `Get-AutopilotStatusLine` helper);
     Task 5 help-text + `lock.ps1` cross-ref comment.
   - **Phase 3** — Task 6 add `<title>` to all four Telegram notify nodes.
   - **Phase 4** — Task 7 docs/changelog sync (CHANGELOG, nx.md, README, SIGNALS, readme-signals test).
   Each code task is TDD: write the `*.assert.ps1` test (red) → implement → run green → commit with
   `SQL_SYNC_SKIP=1`.
2. **Stop at commit** (remote session) — do **not** push or open a PR; the owner pushes.

## Gotchas & notes

- **Nothing is broken.** Planning-only session; the working tree is clean, the only artifact authored
  here is the committed plan file.
- **The plan's own per-task commit trailers say `Claude Fable 5`** (the requested planning model). Since
  Fable was unavailable, the agents ran on Opus; my commit of the plan file used the accurate
  `Claude Opus 4.8` trailer. Adjust execution-commit trailers to whatever model executes if you care.
- **`nx status` elapsed math MUST use the file `LastWriteTime`, never `[datetimeoffset]::Parse`** — the
  latter throws (`datetime - datetimeoffset` has no operator) and would crash `nx status` the instant a
  real build runs. This was red-team finding F1; the plan's Task 4 test invokes the helper behaviourally
  (absent/fresh/stale) to catch any regression.
- **Run-state survives plan→execute and is NOT cleared per phase.** `run-plan` and `run-exec` are
  separate processes; only the plan phase has the title. Clearing happens only at `start-n8n.ps1`
  startup (crash-leak cleanup). Deleting per phase would blank the title during execute.
- **n8n is NOT auto-deployed.** The workflow JSON edits (Task 2 + Task 6) do nothing until the owner
  re-imports `n8n-autopilot.workflow.json` into the live n8n and re-activates — see the plan's
  **Owner actions** section. `tools/` is `/XD`-excluded, so prod never sees it either way.
- **One n8n execution loops the whole queue** (`splitInBatches` "Loop Over Items"), so the execution
  cannot be named per issue — identification is per-ITEM (the Telegram nodes), not per-execution. Any
  node reference must keep the exact node name `Loop Over Items` (with the space).

## Untracked / left for owner

- Nothing untracked from this session. The plan's **Owner actions** (re-import the n8n workflow,
  confirm Telegram renders `#<n> <title>` and run.log shows `execute #<n>`) are deferred to execution.
- `92cc8d3` (bot-identity commit) landed on the branch via a background process, not this session.
- `var/handoff-pending` points at this file (gitignored — not committed).

## How to verify

```powershell
git log -1 --stat                                                    # 5d5687e, the plan file
Get-Content docs/superpowers/plans/2026-06-15-clearer-execution-titles.md   # read the plan
# Existing autopilot test baseline (run during execution, all should end ALL PASS):
Get-ChildItem C:\dev\nexora\tools\autopilot\tests\*.assert.ps1 | ForEach-Object { $_.Name; pwsh -NoProfile -File $_.FullName }
```

## Resuming in a fresh session

`/reset-session` (this file is flagged in `var/handoff-pending`). It is the only handoff dated
2026-06-15, so no tie-break is needed; if `/reset-session` ever picks the wrong file, run
`/reset-session docs/superpowers/handoffs/2026-06-15-clearer-execution-titles-plan.md`. Then run
`/execute-plan` (or open the plan directly) and implement
`docs/superpowers/plans/2026-06-15-clearer-execution-titles.md` — 8 tasks, TDD, ~30–45 minutes.
