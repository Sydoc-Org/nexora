# Branch-name guard for pre-push.
# Refuses pushes from branches not named 'main' or 'feature/<x.y.z>'.
# Bypass with: git push --no-verify
#
# Invoked by the pre-commit framework (.pre-commit-config.yaml) at the
# pre-push stage. Unlike the original bash pre-push hook (which reads
# git push protocol stdin), this script just checks the currently
# checked-out branch via HEAD.

$ErrorActionPreference = 'Stop'

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
$allowed = '^(main|feature/[0-9]+\.[0-9]+\.[0-9]+)$'

if ($branch -notmatch $allowed) {
    Write-Host "[pre-push] refused: branch '$branch' must be 'main' or match 'feature/<x.y.z>' (e.g. feature/2.5.60)." -ForegroundColor Red
    Write-Host "[pre-push] rename with: git branch -m feature/<x.y.z>"
    Write-Host "[pre-push] bypass with: git push --no-verify"
    exit 1
}

Write-Host "[pre-push] branch name '$branch' OK."
exit 0
