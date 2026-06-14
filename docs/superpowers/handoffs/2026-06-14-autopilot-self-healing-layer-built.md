# Handoff — Autopilot self-healing layer built (fixer + auto-push + cost cap + watchdog)

**Date:** 2026-06-14 (later session) · **Branch:** `feature/2.5.63` · **commit + push (this turn)**
**Prior handoff:** `docs/superpowers/handoffs/2026-06-14-autopilot-fixer-and-roadmap.md` (the morning
ask that this session executed).
**Durable context also in auto-memory:** `project_n8n_autopilot` (read it).

## TL;DR

Executed the morning handoff's "next steps". **Step 1 (fix + harden + wire the fixer) is done and
verified.** Of "Step 2 (unbuilt designs)" I built the two contained, low-risk ones — **opt-in
auto-push** and **away-mode reliability (cost cap + watchdog)** — and wrote a precise **build-spec**
for the two that need an interactive smoke-validation (the **Telegram clarify loop** and
**parallel-on-clones**), which should not be wired unattended-and-unvalidated.

5 commits this session (`35e4f87`, `9f3d126`, `508efc9`, `76a69d3`, + this handoff).

## What shipped (all committed)

| Commit | What |
|--------|------|
| `35e4f87` | **The fixer, fixed + hardened + wired.** `solve-blocked.ps1` rewritten; `lock.ps1` cap 1.5h→3h; `n8n-autopilot.workflow.json` halt branches → `solve-blocked` → `fix-ok?`. |
| `9f3d126` | **Opt-in auto-push.** `push-branch.ps1` + wired at queue-drain. OFF unless `AUTOPILOT_AUTOPUSH=1`. |
| `508efc9` | **Watchdog + daily cost cap.** `watchdog.ps1` (restart dead n8n) + `cost-guard.ps1` (per-day USD ledger) wired as a per-issue gate + per-phase accounting. |
| `76a69d3` | **Docs.** README (new scripts, env vars, flow, policy) + the roadmap build-spec. |

### The fixer (`solve-blocked.ps1`) — what was wrong and what it does now
- **Was:** a PowerShell parse error (`$IssueNumber:` namespace-var trap), no trusted-author gate
  (open HIGH security finding), unwired.
- **Now:** parses; mirrors `run-phase.ps1`'s security model (author allowlist + token scrub +
  untrusted-data framing — and the **title** is newline-stripped + framed as untrusted, since a
  GitHub title is author-set, not maintainer-set); **never throws** (emits an `ok:false` verdict +
  `exit 0` on refusal/gh-failure/error so a transient hiccup can't crash the n8n node into a
  re-queue-every-2-min spiral); **self-verifies** (committed+clean+no-leftover-worktree OR
  `ALREADY-DONE`) instead of the morning handoff's `probe-state` re-verify, which had a
  baseline-ordering bug. The `ALREADY-DONE` read filters the claude stream to the `"type":"result"`
  line first (a trailing `{"type":"system"}` line was masking it — caught by adversarial review).
- **Wiring:** `clean?`/`plan-ok?`/`exec-ok?` false → `solve-blocked` → `fix-ok?`; **fixed** →
  `notify-fixed` (🛠️ Telegram that **surfaces any stashed WIP** — the user is stash-sensitive) →
  `comment-built` → resume queue; **still-blocked** → `mark-blocked` → halt.
- **Reviewed:** a 3-lens adversarial Workflow found 1 HIGH (dead ALREADY-DONE) + others; all fixed;
  an independent verifier returned **SAFE TO COMMIT**.

### The other three pieces
- **`push-branch.ps1`** — at queue-drain (once, not per-issue): hard-refuse main/master → reset
  `NEXORA_TEST` → `git push` through the **full** pre-push e2e gate (never `--no-verify`/`--force`).
  `notify-summary` reports the result. **OFF by default.**
- **`cost-guard.ps1`** — `cost-check` gates each issue before planning; over `AUTOPILOT_DAILY_USD_CAP`
  (default $25) → `notify-costcap` + halt (resumes next day). `cost-add` after run-plan/run-exec books
  each phase's `total_cost_usd` from the `run.log` result line. **Fails open**, never throws.
- **`watchdog.ps1`** — restart a dead n8n (`:5678`) via `start-n8n.ps1`; single-shot (Task Scheduler)
  or loop; optional Telegram via `AUTOPILOT_TG_TOKEN`/`AUTOPILOT_TG_CHAT`.

The workflow JSON is **25 → 34 nodes**; JSON valid, every connection endpoint resolves (validated).

## Next steps (the roadmap — designed, not built)

Build-spec: **`docs/superpowers/specs/2026-06-14-autopilot-clarify-and-parallel-design.md`**.
1. **Telegram clarify loop** — ask-instead-of-guess via a **controllable pre-plan `triage.ps1`**
   (NOT a self-stopping `/write-plan`), a `autopilot-needs-input` label, a second
   `n8n-clarify-reply.workflow.json` (Telegram Trigger → comment → unlabel → re-queue), and
   `run-phase` reading `owner-clarification:` comments. Graceful-degradation makes wiring it safe.
2. **n8n-as-a-service + scheduled watchdog** — NSSM/Task Scheduler with the MANDATORY env persisted.
3. **Parallel-on-clones** — separate local clones per lane (NOT worktrees — they merge to the base
   branch), serial DB step (shared INT/TEST DB). Largest; do last.
Each ends in ONE interactive smoke gate.

## Gotchas & notes (READ)

- **The live n8n workflow `PzQXpt99pIIV7fJv` is INACTIVE and was NOT patched.** The corrected source
  JSON is the source of truth → **re-import it** (n8n editor → Import from File) and re-wire the now
  **5** Telegram nodes (`notify-built`/`-halt`/`-summary`/`-fixed`/`-costcap`) to the
  `autopilot-telegram` cred + chat id (README "Import & wire"). Only do this when **no build is
  running** (editing an active workflow crashed an execution last session).
- **This dir is a PHANTOM worktree.** `C:\dev\nexora\.claude\worktrees\plan-reporting-page-
  improvement-options` is NOT a registered git worktree — it's a gitignored leftover folder (6 PNGs).
  All git ops here resolve to the MAIN repo `C:\dev\nexora`. Use absolute `C:\dev\nexora\...` paths;
  Glob/Grep need an explicit `path` or they search the empty phantom dir.
- **Deviations from the morning handoff (intentional, documented in the script headers):** fixer
  self-verifies instead of `probe-state` re-verify; a distinct `notify-fixed`; cost cap added.
- Still-open from the morning handoff: `git stash@{0}` (#90 WIP), close **#89** as dup-of-#88, #90
  `autopilot-blocked`. Untouched this session.

## How to verify

```powershell
# all four scripts parse:
foreach($f in 'solve-blocked','push-branch','cost-guard','watchdog'){ $e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile("C:\dev\nexora\tools\autopilot\$f.ps1",[ref]$null,[ref]$e); "$f: $(if($e){'BROKEN'}else{'OK'})" }
# workflow JSON valid + endpoints resolve:
$wf = gc C:\dev\nexora\tools\autopilot\n8n-autopilot.workflow.json -Raw | ConvertFrom-Json; "nodes=$($wf.nodes.Count)"
```

## Resuming in a fresh session

`/reset-session` (flag in `var/handoff-pending`). Read `project_n8n_autopilot` → this handoff →
the roadmap build-spec. Start at **clarify loop**.
