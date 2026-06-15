# Autopilot headless signal contract

What `claude -p` emits, and what the verifier (`probe-state.ps1`) keys off. Update the
"to confirm on first run" rows after the first real `/execute-plan` so the BLOCKED
detection matches reality.

## `claude -p --output-format json` envelope — CONFIRMED 2026-06-13

A single JSON object on stdout. Fields the loop cares about:

| Field | Meaning | Use |
|-------|---------|-----|
| `type` | always `"result"` | — |
| `subtype` | `"success"` on a normal finish; other values on failure (e.g. `"error_max_turns"`) | phase-level error detect |
| `is_error` | `false` on success | phase-level error detect |
| `terminal_reason` | `"completed"` on a normal finish | phase-level error detect |
| `result` | final assistant text | logging |
| `stop_reason` | e.g. `"end_turn"` | — |
| `session_id`, `num_turns`, `total_cost_usd` | run metadata | logging |
| `permission_denials` | `[]` when nothing was blocked | sanity |

**Owner-confirmed (2026-06-13):** `claude -p "/write-plan ..."` runs headless and the
multi-agent skill spawns under `-p`. The existential feasibility risk is cleared.

> ⚠ A `/execute-plan` that STOPS on "2× BLOCKED" still reports `subtype:"success"`,
> `terminal_reason:"completed"`. The envelope therefore CANNOT distinguish "completed"
> from "stopped-while-blocked". That deeper call is made by `probe-state.ps1` from git +
> handoff state — never from the envelope.

## Verifier source-of-truth (probe-state.ps1, baseline-delta)

- **plan ok** = a commit landed since baseline + a plan md fresh-since-baseline + `var/handoff-pending` fresh-since-baseline.
- **execute ok** = a feature commit landed since the plan's HEAD + the run's `plan-*` worktree merged away (vs the pre-plan worktree set) + no BLOCKED marker in any handoff written since baseline.

## To confirm on first real run (then update probe-state.ps1 if needed)

| Signal | Assumed value | Confirmed? |
|--------|---------------|-----------|
| `/execute-plan` headless merges its worktree back | yes (skill ends with `--merge-worktree`) | ⬜ pending |
| BLOCKED handoff literal | matched by regex `\bBLOCKED\b` or `max_turns` | ⬜ pending — paste the real wording here |
| plan commit message prefix | not relied on (we check commit-landed + fresh plan md) | n/a |
| `--effort high` accepted alongside `--model opus` | yes | ⬜ pending |

When you run the first happy-path issue (README → "First run"), capture the real
`/execute-plan` JSON + the handoff wording here, and tighten `probe-state.ps1`'s
`-Pattern` if the literal differs.

## Recovery-layer emitted-JSON contracts

Each recovery-layer script emits exactly one compact JSON line to stdout, exits 0, and never
throws. Shapes below are the designed contracts; update after the first live run.

### `triage.ps1`

```json
{ "buildable": true|false, "questions": "string (empty when buildable)", "costUsd": 0.0 }
```

`buildable` = `true` → proceed to plan. `false` → emit `questions` for the owner; no plan/exec
attempted. The canvas node reads `buildable`; `questions` is posted as a GitHub comment.

### `diagnose-halt.ps1`

```json
{
  "class": "<enum>",
  "summary": "human-readable string",
  "suggestedFix": "string",
  "costUsd": 0.0
}
```

Closed `class` enum (exhaustive — no other values may be emitted):

| Value | Meaning |
|-------|---------|
| `mechanical` | Deterministic guard fired (dirty tree, missing lock, CRLF drift, etc.) — no LLM needed. |
| `test-gate` | A test suite / linter / pre-commit hook failure; likely fixable by `fix-attempt`. |
| `plan-ok-execute-failed` | Plan phase succeeded but execute phase failed; usually a code-gen error. |
| `infra` | `probe-infra` returned a false gate (DB/n8n/GH/net down). |
| `genuine-blocker` | LLM classified as not auto-fixable; escalate to owner. |

### `recover.ps1`

```json
{
  "action": "built|skip|pause-run",
  "class": "<same enum as diagnose-halt>",
  "summary": "string",
  "stashed": false,
  "attempts": 0
}
```

`action` values:

| Value | Meaning |
|-------|---------|
| `built` | A fix attempt succeeded; a commit landed. Queue continues. |
| `skip` | Skipped this issue (skip-and-continue); queue continues to next issue. |
| `pause-run` | Genuine blocker or livelock limit hit; STOP + notify owner. |

`attempts` = number of fix-attempt calls made (0 if skipped on mechanical/infra class without
trying). `stashed` = true if a dirty tree was stashed before attempting.

### `probe-infra.ps1`

```json
{ "dbOk": true, "n8nOk": true, "ghOk": true, "netOk": true }
```

No LLM; purely deterministic. All booleans. `diagnose-halt.ps1` calls this first; if any
gate is false the class is set to `infra` without invoking an LLM.

### `fix-attempt.ps1`

```json
{
  "ok": true|false,
  "committed": true|false,
  "alreadyDone": false,
  "dirty": false,
  "leftoverWorktree": false,
  "sha": "abc1234|null",
  "stashed": false,
  "costUsd": 0.0,
  "reason": "string"
}
```

`ok` = true means a commit landed and self-verify passed. `alreadyDone` = the fixer agent
concluded the work was already complete (counts as ok). `dirty` / `leftoverWorktree` = cleanup
was incomplete (recover.ps1 accounts for these in the livelock ledger).

### run-state.json (var/autopilot/run-state.json)

Written by run-phase.ps1 at phase start (plan records number+title; execute preserves them and
flips .phase); cleared on n8n startup by start-n8n.ps1. Consumed by `nx status`.

```json
{ "ts": "<ISO8601>", "phase": "plan|execute", "number": 94, "title": "<string>", "procId": 12345 }
```

Readers MUST treat the record as stale (no build in progress) when its file LastWriteTime is older
than 3 min with no live autopilot claude.exe, or older than 3h outright -- mirroring lock.ps1.

## Pending — confirm on first live run

| Signal | Status | Notes |
|--------|--------|-------|
| REAL `diagnose-halt` output shape | ⬜ pending | Capture from first live halt; update class enum + regex in `recover.ps1` if it drifts |
| Read-only claude flag for `diagnose-halt` / `triage` | ⬜ pending | Confirm `--allowedTools` (ReadFile, Bash:readonly) vs `--permission-mode readonly`; update both scripts |
