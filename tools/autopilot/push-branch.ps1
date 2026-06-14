#requires -Version 7
<#
.SYNOPSIS
  Autopilot AUTO-PUSH (opt-in, OFF by default) - after a run drains its queue, reset the test DB
  and push the feature branch to origin, letting the pre-push e2e gate decide. NEVER main, NEVER
  PR, NEVER deploy.
.DESCRIPTION
  DISABLED unless AUTOPILOT_AUTOPUSH=1 is set in the environment. This is a deliberate policy
  evolution of the "commit, never push" design: the owner opts in when ready to let unattended,
  test-passing builds reach origin/<feature-branch> for their own later review (still no PR, the
  branch is never main, so deploy.yml - which triggers only on main - never fires).

  Emits exactly ONE compact JSON verdict on stdout for the n8n flow; never throws.

  HARD SAFETY (belt-and-braces, in priority order):
    1. Refuse if the current branch is main/master. deploy.yml triggers only on pushes to main,
       so never-main == never-deploy; this guard makes that structural rather than incidental.
    2. Opt-in gate: do nothing unless AUTOPILOT_AUTOPUSH=1.
    3. Reset NEXORA_TEST first (scripts/test_db_reset.py) so the pre-push pytest gate (which runs
       the Playwright e2e suite) does not fail on stale, order-dependent test state.
    4. `git push` runs the FULL pre-push gate (branch-name-guard + pytest --reruns 2). NEVER
       --no-verify, NEVER --force. A failing gate => git exits non-zero => verdict pushed:false
       and NOTHING reaches origin; the n8n summary then reports "built but tests failed".
#>
[CmdletBinding()]
param(
  [string]$RepoPath = 'C:\dev\nexora',
  [string]$Remote   = 'origin',
  [int]$IssueNumber = 0
)
$ErrorActionPreference = 'Stop'
Set-Location $RepoPath

$logDir = Join-Path $RepoPath 'var\autopilot\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir 'push.log'

$branch = (git -C $RepoPath rev-parse --abbrev-ref HEAD).Trim()

# 1. Hard refuse on main/master - the single most important guard.
if ($branch -in @('main', 'master')) {
  [ordered]@{ pushed = $false; status = 'refused-main'; branch = $branch; reason = 'refusing to push main/master (never-main policy)' } | ConvertTo-Json -Compress
  exit 0
}

# 2. Opt-in gate.
if ($env:AUTOPILOT_AUTOPUSH -ne '1') {
  [ordered]@{ pushed = $false; status = 'disabled'; branch = $branch; reason = 'auto-push disabled (set AUTOPILOT_AUTOPUSH=1 to enable)' } | ConvertTo-Json -Compress
  exit 0
}

try {
  "=== AUTOPUSH  branch=$branch  issue #$IssueNumber  $(Get-Date -Format o) ===" | Add-Content -Path $log -Encoding utf8

  # 3. Reset the test DB so the pre-push e2e gate starts from a known state.
  $py = Join-Path $RepoPath '.venv\Scripts\python.exe'
  if (-not (Test-Path $py)) { $py = 'python' }
  & $py (Join-Path $RepoPath 'scripts\test_db_reset.py') *>> $log
  $resetOk = ($LASTEXITCODE -eq 0)
  if (-not $resetOk) {
    [ordered]@{ pushed = $false; status = 'db-reset-failed'; branch = $branch; reason = 'scripts/test_db_reset.py failed; not pushing (see var/autopilot/logs/push.log)' } | ConvertTo-Json -Compress
    exit 0
  }

  # 4. Push. The pre-push hook runs the full pytest/e2e gate; never bypass it.
  $pushOut = git -C $RepoPath push $Remote $branch 2>&1
  $pushOut | Out-String | Add-Content -Path $log -Encoding utf8
  $pushed = ($LASTEXITCODE -eq 0)

  if ($pushed) {
    $sha = (git -C $RepoPath rev-parse --short HEAD).Trim()
    [ordered]@{ pushed = $true; status = 'pushed'; branch = $branch; sha = $sha; reason = "pushed $branch to $Remote (pre-push gate passed)" } | ConvertTo-Json -Compress
  } else {
    [ordered]@{ pushed = $false; status = 'gate-failed'; branch = $branch; reason = 'the pre-push test/e2e gate failed; nothing was pushed (see var/autopilot/logs/push.log)' } | ConvertTo-Json -Compress
  }
}
catch {
  [ordered]@{ pushed = $false; status = 'error'; branch = $branch; reason = "auto-push aborted: $($_.Exception.Message)" } | ConvertTo-Json -Compress
  exit 0
}
