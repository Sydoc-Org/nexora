# Cloudflare Tunnel (SYAPP01) — replaces ngrok

Public entry for nexora: `https://nexora.sydoc.ch` → Cloudflare edge →
`cloudflared` Windows service on SYAPP01 (outbound-only connection, no firewall
hole, same shape as the ngrok agent) → local IIS on port 80 → waitress.

Why the switch: the free plan has **no connection/bandwidth caps and no time
limit** (replaces the paid ngrok plan), adds edge DDoS/WAF in front of SYAPP01,
and keeps serving users on the hostname they already use. Costs appear only for
opt-in extras we don't need (Cloudflare Access beyond 50 users at $7/user/mo,
Pro-plan WAF).

**Starting point (recorded 2026-08-25):** `nexora.sydoc.ch` is already the
live URL — a CNAME at cyon to the ngrok edge
(`dzpsykqcwgqzfk1c.zgzyk2x2s1c7jrr8.ngrok-cname.com`; keep this string, it is
the rollback target). `sydoc.ch` DNS is hosted at cyon (`ns1.cyon.ch` /
`ns2.cyon.ch`). Because the hostname stays the same, users and `/api/v1`
clients notice nothing at cutover.

The installer is pre-staged on the server:
`D:\sydoc\tools\cloudflared\` holds `cloudflared.msi` and `install-tunnel.ps1`.

## Phase 1 — move the `sydoc.ch` zone to Cloudflare (no behaviour change)

1. Cloudflare account → *Add a site* → `sydoc.ch` → **Free** plan. Cloudflare
   scans and imports the cyon records.
2. **Compare the imported records against cyon's zone line by line** — above
   all MX/SPF/DKIM/DMARC (company mail!) and any other hosts on the domain.
   Add anything the scan missed. Set every record to **DNS only** (grey
   cloud) for now, including the existing `nexora` CNAME to the ngrok edge —
   imported unchanged, so the NS flip changes nothing.
3. At the registrar (cyon, or wherever `sydoc.ch` is registered): change the
   nameservers to the two Cloudflare assigns. Propagation is usually minutes,
   worst case ~24 h. Until the zone shows *Active*, nothing else works.
4. Verify: `Resolve-DnsName nexora.sydoc.ch` still answers the ngrok CNAME;
   mail still flows. The site is still 100% on ngrok.

## Phase 2 — tunnel connector on SYAPP01

1. Zero Trust → *Networks* → *Tunnels* → **Create a tunnel** → type
   *Cloudflared*, name `nexora-syapp01`. Copy the token from the install
   command the wizard shows (the long string after `service install`).
2. On SYAPP01 (RDP, elevated PowerShell) — everything is pre-staged:

   ```powershell
   cd D:\sydoc\tools\cloudflared
   .\install-tunnel.ps1 -Token <TUNNEL_TOKEN>
   ```

   The token is a credential — paste it into that command only, never into
   git. The dashboard shows the connector as *HEALTHY* within ~30 s.
3. ngrok is untouched and still serving all traffic.

## Phase 3 — verify on a test hostname, then cut over

1. Tunnel → *Public Hostname* → add `nexora-test.sydoc.ch` → service
   `http://localhost:80`. (Cloudflare creates the proxied CNAME
   automatically.)
2. Verify through the test hostname:
   - `https://nexora-test.sydoc.ch/nexora/login` → 200, log in, click around.
   - CSV log (`var/logs/user/...`) shows your real client IP (Cloudflare
     appends it to `X-Forwarded-For`; waitress trims the header to that one
     trusted hop and the app reads the rightmost — unchanged from ngrok, see
     `nx_lib/extensions.py`).
   - One `/api/v1/*` call with a real API key.
3. **Cutover:** add public hostname `nexora.sydoc.ch` → `http://localhost:80`.
   The dashboard warns it will replace the existing (ngrok) CNAME — confirm.
   That DNS swap *is* the cutover; sessions survive (same hostname, same
   cookies). Then delete the `nexora-test` hostname.
4. Watch `ops/outage_monitor.py`'s public-site probe and the app logs for a
   day; ngrok stays installed as instant rollback.

## Rollback

Delete the tunnel's `nexora.sydoc.ch` public hostname and recreate the CNAME:
`nexora` → `dzpsykqcwgqzfk1c.zgzyk2x2s1c7jrr8.ngrok-cname.com`, **DNS only**
(grey cloud — the ngrok edge does its own TLS for the custom domain). ngrok
service was never stopped, so that is the whole rollback.

## Zone settings (once, after cutover)

- **Always Use HTTPS**: on.
- **Bot Fight Mode: leave OFF** — `/api/v1/*` Bearer clients share the
  hostname and it blocks non-browser clients.
- WAF → custom rule replacing ngrok's bot policy (`ngrok.yaml` blocked
  Googlebot/Bingbot/ChatGPT-User/GPTBot/Bytespider): *User Agent contains*
  any of those names → Block. Free tier allows 5 custom rules.
- SSL/TLS: leave the zone default; for a tunnel-published hostname the
  edge↔origin leg is the tunnel itself.

## Decommission ngrok (after a quiet week)

```powershell
ngrok service stop
ngrok service uninstall
```

Cancel the paid ngrok plan, delete `docs/howto/ngrok.md` and drop
`ngrok.yaml` + the `ngrok` service handling from `deploy.yml` (it is
tunnel-agnostic and keeps working either way until then).

## Operations

- Service: `Get-Service cloudflared`; logs in the Windows Event Log (source
  `cloudflared`); auto-reconnects after network blips.
- Tunnel health: Zero Trust → Networks → Tunnels.
- Deploys: `.github/workflows/deploy.yml` stops/starts whichever of
  `ngrok`/`cloudflared` exists around the robocopy mirror — nothing to change
  at cutover.
- The outage monitor's public-site probe keeps working unchanged (same URL).
