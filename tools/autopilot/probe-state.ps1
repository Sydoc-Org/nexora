#requires -Version 7
<#
.SYNOPSIS
  Decide whether a headless /write-plan or /execute-plan phase actually succeeded,
  by inspecting what changed SINCE the pre-plan baseline (NOT global state, NOT the
  claude exit code). Emits one compact JSON object on stdout.
.DESCRIPTION
  A claude -p run that STOPS on "2x BLOCKED" still reports subtype:success, so the
  envelope alone cannot tell success from blocked. This probe is the source of truth
  the n8n IF nodes branch on.

  Baseline (from baseline.ps1) supplies the pre-plan worktree set and a timestamp, so
  pre-existing plan-* worktrees and old handoff docs do NOT cause false halts.
.PARAMETER Phase
  'plan'    -> expect a commit, a plan md, and var/handoff-pending all fresh-since-baseline.
  'execute' -> expect a feature commit, the run's plan-* worktree merged away, and no
               BLOCKED marker in any handoff written since baseline.
.PARAMETER BeforeSha
  plan:    HEAD before the plan phase (baseline.sha).
  execute: HEAD after the plan phase (the plan verifier's headSha) so only execute's
           own commits count.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][ValidateSet('plan','execute')] [string]$Phase,
  [Parameter(Mandatory)][string]$BeforeSha,
  [string]$RepoPath     = 'C:\dev\nexora',
  [string]$BaselineFile = 'C:\dev\nexora\var\autopilot\run-baseline.json'
)
$ErrorActionPreference = 'Stop'

$baseline = if (Test-Path $BaselineFile) { Get-Content $BaselineFile -Raw | ConvertFrom-Json } else { $null }
$since    = if ($baseline) { [datetime]$baseline.sinceIso } else { (Get-Date).AddYears(-100) }
$head     = (git -C $RepoPath rev-parse HEAD).Trim()
$advanced = $head -ne $BeforeSha

if ($Phase -eq 'plan') {
  $handoff      = Join-Path $RepoPath 'var\handoff-pending'
  $handoffFresh = (Test-Path $handoff) -and ((Get-Item $handoff).LastWriteTime -gt $since)
  $plansDir     = Join-Path $RepoPath 'docs\superpowers\plans'
  $newestPlan   = Get-ChildItem $plansDir -Filter *.md -ErrorAction SilentlyContinue |
                  Sort-Object LastWriteTime | Select-Object -Last 1
  $planFresh    = $newestPlan -and ($newestPlan.LastWriteTime -gt $since)
  $out = [ordered]@{
    phase        = 'plan'
    headSha      = $head
    commitLanded = [bool]$advanced
    handoffFresh = [bool]$handoffFresh
    planFresh    = [bool]$planFresh
    ok           = ([bool]$advanced -and [bool]$handoffFresh -and [bool]$planFresh)
  }
}
else {
  $baseWts    = if ($baseline) { @($baseline.worktrees) } else { @() }
  $nowWts     = @((git -C $RepoPath worktree list) | ForEach-Object { ($_ -split '\s+')[0] })
  $newPlanWts = @($nowWts | Where-Object { $_ -match 'worktrees[\\/]+plan-' -and ($baseWts -notcontains $_) })
  $worktreeMerged = ($newPlanWts.Count -eq 0)

  # BLOCKED literals: only handoffs written SINCE baseline; refine \bBLOCKED\b|max_turns
  # against the real wording captured in tools/autopilot/SIGNALS.md after the first run.
  $handoffDir    = Join-Path $RepoPath 'docs\superpowers\handoffs'
  $freshHandoffs = Get-ChildItem $handoffDir -Filter *.md -ErrorAction SilentlyContinue |
                   Where-Object { $_.LastWriteTime -gt $since }
  $blocked = $false
  foreach ($f in $freshHandoffs) {
    if (Select-String -Path $f.FullName -Pattern '\bBLOCKED\b', 'max_turns' -ErrorAction SilentlyContinue) {
      $blocked = $true; break
    }
  }

  $out = [ordered]@{
    phase          = 'execute'
    headSha        = $head
    commitLanded   = [bool]$advanced
    worktreeMerged = [bool]$worktreeMerged
    newWorktrees   = $newPlanWts
    blocked        = [bool]$blocked
    ok             = ([bool]$advanced -and [bool]$worktreeMerged -and -not [bool]$blocked)
  }
}

$out | ConvertTo-Json -Compress
