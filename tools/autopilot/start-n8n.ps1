#requires -Version 7
<#
.SYNOPSIS
  Start n8n with the environment the autopilot workflow REQUIRES.
.DESCRIPTION
  Two n8n 2.x defaults break the workflow unless overridden (both set here):
    * N8N_SECURE_COOKIE=false  -> lets login hold a session over http://localhost
                                  (else the editor can't load /types/nodes.json and
                                  every node shows "Install this node to use it").
    * NODES_EXCLUDE            -> n8n 2.x excludes the Execute Command node by default
                                  (@n8n/config default: executeCommand + localFileTrigger).
                                  Autopilot is built from Execute Command nodes, so this
                                  re-enables it (while keeping localFileTrigger excluded).
  These vars live only in this launcher's process (which becomes n8n) — they don't leak
  into your shell.
.NOTES
  Run this instead of a bare `n8n start`. Ctrl+C to stop.
#>
[CmdletBinding()]
param(
  # Optional: comma/space-separated GitHub logins allowed to queue autopilot issues.
  # Leave empty to use the script defaults (benstreich).
  [string]$AllowedAuthors = ''
)

$env:N8N_SECURE_COOKIE = 'false'
$env:NODES_EXCLUDE     = '["n8n-nodes-base.localFileTrigger"]'
if ($AllowedAuthors) { $env:AUTOPILOT_ALLOWED_AUTHORS = $AllowedAuthors }

# Security config check: the autopilot's gh identity must NOT itself be an allowlisted author, else
# the owner-clarification trust gate is HOLLOW — the bot would comment as a trusted user, so a
# hijacked agent reaching the keyring gh could forge a trusted clarification. Warn loudly; never
# block. See README "Security model" item 5: authenticate gh as a dedicated, non-allowlisted bot.
try {
  $ghLogin = (& gh api user --jq '.login' 2>$null)
  $allow = if ($env:AUTOPILOT_ALLOWED_AUTHORS) { $env:AUTOPILOT_ALLOWED_AUTHORS -split '[,; ]+' | Where-Object { $_ } } else { @('benstreich') }
  if ($ghLogin -and ($allow -contains $ghLogin.Trim())) {
    Write-Warning "gh on this box is authenticated as '$($ghLogin.Trim())', which IS in AUTOPILOT_ALLOWED_AUTHORS ($($allow -join ', '))."
    Write-Warning "  => the autopilot will comment AS a trusted user, so the owner-clarification gate is HOLLOW."
    Write-Warning "  => authenticate gh as a dedicated bot account NOT in the allowlist (README Security model item 5)."
  }
} catch {}

# A fresh start means no run is in progress, so clear any lock leaked by a previous
# crash (an autopilot run that died without releasing it). Prevents the loop from
# bouncing off got-lock? forever.
$lock = 'C:\dev\nexora\var\autopilot.lock'
if (Test-Path $lock) { Remove-Item $lock -Force -ErrorAction SilentlyContinue; Write-Host 'Cleared a leftover autopilot lock.' }

Write-Host 'Starting n8n with autopilot env (secure cookie off, Execute Command enabled)...'
Write-Host 'Editor will be at http://localhost:5678/  (Ctrl+C to stop)'
n8n start
