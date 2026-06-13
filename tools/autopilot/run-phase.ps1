#requires -Version 7
<#
.SYNOPSIS
  Run ONE headless Claude phase (plan or execute) for an autopilot issue.
.DESCRIPTION
  A clean command-adapter so the n8n node only passes scalars (issue number, model)
  and never has to embed multi-line issue bodies in JSON. Sets SQL_SYNC_SKIP=1 (scoped
  to this process), runs from the repo root, and passes Claude's --output-format json
  envelope straight through on stdout for the n8n node to capture.

  This is NOT the loop brain: it runs a single phase. The canvas decides when to call
  plan vs execute, when to verify, and when to halt.
.PARAMETER Phase
  'plan'    -> /write-plan with the issue title+body (requires -IssueNumber).
  'execute' -> /execute-plan (reads var/handoff-pending written by the plan phase).
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][ValidateSet('plan','execute')] [string]$Phase,
  [int]$IssueNumber = 0,
  [string]$Model = '',
  [string]$Repo = 'Sydoc-Code/nexora',
  [string]$RepoPath = 'C:\dev\nexora'
)
$ErrorActionPreference = 'Stop'

Set-Location $RepoPath
$env:SQL_SYNC_SKIP = '1'   # scoped to this child process; never leaks to the user's shell

if (-not $Model) { $Model = if ($Phase -eq 'plan') { 'fable' } else { 'sonnet' } }

$claudeArgs = @('-p', '--model', $Model, '--dangerously-skip-permissions', '--output-format', 'json')

if ($Phase -eq 'plan') {
  if ($IssueNumber -le 0) { throw 'run-phase.ps1 -Phase plan requires -IssueNumber' }
  $issue  = gh issue view $IssueNumber --repo $Repo --json title,body | ConvertFrom-Json
  $prompt = "/write-plan $($issue.title)`n`n$($issue.body)"
  $claudeArgs += @('--effort', 'high')
}
else {
  $prompt = '/execute-plan'
}

# Prompt via stdin so multi-line issue bodies never break argument quoting.
$prompt | claude @claudeArgs
