# Install repo-tracked git hooks into .git/hooks/ for this clone.
# Re-run safely; backs up any existing hook to <name>.bak.

$ErrorActionPreference = "Stop"

$repo = (& git rev-parse --show-toplevel) 2>$null
if (-not $repo) {
    Write-Error "Not inside a git repository."
    exit 1
}

$src = Join-Path $repo "scripts\git-hooks"
$dst = Join-Path $repo ".git\hooks"

if (-not (Test-Path $src)) {
    Write-Error "Hook source folder not found: $src"
    exit 1
}

Get-ChildItem -Path $src -File | ForEach-Object {
    $target = Join-Path $dst $_.Name
    if (Test-Path $target) {
        Copy-Item -Path $target -Destination "$target.bak" -Force
    }
    Copy-Item -Path $_.FullName -Destination $target -Force
    Write-Host "installed: $($_.Name)  ->  $target"
}

Write-Host ""
Write-Host "Done. Pre-commit will run:"
Write-Host "  - python scripts/db-migrate.py --env INT --check  (unapplied migrations)"
Write-Host "  - python sql/sync-from-db.py --check              (drift from INT)"
Write-Host ""
Write-Host "Prerequisites on PATH:"
Write-Host "  - mssql-scripter: pip install -r sql/requirements.txt"
Write-Host "  - sqlcmd (ships with SQL Server Command Line Utilities / SSMS)"
