#requires -Version 7
# Standalone assertion (no Pester). Exit 1 on any failure.
# Guards that start-n8n.ps1 clears a leaked run-state.json on a fresh start,
# the same way it already clears a leftover lock.
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\start-n8n.ps1'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'start-n8n.ps1 parses'

$src = Get-Content $script -Raw
Assert ($src -match 'run-state\.json')                'start-n8n references run-state.json'
Assert ($src -match 'Remove-Item \$state')            'start-n8n removes a leaked run-state file'

if ($fail) { "`n$fail assertion(s) FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
