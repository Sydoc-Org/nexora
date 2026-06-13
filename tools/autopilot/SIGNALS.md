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
| `--effort high` accepted alongside `--model fable` | yes | ⬜ pending |

When you run the first happy-path issue (README → "First run"), capture the real
`/execute-plan` JSON + the handoff wording here, and tighten `probe-state.ps1`'s
`-Pattern` if the literal differs.
