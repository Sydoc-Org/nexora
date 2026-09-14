<#
.SYNOPSIS
  Create one extra nexora host on SYAPP01 (#338). Idempotent; run in an
  ELEVATED PowerShell on the server, once per environment:

    .\setup-env.ps1 -Name dev     -Port 8081 -Environment INT     -Hostname dev-nexora.sydoc.ch
    .\setup-env.ps1 -Name staging -Port 8082 -Environment STAGING -Hostname staging-nexora.sydoc.ch

.DESCRIPTION
  Creates D:\sydoc\nexora-<Name> with its var\ tree and root .env selector, an
  app pool cloned from DefaultAppPool's identity, an IIS site bound to
  127.0.0.1:<Port> only (ngrok is the sole client), grants for the pool and
  the GitHub runner service account, a Defender exclusion on var\ (per-request
  writes), and appends an ngrok endpoint to ngrok.yaml, restarting the ngrok
  service. Nothing here touches the prod site, pool or folder.

  After this: push the env file from a dev box
  (`python scripts/env-sync.py --push <Environment>.env`), then push a branch
  (dev) or merge main (staging) -- .github/workflows/deploy-env.yml does the rest.

  ngrok.yaml note: `endpoints:` must stay the LAST top-level key for the
  append to land inside the list (true today). The file holds the authtoken;
  this script never prints it.
#>
param(
  [Parameter(Mandatory)][ValidateSet('dev', 'staging')] [string]$Name,
  [Parameter(Mandatory)][int]$Port,
  [Parameter(Mandatory)][ValidateSet('INT', 'STAGING')] [string]$Environment,
  [Parameter(Mandatory)][string]$Hostname,
  [string]$NgrokConfig = 'D:\sydoc\nexora\ngrok.yaml'
)
$ErrorActionPreference = 'Stop'
Import-Module WebAdministration

$dir  = "D:\sydoc\nexora-$Name"
$pool = "nexora-$Name"

# 1. folders -- including the per-request write paths, so the Defender
#    exclusion below covers them from the first request
foreach ($d in @($dir, "$dir\var", "$dir\var\logs\system", "$dir\var\logs\user", "$dir\var\session", "$dir\env")) {
  if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d | Out-Null }
}

# 2. root env selector (robocopy /XF *.env never touches it; deploy-env.yml checks it)
Set-Content -Path "$dir\.env" -Value "ENVIRONMENT=$Environment" -Encoding ASCII

# 3. app pool, identity copied from DefaultAppPool; no CLR (HttpPlatformHandler only)
if (-not (Test-Path "IIS:\AppPools\$pool")) { New-WebAppPool -Name $pool | Out-Null }
$src = Get-ItemProperty 'IIS:\AppPools\DefaultAppPool'
Set-ItemProperty "IIS:\AppPools\$pool" -Name managedRuntimeVersion -Value ''
Set-ItemProperty "IIS:\AppPools\$pool" -Name processModel.identityType -Value $src.processModel.identityType
if ($src.processModel.identityType -eq 'SpecificUser') {
  Write-Warning "DefaultAppPool runs as '$($src.processModel.userName)'. Set the same user + password on IIS:\AppPools\$pool by hand (IIS Manager -> Advanced Settings -> Identity)."
  $acct = $src.processModel.userName
} else {
  $acct = "IIS AppPool\$pool"
}
icacls $dir /grant "${acct}:(OI)(CI)M" /T /Q | Out-Null

# 4. site bound to loopback only
if (-not (Get-Website -Name $pool -ErrorAction SilentlyContinue)) {
  New-Website -Name $pool -PhysicalPath $dir -ApplicationPool $pool -IPAddress 127.0.0.1 -Port $Port | Out-Null
}
Start-Website -Name $pool -ErrorAction SilentlyContinue

# 5. the GitHub runner service mirrors into $dir and restarts the pool
$runner = (Get-CimInstance Win32_Service -Filter "Name LIKE 'actions.runner.%'" | Select-Object -First 1).StartName
if ($runner) {
  icacls $dir /grant "${runner}:(OI)(CI)F" /T /Q | Out-Null
} else {
  Write-Warning "GitHub runner service not found; grant its account Full control on $dir by hand."
}

# 6. Defender: var\ takes a file write per request (sessions, CSV request log)
if (-not ((Get-MpPreference).ExclusionPath -contains "$dir\var")) { Add-MpPreference -ExclusionPath "$dir\var" }

# 7. ngrok endpoint, appended once
$yaml = Get-Content $NgrokConfig -Raw
if ($yaml -notmatch [regex]::Escape("url: https://$Hostname")) {
  $block = @"

  - name: nexora-$Name
    url: https://$Hostname
    upstream:
      url: $Port
"@
  Add-Content -Path $NgrokConfig -Value $block -Encoding UTF8
  Restart-Service ngrok
  (Get-Service ngrok).WaitForStatus('Running', '00:01:00')
  Write-Host "ngrok endpoint added and service restarted."
} else {
  Write-Host "ngrok endpoint for $Hostname already present."
}

Write-Host ""
Write-Host "OK  $dir | pool $pool | 127.0.0.1:$Port | ENVIRONMENT=$Environment | https://$Hostname"
Write-Host "Next: from a dev box  python scripts/env-sync.py --push $Environment.env"
Write-Host "      then push a branch (dev) / merge main (staging)."
