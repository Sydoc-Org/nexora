#requires -Version 7
<#
.SYNOPSIS
  Deterministic, NO-LLM infra probe for the autopilot recovery layer. Emits one compact JSON
  line { dbOk, n8nOk, ghOk, netOk } and exits 0; never throws.
.DESCRIPTION
  Lets diagnose-halt.ps1 set class:infra and recover.ps1 set the poison infra term WITHOUT an
  LLM call. recover.ps1 re-runs this after each failed ladder attempt (infra can die mid-attempt
  and masquerade as a test-gate failure). Each TCP probe is bounded by -TimeoutSec via
  TcpClient.BeginConnect so a dead host cannot hang the node.
#>
[CmdletBinding()]
param(
  [string]$DbServer = 'INTSQL01',
  [int]$N8nPort     = 5678,
  [int]$TimeoutSec  = 5
)
$ErrorActionPreference = 'Stop'
$env:SQL_SYNC_SKIP = '1'
Remove-Item Env:GH_TOKEN, Env:GITHUB_TOKEN -ErrorAction SilentlyContinue

function Test-Port([string]$h, [int]$p, [int]$timeoutSec) {
  $client = $null
  try {
    $client = [System.Net.Sockets.TcpClient]::new()
    $iar = $client.BeginConnect($h, $p, $null, $null)
    if (-not $iar.AsyncWaitHandle.WaitOne([TimeSpan]::FromSeconds($timeoutSec))) { return $false }
    $client.EndConnect($iar)   # throws if the connect actually failed
    return $true
  } catch { return $false }
  finally { if ($client) { $client.Close() } }
}

try {
  # netOk: TCP path to the DB host's SQL port is reachable.
  $netOk = Test-Port $DbServer 1433 $TimeoutSec
  # dbOk: a real RO round-trip via sqlcmd if present, else fall back to the port check.
  $dbOk = $false
  if (Get-Command sqlcmd -ErrorAction SilentlyContinue) {
    try {
      $r = & sqlcmd -S $DbServer -d master -E -l $TimeoutSec -h -1 -W -Q 'SELECT 1' 2>$null
      $dbOk = ($LASTEXITCODE -eq 0) -and ("$r" -match '1')
    } catch { $dbOk = $false }
  } else { $dbOk = $netOk }
  # n8nOk: editor port listening locally.
  $n8nOk = Test-Port 'localhost' $N8nPort $TimeoutSec
  # ghOk: gh auth + api reachable (a transient gh/network outage => false, not a throw).
  $ghOk = $false
  try { & gh auth status 2>$null | Out-Null; $ghOk = ($LASTEXITCODE -eq 0) } catch { $ghOk = $false }

  [ordered]@{ dbOk = [bool]$dbOk; n8nOk = [bool]$n8nOk; ghOk = [bool]$ghOk; netOk = [bool]$netOk } |
    ConvertTo-Json -Compress
}
catch {
  # Fail-CLOSED: an internal error means we cannot confirm infra => all false (recover poisons).
  [ordered]@{ dbOk = $false; n8nOk = $false; ghOk = $false; netOk = $false; error = "$($_.Exception.Message)" } |
    ConvertTo-Json -Compress
  exit 0
}
