# n8n Autopilot for the Claude Code Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drive the existing `/write-plan` → `/execute-plan` loop unattended via a local n8n workflow, fed by GitHub issues labelled `autopilot`, stopping at `git commit` and reporting to Telegram.

**Architecture:** Local native n8n polls GitHub for `autopilot`-labelled issues, takes a single-run lockfile, and runs an n8n-native loop. Each issue is planned (`claude -p` on Fable) and executed (`claude -p` on Sonnet) in headless print mode; success/blocked is decided by inspecting git + handoff state (not exit codes) via a small stateless `probe-state.ps1`; branching, looping, and notifications live on the n8n canvas. First failure halts the run.

**Tech Stack:** n8n (native npm, Node 22), Claude Code CLI headless (`claude -p --output-format json`), `gh` CLI, PowerShell 7 (pwsh), Telegram Bot API, git worktrees.

**Spec:** `docs/superpowers/specs/2026-06-13-n8n-autopilot-design.md`

**Conventions baked into every Claude invocation:**
- `$env:SQL_SYNC_SKIP='1'` set in the child pwsh before `claude` (else internal commits die on INT CRLF drift). Scoped to the child process — never leaks to your shell.
- cwd = `C:\dev\nexora`; never `--no-verify`; never `git push`; never PR.
- `--effort high` (NOT "ultracode" — not a valid `--effort` value).

---

## Task 1: Headless smoke-test GATE — prove the multi-agent skills run under `claude -p`

This is a hard gate. `/write-plan` spawns a 7-agent Workflow and `/execute-plan` runs subagent-driven-development. If those cannot spawn under `-p`, the whole design changes. **Do not proceed to Task 2 until this passes.** This task is also where we capture the EXACT success/blocked signals the verifier in Task 4 keys off.

**Files:**
- Create: `var/autopilot/smoke/` (scratch dir for captured JSON — gitignored, see Step 6)

- [ ] **Step 1: Pick a tiny throwaway feature description**

Use a trivial, self-contained ask so the smoke test is cheap, e.g. `add a code comment banner to nx_lib/reporting/export.py`. Do NOT use a real queued issue yet.

- [ ] **Step 2: Capture the git baseline**

Run (pwsh, from `C:\dev\nexora`):
```powershell
$before = git -C C:\dev\nexora rev-parse HEAD
$before
```
Expected: a 40-char sha. Save it.

- [ ] **Step 3: Run `/write-plan` headless and capture the JSON result**

```powershell
$env:SQL_SYNC_SKIP='1'
$prompt = "/write-plan add a code comment banner to nx_lib/reporting/export.py"
New-Item -ItemType Directory -Force C:\dev\nexora\var\autopilot\smoke | Out-Null
$prompt | claude -p --model fable --dangerously-skip-permissions --output-format json --effort high `
  *> C:\dev\nexora\var\autopilot\smoke\plan-result.json
Get-Content C:\dev\nexora\var\autopilot\smoke\plan-result.json
```
Expected: a JSON object ending with `"type":"result"`. **Record these fields** — they drive Task 4: `subtype` (e.g. `success` vs `error_max_turns`), `is_error`, `session_id`, `num_turns`. If the run errors immediately with a tool/agent-spawn restriction → **STOP, gate failed** (see Step 7).

- [ ] **Step 4: Confirm the plan side-effects landed**

```powershell
git -C C:\dev\nexora log --oneline "$before..HEAD"          # expect a "plan:" commit
Get-Content C:\dev\nexora\var\handoff-pending                # expect a path to a fresh handoff
Get-ChildItem C:\dev\nexora\docs\superpowers\plans\ | Sort-Object LastWriteTime | Select-Object -Last 1
git -C C:\dev\nexora worktree list                          # expect a new .claude\worktrees\plan-* entry
```
Expected: a new plan commit, `var/handoff-pending` repointed, a fresh plan md, and (since the branch was busy) a new worktree. **Record** the worktree path + branch name pattern.

- [ ] **Step 5: Run `/execute-plan` headless and confirm the merge-back**

```powershell
$beforeExec = git -C C:\dev\nexora rev-parse HEAD
$env:SQL_SYNC_SKIP='1'
"/execute-plan" | claude -p --model sonnet --dangerously-skip-permissions --output-format json `
  *> C:\dev\nexora\var\autopilot\smoke\exec-result.json
Get-Content C:\dev\nexora\var\autopilot\smoke\exec-result.json
git -C C:\dev\nexora log --oneline "$beforeExec..HEAD"       # expect feature commit(s)
git -C C:\dev\nexora worktree list                           # expect the plan-* worktree GONE
Get-Content C:\dev\nexora\var\handoff-pending                # inspect for BLOCKED markers
```
**Record:** what a SUCCESS handoff looks like vs a BLOCKED one (search the handoff doc text for the literal markers the skill writes — e.g. "BLOCKED", "max_turns", "incomplete"). These literals become the verifier's blocked-detection in Task 4.

- [ ] **Step 6: Clean up the smoke test**

```powershell
git -C C:\dev\nexora reset --hard $before        # drop the throwaway plan+feature commits
git -C C:\dev\nexora worktree prune
# if a plan-* worktree/branch lingers:
git -C C:\dev\nexora worktree list
# remove any leftover smoke worktree dir + branch shown above, then:
git -C C:\dev\nexora branch -D plan/add-a-code-comment-banner 2>$null
```
Add `var/autopilot/smoke/` to `.gitignore` (scratch JSON, never committed):
```
echo "var/autopilot/smoke/" | Out-File -Append -Encoding utf8 C:\dev\nexora\.gitignore
```

- [ ] **Step 7: GATE decision + commit the recorded signals**

Write the observed signal table to `tools/autopilot/SIGNALS.md` (the exact `subtype` strings, the handoff BLOCKED literals, the worktree path pattern, the plan-commit message prefix). Then:
```powershell
git -C C:\dev\nexora add tools/autopilot/SIGNALS.md .gitignore
$env:SQL_SYNC_SKIP='1'; git -C C:\dev\nexora commit -F <message file>
```
Commit message (wrap body ≤100 cols, gitlint needs a body):
```
chore(autopilot): record headless claude -p signal contract

Smoke-tested /write-plan and /execute-plan under claude -p. Captured
the result-JSON subtypes and handoff BLOCKED markers that the n8n
verifier keys off. Gate passed.
```
**If the gate FAILED** (skills can't spawn agents under `-p`): stop here, record the failure mode in `SIGNALS.md`, and report back — the loop-brain needs redesign (likely drive the multi-agent step via a different invocation), which is a spec change, not a plan tweak.

---

## Task 2: Prerequisites — install n8n, create labels, set up Telegram

**Files:**
- Create: `tools/autopilot/setup-labels.ps1`
- Create: `tools/autopilot/README.md` (started here, finished in Task 7)

- [ ] **Step 1: Install n8n natively and confirm it starts**

```powershell
npm i -g n8n
n8n --version            # expect a version string (NOT "command not found")
```

- [ ] **Step 2: Start n8n once and open the editor**

```powershell
n8n start
```
Expected: console prints `Editor is now accessible via: http://localhost:5678/`. Open it, finish the owner-account setup. Leave it running in its own terminal (it must be up for the loop to run).

- [ ] **Step 3: Write the label-creation script**

`tools/autopilot/setup-labels.ps1`:
```powershell
$repo = "Sydoc-Code/nexora"
gh label create autopilot         --repo $repo --color "1d76db" --description "Build this issue unattended via n8n autopilot"          --force
gh label create autopilot-built   --repo $repo --color "0e8a16" --description "Autopilot built it locally; commit pending owner push" --force
gh label create autopilot-blocked --repo $repo --color "b60205" --description "Autopilot halted on this issue; needs a human"          --force
gh label list --repo $repo | Select-String "autopilot"
```

- [ ] **Step 4: Run it and confirm the three labels exist**

```powershell
pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\setup-labels.ps1
```
Expected: three `autopilot*` rows printed.

- [ ] **Step 5: Create the Telegram bot + capture token and chat id**

In Telegram: message `@BotFather` → `/newbot` → record the **token**. Then message your new bot once ("hi"), and:
```powershell
$token = "<bot-token>"
(Invoke-RestMethod "https://api.telegram.org/bot$token/getUpdates").result[-1].message.chat.id
```
Expected: a numeric **chat id**. Record both. In the n8n editor: Credentials → New → Telegram API → paste the token. Save as `autopilot-telegram`.

- [ ] **Step 6: Commit the setup artifacts**

```powershell
git -C C:\dev\nexora add tools/autopilot/setup-labels.ps1 tools/autopilot/README.md
$env:SQL_SYNC_SKIP='1'; git -C C:\dev\nexora commit -F <message file>
```
Message:
```
chore(autopilot): n8n install notes, GitHub label setup, telegram bot

Adds setup-labels.ps1 (creates autopilot / autopilot-built /
autopilot-blocked) and README scaffolding. n8n installed natively;
Telegram credential added in the editor.
```

---

## Task 3: The state probe — `probe-state.ps1` (the testable verifier unit)

A stateless script that inspects git + handoff state and emits JSON. The n8n canvas calls it and an IF node branches on the result, so the loop brain stays on the canvas (your choice) while the fragile inspection is a unit we can run and verify on its own.

**Files:**
- Create: `tools/autopilot/probe-state.ps1`

- [ ] **Step 1: Write `probe-state.ps1`**

```powershell
[CmdletBinding()]
param(
  [Parameter(Mandatory)][ValidateSet('plan','execute')] [string]$Phase,
  [Parameter(Mandatory)][string]$BeforeSha,
  [string]$RepoPath = 'C:\dev\nexora'
)
$ErrorActionPreference = 'Stop'
$head     = (git -C $RepoPath rev-parse HEAD).Trim()
$advanced = $head -ne $BeforeSha
$newLog   = git -C $RepoPath log --oneline "$BeforeSha..HEAD"

if ($Phase -eq 'plan') {
  $handoff = Join-Path $RepoPath 'var\handoff-pending'
  $planCommit = ($newLog | Select-String -SimpleMatch 'plan:') -ne $null
  $out = [ordered]@{
    phase        = 'plan'
    headSha      = $head
    commitLanded = $advanced
    planCommit   = [bool]$planCommit
    handoffFresh = (Test-Path $handoff)
    ok           = ($advanced -and $planCommit -and (Test-Path $handoff))
  }
} else {
  # execute: success = a feature commit landed, the plan-* worktree merged away,
  # and the handoff shows no BLOCKED marker. BLOCKED literals come from Task 1 SIGNALS.md.
  $wtOpen = (git -C $RepoPath worktree list) -match 'worktrees[\\/]+plan-'
  $handoffDir = Join-Path $RepoPath 'docs\superpowers\handoffs'
  $latestHandoff = Get-ChildItem $handoffDir -Filter *.md -ErrorAction SilentlyContinue |
                   Sort-Object LastWriteTime | Select-Object -Last 1
  $blockedMarker = $false
  if ($latestHandoff) {
    $blockedMarker = [bool](Select-String -Path $latestHandoff.FullName -Pattern 'BLOCKED|max_turns|incomplete' -SimpleMatch -ErrorAction SilentlyContinue)
  }
  $out = [ordered]@{
    phase         = 'execute'
    headSha       = $head
    commitLanded  = $advanced
    worktreeMerged= (-not [bool]$wtOpen)
    blocked       = [bool]$blockedMarker
    ok            = ($advanced -and -not $wtOpen -and -not $blockedMarker)
  }
}
$out | ConvertTo-Json -Compress
```

- [ ] **Step 2: Verify the plan-phase probe against a known state**

```powershell
$h = git -C C:\dev\nexora rev-parse HEAD
pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\probe-state.ps1 -Phase plan -BeforeSha $h
```
Expected: JSON with `"commitLanded":false,"ok":false` (HEAD == BeforeSha, nothing landed). This proves the probe reports "not ok" on a no-op — the safe default.

- [ ] **Step 3: Verify the execute-phase probe reports a clean tree as merged**

```powershell
pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\probe-state.ps1 -Phase execute -BeforeSha $h
```
Expected: JSON with `"worktreeMerged":true` (no `plan-*` worktree currently open) and `"ok":false` (no new commit). Confirms worktree detection + the conservative `ok`.

- [ ] **Step 4: Reconcile the BLOCKED literals with Task 1**

Open `tools/autopilot/SIGNALS.md` (from Task 1). If the real handoff BLOCKED wording differs from `BLOCKED|max_turns|incomplete`, update the `-Pattern` in `probe-state.ps1` to match the observed literals. Re-run Step 3.

- [ ] **Step 5: Commit the probe**

```powershell
git -C C:\dev\nexora add tools/autopilot/probe-state.ps1
$env:SQL_SYNC_SKIP='1'; git -C C:\dev\nexora commit -F <message file>
```
Message:
```
feat(autopilot): state probe for headless plan/execute verification

probe-state.ps1 emits JSON describing whether a plan/execute phase
landed its commit, merged its worktree, and is free of BLOCKED
markers. The n8n IF nodes branch on this instead of exit codes.
```

---

## Task 4: Build the n8n workflow — trigger, lock, and the per-issue loop

Build on the canvas, verifying each group with a dry run (no Claude) before wiring the next. Node commands below go verbatim into Execute Command nodes (Command = `pwsh`, Arguments = `-NoProfile -Command "<snippet>"`). Connections described per step.

**Files:**
- (built in the n8n editor; exported to repo in Task 7)

- [ ] **Step 1: Schedule Trigger + queue fetch**

Add **Schedule Trigger** (every 2 minutes). Wire → **Execute Command** "fetch-queue":
```
gh issue list --repo Sydoc-Code/nexora --label autopilot --state open --json number,title,labels --jq '[.[] | select((.labels|map(.name)) as $l | (($l|index(\"autopilot-built\"))|not) and (($l|index(\"autopilot-blocked\"))|not))] | sort_by(.number)'
```
Wire → **Code** node "parse-queue": `return JSON.parse($json.stdout || '[]').map(i => ({json:i}));`

- [ ] **Step 2: Dry-run the queue**

Label a throwaway GitHub issue `autopilot`. Click "Execute Workflow". Expected: the parse-queue node outputs that issue (number/title). Remove the label after. This proves polling + filter without touching Claude.

- [ ] **Step 3: Lock guard**

After parse-queue add **IF** "queue-empty?" (`{{$items().length}}` == 0 → stop). Else → **Execute Command** "acquire-lock":
```
$lock='C:\dev\nexora\var\autopilot.lock'; if(Test-Path $lock){ $age=(Get-Date)-(Get-Item $lock).LastWriteTime; if($age.TotalHours -lt 3){ 'LOCKED' | Write-Output; exit 0 } }; @{ts=(Get-Date -Format o);pid=$PID}|ConvertTo-Json|Set-Content $lock; 'ACQUIRED' | Write-Output
```
Wire → **IF** "got-lock?" (`{{$json.stdout.trim()}}` == `ACQUIRED`). False branch → stop quietly. True → loop.

- [ ] **Step 4: Loop Over Items (oldest first)**

Add **Loop Over Items** (SplitInBatches, batch size 1). Input is the queue array (already sorted ascending). Its loop output drives the per-issue body (Steps 5–8); its done output drives Task 6's summary + lock release.

- [ ] **Step 5: Pre-flight clean check**

In the loop body, **Execute Command** "preflight":
```
$s = git -C C:\dev\nexora status --porcelain; if($s){ 'DIRTY' } else { 'CLEAN' }
```
Wire → **IF** "clean?" (`== CLEAN`). False → halt branch (Task 5). True → plan.

- [ ] **Step 6: Capture baseline + run plan**

**Execute Command** "baseline-plan": `git -C C:\dev\nexora rev-parse HEAD` → store via **Set** node `beforePlan = {{$json.stdout.trim()}}`.
Then **Execute Command** "run-plan" (the issue title+body come from the loop item):
```
$env:SQL_SYNC_SKIP='1'; $b=@'
{{$json.title}}

{{$json.body}}
'@; ("/write-plan " + $b) | claude -p --model fable --dangerously-skip-permissions --output-format json --effort high
```
Wire → **Execute Command** "verify-plan":
```
pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\probe-state.ps1 -Phase plan -BeforeSha {{ $node["baseline-plan"].json.stdout.trim() }}
```
Wire → **IF** "plan-ok?" on `{{ JSON.parse($json.stdout).ok }}`. False → halt. True → execute.

- [ ] **Step 7: Capture baseline + run execute**

**Execute Command** "baseline-exec": `git -C C:\dev\nexora rev-parse HEAD` → **Set** `beforeExec`.
**Execute Command** "run-exec":
```
$env:SQL_SYNC_SKIP='1'; "/execute-plan" | claude -p --model sonnet --dangerously-skip-permissions --output-format json
```
Wire → **Execute Command** "verify-exec":
```
pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\probe-state.ps1 -Phase execute -BeforeSha {{ $node["baseline-exec"].json.stdout.trim() }}
```
Wire → **IF** "exec-ok?" on `{{ JSON.parse($json.stdout).ok }}`. False → halt. True → success.

- [ ] **Step 8: Save partial workflow + dry-note**

Save the workflow (name `autopilot`). Do NOT run a full live pass yet — Task 5 adds the success/halt branches first. Verify the canvas wiring visually: trigger→fetch→parse→queue-empty→acquire-lock→got-lock→loop→preflight→plan→verify→execute→verify, with every IF false-branch currently dangling (wired in Task 5).

---

## Task 5: Success and halt branches + cleanup

**Files:**
- (n8n editor)

- [ ] **Step 1: Success branch (after exec-ok true)**

**Execute Command** "comment-success":
```
$sha = git -C C:\dev\nexora rev-parse --short HEAD; gh issue comment {{$json.number}} --repo Sydoc-Code/nexora --body ("Autopilot built this locally - commit " + $sha + ", pending owner review and push."); gh issue edit {{$json.number}} --repo Sydoc-Code/nexora --add-label autopilot-built
```
Wire → **Telegram** "notify-built" (cred `autopilot-telegram`, chat id from Task 2): text `✅ #{{$json.number}} built — commit pending push`.
Wire → back into the **Loop Over Items** node (next issue).

- [ ] **Step 2: Halt branch (any verify/preflight false → shared path)**

Merge the three false-branches (preflight, plan-ok, exec-ok) into **Execute Command** "mark-blocked":
```
gh issue edit {{$json.number}} --repo Sydoc-Code/nexora --add-label autopilot-blocked; gh issue comment {{$json.number}} --repo Sydoc-Code/nexora --body "Autopilot halted on this issue. Repo left clean; any worktree preserved for inspection. See Telegram for the reason."
```
Wire → **Telegram** "notify-halt": text `⛔ loop HALTED at #{{$json.number}} — {{$json.reason || 'plan/exec verification failed'}}. Worktree (if any) left for inspection.`
Wire → **Execute Command** "release-lock-halt": `Remove-Item C:\dev\nexora\var\autopilot.lock -ErrorAction SilentlyContinue` → then a **NoOp** "STOP" (do NOT loop back — halt skips remaining issues).

- [ ] **Step 3: Loop-done branch (queue drained, no halt)**

From Loop Over Items "done" output → **Execute Command** "release-lock-done": `Remove-Item C:\dev\nexora\var\autopilot.lock -ErrorAction SilentlyContinue`
Wire → **Telegram** "notify-summary": text `🏁 autopilot run complete — queue drained.`

- [ ] **Step 4: Error workflow (crash-proof lock release)**

In n8n Settings → this workflow → **Error Workflow**: create a tiny workflow with an **Error Trigger** → **Execute Command** `Remove-Item C:\dev\nexora\var\autopilot.lock -ErrorAction SilentlyContinue` → **Telegram** `⛔ autopilot crashed — lock released, check n8n executions.` This guarantees a mid-run crash never wedges the lock.

- [ ] **Step 5: Raise the execution timeout**

n8n Settings → Workflow settings → set "Timeout" high (e.g. 7200s) — a single `/execute-plan` can run 20–40 min and must not be killed mid-flight. Save.

---

## Task 6: End-to-end live verification (the real tests)

**Files:** none (operational verification)

- [ ] **Step 1: Happy-path — one real small issue**

Create a GitHub issue with a small, real ask (title = the feature, body = one paragraph of detail). Label it `autopilot`. Within ~2 min the scheduled poll fires (or click Execute Workflow).
Expected, unattended: a `plan:` commit + feature commit land on `feature/2.5.63`; the `plan-*` worktree is created then merged away; the issue gets a comment with the short sha + the `autopilot-built` label and stays **open**; Telegram shows ✅ then 🏁. Confirm:
```powershell
git -C C:\dev\nexora log --oneline -5
git -C C:\dev\nexora worktree list          # no leftover plan-* worktree
git -C C:\dev\nexora status --porcelain     # clean
Test-Path C:\dev\nexora\var\autopilot.lock  # False (released)
```

- [ ] **Step 2: Halt-path — a deliberately impossible issue**

Create an issue whose ask cannot succeed (e.g. "integrate the nonexistent FooBar SDK that does not exist"). Label it `autopilot`.
Expected: the loop halts on it — issue gets `autopilot-blocked` + a comment; Telegram shows ⛔ with a reason; **no later issue is attempted**; `feature/2.5.63` is clean; the lock is released. Confirm with the same commands as Step 1 plus:
```powershell
gh issue view <n> --repo Sydoc-Code/nexora --json labels --jq '.labels[].name'   # includes autopilot-blocked
```

- [ ] **Step 3: Single-run lock — overlap rejection**

While a run is in progress, manually click "Execute Workflow" again. Expected: the second execution hits `got-lock?` false and stops quietly — no second Claude process, no double-build.

- [ ] **Step 4: Record results**

Note pass/fail for Steps 1–3 in `tools/autopilot/README.md` under a "Verified" section. If any fail, debug with superpowers:systematic-debugging before moving on.

---

## Task 7: Export workflow, document, deploy-exclude, final commit

**Files:**
- Create: `tools/autopilot/n8n-autopilot.workflow.json`
- Modify: `tools/autopilot/README.md`
- Modify: `.github/workflows/deploy.yml` (add `tools` to excludes)
- Modify: `var/nexora-claude-workflow.md` (reference autopilot)

- [ ] **Step 1: Export the n8n workflow to the repo**

In the n8n editor: workflow menu → Download. Save the JSON as `C:\dev\nexora\tools\autopilot\n8n-autopilot.workflow.json`. (This is the version-controlled source of truth; re-import to rebuild.)

- [ ] **Step 2: Finish the README**

`tools/autopilot/README.md` — cover: what it does, prerequisites (n8n, gh auth, Telegram cred, labels), how to import the workflow JSON, how to start/stop, the `SQL_SYNC_SKIP` + no-push policy, the halt-recovery procedure (inspect preserved worktree, fix, remove `autopilot-blocked`), and a pointer to `SIGNALS.md` + the spec.

- [ ] **Step 3: Deploy-exclude the dev-only tools dir**

In `.github/workflows/deploy.yml`, add `tools` to the robocopy `/XD` exclude list (dev-only, never shipped to PROD). Confirm the line:
```powershell
Select-String -Path C:\dev\nexora\.github\workflows\deploy.yml -Pattern "/XD"
```

- [ ] **Step 4: Cross-link the workflow doc**

Append a short "Autopilot (n8n)" section to `var/nexora-claude-workflow.md` linking the spec, the plan, and `tools/autopilot/README.md`, noting that labelling a GitHub issue `autopilot` now triggers the unattended loop.

- [ ] **Step 5: Final commit**

```powershell
git -C C:\dev\nexora add tools/autopilot/ .github/workflows/deploy.yml var/nexora-claude-workflow.md
$env:SQL_SYNC_SKIP='1'; git -C C:\dev\nexora commit -F <message file>
```
Message:
```
feat(autopilot): n8n workflow + docs for unattended Claude Code loop

Exports the n8n autopilot workflow JSON, documents setup/recovery in
the README, excludes tools/ from deploy, and cross-links the workflow
doc. Labelling a GitHub issue autopilot now drives plan+execute
unattended, stopping at commit per policy.
```

- [ ] **Step 6: Stop — do not push**

Per policy: leave all commits local on `feature/2.5.63`. Report the commit shas; the owner reviews and pushes.

---

## Self-review notes

- **Spec coverage:** trigger/polling (T4.1–4.3), lock (T4.3, T5.2–5.4, T6.3), queue-via-gh (T4.1), plan+execute headless (T4.6–4.7), BLOCKED-by-inspection (T3, T4.6–4.7), halt+notify (T5.2), Telegram (T2.5, T5), commit-not-push/label-not-close (T5.1, T7.6), SQL_SYNC_SKIP (every claude step), risks #1–#5 (T1 gate, T3, --effort high throughout, T5.5 timeout, T5.4 error workflow). All covered.
- **TDD adaptation:** this is infra/config, not Python — "tests" are dry-runs and probe-verification commands with expected output (T3.2–3.3, T4.2, T6). probe-state.ps1 is the one extracted unit and is verified against known states. No Pester harness (nexora has none; disproportionate for a dev-only probe).
- **No app-feature constellation:** no routes/permissions/SQL/i18n — intentionally out of scope (dev tooling only).
