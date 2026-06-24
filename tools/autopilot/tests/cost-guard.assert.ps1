#requires -Version 7
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\cost-guard.ps1'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'cost-guard.ps1 parses'

$tmp = Join-Path ([IO.Path]::GetTempPath()) ("cg-" + [guid]::NewGuid().ToString('N') + ".json")
try {
  # Booking an explicit -Cost must add exactly that amount, ignoring run.log entirely.
  $o1 = & $script -Action add -Cost 1.25 -LedgerFile $tmp -RunLog 'C:\does\not\exist.log' | ConvertFrom-Json
  Assert ([math]::Abs($o1.spentToday - 1.25) -lt 1e-6) 'first -Cost books 1.25'
  $o2 = & $script -Action add -Cost 0.75 -LedgerFile $tmp | ConvertFrom-Json
  Assert ([math]::Abs($o2.spentToday - 2.00) -lt 1e-6) 'second -Cost accumulates to 2.00'
  $c = & $script -Action check -LedgerFile $tmp -DailyCapUsd 5 | ConvertFrom-Json
  Assert ($c.underBudget -eq $true) 'check underBudget true at 2.00/5'
} finally { Remove-Item $tmp -ErrorAction SilentlyContinue }

if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
