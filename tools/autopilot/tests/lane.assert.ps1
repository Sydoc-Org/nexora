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
