# Branch-name guard for pre-push.
# Refuses pushes from branches not named 'main', 'v<x.y[.z]>' (release cycle
# branches, e.g. v3.1 — convention since the 3.1 cycle) or 'feature/<x.y.z>'
# (pre-3.1 cycle branches, kept for in-flight branches).
# Bypass with: git push --no-verify
#
# Invoked by the pre-commit framework (.pre-commit-config.yaml) at the
# pre-push stage. Unlike the original bash pre-push hook (which reads
# git push protocol stdin), this script just checks the currently
# checked-out branch via HEAD.

$ErrorActionPreference = 'Stop'

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
$allowed = '^(main|v[0-9]+\.[0-9]+(\.[0-9]+)?|feature/[0-9]+\.[0-9]+\.[0-9]+)$'

if ($branch -notmatch $allowed) {
    Write-Host "[pre-push] refused: branch '$branch' must be 'main' or match 'v<x.y[.z]>' (e.g. v3.1) or 'feature/<x.y.z>'." -ForegroundColor Red
    Write-Host "[pre-push] rename with: git branch -m v<x.y>"
    Write-Host "[pre-push] bypass with: git push --no-verify"
    exit 1
}

Write-Host "[pre-push] branch name '$branch' OK."
exit 0
