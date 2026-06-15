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
