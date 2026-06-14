#requires -Version 7
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\recover.ps1'
$tools  = Split-Path $script
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

$errs = @()
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$errs) | Out-Null
Assert ($errs.Count -eq 0) 'recover.ps1 parses'

$tmp = New-Item -ItemType Directory -Path (Join-Path ([IO.Path]::GetTempPath()) ("rec-" + [guid]::NewGuid().ToString('N')))
try {
  # Isolated git repo so recover.ps1's own tree mutations (stash on the built/skip clean-tree
  # guarantee, rev-parse for the SinceSha anchor) operate on a throwaway repo and never touch the
  # live checkout. recover.ps1 resolves its sibling scripts relative to -RepoPath, so the isolated
  # repo is seeded with the real cost-guard/probe-infra/lock so the deterministic gates run for real.
  $repo = Join-Path $tmp 'repo'
  New-Item -ItemType Directory -Path (Join-Path $repo 'tools\autopilot') | Out-Null
  foreach ($s in 'cost-guard.ps1','probe-infra.ps1','lock.ps1') { Copy-Item (Join-Path $tools $s) (Join-Path $repo 'tools\autopilot') }
  git -C $repo init -q -b 'feature/2.5.63' *> $null
  git -C $repo config user.email 't@t'; git -C $repo config user.name 't'
  Set-Content (Join-Path $repo 'seed.txt') 'x'; git -C $repo add -A *> $null; git -C $repo commit -q -m 'init' *> $null

  # Stub diagnose: always genuine-blocker. Stub fix: emits the canned verdict from $env:STUB_FIX,
  # and (when STUB_ADVANCE=1) advances the isolated repo HEAD to mimic a real feature commit, so
  # recover's "HEAD advanced past SinceSha" feature-commit check can fire deterministically.
  $diag = Join-Path $tmp 'diag.ps1'
  Set-Content $diag @'
#requires -Version 7
param($IssueNumber,$Repo,$RepoPath,$DbServer,$N8nPort,$RunLog,$BaselineFile,$AllowedAuthors)
'{"class":"genuine-blocker","summary":"stub","suggestedFix":"","costUsd":0.01}'
'@
  $fix = Join-Path $tmp 'fix.ps1'
  Set-Content $fix @'
#requires -Version 7
param($IssueNumber,$Model,$Effort,$SinceSha,$Diagnosis,$ExtraContext,$Playbook,$Reason,$Repo,$RepoPath,$AllowedAuthors)
if ($env:STUB_ADVANCE -eq '1') {
  Set-Content (Join-Path $RepoPath "feat-$Model.txt") $Model
  git -C $RepoPath add -A *> $null
  git -C $RepoPath commit -q -m "feat $Model" *> $null
}
$env:STUB_FIX
'@
  $led = Join-Path $tmp 'attempts.json'
  $cgl = Join-Path $tmp 'cost.json'

  # HASHTABLE splatting binds named params. (Array splatting binds POSITIONALLY in PowerShell, so a
  # leading '-IssueNumber' string would land on [int]$IssueNumber and fail conversion.) Per-case
  # extras (-PlanHeadSha, -ForcePoison) are passed as trailing named args alongside @common.
  # -SkipDeterministicGates suppresses ALL poison terms so a clean checkout reaches the non-poison
  # path; poison is driven only by -ForcePoison. The real author re-check stays live (issue #91 is
  # benstreich-authored), so we do NOT stub it.
  $common = @{ IssueNumber=91; DiagnoseScript=$diag; FixScript=$fix;
               AttemptsLedger=$led; CostLedger=$cgl; MaxAttempts=2; SkipDeterministicGates=$true; RepoPath=$repo }

  # Case A: fixer succeeds (advances HEAD past SinceSha) => action built.
  $env:STUB_ADVANCE = '1'
  $env:STUB_FIX = '{"ok":true,"committed":true,"alreadyDone":false,"dirty":false,"leftoverWorktree":false,"sha":"abc","stashed":false,"costUsd":0.02,"reason":"ok"}'
  $a = & $script @common | Select-Object -Last 1 | ConvertFrom-Json
  Assert ($a.action -eq 'built') "fixer-success => built (got $($a.action))"

  # Case B: fixer never succeeds, non-poison => skip.
  $env:STUB_ADVANCE = '0'
  $env:STUB_FIX = '{"ok":false,"committed":false,"alreadyDone":false,"dirty":false,"leftoverWorktree":false,"sha":"","stashed":false,"costUsd":0.02,"reason":"no"}'
  $b = & $script @common | Select-Object -Last 1 | ConvertFrom-Json
  Assert ($b.action -eq 'skip') "exhausted + non-poison => skip (got $($b.action))"

  # Case C: malformed child verdict => fail-closed skip, NEVER built/pause.
  $env:STUB_FIX = 'not json at all'
  $c = & $script @common | Select-Object -Last 1 | ConvertFrom-Json
  Assert ($c.action -eq 'skip') "malformed child => skip (got $($c.action))"

  # Case D: bare plan commit (committed at the plan headSha) must NOT count as built.
  # Stub fix reports committed:true but sha == the SinceSha we pass; recover must treat
  # committed-at-SinceSha as no feature commit => skip. Pass -PlanHeadSha to set the anchor.
  $env:STUB_FIX = '{"ok":false,"committed":false,"alreadyDone":false,"dirty":false,"leftoverWorktree":false,"sha":"PLANSHA","stashed":false,"costUsd":0.02,"reason":"only a plan commit landed"}'
  $d = & $script @common -PlanHeadSha 'PLANSHA' | Select-Object -Last 1 | ConvertFrom-Json
  Assert ($d.action -eq 'skip') "bare plan commit => skip not built (got $($d.action))"

  # Case E: poison (forced), under livelock threshold => pause-run.
  Set-Content $led ('{}')
  $e = & $script @common -ForcePoison | Select-Object -Last 1 | ConvertFrom-Json
  Assert ($e.action -eq 'pause-run') "poison under threshold => pause-run (got $($e.action))"

  # Case F: livelock - poison over threshold escalates to a labelled skip, not pause.
  Set-Content $led ('{"91":3}')
  $f2 = & $script @common -ForcePoison | Select-Object -Last 1 | ConvertFrom-Json
  Assert ($f2.action -eq 'skip') "livelock over-threshold => labelled skip not pause (got $($f2.action))"
} finally { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue }

if ($fail) { "`n$fail FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
