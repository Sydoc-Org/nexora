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
# uv provisions its own isolated interpreter per .python-version (step 3) --
# it does NOT need a matching (or any) system Python on PATH. This step is
# informational only. A bare `python` on PATH is notoriously unreliable on
# Windows (the Microsoft Store "app execution alias" shadows it with a stub
# that errors instead of running, even when a real install exists elsewhere)
# and previously made this a hard blocker for anyone hitting that -- don't
# repeat that mistake here.
$pyVersionFile = Join-Path $repoRoot '.python-version'
if (-not (Test-Path $pyVersionFile)) {
    throw "Missing .python-version. Are you in the nexora repo root?"
}
$wantPy = (Get-Content $pyVersionFile -Raw).Trim()
Write-Host "==> Required Python: $wantPy (uv will fetch it in step 3 if it isn't already installed)"

# --- 2. uv -----------------------------------------------------------------
$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvCmd) {
    Write-Host "==> Installing uv (standalone installer -- doesn't depend on"
    Write-Host "    python/pip being resolvable, unlike 'pip install uv')"
    Invoke-Expression (Invoke-RestMethod https://astral.sh/uv/install.ps1)
    $uvBin = Join-Path $env:USERPROFILE '.local\bin'
    if ($env:Path -notlike "*$uvBin*") { $env:Path = "$uvBin;$env:Path" }
    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uvCmd) {
        throw "uv still not found after install. Open a new shell (so PATH picks up $uvBin) and re-run bootstrap.ps1."
    }
}
$uvVersion = (& uv --version 2>&1).ToString().Trim()
Write-Host "==> uv: $uvVersion"

# --- 3. Virtualenv + sync --------------------------------------------------
# `uv sync` creates .venv if missing and resolves from uv.lock. Dev deps are a
# PEP 735 dependency group (pytest, ruff, mypy, playwright, pre-commit, ...),
# which bare `uv sync` installs by default — no flag needed.
Write-Host "==> Syncing dependencies (uv sync)"
& uv sync
if ($LASTEXITCODE -ne 0) { throw "uv sync failed (exit $LASTEXITCODE)" }

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
