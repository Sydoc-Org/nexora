#requires -Version 7
<#
.SYNOPSIS
  Shared DB lock so the DB-touching build/test step runs SERIAL across lanes (parallel /execute-plan
  runs share INT/TEST and stomp NEXORA_TEST state). acquire BLOCKS up to -TimeoutSec so a lane waits
  its turn. Emits ONE compact JSON line; exit 0; never throws.
.DESCRIPTION
  acquire -> {status:ACQUIRED} or {status:TIMEOUT} after waiting -TimeoutSec.
  release -> {status:RELEASED}. A lock older than -MaxAgeHours is reclaimed (a crashed test run must
  not wedge all lanes); -MaxAgeHours must exceed worst-case e2e wall time.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][ValidateSet('acquire','release')] [string]$Action,
  [string]$LockPath = 'C:\dev\nexora\var\autopilot\db.lock',
  [int]$TimeoutSec = 1800,
  [double]$MaxAgeHours = 2.0
)
$ErrorActionPreference = 'Stop'
try {
  New-Item -ItemType Directory -Force (Split-Path $LockPath) | Out-Null
  switch ($Action) {
    'acquire' {
      $deadline = (Get-Date).AddSeconds($TimeoutSec)
      do {
        if (Test-Path $LockPath) {
          $age = (Get-Date) - (Get-Item $LockPath).LastWriteTime
          if ($age.TotalHours -ge $MaxAgeHours) { Remove-Item $LockPath -ErrorAction SilentlyContinue }
        }
        if (-not (Test-Path $LockPath)) {
          try {
            $fs = [System.IO.File]::Open($LockPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
            try {
              $bytes = [System.Text.Encoding]::UTF8.GetBytes((@{ ts = (Get-Date -Format o); procId = $PID } | ConvertTo-Json -Compress))
              $fs.Write($bytes, 0, $bytes.Length)
            } finally { $fs.Dispose() }
            @{ status = 'ACQUIRED' } | ConvertTo-Json -Compress; exit 0
          } catch { }
        }
        Start-Sleep -Milliseconds 500
      } while ((Get-Date) -lt $deadline)
      @{ status = 'TIMEOUT' } | ConvertTo-Json -Compress
    }
    'release' {
      Remove-Item $LockPath -ErrorAction SilentlyContinue
      @{ status = 'RELEASED' } | ConvertTo-Json -Compress
    }
  }
} catch {
  @{ status = 'ERROR'; reason = $_.Exception.Message } | ConvertTo-Json -Compress
  exit 0
}
