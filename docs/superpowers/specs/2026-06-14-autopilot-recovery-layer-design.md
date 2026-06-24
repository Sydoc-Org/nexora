# Autopilot recovery layer — diagnose · escalate · skip-and-continue

**Date:** 2026-06-14 · **Status:** designed, NOT built · **Author:** benstreich (with Claude)
**Builds on:** the live autopilot (`tools/autopilot/`, workflow `PzQXpt99pIIV7fJv`) — the fixer,
opt-in auto-push, watchdog, and cost cap already shipped. **Supersedes** the "clarify loop" half
of `2026-06-14-autopilot-clarify-and-parallel-design.md` by folding it in as a **pre-plan triage**
(the parallel-on-clones half of that doc is untouched and remains future work).

> This spec was adversarially red-teamed (4 lenses: n8n wiring, the crash-proof output contract,
> failure-mode coverage, security) against the real scripts. The hardenings below are the result —
> in particular, every "inherited contract" promise is now made **explicit per script**, because the
> review proved the guarantees do not survive splitting one script into several.

## Problem

The loop "stops on almost every issue." Three real failure modes, from the live issues:

| Issue | Recorded halt | Real class |
|-------|---------------|-----------|
| #90 (twice) | `pre-flight: working tree not clean (1, then 32 changes)` | **mechanical / environment** — a prior partial run polluted the tree |
| #89 | `did not pass verification (no committed result, or worktree did not merge back)` | **diagnosis-free** — you can't tell *why* it stopped |
| #91 | built | — (small, self-contained) |

Two structural causes:

1. **One fix attempt, then give up.** `solve-blocked.ps1` makes a single opus pass.
2. **Any unrecovered halt stops the WHOLE run.** `mark-blocked → STOP` is terminal and does not loop
   back, so the first bad issue freezes the entire queue. This is the literal cause of "stops on
   almost every issue."

Plus no *root-cause* reporting: the halt comment is a generic guess, so the next attempt starts cold.

## Goals / non-goals

**Goals**
- A dedicated **diagnostician** that classifies *why* a halt happened — so every outcome carries a
  real root cause (kills the #89 case).
- An **escalation ladder**: diagnose → targeted fix → re-verify, up to **2 attempts** per issue,
  escalating model/effort, bounded by the daily USD cap.
- **Smart-skip loop semantics**: a genuinely-stuck *single* issue is marked blocked and the loop
  **continues**; only a **poison** failure stops the whole run.
- Auto-recover **mechanical/environment** and **test & quality-gate** failures; route
  **underspecified** issues to a Telegram clarify loop — *before* the plan phase runs (see below).

**Non-goals (this layer)**
- Transient-infra is *detected and pauses the run* (not auto-fixed); the 2-min poll retries.
- Parallel-on-clones isolation (separate roadmap item). Recovery runs in the main tree.
- Changing the happy path (`plan → execute → built`) other than two safety additions
  (per-issue baseline + per-issue run.log scoping, below).

## Decisions (locked with the owner)

| Decision | Choice |
|----------|--------|
| Loop policy on unrecoverable issue | **Smart skip** — skip the issue & continue; stop whole run only on poison |
| Recovery depth | **Escalation ladder**, diagnose → fix → re-verify |
| Per-issue budget | **2 attempts**, also bounded by the daily USD cap |
| Auto-recover classes | mechanical/env, test & quality gates, underspecified (→ Telegram, pre-plan) |
| Transient infra | detected → **pause run** (no fix attempt); poll retries |
| Implementation shape | **Approach A** — orchestrate in PowerShell, route on the canvas |

## Failure taxonomy & routing

The diagnostician classifies every halt into a **closed enum** (validated by `recover.ps1`; any
unexpected value defaults to `genuine-blocker`). The class sets whether a fix is attempted and what
the loop does next. **`poison` is computed deterministically (NOT by the LLM) — see below.**

| Class | Detected by | Recovery action | Loop outcome |
|-------|-------------|-----------------|--------------|
| **mechanical** | dirty tree, leftover `plan-*` worktree, stale lock, CRLF drift, missing `SQL_SYNC_SKIP` (deterministic git signals) | deterministic cleanup, then fixer ladder | cleaned+built → **continue**; cleanup leaves tree unclean → **poison → stop** |
| **test-gate** | ruff / pytest / e2e / i18n / pre-push-gate failure in *this issue's* run.log slice | fixer ladder with the gate-specific playbook | fixed → **continue**; exhausted → **skip → continue** |
| **plan-ok-execute-failed** | plan commit + fresh handoff landed, but no **feature** commit since the plan HEAD (and/or worktree unmerged) | re-enter the **execute** phase (do NOT remove the worktree) | built → **continue**; exhausted → **skip → continue** |
| **infra** | INT/TEST DB unreachable, n8n `:5678` down, `gh`/network down (deterministic `probe-infra.ps1`) | **none** — no fix attempt | **pause run** (poll retries); livelock-guarded (below) |
| **underspecified** | **pre-plan triage** judges the issue too vague to build unattended | **none** — ask the owner | **needs-input** → label + Telegram, **continue** to next issue |
| **genuine-blocker** | real missing dependency / decision the agent can't make; also the safe default for any unrecognised class | fixer ladder (one honest try) | exhausted → **skip → continue** with a rich reason |

### `poison` is deterministic, default-true

`poison` answers: *would continuing corrupt the next issue?* It is **computed by `recover.ps1` from
observed state at the skip decision**, never taken from the LLM:

```
poison := (git status --porcelain non-empty after cleanup)
       OR (detached HEAD or not on the expected branch)
       OR (unmerged paths present: git ls-files -u)
       OR (leftover plan-* worktree whose HEAD is NOT an ancestor of branch HEAD)
       OR (probe-infra reports infra down)
       OR (the run lock cannot be confirmed held)
```

Default `poison = true`; downgrade to `false` only when **all** deterministic checks pass. The LLM
may *suggest* a class and a fix; it may never assert that continuing is safe. A `poison` skip becomes
`pause-run` (stop the whole run); a non-poison skip marks the issue blocked and continues.

### Clean-tree guarantee before any "continue"

Before emitting any continue verdict (`built` / `skip` / `needs-input`), `recover.ps1` must leave the
tree clean for the next issue: stash any residual dirt to a **labelled, recoverable** stash and
assert `git status --porcelain` is empty. If it cannot reach clean → `poison → pause-run`. ("Leaves a
dirty tree" is part of the poison definition, not only "uncleanable at the start.")

## Pre-plan triage (underspecified → ask, don't guess)

Detecting "underspecified" *after* a halt is too late: the plan phase already ran (the planning skill
"tends to make assumptions rather than stop") and may have produced a speculative plan commit +
handoff + `plan-*` worktree. So underspecified detection moves **before** the plan phase, exactly as
the clarify design specified:

- **`tools/autopilot/triage.ps1`** (new) runs a cheap, **constrained** `claude -p` (sonnet,
  `--effort low`, **read-only** — see the diagnostician hygiene note) with a locked-down prompt:
  reply EXACTLY `BUILDABLE` or `QUESTIONS-FOR-OWNER: <numbered questions>`. Issue title
  newline-stripped + body framed as untrusted data; trusted-author gate + token scrub. Filter to the
  `"type":"result"` line (the fixer lesson). Emits `{ buildable:bool, questions, costUsd }`.
- Canvas: after `clean?`/`cost-ok?`, before `baseline`, insert `triage → triage-ok?`. `true` →
  proceed to baseline as today; `false` → `notify-questions` + `label-needs-input` → **continue**
  (the issue waits; the loop moves on). Graceful degradation: if triage ever fails to emit a token it
  builds as today, so wiring it is low-risk to the proven path.
- Because triage runs *before* the plan phase, an underspecified issue never dirties the tree. The
  post-halt diagnostician therefore does **not** classify `underspecified` (it can't reach a halt for
  that reason); that class lives only in triage. (If a vague issue slips past triage and halts, the
  diagnostician classifies it `genuine-blocker → skip`, which is safe.)

## Components

### Output-contract invariants (apply to EVERY new script — non-negotiable)

Each script invoked as an n8n node, **and each child script invoked by `recover.ps1`**, must:

1. Emit **exactly one** compact JSON line on stdout and **exit 0**; **never throw** (empty/garbled
   stdout crashes the node, skips the terminal label, and lets the 2-min poll relaunch a full opus
   run forever). This is enforced by a single top-level `try { … } catch { emit a known-good default
   verdict; exit 0 }` wrapping the whole body — the `gh issue view` author re-check included (a
   transient `gh` outage must fall to the catch, not crash).
2. Confine any `claude` stream to `run.log` via `Tee-Object`, capture the **single** result envelope
   into a variable (`$x = … | Where-Object {match `"type":"result"`} | Select-Object -Last 1`), and
   never let that intermediate line reach stdout. Only the final `ConvertTo-Json -Compress` verdict
   is emitted.
3. Perform the `Remove-Item Env:GH_TOKEN, GITHUB_TOKEN` scrub and set `$env:SQL_SYNC_SKIP='1'` **at
   its own entry** — the canvas runs scripts as separate `pwsh` processes, so hygiene is **not**
   inherited from `recover.ps1`.

`recover.ps1` additionally must **capture every child-script invocation** (`$d = & diagnose-halt.ps1
…` / `& cost-guard.ps1 … | Out-Null`) so no child's JSON leaks into its own stdout; build ONE
`[ordered]@{ action = … }`; emit it with a SINGLE `ConvertTo-Json -Compress` as the last statement;
and wrap every `ConvertFrom-Json` of child output in a try with a defined fallback action (a
null/empty/unparseable child verdict ⇒ `class:unknown → skip`, never `built`/`pause`).

### New scripts (the "hands")

- **`probe-infra.ps1`** — deterministic, no LLM. `{ dbOk, n8nOk, ghOk, netOk }` from a fast
  `Test-NetConnection`/`sqlcmd` to INTSQL01, n8n `:5678` listening, `gh auth status`, network. Lets
  the diagnostician set `class:infra` and the `poison` infra term **without** an LLM call — directly
  handles the recurring INT outages. Re-run after **each** failed ladder attempt too (infra can die
  mid-attempt and masquerade as a test-gate failure).

- **`diagnose-halt.ps1`** — the **diagnostician**. Takes `-IssueNumber`. Gathers evidence scoped to
  **this issue** (git porcelain; `git log`/diff since *this issue's* baseline; leftover `plan-*`
  worktrees; the run.log slice **after the most recent `=== plan #<n> ===` / `=== FIXER #<n> ===`
  header** — matched on the issue number, never "last N lines"; the `probe-state.ps1` verdict;
  fresh-handoff BLOCKED markers; `probe-infra.ps1`). Deterministic guards first (infra/mechanical);
  then a **constrained** classifier disambiguates test-gate vs plan-ok-execute-failed vs
  genuine-blocker and writes a summary + advisory `suggestedFix`. Emits
  `{ class, summary, suggestedFix, costUsd }` — note **no `poison`** (that's `recover.ps1`'s
  deterministic job). `class` is a closed enum.
  - **Security — evidence framing:** run.log, diff, git log, and handoff excerpts are *not* trusted
    input (run.log echoes attacker-controlled issue text; a diff can contain attacker-chosen file
    content). diagnose-halt wraps **every** evidence blob in its own untrusted-data markers + a
    do-not-obey preamble, stripping the marker literal from the evidence first (as the title is
    newline-stripped today). The classifier prompt forbids treating embedded text as instructions.
  - **Hygiene:** run it **without `--dangerously-skip-permissions`** and with a read-only tool
    allowlist (no Bash/gh/write) — a pure classifier needs no write tools, the rare case a static
    allowlist is feasible. Token scrub + result-line filter still apply.

- **`recover.ps1`** — the **escalation-ladder orchestrator**; replaces `solve-blocked.ps1` as the
  canvas node. Top-level try/catch (per the contract). Flow:
  1. Author allowlist re-check (inside the try; a `gh` failure falls to the catch).
  2. `$diag = & diagnose-halt.ps1 -IssueNumber n` (captured).
  3. **Deterministic** infra/poison probe (`probe-infra` + git checks). `infra` or poison ⇒
     `pause-run` (livelock-guarded, below). No fix spent.
  4. Else run the **ladder** (`$MaxAttempts`, default 2):
     - `& cost-guard.ps1 -Action check | …`; over cap ⇒ `pause-run` (reason: cost cap).
     - `$fix = & fix-attempt.ps1 -Model <ladder> -Effort high -SinceSha <planHeadSha> -Diagnosis …
       -Playbook …` (captured). i=1 sonnet→opus; i=2 opus + the prior attempt's own failure as
       `-ExtraContext`. `suggestedFix`/`summary` are passed **as untrusted, advisory** text (wrapped
       in do-not-obey markers), never as trusted instructions.
     - Book cost from `$fix.costUsd` (and `$diag.costUsd`) via `cost-guard -Cost` (see below).
     - Re-run `probe-infra`; if infra died mid-attempt, roll the tree back to the pre-attempt sha and
       `pause-run` (don't blame the issue).
     - Self-verify with `-SinceSha` = the plan phase's headSha if a plan ran for this issue, else the
       per-issue baseline sha (the mechanical pre-flight case has no plan phase, so any feature commit
       after recovery started counts) — so **"commit landed" never counts a bare plan commit as a
       feature commit**. `ALREADY-DONE` is **not** a sole success signal:
       accept it only with corroboration (tree clean AND no commit AND a deterministic re-check that
       the claimed change is present AND no gh-mutation occurred this attempt).
     - Success ⇒ deterministic poison check passes ⇒ `built` (+ clean-tree guarantee) and return.
  5. Ladder exhausted ⇒ deterministic `poison ? "pause-run" : "skip"` with `class`, `summary`,
     `stashed`, `attempts`.
  - **Worktree safety:** before any mechanical `git worktree remove`, assert the worktree HEAD is an
    ancestor of branch HEAD (`git merge-base --is-ancestor`); refuse to remove a worktree holding
    unmerged commits — classify that `genuine-blocker`/poison instead (removing it is data loss).

- **`fix-attempt.ps1`** — **refactor of `solve-blocked.ps1`'s proven body** into one parameterized
  attempt: mechanical cleanup → fixer `claude` agent (`-Model`, `-Effort`, `-SinceSha`, `-Diagnosis`,
  `-ExtraContext`, `-Playbook`) → self-verify → verdict `{ ok, committed, alreadyDone, sha, stashed,
  costUsd }`. Derives its result text from the **in-pipeline `$final` of its own `claude` call**,
  never by re-reading the shared run.log. Keeps every existing security control verbatim plus the
  per-script hygiene above. The fixer prompt uses **systematic-debugging** discipline and reads
  `RECOVERY-PLAYBOOK.md` for the matched class.

- **`RECOVERY-PLAYBOOK.md`** — a short nexora-specific cookbook the fixer reads, from project memory:
  i18n catalog out of sync → extract→update→compile (`nx-i18n`), commit `.po`/`.mo`; CRLF / SQL
  migration checksum drift → `SQL_SYNC_SKIP=1` already set, never `--no-verify`, durable fix
  `.gitattributes *.sql eol=lf`; flaky/order-dependent e2e → `python scripts/test_db_reset.py` first;
  leftover `plan-*` worktree → merge-away/`git worktree remove` **only after** the ancestor check.

### Edited scripts

- **`baseline.ps1` + canvas** — run baseline **unconditionally at the top of each loop iteration,
  before `clean?`**, so a baseline for *this* issue always exists when recovery reads it (today it
  runs only on the happy path after `clean?`/`cost-ok?`, so the `clean?`-false edge — the #90 case —
  has a stale baseline). `baseline.sinceIso` thus scopes `probe-state`'s BLOCKED-marker scan to this
  issue, fixing the cross-issue false-positive.
- **`run-phase.ps1`** — (a) write a per-issue run.log header (`=== plan #<n> === <iso>`) so
  diagnose/cost-guard can slice by issue; (b) plan: pull `owner-clarification:` comments **filtered
  by `author.login` ∈ allowlist** (`gh issue view <n> --json comments` includes author) and append
  them as trusted maintainer guidance. Body-prefix matching alone is insufficient — the autopilot's
  own `gh` keyring identity (or any non-owner) could otherwise mint a "trusted" clarification.
- **`cost-guard.ps1`** — add an `add -Cost <usd>` mode that books an explicit number (from a child's
  returned `costUsd`) instead of re-reading the shared run.log's last result line. The
  read-last-line mode is unsafe inside the ladder (multiple result lines per add; the diagnostician's
  spend is otherwise never booked). recover.ps1 books each attempt **and** the diagnostician via
  `-Cost`.
- **`comment-result.ps1`** — add `-Class` / `-Detail` so a blocked/skip comment names the real root
  cause and what was tried ("blocked after 2 recovery attempts — *test-gate: pytest X*; tried i18n
  recompile + e2e reset"); add a `needs-input` status (label `autopilot-needs-input` + comment the
  questions). Idempotent on re-label.
- **`fetch-queue.ps1`** — also exclude `autopilot-needs-input`. (Infra-pause uses **no** label so the
  issue stays queued — but see the livelock guard.)
- **`setup-labels.ps1`** — add `autopilot-needs-input` (colour `fbca04`).

### n8n canvas changes (the "brain")

`needs-input` is produced **pre-plan** by the `triage` branch (above), not by `recover.ps1` — so the
post-halt `route-recovery` Switch has only **three data outputs + a fallback**. The three "continue"
outcomes across the canvas (triage's `needs-input`, recover's `built`, recover's `skip`) all
reconverge into **one collector** before re-entering the loop:

```
preflight ─► clean? ─► cost-ok? ─► triage ─► triage-ok?
                                              ├─ true  ─► baseline ─► run-plan ─► … ─► run-exec ─► … (happy path)
                                              └─ false ─► notify-questions (❓ #n) ─► label-needs-input ─────────────┐
... failure edges ─► recover (recover.ps1)                                                                          │
                       └─► route-recovery (Switch on JSON.parse(stdout).action; typeVersion pinned, FALLBACK enabled)│
                            ├─ "built"     ─► comment-built ─► notify-recovered (🛠️ + cause + attempt n/2) ─────────┤
                            ├─ "skip"      ─► mark-blocked (-Class/-Detail) ─► notify-skip (⏭️ #n: cause) ──────────┤
                            │                                                       (collector: NoOp/Merge) ◄────────┘
                            │                                                              └─► Loop Over Items  (MAIN INPUT — CONTINUE)
                            ├─ "pause-run" ─► notify-pause (⏸️ infra/cost) ─► release-lock-halt ─► STOP   (WHOLE RUN; poll retries)
                            └─ FALLBACK    ─► (treat unknown/empty action as poison) ─► release-lock-halt ─► STOP
```

Wiring rules the review made explicit:
- The three continue outcomes reconverge into **one collector** (NoOp/Merge); only that node's single
  output connects to **Loop Over Items' MAIN INPUT (index 0)** — *identical to today's
  `notify-built → Loop Over Items` edge*. Do **not** wire a continue branch to the loop's output-1
  (loop body) — that re-runs the same item forever. The loop body output (1 → preflight) and done
  output (0 → push-branch) are unchanged.
- The Switch **typeVersion is pinned** (current 3.x), outputs = the three actions, and the **Fallback
  Output is enabled** and wired to the pause-run terminal. An unmatched/empty action must never drop
  the item silently (the lock would leak until the 3h reclaim). recover.ps1's catch also emits a
  known-good action so the fallback is belt-and-suspenders.
- **Lock invariant (reworded):** the lock is held for the whole run and **released exactly once** —
  on the loop *done* output (`release-lock-done`) or on *pause-run/fallback* (`release-lock-halt`).
  Continue branches never release it. The Switch-fallback + collector fixes guarantee the run cannot
  end without hitting one of those two release nodes; the Error Workflow remains the crash backstop.
- **Import precondition (build-order step):** re-import **only via `start-n8n.ps1`** (executeCommand
  enabled), then verify all four Switch routes + the fallback + every loop-back edge are present
  (n8n silently drops edges to unresolved node types). Add the Switch to the README typeVersion
  caveat table (next to IF=2/Loop=3/Telegram=1.2) and add the new Telegram nodes
  (`notify-recovered/skip/questions/pause`) to the README's "set credential + chat id on each" list.

A second workflow **`n8n-clarify-reply.workflow.json`** handles owner replies (see Security for the
correlation hardening).

## Cost & safety guardrails

- **Per-issue:** hard `$MaxAttempts = 2` ladder counter.
- **Daily:** `cost-guard -Action check` between attempts; over-cap ⇒ `pause-run`. Every claude call
  (diagnostician + each attempt) is booked via `cost-guard add -Cost <usd>` from the child's returned
  `costUsd` — **not** the fragile shared-log read. Recovery spend now counts toward the cap (today
  the fixer's spend is unbooked entirely).
- **Livelock guard:** a `var/autopilot/attempts.json` ledger keyed by issue number counts how often
  an issue reached `pause-run` *without* a label. Global infra-down (no issue is buildable) correctly
  pauses the whole run; but an issue that triggers `pause-run` more than `N` times (default 3) is
  escalated to `needs-input`/blocked **with a label**, so it can't be re-queued every poll forever
  while burning the daily cap on a false infra read.
- **Crash-proof:** the explicit per-script contract above (child-stdout capture, top-level try/catch,
  result-line filter, Switch fallback, fail-closed parse) — not an inherited promise.
- **Loop-protection:** a `skip` adds `autopilot-blocked`; `fetch-queue` won't re-queue it. Labels on
  skip/needs-input must complete (executeCommand awaited) before the branch returns to the loop.

## Security

**This design adds two new trust surfaces** (the previous "no new trust surface" claim was wrong):

1. **Evidence channel → classifier.** run.log/diff/handoff (attacker-influenced) flow into the new
   classifier, whose output steers the fixer and the routing. **Controls:** untrusted-data framing on
   *every* evidence blob; `class` validated against a closed enum (unexpected ⇒ `genuine-blocker`);
   `suggestedFix`/`summary` re-injected into the fixer only as untrusted, advisory text; the
   classifier run **without** `--dangerously-skip-permissions` and read-only; `ALREADY-DONE` accepted
   only with deterministic corroboration; **poison computed deterministically**, so the LLM can never
   assert "safe to continue."
2. **Inbound Telegram clarify reply → trusted comment.** **Controls:** the clarify-reply workflow
   gates on the owner chat id; binds the reply to the issue via a stored `message_id → issue` mapping
   + `reply_to_message` (not by parsing a `#<n>` substring, which is forgeable when the questions text
   is LLM-generated from issue content); requires the resolved issue to currently carry
   `autopilot-needs-input`; rejects messages with more than one number token. The resulting
   `owner-clarification:` comment is trusted by the next build **only if its `author.login` is in the
   allowlist** (ideally a distinct owner identity), since the autopilot's own `gh` identity can write
   comments.

All other controls are unchanged and **re-applied per script** (not inherited): author allowlist
re-check, `GH_TOKEN`/`GITHUB_TOKEN` scrub, untrusted title+body framing, `SQL_SYNC_SKIP=1`,
commit-not-push, never `--no-verify`. Prompt injection cannot be fully prevented; the trusted-author
gate remains the primary defence.

## Testing & the validation gate

Deterministically unit-testable (no LLM): `probe-infra.ps1` (mock unreachable host); the
`recover.ps1` router fed canned `class`/state for each row (assert the `action`, and that a
**malformed/empty** child verdict ⇒ `skip`, never `built`); the deterministic `poison` function;
`-SinceSha` self-verify (a plan-only commit must NOT count as built); the worktree ancestor check;
cost booking via `-Cost`; the livelock ledger; `comment-result.ps1` rich reasons; the Switch fallback
(feed malformed JSON, assert the lock is released).

**Interactive smoke gate** before activating, six cases:
1. **mechanical** — dirty the tree, tiny issue → cleanup + build + 🛠️ + **next issue runs**.
2. **test-gate** — trips a known gate → fix+re-verify, or skip-with-cause after 2 attempts, then **continue**.
3. **plan-ok-execute-failed** — plan lands, execute hits max_turns → recovery re-enters execute (does NOT ship the plan commit as "built" or delete the worktree).
4. **underspecified** — vague issue → **triage** (pre-plan) emits ❓ Telegram with `#n`, label `needs-input`, loop continues; a correlated reply re-queues it.
5. **infra** — INT DB/n8n down → `pause-run` (no fix attempt), lock released, poll retries; repeat on the *same* issue 3× → it escalates to a label (livelock guard).
6. **mixed multi-issue drain** — a queue mixing built+skip+needs-input → assert the loop `done` output fires **exactly once** (push-branch / release-lock-done / 🏁 summary run once).

Capture the real diagnostician output shape and tighten the classifier prompt / `probe-state` regex
from the live run, as `SIGNALS.md` prescribes.

## Build order
1. `probe-infra.ps1` + `RECOVERY-PLAYBOOK.md` + `cost-guard.ps1 -Cost` mode (pure, no canvas).
2. Per-issue baseline + run.log header (`baseline.ps1`, `run-phase.ps1`, canvas baseline-moves-up).
3. Refactor `solve-blocked.ps1` → `fix-attempt.ps1` (preserve security body + per-script contract; `-SinceSha`, `costUsd`, ALREADY-DONE corroboration).
4. `diagnose-halt.ps1` (deterministic guards + constrained classifier + evidence framing + per-issue scoping).
5. `recover.ps1` (ladder + deterministic poison + clean-tree guarantee + worktree ancestor check + child-stdout capture + top-level try/catch + attempts ledger) + `comment-result.ps1`/`setup-labels.ps1`/`fetch-queue.ps1` edits.
6. `triage.ps1` (pre-plan) + canvas rewire (move baseline up; swap node; add Switch + fallback + collector + loop-back to main input; triage branch; new Telegram nodes) — re-import via `start-n8n.ps1`, verify edges.
7. `n8n-clarify-reply.workflow.json` (message_id↔issue mapping, owner-chat gate, needs-input check) + `run-phase.ps1` author-checked clarification pull.
8. The six-case smoke gate, then activate.
