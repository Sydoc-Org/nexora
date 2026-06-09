---
description: Resume after a /clear — load the newest handoff (written by /handoff-session-state), orient, then front-load questions before working
argument-hint: "[optional: a specific handoff file, or a focus note]"
---

Resume work from the most recent handoff — the counterpart of `/handoff-session-state`. Optional
context the user passed: `$ARGUMENTS`.

## 1. Load the handoff

- Look in `docs/superpowers/handoffs/` (fall back to `docs/handoffs/`). Pick the **most recent** by
  filename date — unless `$ARGUMENTS` names a specific handoff file, in which case use that. If two
  handoffs share the newest date, the older one carries a forward-pointer banner at the top (written
  by `/handoff-session-state`) — follow it. **Read the handoff in full.**
- Follow its **"Prior handoff"** link and read any design doc, plan, or source files it references
  that you'll need to act (e.g. `docs/design/*`, `docs/superpowers/plans/*`). Don't read the whole
  repo — just what the handoff points at.

## 2. Establish current state (read-only — change nothing yet)

Run `git branch --show-current`, `git status`, `git log --oneline -15`, and `git diff --stat`.
Determine: the branch, what's uncommitted, and which of the handoff's commits already landed. If
GitNexus is connected and the next step touches code, use it to orient. Do **not** stage, commit,
push, or edit anything in this step.

## 3. Orient the user (briefly)

In a few bullets: what the last session did, where it left off, and the **open next steps** drawn
from the handoff's "Owner actions" / "Resuming in a fresh session" sections. Use **bold** for
section breaks, not markdown headers.

## 4. Front-load questions, then run to completion

This is the user's preferred working style — **ask before starting, then finish without mid-flow
checkpoints**:

- Use **AskUserQuestion** to surface the decisions that gate the next step *before* you begin: the
  scope of this session, any open design choices the handoff flags, and **git handling**
  (remote/commit-only vs. local/push-allowed). Ask everything up front, in one batch where possible.
- State any sensible defaults you'll assume for things you didn't ask, so the user can correct them.
- After the user answers, **do the work to completion** — the user reviews and adjusts at the end.
  Respect the nexora git policy: never modify `main`; default to **commit-only (no push, no PR)**
  unless the user opts into pushing this turn.

Keep the orientation tight and get to the questions quickly.
