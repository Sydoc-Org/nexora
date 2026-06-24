# Autopilot Concurrent Issues (parallel lanes) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the autopilot build up to **3 issues at once** instead of one. Replace the global single-run lock with a **3-slot semaphore**; give each in-flight issue its **own git worktree** on a fresh `auto/issue-NN` branch off `feature/2.5.63`; run plan+execute **in that worktree on that branch** (never letting `/write-plan` spawn a nested `plan/<slug>` worktree, see Context); then **serialize the merge-back** onto `feature/2.5.63` in **completion order** (one lane writes the shared branch at a time). On a git conflict a **separate merge-resolver agent** (`claude -p`) resolves it; on a per-issue **build failure** that issue's run **pauses** while the other lanes keep going; the **DB-touching build/test step is serialized** across lanes behind a shared DB lock. Excess issues beyond 3 just **queue**.

**Architecture:** PowerShell scripts orchestrated by an n8n canvas (the live "orchestrate in PowerShell, route on the canvas" pattern). Extract lane provisioning + the semaphore + the serialized merge-back into clean single-responsibility scripts so each is independently testable on a throwaway git repo: `semaphore.ps1` (N-slot lock with an **atomic** slot-file claim, mirrors `lock.ps1`'s `-Action` + JSON shape), `lane-paths.ps1` (dot-sourced path module — the single source of truth for per-lane log/run-state/baseline paths), `lane.ps1` (worktree acquire/release on `auto/issue-NN`), `merge-back.ps1` (serialized `--no-ff` merge under a dedicated **blocking** merge-lock, never-main guard like `push-branch.ps1`), `merge-resolve.ps1` (the separate conflict claude-p agent), and `db-lock.ps1` (the build/test DB lock). The existing build entry (`run-phase.ps1`) already has `-RepoPath`; it gains explicit per-lane path params and sets `AUTOPILOT_LANE=1` so `/write-plan` builds in place on `auto/issue-NN` instead of spawning a nested worktree. `recover.ps1`, `diagnose-halt.ps1`, `start-n8n.ps1`, `bin/nx.ps1`, and `watchdog.ps1` are made lane-aware. The canvas keeps one workflow and replaces the single `acquire-lock` with a **per-issue lane acquire** + adds a serialized **merge-back** node after `exec-ok?`. `handoff-session-state --merge-worktree` is **never triggered** in the autopilot lane path — merge-back is owned solely by `merge-back.ps1`.

**Tech Stack:** PowerShell 7 (`pwsh`) + n8n workflow JSON + Markdown docs. NO Python/Flask, NO SQL migration, NO i18n/pybabel, NO permission codes, NO Jinja templates, NO routes. Verification is standalone pwsh `*.assert.ps1` scripts (no Pester) + `[System.Management.Automation.Language.Parser]::ParseFile` parse-checks.

**Spec (source of truth):** `C:\dev\nexora\docs\superpowers\specs\2026-06-14-autopilot-clarify-and-parallel-design.md`, **Section 2 "Parallel execution on separate CLONES."** The spec originally chose *clones*; this plan honors the **owner override to worktrees** and documents below the corrected reason it is safe.

---

## Context an engineer needs (read first)

- **Branch:** work directly on `feature/2.5.63` (confirmed current branch — where the live autopilot tree lives). **Remote-session policy: stop at `git commit`. Do NOT push, do NOT open a PR.** The owner pushes after review.
- **Sequencing vs in-flight plans:** the **recovery layer** (`recover.ps1`, `diagnose-halt.ps1`, `fix-attempt.ps1`, `probe-infra.ps1`, `probe-state.ps1`, `baseline.ps1`, the `route-recovery` Switch with outputs `comment-built-recovered` / `mark-blocked` / `notify-pause` / `notify-pause`-fallback) and the **clarify loop** + **triage** are very recently shipped and committed on `feature/2.5.63`. This feature builds **on top** of the live single-run pipeline and MUST NOT break the `route-recovery` Switch outputs or the lock contract that `nx status`, `watchdog.ps1`, `start-n8n.ps1`, and `recover.ps1`'s `Test-Poison` all read.

- **Why worktrees are safe here — the load-bearing reconciliation (document this verbatim in README + the spec note; it is NOT what either draft originally said):**
  The spec chose clones because `handoff-session-state --merge-worktree` merges a finished worktree's branch into the **base repo's current branch** with no cross-process lock. **Verified live, the hazard is real, not a no-op:**
  1. A lane worktree IS a *linked* worktree, so `/write-plan` step 1.6 Condition B (`$gitDir -ne $gitCommon`, `.claude/commands/write-plan.md` lines 44-47) is TRUE → `/write-plan` would create a **nested** `plan/<slug>` worktree (`git worktree add .claude/worktrees/plan-$slug -b plan/$slug`).
  2. `/execute-plan` step 5 (`.claude/commands/execute-plan.md` line 91) then **unconditionally** calls `handoff-session-state --merge-worktree <slug>`.
  3. `handoff-session-state` step 5 (`.claude/commands/handoff-session-state.md` lines 82-100) merges `$worktreeBranch` from `$baseRoot = git rev-parse --git-common-dir` into `git -C $baseRoot branch --show-current`. For a lane worktree, `--git-common-dir` resolves to the **base repo's** `.git`, whose checked-out branch is `feature/2.5.63`. So the nested `plan/<slug>` would be merged **straight into `feature/2.5.63`, completely unserialized** — exactly the corruption the spec feared.
  **The fix this plan adopts:** in lane mode, `/write-plan` must NOT create a nested worktree, so plan+execute run in place on `auto/issue-NN` and no `--merge-worktree` is ever triggered. `run-phase.ps1` sets `AUTOPILOT_LANE=1` (Task 7) and `write-plan.md` step 1.6 is taught one guard (Task 8): when `AUTOPILOT_LANE` is set, skip the busy-branch worktree creation (build in the current directory, i.e. the lane worktree on `auto/issue-NN`). Merge-back to `feature/2.5.63` is then owned **solely** by `merge-back.ps1` under a serialized `merge.lock`, in completion order. With the nested worktree suppressed, `--merge-worktree` never fires in the autopilot path and separate lane worktrees off the same base are safe.

- **Anchor on snippets, NEVER line numbers.** Every Edit below quotes verbatim text from the live files; line numbers shift with every edit. Match the quoted `old_string` exactly (strip the Read line-number prefix).
- **Template cache:** N/A — no Jinja/Flask changes.
- **Commit escape hatch:** the `sql-migrate-int` + `sql-sync-check` pre-commit hooks fire on **every** commit (including a pure `tools/autopilot` commit) and fail on Windows from INT `SchemaMigrations` CRLF checksum drift. Set `$env:SQL_SYNC_SKIP = '1'` for the commit, then clear it. **NEVER use `--no-verify`.**
- **Paste-ready commit form — repeated `-m` flags, NOT here-strings.** A here-string whose closing `'@` is indented is a hard PowerShell ParserError. Use `git commit -m "subject" -m "body" -m "body"`. Subject <=72 chars, imperative, no trailing period; each body `-m` line <=100 chars (gitlint); conventional-commits types `feat,fix,chore,refactor,docs,test`; end the last `-m` with the Co-Authored-By trailer.
- **Per-script crash-proof OUTPUT CONTRACT (non-negotiable; re-applied at EVERY new script's entry — the canvas runs each as a separate `pwsh` process, hygiene is NOT inherited):**
  1. Emit **exactly one** compact JSON line on stdout and **exit 0**; **never throw.** A single top-level `try { … } catch { emit a known-good default verdict; exit 0 }` wraps the whole body.
  2. Confine any `claude` stream to a per-lane log via `Tee-Object`; capture only the single `"type":"result"` envelope; never let it reach stdout.
  3. `Remove-Item Env:GH_TOKEN, Env:GITHUB_TOKEN -ErrorAction SilentlyContinue` + `$env:SQL_SYNC_SKIP = '1'` at the script's own entry.
- **Migrations needed:** no.
- **Shared-state blast radius this plan resolves** (all currently SINGLE paths keyed off the base RepoPath):
  1. `var/autopilot.lock` (single global lock) → **3-slot semaphore** (`semaphore.ps1`, slot files under `var/autopilot/slots/`).
  2. `var/autopilot/run-state.json` (single) → **per-lane** `var/autopilot/lanes/lane-K/run-state.json`.
  3. `var/autopilot/logs/run.log` (single, sliced by `=== <phase> #<n> ===`) → **per-lane** `var/autopilot/lanes/lane-K/run.log`.
  4. `var/autopilot/run-baseline.json` (single) → **per-lane** baseline; `attempts.json` stays a **per-issue-keyed shared** file; `cost-ledger.json` stays a **shared** global daily cap.
  - `var/autopilot/` is gitignored, so all of the above never dirty the tree. The **worktree directories live OUTSIDE the repo** at `<RepoParent>\nexora-lanes\lane-K` (derived from `$RepoPath`, NOT hardcoded), so they are never tracked nor robocopied.
- **`run-phase.ps1` already has `-RepoPath`** (it `Set-Location`s there). Pointing it at a lane worktree is near-zero for the build; the only fix is its `$logDir`/`$statePath` must come from explicit per-lane params, not `Join-Path $RepoPath`.
- **Test mechanism (chosen):** standalone pwsh `*.assert.ps1` under `tools/autopilot/tests/` + `Parser::ParseFile`. Git-exercising tests build an **isolated throwaway repo** (`git init -b feature/2.5.63`), seed sibling scripts, and drive real `git worktree add`/`merge`. **Gotchas (from `recover.assert.ps1`):** splat with a **HASHTABLE** (`@common`), never an array (array splatting binds positionally); a child script that `Set-Location`s changes the harness CWD for the next case, so pass absolute `-RepoPath` every case; when invoking a child that may emit warnings, pipe through `Select-Object -Last 1` before `ConvertFrom-Json`.
- **Chores:** i18n none, permissions none. `deploy.yml` already `/XD`-excludes `tools`, `docs`, `var` — **no deploy change** (the `nexora-lanes` worktree root is outside the repo anyway). `.gitignore` already ignores `var/autopilot/` — **no gitignore change**. CHANGELOG already carries an autopilot `[Unreleased] > Added` entry today, so a one-line lanes entry is precedented (Task 14).

---

## Decisions locked in

| Decision | Choice |
|---|---|
| Isolation unit | **Separate git WORKTREES** (one per issue) at `<RepoParent>\nexora-lanes\lane-K`, NOT clones, and the lane path NEVER triggers `--merge-worktree` |
| Per-issue branch | **`auto/issue-NN`** off `feature/2.5.63`, created in the lane worktree; plan+execute run in place on it (`AUTOPILOT_LANE=1` suppresses the nested `plan/<slug>` worktree) |
| Concurrency cap | **3** (hard cap) via a **3-slot semaphore** replacing the single global lock |
| Excess beyond 3 | **Queue** (no extra lanes); a 4th acquire returns FULL |
| Merge destination | **`feature/2.5.63`** always; **never** main, **never** a PR |
| Merge ordering | **Order of COMPLETION**, **serialized** — one lane writes the shared branch at a time under a dedicated `merge.lock` |
| Merge conflict | **Separate merge-resolver agent** (`merge-resolve.ps1` → `claude -p`); `merge-back.ps1` never resolves inline (aborts clean, returns CONFLICT) |
| Per-issue build FAILURE | **PAUSE that issue's run only** — release just that lane's slot, leave its branch/worktree for inspection; other lanes continue |
| DB interference | **Serial DB rule (v1):** the DB-touching build/test step (`run-exec` = `/execute-plan`, which runs the suite) takes a shared **blocking** `db.lock`; plan + non-DB steps stay parallel |
| Double-pickup prevention | **Atomic slot-file claim** (CreateNew, no TOCTOU) recording the issue number; the queue also excludes an `autopilot-building` label as a visible second line |
| Per-lane state | Per-lane `run.log`/`run-state.json`/`run-baseline.json` under `var/autopilot/lanes/lane-K/`; per-issue-keyed `attempts.json`; shared `cost-ledger.json` |
| n8n shape | **Single workflow**; per-issue lane acquire replaces the global lock; a serialized `merge-back` → (CONFLICT) `merge-resolve` node after `exec-ok?`; the loop-DONE `push-branch` stays the single end-of-run push |
| Other workflows | `clarify-reply` + `watchdog` run **independently**; the watchdog liveness probe is taught the semaphore |
| Test mechanism | Standalone pwsh `*.assert.ps1` + `Parser::ParseFile` (no Pester); git-exercising tests use an isolated throwaway repo |

---

## Owner actions (cannot run unattended — live n8n UI / Telegram creds / INT / SYAPP01)

1. **Run `setup-labels.ps1` once** so the new `autopilot-building` claim label exists before first run: `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\setup-labels.ps1`.
2. **Re-import the rewired `n8n-autopilot.workflow.json`** into live workflow `PzQXpt99pIIV7fJv` **via `start-n8n.ps1`** (it sets `NODES_EXCLUDE` so `executeCommand` stays enabled). Then export/verify the new `dispatch-acquire`, `got-slot?`, `db-acquire`/`db-release`, `merge-back`, `merge-route`, `merge-resolve`, and rewired `pause-lane` nodes + their edges survived (n8n silently drops edges to unresolved node types) and all four `route-recovery` routes are intact.
3. **Provision the lane worktree root.** Pre-create `<RepoParent>\nexora-lanes\` (the dir only — `lane.ps1` creates each `lane-K` worktree on demand). Confirm `git worktree list` is clean before first run.
4. **Telegram:** confirm per-lane notifications still name issue **title + number** (the per-lane `run-state.json` carries the title).
5. **Defender (only on SYAPP01 / prod-adjacent, where the repo is `D:\sydoc\nexora`):** the worktree root `D:\sydoc\nexora-lanes` is a NEW heavy-IO path outside `D:\sydoc\nexora\var`. Run `Add-MpPreference -ExclusionPath 'D:\sydoc\nexora-lanes'` (compute the path as `<repo-parent>\nexora-lanes` for the actual box). On the dev box (`C:\dev\nexora`) this is a no-op caveat.
6. **Run the interactive SMOKE GATE (PHASE 6 / Task 15)** against live n8n + INT, then **Activate.** This validation must NOT run unattended (spec line 9). During the gate, confirm `/execute-plan` did NOT create a nested `plan/<slug>` worktree (the `AUTOPILOT_LANE` guard held) and that `feature/2.5.63` was written only by `merge-back.ps1`.

---

# PHASE 1 — Foundation: atomic semaphore + per-lane path module

*No canvas changes. Build these first — every later script consumes them.*

### Task 1: Add `semaphore.ps1` (3-slot lock, atomic claim, per-slot staleness)

**Files:** `C:\dev\nexora\tools\autopilot\semaphore.ps1` (new), `C:\dev\nexora\tools\autopilot\tests\semaphore.assert.ps1` (new)

**Design:** Mirror `lock.ps1`'s `-Action` switch and JSON shape, backed by N slot files `var/autopilot/slots/lane-K.lock` holding `{ts, procId, issue}`. `acquire -IssueNumber NN` claims the lowest free slot with an **atomic** `[System.IO.File]::Open(path, CreateNew)` (no Test-Path/Set-Content TOCTOU, so two near-simultaneous acquires cannot both win slot K), returns `{status:'ACQUIRED', slot:K}`; if all N held & fresh, `{status:'FULL'}`. A slot is **stale** (reclaimable) past `-MaxAgeHours` OR (age >= 3 min AND no live process with the stored `procId`). Staleness keys on the **stored procId**, NOT the host-wide claude probe (3 concurrent claudes make the aggregate probe useless). `release -Slot K` removes the file. `check` returns `{slots:[{slot,issue,heldForMin}], free:M}`.

- [ ] **Write the failing assertion first.** Create `C:\dev\nexora\tools\autopilot\tests\semaphore.assert.ps1`:

```powershell
#requires -Version 7
# Standalone assertion (no Pester). Exit 1 on any failure.
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\semaphore.ps1'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'semaphore.ps1 parses'

$tmp = New-Item -ItemType Directory -Path (Join-Path ([IO.Path]::GetTempPath()) ("sem-" + [guid]::NewGuid().ToString('N')))
try {
  $slots = Join-Path $tmp 'slots'
  $common = @{ SlotsDir = $slots; MaxSlots = 3 }

  $a = & $script -Action acquire -IssueNumber 11 @common | ConvertFrom-Json
  $b = & $script -Action acquire -IssueNumber 12 @common | ConvertFrom-Json
  $c = & $script -Action acquire -IssueNumber 13 @common | ConvertFrom-Json
  Assert ($a.status -eq 'ACQUIRED' -and $b.status -eq 'ACQUIRED' -and $c.status -eq 'ACQUIRED') '3 acquires succeed'
  $distinct = @($a.slot, $b.slot, $c.slot | Sort-Object -Unique)
  Assert ($distinct.Count -eq 3) "3 acquires get distinct slots (got $($distinct -join ','))"

  $d = & $script -Action acquire -IssueNumber 14 @common | ConvertFrom-Json
  Assert ($d.status -eq 'FULL') "4th acquire => FULL (got $($d.status))"

  $r = & $script -Action release -Slot $a.slot @common | ConvertFrom-Json
  Assert ($r.status -eq 'RELEASED') 'release => RELEASED'
  $e = & $script -Action acquire -IssueNumber 15 @common | ConvertFrom-Json
  Assert ($e.status -eq 'ACQUIRED' -and $e.slot -eq $a.slot) 'released slot is reusable'

  $chk = & $script -Action check @common | ConvertFrom-Json
  $issues = @($chk.slots | ForEach-Object { $_.issue } | Sort-Object)
  Assert ($issues -contains 15 -and $issues -contains 12 -and $issues -contains 13) 'check reports claimed issues per slot'

  # Stale reclaim: a slot file with a dead procId and old timestamp is reclaimable.
  $stale = Join-Path $slots 'lane-0.lock'
  @{ ts = (Get-Date).AddHours(-5).ToString('o'); procId = 999999; issue = 99 } | ConvertTo-Json | Set-Content -Encoding utf8 $stale
  (Get-Item $stale).LastWriteTime = (Get-Date).AddHours(-5)
  $f2 = & $script -Action acquire -IssueNumber 20 @common | ConvertFrom-Json
  Assert ($f2.status -eq 'ACQUIRED') 'stale slot (dead proc + old) is reclaimed on acquire'
} finally { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue }

if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
```

- [ ] **Run it red:** `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\semaphore.assert.ps1`.

- [ ] **Implement `C:\dev\nexora\tools\autopilot\semaphore.ps1`:**

```powershell
#requires -Version 7
<#
.SYNOPSIS
  N-slot semaphore for concurrent autopilot lanes. Replaces lock.ps1's global single-run lock.
  Emits ONE compact JSON line; exit 0; never throws.
.DESCRIPTION
  acquire -IssueNumber NN -> {status:ACQUIRED, slot:K} (lowest free slot, claimed ATOMICALLY for NN)
                             or {status:FULL} when all MaxSlots are held & fresh (excess queues).
  release -Slot K          -> {status:RELEASED} (no-op if absent).
  check                    -> {slots:[{slot,issue,heldForMin}], free:M}.
  Each slot is a file var/autopilot/slots/lane-K.lock holding {ts, procId, issue}. The claim uses
  [IO.File]::Open(path, CreateNew) so two processes cannot both win slot K (no Test-Path TOCTOU).
  A slot is stale (reclaimable) past -MaxAgeHours, or after a 3-min grace if NO live process carries
  its procId. Staleness keys on the STORED procId, not a host-wide claude probe (3 concurrent claudes
  make the aggregate probe useless).
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][ValidateSet('acquire','release','check')] [string]$Action,
  [int]$IssueNumber = 0,
  [int]$Slot = -1,
  [string]$SlotsDir = 'C:\dev\nexora\var\autopilot\slots',
  [int]$MaxSlots = 3,
  [double]$MaxAgeHours = 3.0
)
$ErrorActionPreference = 'Stop'
try {
  New-Item -ItemType Directory -Force $SlotsDir | Out-Null
  function Slot-Path([int]$k) { Join-Path $SlotsDir ("lane-$k.lock") }
  function Read-Slot([int]$k) {
    $p = Slot-Path $k
    if (-not (Test-Path $p)) { return $null }
    try {
      $o = Get-Content $p -Raw | ConvertFrom-Json
      $o | Add-Member -NotePropertyName _age -NotePropertyValue ((Get-Date) - (Get-Item $p).LastWriteTime) -Force
      return $o
    } catch { return $null }
  }
  function Is-Stale($s) {
    if ($null -eq $s) { return $true }
    if ($s._age.TotalHours -ge $MaxAgeHours) { return $true }
    $alive = [bool](Get-Process -Id ([int]$s.procId) -ErrorAction SilentlyContinue)
    return ($s._age.TotalMinutes -ge 3 -and -not $alive)
  }
  function Try-Claim([int]$k) {
    # Atomic create-new; returns $true only if THIS process created the file.
    $p = Slot-Path $k
    try {
      $fs = [System.IO.File]::Open($p, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
      try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes((@{ ts = (Get-Date -Format o); procId = $PID; issue = $IssueNumber } | ConvertTo-Json -Compress))
        $fs.Write($bytes, 0, $bytes.Length)
      } finally { $fs.Dispose() }
      return $true
    } catch { return $false }
  }
  switch ($Action) {
    'acquire' {
      for ($k = 0; $k -lt $MaxSlots; $k++) {
        $s = Read-Slot $k
        if ($null -eq $s) {
          if (Try-Claim $k) { @{ status = 'ACQUIRED'; slot = $k } | ConvertTo-Json -Compress; exit 0 }
        } elseif (Is-Stale $s) {
          Remove-Item (Slot-Path $k) -ErrorAction SilentlyContinue
          if (Try-Claim $k) { @{ status = 'ACQUIRED'; slot = $k } | ConvertTo-Json -Compress; exit 0 }
        }
      }
      @{ status = 'FULL' } | ConvertTo-Json -Compress
    }
    'release' {
      if ($Slot -ge 0) { Remove-Item (Slot-Path $Slot) -ErrorAction SilentlyContinue }
      @{ status = 'RELEASED'; slot = $Slot } | ConvertTo-Json -Compress
    }
    'check' {
      $out = @(); $free = 0
      for ($k = 0; $k -lt $MaxSlots; $k++) {
        $s = Read-Slot $k
        if ($null -eq $s -or (Is-Stale $s)) { $free++ }
        else { $out += [ordered]@{ slot = $k; issue = [int]$s.issue; heldForMin = [math]::Round($s._age.TotalMinutes, 1) } }
      }
      @{ slots = $out; free = $free } | ConvertTo-Json -Compress -Depth 5
    }
  }
} catch {
  @{ status = 'ERROR'; reason = $_.Exception.Message } | ConvertTo-Json -Compress
  exit 0
}
```

- [ ] **Run it green:** `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\semaphore.assert.ps1` — expect `ALL PASS`.

- [ ] **Commit:**
```powershell
$env:SQL_SYNC_SKIP = '1'
git add tools/autopilot/semaphore.ps1 tools/autopilot/tests/semaphore.assert.ps1
git commit -m "feat(autopilot): add atomic 3-slot semaphore for concurrent lanes" -m "Replaces the global single-run lock with an N-slot semaphore (default 3). Slots are claimed via [IO.File]::Open CreateNew so two near-simultaneous acquires cannot both win slot K. Each slot file records procId + claimed issue; staleness is scoped per-slot via the stored procId, not the host-wide claude probe. acquire returns the slot index, the (N+1)th returns FULL so excess issues queue." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
Remove-Item Env:SQL_SYNC_SKIP
```

### Task 2: Add `lane-paths.ps1` (per-lane path module) + its assert

**Files:** `C:\dev\nexora\tools\autopilot\lane-paths.ps1` (new — dot-sourced helper, no `-Action`, emits no JSON), `C:\dev\nexora\tools\autopilot\tests\lane-paths.assert.ps1` (new)

**Design:** Single source of truth for the per-lane layout so `run-phase.ps1`, `recover.ps1`, `diagnose-halt.ps1`, `start-n8n.ps1`, `bin/nx.ps1` all derive IDENTICAL paths. `Get-LanePaths -Lane K -BaseRepo C:\dev\nexora -IssueNumber NN` returns `lane, root, worktree, branch, log, runState, baseline, attempts`. STATE lives under the **base** repo (`var/autopilot/lanes/lane-K/`); the **worktree** lives OUTSIDE the repo at `<BaseRepo>-lanes\lane-K` (derived, never hardcoded). Also `Get-AllLaneRoots -BaseRepo ... -MaxSlots 3`.

- [ ] **Write the failing assertion first.** Create `C:\dev\nexora\tools\autopilot\tests\lane-paths.assert.ps1`:

```powershell
#requires -Version 7
$ErrorActionPreference = 'Stop'
$mod = Join-Path $PSScriptRoot '..\lane-paths.ps1'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $mod), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'lane-paths.ps1 parses'

. $mod
$p = Get-LanePaths -Lane 1 -BaseRepo 'C:\dev\nexora' -IssueNumber 42
Assert ($p.branch -eq 'auto/issue-42') "branch is auto/issue-NN (got $($p.branch))"
Assert ($p.worktree -eq 'C:\dev\nexora-lanes\lane-1') "worktree is OUTSIDE the repo (got $($p.worktree))"
Assert ($p.log -like '*\var\autopilot\lanes\lane-1\run.log') "per-lane log under base var (got $($p.log))"
Assert ($p.runState -like '*\var\autopilot\lanes\lane-1\run-state.json') 'per-lane run-state under base var'
Assert ($p.baseline -like '*\var\autopilot\lanes\lane-1\run-baseline.json') 'per-lane baseline under base var'
$p0 = Get-LanePaths -Lane 0 -BaseRepo 'C:\dev\nexora' -IssueNumber 7
Assert ($p0.log -ne $p.log -and $p0.worktree -ne $p.worktree) 'distinct lanes have distinct log + worktree'
# Worktree root is DERIVED from BaseRepo, not a hardcoded C:\ literal.
$pd = Get-LanePaths -Lane 0 -BaseRepo 'D:\sydoc\nexora' -IssueNumber 7
Assert ($pd.worktree -eq 'D:\sydoc\nexora-lanes\lane-0') "worktree root derives from BaseRepo (got $($pd.worktree))"
$roots = Get-AllLaneRoots -BaseRepo 'C:\dev\nexora' -MaxSlots 3
Assert ($roots.Count -eq 3) 'Get-AllLaneRoots returns one root per slot'

if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
```

- [ ] **Run it red:** `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\lane-paths.assert.ps1`.

- [ ] **Implement `C:\dev\nexora\tools\autopilot\lane-paths.ps1`:**

```powershell
#requires -Version 7
<#
.SYNOPSIS
  Per-lane path layout for concurrent autopilot lanes. Dot-source this; it defines functions only and
  emits nothing. Single source of truth so every lane-aware script derives identical paths.
.DESCRIPTION
  STATE (log/run-state/baseline) lives under the BASE repo var/autopilot/lanes/lane-K/ (gitignored,
  exists on the base, survives across phases). The WORKTREE lives OUTSIDE the repo at
  <BaseRepo>-lanes\lane-K (derived from BaseRepo, never hardcoded) so it is never robocopied/tracked.
#>
function Get-LanePaths {
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)][int]$Lane,
    [string]$BaseRepo = 'C:\dev\nexora',
    [int]$IssueNumber = 0
  )
  $lanesState = Join-Path $BaseRepo ("var\autopilot\lanes\lane-$Lane")
  $worktree   = "$BaseRepo-lanes\lane-$Lane"
  [pscustomobject]@{
    lane     = $Lane
    root     = $lanesState
    worktree = $worktree
    branch   = "auto/issue-$IssueNumber"
    log      = (Join-Path $lanesState 'run.log')
    runState = (Join-Path $lanesState 'run-state.json')
    baseline = (Join-Path $lanesState 'run-baseline.json')
    attempts = (Join-Path $BaseRepo 'var\autopilot\attempts.json')   # per-issue-keyed, shared file
  }
}
function Get-AllLaneRoots {
  [CmdletBinding()]
  param([string]$BaseRepo = 'C:\dev\nexora', [int]$MaxSlots = 3)
  0..($MaxSlots - 1) | ForEach-Object { Get-LanePaths -Lane $_ -BaseRepo $BaseRepo }
}
```

- [ ] **Run it green:** `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\lane-paths.assert.ps1` — expect `ALL PASS`.

- [ ] **Commit:**
```powershell
$env:SQL_SYNC_SKIP = '1'
git add tools/autopilot/lane-paths.ps1 tools/autopilot/tests/lane-paths.assert.ps1
git commit -m "feat(autopilot): add lane-paths module for per-lane state isolation" -m "Single source of truth for the per-lane layout. Per-lane log/run-state/baseline live under the BASE repo var/autopilot/lanes/lane-K/ (gitignored); the worktree lives OUTSIDE the repo at <base>-lanes/lane-K, derived from BaseRepo (not a hardcoded C: literal) so prod (D:/sydoc/nexora) resolves correctly. Every later lane-aware script derives identical paths from this module." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
Remove-Item Env:SQL_SYNC_SKIP
```

---

# PHASE 2 — Lane provisioning + serialized merge-back + conflict resolver

*The worktree model's heart. Each script is tested against an isolated throwaway repo (the `recover.assert.ps1` pattern); no live checkout is touched.*

### Task 3: Add `lane.ps1` (worktree acquire / release on `auto/issue-NN`)

**Files:** `C:\dev\nexora\tools\autopilot\lane.ps1` (new), `C:\dev\nexora\tools\autopilot\tests\lane.assert.ps1` (new)

**Design:** `acquire -IssueNumber NN` calls `semaphore.ps1` to claim a slot, then `git -C <base> worktree add <worktree> -b auto/issue-NN feature/2.5.63`. A leftover worktree/branch from a crashed run is cleaned (worktree remove + prune + branch -D) and recreated. Emits `{status:'ACQUIRED', slot, worktree, branch, issue}` or `{status:'FULL'}`. `release -Slot K -IssueNumber NN` is **ancestor-checked**: if the lane HEAD did NOT land on `feature/2.5.63` it refuses (`{status:'UNMERGED'}`, worktree kept for inspection, slot STILL freed so other work flows); else worktree remove + branch -D + slot release (`{status:'RELEASED'}`). Output contract applies.

- [ ] **Write the failing assertion first.** Create `C:\dev\nexora\tools\autopilot\tests\lane.assert.ps1`:

```powershell
#requires -Version 7
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\lane.ps1'
$tools  = Split-Path $script
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'lane.ps1 parses'

$tmp = New-Item -ItemType Directory -Path (Join-Path ([IO.Path]::GetTempPath()) ("lane-" + [guid]::NewGuid().ToString('N')))
try {
  $repo = Join-Path $tmp 'repo'
  New-Item -ItemType Directory -Path (Join-Path $repo 'tools\autopilot') | Out-Null
  foreach ($s in 'semaphore.ps1','lane-paths.ps1') { Copy-Item (Join-Path $tools $s) (Join-Path $repo 'tools\autopilot') }
  git -C $repo init -q -b 'feature/2.5.63' *> $null
  git -C $repo config user.email 't@t'; git -C $repo config user.name 't'
  Set-Content (Join-Path $repo 'seed.txt') 'x'; git -C $repo add -A *> $null; git -C $repo commit -q -m 'init' *> $null

  $slots = Join-Path $tmp 'slots'
  $common = @{ BaseRepo = $repo; SlotsDir = $slots; MaxSlots = 2 }

  $a = & $script -Action acquire -IssueNumber 11 @common | Select-Object -Last 1 | ConvertFrom-Json
  $b = & $script -Action acquire -IssueNumber 12 @common | Select-Object -Last 1 | ConvertFrom-Json
  Assert ($a.status -eq 'ACQUIRED' -and $b.status -eq 'ACQUIRED') 'two lane acquires succeed'
  Assert ($a.slot -ne $b.slot) 'lanes get distinct slots'
  Assert ($a.branch -eq 'auto/issue-11' -and $b.branch -eq 'auto/issue-12') 'each lane on auto/issue-NN'
  Assert (Test-Path (Join-Path $a.worktree '.git')) 'lane worktree created on disk'
  Assert ((@(git -C $repo worktree list) -join "`n") -match 'auto/issue-11') 'auto/issue-11 worktree registered'

  $c = & $script -Action acquire -IssueNumber 13 @common | Select-Object -Last 1 | ConvertFrom-Json
  Assert ($c.status -eq 'FULL') "over-cap acquire => FULL (got $($c.status))"

  # Release an UNMERGED lane (commit never landed on feature) -> UNMERGED, worktree kept, slot freed.
  Set-Content (Join-Path $a.worktree 'feat.txt') 'work'
  git -C $a.worktree add -A *> $null; git -C $a.worktree commit -q -m 'feat work' *> $null
  $rel = & $script -Action release -Slot $a.slot -IssueNumber 11 @common | Select-Object -Last 1 | ConvertFrom-Json
  Assert ($rel.status -eq 'UNMERGED') "release of unmerged lane => UNMERGED (got $($rel.status))"
  Assert (Test-Path $a.worktree) 'unmerged worktree NOT removed'
  # Slot freed despite UNMERGED -> a new acquire can take that slot.
  $reuse = & $script -Action acquire -IssueNumber 14 @common | Select-Object -Last 1 | ConvertFrom-Json
  Assert ($reuse.status -eq 'ACQUIRED') 'slot freed even on UNMERGED release'

  # A lane whose HEAD == feature HEAD (nothing to lose) releases cleanly.
  $relB = & $script -Action release -Slot $b.slot -IssueNumber 12 @common | Select-Object -Last 1 | ConvertFrom-Json
  Assert ($relB.status -eq 'RELEASED') "merged/empty lane releases (got $($relB.status))"
} finally { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue }

if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
```

- [ ] **Run it red:** `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\lane.assert.ps1`.

- [ ] **Implement `C:\dev\nexora\tools\autopilot\lane.ps1`:**

```powershell
#requires -Version 7
<#
.SYNOPSIS
  Provision/tear down a concurrent autopilot lane: a git WORKTREE on a fresh auto/issue-NN branch.
  Owner override: WORKTREES not clones. The autopilot lane path NEVER triggers handoff --merge-worktree
  (run-phase sets AUTOPILOT_LANE=1 so /write-plan builds in place); merge-back is owned by merge-back.ps1.
  Emits ONE compact JSON line; exit 0; never throws.
.DESCRIPTION
  acquire -IssueNumber NN -> claim a semaphore slot, create the lane worktree on auto/issue-NN off
                             $Branch, emit {status:ACQUIRED, slot, worktree, branch, issue} | {FULL}.
  release -Slot K -IssueNumber NN -> ancestor-checked: if the lane HEAD did NOT land on $Branch, refuse
                             (=> {UNMERGED}, worktree kept for inspection, slot STILL freed); else
                             worktree remove + branch -D + slot release => {RELEASED}.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][ValidateSet('acquire','release')] [string]$Action,
  [int]$IssueNumber = 0,
  [int]$Slot = -1,
  [string]$BaseRepo = 'C:\dev\nexora',
  [string]$Branch = 'feature/2.5.63',
  [string]$SlotsDir = 'C:\dev\nexora\var\autopilot\slots',
  [int]$MaxSlots = 3
)
$ErrorActionPreference = 'Stop'
$env:SQL_SYNC_SKIP = '1'
Remove-Item Env:GH_TOKEN, Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
$sem = Join-Path $BaseRepo 'tools\autopilot\semaphore.ps1'
. (Join-Path $BaseRepo 'tools\autopilot\lane-paths.ps1')
try {
  switch ($Action) {
    'acquire' {
      $s = (& $sem -Action acquire -IssueNumber $IssueNumber -SlotsDir $SlotsDir -MaxSlots $MaxSlots | Select-Object -Last 1 | ConvertFrom-Json)
      if ($s.status -ne 'ACQUIRED') { @{ status = 'FULL' } | ConvertTo-Json -Compress; exit 0 }
      $lp = Get-LanePaths -Lane $s.slot -BaseRepo $BaseRepo -IssueNumber $IssueNumber
      New-Item -ItemType Directory -Force $lp.root | Out-Null
      if (Test-Path $lp.worktree) { git -C $BaseRepo worktree remove --force $lp.worktree 2>$null | Out-Null }
      git -C $BaseRepo worktree prune 2>$null | Out-Null
      git -C $BaseRepo branch -D $lp.branch 2>$null | Out-Null
      git -C $BaseRepo worktree add -b $lp.branch $lp.worktree $Branch 2>$null | Out-Null
      if (-not (Test-Path (Join-Path $lp.worktree '.git'))) { throw "worktree add failed for $($lp.worktree)" }
      @{ status = 'ACQUIRED'; slot = $s.slot; worktree = $lp.worktree; branch = $lp.branch; issue = $IssueNumber } | ConvertTo-Json -Compress
    }
    'release' {
      $lp = Get-LanePaths -Lane $Slot -BaseRepo $BaseRepo -IssueNumber $IssueNumber
      $unmerged = $false
      if (Test-Path $lp.worktree) {
        $wtHead = (git -C $lp.worktree rev-parse HEAD 2>$null)
        $featHead = (git -C $BaseRepo rev-parse $Branch 2>$null)
        if ($wtHead -and $featHead) {
          git -C $BaseRepo merge-base --is-ancestor $wtHead.Trim() $featHead.Trim() 2>$null
          if ($LASTEXITCODE -ne 0) { $unmerged = $true }
        }
      }
      if ($unmerged) {
        & $sem -Action release -Slot $Slot -SlotsDir $SlotsDir -MaxSlots $MaxSlots | Out-Null
        @{ status = 'UNMERGED'; slot = $Slot; worktree = $lp.worktree; branch = $lp.branch } | ConvertTo-Json -Compress
        exit 0
      }
      if (Test-Path $lp.worktree) { git -C $BaseRepo worktree remove --force $lp.worktree 2>$null | Out-Null }
      git -C $BaseRepo worktree prune 2>$null | Out-Null
      git -C $BaseRepo branch -D $lp.branch 2>$null | Out-Null
      & $sem -Action release -Slot $Slot -SlotsDir $SlotsDir -MaxSlots $MaxSlots | Out-Null
      @{ status = 'RELEASED'; slot = $Slot } | ConvertTo-Json -Compress
    }
  }
} catch {
  @{ status = 'ERROR'; reason = $_.Exception.Message } | ConvertTo-Json -Compress
  exit 0
}
```

- [ ] **Run it green:** `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\lane.assert.ps1` — expect `ALL PASS`.

- [ ] **Commit:**
```powershell
$env:SQL_SYNC_SKIP = '1'
git add tools/autopilot/lane.ps1 tools/autopilot/tests/lane.assert.ps1
git commit -m "feat(autopilot): add lane provisioner (worktree per issue)" -m "lane.ps1 acquire claims a semaphore slot and creates a git worktree on a fresh auto/issue-NN branch off feature/2.5.63 (owner override: worktrees not clones). release is ancestor-checked: an unmerged lane is kept for inspection (per-issue pause) but its slot is freed so other work flows; a landed/empty lane is removed and its branch deleted." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
Remove-Item Env:SQL_SYNC_SKIP
```

### Task 4: Add `merge-back.ps1` (serialized `--no-ff` onto `feature/2.5.63`, never main, conflict-defer)

**Files:** `C:\dev\nexora\tools\autopilot\merge-back.ps1` (new), `C:\dev\nexora\tools\autopilot\tests\merge-back.assert.ps1` (new)

**Design:** Template = `push-branch.ps1` (single git-mutating action, never-main guard, one JSON verdict, own log, never-throw; uses `git -C` throughout — **no top-level `Set-Location`**, which would corrupt the multi-case assert harness CWD). `merge-back.ps1 -Slot K -IssueNumber NN -Branch feature/2.5.63` takes a dedicated **`merge.lock`** via `lock.ps1` with a **bounded blocking wait** (poll up to `-LockWaitSec`, default 1800) so a second lane WAITS rather than needing an in-canvas retry cycle; if it cannot get the lock in time, returns `{status:'BUSY'}` (caller routes BUSY to continue-collector, NOT a self-loop). Then: refuse if base is on main/master; `git -C <base> checkout feature/2.5.63`; `git -C <base> merge --no-ff auto/issue-NN`. On success → release the lane → `{status:'MERGED', sha}`. On conflict → `git merge --abort`, leave the lane intact, `{status:'CONFLICT', slot, branch, issue}`. Always release `merge.lock` in `finally`.

- [ ] **Write the failing assertion first.** Create `C:\dev\nexora\tools\autopilot\tests\merge-back.assert.ps1`:

```powershell
#requires -Version 7
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\merge-back.ps1'
$tools  = Split-Path $script
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'merge-back.ps1 parses'

$tmp = New-Item -ItemType Directory -Path (Join-Path ([IO.Path]::GetTempPath()) ("mb-" + [guid]::NewGuid().ToString('N')))
try {
  $repo = Join-Path $tmp 'repo'
  New-Item -ItemType Directory -Path (Join-Path $repo 'tools\autopilot') | Out-Null
  foreach ($s in 'semaphore.ps1','lane-paths.ps1','lane.ps1','lock.ps1') { Copy-Item (Join-Path $tools $s) (Join-Path $repo 'tools\autopilot') }
  git -C $repo init -q -b 'feature/2.5.63' *> $null
  git -C $repo config user.email 't@t'; git -C $repo config user.name 't'
  Set-Content (Join-Path $repo 'base.txt') "line1`nline2`n"; git -C $repo add -A *> $null; git -C $repo commit -q -m 'init' *> $null

  $slots = Join-Path $tmp 'slots'; $mlock = Join-Path $tmp 'merge.lock'
  $laneScript = Join-Path $repo 'tools\autopilot\lane.ps1'
  $common = @{ BaseRepo = $repo; SlotsDir = $slots; MaxSlots = 3; MergeLock = $mlock; LockWaitSec = 2 }

  # Lane A: clean change on a DIFFERENT file -> merges cleanly.
  $a = & $laneScript -Action acquire -IssueNumber 11 -BaseRepo $repo -SlotsDir $slots -MaxSlots 3 | Select-Object -Last 1 | ConvertFrom-Json
  Set-Content (Join-Path $a.worktree 'new-a.txt') 'A'; git -C $a.worktree add -A *> $null; git -C $a.worktree commit -q -m 'feat A' *> $null
  $ra = & $script -Slot $a.slot -IssueNumber 11 @common | Select-Object -Last 1 | ConvertFrom-Json
  Assert ($ra.status -eq 'MERGED') "clean lane => MERGED (got $($ra.status))"
  Assert (Test-Path (Join-Path $repo 'new-a.txt')) 'lane A change landed on feature/2.5.63'

  # Lane B: conflicting change on base.txt -> CONFLICT, deferred (not resolved), aborted clean.
  $b = & $laneScript -Action acquire -IssueNumber 12 -BaseRepo $repo -SlotsDir $slots -MaxSlots 3 | Select-Object -Last 1 | ConvertFrom-Json
  Set-Content (Join-Path $b.worktree 'base.txt') "LANE-B`nline2`n"; git -C $b.worktree add -A *> $null; git -C $b.worktree commit -q -m 'feat B' *> $null
  Set-Content (Join-Path $repo 'base.txt') "FEATURE`nline2`n"; git -C $repo add -A *> $null; git -C $repo commit -q -m 'feature edit' *> $null
  $rb = & $script -Slot $b.slot -IssueNumber 12 @common | Select-Object -Last 1 | ConvertFrom-Json
  Assert ($rb.status -eq 'CONFLICT') "conflicting lane => CONFLICT deferred (got $($rb.status))"
  Assert (@(git -C $repo ls-files -u).Count -eq 0) 'merge aborted clean (no unmerged index left behind)'
  Assert ((git -C $repo rev-parse --abbrev-ref HEAD).Trim() -eq 'feature/2.5.63') 'still on feature branch after abort'
  Assert (Test-Path $b.worktree) 'lane B worktree kept for the resolver'

  # merge.lock released after the call (serialization, not a permanent hold).
  $lk = & (Join-Path $repo 'tools\autopilot\lock.ps1') -Action check -LockPath $mlock | ConvertFrom-Json
  Assert (-not $lk.exists) 'merge.lock released after merge-back returns'

  # never-main guard.
  git -C $repo branch -f main 2>$null *> $null; git -C $repo checkout -q main *> $null
  $rm = & $script -Slot 0 -IssueNumber 99 @common | Select-Object -Last 1 | ConvertFrom-Json
  Assert ($rm.status -eq 'refused-main') "refuses to merge onto main (got $($rm.status))"
} finally { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue }

if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
```

- [ ] **Run it red:** `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\merge-back.assert.ps1`.

- [ ] **Implement `C:\dev\nexora\tools\autopilot\merge-back.ps1`:**

```powershell
#requires -Version 7
<#
.SYNOPSIS
  Serialized merge-back of a finished lane (auto/issue-NN) onto the feature branch, in completion
  order, one lane at a time. NEVER main, NEVER PR. On a git conflict it does NOT resolve - it aborts
  cleanly and defers to merge-resolve.ps1. Emits ONE compact JSON line; exit 0; never throws.
.DESCRIPTION
  Takes a dedicated merge.lock with a BOUNDED BLOCKING wait so only one lane writes the shared branch
  at a time and a second lane WAITS rather than needing an in-canvas retry cycle. status:
    BUSY         -> could not get merge.lock within -LockWaitSec; caller routes to continue-collector.
    refused-main -> base is on main/master; refuse (never-main).
    MERGED       -> merge --no-ff succeeded; lane removed; {sha}.
    CONFLICT     -> merge conflicted; aborted clean; lane left intact for merge-resolve.ps1.
  Uses git -C throughout; NO top-level Set-Location (it would corrupt a multi-case assert harness CWD).
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][int]$Slot,
  [Parameter(Mandatory)][int]$IssueNumber,
  [string]$BaseRepo = 'C:\dev\nexora',
  [string]$Branch = 'feature/2.5.63',
  [string]$SlotsDir = 'C:\dev\nexora\var\autopilot\slots',
  [int]$MaxSlots = 3,
  [string]$MergeLock = 'C:\dev\nexora\var\autopilot\merge.lock',
  [int]$LockWaitSec = 1800
)
$ErrorActionPreference = 'Stop'
$env:SQL_SYNC_SKIP = '1'
Remove-Item Env:GH_TOKEN, Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
$lockScript = Join-Path $BaseRepo 'tools\autopilot\lock.ps1'
$laneScript = Join-Path $BaseRepo 'tools\autopilot\lane.ps1'
. (Join-Path $BaseRepo 'tools\autopilot\lane-paths.ps1')
$logDir = Join-Path $BaseRepo 'var\autopilot\logs'; New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir 'merge.log'
$haveLock = $false
try {
  $cur = (git -C $BaseRepo rev-parse --abbrev-ref HEAD).Trim()
  if ($cur -in @('main','master')) { [ordered]@{ status = 'refused-main'; branch = $cur } | ConvertTo-Json -Compress; exit 0 }

  # Bounded blocking acquire of the serialization lock.
  $deadline = (Get-Date).AddSeconds($LockWaitSec)
  do {
    $lk = (& $lockScript -Action acquire -LockPath $MergeLock | Select-Object -Last 1 | ConvertFrom-Json)
    if ($lk.status -eq 'ACQUIRED') { $haveLock = $true; break }
    Start-Sleep -Milliseconds 500
  } while ((Get-Date) -lt $deadline)
  if (-not $haveLock) { [ordered]@{ status = 'BUSY' } | ConvertTo-Json -Compress; exit 0 }

  $lp = Get-LanePaths -Lane $Slot -BaseRepo $BaseRepo -IssueNumber $IssueNumber
  "=== MERGE-BACK lane $Slot $($lp.branch) onto $Branch $(Get-Date -Format o) ===" | Add-Content -Path $log -Encoding utf8
  git -C $BaseRepo checkout $Branch 2>&1 | Add-Content -Path $log -Encoding utf8
  git -C $BaseRepo merge --no-ff $lp.branch -m "feat(autopilot): merge $($lp.branch) for issue #$IssueNumber" 2>&1 | Add-Content -Path $log -Encoding utf8
  $merged = ($LASTEXITCODE -eq 0) -and (@(git -C $BaseRepo ls-files -u).Count -eq 0)
  if (-not $merged) {
    git -C $BaseRepo merge --abort 2>&1 | Add-Content -Path $log -Encoding utf8
    [ordered]@{ status = 'CONFLICT'; slot = $Slot; branch = $lp.branch; issue = $IssueNumber } | ConvertTo-Json -Compress
    exit 0
  }
  $sha = (git -C $BaseRepo rev-parse --short HEAD).Trim()
  & $laneScript -Action release -Slot $Slot -IssueNumber $IssueNumber -BaseRepo $BaseRepo -SlotsDir $SlotsDir -MaxSlots $MaxSlots | Out-Null
  [ordered]@{ status = 'MERGED'; slot = $Slot; branch = $lp.branch; sha = $sha; issue = $IssueNumber } | ConvertTo-Json -Compress
} catch {
  try { git -C $BaseRepo merge --abort 2>$null | Out-Null } catch {}
  [ordered]@{ status = 'ERROR'; slot = $Slot; reason = $_.Exception.Message } | ConvertTo-Json -Compress
  exit 0
} finally {
  if ($haveLock) { & $lockScript -Action release -LockPath $MergeLock | Out-Null }
}
```

- [ ] **Run it green:** `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\merge-back.assert.ps1` — expect `ALL PASS`.

- [ ] **Commit:**
```powershell
$env:SQL_SYNC_SKIP = '1'
git add tools/autopilot/merge-back.ps1 tools/autopilot/tests/merge-back.assert.ps1
git commit -m "feat(autopilot): add serialized merge-back onto the feature branch" -m "merge-back.ps1 takes a dedicated merge.lock with a bounded blocking wait so only one lane writes feature/2.5.63 at a time (completion order) and a second lane waits rather than needing an in-canvas retry loop. merge --no-ff of auto/issue-NN; on success the lane is removed and slot freed. A conflict is NOT resolved inline - it aborts clean and returns CONFLICT, leaving the lane intact for merge-resolve.ps1. Hard never-main guard; uses git -C throughout (no Set-Location)." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
Remove-Item Env:SQL_SYNC_SKIP
```

### Task 5: Add `merge-resolve.ps1` (separate conflict-resolver agent)

**Files:** `C:\dev\nexora\tools\autopilot\merge-resolve.ps1` (new), `C:\dev\nexora\tools\autopilot\tests\merge-resolve.assert.ps1` (new)

**Design:** Runs ONLY when `merge-back.ps1` returned `CONFLICT`. Takes `merge.lock` (same bounded blocking wait), re-runs `git merge --no-ff auto/issue-NN`, and hands the conflicted tree to a `claude -p` (`--model opus --dangerously-skip-permissions`, token-scrub + `SQL_SYNC_SKIP=1`). On a clean result it commits + releases the lane (`{status:'MERGED', sha}`); else aborts and returns `{status:'UNRESOLVED'}` (owner-notified, lane kept). The claude stream goes to `var/autopilot/logs/merge-resolve.log` via `Tee-Object`; only the verdict reaches stdout. `-ResolverCommand` is a test affordance (default = real claude); the assert drives a fake resolver. **Fixture files are written with single-quoted here-strings (`@'...'@`) and parse-checked before use** (a single-quoted string does NOT process `""` escapes).

- [ ] **Write the failing assertion first.** Create `C:\dev\nexora\tools\autopilot\tests\merge-resolve.assert.ps1`:

```powershell
#requires -Version 7
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\merge-resolve.ps1'
$tools  = Split-Path $script
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'merge-resolve.ps1 parses'

$tmp = New-Item -ItemType Directory -Path (Join-Path ([IO.Path]::GetTempPath()) ("mr-" + [guid]::NewGuid().ToString('N')))
try {
  $repo = Join-Path $tmp 'repo'
  New-Item -ItemType Directory -Path (Join-Path $repo 'tools\autopilot') | Out-Null
  foreach ($s in 'semaphore.ps1','lane-paths.ps1','lane.ps1','lock.ps1') { Copy-Item (Join-Path $tools $s) (Join-Path $repo 'tools\autopilot') }
  git -C $repo init -q -b 'feature/2.5.63' *> $null
  git -C $repo config user.email 't@t'; git -C $repo config user.name 't'
  Set-Content (Join-Path $repo 'base.txt') "line1`nline2`n"; git -C $repo add -A *> $null; git -C $repo commit -q -m 'init' *> $null
  $slots = Join-Path $tmp 'slots'; $mlock = Join-Path $tmp 'merge.lock'
  $laneScript = Join-Path $repo 'tools\autopilot\lane.ps1'

  # Fixtures written with single-quoted here-strings (closing '@ at column 0), then parse-checked.
  $good = Join-Path $tmp 'resolve-good.ps1'
  Set-Content $good @'
#requires -Version 7
param($RepoPath)
Set-Content (Join-Path $RepoPath 'base.txt') "MERGED`nline2`n"
git -C $RepoPath add -A *> $null
'{"ok":true}'
'@
  $noop = Join-Path $tmp 'resolve-noop.ps1'
  Set-Content $noop @'
#requires -Version 7
param($RepoPath)
'{"ok":false}'
'@
  foreach ($fx in @($good,$noop)) {
    $fe = @(); [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $fx), [ref]$null, [ref]$fe) | Out-Null
    Assert ($fe.Count -eq 0) "fixture $([IO.Path]::GetFileName($fx)) parses"
  }

  # Conflict + a resolver that RESOLVES => MERGED.
  $a = & $laneScript -Action acquire -IssueNumber 12 -BaseRepo $repo -SlotsDir $slots -MaxSlots 3 | Select-Object -Last 1 | ConvertFrom-Json
  Set-Content (Join-Path $a.worktree 'base.txt') "LANE-B`nline2`n"; git -C $a.worktree add -A *> $null; git -C $a.worktree commit -q -m 'feat B' *> $null
  Set-Content (Join-Path $repo 'base.txt') "FEATURE`nline2`n"; git -C $repo add -A *> $null; git -C $repo commit -q -m 'feature edit' *> $null
  $rgood = & $script -Slot $a.slot -IssueNumber 12 -BaseRepo $repo -SlotsDir $slots -MaxSlots 3 -MergeLock $mlock -ResolverCommand "pwsh -NoProfile -File $good" | Select-Object -Last 1 | ConvertFrom-Json
  Assert ($rgood.status -eq 'MERGED') "resolver fixes conflict => MERGED (got $($rgood.status))"
  Assert ((Get-Content (Join-Path $repo 'base.txt') -Raw) -match 'MERGED') 'resolved content landed on feature'

  # Conflict + a resolver that does NOTHING => UNRESOLVED, aborted clean.
  $b = & $laneScript -Action acquire -IssueNumber 13 -BaseRepo $repo -SlotsDir $slots -MaxSlots 3 | Select-Object -Last 1 | ConvertFrom-Json
  Set-Content (Join-Path $b.worktree 'base.txt') "LANE-C`nline2`n"; git -C $b.worktree add -A *> $null; git -C $b.worktree commit -q -m 'feat C' *> $null
  Set-Content (Join-Path $repo 'base.txt') "FEATURE2`nline2`n"; git -C $repo add -A *> $null; git -C $repo commit -q -m 'feature edit 2' *> $null
  $rbad = & $script -Slot $b.slot -IssueNumber 13 -BaseRepo $repo -SlotsDir $slots -MaxSlots 3 -MergeLock $mlock -ResolverCommand "pwsh -NoProfile -File $noop" | Select-Object -Last 1 | ConvertFrom-Json
  Assert ($rbad.status -eq 'UNRESOLVED') "resolver leaves conflict => UNRESOLVED (got $($rbad.status))"
  Assert (@(git -C $repo ls-files -u).Count -eq 0) 'tree aborted clean after UNRESOLVED'
} finally { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue }

if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
```

- [ ] **Run it red:** `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\merge-resolve.assert.ps1`.

- [ ] **Implement `C:\dev\nexora\tools\autopilot\merge-resolve.ps1`:**

```powershell
#requires -Version 7
<#
.SYNOPSIS
  Separate merge-conflict resolver agent. Runs ONLY when merge-back.ps1 returned CONFLICT. Takes
  merge.lock (bounded blocking wait), re-runs the merge, and hands the conflicted tree to a claude -p
  agent to resolve. On a clean result it commits + releases the lane; else aborts and returns
  UNRESOLVED. Emits ONE compact JSON line; exit 0; never throws.
.DESCRIPTION
  -ResolverCommand is a test affordance (default = the real claude invocation, streamed to
  merge-resolve.log via Tee-Object; only the verdict reaches stdout). Uses git -C throughout.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][int]$Slot,
  [Parameter(Mandatory)][int]$IssueNumber,
  [string]$BaseRepo = 'C:\dev\nexora',
  [string]$Branch = 'feature/2.5.63',
  [string]$SlotsDir = 'C:\dev\nexora\var\autopilot\slots',
  [int]$MaxSlots = 3,
  [string]$MergeLock = 'C:\dev\nexora\var\autopilot\merge.lock',
  [int]$LockWaitSec = 1800,
  [string]$ResolverCommand = ''
)
$ErrorActionPreference = 'Stop'
$env:SQL_SYNC_SKIP = '1'
Remove-Item Env:GH_TOKEN, Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
$lockScript = Join-Path $BaseRepo 'tools\autopilot\lock.ps1'
$laneScript = Join-Path $BaseRepo 'tools\autopilot\lane.ps1'
. (Join-Path $BaseRepo 'tools\autopilot\lane-paths.ps1')
$logDir = Join-Path $BaseRepo 'var\autopilot\logs'; New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir 'merge-resolve.log'
$haveLock = $false
try {
  $cur = (git -C $BaseRepo rev-parse --abbrev-ref HEAD).Trim()
  if ($cur -in @('main','master')) { [ordered]@{ status = 'refused-main' } | ConvertTo-Json -Compress; exit 0 }
  $deadline = (Get-Date).AddSeconds($LockWaitSec)
  do {
    $lk = (& $lockScript -Action acquire -LockPath $MergeLock | Select-Object -Last 1 | ConvertFrom-Json)
    if ($lk.status -eq 'ACQUIRED') { $haveLock = $true; break }
    Start-Sleep -Milliseconds 500
  } while ((Get-Date) -lt $deadline)
  if (-not $haveLock) { [ordered]@{ status = 'BUSY' } | ConvertTo-Json -Compress; exit 0 }

  $lp = Get-LanePaths -Lane $Slot -BaseRepo $BaseRepo -IssueNumber $IssueNumber
  "=== MERGE-RESOLVE lane $Slot $($lp.branch) $(Get-Date -Format o) ===" | Add-Content -Path $log -Encoding utf8
  git -C $BaseRepo checkout $Branch 2>&1 | Add-Content -Path $log -Encoding utf8
  git -C $BaseRepo merge --no-ff $lp.branch -m "feat(autopilot): merge $($lp.branch) for issue #$IssueNumber" 2>&1 | Add-Content -Path $log -Encoding utf8
  if ($LASTEXITCODE -eq 0 -and (@(git -C $BaseRepo ls-files -u).Count -eq 0)) {
    $sha = (git -C $BaseRepo rev-parse --short HEAD).Trim()
    & $laneScript -Action release -Slot $Slot -IssueNumber $IssueNumber -BaseRepo $BaseRepo -SlotsDir $SlotsDir -MaxSlots $MaxSlots | Out-Null
    [ordered]@{ status = 'MERGED'; slot = $Slot; sha = $sha } | ConvertTo-Json -Compress; exit 0
  }
  if (-not $ResolverCommand) {
    $resolverArgs = @('-p','--model','opus','--dangerously-skip-permissions','--output-format','stream-json','--verbose')
    $conflicted = (git -C $BaseRepo diff --name-only --diff-filter=U) -join "`n"
    $prompt = @"
You are resolving a git merge conflict in $BaseRepo. The branch $($lp.branch) is being merged into
$Branch and conflicts. Resolve every conflict correctly keeping BOTH intents where possible, and
``git add`` each resolved file. Do NOT commit and do NOT push. When done, ensure ``git ls-files -u``
is empty. Conflicted files:
$conflicted
"@
    Push-Location $BaseRepo
    try { $prompt | claude @resolverArgs | Tee-Object -FilePath $log -Append | Out-Null } finally { Pop-Location }
  } else {
    Invoke-Expression "$ResolverCommand -RepoPath `"$BaseRepo`"" 2>&1 | Add-Content -Path $log -Encoding utf8
  }
  if ((@(git -C $BaseRepo ls-files -u).Count -eq 0) -and (git -C $BaseRepo status --porcelain)) {
    git -C $BaseRepo commit --no-edit 2>&1 | Add-Content -Path $log -Encoding utf8
    $sha = (git -C $BaseRepo rev-parse --short HEAD).Trim()
    & $laneScript -Action release -Slot $Slot -IssueNumber $IssueNumber -BaseRepo $BaseRepo -SlotsDir $SlotsDir -MaxSlots $MaxSlots | Out-Null
    [ordered]@{ status = 'MERGED'; slot = $Slot; sha = $sha } | ConvertTo-Json -Compress
  } else {
    git -C $BaseRepo merge --abort 2>&1 | Add-Content -Path $log -Encoding utf8
    [ordered]@{ status = 'UNRESOLVED'; slot = $Slot; branch = $lp.branch; issue = $IssueNumber } | ConvertTo-Json -Compress
  }
} catch {
  try { git -C $BaseRepo merge --abort 2>$null | Out-Null } catch {}
  [ordered]@{ status = 'ERROR'; slot = $Slot; reason = $_.Exception.Message } | ConvertTo-Json -Compress
  exit 0
} finally {
  if ($haveLock) { & $lockScript -Action release -LockPath $MergeLock | Out-Null }
}
```

- [ ] **Run it green:** `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\merge-resolve.assert.ps1` — expect `ALL PASS`.

- [ ] **Commit:**
```powershell
$env:SQL_SYNC_SKIP = '1'
git add tools/autopilot/merge-resolve.ps1 tools/autopilot/tests/merge-resolve.assert.ps1
git commit -m "feat(autopilot): add separate merge-conflict resolver agent" -m "merge-resolve.ps1 runs only when merge-back.ps1 returns CONFLICT. Under the same serialized merge.lock it re-runs the merge and hands the conflicted tree to a claude -p (opus) agent; on a clean result it commits and releases the lane, else aborts clean and returns UNRESOLVED for a human. The conflict handler is a SEPARATE agent, never inline. claude stream is confined to merge-resolve.log." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
Remove-Item Env:SQL_SYNC_SKIP
```

---

# PHASE 3 — Serial DB lock

*The real correctness risk: parallel `/execute-plan` runs share INT/TEST and stomp `NEXORA_TEST` state. v1 keeps the DB-touching step serial. **The DB-touching step is `run-exec` (`/execute-plan`, which runs the suite during the build), NOT `verify-exec` (which is pure git/file inspection via probe-state).** So the canvas wraps `run-exec` in this lock (Task 13).*

### Task 6: Add `db-lock.ps1` (shared DB lock with bounded wait)

**Files:** `C:\dev\nexora\tools\autopilot\db-lock.ps1` (new), `C:\dev\nexora\tools\autopilot\tests\db-lock.assert.ps1` (new)

**Design:** A lock around `var/autopilot/db.lock` with a **blocking acquire** (poll up to `-TimeoutSec`, default 1800) so a lane waits its turn. `acquire` → `{status:'ACQUIRED'}` or `{status:'TIMEOUT'}`; `release` removes it; staleness reclaim by `LastWriteTime` past `-MaxAgeHours` (a crashed test run must not wedge all lanes forever — but `-MaxAgeHours` must exceed worst-case e2e wall time).

- [ ] **Write the failing assertion first.** Create `C:\dev\nexora\tools\autopilot\tests\db-lock.assert.ps1`:

```powershell
#requires -Version 7
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\db-lock.ps1'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'db-lock.ps1 parses'

$tmp = New-Item -ItemType Directory -Path (Join-Path ([IO.Path]::GetTempPath()) ("dbl-" + [guid]::NewGuid().ToString('N')))
try {
  $lk = Join-Path $tmp 'db.lock'
  $a = & $script -Action acquire -LockPath $lk -TimeoutSec 1 | ConvertFrom-Json
  Assert ($a.status -eq 'ACQUIRED') 'first acquire succeeds'
  $b = & $script -Action acquire -LockPath $lk -TimeoutSec 1 | ConvertFrom-Json
  Assert ($b.status -eq 'TIMEOUT') "held lock => TIMEOUT within bound (got $($b.status))"
  $r = & $script -Action release -LockPath $lk | ConvertFrom-Json
  Assert ($r.status -eq 'RELEASED') 'release frees the lock'
  $c = & $script -Action acquire -LockPath $lk -TimeoutSec 1 | ConvertFrom-Json
  Assert ($c.status -eq 'ACQUIRED') 'after release a new acquire succeeds'
  (Get-Item $lk).LastWriteTime = (Get-Date).AddHours(-5)
  $d = & $script -Action acquire -LockPath $lk -TimeoutSec 1 -MaxAgeHours 3 | ConvertFrom-Json
  Assert ($d.status -eq 'ACQUIRED') 'stale db.lock is reclaimed'
} finally { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue }

if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
```

- [ ] **Run it red:** `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\db-lock.assert.ps1`.

- [ ] **Implement `C:\dev\nexora\tools\autopilot\db-lock.ps1`:**

```powershell
#requires -Version 7
<#
.SYNOPSIS
  Shared DB lock so the DB-touching build/test step runs SERIAL across lanes (parallel /execute-plan
  runs share INT/TEST and stomp NEXORA_TEST state). acquire BLOCKS up to -TimeoutSec so a lane waits
  its turn. Emits ONE compact JSON line; exit 0; never throws.
.DESCRIPTION
  acquire -> {status:ACQUIRED} or {status:TIMEOUT} after waiting -TimeoutSec.
  release -> {status:RELEASED}. A lock older than -MaxAgeHours is reclaimed (a crashed test run must
  not wedge all lanes); -MaxAgeHours must exceed worst-case e2e wall time.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][ValidateSet('acquire','release')] [string]$Action,
  [string]$LockPath = 'C:\dev\nexora\var\autopilot\db.lock',
  [int]$TimeoutSec = 1800,
  [double]$MaxAgeHours = 2.0
)
$ErrorActionPreference = 'Stop'
try {
  New-Item -ItemType Directory -Force (Split-Path $LockPath) | Out-Null
  switch ($Action) {
    'acquire' {
      $deadline = (Get-Date).AddSeconds($TimeoutSec)
      do {
        if (Test-Path $LockPath) {
          $age = (Get-Date) - (Get-Item $LockPath).LastWriteTime
          if ($age.TotalHours -ge $MaxAgeHours) { Remove-Item $LockPath -ErrorAction SilentlyContinue }
        }
        if (-not (Test-Path $LockPath)) {
          try {
            $fs = [System.IO.File]::Open($LockPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
            try {
              $bytes = [System.Text.Encoding]::UTF8.GetBytes((@{ ts = (Get-Date -Format o); procId = $PID } | ConvertTo-Json -Compress))
              $fs.Write($bytes, 0, $bytes.Length)
            } finally { $fs.Dispose() }
            @{ status = 'ACQUIRED' } | ConvertTo-Json -Compress; exit 0
          } catch { }
        }
        Start-Sleep -Milliseconds 500
      } while ((Get-Date) -lt $deadline)
      @{ status = 'TIMEOUT' } | ConvertTo-Json -Compress
    }
    'release' {
      Remove-Item $LockPath -ErrorAction SilentlyContinue
      @{ status = 'RELEASED' } | ConvertTo-Json -Compress
    }
  }
} catch {
  @{ status = 'ERROR'; reason = $_.Exception.Message } | ConvertTo-Json -Compress
  exit 0
}
```

- [ ] **Run it green:** `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\db-lock.assert.ps1` — expect `ALL PASS`.

- [ ] **Commit:**
```powershell
$env:SQL_SYNC_SKIP = '1'
git add tools/autopilot/db-lock.ps1 tools/autopilot/tests/db-lock.assert.ps1
git commit -m "feat(autopilot): add shared DB lock to serialize the build/test step" -m "db-lock.ps1 serializes the DB-touching step across lanes. The DB-stomping work is the /execute-plan build (run-exec, which runs the suite), not the pure-git verify-exec, so the canvas wraps run-exec in this lock. acquire blocks up to -TimeoutSec (CreateNew, no TOCTOU); a lock older than -MaxAgeHours is reclaimed so a crashed test run never wedges all lanes." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
Remove-Item Env:SQL_SYNC_SKIP
```

---

# PHASE 4 — Make the existing scripts lane-aware

*Thread per-lane paths through the build/recovery/state scripts. Each edit anchors on verbatim snippets and keeps the single-run path byte-for-byte intact.*

### Task 7: Make `run-phase.ps1` per-lane (log + state params) and set `AUTOPILOT_LANE`

**File:** `C:\dev\nexora\tools\autopilot\run-phase.ps1` (modified)

**Design:** Add `-LogPath`/`-StatePath` (default empty → today's single paths) plus a `-Lane` switch. When `-Lane` is set, export `AUTOPILOT_LANE=1` so `/write-plan` builds in place on `auto/issue-NN` (Task 8) and never spawns a nested `plan/<slug>` worktree → `--merge-worktree` never fires.

- [ ] **Add the params.** Anchor on this verbatim block:
```
  [string]$RepoPath = 'C:\dev\nexora',
  [string[]]$AllowedAuthors = @()
)
```
Replace with:
```
  [string]$RepoPath = 'C:\dev\nexora',
  [string]$LogPath = '',
  [string]$StatePath = '',
  [switch]$Lane,
  [string[]]$AllowedAuthors = @()
)
```

- [ ] **Set the lane env right after the token scrub.** Anchor on this verbatim block:
```
Set-Location $RepoPath
$env:SQL_SYNC_SKIP = '1'   # scoped to this child process; never leaks to the user's shell
# Defence in depth: don't hand cached API tokens to the permission-skipped agent.
Remove-Item Env:GH_TOKEN, Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
```
Replace with:
```
Set-Location $RepoPath
$env:SQL_SYNC_SKIP = '1'   # scoped to this child process; never leaks to the user's shell
# Lane mode: tell /write-plan to build in place on auto/issue-NN (no nested plan/<slug> worktree),
# so handoff-session-state --merge-worktree never fires. Merge-back is owned by merge-back.ps1.
if ($Lane) { $env:AUTOPILOT_LANE = '1' }
# Defence in depth: don't hand cached API tokens to the permission-skipped agent.
Remove-Item Env:GH_TOKEN, Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
```

- [ ] **Derive log from the param.** Anchor:
```
$logDir = Join-Path $RepoPath 'var\autopilot\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir 'run.log'
```
Replace with:
```
if ($LogPath) { $log = $LogPath } else { $log = Join-Path $RepoPath 'var\autopilot\logs\run.log' }
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
```

- [ ] **Derive state from the param.** Anchor:
```
$statePath = Join-Path $RepoPath 'var\autopilot\run-state.json'
```
Replace with:
```
$statePath = if ($StatePath) { $StatePath } else { Join-Path $RepoPath 'var\autopilot\run-state.json' }
New-Item -ItemType Directory -Force (Split-Path $statePath) | Out-Null
```

- [ ] **Parse-check + regression assert.** Create `C:\dev\nexora\tools\autopilot\tests\run-phase-lane.assert.ps1`:
```powershell
#requires -Version 7
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\run-phase.ps1'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }
$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'run-phase.ps1 parses'
$raw = Get-Content $script -Raw
Assert ($raw -match '\[string\]\$LogPath')   'run-phase exposes -LogPath'
Assert ($raw -match '\[string\]\$StatePath') 'run-phase exposes -StatePath'
Assert ($raw -match '\[switch\]\$Lane')      'run-phase exposes -Lane'
Assert ($raw -match 'AUTOPILOT_LANE')        'run-phase sets AUTOPILOT_LANE in lane mode'
Assert ($raw -match 'if \(\$LogPath\)')      'run.log uses -LogPath when supplied'
Assert ($raw -match 'if \(\$StatePath\)')    'run-state uses -StatePath when supplied'
if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
```
Run it: `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\run-phase-lane.assert.ps1` — expect `ALL PASS`. Then run the existing single-run assert if present: `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\run-state.assert.ps1`.

- [ ] **Commit:**
```powershell
$env:SQL_SYNC_SKIP = '1'
git add tools/autopilot/run-phase.ps1 tools/autopilot/tests/run-phase-lane.assert.ps1
git commit -m "feat(autopilot): make run-phase lane-aware (per-lane paths + AUTOPILOT_LANE)" -m "Adds -LogPath/-StatePath so concurrent lanes write to var/autopilot/lanes/lane-K/ instead of three lanes interleaving one run.log, and a -Lane switch that exports AUTOPILOT_LANE=1 so /write-plan builds in place on auto/issue-NN and never spawns a nested plan/<slug> worktree (which would otherwise trigger handoff --merge-worktree straight into feature/2.5.63, unserialized). All defaults preserve the single-run path." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
Remove-Item Env:SQL_SYNC_SKIP
```

### Task 8: Teach `write-plan.md` to skip the busy-branch worktree in lane mode

**File:** `C:\dev\nexora\.claude\commands\write-plan.md` (modified)

**Design:** This is the load-bearing safety edit (see Context, finding 1). In lane mode the build is already isolated in its own worktree on `auto/issue-NN`; a nested `plan/<slug>` worktree must NOT be created (it would be merged into `feature/2.5.63` by `--merge-worktree`). Add one guard so when `AUTOPILOT_LANE` is set, step 1.6 proceeds in the current directory.

- [ ] **Anchor on this verbatim block:**
```
**If either condition is true**, create an isolated worktree for the planning work:
```
Replace with:
```
**Autopilot lane exception:** if the environment variable `AUTOPILOT_LANE` is set (the autopilot is
already building this issue inside a dedicated `auto/issue-NN` worktree), do **NOT** create a nested
worktree even if a condition below is true — proceed in the current directory. The autopilot owns the
merge-back via its serialized `merge-back.ps1`; a nested `plan/<slug>` worktree would be merged into
the parent branch by `--merge-worktree` outside that serialization.

**Otherwise, if either condition is true**, create an isolated worktree for the planning work:
```

- [ ] **Add a doc assert.** Create `C:\dev\nexora\tools\autopilot\tests\write-plan-lane.assert.ps1`:
```powershell
#requires -Version 7
$ErrorActionPreference = 'Stop'
$doc = Join-Path $PSScriptRoot '..\..\..\.claude\commands\write-plan.md'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }
Assert (Test-Path $doc) 'write-plan.md found'
$raw = Get-Content $doc -Raw
Assert ($raw -match 'AUTOPILOT_LANE') 'write-plan documents the AUTOPILOT_LANE lane exception'
Assert ($raw -match 'do \*\*NOT\*\* create a nested worktree') 'lane exception says do not create nested worktree'
if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
```
Run it: `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\write-plan-lane.assert.ps1` — expect `ALL PASS`.

- [ ] **Note for the implementer:** `.claude/commands/` is a runtime command spec read by Claude, not deployed code; no deploy/exclude change. Confirm `deploy.yml` already `/XD`-excludes `.claude` or that `.claude` is not robocopied (it is dev-side tooling). If `.claude` is NOT already excluded, add `/XD .claude` in `deploy.yml` in this commit.

- [ ] **Commit:**
```powershell
$env:SQL_SYNC_SKIP = '1'
git add .claude/commands/write-plan.md tools/autopilot/tests/write-plan-lane.assert.ps1
git commit -m "fix(autopilot): skip nested plan worktree when building in a lane" -m "write-plan step 1.6 now bails out of busy-branch worktree creation when AUTOPILOT_LANE is set. Without this, a lane worktree (a linked worktree) trips Condition B, /write-plan spawns plan/<slug>, and /execute-plan's --merge-worktree merges it straight into feature/2.5.63 in the base repo, unserialized - the exact corruption the spec feared. In lane mode the build stays in place on auto/issue-NN and merge-back is owned by merge-back.ps1." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
Remove-Item Env:SQL_SYNC_SKIP
```

### Task 9: Make `recover.ps1` lane-aware (slot lock + lane worktrees + lane branch + per-lane run.log)

**File:** `C:\dev\nexora\tools\autopilot\recover.ps1` (modified)

**Design (correctness, not YAGNI):** Under concurrency `Test-Poison` (verified live) checks `$head -ne $Branch` — in a lane `$head` is `auto/issue-NN`, so EVERY healthy lane would poison; it only matches `worktrees[\\/]+plan-`; and it asserts the single global lock exists. Add `-Slot`/`-SlotsDir`; when `-Slot >= 0`, the caller passes `-Branch auto/issue-NN` (so the HEAD check passes), `Test-Poison` recognizes lane worktrees, and the lock gate checks the lane's semaphore slot. Also forward `-RunLog` (the lane's log) into the diagnose call so the `#<n>` slice is per-lane.

- [ ] **Add `-Slot`/`-SlotsDir` params.** Anchor:
```
  [string]$LockPath = 'C:\dev\nexora\var\autopilot.lock',
  [string]$BaselineFile = 'C:\dev\nexora\var\autopilot\run-baseline.json',
```
Replace with:
```
  [string]$LockPath = 'C:\dev\nexora\var\autopilot.lock',
  [int]$Slot = -1,
  [string]$SlotsDir = 'C:\dev\nexora\var\autopilot\slots',
  [string]$BaselineFile = 'C:\dev\nexora\var\autopilot\run-baseline.json',
```

- [ ] **Teach the worktree-poison check the lane naming.** Anchor:
```
  foreach ($wt in (git -C $RepoPath worktree list)) {
    if ($wt -match 'worktrees[\\/]+plan-') {
```
Replace with:
```
  foreach ($wt in (git -C $RepoPath worktree list)) {
    if ($wt -match 'worktrees[\\/]+plan-' -or $wt -match '[\\/]lane-\d+\b') {
```

- [ ] **Make the lock sanity check slot-aware.** Anchor:
```
  $lk = ParseChild (& $lockScript -Action check -LockPath $LockPath) $null
  if ($null -eq $lk -or -not $lk.exists) { return $true }
  return $false
```
Replace with:
```
  if ($Slot -ge 0) {
    $semScript = Join-Path $RepoPath 'tools\autopilot\semaphore.ps1'
    $sm = ParseChild (& $semScript -Action check -SlotsDir $SlotsDir) $null
    $held = $false
    if ($sm -and $sm.slots) { $held = [bool](@($sm.slots) | Where-Object { [int]$_.slot -eq $Slot }) }
    if (-not $held) { return $true }
  } else {
    $lk = ParseChild (& $lockScript -Action check -LockPath $LockPath) $null
    if ($null -eq $lk -or -not $lk.exists) { return $true }
  }
  return $false
```

- [ ] **Forward the per-lane run.log into diagnose.** Anchor:
```
  $diag = ParseChild (& $DiagnoseScript -IssueNumber $IssueNumber -Repo $Repo -RepoPath $RepoPath -DbServer $DbServer -N8nPort $N8nPort -BaselineFile $BaselineFile) ([pscustomobject]@{ class='unknown'; summary='diagnose unparseable'; suggestedFix=''; costUsd=0 })
```
Replace with:
```
  $laneRunLog = Join-Path (Split-Path $BaselineFile) 'run.log'
  $diag = ParseChild (& $DiagnoseScript -IssueNumber $IssueNumber -Repo $Repo -RepoPath $RepoPath -DbServer $DbServer -N8nPort $N8nPort -BaselineFile $BaselineFile -RunLog $laneRunLog) ([pscustomobject]@{ class='unknown'; summary='diagnose unparseable'; suggestedFix=''; costUsd=0 })
```

- [ ] **Parse-check + regression.** `pwsh -NoProfile -Command "[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path 'C:\dev\nexora\tools\autopilot\recover.ps1'), [ref]\$null, [ref]\$null)"` then `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\recover.assert.ps1` — expect `ALL PASS` (`-Slot` defaults -1 so the single-run global-lock branch is unchanged).

- [ ] **Commit:**
```powershell
$env:SQL_SYNC_SKIP = '1'
git add tools/autopilot/recover.ps1
git commit -m "feat(autopilot): make recover lane-aware (slot lock + lane worktrees + lane log)" -m "Adds -Slot/-SlotsDir. Test-Poison now recognises lane-K worktrees (auto/issue-NN) alongside plan-* ones, and the lock gate checks the lane's semaphore slot rather than the single global lock. The diagnose call forwards the lane run.log so the #<n> slice is per-lane, not three interleaved lanes. The caller passes -Branch=auto/issue-NN so the HEAD==Branch check passes for a healthy lane. -Slot defaults -1 => single-run path unchanged." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
Remove-Item Env:SQL_SYNC_SKIP
```

### Task 10: Make `diagnose-halt.ps1` slice the per-lane run.log

**File:** `C:\dev\nexora\tools\autopilot\diagnose-halt.ps1` (modified)

**Design:** It hard-codes the single `run.log` (or derives it from `$RepoPath`). Add/confirm a `-RunLog` param defaulting to the single-run path; `recover.ps1` (Task 9) already passes the lane log.

- [ ] **Read the verbatim run.log/RunLog handling.** `pwsh -NoProfile -Command "Select-String -Path 'C:\dev\nexora\tools\autopilot\diagnose-halt.ps1' -Pattern 'RunLog|run\.log' | ForEach-Object { \$_.LineNumber.ToString() + ': ' + \$_.Line.Trim() }"`.

- [ ] **If a `-RunLog` param already exists** (defaulting to the single path), no edit is needed — the regression below confirms it. **Otherwise**, add it. Anchor on the param-block tail (read it first; it will look like `[string]$BaselineFile = '...run-baseline.json'` as the last param) and insert before the closing `)`:
```
  [string]$RunLog = 'C:\dev\nexora\var\autopilot\logs\run.log',
```
and replace the in-body derivation of the log path (the verbatim `Join-Path ... 'run.log'` or `$RepoPath ... run.log` snippet the grep returned) with `$RunLog`.

- [ ] **Parse-check + regression.** `Parser::ParseFile` on `diagnose-halt.ps1`, then `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\recover.assert.ps1` — expect `ALL PASS` (the wired call still parses children correctly).

- [ ] **Commit:**
```powershell
$env:SQL_SYNC_SKIP = '1'
git add tools/autopilot/diagnose-halt.ps1
git commit -m "feat(autopilot): slice the per-lane run.log in diagnose-halt" -m "diagnose-halt.ps1 takes -RunLog (default = the single-run path) so under concurrency it slices the lane's own run.log, not three interleaved lanes. recover.ps1 passes the lane log (sibling of the lane baseline). Default unchanged => single-run behaviour intact." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
Remove-Item Env:SQL_SYNC_SKIP
```

### Task 11: `fetch-queue.ps1` + `setup-labels.ps1` — `autopilot-building` claim label

**Files:** `C:\dev\nexora\tools\autopilot\fetch-queue.ps1`, `C:\dev\nexora\tools\autopilot\setup-labels.ps1` (modified)

**Design:** Belt-and-braces against double-pickup (the atomic slot file is primary). Exclude an `autopilot-building` label in the queue and create it in setup.

- [ ] **Exclude the claim label in the queue.** Anchor:
```
        ($names -notcontains 'autopilot-needs-input') -and
        ($AllowedAuthors -contains $_.author.login)
```
Replace with:
```
        ($names -notcontains 'autopilot-needs-input') -and
        ($names -notcontains 'autopilot-building') -and
        ($AllowedAuthors -contains $_.author.login)
```

- [ ] **Add the label in setup.** Anchor:
```
gh label create autopilot-needs-input --repo $Repo --color 'fbca04' --description 'Autopilot needs the owner to clarify before building' --force
```
Add immediately after:
```
gh label create autopilot-building --repo $Repo --color 'c5def5' --description 'Autopilot is currently building this issue in a lane' --force
```

- [ ] **Parse-check both** with `Parser::ParseFile`. Then `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\fetch-queue.ps1` against the live repo should still print a JSON array or `[]` (no crash).

- [ ] **Commit:**
```powershell
$env:SQL_SYNC_SKIP = '1'
git add tools/autopilot/fetch-queue.ps1 tools/autopilot/setup-labels.ps1
git commit -m "feat(autopilot): add autopilot-building claim label to prevent double-pickup" -m "fetch-queue.ps1 also excludes autopilot-building so an issue already claimed by a lane is not re-assigned. setup-labels.ps1 creates the label idempotently. The atomic semaphore slot file is the primary claim record (no gh latency); the label is a visible second line and shows in-flight issues on GitHub." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
Remove-Item Env:SQL_SYNC_SKIP
```

### Task 12: `start-n8n.ps1` self-heal + `bin/nx.ps1` / `watchdog.ps1` semaphore awareness

**Files:** `C:\dev\nexora\tools\autopilot\start-n8n.ps1`, `C:\dev\nexora\bin\nx.ps1`, `C:\dev\nexora\tools\autopilot\watchdog.ps1` (modified)

**Design:** start-n8n must clear all slot files, per-lane state, merge/db locks, and ancestor-checked-prune merged lane worktrees (NEVER discard unmerged work). `nx status` must enumerate lane run-states (not the single file). The nx + watchdog liveness probes must treat a held semaphore slot as a live run (3 concurrent claudes make the host-wide probe useless).

- [ ] **start-n8n.ps1 — extend the cleanup.** Anchor:
```
$state = 'C:\dev\nexora\var\autopilot\run-state.json'
if (Test-Path $state) { Remove-Item $state -Force -ErrorAction SilentlyContinue; Write-Host 'Cleared a leftover autopilot run-state.' }
```
Replace with:
```
$state = 'C:\dev\nexora\var\autopilot\run-state.json'
if (Test-Path $state) { Remove-Item $state -Force -ErrorAction SilentlyContinue; Write-Host 'Cleared a leftover autopilot run-state.' }

# Concurrency self-heal: a crashed multi-lane run leaks slot files, per-lane state, and the merge/db
# locks; the dispatcher would then under-fill forever. NOTE: only run start-n8n when no autopilot run
# is active - this clears ALL slots unconditionally (the single-run code already assumes a clean restart).
$base = 'C:\dev\nexora'
foreach ($p in @("$base\var\autopilot\slots","$base\var\autopilot\merge.lock","$base\var\autopilot\db.lock")) {
  if (Test-Path $p) { Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue; Write-Host "Cleared leftover autopilot state: $p" }
}
$lanesDir = "$base\var\autopilot\lanes"
if (Test-Path $lanesDir) { Remove-Item $lanesDir -Recurse -Force -ErrorAction SilentlyContinue; Write-Host 'Cleared per-lane autopilot state.' }
# Prune leftover lane worktrees ONLY when their HEAD already landed on the feature branch (never
# discard unmerged work - leave it for inspection).
try {
  $featHead = (git -C $base rev-parse feature/2.5.63 2>$null)
  foreach ($wt in (git -C $base worktree list 2>$null)) {
    if ($wt -match '[\\/]lane-\d+\b') {
      $wtPath = ($wt -split '\s+')[0]
      $wtHead = (git -C $wtPath rev-parse HEAD 2>$null)
      if ($featHead -and $wtHead) {
        git -C $base merge-base --is-ancestor $wtHead.Trim() $featHead.Trim() 2>$null
        if ($LASTEXITCODE -eq 0) { git -C $base worktree remove --force $wtPath 2>$null | Out-Null; Write-Host "Pruned merged lane worktree: $wtPath" }
        else { Write-Host "Kept UNMERGED lane worktree for inspection: $wtPath" }
      }
    }
  }
  git -C $base worktree prune 2>$null | Out-Null
} catch {}
```

- [ ] **bin/nx.ps1 — read the exact bodies first.** `pwsh -NoProfile -Command "Select-String -Path 'C:\dev\nexora\bin\nx.ps1' -Pattern 'run-state.json|Get-AutopilotStatusLine|Test-AutopilotClaudeAlive|autopilot.lock' | ForEach-Object { \$_.LineNumber.ToString() + ': ' + \$_.Line.Trim() }"`.

- [ ] **nx.ps1 — enumerate lanes in the status line.** Anchor on the verbatim single `$state = ...run-state.json` read the grep returns inside `Get-AutopilotStatusLine`, and wrap it so it first enumerates `var\autopilot\lanes\lane-*\run-state.json` (format each as `#<number> <title> (<phase>, <age>m, lane <K>)`, join with `; `) and falls back to the legacy single file when no `lanes\` dir exists. Keep the exact existing format helpers; only change the source set.

- [ ] **nx.ps1 + watchdog.ps1 — semaphore-aware liveness.** Where `Test-AutopilotClaudeAlive` (nx) and watchdog check `autopilot.lock`/the host-wide claude probe, additionally treat a held, fresh semaphore slot as "a run is alive" (`semaphore.ps1 -Action check` → `free < MaxSlots`). Grep watchdog first: `pwsh -NoProfile -Command "Select-String -Path 'C:\dev\nexora\tools\autopilot\watchdog.ps1' -Pattern 'autopilot.lock|run-state.json|claude' | ForEach-Object { \$_.LineNumber.ToString() + ': ' + \$_.Line.Trim() }"` and anchor on the verbatim probe block.

- [ ] **Parse-check all three** with `Parser::ParseFile`. Then run the existing status/start-n8n asserts: `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\nx-status.assert.ps1` and `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\start-n8n-state.assert.ps1` — expect `ALL PASS` (legacy fallbacks keep them green).

- [ ] **Add a lane self-heal assert.** Create `C:\dev\nexora\tools\autopilot\tests\start-n8n-lanes.assert.ps1`:
```powershell
#requires -Version 7
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\start-n8n.ps1'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }
$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'start-n8n.ps1 parses'
$raw = Get-Content $script -Raw
Assert ($raw -match 'autopilot\\slots')           'clears slot files on startup'
Assert ($raw -match 'merge\.lock')                'clears the merge-lock on startup'
Assert ($raw -match 'db\.lock')                   'clears the db-lock on startup'
Assert ($raw -match 'lane-\\d\+')                 'prunes lane worktrees'
Assert ($raw -match 'merge-base --is-ancestor')   'lane-worktree prune is ancestor-checked'
if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
```
Run it: `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\start-n8n-lanes.assert.ps1` — expect `ALL PASS`.

- [ ] **Commit:**
```powershell
$env:SQL_SYNC_SKIP = '1'
git add tools/autopilot/start-n8n.ps1 tools/autopilot/tests/start-n8n-lanes.assert.ps1 bin/nx.ps1 tools/autopilot/watchdog.ps1
git commit -m "feat(autopilot): multi-lane self-heal, nx status, and watchdog semaphore awareness" -m "start-n8n.ps1 self-heals a crashed concurrent run: clears all semaphore slots, per-lane state, and the merge/db locks, and ancestor-checked-prunes merged lane worktrees (unmerged ones kept for inspection). nx status enumerates var/autopilot/lanes/lane-*/run-state.json (falling back to the single file), and the nx + watchdog liveness probes treat a held semaphore slot as a live run so a healthy 3-lane build is never flagged stale." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
Remove-Item Env:SQL_SYNC_SKIP
```

---

# PHASE 5 — Rewire the canvas

*One workflow. Replace the single `acquire-lock` with a per-issue lane acquire; build each lane in its worktree; wrap **run-exec** (the DB-touching /execute-plan) in the DB lock; route per-issue success through a serialized merge-back; route per-issue failure (recover → route-recovery pause) to a lane-scoped pause that frees only that slot.*

### Task 13: Add lane/db-lock/merge nodes to the canvas + a regression assert

**Files:** `C:\dev\nexora\tools\autopilot\n8n-autopilot.workflow.json` (modified), `C:\dev\nexora\tools\autopilot\tests\lanes-canvas.assert.ps1` (new)

**Verified live connection facts to preserve (do NOT drop these edges):**
- `Loop Over Items` has two outputs: DONE → `push-branch` → `release-lock-done` → `notify-summary` (the single end-of-run push), and loop → `preflight`.
- Per-issue success: `exec-ok? [true] → comment-built → notify-built → continue-collector`.
- Per-issue failure: `exec-ok? [false] → recover → route-recovery`. `route-recovery` outputs: [0] `comment-built-recovered` (built), [1] `mark-blocked` (skip), [2] `notify-pause` (pause-run), [3] `notify-pause` (Fallback).
- `push-branch` is NOT in the per-issue path and is NOT a DB step — do not chain merge onto it.

**Node-string forms (copy verbatim from the live canvas):** Execute Command nodes use the `=` expression prefix and absolute `pwsh -NoProfile -File <abs path>` with `{{ $('Node').item.json.x }}`; an arg that can resolve to `''` is wrapped in escaped quotes (the documented crash-loop guard).

- [ ] **Read the current node params + connections.** `pwsh -NoProfile -Command "\$wf = Get-Content 'C:\dev\nexora\tools\autopilot\n8n-autopilot.workflow.json' -Raw | ConvertFrom-Json; \$wf.connections | ConvertTo-Json -Depth 8"` and capture the `acquire-lock`, `run-plan`, `run-exec`, `verify-exec`, `route-recovery` node `command` strings.

- [ ] **Write the failing canvas assert first.** Create `C:\dev\nexora\tools\autopilot\tests\lanes-canvas.assert.ps1`:
```powershell
#requires -Version 7
$ErrorActionPreference = 'Stop'
$wfPath = Join-Path $PSScriptRoot '..\n8n-autopilot.workflow.json'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

$wf = $null; try { $wf = Get-Content $wfPath -Raw | ConvertFrom-Json } catch {}
Assert ($null -ne $wf) 'workflow JSON parses'
$raw = Get-Content $wfPath -Raw
$names = @($wf.nodes.name)

Assert ($names -contains 'dispatch-acquire') 'dispatch-acquire node present (lane acquire)'
Assert ($names -contains 'merge-back')        'merge-back node present (serialized merge)'
Assert ($names -contains 'merge-resolve')     'merge-resolve node present (conflict agent)'
Assert ($names -contains 'merge-route')       'merge-route Switch present'
Assert ($names -contains 'db-acquire' -and $names -contains 'db-release') 'db-lock acquire+release nodes present'
Assert ($names -contains 'pause-lane')        'pause-lane node present (lane-scoped pause)'

$da = ($wf.nodes | Where-Object { $_.name -eq 'dispatch-acquire' }).parameters.command
Assert ($da -match '^=')                         'dispatch-acquire is an n8n expression'
Assert ($da -match 'lane\.ps1 -Action acquire')  'dispatch-acquire runs lane.ps1 acquire'

# run-exec builds in the LANE worktree + per-lane log/state + -Lane mode.
$exec = ($wf.nodes | Where-Object { $_.name -eq 'run-exec' }).parameters.command
Assert ($exec -match '-RepoPath "\{\{') 'run-exec points -RepoPath at the lane worktree (quoted expr)'
Assert ($exec -match '-LogPath "\{\{')  'run-exec passes a per-lane -LogPath'
Assert ($exec -match '-Lane')           'run-exec runs in -Lane mode (suppresses nested worktree)'

# The DB lock wraps run-exec (the /execute-plan build), NOT the pure-git verify-exec.
$conns = $wf.connections
Assert (@($conns.'db-acquire'.main[0].node) -contains 'run-exec') 'db-acquire feeds run-exec (serial-DB step)'
Assert (@($conns.'verify-exec'.main[0].node) -contains 'db-release' -or @($conns.'exec-ok?'.main[0].node) -contains 'db-release' -or $names -contains 'db-release') 'db-release present after the DB step'

$mb = ($wf.nodes | Where-Object { $_.name -eq 'merge-back' }).parameters.command
Assert ($mb -match 'merge-back\.ps1 -Slot "\{\{') 'merge-back passes the lane -Slot (quoted expr)'

# No bare empty-fallback args (crash-loop guard) on the new nodes.
Assert ($raw -notmatch '-Slot \{\{') 'no bare -Slot {{ (would crash when slot expr empty)'

if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
```

- [ ] **Run it red:** `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\lanes-canvas.assert.ps1`.

- [ ] **Edit the canvas JSON** so the assert passes, preserving every verified edge above:
  - (a) Replace `acquire-lock`/`got-lock?` with a per-issue **`dispatch-acquire`** Execute Command node (`=pwsh -NoProfile -File C:\\dev\\nexora\\tools\\autopilot\\lane.ps1 -Action acquire -IssueNumber {{ $('Loop Over Items').item.json.number }}`) and a **`got-slot?`** IF on `status == ACQUIRED` (FULL → `continue-collector`, requeued next poll). Place these on the loop branch before `preflight` so each looped issue claims a lane.
  - (b) Thread the acquire JSON into `run-plan` and `run-exec`: `-RepoPath "{{ JSON.parse($('dispatch-acquire').item.json.stdout).worktree }}"`, `-LogPath "C:\\dev\\nexora\\var\\autopilot\\lanes\\lane-{{ JSON.parse($('dispatch-acquire').item.json.stdout).slot }}\\run.log"`, `-StatePath "...lane-<slot>\\run-state.json"`, and add `-Lane` to both.
  - (c) **DB lock around run-exec:** insert `db-acquire` (`=pwsh ... db-lock.ps1 -Action acquire`) feeding `run-exec`, and `db-release` (`db-lock.ps1 -Action release`) after `verify-exec` resolves (place it on the `verify-exec → exec-ok?` path so the lock is freed once the build/verify completes regardless of pass/fail). Both branches of `exec-ok?` must end up having released the DB lock.
  - (d) **Per-issue success:** rewire `exec-ok? [true]` to **`merge-back`** (`=pwsh ... merge-back.ps1 -Slot "{{ JSON.parse($('dispatch-acquire').item.json.stdout).slot }}" -IssueNumber {{ $('Loop Over Items').item.json.number }}`) → a **`merge-route`** Switch on `status`: `MERGED` → `comment-built` (existing success tail), `CONFLICT` → `merge-resolve` (`=pwsh ... merge-resolve.ps1 -Slot "{{...slot}}" -IssueNumber {{...number}}`) → `notify-conflict` Telegram → `continue-collector`, `BUSY` → `continue-collector` (retried next poll — NO in-canvas self-loop), Fallback → `notify-pause`.
  - (e) **Per-issue failure pause:** rewire `route-recovery` output [2] and [3] (`notify-pause`) so after `notify-pause` the flow goes to a **`pause-lane`** Execute Command (`=pwsh ... lane.ps1 -Action release -Slot "{{ JSON.parse($('dispatch-acquire').item.json.stdout).slot }}" -IssueNumber {{ $('Loop Over Items').item.json.number }}` — the UNMERGED path frees the slot, keeps the worktree) → `continue-collector`. This frees only the failing lane; the whole pipeline does NOT stop.
  - Keep `Loop Over Items` DONE → `push-branch` → `release-lock-done` → `notify-summary` untouched (the single end-of-run push of feature/2.5.63, now containing all merged lanes).

- [ ] **Run both canvas asserts green:** `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\lanes-canvas.assert.ps1` and `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\canvas-args.assert.ps1` — both `ALL PASS`.

- [ ] **Full assert sweep:** `pwsh -NoProfile -Command "Get-ChildItem 'C:\dev\nexora\tools\autopilot\tests\*.assert.ps1' | ForEach-Object { '== ' + \$_.Name; pwsh -NoProfile -File \$_.FullName }"` — every suite ends `ALL PASS`.

- [ ] **Commit:**
```powershell
$env:SQL_SYNC_SKIP = '1'
git add tools/autopilot/n8n-autopilot.workflow.json tools/autopilot/tests/lanes-canvas.assert.ps1
git commit -m "feat(autopilot): rewire canvas for concurrent lanes and serialized merge-back" -m "Replaces the single acquire-lock with per-issue dispatch-acquire (lane.ps1) + got-slot?, builds each lane in its worktree (run-plan/run-exec take -RepoPath=worktree, per-lane -LogPath/-StatePath, and -Lane), and wraps run-exec (the DB-touching /execute-plan) in db-acquire/db-release - the correct serial-DB seam, since verify-exec is pure git. exec-ok true now routes through serialized merge-back -> merge-route (MERGED->comment-built / CONFLICT->merge-resolve / BUSY->continue). The recover pause-run output frees only the failing lane (pause-lane keeps its worktree) and continues, instead of halting the pipeline. push-branch stays the single end-of-run push." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
Remove-Item Env:SQL_SYNC_SKIP
```

### Task 14: Docs + CHANGELOG

**Files:** `C:\dev\nexora\tools\autopilot\README.md`, `SIGNALS.md`, `RECOVERY-PLAYBOOK.md`, `C:\dev\nexora\CHANGELOG.md` (modified)

- [ ] **README:** add a `## Concurrency / lanes` subsection: 3-slot atomic semaphore replacing the global lock; worktree-per-issue on `auto/issue-NN` under `<repo-parent>\nexora-lanes`; the **corrected** worktree-vs-clone reconciliation (`AUTOPILOT_LANE` suppresses the nested `plan/<slug>` worktree, so `--merge-worktree` never fires; merge-back is the only writer of feature/2.5.63, serialized under merge.lock); the separate `merge-resolve.ps1` conflict agent; the serial-DB rule (the lock wraps `run-exec`/`/execute-plan`, the actual DB step, not `verify-exec`); per-issue PAUSE (slot freed, worktree kept); max 3 cap + queue-the-excess; the `autopilot-building` claim label; and the start-n8n "only restart when no run is active" caveat. Update the top flow, the Roadmap bullet (mark parallel **built — worktrees, owner override**), the Node/connection reference, and the lock-semantics paragraph. Add the lane-count + worktree-root to the env/vars section.

- [ ] **SIGNALS.md:** add output-contract rows for `semaphore.ps1` (`{ACQUIRED,slot}|{FULL}`), `lane.ps1` (`{ACQUIRED,slot,worktree,branch}|{FULL}|{UNMERGED}|{RELEASED}`), `merge-back.ps1` (`{MERGED,sha}|{CONFLICT}|{BUSY}|{refused-main}`), `merge-resolve.ps1` (`{MERGED}|{UNRESOLVED}|{BUSY}`), `db-lock.ps1` (`{ACQUIRED}|{TIMEOUT}|{RELEASED}`); note per-lane state lives under the BASE repo `var/autopilot/lanes/lane-K/`; add a "Pending — confirm on first live run" row for the concurrent smoke gate.

- [ ] **RECOVERY-PLAYBOOK.md:** add a "lane stuck / merge-back conflict" entry — how a per-issue PAUSE surfaces (slot freed, `lane-K` worktree + `auto/issue-NN` branch kept), how the merge-resolver agent is invoked, and how to drain a wedged slot / clean an orphaned worktree (`git worktree remove --force` + `semaphore.ps1 -Action release -Slot K`).

- [ ] **CHANGELOG:** under `## [Unreleased]` > `### Added`: `- Autopilot: build up to 3 issues concurrently — one git worktree per issue on auto/issue-NN, a 3-slot semaphore, serialized merge-back to the feature branch in completion order (a separate agent resolves conflicts), per-issue pause-on-failure, and a serial DB lock for the build/test step.`

- [ ] **Commit:**
```powershell
$env:SQL_SYNC_SKIP = '1'
git add tools/autopilot/README.md tools/autopilot/SIGNALS.md tools/autopilot/RECOVERY-PLAYBOOK.md CHANGELOG.md
git commit -m "docs(autopilot): document concurrent lanes, semaphore, and serialized merge-back" -m "README gains a Concurrency/lanes section (atomic 3-slot semaphore, worktree-per-issue, the AUTOPILOT_LANE reconciliation so --merge-worktree never fires, serialized merge-back as the only feature-branch writer, separate conflict agent, serial-DB lock around run-exec, per-issue pause, claim label). SIGNALS lists every new script's JSON contract; RECOVERY-PLAYBOOK adds a lane-stuck/merge-conflict entry; CHANGELOG gets an [Unreleased] Added line." -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
Remove-Item Env:SQL_SYNC_SKIP
```

---

# PHASE 6 — Smoke gate (OWNER ACTION — must NOT run unattended)

### Task 15: Live concurrent validation gate

**This is an Owner action** (spec line 9). It runs against live n8n + INT and cannot be automated in this session. Record results in `SIGNALS.md` afterward.

- [ ] **Pre-flight.** Run the full offline assert sweep once more; confirm `git worktree list` shows only the base + no stale `lane-*`; `pwsh ... semaphore.ps1 -Action check` shows `free: 3`.
- [ ] **Re-import the canvas via `start-n8n.ps1`** (so `executeCommand` stays enabled), then export/verify `dispatch-acquire`, `got-slot?`, `db-acquire`/`db-release`, `merge-back`, `merge-route`, `merge-resolve`, `pause-lane`, and all four `route-recovery` edges survived import.
- [ ] **Run `setup-labels.ps1` once** so `autopilot-building` exists.
- [ ] **Two trivial NON-DB issues, lanes=2.** Label two tiny doc/comment-only issues `autopilot`. Confirm: both acquire distinct slots; both build in their own worktrees (`git worktree list` shows two `lane-*` on `auto/issue-NN`); **no nested `plan/<slug>` worktree was created** (the `AUTOPILOT_LANE` guard held — check `.claude/worktrees/` stays empty in each lane); both `merge-back` serialize cleanly onto `feature/2.5.63` (the `merge.log` shows one-at-a-time acquire/release; `git log --oneline feature/2.5.63` shows both merge commits, no cross-contamination); both lane worktrees removed and slots freed afterward.
- [ ] **One DB-touch issue** (touches a route/test that runs the e2e gate) with another lane active. Confirm `db.lock` serializes the build (`db.log`/`merge.log` timing shows the two `/execute-plan` test phases did not overlap) and `NEXORA_TEST` state is not stomped (the e2e gate passes).
- [ ] **One deliberately failing issue.** Confirm its lane PAUSES (slot freed, `lane-K` worktree + `auto/issue-NN` branch kept, pause Telegram fired) while the other lanes continue — the whole pipeline does NOT stop.
- [ ] **Record the outcome** in `SIGNALS.md` ("Pending — confirm on first live run" → confirmed, with date), then **Activate** the workflow. Commit the SIGNALS update with `docs(autopilot): record concurrent smoke-gate pass` (repeated `-m`, Co-Authored-By trailer, `SQL_SYNC_SKIP=1`).

---

## Gotchas & notes

- **The reconciliation is `AUTOPILOT_LANE`, NOT "never call --merge-worktree by accident."** Verified live: a lane worktree IS a linked worktree → `/write-plan` Condition B fires → it would create a nested `plan/<slug>` worktree → `/execute-plan` unconditionally calls `--merge-worktree` → `handoff-session-state` merges into `git -C $baseRoot branch --show-current` where `$baseRoot = --git-common-dir` = the **base repo** on `feature/2.5.63` = unserialized corruption. The ONLY thing that prevents this is the `AUTOPILOT_LANE` guard in `write-plan.md` (Task 8), driven by `run-phase.ps1 -Lane` (Task 7). If a future change removes that guard or stops passing `-Lane`, lanes will race-merge into `feature/2.5.63`. The smoke gate explicitly checks `.claude/worktrees/` stayed empty.
- **The DB lock wraps `run-exec`, not `verify-exec`.** `verify-exec` runs `probe-state.ps1` (pure git/file inspection — no DB). The `NEXORA_TEST`-stomping work is inside `/execute-plan` (`run-exec`), which runs the suite during the build. Wrapping `verify-exec` would serialize a step that never touches the DB and leave the real hazard unserialized.
- **`push-branch` is the loop-DONE node, not a per-issue step.** Per-issue success is `exec-ok? → merge-back → comment-built`. `push-branch` runs once after the whole loop and pushes `feature/2.5.63` (now containing all merged lanes). Do not chain merge-back onto push-branch.
- **`recover.ps1` MUST be lane-aware** (Task 9). Its `Test-Poison` checks `HEAD == feature/2.5.63`; a lane HEAD is `auto/issue-NN`, so without `-Slot` + a lane `-Branch` every healthy lane would self-poison. This is correctness, not optional.
- **Per-lane state under the BASE repo, not the worktree.** A worktree shares the base `.git` but has its own working dir; `<lane>/var/autopilot/` does not exist. All per-lane log/state/baseline resolve under `<base>\var\autopilot\lanes\lane-K\` (via `lane-paths.ps1`), passed explicitly — never let `run-phase.ps1` derive them from `-RepoPath` (which now points at the worktree).
- **Staleness keys on the stored procId, not the host-wide claude probe.** With 3 concurrent claudes, "is ANY claude alive" is always true. `semaphore.ps1`, `bin/nx.ps1`, and `watchdog.ps1` all use per-slot/semaphore liveness.
- **`merge.lock` and `db.lock` both block with a timeout.** `merge.lock` (try up to `-LockWaitSec`) serializes the one writer of `feature/2.5.63`; a returned `BUSY` means "timed out, retry next loop" and the canvas routes BUSY to `continue-collector` — there is NO in-canvas self-loop (which n8n may drop on import). `db.lock` (try up to `-TimeoutSec`) queues the build/test step. Both `-MaxAgeHours` must exceed worst-case e2e wall time or a long healthy run gets its lock stolen.
- **Atomic claim.** `semaphore.ps1` and `db-lock.ps1` use `[IO.File]::Open(..., CreateNew)` so two near-simultaneous acquires cannot both win the same slot/lock (no Test-Path/Set-Content TOCTOU). Plus the `autopilot-building` label guards cross-cycle double-pick.
- **start-n8n clears ALL lane state unconditionally** — only restart it when no autopilot run is active (the single-run code already assumes a clean restart; with 3 lanes the blast radius is 3x). Documented in README + the start-n8n comment.
- **Worktree root is derived (`<base>-lanes`), not hardcoded.** On prod it is `D:\sydoc\nexora-lanes`; the Defender owner-action computes the path for the actual box.
- **Test isolation:** every git-exercising assert builds a throwaway repo, passes absolute `-RepoPath`/`-SlotsDir` per case, splats with a **hashtable** (`@common`, never an array — positional binding), pipes child output through `Select-Object -Last 1` before `ConvertFrom-Json`, and writes fixture scripts with single-quoted here-strings (`@'...'@`, closing `'@` at column 0) parse-checked before use. No script uses a top-level `Set-Location` that would corrupt the harness CWD across cases.
- **Commit hygiene:** every commit sets `$env:SQL_SYNC_SKIP='1'` then clears it, uses repeated `-m` flags (here-strings ParserError), and the Co-Authored-By trailer. **Never `--no-verify`.** **Remote session: stop at `git commit` — no push, no PR.**
- **No deploy/gitignore change for tools/var:** `tools`, `docs`, `var` are already `/XD`-excluded; `var/autopilot/` is gitignored; `<base>-lanes` is outside the repo. The only possible deploy edit is `/XD .claude` if `.claude` is not already excluded (checked in Task 8).
