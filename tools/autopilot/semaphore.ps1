#requires -Version 7
<#
.SYNOPSIS
  N-slot semaphore for concurrent autopilot lanes. Replaces lock.ps1's global single-run lock.
  Emits ONE compact JSON line; exit 0; never throws.
.DESCRIPTION
  acquire -IssueNumber NN -> {status:ACQUIRED, slot:K} (lowest free slot, claimed ATOMICALLY for NN)
                             or {status:FULL} when all MaxSlots are held & fresh (excess queues).
  release -Slot K          -> {status:RELEASED} (no-op if absent).
  check                    -> {slots:[{slot,issue,heldForMin}], free:M}.
  Each slot is a file var/autopilot/slots/lane-K.lock holding {ts, procId, issue}. The claim uses
  [IO.File]::Open(path, CreateNew) so two processes cannot both win slot K (no Test-Path TOCTOU).
  A slot is stale (reclaimable) past -MaxAgeHours, or after a 3-min grace if NO live process carries
  its procId. Staleness keys on the STORED procId, not a host-wide claude probe (3 concurrent claudes
  make the aggregate probe useless).
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][ValidateSet('acquire','release','check')] [string]$Action,
  [int]$IssueNumber = 0,
  [int]$Slot = -1,
  [string]$SlotsDir = 'C:\dev\nexora\var\autopilot\slots',
  [int]$MaxSlots = 3,
  [double]$MaxAgeHours = 3.0
)
$ErrorActionPreference = 'Stop'
try {
  New-Item -ItemType Directory -Force $SlotsDir | Out-Null
  function Slot-Path([int]$k) { Join-Path $SlotsDir ("lane-$k.lock") }
  function Read-Slot([int]$k) {
    $p = Slot-Path $k
    if (-not (Test-Path $p)) { return $null }
    try {
      $o = Get-Content $p -Raw | ConvertFrom-Json
      $o | Add-Member -NotePropertyName _age -NotePropertyValue ((Get-Date) - (Get-Item $p).LastWriteTime) -Force
      return $o
    } catch { return $null }
  }
  function Is-Stale($s) {
    if ($null -eq $s) { return $true }
    if ($s._age.TotalHours -ge $MaxAgeHours) { return $true }
    $alive = [bool](Get-Process -Id ([int]$s.procId) -ErrorAction SilentlyContinue)
    return ($s._age.TotalMinutes -ge 3 -and -not $alive)
  }
  function Try-Claim([int]$k) {
    # Atomic create-new; returns $true only if THIS process created the file.
    $p = Slot-Path $k
    try {
      $fs = [System.IO.File]::Open($p, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
      try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes((@{ ts = (Get-Date -Format o); procId = $PID; issue = $IssueNumber } | ConvertTo-Json -Compress))
        $fs.Write($bytes, 0, $bytes.Length)
      } finally { $fs.Dispose() }
      return $true
    } catch { return $false }
  }
  switch ($Action) {
    'acquire' {
      for ($k = 0; $k -lt $MaxSlots; $k++) {
        $s = Read-Slot $k
        if ($null -eq $s) {
          if (Try-Claim $k) { @{ status = 'ACQUIRED'; slot = $k } | ConvertTo-Json -Compress; exit 0 }
        } elseif (Is-Stale $s) {
          Remove-Item (Slot-Path $k) -ErrorAction SilentlyContinue
          if (Try-Claim $k) { @{ status = 'ACQUIRED'; slot = $k } | ConvertTo-Json -Compress; exit 0 }
        }
      }
      @{ status = 'FULL' } | ConvertTo-Json -Compress
    }
    'release' {
      if ($Slot -ge 0) { Remove-Item (Slot-Path $Slot) -ErrorAction SilentlyContinue }
      @{ status = 'RELEASED'; slot = $Slot } | ConvertTo-Json -Compress
    }
    'check' {
      $out = @(); $free = 0
      for ($k = 0; $k -lt $MaxSlots; $k++) {
        $s = Read-Slot $k
        if ($null -eq $s -or (Is-Stale $s)) { $free++ }
        else { $out += [ordered]@{ slot = $k; issue = [int]$s.issue; heldForMin = [math]::Round($s._age.TotalMinutes, 1) } }
      }
      @{ slots = $out; free = $free } | ConvertTo-Json -Compress -Depth 5
    }
  }
} catch {
  @{ status = 'ERROR'; reason = $_.Exception.Message } | ConvertTo-Json -Compress
  exit 0
}
