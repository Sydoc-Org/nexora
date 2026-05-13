<#
.SYNOPSIS
    Resets NEXORA_TEST to a known state.

.DESCRIPTION
    Thin wrapper around scripts/test_db_reset.py (pyodbc-based, no sqlcmd
    dependency). The Python version works locally and in CI without needing
    SQL Server Command Line Tools installed.

.EXAMPLE
    .\scripts\test-db-reset.ps1
#>

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $repoRoot 'scripts\test_db_reset.py'

# Prefer the production runner's Python; fall back to whatever's on PATH locally.
$python = if (Test-Path 'D:\sydoc\tools\py\python.exe') {
    'D:\sydoc\tools\py\python.exe'
} else {
    'python'
}

& $python $scriptPath
if ($LASTEXITCODE -ne 0) { throw "test_db_reset.py failed (exit $LASTEXITCODE)" }
