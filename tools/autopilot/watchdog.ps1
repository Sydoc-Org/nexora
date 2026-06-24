#requires -Version 7
<#
.SYNOPSIS
  Keep n8n alive for unattended (away-mode) autopilot: if the editor port is down, relaunch it
  via start-n8n.ps1. Run once (for Task Scheduler) or as a foreground loop.
.DESCRIPTION
  n8n can die (OOM, a crashed long execution, a host hiccup). While it is down the 2-minute
  poll never fires and the queue stalls silently. This watchdog detects that and restarts n8n
  with the REQUIRED autopilot env (start-n8n.ps1 clears any leaked lock on boot).

  Modes:
    -IntervalSeconds 0   (default) single check + exit - wire to Task Scheduler every N minutes.
    -IntervalSeconds 120          loop forever, checking every 120s (a foreground watcher).

  Notifications are best-effort and OPTIONAL: if AUTOPILOT_TG_TOKEN + AUTOPILOT_TG_CHAT are set,
  a restart pings Telegram; otherwise it only logs (the n8n Telegram credential lives inside n8n
  and is not reachable from here).
.EXAMPLE
  .\watchdog.ps1
  .\watchdog.ps1 -IntervalSeconds 120

.NOTES
  A restart does NOT resume a crashed execution; lock.ps1's self-heal + start-n8n.ps1's
  boot-time lock clear handle the orphaned-run case. The watchdog only guarantees n8n is back
  up to poll again.
#>
[CmdletBinding()]
param(
  [int]$Port = 5678,
  [int]$IntervalSeconds = 0,
  [string]$RepoPath = 'C:\dev\nexora'
)
$ErrorActionPreference = 'Stop'

$logDir = Join-Path $RepoPath 'var\autopilot\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir 'watchdog.log'
$startScript = Join-Path $RepoPath 'tools\autopilot\start-n8n.ps1'

function Write-Log([string]$m) {
  "$([datetime]::Now.ToString('o'))  $m" | Add-Content -Path $log -Encoding utf8
}

function Test-N8nUp([int]$p) {
  try { return (Test-NetConnection -ComputerName 'localhost' -Port $p -InformationLevel Quiet -WarningAction SilentlyContinue) }
  catch { return $false }
}

function Send-Telegram([string]$text) {
  $token = $env:AUTOPILOT_TG_TOKEN; $chat = $env:AUTOPILOT_TG_CHAT
  if (-not $token -or -not $chat) { return }
  try {
    Invoke-RestMethod -Method Post -Uri "https://api.telegram.org/bot$token/sendMessage" `
      -Body @{ chat_id = $chat; text = $text } -TimeoutSec 15 | Out-Null
  } catch { Write-Log "telegram notify failed: $($_.Exception.Message)" }
}

function Test-AutopilotLanesActive([string]$repo) {
  # Returns $true when the semaphore has at least one held (non-stale) slot.
  # With 3 concurrent lanes, the host-wide claude probe is always true and useless; prefer slot-based.
  $semScript = Join-Path $repo 'tools\autopilot\semaphore.ps1'
  if (-not (Test-Path $semScript)) { return $false }
  try {
    $sm = (& $semScript -Action check 2>$null | Select-Object -Last 1 | ConvertFrom-Json)
    return ($sm -and ($sm.free -lt 3))
  } catch { return $false }
}

function Invoke-Check {
  if (Test-N8nUp $Port) { return }
  $lanesActive = Test-AutopilotLanesActive $RepoPath
  $laneNote = if ($lanesActive) { ' (active autopilot lanes detected - they will resume when n8n is back)' } else { '' }
  Write-Log "n8n DOWN on :$Port - restarting via start-n8n.ps1$laneNote"
  Send-Telegram "watchdog: n8n was down on :$Port - restarting.$laneNote"
  # Detached, hidden: start-n8n.ps1 runs `n8n start` (blocks), so it must own its own process.
  Start-Process -FilePath 'pwsh' `
    -ArgumentList @('-NoProfile', '-File', $startScript) `
    -WindowStyle Hidden | Out-Null
  Start-Sleep -Seconds 20
  if (Test-N8nUp $Port) { Write-Log 'n8n back up.'; Send-Telegram 'watchdog: n8n is back up.' }
  else { Write-Log 'n8n STILL down 20s after restart attempt.'; Send-Telegram 'watchdog: n8n still down after a restart attempt - check the host.' }
}

if ($IntervalSeconds -le 0) {
  Invoke-Check
} else {
  Write-Log "watchdog loop started (every ${IntervalSeconds}s, port $Port)"
  while ($true) {
    try { Invoke-Check } catch { Write-Log "check error: $($_.Exception.Message)" }
    Start-Sleep -Seconds $IntervalSeconds
  }
}
