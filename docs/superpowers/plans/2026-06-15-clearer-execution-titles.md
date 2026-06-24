# Clearer Execution Title Names -- Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make it obvious which GitHub issue an autopilot run is building, and for how long, on the two surfaces the maintainer named: (A) the canonical `nx status` (alias `nx -s`) CLI output, which must print `#<n> <title>  -- building <elapsed>`; and (B) the n8n autopilot workflow, whose per-issue Telegram notifications should each carry `#<n> <title>` so the live run is identifiable as it loops the queue.

**Architecture:** A tiny on-disk **run-state file** (`var/autopilot/run-state.json`) is the pivot. `run-phase.ps1` writes it at the start of the `plan` phase (where the issue title is already fetched), and in the `execute` phase it PRESERVES the plan-phase `number`/`title` and only flips `.phase` (the execute phase has no title of its own). The file is cleared at lifecycle boundaries only -- on `start-n8n.ps1` startup (crash-leak cleanup) -- never per phase, so it survives the plan -> execute hand-off. `nx status` reads the file, computes elapsed time from the file's `LastWriteTime` exactly as `lock.ps1` already does, applies the same liveness/staleness rule `lock.ps1` uses (so a crashed run never shows a phantom build), and appends one line. Surface B reuses the existing `{{ $('Loop Over Items').item.json.number }}` / `.title` expressions already proven in the workflow -- no new n8n feature is required (per-execution custom naming is **not** used; see Decisions).

**Tech Stack:** PowerShell 7 (`.ps1`), n8n workflow JSON, Markdown docs. No Python, no SQL, no Jinja, no JS, no i18n.

## Context an engineer needs (read first)

- **Branch:** work on `feature/2.5.63` (NOT `main`). Never run a modifying git command on `main`.
- **Remote-session policy:** stop at `git commit`. Do **not** `git push` and do **not** open a PR -- the owner does those after local review.
- **Anchor on SNIPPETS, never line numbers.** Every edit below quotes the exact string to search for; files drift, so re-`grep` the quoted snippet/symbol and edit there.
- **No SQL migration.** This feature touches no database. Do not create anything under `sql/_migrations/`.
- **No i18n.** `.ps1` scripts and `.json` workflow files are outside Flask-Babel scope (`babel.cfg` extracts only `nx_lib/**.py`, root `*.py`, `templates/**.html`). The new `nx status` strings are `Write-Host`/`Write-Info` literals -- do **not** run the pybabel cycle.
- **No Jinja templates touched** -> no Flask template-cache restart concern.
- **Commit escape hatch:** commits on this branch require `$env:SQL_SYNC_SKIP='1'` (INT `SchemaMigrations` has CRLF checksum drift that makes the `sql-migrate-int` pre-commit hook fail on Windows). Set it before each `git commit` and clear it after. **Never** use `--no-verify`.
- **How autopilot tests run:** there is NO aggregate runner and NO Pester. Each test is a standalone `tools/autopilot/tests/<name>.assert.ps1`, run with `pwsh -NoProfile -File <path>`. The house pattern (see `canvas-args.assert.ps1`): `#requires -Version 7`, `$ErrorActionPreference = 'Stop'`, an `Assert([bool]$cond,[string]$msg)` helper that prints `PASS`/`FAIL` and increments `$script:fail`, a parse-clean guard via `[System.Management.Automation.Language.Parser]::ParseFile(...)` FIRST, behavioural asserts, then `if ($fail) { "...FAILED"; exit 1 } else { "ALL PASS"; exit 0 }`. Tests that invoke a workflow grab `(Get-Content $wfPath -Raw | ConvertFrom-Json)` and query `.nodes | Where-Object { $_.name -eq '<node>' }`.
- **The n8n one-execution-loops-many-issues nuance:** the `autopilot` workflow is a SINGLE `scheduleTrigger` ("Every 2 min") whose ONE execution drains the WHOLE queue via the `splitInBatches` node named **`Loop Over Items`** (`"batchSize": 1`). One execution can therefore build many issues -- there is NOT a 1:1 execution-to-issue mapping, and self-hosted n8n cannot be made to show one execution row per issue by "naming" it. Surface B's deliverable is per-**issue** identification in the per-item Telegram notifications, NOT renaming the n8n execution. Any node referencing the looped item MUST use the exact node name `Loop Over Items` (with the space): `{{ $('Loop Over Items').item.json.number }}` / `.title`. (Verified: `split-to-items`'s jsCode `return q.map(i => ({ json: i }))` maps each `{number,title}` queue item to `{json:i}`, so `.title` resolves on each looped item.)
- **`lock.ps1` already owns the liveness probe** that `nx status` must reuse. Its exact idiom (verified): `$age = (Get-Date) - (Get-Item $LockPath).LastWriteTime` (a **datetime minus datetime**, NOT an ISO parse), then a `claude.exe` check `Where-Object { ($_.CommandLine -like '* -p *' -or $_.CommandLine -like '*stream-json*') -and $_.CommandLine -notlike '*--remote-control*' }`, with `$stale = ($age.TotalHours -ge $MaxAgeHours) -or ($age.TotalMinutes -ge 3 -and -not $running)` and `[double]$MaxAgeHours = 3.0`. **`nx status` MUST mirror this exactly** -- including using the file's `LastWriteTime` for age, never `[datetimeoffset]::Parse` (see Gotchas: that subtraction throws at runtime).
- **`run-phase.ps1` plan/execute structure** (verified): the prompt block `if ($Phase -eq 'plan') { ... $issue = gh issue view ... --json title,body,author,comments | ConvertFrom-Json ... } else { $prompt = '/execute-plan' }` runs BEFORE the run.log header block `"=== $Phase #$IssueNumber === $(Get-Date -Format o)" | Add-Content -Path $log -Encoding utf8`. So `$issue.title` is in scope after that block in the plan phase; the execute phase has neither `$issue` nor a title. The final stdout line is the result envelope: `$prompt | claude @claudeArgs | Tee-Object -FilePath $log -Append | Select-Object -Last 1` -- the n8n nodes parse that last line, so the run-state write must NEVER print to stdout.
- **deploy.yml:** VERIFY-ONLY, expect no change. `/XD` already excludes `tools`; `/XF` already excludes `nx.ps1`. `var/` is gitignored (so `run-state.json` is never committed) and deploy-excluded. Everything this feature touches is dev-side.

## Decisions locked in

| # | Decision | Why |
|---|----------|-----|
| 1 | Pivot is a NEW file `var/autopilot/run-state.json`, not the existing `var/autopilot.lock`. | The lock is acquired once per queue-drain (per-run, not per-issue) and its `{ts,procId}` shape is consumed by `recover.ps1`/`start-n8n.ps1`; widening it risks those. A sibling file rewritten per phase naturally tracks the *current* issue and is purely additive. |
| 2 | State shape: `{ ts, phase, number, title, procId }`; `ts` is ISO (`Get-Date -Format o`). | Superset of the lock schema; `procId` aids debugging. `ts` is informational only -- elapsed is computed from the file's `LastWriteTime` (Decision 4). |
| 3 | `run-phase.ps1` writes the state in the `plan` branch (number+title+ts), and in the `execute` branch PRESERVES `number`/`title`/`ts` from the existing file and only flips `.phase`. State is NOT cleared per phase. | The plan branch is the only place with the title; the execute node fetches no title. Clearing in run-phase's `finally` would delete the title before execute reads it -- defeating the whole feature (red-team F2). |
| 4 | Elapsed time = `(Get-Date) - (Get-Item $statePath).LastWriteTime`, mirroring `lock.ps1` exactly. | `(Get-Date) - [datetimeoffset]::Parse($s.ts)` THROWS at runtime (datetime minus datetimeoffset has no operator overload) -- it would crash `nx status` the instant a real build is in flight (red-team F1). `lock.ps1`'s mtime idiom is the verified-working authority. |
| 5 | Staleness in `nx status` reuses `lock.ps1`'s rule verbatim: live `claude.exe -p`/`stream-json` (not `--remote-control`), 3-min grace, 3h (`MaxAgeHours = 3.0`) hard cap. | A crashed run leaks the state file; without this `nx status` reports a phantom build. |
| 6 | `nx status` reports the autopilot line INDEPENDENTLY of `Find-AppProcess`. | A build can run while the dev server is down. |
| 7 | Surface B = enrich ALL FOUR per-item Telegram notify nodes (`notify-built`, `notify-recovered`, `notify-skip`, `notify-questions`) to `#<n> <title>`. NO per-execution n8n naming/customData. | All four already interpolate `.number`; adding `.title` is one token each and keeps "which issue" unambiguous on the built/recovered/skip/needs-input paths. Per-execution custom naming is Enterprise-gated/unverified and semantically wrong (one execution loops many issues) -- rejected (red-team F8). |
| 8 | Thread `-IssueNumber {{ $('Loop Over Items').item.json.number }}` into the `run-exec` node (adding the `=` expression prefix), mirroring `run-plan`. | Today the `run-exec` command is the literal `pwsh ... run-phase.ps1 -Phase execute` (no `=`, no number), so the execute-phase run.log header prints `=== execute #0 ===` and the execute run-state `number` would be 0. Threading the number makes the execute phase self-describing (red-team F6). |
| 9 | New `nx` flag? No -- extend the existing `status` action only. | The maintainer asked for `nx status` output (clarification #3), not a new command. |
| 10 | `run-phase.ps1` keeps its current final-stdout contract (`Select-Object -Last 1`); run-state goes to a file via `Set-Content`, never stdout. | The n8n nodes and tests parse the last stdout line; a stray `Write-Output` would break them. |

## Owner actions

These are NOT done by the implementing agent; surface them in the final handoff:

- [ ] **Re-import the edited `tools/autopilot/n8n-autopilot.workflow.json` into the live n8n editor and re-activate the `autopilot` workflow.** n8n state lives outside git and `tools/` is `/XD`-excluded from deploy, so the Surface-B Telegram change and the `run-exec` `-IssueNumber` change do nothing until re-imported. Start n8n via `tools/autopilot/start-n8n.ps1` *before* importing (its node-exclude override keeps the Execute Command nodes available; otherwise n8n silently drops node connections on import).
- [ ] Confirm on the next live run that the per-item Telegram text renders `#<n> <title>` and the `run.log` execute header now shows `=== execute #<n> ===` instead of `#0`.
- [ ] **Optional future spike:** if true per-execution n8n run names are ever wanted, evaluate whether the installed n8n version/license exposes `$execution.customData` / execution naming. Out of scope here.

---

# PHASE 0: Verify the ground truth

### Task 0: Confirm anchors, deploy excludes, and a green test baseline

**Files:** none modified (read-only verification).

- [ ] Confirm the `status` action arm still matches the anchor:
```
pwsh -NoProfile -Command "Select-String -Path C:\dev\nexora\bin\nx.ps1 -Pattern 'Running  \(PID' -SimpleMatch"
```
Expect a hit on `Write-Ok "Running  (PID $($p.Id)  ·  env $envName  ·  port 8000)"`.
- [ ] Confirm `run-phase.ps1` still writes the run.log header and fetches the title in the plan branch:
```
pwsh -NoProfile -Command "Select-String -Path C:\dev\nexora\tools\autopilot\run-phase.ps1 -Pattern '=== \$Phase #\$IssueNumber ===','--json title,body,author,comments'"
```
Expect both hits.
- [ ] Confirm `lock.ps1`'s mtime + liveness idiom (the thing `nx status` must mirror, NOT `[datetimeoffset]::Parse`):
```
pwsh -NoProfile -Command "Select-String -Path C:\dev\nexora\tools\autopilot\lock.ps1 -Pattern 'LastWriteTime','stream-json','--remote-control','MaxAgeHours'"
```
Expect four hits.
- [ ] Confirm the `run-exec` node currently lacks both the `=` prefix and `-IssueNumber`:
```
pwsh -NoProfile -Command "(Get-Content C:\dev\nexora\tools\autopilot\n8n-autopilot.workflow.json -Raw | ConvertFrom-Json).nodes | Where-Object { $_.name -eq 'run-exec' } | ForEach-Object { $_.parameters.command }"
```
Expect `pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\run-phase.ps1 -Phase execute` (no leading `=`, no `-IssueNumber`).
- [ ] Confirm deploy excludes already cover everything (expect NO edit):
```
pwsh -NoProfile -Command "Select-String -Path C:\dev\nexora\.github\workflows\deploy.yml -Pattern '/XD','/XF'"
```
Verify `/XD` contains `tools` and `/XF` contains `nx.ps1`. Record "deploy.yml: no change" and move on.
- [ ] Capture a green baseline of the existing suite:
```
pwsh -NoProfile -Command "Get-ChildItem C:\dev\nexora\tools\autopilot\tests\*.assert.ps1 | ForEach-Object { $_.Name; pwsh -NoProfile -File $_.FullName }"
```
Expect every file to end `ALL PASS`. If any are already red, note it and do not blame later failures on your changes.

No commit (verification only).

---

# PHASE 1: run-state file (the pivot)

### Task 1: `run-phase.ps1` writes/preserves `var/autopilot/run-state.json`

**Files:**
- Test (Create): `C:\dev\nexora\tools\autopilot\tests\run-state.assert.ps1`
- Modify: `C:\dev\nexora\tools\autopilot\run-phase.ps1`

- [ ] **Write the failing test.** Create `tools/autopilot/tests/run-state.assert.ps1`:

```powershell
#requires -Version 7
# Standalone assertion (no Pester). Exit 1 on any failure.
# Guards that run-phase.ps1 writes var/autopilot/run-state.json with the building issue
# (number+title+ts+phase) and -- crucially -- PRESERVES number/title in the execute phase
# (which has no title of its own) instead of blanking or deleting them.
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\run-phase.ps1'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

# 1) parse-clean guard (ALWAYS first)
$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'run-phase.ps1 parses'

$src = Get-Content $script -Raw

# 2) writes a run-state record carrying number+title+ts+phase
Assert ($src -match 'run-state\.json')                       'references run-state.json'
Assert ($src -match 'ts\s*=\s*\(Get-Date -Format o\)')      'run-state carries ISO ts'
Assert ($src -match 'number\s*=\s*\$IssueNumber')           'run-state carries issue number'
Assert ($src -match 'title\s*=')                            'run-state carries title'
Assert ($src -match 'phase\s*=\s*\$Phase')                 'run-state carries phase'
Assert ($src -match 'ConvertTo-Json')                       'serialises run-state to JSON'

# 3) execute branch must PRESERVE an existing record (number/title), not blank/delete it.
Assert ($src -match 'Test-Path \$statePath')               'execute reuses existing state when present'
# 4) run-phase must NOT delete run-state on exit (that would lose the title before execute reads it).
Assert ($src -notmatch 'Remove-Item.*run-state')           'run-phase does NOT delete run-state (cleared at lifecycle boundary, not per phase)'

if ($fail) { "`n$fail assertion(s) FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
```

- [ ] **Run it -- expect FAIL:**
```
pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\run-state.assert.ps1
```
Expect `FAIL  references run-state.json` (and others), trailing `N assertion(s) FAILED`, exit 1.

- [ ] **Implement.** In `run-phase.ps1`, locate the run.log header block (anchor on the snippet):

```powershell
$logDir = Join-Path $RepoPath 'var\autopilot\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir 'run.log'
"=== $Phase #$IssueNumber === $(Get-Date -Format o)" | Add-Content -Path $log -Encoding utf8
```

Insert, immediately AFTER that block and BEFORE the `$prompt | claude @claudeArgs ...` line, the run-state write. The plan branch has `$issue.title`; the execute branch has no title, so it preserves the existing record and only flips `.phase`:

```powershell
# Run-state side-channel for `nx status` ("which issue is building, and for how long").
# Plan phase has the title; execute phase has neither $issue nor a title (it reuses what the
# plan phase persisted). State is cleared at a lifecycle boundary (start-n8n.ps1 startup), NOT
# here -- deleting it per phase would lose the title before the execute phase reads it.
$statePath = Join-Path $RepoPath 'var\autopilot\run-state.json'
if ($Phase -eq 'plan') {
  $state = @{ ts = (Get-Date -Format o); phase = $Phase; number = $IssueNumber; title = $issue.title; procId = $PID }
} elseif (Test-Path $statePath) {
  $prior = Get-Content $statePath -Raw | ConvertFrom-Json
  $state = @{ ts = $prior.ts; phase = $Phase; number = $prior.number; title = $prior.title; procId = $PID }
} else {
  # Execute run with no prior plan-phase record (e.g. resumed half-built issue): record what we have.
  $state = @{ ts = (Get-Date -Format o); phase = $Phase; number = $IssueNumber; title = ''; procId = $PID }
}
$state | ConvertTo-Json | Set-Content -Encoding utf8 $statePath
```

Note: `$issue` exists only in the `plan` branch, and the prompt `if/else` block runs before the run.log header block, so `$issue.title` is in scope here for plan. Re-grep to confirm the prompt block precedes the header block before editing.

- [ ] **Run green:**
```
pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\run-state.assert.ps1
```
Expect `ALL PASS`, exit 0.

- [ ] **Re-run the full suite (no regression):**
```
pwsh -NoProfile -Command "Get-ChildItem C:\dev\nexora\tools\autopilot\tests\*.assert.ps1 | ForEach-Object { pwsh -NoProfile -File $_.FullName }"
```
Expect every file `ALL PASS`.

- [ ] **Commit:**
```
$env:SQL_SYNC_SKIP='1'
git add tools/autopilot/run-phase.ps1 tools/autopilot/tests/run-state.assert.ps1
git commit -F - <<'MSG'
feat(autopilot): persist run-state for which issue is building

run-phase.ps1 now writes var/autopilot/run-state.json at phase start
{ts,phase,number,title,procId} so nx status can show the in-flight issue
and its elapsed time. The plan phase records number+title (the only
phase that fetches them); the execute phase preserves them and flips
.phase. The file is cleared at a lifecycle boundary, not per phase, so
the title survives the plan-to-execute hand-off.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
MSG
$env:SQL_SYNC_SKIP=''
```

### Task 2: thread `-IssueNumber` into the `run-exec` node

**Files:**
- Test (Modify): `C:\dev\nexora\tools\autopilot\tests\canvas-args.assert.ps1`
- Modify: `C:\dev\nexora\tools\autopilot\n8n-autopilot.workflow.json`

Rationale: today `run-exec` runs `run-phase.ps1 -Phase execute` with no issue number, so the execute-phase run.log header prints `=== execute #0 ===` and the execute run-state `number` would be 0 if the plan record were ever missing. Threading the number (mirroring `run-plan`) makes the execute phase self-describing. Adding an n8n `{{ }}` expression REQUIRES the `=` prefix, else n8n passes the braces literally.

- [ ] **Add a failing assert.** In `tools/autopilot/tests/canvas-args.assert.ps1`, before the final `if ($fail)` line, add:
```powershell
# run-exec must forward the issue number so the execute phase's run.log header / run-state
# carry the real issue, not #0. Mirrors run-plan. The `=` prefix is mandatory for n8n {{ }}.
$exec = ($wf.nodes | Where-Object { $_.name -eq 'run-exec' }).parameters.command
Assert ($exec -match '^=')                                       'run-exec command is an n8n expression (= prefix)'
Assert ($exec -match "-IssueNumber \{\{ \`$\('Loop Over Items'\)\.item\.json\.number \}\}") 'run-exec passes -IssueNumber from the looped item'
```

- [ ] **Run it -- expect FAIL** on the two new asserts:
```
pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\canvas-args.assert.ps1
```

- [ ] **Implement.** In `n8n-autopilot.workflow.json`, find the `run-exec` node command (anchor on the exact current string):
```json
        "command": "pwsh -NoProfile -File C:\\dev\\nexora\\tools\\autopilot\\run-phase.ps1 -Phase execute"
```
Replace with (note the leading `=` to make it an expression, matching `run-plan`):
```json
        "command": "=pwsh -NoProfile -File C:\\dev\\nexora\\tools\\autopilot\\run-phase.ps1 -Phase execute -IssueNumber {{ $('Loop Over Items').item.json.number }}"
```
The `if ($Phase -eq 'plan')` trust gate (`if ($IssueNumber -le 0) { throw ... }`) and the `gh issue view` fetch are inside the plan branch only, so passing a number to execute is inert there -- no `run-phase.ps1` change needed for this.

- [ ] **Run green:**
```
pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\canvas-args.assert.ps1
```
Expect `ALL PASS`.

- [ ] **Confirm the workflow JSON still parses:**
```
pwsh -NoProfile -Command "Get-Content C:\dev\nexora\tools\autopilot\n8n-autopilot.workflow.json -Raw | ConvertFrom-Json | Out-Null; 'JSON OK'"
```
Expect `JSON OK`.

- [ ] **Commit:**
```
$env:SQL_SYNC_SKIP='1'
git add tools/autopilot/n8n-autopilot.workflow.json tools/autopilot/tests/canvas-args.assert.ps1
git commit -F - <<'MSG'
fix(autopilot): pass issue number to the execute phase node

run-exec now forwards -IssueNumber from the Loop Over Items item (with
the required = expression prefix, mirroring run-plan), so the execute
phase run.log header reads "execute #<n>" instead of "execute #0" and
its run-state record carries the real issue number.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
MSG
$env:SQL_SYNC_SKIP=''
```

### Task 3: clear leaked run-state on n8n startup

**Files:**
- Test (Create): `C:\dev\nexora\tools\autopilot\tests\start-n8n-state.assert.ps1`
- Modify: `C:\dev\nexora\tools\autopilot\start-n8n.ps1`

A crashed run leaks `run-state.json` exactly as it leaks the lock. `start-n8n.ps1` already clears a leftover lock on a fresh start; it must clear the run-state file too, else `nx status` reports a ghost build until the next plan phase overwrites it.

- [ ] **Write the failing test.** Create `tools/autopilot/tests/start-n8n-state.assert.ps1`:
```powershell
#requires -Version 7
# Standalone assertion (no Pester). Exit 1 on any failure.
# Guards that start-n8n.ps1 clears a leaked run-state.json on a fresh start,
# the same way it already clears a leftover lock.
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\start-n8n.ps1'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'start-n8n.ps1 parses'

$src = Get-Content $script -Raw
Assert ($src -match 'run-state\.json')                'start-n8n references run-state.json'
Assert ($src -match 'Remove-Item \$state')            'start-n8n removes a leaked run-state file'

if ($fail) { "`n$fail assertion(s) FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
```

- [ ] **Run it -- expect FAIL:**
```
pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\start-n8n-state.assert.ps1
```

- [ ] **Implement.** In `start-n8n.ps1`, find the leftover-lock cleanup (anchor on the snippet):
```powershell
$lock = 'C:\dev\nexora\var\autopilot.lock'
if (Test-Path $lock) { Remove-Item $lock -Force -ErrorAction SilentlyContinue; Write-Host 'Cleared a leftover autopilot lock.' }
```
Insert directly after it (mirroring its exact style):
```powershell

# Same for a leaked run-state file (a run that died mid-phase) -- else `nx status`
# would report a phantom build until the next plan phase overwrites it.
$state = 'C:\dev\nexora\var\autopilot\run-state.json'
if (Test-Path $state) { Remove-Item $state -Force -ErrorAction SilentlyContinue; Write-Host 'Cleared a leftover autopilot run-state.' }
```

- [ ] **Run green:**
```
pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\start-n8n-state.assert.ps1
```
Expect `ALL PASS`.

- [ ] **Re-run the full suite:**
```
pwsh -NoProfile -Command "Get-ChildItem C:\dev\nexora\tools\autopilot\tests\*.assert.ps1 | ForEach-Object { pwsh -NoProfile -File $_.FullName }"
```
Expect every file `ALL PASS`.

- [ ] **Commit:**
```
$env:SQL_SYNC_SKIP='1'
git add tools/autopilot/start-n8n.ps1 tools/autopilot/tests/start-n8n-state.assert.ps1
git commit -F - <<'MSG'
fix(autopilot): clear leaked run-state on n8n startup

A crashed run leaks var/autopilot/run-state.json the same way it leaks
the lock. start-n8n.ps1 already wipes a leftover lock on a fresh start;
clear the run-state file alongside it so nx status never reports a
phantom in-flight build.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
MSG
$env:SQL_SYNC_SKIP=''
```

---

# PHASE 2: nx status surface (canonical)

### Task 4: `nx status` shows the in-flight autopilot issue

**Files:**
- Test (Create): `C:\dev\nexora\tools\autopilot\tests\nx-status.assert.ps1`
- Modify: `C:\dev\nexora\bin\nx.ps1`

Structural choice: extract the read + staleness + format logic into a single helper `Get-AutopilotStatusLine` near the output helpers, so the `status` arm stays a thin two-liner AND the logic is testable in isolation. The test dot-sources a thin extraction is unsafe (nx.ps1 runs its action switch and has no `param()` block), so the test instead **invokes the helper by extracting + executing just its body** against synthetic state files (behavioural, not source-grep theatre -- red-team F3). The helper reads `var/autopilot/run-state.json`, computes age from the file's `LastWriteTime` (mirroring `lock.ps1`, NOT `[datetimeoffset]::Parse`, which throws), and returns `$null` when absent/stale.

- [ ] **Write the failing test.** Create `tools/autopilot/tests/nx-status.assert.ps1`. It loads ONLY the helper functions out of `nx.ps1` via the AST (so the action switch never runs), then invokes `Get-AutopilotStatusLine` against synthetic state files:

```powershell
#requires -Version 7
# Standalone assertion (no Pester). Exit 1 on any failure.
# Behavioural test: extract the autopilot-status helpers out of nx.ps1 (without running its
# action switch) and invoke Get-AutopilotStatusLine against synthetic run-state files. Catches
# the [datetimeoffset]::Parse runtime crash that a source-grep test would miss.
$ErrorActionPreference = 'Stop'
$nx = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\bin\nx.ps1')).Path
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

# 1) parse-clean guard
$errs = @()
$ast = [System.Management.Automation.Language.Parser]::ParseFile($nx, [ref]$null, [ref]$errs)
Assert ($errs.Count -eq 0) 'nx.ps1 parses'

# 2) source-text contracts (cheap structural guards)
$src = Get-Content $nx -Raw
Assert ($src -match 'function Get-AutopilotStatusLine') 'defines Get-AutopilotStatusLine'
Assert ($src -match 'run-state\.json')                 'reads run-state.json'
Assert ($src -match 'LastWriteTime')                   'computes elapsed from file LastWriteTime (lock.ps1 idiom, not datetimeoffset)'
Assert ($src -notmatch '\[datetimeoffset\]::Parse')    'does NOT use [datetimeoffset]::Parse (would throw at runtime)'
Assert ($src -match 'stream-json' -and $src -match '--remote-control') 'reuses lock-style claude liveness probe'

# 3) BEHAVIOURAL: extract the helper function definitions and dot-source ONLY them, with a
#    settable $AppDir, so we can call Get-AutopilotStatusLine without running nx.ps1's switch.
$fnDefs = $ast.FindAll(
  { param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
              $n.Name -in @('Get-AutopilotStatusLine','Test-AutopilotClaudeAlive') }, $true)
Assert ($fnDefs.Count -ge 1) 'helper function(s) extractable from AST'
$AppDir = Join-Path $env:TEMP ("nxstat_" + [guid]::NewGuid())
New-Item -ItemType Directory -Force (Join-Path $AppDir 'var\autopilot') | Out-Null
$statePath = Join-Path $AppDir 'var\autopilot\run-state.json'
foreach ($d in $fnDefs) { . ([scriptblock]::Create($d.Extent.Text)) }

try {
  # (a) absent file => $null
  if (Test-Path $statePath) { Remove-Item $statePath -Force }
  $r = Get-AutopilotStatusLine
  Assert ($null -eq $r) 'absent run-state => $null'

  # (b) fresh file (under 3-min grace) => "#<n> <title>  -- building <m>m", does NOT throw
  @{ ts=(Get-Date -Format o); phase='plan'; number=94; title='Clearer execution title name'; procId=$PID } |
    ConvertTo-Json | Set-Content -Encoding utf8 $statePath
  $r = Get-AutopilotStatusLine
  Assert ($r -is [string] -and $r -match '^#94 .*building \d+m') "fresh state => '$r'"

  # (c) stale file (mtime 10 min ago, no live claude) => $null
  (Get-Item $statePath).LastWriteTime = (Get-Date).AddMinutes(-10)
  $r = Get-AutopilotStatusLine
  Assert ($null -eq $r) 'stale run-state (10m old, no live claude) => $null'
} finally {
  Remove-Item $AppDir -Recurse -Force -ErrorAction SilentlyContinue
}

if ($fail) { "`n$fail assertion(s) FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
```

- [ ] **Run it -- expect FAIL** (helper not defined yet):
```
pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\nx-status.assert.ps1
```

- [ ] **Implement the helper.** In `bin/nx.ps1`, add both functions right after the output helpers (anchor on `function Write-Dim  ($msg)`):
```powershell
function Test-AutopilotClaudeAlive {
    # Same probe lock.ps1 uses: an autopilot run's claude runs with -p or stream-json,
    # and is NOT the interactive --remote-control session. Keep in sync with lock.ps1.
    try {
        return [bool](Get-CimInstance Win32_Process -Filter "Name='claude.exe'" -ErrorAction SilentlyContinue |
            Where-Object { ($_.CommandLine -like '* -p *' -or $_.CommandLine -like '*stream-json*') -and $_.CommandLine -notlike '*--remote-control*' })
    } catch { return $false }
}

function Get-AutopilotStatusLine {
    # Returns "#<n> <title>  -- building <Xm> (<phase>)" for the issue currently building,
    # or $null if nothing is building / the state file is stale (leaked by a crashed run).
    # Elapsed is computed from the file's LastWriteTime exactly like lock.ps1 -- NEVER via
    # [datetimeoffset]::Parse($state.ts), which throws (datetime minus datetimeoffset has no
    # op_Subtraction overload). Staleness mirrors lock.ps1: 3-min grace then require a live
    # autopilot claude; hard cap 3h.
    $statePath = Join-Path $AppDir 'var\autopilot\run-state.json'
    if (-not (Test-Path $statePath)) { return $null }
    try { $state = Get-Content $statePath -Raw | ConvertFrom-Json } catch { return $null }
    $age   = (Get-Date) - (Get-Item $statePath).LastWriteTime
    $stale = ($age.TotalHours -ge 3.0) -or ($age.TotalMinutes -ge 3 -and -not (Test-AutopilotClaudeAlive))
    if ($stale) { return $null }
    $mins  = [math]::Round($age.TotalMinutes)
    $title = if ($state.title) { $state.title } else { '(title unknown)' }
    return "#$($state.number) $title  -- building ${mins}m ($($state.phase))"
}
```

  Note on the test's behavioural assert (b): the synthetic fresh file's `LastWriteTime` is "now", well under the 3-min grace, so `Get-AutopilotStatusLine` returns the line even with no live claude -- this matches real behaviour at the very start of a run.

- [ ] **Wire the `status` arm.** Find it (anchor on the snippet) and append after the dev-server `if/else`:
```powershell
    'status' {
        $p = Find-AppProcess
        if ($p) {
            $envName = if (Test-Path $EnvStateFile) {
                (Get-Content $EnvStateFile -Raw).Trim()
            } else { '?' }
            Write-Ok "Running  (PID $($p.Id)  ·  env $envName  ·  port 8000)"
        } else {
            Write-Warn "Not running  — use -u / --up to start"
        }
        # Autopilot build status is independent of the dev server (a build can run while
        # nexora is down), so report it regardless of $p.
        $apLine = Get-AutopilotStatusLine
        if ($apLine) { Write-Info "autopilot: $apLine" }
    }
```
(`$AppDir` is the repo root inside `nx.ps1`, defined as `Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)`; `Write-Info`/`Write-Ok`/`Write-Warn` are the existing helpers.)

- [ ] **Run the test green:**
```
pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\nx-status.assert.ps1
```
Expect `ALL PASS`, exit 0.

- [ ] **Smoke: absent-file path** (no build running):
```
pwsh -NoProfile -File C:\dev\nexora\bin\nx.ps1 -s
```
Expect the normal `Running`/`Not running` line and NO `autopilot:` line.

- [ ] **Smoke: present (fresh) path.** Write a synthetic record at the real path, run status, then clean up:
```
pwsh -NoProfile -Command "$d='C:\dev\nexora\var\autopilot'; New-Item -ItemType Directory -Force $d | Out-Null; @{ ts=(Get-Date -Format o); phase='plan'; number=94; title='Clearer execution title name'; procId=$PID } | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $d 'run-state.json'); pwsh -NoProfile -File C:\dev\nexora\bin\nx.ps1 -s; Remove-Item (Join-Path $d 'run-state.json')"
```
Expect a line like `  →  autopilot: #94 Clearer execution title name  -- building 0m (plan)`.

- [ ] **Smoke: stale path.** Write a record then back-date its mtime 10 min; expect NO autopilot line:
```
pwsh -NoProfile -Command "$d='C:\dev\nexora\var\autopilot'; $f=Join-Path $d 'run-state.json'; @{ ts=(Get-Date -Format o); phase='execute'; number=94; title='x'; procId=1 } | ConvertTo-Json | Set-Content -Encoding utf8 $f; (Get-Item $f).LastWriteTime=(Get-Date).AddMinutes(-10); pwsh -NoProfile -File C:\dev\nexora\bin\nx.ps1 -s; Remove-Item $f"
```
Expect NO `autopilot:` line.

- [ ] **Re-run the full suite:**
```
pwsh -NoProfile -Command "Get-ChildItem C:\dev\nexora\tools\autopilot\tests\*.assert.ps1 | ForEach-Object { pwsh -NoProfile -File $_.FullName }"
```
Expect every file `ALL PASS`.

- [ ] **Commit:**
```
$env:SQL_SYNC_SKIP='1'
git add bin/nx.ps1 tools/autopilot/tests/nx-status.assert.ps1
git commit -F - <<'MSG'
feat(nx): show in-flight autopilot issue in nx status

nx status (alias nx -s) now also prints the autopilot issue currently
being built as "autopilot: #<n> <title> -- building <elapsed> (<phase>)",
read from var/autopilot/run-state.json. A new Get-AutopilotStatusLine
helper computes elapsed from the file's LastWriteTime (mirroring
lock.ps1, not [datetimeoffset]::Parse which throws) and reuses lock.ps1's
claude-liveness staleness rule, so a leaked state file never shows a
phantom build. Reported independently of the dev server, which can be
down while a build runs.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
MSG
$env:SQL_SYNC_SKIP=''
```

### Task 5: update the `-s`/`--status` help text + add a lock.ps1 cross-reference

**Files:**
- Modify: `C:\dev\nexora\bin\nx.ps1` (help text)
- Modify: `C:\dev\nexora\tools\autopilot\lock.ps1` (one comment line)

- [ ] **Help text.** In `nx.ps1` find the help line (anchor on the snippet) and clarify it:
```powershell
    Write-Host "    -s, --status          Show running status (PID, env, port) + in-flight autopilot issue"
```
(If the exact current wording differs, re-grep `--status` in the help block and append `+ in-flight autopilot issue` to whatever the current row says.)

- [ ] **lock.ps1 cross-reference.** So the duplicated staleness logic does not drift, add a one-line comment beside `lock.ps1`'s liveness probe (anchor on its `Where-Object { ($_.CommandLine -like '* -p *'`):
```powershell
      # NOTE: bin/nx.ps1 Get-AutopilotStatusLine duplicates this probe + the 3h/3-min staleness
      # rule for `nx status`. If you change the probe here, mirror it there.
```
(The nx.ps1 helper already carries the reciprocal comment, added in Task 4.)

- [ ] **Verify help renders:**
```
pwsh -NoProfile -File C:\dev\nexora\bin\nx.ps1 --help
```
Expect the `-s, --status` row to mention the autopilot issue.

- [ ] **Confirm lock.ps1 still parses:**
```
pwsh -NoProfile -Command "[System.Management.Automation.Language.Parser]::ParseFile('C:\dev\nexora\tools\autopilot\lock.ps1',[ref]$null,[ref]([System.Management.Automation.Language.ParseError[]]@())) | Out-Null; 'lock OK'"
```
Expect `lock OK`.

- [ ] **Commit:**
```
$env:SQL_SYNC_SKIP='1'
git add bin/nx.ps1 tools/autopilot/lock.ps1
git commit -F - <<'MSG'
docs(nx): note autopilot issue in -s/--status help; cross-ref lock probe

The -s/--status help row now mentions the in-flight autopilot issue, and
lock.ps1 gains a comment pointing at nx.ps1's duplicated liveness/
staleness logic so the two encodings stay in sync.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
MSG
$env:SQL_SYNC_SKIP=''
```

---

# PHASE 3: n8n run identification (surface B)

### Task 6: name `#<n> <title>` in all four per-item Telegram notifications

**Files:**
- Test (Create): `C:\dev\nexora\tools\autopilot\tests\notify-titles.assert.ps1`
- Modify: `C:\dev\nexora\tools\autopilot\n8n-autopilot.workflow.json`

Honest scope: ONE n8n execution loops the whole queue, so the *execution* cannot be named per issue. What we CAN do, with zero new n8n features, is make every per-item Telegram signal carry `#<n> <title>`. All four nodes already interpolate `.number`; we add `.title`. Each must keep the exact looped node name `Loop Over Items`.

- [ ] **Write the failing test.** Create `tools/autopilot/tests/notify-titles.assert.ps1`:
```powershell
#requires -Version 7
# Standalone assertion (no Pester). Exit 1 on any failure.
# Guards that every per-item Telegram notify node identifies the issue as "#<n> <title>"
# (one n8n execution loops many issues, so identification is per-ITEM, not per-execution).
$ErrorActionPreference = 'Stop'
$wfPath = Join-Path $PSScriptRoot '..\n8n-autopilot.workflow.json'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

$wf = $null; try { $wf = Get-Content $wfPath -Raw | ConvertFrom-Json } catch {}
Assert ($null -ne $wf) 'workflow JSON parses'

foreach ($name in @('notify-built','notify-recovered','notify-skip','notify-questions')) {
    $text = ($wf.nodes | Where-Object { $_.name -eq $name }).parameters.text
    Assert ($text -match "Loop Over Items'\)\.item\.json\.number") "$name still shows the issue number"
    Assert ($text -match "Loop Over Items'\)\.item\.json\.title")  "$name now also shows the issue title"
}

# No reference may strip the space out of the looped node name.
$raw = Get-Content $wfPath -Raw
Assert ($raw -notmatch "LoopOverItems'\)\.item") 'no broken (space-stripped) Loop Over Items reference'

if ($fail) { "`n$fail assertion(s) FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
```

- [ ] **Run it -- expect FAIL** (the four `... now also shows the issue title` asserts):
```
pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\notify-titles.assert.ps1
```

- [ ] **Implement.** In `n8n-autopilot.workflow.json`, edit each notify node's `text` (anchor on each exact current string). Add `{{ $('Loop Over Items').item.json.title }}` right after the number. Each value stays a single JSON line.

  `notify-built` -- from:
```json
        "text": "=✅ #{{ $('Loop Over Items').item.json.number }} built — commit pending push",
```
  to:
```json
        "text": "=✅ #{{ $('Loop Over Items').item.json.number }} {{ $('Loop Over Items').item.json.title }} built — commit pending push",
```

  `notify-recovered` -- from:
```json
        "text": "=🛠️ #{{ $('Loop Over Items').item.json.number }} recovered by autopilot — {{ (() => { try { const v = JSON.parse($('recover').item.json.stdout); return v.summary + (v.stashed ? ' ⚠ pre-existing WIP was stashed (git stash list / pop).' : ''); } catch (e) { return 'commit pending push'; } })() }}",
```
  to (insert the title after the number only):
```json
        "text": "=🛠️ #{{ $('Loop Over Items').item.json.number }} {{ $('Loop Over Items').item.json.title }} recovered by autopilot — {{ (() => { try { const v = JSON.parse($('recover').item.json.stdout); return v.summary + (v.stashed ? ' ⚠ pre-existing WIP was stashed (git stash list / pop).' : ''); } catch (e) { return 'commit pending push'; } })() }}",
```

  `notify-skip` -- from:
```json
        "text": "=⏭️ #{{ $('Loop Over Items').item.json.number }} skipped — {{ (() => { try { return JSON.parse($('recover').item.json.stdout).summary; } catch (e) { return 'blocked after recovery'; } })() }}",
```
  to:
```json
        "text": "=⏭️ #{{ $('Loop Over Items').item.json.number }} {{ $('Loop Over Items').item.json.title }} skipped — {{ (() => { try { return JSON.parse($('recover').item.json.stdout).summary; } catch (e) { return 'blocked after recovery'; } })() }}",
```

  `notify-questions` -- from:
```json
        "text": "=❓ #{{ $('Loop Over Items').item.json.number }} needs input — {{ (() => { try { return JSON.parse($('triage').item.json.stdout).questions; } catch (e) { return 'see the issue comment'; } })() }}",
```
  to:
```json
        "text": "=❓ #{{ $('Loop Over Items').item.json.number }} {{ $('Loop Over Items').item.json.title }} needs input — {{ (() => { try { return JSON.parse($('triage').item.json.stdout).questions; } catch (e) { return 'see the issue comment'; } })() }}",
```

- [ ] **Run green:**
```
pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\notify-titles.assert.ps1
```
Expect `ALL PASS`.

- [ ] **Confirm the workflow JSON still parses:**
```
pwsh -NoProfile -Command "Get-Content C:\dev\nexora\tools\autopilot\n8n-autopilot.workflow.json -Raw | ConvertFrom-Json | Out-Null; 'JSON OK'"
```
Expect `JSON OK`.

- [ ] **Re-run the full suite:**
```
pwsh -NoProfile -Command "Get-ChildItem C:\dev\nexora\tools\autopilot\tests\*.assert.ps1 | ForEach-Object { pwsh -NoProfile -File $_.FullName }"
```
Expect every file `ALL PASS`.

- [ ] **Commit:**
```
$env:SQL_SYNC_SKIP='1'
git add tools/autopilot/n8n-autopilot.workflow.json tools/autopilot/tests/notify-titles.assert.ps1
git commit -F - <<'MSG'
feat(autopilot): name issue title in all n8n Telegram notifications

The built/recovered/skipped/needs-input Telegram messages now read
"#<n> <title> ..." instead of just "#<n>", so it is clear which issue
each per-item notification refers to. One n8n execution loops the whole
queue (splitInBatches "Loop Over Items"), so these per-item
notifications -- not execution naming, which is Enterprise-gated -- are
the surface that identifies each issue. Owner must re-import the
workflow into live n8n.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
MSG
$env:SQL_SYNC_SKIP=''
```

---

# PHASE 4: docs + changelog

### Task 7: docs + changelog sync, with test-guarded README/SIGNALS

**Files:**
- Modify: `C:\dev\nexora\CHANGELOG.md`
- Modify: `C:\dev\nexora\docs\howto\nx.md`
- Modify: `C:\dev\nexora\tools\autopilot\README.md`
- Modify: `C:\dev\nexora\tools\autopilot\SIGNALS.md`
- Modify: `C:\dev\nexora\tools\autopilot\tests\readme-signals.assert.ps1` (add two guards for the new contract)

Note (red-team F5): the existing `readme-signals.assert.ps1` only greps fixed recovery-layer literals; it will NOT fail on a missing run-state row. So this task adds two cheap asserts to actually guard the new doc additions.

- [ ] **CHANGELOG.md.** Under `## [Unreleased]` -> `### Added` (re-grep for the exact heading; create the subhead if absent, matching the file's Keep-a-Changelog style), add:
```
- Autopilot/nx: `nx status` (alias `nx -s`) now also shows the issue an autopilot run is currently building as `#<n> <title>  -- building <elapsed> (<phase>)`, read from `var/autopilot/run-state.json` and suppressed when stale by the same liveness rule as the run lock. The four per-item n8n Telegram notifications (built, recovered, skipped, needs-input) now name the issue title alongside its number, and the execute-phase node now forwards the issue number (run.log header reads `execute #<n>` instead of `#0`).
```

- [ ] **docs/howto/nx.md.** Update the three status references (re-grep each snippet):
  - One-shot table row `| `-s`, `--status` | Show running status (PID, env, port) |` -> append `+ any in-flight autopilot build`.
  - Interactive REPL table row `| `status` | Show running status |` -> append `+ in-flight autopilot build`.
  - The prose `With no command, `nx` defaults to `--status`` -> add a sentence: "When an autopilot build is in progress, `status` also prints `autopilot: #<n> <title>  -- building <elapsed> (<phase>)`."

- [ ] **tools/autopilot/README.md.** In the "pieces" table, add a row for the run-state file (do NOT reword existing rows -- `readme-signals.assert.ps1` greps literals):
```
| `run-state.json` (var/autopilot/) | State file | Per-issue record (number, title, phase, ts) written by `run-phase.ps1` at phase start, cleared on n8n startup. `nx status` reads it to show what is building and for how long. |
```
  Add a short line near the existing `nx --workflow-logs` / monitoring docs: "`nx status` (or `nx -s`) shows the issue currently building as `#<n> <title>  -- building <elapsed>`; a leaked state file from a crashed run is suppressed by the same liveness check the lock uses."

- [ ] **tools/autopilot/SIGNALS.md.** Add a contract section:
```
### run-state.json (var/autopilot/run-state.json)

Written by run-phase.ps1 at phase start (plan records number+title; execute preserves them and
flips .phase); cleared on n8n startup by start-n8n.ps1. Consumed by `nx status`.

{ "ts": "<ISO8601>", "phase": "plan|execute", "number": <int>, "title": "<string>", "procId": <int> }

Readers MUST treat the record as stale (no build in progress) when its file LastWriteTime is older
than 3 min with no live autopilot claude.exe, or older than 3h outright -- mirroring lock.ps1.
```

- [ ] **Add two guards to `readme-signals.assert.ps1`** (anchor before its final `if ($fail)` / summary line; it uses an `Assert($label, $cond)` helper and the `$readme` / `$signals` raw strings):
```powershell
# run-state contract (clearer-execution-titles feature)
Assert "README pieces table has run-state.json" ($readme -match 'run-state\.json')
Assert "SIGNALS documents run-state.json"        ($signals -match 'run-state\.json')
```

- [ ] **Run the doc-sync guard green:**
```
pwsh -NoProfile -File C:\dev\nexora\tools\autopilot\tests\readme-signals.assert.ps1
```
Expect `ALL PASS` (its summary prints `PASS:`/`FAIL:` per line). If it fails on a pre-existing literal you did not touch, note it -- do not reword its existing targets.

- [ ] **Run the full suite one final time:**
```
pwsh -NoProfile -Command "Get-ChildItem C:\dev\nexora\tools\autopilot\tests\*.assert.ps1 | ForEach-Object { $_.Name; pwsh -NoProfile -File $_.FullName }"
```
Expect every file to end `ALL PASS` / exit 0.

- [ ] **Commit:**
```
$env:SQL_SYNC_SKIP='1'
git add CHANGELOG.md docs/howto/nx.md tools/autopilot/README.md tools/autopilot/SIGNALS.md tools/autopilot/tests/readme-signals.assert.ps1
git commit -F - <<'MSG'
docs(autopilot): document nx status build line + run-state contract

CHANGELOG [Unreleased], nx.md status rows, the autopilot README pieces
table, and SIGNALS.md gain the var/autopilot/run-state.json contract and
the new nx status "#<n> <title> -- building <elapsed>" line. The
readme-signals guard now asserts both docs mention run-state.json so the
contract stays documented.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
MSG
$env:SQL_SYNC_SKIP=''
```

---

## Gotchas & notes

- **Elapsed math MUST use file mtime, never `[datetimeoffset]::Parse`.** `Get-Date -Format o` yields an offset-bearing string; `(Get-Date) - [datetimeoffset]::Parse($s.ts)` THROWS (`op_Subtraction` has no datetime-minus-datetimeoffset overload) and would crash `nx status` the instant a real build runs. `lock.ps1` uses `(Get-Date) - (Get-Item $path).LastWriteTime`; the `nx status` helper does the same. `ts` is stored for display/debugging only. The Task 4 test invokes the helper against a synthetic file specifically to catch any regression here.
- **Run-state survives the plan->execute hand-off; it is NOT cleared per phase.** `run-plan` and `run-exec` are SEPARATE `executeCommand` processes. If `run-phase.ps1` deleted the file in a `finally`, the plan process would wipe the title before the execute process reads it -- `nx status` would then show `(title unknown)` during execute, defeating the feature. Clearing happens only at `start-n8n.ps1` startup (crash-leak cleanup).
- **`$issue` scope in run-phase.** `$issue` is defined only in the `plan` branch, and the prompt `if/else` block runs before the run.log header. The run-state block must sit AFTER both, and reference `$issue.title` only inside the `$Phase -eq 'plan'` arm. Re-grep to confirm ordering before editing.
- **Execute phase has no number/title of its own (today).** It preserves the plan-phase record. Task 2 additionally threads `-IssueNumber` so the execute run.log header and the execute-branch fallback `number` are correct even if the plan record were missing. If a future workflow ever runs `execute` without a preceding `plan` and with a cleared file, `nx status` shows `(title unknown)` -- acceptable under today's single-lock single-drain model.
- **Staleness parity with the lock is by-convention, not shared code.** `nx status` and `lock.ps1` independently encode the same 3h cap + 3-min-no-live-claude grace + the `* -p *`/`stream-json`/`--remote-control` probe. Task 5 adds reciprocal cross-reference comments in both files. If you change one, change both. (A shared probe module was considered and rejected for minimal-diff; red-team F7 accepts this as a YAGNI tradeoff.)
- **Final-stdout contract.** `run-phase.ps1`'s last stdout line is consumed by n8n (`Select-Object -Last 1`). The run-state write uses `Set-Content` to a FILE and happens before `claude` runs; never add a `Write-Host`/`Write-Output` after the result line.
- **Surface B is per-item, not per-execution.** One n8n execution loops many issues, so the execution itself cannot be named per issue. The four per-item Telegram nodes are the correct identity surface; do NOT add a Set/customData node to name the execution (Enterprise-gated/unverified and semantically wrong).
- **`comment-result.ps1` nodes carry no title.** Surface B enriches the Telegram *notify* nodes only; the GitHub `comment-result.ps1` calls already post to the right issue by number and need no change.
- **n8n is NOT auto-deployed.** Editing the workflow JSON in git does nothing to the running n8n until the owner re-imports it (Owner actions). `tools/` is `/XD`-excluded, so prod never sees it either way.
- **`var/` is gitignored** -- `run-state.json` itself is never committed; only the scripts that read/write it are. No `.gitignore` change.
- **Parallel-on-clones (future).** The designed-not-built "parallel-on-clones" roadmap would allow >1 concurrent build, making a single `run-state.json` insufficient (you'd need per-run-id records and `nx status` enumerating them). No action today since `lock.ps1` enforces single-run.
- **Commit hygiene.** Every `git commit` needs `$env:SQL_SYNC_SKIP='1'` set first and cleared after; never `--no-verify`. Stop at commit -- no push, no PR (remote-session policy).
