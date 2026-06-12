---
description: Execute the latest plan autonomously (subagent-driven development), detect natural stop, then merge worktree + hand off
argument-hint: "[optional path to plan file, e.g. docs/superpowers/plans/2026-06-12-foo.md]"
---

Execute the plan autonomously using subagent-driven development. Run **fully autonomously, in
order** — no mid-flow check-ins. `$ARGUMENTS` optionally names a specific plan file; if omitted,
derive it from the latest handoff and plan directory.

## 1. Find the plan and worktree

**Locate the plan file:**

- If `$ARGUMENTS` is a path, use it directly (confirm it exists).
- Otherwise: read `var/handoff-pending` for the latest handoff path, open that handoff, and extract
  the plan file path and worktree info from the "Resuming" / "Next steps" section.
- If no handoff, Glob `docs/superpowers/plans/*.md` and pick the newest by filename date.

**Locate the execution worktree (if any):**

The handoff written by `/write-plan` records a `Worktree:` and `Branch:` line when it created an
isolated worktree. If those lines exist:

```powershell
$worktreePath   = "<path from handoff>"     # e.g. .claude/worktrees/plan-<slug>
$worktreeBranch = "<branch from handoff>"   # e.g. plan/<slug>
```

Verify the worktree still exists: `git worktree list | Select-String $worktreePath`. If it exists,
use **`EnterWorktree`** (if available) to switch into it, or prefix all git/file commands with
`-C $worktreePath`. All execution work happens in the worktree from here on.

If no worktree was recorded (branch was clean during `/write-plan`), proceed in the current directory.

## 2. `main` guard

If the effective working branch is `main`: stop, say so, tell the user to switch branches, do nothing.

## 3. Read the plan

Read the plan file in full. Extract:

- The ordered task list (all `### Task N:` blocks with their checkbox steps)
- The context section (branch, sequencing, anchor points, gotchas)
- Any **Owner actions** or locked decisions that affect execution order

Do **not** start executing yet.

## 4. Execute via subagent-driven development

Invoke the **Skill tool** with `skill: superpowers:subagent-driven-development`, passing the plan
content and full context. Follow that skill's process exactly:

- Fresh subagent per task → spec-compliance review → code-quality review → mark complete → next task
- The skill runs to completion on its own; do not interrupt between tasks

**Natural stop conditions** — when any of these occur, proceed to step 5 rather than continuing:

- All tasks are marked `[completed]` in the TodoWrite list
- A task returns `BLOCKED` **and you cannot resolve the blocker** (missing external dependency,
  conflicting in-flight change, requires owner decision)
- Two consecutive tasks return `BLOCKED` for any reason

Surface the stop reason clearly before moving to step 5.

## 5. Hand off with worktree merge

After the natural stop, invoke the **Skill tool** with:

```
skill: handoff-session-state
args:  "--merge-worktree <slug> execution complete"
```

The `--merge-worktree` flag tells `/handoff-session-state` to:

1. Write the handoff (recording which tasks completed and the stop reason)
2. Commit the handoff
3. **Merge the worktree branch** (`plan/<slug>`) into the parent feature branch
4. Remove the worktree directory
5. Delete the worktree branch
6. Drop the `var/handoff-pending` flag
7. Prompt `/clear`

That command ends your response with its "Type `/clear` now" line — put **nothing** after it.
