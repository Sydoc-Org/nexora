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
