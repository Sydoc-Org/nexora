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
