<#
.SYNOPSIS
  One-shot bootstrap for a fresh nexora dev environment.

.DESCRIPTION
  Idempotent and re-runnable. Detects Python, installs uv if missing,
  creates .venv and runs uv sync, installs Playwright chromium, seeds
  env/<ENV>.env from env/<ENV>.env.example (without ever overwriting an
  existing env file), installs pre-commit hooks, and ensures the var/
  subdirs exist. Prints a checklist of remaining manual steps at the
  end (DB credentials, NEXORA_TEST reset, dev-server start, etc.).

.PARAMETER Env
  Which environment to seed. Default: INT. Options: INT, STAGING, TEST.
  TEST.env is always seeded alongside since the test suite needs it.

.EXAMPLE
  .\bootstrap.ps1
  .\bootstrap.ps1 -Env STAGING

.NOTES
  PR 10 of the dev-env upgrade. See CONTRIBUTING.md for the manual
  fallback if any step fails.
#>
[CmdletBinding()]
param(
    [ValidateSet('INT', 'STAGING', 'TEST')]
    [string]$Env = 'INT'
)

$ErrorActionPreference = 'Stop'
$repoRoot = $PSScriptRoot
Set-Location $repoRoot

Write-Host "==> Bootstrapping nexora dev environment ($Env)" -ForegroundColor Cyan
Write-Host ""

# --- 1. Python -------------------------------------------------------------
$pyVersionFile = Join-Path $repoRoot '.python-version'
if (-not (Test-Path $pyVersionFile)) {
    throw "Missing .python-version. Are you in the nexora repo root?"
}
$wantPy = (Get-Content $pyVersionFile -Raw).Trim()
Write-Host "==> Required Python: $wantPy"

$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyCmd) {
    throw "Python not found on PATH. Install Python $wantPy first (https://www.python.org/downloads/)."
}
$gotPy = (& python --version 2>&1).ToString().Replace('Python ', '').Trim()
Write-Host "==> Found Python: $gotPy"
if ($gotPy -ne $wantPy) {
    Write-Warning "Python version mismatch (want $wantPy, got $gotPy). Continuing, but the locked deps target $wantPy."
}

# --- 2. uv -----------------------------------------------------------------
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "==> Installing uv via pip"
    & python -m pip install --user --upgrade uv
}
$uvVersion = (& uv --version 2>&1).ToString().Trim()
Write-Host "==> uv: $uvVersion"

# --- 3. Virtualenv + sync --------------------------------------------------
# `uv sync --extra dev` creates .venv if missing and resolves from uv.lock,
# including the dev group (pytest, ruff, mypy, playwright, pre-commit, ...).
# Without --extra dev only runtime deps land, which would break the
# Playwright install step and every later dev workflow.
Write-Host "==> Syncing dependencies (uv sync --extra dev)"
& uv sync --extra dev
if ($LASTEXITCODE -ne 0) { throw "uv sync --extra dev failed (exit $LASTEXITCODE)" }

# --- 4. Playwright ---------------------------------------------------------
Write-Host "==> Installing Playwright chromium (no-op if already present)"
& .venv\Scripts\python.exe -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "playwright install failed (exit $LASTEXITCODE)" }

# --- 5. Env files ----------------------------------------------------------
$envDir = Join-Path $repoRoot 'env'
if (-not (Test-Path $envDir)) {
    New-Item -ItemType Directory -Path $envDir | Out-Null
}

function Seed-EnvFile {
    param([string]$Name)
    $envFile = Join-Path $envDir "$Name.env"
    $exampleFile = Join-Path $envDir "$Name.env.example"
    if (Test-Path $envFile) {
        Write-Host "==> env/$Name.env already exists (not overwritten)"
        return
    }
    if (Test-Path $exampleFile) {
        Copy-Item $exampleFile $envFile
        Write-Host "==> Created env/$Name.env from template -- FILL IN REAL VALUES" -ForegroundColor Yellow
    } else {
        Write-Warning "No env/$Name.env or env/$Name.env.example present."
    }
}

Seed-EnvFile -Name $Env
# TEST.env is always needed (pytest reads it).
if ($Env -ne 'TEST') {
    Seed-EnvFile -Name 'TEST'
}

# --- 6. Pre-commit ---------------------------------------------------------
$preCommit = Join-Path $repoRoot '.venv\Scripts\pre-commit.exe'
if (-not (Test-Path $preCommit)) {
    throw "pre-commit not found at $preCommit. uv sync should have installed it -- check pyproject.toml dev deps."
}
Write-Host "==> Installing pre-commit hooks (pre-commit, commit-msg, pre-push)"
& $preCommit install --install-hooks
& $preCommit install --hook-type commit-msg
& $preCommit install --hook-type pre-push

# --- 7. var/ ---------------------------------------------------------------
# config.py auto-creates these on import, but cover bootstrap-only scenarios
# (e.g. running scripts that don't import nx_lib.config first).
$varDirs = @(
    'var', 'var/uploads', 'var/session', 'var/logs',
    'var/screenshots', 'var/backups', 'var/test-results'
)
foreach ($d in $varDirs) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d | Out-Null }
}

# --- 8. Final checklist ----------------------------------------------------
Write-Host ""
Write-Host "==> Bootstrap complete." -ForegroundColor Green
Write-Host ""
Write-Host "Next steps (manual):" -ForegroundColor Yellow
Write-Host "  1. Edit env\$Env.env with real DB / Graph / Octo / Bexio credentials"
if ($Env -ne 'TEST') {
    Write-Host "  2. Edit env\TEST.env with NEXORA_TEST credentials"
}
Write-Host "  3. Reset the NEXORA_TEST database:  .\scripts\test-db-reset.ps1"
Write-Host "  4. Activate the venv:               .venv\Scripts\Activate.ps1"
Write-Host "  5. Run the dev server:              .\bin\nx.ps1 -u"
Write-Host "  6. Run the tests:                   python -m pytest tests -v"
Write-Host ""
Write-Host "If anything went sideways, see CONTRIBUTING.md for the manual fallback."
