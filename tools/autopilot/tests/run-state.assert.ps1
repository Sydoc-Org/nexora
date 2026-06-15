#requires -Version 7
# Standalone assertion (no Pester). Exit 1 on any failure.
# Guards that run-phase.ps1 writes var/autopilot/run-state.json with the building issue
# (number+title+ts+phase) and -- crucially -- PRESERVES number/title in the execute phase
# (which has no title of its own) instead of blanking or deleting them.
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\run-phase.ps1'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

# 1) parse-clean guard (ALWAYS first)
$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'run-phase.ps1 parses'

$src = Get-Content $script -Raw

# 2) writes a run-state record carrying number+title+ts+phase
Assert ($src -match 'run-state\.json')                       'references run-state.json'
Assert ($src -match 'ts\s*=\s*\(Get-Date -Format o\)')      'run-state carries ISO ts'
Assert ($src -match 'number\s*=\s*\$IssueNumber')           'run-state carries issue number'
Assert ($src -match 'title\s*=')                            'run-state carries title'
Assert ($src -match 'phase\s*=\s*\$Phase')                 'run-state carries phase'
Assert ($src -match 'ConvertTo-Json')                       'serialises run-state to JSON'

# 3) execute branch must PRESERVE an existing record (number/title), not blank/delete it.
Assert ($src -match 'Test-Path \$statePath')               'execute reuses existing state when present'
# 4) run-phase must NOT delete run-state on exit (that would lose the title before execute reads it).
Assert ($src -notmatch 'Remove-Item.*run-state')           'run-phase does NOT delete run-state (cleared at lifecycle boundary, not per phase)'

if ($fail) { "`n$fail assertion(s) FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
