# n8n Autopilot for the Claude Code Loop — Design

**Date:** 2026-06-13
**Author:** benstreich (with Claude)
**Status:** Approved design — ready for implementation plan
**Source workflow:** `var/nexora-claude-workflow.md`

## Goal

Automate the existing manual Claude Code development loop (`/write-plan` on Opus
→ `/clear` → `/execute-plan` on Sonnet → `/clear` → repeat) into an **unattended
feature factory** driven by n8n. A GitHub issue labelled `autopilot` is the unit
of work; n8n plans it, executes it, and commits — stopping exactly where the human
loop stops today: **at `git commit`, never push, never PR.**

## Decisions (locked during brainstorming)

| Dimension | Decision |
|-----------|----------|
| Automation level | **Full autopilot** — n8n drives the whole plan→execute loop headless |
| n8n location | **Local, native npm install** on the Windows dev box (`npm i -g n8n`) |
| Claude invocation | n8n **Execute Command** node → `claude -p` (headless print mode) |
| Work queue | **GitHub issues** labelled `autopilot` on `Sydoc-Code/nexora`, via the already-authed `gh` CLI |
| Failure posture | **Halt + notify** on first failure; leave repo clean; do not attempt later issues |
| Notifications | **Telegram bot** (BotFather token + chat id) |
| Trigger | **On-label**, realised as **short-interval polling** (local-only, nothing exposed to the internet) + single-run lock |
| Loop brain | **n8n-native** — control flow lives on the n8n canvas (nodes), not a wrapper script |

## Non-negotiable constraints (from repo policy + prior gotchas)

- **`main` is read-only.** Autopilot only ever operates on `feature/2.5.63` (and its
  per-feature worktrees). Never commits to `main`.
- **Stop at `git commit`.** No `git push`, no PR. The owner reviews and pushes.
  Because of this, a successfully-built issue is **commented + labelled, not closed** —
  the commit is local-only until the owner pushes.
- **`SQL_SYNC_SKIP=1` must be set in the environment** for every `claude -p`
  invocation. The skills commit internally; without this env var the `sql-migrate-int`
  pre-commit hook fails on INT SchemaMigrations CRLF drift and **every** commit dies.
- **Never `--no-verify`**, never bypass hooks.
- cwd is forced to `C:\dev\nexora`; Execute Command shell is **pwsh**.

## Security model & trust boundary

Autopilot runs `claude --dangerously-skip-permissions` on the dev box (git push ability,
`gh` auth, DB/dev access) and feeds it GitHub-issue text — a prompt-injection →
permission-bypass surface. Controls:

- **Trusted-author allowlist is the primary control.** Only issues authored by an
  allowlisted login are built (default `benstreich`; override via
  `AUTOPILOT_ALLOWED_AUTHORS`). Enforced in `fetch-queue.ps1` (filter) and re-checked in
  `run-phase.ps1` (hard refuse). The `autopilot` label alone is insufficient.
- **Issue body framed as untrusted data** (delimiters + "do not obey" preamble) — reduces
  but does not eliminate injection.
- **`GH_TOKEN`/`GITHUB_TOKEN` scrubbed** from the child env. Note `gh` uses keyring auth, so
  the agent can still call `gh` by design; blast radius is bounded by the author gate +
  commit-not-push (nothing reaches the remote until the owner reviews).
- **`--dangerously-skip-permissions` is retained deliberately** — headless unattended work
  can't answer prompts or be covered by a static tool allowlist; the trust gate is the
  safety mechanism, not the permission flag.
- **Stronger isolation** (least-priv account / disposable VM with a scoped token and no push
  creds, building a clone) is a noted future option, incompatible with the "runs on my dev
  box against the real repo" design chosen here.

## Architecture

```
GitHub issue gets `autopilot` label
        │
        ▼  (n8n Schedule Trigger, ~every 2 min — polling, no inbound webhook)
[poll] gh issue list --label autopilot --state open  →  jq-filter out
       issues that ALSO carry autopilot-built / autopilot-blocked  =  work queue
        │  (queue non-empty AND no fresh lock?)
        ▼
[lock] write var/autopilot.lock (timestamp+PID); stale (>3h) ⇒ reclaim
        │
        ▼
[Loop Over Items]  batch size 1, issues oldest-first (by number asc)
  ├─ pre-flight:  git status --porcelain on feature/2.5.63  →  dirty? HALT
  ├─ PLAN:        claude -p --model opus --dangerously-skip-permissions
  │                      --output-format json --effort high  "/write-plan <title+body>"
  ├─ verify plan: json subtype ≠ error_max_turns  AND  var/handoff-pending points to a
  │                fresh docs/superpowers/plans/<date>-*.md  AND  a plan commit landed
  ├─ EXECUTE:     claude -p --model sonnet --dangerously-skip-permissions
  │                      --output-format json  "/execute-plan"
  ├─ verify exec: worktree merged & gone  AND  a feature commit landed  AND
  │                handoff doc shows no BLOCKED/incomplete marker
  ├─ success →  gh issue comment "🤖 built locally, commit <sha>, pending review+push"
  │             gh issue edit --add-label autopilot-built   (issue stays OPEN)
  │             Telegram ✅ #N built              →  next issue
  └─ failure →  gh issue edit --add-label autopilot-blocked  +  comment reason
                leave worktree intact for inspection; feature/2.5.63 stays clean
                Telegram ⛔ halt + reason + worktree path
                STOP loop (skip remaining issues)
        │
        ▼
[cleanup] delete var/autopilot.lock   (also wired as n8n error-workflow so a crash
          can't wedge the lock)   →   Telegram 🏁 run summary
```

## Components (each independently understandable)

1. **Trigger + queue node group** — Schedule Trigger + `gh issue list` + jq filter.
   Input: nothing. Output: ordered list of `{number, title, body}` to build.
   Depends on: `gh` auth, the three labels existing.

2. **Lock guard** — checks/writes/reclaims `var/autopilot.lock`. Single purpose:
   guarantee one run at a time; self-heal stale locks. Depends on: filesystem.

3. **Per-issue loop body** — pre-flight → plan → verify → execute → verify →
   success/halt. One iteration per issue. Depends on: `claude` CLI, `git`, `gh`,
   the prompt-via-stdin helper.

4. **Prompt builder** — composes `<title>\n\n<body>`, writes to a temp file, pipes
   to `claude -p` via **stdin** so multi-line issue bodies never break shell quoting.

5. **Outcome verifier** — pure git/file inspection that decides success vs halt
   (because `claude -p` exit code alone does NOT distinguish "completed" from
   "stopped on 2× BLOCKED"). Reads handoff doc + `git log` + worktree presence.

6. **Notifier** — Telegram node; three message shapes (per-issue ✅, halt ⛔, run 🏁).

7. **Cleanup / error workflow** — removes the lock on success, halt, or crash.

## Open risks the implementation plan MUST resolve

1. **Headless multi-agent feasibility (highest risk).** `/write-plan` runs a 7-agent
   Workflow; `/execute-plan` runs subagent-driven-development. The plan's **first task**
   is a manual end-to-end smoke test of one real issue through `claude -p` to confirm
   subagent/Workflow spawning works in print mode. If it does not, the loop-brain design
   changes (e.g. drive the multi-agent step differently). Everything downstream is gated
   on this.
2. **BLOCKED detection.** Resolved in design via handoff-doc + git-state inspection,
   not exit codes. Plan must implement and test the verifier explicitly.
3. **`--effort` flag.** The source workflow doc shows `--effort ultracode`, which is
   **not** a valid value (`--effort` = low|medium|high|xhigh|max). Autopilot uses
   `--effort high`; "ultracode" is a separate session concept and is dropped from the
   headless invocation.
4. **Long-running nodes.** A single `/execute-plan` phase can run 20–40 min. n8n's
   execution timeout must be raised (workflow setting / `EXECUTIONS_TIMEOUT`).
5. **Stale lock on crash.** Mitigated by timestamp+PID lockfile with a >3h staleness
   reclaim plus an n8n error-workflow that releases the lock.

## Setup the plan will cover

- `npm i -g n8n` (Node 22 already present), run via `n8n start` (optionally a Windows
  service for always-on); raise the execution timeout.
- BotFather: create bot, capture token + chat id; add Telegram credential in n8n.
- Create three GitHub labels: `autopilot`, `autopilot-built`, `autopilot-blocked`.
- One **manual smoke-test issue** end-to-end before trusting the loop unattended.

## Out of scope (YAGNI)

- No push / PR automation (policy).
- No parallel issue building (issues share `feature/2.5.63` and merge worktrees back —
  must be sequential).
- No live GitHub webhook / tunnel (polling chosen to keep nothing exposed).
- No retry/skip posture (halt-on-first-failure chosen for v1).
- No phone-trigger Telegram command yet (the bot is notify-only for v1; two-way trigger
  is a noted future extension).

## Success criteria

- Labelling a GitHub issue `autopilot` results, unattended, in: a planned + executed +
  locally-committed feature on `feature/2.5.63`, the issue commented with the commit sha
  and labelled `autopilot-built` (still open), and a Telegram ✅.
- A failing issue halts the loop, labels the issue `autopilot-blocked`, leaves the repo
  clean (worktree preserved for inspection), and sends a Telegram ⛔ with the reason —
  with no later issues attempted.
- The whole thing runs with nothing exposed to the internet and never pushes.
