# Remote admin access to SYAPP01 (WinRM)

Today only two ports are reachable from a dev box on the VPN: **445** (SMB — the
`\syapp01\d$` admin share, used by `scripts/env-sync.py`) and **3389** (RDP).
That means files can be read and written remotely, but **no command can be run**
on the box without an interactive RDP session or a push to `main` (the
`self-hosted` GitHub runner in `.github/workflows/deploy.yml` executes there).

WinRM closes that gap with no extra software: it ships with Windows and
PowerShell speaks it natively (`Invoke-Command -ComputerName syapp01 { ... }`).
Both machines are domain-joined (`dom.local`), so authentication is Kerberos —
no `TrustedHosts`, no certificates, no stored credentials.

## One-time setup on SYAPP01

RDP in as a domain admin, open an **elevated** PowerShell, then:

```powershell
Enable-PSRemoting -Force

# The firewall exception only opens to the whole network on a domain profile.
# If this prints anything other than DomainAuthenticated, fix the NIC profile first.
Get-NetConnectionProfile | Select-Object InterfaceAlias, NetworkCategory

# Allow the VPN client pool (preferred). Widen to -RemoteAddress Any only if the
# pool range is unknown — WinRM still requires local Administrators membership.
Set-NetFirewallRule -Name WINRM-HTTP-In-TCP -Enabled True -RemoteAddress 10.212.134.0/24
```

`Enable-PSRemoting` starts the `WinRM` service, sets it to `Automatic`, and
registers the HTTP listener on port **5985**. Traffic is encrypted at the
message level by Kerberos even though the transport is HTTP; HTTPS (5986) needs
a certificate and buys nothing extra inside the domain.

## Verify from the dev box

```powershell
Test-WSMan -ComputerName syapp01
Invoke-Command -ComputerName syapp01 { $env:COMPUTERNAME; $PSVersionTable.PSVersion }
```

## What it is used for

```powershell
# tail the app log (see docs/howto/outage-monitor.md)
Invoke-Command -ComputerName syapp01 { Get-Content D:\sydoc\nexora\var\logs\system\app.log -Tail 50 }

# app pool state / recycle after a deploy (docs/howto/iis.md)
Invoke-Command -ComputerName syapp01 { Get-WebAppPoolState nexora }

# which env keys PROD actually has (values stay on the server)
Invoke-Command -ComputerName syapp01 {
    (Get-Content D:\sydoc\nexora\env\PROD.env) -match '^\w' -replace '=.*', ''
}
```

Everything file-shaped keeps working over SMB — `scripts/env-sync.py` needs no
change. WinRM is only for the things that must *execute* on the server.

## If it stops working

| Symptom | Cause |
|---------|-------|
| `WSManFault` … *Firewallausnahme* | Service off, or the rule is scoped to the local subnet (NIC profile is Public/Private). |
| `Access is denied` | The calling account is not in the server's local `Administrators` group. |
| `Kerberos … cannot find the computer` | Name resolved but SPN mismatch — use the FQDN `syapp01.dom.local`. |
