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
  [int]$MaxAgeHours = 3
)
$ErrorActionPreference = 'Stop'

switch ($Action) {
  'acquire' {
    if (Test-Path $LockPath) {
      $age = (Get-Date) - (Get-Item $LockPath).LastWriteTime
      if ($age.TotalHours -lt $MaxAgeHours) {
        @{ status = 'LOCKED'; heldForHours = [math]::Round($age.TotalHours, 2) } | ConvertTo-Json -Compress
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
