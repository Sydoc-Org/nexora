#requires -Version 7
# Standalone assertion (no Pester). Exit 1 on any failure.
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\probe-infra.ps1'
$fail = 0
function Assert([bool]$cond, [string]$msg) {
  if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ }
}

# 1) Parse-check.
$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'probe-infra.ps1 parses with no errors'

# 2) One compact JSON line, exit 0, all four bool keys present. Force a guaranteed-unreachable
#    host/port so dbOk/netOk cannot hang the test (bounded TCP probe).
$out = & $script -DbServer 'INTSQL01.invalid.nonexistent' -N8nPort 59999 2>$null
Assert ($LASTEXITCODE -eq 0) 'exits 0'
Assert (@($out).Count -eq 1) 'emits exactly one stdout line'
$j = $null; try { $j = $out | ConvertFrom-Json } catch {}
Assert ($null -ne $j) 'stdout is valid JSON'
Assert ($j.PSObject.Properties.Name -contains 'dbOk')  'has dbOk'
Assert ($j.PSObject.Properties.Name -contains 'n8nOk') 'has n8nOk'
Assert ($j.PSObject.Properties.Name -contains 'ghOk')  'has ghOk'
Assert ($j.PSObject.Properties.Name -contains 'netOk') 'has netOk'
Assert ($j.dbOk -eq $false)  'unreachable DB host => dbOk false'
Assert ($j.n8nOk -eq $false) 'unreachable n8n port => n8nOk false'

if ($fail) { "`n$fail assertion(s) FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
