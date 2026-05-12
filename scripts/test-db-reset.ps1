<#
.SYNOPSIS
    Resets NEXORA_TEST to a known state: applies sql/test/schema.sql then sql/test/seed.sql.

.DESCRIPTION
    Reads connection info from TEST.env at the repo root. Uses sqlcmd.
    Idempotent: safe to run any number of times. Run this:
      - Once after creating NEXORA_TEST via environment_transfer_queries.tmp.sql
      - In CI before every test run
      - Locally whenever the test DB has drifted

.EXAMPLE
    .\scripts\test-db-reset.ps1
#>

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$testEnv = Join-Path $repoRoot 'TEST.env'
if (-not (Test-Path $testEnv)) {
    throw "TEST.env not found at $testEnv. Copy TEST.env.example and fill in values."
}

# Parse KEY=VALUE lines
$env_vars = @{}
Get-Content $testEnv | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $k, $v = $line -split '=', 2
        $env_vars[$k.Trim()] = $v.Trim()
    }
}

$server = $env_vars['DB_SERVER_PRD']
$uid = $env_vars['DB_UID']
$pwd = $env_vars['DB_PWD']
$db = $env_vars['DB_NEXORA']

if (-not $server -or -not $uid -or -not $pwd -or -not $db) {
    throw "TEST.env is missing one of: DB_SERVER_PRD, DB_UID, DB_PWD, DB_NEXORA"
}

if ($db -ne 'NEXORA_TEST') {
    throw "Refusing to run: DB_NEXORA in TEST.env must be 'NEXORA_TEST', got '$db'."
}

$schema = Join-Path $repoRoot 'sql\test\schema.sql'
$seed = Join-Path $repoRoot 'sql\test\seed.sql'

if (-not (Test-Path $schema)) { throw "Missing: $schema" }
if (-not (Test-Path $seed)) { throw "Missing: $seed" }

Write-Host "Applying schema to $db on $server..."
sqlcmd -S $server -U $uid -P $pwd -d $db -i $schema -b
if ($LASTEXITCODE -ne 0) { throw "schema.sql failed (exit $LASTEXITCODE)" }

Write-Host "Applying seed to $db on $server..."
sqlcmd -S $server -U $uid -P $pwd -d $db -i $seed -b
if ($LASTEXITCODE -ne 0) { throw "seed.sql failed (exit $LASTEXITCODE)" }

Write-Host "NEXORA_TEST reset complete."
