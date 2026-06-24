#requires -Version 7
<#
.SYNOPSIS
  Escalation-ladder recovery orchestrator. REPLACES solve-blocked.ps1 as the canvas node. Emits
  ONE JSON line { action: built|skip|pause-run, class, summary, stashed, attempts } and exits 0;
  never throws. poison is computed DETERMINISTICALLY here (never from the LLM).
.DESCRIPTION
  Flow: author re-check -> capture diagnose-halt -> deterministic infra/poison gate (infra or
  poison => pause-run, livelock-guarded) -> ladder (MaxAttempts, sonnet then opus) via fix-attempt
  -> book each child's costUsd via cost-guard -Cost -> re-probe infra each attempt (on mid-attempt
  infra death, git reset --hard to the pre-attempt sha then pause-run) -> self-verify with
  -SinceSha (= -PlanHeadSha when a plan ran, else the per-issue baseline sha) -> success =>
  clean-tree guarantee + built. Ladder exhausted => deterministic poison ? pause-run : skip.
  Captures EVERY child invocation so no child JSON leaks; wraps every ConvertFrom-Json in a try
  with a fail-closed fallback (unparseable => skip, never built/pause). Before any continue verdict
  it leaves the tree clean (stash residual dirt) or poisons. A worktree is removed only after a
  git merge-base --is-ancestor check.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][int]$IssueNumber,
  [string]$PlanHeadSha = '',
  [int]$MaxAttempts = 2,
  [int]$LivelockMax = 3,
  [string]$Repo = 'Sydoc-Code/nexora',
  [string]$RepoPath = 'C:\dev\nexora',
  [string]$Branch = 'feature/2.5.63',
  [string]$DbServer = 'INTSQL01',
  [int]$N8nPort = 5678,
  [string]$LockPath = 'C:\dev\nexora\var\autopilot.lock',
  [int]$Slot = -1,
  [string]$SlotsDir = 'C:\dev\nexora\var\autopilot\slots',
  [string]$BaselineFile = 'C:\dev\nexora\var\autopilot\run-baseline.json',
  [string]$AttemptsLedger = 'C:\dev\nexora\var\autopilot\attempts.json',
  [string]$CostLedger = 'C:\dev\nexora\var\autopilot\cost-ledger.json',
  [string]$Playbook = 'C:\dev\nexora\tools\autopilot\RECOVERY-PLAYBOOK.md',
  # Test affordances (production canvas passes none of these):
  [string]$DiagnoseScript = 'C:\dev\nexora\tools\autopilot\diagnose-halt.ps1',
  [string]$FixScript = 'C:\dev\nexora\tools\autopilot\fix-attempt.ps1',
  [switch]$SkipDeterministicGates,
  [switch]$ForcePoison,
  [string[]]$AllowedAuthors = @()
)
$ErrorActionPreference = 'Stop'
if (-not $AllowedAuthors -or $AllowedAuthors.Count -eq 0) {
  $envAuthors = $env:AUTOPILOT_ALLOWED_AUTHORS
  $AllowedAuthors = if ($envAuthors) { $envAuthors -split '[,; ]+' | Where-Object { $_ } } else { @('benstreich') }
}
Set-Location $RepoPath
$env:SQL_SYNC_SKIP = '1'
Remove-Item Env:GH_TOKEN, Env:GITHUB_TOKEN -ErrorAction SilentlyContinue

$costGuard  = Join-Path $RepoPath 'tools\autopilot\cost-guard.ps1'
$probeInfra = Join-Path $RepoPath 'tools\autopilot\probe-infra.ps1'
$lockScript = Join-Path $RepoPath 'tools\autopilot\lock.ps1'

# ---- helpers (all fail-closed) ----
function ParseChild($raw, $fallback) {
  try { $j = ($raw | Select-Object -Last 1 | ConvertFrom-Json); if ($null -eq $j) { return $fallback }; return $j }
  catch { return $fallback }
}
function Read-AttemptLedger {
  if (Test-Path $AttemptsLedger) { try { $m=@{}; (Get-Content $AttemptsLedger -Raw|ConvertFrom-Json).PSObject.Properties|ForEach-Object{$m[$_.Name]=[int]$_.Value}; return $m } catch { return @{} } }
  return @{}
}
function Bump-AttemptLedger {
  $m = Read-AttemptLedger
  $k = "$IssueNumber"; $m[$k] = ([int]$m[$k]) + 1
  New-Item -ItemType Directory -Force (Split-Path $AttemptsLedger) | Out-Null
  $m | ConvertTo-Json -Compress | Set-Content -Encoding utf8 $AttemptsLedger
  return [int]$m[$k]
}
function Test-Poison {
  if ($ForcePoison) { return $true }
  if ($SkipDeterministicGates) { return $false }   # test affordance: suppress all poison terms
  # Default TRUE: downgrade only when ALL deterministic checks pass.
  if (git -C $RepoPath status --porcelain) { return $true }
  $head = (git -C $RepoPath rev-parse --abbrev-ref HEAD).Trim()
  if ($head -ne $Branch) { return $true }
  if (@(git -C $RepoPath ls-files -u).Count) { return $true }
  # leftover plan-* worktree whose HEAD is NOT an ancestor of branch HEAD.
  $branchHead = (git -C $RepoPath rev-parse HEAD).Trim()
  foreach ($wt in (git -C $RepoPath worktree list)) {
    if ($wt -match 'worktrees[\\/]+plan-' -or $wt -match '[\\/]lane-\d+\b') {
      $wtPath = ($wt -split '\s+')[0]
      $wtHead = (git -C $wtPath rev-parse HEAD 2>$null)
      if ($wtHead) { git -C $RepoPath merge-base --is-ancestor $wtHead.Trim() $branchHead 2>$null; if ($LASTEXITCODE -ne 0) { return $true } }
    }
  }
  $inf = ParseChild (& $probeInfra -DbServer $DbServer -N8nPort $N8nPort) $null
  if ($null -eq $inf -or -not ($inf.dbOk -and $inf.n8nOk -and $inf.ghOk -and $inf.netOk)) { return $true }
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
}
function Ensure-CleanTree {
  if (git -C $RepoPath status --porcelain) {
    git -C $RepoPath stash push -u -m "autopilot-recover: residual dirt before continue #$IssueNumber $(Get-Date -Format o)" | Out-Null
  }
  return (-not [bool](git -C $RepoPath status --porcelain))
}
function Pause-Or-Skip([string]$class, [string]$summary, [bool]$stashed, [int]$attempts) {
  # poison => pause-run, UNLESS this issue has hit pause too many times (livelock) => labelled skip.
  if (Test-Poison) {
    $count = Bump-AttemptLedger
    if ($count -gt $LivelockMax) {
      return [ordered]@{ action='skip'; class=$class; summary="livelock guard: $summary"; stashed=$stashed; attempts=$attempts }
    }
    return [ordered]@{ action='pause-run'; class=$class; summary=$summary; stashed=$stashed; attempts=$attempts }
  }
  [void](Ensure-CleanTree)
  return [ordered]@{ action='skip'; class=$class; summary=$summary; stashed=$stashed; attempts=$attempts }
}

$stashed = $false
try {
  # 1. Author re-check (a gh outage falls to the catch).
  $issue = gh issue view $IssueNumber --repo $Repo --json author | ConvertFrom-Json
  if ($AllowedAuthors -notcontains $issue.author.login) {
    [ordered]@{ action='skip'; class='genuine-blocker'; summary="author off allowlist"; stashed=$false; attempts=0 } | ConvertTo-Json -Compress
    exit 0
  }

  # 2. Diagnose (captured; never leaks to stdout).
  $laneRunLog = Join-Path (Split-Path $BaselineFile) 'run.log'
  $diag = ParseChild (& $DiagnoseScript -IssueNumber $IssueNumber -Repo $Repo -RepoPath $RepoPath -DbServer $DbServer -N8nPort $N8nPort -BaselineFile $BaselineFile -RunLog $laneRunLog) ([pscustomobject]@{ class='unknown'; summary='diagnose unparseable'; suggestedFix=''; costUsd=0 })
  if ($diag.costUsd) { & $costGuard -Action add -Cost ([double]$diag.costUsd) -LedgerFile $CostLedger | Out-Null }
  $class = $diag.class; $summary = $diag.summary

  # 3. Deterministic infra/poison gate (no fix spent on infra or poison).
  if ($class -eq 'infra' -or (Test-Poison)) {
    ((Pause-Or-Skip $class "$summary" $stashed 0) | ConvertTo-Json -Compress)
    exit 0
  }

  # 4. Ladder. -SinceSha anchor: the plan headSha when a plan ran, else the per-issue baseline sha.
  $sinceSha = if ($PlanHeadSha) { $PlanHeadSha } else { (git -C $RepoPath rev-parse HEAD).Trim() }
  if (-not $PlanHeadSha -and (Test-Path $BaselineFile)) { try { $sinceSha = (Get-Content $BaselineFile -Raw | ConvertFrom-Json).sha } catch {} }
  $models = @('sonnet','opus'); $extra = ''
  for ($i = 0; $i -lt $MaxAttempts; $i++) {
    $cost = ParseChild (& $costGuard -Action check -LedgerFile $CostLedger) ([pscustomobject]@{ underBudget=$true })
    if (-not $cost.underBudget) {
      ((Pause-Or-Skip 'genuine-blocker' "daily cost cap reached during recovery" $stashed $i) | ConvertTo-Json -Compress); exit 0
    }
    $model = $models[[math]::Min($i, $models.Count-1)]
    $preAttemptSha = (git -C $RepoPath rev-parse HEAD).Trim()   # for mid-attempt infra rollback
    $fix = ParseChild (& $FixScript -IssueNumber $IssueNumber -Model $model -Effort 'high' -SinceSha $sinceSha -Diagnosis "$summary" -ExtraContext $extra -Playbook $Playbook -Repo $Repo -RepoPath $RepoPath) $null
    if ($null -eq $fix) {
      # fail-closed: a child we cannot parse never counts as success.
      ((Pause-Or-Skip $class "$summary (unparseable fix verdict)" $stashed ($i+1)) | ConvertTo-Json -Compress); exit 0
    }
    if ($fix.stashed) { $stashed = $true }
    if ($fix.costUsd) { & $costGuard -Action add -Cost ([double]$fix.costUsd) -LedgerFile $CostLedger | Out-Null }
    # infra can die mid-attempt and look like a test-gate failure: re-probe; on death, roll the
    # tree back to the pre-attempt sha (don't blame the issue) then pause-run.
    if (-not $SkipDeterministicGates) {
      $inf = ParseChild (& $probeInfra -DbServer $DbServer -N8nPort $N8nPort) $null
      if ($null -eq $inf -or -not ($inf.dbOk -and $inf.n8nOk -and $inf.ghOk -and $inf.netOk)) {
        git -C $RepoPath reset --hard $preAttemptSha 2>$null | Out-Null
        git -C $RepoPath clean -fd 2>$null | Out-Null
        ((Pause-Or-Skip 'infra' "infra died mid-attempt; rolled back to $preAttemptSha" $stashed ($i+1)) | ConvertTo-Json -Compress); exit 0
      }
    }
    # A bare plan commit (HEAD == SinceSha) is NOT a feature commit, so fix.ok cannot be trusted
    # unless HEAD advanced past SinceSha OR the fixer corroborated ALREADY-DONE.
    $headNow = (git -C $RepoPath rev-parse HEAD).Trim()
    $featureCommit = ($headNow -ne $sinceSha)
    if ($fix.ok -and ($featureCommit -or $fix.alreadyDone)) {
      # deterministic poison must ALSO pass before declaring built.
      if (-not (Test-Poison)) {
        [void](Ensure-CleanTree)
        [ordered]@{ action='built'; class=$class; summary="$summary"; stashed=$stashed; attempts=($i+1) } | ConvertTo-Json -Compress
        exit 0
      }
      # built-but-poison: stop the run rather than corrupt the next issue.
      ((Pause-Or-Skip $class "fixer succeeded but tree is poison" $stashed ($i+1)) | ConvertTo-Json -Compress); exit 0
    }
    $extra = "Attempt $($i+1) ($model) failed: $($fix.reason)"
  }

  # 5. Exhausted.
  ((Pause-Or-Skip $class "$summary" $stashed $MaxAttempts) | ConvertTo-Json -Compress)
}
catch {
  # NEVER throw: emit a known-good action (the Switch fallback is belt-and-suspenders).
  $a = if ($ForcePoison) { 'pause-run' } else { 'skip' }
  [ordered]@{ action=$a; class='genuine-blocker'; summary="recover aborted: $($_.Exception.Message)"; stashed=[bool]$stashed; attempts=0 } | ConvertTo-Json -Compress
  exit 0
}
