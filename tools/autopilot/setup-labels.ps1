#requires -Version 7
<#
.SYNOPSIS
  Create the four GitHub labels the n8n autopilot loop depends on.
.DESCRIPTION
  Idempotent (--force updates if they already exist). Run once during setup.
#>
[CmdletBinding()]
param(
  [string]$Repo = 'Sydoc-Code/nexora'
)
$ErrorActionPreference = 'Stop'

gh label create autopilot         --repo $Repo --color '1d76db' --description 'Build this issue unattended via n8n autopilot'          --force
gh label create autopilot-built   --repo $Repo --color '0e8a16' --description 'Autopilot built it locally; commit pending owner push' --force
gh label create autopilot-blocked     --repo $Repo --color 'b60205' --description 'Autopilot halted on this issue; needs a human'          --force
gh label create autopilot-needs-input --repo $Repo --color 'fbca04' --description 'Autopilot needs the owner to clarify before building' --force

Write-Host '--- autopilot labels now on' $Repo '---'
gh label list --repo $Repo | Select-String 'autopilot'
