---
description: Multi-agent planning run on Fable agents (explore → dual drafts → adversarial review → merge) — write the plan to docs/superpowers/plans/, commit (no push), then chain into /handoff-session-state
argument-hint: "<feature description / plan request, e.g. 'reporting drill-through filters'>"
---

Write a comprehensive nexora implementation plan for: `$ARGUMENTS`. Run **fully autonomously** — front-load any genuinely blocking questions *before* starting the workflow (use `AskUserQuestion`, one batch), then run to completion without mid-flow checkpoints. If `$ARGUMENTS` is empty, ask for the feature description and stop.

## 1. Preflight

- `git branch --show-current` — if on `main`, **stop**: the plan gets committed, and `main` is read-only under nexora git policy (even with explicit permission). Tell the user to switch to a feature branch first and do nothing else.
- Get today's date: `Get-Date -Format yyyy-MM-dd`. Derive `<slug>` (kebab-case, 3–6 words) from `$ARGUMENTS`. Target file: `docs/superpowers/plans/YYYY-MM-DD-<slug>.md`. If that file already exists, pick a more specific slug.
- Read the **two most recent plans** in `docs/superpowers/plans/` — they are the format exemplars.
- Locate and **read** the `superpowers:writing-plans` skill's `SKILL.md` (Glob for it under the plugin/skills directories). Do **not** invoke it via the Skill tool — you need its content as input for the draft agents, not its interactive process.
- Search `docs/superpowers/specs/` for a spec matching the slug. If one exists, the plan must link it and honor its decisions; this command never authors a spec.

## 1.5. Busy-branch worktree isolation

Before starting the planning Workflow, check whether the current branch is being actively worked on:

```powershell
# Condition A — uncommitted changes present
git status --porcelain        # any output → busy

# Condition B — already inside a linked worktree
$gitDir    = git rev-parse --git-dir
$gitCommon = git rev-parse --git-common-dir
# $gitDir -ne $gitCommon → already in a worktree
```

**If either condition is true**, create an isolated worktree for the planning work:

```powershell
$worktreePath = ".claude/worktrees/plan-$slug"
$worktreeBranch = "plan/$slug"
git worktree add $worktreePath -b $worktreeBranch
```

Then use the **`EnterWorktree`** tool (if available) to switch the session into that path, or prefix
all subsequent git/file commands with the worktree path. **All steps from here on — plan file write,
anchor verification, commit, and handoff — run inside the worktree.**

Record the worktree path and branch in a variable (`$worktreePath`, `$worktreeBranch`) — the handoff
doc (step 6) must include them so `/execute-plan` knows where to resume.

**If neither condition is true**, proceed in the current directory — no worktree needed.

## 2. Run the planning Workflow (Fable, multi-agent)

Use the **Workflow tool**: author the orchestration script now, then run it. Contract — non-negotiable:

- **Every agent uses `model: 'fable'`.** This is design work; do not downgrade any agent.
- Every agent returns findings as **structured output** (define an output schema per agent). Agents never write files — only you, the orchestrating session, write the final plan in step 3.
- Pass every agent the **verbatim** `$ARGUMENTS`, the slug, and the outputs of earlier phases it depends on, embedded in its prompt.
- **Script rules:** plain JavaScript only — no TypeScript annotations, no `import` statements. Use `async`/`await`; parallelize within a phase via `Promise.all`. Define the prompt-builder helpers and output schemas above the orchestration block.

Shape contract (adapt identifiers to the Workflow tool's actual schema; the structure — 3 parallel, then 2 parallel, then 2 sequential, all on `fable` — is fixed):

```js
// Helpers reconPrompt/precedentPrompt/choresPrompt/draftPrompt/redTeamPrompt/mergePrompt
// and the *Schema objects are defined above this block, in the same script.
const ctx = { request: ARGUMENTS, slug: SLUG, today: TODAY };

// Phase 1 — explore (parallel)
const [recon, precedent, chores] = await Promise.all([
  agent({ name: 'code-recon',  model: 'fable', prompt: reconPrompt(ctx),     output: findingsSchema }),
  agent({ name: 'precedent',   model: 'fable', prompt: precedentPrompt(ctx), output: findingsSchema }),
  agent({ name: 'chore-sweep', model: 'fable', prompt: choresPrompt(ctx),    output: findingsSchema }),
]);

// Phase 2 — dual drafts (parallel, opposed stances)
const phase1 = { recon, precedent, chores };
const [draftA, draftB] = await Promise.all([
  agent({ name: 'draft-minimal',    model: 'fable', prompt: draftPrompt(ctx, phase1, 'minimal-diff incrementalist'), output: draftSchema }),
  agent({ name: 'draft-structural', model: 'fable', prompt: draftPrompt(ctx, phase1, 'structural refactorer'),       output: draftSchema }),
]);

// Phase 3 — adversarial review, then merge (sequential)
const findings  = await agent({ name: 'red-team', model: 'fable', prompt: redTeamPrompt(ctx, draftA, draftB),          output: reviewSchema });
const finalPlan = await agent({ name: 'merge',    model: 'fable', prompt: mergePrompt(ctx, draftA, draftB, findings),  output: planSchema });

return finalPlan;
```

If the Workflow tool is unavailable in this session, fall back to dispatching the same seven agents as parallel subagents (see `superpowers:dispatching-parallel-agents`), preserving the phase ordering and the structured-output contract.

**Phase 1 — Explore (3 agents, parallel):**

- *Code recon* — map every file/route/template/JS-partial/symbol the feature touches. Use GitNexus (`gitnexus_query`, `gitnexus_context`, `gitnexus_impact` on symbols the plan will edit) plus Grep; if GitNexus MCP tools are unavailable inside the agent, fall back to Grep/Read and say so in the output. Returns: file list with responsibilities, anchor points as **function names + quoted code snippets** (never line numbers), blast-radius notes.
- *Precedent* — find the closest existing nexora feature(s) and how they solved the same shape of problem (route + template + `templates/js/_*_js.html` partial + permission + tests). Returns: patterns to copy, file pairs, test exemplars.
- *Chore sweep* — enumerate the non-code chores this feature implies: SQL migration (`sql/_migrations/<Db>/NNNN_*.sql`) yes/no, permission codes + `page_visibility()`, i18n (pybabel cycle, de/fr/it), `CHANGELOG.md`, docs to touch (`docs/howto/*`, `CLAUDE.md` references), deploy-exclude additions in `.github/workflows/deploy.yml`, e2e constraints (TEST env has no Statistics DB), Jinja template-cache restart note. Also check the most recent plans + handoffs in `docs/superpowers/` for **in-flight work that conflicts or sequences** with this feature.

**Phase 2 — Draft (2 agents, parallel):** each receives all Phase 1 findings, the writing-plans skill content, and one recent plan as exemplar. Both produce a complete draft plan (full markdown) as structured output. Give them different stances:

- Draft A: *minimal-diff incrementalist* — smallest safe change, maximal reuse of existing code.
- Draft B: *structural* — willing to refactor/extract where it makes the feature and its tests cleaner.

**Phase 3 — Adversarial review + merge (sequential):**

- *Red-team agent* — attacks both drafts **against the live repo** (it must Grep/Read to verify, not reason from memory): fabricated paths/symbols/APIs, wrong anchors, tasks too big (each step must be one 2–5 min action), missing test-first steps, missing chores from the sweep, sequencing conflicts with in-flight plans, scope creep vs YAGNI, untestable acceptance criteria. Returns: numbered findings with severity, each tagged to a draft.
- *Merge agent* — receives both drafts + all findings; produces the **final plan markdown**, resolving every finding (fix or explicitly justify), taking the best of each draft.

## 3. Write the plan file

Write the merge agent's output to `docs/superpowers/plans/YYYY-MM-DD-<slug>.md`, conforming to nexora plan conventions (compare against the exemplars from step 1):

- Title `# <Feature> — Implementation Plan`, then this exact header on the next line:

  ```markdown
  > **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
  ```

- Bold **Goal:** / **Architecture:** / **Tech Stack:** lines; link the spec if one exists.
- `## Context an engineer needs (read first)` — branch, sequencing/blockers vs in-flight plans, anchor-on-snippets rule (never line numbers), template-cache restart, e2e constraints, pre-commit hook escape hatch (`SQL_SYNC_SKIP=1 git commit ...`), i18n cycle, "migrations needed: yes/no".
- A **Decisions locked in** table; anything unresolved goes to an **Owner actions** section instead of being silently assumed.
- `# PHASE N` sections → `### Task N:` blocks with bite-sized checkbox steps (write failing test → run it → implement → run green → commit), exact commands, and a paste-ready conventional-commit message per task.
- **Gotchas & notes** section at the end.

## 4. Verify anchors (no fabrication ships)

For **every** file path named in the final plan: confirm it exists (or is explicitly marked "new file"). For every quoted code snippet: Grep it verbatim. For every named symbol: Grep its definition. Fix any miss yourself — re-query the repo, correct the anchor. Do not commit a plan containing an unverified anchor.

## 5. Commit (nexora policy — see CLAUDE.md "Git")

- If GitNexus is connected, run `gitnexus_detect_changes()` first (docs-only change — expect zero affected symbols).
- Stage **only** the plan file. Commit on the feature branch — **no push, no PR** (remote policy: stop at commit; the owner pushes).
- **gitlint will reject** (avoid retries): subject imperative, ≤72 chars, no trailing period; a **non-empty body** (blank line, then prose wrapped ≤100 chars/line); end with the current model's `Co-Authored-By` trailer. Use `git commit -F -` with a here-doc. Paste-ready template:

  ```
  docs(plans): add <slug> implementation plan

  Multi-agent planning run (explore, dual drafts, adversarial review, merge)
  for: <one-line feature summary>. All file/symbol anchors verified against
  the live repo; sequencing vs in-flight plans noted in the plan header.

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  ```

- If the pre-commit SQL hooks fail (INT unreachable, or the known `SchemaMigrations` CRLF-checksum drift), prefix with `SQL_SYNC_SKIP=1` — **never** `--no-verify`.

## 6. Hand off

After the commit lands, invoke the **Skill tool** with `skill: handoff-session-state` and
`args: "<slug> plan — resume at docs/superpowers/plans/YYYY-MM-DD-<slug>.md"`.

**Do NOT pass `--merge-worktree`.** The worktree (if created in step 1.5) must stay open — it is
the execution vessel for `/execute-plan`. The handoff doc must record:

- The plan file path
- The worktree path and branch (if a worktree was created), e.g.:
  `Worktree: .claude/worktrees/plan-<slug>  Branch: plan/<slug>`

`/execute-plan` reads this to know where to resume. Do not skip this step and do not merely mention
it — call the Skill tool. That command ends your response with its "Type `/clear` now" line —
put **nothing** after it.

Working directory: C:\dev\nexora (check with git status first to confirm branch and cleanliness).
