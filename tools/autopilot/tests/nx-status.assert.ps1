#requires -Version 7
# Standalone assertion (no Pester). Exit 1 on any failure.
# Behavioural test: extract the autopilot-status helpers out of nx.ps1 (without running its
# action switch) and invoke Get-AutopilotStatusLine against synthetic run-state files. Catches
# the [datetimeoffset]::Parse runtime crash that a source-grep test would miss.
$ErrorActionPreference = 'Stop'
$nx = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\bin\nx.ps1')).Path
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

# 1) parse-clean guard
$errs = @()
$ast = [System.Management.Automation.Language.Parser]::ParseFile($nx, [ref]$null, [ref]$errs)
Assert ($errs.Count -eq 0) 'nx.ps1 parses'

# 2) source-text contracts (cheap structural guards)
$src = Get-Content $nx -Raw
Assert ($src -match 'function Get-AutopilotStatusLine') 'defines Get-AutopilotStatusLine'
Assert ($src -match 'run-state\.json')                 'reads run-state.json'
Assert ($src -match 'LastWriteTime')                   'computes elapsed from file LastWriteTime (lock.ps1 idiom, not datetimeoffset)'
Assert ($src -notmatch '\[datetimeoffset\]::Parse')    'does NOT use [datetimeoffset]::Parse (would throw at runtime)'
Assert ($src -match 'stream-json' -and $src -match '--remote-control') 'reuses lock-style claude liveness probe'

# 3) BEHAVIOURAL: extract the helper function definitions and dot-source ONLY them, with a
#    settable $AppDir, so we can call Get-AutopilotStatusLine without running nx.ps1's switch.
$fnDefs = $ast.FindAll(
  { param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
              $n.Name -in @('Get-AutopilotStatusLine','Test-AutopilotClaudeAlive') }, $true)
Assert ($fnDefs.Count -ge 1) 'helper function(s) extractable from AST'
$AppDir = Join-Path $env:TEMP ("nxstat_" + [guid]::NewGuid())
New-Item -ItemType Directory -Force (Join-Path $AppDir 'var\autopilot') | Out-Null
$statePath = Join-Path $AppDir 'var\autopilot\run-state.json'
foreach ($d in $fnDefs) { . ([scriptblock]::Create($d.Extent.Text)) }

try {
  # (a) absent file => $null
  if (Test-Path $statePath) { Remove-Item $statePath -Force }
  $r = Get-AutopilotStatusLine
  Assert ($null -eq $r) 'absent run-state => $null'

  # (b) fresh file (under 3-min grace) => "#<n> <title>  -- building <m>m", does NOT throw
  @{ ts=(Get-Date -Format o); phase='plan'; number=94; title='Clearer execution title name'; procId=$PID } |
    ConvertTo-Json | Set-Content -Encoding utf8 $statePath
  $r = Get-AutopilotStatusLine
  Assert ($r -is [string] -and $r -match '^#94 .*building \d+m') "fresh state => '$r'"

  # (c) stale file (mtime 10 min ago, no live autopilot claude) => $null.
  # Stub Test-AutopilotClaudeAlive to $false so the test is deterministic regardless of
  # whether the test runner itself is a claude -p process (e.g. the autopilot fixer).
  function Test-AutopilotClaudeAlive { return $false }
  (Get-Item $statePath).LastWriteTime = (Get-Date).AddMinutes(-10)
  $r = Get-AutopilotStatusLine
  Assert ($null -eq $r) 'stale run-state (10m old, no live claude) => $null'
} finally {
  Remove-Item $AppDir -Recurse -Force -ErrorAction SilentlyContinue
}

if ($fail) { "`n$fail assertion(s) FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
