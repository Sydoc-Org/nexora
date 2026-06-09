# SessionStart hook: pending-handoff auto-resume.
#
# /handoff-session-state writes the handoff's repo-relative path into the gitignored
# flag file var/handoff-pending. On the next fresh session (startup|clear) this hook
# sees the flag and injects a pointer so the new session resumes via /reset-session
# (which deletes the flag). No flag -> no output -> zero context cost.

$ErrorActionPreference = 'SilentlyContinue'

$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { (Get-Location).Path }
$flag = Join-Path $root 'var/handoff-pending'
if (-not (Test-Path $flag)) { exit 0 }

$handoff = (Get-Content $flag -TotalCount 1).Trim()
if (-not $handoff) { exit 0 }

$ageHours = [math]::Round(((Get-Date) - (Get-Item $flag).LastWriteTime).TotalHours, 1)

Write-Output "PENDING HANDOFF (flag var/handoff-pending, written ${ageHours}h ago): $handoff"
Write-Output "A previous session handed off here. Invoke the reset-session skill now with that path as the argument and resume the work - unless the user's first message clearly starts unrelated work (then leave the flag alone; /reset-session consumes it when run)."
exit 0
