# Autopilot roadmap designs — clarify loop, parallel-on-clones, n8n-as-service

**Date:** 2026-06-14 · **Status:** designed, NOT built · **Author:** benstreich (with Claude)
**Builds on:** the live autopilot (`tools/autopilot/`, workflow `PzQXpt99pIIV7fJv`) after this
session shipped the **fixer**, **opt-in auto-push**, **watchdog**, and **cost cap**.

These three remain unbuilt because each has a half that needs **one interactive smoke-validation**
(does headless `/write-plan` emit a stop token? does a live Telegram Trigger correlate replies? do
parallel clones interfere on the shared INT DB?) — validation that must NOT run unattended while the
working tree is being edited. This doc specifies them precisely so a focused session can build each
with the behavioural risk isolated to a single gate, exactly like the original Task-1 smoke gate.

---

## 1. Telegram two-way clarify loop  (ask instead of guess)

**Goal:** when an issue is too underspecified to build unattended, autopilot asks the owner on
Telegram, pauses that issue, and resumes it once the owner answers — instead of guessing or halting.

### Why a pre-plan TRIAGE, not "make /write-plan stop"
The obvious design (tell `/write-plan` to emit `QUESTIONS-FOR-OWNER:` and stop if ambiguous) is
**behaviourally unreliable**: under `-p --dangerously-skip-permissions` the planning skill is built
to *produce a plan* and tends to make assumptions rather than stop. Instead add a **separate,
controllable triage call BEFORE the plan phase** whose only job is a yes/ask decision — a tight
prompt is far more likely to comply than hoping a multi-agent skill self-aborts.

### Components
- **`tools/autopilot/triage.ps1`** (new): runs a cheap `claude -p` (sonnet, `--effort low`) with a
  locked-down prompt:
  > "Decide if the GitHub issue below is specific enough to plan AND implement UNATTENDED with no
  > human available. Reply with EXACTLY one line: `BUILDABLE` or `QUESTIONS-FOR-OWNER: <numbered
  > questions>`. Nothing else." (issue title newline-stripped + body framed as untrusted data, same
  > as `run-phase.ps1`/`solve-blocked.ps1`; reuse the trusted-author gate + token scrub.)
  Filter the stream to the `"type":"result"` line (the lesson from the fixer review — a trailing
  `{"type":"system"}` line otherwise masks the result). Emit `{ buildable:bool, questions:string }`.
- **`fetch-queue.ps1`** (edit): also exclude issues carrying the new label `autopilot-needs-input`
  (so a paused-for-input issue is not re-queued while waiting). One line in the `Where-Object`.
- **`setup-labels.ps1`** (edit): add `autopilot-needs-input` (e.g. colour `fbca04`).
- **Main workflow** (edit `n8n-autopilot.workflow.json`): after `clean?`/`cost-ok?`, before
  `baseline`, insert `triage` → `triage-ok?` IF on `{{ JSON.parse($json.stdout).buildable }}`:
  - **true** → `baseline` (proceed exactly as today).
  - **false** → `notify-questions` (Telegram: post the questions, **prefixed with the issue number
    so the reply can be correlated**, e.g. `❓ #<n> needs input: <questions>`) → `label-needs-input`
    (`comment-result.ps1`-style: add `autopilot-needs-input` + comment the questions on the issue) →
    `release-lock-halt` → `STOP`.
  - **Graceful degradation:** a clear issue returns `BUILDABLE` and flows normally; if triage ever
    fails to emit the token it just builds as today. So wiring this is LOW risk to the proven path —
    worst case the feature is dormant, not broken.
- **Second workflow `tools/autopilot/n8n-clarify-reply.workflow.json`** (new): `Telegram Trigger`
  (the bot's `@nexora_n8n_bot`) → Code node that reads the owner's reply, extracts the issue number
  (from the `reply_to_message` text `#<n>`, or require the owner to start the reply with `#<n>`) →
  `gh issue comment <n> --body "owner-clarification: <reply>"` → `gh issue edit <n> --remove-label
  autopilot-needs-input`. Removing the label re-queues the issue on the next 2-min poll.
- **`run-phase.ps1` plan** (edit): before composing the `/write-plan` prompt, pull any
  `owner-clarification:` comments (`gh issue view <n> --json comments`) and append them to the plan
  prompt as trusted maintainer guidance, so the re-queued build incorporates the answers.

### The single validation gate (run once, interactively, before activating)
Label one deliberately-vague issue; confirm `triage.ps1` emits `QUESTIONS-FOR-OWNER:`, the Telegram
question arrives with `#<n>`, a reply drops an `owner-clarification:` comment + removes the label,
and the re-queued run reads the clarification. Capture the real reply-correlation shape (reply-to vs
leading `#<n>`) and lock whichever is reliable.

### Security
`triage.ps1` is another permission-skipped agent on attacker-influenced text → same controls as
`run-phase.ps1` (author allowlist, token scrub, untrusted-data framing). The Telegram Trigger only
acts on messages from the configured owner chat id; ignore others. The owner's reply becomes an
issue comment that the next build trusts — acceptable because the owner is the trusted author.

---

## 2. Parallel execution on separate CLONES (not worktrees)

**Goal:** build up to N issues concurrently to drain a backlog faster.

### Why clones, not worktrees (the load-bearing constraint)
`handoff-session-state --merge-worktree` merges a finished worktree back into the **base repo's
current branch** (`feature/2.5.63`). Two worktrees off the same base therefore both merge into the
same branch and corrupt each other. Isolation requires **separate local clones**, one per lane, each
on its own `auto/issue-NN` branch, with the result **fetched back** to the main repo.

### Design
- **Lane provisioning** `tools/autopilot/lane.ps1 -Action acquire|release`: maintain a small pool of
  hardlinked local clones (`git clone --local C:\dev\nexora C:\dev\nexora-lanes\lane-K`) — `--local`
  hardlinks objects, so a clone is cheap on disk. Each lane has its OWN lock; the global single-run
  lock is replaced by an **N-slot semaphore** (N = lane count, default 3).
- **Per-lane build:** run plan+execute **in the lane clone** on a fresh branch `auto/issue-NN`
  (point `-RepoPath` at the lane). On success, from the main repo:
  `git fetch C:\dev\nexora-lanes\lane-K auto/issue-NN:auto/issue-NN`, then fast-forward / cherry-pick
  onto `feature/2.5.63` **serialized** (a short critical section so only one lane writes the shared
  branch at a time). Never auto-merge to main.
- **Shared INT DB interference (the real risk):** parallel `/execute-plan` runs hit the SAME INT/TEST
  database and will stomp each other's `NEXORA_TEST` state (cf. `project_prepush_gate_e2e`). Options,
  in order of preference: (a) keep DB-touching e2e **serial** — only the plan + non-DB execute steps
  run parallel, the test/verify step takes a DB lock; (b) per-lane test schemas/databases; (c) cap
  concurrency at 1 for DB-heavy issues via a label. Pick (a) for v1.
- **n8n shape:** either one workflow per lane (cloned canvas, `-RepoPath` differs) triggered by a
  dispatcher, or a single workflow using n8n's parallel branches with a lane semaphore. The
  per-lane-workflow option is simpler to reason about and matches the "clone per lane" model.

### Validation gate
Two trivial non-DB issues, lanes=2: confirm both build in their own clones on `auto/issue-NN`, both
fetch back, and serialize cleanly onto `feature/2.5.63` with no cross-contamination; then one DB-touch
issue to confirm the serial-DB rule holds.

---

## 3. n8n-as-service + watchdog wiring  (always-on away mode)

The `watchdog.ps1` and `cost-guard.ps1` shipped this session; this is how to run them always-on.

- **n8n as a service:** wrap `start-n8n.ps1` with **NSSM** (`nssm install nexora-n8n pwsh -NoProfile
  -File C:\dev\nexora\tools\autopilot\start-n8n.ps1`) OR a **Task Scheduler** task `At startup`,
  `Run whether logged on or not`. The MANDATORY env (`N8N_SECURE_COOKIE=false`,
  `NODES_EXCLUDE='["n8n-nodes-base.localFileTrigger"]'`) must live in the **service definition / a
  persisted `.env`**, not just a shell, or every node shows "not installed" and Execute Command is
  excluded (see README).
- **Watchdog as a scheduled task:** `watchdog.ps1` single-shot every 3–5 min via Task Scheduler
  (`pwsh -NoProfile -File ...\watchdog.ps1`), OR run the loop mode under its own service. Set
  `AUTOPILOT_TG_TOKEN` + `AUTOPILOT_TG_CHAT` (the same `@nexora_n8n_bot` token + owner chat id) so a
  restart pings Telegram.
- **Cost cap:** set `AUTOPILOT_DAILY_USD_CAP` in the same persisted env (default $25).
- **Defender:** `var/autopilot/` is a new per-run write path; if PROD-style path-scoped Defender is
  on this box, add an exclusion (cf. `project_syapp01_defender_exclusion`) to avoid latency.

---

## Suggested build order (each is one focused session ending in a smoke gate)
1. **Clarify loop** — highest autonomy gain; graceful-degradation makes it safe to wire.
2. **n8n-as-service + scheduled watchdog** — small, makes away-mode actually unattended.
3. **Parallel-on-clones** — largest; do last, behind the serial-DB rule.
