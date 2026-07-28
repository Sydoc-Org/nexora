---
description: Look up a GitHub issue, interpret what's actually being asked, and report back for approval before touching code
argument-hint: "<issue_number>"
---

Look up GitHub issue `$1` and figure out what's actually being asked — then STOP and report back. Do not start implementing, do not open a plan.

1. `gh issue view $1 --repo $(gh repo view --json nameWithOwner -q .nameWithOwner) --comments` — read title, body, labels, and all comments.
2. Issue bodies here are often screenshot-only with little or no text. If the body/comments reference `github.com/user-attachments/assets/...` images, download with an auth token (plain curl 404s on these):
   `curl -sL -H "Authorization: Bearer $(gh auth token)" "<url>" -o <scratchpad>/issue$1.png`
   then Read the image.
3. If the issue references a page/feature that exists in the repo, do a quick Grep/Glob to ground the interpretation in real code rather than guessing blind.
4. Report back: a short plain-language read of what's wrong or wanted, and what you'd guess the fix touches. Flag explicitly if the issue is ambiguous, image-only, or you're inferring beyond what's stated.
5. Recommend a model + effort tier for doing the actual fix (e.g. "sonnet, low" for a scoped 2-file CSS/JS tweak; "opus, high" for a multi-system change) — one line, with a one-clause reason.
6. Wait for the user to correct or approve before writing any code.
7. Once approved and you start work, label the issue `inprogress` (`gh issue edit $1 --add-label inprogress`), plus `bug`/`enhancement`/`brushup` if none of those are already set.
8. If the fix touches templates/, static/, or any *_js.html partial: after fixing, restart the dev server (`nx -r` — Jinja templates cache for the process lifetime), drive it with Playwright (`nx -u -b --loginas:ben.streich` if not already up) to the real page showing the bug, screenshot it, and send it with SendUserFile. Reproduce the original screenshot's exact scenario where possible (same field/table/data shape) rather than an arbitrary example.
