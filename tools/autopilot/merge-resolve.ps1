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
