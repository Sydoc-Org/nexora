#requires -Version 7
<#
.SYNOPSIS
  Provision/tear down a concurrent autopilot lane: a git WORKTREE on a fresh auto/issue-NN branch.
  Owner override: WORKTREES not clones. The autopilot lane path NEVER triggers handoff --merge-worktree
  (run-phase sets AUTOPILOT_LANE=1 so /write-plan builds in place); merge-back is owned by merge-back.ps1.
  Emits ONE compact JSON line; exit 0; never throws.
.DESCRIPTION
  acquire -IssueNumber NN -> claim a semaphore slot, create the lane worktree on auto/issue-NN off
                             $Branch, emit {status:ACQUIRED, slot, worktree, branch, issue} | {FULL}.
  release -Slot K -IssueNumber NN -> ancestor-checked: if the lane HEAD did NOT land on $Branch, refuse
                             (=> {UNMERGED}, worktree kept for inspection, slot STILL freed); else
                             worktree remove + branch -D + slot release => {RELEASED}.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][ValidateSet('acquire','release')] [string]$Action,
  [int]$IssueNumber = 0,
  [int]$Slot = -1,
  [string]$BaseRepo = 'C:\dev\nexora',
  [string]$Branch = 'feature/2.5.63',
  [string]$SlotsDir = 'C:\dev\nexora\var\autopilot\slots',
  [int]$MaxSlots = 3
)
$ErrorActionPreference = 'Stop'
$env:SQL_SYNC_SKIP = '1'
Remove-Item Env:GH_TOKEN, Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
$sem = Join-Path $BaseRepo 'tools\autopilot\semaphore.ps1'
. (Join-Path $BaseRepo 'tools\autopilot\lane-paths.ps1')
try {
  switch ($Action) {
    'acquire' {
      $s = (& $sem -Action acquire -IssueNumber $IssueNumber -SlotsDir $SlotsDir -MaxSlots $MaxSlots | Select-Object -Last 1 | ConvertFrom-Json)
      if ($s.status -ne 'ACQUIRED') { @{ status = 'FULL' } | ConvertTo-Json -Compress; exit 0 }
      $lp = Get-LanePaths -Lane $s.slot -BaseRepo $BaseRepo -IssueNumber $IssueNumber
      New-Item -ItemType Directory -Force $lp.root | Out-Null
      if (Test-Path $lp.worktree) { git -C $BaseRepo worktree remove --force $lp.worktree 2>$null | Out-Null }
      git -C $BaseRepo worktree prune 2>$null | Out-Null
      git -C $BaseRepo branch -D $lp.branch 2>$null | Out-Null
      git -C $BaseRepo worktree add -b $lp.branch $lp.worktree $Branch 2>$null | Out-Null
      if (-not (Test-Path (Join-Path $lp.worktree '.git'))) { throw "worktree add failed for $($lp.worktree)" }
      @{ status = 'ACQUIRED'; slot = $s.slot; worktree = $lp.worktree; branch = $lp.branch; issue = $IssueNumber } | ConvertTo-Json -Compress
    }
    'release' {
      $lp = Get-LanePaths -Lane $Slot -BaseRepo $BaseRepo -IssueNumber $IssueNumber
      $unmerged = $false
      if (Test-Path $lp.worktree) {
        $wtHead = (git -C $lp.worktree rev-parse HEAD 2>$null)
        $featHead = (git -C $BaseRepo rev-parse $Branch 2>$null)
        if ($wtHead -and $featHead) {
          git -C $BaseRepo merge-base --is-ancestor $wtHead.Trim() $featHead.Trim() 2>$null
          if ($LASTEXITCODE -ne 0) { $unmerged = $true }
        }
      }
      if ($unmerged) {
        & $sem -Action release -Slot $Slot -SlotsDir $SlotsDir -MaxSlots $MaxSlots | Out-Null
        @{ status = 'UNMERGED'; slot = $Slot; worktree = $lp.worktree; branch = $lp.branch } | ConvertTo-Json -Compress
        exit 0
      }
      if (Test-Path $lp.worktree) { git -C $BaseRepo worktree remove --force $lp.worktree 2>$null | Out-Null }
      git -C $BaseRepo worktree prune 2>$null | Out-Null
      git -C $BaseRepo branch -D $lp.branch 2>$null | Out-Null
      & $sem -Action release -Slot $Slot -SlotsDir $SlotsDir -MaxSlots $MaxSlots | Out-Null
      @{ status = 'RELEASED'; slot = $Slot } | ConvertTo-Json -Compress
    }
  }
} catch {
  @{ status = 'ERROR'; reason = $_.Exception.Message } | ConvertTo-Json -Compress
  exit 0
}
