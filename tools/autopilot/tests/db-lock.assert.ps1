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
