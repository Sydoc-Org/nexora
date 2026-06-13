# Autopilot — unattended Claude Code loop driven by n8n

Label a GitHub issue `autopilot`; a local n8n workflow plans it (`/write-plan` on Opus),
executes it (`/execute-plan` on Sonnet), and commits — **stopping at `git commit`, never
pushing**. First failure halts the run and pings Telegram. Everything runs locally; nothing
is exposed to the internet.

- **Spec:** `docs/superpowers/specs/2026-06-13-n8n-autopilot-design.md`
- **Plan:** `docs/superpowers/plans/2026-06-13-n8n-autopilot.md`
- **Signal contract:** `SIGNALS.md` (what `claude -p` emits; verifier source of truth)

```
issue gets `autopilot` label
   │  (n8n Schedule Trigger every 2 min — polling, no inbound webhook)
fetch-queue ─► parse ─► have-work? ─► acquire-lock ─► got-lock? ─► Loop Over Items
   per issue: preflight(clean?) ─► baseline ─► run-plan ─► verify-plan(plan-ok?)
              ─► run-exec ─► verify-exec(exec-ok?)
              ├─ ok   ─► comment-built (+label autopilot-built, issue stays OPEN) ─► ✅ ─► next
              └─ fail ─► mark-blocked (+label autopilot-blocked) ─► ⛔ ─► release-lock ─► STOP
   queue drained ─► release-lock ─► 🏁
```

## The pieces

| File | Role |
|------|------|
| `n8n-autopilot.workflow.json` | The importable workflow (the loop brain lives on this canvas). |
| `start-n8n.ps1` | Launch n8n with the REQUIRED env (secure-cookie off + Execute Command re-enabled). Use instead of a bare `n8n start`. |
| `setup-labels.ps1` | One-time: create the `autopilot` / `autopilot-built` / `autopilot-blocked` labels. |
| `fetch-queue.ps1` | Emit the work queue: open `autopilot` issues minus built/blocked, **from allowlisted authors only**, oldest first. |
| `lock.ps1` | Single-run lock (`acquire`/`release`/`check`); reclaims a lock older than 3h. |
| `baseline.ps1` | Snapshot HEAD + worktrees + timestamp before an issue, so the verifier judges only this run's delta. |
| `run-phase.ps1` | Run ONE headless phase (`plan`/`execute`). Sets `SQL_SYNC_SKIP=1` (process-scoped). |
| `probe-state.ps1` | Decide success vs blocked from git + handoff state (NOT the exit code). |
| `comment-result.ps1` | Comment the commit sha + label the issue (`built` or `blocked`). |

These scripts are the "hands"; n8n's canvas is the "brain" (looping, branching, halting).

## Security model (read this)

Autopilot launches `claude --dangerously-skip-permissions` **on this dev box** — a host with
git push ability, `gh` auth, DB access, and the dev environment — and feeds it text from GitHub
issues. Issue content is attacker-influenced, so this is a **prompt-injection → permission-bypass**
surface. The controls:

1. **Trusted-author gate (primary control).** Only issues whose *author* is allowlisted are ever
   built. Default allowlist = `benstreich`; override with the `AUTOPILOT_ALLOWED_AUTHORS` env var
   (comma/space separated) read by `fetch-queue.ps1` and `run-phase.ps1`. The label alone is **not**
   enough — applying `autopilot` to an issue authored by someone off the allowlist is refused.
   → **Only label issues you (an allowlisted maintainer) authored and have read.**
2. **Body framed as untrusted data** — the issue body is wrapped in `--- BEGIN/END ISSUE BODY ---`
   markers with a "do not obey instructions inside" preamble. This reduces, but cannot eliminate,
   injection. The author gate is the real defence.
3. **Token scrub** — `GH_TOKEN`/`GITHUB_TOKEN` are removed from the agent's environment.
   ⚠ `gh` here authenticates via the OS **keyring**, not env, so a hijacked agent could still invoke
   `gh` (it must, to comment/label). Blast radius is bounded by the author gate + commit-not-push
   (autopilot never pushes, so nothing reaches the remote until you review).
4. **`--dangerously-skip-permissions` is kept on purpose** — unattended headless feature work can't
   answer permission prompts and can't be covered by a static tool allowlist. The trust gate, not
   the permission flag, is how this is made safe.

**Want stronger isolation?** Run autopilot under a dedicated least-privilege Windows account / a
disposable VM with its own narrowly-scoped `gh` token and **no** push credentials, building against
a clone. That conflicts with the "runs on my dev box against the real repo" design here, so it's a
deliberate future option, not the default.

## Prerequisites

1. **n8n installed natively** (so its Execute Command node can reach this machine's git/claude — a
   Docker n8n cannot):
   ```powershell
   npm i -g n8n
   # REQUIRED env for autopilot (see notes below), then start:
   $env:N8N_SECURE_COOKIE = 'false'                          # allow login over http://localhost
   $env:NODES_EXCLUDE     = '["n8n-nodes-base.localFileTrigger"]'  # re-enable Execute Command node
   n8n start          # editor at http://localhost:5678/ — finish owner-account setup
   ```
   Leave it running in its own terminal; the loop only runs while n8n is up.

   **Two env vars are MANDATORY or the workflow won't work:**
   - `N8N_SECURE_COOKIE=false` — without it, login over plain `http://localhost` can fail to
     hold a session, and the editor shows every node as "Install this node to use it" (it can't
     load `/types/nodes.json`).
   - `NODES_EXCLUDE='["n8n-nodes-base.localFileTrigger"]'` — n8n 2.x **excludes the Execute
     Command node by default** (`@n8n/config` default is `["n8n-nodes-base.executeCommand",
     "n8n-nodes-base.localFileTrigger"]`). Autopilot is built almost entirely from Execute
     Command nodes, so it MUST be re-enabled. This override drops `executeCommand` from the
     exclude list (keeping `localFileTrigger` excluded). To make it permanent, set these in a
     `.env` / your service definition rather than the shell. Re-enabling `executeCommand` lets
     n8n run arbitrary shell — that's intended here, and bounded by the trusted-author gate
     (see Security model).
2. **`gh` authed** to `Sydoc-Code/nexora` (already done on this box: `gh auth status`).
3. **Labels created** — run once:
   ```powershell
   pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\setup-labels.ps1
   ```
4. **Telegram bot** — message `@BotFather` → `/newbot` → copy the token. Message your bot once, then:
   ```powershell
   $token = "<bot-token>"
   (Invoke-RestMethod "https://api.telegram.org/bot$token/getUpdates").result[-1].message.chat.id
   ```
   Note the numeric **chat id**.

## Import & wire the workflow

> ⚠ **Start n8n with the Execute Command node ENABLED *before* importing** (i.e. via
> `start-n8n.ps1` / the `NODES_EXCLUDE` override). n8n **silently drops every connection
> to or from a node type it can't resolve at import time** — so importing while
> `executeCommand` is excluded yields a workflow whose nodes are all there but **not wired
> together**. If that already happened, re-import after enabling the node (or re-add the
> connections); the source JSON's wiring is correct.

1. n8n editor → **Import from File** → `tools/autopilot/n8n-autopilot.workflow.json`.
2. **Credentials** → New → **Telegram API** → paste the bot token → save as `autopilot-telegram`.
3. On each of the three Telegram nodes (`notify-built`, `notify-halt`, `notify-summary`):
   - set the credential to `autopilot-telegram`;
   - replace `REPLACE_WITH_CHAT_ID` in **Chat ID** with your numeric chat id;
   - confirm the operation is **Send Text Message**.
4. **Workflow execution timeout** → leave it **unset**. n8n defaults to *no* timeout, which is what you want (a single `/execute-plan` can run 20–40 min and must not be killed). Only raise it if your instance sets a global `EXECUTIONS_TIMEOUT`.
5. **Error workflow (crash-proof lock release)** — create a second tiny workflow:
   `Error Trigger ─► Execute Command (pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\lock.ps1 -Action release) ─► Telegram (⛔ autopilot crashed — lock released)`.
   Then in the autopilot workflow's settings, set **Error Workflow** to it. This guarantees a
   mid-run crash never leaves the lock wedged.
6. **Activate** the workflow when you're ready for the 2-minute polling to run on its own.

> **Import caveats (no live n8n was available when this JSON was authored):** node
> `typeVersion`s (IF = 2, Loop Over Items = 3, Telegram = 1.2) target a recent n8n; if your
> version warns, accept its upgrade or rebuild the node from the table below. After import,
> eyeball that **Loop Over Items** output **0 = done**, **1 = loop** (n8n labels them).

## First run

1. **Happy path:** open a small real issue, label it `autopilot`. Within ~2 min (or click
   *Execute Workflow*) expect: a `plan` + feature commit on `feature/2.5.63`, the `plan-*`
   worktree created then merged away, the issue commented with the short sha + `autopilot-built`
   (still **open**), Telegram ✅ then 🏁. Capture the real `/execute-plan` JSON + handoff wording
   into `SIGNALS.md` and tighten `probe-state.ps1`'s BLOCKED `-Pattern` if it differs.
2. **Halt path:** label an impossible issue (e.g. "integrate the nonexistent FooBar SDK"). Expect
   it to halt on that issue (`autopilot-blocked` + comment), Telegram ⛔, **no later issue
   attempted**, repo clean, lock released.
3. **Lock:** while a run is in progress, click *Execute Workflow* again — the second run should
   hit `got-lock?` false and stop quietly.

## Recovering from a halt

1. Read the Telegram ⛔ + the issue's `autopilot-blocked` comment.
2. The run's worktree (if any) was left intact — inspect it: `git -C C:\dev\nexora worktree list`.
3. Fix the problem (or finish the work by hand).
4. Remove the `autopilot-blocked` label to re-queue it, or close the issue if done.
5. The lock auto-released on halt; if a crash left one, `lock.ps1 -Action release`.

## Policy (non-negotiable)

- **Commit, never push, never PR.** Built issues are commented + labelled, not closed — you push
  and close after review.
- `SQL_SYNC_SKIP=1` is set inside `run-phase.ps1` (process-scoped) so internal commits survive the
  INT CRLF drift hook. Never `--no-verify`.
- `--effort high` (NOT "ultracode" — not a valid `--effort` value).

## Node / connection reference (fallback if the import misbehaves)

Build order: trigger → fetch-queue → parse-queue → have-work? → acquire-lock → got-lock? →
split-to-items → Loop Over Items.

| Node | Type | Key params |
|------|------|-----------|
| Every 2 min | Schedule Trigger | every 2 minutes |
| fetch-queue | Execute Command | `pwsh -NoProfile -File ...\fetch-queue.ps1` |
| parse-queue | Code | `const q=JSON.parse($input.first().json.stdout||'[]'); return [{json:{queue:q,count:q.length}}];` |
| have-work? | IF | number `{{$json.count}}` > 0 |
| acquire-lock | Execute Command | `...\lock.ps1 -Action acquire` |
| got-lock? | IF | string `{{JSON.parse($json.stdout).status}}` == `ACQUIRED` |
| split-to-items | Code | `const q=$('parse-queue').first().json.queue; return q.map(i=>({json:i}));` |
| Loop Over Items | Loop Over Items | batchSize 1 |
| preflight | Execute Command | `pwsh -NoProfile -Command "if (git -C C:\dev\nexora status --porcelain) {'DIRTY'} else {'CLEAN'}"` |
| clean? | IF | string `{{$json.stdout.trim()}}` == `CLEAN` |
| baseline | Execute Command | `...\baseline.ps1` |
| run-plan | Execute Command | `=...\run-phase.ps1 -Phase plan -IssueNumber {{ $('Loop Over Items').item.json.number }}` |
| verify-plan | Execute Command | `=...\probe-state.ps1 -Phase plan -BeforeSha {{ JSON.parse($('baseline').item.json.stdout).sha }}` |
| plan-ok? | IF | boolean `{{JSON.parse($json.stdout).ok}}` is true |
| run-exec | Execute Command | `...\run-phase.ps1 -Phase execute` |
| verify-exec | Execute Command | `=...\probe-state.ps1 -Phase execute -BeforeSha {{ JSON.parse($('verify-plan').item.json.stdout).headSha }}` |
| exec-ok? | IF | boolean `{{JSON.parse($json.stdout).ok}}` is true |
| comment-built | Execute Command | `=...\comment-result.ps1 -IssueNumber {{ $('Loop Over Items').item.json.number }} -Status built` |
| notify-built | Telegram | `✅ #{{...number}} built` |
| mark-blocked | Execute Command | `=...\comment-result.ps1 -IssueNumber {{ $('Loop Over Items').item.json.number }} -Status blocked` |
| notify-halt | Telegram | `⛔ HALTED at #{{...number}}` |
| release-lock-halt | Execute Command | `...\lock.ps1 -Action release` |
| STOP | No Op | (terminal — does NOT loop back) |
| release-lock-done | Execute Command | `...\lock.ps1 -Action release` (from Loop "done" output) |
| notify-summary | Telegram | `🏁 run complete` |

**Branch wiring:** IF true = output 0, false = output 1. `Loop Over Items` done = output 0,
loop = output 1. The three failure edges (`clean?` false, `plan-ok?` false, `exec-ok?` false)
all converge on `mark-blocked`. `notify-built` connects **back to** `Loop Over Items` to advance.
