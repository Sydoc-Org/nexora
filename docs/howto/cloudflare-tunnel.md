# Cloudflare Tunnel (SYAPP01) — replaces ngrok

Public entry for nexora: `https://nexora.sydoc.ch` → Cloudflare edge →
`cloudflared` Windows service on SYAPP01 (outbound-only connection, no firewall
hole, same shape as the ngrok agent) → local IIS on port 80 → waitress.

Why the switch: the free plan has **no connection/bandwidth caps and no time
limit** (replaces the paid ngrok plan), adds edge DDoS/WAF in front of SYAPP01,
and serves users on our own domain. Costs appear only for opt-in extras we
don't need (Cloudflare Access beyond 50 users at $7/user/mo, Pro-plan WAF).

Status: **prepared, not yet cut over.** ngrok keeps running in parallel until
the Cloudflare hostname is verified; rollback at any point = users keep using
the ngrok URL. `docs/howto/ngrok.md` stays valid until the ngrok service is
removed.

## One-time setup

1. **Zone**: add `sydoc.ch` to the Cloudflare account (or delegate just
   `nexora.sydoc.ch` via NS records if the parent zone stays where it is).
   Wait until the zone shows *Active*.
2. **Create the tunnel** (remotely managed — config lives in the dashboard,
   only a token lives on the server):
   Zero Trust → Networks → Tunnels → *Create a tunnel* → type **Cloudflared**,
   name `nexora-syapp01`. The wizard shows a Windows install command with the
   tunnel token — copy it.
3. **Install on SYAPP01** (elevated PowerShell):

   ```powershell
   winget install --id Cloudflare.cloudflared
   cloudflared service install <TUNNEL_TOKEN>
   Start-Service cloudflared
   ```

   The token is a credential: paste it only into the service install, never
   into git. No YAML file is needed for a remotely-managed tunnel.
4. **Public hostname** (tunnel → *Public Hostname* tab):
   `nexora.sydoc.ch` → service `http://localhost:80`. Path stays untouched, so
   the app keeps living under `/nexora` exactly as with ngrok
   (`PrefixMiddleware` unchanged).
5. **Zone settings** (once, under the `sydoc.ch` zone):
   - SSL/TLS mode **Flexible is wrong; use Full** is wrong too for tunnels —
     for a tunnel-published hostname the edge↔origin leg *is* the tunnel, so
     just leave the zone default and enable **Always Use HTTPS**.
   - Security → keep **managed DDoS** on (default). Leave **Bot Fight Mode
     OFF** — the external machine API (`/api/v1/*`, Bearer clients) flows
     through this hostname and Bot Fight Mode blocks non-browser clients.

## Verify before cutover

```powershell
# On any machine:
curl.exe -sS -o NUL -w "%{http_code}`n" https://nexora.sydoc.ch/nexora/login   # expect 200
```

- Log in via the new hostname, check `var/logs/user/.../nexora_logs.csv` shows
  your real client IP (Cloudflare appends it to `X-Forwarded-For`; the app
  reads the leftmost hop — unchanged from ngrok, see `nx_lib/extensions.py`).
- Run one `/api/v1/*` call with a real API key through the new hostname.

## Cutover / rollback

- Cutover: tell users / update bookmarks + API consumers to
  `https://nexora.sydoc.ch`, then decommission ngrok
  (`ngrok service stop; ngrok service uninstall`) and delete the paid plan.
- Rollback: `Stop-Service cloudflared` — ngrok is still running; nothing else
  to undo.
- The deploy workflow stops/starts **both** services around the robocopy
  mirror when they exist (`.github/workflows/deploy.yml`), so deploys work
  identically before, during and after the transition.

## Operations

- Service: `Get-Service cloudflared`, logs in the Windows Event Log
  (source `cloudflared`), auto-reconnects after network blips.
- Tunnel health: Zero Trust → Networks → Tunnels (shows connector status).
- The outage monitor (`ops/outage_monitor.py`) probes the public site; once
  cut over, point its public-site URL at `https://nexora.sydoc.ch` (env-based;
  see `docs/howto/outage-monitor.md`).
