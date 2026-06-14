#requires -Version 7
<#
.SYNOPSIS
  Daily USD cost cap for unattended autopilot. `check` gates a run; `add` books a phase's spend.
.DESCRIPTION
  Each `claude -p` result envelope carries total_cost_usd. This guard keeps a per-day ledger
  (var/autopilot/cost-ledger.json = { "YYYY-MM-DD": <cumulative_usd> }) so an away-mode run can
  refuse to keep spending once a daily cap is hit. Emits ONE compact JSON line on stdout (the
  n8n IF contract); never throws.

  Cap source: -DailyCapUsd, else AUTOPILOT_DAILY_USD_CAP, else 25.

  Actions:
    check  -> { underBudget, spentToday, cap, date }. The n8n `cost-ok?` IF branches on
              underBudget; over budget => notify + halt the run (the queue resumes tomorrow).
    add    -> read the LAST `"type":"result"` line from var/autopilot/logs/run.log (the phase
              that just finished), add its total_cost_usd to today's ledger, emit the new total.
              Wire one `add` after run-plan and one after run-exec. No change to run-phase.ps1
              needed: run-phase tees every phase's full stream to run.log, so the last result
              line is always the most-recently-finished phase.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][ValidateSet('check', 'add')] [string]$Action,
  [double]$DailyCapUsd = 0,
  [string]$RepoPath = 'C:\dev\nexora',
  [string]$LedgerFile = 'C:\dev\nexora\var\autopilot\cost-ledger.json',
  [string]$RunLog = 'C:\dev\nexora\var\autopilot\logs\run.log'
)
$ErrorActionPreference = 'Stop'

if ($DailyCapUsd -le 0) {
  $envCap = $env:AUTOPILOT_DAILY_USD_CAP
  $DailyCapUsd = if ($envCap -and [double]::TryParse($envCap, [ref]([double]$null))) { [double]$envCap } else { 25 }
}
$today = [datetime]::Now.ToString('yyyy-MM-dd')

function Read-Ledger {
  if (Test-Path $LedgerFile) {
    try { return (Get-Content $LedgerFile -Raw | ConvertFrom-Json) } catch { return $null }
  }
  return $null
}
function Get-SpentToday($ledger) {
  if ($ledger -and ($ledger.PSObject.Properties.Name -contains $today)) { return [double]$ledger.$today }
  return 0.0
}

try {
  $ledger = Read-Ledger
  $spent = Get-SpentToday $ledger

  if ($Action -eq 'check') {
    $under = $spent -lt $DailyCapUsd
    [ordered]@{ underBudget = [bool]$under; spentToday = [math]::Round($spent, 4); cap = $DailyCapUsd; date = $today } | ConvertTo-Json -Compress
    exit 0
  }

  # add: pull the just-finished phase's cost from the last result line in run.log.
  $cost = 0.0
  if (Test-Path $RunLog) {
    $last = Get-Content $RunLog | Where-Object { $_ -match '"type":\s*"result"' } | Select-Object -Last 1
    if ($last) { try { $cost = [double]((($last | ConvertFrom-Json).total_cost_usd)) } catch { $cost = 0.0 } }
  }
  $newTotal = [math]::Round(($spent + $cost), 6)

  # Merge into a plain hashtable keyed by date so ConvertTo-Json round-trips cleanly.
  $map = @{}
  if ($ledger) { foreach ($p in $ledger.PSObject.Properties) { $map[$p.Name] = [double]$p.Value } }
  $map[$today] = $newTotal
  New-Item -ItemType Directory -Force (Split-Path $LedgerFile) | Out-Null
  $map | ConvertTo-Json -Compress | Set-Content -Encoding utf8 $LedgerFile

  [ordered]@{ action = 'add'; added = [math]::Round($cost, 6); spentToday = $newTotal; cap = $DailyCapUsd; date = $today } | ConvertTo-Json -Compress
}
catch {
  # Fail OPEN on check (don't wedge the queue on a ledger glitch), but report the error.
  [ordered]@{ underBudget = $true; action = $Action; error = "$($_.Exception.Message)"; cap = $DailyCapUsd; date = $today } | ConvertTo-Json -Compress
  exit 0
}
