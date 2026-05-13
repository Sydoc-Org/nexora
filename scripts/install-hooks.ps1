<#
.SYNOPSIS
    Installs the nexora pre-push hook into .git/hooks.

.DESCRIPTION
    Run once per clone. The hook runs the full pytest suite (unit + integration + e2e)
    before allowing `git push`. If tests fail, the push is aborted.

    Bypass for emergencies: `git push --no-verify`.

.EXAMPLE
    .\scripts\install-hooks.ps1
#>

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$hookPath = Join-Path $repoRoot '.git\hooks\pre-push'

if (-not (Test-Path (Join-Path $repoRoot '.git'))) {
    throw "Not a git repo (no .git directory at $repoRoot)"
}

# Sanity checks
$checks = @(
    @{ Path = (Join-Path $repoRoot 'TEST.env'); Msg = "TEST.env missing. Copy TEST.env.example and fill in values." },
    @{ Path = (Join-Path $repoRoot 'tests'); Msg = "tests/ missing - nothing to run." }
)
foreach ($c in $checks) {
    if (-not (Test-Path $c.Path)) { throw $c.Msg }
}

# Use `python` from PATH. This repo currently has no .\venv; if you later create
# one, change the exec line below to .\venv\Scripts\python or similar.
$hookContent = @'
#!/usr/bin/env bash
# Auto-installed by scripts/install-hooks.ps1.
# Runs the full nexora test suite before allowing push.
# Bypass with: git push --no-verify
set -e
echo "[pre-push] Running pytest..."
exec python -m pytest tests -q --reruns 2 --only-rerun flaky_e2e
'@

# Write as UTF-8 *without* BOM. Set-Content -Encoding UTF8 adds a BOM, which
# breaks #!/usr/bin/env bash on the first line.
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($hookPath, $hookContent, $utf8NoBom)

# Git on Windows reads the bash shebang; chmod +x is a no-op on NTFS.
Write-Host "Installed pre-push hook at $hookPath"
Write-Host "Test it with: git push --dry-run"
