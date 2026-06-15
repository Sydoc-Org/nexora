#requires -Version 7
# Standalone assertion (no Pester). Exit 1 on any failure.
# Guards that every per-item Telegram notify node identifies the issue as "#<n> <title>"
# (one n8n execution loops many issues, so identification is per-ITEM, not per-execution).
$ErrorActionPreference = 'Stop'
$wfPath = Join-Path $PSScriptRoot '..\n8n-autopilot.workflow.json'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

$wf = $null; try { $wf = Get-Content $wfPath -Raw | ConvertFrom-Json } catch {}
Assert ($null -ne $wf) 'workflow JSON parses'

foreach ($name in @('notify-built','notify-recovered','notify-skip','notify-questions')) {
    $text = ($wf.nodes | Where-Object { $_.name -eq $name }).parameters.text
    Assert ($text -match "Loop Over Items'\)\.item\.json\.number") "$name still shows the issue number"
    Assert ($text -match "Loop Over Items'\)\.item\.json\.title")  "$name now also shows the issue title"
}

# No reference may strip the space out of the looped node name.
$raw = Get-Content $wfPath -Raw
Assert ($raw -notmatch "LoopOverItems'\)\.item") 'no broken (space-stripped) Loop Over Items reference'

if ($fail) { "`n$fail assertion(s) FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
