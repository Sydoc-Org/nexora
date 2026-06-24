#requires -Version 7
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\comment-result.ps1'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'comment-result.ps1 parses'

$o = & $script -IssueNumber 91 -Status blocked -Class 'test-gate' -Detail 'pytest X; tried i18n recompile' -DryRun | ConvertFrom-Json
Assert ($o.status -eq 'blocked') 'blocked status round-trips'
Assert ($o.reason -match 'test-gate') 'reason names the class'
Assert ($o.reason -match 'tried i18n recompile') 'reason names what was tried'

$n = & $script -IssueNumber 91 -Status needs-input -Detail '1. Which DB?' -DryRun | ConvertFrom-Json
Assert ($n.status -eq 'needs-input') 'needs-input status accepted'

if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
