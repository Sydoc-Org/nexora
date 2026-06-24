#requires -Version 7
# Standalone assertion (no Pester). Exit 1 on any failure.
# Guards the n8n-clarify-reply workflow against the command-injection regression: the owner's
# Telegram reply text must reach `gh` ONLY as file contents (--body-file), never interpolated
# into the shell command; and the inbound gate must pin chat.id + private chat + from.id.
$ErrorActionPreference = 'Stop'
$wfPath = Join-Path $PSScriptRoot '..\n8n-clarify-reply.workflow.json'
$fail = 0
function Assert([bool]$cond, [string]$msg) { if ($cond) { "PASS  $msg" } else { "FAIL  $msg"; $script:fail++ } }

# 1) Valid JSON.
$wf = $null; try { $wf = Get-Content $wfPath -Raw | ConvertFrom-Json } catch {}
Assert ($null -ne $wf) 'workflow JSON parses'

# 2) No undefined-edge: every connection source + target is a real node.
$names = $wf.nodes | ForEach-Object { $_.name }
$undef = @()
foreach ($p in $wf.connections.PSObject.Properties) {
  if ($names -notcontains $p.Name) { $undef += $p.Name }
  foreach ($outArr in $p.Value.main) { foreach ($e in $outArr) { if ($e -and ($names -notcontains $e.node)) { $undef += $e.node } } }
}
Assert ($undef.Count -eq 0) "no undefined-edge targets ($($undef -join ','))"

# 3) post-clarification is injection-safe.
$post = ($wf.nodes | Where-Object { $_.name -eq 'post-clarification' }).parameters.command
Assert ($post -match '--body-file')   'post-clarification uses --body-file'
Assert ($post -notmatch '--body\s+"') 'post-clarification has no inline --body "..."'
Assert ($post -notmatch 'replyText')  'post-clarification does not interpolate replyText'

# 4) Inbound gate hardened: chat.id + chat.type private + from.id.
$gate = ($wf.nodes | Where-Object { $_.name -eq 'owner-chat?' }).parameters.conditions.conditions
Assert ((@($gate)).Count -ge 3) 'owner-chat? has >=3 gate conditions'
$gateText = ($gate | ForEach-Object { "$($_.leftValue)|$($_.rightValue)" }) -join ' ; '
Assert ($gateText -match 'chat\.type' -and $gateText -match 'private') 'owner-chat? requires chat.type private'
Assert ($gateText -match 'from\.id') 'owner-chat? checks from.id'

# 5) The body file is written WITH the owner-clarification: prefix in a Code node.
$guard = ($wf.nodes | Where-Object { $_.name -eq 'guard-number-count' }).parameters.jsCode
Assert ($guard -match 'bodyFile' -and $guard -match 'owner-clarification:') 'guard-number-count writes prefixed body file'

if ($fail) { "`n$fail assertion(s) FAILED"; exit 1 } else { "`nALL PASS"; exit 0 }
