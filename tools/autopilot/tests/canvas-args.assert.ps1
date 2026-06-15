#requires -Version 7
# Standalone assertion (no Pester). Exit 1 on any failure.
# Regression guard for the recover/mark-blocked crash-loop: an n8n executeCommand arg whose
# expression can resolve to '' MUST be wrapped in quotes, else `pwsh -File ... -Arg` (bare) fails
# parameter binding ("Missing an argument for parameter ...") and the node throws every run.
$ErrorActionPreference = 'Stop'
$wfPath = Join-Path $PSScriptRoot '..\n8n-autopilot.workflow.json'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

# 1) Valid JSON.
$wf = $null; try { $wf = Get-Content $wfPath -Raw | ConvertFrom-Json } catch {}
Assert ($null -ne $wf) 'workflow JSON parses'

$raw = Get-Content $wfPath -Raw

# 2) Args whose expression has a `return ''` empty-fallback are QUOTED (escaped \" in the JSON).
#    Bare form `-PlanHeadSha {{` / `-Class {{` must NOT appear.
Assert ($raw -match '-PlanHeadSha \\"\{\{') 'recover -PlanHeadSha is wrapped in escaped quotes'
Assert ($raw -notmatch '-PlanHeadSha \{\{')  'no bare -PlanHeadSha {{ (would crash on the pre-plan path)'
Assert ($raw -match '-Class \\"\{\{')        'mark-blocked -Class is wrapped in escaped quotes'
Assert ($raw -notmatch '-Class \{\{')        'no bare -Class {{ (would crash when recover class is empty)'

# 3) The recover + mark-blocked nodes specifically carry the quoted forms (parsed-level guard).
$rec = ($wf.nodes | Where-Object { $_.name -eq 'recover' }).parameters.command
$mb  = ($wf.nodes | Where-Object { $_.name -eq 'mark-blocked' }).parameters.command
Assert ($rec -match '-PlanHeadSha "\{\{') 'recover node command quotes -PlanHeadSha (parsed)'
Assert ($mb  -match '-Class "\{\{')        'mark-blocked node command quotes -Class (parsed)'

# 4) clean? must read PREFLIGHT's stdout explicitly. `baseline` now sits between preflight and
#    clean?, so a bare `$json.stdout` reads baseline's JSON (never 'CLEAN') => clean? always false
#    => every run wrongly routes to recover and nothing builds.
$cleanCond = (($wf.nodes | Where-Object { $_.name -eq 'clean?' }).parameters.conditions.conditions | Select-Object -First 1).leftValue
Assert ($cleanCond -match "preflight") "clean? reads preflight's stdout, not its baseline input ($cleanCond)"

# run-exec must forward the issue number so the execute phase's run.log header / run-state
# carry the real issue, not #0. Mirrors run-plan. The `=` prefix is mandatory for n8n {{ }}.
$exec = ($wf.nodes | Where-Object { $_.name -eq 'run-exec' }).parameters.command
Assert ($exec -match '^=')                                       'run-exec command is an n8n expression (= prefix)'
Assert ($exec -match "-IssueNumber \{\{ \`$\('Loop Over Items'\)\.item\.json\.number \}\}") 'run-exec passes -IssueNumber from the looped item'

if ($fail) { "`n$fail assertion(s) FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
