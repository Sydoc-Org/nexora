> **➡ SUPERSEDED — a later 2026-06-14 session executed this.** Continue from
> `docs/superpowers/handoffs/2026-06-14-autopilot-self-healing-layer-built.md` (fixer fixed+wired,
> auto-push + cost cap + watchdog built, clarify-loop + parallel-on-clones specced).

# Handoff — Autopilot tooling: fixer + unbuilt-design roadmap

**Date:** 2026-06-14 · **Branch:** `feature/2.5.63` · **159 commits unpushed** · **commit-only (remote)**
**Prior handoff:** `docs/superpowers/handoffs/2026-06-13-reporting-ui-redesign-plan.md`
**Durable context also in auto-memory:** `project_n8n_autopilot` (loads every session — read it).

## TL;DR

- Built a full **GitHub-issue → n8n → Claude autopilot**: label an issue `autopilot`, a local n8n
  workflow runs `/write-plan` (Opus) → `/execute-plan` (Sonnet) → **commits** the result on
  `feature/2.5.63`, with Telegram notifications. It is **live and works** — it autonomously built
  **#88** this session (real code: `5f24d0e` fix + tests + changelog).
- The whole thing lives in **`tools/autopilot/`** + **`bin/nx.ps1`** + the live n8n workflow
  **`PzQXpt99pIIV7fJv`** ("nexora claude workflow", currently **INACTIVE**).
- **Next session, do (in order):** (1) **fix + harden + wire the fixer** (`solve-blocked.ps1`),
  (2) **build the unbuilt designs** (Telegram clarify loop, auto-push, parallel-via-clones,
  n8n-service+watchdog, cost cap). Details below.

## This session's commits (newest → oldest, the tooling ones)

```
2096871 feat(autopilot): fixer script for self-healing on halt   <-- COMMITTED BUT BROKEN (see gotchas)
11ccb6c feat(autopilot): live run log + nx --workflow-logs
984e4e3 chore(nx): drop -iw/-kw short aliases
d577bda refactor(nx): rename autopilot cmd to invoke-workflow, run detached
49bd8a7 fix(autopilot): self-healing lock so a crashed run can't wedge it
602f197 fix(autopilot): report the real halt reason, not a generic message
16ada2f feat(nx): add autopilot launcher and queue commands
f41a5fd docs(autopilot): warn that import drops edges if nodes unresolved
98cd2ad feat(autopilot): add start-n8n.ps1 launcher with required env
43ee851 docs(autopilot): leave n8n execution timeout unset
53701b6 docs(autopilot): document mandatory n8n env vars
2164611 fix(autopilot): plan phase runs on opus (fable 5 now US-only)
875fc86 fix(autopilot): gate headless agent on trusted issue authors
71a1cba feat(autopilot): importable n8n workflow, README, signal contract
440768a feat(autopilot): command-adapter scripts for the n8n loop
b628c8e docs(autopilot): record headless gate confirmation and json envelope
236eed9 docs(autopilot): implementation plan
4cdb9a2 docs(autopilot): n8n autopilot design spec
d86787b chore(autopilot): exclude dev-only tools/ dir from deploy
```
**Interleaved, produced BY the autopilot itself (not hand-written):** `#88` build —
`acfd6e3`/`97f7960` (plan), `10b313f`+`5f24d0e`+`9ae0779` (fix+tests), `501b26b` (changelog),
`cbb9b41` (handoff); `#90` plan — `fff24ad`+`c8464f5` (planned, then execute halted).

## What shipped

| Area | Files |
|------|-------|
| Adapter scripts | `tools/autopilot/`: `setup-labels.ps1`, `fetch-queue.ps1`, `lock.ps1`, `baseline.ps1`, `run-phase.ps1`, `probe-state.ps1`, `comment-result.ps1`, `solve-blocked.ps1` (broken), `start-n8n.ps1` |
| n8n workflow (source) | `tools/autopilot/n8n-autopilot.workflow.json` (25 nodes) — already imported as live workflow `PzQXpt99pIIV7fJv` |
| Docs | `tools/autopilot/README.md`, `SIGNALS.md`; spec `docs/superpowers/specs/2026-06-13-n8n-autopilot-design.md`; plan `docs/superpowers/plans/2026-06-13-n8n-autopilot.md` |
| CLI | `bin/nx.ps1`: `--invoke-workflow` (start n8n bg), `--kill-workflow`, `--workflow-logs` (tail live run), `--queue:"title"` `--body:"…"` |
| Deploy | `tools/` added to `deploy.yml` `/XD` |

**Live n8n state:** workflow `PzQXpt99pIIV7fJv` is wired (Telegram cred "Telegram account" id
`JIABjX2swG8T9b94`, chat id `8640120021`, bot `@nexora_n8n_bot`), all 25 nodes resolve, **INACTIVE**
(I deactivated it during debugging — reactivate via Publish toggle when ready). Data-saving is ON.

## Next steps (ordered — this is the ask)

**1. The fixer (`solve-blocked.ps1`):**
   - **Fix the syntax bug** — it has an invalid `$…:` reference in the prompt here-string (PowerShell
     `ParseFile` fails). Parse-check with the one-liner in "How to verify".
   - **Security-harden** (a HIGH security-review finding is open on it): add the explicit
     trusted-author hard-check that `run-phase.ps1` has, and match `run-phase.ps1`'s untrusted-body
     delimiters. `--dangerously-skip-permissions` stays by design (author gate is the control).
   - **Wire into the live n8n**: the three halt branches (`clean?`/`plan-ok?`/`exec-ok?` false) →
     `solve-blocked` node (`pwsh -File …\solve-blocked.ps1 -IssueNumber {{…number}} -Reason {{…}}`) →
     a baseline + re-verify (`probe-state -Phase execute`) → IF ok → `comment-built`; else →
     `mark-blocked`. One-shot (no loop). Do this via the REST PATCH pattern in README / the way this
     session patched nodes (browser_evaluate `fetch('/rest/workflows/<id>', {method:'PATCH'…})`).
     **Only patch the live workflow when NO build is running** (editing an active workflow crashed an
     execution this session).

**2. Unbuilt designs (build after the fixer):**
   - **Telegram two-way clarify loop** — prompt protocol: agent emits `QUESTIONS-FOR-OWNER:` and stops
     instead of guessing → new outcome `autopilot-needs-input` posts the questions to Telegram → a
     **second n8n workflow with a Telegram Trigger** catches the owner's reply, matches it to the
     issue (reply-to message-id), drops the answer as an issue comment, removes the label → re-queue;
     `run-phase` reads owner-clarification comments into the build prompt.
   - **Auto-push feature branch on success** — after a built issue, `python scripts/test_db_reset.py`
     then `git push origin feature/2.5.63`. **NEVER open a PR. NEVER push/merge `main`. NEVER deploy**
     (deploy.yml triggers only on push/PR to `main`, so never-main ⇒ never-deploy is structural; also
     hard-assert refuse-if-main in the push step). The pre-push hook runs the e2e gate, so only
     test-passing builds push; if it fails, don't push, Telegram "built but tests failed #N". Never
     `--no-verify`.
   - **Parallel-on-branches (3 concurrent, off `feature/2.5.63`)** — MUST use **separate local clones**
     per lane, NOT worktrees: `handoff-session-state --merge-worktree` merges into the *base repo's*
     current branch (`feature/2.5.63`), so worktrees can't isolate branches. Clone per lane (hardlinked
     local clone), build in-place on `auto/issue-NN`, fetch the branch back to the main repo. Watch the
     shared INT DB (parallel test runs interfere).
   - **n8n-as-service + watchdog** + **cost cap** — for unattended "while away" reliability.

   Design rationale + decisions for all of the above are in the conversation that produced this
   handoff; the away-mode policy is also saved in memory `project_n8n_autopilot`.

## Gotchas & notes (READ)

- **Autopilot builds in the MAIN tree** (`/write-plan` only makes a worktree if the branch is busy;
  the clean-tree pre-flight means it never is) → **nobody touches `C:\dev\nexora` while a build runs.**
- **n8n env vars are MANDATORY** (set by `start-n8n.ps1` / `nx --invoke-workflow`): `N8N_SECURE_COOKIE=false`
  (else login can't load `/types/nodes.json` → every node "not installed") and
  `NODES_EXCLUDE='["n8n-nodes-base.localFileTrigger"]'` (n8n 2.x excludes the **Execute Command** node by
  default — autopilot is built from it). n8n is **2.8.4**.
- **Self-healing lock** — `lock.ps1` reclaims a lock if no autopilot `claude` is alive (3-min grace) or
  past 1.5h; `start-n8n.ps1` clears it on boot. Fixed the "always fails at got-lock?" leak.
- **Policy:** push/merge to feature branches OK; **NEVER PR, NEVER main, NEVER deploy.** Trusted-author
  gate (`AUTOPILOT_ALLOWED_AUTHORS`, default `benstreich`). `SQL_SYNC_SKIP=1` on every commit.
- **`solve-blocked.ps1` is committed but BROKEN and NOT wired** → harmless until fixed+wired.

## Untracked / left for owner

- **`git stash@{0}`** = #90's partial UI WIP (halted "Upgrade the UI" build) — recover or drop.
- **#89** is a **duplicate of #88** (#88 built + CLOSED) — close #89 as dup. (`autopilot-blocked`)
- **#90** halted (issue too vague for unattended build) — `autopilot-blocked`; the plan it wrote is at
  `docs/superpowers/plans/2026-06-13-reporting-ui-redesign*.md`.
- The live n8n workflow is **INACTIVE** — left for the owner to reactivate.
- `var/handoff-pending` points at this file (gitignored).

## How to verify

```powershell
# fixer parse check (currently FAILS — that's the bug to fix):
pwsh -NoProfile -Command "$t=$null;$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('C:\dev\nexora\tools\autopilot\solve-blocked.ps1',[ref]$t,[ref]$e); if($e){'BROKEN'}else{'OK'}"
nx --invoke-workflow          # start n8n (http://localhost:5678/, workflow PzQXpt99pIIV7fJv)
nx --workflow-logs            # tail a live run
git stash list                # see #90's stashed WIP
```

## Resuming in a fresh session

`/reset-session` (this file is flagged in `var/handoff-pending`). Then read, in order:
`project_n8n_autopilot` memory → this handoff → `tools/autopilot/README.md` → the spec + plan. Start at
**Next steps #1 (fix + wire the fixer)**.
