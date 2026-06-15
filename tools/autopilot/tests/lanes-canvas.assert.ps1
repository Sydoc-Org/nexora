#requires -Version 7
<#
.SYNOPSIS
  Structural assertions for the concurrent-lanes canvas rewiring in n8n-autopilot.workflow.json.
  Verifies new nodes exist, critical connections are present, and commands include lane-aware params.
  No Pester required.
#>
$ErrorActionPreference = 'Stop'
$pass = 0; $fail = 0

function Assert([bool]$cond, [string]$label) {
    if ($cond) { Write-Host "PASS  $label"; $script:pass++ }
    else        { Write-Host "FAIL  $label"; $script:fail++ }
}

$wfPath = Join-Path (Split-Path $PSScriptRoot) 'n8n-autopilot.workflow.json'
$raw    = Get-Content $wfPath -Raw
$wf     = $raw | ConvertFrom-Json -Depth 30
$nodes  = @{} ; $wf.nodes | ForEach-Object { $nodes[$_.name] = $_ }
$conn   = $wf.connections

# ── New nodes exist ────────────────────────────────────────────────────────────
Assert ($nodes.ContainsKey('dispatch-acquire')) 'dispatch-acquire node present'
Assert ($nodes.ContainsKey('got-slot?'))        'got-slot? node present'
Assert ($nodes.ContainsKey('db-acquire'))       'db-acquire node present'
Assert ($nodes.ContainsKey('db-release'))       'db-release node present'
Assert ($nodes.ContainsKey('merge-back'))       'merge-back node present'
Assert ($nodes.ContainsKey('merge-route'))      'merge-route node present'
Assert ($nodes.ContainsKey('merge-resolve'))    'merge-resolve node present'
Assert ($nodes.ContainsKey('pause-lane'))       'pause-lane node present'

# ── Connection: have-work? [0] → split-to-items (global lock bypassed) ─────────
$hwConn = try { $conn.'have-work?'.main[0][0].node } catch { $null }
Assert ($hwConn -eq 'split-to-items') 'have-work?[0] → split-to-items (global lock bypassed)'

# ── Connection: Loop Over Items [1] → dispatch-acquire ────────────────────────
$loopConn = try { $conn.'Loop Over Items'.main[1][0].node } catch { $null }
Assert ($loopConn -eq 'dispatch-acquire') 'Loop Over Items[1] → dispatch-acquire'

# ── Connection: dispatch-acquire → got-slot? ──────────────────────────────────
$daConn = try { $conn.'dispatch-acquire'.main[0][0].node } catch { $null }
Assert ($daConn -eq 'got-slot?') 'dispatch-acquire → got-slot?'

# ── Connection: got-slot? [0]=ACQUIRED → preflight ───────────────────────────
$gsTrue  = try { $conn.'got-slot?'.main[0][0].node } catch { $null }
Assert ($gsTrue -eq 'preflight') 'got-slot?[0] → preflight'

# ── Connection: got-slot? [1]=FULL → continue-collector ──────────────────────
$gsFalse = try { $conn.'got-slot?'.main[1][0].node } catch { $null }
Assert ($gsFalse -eq 'continue-collector') 'got-slot?[1] → continue-collector'

# ── Connection: plan-ok? [0] → db-acquire (not run-exec directly) ─────────────
$planOkConn = try { $conn.'plan-ok?'.main[0][0].node } catch { $null }
Assert ($planOkConn -eq 'db-acquire') 'plan-ok?[0] → db-acquire'

# ── Connection: db-acquire → run-exec ────────────────────────────────────────
$dbAcqConn = try { $conn.'db-acquire'.main[0][0].node } catch { $null }
Assert ($dbAcqConn -eq 'run-exec') 'db-acquire → run-exec'

# ── Connection: verify-exec [0] → db-release ─────────────────────────────────
$veConn = try { $conn.'verify-exec'.main[0][0].node } catch { $null }
Assert ($veConn -eq 'db-release') 'verify-exec[0] → db-release'

# ── Connection: db-release → exec-ok? ────────────────────────────────────────
$dbRelConn = try { $conn.'db-release'.main[0][0].node } catch { $null }
Assert ($dbRelConn -eq 'exec-ok?') 'db-release → exec-ok?'

# ── Connection: exec-ok? [0] → merge-back ────────────────────────────────────
$eoConn = try { $conn.'exec-ok?'.main[0][0].node } catch { $null }
Assert ($eoConn -eq 'merge-back') 'exec-ok?[0] → merge-back'

# ── Connection: merge-back → merge-route ─────────────────────────────────────
$mbConn = try { $conn.'merge-back'.main[0][0].node } catch { $null }
Assert ($mbConn -eq 'merge-route') 'merge-back → merge-route'

# ── Connection: merge-route outputs ──────────────────────────────────────────
$mr0 = try { $conn.'merge-route'.main[0][0].node } catch { $null }
$mr1 = try { $conn.'merge-route'.main[1][0].node } catch { $null }
$mr2 = try { $conn.'merge-route'.main[2][0].node } catch { $null }
$mr3 = try { $conn.'merge-route'.main[3][0].node } catch { $null }
Assert ($mr0 -eq 'comment-built')      'merge-route[0]=MERGED → comment-built'
Assert ($mr1 -eq 'merge-resolve')      'merge-route[1]=CONFLICT → merge-resolve'
Assert ($mr2 -eq 'continue-collector') 'merge-route[2]=BUSY → continue-collector'
Assert ($mr3 -eq 'notify-pause')       'merge-route[fallback] → notify-pause'

# ── Connection: merge-resolve → continue-collector ───────────────────────────
$mresConn = try { $conn.'merge-resolve'.main[0][0].node } catch { $null }
Assert ($mresConn -eq 'continue-collector') 'merge-resolve → continue-collector'

# ── Connection: notify-pause → pause-lane ────────────────────────────────────
$npConn = try { $conn.'notify-pause'.main[0][0].node } catch { $null }
Assert ($npConn -eq 'pause-lane') 'notify-pause → pause-lane'

# ── Connection: pause-lane → continue-collector ───────────────────────────────
$plConn = try { $conn.'pause-lane'.main[0][0].node } catch { $null }
Assert ($plConn -eq 'continue-collector') 'pause-lane → continue-collector'

# ── run-plan command includes lane-aware params ───────────────────────────────
$rpCmd = $nodes['run-plan'].parameters.command
Assert ($rpCmd -match '-Lane')      'run-plan command has -Lane flag'
Assert ($rpCmd -match '-LogPath')   'run-plan command has -LogPath'
Assert ($rpCmd -match '-StatePath') 'run-plan command has -StatePath'
Assert ($rpCmd -match '-RepoPath')  'run-plan command has -RepoPath'
Assert ($rpCmd -match 'dispatch-acquire') 'run-plan -RepoPath references dispatch-acquire worktree'

# ── run-exec command includes lane-aware params ───────────────────────────────
$reCmd = $nodes['run-exec'].parameters.command
Assert ($reCmd -match '-Lane')      'run-exec command has -Lane flag'
Assert ($reCmd -match '-LogPath')   'run-exec command has -LogPath'
Assert ($reCmd -match '-StatePath') 'run-exec command has -StatePath'
Assert ($reCmd -match '-RepoPath')  'run-exec command has -RepoPath'

# ── merge-route has 3 named rules (MERGED / CONFLICT / BUSY) ─────────────────
$rules = try { @($nodes['merge-route'].parameters.rules.values) } catch { @() }
Assert ($rules.Count -eq 3) 'merge-route has exactly 3 rules (MERGED/CONFLICT/BUSY)'

# ── got-slot? uses correct condition (status == ACQUIRED) ────────────────────
$gsCondVal = try { $nodes['got-slot?'].parameters.conditions.conditions[0].rightValue } catch { $null }
Assert ($gsCondVal -eq 'ACQUIRED') 'got-slot? condition rightValue is ACQUIRED'

# ── merge-route fallbackOutput = extra (enables 4th output = notify-pause) ───
$fbOut = try { $nodes['merge-route'].parameters.options.fallbackOutput } catch { $null }
Assert ($fbOut -eq 'extra') 'merge-route fallbackOutput = extra'

# ── dispatch-acquire node type ────────────────────────────────────────────────
Assert ($nodes['dispatch-acquire'].type -eq 'n8n-nodes-base.executeCommand') 'dispatch-acquire is executeCommand'

# ── pause-lane releases the slot (freeing it for the next issue) ──────────────
$pauseCmd = $nodes['pause-lane'].parameters.command
Assert ($pauseCmd -match 'lane\.ps1') 'pause-lane calls lane.ps1'
Assert ($pauseCmd -match '-Action release') 'pause-lane uses -Action release'

# ── merge-back references the slot expr ──────────────────────────────────────
$mbCmd = $nodes['merge-back'].parameters.command
Assert ($mbCmd -match 'merge-back\.ps1') 'merge-back calls merge-back.ps1'
Assert ($mbCmd -match '-Slot') 'merge-back passes -Slot'

# ── Summary ──────────────────────────────────────────────────────────────────
Write-Host ""
if ($fail -eq 0) { Write-Host "ALL PASS  ($pass tests)" }
else             { Write-Host "FAIL: $fail of $($pass+$fail) tests failed"; exit 1 }
