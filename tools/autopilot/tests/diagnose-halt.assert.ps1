#requires -Version 7
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\diagnose-halt.ps1'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'diagnose-halt.ps1 parses'

# Infra-down deterministic guard short-circuits BEFORE any classifier call.
$out = & $script -IssueNumber 91 -DbServer 'INTSQL01.invalid.nonexistent' -N8nPort 59999 -SkipClassifier 2>$null
Assert ($LASTEXITCODE -eq 0) 'exits 0'
$j = $null; try { $j = $out | Select-Object -Last 1 | ConvertFrom-Json } catch {}
Assert ($null -ne $j) 'emits valid JSON'
$enum = @('mechanical','test-gate','plan-ok-execute-failed','infra','genuine-blocker')
Assert ($enum -contains $j.class) "class in closed enum (got '$($j.class)')"
Assert ($j.PSObject.Properties.Name -contains 'summary') 'has summary'
Assert ($j.PSObject.Properties.Name -contains 'suggestedFix') 'has suggestedFix'
Assert ($j.PSObject.Properties.Name -notcontains 'poison') 'does NOT emit poison'

if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
