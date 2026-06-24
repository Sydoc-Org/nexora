#requires -Version 7
$ErrorActionPreference = 'Stop'
$mod = Join-Path $PSScriptRoot '..\lane-paths.ps1'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $mod), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'lane-paths.ps1 parses'

. $mod
$p = Get-LanePaths -Lane 1 -BaseRepo 'C:\dev\nexora' -IssueNumber 42
Assert ($p.branch -eq 'auto/issue-42') "branch is auto/issue-NN (got $($p.branch))"
Assert ($p.worktree -eq 'C:\dev\nexora-lanes\lane-1') "worktree is OUTSIDE the repo (got $($p.worktree))"
Assert ($p.log -like '*\var\autopilot\lanes\lane-1\run.log') "per-lane log under base var (got $($p.log))"
Assert ($p.runState -like '*\var\autopilot\lanes\lane-1\run-state.json') 'per-lane run-state under base var'
Assert ($p.baseline -like '*\var\autopilot\lanes\lane-1\run-baseline.json') 'per-lane baseline under base var'
$p0 = Get-LanePaths -Lane 0 -BaseRepo 'C:\dev\nexora' -IssueNumber 7
Assert ($p0.log -ne $p.log -and $p0.worktree -ne $p.worktree) 'distinct lanes have distinct log + worktree'
# Worktree root is DERIVED from BaseRepo, not a hardcoded C:\ literal.
$pd = Get-LanePaths -Lane 0 -BaseRepo 'D:\sydoc\nexora' -IssueNumber 7
Assert ($pd.worktree -eq 'D:\sydoc\nexora-lanes\lane-0') "worktree root derives from BaseRepo (got $($pd.worktree))"
$roots = Get-AllLaneRoots -BaseRepo 'C:\dev\nexora' -MaxSlots 3
Assert ($roots.Count -eq 3) 'Get-AllLaneRoots returns one root per slot'

if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
