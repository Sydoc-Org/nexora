#requires -Version 7
<#
.SYNOPSIS
  Snapshot repo state BEFORE an issue's plan phase, so probe-state.ps1 can judge
  only what THIS run changed (not pre-existing worktrees or old handoffs).
.DESCRIPTION
  Writes {sha, worktrees[], sinceIso} to a baseline file AND echoes it to stdout
  (n8n reads .sha for the plan verifier's -BeforeSha). Single-run lock guarantees
  one baseline at a time, so a shared file is safe.
#>
[CmdletBinding()]
param(
  [string]$RepoPath     = 'C:\dev\nexora',
  [string]$BaselineFile = 'C:\dev\nexora\var\autopilot\run-baseline.json'
)
$ErrorActionPreference = 'Stop'

New-Item -ItemType Directory -Force (Split-Path $BaselineFile) | Out-Null
$sha = (git -C $RepoPath rev-parse HEAD).Trim()
$wts = @((git -C $RepoPath worktree list) | ForEach-Object { ($_ -split '\s+')[0] })
$o   = [ordered]@{ sha = $sha; worktrees = $wts; sinceIso = (Get-Date -Format o) }

$o | ConvertTo-Json -Compress | Set-Content -Encoding utf8 $BaselineFile
$o | ConvertTo-Json -Compress
