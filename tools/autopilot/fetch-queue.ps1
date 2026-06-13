#requires -Version 7
<#
.SYNOPSIS
  Emit the autopilot work queue as a JSON array of {number, title}, oldest first.
.DESCRIPTION
  Open issues labelled `autopilot`, MINUS any also carrying `autopilot-built` or
  `autopilot-blocked` (already done / already halted). The n8n parse node consumes stdout.
#>
[CmdletBinding()]
param(
  [string]$Repo = 'Sydoc-Code/nexora'
)
$ErrorActionPreference = 'Stop'

$jq = '[.[] | select((.labels|map(.name)) as $l | (($l|index("autopilot-built"))|not) and (($l|index("autopilot-blocked"))|not))] | sort_by(.number) | [.[] | {number, title}]'

gh issue list --repo $Repo --label autopilot --state open --json number,title,labels --jq $jq
