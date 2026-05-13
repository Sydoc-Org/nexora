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
Write-Host "Done. Pre-commit will now run 'python sql/sync-from-db.py --check'."
Write-Host "Make sure mssql-scripter is installed:  pip install -r sql/requirements.txt"
