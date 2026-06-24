#requires -Version 7
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\start-n8n.ps1'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }
$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'start-n8n.ps1 parses'
$raw = Get-Content $script -Raw
Assert ($raw -match 'autopilot\\slots')           'clears slot files on startup'
Assert ($raw -match 'merge\.lock')                'clears the merge-lock on startup'
Assert ($raw -match 'db\.lock')                   'clears the db-lock on startup'
Assert ($raw -match 'lane-\\d\+')                 'prunes lane worktrees'
Assert ($raw -match 'merge-base --is-ancestor')   'lane-worktree prune is ancestor-checked'
if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
