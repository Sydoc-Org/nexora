#requires -Version 7
<#
.SYNOPSIS
  Per-lane path layout for concurrent autopilot lanes. Dot-source this; it defines functions only and
  emits nothing. Single source of truth so every lane-aware script derives identical paths.
.DESCRIPTION
  STATE (log/run-state/baseline) lives under the BASE repo var/autopilot/lanes/lane-K/ (gitignored,
  exists on the base, survives across phases). The WORKTREE lives OUTSIDE the repo at
  <BaseRepo>-lanes\lane-K (derived from BaseRepo, never hardcoded) so it is never robocopied/tracked.
#>
function Get-LanePaths {
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)][int]$Lane,
    [string]$BaseRepo = 'C:\dev\nexora',
    [int]$IssueNumber = 0
  )
  $lanesState = [IO.Path]::Combine($BaseRepo, "var\autopilot\lanes\lane-$Lane")
  $worktree   = "$BaseRepo-lanes\lane-$Lane"
  [pscustomobject]@{
    lane     = $Lane
    root     = $lanesState
    worktree = $worktree
    branch   = "auto/issue-$IssueNumber"
    log      = [IO.Path]::Combine($lanesState, 'run.log')
    runState = [IO.Path]::Combine($lanesState, 'run-state.json')
    baseline = [IO.Path]::Combine($lanesState, 'run-baseline.json')
    attempts = [IO.Path]::Combine($BaseRepo,   'var\autopilot\attempts.json')
  }
}
function Get-AllLaneRoots {
  [CmdletBinding()]
  param([string]$BaseRepo = 'C:\dev\nexora', [int]$MaxSlots = 3)
  0..($MaxSlots - 1) | ForEach-Object { Get-LanePaths -Lane $_ -BaseRepo $BaseRepo }
}
