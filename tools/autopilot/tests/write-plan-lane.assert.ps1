#requires -Version 7
$ErrorActionPreference = 'Stop'
$doc = Join-Path $PSScriptRoot '..\..\..\.claude\commands\write-plan.md'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }
Assert (Test-Path $doc) 'write-plan.md found'
$raw = Get-Content $doc -Raw
Assert ($raw -match 'AUTOPILOT_LANE') 'write-plan documents the AUTOPILOT_LANE lane exception'
Assert ($raw -match 'do \*\*NOT\*\* create a nested worktree') 'lane exception says do not create nested worktree'
if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
