#requires -Version 7
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\run-phase.ps1'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }
$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'run-phase.ps1 parses'
$raw = Get-Content $script -Raw
Assert ($raw -match '\[string\]\$LogPath')   'run-phase exposes -LogPath'
Assert ($raw -match '\[string\]\$StatePath') 'run-phase exposes -StatePath'
Assert ($raw -match '\[switch\]\$Lane')      'run-phase exposes -Lane'
Assert ($raw -match 'AUTOPILOT_LANE')        'run-phase sets AUTOPILOT_LANE in lane mode'
Assert ($raw -match 'if \(\$LogPath\)')      'run.log uses -LogPath when supplied'
Assert ($raw -match 'if \(\$StatePath\)')    'run-state uses -StatePath when supplied'
if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
