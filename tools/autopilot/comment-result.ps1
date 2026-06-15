#requires -Version 7
<#
.SYNOPSIS
  Report an autopilot outcome back to a GitHub issue (comment + label).
.DESCRIPTION
  built       -> comment the short commit sha + add label `autopilot-built`. The issue
                 stays OPEN: per repo policy autopilot commits locally and never pushes,
                 so the owner closes it after reviewing + pushing.
  blocked     -> add label `autopilot-blocked` + comment the halt. -Class names the real
                 root cause and -Detail names what was tried (rich blocked reason).
  needs-input -> add label `autopilot-needs-input` + comment the owner questions (-Detail).
  -DryRun composes the body + emits the verdict WITHOUT touching GitHub (for offline tests).
  Emits a compact JSON result on stdout.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][int]$IssueNumber,
  [Parameter(Mandatory)][ValidateSet('built','blocked','needs-input')] [string]$Status,
  [string]$Repo = 'Sydoc-Code/nexora',
  [string]$RepoPath = 'C:\dev\nexora',
  [string]$Reason = '',
  [string]$Class = '',
  [string]$Detail = '',
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'

function Add-Label([string]$label) {
  if ($DryRun) { return }
  gh issue edit $IssueNumber --repo $Repo --add-label $label | Out-Null
}
function Comment([string]$body) {
  if ($DryRun) { return }
  # Post the autopilot's OWN comments as the dedicated bot account when AUTOPILOT_BOT_TOKEN is set, so
  # they are visibly distinct from your replies and a forged owner-clarification (posted by the bot) is
  # never trusted. The token is scoped to THIS call only (save/restore); labels, issue reads, commits,
  # and the owner's clarify-reply relay all keep the box's own (allowlisted) gh identity.
  if ($env:AUTOPILOT_BOT_TOKEN) {
    $prevToken = $env:GH_TOKEN
    $env:GH_TOKEN = $env:AUTOPILOT_BOT_TOKEN
    try     { gh issue comment $IssueNumber --repo $Repo --body $body | Out-Null }
    finally { $env:GH_TOKEN = $prevToken }
  } else {
    gh issue comment $IssueNumber --repo $Repo --body $body | Out-Null
  }
}

if ($Status -eq 'built') {
  $sha = (git -C $RepoPath rev-parse --short HEAD).Trim()
  Comment "Autopilot built this locally - commit $sha, pending owner review and push."
  Add-Label 'autopilot-built'
  @{ status = 'built'; sha = $sha } | ConvertTo-Json -Compress
}
elseif ($Status -eq 'needs-input') {
  $body = "Autopilot needs clarification before building this issue:`n`n$Detail`n`nReply to the Telegram question (or comment with an ``owner-clarification:`` prefix) and remove the ``autopilot-needs-input`` label to re-queue."
  Add-Label 'autopilot-needs-input'
  Comment $body
  @{ status = 'needs-input'; reason = $Detail } | ConvertTo-Json -Compress
}
else {
  # blocked: name the real root cause (Class) AND what was tried (Detail).
  if (-not $Reason) {
    $dirty = git -C $RepoPath status --porcelain
    if ($dirty) {
      $n = @($dirty -split "`r?`n" | Where-Object { $_ }).Count
      $Reason = "pre-flight: the working tree was not clean at start ($n uncommitted change(s))."
    } else {
      $Reason = 'a plan or execute step did not pass verification (no committed result, or the worktree did not merge back).'
    }
  }
  $classPart = if ($Class)  { " - $Class" } else { '' }
  $triedPart = if ($Detail) { "; tried: $Detail" } else { '' }
  $Reason = "blocked after recovery${classPart}: $Reason$triedPart"
  Add-Label 'autopilot-blocked'
  Comment "Autopilot halted on this issue. Reason: $Reason"
  @{ status = 'blocked'; reason = $Reason } | ConvertTo-Json -Compress
}
