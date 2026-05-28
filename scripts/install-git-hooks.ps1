# DEPRECATED: superseded by the pre-commit framework.
#
# Use this instead (one-time, per clone):
#   .venv\Scripts\pre-commit.exe install --install-hooks
#   .venv\Scripts\pre-commit.exe install --hook-type commit-msg
#   .venv\Scripts\pre-commit.exe install --hook-type pre-push
#
# This script is kept temporarily as a redirect so existing muscle memory
# (`.\scripts\install-git-hooks.ps1`) still produces a working hook setup.
# It will be removed in a follow-up cleanup PR.

$ErrorActionPreference = 'Stop'

Write-Warning "scripts\install-git-hooks.ps1 is deprecated. Use 'pre-commit install' instead."
Write-Host ""
Write-Host "Running 'pre-commit install ...' for you..."

$preCommit = Join-Path (Split-Path $PSScriptRoot -Parent) '.venv\Scripts\pre-commit.exe'
if (-not (Test-Path $preCommit)) {
    Write-Error "pre-commit not found at $preCommit. Run 'uv sync' first."
    exit 1
}

& $preCommit install --install-hooks
& $preCommit install --hook-type commit-msg
& $preCommit install --hook-type pre-push

Write-Host ""
Write-Host "Done. Future runs: use 'pre-commit install ...' directly."
