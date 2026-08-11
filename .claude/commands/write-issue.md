---
description: Turn a described change into a GitHub issue — ask all clarifying questions up front, then create it
argument-hint: "<what you want changed>"
---

The user describes something they want changed: $ARGUMENTS

1. Read the description. Grep/Glob the repo if it references a page, route, or feature — ground the issue in real code, don't guess blind.
2. Ask every clarifying question you need in ONE `AskUserQuestion` call (multiple questions in that one call, not several rounds). Concrete questions only — no preamble, no restating what they said. Cover whatever's actually unclear, e.g.:
   - What's the current (broken/missing) behavior vs. the wanted behavior?
   - Which page/route/file, if not obvious from the description?
   - Bug, enhancement, or brushup (small/internal)?
   - Priority — normal, or `urgent`?
   - Anything explicitly out of scope?
3. Once answered, write the issue — no further questions, no confirmation round-trip:
   - Title: short, specific, imperative (e.g. "Fix X not saving on Y page").
   - Body: `## Problem` (current state), `## Expected` (wanted state), `## Notes` (scope/edge cases, only if relevant).
   - Labels: pick from `bug`, `enhancement`, `brushup`, `documentation`, `urgent` — match the repo's existing label set (`gh label list`), don't invent new ones.
4. Create it: `gh issue create --repo $(gh repo view --json nameWithOwner -q .nameWithOwner) --title "..." --body "..." --label "..."`.
5. Report back: the issue number + URL, one line. Nothing else — no summary of what you wrote, the issue itself is the record.
