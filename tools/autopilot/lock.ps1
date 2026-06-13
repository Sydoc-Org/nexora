#requires -Version 7
<#
.SYNOPSIS
  Single-run lock for the autopilot loop. Emits {status:...} JSON on stdout.
.DESCRIPTION
  acquire -> ACQUIRED (lock written) or LOCKED (a fresh lock already held).
             A lock older than -MaxAgeHours is treated as stale (n8n crashed
             mid-run) and reclaimed.
  release -> RELEASED (lock removed; no-op if absent).
  check   -> {exists:bool}.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][ValidateSet('acquire','release','check')] [string]$Action,
  [string]$LockPath = 'C:\dev\nexora\var\autopilot.lock',
  # Hard staleness cap. A single queue item is now plan + execute + (on a halt) the opus FIXER -
  # up to ~3 heavy phases - so this must exceed the worst-case single-item wall time, otherwise a
  # legitimately long run gets its lock reclaimed mid-flight and the 2-min poll starts a SECOND,
  # concurrent build. Real crashes are still caught fast by the no-live-claude 3-min grace below;
  # this cap only governs the rare "claude looks alive but is wedged" case.
  [double]$MaxAgeHours = 3.0
)
$ErrorActionPreference = 'Stop'

switch ($Action) {
  'acquire' {
    if (Test-Path $LockPath) {
      $age = (Get-Date) - (Get-Item $LockPath).LastWriteTime
      # Is an autopilot run actually alive? Its claude runs with -p (plan/exec) or spawns
      # stream-json sub-agents. The interactive Claude Code session (--remote-control) is excluded.
      $running = $false
      try {
        $running = [bool](Get-CimInstance Win32_Process -Filter "Name='claude.exe'" -ErrorAction SilentlyContinue |
          Where-Object { ($_.CommandLine -like '* -p *' -or $_.CommandLine -like '*stream-json*') -and $_.CommandLine -notlike '*--remote-control*' })
      } catch {}
      # Self-heal: a crashed run leaks the lock. Treat it as stale if no autopilot claude is
      # alive (after a 3-min grace for brief inter-phase gaps), or past the hard age cap.
      $stale = ($age.TotalHours -ge $MaxAgeHours) -or ($age.TotalMinutes -ge 3 -and -not $running)
      if (-not $stale) {
        @{ status = 'LOCKED'; heldForMin = [math]::Round($age.TotalMinutes, 1); running = $running } | ConvertTo-Json -Compress
        return
      }
    }
    @{ ts = (Get-Date -Format o); procId = $PID } | ConvertTo-Json | Set-Content -Encoding utf8 $LockPath
    @{ status = 'ACQUIRED' } | ConvertTo-Json -Compress
  }
  'release' {
    Remove-Item $LockPath -ErrorAction SilentlyContinue
    @{ status = 'RELEASED' } | ConvertTo-Json -Compress
  }
  'check' {
    @{ exists = (Test-Path $LockPath) } | ConvertTo-Json -Compress
  }
}
