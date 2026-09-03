# Branch-name guard for pre-push.
# Allows 'main', a topic branch '<type>/<slug>' where <type> is one of the
# Conventional-Commit types (feat|fix|chore|refactor|docs|test|ci) and <slug>
# is lowercase-with-hyphens, ideally issue-numbered (fix/253-collab-rules),
# and — legacy, for in-flight work only — 'v<x.y[.z[.n]]>' release-cycle
# branches and 'feature/<x.y.z>' pre-3.1 branches. See CONTRIBUTING.md.
# Bypass with: git push --no-verify
#
# Invoked by the pre-commit framework (.pre-commit-config.yaml) at the
# pre-push stage. Unlike the original bash pre-push hook (which reads
# git push protocol stdin), this script just checks the currently
# checked-out branch via HEAD.

$ErrorActionPreference = 'Stop'

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
$allowed = '^(main|(feat|fix|chore|refactor|docs|test|ci)/[a-z0-9][a-z0-9._-]*|v[0-9]+\.[0-9]+(\.[0-9]+){0,2}|feature/[0-9]+\.[0-9]+\.[0-9]+)$'

if ($branch -notmatch $allowed) {
    Write-Host "[pre-push] refused: branch '$branch' must be 'main' or '<type>/<slug>' (e.g. fix/253-collab-rules); 'v<x.y[.z[.n]]>' and 'feature/<x.y.z>' are legacy." -ForegroundColor Red
    Write-Host "[pre-push] rename with: git branch -m fix/<issue>-<slug>"
    Write-Host "[pre-push] bypass with: git push --no-verify"
    exit 1
}

Write-Host "[pre-push] branch name '$branch' OK."
exit 0
