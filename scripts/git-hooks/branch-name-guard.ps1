# Branch-name guard for pre-push.
# Refuses 'main' outright -- nothing is pushed there directly, it takes merged
# PRs only. GitHub cannot enforce that for us (branch protection and rulesets
# are both unavailable on a private repo on the Free plan), so this hook is the
# enforcement. Otherwise allows a topic branch '<type>/<slug>' where <type> is one of the
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
$allowed = '^((feat|fix|chore|refactor|docs|test|ci)/[a-z0-9][a-z0-9._-]*|v[0-9]+\.[0-9]+(\.[0-9]+){0,2}|feature/[0-9]+\.[0-9]+\.[0-9]+)$'

# ponytail: checks HEAD only, so 'git push origin main' from a topic branch
# still slips through. Catching that needs the stdin push-protocol hook this
# script deliberately replaced -- add it back the first time someone does it.
if ($branch -eq 'main') {
    Write-Host "[pre-push] refused: nothing is pushed to 'main' directly -- open a PR from a topic branch. See CONTRIBUTING.md." -ForegroundColor Red
    Write-Host "[pre-push] bypass with: git push --no-verify"
    exit 1
}

if ($branch -notmatch $allowed) {
    Write-Host "[pre-push] refused: branch '$branch' must be '<type>/<slug>' (e.g. fix/253-collab-rules); 'v<x.y[.z[.n]]>' and 'feature/<x.y.z>' are legacy." -ForegroundColor Red
    Write-Host "[pre-push] rename with: git branch -m fix/<issue>-<slug>"
    Write-Host "[pre-push] bypass with: git push --no-verify"
    exit 1
}

Write-Host "[pre-push] branch name '$branch' OK."
exit 0
