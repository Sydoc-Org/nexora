#requires -Version 7
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\fix-attempt.ps1'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'fix-attempt.ps1 parses'

# Off-allowlist author => refused verdict, exit 0, never launches claude.
$out = & $script -IssueNumber 91 -Model sonnet -Effort high -SinceSha 'HEAD' -AllowedAuthors @('nobody-xyz') 2>$null
Assert ($LASTEXITCODE -eq 0) 'exits 0 on refusal'
$j = $null; try { $j = $out | Select-Object -Last 1 | ConvertFrom-Json } catch {}
Assert ($null -ne $j) 'emits valid JSON verdict'
Assert ($j.ok -eq $false) 'refused verdict ok:false'
Assert ($j.PSObject.Properties.Name -contains 'costUsd') 'verdict carries costUsd'

if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
