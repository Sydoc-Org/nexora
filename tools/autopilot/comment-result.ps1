#requires -Version 7
<#
.SYNOPSIS
  Report an autopilot outcome back to a GitHub issue (comment + label).
.DESCRIPTION
  built   -> comment the short commit sha + add label `autopilot-built`. The issue
             stays OPEN: per repo policy autopilot commits locally and never pushes,
             so the owner closes it after reviewing + pushing.
  blocked -> add label `autopilot-blocked` + comment the halt (optional -Reason).
  Emits a compact JSON result on stdout.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][int]$IssueNumber,
  [Parameter(Mandatory)][ValidateSet('built','blocked')] [string]$Status,
  [string]$Repo = 'Sydoc-Code/nexora',
  [string]$RepoPath = 'C:\dev\nexora',
  [string]$Reason = ''
)
$ErrorActionPreference = 'Stop'

if ($Status -eq 'built') {
  $sha = (git -C $RepoPath rev-parse --short HEAD).Trim()
  gh issue comment $IssueNumber --repo $Repo --body "Autopilot built this locally - commit $sha, pending owner review and push." | Out-Null
  gh issue edit    $IssueNumber --repo $Repo --add-label autopilot-built | Out-Null
  @{ status = 'built'; sha = $sha } | ConvertTo-Json -Compress
}
else {
  # Self-diagnose the halt reason if the caller didn't pass one, so the comment +
  # Telegram name the real cause instead of a generic "verification failed".
  if (-not $Reason) {
    $dirty = git -C $RepoPath status --porcelain
    if ($dirty) {
      $n = @($dirty -split "`r?`n" | Where-Object { $_ }).Count
      $Reason = "pre-flight: the working tree was not clean at start ($n uncommitted change(s)). Commit or stash your changes, then remove the autopilot-blocked label to re-queue."
    } else {
      $Reason = 'a plan or execute step did not pass verification (no committed result, or the worktree did not merge back).'
    }
  }
  gh issue edit $IssueNumber --repo $Repo --add-label autopilot-blocked | Out-Null
  $body = "Autopilot halted on this issue. Reason: $Reason"
  gh issue comment $IssueNumber --repo $Repo --body $body | Out-Null
  @{ status = 'blocked'; reason = $Reason } | ConvertTo-Json -Compress
}
