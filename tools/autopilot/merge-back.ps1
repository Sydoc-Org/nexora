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
