# Remote admin access to SYAPP01 (WinRM)

Today only two ports are reachable from a dev box on the VPN: **445** (SMB — the
`\syapp01\d$` admin share, used by `scripts/env-sync.py`) and **3389** (RDP).
That means files can be read and written remotely, but **no command can be run**
on the box without an interactive RDP session or a push to `main` (the
`self-hosted` GitHub runner in `.github/workflows/deploy.yml` executes there).

**Status (2026-08-25): not reachable yet.** SYAPP01 is configured correctly —
`WinRM` running/Automatic, listening on `0.0.0.0:5985`, NIC profile
`DomainAuthenticated`, `WINRM-HTTP-In-TCP` enabled with `RemoteAddress = Any` —
and `Get-SmbSession` on the server shows the dev box arriving unNATted as
`10.212.134.5`. From that same address 445 connects and 5985 never does, so the
remaining blocker is the VPN/network ACL, not the host. It needs a firewall
request: **permit TCP 5985 from the VPN client pool to 192.168.40.7**. Until
that lands, use the *PROD diagnostics* workflow below.

**Re-checked 2026-09-08:** still the same — `Test-NetConnection syapp01` from the
dev box passes on 445 and 3389, fails on 5985/5986/22. Nothing on the host or in
this repo changes it; the fix is one firewall rule.

## Opening the ACL yourself (Swisscom firewall)

The blocking ACL lives in the **Swisscom hosting/firewall interface** that
fronts syapp01 — not on the host, not in this repo. If you have access to that
interface you can open it without a network-team ticket. Add one inbound rule:

| Field | Value |
|---|---|
| Direction | Inbound |
| Protocol | TCP |
| Port | `5985` |
| Source | `10.212.134.5/32` (the dev box, tightest) or `10.212.134.0/24` (the VPN pool) |
| Destination | `192.168.40.7` (syapp01) |

`10.212.134.5` is the address the dev box arrives as un-NATted over SMB
(`Get-SmbSession` on the server), so it is the correct source. Use the `/32` for
least privilege; widen to the `/24` only if the VPN hands out changing addresses.

Nothing else is needed — the host side is already done (WinRM running, listening
on `0.0.0.0:5985`, domain NIC profile, `WINRM-HTTP-In-TCP` enabled for
`RemoteAddress = Any`). After the rule is live, verify from the dev box:

```powershell
Test-NetConnection syapp01 -Port 5985      # TcpTestSucceeded : True
Test-WSMan -ComputerName syapp01           # returns product version XML
Invoke-Command -ComputerName syapp01 { $env:COMPUTERNAME }   # -> SYAPP01
```

All three green means the "What it is used for" commands below work directly —
no Actions round-trip, no PR.

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

## Interim: the PROD diagnostics workflow

The `self-hosted` GitHub Actions runner already executes **on** SYAPP01 (see the
`robocopy` to the local `D:\sydoc\nexora` in `.github/workflows/deploy.yml`),
which is command execution the ACL does not touch.
`.github/workflows/prod-diagnostics.yml` borrows it for a fixed, read-only
sweep: `app.log` tail, IIS app-pool/site state, PROD env **key names** (never
values), disk + uptime, and the outage-monitor state file.

```powershell
gh workflow run "PROD diagnostics" --ref main -f log_lines=200
gh run watch   # then: gh run view --log
```

Output lands in the Actions run log, so a run shares that slice of `app.log`
with everyone holding repo read for the retention window — fine for an
internal team, worth a thought before tailing 5000 lines. Env **key names**
are printed; values never leave the server.

It takes no command input by design — it is a diagnostic window, not a remote
shell. `workflow_dispatch` only registers once the file is on the **default
branch**, so it cannot be triggered from a feature branch before the merge.
When the ACL opens, `Invoke-Command` supersedes it and this workflow can go.
