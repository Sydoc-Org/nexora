#requires -Version 7
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\triage.ps1'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }
$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'triage.ps1 parses'

# Graceful degradation: classifier skipped => builds as today (buildable true).
$o = & $script -IssueNumber 91 -SkipClassifier 2>$null | Select-Object -Last 1 | ConvertFrom-Json
Assert ($LASTEXITCODE -eq 0) 'exits 0'
Assert ($o.buildable -eq $true) 'skip-classifier => buildable true (graceful degradation)'
Assert ($o.PSObject.Properties.Name -contains 'questions') 'has questions field'
Assert ($o.PSObject.Properties.Name -contains 'costUsd') 'has costUsd'

# BUILDABLE token => buildable true.
$b = & $script -IssueNumber 91 -ClassifierText 'BUILDABLE' 2>$null | Select-Object -Last 1 | ConvertFrom-Json
Assert ($b.buildable -eq $true) 'BUILDABLE token => buildable true'

# QUESTIONS-FOR-OWNER token (with a newline in the questions) => buildable false + questions set.
# This is the case the broken comma-form regex would silently miss.
$qtext = "QUESTIONS-FOR-OWNER: 1. Which DB?`n2. Which locale?"
$q = & $script -IssueNumber 91 -ClassifierText $qtext 2>$null | Select-Object -Last 1 | ConvertFrom-Json
Assert ($q.buildable -eq $false) 'QUESTIONS token => buildable false'
Assert ($q.questions -match 'Which DB') 'questions captured (multiline via (?s))'

if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
