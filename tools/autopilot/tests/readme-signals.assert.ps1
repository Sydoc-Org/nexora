#!/usr/bin/env pwsh
# Assertion: README.md + SIGNALS.md contain the recovery-layer documentation updates
$pass = 0; $fail = 0
function Assert($label, $cond) {
    if ($cond) { Write-Host "PASS: $label"; $script:pass++ }
    else        { Write-Host "FAIL: $label"; $script:fail++ }
}

$readme  = Get-Content C:\dev\nexora\tools\autopilot\README.md  -Raw
$signals = Get-Content C:\dev\nexora\tools\autopilot\SIGNALS.md -Raw

# --- README checks ---

# typeVersion caveat: Switch node added
Assert "README typeVersion caveat mentions Switch = 3" ($readme -match 'Switch = 3')
Assert "README typeVersion caveat mentions Fallback Output" ($readme -match 'Fallback Output enabled')

# Telegram node list expanded
Assert "README Telegram list has notify-recovered" ($readme -match 'notify-recovered')
Assert "README Telegram list has notify-skip"      ($readme -match 'notify-skip')
Assert "README Telegram list has notify-questions" ($readme -match 'notify-questions')
Assert "README Telegram list has notify-pause"     ($readme -match 'notify-pause')
Assert "README Telegram list has notify-costcap"   ($readme -match 'notify-costcap')
Assert "README Telegram list no longer lists only three nodes (seven)" ($readme -match 'seven Telegram nodes')
Assert "README Telegram list removed notify-halt"  ($readme -notmatch '`notify-halt`.*credential')

# Pieces table: new recovery-layer scripts
Assert "README pieces table has recover.ps1"        ($readme -match '`recover\.ps1`')
Assert "README pieces table has diagnose-halt.ps1"  ($readme -match '`diagnose-halt\.ps1`')
Assert "README pieces table has fix-attempt.ps1"    ($readme -match '`fix-attempt\.ps1`')
Assert "README pieces table has triage.ps1"         ($readme -match '`triage\.ps1`')
Assert "README pieces table has probe-infra.ps1"    ($readme -match '`probe-infra\.ps1`')
Assert "README pieces table has RECOVERY-PLAYBOOK"  ($readme -match 'RECOVERY-PLAYBOOK\.md')
Assert "README pieces table marks solve-blocked deprecated" ($readme -match '[Dd]eprecated.*superseded')

# Top flow updated for new semantics
Assert "README top flow mentions skip-and-continue or skip" ($readme -match 'skip')
Assert "README top flow mentions needs-input or QUESTIONS"  ($readme -match 'needs-input|QUESTIONS-FOR-OWNER')
Assert "README top flow mentions pause-run"                 ($readme -match 'pause-run')
Assert "README flow no longer shows old solve-blocked ONE attempt line" `
    ($readme -notmatch 'solve-blocked.*ONE recovery attempt')

# MaxAttempts / LivelockMax / attempts.json
Assert "README documents MaxAttempts"      ($readme -match 'MaxAttempts')
Assert "README documents LivelockMax"      ($readme -match 'LivelockMax')
Assert "README documents attempts.json"    ($readme -match 'attempts\.json')

# clarify-reply workflow + autopilot-needs-input label
Assert "README mentions n8n-clarify-reply workflow"    ($readme -match 'n8n-clarify-reply')
Assert "README mentions autopilot-needs-input label"   ($readme -match 'autopilot-needs-input')

# Node/connection reference: new nodes
Assert "README node table has recover"          ($readme -match '\| recover ')
Assert "README node table has route-recovery"   ($readme -match 'route-recovery')
Assert "README node table has triage node"      ($readme -match '\| triage ')
Assert "README node table has continue-collector" ($readme -match 'continue-collector')
Assert "README node table has comment-built-recovered" ($readme -match 'comment-built-recovered')

# Branch wiring updated
Assert "README branch wiring: failure edges converge on recover" `
    ($readme -match "converge on \`recover\`|converge on ``recover``|converge on .recover.")

# --- SIGNALS checks ---

# New emitted-JSON contracts
Assert "SIGNALS has triage contract"       ($signals -match 'triage')
Assert "SIGNALS has diagnose-halt contract" ($signals -match 'diagnose-halt')
Assert "SIGNALS has recover contract"      ($signals -match '`recover\.ps1`|recover \{|recover.*action|### .recover')
Assert "SIGNALS has probe-infra contract"  ($signals -match 'probe-infra')
Assert "SIGNALS has fix-attempt contract"  ($signals -match 'fix-attempt')

# Closed class enum
Assert "SIGNALS documents mechanical class"           ($signals -match 'mechanical')
Assert "SIGNALS documents test-gate class"            ($signals -match 'test-gate')
Assert "SIGNALS documents plan-ok-execute-failed"     ($signals -match 'plan-ok-execute-failed')
Assert "SIGNALS documents infra class"                ($signals -match 'infra')
Assert "SIGNALS documents genuine-blocker class"      ($signals -match 'genuine-blocker')

# action values in recover
Assert "SIGNALS documents action=built"     ($signals -match '\bbuilt\b')
Assert "SIGNALS documents action=skip"      ($signals -match '\bskip\b')
Assert "SIGNALS documents action=pause-run" ($signals -match 'pause-run')

# Pending rows
Assert "SIGNALS has pending row for diagnostician shape" `
    ($signals -match 'live run|first live|real.*run|pending.*diagnos|diagnos.*pending')
Assert "SIGNALS has pending row for read-only claude flag" `
    ($signals -match 'allowedTools|permission-mode|read-only.*claude|claude.*flag')

Write-Host ""
if ($fail -eq 0) { Write-Host "ALL PASS ($pass assertions)" }
else              { Write-Host "FAILURES: $fail / $($pass+$fail)" }
exit $fail
