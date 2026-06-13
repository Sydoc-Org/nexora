#requires -Version 7
<#
.SYNOPSIS
  Emit the autopilot work queue as a JSON array of {number, title}, oldest first.
.DESCRIPTION
  Open issues labelled `autopilot`, MINUS any also carrying `autopilot-built` or
  `autopilot-blocked`, AND restricted to TRUSTED AUTHORS.

  SECURITY: the issue body is fed to a permission-skipped headless agent on a host with
  git/gh/DB access, so an untrusted issue is a prompt-injection vector. Only issues whose
  author is allowlisted are ever queued. Default allowlist = 'benstreich'; override with
  -AllowedAuthors or the AUTOPILOT_ALLOWED_AUTHORS env var (comma/space separated).
#>
[CmdletBinding()]
param(
  [string]$Repo = 'Sydoc-Code/nexora',
  [string[]]$AllowedAuthors = @()
)
$ErrorActionPreference = 'Stop'

if (-not $AllowedAuthors -or $AllowedAuthors.Count -eq 0) {
  $envAuthors = $env:AUTOPILOT_ALLOWED_AUTHORS
  $AllowedAuthors = if ($envAuthors) { $envAuthors -split '[,; ]+' | Where-Object { $_ } } else { @('benstreich') }
}

$raw = gh issue list --repo $Repo --label autopilot --state open --json number,title,author,labels | ConvertFrom-Json

$queue = @(
  $raw | Where-Object {
    $names = @($_.labels.name)
    ($names -notcontains 'autopilot-built') -and
    ($names -notcontains 'autopilot-blocked') -and
    ($AllowedAuthors -contains $_.author.login)
  } | Sort-Object number | ForEach-Object {
    [pscustomobject]@{ number = $_.number; title = $_.title }
  }
)

if ($queue.Count -eq 0) { '[]' } else { $queue | ConvertTo-Json -AsArray -Compress }
