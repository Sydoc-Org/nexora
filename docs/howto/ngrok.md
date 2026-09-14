# ngrok setup (SYAPP01) — three endpoints

One ngrok agent (Windows service `ngrok`) on SYAPP01 fronts all three hosted
environments (#338). It reads `D:\sydoc\nexora\ngrok.yaml`, which is **not** in
git (it holds the authtoken) and is in `deploy-env.yml`'s robocopy `/XF` list, so
deploys never touch it. Deploys also never stop the service any more: a stopped
app pool answers 503 while the mirror runs, which is enough.

| host | local upstream | folder | `ENVIRONMENT` | deployed by |
|---|---|---|---|---|
| `nexora.sydoc.ch` | `http://localhost:80` (IIS Default Web Site, `DefaultAppPool`) | `D:\sydoc\nexora` | `PROD` | push of a `v*` tag |
| `staging-nexora.sydoc.ch` | `http://127.0.0.1:8082` (site `nexora-staging`) | `D:\sydoc\nexora-staging` | `STAGING` | merge to `main` + 01:30 nightly |
| `dev-nexora.sydoc.ch` | `http://127.0.0.1:8081` (site `nexora-dev`) | `D:\sydoc\nexora-dev` | `INT` | any other branch push (last push wins) |

## DNS (cyon)

`sydoc.ch` DNS stays at cyon. Each host is a CNAME to its own ngrok edge target
(ngrok dashboard → *Domains*; the target is per domain):

| record | CNAME target |
|---|---|
| `nexora` | `dzpsykqcwgqzfk1c.zgzyk2x2s1c7jrr8.ngrok-cname.com` |
| `dev-nexora` | `3vvfskuc7isen9djp.zgzyk2x2s1c7jrr8.ngrok-cname.com` |
| `staging-nexora` | `62ubvmwfstncuu83.zgzyk2x2s1c7jrr8.ngrok-cname.com` |

Cost: the pay-as-you-go plan bills each custom domain at $0.01 per active hour
(≈ $7.30/month per always-on host); endpoints themselves are free.

## `ngrok.yaml` shape

```yaml
version: 3
agent:
  authtoken: <redacted>
endpoints:
  - name: nexora-app
    url: https://nexora.sydoc.ch
    upstream:
      url: 80
    traffic_policy:          # bot block, prod only
      on_http_request: [...]
  - name: nexora-dev
    url: https://dev-nexora.sydoc.ch
    upstream:
      url: 8081
  - name: nexora-staging
    url: https://staging-nexora.sydoc.ch
    upstream:
      url: 8082
```

`ops/setup-env.ps1` appends the dev/staging entries (idempotent) and restarts
the service; it assumes `endpoints:` is the last top-level key.

## Adding a host

RDP to SYAPP01, elevated PowerShell, once per environment:

```powershell
cd D:\sydoc\tools
.\setup-env.ps1 -Name dev     -Port 8081 -Environment INT     -Hostname dev-nexora.sydoc.ch
.\setup-env.ps1 -Name staging -Port 8082 -Environment STAGING -Hostname staging-nexora.sydoc.ch
```

(The script ships in the repo as `ops/setup-env.ps1`; copy it to `D:\sydoc\tools`
first — `tools\` is outside the deploy mirror.) Then push the env file from a
dev box: `python scripts/env-sync.py --push INT.env` / `--push STAGING.env`.

## Service commands

```powershell
cd /d "D:\sydoc\tools\ngrok"
ngrok start --config="D:\sydoc\nexora\ngrok.yaml" --all      # run in the foreground
ngrok service install --config="D:\sydoc\nexora\ngrok.yaml"  # once, elevated
ngrok service start
Restart-Service ngrok                                        # after editing ngrok.yaml
```

Cloudflare Tunnel was evaluated and parked — see `docs/howto/cloudflare-tunnel.md`.
