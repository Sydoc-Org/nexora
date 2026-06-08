---
description: Verify a nexora UI change in the browser — restart server, auto-login, screenshot, compare
argument-hint: "<route-or-page> [user]"
---

Verify a UI change by actually rendering it and capturing a screenshot — don't ask the user to look, drive the browser yourself. Reference: `docs/howto/nx.md`, `docs/howto/claude-workflow.md`.

Target: $ARGUMENTS (a route like `/reporting`, or a page name; optional user to log in as).

Steps:

1. **Restart the dev server first.** Jinja templates are cached for the process lifetime, so any template/partial edit needs a fresh server or you'll screenshot stale HTML. Start (or restart) with auto-login: `nx -u -b --loginas:<user>` — pick a user who holds the permission for the page under test.
2. **Navigate** to the target page using the Playwright MCP tools.
3. **Screenshot** the result into `var/screenshots/` (never the repo root). For a redesign, capture a **before/after** pair.
4. **Compare to intent** — list the concrete visual differences against the design/goal, fix them, re-screenshot, and iterate until it matches.
5. For a rollout across many pages (e.g. applying nexora-ui to the Reporting page), repeat per page with a before/after pair so each page is independently verified.

Notes:
- If running remotely, surface the screenshots to the user (send the files) — they can't see the screen.
- Keep one browser MCP active: Playwright for routine UI work; chrome-devtools only when you need perf / a11y / Lighthouse.
